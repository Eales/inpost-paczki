"""Async client for the InPost Mobile consumer API."""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import aiohttp

from .const import (
    API_BASE_URL,
    APP_ID,
    ENDPOINT_ME,
    ENDPOINT_NOTIFICATIONS,
    ENDPOINT_TOKEN,
    ENDPOINT_TRACKED,
    OAUTH_AUTHORIZE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Refresh a little before the access token actually expires.
_EXPIRY_MARGIN = 120


class InPostApiError(Exception):
    """Raised when the InPost API cannot be reached or returns an error."""


class InPostAuthError(InPostApiError):
    """Raised when the session is gone and the user has to log in again."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class InPostLogin:
    """One browser login attempt: builds the link and redeems the callback.

    The login pages need a captcha, so they cannot be driven from Home Assistant.
    The user opens the link, logs in as in the app, and pastes the address the
    browser lands on (``.../callback?code=...``) back into the config flow.
    """

    def __init__(self) -> None:
        self._verifier = _b64url(secrets.token_bytes(48))
        self._state = _b64url(secrets.token_bytes(24))

    @property
    def url(self) -> str:
        """The login link to open in a browser."""
        challenge = _b64url(hashlib.sha256(self._verifier.encode()).digest())
        params = {
            "response_type": "code",
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": "openid",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": self._state,
            "nonce": _b64url(secrets.token_bytes(24)),
            "response_mode": "query",
            "lang": "pl",
            "supported_markets": "PL",
        }
        return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    def extract_code(self, pasted: str) -> str:
        """Take the pasted callback URL (or the bare code) and return the code.

        Raises ``ValueError`` when there is no code, or the URL belongs to a
        different login attempt.
        """
        value = pasted.strip()
        if "code=" not in value:
            if value and " " not in value and "/" not in value:
                return value
            raise ValueError("no code")
        query = parse_qs(urlsplit(value).query) if "?" in value else parse_qs(value)
        code = (query.get("code") or [""])[0]
        if not code:
            raise ValueError("no code")
        state = (query.get("state") or [None])[0]
        if state is not None and state != self._state:
            raise ValueError("state mismatch")
        return code

    @property
    def verifier(self) -> str:
        return self._verifier


def _headers(device_uid: str) -> dict[str, str]:
    return {
        "x-app-id": APP_ID,
        "device-uid": device_uid,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "pl-PL",
    }


def tokens_from_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Pick the fields worth keeping out of a token response."""
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    if not access or not refresh:
        raise InPostAuthError("token response without tokens")
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": time.time() + float(payload.get("expires_in") or 0),
    }


async def async_exchange_code(
    session: aiohttp.ClientSession, device_uid: str, code: str, verifier: str
) -> dict[str, Any]:
    """Redeem an authorization code for a token set."""
    return await _async_token_request(
        session,
        device_uid,
        {
            "client_id": OAUTH_CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": OAUTH_REDIRECT_URI,
        },
    )


async def _async_token_request(
    session: aiohttp.ClientSession, device_uid: str, form: dict[str, str]
) -> dict[str, Any]:
    try:
        async with session.post(
            f"{API_BASE_URL}{ENDPOINT_TOKEN}",
            data=form,
            headers=_headers(device_uid),
            timeout=_TIMEOUT,
        ) as response:
            if response.status in (400, 401, 403):
                # invalid_grant: the code or refresh token is spent or revoked.
                raise InPostAuthError(f"token endpoint HTTP {response.status}")
            response.raise_for_status()
            payload = await response.json(content_type=None)
    except aiohttp.ClientError as err:
        raise InPostApiError(f"token request failed: {err}") from err
    return tokens_from_response(payload)


class InPostApi:
    """Authenticated client for one account.

    InPost rotates refresh tokens: every refresh returns a new one and retires
    the old. ``on_tokens`` is awaited after each refresh so the new set can be
    persisted before it is needed again.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        device_uid: str,
        tokens: dict[str, Any],
        on_tokens: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._session = session
        self._device_uid = device_uid
        self._tokens = dict(tokens)
        self._on_tokens = on_tokens

    async def _async_refresh(self) -> None:
        _LOGGER.debug("Refreshing InPost access token")
        self._tokens = await _async_token_request(
            self._session,
            self._device_uid,
            {
                "client_id": OAUTH_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self._tokens["refresh_token"],
            },
        )
        if self._on_tokens is not None:
            await self._on_tokens(dict(self._tokens))

    async def _get(self, endpoint: str, params: dict[str, str] | None = None) -> Any:
        if time.time() > float(self._tokens.get("expires_at") or 0) - _EXPIRY_MARGIN:
            await self._async_refresh()
        for attempt in (1, 2):
            headers = {
                **_headers(self._device_uid),
                "Authorization": f"Bearer {self._tokens['access_token']}",
            }
            try:
                async with self._session.get(
                    f"{API_BASE_URL}{endpoint}",
                    params=params,
                    headers=headers,
                    timeout=_TIMEOUT,
                ) as response:
                    if response.status == 401 and attempt == 1:
                        # Revoked early (e.g. logout elsewhere); one refresh decides.
                        await self._async_refresh()
                        continue
                    if response.status in (401, 403):
                        raise InPostAuthError(f"{endpoint} HTTP {response.status}")
                    response.raise_for_status()
                    return await response.json(content_type=None)
            except aiohttp.ClientError as err:
                raise InPostApiError(f"Error calling {endpoint}: {err}") from err
        raise InPostAuthError(f"{endpoint}: unauthorized after refresh")

    async def async_get_me(self) -> dict[str, Any]:
        """Account profile: person id and phone number identify the account."""
        data = await self._get(ENDPOINT_ME)
        return data if isinstance(data, dict) else {}

    async def async_get_tracked(self) -> dict[str, Any]:
        """Incoming parcels, full list.

        The app sends ``If-None-Match`` and then gets only what changed since;
        without it the API returns every parcel, which keeps this stateless.
        """
        data = await self._get(ENDPOINT_TRACKED)
        return data if isinstance(data, dict) else {}

    async def async_get_notifications(self) -> dict[str, Any]:
        """The notifications the app shows in its inbox (and as push)."""
        data = await self._get(ENDPOINT_NOTIFICATIONS, {"type": "PUSH,SYNERISE"})
        return data if isinstance(data, dict) else {}
