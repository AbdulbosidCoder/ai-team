"""Storage backend: local files (default) or Postgres when DATABASE_URL is set (Render free + Neon/Supabase).

Two kinds of data:
- documents: one JSON value per name (tasks, settings, transactions)
- lines: append-only rows per name (chat messages)

Postgres mode keeps everything in memory and writes only on change, and chat messages are written
in batches (every FLUSH_EVERY rows or when flush() is called by the bot's timer). That keeps a
free serverless database asleep most of the time, so its monthly compute quota is enough.
"""
from __future__ import annotations

import atexit
import copy
import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def load_env_files() -> None:
    """Read .env.local (written by `neon env pull` / `neon deploy`) and .env into os.environ.

    Real environment variables win, then .env.local, then .env. This runs on import, because store
    and money import this module before bot.py gets a chance to load settings.
    """
    for name in (".env.local", ".env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env_files()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
FLUSH_EVERY = int(os.getenv("DB_FLUSH_EVERY", "25"))
_lock = threading.RLock()


# ---------------- file backend ----------------

class FileBackend:
    def __init__(self, doc_paths: dict[str, Path], line_dir_for):
        self.doc_paths = doc_paths
        self.line_dir_for = line_dir_for  # name -> Path of a .jsonl file

    def get_doc(self, name, default):
        try:
            return json.loads(self.doc_paths[name].read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return copy.deepcopy(default)

    def put_doc(self, name, data):
        path = self.doc_paths[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def append(self, name, row):
        path = self.line_dir_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def lines(self, prefix):
        out = []
        base = self.line_dir_for(prefix + "x").parent
        if not base.exists():
            return out
        for path in base.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def flush(self):
        pass


# ---------------- postgres backend ----------------

class PostgresBackend:
    def __init__(self, url: str):
        import psycopg  # only needed in Postgres mode

        self.psycopg = psycopg
        self.url = url
        self.docs: dict = {}
        self.line_cache: dict[str, list] = {}
        self.pending: list[tuple[str, dict]] = []
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS kv (name text PRIMARY KEY, data jsonb NOT NULL, updated timestamptz DEFAULT now())")
            c.execute("CREATE TABLE IF NOT EXISTS lines (id bigserial PRIMARY KEY, name text NOT NULL, data jsonb NOT NULL)")
            for name, data in c.execute("SELECT name, data FROM kv").fetchall():
                self.docs[name] = data
            for name, data in c.execute("SELECT name, data FROM lines ORDER BY id").fetchall():
                self.line_cache.setdefault(name, []).append(data)
        log.info("Postgres storage: %d documents, %d message rows loaded",
                 len(self.docs), sum(len(v) for v in self.line_cache.values()))
        atexit.register(self.flush)

    def _conn(self):
        # DATABASE_URL from Neon is the pooled (-pooler, PgBouncer transaction mode) string, so turn off
        # psycopg's automatic server-side prepared statements, which don't survive a pooled backend swap.
        return self.psycopg.connect(self.url, autocommit=True, connect_timeout=20, prepare_threshold=None)

    def get_doc(self, name, default):
        with _lock:
            return copy.deepcopy(self.docs.get(name, default))

    def put_doc(self, name, data):
        with _lock:
            if self.docs.get(name) == data:
                return
            self.docs[name] = copy.deepcopy(data)
            payload = json.dumps(data, ensure_ascii=False)
        with self._conn() as c:
            c.execute(
                "INSERT INTO kv (name, data, updated) VALUES (%s, %s::jsonb, now()) "
                "ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data, updated = now()",
                (name, payload),
            )

    def append(self, name, row):
        with _lock:
            self.line_cache.setdefault(name, []).append(row)
            self.pending.append((name, row))
            full = len(self.pending) >= FLUSH_EVERY
        if full:
            self.flush()

    def lines(self, prefix):
        with _lock:
            return [copy.deepcopy(r) for name, rows in self.line_cache.items() if name.startswith(prefix) for r in rows]

    def flush(self):
        with _lock:
            batch, self.pending = self.pending, []
        if not batch:
            return
        try:
            with self._conn() as c, c.cursor() as cur:
                cur.executemany("INSERT INTO lines (name, data) VALUES (%s, %s::jsonb)",
                                [(n, json.dumps(r, ensure_ascii=False)) for n, r in batch])
        except Exception:
            log.exception("flush failed, will retry")
            with _lock:
                self.pending = batch + self.pending


_backend = None


def backend(doc_paths: dict[str, Path], line_path_for):
    """Create the backend once. Store and money modules pass their file layout for file mode."""
    global _backend
    if _backend is None:
        _backend = PostgresBackend(DATABASE_URL) if DATABASE_URL else FileBackend(doc_paths, line_path_for)
    elif isinstance(_backend, FileBackend):
        _backend.doc_paths.update(doc_paths)
    return _backend


def flush():
    if _backend is not None:
        _backend.flush()
