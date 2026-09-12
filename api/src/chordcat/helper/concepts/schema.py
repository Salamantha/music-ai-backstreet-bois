"""The concept map's node type and loader.

A node is not a lookup row with teaching text bolted on -- the teaching text is
the node. So loading refuses anything that has structure but nothing to say,
which is the failure mode that would otherwise ship silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

NODES_FILE = Path(__file__).parent / "nodes.yaml"

TEACHING_FIELDS = ("what_it_means", "what_it_does_to_the_sound", "when_it_helps")

#: Written by an engineer to make the pipeline runnable. Never shown as final.
DRAFT = "draft"
APPROVED = "tutor-approved"
#: Placeholder for a device instruction that has to come from the manual.
UNFILLED_DEVICE = "TUTOR_TODO"


@dataclass(frozen=True, slots=True)
class ConceptNode:
    id: str
    kind: str
    plain_name: str
    detect: str
    what_it_means: str
    what_it_does_to_the_sound: str
    when_it_helps: str
    prerequisites: tuple[str, ...] = ()
    edges: tuple[str, ...] = ()
    on_device: str = UNFILLED_DEVICE
    common_mistake: str = ""
    status: str = DRAFT

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> ConceptNode:
        missing = [f for f in TEACHING_FIELDS if not str(raw.get(f, "")).strip()]
        if missing:
            raise ValueError(f"node {raw.get('id')!r} has no {', '.join(missing)}")
        return cls(
            id=raw["id"],
            kind=raw["kind"],
            plain_name=raw["plain_name"],
            detect=raw["detect"],
            what_it_means=raw["what_it_means"].strip(),
            what_it_does_to_the_sound=raw["what_it_does_to_the_sound"].strip(),
            when_it_helps=raw["when_it_helps"].strip(),
            prerequisites=tuple(raw.get("prerequisites") or ()),
            edges=tuple(raw.get("edges") or ()),
            on_device=raw.get("on_device", UNFILLED_DEVICE),
            common_mistake=(raw.get("common_mistake") or "").strip(),
            status=raw.get("status", DRAFT),
        )


def load_nodes(path: Path = NODES_FILE) -> dict[str, ConceptNode]:
    raw = yaml.safe_load(path.read_text()) or []
    nodes = {n["id"]: ConceptNode.from_raw(n) for n in raw}
    for node in nodes.values():
        unknown = (set(node.prerequisites) | set(node.edges)) - set(nodes)
        if unknown:
            raise ValueError(f"node {node.id!r} references unknown nodes: {sorted(unknown)}")
    return nodes
