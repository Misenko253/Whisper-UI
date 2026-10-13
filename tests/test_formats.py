from formats import hms, srt_time, to_srt, to_txt

SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": " Dobrý deň, "},
    {"start": 2.5, "end": 3.0, "text": "  "},
    {"start": 3725.9, "end": 3727.123, "text": "toto je test."},
]


def test_hms_floors_to_whole_seconds():
    assert hms(0) == "00:00:00"
    assert hms(3725.9) == "01:02:05"


def test_srt_time_has_milliseconds():
    assert srt_time(3727.123) == "01:02:07,123"
    assert srt_time(1.2346) == "00:00:01,235"


def test_txt_has_one_stamped_line_per_non_empty_segment():
    assert to_txt(SEGMENTS) == "[00:00:00] Dobrý deň,\n[01:02:05] toto je test.\n"


def test_srt_numbers_non_empty_segments():
    assert to_srt(SEGMENTS) == (
        "1\n00:00:00,000 --> 00:00:02,500\nDobrý deň,\n\n"
        "2\n01:02:05,900 --> 01:02:07,123\ntoto je test.\n"
    )


def test_empty_result_gives_empty_files():
    assert to_txt([]) == ""
    assert to_srt([]) == ""
