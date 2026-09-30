import pytest
import redis

from mednexus.config import get_settings

pytestmark = pytest.mark.integration


def test_redis_connection():
    settings = get_settings()

    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )

    assert client.ping() is True
