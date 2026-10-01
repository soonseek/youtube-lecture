"""PostgreSQL storage and atomic anonymous-upload limits."""

import hashlib
import hmac
import secrets
import threading
import psycopg


class LimitExceeded(RuntimeError):
    def __init__(self, retry_after_seconds: int = 3600):
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__("업로드 한도를 초과했습니다")


def check_rate_counts(ip_count: int, total_count: int, per_ip_limit: int = 5, global_limit: int = 100) -> None:
    if ip_count >= per_ip_limit or total_count >= global_limit:
        raise LimitExceeded()


class PostgresLectureStore:
    def __init__(self, dsn: str, rate_limit_salt: str, per_ip_limit: int = 5, global_limit: int = 100):
        if not dsn or not rate_limit_salt:
            raise ValueError("DATABASE_URL과 RATE_LIMIT_SALT가 필요합니다")
        self.dsn = dsn
        self.rate_limit_salt = rate_limit_salt.encode("utf-8")
        self.per_ip_limit = per_ip_limit
        self.global_limit = global_limit
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def _connect(self):
        return psycopg.connect(self.dsn)

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS lectures (
                        share_id TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS upload_events (
                        id BIGSERIAL PRIMARY KEY,
                        ip_hash TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS upload_events_created_at_idx ON upload_events (created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS upload_events_ip_hash_idx ON upload_events (ip_hash, created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS lectures_created_at_idx ON lectures (created_at DESC, share_id DESC)")
            self._schema_ready = True

    def check_ready(self) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute("SELECT 1")

    def create(self, payload: dict, client_ip: str) -> str:
        self._ensure_schema()
        ip_hash = hmac.new(self.rate_limit_salt, client_ip.encode("utf-8"), hashlib.sha256).hexdigest()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (715421001,))
                cursor.execute("DELETE FROM upload_events WHERE created_at < now() - interval '24 hours'")
                cursor.execute("SELECT count(*) FROM upload_events WHERE ip_hash = %s", (ip_hash,))
                ip_count = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM upload_events")
                total_count = cursor.fetchone()[0]
                check_rate_counts(ip_count, total_count, self.per_ip_limit, self.global_limit)
                share_id = secrets.token_urlsafe(24)
                cursor.execute(
                    "INSERT INTO lectures (share_id, payload) VALUES (%s, %s::jsonb)",
                    (share_id, psycopg.types.json.Jsonb(payload)),
                )
                cursor.execute("INSERT INTO upload_events (ip_hash) VALUES (%s)", (ip_hash,))
        return share_id

    def get(self, share_id: str) -> dict | None:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM lectures WHERE share_id = %s", (share_id,)).fetchone()
        return row[0] if row else None

    def list_page(self, page: int, page_size: int = 24) -> tuple[list[dict], bool]:
        self._ensure_schema()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT share_id, payload->'video'->>'youtube_id',
                       payload->'video'->>'title', payload->'video'->>'source_language',
                       payload->'video'->>'processed_at', jsonb_array_length(payload->'outline')
                FROM lectures
                ORDER BY created_at DESC, share_id DESC
                LIMIT %s OFFSET %s
            """, (page_size + 1, (page - 1) * page_size)).fetchall()
        items = [
            {"share_id": row[0], "youtube_id": row[1], "title": row[2],
             "source_language": row[3], "processed_at": row[4], "topic_count": row[5]}
            for row in rows[:page_size]
        ]
        return items, len(rows) > page_size
