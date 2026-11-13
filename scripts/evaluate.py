"""
Evaluation script: runs 3 fixed demo questions and prints a results table.
Requires live API keys (GOOGLE_API_KEY / ANTHROPIC_API_KEY and TAVILY_API_KEY).
"""
import asyncio
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Ensure root and backend directory are in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

load_dotenv(ROOT_DIR / "backend" / ".env")
load_dotenv(ROOT_DIR / ".env")

try:
    from backend.app.cost import UsageTracker
    from backend.app.graph import build_graph, get_checkpointer_context
    from backend.app.schemas import ReportDraft
except ImportError:
    from app.cost import UsageTracker  # type: ignore
    from app.graph import build_graph, get_checkpointer_context  # type: ignore
    from app.schemas import ReportDraft  # type: ignore

EVAL_QUESTIONS = [
    "What are the most promising breakthroughs in quantum computing error correction?",
    "How are solid-state batteries changing electric vehicle performance and range?",
    "What is the impact of mRNA vaccine technology on cancer immunotherapy?",
]


async def evaluate_single(question: str) -> dict:
    """Run one research question end-to-end and return evaluation metrics."""
    run_id = f"eval_{uuid.uuid4().hex[:8]}"
    tracker = UsageTracker()

    # Use async context-manager checkpointer (SQLite in dev, Postgres if DATABASE_URL set)
    async with get_checkpointer_context() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": run_id}}

        initial_input = {
            "run_id": run_id,
            "question": question,
            "round_number": 0,
            "search_count": 0,
            "notes": [],
            "sources": [],
            "events": [],
        }

        final_state = await graph.ainvoke(initial_input, config=config)

    tracker.record_search(final_state.get("search_count", 0))
    summary = tracker.summary()

    report: ReportDraft | None = final_state.get("report")
    has_summary = bool(report and report.summary and len(report.summary) > 20)
    sections_count = len(report.sections) if report else 0
    sources_count = len(final_state.get("source_index", {}))
    removed_count = len(final_state.get("removed_claims", []))

    return {
        "question": question[:35] + "..." if len(question) > 35 else question,
        "duration": f"{summary['duration_seconds']}s",
        "searches": summary["searches"],
        "sources": sources_count,
        "removed": removed_count,
        "cost": f"${summary['estimated_cost_usd']:.4f}",
        "summary_ok": "Yes" if has_summary else "No",
        "sections": sections_count,
    }


async def main() -> None:
    print("=" * 85)
    print("RUNNING BENCHMARK EVALUATION (3 Questions)")
    print("=" * 85)

    results = []
    for idx, q in enumerate(EVAL_QUESTIONS, 1):
        print(f"\n[{idx}/3] Evaluating: '{q}'...")
        try:
            res = await evaluate_single(q)
        except Exception as exc:
            print(f"  [ERROR] Question {idx} failed: {exc}")
            res = {
                "question": q[:35] + "..." if len(q) > 35 else q,
                "duration": "N/A",
                "searches": 0,
                "sources": 0,
                "removed": 0,
                "cost": "$0.0000",
                "summary_ok": "No",
                "sections": 0,
            }
        results.append(res)

    print("\n" + "=" * 85)
    print("EVALUATION RESULTS TABLE")
    print("=" * 85)
    header = (
        f"{'Question':<38} | {'Duration':<9} | {'Searches':<8} | "
        f"{'Sources':<7} | {'Removed':<7} | {'Cost':<9} | {'Summary':<7} | {'Sections':<8}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['question']:<38} | {r['duration']:<9} | {r['searches']:<8} | "
            f"{r['sources']:<7} | {r['removed']:<7} | {r['cost']:<9} | {r['summary_ok']:<7} | {r['sections']:<8}"
        )
    print("=" * 85)


if __name__ == "__main__":
    asyncio.run(main())
