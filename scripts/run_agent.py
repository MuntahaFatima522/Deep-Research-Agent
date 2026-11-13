import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Ensure root and backend directory are in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Load environment variables
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


async def run_agent(question: str, run_id: str | None = None, is_resume: bool = False) -> None:
    if not run_id:
        run_id = f"run_{uuid.uuid4().hex[:8]}"

    tracker = UsageTracker()

    async with get_checkpointer_context() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": run_id}}

        print("=" * 70)
        print(f"DEEP RESEARCH AGENT  |  Run ID: {run_id}")
        print(f"Question: {question}")
        print("=" * 70)

        initial_input = None if is_resume else {
            "run_id": run_id,
            "question": question,
            "round_number": 0,
            "search_count": 0,
            "notes": [],
            "sources": [],
            "events": [],
        }

        seen_event_count = 0
        final_state = {}

        async for chunk in graph.astream(initial_input, config=config, stream_mode="values"):
            final_state = chunk
            events = chunk.get("events", [])
            if len(events) > seen_event_count:
                for ev in events[seen_event_count:]:
                    ev_type = ev.get("type", "info").upper()
                    msg = ev.get("message", "")
                    print(f"[{ev_type:15}] {msg}", flush=True)
                seen_event_count = len(events)

    # Display Final Report
    report: ReportDraft | None = final_state.get("report")
    print("\n" + "=" * 70)
    if report:
        print(f"FINAL REPORT: {report.title}")
        print("=" * 70)
        print(f"\nEXECUTIVE SUMMARY:\n{report.summary}\n")

        for section in report.sections:
            print(f"\n### {section.heading}")
            for claim in section.claims:
                citations = ", ".join(f"[{n}]" for n in claim.note_numbers)
                cite_str = f" {citations}" if citations else ""
                print(f"- {claim.text}{cite_str}")
    else:
        print("No report was generated.")

    # Display Sources
    source_index = final_state.get("source_index", {})
    if source_index:
        print("\n" + "-" * 70)
        print("CITED SOURCES:")
        for num, info in sorted(source_index.items()):
            print(f"  [{num}] {info.get('title')} -> {info.get('url')}")

    # Display Removed Claims
    removed = final_state.get("removed_claims", [])
    if removed:
        print("\n" + "-" * 70)
        print(f"VERIFICATION PRUNED ({len(removed)} unsupported claims):")
        for claim_text in removed:
            print(f"  [X] {claim_text}")

    # Display Usage Summary
    tracker.record_search(final_state.get("search_count", 0))
    summary = tracker.summary()
    print("\n" + "=" * 70)
    print("USAGE & COST SUMMARY (Estimated):")
    print(f"  Searches executed:   {summary['searches']}")
    print(f"  Duration:            {summary['duration_seconds']}s")
    print(f"  Estimated Cost:      ${summary['estimated_cost_usd']:.4f} USD")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Deep Research Agent from the CLI.")
    parser.add_argument(
        "question",
        nargs="?",
        default="What is the impact of artificial intelligence on healthcare diagnostics?",
        help="Research question to investigate",
    )
    parser.add_argument("--resume", help="Resume an existing run_id from checkpoint")
    args = parser.parse_args()

    if args.resume:
        asyncio.run(run_agent(question="", run_id=args.resume, is_resume=True))
    else:
        asyncio.run(run_agent(question=args.question))


if __name__ == "__main__":
    main()
