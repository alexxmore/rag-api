from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class UsageToday(BaseModel):
    requests: int
    tokens: int
    cost_usd: float


class HealthResponse(BaseModel):
    status: str
    active_streams: int
    aborted_streams: int
    vector_backend: str


class ApiKeyConfig(BaseModel):
    tier: str
    tokens_per_minute: int
    models: list[str]
