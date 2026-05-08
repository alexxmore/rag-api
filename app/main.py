import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth import require_api_key
from app.documents import read_source, split_text
from app.llm import OpenRouterLLM, build_messages
from app.observability import Observability
from app.pricing import estimate_cost_usd
from app.rate_limit import TokenRateLimiter
from app.schemas import ApiKeyConfig, ChatRequest
from app.security import output_needs_filtering, validate_user_input
from app.semantic_cache import lookup_cache, store_cache
from app.settings import get_settings
from app.tokens import count_tokens
from app.usage_db import init_db, log_usage, usage_breakdown, usage_today
from app.vector_store import EmbeddingService, get_cache_store, get_chunk_store

app = FastAPI(title="Production RAG API")

settings = get_settings()
embedding_service = EmbeddingService()
chunk_store = get_chunk_store()
cache_store = get_cache_store()
rate_limiter = TokenRateLimiter()
llm = OpenRouterLLM()
observability = Observability()
llm_semaphore = asyncio.Semaphore(settings.max_llm_concurrency)
active_streams = 0
aborted_streams = 0


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def append_suspicious_response(record: dict) -> None:
    with Path("suspicious_responses.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "active_streams": active_streams,
        "aborted_streams": aborted_streams,
        "vector_backend": settings.vector_backend,
    }


@app.get("/usage/today")
async def usage_today_endpoint(auth: tuple[str, ApiKeyConfig] = Depends(require_api_key)) -> dict:
    api_key, _ = auth
    return await usage_today(api_key)


@app.get("/usage/breakdown")
async def usage_breakdown_endpoint(auth: tuple[str, ApiKeyConfig] = Depends(require_api_key)) -> dict:
    api_key, _ = auth
    return await usage_breakdown(api_key)


@app.post("/index/rebuild")
async def rebuild_index(auth: tuple[str, ApiKeyConfig] = Depends(require_api_key)) -> dict:
    text = read_source(settings.source_path)
    chunks = split_text(text)
    vectors = embedding_service.embed_many(chunks)
    payloads = [{"id": f"chunk_{idx}", "text": chunk, "source": str(settings.source_path)} for idx, chunk in enumerate(chunks)]
    chunk_store.rebuild(vectors, payloads)
    return {"status": "ok", "chunks": len(payloads)}


@app.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    auth: tuple[str, ApiKeyConfig] = Depends(require_api_key),
) -> StreamingResponse:
    api_key, key_config = auth
    validate_user_input(api_key, payload.message)
    await rate_limiter.preflight(api_key, key_config)

    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    async def generate():
        global active_streams, aborted_streams
        active_streams += 1
        charged = False
        try:
            with observability.trace("rag-chat", api_key=api_key, tier=key_config.tier, request_id=request_id) as trace:
                with observability.span(trace, "embed_query"):
                    query_vector = embedding_service.embed(payload.message)

                with observability.span(trace, "cache_check"):
                    cached = lookup_cache(cache_store, query_vector)

                if cached:
                    text = cached["response"]
                    input_tokens = count_tokens(payload.message)
                    output_tokens = count_tokens(text)
                    pieces = text.split(" ")
                    for idx, piece in enumerate(pieces):
                        if await request.is_disconnected():
                            aborted_streams += 1
                            return
                        await asyncio.sleep(0.005)
                        suffix = " " if idx < len(pieces) - 1 else ""
                        yield sse({"type": "token", "content": piece + suffix})
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    await log_usage(
                        {
                            "request_id": request_id,
                            "api_key": api_key,
                            "model": cached.get("model", "semantic-cache"),
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "cost_usd": 0.0,
                            "latency_ms": latency_ms,
                            "ttft_ms": 0,
                            "cache_hit": True,
                            "fallback_used": False,
                        }
                    )
                    charged = True
                    yield sse(
                        {
                            "type": "done",
                            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                            "cost_usd": 0.0,
                            "cache_hit": True,
                            "similarity": round(cached["score"], 4),
                            "sources": cached.get("sources", []),
                        }
                    )
                    return

                with observability.span(trace, "vector_search"):
                    chunks = chunk_store.search(query_vector, top_k=3)
                if not chunks:
                    raise HTTPException(status_code=503, detail="Vector index is empty. Run POST /index/rebuild first.")

                messages = build_messages(payload.message, chunks)
                prompt_text = "\n".join(message["content"] for message in messages)
                input_tokens = count_tokens(prompt_text)
                completion_parts: list[str] = []
                model_used = key_config.models[0]
                fallback_used = False
                ttft_ms = 0

                async with llm_semaphore:
                    with observability.span(trace, "llm_call", model=key_config.models[0]):
                        async for chunk in llm.stream(key_config.models, messages):
                            if await request.is_disconnected():
                                aborted_streams += 1
                                raise asyncio.CancelledError()
                            model_used = chunk.model
                            fallback_used = chunk.fallback_used
                            ttft_ms = chunk.ttft_ms or ttft_ms
                            completion_parts.append(chunk.content)
                            yield sse({"type": "token", "content": chunk.content})

                completion = "".join(completion_parts)
                output_tokens = count_tokens(completion)
                total_tokens = input_tokens + output_tokens
                await rate_limiter.charge_actual(api_key, key_config, total_tokens)
                charged = True
                cost = estimate_cost_usd(model_used, input_tokens, output_tokens)
                output_filtered = output_needs_filtering(completion)
                if output_filtered:
                    append_suspicious_response(
                        {
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "request_id": request_id,
                            "api_key": api_key,
                            "model": model_used,
                            "response": completion[:1000],
                        }
                    )
                source_ids = [chunk["id"] for chunk in chunks]
                store_cache(cache_store, query_vector, payload.message, completion, model_used, source_ids)
                latency_ms = int((time.perf_counter() - started) * 1000)
                await log_usage(
                    {
                        "request_id": request_id,
                        "api_key": api_key,
                        "model": model_used,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": cost,
                        "latency_ms": latency_ms,
                        "ttft_ms": ttft_ms,
                        "cache_hit": False,
                        "fallback_used": fallback_used,
                        "output_filtered": output_filtered,
                    }
                )
                yield sse(
                    {
                        "type": "done",
                        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                        "cost_usd": cost,
                        "cache_hit": False,
                        "sources": source_ids,
                        "model": model_used,
                        "fallback_used": fallback_used,
                    }
                )
        except asyncio.CancelledError:
            raise
        finally:
            if not charged:
                await rate_limiter.refund_preflight(api_key, key_config)
            active_streams -= 1

    return StreamingResponse(generate(), media_type="text/event-stream")
