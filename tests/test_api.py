import json

from fastapi.testclient import TestClient

from server.app.main import create_app
from server.app.storage import LimitExceeded, check_rate_counts


def payload():
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


class FakeStore:
    def __init__(self):
        self.saved = {}
        self.clients = []

    def create(self, lecture, client_ip):
        ip_count = self.clients.count(client_ip)
        check_rate_counts(ip_count, len(self.clients), per_ip_limit=5, global_limit=100)
        share_id = f"shared{len(self.clients) + 1:04d}"
        self.saved[share_id] = lecture
        self.clients.append(client_ip)
        return share_id

    def get(self, share_id):
        return self.saved.get(share_id)

    def check_ready(self):
        return None


def client(store=None):
    store = store or FakeStore()
    return TestClient(create_app(store=store)), store


def test_upload_and_read_roundtrip():
    api, store = client()
    response = api.post("/api/lectures", json=payload())
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"share_id": "shared0001", "share_url": "http://testserver/lectures/shared0001"}
    assert api.get("/api/lectures/shared0001").json() == payload()
    assert store.clients == ["testclient"]


def test_uploaded_result_is_rendered_at_share_url():
    api, _ = client()
    result = api.post("/api/lectures", json=payload()).json()
    page = api.get(result["share_url"])
    assert page.status_code == 200
    assert "전체 요약" in page.text
    assert "자막 전문" in page.text
    assert "내용" in page.text


def test_invalid_json_and_unknown_id():
    api, _ = client()
    assert api.post("/api/lectures", content=b"{", headers={"content-type": "application/json"}).status_code == 422
    invalid = payload()
    invalid["summary"]["overview"] = " "
    assert api.post("/api/lectures", json=invalid).status_code == 422
    assert api.get("/api/lectures/missing").status_code == 404
    assert api.get("/api/lectures").status_code == 405


def test_rejects_body_over_four_mebibytes():
    api, _ = client()
    body = b"x" * (4 * 1024 * 1024 + 1)
    response = api.post("/api/lectures", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_per_ip_limit_and_forged_header_ignored_locally():
    api, store = client()
    for index in range(5):
        response = api.post("/api/lectures", json=payload(), headers={"X-Real-IP": f"1.2.3.{index}"})
        assert response.status_code == 201
    response = api.post("/api/lectures", json=payload(), headers={"X-Real-IP": "9.9.9.9"})
    assert response.status_code == 429
    assert response.headers["retry-after"]
    assert store.clients == ["testclient"] * 5


def test_global_limit_after_one_hundred_uploads():
    check_rate_counts(0, 99, per_ip_limit=5, global_limit=100)
    try:
        check_rate_counts(0, 100, per_ip_limit=5, global_limit=100)
    except LimitExceeded as error:
        assert error.retry_after_seconds > 0
    else:
        raise AssertionError("global limit was not enforced")


def test_health():
    api, _ = client()
    assert api.get("/health").json() == {"status": "ok"}


def test_health_reports_storage_failure():
    class BrokenStore(FakeStore):
        def check_ready(self):
            raise RuntimeError("database unavailable")

    api, _ = client(BrokenStore())
    assert api.get("/health").status_code == 503
