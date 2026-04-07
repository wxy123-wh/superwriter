from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI, OpenAIError


@dataclass(frozen=True, slots=True)
class AIProviderConfig:
    """Configuration for an AI provider using OpenAI-compatible API."""

    provider_id: str
    provider_name: str  # "openai", "azure", "local", "custom"
    base_url: str
    api_key: str
    model_name: str
    temperature: float = 0.7
    max_tokens: int = 4096
    is_active: bool = True

    def validate(self) -> None:
        """Validate provider configuration."""
        if not self.provider_name.strip():
            raise ProviderValidationError("provider_name is required")
        if not self.base_url.strip():
            raise ProviderValidationError("base_url is required")
        if not self.api_key.strip():
            raise ProviderValidationError("api_key is required")
        if not self.model_name.strip():
            raise ProviderValidationError("model_name is required")
        if self.temperature < 0 or self.temperature > 2:
            raise ProviderValidationError("temperature must be between 0 and 2")
        if self.max_tokens < 1:
            raise ProviderValidationError("max_tokens must be positive")

    def for_storage(self) -> dict[str, Any]:
        """Convert to storage format."""
        return {
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "base_url": self.base_url,
            "api_key": self.api_key,  # In production, encrypt this
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "is_active": 1 if self.is_active else 0,
        }

    @classmethod
    def from_storage(cls, data: dict[str, Any]) -> AIProviderConfig:
        """Create from storage format."""
        return cls(
            provider_id=str(data["provider_id"]),
            provider_name=str(data["provider_name"]),
            base_url=str(data["base_url"]),
            api_key=str(data["api_key"]),
            model_name=str(data["model_name"]),
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 4096)),
            is_active=bool(data.get("is_active", 1)),
        )


@dataclass(frozen=True, slots=True)
class AIProviderTestResult:
    """Result of testing a provider connection."""

    success: bool
    message: str
    latency_ms: int | None = None
    model_info: dict[str, Any] | None = None
    error_detail: str | None = None


class ProviderValidationError(ValueError):
    """Raised when provider configuration is invalid."""


class AIProviderClient:
    """OpenAI-compatible AI client wrapper."""

    def __init__(self, config: AIProviderConfig):
        config.validate()
        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    @property
    def config(self) -> AIProviderConfig:
        return self._config

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        Generate a completion from the AI provider.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max tokens
            stream: Whether to stream responses (not yet supported)
            **kwargs: Additional parameters passed to API

        Returns:
            The generated text content
        """
        try:
            response = self._client.chat.completions.create(
                model=self._config.model_name,
                messages=messages,
                temperature=temperature if temperature is not None else self._config.temperature,
                max_tokens=max_tokens if max_tokens is not None else self._config.max_tokens,
                stream=stream,
                **kwargs,
            )
            return response.choices[0].message.content or ""
        except OpenAIError as e:
            raise AIProviderError(f"AI generation failed: {e}") from e

    def generate_structured(
        self,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate structured JSON output from the AI provider.

        Args:
            messages: List of message dicts with 'role' and 'content'
            output_schema: JSON schema for the expected output
            temperature: Override default temperature
            max_tokens: Override default max tokens
            **kwargs: Additional parameters passed to API

        Returns:
            Parsed JSON response matching the schema
        """
        # Add schema to system message
        system_message = {
            "role": "system",
            "content": f"You must respond with valid JSON matching this schema:\n{json.dumps(output_schema, ensure_ascii=False)}",
        }

        # Prepend to existing messages
        all_messages = [system_message] + [
            m for m in messages if m.get("role") != "system"
        ]

        try:
            response = self._client.chat.completions.create(
                model=self._config.model_name,
                messages=all_messages,
                response_format={"type": "json_object"},
                temperature=temperature if temperature is not None else self._config.temperature,
                max_tokens=max_tokens if max_tokens is not None else self._config.max_tokens,
                **kwargs,
            )

            content = response.choices[0].message.content or ""
            return json.loads(content)
        except OpenAIError as e:
            raise AIProviderError(f"Structured generation failed: {e}") from e
        except json.JSONDecodeError as e:
            raise AIProviderError(f"Failed to parse AI response as JSON: {e}") from e

    def test_connection(self) -> AIProviderTestResult:
        """Test the provider connection with a simple request."""
        import time

        test_messages = [
            {"role": "user", "content": "Respond with exactly: OK"},
        ]

        start = time.time()
        try:
            response = self._client.chat.completions.create(
                model=self._config.model_name,
                messages=test_messages,
                max_tokens=10,
            )
            latency = int((time.time() - start) * 1000)

            content = response.choices[0].message.content or ""
            if "OK" in content.upper():
                return AIProviderTestResult(
                    success=True,
                    message="Connection successful",
                    latency_ms=latency,
                    model_info={"model": response.model, "usage": response.usage.model_dump()},
                )
            else:
                return AIProviderTestResult(
                    success=False,
                    message=f"Unexpected response: {content[:100]}",
                    latency_ms=latency,
                )
        except OpenAIError as e:
            latency = int((time.time() - start) * 1000)
            return AIProviderTestResult(
                success=False,
                message=f"Connection failed: {type(e).__name__}",
                latency_ms=latency,
                error_detail=str(e),
            )


class AIProviderError(RuntimeError):
    """Raised when AI provider operations fail."""
