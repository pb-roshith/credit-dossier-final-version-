"""Read Windows-local AES-GCM secrets using a DPAPI-protected keyring."""

from __future__ import annotations

import base64
import ctypes
import json
import os
import threading
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AAD_PREFIX = b"credit-dossier/local-secret/v1\0"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / ".data"
KEYRING_PATH = DEFAULT_DATA_DIR / "secret-keyring.dpapi"
SECRETS_PATH = DEFAULT_DATA_DIR / "secrets.aesgcm.json"
_store_lock = threading.RLock()


class LocalSecretError(RuntimeError):
    """Raised when the encrypted local secret store cannot be read safely."""


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise LocalSecretError("The local secret keyring requires Windows DPAPI.")

    class Blob(ctypes.Structure):
        _fields_ = [
            ("size", ctypes.c_ulong),
            ("data", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    def blob(value: bytes) -> tuple[Blob, object]:
        buffer = ctypes.create_string_buffer(value)
        return (
            Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))),
            buffer,
        )

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    source, source_buffer = blob(data)
    entropy, entropy_buffer = blob(b"credit-dossier/local-secrets/v1")
    output = Blob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        0x01,
        ctypes.byref(output),
    )
    _ = source_buffer, entropy_buffer
    if not ok:
        raise LocalSecretError(
            f"DPAPI failed with Windows error {ctypes.get_last_error()}."
        )
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(output.data)


def _read_keyring() -> dict:
    if not KEYRING_PATH.is_file():
        raise LocalSecretError("The DPAPI-protected secret keyring is missing.")
    try:
        return json.loads(_dpapi_unprotect(KEYRING_PATH.read_bytes()))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise LocalSecretError("The DPAPI-protected secret keyring is invalid.") from exc


def _read_document() -> dict:
    if not SECRETS_PATH.is_file():
        return {"format": 1, "secrets": {}}
    try:
        document = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalSecretError("The AES-GCM secret document is invalid.") from exc
    if document.get("format") != 1 or not isinstance(document.get("secrets"), dict):
        raise LocalSecretError("Unsupported encrypted secret document format.")
    return document


def _decrypt(name: str, record: dict, ring: dict) -> str:
    try:
        key = base64.urlsafe_b64decode(ring["keys"][str(record["key_version"])])
        nonce = base64.urlsafe_b64decode(record["nonce"])
        ciphertext = base64.urlsafe_b64decode(record["ciphertext"])
        plaintext = AESGCM(key).decrypt(
            nonce,
            ciphertext,
            AAD_PREFIX + name.encode("utf-8"),
        )
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise LocalSecretError(
            f"Unable to authenticate or decrypt secret {name!r}."
        ) from exc


def load_secrets(namespace: str) -> dict[str, str]:
    """Decrypt all values belonging to one application namespace."""
    with _store_lock:
        if not SECRETS_PATH.is_file():
            return {}
        ring = _read_keyring()
        prefix = namespace + "."
        return {
            name[len(prefix) :]: _decrypt(name, record, ring)
            for name, record in _read_document()["secrets"].items()
            if name.startswith(prefix)
        }


def load_into_environment(namespace: str, *, overwrite: bool = True) -> int:
    """Load encrypted values into this process without exposing them in logs."""
    values = load_secrets(namespace)
    for name, value in values.items():
        if overwrite or name not in os.environ:
            os.environ[name] = value
    return len(values)
