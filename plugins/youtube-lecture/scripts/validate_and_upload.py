"""Validate and upload a completed lecture JSON file."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from contract import validate_lecture


MAX_BODY_BYTES = 4 * 1024 * 1024
DEFAULT_SERVER_URL = "https://youtube-lecture-web-production.up.railway.app"


class UploadError(RuntimeError):
    pass


def _base_url(value: str) -> str:
    parsed = urlsplit(value.rstrip("/"))
    local = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    if not parsed.hostname or (parsed.scheme != "https" and not local) or parsed.username or parsed.password:
        raise UploadError("HTTPS 서버 주소가 필요합니다")
    if parsed.path or parsed.query or parsed.fragment:
        raise UploadError("서버 주소에는 도메인만 입력해 주세요")
    return value.rstrip("/")


def upload_lecture(payload_path: Path, base_url: str) -> str:
    payload_path = Path(payload_path)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    validate_lecture(payload)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_BODY_BYTES:
        raise UploadError("JSON이 4 MiB 업로드 한도를 넘었습니다")
    base = _base_url(base_url)
    request = Request(
        base + "/api/lectures",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 201:
                raise UploadError(f"서버가 예상하지 못한 상태 {response.status}를 반환했습니다")
            result = json.loads(response.read())
    except HTTPError as error:
        if error.code == 429:
            raise UploadError("업로드 한도를 초과했습니다 (HTTP 429). 나중에 다시 시도해 주세요") from error
        raise UploadError(f"업로드에 실패했습니다 (HTTP {error.code})") from error
    except URLError as error:
        raise UploadError("서버에 연결하지 못했습니다. JSON 파일은 로컬에 남아 있습니다") from error

    share_url = result.get("share_url")
    if not isinstance(share_url, str):
        raise UploadError("서버 응답에 공유 URL이 없습니다")
    shared = urlsplit(share_url)
    origin = urlsplit(base)
    if (shared.scheme, shared.netloc) != (origin.scheme, origin.netloc) or not shared.path.startswith("/lectures/"):
        raise UploadError("서버 응답의 공유 URL이 올바르지 않습니다")
    return share_url


def main() -> int:
    parser = argparse.ArgumentParser(description="강의 JSON을 검증하고 공유 서버에 업로드합니다")
    parser.add_argument("payload", type=Path)
    parser.add_argument("--server-url", default=os.getenv("YOUTUBE_LECTURE_SERVER_URL") or DEFAULT_SERVER_URL)
    args = parser.parse_args()
    if not args.server_url:
        print("서버 URL이 설정되지 않았습니다. YOUTUBE_LECTURE_SERVER_URL을 설정해 주세요", file=sys.stderr)
        return 2
    try:
        print(upload_lecture(args.payload, args.server_url))
        return 0
    except (ValueError, UploadError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
