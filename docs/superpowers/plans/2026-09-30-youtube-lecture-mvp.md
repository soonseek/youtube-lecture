# YouTube Lecture MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 지인이 Codex의 `youtube-lecture` 플러그인을 설치하고 공개 강의 링크를 주면 한국어 학습 자료를 생성해 Railway 공유 페이지를 받는다.

**Architecture:** 플러그인의 로컬 스크립트가 자막을 수집하고 Codex가 내용을 생성한다. 하나의 JSON Schema로 로컬 검증과 서버 검증을 맞춘다. FastAPI 서버가 무계정 업로드를 제한하며 PostgreSQL에 저장하고 공개 페이지를 렌더링한다.

**Tech Stack:** Codex plugin + Python 3.12, `uv`, `youtube-transcript-api`, JSON Schema, FastAPI, psycopg 3, PostgreSQL, Jinja2, HTML/CSS/JavaScript, pytest, Railway.

**Spec:** `docs/superpowers/specs/2026-09-30-youtube-lecture-companion-design.md`

## Global Constraints

- 플러그인 식별자는 `youtube-lecture`; 경로는 `plugins/youtube-lecture/`이다.
- 공개 유튜브 영상 하나씩 처리한다. 자막 확보 실패 시 중단하며 음성 전사는 하지 않는다.
- 자막 전문·목차·요약·용어집의 표시 언어는 한국어이다. 명백한 오전사만 교정하고 불확실한 고유명사·수치는 원문을 유지한다. 외국어 자막을 번역한 경우 표시한다.
- 한 JSON에 `schema_version`, `video`, `transcript`, `outline`, `summary`, `glossary`를 넣고 시점은 밀리초로 저장한다.
- 설치자는 서비스 계정이나 API 키가 필요 없다. 서버에 공통 업로드 비밀 키를 플러그인에 넣지 않는다.
- 업로드 본문 상한은 4 MiB, 동일 IP 한도는 24시간 5건, 전체 한도는 24시간 100건이다.
- 읽기 페이지는 추측하기 어려운 공유 ID로 접근한다. 자막 전문을 보여주되 전체 목록은 공개하지 않는다.
- 공식 공개 플러그인 디렉터리 제출은 범위 밖이다. GitHub 저장소 마켓플레이스로 지인에게 배포한다.

## Review Focus

- `youtube.com.evil.test` 같은 위장 호스트가 입력되면 자막 수집 전에 거부되어야 한다. Task 2의 URL 테스트에 포함한다.
- 자막 시작 시간이 같거나 거꾸로 된 경우 전체 결과가 거부되어야 한다. Task 1의 계약 테스트에 포함한다.
- 외국어 자막의 번역 표시가 빠지면 업로드가 거부되어야 한다. Task 1의 계약 테스트에 포함한다.
- `X-Real-IP`를 임의로 보낸 로컬 요청이 IP별 한도를 우회하지 못해야 한다. Task 4의 한도 테스트에 포함한다.
- 자막에 HTML·스크립트 문자열이 있어도 공유 페이지에서 실행되지 않아야 한다. Task 5의 렌더링 테스트에 포함한다.

## File map

- `plugins/youtube-lecture/.codex-plugin/plugin.json`: 플러그인 식별자·설명·표시 메타데이터.
- `plugins/youtube-lecture/skills/lecture-notes/SKILL.md`: 링크 입력부터 자막 수집, 한국어 생성, 검증, 업로드까지의 Codex 흐름.
- `plugins/youtube-lecture/resources/lecture-v1.schema.json`: JSON 계약의 단일 원본.
- `plugins/youtube-lecture/scripts/contract.py`: 설치된 플러그인의 로컬 JSON 검증.
- `plugins/youtube-lecture/scripts/fetch_transcript.py`: URL 검사, 자막 수집, 로컬 입력 파일 기록.
- `plugins/youtube-lecture/scripts/validate_and_upload.py`: JSON 계약 검증, 로컬 보존, 서버 업로드.
- `plugins/youtube-lecture/pyproject.toml`, `plugins/youtube-lecture/uv.lock`: 설치 후 로컬 실행 의존성.
- `.agents/plugins/marketplace.json`: 저장소 마켓플레이스 목록.
- `server/app/schema.py`: 플러그인의 JSON Schema 로드와 추가 시점 검증.
- `server/app/storage.py`: PostgreSQL 저장과 한도 트랜잭션.
- `server/app/main.py`: FastAPI 경로, 본문 크기 제한, 응답.
- `server/app/templates/lecture.html`, `server/app/static/lecture.css`, `server/app/static/lecture.js`: 공개 학습 화면.
- `Dockerfile`, `pyproject.toml`, `uv.lock`, `railway.json`: 서버 배포와 개발 테스트. Docker 빌드 컨텍스트는 저장소 루트로 하여 플러그인의 스키마를 복사한다.
- `tests/`: 계약, 수집, API, 화면, 업로드 테스트.
- `README.md`, `.gitignore`: 설치와 배포 절차, 비밀 값·생성 결과 제외.

---

### Task 1: JSON 계약과 시점 검증

**Files:** Create `plugins/youtube-lecture/resources/lecture-v1.schema.json`, `plugins/youtube-lecture/scripts/contract.py`, `server/app/schema.py`, `tests/test_schema.py`, root `pyproject.toml` test dependencies.

**Interfaces:** Both `server.app.schema.validate_lecture(payload: dict) -> None` and plugin `contract.validate_lecture(payload: dict) -> None` raise `LectureValidationError` with field paths. Both read the same packaged JSON Schema; small chronological/range checks are duplicated because the plugin must run outside this repository. Cross-check both validators on the same fixtures. Valid range is the last `start_ms + duration_ms` of a nonempty transcript; transcript starts must strictly increase.

- [ ] Write `tests/test_schema.py` for a valid Korean fixture, missing/blank fields, wrong `schema_version`, duplicate/reversed transcript starts, out-of-range outline/note/glossary timestamps, and `is_translated=true` when `source_language` is not `ko`.
- [ ] Run `uv run pytest tests/test_schema.py -q`; confirm failure because validators do not exist.
- [ ] Implement schema and `validate_lecture` with JSON Schema structural checks plus chronological/range checks. Keep error messages user-readable.
- [ ] Run the focused test and confirm pass; commit as `feat: define lecture JSON contract`.

### Task 2: 로컬 자막 수집

**Files:** Create `plugins/youtube-lecture/scripts/fetch_transcript.py`, `plugins/youtube-lecture/pyproject.toml`, `plugins/youtube-lecture/uv.lock`, `tests/test_fetch_transcript.py`.

**Interfaces:** Produces `parse_video_id(url: str) -> str`, `fetch_transcript(video_id: str, preferred_languages: tuple[str, ...] = ("ko", "en")) -> TranscriptFetchResult`, and `split_batches(snippets, max_chars: int = 12000) -> list[list]`. CLI accepts URL and output path, writes metadata and source snippets as UTF-8 JSON. Depend on `youtube-transcript-api`; prioritize Korean, then English, then the first accessible track. Keep original snippet text and timing.

- [ ] Write tests for standard, short, and live YouTube URLs; forged host, invalid ID, missing caption, generated track fallback, 0-second or empty snippets, and a long caption fixture whose batches stay chronological. Mock the transcript library; do not call YouTube in unit tests.
- [ ] Run `uv run pytest tests/test_fetch_transcript.py -q`; confirm failure.
- [ ] Implement parser, language selection, normalized error categories, and CLI output. Document automatic local dependency setup through `uv`; if Python/uv is unavailable, give a clear runtime prerequisite error.
- [ ] Run focused tests and confirm pass; commit as `feat: collect timed YouTube captions`.

### Task 3: 플러그인 생성 흐름과 업로드

**Files:** Create `plugins/youtube-lecture/.codex-plugin/plugin.json`, `plugins/youtube-lecture/skills/lecture-notes/SKILL.md`, `plugins/youtube-lecture/scripts/validate_and_upload.py`, `.agents/plugins/marketplace.json`, `tests/test_plugin_upload.py`.

**Interfaces:** Produces `upload_lecture(payload_path: Path, base_url: str) -> str`; returns server-supplied share URL only after 201 response. The skill first reads all caption batches and merges context notes about subject, flow, repeated terms, and names. It then revisits batches to write `ko_text`, using later clear occurrences to repair likely transcription errors while keeping `source_text` unchanged and preserving uncertain names/numbers. After that it creates overview/section notes/2-level outline/glossary, calls local validator, and uploads once. Validated JSON remains in a local output directory on upload failure.

- [ ] Write tests with a fake HTTP server for valid upload, local validation failure without network request, 429 and 5xx with preserved JSON, and returned share URL verification.
- [ ] Run focused tests and confirm failure.
- [ ] Implement plugin package, skill, upload script, and repo marketplace entry. Until deployment, require `YOUTUBE_LECTURE_SERVER_URL` and fail with a specific configuration error; after deployment Task 6 sets the public default. Never bundle credentials.
- [ ] Run tests, plugin manifest validator, skill quick validator, and local marketplace installation smoke test; commit as `feat: package youtube-lecture plugin`.

### Task 4: 저장 API와 무계정 한도

**Files:** Create `server/app/storage.py`, `server/app/main.py`, `tests/test_api.py`, root `Dockerfile`, `railway.json`.

**Interfaces:** `POST /api/lectures` accepts one contract-valid JSON, returns 201 `{"share_url": ..., "share_id": ...}`. `GET /api/lectures/{share_id}` returns the saved JSON or 404. `GET /health` reports readiness. PostgreSQL tables `lectures(share_id, payload, created_at)` and `upload_events(ip_hash, created_at)` are initialized with idempotent SQL. Atomic transaction enforces sliding 24-hour per-IP and global counts; hash the IP with a server-only salt. Railway's `X-Real-IP` is trusted only behind configured Railway proxy mode; local requests use connection IP.

- [ ] Write API tests for valid save/read, unknown ID, invalid JSON, over 4 MiB, five per-IP successes then 429, 100 global successes then 429, and a forged `X-Real-IP` in local mode. Mock storage for route tests; exercise rate accounting with a disposable PostgreSQL database when available.
- [ ] Run focused tests and confirm failure.
- [ ] Implement routes and storage with parameterized SQL, collision-safe random share IDs, atomic rate-limit transaction, request-size guard, and no public list endpoint. Set `Cache-Control: no-store` for writes.
- [ ] Run focused tests and confirm pass; commit as `feat: store shared lecture results`.

### Task 5: 웹 학습 화면

**Files:** Create `server/app/templates/lecture.html`, `server/app/static/lecture.css`, `server/app/static/lecture.js`, `tests/test_page.py`.

**Interfaces:** `GET /lectures/{share_id}` renders saved video and Korean transcript, outline, summary, glossary. Timestamp controls seek YouTube video; transcript search filters visible caption segments without changing stored content. The page labels translated transcripts and emits `noindex`.

- [ ] Write page tests for visible headings, translated label, nested outline, transcript content, escaped HTML payload, missing ID, and `noindex`.
- [ ] Run focused tests and confirm failure.
- [ ] Implement responsive template and small client script for search and timestamp seeking; render user text through autoescaping templates.
- [ ] Run focused tests and inspect desktop/mobile in a browser; commit as `feat: render lecture study page`.

### Task 6: 설치·배포·실제 흐름

**Files:** Create `README.md`, `.gitignore`; modify plugin manifest/server URL and deployment files as needed.

**Interfaces:** GitHub repo has `.agents/plugins/marketplace.json` with `youtube-lecture` pointing to `./plugins/youtube-lecture`. Railway deploys the server from GitHub with a PostgreSQL `DATABASE_URL`, server-only IP hash salt, and an HTTPS domain. Plugin uses that domain by default.

- [ ] Document one-command marketplace addition, plugin installation, accepted YouTube URLs, Codex desktop/runtime prerequisites, expected failures, Railway setup, limits, and explicit public-by-link transcript behavior.
- [ ] Run `uv run pytest -q`, plugin and marketplace validation, and a local server upload/page smoke test; record observed results.
- [ ] Authenticate `gh` and `railway` only through their normal login flows, then create/connect the intended GitHub repository and Railway project when access is available. Deploy PostgreSQL and server, set Railway root/build configuration and environment values, then record public URL in plugin config.
- [ ] Test one accessible public lecture end to end from a freshly installed repo-marketplace plugin; inspect the returned share page. Use a fixed noisy-caption sample where a term is misrecognized early and correctly spoken later: verify the first-pass context memo precedes correction, the earlier term is corrected using later evidence, uncertain terms remain untouched, and `source_text` stays unchanged. Publish the GitHub repo and give the install command to the user.

## External access currently needed for Task 6

`gh auth status` reports an invalid GitHub token, and `railway whoami` reports unauthorized on this machine. Local implementation and tests can proceed; pushing the repository and deploying Railway require those login sessions or equivalent user-provided access. Do not store credentials in Git.
