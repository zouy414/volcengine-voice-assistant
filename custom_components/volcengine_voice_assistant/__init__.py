"""The Volcengine Voice Assistant integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

DOMAIN = "volcengine_voice_assistant"
PLATFORMS = [Platform.STT]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Edge TTS from a config entry."""

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def listener(hass: HomeAssistant, entry: ConfigEntry):
        await hass.config_entries.async_reload(entry.entry_id)
    entry.async_on_unload(entry.add_update_listener(listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
