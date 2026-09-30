from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MedNexus AI"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"

    postgres_db: str = "mednexus"
    postgres_user: str = "mednexus"
    postgres_password: SecretStr
    postgres_host: str = "localhost"
    postgres_port: int = 55432

    redis_host: str = "localhost"
    redis_port: int = 6379

    kafka_bootstrap_servers: str = "localhost:9094"

    minio_root_user: str = "mednexus"
    minio_root_password: SecretStr
    minio_endpoint: str = "http://localhost:9000"

    mlflow_tracking_uri: str = "http://localhost:5000"

    epic_smart_enabled: bool = False
    epic_fhir_base_url: str = (
        "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"
    )
    epic_client_id: str | None = None
    epic_redirect_uri: str = "http://localhost:8000/api/v1/integrations/epic/callback"
    epic_smart_scopes: str = (
        "openid fhirUser launch/patient patient/Patient.rs "
        "patient/Encounter.rs patient/Observation.rs offline_access"
    )
    epic_state_encryption_key: SecretStr | None = None
    epic_session_ttl_seconds: int = 3600
    web_base_url: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return normalized

    @model_validator(mode="after")
    def reject_example_secrets_outside_local_development(self) -> "Settings":
        if self.environment in {"staging", "production"}:
            example_secrets = {"mednexus_dev_password", "mednexus_dev_storage"}
            supplied = {
                self.postgres_password.get_secret_value(),
                self.minio_root_password.get_secret_value(),
            }
            if supplied & example_secrets:
                raise ValueError("example credentials are forbidden outside local development")
        return self

    @model_validator(mode="after")
    def validate_epic_configuration(self) -> "Settings":
        if not self.epic_smart_enabled:
            return self
        if not self.epic_client_id or not self.epic_state_encryption_key:
            raise ValueError(
                "Epic SMART requires EPIC_CLIENT_ID and EPIC_STATE_ENCRYPTION_KEY"
            )
        if self.environment in {"staging", "production"}:
            if not self.epic_fhir_base_url.startswith("https://"):
                raise ValueError("Epic FHIR must use HTTPS outside local development")
            if not self.epic_redirect_uri.startswith("https://"):
                raise ValueError("Epic redirect URI must use HTTPS outside local development")
            if not self.web_base_url.startswith("https://"):
                raise ValueError("Web application must use HTTPS outside local development")
        return self

    @property
    def database_url(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password.get_secret_value())
        database = quote_plus(self.postgres_db)
        return (
            f"postgresql://{user}:"
            f"{password}@"
            f"{self.postgres_host}:"
            f"{self.postgres_port}/"
            f"{database}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_settings() -> Settings:
    # BaseSettings obtains required secrets from the environment at runtime;
    # static type checkers cannot infer that environment-backed construction.
    return Settings()  # type: ignore[call-arg]
