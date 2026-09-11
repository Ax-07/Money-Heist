from __future__ import annotations


class AIGatewayError(Exception):
    """Base exception for the AI gateway."""


class AIConfigurationError(AIGatewayError):
    """Raised when model routing or pricing configuration is invalid."""


class BudgetExceededError(AIGatewayError):
    """Raised when no configured route can fit inside the hard AI budget."""


class AIProviderError(AIGatewayError):
    """Base exception for provider failures."""


class RetryableAIProviderError(AIProviderError):
    """Provider failure that may be retried within the bounded retry policy."""


class NonRetryableAIProviderError(AIProviderError):
    """Provider failure that must not be retried automatically."""


class IncompleteAIProviderError(NonRetryableAIProviderError):
    """Non-retryable provider response that already incurred billable token usage."""

    def __init__(
        self,
        message: str,
        *,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        provider_request_id: str | None,
        model_id: str,
    ) -> None:
        super().__init__(message)
        self.input_tokens = input_tokens
        self.cached_input_tokens = cached_input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms
        self.provider_request_id = provider_request_id
        self.model_id = model_id


class StructuredOutputError(AIGatewayError):
    """Raised when a provider response cannot be validated against the schema."""
