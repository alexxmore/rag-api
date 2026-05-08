MODEL_PRICING_USD_PER_1M = {
    "openrouter/free": {"input": 0.0, "output": 0.0},
    "meta-llama/llama-3.1-8b-instruct:free": {"input": 0.0, "output": 0.0},
    "meta-llama/llama-3.2-3b-instruct:free": {"input": 0.0, "output": 0.0},
    "google/gemini-flash-1.5": {"input": 0.075, "output": 0.30},
    "google/gemini-2.0-flash-001": {"input": 0.10, "output": 0.40},
    "mistralai/mistral-small-3.1-24b-instruct": {"input": 0.10, "output": 0.30},
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING_USD_PER_1M.get(model, {"input": 0.0, "output": 0.0})
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost, 8)
