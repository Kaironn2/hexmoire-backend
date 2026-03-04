"""Steam authentication via httpx (no browser needed).

Implements the new IAuthenticationService JWT-based login flow:
    1. GET  /IAuthenticationService/GetPasswordRSAPublicKey/v1
    2. Encrypt the password client-side with the RSA key (PKCS#1 v1.5)
    3. POST /IAuthenticationService/BeginAuthSessionViaCredentials/v1
    4. POST /IAuthenticationService/PollAuthSessionStatus/v1  (loop)
    5. POST login.steampowered.com/jwt/finalizelogin
    6. Construct ``steamLoginSecure`` = ``steamid%7C%7Caccess_token``

The resulting cookies are cached on disk so subsequent runs can skip login.
"""

import asyncio
import base64
import json
import logging
import os
from http import HTTPStatus
from typing import Any

import httpx
from httpx import Cookies

from src.bots.steam.headers import DEFAULT_HEADERS
from src.bots.steam.items import SteamCookies
from src.core.settings import DATA_DIR

logger = logging.getLogger(__name__)

COOKIES_FILE = DATA_DIR / 'steam' / '.cookies.json'
AUTH_API = 'https://api.steampowered.com/IAuthenticationService'
COMMUNITY_URL = 'https://steamcommunity.com'

_MAX_POLL_ATTEMPTS = 120

_GUARD_EMAIL = 1
_GUARD_DEVICE_CODE = 2
_GUARD_DEVICE_CONFIRM = 3


class SteamAuthClient:
    """Pure-httpx Steam authenticator (IAuthenticationService / JWT).

    Usage::

        async with HttpClient(config) as http:
            auth = SteamAuthClient(http, username='…', password='…')
            cookies = await auth.authenticate()
    """

    def __init__(
        self,
        http: httpx.AsyncClient | Any,
        *,
        username: str,
        password: str,
    ) -> None:
        self._http = http
        self._username = username
        self._password = password

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def authenticate(self) -> Cookies:
        """Return a valid cookie jar, reusing a cached session when possible."""
        saved = self._load_cookies()
        if saved and await self._cookies_are_valid(saved):
            logger.info('Reusing cached Steam session')
            return self._build_jar(saved)

        logger.info('No valid session found — logging in via IAuthenticationService')
        return await self._do_login()

    # ------------------------------------------------------------------
    # Login flow (IAuthenticationService)
    # ------------------------------------------------------------------

    async def _do_login(self) -> Cookies:
        rsa = await self._get_rsa_key()
        encrypted_password = self._encrypt_password(rsa)

        session = await self._begin_auth_session(encrypted_password, rsa['timestamp'])
        client_id: str = session['client_id']
        request_id: str = session['request_id']
        steamid: str = session['steamid']
        interval: float = session.get('interval', 5.0)

        confirmations = session.get('allowed_confirmations', [])
        conf_types = [c.get('confirmation_type') for c in confirmations]
        if _GUARD_DEVICE_CONFIRM in conf_types:
            logger.info('Steam Guard: waiting for mobile device confirmation')
        elif _GUARD_DEVICE_CODE in conf_types:
            logger.info('Steam Guard: waiting for mobile authenticator code')
        elif _GUARD_EMAIL in conf_types:
            logger.info('Steam Guard: email code (auto-approved)')

        refresh_token, access_token = await self._poll_auth_status(client_id, request_id, interval,)

        await self._finalize_login(refresh_token)

        jar = Cookies()
        jar.set('steamLoginSecure', f'{steamid}%7C%7C{access_token}', domain='steamcommunity.com', path='/')
        jar.set('steamRefresh_steam', f'{steamid}%7C%7C{refresh_token}', domain='login.steampowered.com', path='/')

        self._save_cookies_from_jar(jar)
        logger.info('Login successful for %s (steamid=%s)', self._username, steamid)
        return jar

    # ------------------------------------------------------------------
    # IAuthenticationService endpoints
    # ------------------------------------------------------------------

    async def _get_rsa_key(self) -> dict[str, str]:
        resp = await self._http.get(
            f'{AUTH_API}/GetPasswordRSAPublicKey/v1',
            params={'account_name': self._username},
        )
        data: dict[str, Any] = resp.json()
        response = data.get('response', {})
        if not response.get('publickey_mod'):
            raise SteamLoginError(f'Failed to get RSA key: {data}')
        return response

    async def _begin_auth_session(
        self, encrypted_password: str, timestamp: str,
    ) -> dict[str, Any]:
        resp = await self._http.post(
            f'{AUTH_API}/BeginAuthSessionViaCredentials/v1',
            data={
                'account_name': self._username,
                'encrypted_password': encrypted_password,
                'encryption_timestamp': timestamp,
                'remember_login': 'true',
                'persistence': '1',
                'website_id': 'Community',
                'device_friendly_name': 'hexmoire-bot',
            },
        )
        data = resp.json()
        session = data.get('response', {})
        if not session.get('client_id'):
            raise SteamLoginError(f'BeginAuthSession failed: {data}')
        return session

    async def _poll_auth_status(
        self, client_id: str, request_id: str, interval: float,
    ) -> tuple[str, str]:
        """Poll until Steam returns JWT tokens (refresh + access)."""
        for attempt in range(_MAX_POLL_ATTEMPTS):
            resp = await self._http.post(
                f'{AUTH_API}/PollAuthSessionStatus/v1',
                data={
                    'client_id': str(client_id),
                    'request_id': request_id,
                },
            )
            poll = resp.json().get('response', {})
            refresh_token = poll.get('refresh_token')
            access_token = poll.get('access_token')

            if refresh_token and access_token:
                return refresh_token, access_token

            logger.debug('Poll attempt %d — waiting %.2fs', attempt + 1, interval)
            await asyncio.sleep(interval)

        raise SteamLoginError('Timed out waiting for auth confirmation')

    async def _finalize_login(self, refresh_token: str) -> dict[str, Any]:
        """Call jwt/finalizelogin to complete the session."""
        resp = await self._http.post(
            'https://login.steampowered.com/jwt/finalizelogin',
            data={
                'nonce': refresh_token,
                'sessionid': '',
                'redir': f'{COMMUNITY_URL}/login/home/?goto=',
            },
        )
        return resp.json()

    # ------------------------------------------------------------------
    # RSA encryption (PKCS#1 v1.5)
    # ------------------------------------------------------------------

    @staticmethod
    def _rsa_encrypt(message: bytes, mod: int, exp: int) -> bytes:
        """Textbook RSA encryption with PKCS#1 v1.5 type-2 padding."""
        k = (mod.bit_length() + 7) // 8
        if len(message) > k - 11:
            raise ValueError('Message too long for RSA key size')

        padding_len = k - len(message) - 3
        padding = b''
        while len(padding) < padding_len:
            byte = os.urandom(1)
            if byte != b'\x00':
                padding += byte

        padded = b'\x00\x02' + padding + b'\x00' + message
        plaintext_int = int.from_bytes(padded, 'big')
        cipher_int = pow(plaintext_int, exp, mod)
        return cipher_int.to_bytes(k, 'big')

    def _encrypt_password(self, rsa_data: dict[str, str]) -> str:
        mod = int(rsa_data['publickey_mod'], 16)
        exp = int(rsa_data['publickey_exp'], 16)
        cipher = self._rsa_encrypt(self._password.encode(), mod, exp)
        return base64.b64encode(cipher).decode()

    # ------------------------------------------------------------------
    # Cookie validation & persistence
    # ------------------------------------------------------------------

    async def _cookies_are_valid(self, cookies: SteamCookies) -> bool:
        jar = self._build_jar(cookies)
        try:
            resp = await self._http.get(
                f'{COMMUNITY_URL}/my/games/?tab=all',
                headers=DEFAULT_HEADERS,
                cookies=jar,
                follow_redirects=False,
            )
        except httpx.RequestError:
            return False

        if resp.status_code == HTTPStatus.OK:
            logger.debug('Cached Steam session is valid (200)')
            return True

        if resp.status_code == HTTPStatus.FOUND:
            location = resp.headers.get('location', '')
            if '/login' in location:
                logger.debug('Cached Steam session expired (redirect to login)')
                return False
            logger.debug('Cached Steam session is valid (redirect to profile)')
            return True

        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_jar(cookies: SteamCookies) -> Cookies:
        jar = Cookies()
        for c in cookies.cookies:
            jar.set(name=c.name, value=c.value, domain=c.domain, path=c.path)
        return jar

    @staticmethod
    def _save_cookies_from_jar(jar: Cookies) -> None:
        """Convert an httpx.Cookies jar to SteamCookies and save to disk."""
        cookie_list = []
        for cookie in jar.jar:
            cookie_list.append({
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain or '',
                'path': cookie.path or '/',
                'expires': cookie.expires or 0,
                'httpOnly': False,
                'secure': True,
                'sameSite': 'None',
            })

        model = SteamCookies.model_validate({'cookies': cookie_list})
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_FILE.write_text(model.model_dump_json(indent=4), encoding='utf-8')
        logger.info('Saved %d cookies to %s', len(cookie_list), COOKIES_FILE)

    @staticmethod
    def _load_cookies() -> SteamCookies | None:
        if not COOKIES_FILE.exists():
            return None
        try:
            return SteamCookies.model_validate_json(COOKIES_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, ValueError):
            logger.warning('Corrupted cookies file, ignoring')
            return None


class SteamLoginError(Exception):
    """Raised when Steam login fails for any reason."""
