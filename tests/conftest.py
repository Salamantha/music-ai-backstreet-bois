import pretty_midi
import pytest
import soundfile as sf

SAMPLE_RATE = 22050


def _make_midi(pitches, note_duration=0.4, velocity=100):
    pm = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)
    t = 0.0
    for pitch in pitches:
        instrument.notes.append(
            pretty_midi.Note(velocity=velocity, pitch=pitch, start=t, end=t + note_duration)
        )
        t += note_duration
    pm.instruments.append(instrument)
    return pm


@pytest.fixture
def melody_pitches():
    return [60, 62, 64, 65, 67, 69, 71, 72]  # C major scale


@pytest.fixture
def different_pitches():
    return [61, 63, 66, 68, 70, 73, 75, 77]  # unrelated pitch sequence


@pytest.fixture
def midi_file(tmp_path, melody_pitches):
    path = tmp_path / "melody.mid"
    _make_midi(melody_pitches).write(str(path))
    return str(path)


@pytest.fixture
def matching_audio_file(tmp_path, melody_pitches):
    audio = _make_midi(melody_pitches).synthesize(fs=SAMPLE_RATE)
    path = tmp_path / "melody_match.wav"
    sf.write(str(path), audio, SAMPLE_RATE)
    return str(path)


@pytest.fixture
def different_audio_file(tmp_path, different_pitches):
    audio = _make_midi(different_pitches).synthesize(fs=SAMPLE_RATE)
    path = tmp_path / "melody_different.wav"
    sf.write(str(path), audio, SAMPLE_RATE)
    return str(path)
