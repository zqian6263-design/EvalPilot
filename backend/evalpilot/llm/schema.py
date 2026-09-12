"""Strict JSON-schema validation for model output.

The investigation asks a model for a small, fixed JSON shape. Anything else is
a failure: a partially-parsed hypothesis would end up as a claim in a release
report with a fabricated field, and a report is not a place for best-effort
parsing. So a response that does not satisfy the schema raises
:class:`~evalpilot.llm.errors.LLMSchemaError` rather than being coerced.

The supported subset is the one this package's own prompts describe:

``type``
    ``object``, ``array``, ``string``, ``integer``, ``number``, ``boolean``,
    ``null``, or a list of those (union).
``properties`` / ``required`` / ``additionalProperties``
    For objects. Unknown keys are rejected unless ``additionalProperties`` is
    true, because a model that invents fields is not following the prompt.
``items`` / ``minItems`` / ``maxItems``
    For arrays.
``enum`` / ``const``
    Membership, compared by value.
``minLength`` / ``maxLength`` / ``minimum`` / ``maximum``
    Bounds, applied only when the value is the matching type.

Deliberately absent: ``$ref``, ``oneOf``, ``patternProperties``. None of the
shapes this package requests needs them, and a half-implemented reference
resolver is worse than not having one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from evalpilot.llm.errors import LLMSchemaError

#: JSON type name -> the Python types that satisfy it. ``bool`` is excluded
#: from the numeric types on purpose: ``isinstance(True, int)`` is true in
#: Python, but a JSON ``true`` is not a JSON number.
_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list, tuple),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def validate_json_schema(payload: Any, schema: Mapping[str, Any]) -> None:
    """Raise :class:`LLMSchemaError` unless ``payload`` satisfies ``schema``.

    Returns ``None`` on success; the payload is not transformed or filled in.
    """
    error = _first_error(payload, schema, path="$")
    if error is not None:
        raise LLMSchemaError(f"LLM output failed schema validation: {error}")


def _first_error(value: Any, schema: Any, *, path: str) -> str | None:
    """The first violation found, as a readable one-line explanation."""
    if not isinstance(schema, Mapping):
        return None  # an untyped node asserts nothing

    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        return f"{path}: expected {_type_label(expected)}, got {_json_type(value)}"

    if "const" in schema and value != schema["const"]:
        return f"{path}: expected exactly {schema['const']!r}, got {value!r}"

    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, str):
        if value not in enum:
            return f"{path}: {value!r} is not one of {list(enum)!r}"

    if isinstance(value, bool):
        return None  # booleans satisfy no other constraint worth checking

    if isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            return f"{path}: string is {len(value)} chars, minimum is {minimum}"
        maximum = schema.get("maxLength")
        if isinstance(maximum, int) and len(value) > maximum:
            return f"{path}: string is {len(value)} chars, maximum is {maximum}"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            return f"{path}: {value} is below the minimum {minimum}"
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            return f"{path}: {value} is above the maximum {maximum}"

    if isinstance(value, Mapping):
        error = _object_error(value, schema, path=path)
        if error is not None:
            return error

    if isinstance(value, (list, tuple)):
        error = _array_error(value, schema, path=path)
        if error is not None:
            return error

    return None


def _object_error(
    value: Mapping[str, Any], schema: Mapping[str, Any], *, path: str
) -> str | None:
    properties = schema.get("properties")
    properties = properties if isinstance(properties, Mapping) else {}

    for name in schema.get("required") or []:
        if name not in value:
            return f"{path}: missing required property {name!r}"

    if schema.get("additionalProperties") is False:
        unknown = sorted(set(value) - set(properties))
        if unknown:
            return f"{path}: unexpected propert{'y' if len(unknown) == 1 else 'ies'} {unknown!r}"

    for name, subschema in properties.items():
        if name in value:
            error = _first_error(value[name], subschema, path=f"{path}.{name}")
            if error is not None:
                return error
    return None


def _array_error(
    value: Sequence[Any], schema: Mapping[str, Any], *, path: str
) -> str | None:
    minimum = schema.get("minItems")
    if isinstance(minimum, int) and len(value) < minimum:
        return f"{path}: {len(value)} item(s), minimum is {minimum}"
    maximum = schema.get("maxItems")
    if isinstance(maximum, int) and len(value) > maximum:
        return f"{path}: {len(value)} item(s), maximum is {maximum}"

    items = schema.get("items")
    if isinstance(items, Mapping):
        for index, item in enumerate(value):
            error = _first_error(item, items, path=f"{path}[{index}]")
            if error is not None:
                return error
    return None


def _matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, str):
        return _matches_single_type(value, expected)
    if isinstance(expected, Sequence) and not isinstance(expected, str):
        return any(_matches_single_type(value, name) for name in expected)
    return True


def _matches_single_type(value: Any, name: str) -> bool:
    python_types = _JSON_TYPES.get(name)
    if python_types is None:
        return True  # an unknown type name asserts nothing we can check
    if name in {"integer", "number"} and isinstance(value, bool):
        return False
    return isinstance(value, python_types)


def _type_label(expected: Any) -> str:
    if isinstance(expected, str):
        return expected
    if isinstance(expected, Sequence) and not isinstance(expected, str):
        return " or ".join(str(name) for name in expected)
    return str(expected)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return type(value).__name__
