import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from mednexus.config import Settings


def build_settings(**overrides):
    values = {
        "postgres_password": "p@ss/word",
        "minio_root_password": "storage-secret",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_host_development_defaults_match_compose_ports():
    settings = build_settings()

    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 55432
    assert settings.kafka_bootstrap_servers == "localhost:9094"


def test_database_url_encodes_credentials():
    settings = build_settings()

    assert "p%40ss%2Fword" in settings.database_url


def test_example_credentials_are_rejected_in_production():
    with pytest.raises(ValidationError, match="example credentials"):
        build_settings(
            environment="production",
            postgres_password="mednexus_dev_password",
        )


def test_epic_requires_credentials_when_enabled():
    with pytest.raises(ValidationError, match="Epic SMART requires"):
        build_settings(epic_smart_enabled=True)

    settings = build_settings(
        epic_smart_enabled=True,
        epic_client_id="non-production-client",
        epic_state_encryption_key=Fernet.generate_key().decode(),
    )
    assert settings.epic_smart_enabled is True
