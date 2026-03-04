import logging

from src.tasks.broker import broker
from src.core.settings import config
from src.infra.http.client import HttpClient
from src.bots.steam.crawlers.achievements import SteamAchievementsCrawler

logger = logging.getLogger(__name__)


@broker.task
async def steam_crawl_achievements(username: str = 'kaironn1') -> int:
    """Crawl Steam achievements for a given user.

    Authenticates via httpx (RSA + form login), then scrapes all
    achievement pages and persists the results.

    Returns the total number of achievements parsed.
    """
    logger.info('Starting steam_crawl_achievements for %s', username)

    async with HttpClient(config.http_config) as http:
        crawler = SteamAchievementsCrawler(http=http, username=username)
        achievements = await crawler.run()

    logger.info('steam_crawl_achievements completed: %d achievements', len(achievements))
    return len(achievements)
