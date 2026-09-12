"""Facts light nodes; the helper speaks from the edge of what you have done.

Deterministic and explainable on purpose. No ML, no scoring model -- just: which
nodes are lit, which unlit nodes touch them, which of those you have not been
offered yet. So "why are you telling me this?" always has a real answer.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..facts import FactSet
from ..session import Session
from .detectors import DETECTORS
from .schema import APPROVED, ConceptNode

#: Musician's words, mapped to the nodes they should pull forward. Capped at
#: 6-8; the tutor names them.
INTENT_TAGS: dict[str, tuple[str, ...]] = {
    "heavier": ("minor_key", "wide_register", "open_voicing"),
    "jazzier": ("seventh_chords", "extended_harmony", "backdoor_cadence"),
    "smoother": ("inversions", "moves_by_step_node", "close_voicing"),
    "simpler": ("chords_in_a_key", "slow_harmony"),
    "bigger": ("open_voicing", "wide_register"),
    "moodier": ("minor_key", "sus_chords", "moves_by_thirds_node"),
    "busier": ("fast_harmony", "moves_by_fourths_node"),
    "more human": ("dynamic_range",),
}

#: How far out we look when nothing sits directly on the frontier.
MAX_DISTANCE = 2


@dataclass(frozen=True, slots=True)
class Choice:
    node: ConceptNode
    #: Lit nodes this one hangs off -- the answer to "why are you telling me this?"
    why: tuple[str, ...]
    distance: int
    score: float


def visited(facts: FactSet, nodes: dict[str, ConceptNode]) -> set[str]:
    return {n.id for n in nodes.values() if DETECTORS[n.detect](facts)}


def _neighbours(node_id: str, nodes: dict[str, ConceptNode]) -> set[str]:
    """Edges are undirected for traversal: adjacency is symmetric."""
    out = set(nodes[node_id].edges)
    out |= {n.id for n in nodes.values() if node_id in n.edges}
    return out


def _distances(lit: set[str], nodes: dict[str, ConceptNode]) -> dict[str, int]:
    dist = {i: 0 for i in lit}
    queue = deque(lit)
    while queue:
        current = queue.popleft()
        for nxt in _neighbours(current, nodes):
            if nxt not in dist:
                dist[nxt] = dist[current] + 1
                queue.append(nxt)
    return dist


def frontier(lit: set[str], nodes: dict[str, ConceptNode], max_distance: int = 1) -> set[str]:
    dist = _distances(lit, nodes)
    return {
        i
        for i, d in dist.items()
        if 0 < d <= max_distance and set(nodes[i].prerequisites) <= lit
    }


def choose(
    facts: FactSet,
    session: Session,
    nodes: dict[str, ConceptNode],
    *,
    require_approved: bool = False,
) -> Choice | None:
    lit = visited(facts, nodes)
    if not lit:
        return None

    dist = _distances(lit, nodes)
    wanted: set[str] = set()
    for tag in session.intent_tags:
        wanted |= set(INTENT_TAGS.get(tag, ()))

    best: Choice | None = None
    for reach in range(1, MAX_DISTANCE + 1):
        for node_id in sorted(frontier(lit, nodes, reach)):
            node = nodes[node_id]
            if require_approved and node.status != APPROVED:
                continue
            score = 10.0 - dist[node_id]
            if node_id in wanted:
                score += 5.0
            if node_id in session.suggested_nodes:
                score -= 8.0
            if node_id in session.tried_nodes:
                score -= 4.0
            if best is None or score > best.score:
                best = Choice(
                    node=node,
                    why=tuple(sorted(_neighbours(node_id, nodes) & lit)),
                    distance=dist[node_id],
                    score=score,
                )
        if best is not None:
            return best
    return best
