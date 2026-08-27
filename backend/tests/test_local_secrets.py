import json
from pathlib import Path

import pytest

from app import local_secrets


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(local_secrets, "KEYRING_PATH", tmp_path / "keyring.dpapi")
    monkeypatch.setattr(local_secrets, "SECRETS_PATH", tmp_path / "secrets.json")
    return tmp_path


@pytest.mark.skipif(local_secrets.os.name != "nt", reason="DPAPI is Windows-only")
def test_round_trip_and_rotation_reencrypt_every_secret(isolated_store):
    assert local_secrets.store_secrets(
        "backend", {"DATABASE_URL": "postgresql://secret", "MISTRAL_API_KEY": "api-secret"}
    ) == 1
    before = json.loads(local_secrets.SECRETS_PATH.read_text(encoding="utf-8"))

    result = local_secrets.rotate_if_due(force=True)
    after = json.loads(local_secrets.SECRETS_PATH.read_text(encoding="utf-8"))

    assert result["rotated"] is True
    assert result["active_version"] == 2
    assert result["secret_count"] == 2
    assert before != after
    assert {record["key_version"] for record in after["secrets"].values()} == {2}
    assert local_secrets.load_secrets("backend") == {
        "DATABASE_URL": "postgresql://secret",
        "MISTRAL_API_KEY": "api-secret",
    }

    local_secrets.rewrap_keyring_for_local_machine()
    assert local_secrets.load_secrets("backend")["MISTRAL_API_KEY"] == "api-secret"


@pytest.mark.skipif(local_secrets.os.name != "nt", reason="DPAPI is Windows-only")
def test_ciphertext_tampering_is_rejected(isolated_store):
    local_secrets.store_secrets("backend", {"MISTRAL_API_KEY": "api-secret"})
    document = json.loads(local_secrets.SECRETS_PATH.read_text(encoding="utf-8"))
    record = document["secrets"]["backend.MISTRAL_API_KEY"]
    record["ciphertext"] = "A" + record["ciphertext"][1:]
    local_secrets.SECRETS_PATH.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(local_secrets.LocalSecretError):
        local_secrets.load_secrets("backend")


@pytest.mark.skipif(local_secrets.os.name != "nt", reason="DPAPI is Windows-only")
def test_env_migration_removes_plaintext(isolated_store):
    env_file = isolated_store / ".env"
    env_file.write_text("MISTRAL_API_KEY=secret-value\nPUBLIC_SETTING=visible\n", encoding="utf-8")

    count = local_secrets.migrate_env_file(env_file, "backend", {"MISTRAL_API_KEY"})

    assert count == 1
    assert "secret-value" not in env_file.read_text(encoding="utf-8")
    assert "PUBLIC_SETTING=visible" in env_file.read_text(encoding="utf-8")
    assert local_secrets.load_secrets("backend")["MISTRAL_API_KEY"] == "secret-value"
