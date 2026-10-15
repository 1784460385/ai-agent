"""validators 模块测试。

测文件名清理、扩展名校验、magic bytes 校验、大小限制。
不依赖数据库,只测纯函数。
"""

import pytest
from fastapi import HTTPException

from validators import check_payload, safe_filename


# ---- safe_filename ----
def test_safe_filename_normal():
    assert safe_filename("hello.pdf") == "hello.pdf"


def test_safe_filename_strips_path():
    """防止目录穿越:只保留 basename。"""
    assert safe_filename("../etc/passwd.pdf") == "passwd.pdf"
    assert safe_filename("..\\windows\\evil.pdf") == "evil.pdf"
    assert safe_filename("subdir/file.docx") == "file.docx"


def test_safe_filename_rejects_none():
    with pytest.raises(HTTPException) as exc:
        safe_filename(None)
    assert exc.value.status_code == 400


def test_safe_filename_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        safe_filename("")
    assert exc.value.status_code == 400


def test_safe_filename_rejects_dot():
    with pytest.raises(HTTPException) as exc:
        safe_filename(".")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        safe_filename("..")
    assert exc.value.status_code == 400


def test_safe_filename_rejects_hidden():
    with pytest.raises(HTTPException) as exc:
        safe_filename(".htaccess")
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "name",
    [
        "evil.exe",
        "shell.bat",
        "powershell.ps1",
        "dropper.dll",
        "archive.zip",
    ],
)
def test_safe_filename_blocks_dangerous(name: str):
    """黑名单后缀一律拒绝。"""
    with pytest.raises(HTTPException) as exc:
        safe_filename(name)
    assert exc.value.status_code == 400


def test_safe_filename_rejects_unsupported_ext():
    """未声明的扩展名(不在 SUPPORTED_FORMATS 也未在 coming-soon)。"""
    with pytest.raises(HTTPException) as exc:
        safe_filename("data.csv.zip")  # .zip 被黑名单,走不到这里
    assert exc.value.status_code == 400


def test_safe_filename_case_insensitive():
    """后缀大小写不敏感:统一按 .lower() 比较。"""
    assert safe_filename("Photo.JPG") == "Photo.JPG"  # 返回原名,只用来校验


def test_safe_filename_gif_coming_soon():
    """GIF 是 coming-soon,必须单独抛错提示。"""
    with pytest.raises(HTTPException) as exc:
        safe_filename("funny.gif")
    assert exc.value.status_code == 400
    assert "即将支持" in str(exc.value.detail)


# ---- check_payload ----
def test_check_payload_pdf_valid():
    payload = b"%PDF-1.4\n..."
    check_payload(payload, ".pdf")  # 不抛


def test_check_payload_pdf_invalid():
    """PDF 但内容不是 %PDF 开头。"""
    with pytest.raises(HTTPException) as exc:
        check_payload(b"plain text", ".pdf")
    assert exc.value.status_code == 400


def test_check_payload_docx_zip_magic():
    """docx 是 zip,必须以 PK 开头。"""
    payload = b"PK\x03\x04hello"
    check_payload(payload, ".docx")
    with pytest.raises(HTTPException):
        check_payload(b"plain text", ".docx")


def test_check_payload_png_magic():
    payload = b"\x89PNG\r\n\x1a\n"
    check_payload(payload, ".png")
    with pytest.raises(HTTPException):
        check_payload(b"plain text", ".png")


def test_check_payload_jpg_magic():
    payload = b"\xff\xd8\xff\xe0"
    check_payload(payload, ".jpg")
    with pytest.raises(HTTPException):
        check_payload(b"plain text", ".jpg")


def test_check_payload_webp_secondary():
    """WEBP 不光要 RIFF 头,还要 8~12 字节是 WEBP。"""
    with pytest.raises(HTTPException):
        check_payload(b"RIFF\x00\x00\x00\x00WAVE", ".webp")


def test_check_payload_executable_rejected():
    """MZ 是 PE/EXE 头,一律拒绝(防止绕过扩展名)。"""
    with pytest.raises(HTTPException) as exc:
        check_payload(b"MZ\x00\x00fake", ".pdf")
    assert exc.value.status_code == 400


def test_check_payload_size_limit_413():
    """超限给 413 而不是 400。"""
    big = b"%PDF-1.4\n" + b"x" * (30 * 1024 * 1024)  # 30 MB,超过 MAX_UPLOAD_BYTES
    with pytest.raises(HTTPException) as exc:
        check_payload(big, ".pdf")
    assert exc.value.status_code == 413