import json
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from config import ALLOWED_SUFFIXES, KNOWLEDGE_BASE_DIR, sqlite_path

engine = create_engine(
    "sqlite:///" + sqlite_path().resolve().as_posix(),
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_orm_tables() -> None:
    import models_db  # noqa: F401

    Base.metadata.create_all(bind=engine)

_lock = threading.RLock()
_ready = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  keywords TEXT NOT NULL DEFAULT '[]',
  collection TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (user_id, key)
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  size INTEGER NOT NULL,
  suffix TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  content BLOB,
  content_hash TEXT,
  parse_status TEXT,
  parse_error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (folder_id, filename)
);

CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '新对话',
  model_name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  router_via TEXT,
  router_departments TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS message_sources (
  id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
  source_label TEXT NOT NULL,
  department_key TEXT NOT NULL,
  snippet TEXT NOT NULL,
  distance REAL
);

CREATE INDEX IF NOT EXISTS idx_documents_folder ON documents(folder_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_sources_message ON message_sources(message_id);
"""


def init_db() -> None:
    global _ready
    with _lock:
        if _ready:
            return
        path = sqlite_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.executescript(SCHEMA)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
            if "content" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN content BLOB")
            folder_columns = {row[1] for row in conn.execute("PRAGMA table_info(folders)")}
            if "user_id" in folder_columns:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_folders_user ON folders(user_id)")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.commit()
        finally:
            conn.close()
        create_orm_tables()
        conn = sqlite3.connect(path)
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "chat_history" in tables:
                history_columns = {row[1] for row in conn.execute("PRAGMA table_info(chat_history)")}
                if "conversation_id" not in history_columns:
                    conn.execute("ALTER TABLE chat_history ADD COLUMN conversation_id INTEGER")
                if "attachments" not in history_columns:
                    conn.execute("ALTER TABLE chat_history ADD COLUMN attachments TEXT")
            conn.commit()
        finally:
            conn.close()
        _ready = True


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    init_db()
    with _lock:
        conn = sqlite3.connect(sqlite_path(), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _folder_dict(row: sqlite3.Row) -> dict:
    try:
        keywords = json.loads(row["keywords"] or "[]")
    except json.JSONDecodeError:
        keywords = []
    if not isinstance(keywords, list):
        keywords = []
    return {
        "key": row["key"],
        "name": row["name"],
        "description": row["description"],
        "keywords": [str(item) for item in keywords],
        "collection": row["collection"],
    }


def list_folders(user_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM folders WHERE user_id = ? ORDER BY key",
            (user_id,),
        ).fetchall()
    return [_folder_dict(row) for row in rows]


def get_folder(user_id: int, folder_key: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM folders WHERE user_id = ? AND key = ?",
            (user_id, folder_key),
        ).fetchone()
    if row is None:
        return None
    return _folder_dict(row)


def insert_folder(meta: dict, conn: sqlite3.Connection | None = None) -> None:
    keywords = json.dumps(meta["keywords"], ensure_ascii=False)

    def write(current: sqlite3.Connection) -> None:
        try:
            current.execute(
                """
                INSERT INTO folders (user_id, key, name, description, keywords, collection)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (meta["user_id"], meta["key"], meta["name"], meta["description"], keywords, meta["collection"]),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("同名文件夹已存在") from exc

    if conn is not None:
        write(conn)
        return
    with db() as owned:
        write(owned)


def delete_folder_row(user_id: int, folder_key: str) -> None:
    with db() as conn:
        conn.execute("DELETE FROM folders WHERE user_id = ? AND key = ?", (user_id, folder_key))


def update_folder_meta(user_id: int, folder_key: str, name: str, description: str, keywords: list) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE folders
            SET name = ?, description = ?, keywords = ?, updated_at = datetime('now')
            WHERE user_id = ? AND key = ?
            """,
            (name, description, json.dumps(keywords, ensure_ascii=False), user_id, folder_key),
        )


def document_rows(user_id: int, folder_key: str | None = None) -> list[dict]:
    sql = """
        SELECT d.filename AS name, d.size, f.key AS department, d.parse_status, d.parse_error
        FROM documents d
        JOIN folders f ON f.id = d.folder_id
        WHERE f.user_id = ?
    """
    params: tuple = (user_id,)
    if folder_key is not None:
        sql += " AND f.key = ?"
        params = (user_id, folder_key)
    sql += " ORDER BY f.key, d.filename"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "name": row["name"],
            "size": row["size"],
            "department": row["department"],
            "parse_status": row["parse_status"],
            "parse_error": row["parse_error"],
        }
        for row in rows
    ]


def get_document_status(user_id: int, department: str, filename: str) -> dict | None:
    with db() as conn:
        row = conn.execute(
            """
            SELECT d.parse_status, d.parse_error
            FROM documents d
            JOIN folders f ON f.id = d.folder_id
            WHERE f.user_id = ? AND f.key = ? AND d.filename = ?
            """,
            (user_id, department, filename),
        ).fetchone()
    if row is None:
        return None
    return {"status": row["parse_status"], "error": row["parse_error"]}


def _owned_folder_id(conn: sqlite3.Connection, user_id: int, department: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM folders WHERE user_id = ? AND key = ?",
        (user_id, department),
    ).fetchone()
    return None if row is None else int(row["id"])


def upsert_document(
    user_id: int,
    department: str,
    filename: str,
    status: str,
    error: str | None = None,
    *,
    size: int | None = None,
    content_hash: str | None = None,
) -> None:
    """更新解析状态。未提供的大小和哈希保持原值，不改动文件内容。"""
    suffix = Path(filename).suffix.lower()
    storage_path = f"{department}/{filename}"
    with db() as conn:
        folder_id = _owned_folder_id(conn, user_id, department)
        if folder_id is None:
            return
        existing = conn.execute(
            "SELECT id FROM documents WHERE folder_id = ? AND filename = ?",
            (folder_id, filename),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO documents (
                  folder_id, filename, size, suffix, storage_path, content_hash, parse_status, parse_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (folder_id, filename, size or 0, suffix, storage_path, content_hash, status, error),
            )
            return
        conn.execute(
            """
            UPDATE documents SET
              size = COALESCE(?, size),
              suffix = ?,
              storage_path = ?,
              content_hash = COALESCE(?, content_hash),
              parse_status = ?,
              parse_error = ?,
              updated_at = datetime('now')
            WHERE id = ?
            """,
            (size, suffix, storage_path, content_hash, status, error, existing["id"]),
        )


def save_document_bytes(
    user_id: int,
    department: str,
    filename: str,
    data: bytes,
    *,
    status: str,
    content_hash: str | None = None,
    error: str | None = None,
) -> None:
    suffix = Path(filename).suffix.lower()
    storage_path = f"{department}/{filename}"
    with db() as conn:
        folder_id = _owned_folder_id(conn, user_id, department)
        if folder_id is None:
            raise ValueError("文件夹不存在")
        conn.execute(
            """
            INSERT INTO documents (
              folder_id, filename, size, suffix, storage_path, content, content_hash, parse_status, parse_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(folder_id, filename) DO UPDATE SET
              size = excluded.size,
              suffix = excluded.suffix,
              storage_path = excluded.storage_path,
              content = excluded.content,
              content_hash = excluded.content_hash,
              parse_status = excluded.parse_status,
              parse_error = excluded.parse_error,
              updated_at = datetime('now')
            """,
            (folder_id, filename, len(data), suffix, storage_path, data, content_hash, status, error),
        )


def read_document_bytes(user_id: int, department: str, filename: str) -> bytes | None:
    with db() as conn:
        row = conn.execute(
            """
            SELECT d.content
            FROM documents d
            JOIN folders f ON f.id = d.folder_id
            WHERE f.user_id = ? AND f.key = ? AND d.filename = ?
            """,
            (user_id, department, filename),
        ).fetchone()
    if row is None or row["content"] is None:
        return None
    return bytes(row["content"])


def document_blobs(user_id: int, folder_key: str) -> list[tuple[str, bytes]]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT d.filename, d.content
            FROM documents d
            JOIN folders f ON f.id = d.folder_id
            WHERE f.user_id = ? AND f.key = ? AND d.content IS NOT NULL
            ORDER BY d.filename
            """,
            (user_id, folder_key),
        ).fetchall()
    return [(row["filename"], bytes(row["content"])) for row in rows]


def delete_document_row(user_id: int, department: str, filename: str) -> None:
    with db() as conn:
        conn.execute(
            """
            DELETE FROM documents
            WHERE filename = ?
              AND folder_id = (SELECT id FROM folders WHERE user_id = ? AND key = ?)
            """,
            (filename, user_id, department),
        )


def _legacy_status(root: Path) -> dict:
    file_path = root / ".parse_status.json"
    if not file_path.is_file():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def isolate_folders(owner_id: int) -> None:
    """给已有文件夹补上所属用户。旧库里的公共文件夹归到管理员。"""
    with db() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(folders)")}
        if "user_id" in columns:
            conn.execute("UPDATE folders SET user_id = ? WHERE user_id IS NULL", (owner_id,))
            return
        conn.execute("DROP TABLE IF EXISTS folders_new")
        conn.execute(
            """
            CREATE TABLE folders_new (
              id INTEGER PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              key TEXT NOT NULL,
              name TEXT NOT NULL,
              description TEXT NOT NULL,
              keywords TEXT NOT NULL DEFAULT '[]',
              collection TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now')),
              UNIQUE (user_id, key)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO folders_new (id, user_id, key, name, description, keywords, collection, created_at, updated_at)
            SELECT id, ?, key, name, description, keywords, collection, created_at, updated_at
            FROM folders
            """,
            (owner_id,),
        )
        conn.execute("DROP TABLE folders")
        conn.execute("ALTER TABLE folders_new RENAME TO folders")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_folders_user ON folders(user_id)")


def sync_catalog(read_meta: Callable[[Path], dict], owner_id: int) -> None:
    """把磁盘上尚未入库的原文导入指定用户的 documents.content。"""
    root = Path(KNOWLEDGE_BASE_DIR)
    if not root.is_dir():
        return
    legacy = _legacy_status(root)
    with db() as conn:
        owned = {
            row["key"]
            for row in conn.execute("SELECT key FROM folders WHERE user_id = ?", (owner_id,))
        }
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if not path.is_dir() or path.name.startswith("."):
                continue
            if path.name in owned:
                continue
            insert_folder(read_meta(path), conn)
            owned.add(path.name)

        folders = conn.execute(
            "SELECT id, key FROM folders WHERE user_id = ?",
            (owner_id,),
        ).fetchall()
        for folder in folders:
            directory = root / folder["key"]
            if not directory.is_dir():
                continue
            for file_path in sorted(directory.iterdir(), key=lambda item: item.name):
                if not file_path.is_file() or file_path.name.startswith("."):
                    continue
                if file_path.suffix.lower() not in ALLOWED_SUFFIXES:
                    continue
                found = conn.execute(
                    "SELECT id, content IS NULL AS missing FROM documents WHERE folder_id = ? AND filename = ?",
                    (folder["id"], file_path.name),
                ).fetchone()
                if found is not None and not found["missing"]:
                    continue
                payload = file_path.read_bytes()
                if found is None:
                    legacy_row = legacy.get(f"{folder['key']}/{file_path.name}") or {}
                    status = legacy_row.get("status") if isinstance(legacy_row, dict) else None
                    error = legacy_row.get("error") if isinstance(legacy_row, dict) else None
                    conn.execute(
                        """
                        INSERT INTO documents (
                          folder_id, filename, size, suffix, storage_path, content, parse_status, parse_error
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            folder["id"],
                            file_path.name,
                            len(payload),
                            file_path.suffix.lower(),
                            f"{folder['key']}/{file_path.name}",
                            payload,
                            status,
                            error,
                        ),
                    )
                elif found["missing"]:
                    conn.execute(
                        """
                        UPDATE documents
                        SET content = ?, size = ?, updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (payload, len(payload), found["id"]),
                    )
