from homeassistant.config_entries import Any, ConfigEntry, ConfigFlow, ConfigFlowResult, ConfigSubentryFlow, FlowResult
from homeassistant.core import callback

from custom_components.volcengine_voice_assistant import DOMAIN, stt


class VolcengineVoiceAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Volcengine Voice Assistant integration."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="Already configured")

        return self.async_create_entry(title="Volcengine Voice Assistant", data={})

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            "stt": stt.SubentryFlow
        }
