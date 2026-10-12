from database import delete_document_row, get_document_status, upsert_document


def get_status(department: str, filename: str) -> dict | None:
    return get_document_status(department, filename)


def set_status(
    department: str,
    filename: str,
    status: str,
    error: str | None = None,
    *,
    size: int | None = None,
    content_hash: str | None = None,
) -> None:
    upsert_document(
        department,
        filename,
        status,
        error,
        size=size,
        content_hash=content_hash,
    )


def clear_status(department: str, filename: str) -> None:
    delete_document_row(department, filename)
