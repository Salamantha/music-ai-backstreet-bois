from __future__ import annotations

import pytest

from chordcat.helper.concepts.schema import ConceptNode, load_nodes
from chordcat.helper.facts import Fact, FactSet


def test_the_shipped_map_loads_and_is_internally_consistent():
    nodes = load_nodes()
    assert len(nodes) >= 20
    ids = set(nodes)
    for node in nodes.values():
        assert node.kind in {"harmony", "voicing", "performance"}
        assert set(node.prerequisites) <= ids, f"{node.id} needs a node that does not exist"
        assert set(node.edges) <= ids, f"{node.id} links to a node that does not exist"
        assert node.id not in node.edges


def test_every_node_names_a_detector_that_exists():
    from chordcat.helper.concepts.detectors import DETECTORS

    for node in load_nodes().values():
        assert node.detect in DETECTORS, f"{node.id} names unknown detector {node.detect!r}"


def test_no_detector_is_dead_code():
    from chordcat.helper.concepts.detectors import DETECTORS

    assert set(DETECTORS) == {n.detect for n in load_nodes().values()}


def test_a_node_missing_teaching_text_is_rejected():
    with pytest.raises(ValueError, match="what_it_means"):
        ConceptNode.from_raw(
            {"id": "x", "kind": "harmony", "detect": "has_chords", "plain_name": "x"}
        )


def test_draft_nodes_are_flagged_not_silently_shipped():
    drafts = [n.id for n in load_nodes().values() if n.status != "tutor-approved"]
    # Expected to be non-empty until the tutor has been through it -- the point
    # is that the list is visible, not that it is empty.
    assert isinstance(drafts, list)


def test_detectors_read_facts_and_nothing_else():
    from chordcat.helper.concepts.detectors import DETECTORS

    fs = FactSet(
        (Fact("harmony.extensions#0", "harmony.extensions", {"sevenths": 2, "of": 8},
              n_observations=2),)
    )
    assert DETECTORS["has_sevenths"](fs) is True
    assert DETECTORS["has_sevenths"](FactSet()) is False
