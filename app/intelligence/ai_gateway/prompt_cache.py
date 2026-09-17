from __future__ import annotations

import hashlib
import json

PROMPT_TRANSPORT_VERSION = "money-heist.prompt-transport.v3"
AGENT_DIALOGUE_LANGUAGE = "fr-FR"
AGENT_DIALOGUE_LANGUAGE_VERSION = "money-heist.agent-dialogue.fr.v1"

_AGENT_DIALOGUE_LANGUAGE_MARKER = f"[{AGENT_DIALOGUE_LANGUAGE_VERSION}]"
_AGENT_DIALOGUE_LANGUAGE_CONTRACT = (
    f"{_AGENT_DIALOGUE_LANGUAGE_MARKER} "
    "Rédige en français (fr-FR) tout contenu explicatif en langage naturel destiné à être lu "
    "par un humain ou par un autre agent. Conserve exactement les clés JSON, noms de champs de "
    "schéma, valeurs d'enum, identifiants, source_key/source_index, symboles de marché, nombres, "
    "hashes, URLs et autres tokens machine imposés par le contrat ou présents dans les entrées. "
    "Ne traduis jamais les tokens de contrôle tels que LONG, SHORT, NO_TRADE, NO_ANALYSIS, "
    "NEUTRAL, UNKNOWN, CLEAR, CAUTION, REJECT, APPROVE, APPROVED, REJECTED, RESIZE, RESIZED, "
    "ACTIVE, ON_DEMAND, SHADOW, PROBATION ou DISABLED. Les termes techniques standards peuvent "
    "rester en anglais lorsqu'ils améliorent la précision."
)


def apply_agent_dialogue_language_contract(instructions: str | None) -> str:
    """Append the stable French human-language contract exactly once."""

    base = (instructions or "").strip()
    if _AGENT_DIALOGUE_LANGUAGE_MARKER in base:
        return base
    if not base:
        return _AGENT_DIALOGUE_LANGUAGE_CONTRACT
    return f"{base}\n\n{_AGENT_DIALOGUE_LANGUAGE_CONTRACT}"


def schema_fingerprint(json_schema: dict) -> str:
    payload = json.dumps(
        json_schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_cacheable_developer_prefix(
    *,
    agent_id: str,
    prompt_version: str,
    prompt_render_version: str,
    instructions: str | None,
    schema_name: str,
    schema_sha256: str,
) -> str:
    """Render the provider-facing stable prefix byte-for-byte deterministically.

    Dynamic request/run/opportunity data is deliberately excluded.  The schema
    fingerprint is included so a material Structured Output contract change cannot
    accidentally share a cache prefix with the previous contract.
    """

    instruction_text = (instructions or "").strip()
    return "\n".join(
        (
            "MONEY_HEIST_STABLE_DEVELOPER_PREFIX",
            f"prompt_render_version={prompt_render_version}",
            f"agent_id={agent_id}",
            f"prompt_version={prompt_version}",
            f"schema_name={schema_name}",
            f"schema_sha256={schema_sha256}",
            "instructions:",
            instruction_text,
        )
    )


def stable_prefix_fingerprint(prefix: str) -> str:
    return hashlib.sha256(prefix.encode("utf-8")).hexdigest()
