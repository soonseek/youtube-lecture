"""Fetch timed public YouTube captions on the user's machine."""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from requests.exceptions import RequestException
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApiException,
)


VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
SHORT_HOSTS = {"youtu.be", "www.youtu.be"}


class TranscriptUnavailable(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass
class TranscriptFetchResult:
    video_id: str
    language_code: str
    is_generated: bool
    snippets: list[dict]


def parse_video_id(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port is not None:
        raise ValueError("HTTPS 유튜브 링크를 입력해 주세요")
    host = parsed.hostname or ""
    if host in YOUTUBE_HOSTS and parsed.path == "/watch":
        values = parse_qs(parsed.query, keep_blank_values=True).get("v", [])
        if len(values) != 1:
            raise ValueError("영상 ID가 하나인 유튜브 링크를 입력해 주세요")
        video_id = values[0]
    elif host in YOUTUBE_HOSTS and (parsed.path.startswith("/live/") or parsed.path.startswith("/shorts/")):
        parts = parsed.path.strip("/").split("/")
        video_id = parts[1] if len(parts) == 2 else ""
    elif host in SHORT_HOSTS:
        parts = parsed.path.strip("/").split("/")
        video_id = parts[0] if len(parts) == 1 else ""
    else:
        raise ValueError("지원하는 유튜브 링크가 아닙니다")
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("유효한 11자리 영상 ID를 찾지 못했습니다")
    return video_id


def _track_priority(track, preferred_languages: tuple[str, ...]) -> tuple[int, bool]:
    code = track.language_code.lower()
    for index, language in enumerate(preferred_languages):
        if code == language or code.startswith(language + "-"):
            return index, track.is_generated
    return len(preferred_languages), track.is_generated


def fetch_transcript(video_id: str, preferred_languages: tuple[str, ...] = ("ko", "en")) -> TranscriptFetchResult:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("유효한 11자리 영상 ID가 아닙니다")
    try:
        tracks = list(YouTubeTranscriptApi().list(video_id))
        if not tracks:
            raise TranscriptUnavailable("no_captions", "이 영상에서 사용할 수 있는 자막이 없습니다")
        track = min(tracks, key=lambda item: _track_priority(item, preferred_languages))
        fetched = track.fetch()
    except TranscriptUnavailable:
        raise
    except (NoTranscriptFound, TranscriptsDisabled) as error:
        raise TranscriptUnavailable("no_captions", "이 영상에서 사용할 수 있는 자막이 없습니다") from error
    except (AgeRestricted, PoTokenRequired) as error:
        raise TranscriptUnavailable("restricted", "이 영상의 자막에 접근할 수 없습니다") from error
    except (IpBlocked, RequestBlocked) as error:
        raise TranscriptUnavailable("blocked", "유튜브가 현재 자막 요청을 차단했습니다") from error
    except VideoUnavailable as error:
        raise TranscriptUnavailable("unavailable", "이 영상을 사용할 수 없습니다") from error
    except RequestException as error:
        raise TranscriptUnavailable("network", "유튜브에 연결하지 못했습니다. 네트워크 상태를 확인해 주세요") from error
    except YouTubeTranscriptApiException as error:
        raise TranscriptUnavailable("fetch_failed", "자막을 가져오지 못했습니다") from error

    snippets = []
    for item in fetched:
        text = str(item.text)
        duration_ms = round(float(item.duration) * 1000)
        if text.strip() and duration_ms > 0:
            snippets.append({
                "start_ms": round(float(item.start) * 1000),
                "duration_ms": duration_ms,
                "source_text": text,
            })
    if not snippets:
        raise TranscriptUnavailable("empty", "자막에 읽을 수 있는 내용이 없습니다")
    return TranscriptFetchResult(video_id, track.language_code, track.is_generated, snippets)


def split_batches(snippets: list[dict], max_chars: int = 12000) -> list[list[dict]]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    batches: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for snippet in snippets:
        length = len(snippet["source_text"])
        if current and size + length > max_chars:
            batches.append(current)
            current = []
            size = 0
        current.append(snippet)
        size += length
    if current:
        batches.append(current)
    return batches


def main() -> int:
    parser = argparse.ArgumentParser(description="공개 유튜브 강의의 시간 정보가 있는 자막을 가져옵니다")
    parser.add_argument("url")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        video_id = parse_video_id(args.url)
        result = fetch_transcript(video_id)
    except (ValueError, TranscriptUnavailable) as error:
        print(str(error), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "video_id": result.video_id,
        "url": f"https://www.youtube.com/watch?v={result.video_id}",
        "language_code": result.language_code,
        "is_generated": result.is_generated,
        "snippets": result.snippets,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
