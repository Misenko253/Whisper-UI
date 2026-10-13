import wave

from wavio import WavWriter, repair

PCM = bytes(range(256)) * 40  # 10240 bytes = 5120 int16 frames


def frames(path):
    with wave.open(str(path)) as w:
        return w.getframerate(), w.readframes(w.getnframes())


def test_closed_file_is_a_valid_wav(tmp_path):
    path = tmp_path / "a.wav"
    w = WavWriter(path, 16000)
    w.write(PCM[:4000])
    w.write(PCM[4000:])
    w.close()
    assert frames(path) == (16000, PCM)
    assert w.duration == len(PCM) / 2 / 16000


def test_header_is_kept_current_while_recording(tmp_path):
    path = tmp_path / "a.wav"
    w = WavWriter(path, 16000, sync_interval=0)
    w.write(PCM)
    assert frames(path) == (16000, PCM)  # readable without close()
    w.close()


def test_repair_after_kill_recovers_all_written_audio(tmp_path):
    path = tmp_path / "a.wav"
    w = WavWriter(path, 16000, sync_interval=3600)
    w.write(PCM)
    w._f.flush()  # data reached the file, header still says 0 bytes: the process "dies" here
    w._f.write(b"\x01")  # plus a torn half frame
    w._f.close()
    assert frames(path) == (16000, b"")
    assert repair(path) is True
    assert frames(path) == (16000, PCM)
    assert repair(path) is False  # already consistent


def test_repair_ignores_files_that_are_not_wav(tmp_path):
    path = tmp_path / "x.wav"
    path.write_bytes(b"nope")
    assert repair(path) is False
