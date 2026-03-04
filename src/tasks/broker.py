import logging

from taskiq import InMemoryBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from src.core.settings import config

logger = logging.getLogger(__name__)


def _create_broker() -> ListQueueBroker | InMemoryBroker:
    """Create the TaskIQ broker.

    In production, uses Redis as both queue and result backend.
    In development/testing, falls back to InMemoryBroker.
    """
    if config.PROD:
        result_backend = RedisAsyncResultBackend(redis_url=config.REDIS_URL)
        return ListQueueBroker(url=config.REDIS_URL).with_result_backend(result_backend)

    return InMemoryBroker()


broker = _create_broker()
