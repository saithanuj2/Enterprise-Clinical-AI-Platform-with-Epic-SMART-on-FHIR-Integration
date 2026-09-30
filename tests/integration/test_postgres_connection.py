import pytest
from sqlalchemy import create_engine, text

from mednexus.config import get_settings

pytestmark = pytest.mark.integration


def test_postgres_connection():
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        assert result.scalar() == 1
