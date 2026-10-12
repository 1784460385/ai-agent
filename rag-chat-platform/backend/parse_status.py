from database import delete_document_row, get_document_status, upsert_document


def get_status(user_id: int, department: str, filename: str) -> dict | None:
    return get_document_status(user_id, department, filename)


def set_status(
    user_id: int,
    department: str,
    filename: str,
    status: str,
    error: str | None = None,
    *,
    size: int | None = None,
    content_hash: str | None = None,
) -> None:
    upsert_document(
        user_id,
        department,
        filename,
        status,
        error,
        size=size,
        content_hash=content_hash,
    )


def clear_status(user_id: int, department: str, filename: str) -> None:
    delete_document_row(user_id, department, filename)
