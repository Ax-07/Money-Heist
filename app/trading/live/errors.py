from __future__ import annotations


class LiveBrokerError(RuntimeError):
    """Base class for deterministic LIVE execution failures."""


class LiveExecutionDisabledError(LiveBrokerError):
    """LIVE submission is structurally disabled."""


class LiveIntentValidationError(LiveBrokerError):
    """An OrderIntent violates a local execution guard."""


class LiveTransportError(LiveBrokerError):
    """Network/HTTP transport failed before a trustworthy API result was obtained."""


class LiveAmbiguousSubmissionError(LiveTransportError):
    """A write may have reached the exchange; reconciliation is mandatory."""


class LiveApiError(LiveBrokerError):
    """Kraken returned a syntactically valid API error response."""


class LiveExchangeRejectError(LiveApiError):
    """The exchange rejected the requested operation."""


class LiveReconciliationError(LiveBrokerError):
    """Local and exchange execution state cannot be reconciled safely."""


class LivePermissionError(LiveBrokerError):
    """API-key permissions are missing or unsafe for the configured boundary."""
