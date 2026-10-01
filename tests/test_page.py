from fastapi.testclient import TestClient

from server.app.main import create_app


def lecture(translated=False):
    return {
        "schema_version": 1,
        "video": {
            "youtube_id": "abcdefghijk", "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "title": "처음 배우는 데이터 분석", "source_language": "en" if translated else "ko",
            "transcript_language": "ko", "is_translated": translated,
            "processed_at": "2026-09-30T08:00:00Z",
        },
        "transcript": [
            {"start_ms": 1000, "duration_ms": 2000, "source_text": "first", "ko_text": "첫 번째 문장"},
            {"start_ms": 5000, "duration_ms": 2000, "source_text": "second", "ko_text": "두 번째 문장"},
        ],
        "outline": [{"title": "데이터 읽기", "start_ms": 1000, "children": [{"title": "표 살펴보기", "start_ms": 5000}]}],
        "summary": {"overview": "강의 전체 요약", "sections": [{"heading": "핵심", "body": "표의 의미를 배웁니다.", "source_start_ms": 1000}]},
        "glossary": [{"term": "변수", "definition": "값이 변하는 항목", "source_start_ms": 5000}],
    }


class Store:
    def __init__(self, item):
        self.item = item

    def get(self, share_id):
        return self.item if share_id == "shared123" else None


def test_page_has_study_sections_and_timestamp_links():
    response = TestClient(create_app(store=Store(lecture()))).get("/lectures/shared123")
    assert response.status_code == 200
    assert "처음 배우는 데이터 분석" in response.text
    assert "강의 전체 요약" in response.text
    assert "데이터 읽기" in response.text
    assert "표 살펴보기" in response.text
    assert "변수" in response.text
    assert "첫 번째 문장" in response.text
    assert "두 번째 문장" in response.text
    assert 'data-seek-ms="5000"' in response.text
    assert 'id="transcript-search"' in response.text
    assert "youtube-nocookie.com/embed/abcdefghijk" in response.text
    assert "noindex" in response.text


def test_translated_page_is_labeled():
    response = TestClient(create_app(store=Store(lecture(translated=True)))).get("/lectures/shared123")
    assert "한국어 번역 자막" in response.text


def test_user_text_is_escaped_not_executed():
    item = lecture()
    item["transcript"][0]["ko_text"] = '<script>alert("x")</script>'
    response = TestClient(create_app(store=Store(item))).get("/lectures/shared123")
    assert "&lt;script&gt;" in response.text
    assert '<script>alert("x")</script>' not in response.text


def test_unknown_page_returns_404():
    response = TestClient(create_app(store=Store(lecture()))).get("/lectures/missing")
    assert response.status_code == 404


def test_static_assets_use_same_origin_paths_behind_https_proxy():
    client = TestClient(create_app(store=Store(lecture())), base_url="http://testserver")
    lecture_response = client.get("/lectures/shared123", headers={"x-forwarded-proto": "https"})
    missing_response = client.get("/lectures/missing", headers={"x-forwarded-proto": "https"})

    assert 'href="/static/lecture.css"' in lecture_response.text
    assert 'src="/static/lecture.js"' in lecture_response.text
    assert 'href="/static/lecture.css"' in missing_response.text


def test_detail_places_video_and_scrollable_transcript_before_tabbed_notes():
    response = TestClient(create_app(store=Store(lecture()))).get("/lectures/shared123")
    html = response.text
    assert html.index('id="watch-column"') < html.index('id="lecture-player"')
    assert html.index('id="lecture-player"') < html.index('id="transcript"')
    assert html.index('id="transcript"') < html.index('id="study-tabs"')
    assert 'role="tablist"' in html
    assert 'role="tab"' in html
    assert 'role="tabpanel"' in html
    assert 'aria-controls="panel-outline"' in html
    assert 'aria-controls="panel-notes"' in html
    assert 'aria-controls="panel-glossary"' in html
