# Production RAG API Report

## Public Links

- GitHub repository: `https://github.com/alexxmore/rag-api`
- Fly.io public API: `https://alexxmore-rag-api.fly.dev`
- Health check: `https://alexxmore-rag-api.fly.dev/health`

## What Was Implemented

- FastAPI service with the required endpoints:
  - `POST /chat/stream`
  - `GET /usage/today`
  - `GET /usage/breakdown`
  - `GET /health`
  - `POST /index/rebuild`
- SSE streaming response format with `token` events and final `done` event.
- Basic RAG pipeline:
  - document loading from `data/source.md`
  - chunking
  - local `sentence-transformers/all-MiniLM-L6-v2` embeddings
  - vector search with top-k chunks
  - source chunk IDs returned in the final event
- OpenRouter LLM integration through the OpenAI-compatible async SDK.
- Multi-model fallback chain per API key tier.
- API key authentication via `X-API-Key`.
- Token-based rate limiting with Redis support and in-memory fallback.
- Semantic cache using the same embedding generated for retrieval.
- SQLite usage and cost tracking.
- Prompt-injection input detection and suspicious request logging.
- Output filtering flag for suspicious completion fragments.
- LLM concurrency control with `asyncio.Semaphore`.
- Client disconnect handling with `request.is_disconnected()`.
- Optional Langfuse tracing hooks.
- Dockerfile and Fly.io deployment configuration.
- Public Fly.io deployment with persistent Fly volume.

## Verified Behavior

The following acceptance evidence is included in `screenshots/`:

- `01_health.png` - health endpoint with `active_streams` and `aborted_streams`.
- `02_streaming_sources.png` - SSE streaming with final `sources`.
- `03_cache_hit.png` - semantic cache hit with similarity and faster response.
- `04_rate_limit_429.png` - token rate limit returning `429` and `Retry-After`.
- `05_fallback.png` - invalid primary model falling back to `openrouter/free`.
- `06_usage.png` - usage and model breakdown.
- `07_prompt_injection_400.png` - suspicious prompt returning `400` and being logged.

Production smoke checks were also performed:

- `GET /health` returned `200 OK`.
- `POST /index/rebuild` returned `{"status":"ok","chunks":2}`.
- `POST /chat/stream` streamed token-by-token from the public Fly URL.
- Final `done` event included `sources`.
- `GET /usage/today` returned request, token, and cost totals.

## Known Limitations and Workarounds

### Redis / Upstash

The rate limiter is implemented with Redis commands and falls back to an in-memory token bucket when Redis is unavailable. For the deployed Fly.io version, no external Redis/Upstash instance is configured yet, so production currently uses the fallback path.

Impact: the rate limit works for a single running process, but it is not shared across multiple machines or restarts.

Next step: create an Upstash Redis instance and set `REDIS_URL` as a Fly secret.

### Vector DB and Semantic Cache

The code supports both FAISS and Qdrant through the same vector store interface. The deployed Fly.io configuration currently uses:

```toml
VECTOR_BACKEND = "faiss"
```

This satisfies the allowed fallback option from the assignment, but the semantic cache requirement specifically mentions a Qdrant cache collection. Qdrant support exists, but Qdrant Cloud credentials were not configured for production.

Next step: create a Qdrant Cloud cluster and set `VECTOR_BACKEND=qdrant`, `QDRANT_URL`, and `QDRANT_API_KEY`.

### Langfuse

Langfuse tracing hooks are implemented and are enabled when the following environment variables are provided:

```env
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
```

Langfuse Cloud was not configured during this run, so no dashboard screenshot is included.

Next step: create a Langfuse project, add the keys as Fly secrets, and capture a dashboard screenshot.

### Fly.io Trial Runtime

Fly.io trial machines can stop after a short runtime unless billing is enabled. During verification, Fly logs showed:

```text
Trial machine stopping. To run for longer than 5m0s, add a credit card by visiting https://fly.io/trial.
```

Impact: the public URL works, but after inactivity the first request can take longer because the machine restarts and reloads the embedding model.

Next step: enable billing or use another platform that keeps the machine warm.

### OpenRouter Free Models

The initially chosen free model endpoint was no longer available:

```text
meta-llama/llama-3.1-8b-instruct:free
```

The implementation now uses:

```text
openrouter/free
```

This routes requests to currently available free models. This is more robust for a demo, but the exact underlying model can vary.

### Invalid Model Fallback

The assignment suggests testing fallback by setting the primary model to:

```text
openai/this-does-not-exist
```

OpenRouter returns this as a `400` error with message `not a valid model ID`. The assignment says most `400` errors should not trigger fallback, but this specific case is an acceptance test for fallback. The implementation treats only this specific invalid-model `400` as retryable while keeping other `400` errors as client errors.

### Docker / Fly Build

Several deployment build workarounds were required:

- Fly Depot remote builder failed with TLS certificate verification.
- Buildkit remote builder hit the organization CPU limit.
- Local Docker build had SSL verification problems when downloading packages.
- The Dockerfile uses trusted hosts for PyPI/PyTorch package download in this environment.
- PyTorch is pinned to CPU-only:

```text
torch==2.2.2+cpu
```

This avoids large CUDA dependencies and keeps the image suitable for a small Fly machine.

## What I Would Improve Next

- Configure Upstash Redis for distributed token rate limiting.
- Configure Qdrant Cloud for both document chunks and semantic cache.
- Configure Langfuse Cloud and attach dashboard screenshots.
- Add automated tests for:
  - auth
  - prompt-injection rejection
  - rate limit behavior
  - fallback decision logic
  - usage aggregation
- Preload or persist the embedding model to reduce cold-start time on Fly.
- Replace the sample document with a larger 10-50 page source document for a more realistic RAG demo.
