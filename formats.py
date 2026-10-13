"""Turn mlx-whisper segments into .txt (with [hh:mm:ss] stamps) and .srt text."""


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _segments(segments):
    for seg in segments:
        text = seg["text"].strip()
        if text:
            yield seg["start"], seg["end"], text


def to_txt(segments) -> str:
    return "".join(f"[{hms(start)}] {text}\n" for start, _, text in _segments(segments))


def to_srt(segments) -> str:
    return "\n".join(
        f"{i}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n"
        for i, (start, end, text) in enumerate(_segments(segments), 1)
    )
