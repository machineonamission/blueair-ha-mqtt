import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_REGION,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api_to_mqtt import api_to_mqtt
from .const import (
    DOMAIN,
    DATA_DEVICES,
    DATA_AWS_DEVICES,
    REGION_USA,
)
from .http_aws_blueair import LoginError

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_REGION): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        new_data = {**config_entry.data, CONF_REGION: REGION_USA}

        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data=new_data)

    _LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


async def async_setup(hass: HomeAssistant, config_entry: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("async setup")
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    _LOGGER.debug(f"async setup entry: {config_entry}")
    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    region = config_entry.data[CONF_REGION]
    # interval = config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    # _LOGGER.debug(f"setting up scan interval: {interval}")

    data = {}

    client_session = async_get_clientsession(hass)
    try:
        _ = await api_to_mqtt(
            username=username,
            password=password,
            client_session=client_session,
            region=region,
        )
        hass.data[DOMAIN] = data

        # await hass.config_entries.async_forward_entry_setups(config_entry)
        _LOGGER.debug("integration setup completed")


        return True
    except LoginError as error:
        _LOGGER.debug("login failure, ha should retry")
        raise ConfigEntryNotReady("Login failure") from error


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    _LOGGER.debug("unload entry")
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry
    )
    if unload_ok:
        hass.data[DOMAIN] = None

    return unload_ok
