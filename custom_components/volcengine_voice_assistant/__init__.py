"""The Volcengine Voice Assistant integration."""

import logging
from logging import Logger

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

DOMAIN = "volcengine_voice_assistant"
PLATFORMS = [Platform.STT]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

LOGGER: Logger = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def listener(hass: HomeAssistant, entry: ConfigEntry):
        await hass.config_entries.async_reload(entry.entry_id)
    entry.async_on_unload(entry.add_update_listener(listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
