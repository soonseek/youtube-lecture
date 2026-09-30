import copy
import importlib.util
from pathlib import Path

import pytest

from server.app.schema import LectureValidationError as ServerError
from server.app.schema import validate_lecture as validate_server


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = ROOT / "plugins/youtube-lecture/scripts/contract.py"
spec = importlib.util.spec_from_file_location("lecture_contract", CONTRACT_FILE)
contract = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(contract)


@pytest.fixture
def lecture():
    return {
        "schema_version": 1,
        "video": {
            "youtube_id": "abcdefghijk",
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "title": "예제 강의",
            "source_language": "ko",
            "transcript_language": "ko",
            "is_translated": False,
            "processed_at": "2026-09-30T08:00:00Z",
        },
        "transcript": [
            {"start_ms": 1000, "duration_ms": 2000, "source_text": "첫 문장", "ko_text": "첫 문장"},
            {"start_ms": 5000, "duration_ms": 2000, "source_text": "둘째 문장", "ko_text": "둘째 문장"},
        ],
        "outline": [
            {"title": "첫 주제", "start_ms": 1000, "children": [{"title": "세부 주제", "start_ms": 5000}]}
        ],
        "summary": {
            "overview": "강의 전체 요약",
            "sections": [{"heading": "첫 주제", "body": "핵심 내용", "source_start_ms": 1000}],
        },
        "glossary": [{"term": "용어", "definition": "설명", "source_start_ms": 5000}],
    }


@pytest.fixture(params=[(validate_server, ServerError), (contract.validate_lecture, contract.LectureValidationError)])
def validator(request):
    return request.param


def test_valid_korean_lecture(lecture, validator):
    validate, _ = validator
    validate(copy.deepcopy(lecture))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.pop("summary"),
        lambda value: value["video"].__setitem__("title", "  "),
        lambda value: value.__setitem__("schema_version", 2),
        lambda value: value["transcript"][1].__setitem__("start_ms", 1000),
        lambda value: value["transcript"][1].__setitem__("start_ms", 500),
        lambda value: value["outline"][0].__setitem__("start_ms", 8000),
        lambda value: value["summary"]["sections"][0].__setitem__("source_start_ms", 8000),
        lambda value: value["glossary"][0].__setitem__("source_start_ms", 8000),
        lambda value: value["video"].__setitem__("source_language", "en"),
    ],
)
def test_rejects_invalid_contract(lecture, validator, mutate):
    validate, error = validator
    mutate(lecture)
    with pytest.raises(error):
        validate(lecture)
