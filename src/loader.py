"""ORD loader. Reads every system's ord.json (or ord_enriched.json) and
produces one flat list of Resource dicts with the fields used by the
retrieval methods.

A Resource is:
    {
      "ordId":        "sap.s4:apiResource:MaterialInventory:v1",
      "namespace":    "sap.s4",
      "type":         "apiResource" | "agent" | "dataProduct" | "entityType" | "event",
      "title":        "...",
      "shortDescription": "...",
      "description":  "...",
      "entityTypes":  ["sap.odm:entityType:Material:v1", ...],
      "partOfPackage": "sap.s4:package:Logistics:v1",
      "tags":         [...],
    }
"""

from __future__ import annotations

import json
from typing import Any

from src.core import config


RESOURCE_KEYS = ["apiResources", "agents", "dataProducts", "entityTypes", "eventResources"]
TYPE_FROM_KEY = {
    "apiResources": "apiResource",
    "agents": "agent",
    "dataProducts": "dataProduct",
    "entityTypes": "entityType",
    "eventResources": "event",
}


def _extract_entity_types(item: dict[str, Any]) -> list[str]:
    """Collect every entity-type ORD ID a resource references.

    The ORD v1.15 spec uses different fields per resource kind:

      apiResource    →  exposedEntityTypes  ([{"ordId": "..."}, ...])
      eventResource  →  exposedEntityTypes
      dataProduct    →  entityTypes         (["sap.odm:entityType:X:v1", ...])
      agent          →  relatedEntityTypes  (["sap.odm:entityType:X:v1", ...])
      capability     →  relatedEntityTypes

    The legacy field `entityTypeMappings` is still tolerated here for
    forward compatibility (the spec says exposedEntityTypes replaces it
    on api/event resources since v1.11), but the canonical landscape on
    disk has been normalised to drop it during benchmark landscape
    generation.
    """
    ets: list[str] = []

    def _add(oid: str) -> None:
        if oid and oid not in ets:
            ets.append(oid)

    # Legacy entityTypeMappings — tolerated, not produced
    for mapping in item.get("entityTypeMappings", []) or []:
        for target in mapping.get("entityTypeTargets", []) or []:
            if isinstance(target, dict) and isinstance(target.get("ordId"), str):
                _add(target["ordId"])

    # exposedEntityTypes  (api / event)
    for ref in item.get("exposedEntityTypes", []) or []:
        if isinstance(ref, dict) and isinstance(ref.get("ordId"), str):
            _add(ref["ordId"])

    # relatedEntityTypes  (agent / capability)
    for ref in item.get("relatedEntityTypes", []) or []:
        if isinstance(ref, dict) and isinstance(ref.get("ordId"), str):
            _add(ref["ordId"])
        elif isinstance(ref, str):
            _add(ref)

    # entityTypes  (dataProduct)
    for et in item.get("entityTypes", []) or []:
        if isinstance(et, str):
            _add(et)

    return ets


def _package_index(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a {packageId → packageMeta} index so resources can inherit
    lineOfBusiness / vendor / package-level tags."""
    idx: dict[str, dict[str, Any]] = {}
    for pkg in doc.get("packages", []) or []:
        ordId = pkg.get("ordId")
        if ordId:
            idx[ordId] = {
                "title": pkg.get("title", ""),
                "shortDescription": pkg.get("shortDescription", ""),
                "lineOfBusiness": pkg.get("lineOfBusiness", []) or [],
                "vendor": pkg.get("vendor", ""),
                "tags": pkg.get("tags", []) or [],
            }
    return idx


def _flatten_doc(doc: dict[str, Any], namespace: str) -> list[dict[str, Any]]:
    pkg_idx = _package_index(doc)
    out: list[dict[str, Any]] = []
    for key in RESOURCE_KEYS:
        for item in doc.get(key, []) or []:
            pkg_id = item.get("partOfPackage", "")
            pkg_meta = pkg_idx.get(pkg_id, {})
            out.append({
                "ordId": item.get("ordId", ""),
                "namespace": namespace,
                "type": TYPE_FROM_KEY[key],
                "title": item.get("title", ""),
                "shortDescription": item.get("shortDescription", ""),
                "description": item.get("description", ""),
                "entityTypes": _extract_entity_types(item),
                "partOfPackage": pkg_id,
                "packageTitle": pkg_meta.get("title", ""),
                # resource-level fields override package-level when present
                "lineOfBusiness": item.get("lineOfBusiness")
                                  or pkg_meta.get("lineOfBusiness", []),
                "partOfProducts": item.get("partOfProducts")
                                  or pkg_meta.get("partOfProducts", []),
                "tags": item.get("tags", []) or [],
                "capabilities": item.get("capabilities", []) or [],
                "useCases": item.get("useCases", []) or [],
                "apiProtocol": item.get("apiProtocol", ""),
                "resourceDefinitions": item.get("resourceDefinitions", []) or [],
                "apiResourceLinks": item.get("apiResourceLinks", []) or [],
                "responsible": item.get("responsible", ""),
                # enrichment fields — present only in ord_enriched.json
                "partOfGroups": item.get("partOfGroups", []) or [],
                "processNext": item.get("processNext", []) or [],
            })
    return out


def load_landscape(state: str | None = None) -> list[dict[str, Any]]:
    """Load all resources across systems.

    state:
      "enriched" → systems_enriched/{ns}/ord_enriched.json
      "clean"    → systems/{ns}/ord.json
    """
    state = state or config.ORD_STATE
    resources: list[dict[str, Any]] = []

    for system_dir in sorted(config.LANDSCAPE_DIR.iterdir()):
        if not system_dir.is_dir() or system_dir.name == "sap.odm":
            continue

        if state == "enriched":
            enriched_path = config.LANDSCAPE_ENRICHED_DIR / system_dir.name / "ord_enriched.json"
            path = enriched_path if enriched_path.exists() else system_dir / "ord.json"
        else:
            path = system_dir / "ord.json"

        if not path.exists():
            continue
        with path.open() as f:
            doc = json.load(f)
        resources.extend(_flatten_doc(doc, system_dir.name))
    return resources


if __name__ == "__main__":
    rs = load_landscape()
    print(f"Loaded {len(rs)} resources from {config.LANDSCAPE_DIR}")
    by_type: dict[str, int] = {}
    for r in rs:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    print("by type:", by_type)
    print("namespaces:", sorted({r['namespace'] for r in rs}))
