from __future__ import annotations

from chordcat.helper.concepts.graph import INTENT_TAGS, choose, frontier, visited
from chordcat.helper.concepts.schema import load_nodes
from chordcat.helper.facts import Fact, FactSet
from chordcat.helper.session import Session

NODES = load_nodes()


def plain_chords() -> FactSet:
    return FactSet((
        Fact("harmony.chord#0", "harmony.chord", "C", n_observations=1),
        Fact("harmony.quality_counts#0", "harmony.quality_counts",
             {"major": 3, "minor": 1}, n_observations=4),
    ))


def test_playing_chords_lights_the_root_node():
    assert "chords_in_a_key" in visited(plain_chords(), NODES)
    assert "seventh_chords" not in visited(plain_chords(), NODES)


def test_the_frontier_is_unlit_neighbours_whose_prerequisites_are_met():
    lit = visited(plain_chords(), NODES)
    edge = frontier(lit, NODES)
    assert "seventh_chords" in edge
    # Two steps out, and its prerequisite is unlit, so not on the frontier.
    assert "extended_harmony" not in edge


def test_choose_returns_exactly_one_node_with_a_traceable_path():
    got = choose(plain_chords(), Session(id="t"), NODES)
    assert got is not None
    assert got.node.id in frontier(visited(plain_chords(), NODES), NODES)
    assert got.why
    assert got.distance == 1


def test_an_intent_tag_steers_the_choice():
    jazzier = choose(plain_chords(), Session(id="t", intent_tags=["jazzier"]), NODES)
    assert jazzier.node.id == "seventh_chords"


def test_already_suggested_nodes_are_pushed_down():
    session = Session(id="t", suggested_nodes=["seventh_chords"], intent_tags=["jazzier"])
    assert choose(plain_chords(), session, NODES).node.id != "seventh_chords"


def test_silence_chooses_nothing():
    assert choose(FactSet(), Session(id="t"), NODES) is None


def test_every_intent_tag_names_real_nodes():
    for tag, ids in INTENT_TAGS.items():
        assert set(ids) <= set(NODES), tag


def measured_absence() -> FactSet:
    """Chords played, and inversions explicitly measured at zero."""
    return FactSet((
        Fact("harmony.chord#0", "harmony.chord", "C", n_observations=1, is_pattern=False),
        Fact("voicing.inversions#0", "voicing.inversions",
             {"root_position": 9, "inverted": 0}, n_observations=9),
    ))


def test_a_measured_absence_outranks_one_we_never_took_a_reading_for():
    got = choose(measured_absence(), Session(id="t"), NODES)
    assert got.node.id == "inversions"
    assert got.measured is True


def test_a_node_with_no_reading_behind_it_is_marked_unmeasured():
    """Suggesting it would assert an absence the truth layer never established."""
    from chordcat.helper.concepts.detectors import DETECTORS

    facts = measured_absence()
    assert DETECTORS["has_inversions"].measured(facts) is True
    assert DETECTORS["has_authentic_cadence"].measured(facts) is False


def test_equal_scoring_alternatives_are_reported_not_hidden():
    got = choose(plain_chords(), Session(id="t"), NODES)
    assert got.node.id not in got.tied_with
    # Ties are broken alphabetically, so the loser of a tie must still surface.
    assert all(t in NODES for t in got.tied_with)
