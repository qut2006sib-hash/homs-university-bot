"""Optional model adapter. The answering pipeline does not call it."""

from __future__ import annotations


class ModelProvider:
    """Future providers implement this. None are configured in the MVP."""

    name = "disabled"

    def rewrite_query(self, text: str) -> str:
        raise NotImplementedError("No model provider is configured")


class DisabledModelProvider(ModelProvider):
    name = "disabled"
