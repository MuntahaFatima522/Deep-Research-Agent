import time
from typing import Any

# Pricing per million tokens (USD) — input/output rates per model
LLM_PRICES: dict[str, dict[str, float]] = {
    "gemini-1.5-flash": {"input": 0.0, "output": 0.0},
    "gemini-2.0-flash": {"input": 0.0, "output": 0.0},
    "gemini-2.0-flash-exp": {"input": 0.0, "output": 0.0},
    "gemini-2.5-flash": {"input": 0.0, "output": 0.0},
    "gemini-1.5-pro": {"input": 0.0, "output": 0.0},
    # TODO: Add Claude model prices when switching to production provider
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}

# Estimated cost per API call in USD (non-LLM services)
SEARCH_PRICES: dict[str, float] = {
    "tavily_search": 0.005,
}


class UsageTracker:
    """Collects token counts, search counts, and estimates cost and duration."""

    def __init__(self, model_name: str = "gemini-1.5-flash") -> None:
        self.model_name = model_name
        self.input_tokens = 0
        self.output_tokens = 0
        self.searches = 0
        self.extracts = 0
        self.start_time = time.time()

    def record_llm_response(self, response: Any) -> None:
        """Extract input and output token counts from standard LangChain ChatResult or AIMessage."""
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict):
            self.input_tokens += usage.get("input_tokens", 0)
            self.output_tokens += usage.get("output_tokens", 0)
        elif hasattr(response, "response_metadata") and isinstance(response.response_metadata, dict):
            token_usage = response.response_metadata.get("token_usage", {})
            self.input_tokens += token_usage.get("prompt_tokens", 0)
            self.output_tokens += token_usage.get("completion_tokens", 0)

    def record_search(self, count: int = 1) -> None:
        """Increment count of web searches."""
        self.searches += count

    def record_extract(self, count: int = 1) -> None:
        """Increment count of page extractions."""
        self.extracts += count

    def summary(self) -> dict[str, Any]:
        """Compute estimated cost and duration metrics."""
        duration = round(time.time() - self.start_time, 2)
        model_rates = LLM_PRICES.get(self.model_name, {"input": 0.0, "output": 0.0})

        llm_cost = (
            (self.input_tokens / 1_000_000) * model_rates.get("input", 0.0)
            + (self.output_tokens / 1_000_000) * model_rates.get("output", 0.0)
        )
        search_rate = SEARCH_PRICES.get("tavily_search", 0.005)
        search_cost = self.searches * search_rate
        total_estimated_cost = round(llm_cost + search_cost, 6)

        return {
            "searches": self.searches,
            "extracts": self.extracts,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": total_estimated_cost,
            "duration_seconds": duration,
        }
