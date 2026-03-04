import logging
from typing import TypeVar

from src.bots.base import BaseCrawler

logger = logging.getLogger(__name__)

# Type alias for any bot type
BotType = type[BaseCrawler]
_T = TypeVar('_T', bound=type[BaseCrawler])

# Global bot registry
_registry: dict[str, BotType] = {}


def register_bot(name: str | None = None):
    """Decorator to register a bot class in the global registry.

    Args:
        name: Optional custom name. Defaults to the class name.

    Usage:
        @register_bot()
        class GoogleCrawler(BaseCrawler):
            async def run(self):
                ...

        @register_bot("custom-name")
        class AnotherCrawler(BaseCrawler):
            async def run(self):
                ...
    """

    def decorator(cls: _T) -> _T:
        bot_name = name or cls.__name__
        if bot_name in _registry:
            logger.warning('Bot "%s" is already registered. Overwriting.', bot_name)
        _registry[bot_name] = cls
        logger.debug('Registered bot: %s -> %s', bot_name, cls.__qualname__)
        return cls

    return decorator


def get_bot(name: str) -> BotType:
    """Retrieve a registered bot class by name.

    Raises:
        KeyError: If no bot is registered with the given name.
    """
    if name not in _registry:
        raise KeyError(f'Bot "{name}" not found. Available: {list(_registry.keys())}')
    return _registry[name]


def list_bots() -> dict[str, BotType]:
    """Return a copy of the bot registry."""
    return dict(_registry)


def clear_registry() -> None:
    """Clear all registered bots (useful for testing)."""
    _registry.clear()
