"""Config flow for the InPost Paczki integration."""
from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .api import (
    InPostApi,
    InPostApiError,
    InPostAuthError,
    InPostLogin,
    async_exchange_code,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_UID,
    CONF_EXPIRES_AT,
    CONF_PERSON_ID,
    CONF_PHONE,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_SHOW_CODES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SHOW_CODES,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    OAUTH_REDIRECT_URI,
)

_LOGGER = logging.getLogger(__name__)

CONF_CALLBACK_URL = "callback_url"


def _phone(me: dict[str, Any]) -> str | None:
    for identity in me.get("identities") or []:
        if identity.get("type") == "PHONE_IDENTITY":
            return identity.get("value")
    return None


class InPostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Browser login: open the link, log in as in the app, paste the address back."""

    VERSION = 1

    def __init__(self) -> None:
        self._login = InPostLogin()
        # Home Assistant shows up to InPost as one more phone of the account,
        # with its own session, so the app on your phone stays logged in.
        self._device_uid = uuid.uuid4().hex.upper()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the login link and take the callback address."""
        return await self._async_step_login("user", user_input)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The refresh token died (logout, long outage): log in again."""
        self._device_uid = entry_data[CONF_DEVICE_UID]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_step_login("reauth_confirm", user_input)

    async def _async_step_login(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                code = self._login.extract_code(user_input[CONF_CALLBACK_URL])
            except ValueError:
                errors[CONF_CALLBACK_URL] = "invalid_callback"
            else:
                session = async_get_clientsession(self.hass)
                try:
                    tokens = await async_exchange_code(
                        session, self._device_uid, code, self._login.verifier
                    )
                    me = await InPostApi(session, self._device_uid, tokens).async_get_me()
                except InPostAuthError as err:
                    _LOGGER.warning("InPost rejected the login code: %s", err)
                    errors["base"] = "invalid_auth"
                except InPostApiError as err:
                    _LOGGER.error("Error logging in to InPost: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    person_id = me.get("personId")
                    if not person_id:
                        errors["base"] = "invalid_auth"
                    else:
                        return await self._async_finish(person_id, _phone(me), tokens)

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_CALLBACK_URL): TextSelector()}),
            description_placeholders={
                "login_url": self._login.url,
                "callback_url": f"{OAUTH_REDIRECT_URI}?code=",
            },
            errors=errors,
        )

    async def _async_finish(
        self, person_id: str, phone: str | None, tokens: dict[str, Any]
    ) -> ConfigFlowResult:
        data = {
            CONF_DEVICE_UID: self._device_uid,
            CONF_PERSON_ID: person_id,
            CONF_PHONE: phone,
            CONF_ACCESS_TOKEN: tokens["access_token"],
            CONF_REFRESH_TOKEN: tokens["refresh_token"],
            CONF_EXPIRES_AT: tokens["expires_at"],
        }
        await self.async_set_unique_id(person_id)
        if self.source == "reauth":
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=data
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"InPost {phone or person_id}", data=data)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> InPostOptionsFlow:
        """Return the options flow handler."""
        return InPostOptionsFlow()


class InPostOptionsFlow(OptionsFlow):
    """Polling interval and whether pickup codes are exposed."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_SHOW_CODES: bool(user_input[CONF_SHOW_CODES]),
                }
            )

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_SHOW_CODES,
                        default=options.get(CONF_SHOW_CODES, DEFAULT_SHOW_CODES),
                    ): BooleanSelector(),
                }
            ),
        )
