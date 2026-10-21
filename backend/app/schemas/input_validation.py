"""Shared validation policy for JSON request bodies."""

from typing import Annotated, Any
import re

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


_ALLOWED_WHITESPACE = {"\t", "\n", "\r"}
_MAX_JSON_DEPTH = 12


def normalize_user_id(value: str) -> str:
    """One account-identifier policy for JSON, path parameters, and bootstrap."""
    if not 3 <= len(value) <= 31 or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ValueError("User ID must be 3?31 characters using letters, numbers, periods, hyphens, or underscores; whitespace is not allowed.")
    return value.lower()


UserIdentifier = Annotated[str, Field(min_length=3, max_length=31), AfterValidator(normalize_user_id)]


def validate_markdown_text(value: str | None) -> str | None:
    """Allow multiline prose/Markdown, but exclude raw HTML and active links."""
    if value is None:
        return value
    _validate_value(value)
    if re.search(r"<\s*(?:/?\s*[A-Za-z]|[!?])", value):
        raise ValueError("Use plain text or Markdown; HTML markup is not supported.")
    if re.search(r"\]\(\s*(?:javascript|vbscript|data)\s*:", value, re.IGNORECASE):
        raise ValueError("Executable or data links are not supported.")
    return value


def validate_source_url(value: str | None) -> str | None:
    """Only accept ordinary HTTP(S) source URLs, never executable schemes."""
    if value is None:
        return value
    from urllib.parse import urlsplit
    if len(value) > 2048 or any(c.isspace() or ord(c) < 32 or c in '<>"\'\\' for c in value):
        raise ValueError("Enter an HTTP/HTTPS URL without whitespace, markup, or control characters.")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid HTTP/HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs must not contain credentials.")
    parsed.port  # Reject malformed ports before storage or network processing.
    return value



def _validate_value(value: Any, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("Input nesting is too deep.")
    if isinstance(value, str):
        if len(value) > 500_000:
            raise ValueError("Text cannot exceed 500000 characters.")
        if any(ord(char) < 32 and char not in _ALLOWED_WHITESPACE for char in value):
            raise ValueError("Input contains a prohibited control character.")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_value(key, depth + 1)
            _validate_value(item, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_value(item, depth + 1)


class StrictInputModel(BaseModel):
    """Reject coercion, unknown fields, and non-text control characters."""

    model_config = ConfigDict(strict=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def validate_raw_input(cls, value: Any) -> Any:
        # Check raw lengths before field validators can trim or normalize input.
        if isinstance(value, dict):
            for name, field in cls.model_fields.items():
                raw = value.get(name)
                if isinstance(raw, (str, list, tuple, dict)):
                    for constraint in field.metadata:
                        limit = getattr(constraint, "max_length", None)
                        if limit is not None and len(raw) > limit:
                            raise ValueError(f"{name} cannot exceed {limit} characters or items.")
        _validate_value(value)
        return value


class CredentialInputModel(StrictInputModel):
    """Reject whitespace in credentials before any normalization."""

    @field_validator(
        "user_id", "password", "current_password", "new_password", "confirm_password",
        mode="before", check_fields=False,
    )
    @classmethod
    def no_credential_whitespace(cls, value: Any) -> Any:
        if isinstance(value, str) and any(char.isspace() for char in value):
            raise ValueError("User ID and password cannot contain spaces or whitespace.")
        return value
