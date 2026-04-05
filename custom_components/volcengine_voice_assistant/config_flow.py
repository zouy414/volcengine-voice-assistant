"""Home Assistant Config Flow"""

from homeassistant.config_entries import (Any, ConfigEntry, ConfigFlow,
                                          ConfigFlowResult, ConfigSubentryFlow)
from homeassistant.core import callback

from . import DOMAIN, stt, tts


class VolcengineVoiceAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Volcengine Voice Assistant integration."""

    VERSION = 1
    MINOR_VERSION = 1

    def is_matching(self, _: ConfigFlow) -> bool:
        """Return True if other_flow is matching this flow."""

        return False

    async def async_step_user(self, _: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""

        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        return self.async_create_entry(title="Volcengine Voice Assistant", data={})

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, _: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            "stt": stt.SubentryFlow,
            "tts": tts.SubentryFlow
        }
