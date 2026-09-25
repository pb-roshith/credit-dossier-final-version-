"""Environment-aware secret loading for local and production runtimes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import MutableMapping

from app.local_secrets import load_into_environment


PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})


class SecretProviderError(RuntimeError):
    """Raised when the configured secret provider cannot supply required values."""


@dataclass(frozen=True)
class SecretSpec:
    variable: str
    default_vault_name: str
    required: bool = False


_SECRET_SPECS = {
    "backend": (
        SecretSpec("MISTRAL_API_KEY", "mistral-api-key", required=True),
        SecretSpec("DATABASE_URL", "database-url", required=True),
        SecretSpec("REPORT_TOKENIZATION_KEY", "report-tokenization-key"),
        SecretSpec("INITIAL_RELATIONSHIP_MANAGER_PASSWORD", "initial-relationship-manager-password"),
        SecretSpec("INITIAL_CREDIT_ANALYST_PASSWORD", "initial-credit-analyst-password"),
        SecretSpec("INITIAL_ADMIN_PASSWORD", "initial-admin-password"),
    ),
    "mcp": (
        SecretSpec("MISTRAL_API_KEY", "mistral-api-key", required=True),
        SecretSpec("POSTGRES_PASSWORD", "mcp-postgres-password", required=True),
    ),
}


def is_production(environment: str | None) -> bool:
    return (environment or "").strip().casefold() in PRODUCTION_ENVIRONMENTS


def _azure_client(vault_url: str):
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as exc:
        raise SecretProviderError(
            "Production secret loading requires azure-identity and azure-keyvault-secrets."
        ) from exc
    return SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())


def _is_not_found(exc: Exception) -> bool:
    return exc.__class__.__name__ == "ResourceNotFoundError" or getattr(exc, "status_code", None) == 404


def load_runtime_secrets(
    namespace: str,
    *,
    environment: str | None = None,
    environ: MutableMapping[str, str] | None = None,
    vault_client=None,
) -> int:
    """Load DPAPI secrets locally and Azure Key Vault secrets in production.

    Production values always overwrite process environment values. Required
    secrets fail closed: production never falls back to DPAPI, ``.env``, or a
    placeholder when Key Vault cannot supply them.
    """
    target = environ if environ is not None else os.environ
    app_environment = environment if environment is not None else target.get("APP_ENV", "development")
    if not is_production(app_environment):
        if target is not os.environ:
            raise SecretProviderError("A custom environment mapping is supported only for production tests.")
        return load_into_environment(namespace, overwrite=True)

    specs = _SECRET_SPECS.get(namespace)
    if not specs:
        raise SecretProviderError(f"No production secret mapping is defined for {namespace!r}.")

    vault_url = target.get("AZURE_KEY_VAULT_URL", "").strip()
    if not vault_url:
        raise SecretProviderError("AZURE_KEY_VAULT_URL is required when APP_ENV=production.")
    client = vault_client or _azure_client(vault_url)

    loaded = 0
    for spec in specs:
        override_name = f"AZURE_KEY_VAULT_{spec.variable}_SECRET_NAME"
        secret_name = target.get(override_name, spec.default_vault_name).strip()
        try:
            value = client.get_secret(secret_name).value
        except Exception as exc:
            if not spec.required and _is_not_found(exc):
                continue
            raise SecretProviderError(
                f"Unable to load required production secret {secret_name!r} from Azure Key Vault."
            ) from exc
        if not value:
            if spec.required:
                raise SecretProviderError(
                    f"Required production secret {secret_name!r} is empty in Azure Key Vault."
                )
            continue
        target[spec.variable] = value
        loaded += 1
    return loaded
