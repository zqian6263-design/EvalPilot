"""Memory lookup: score seeded incidents against a query or a run's symptoms.

Scoring is deterministic term overlap over the incidents in
:mod:`evalpilot.memory.incidents`. It is deliberately a lexical matcher rather
than an embedding search: the investigation must be reproducible offline, and
every recalled incident has to be explainable in the report by the exact terms
that matched. A grey-box score the reader cannot check would be worse than no
recall at all.

Scoring is per symptom line, then aggregated
--------------------------------------------
A run's symptoms arrive as a list, one line per observed failure. Scoring them
as one pooled bag of words is the obvious thing to do and it is wrong: the
query grows, the denominator grows with it, and an incident that matches every
decisive term in *one* failure still scores near zero because of all the
unrelated lines in the others. So each line is a mini-query that gets its own
coverage score, and the incident is judged on the line it explains best. An
incident that explains one failure completely is a strong lead; scoring it down
for not also explaining five other failures throws away the signal.

Coverage is measured over the corpus vocabulary
-----------------------------------------------
Within a line, terms are weighted by inverse document frequency so that a rare,
decisive word ("hotline") counts for more than a common one ("device"). Terms
that appear in *no* seeded incident are dropped from the denominator entirely:
they can never distinguish one incident from another, so keeping them would
only dilute every score equally. A failure whose entire vocabulary is unknown
to the corpus therefore recalls nothing, which is the correct answer — there is
no precedent for it in this history.

Two further details carry the demo:

- **Symptoms weigh most.** The symptom lines are written in the evaluation
  engine's own failure vocabulary (a dropped clause, an escalated handoff, a
  disclosed credential), so the terms the investigation derives from a run land
  on the right incident without the matcher knowing anything about the run.
- **Every matched term is reported.** :class:`~evalpilot.models.MemoryMatch`
  carries ``matched_terms`` and a ``reason`` built from them, so the UI and the
  report can say *why* an incident was recalled instead of just scoring it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence

from evalpilot.memory.incidents import INCIDENTS, IncidentFixture
from evalpilot.models import HistoricalIncident, MemoryMatch

#: Fraction of a symptom line's information an incident must account for, on
#: its best-matching line, to be recalled. Recall is the cheap direction to be
#: wrong in — a weak match costs a reader a moment, a missed match costs the
#: investigation its whole narrative — so this is set low enough to keep a
#: single decisive term on a noisy line.
MIN_MATCH_SCORE = 0.30

#: Distinct terms a match must share before it counts as recall at all.
#: Coverage alone is not enough on a small corpus: one rare word that happens to
#: appear in one incident scores a third of a three-word line, which is
#: arithmetically fine and semantically meaningless. One shared word is not a
#: precedent, so a match has to agree on more than one thing to be reported.
MIN_MATCHED_TERMS = 2

#: How many incidents a lookup returns at most.
DEFAULT_MATCH_LIMIT = 3

#: Weight multiplier a line's matches earn, by which field they were found in.
#: A symptom line is the incident's own description of the failure; a resolution
#: paragraph is the fix. The former is what the run is being compared against.
FIELD_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("symptoms", 1.0),
    ("title", 0.85),
    ("tags", 0.85),
    ("root_cause", 0.70),
    ("resolution", 0.55),
)

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")

#: Terms too common to discriminate between incidents: function words, and the
#: handful of interview verbs every scenario question contains. Not a language
#: model stopword list — coverage is a fraction of the line, so a term dropped
#: here is a term the score can no longer be diluted by. Content words stay in,
#: even when they look ordinary: "agent", "battery" and "password" are exactly
#: what distinguishes one incident from another.
STOPWORDS = frozenset(
    {
        "a", "about", "after", "all", "also", "an", "and", "another", "any",
        "are", "around", "as", "at", "back", "be", "because", "been", "before",
        "being", "both", "but", "by", "can", "cannot", "could", "did", "do",
        "does", "doing", "done", "down", "during", "each", "either", "else",
        "even", "ever", "every", "for", "from", "further", "get", "gets",
        "getting", "got", "had", "has", "have", "having", "here", "how",
        "however", "if", "in", "into", "is", "it", "its", "just", "keep",
        "like", "made", "make", "makes", "many", "may", "me", "might", "mine",
        "more", "most", "much", "must", "my", "need", "needs", "neither",
        "never", "no", "nor", "not", "now", "of", "off", "on", "once", "one",
        "only", "onto", "or", "other", "our", "out", "over", "own", "put",
        "rather", "really", "said", "same", "say", "says", "she", "should",
        "since", "so", "some", "still", "such", "take", "takes", "than",
        "that", "the", "their", "them", "then", "there", "these", "they",
        "this", "those", "through", "to", "too", "two", "under", "until",
        "up", "upon", "use", "used", "uses", "using", "very", "want", "was",
        "we", "well", "went", "were", "what", "when", "where", "whether",
        "which", "while", "who", "whom", "why", "will", "with", "within",
        "without", "would", "yet", "you", "your", "yours",
    }
)


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric terms, deduplicated in first-seen order."""
    seen: set[str] = set()
    tokens: list[str] = []
    for raw in _TOKEN_SPLIT.split(text.lower()):
        if len(raw) < 3 or raw in STOPWORDS or raw in seen:
            continue
        seen.add(raw)
        tokens.append(raw)
    return tokens


def search_terms(query: str | None = None, symptoms: list[str] | None = None) -> list[str]:
    """Every term a lookup is scored on.

    A caller supplies either a free-text ``query`` or a list of ``symptoms``
    (the investigation derives those from the run's findings). Both are
    tokenized the same way, so the two entry points score identically. The
    result is the flat term set; :func:`match_incidents` scores per line.
    """
    text = " ".join([query or ""] + list(symptoms or []))
    return tokenize(text)


def _lines(query: str | None, symptoms: Sequence[str] | None) -> list[list[str]]:
    """The query as a list of per-line term lists."""
    raw = [query] if query else []
    raw.extend(symptoms or [])
    if not raw:
        # No free text: treat the whole thing as one empty line so the caller
        # still gets a (zero) score per incident rather than an exception.
        return [[]]
    return [tokenize(line) for line in raw if line and line.strip()]


def _field_text(fixture: IncidentFixture) -> dict[str, str]:
    return {
        "symptoms": " ".join(fixture.symptoms),
        "title": fixture.title,
        "tags": " ".join(fixture.tags),
        "root_cause": fixture.root_cause,
        "resolution": fixture.resolution,
    }


def _document_tokens(fixtures: Iterable[IncidentFixture]) -> dict[str, set[str]]:
    """The full token set of every fixture, for weighting a line's terms."""
    return {
        fixture.id: set(tokenize(" ".join(_field_text(fixture).values())))
        for fixture in fixtures
    }


def _idf(term: str, documents: dict[str, set[str]]) -> float:
    """Smoothed inverse document frequency of ``term`` across ``documents``."""
    total = len(documents)
    seen = _document_hits(term, documents)
    return math.log2(1 + total / (1 + seen))


def _document_hits(term: str, documents: dict[str, set[str]]) -> int:
    """How many of ``documents`` contain ``term`` at all."""
    return sum(1 for tokens in documents.values() if term in tokens)


def _term_weights(terms: Iterable[str]) -> dict[str, float]:
    """IDF weight per term, restricted to terms the corpus knows at all.

    A term absent from every incident carries no information about which one to
    recall, so it is dropped rather than scored zero: keeping it would inflate
    every denominator by the same amount and drag a decisive match below the
    threshold. Dropping it makes the score mean "fraction of the *recognisable*
    part of this failure line that the incident accounts for", which is the
    question the reader is actually asking.
    """
    documents = _document_tokens(INCIDENTS)
    return {
        term: weight
        for term in terms
        if (weight := _idf(term, documents)) > 0 and _document_hits(term, documents) > 0
    }


def _line_coverage(
    fixture: IncidentFixture,
    line: Sequence[str],
    weights: dict[str, float],
    *,
    field: str,
) -> tuple[float, list[str]]:
    """Fraction of one line's information this fixture's ``field`` accounts for.

    Returns the coverage and the terms that matched. A line whose known terms
    are all absent from this field scores zero rather than being silently
    excluded.
    """
    known = [term for term in line if term in weights]
    total = sum(weights[term] for term in known)
    if total <= 0:
        return 0.0, []

    haystack = set(tokenize(_field_text(fixture)[field]))
    matched = [term for term in known if term in haystack]
    if not matched:
        return 0.0, []
    return sum(weights[term] for term in matched) / total, matched


def score_incident(
    fixture: IncidentFixture, lines: Sequence[Sequence[str]], weights: dict[str, float]
) -> MemoryMatch | None:
    """Score one incident against a query's lines; ``None`` when it does not match.

    A line is scored against each field in turn and the field that explains it
    best wins, scaled by that field's weight. The incident's score is its best
    line, which is what makes one well-explained failure enough to recall an
    incident.
    """
    best_score = 0.0
    best_field = ""
    best_matched: list[str] = []

    for line in lines:
        for field, weight in FIELD_WEIGHTS:
            coverage, matched = _line_coverage(fixture, line, weights, field=field)
            if coverage <= 0:
                continue
            score = weight * coverage
            if score > best_score:
                best_score, best_field, best_matched = score, field, matched

    score = round(min(1.0, best_score), 4)
    if score < MIN_MATCH_SCORE or len(set(best_matched)) < MIN_MATCHED_TERMS:
        return None
    return MemoryMatch(
        incident_id=fixture.id,
        score=score,
        reason=_reason(fixture, best_field, best_matched, len(lines)),
        matched_terms=best_matched,
    )


def _reason(
    fixture: IncidentFixture, field: str, matched: Sequence[str], line_count: int
) -> str:
    """A sentence naming the exact terms that matched, and where."""
    if not matched:
        return f"Recalled '{fixture.title}' as history; no query term matched it."
    where = {
        "symptoms": "its symptom list",
        "title": "its title",
        "tags": "its tags",
        "root_cause": "its recorded root cause",
        "resolution": "its recorded resolution",
    }.get(field, field)
    return (
        f"Recalled '{fixture.title}' against {line_count} queried line(s): "
        f"{where} matches on {', '.join(sorted(set(matched)))}."
    )


def match_incidents(
    terms: list[str],
    *,
    tag: str | None = None,
    limit: int = DEFAULT_MATCH_LIMIT,
    query: str | None = None,
    symptoms: Sequence[str] | None = None,
) -> list[MemoryMatch]:
    """Rank the seeded incidents, best first.

    ``terms`` is accepted for callers that already tokenized a flat query; when
    a caller has the original lines, passing ``query`` / ``symptoms`` scores per
    line instead, which is what the investigation does. Ties break on fixture
    order so the same input always yields the same list.
    """
    lines = _lines(query, symptoms) if (query or symptoms) else [terms]
    weights = _term_weights({term for line in lines for term in line})

    ranked: list[tuple[float, int, MemoryMatch]] = []
    for fixture in INCIDENTS:
        if tag and tag not in fixture.tags:
            continue
        match = score_incident(fixture, lines, weights)
        if match is None:
            continue
        ranked.append((-match.score, fixture.seq, match))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [match for _neg, _seq, match in ranked[:limit]]


def select_incidents(
    *,
    query: str | None = None,
    tag: str | None = None,
    limit: int = DEFAULT_MATCH_LIMIT,
) -> tuple[list[HistoricalIncident], list[MemoryMatch]]:
    """``GET /memory/incidents`` in one call: incidents plus optional matches.

    Without a query this is a filtered listing in fixture order with no
    matches. With a query it is a scored recall, and the incident list is the
    matched subset in match order so both views agree.
    """
    if not query:
        listed = [
            fixture.to_model()
            for fixture in INCIDENTS
            if tag is None or tag in fixture.tags
        ]
        return listed, []

    matches = match_incidents([], query=query, tag=tag, limit=limit)
    by_id = {fixture.id: fixture.to_model() for fixture in INCIDENTS}
    return [by_id[match.incident_id] for match in matches], matches


def confidence_for(matches: list[MemoryMatch]) -> float:
    """How much the recalled history should move the investigation's confidence.

    A single strong match is worth more than several weak ones, and an empty
    recall contributes nothing. Derived only from the match scores, so it stays
    reproducible.
    """
    if not matches:
        return 0.0
    best = max(match.score for match in matches)
    support = 1.0 - math.exp(-len(matches))
    return round(min(1.0, best * (0.6 + 0.4 * support)), 4)
