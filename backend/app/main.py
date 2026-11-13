import asyncio
import json
import logging
import time
from typing import Any
import uuid
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse  # pyrefly: ignore[missing-import] # type: ignore

try:
    from .config import get_settings
    from .cost import UsageTracker
    from .graph import build_graph, get_checkpointer_context
except (ImportError, ValueError):
    try:
        from app.config import get_settings  # type: ignore
        from app.cost import UsageTracker  # type: ignore
        from app.graph import build_graph, get_checkpointer_context  # type: ignore
    except (ImportError, ValueError):
        from backend.app.config import get_settings  # type: ignore
        from backend.app.cost import UsageTracker  # type: ignore
        from backend.app.graph import build_graph, get_checkpointer_context  # type: ignore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Deep Research Agent API",
    version="1.0.0",
    description="Autonomous deep research agent with parallel workers, verification, and live SSE streaming.",
)

# Configure CORS
origins = [
    settings.frontend_url,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory stores for run tracking and live event broadcasting
RUN_STORE: dict[str, dict[str, Any]] = {}
EVENT_QUEUES: dict[str, list[asyncio.Queue]] = {}
IP_REQUEST_TIMES: dict[str, list[float]] = {}


class ResearchRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Research question (10-500 characters)",
        examples=["What is the impact of AI on healthcare diagnostics?"],
    )


def check_rate_limit(client_ip: str, max_requests: int = 5, window_seconds: float = 3600.0) -> None:
    """Enforce per-IP sliding window rate limiting (relaxed in dev mode)."""
    if settings.app_env == "dev" or client_ip in ("127.0.0.1", "::1", "localhost", "testclient"):
        return

    now = time.time()
    timestamps = IP_REQUEST_TIMES.get(client_ip, [])
    # Prune timestamps older than window
    timestamps = [t for t in timestamps if now - t < window_seconds]
    if len(timestamps) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: maximum {max_requests} research runs per hour.",
        )
    timestamps.append(now)
    IP_REQUEST_TIMES[client_ip] = timestamps


async def _execute_agent_task(run_id: str, question: str, is_resume: bool = False) -> None:
    """Background task driving the LangGraph execution and publishing events to SSE listeners."""
    tracker = UsageTracker(model_name=settings.llm_model)
    RUN_STORE[run_id]["status"] = "running"

    try:
        async with get_checkpointer_context() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)

            initial_state = None if is_resume else {
                "run_id": run_id,
                "question": question,
                "round_number": 0,
                "search_count": 0,
                "notes": [],
                "sources": [],
                "events": [],
            }

            seen_event_count = 0
            final_state: dict[str, Any] = {}

            run_config = {
                "configurable": {"thread_id": run_id},
                "run_name": "deep_research_agent",
                "metadata": {
                    "run_id": run_id,
                    "llm_provider": settings.llm_provider,
                    "llm_model": settings.llm_model,
                    "APP_ENV": settings.app_env,
                },
                "tags": [settings.app_env],
            }

            async def _stream_graph() -> None:
                nonlocal final_state, seen_event_count
                async for chunk in graph.astream(initial_state, config=run_config, stream_mode="values"):
                    final_state = chunk
                    events = chunk.get("events", [])
                    if len(events) > seen_event_count:
                        new_events = events[seen_event_count:]
                        seen_event_count = len(events)
                        for ev in new_events:
                            RUN_STORE[run_id]["events"].append(ev)
                            for q in EVENT_QUEUES.get(run_id, []):
                                await q.put(ev)

            await asyncio.wait_for(_stream_graph(), timeout=settings.run_timeout_seconds)

            tracker.record_search(final_state.get("search_count", 0))
            usage_summary = tracker.summary()

            if final_state.get("error"):
                RUN_STORE[run_id].update(
                    {
                        "status": "failed",
                        "error": final_state.get("error"),
                        "usage": usage_summary,
                    }
                )
                err_event = {
                    "type": "error",
                    "message": str(final_state.get("error")),
                    "data": usage_summary,
                }
                for q in EVENT_QUEUES.get(run_id, []):
                    await q.put(err_event)
                return

            report_dump = final_state.get("report").model_dump() if final_state.get("report") else None
            RUN_STORE[run_id].update(
                {
                    "status": "completed",
                    "report": report_dump,
                    "notes": final_state.get("numbered_notes", []),
                    "sources": final_state.get("source_index", {}),
                    "verdicts": [v.model_dump() for v in final_state.get("verdicts", [])],
                    "removed_claims": final_state.get("removed_claims", []),
                    "usage": usage_summary,
                    "stop_reason": final_state.get("stop_reason"),
                }
            )
            done_event = {"type": "done", "message": "Research run completed successfully.", "data": usage_summary}
            for q in EVENT_QUEUES.get(run_id, []):
                await q.put(done_event)

    except Exception as exc:
        logger.exception("Run %s failed: %s", run_id, exc)
        RUN_STORE[run_id]["status"] = "failed"
        RUN_STORE[run_id]["error"] = str(exc)
        err_event = {"type": "error", "message": f"Run failed: {exc}", "data": {}}
        for q in EVENT_QUEUES.get(run_id, []):
            await q.put(err_event)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Deep Research Agent starting up...")
    logger.info("Active LLM Provider: %s", settings.llm_provider)
    logger.info("Active LLM Model:    %s", settings.llm_model)
    logger.info("App Environment:     %s", settings.app_env)


@app.api_route("/health", methods=["GET", "HEAD"])
def health() -> dict[str, str]:
    """Healthcheck endpoint (no external service calls)."""
    return {"status": "ok"}


@app.post("/api/runs", status_code=status.HTTP_201_CREATED)
async def create_run(req: ResearchRequest, request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Submit a research question, initiate the background research agent, and return run_id."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    check_rate_limit(client_ip)

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    RUN_STORE[run_id] = {
        "run_id": run_id,
        "question": req.question,
        "status": "queued",
        "events": [],
        "report": None,
        "notes": [],
        "sources": {},
        "verdicts": [],
        "removed_claims": [],
        "usage": {},
    }
    EVENT_QUEUES[run_id] = []

    background_tasks.add_task(_execute_agent_task, run_id, req.question, False)
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}/events")
async def stream_run_events(run_id: str) -> EventSourceResponse:
    """Stream live research events for a run using Server-Sent Events (SSE)."""
    if run_id not in RUN_STORE:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    queue: asyncio.Queue = asyncio.Queue()
    EVENT_QUEUES.setdefault(run_id, []).append(queue)

    # Replay past events first
    for ev in RUN_STORE[run_id].get("events", []):
        await queue.put(ev)

    async def event_generator():
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": "message", "data": json.dumps(ev)}
                    if ev.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    # Keep-alive comment every 15 seconds
                    yield {"comment": "keep-alive"}
        finally:
            if run_id in EVENT_QUEUES and queue in EVENT_QUEUES[run_id]:
                EVENT_QUEUES[run_id].remove(queue)

    return EventSourceResponse(event_generator())


@app.get("/api/runs/{run_id}")
def get_run_status(run_id: str) -> dict[str, Any]:
    """Get the current execution status and final research result."""
    if run_id not in RUN_STORE:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return RUN_STORE[run_id]


@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Resume a research run from its checkpoint."""
    if run_id not in RUN_STORE:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    question = RUN_STORE[run_id].get("question", "")
    background_tasks.add_task(_execute_agent_task, run_id, question, True)
    return {"run_id": run_id, "status": "resumed"}
