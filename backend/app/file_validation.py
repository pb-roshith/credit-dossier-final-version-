"""Central allowlist and content-signature validation for uploaded files."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


DOCUMENT_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".csv", ".txt", ".md", ".json"}
)
TEMPLATE_EXTENSIONS = frozenset({".md", ".txt", ".docx"})
MAX_TEMPLATE_BYTES = 5 * 1024 * 1024
THEME_EXTENSIONS = frozenset({".pdf", ".txt"})

_OOXML_DIRECTORIES = {
    ".docx": "word/",
    ".xlsx": "xl/",
    ".pptx": "ppt/",
}
_OOXML_ALLOWED_COMPRESSION = frozenset(
    {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
)
_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


class UploadValidationError(ValueError):
    """Raised when an uploaded file is outside the configured allowlist."""


def validate_template_file(filename: str | None, file_bytes: bytes) -> str:
    """Bound template size and reject active content before document parsing."""
    if len(file_bytes) > MAX_TEMPLATE_BYTES:
        raise UploadValidationError("Template file exceeds the 5 MB limit.")
    safe_name = validate_uploaded_file(filename, file_bytes, allowed_extensions=TEMPLATE_EXTENSIONS)
    if Path(safe_name).suffix.lower() == ".docx":
        from xml.etree import ElementTree
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                entries = archive.infolist()
                if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 20 * 1024 * 1024:
                    raise ValueError("Archive too large")
                names = [entry.filename for entry in entries]
                if len(names) != len(set(names)) or "word/document.xml" not in names:
                    raise ValueError("Invalid document structure")
                for entry in entries:
                    name = entry.filename.lower()
                    if (entry.flag_bits & 1 or name.startswith("/") or "\\" in name
                            or ".." in name.split("/") or "vbaproject" in name
                            or "/embeddings/" in name or "/activex/" in name):
                        raise ValueError("Unsafe archive entry")
                    if name.endswith((".xml", ".rels")):
                        xml_bytes = archive.read(entry)
                        # Reject DTD/entity declarations before parsing, including
                        # UTF-16/32 encodings used to disguise the declarations.
                        declarations = xml_bytes.replace(b"\x00", b"").lower()
                        if b"<!doctype" in declarations or b"<!entity" in declarations:
                            raise ValueError("Unsafe XML declaration")
                        root = ElementTree.fromstring(xml_bytes)
                        if name.endswith(".rels") and any(
                            node.attrib.get("TargetMode", "").lower() == "external" for node in root.iter()
                        ):
                            raise ValueError("External relationship")
                        if name == "[content_types].xml" and any(
                            "macroenabled" in node.attrib.get("ContentType", "").lower() for node in root.iter()
                        ):
                            raise ValueError("Macro content")
        except Exception as exc:
            raise UploadValidationError("The uploaded DOCX template is invalid or contains unsupported active or external content.") from exc
    return safe_name


def _safe_filename(filename: str | None) -> str:
    normalized = (filename or "").replace("\\", "/")
    safe = Path(normalized).name.strip()
    if not safe or safe in {".", ".."}:
        raise UploadValidationError("A valid filename with an allowed extension is required.")
    return safe


def _validate_ooxml(file_bytes: bytes, extension: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            entries = archive.infolist()
            if any(
                entry.compress_type not in _OOXML_ALLOWED_COMPRESSION
                for entry in entries
            ):
                return False

            names = [entry.filename for entry in entries]
            return "[Content_Types].xml" in names and any(
                name.startswith(_OOXML_DIRECTORIES[extension]) for name in names
            )
    except (OSError, zipfile.BadZipFile):
        return False


def _looks_like_text(file_bytes: bytes) -> bool:
    if b"\x00" in file_bytes:
        return False
    try:
        file_bytes.decode("utf-8-sig")
        return True
    except UnicodeDecodeError:
        return False


def validate_uploaded_file(
    filename: str | None,
    file_bytes: bytes,
    *,
    allowed_extensions: frozenset[str] = DOCUMENT_EXTENSIONS,
) -> str:
    """Validate extension and content, returning a path-safe filename."""
    safe_filename = _safe_filename(filename)
    extension = Path(safe_filename).suffix.lower()
    supported = ", ".join(sorted(allowed_extensions))
    if extension not in allowed_extensions:
        raise UploadValidationError(
            f"Unsupported file type '{extension or 'none'}'. Allowed types: {supported}."
        )
    if not file_bytes:
        raise UploadValidationError("The uploaded file is empty.")

    valid_content = False
    if extension == ".pdf":
        valid_content = file_bytes.startswith(b"%PDF-")
    elif extension in _OOXML_DIRECTORIES:
        valid_content = _validate_ooxml(file_bytes, extension)
    elif extension in {".doc", ".xls"}:
        valid_content = file_bytes.startswith(_OLE_SIGNATURE)
    elif extension in {".csv", ".txt", ".md", ".json"}:
        valid_content = _looks_like_text(file_bytes)

    if not valid_content:
        raise UploadValidationError(
            f"The file content does not match the '{extension}' extension."
        )
    return safe_filename
