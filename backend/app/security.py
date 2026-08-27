"""Security primitives for report redaction and OS-bound key management."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import logging
import os
import re
import secrets
from ctypes import wintypes
from pathlib import Path
from threading import Lock

from app.config import settings


logger = logging.getLogger(__name__)
_key_lock = Lock()
_cached_key: bytes | None = None


class KeyManagementError(RuntimeError):
    """Raised when a persistent tokenization key cannot be protected safely."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi_transform(data: bytes, protect: bool) -> bytes:
    """Protect/unprotect bytes with Windows DPAPI for the current OS user."""
    if os.name != "nt":
        raise KeyManagementError("Windows DPAPI is only available on Windows.")

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    input_blob, input_buffer = _blob(data)
    entropy_blob, entropy_buffer = _blob(b"credit-dossier/report-tokenization/v1")
    output_blob = _DataBlob()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect:
        ok = function(
            ctypes.byref(input_blob), None, ctypes.byref(entropy_blob), None, None,
            flags, ctypes.byref(output_blob),
        )
    else:
        ok = function(
            ctypes.byref(input_blob), None, ctypes.byref(entropy_blob), None, None,
            flags, ctypes.byref(output_blob),
        )
    # Keep ctypes-owned input buffers alive through the native call.
    _ = input_buffer, entropy_buffer
    if not ok:
        raise KeyManagementError(f"DPAPI operation failed with Windows error {ctypes.get_last_error()}.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, wintypes.HLOCAL))


def _decode_injected_key(value: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise KeyManagementError("REPORT_TOKENIZATION_KEY must be URL-safe base64.") from exc
    if len(key) < 32:
        raise KeyManagementError("REPORT_TOKENIZATION_KEY must decode to at least 32 bytes.")
    return key


def _load_tokenization_key() -> bytes:
    """Load a key from DPAPI, or from an OS secret-injected environment value."""
    injected = settings.REPORT_TOKENIZATION_KEY.strip()
    if injected:
        return _decode_injected_key(injected)

    if os.name == "nt":
        key_path = Path(settings.DPAPI_KEY_FILE).expanduser().resolve()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            return _dpapi_transform(key_path.read_bytes(), protect=False)
        key = secrets.token_bytes(32)
        protected = _dpapi_transform(key, protect=True)
        temporary = key_path.with_suffix(key_path.suffix + ".tmp")
        temporary.write_bytes(protected)
        os.replace(temporary, key_path)
        return key

    if settings.APP_ENV.lower() == "production":
        raise KeyManagementError(
            "Production requires Windows DPAPI or REPORT_TOKENIZATION_KEY supplied by the host secret manager."
        )
    logger.warning(
        "Using an ephemeral report-tokenization key outside Windows development; "
        "tokens will change after restart."
    )
    return secrets.token_bytes(32)


def tokenization_key() -> bytes:
    global _cached_key
    if _cached_key is None:
        with _key_lock:
            if _cached_key is None:
                _cached_key = _load_tokenization_key()
    return _cached_key


def tokenize_sensitive_value(value: str, namespace: str = "report") -> str:
    """Return a stable, non-reversible HMAC token without exposing the source value."""
    normalized = " ".join(value.strip().casefold().split())
    digest = hmac.new(
        tokenization_key(),
        f"{namespace}\0{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).digest()[:12]
    return "tok_" + base64.b32encode(digest).decode("ascii").rstrip("=").lower()


_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")),
    ("pan", re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])", re.IGNORECASE)),
    ("aadhaar", re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")),
    ("account", re.compile(r"(?i)(?P<label>\b(?:account|a/c)\s*(?:number|no\.?|#)?\s*[:=-]?\s*)(?P<value>[A-Z0-9-]{6,34})")),
    ("phone", re.compile(r"(?i)(?P<label>\b(?:phone|mobile|contact)\s*(?:number|no\.?|#)?\s*[:=-]?\s*)(?P<value>\+?[0-9][0-9 ()-]{7,18}[0-9])")),
)


def mask_sensitive_text(text: str) -> str:
    """Replace recognized identifiers with strongly masked, correlatable tokens."""
    if not text or not settings.REPORT_MASK_SENSITIVE_DATA:
        return text
    masked = text
    for namespace, pattern in _SENSITIVE_PATTERNS:
        def replacement(match: re.Match[str], kind: str = namespace) -> str:
            value = match.groupdict().get("value") or match.group(0)
            label = match.groupdict().get("label") or ""
            return f"{label}[MASKED:{tokenize_sensitive_value(value, kind)}]"
        masked = pattern.sub(replacement, masked)
    return masked
