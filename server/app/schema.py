"""Server-side validation of the shared lecture payload."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "plugins" / "youtube-lecture" / "resources" / "lecture-v1.schema.json"


class LectureValidationError(ValueError):
    pass


def validate_lecture(payload: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload), key=lambda e: list(map(str, e.path)))
    if errors:
        error = errors[0]
        location = ".".join(map(str, error.path)) or "root"
        raise LectureValidationError(f"{location}: {error.message}")

    if payload["video"]["is_translated"] != (payload["video"]["source_language"] != "ko"):
        raise LectureValidationError("video.is_translated: 원본 언어와 번역 표시가 일치하지 않습니다")

    transcript = payload["transcript"]
    previous = -1
    for index, segment in enumerate(transcript):
        start = segment["start_ms"]
        if start <= previous:
            raise LectureValidationError(f"transcript.{index}.start_ms: 자막 시점은 엄격히 증가해야 합니다")
        previous = start

    maximum = transcript[-1]["start_ms"] + transcript[-1]["duration_ms"]

    def check_time(value: int, path: str) -> None:
        if value < transcript[0]["start_ms"] or value > maximum:
            raise LectureValidationError(f"{path}: 자막 범위를 벗어난 시점입니다")

    last_main = -1
    for index, item in enumerate(payload["outline"]):
        start = item["start_ms"]
        check_time(start, f"outline.{index}.start_ms")
        if start < last_main:
            raise LectureValidationError(f"outline.{index}.start_ms: 목차 순서가 거꾸로입니다")
        last_main = start
        last_child = start
        for child_index, child in enumerate(item["children"]):
            child_start = child["start_ms"]
            check_time(child_start, f"outline.{index}.children.{child_index}.start_ms")
            if child_start < last_child:
                raise LectureValidationError(f"outline.{index}.children.{child_index}.start_ms: 세부 목차 순서가 거꾸로입니다")
            last_child = child_start

    for index, item in enumerate(payload["summary"]["sections"]):
        check_time(item["source_start_ms"], f"summary.sections.{index}.source_start_ms")
    for index, item in enumerate(payload["glossary"]):
        check_time(item["source_start_ms"], f"glossary.{index}.source_start_ms")
