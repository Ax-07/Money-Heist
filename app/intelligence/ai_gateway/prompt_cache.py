from __future__ import annotations

import hashlib
import json

PROMPT_TRANSPORT_VERSION = "money-heist.prompt-transport.v2"


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
