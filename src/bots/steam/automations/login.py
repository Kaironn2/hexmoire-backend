from fastapi import status
from httpx import Cookies

from src.bots.base import HybridBot
from src.bots.registry import register_bot
from src.bots.steam.items import SteamCookies
from src.bots.steam.headers import DEFAULT_HEADERS
from src.core.settings import DATA_DIR, config


@register_bot('steam_login_automation')
class SteamLoginAutomation(HybridBot):
    BASE_URL = 'https://steamcommunity.com'
    COOKIES_FILE = DATA_DIR / 'steam' / '.cookies.json'

    async def run(self) -> Cookies:
        saved = self.load_cookies()
        if saved and await self.cookies_are_valid(saved):
            return self.build_jar(saved)

        return await self.login()

    async def login(self) -> Cookies:
        page = await self.browser.new_page()

        try:
            print('Navigating to steam page…')
            await page.goto(f'{self.BASE_URL}/login/home/?goto=', wait_until='networkidle')

            username_input = page.locator('input[type="text"]').first
            await username_input.click()
            await username_input.fill(config.STEAM_USERNAME)

            password_input = page.locator('input[type="password"]')
            await password_input.click()
            await password_input.fill(config.STEAM_PASSWORD)

            submit_btn = page.locator('button[type="submit"]')
            await submit_btn.click()

            print('Credentials submitted - waiting for login to complete…')
            await page.wait_for_url(
                lambda url: 'steamcommunity.com' in url and '/login' not in url,
                timeout=300_000,
            )

            cookies_raw = await self.browser.context.cookies()

            cookies = SteamCookies.model_validate({'cookies': cookies_raw})

            self.save_cookies(cookies)

            return self.build_jar(cookies)
        finally:
            await page.close()

    async def cookies_are_valid(self, cookies: SteamCookies) -> bool:
        jar = self.build_jar(cookies)

        response = await self.http.get(
            self.BASE_URL + '/my/games/?tab=all',
            headers=DEFAULT_HEADERS,
            cookies=jar,
            follow_redirects=False,
        )

        if response.status_code == status.HTTP_200_OK:
            print('Session is valid')
            return True

        if response.status_code == status.HTTP_302_FOUND:
            location = response.headers.get('location', '')
            if '/login' in location:
                print('Cookies expired (redirected to login)')
                return False

            print('Session is valid (redirected to profile)')
            return True

        print('Session is invalid')
        return False

    def save_cookies(self, cookies: SteamCookies) -> None:
        self.COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.COOKIES_FILE.write_text(cookies.model_dump_json(indent=4), encoding='utf-8')

    def load_cookies(self) -> SteamCookies | None:
        if not self.COOKIES_FILE.exists():
            return None

        return SteamCookies.model_validate_json(self.COOKIES_FILE.read_text(encoding='utf-8'))

    @classmethod
    def build_jar(cls, cookies: SteamCookies) -> Cookies:
        jar = Cookies()
        for cookie in cookies.cookies:
            jar.set(
                name=cookie.name,
                value=cookie.value,
                domain=cookie.domain,
                path=cookie.path,
            )

        return jar
