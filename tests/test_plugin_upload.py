import importlib.util
import json
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "plugins/youtube-lecture/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("validate_and_upload", SCRIPTS / "validate_and_upload.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def valid_payload():
    return {
        "schema_version": 1,
        "video": {
            "youtube_id": "abcdefghijk", "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "title": "강의", "source_language": "ko", "transcript_language": "ko",
            "is_translated": False, "processed_at": "2026-09-30T08:00:00Z",
        },
        "transcript": [{"start_ms": 0, "duration_ms": 2000, "source_text": "내용", "ko_text": "내용"}],
        "outline": [{"title": "목차", "start_ms": 0, "children": [{"title": "세부", "start_ms": 0}]}],
        "summary": {"overview": "전체 요약", "sections": [{"heading": "목차", "body": "노트", "source_start_ms": 0}]},
        "glossary": [{"term": "용어", "definition": "풀이", "source_start_ms": 0}],
    }


@contextmanager
def upload_server(status=201):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, self.headers, self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if status == 201:
                base = f"http://127.0.0.1:{self.server.server_port}"
                self.wfile.write(json.dumps({"share_url": base + "/lectures/shared123", "share_id": "shared123"}).encode())
            else:
                self.wfile.write(b'{"detail":"unavailable"}')

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def write_payload(tmp_path, payload):
    path = tmp_path / "result.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_validated_payload_is_posted_once_and_share_url_returned(tmp_path):
    path = write_payload(tmp_path, valid_payload())
    with upload_server() as (base, received):
        share_url = module.upload_lecture(path, base)
    assert share_url == base + "/lectures/shared123"
    assert len(received) == 1
    assert received[0][0] == "/api/lectures"
    assert json.loads(received[0][2]) == valid_payload()
    assert path.exists()


def test_invalid_payload_never_reaches_network(tmp_path):
    payload = valid_payload()
    payload["summary"]["overview"] = " "
    path = write_payload(tmp_path, payload)
    with pytest.raises(ValueError):
        module.upload_lecture(path, "http://127.0.0.1:1")
    assert path.exists()


@pytest.mark.parametrize("status", [429, 500])
def test_upload_failure_preserves_json_and_reports_status(tmp_path, status):
    path = write_payload(tmp_path, valid_payload())
    with upload_server(status) as (base, received):
        with pytest.raises(module.UploadError) as error:
            module.upload_lecture(path, base)
    assert str(status) in str(error.value)
    assert len(received) == 1
    assert path.exists()
