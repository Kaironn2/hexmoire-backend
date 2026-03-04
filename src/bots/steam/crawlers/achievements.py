import re
import asyncio
import logging
from http import HTTPStatus
from typing import ClassVar

import httpx
from lxml import html
from lxml.etree import _Element

from src.bots.base import BaseCrawler
from src.bots.registry import register_bot
from src.bots.steam.crawlers.auth import SteamAuthClient
from src.bots.steam.items import Achievement, AchievementList
from src.bots.steam.headers import DEFAULT_HEADERS
from src.core.db.session import AsyncSessionLocal
from src.core.settings import ROOT_DIR, config
from src.infra.http.client import HttpClient
from src.infra.http.config import HttpConfigOverrides
from src.repositories.sql.achievement import SteamAchievementRepository
from src.utils.datetime import DatetimeUtils
from src.utils.text import TextUtils

logger = logging.getLogger(__name__)


class UnlockParseLogger:
    _errors: list[str] = []

    @classmethod
    def add(cls, message: str) -> None:
        cls._errors.append(message)

    @classmethod
    def flush(cls, filename: str = 'unlock_parse_errors.txt') -> None:
        if not cls._errors:
            return

        with open(filename, 'a', encoding='utf-8') as f:
            for line in cls._errors:
                f.write(line + '\n')

        cls._errors.clear()


@register_bot('steam_achievements_crawler')
class SteamAchievementsCrawler(BaseCrawler):
    BASE_URL = 'https://steamcommunity.com'
    _semaphore = asyncio.Semaphore(64)

    http_config_overrides: ClassVar[HttpConfigOverrides] = {
        'max_per_domain': 10,
        'timeout': 60.0,
    }

    def __init__(self, http: HttpClient, username: str, cookies: httpx.Cookies | None = None) -> None:
        super().__init__(http=http)
        self.username = username
        self.cookies = cookies
        self.export_path = ROOT_DIR / 'data' / f'achievements_{username}.json'

    async def run(self) -> list[Achievement]:
        # Authenticate via httpx if no cookies were provided.
        if not self.cookies:
            auth = SteamAuthClient(
                self.http,
                username=config.STEAM_USERNAME,
                password=config.STEAM_PASSWORD,
            )
            self.cookies = await auth.authenticate()

        game_urls = await self._fetch_all_game_urls()

        logger.info('Starting to parse %d games...', len(game_urls))
        tasks = [self._process_game_page(url) for url in game_urls]
        results = await asyncio.gather(*tasks)

        all_achievements = [ach for game_achs in results for ach in game_achs]

        batch_data = [achievement.model_dump() for achievement in all_achievements]
        async with AsyncSessionLocal() as session:
            await SteamAchievementRepository(session).batch_upsert(batch_data)

        logger.info('Finished! Total achievements parsed: %d', len(all_achievements))

        model_list = AchievementList(root=all_achievements)
        json_str = model_list.model_dump_json(indent=2)

        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        self.export_path.write_text(json_str, encoding='utf-8')

        logger.info('Unlock parse errors: %d', len(UnlockParseLogger._errors))
        UnlockParseLogger.flush(str(ROOT_DIR / 'data' / 'unlock_parse_errors.txt'))

        return all_achievements

    # -- Page fetching --

    async def _fetch_all_game_urls(self) -> set[str]:
        game_urls: set[str] = set()
        tabs = ['all', 'perfect']

        headers = {**DEFAULT_HEADERS, 'Accept-Language': 'en;q=0.9,en-US;q=0.8'}

        for tab in tabs:
            url = f'{self.BASE_URL}/id/{self.username}/games/?tab={tab}'
            logger.info("Fetching '%s' games tab...", tab)

            try:
                response = await self.http.get(
                    url,
                    headers=headers,
                    cookies=self.cookies,
                )
                if response.status_code == HTTPStatus.OK:
                    appids = re.findall(r'"appid\\*"?:(\d+)', response.text)
                    for appid in appids:
                        full_url = (
                            f'{self.BASE_URL}/id/{self.username}/stats/{appid}/achievements/'
                        )
                        game_urls.add(full_url)
                    logger.info("Found %d games in '%s' tab.", len(appids), tab)
            except httpx.RequestError as e:
                logger.warning('Error fetching %s: %s', tab, e)

        return game_urls

    async def _process_game_page(self, url: str) -> list[Achievement]:
        headers = {**DEFAULT_HEADERS, 'Accept-Language': 'en;q=0.9,en-US;q=0.8'}

        async with self._semaphore:
            try:
                logger.debug('Processing: %s', url)
                response = await self.http.get(
                    url,
                    headers=headers,
                    cookies=self.cookies,
                )
                response.raise_for_status()

                tree = html.fromstring(response.text)

                game_nodes = tree.xpath(
                    '(//span[@class="profile_small_header_location"])[2]/text()'
                )
                game_name = self._parse_game_name(game_nodes[0]) if game_nodes else None

                cards = tree.xpath('//div[@class="achieveTxtHolder"]')
                return [self._parse_card(card, game_name, url) for card in cards]

            except Exception as e:
                logger.warning('Failed to parse game %s: %s', url, e)

        return []

    def _parse_card(self, card: _Element, game_name: str | None, url: str) -> Achievement:
        title_nodes = card.xpath('./div[contains(@class, "achieveTxt")]/h3/text()')
        title = title_nodes[0] if title_nodes else None

        desc_nodes = card.xpath('./div[contains(@class, "achieveTxt")]/h5/text()')
        description = TextUtils.normalize(desc_nodes[0]) if desc_nodes else None

        current_prog, total_prog = (None, None)
        p_bar_nodes = card.xpath(
            './div[contains(@class, "achieveTxt")]'
            '/div[contains(@class, "achievementProgressBar")]'
        )
        if p_bar_nodes:
            current_prog, total_prog = self._parse_progression(p_bar_nodes[0])

        unlock_nodes = card.xpath('./div[@class="achieveUnlockTime"]/text()')
        unlock_time = (
            DatetimeUtils.parse_unlock_time(unlock_nodes[0]) if unlock_nodes else None
        )

        return Achievement(
            username=self.username,
            game=game_name,
            title=title,
            description=description,
            unlock_time=unlock_time,
            current_progress=current_prog,
            total_progress=total_prog,
            language='en',
            url=url,
        )

    # -- Parsing helpers --

    @staticmethod
    def _parse_game_name(game: str) -> str:
        game = game.strip().replace('Estatísticas de ', '')
        return re.sub(r'\s*stats$', '', game, flags=re.I).strip()

    @staticmethod
    def _parse_achievements_summary(summary: str | None) -> tuple[int | None, int | None]:
        PARTS = 2

        if not summary:
            return None, None
        parts = summary.strip().split(' de ')
        if len(parts) >= PARTS:
            try:
                return int(parts[0].strip()), int(parts[1].split()[0].strip())
            except ValueError:
                pass
        return None, None

    @staticmethod
    def _parse_progression(node: _Element) -> tuple[float | None, float | None]:
        PARTS = 2

        text_nodes = node.xpath('./div[contains(@class, "progressText")]/text()')
        if text_nodes:
            parts = text_nodes[0].strip().split(' / ')
            if len(parts) == PARTS:
                try:
                    return float(parts[0].replace(',', '')), float(parts[1].replace(',', ''))
                except ValueError:
                    pass
        return None, None
