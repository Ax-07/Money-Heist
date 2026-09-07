from __future__ import annotations

import time
from typing import Any

import httpx

from .errors import NonRetryableAIProviderError, RetryableAIProviderError
from .models import ProviderRequest, ProviderResponse, TokenUsage


_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenAIResponsesClient:
    """Minimal async adapter for the OpenAI Responses API.

    No OpenAI SDK dependency is required. The API key is accepted only by this
    infrastructure adapter and never added to business-domain models or prompts.
    """

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": request.model_id,
            "input": request.input_text,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "schema": request.json_schema,
                    "strict": True,
                }
            },
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "metadata": self._safe_metadata(request.metadata),
        }
        if request.instructions:
            payload["instructions"] = request.instructions

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Client-Request-Id": str(request.request_id),
        }

        started = time.perf_counter()
        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    f"{self._base_url}/responses",
                    json=payload,
                    headers=headers,
                    timeout=request.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                    response = await client.post(
                        f"{self._base_url}/responses",
                        json=payload,
                        headers=headers,
                    )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RetryableAIProviderError(f"OpenAI transport failure: {exc}") from exc
        latency_ms = max(int((time.perf_counter() - started) * 1000), 0)

        if response.status_code >= 400:
            message = self._error_message(response)
            error_cls = (
                RetryableAIProviderError
                if response.status_code in _RETRYABLE_STATUS_CODES
                else NonRetryableAIProviderError
            )
            raise error_cls(f"OpenAI HTTP {response.status_code}: {message}")

        try:
            body = response.json()
        except ValueError as exc:
            raise RetryableAIProviderError("OpenAI returned invalid JSON") from exc

        output_text = self._extract_output_text(body)
        usage_raw = body.get("usage") or {}
        input_details = usage_raw.get("input_tokens_details") or {}
        usage = TokenUsage(
            input_tokens=int(usage_raw.get("input_tokens") or 0),
            cached_input_tokens=int(input_details.get("cached_tokens") or 0),
            output_tokens=int(usage_raw.get("output_tokens") or 0),
        )
        return ProviderResponse(
            provider_request_id=body.get("id"),
            model_id=str(body.get("model") or request.model_id),
            output_text=output_text,
            usage=usage,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _safe_metadata(metadata: dict[str, str]) -> dict[str, str]:
        # Only caller-supplied non-secret metadata is accepted; the API key never enters this mapping.
        return {str(k)[:64]: str(v)[:512] for k, v in metadata.items()}

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
            error = body.get("error") or {}
            return str(error.get("message") or body)[:500]
        except ValueError:
            return response.text[:500]

    @staticmethod
    def _extract_output_text(body: dict[str, Any]) -> str:
        for item in body.get("output") or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if content.get("type") == "refusal":
                    raise NonRetryableAIProviderError(
                        f"OpenAI refusal: {str(content.get('refusal') or '')[:500]}"
                    )
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise RetryableAIProviderError("OpenAI response did not contain output_text")
