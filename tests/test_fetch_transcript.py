import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from requests.exceptions import ConnectionError as RequestConnectionError


SCRIPT = Path(__file__).resolve().parents[1] / "plugins/youtube-lecture/scripts/fetch_transcript.py"
spec = importlib.util.spec_from_file_location("fetch_transcript", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abcdefghijk&t=30s",
        "https://youtu.be/abcdefghijk",
        "https://www.youtube.com/live/abcdefghijk?feature=share",
    ],
)
def test_parse_video_id_accepts_known_youtube_urls(url):
    assert module.parse_video_id(url) == "abcdefghijk"


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com.evil.test/watch?v=abcdefghijk",
        "http://www.youtube.com/watch?v=abcdefghijk",
        "https://youtu.be/not-an-id",
        "https://www.youtube.com/watch?v=abcdefghijk&v=12345678901",
        "file:///watch?v=abcdefghijk",
    ],
)
def test_parse_video_id_rejects_untrusted_or_ambiguous_urls(url):
    with pytest.raises(ValueError):
        module.parse_video_id(url)


class FakeTrack:
    def __init__(self, language_code, is_generated, snippets):
        self.language_code = language_code
        self.is_generated = is_generated
        self.snippets = snippets

    def fetch(self):
        return self.snippets


def fake_api(monkeypatch, tracks):
    class FakeApi:
        def list(self, video_id):
            assert video_id == "abcdefghijk"
            return tracks

    monkeypatch.setattr(module, "YouTubeTranscriptApi", FakeApi)


def test_prefers_korean_generated_over_english_manual(monkeypatch):
    english = FakeTrack("en", False, [SimpleNamespace(text="English", start=1.0, duration=2.0)])
    korean = FakeTrack("ko", True, [SimpleNamespace(text="한국어", start=1.25, duration=2.5)])
    fake_api(monkeypatch, [english, korean])

    result = module.fetch_transcript("abcdefghijk")

    assert result.language_code == "ko"
    assert result.is_generated is True
    assert result.snippets == [{"start_ms": 1250, "duration_ms": 2500, "source_text": "한국어"}]


def test_prefers_manual_track_within_same_language(monkeypatch):
    generated = FakeTrack("ko", True, [SimpleNamespace(text="자동", start=1, duration=1)])
    manual = FakeTrack("ko", False, [SimpleNamespace(text="수동", start=1, duration=1)])
    fake_api(monkeypatch, [generated, manual])

    result = module.fetch_transcript("abcdefghijk")

    assert result.snippets[0]["source_text"] == "수동"


def test_uses_first_available_language_when_korean_and_english_missing(monkeypatch):
    fake_api(monkeypatch, [FakeTrack("ja", True, [SimpleNamespace(text="本文", start=0, duration=1)])])
    assert module.fetch_transcript("abcdefghijk").language_code == "ja"


def test_drops_empty_and_zero_duration_snippets(monkeypatch):
    snippets = [
        SimpleNamespace(text=" ", start=0, duration=1),
        SimpleNamespace(text="무음", start=1, duration=0),
        SimpleNamespace(text="내용", start=2, duration=1),
    ]
    fake_api(monkeypatch, [FakeTrack("ko", True, snippets)])
    assert module.fetch_transcript("abcdefghijk").snippets == [
        {"start_ms": 2000, "duration_ms": 1000, "source_text": "내용"}
    ]


def test_empty_usable_caption_stops_processing(monkeypatch):
    fake_api(monkeypatch, [FakeTrack("ko", True, [SimpleNamespace(text=" ", start=0, duration=1)])])
    with pytest.raises(module.TranscriptUnavailable) as error:
        module.fetch_transcript("abcdefghijk")
    assert error.value.code == "empty"


def test_no_caption_track_stops_processing(monkeypatch):
    fake_api(monkeypatch, [])
    with pytest.raises(module.TranscriptUnavailable) as error:
        module.fetch_transcript("abcdefghijk")
    assert error.value.code == "no_captions"


def test_network_failure_has_short_user_message(monkeypatch):
    class OfflineApi:
        def list(self, video_id):
            raise RequestConnectionError("network blocked")

    monkeypatch.setattr(module, "YouTubeTranscriptApi", OfflineApi)
    with pytest.raises(module.TranscriptUnavailable) as error:
        module.fetch_transcript("abcdefghijk")
    assert error.value.code == "network"
    assert "연결" in str(error.value)


def test_split_batches_keeps_order_and_every_snippet():
    snippets = [{"start_ms": n * 1000, "source_text": str(n)} for n in range(8)]
    batches = module.split_batches(snippets, max_chars=3)
    assert len(batches) > 1
    assert [item["start_ms"] for batch in batches for item in batch] == [n * 1000 for n in range(8)]
    assert all(batch for batch in batches)
