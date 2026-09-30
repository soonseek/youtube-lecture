# youtube-lecture

공개 유튜브 강의 링크를 Codex에 주면 자막을 읽고 한국어 학습 자료로 정리하는 Codex 플러그인입니다. 결과에는 **정제한 자막 전문, 2단 목차, 전체·구간별 요약 노트, 용어집**이 들어갑니다. 한 JSON 파일로 검증한 뒤 Railway 서버에 저장하고 공유 페이지 링크를 돌려줍니다.

자막 수집과 내용 생성은 플러그인을 설치한 사람의 컴퓨터와 Codex 세션에서 진행합니다. Railway는 완성된 JSON의 저장과 화면 표시를 맡습니다. 별도 서비스 가입이나 API 키는 필요하지 않습니다.

## 지인에게 배포하기

공개 저장소는 [soonseek/youtube-lecture](https://github.com/soonseek/youtube-lecture)입니다. 다음 두 명령으로 플러그인을 설치할 수 있습니다.

```powershell
codex plugin marketplace add soonseek/youtube-lecture --ref main
codex plugin add youtube-lecture@youtube-lecture-tools
```

Codex에서 “이 유튜브 강의를 목차·요약·용어집으로 정리해 줘: https://www.youtube.com/watch?v=...”처럼 요청합니다. `https://youtu.be/...`, `youtube.com/live/...`, `youtube.com/shorts/...` 링크도 받습니다. 영상 하나씩 처리합니다.

공유 서버 기본 주소는 `https://youtube-lecture-web-production.up.railway.app`입니다. 다른 서버를 시험할 때만 `YOUTUBE_LECTURE_SERVER_URL`로 바꿀 수 있습니다.

```powershell
$env:YOUTUBE_LECTURE_SERVER_URL = 'https://<Railway-도메인>'
```

로컬 실행에는 Python 3.12~3.14와 `uv`가 필요합니다. 플러그인의 첫 스크립트 실행에서 `uv`가 잠금 파일에 맞춰 패키지를 설치합니다. Codex 자체의 사용 환경은 별도로 준비되어 있어야 합니다.

## 처리 방식

1. 로컬 스크립트가 유튜브 링크를 검사하고 접근 가능한 공개 자막의 원문과 시점을 가져옵니다. 한국어 자막을 우선하며, 없으면 영어 또는 다른 자막을 사용합니다.
2. Codex가 **자막 전체를 먼저 읽고** 강의 흐름과 반복되는 용어를 메모합니다. 이후 다시 읽으면서 근거가 분명한 오전사만 교정합니다. 불확실한 이름과 숫자는 그대로 둡니다. 외국어 자막은 한국어로 번역해 표시합니다.
3. Codex가 목차·노트·용어집을 만들고 `lecture-v1.schema.json`으로 JSON과 시점 범위를 검사합니다. 원문 자막도 JSON에 남깁니다.
4. 로컬 스크립트가 검증된 JSON을 서버에 한 번 업로드합니다. 실패하면 JSON 파일을 로컬 `output/`에 남깁니다.

공개 자막을 구할 수 없는 영상, 접근 제한 영상, 유튜브 측 차단은 오류를 보여주고 중단합니다. 영상 음성을 별도로 전사하지 않습니다. `youtube-transcript-api`는 별도 유료 API 키 없이 쓰는 라이브러리이지만 유튜브의 비공식 공개 자막 경로에 의존하므로 모든 영상에서 성공하지는 않습니다.

## 공유 범위와 운영 한도

공유 URL을 아는 사람은 가입 없이 **한국어 자막 전문까지** 읽을 수 있습니다. 공유 ID는 무작위이며 공개 목록은 제공하지 않습니다. 페이지에는 검색 엔진 색인 방지 지시가 포함됩니다. 공유 URL을 받은 사람에게는 전문이 공개된다는 점을 안내하세요.

기본 업로드 한도는 JSON 4 MiB, IP당 24시간 5건, 서비스 전체 24시간 100건입니다. 가입 없는 서비스의 오용을 줄이는 기본 제한이며 완전한 접근 통제는 아닙니다. `PER_IP_DAILY_LIMIT`, `GLOBAL_DAILY_LIMIT`로 건수만 조정할 수 있습니다.

## 개발

저장소 루트에서 실행합니다.

```powershell
uv sync --frozen
uv run pytest -q
codex plugin marketplace add .
codex plugin add youtube-lecture@youtube-lecture-tools
```

주요 경로:

| 경로 | 역할 |
| --- | --- |
| `plugins/youtube-lecture/` | Codex 플러그인, 자막 수집·검증·업로드 스크립트 |
| `.agents/plugins/marketplace.json` | 저장소 마켓플레이스 목록 |
| `server/app/` | FastAPI, PostgreSQL 저장, 공유 페이지 |
| `tests/` | JSON 계약, 자막 수집, API, 페이지, 업로드 테스트 |

## Railway 배포

1. 이 저장소를 GitHub에 올리고 Railway 프로젝트에 **저장소 루트**를 소스로 하는 웹 서비스를 만듭니다. 루트의 `Dockerfile`이 서버와 플러그인의 JSON Schema를 함께 복사합니다.
2. 같은 프로젝트에 PostgreSQL을 추가합니다. 웹 서비스의 `DATABASE_URL`을 PostgreSQL 서비스의 `DATABASE_URL` 참조 변수로 연결합니다(예: `${{Postgres.DATABASE_URL}}`; 실제 서비스 이름에 맞게 변경).
3. 웹 서비스 변수 `RATE_LIMIT_SALT`에 충분히 긴 임의 문자열을 설정합니다. 이 값은 서버에서 IP를 해시할 때만 사용하고 Git이나 플러그인에 넣지 않습니다. `TRUST_RAILWAY_PROXY=1`을 설정합니다.
4. 웹 서비스의 공개 HTTPS 도메인을 생성하고 `PUBLIC_BASE_URL=https://<도메인>`으로 설정합니다. 서비스 설정에서 Healthcheck Path를 `/health`로 지정합니다. `https://<도메인>/health`가 `{"status":"ok"}`를 반환하는지 확인합니다. 이 상태 확인은 데이터베이스 연결도 점검합니다.
5. 공개 HTTPS 도메인이 바뀌면 `plugins/youtube-lecture/scripts/validate_and_upload.py`의 기본 서버 URL을 갱신해 GitHub에 올립니다.
6. 실제 공개 강의 하나로 설치→자막 수집→JSON 생성→업로드→공유 페이지를 확인합니다. 공개 페이지에서 목차 시점 이동, 자막 검색, 모바일 표시와 번역 표기를 확인합니다.

필수 서버 변수: `DATABASE_URL`, `RATE_LIMIT_SALT`, `PUBLIC_BASE_URL`, `TRUST_RAILWAY_PROXY=1`. 값이 없거나 데이터베이스를 사용할 수 없으면 `/health`가 503을 반환합니다. PostgreSQL 테이블은 첫 연결 때 생성됩니다.

참고: [Railway Dockerfile 배포](https://docs.railway.com/builds/dockerfiles), [Railway PostgreSQL](https://docs.railway.com/databases/postgresql), [Railway 변수 참조](https://docs.railway.com/integrations/api/manage-variables).

## 현재 상태

로컬 코드와 테스트를 마쳤고 GitHub 저장소와 Railway 서버를 게시했습니다. 실제 강의 한 건의 전체 생성·업로드 결과는 마지막 검증 단계에서 확인합니다.
