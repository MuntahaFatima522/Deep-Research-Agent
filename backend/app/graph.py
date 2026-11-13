import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Any
import uuid
from langgraph.graph import END, START, StateGraph  # pyrefly: ignore[missing-import] # type: ignore
from langgraph.types import Send  # pyrefly: ignore[missing-import] # type: ignore

try:
    from .config import get_settings
    from .nodes.evidence import organize_evidence
    from .nodes.gaps import check_gaps, should_continue
    from .nodes.planner import make_plan
    from .nodes.synthesizer import write_report
    from .nodes.verifier import apply_verdicts, verify_claims
    from .nodes.worker import run_worker
    from .schemas import SubQuestion
    from .state import ResearchState
except (ImportError, ValueError):
    try:
        from app.config import get_settings  # type: ignore
        from app.nodes.evidence import organize_evidence  # type: ignore
        from app.nodes.gaps import check_gaps, should_continue  # type: ignore
        from app.nodes.planner import make_plan  # type: ignore
        from app.nodes.synthesizer import write_report  # type: ignore
        from app.nodes.verifier import apply_verdicts, verify_claims  # type: ignore
        from app.nodes.worker import run_worker  # type: ignore
        from app.schemas import SubQuestion  # type: ignore
        from app.state import ResearchState  # type: ignore
    except (ImportError, ValueError):
        from backend.app.config import get_settings  # type: ignore
        from backend.app.nodes.evidence import organize_evidence  # type: ignore
        from backend.app.nodes.gaps import check_gaps, should_continue  # type: ignore
        from backend.app.nodes.planner import make_plan  # type: ignore
        from backend.app.nodes.synthesizer import write_report  # type: ignore
        from backend.app.nodes.verifier import apply_verdicts, verify_claims  # type: ignore
        from backend.app.nodes.worker import run_worker  # type: ignore
        from backend.app.schemas import SubQuestion  # type: ignore
        from backend.app.state import ResearchState  # type: ignore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Node Implementations
# ---------------------------------------------------------

async def plan_node(state: ResearchState) -> dict[str, Any]:
    """Analyze the research question and construct a structured research plan."""
    question = state["question"]
    plan = await make_plan(question)
    return {
        "plan": plan,
        "pending_sub_questions": plan.sub_questions,
        "round_number": 0,
        "events": [
            {
                "type": "plan",
                "message": f"Created research plan with {len(plan.sub_questions)} sub-questions.",
                "data": plan.model_dump(),
            }
        ],
    }


def fan_out_workers(state: ResearchState) -> list[Send]:
    """Fan out parallel worker executions, one Send per pending sub-question."""
    settings = get_settings()
    pending = state.get("pending_sub_questions", [])
    run_id = state.get("run_id", "")
    searches_remaining = max(0, settings.max_searches - state.get("search_count", 0))
    return [
        Send(
            "worker_node",
            {
                "sub_question": sq,
                "run_id": run_id,
                "searches_remaining": searches_remaining,
                "max_searches_per_worker": settings.max_searches_per_worker,
            },
        )
        for sq in pending
    ]


async def worker_node(input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute research worker for a single sub-question: search and extract notes."""
    raw_sq = input_data["sub_question"]
    sub_question = SubQuestion(**raw_sq) if isinstance(raw_sq, dict) else raw_sq

    start_event = {
        "type": "worker_started",
        "message": f"Worker started for: '{sub_question.question}'",
        "data": {"sub_question_id": sub_question.id},
    }

    try:
        worker_res = await run_worker(
            sub_question,
            searches_remaining=input_data.get("searches_remaining"),
            max_searches_per_worker=int(input_data.get("max_searches_per_worker", 4)),
        )
        finish_event = {
            "type": "worker_finished",
            "message": f"Worker completed {sub_question.id} with {len(worker_res['notes'])} notes.",
            "data": {
                "sub_question_id": sub_question.id,
                "notes_count": len(worker_res["notes"]),
            },
        }
        return {
            "notes": worker_res["notes"],
            "sources": worker_res["sources"],
            "search_count": worker_res["search_count"],
            "events": [start_event, finish_event],
        }
    except Exception as exc:
        logger.warning("Worker node failed for %s: %s", sub_question.id, exc)
        fail_event = {
            "type": "worker_failed",
            "message": f"Worker for {sub_question.id} failed: {exc}",
            "data": {"sub_question_id": sub_question.id, "error": str(exc)},
        }
        return {
            "notes": [],
            "sources": [],
            "search_count": 0,
            "events": [start_event, fail_event],
        }


def merge_node(state: ResearchState) -> dict[str, Any]:
    """Organize, deduplicate, and number gathered evidence notes and sources."""
    notes = state.get("notes", [])
    sources = state.get("sources", [])
    organized = organize_evidence(notes, sources)

    updates: dict[str, Any] = {
        "source_index": organized["source_index"],
        "numbered_notes": organized["numbered_notes"],
        "events": [
            {
                "type": "evidence",
                "message": f"Organized {len(organized['numbered_notes'])} notes across {len(organized['source_index'])} sources.",
                "data": {
                    "notes_count": len(organized["numbered_notes"]),
                    "sources_count": len(organized["source_index"]),
                    "notes": organized["numbered_notes"],
                },
            }
        ],
    }
    if not organized["numbered_notes"] and not notes:
        updates["error"] = "All research workers failed; no evidence collected."
    return updates


def route_after_merge(state: ResearchState) -> str:
    """Skip gap analysis when no evidence was collected."""
    if state.get("error") or (not state.get("notes") and not state.get("numbered_notes")):
        return "error_node"
    return "gaps_node"


async def gaps_node(state: ResearchState) -> dict[str, Any]:
    """Evaluate gathered evidence, detecting missing knowledge and incrementing round number."""
    question = state["question"]
    plan = state["plan"]
    numbered_notes = state.get("numbered_notes", [])

    if plan is None:
        raise ValueError("Cannot perform gap check without a research plan.")

    gap_result = await check_gaps(question, plan, numbered_notes)
    current_round = state.get("round_number", 0) + 1
    stop_reason = "Stopped: enough evidence" if gap_result.is_enough else state.get("stop_reason")

    return {
        "gaps": gap_result,
        "pending_sub_questions": gap_result.new_sub_questions,
        "round_number": current_round,
        "stop_reason": stop_reason,
        "events": [
            {
                "type": "gaps",
                "message": f"Gap review round {current_round}: sufficient={gap_result.is_enough}, missing={len(gap_result.missing)} items.",
                "data": gap_result.model_dump(),
            }
        ],
    }


def route_after_gaps(state: ResearchState) -> list[Send] | str:
    """Conditional router determining whether to launch another round of parallel workers or synthesize."""
    if not state.get("numbered_notes") and not state.get("notes"):
        return "error_node"

    settings = get_settings()
    keep_going, stop_reason = should_continue(state, settings)
    if keep_going:
        return fan_out_workers(state)
    if not state.get("numbered_notes"):
        return "error_node"
    return "synthesize_node"


async def error_node(state: ResearchState) -> dict[str, Any]:
    """Stop the run when all workers failed and no evidence was collected."""
    message = state.get("error") or "All research workers failed; no evidence collected."
    return {
        "error": message,
        "stop_reason": message,
        "events": [
            {
                "type": "error",
                "message": message,
                "data": {},
            }
        ],
    }


async def synthesize_node(state: ResearchState) -> dict[str, Any]:
    """Synthesize the comprehensive research report strictly grounded on numbered notes."""
    question = state["question"]
    numbered_notes = state.get("numbered_notes", [])

    writing_event = {
        "type": "writing",
        "message": "Synthesizing research report grounded in collected evidence...",
        "data": {},
    }

    report = await write_report(question, numbered_notes)
    return {
        "report": report,
        "events": [writing_event],
    }


async def verify_node(state: ResearchState) -> dict[str, Any]:
    """Verify all report claims against cited snippets and prune unsupported assertions."""
    report = state.get("report")
    numbered_notes = state.get("numbered_notes", [])

    if report is None:
        raise ValueError("Cannot verify report claims before synthesis.")

    verifying_event = {
        "type": "verifying",
        "message": "Verifying all claims concurrently against cited source snippets...",
        "data": {},
    }

    verdicts = await verify_claims(report, numbered_notes)
    cleaned_report, removed_claims = apply_verdicts(report, verdicts)

    report_event = {
        "type": "report",
        "message": f"Report finalized: {len(removed_claims)} unsupported claims removed.",
        "data": {
            "removed_claims": removed_claims,
            "retained_sections": len(cleaned_report.sections),
            "verdicts": [v.model_dump() for v in verdicts],
        },
    }

    return {
        "report": cleaned_report,
        "verdicts": verdicts,
        "removed_claims": removed_claims,
        "events": [verifying_event, report_event],
    }


def finish_node(state: ResearchState) -> dict[str, Any]:
    """Finalize research state and emit completion event."""
    return {
        "stop_reason": state.get("stop_reason") or "Completed successfully",
        "events": [
            {
                "type": "done",
                "message": "Deep research process completed successfully.",
                "data": {
                    "total_rounds": state.get("round_number", 0),
                    "total_searches": state.get("search_count", 0),
                },
            }
        ],
    }


# ---------------------------------------------------------
# Graph Compilation
# ---------------------------------------------------------

def build_graph(checkpointer: Any = None) -> Any:
    """Build and compile the LangGraph StateGraph orchestration workflow."""
    builder = StateGraph(ResearchState)

    # Register workflow nodes
    builder.add_node("plan_node", plan_node)
    builder.add_node("worker_node", worker_node)
    builder.add_node("merge_node", merge_node)
    builder.add_node("gaps_node", gaps_node)
    builder.add_node("synthesize_node", synthesize_node)
    builder.add_node("verify_node", verify_node)
    builder.add_node("finish_node", finish_node)
    builder.add_node("error_node", error_node)

    # Wire up edges
    builder.add_edge(START, "plan_node")
    builder.add_conditional_edges(
        "plan_node",
        fan_out_workers,
        ["worker_node"],
    )
    builder.add_edge("worker_node", "merge_node")
    builder.add_conditional_edges(
        "merge_node",
        route_after_merge,
        ["gaps_node", "error_node"],
    )
    builder.add_conditional_edges(
        "gaps_node",
        route_after_gaps,
        ["worker_node", "synthesize_node", "error_node"],
    )
    builder.add_edge("synthesize_node", "verify_node")
    builder.add_edge("verify_node", "finish_node")
    builder.add_edge("error_node", "finish_node")
    builder.add_edge("finish_node", END)

    return builder.compile(checkpointer=checkpointer)


@asynccontextmanager
async def get_checkpointer_context():
    """Return configured async checkpointer (Postgres when DATABASE_URL is set, SQLite otherwise)."""
    settings = get_settings()
    if settings.database_url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
        async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
            await saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # type: ignore
        data_dir = Path(__file__).resolve().parent.parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(data_dir / "checkpoints.sqlite")
        async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
            yield saver


def _run_config(run_id: str) -> dict[str, Any]:
    """Build LangGraph invoke config with LangSmith metadata."""
    settings = get_settings()
    return {
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


async def run_research(question: str, run_id: str | None = None) -> dict[str, Any]:
    """Execute a research run from start to finish."""
    if not run_id:
        run_id = f"run_{uuid.uuid4().hex[:10]}"

    settings = get_settings()
    async with get_checkpointer_context() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        config = _run_config(run_id)

        initial_state = {
            "run_id": run_id,
            "question": question,
            "round_number": 0,
            "search_count": 0,
            "notes": [],
            "sources": [],
            "events": [],
        }

        final_state = await asyncio.wait_for(
            graph.ainvoke(initial_state, config=config),
            timeout=settings.run_timeout_seconds,
        )
        return final_state


async def resume_research(run_id: str) -> dict[str, Any]:
    """Resume a research run from its latest persisted checkpoint."""
    settings = get_settings()
    async with get_checkpointer_context() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        config = _run_config(run_id)

        final_state = await asyncio.wait_for(
            graph.ainvoke(None, config=config),
            timeout=settings.run_timeout_seconds,
        )
        return final_state
