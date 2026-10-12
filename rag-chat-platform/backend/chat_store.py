import json
import sqlite3

from database import db


def list_conversations() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, model_name, created_at
            FROM conversations
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def conversation_exists(conversation_id: int) -> bool:
    with db() as conn:
        row = conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    return row is not None


def _sources(conn: sqlite3.Connection, message_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT ms.source_label, ms.department_key, ms.snippet, ms.distance, f.name AS department_name
        FROM message_sources ms
        LEFT JOIN folders f ON f.key = ms.department_key
        WHERE ms.message_id = ?
        ORDER BY ms.id
        """,
        (message_id,),
    ).fetchall()
    sources = []
    for index, row in enumerate(rows, start=1):
        snippet = row["snippet"] or ""
        sources.append(
            {
                "index": index,
                "source": row["source_label"],
                "department": row["department_key"],
                "department_name": row["department_name"] or row["department_key"],
                "preview": " ".join(snippet.split())[:80],
                "excerpt": snippet,
            }
        )
    return sources


def get_conversation(conversation_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT id, title, model_name, created_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        messages = conn.execute(
            """
            SELECT id, role, content, router_via, router_departments
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id
            """,
            (conversation_id,),
        ).fetchall()
        payload = []
        for message in messages:
            item: dict = {"role": message["role"], "content": message["content"]}
            if message["router_via"]:
                try:
                    departments = json.loads(message["router_departments"] or "[]")
                except json.JSONDecodeError:
                    departments = []
                item["router"] = {"via": message["router_via"], "departments": departments}
            sources = _sources(conn, message["id"])
            if sources:
                item["sources"] = sources
            payload.append(item)
        return {**dict(row), "messages": payload}


def create_conversation(title: str, model_name: str) -> dict:
    cleaned = " ".join(title.split())[:32] or "新对话"
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO conversations (title, model_name) VALUES (?, ?)",
            (cleaned, model_name or "deepseek-flash"),
        )
        row = conn.execute(
            "SELECT id, title, model_name, created_at FROM conversations WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)


def delete_conversation(conversation_id: int) -> bool:
    with db() as conn:
        cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return cursor.rowcount > 0


def add_message(conversation_id: int, role: str, content: str) -> int:
    with db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (conversation_id, role, content),
        )
        return int(cursor.lastrowid)


def _document_id(conn: sqlite3.Connection, department: str, source: str) -> int | None:
    rows = conn.execute(
        """
        SELECT d.id, d.filename
        FROM documents d
        JOIN folders f ON f.id = d.folder_id
        WHERE f.key = ?
        """,
        (department,),
    ).fetchall()
    best_id = None
    best_len = -1
    for row in rows:
        filename = row["filename"] or ""
        if filename and filename in source and len(filename) > best_len:
            best_id = row["id"]
            best_len = len(filename)
    return best_id


def _distance(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save_assistant_message(
    conversation_id: int,
    content: str,
    via: str | None,
    departments: list[dict],
    hits: list[dict],
) -> None:
    departments_json = json.dumps(departments, ensure_ascii=False)
    try:
        with db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, router_via, router_departments)
                VALUES (?, 'assistant', ?, ?, ?)
                """,
                (conversation_id, content, via, departments_json),
            )
            message_id = int(cursor.lastrowid)
            for hit in hits:
                snippet = str(hit.get("content") or "")
                if not snippet:
                    continue
                department = str(hit.get("department") or "")
                source = str(hit.get("source") or "未知来源")
                conn.execute(
                    """
                    INSERT INTO message_sources (
                      message_id, document_id, source_label, department_key, snippet, distance
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        _document_id(conn, department, source),
                        source,
                        department,
                        snippet[:8000],
                        _distance(hit.get("distance")),
                    ),
                )
    except sqlite3.IntegrityError:
        return
