from musicsim import compare


def test_same_melody_scores_high(midi_file, matching_audio_file):
    result = compare(midi_file, matching_audio_file)
    assert result.score > 0.7


def test_different_melody_scores_lower(midi_file, matching_audio_file, different_audio_file):
    same = compare(midi_file, matching_audio_file)
    different = compare(midi_file, different_audio_file)
    assert different.score < same.score
