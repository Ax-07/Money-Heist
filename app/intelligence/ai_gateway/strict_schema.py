from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from .errors import AIConfigurationError

_MISSING = object()

_UNSUPPORTED_REGEX_LOOKAROUNDS = ("(?=", "(?!", "(?<=", "(?<!")


def _has_unsupported_regex_lookaround(pattern: str) -> bool:
    return any(marker in pattern for marker in _UNSUPPORTED_REGEX_LOOKAROUNDS)


def _normalize_pydantic_decimal_compatibility_union(node: dict[str, Any]) -> None:
    # Pydantic represents Decimal as number | string(pattern=...).
    # The generated decimal-string regex uses negative lookahead, which OpenAI
    # strict Structured Outputs rejects. Keep Decimal in the business model,
    # but narrow the provider-facing schema to JSON numbers.
    variants = node.get("anyOf")
    if not isinstance(variants, list):
        return

    has_number_variant = any(
        isinstance(variant, dict) and variant.get("type") == "number"
        for variant in variants
    )
    if not has_number_variant:
        return

    compatible_variants: list[Any] = []
    removed_decimal_string_variant = False
    for variant in variants:
        if isinstance(variant, dict) and variant.get("type") == "string":
            pattern = variant.get("pattern")
            if isinstance(pattern, str) and _has_unsupported_regex_lookaround(pattern):
                removed_decimal_string_variant = True
                continue
        compatible_variants.append(variant)

    if not removed_decimal_string_variant:
        return

    if len(compatible_variants) == 1 and isinstance(compatible_variants[0], dict):
        annotations = {key: value for key, value in node.items() if key != "anyOf"}
        replacement = deepcopy(compatible_variants[0])
        replacement.update(annotations)
        node.clear()
        node.update(replacement)
        return

    node["anyOf"] = compatible_variants


def build_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Normalize a Pydantic schema for OpenAI strict Structured Outputs."""

    schema = deepcopy(model.model_json_schema())
    return _ensure_strict(schema, root=schema, path=(model.__name__,))


def _ensure_strict(
    node: Any,
    *,
    root: dict[str, Any],
    path: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise TypeError(f"expected JSON-schema object at {'/'.join(path)}")

    defs = node.get("$defs")
    if isinstance(defs, dict):
        for name, definition in defs.items():
            if isinstance(definition, dict):
                defs[name] = _ensure_strict(
                    definition,
                    root=root,
                    path=(*path, "$defs", str(name)),
                )

    definitions = node.get("definitions")
    if isinstance(definitions, dict):
        for name, definition in definitions.items():
            if isinstance(definition, dict):
                definitions[name] = _ensure_strict(
                    definition,
                    root=root,
                    path=(*path, "definitions", str(name)),
                )

    if node.get("type") == "object":
        additional = node.get("additionalProperties")
        if additional is True or isinstance(additional, dict):
            raise AIConfigurationError(
                "OpenAI strict Structured Outputs cannot safely preserve a free-form "
                f"mapping at {'/'.join(path)}"
            )
        node["additionalProperties"] = False

    properties = node.get("properties")
    if isinstance(properties, dict):
        node["required"] = list(properties)
        node["properties"] = {
            key: _ensure_strict(
                value,
                root=root,
                path=(*path, "properties", str(key)),
            )
            if isinstance(value, dict)
            else value
            for key, value in properties.items()
        }

    items = node.get("items")
    if isinstance(items, dict):
        node["items"] = _ensure_strict(
            items,
            root=root,
            path=(*path, "items"),
        )

    _normalize_pydantic_decimal_compatibility_union(node)

    for union_key in ("anyOf", "oneOf"):
        variants = node.get(union_key)
        if isinstance(variants, list):
            node[union_key] = [
                _ensure_strict(
                    variant,
                    root=root,
                    path=(*path, union_key, str(index)),
                )
                if isinstance(variant, dict)
                else variant
                for index, variant in enumerate(variants)
            ]

    all_of = node.get("allOf")
    if isinstance(all_of, list):
        if len(all_of) == 1 and isinstance(all_of[0], dict):
            merged = _ensure_strict(
                all_of[0],
                root=root,
                path=(*path, "allOf", "0"),
            )
            node.pop("allOf")
            node.update(merged)
        else:
            node["allOf"] = [
                _ensure_strict(
                    variant,
                    root=root,
                    path=(*path, "allOf", str(index)),
                )
                if isinstance(variant, dict)
                else variant
                for index, variant in enumerate(all_of)
            ]

    pattern = node.get("pattern")
    if isinstance(pattern, str) and _has_unsupported_regex_lookaround(pattern):
        raise AIConfigurationError(
            "OpenAI strict Structured Outputs does not support regex lookaround "
            f"at {'/'.join(path)}"
        )

    if node.get("default", _MISSING) is None:
        node.pop("default", None)

    ref = node.get("$ref")
    if isinstance(ref, str) and len(node) > 1:
        resolved = _resolve_ref(root, ref)
        merged = {**resolved, **node}
        merged.pop("$ref", None)
        return _ensure_strict(merged, root=root, path=path)

    return node


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise AIConfigurationError(f"unsupported JSON-schema ref: {ref!r}")
    current: Any = root
    for key in ref[2:].split("/"):
        if not isinstance(current, dict) or key not in current:
            raise AIConfigurationError(f"unresolvable JSON-schema ref: {ref!r}")
        current = current[key]
    if not isinstance(current, dict):
        raise AIConfigurationError(f"JSON-schema ref does not resolve to an object: {ref!r}")
    return deepcopy(current)
