"""AI Provider Configuration Service.

Manages AI provider configurations including listing, saving, activating,
deleting, and testing provider configurations.
"""

from core.ai import AIProviderClient, AIProviderConfig
from core.runtime.storage import CanonicalStorage


class AIConfigService:
    """Service for managing AI provider configurations."""

    def __init__(self, storage: CanonicalStorage):
        """Initialize the AI configuration service.

        Args:
            storage: The canonical storage instance for persisting configurations.
        """
        self.__storage = storage

    def list_provider_configs(self) -> tuple[dict[str, object], ...]:
        """List all AI provider configurations."""
        configs = self.__storage.list_provider_configs()
        return tuple(configs)

    def save_provider_config(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        is_active: bool = False,
        created_by: str = "user",
    ) -> str:
        """Save or update an AI provider configuration."""
        return self.__storage.save_provider_config(
            provider_id=None,
            provider_name=provider_name,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            is_active=is_active,
            created_by=created_by,
        )

    def set_active_provider(self, provider_id: str) -> bool:
        """Set a provider as active."""
        return self.__storage.set_active_provider(provider_id)

    def delete_provider_config(self, provider_id: str) -> bool:
        """Delete an AI provider configuration."""
        return self.__storage.delete_provider_config(provider_id)

    def test_provider_config(self, provider_id: str) -> dict[str, object]:
        """Test an AI provider configuration."""
        config_data = self.__storage.get_provider_config(provider_id)
        if config_data is None:
            return {"success": False, "message": "Provider not found"}

        try:
            config = AIProviderConfig(
                provider_id=str(config_data["provider_id"]),
                provider_name=str(config_data["provider_name"]),
                base_url=str(config_data["base_url"]),
                api_key=str(config_data["api_key"]),
                model_name=str(config_data["model_name"]),
                temperature=float(config_data["temperature"]),
                max_tokens=int(config_data["max_tokens"]),
                is_active=bool(config_data["is_active"]),
            )
            client = AIProviderClient(config)
            result = client.test_connection()
            return {
                "success": result.success,
                "message": result.message,
                "latency_ms": result.latency_ms,
                "model_info": result.model_info,
                "error_detail": result.error_detail,
            }
        except Exception as e:
            return {"success": False, "message": f"Test failed: {e}"}

    def get_active_ai_provider(self) -> AIProviderClient | None:
        """Get the active AI provider client, or None if not configured."""
        config_data = self.__storage.get_active_provider_config()
        if config_data is None:
            return None
        try:
            config = AIProviderConfig(
                provider_id=str(config_data["provider_id"]),
                provider_name=str(config_data["provider_name"]),
                base_url=str(config_data["base_url"]),
                api_key=str(config_data["api_key"]),
                model_name=str(config_data["model_name"]),
                temperature=float(config_data["temperature"]),
                max_tokens=int(config_data["max_tokens"]),
                is_active=bool(config_data["is_active"]),
            )
            return AIProviderClient(config)
        except Exception:
            return None
