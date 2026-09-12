/**
 * The market fixture — the market surface's data.
 *
 * This file is the *only* place commercial numbers are allowed to be typed.
 * A component that hard-codes one has made a claim the model cannot check, and
 * `marketFixtures.test.ts` fails on the numbers it can see.
 *
 * Everything here is either zero (traction), a hypothesis (pricing), or a
 * published position (the criteria). Nothing here is a result.
 */

import type { SourceLabel, TractionKey } from './marketModel'
import { SOURCE_LABELS } from './marketModel'

// ------------------------------------------------------------------ criteria --

/**
 * The five official competition criteria, verbatim from the brief.
 *
 * `max` is 20 for every criterion and the total is therefore 100. The type
 * pins it: a sixth criterion, or a different weight, would be a different
 * competition, and this surface must not quietly re-weight one.
 */
export interface Criterion {
  id: 'technical' | 'market' | 'innovation' | 'llm' | 'track'
  /** The criterion as published. Do not paraphrase. */
  official: string
  /** The question a judge is actually answering. */
  question: string
  max: 20
  /** The team's own score. Not a judge's. */
  selfScore: number
  /** How much the team trusts its own score. */
  confidence: 'high' | 'medium' | 'low' | 'very-low'
  /** What backs the score today. */
  evidence: string
  /** The distance to the target, in the terms of the actions below. */
  gap: string
  target: number
  /** The exact actions that would close the gap. */
  actions: readonly ImprovementAction[]
}

export interface ImprovementAction {
  id: string
  what: string
  /** How anyone can check it was done. */
  verification: string
}

export const CRITERIA: readonly Criterion[] = [
  {
    id: 'technical',
    official: '技术可行性 — Technical feasibility',
    question: 'Can this be built and demonstrated, by these people, in the time available?',
    max: 20,
    selfScore: 16,
    confidence: 'high',
    evidence:
      'The MVP builds and its suites are green: production build clean, frontend 150 tests passing, backend 115 passing, and a 31/31 end-to-end check recorded. The scenario is deliberately narrow and the demo falls back to a labelled offline corpus rather than dead-ending.',
    gap:
      'Three claims carried in the pitch are not backed by an artifact, and the `typecheck` script is broken on a clean checkout of `main` too. No third party has run the clean-start checklist.',
    target: 18,
    actions: [
      {
        id: 'T1',
        what: 'Fix the `typecheck` script — it pairs `--noEmit false` with `allowImportingTsExtensions` and cannot pass. Do not fix it by honouring `--noEmit` under `-b`: that emits sibling `.js` files and Vite then resolves a generated `vite.config.js` over the real one.',
        verification:
          '`npm --prefix frontend run typecheck` exits 0, `npm run build` still exits 0, and `git status` shows no stray `.js` under `src/`.',
      },
      {
        id: 'T2',
        what: 'Either delete the “reproducible across repeated runs” claim or run the same comparison twice and record both reports.',
        verification: 'Two report artifacts, comparable byte for byte.',
      },
      {
        id: 'T3',
        what: 'Back the statistical-power claim in the backend README with a committed measurement, or remove it.',
        verification: 'A committed command with its output, or a deleted line.',
      },
      {
        id: 'T4',
        what: 'Run the clean-start checklist on a machine that did not build the product.',
        verification: 'The transcript of the run, failures left in.',
      },
    ],
  },
  {
    id: 'market',
    official: '市场可行性 — Market feasibility',
    question: 'Is there a buyer, a budget, a recurring need, and a route to them?',
    max: 20,
    selfScore: 8,
    // The score is low and the confidence in it is the opposite of low: we are
    // certain there is no evidence, because there is none to be uncertain about.
    confidence: 'very-low',
    evidence:
      'A working product and a structured strategy hypothesis: a named ICP, buyer, trigger, alternatives analysis, pricing hypothesis, an adjustable ROI model, a GTM sequence and a 90-day plan with kill conditions. Zero of it is externally tested.',
    gap:
      'No customer conversations, no design partner, no pilot, no paying customer, no revenue, no quoted price, no validated figure of any kind. No engineering action moves this score.',
    target: 13,
    actions: [
      {
        id: 'M1',
        what: 'Complete ten ICP conversations, each answering whether the trigger fired in the last six months.',
        verification: 'Ten written notes, one per conversation, with the trigger question answered explicitly.',
      },
      {
        id: 'M2',
        what: 'Extract two retrospective numbers from those calls: how often releases regress, and what one bad release costs.',
        verification: 'Two real values replacing two assumptions in the ROI model.',
      },
      {
        id: 'M3',
        what: 'Confirm or kill the budget-line hypothesis.',
        verification: 'A named budget line from a real conversation, or a written “no such line exists”.',
      },
      {
        id: 'M4',
        what: 'Secure one design partner who has already had the trigger fire.',
        verification: 'A signed agreement naming the application and the corpus, even at zero price.',
      },
      {
        id: 'M5',
        what: 'Re-run the tool on that partner’s already-shipped release and compare the verdict to what actually happened.',
        verification: 'A retro-diagnosis artifact — agreement or disagreement. Disagreement is a product bug and a finding.',
      },
    ],
  },
  {
    id: 'innovation',
    official: '综合创新性 — Comprehensive innovation',
    question: 'Is the core idea non-obvious, and is it the product’s substance rather than a wrapper?',
    max: 20,
    selfScore: 14,
    confidence: 'medium',
    evidence:
      'Causal comparison by matched scenario with controlled difficulty; counterfactual replay that attributes a failure to a specific intervention; recalled incident fingerprints; and an aggregate verdict permitted to come back inconclusive. Every finding carries evidence ids and a rationale.',
    gap:
      'The mechanism is standard statistics, so the innovation is design discipline rather than novel technique. The counterfactual replay has never been checked against a real defect, and the memory asset has no real history in it.',
    target: 17,
    actions: [
      {
        id: 'I1',
        what: 'Run the retro-diagnosis on a real shipped release and publish the result whether or not it agrees.',
        verification: 'An artifact comparing the tool’s verdict with the known outcome.',
      },
      {
        id: 'I2',
        what: 'Publish a head-to-head against an aggregate-score-delta tool on the same candidate and corpus.',
        verification: 'Two verdicts side by side, including the case where they disagree.',
      },
      {
        id: 'I3',
        what: 'Restate the innovation claim without the overloaded word “causal” and check whether it survives.',
        verification: 'The rewritten claim in the pitch; if it collapses, the pitch was leaning on the word.',
      },
      {
        id: 'I4',
        what: 'Disclose the engine’s statistical power limit as a stated product property, with the minimum case count derived.',
        verification: 'A stated minimum-N and its derivation.',
      },
    ],
  },
  {
    id: 'llm',
    official: 'AI大模型融合 — AI large-model integration',
    question: 'Is the model load-bearing, are its roles explicit, and does it degrade honestly when absent?',
    max: 20,
    selfScore: 15,
    confidence: 'medium',
    evidence:
      'A frozen provider seam with an OpenAI-compatible endpoint and schema-validated JSON; three named roles — planner, judge, report narrative; structured integration with `source`, `model` and call id on every generated step; explicit deterministic fallback with a recorded reason; keys never returned by the runtime endpoint; no chain-of-thought displayed.',
    gap:
      'No recorded successful call to a real model, no judge validated against a human, no second provider, and no measured token cost. Every LLM-shaped output in the repository is fixture data.',
    target: 18,
    actions: [
      {
        id: 'L1',
        what: 'Record one live run against a real endpoint and commit the resulting report artifact.',
        verification: 'A committed report carrying a model id and a call id on the generated steps.',
      },
      {
        id: 'L2',
        what: 'Record one deliberate failure — invalid key or forced timeout — showing the deterministic fallback with its reason.',
        verification: 'The fallback reason visible in the artifact.',
      },
      {
        id: 'L3',
        what: 'Handle judge-versus-check disagreement explicitly: show both readings rather than merging them.',
        verification: 'A fixture where they disagree, rendered as two rows.',
      },
      {
        id: 'L4',
        what: 'Measure tokens and cost for one full comparison and put the number into the pricing hypothesis.',
        verification: 'One measured number replacing one assumption.',
      },
      {
        id: 'L5',
        what: 'Run the same comparison against a second OpenAI-compatible provider.',
        verification: 'Two artifacts from two providers against the same contract.',
      },
    ],
  },
  {
    id: 'track',
    official: '赛道维度评估 — Track-dimension assessment',
    question: 'Does the agent execute autonomously end to end, and does it leave a verifiable deliverable?',
    max: 20,
    selfScore: 14,
    confidence: 'medium',
    evidence:
      'The investigation loop runs intake → plan → probe → counterfactual replay → decision → report without step-by-step human input, showing structured actions rather than reasoning. Every finding links to evidence. The deliverable is a downloadable report. The demo’s aggregate verdict is a measured, confirmed regression — mean score fall 0.173 with a 95% interval entirely below the −0.05 threshold.',
    gap:
      'The required demo video does not exist. The clean-start checklist has not been run by a non-author. The autonomy is demonstrated on fixtures, and the live-model path is unexercised.',
    target: 17,
    actions: [
      {
        id: 'K1',
        what: 'Record the two-to-three-minute demo video, publish it, and confirm it plays with no login in a private window.',
        verification: 'The URL, opened logged out.',
      },
      {
        id: 'K2',
        what: 'Run the full clean-start checklist on a machine that is not the development machine.',
        verification: 'The transcript, failures included.',
      },
      {
        id: 'K3',
        what: 'Capture the live-model run in the recording so the runtime badge reads the real mode.',
        verification: 'The badge visible in the recording.',
      },
      {
        id: 'K4',
        what: 'State the minimum case count the aggregate verdict requires, in the pitch.',
        verification: 'One sentence with the derivation.',
      },
      {
        id: 'K5',
        what: 'Verify the two presenter deep links on a clean backend.',
        verification: 'Two screenshots.',
      },
    ],
  },
]

export const MAX_TOTAL = 100

export function totalSelfScore(): number {
  return CRITERIA.reduce((sum, criterion) => sum + criterion.selfScore, 0)
}

export function totalTargetScore(): number {
  return CRITERIA.reduce((sum, criterion) => sum + criterion.target, 0)
}

// ------------------------------------------------------------------ position --

export interface MarketPosition {
  /**
   * The single sentence the surface is built around. Kept here rather than in
   * the component so it can be asserted by a test.
   */
  headline: string
  /** What the demo proves, and what it does not. */
  demonstrated: readonly string[]
  /** The parts of a market pitch that do not exist yet. */
  missing: readonly string[]
}

export const POSITION: MarketPosition = {
  headline:
    'The competition result is not the market result: the mechanism is implemented and demonstrated on a corpus we seeded ourselves, and nobody outside this repository has seen it.',
  demonstrated: [
    'A working comparison engine, end to end, on a 26-scenario corpus.',
    'A confirmed aggregate regression on that corpus, with a paired interval and unchanged controls.',
    'Evidence-linked findings and a downloadable report.',
    'An honest, reproducible demo that labels its own data.',
  ],
  missing: [
    'Any external user.',
    'Any design partner or pilot.',
    'Any paying customer or revenue.',
    'Any quoted price or validated ROI figure.',
    'A public demo video.',
  ],
}

// --------------------------------------------------------------- disclosure --

/**
 * The `SourceLabel` objects the surface renders beside each block, resolved by
 * id so a label can never be invented at a call site.
 */
export function sourceLabel(id: SourceLabel['id']): SourceLabel {
  const found = SOURCE_LABELS.find((label) => label.id === id)
  if (!found) throw new Error(`unknown source label: ${id}`)
  return found
}

/** The counts that must render as dashes, in the order they appear. */
export const TRACTION_ROWS: ReadonlyArray<{ key: TractionKey; label: string }> = [
  { key: 'paying_customers', label: 'Paying customers' },
  { key: 'active_pilots', label: 'Active pilots' },
  { key: 'design_partners', label: 'Design partners' },
  { key: 'external_users', label: 'External users' },
  { key: 'external_conversations', label: 'External conversations' },
  { key: 'revenue_ytd_cny', label: 'Revenue, year to date' },
]
