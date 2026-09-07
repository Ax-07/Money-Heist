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


class StructuredOutputError(AIGatewayError):
    """Raised when a provider response cannot be validated against the schema."""
