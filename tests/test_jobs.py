import wave
from datetime import datetime

from jobs import FAILED, PENDING, RECORDING, Job, JobStore, recover, unique_id
from wavio import WavWriter

NOW = datetime(2026, 10, 13, 15, 4, 5)


def test_unique_id_is_a_timestamp_with_suffix_on_collision(tmp_path):
    assert unique_id([tmp_path], NOW) == "2026-10-13_15-04-05"
    (tmp_path / "2026-10-13_15-04-05.wav").touch()
    assert unique_id([tmp_path], NOW) == "2026-10-13_15-04-05-2"


def test_store_round_trip_and_delete(tmp_path):
    store = JobStore(tmp_path)
    job = Job("b", "/x/b.wav", "sk", "whisper-large-v3-mlx")
    store.save(Job("a", "/x/a.wav", None, "large-v3-turbo", state=RECORDING))
    store.save(job)
    assert [j.id for j in store.all()] == ["a", "b"]
    assert store.all()[1] == job
    store.delete("a")
    assert [j.id for j in store.all()] == ["b"]
    assert not list(tmp_path.glob("*.tmp"))


def test_recover_repairs_interrupted_recordings_and_returns_pending(tmp_path):
    store = JobStore(tmp_path / "jobs")
    wav = tmp_path / "rec.wav"
    w = WavWriter(wav, 16000, sync_interval=3600)
    w.write(b"\x01\x00" * 100)
    w._f.flush()
    w._f.close()  # killed mid-recording
    empty = tmp_path / "empty.wav"
    WavWriter(empty, 16000)._f.close()  # killed before any audio arrived

    store.save(Job("1", str(wav), "sk", "m", state=RECORDING))
    store.save(Job("2", "/x/file.mp3", "sk", "m", state=PENDING))
    store.save(Job("3", "/x/bad.mp3", "sk", "m", state=FAILED, error="boom"))
    store.save(Job("4", str(empty), "sk", "m", state=RECORDING))
    store.save(Job("5", str(tmp_path / "missing.wav"), "sk", "m", state=RECORDING))

    pending = recover(store)

    assert [j.id for j in pending] == ["1", "2"]
    assert all(j.state == PENDING for j in pending)
    with wave.open(str(wav)) as w:
        assert w.getnframes() == 100
    assert [j.id for j in store.all()] == ["1", "2", "3"]  # empty/missing recordings dropped
