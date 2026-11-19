"""Config flow for the Pulse-Eight ProAmp8 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ProAmpApiError, ProAmpClient, ProAmpConnectionError, first_of
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import ProAmpConfigEntry

_LOGGER = logging.getLogger(__name__)

HOST_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class ProAmpConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a ProAmp8."""

    VERSION = 1

    async def _probe(self, host: str) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Contact the amp. Returns (details, errors)."""
        client = ProAmpClient(host, async_get_clientsession(self.hass), timeout=8)
        try:
            details = await client.get_details()
        except ProAmpConnectionError:
            return None, {"base": "cannot_connect"}
        except ProAmpApiError:
            return None, {"base": "invalid_response"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error probing ProAmp8 at %s", host)
            return None, {"base": "unknown"}
        if not first_of(details, "Serial"):
            return None, {"base": "invalid_response"}
        return details, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the amplifier's IP address / hostname."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            details, errors = await self._probe(host)
            if details is not None:
                await self.async_set_unique_id(str(first_of(details, "Serial")))
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                model = str(first_of(details, "Model", default=DEFAULT_MODEL))
                title = f"{DEFAULT_MODEL if model.upper() == 'PROAMP8' else model} ({host})"
                return self.async_create_entry(title=title, data={CONF_HOST: host})

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(HOST_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the IP address of an existing amplifier."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            details, errors = await self._probe(host)
            if details is not None:
                await self.async_set_unique_id(str(first_of(details, "Serial")))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                HOST_SCHEMA, user_input or {CONF_HOST: entry.data[CONF_HOST]}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ProAmpConfigEntry) -> OptionsFlow:
        """Options flow (poll interval)."""
        return ProAmpOptionsFlow()


class ProAmpOptionsFlow(OptionsFlow):
    """Handle ProAmp8 options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
