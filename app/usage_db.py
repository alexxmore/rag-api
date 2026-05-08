from datetime import datetime, timezone
from pathlib import Path
from statistics import quantiles

import aiosqlite

from app.settings import get_settings


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS usage_records (
    request_id TEXT PRIMARY KEY,
    api_key TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    ttft_ms INTEGER NOT NULL,
    cache_hit INTEGER NOT NULL,
    fallback_used INTEGER NOT NULL,
    output_filtered INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


async def init_db() -> None:
    settings = get_settings()
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(CREATE_SQL)
        await db.commit()


async def log_usage(record: dict) -> None:
    settings = get_settings()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            """
            INSERT INTO usage_records (
                request_id, api_key, model, input_tokens, output_tokens, cost_usd,
                latency_ms, ttft_ms, cache_hit, fallback_used, output_filtered, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["request_id"],
                record["api_key"],
                record["model"],
                record["input_tokens"],
                record["output_tokens"],
                record["cost_usd"],
                record["latency_ms"],
                record["ttft_ms"],
                int(record["cache_hit"]),
                int(record["fallback_used"]),
                int(record.get("output_filtered", False)),
                record.get("created_at") or datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db.commit()


async def usage_today(api_key: str) -> dict:
    settings = get_settings()
    today = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        row = await db.execute_fetchall(
            """
            SELECT COUNT(*), COALESCE(SUM(input_tokens + output_tokens), 0), COALESCE(SUM(cost_usd), 0)
            FROM usage_records
            WHERE api_key = ? AND substr(created_at, 1, 10) = ?
            """,
            (api_key, today),
        )
    requests, tokens, cost = row[0]
    return {"requests": requests, "tokens": tokens, "cost_usd": round(cost, 6)}


async def usage_breakdown(api_key: str) -> dict:
    settings = get_settings()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        rows = await db.execute_fetchall(
            """
            SELECT model, COUNT(*), SUM(input_tokens + output_tokens), SUM(cost_usd),
                   AVG(cache_hit), AVG(fallback_used), AVG(latency_ms)
            FROM usage_records
            WHERE api_key = ?
            GROUP BY model
            """,
            (api_key,),
        )
        latency_rows = await db.execute_fetchall(
            "SELECT latency_ms FROM usage_records WHERE api_key = ? ORDER BY latency_ms",
            (api_key,),
        )
        recent = await db.execute_fetchall(
            """
            SELECT COUNT(*), COALESCE(AVG(cache_hit), 0)
            FROM usage_records
            WHERE api_key = ? AND created_at >= datetime('now', '-1 hour')
            """,
            (api_key,),
        )

    latencies = [row[0] for row in latency_rows]
    p95 = quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0)
    return {
        "models": [
            {
                "model": row[0],
                "requests": row[1],
                "tokens": row[2],
                "cost_usd": round(row[3], 6),
                "cache_hit_rate": round(row[4], 4),
                "fallback_rate": round(row[5], 4),
                "avg_latency_ms": round(row[6], 2),
            }
            for row in rows
        ],
        "cache_hit_rate_last_hour": round(recent[0][1], 4),
        "p95_latency_ms": round(p95, 2),
    }
