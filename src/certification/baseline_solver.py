"""Frozen single-call baseline used by ORD-Bench construction gates.

This module intentionally lives in ORD-Bench so benchmark generation does not
import retrieval code from the separate semantic-retrieval repository.  Its
prompt and resource projection match the baseline used for certification.
"""
from __future__ import annotations

import re

from src import llm

_SYSTEM = (
    "You are a resource selector. Given a business activity and a list of ORD "
    "resources, return the single ordId that best fulfils the activity. "
    'Respond with a JSON object: {"ordId": "<best match>"}'
)


def retrieve(label: str, resources: list[dict], top_k: int = 1) -> dict:
    """Select one resource using the frozen ORD-Bench gate prompt."""
    if top_k != 1:
        raise ValueError("ORD-Bench's construction gate supports top_k=1 only")

    lines = [f"Activity: {label}", "", "Resources:"]
    for resource in resources:
        lines.append(
            f"  - {resource['ordId']}: {resource['title']}. "
            f"{resource.get('shortDescription', '')}"
        )

    text, meta = llm.chat("\n".join(lines), system=_SYSTEM)
    match = re.search(r'\{[^}]*"ordId"\s*:\s*"([^"]+)"', text)
    ord_id = match.group(1).strip() if match else None
    candidates = [{"ordId": ord_id, "score": 1.0}] if ord_id else []
    return {
        "method": "S",
        "candidates": candidates,
        "trace": {
            "tokens": meta["tokens"],
            "latency_s": round(meta["latency"], 3),
            "llm_calls": 1,
        },
    }
