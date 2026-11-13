import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend and root directory are in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

# Load environment variables from backend/.env or root .env
load_dotenv(ROOT_DIR / "backend" / ".env")
load_dotenv(ROOT_DIR / ".env")

try:
    from backend.app.tools.reader import read_pages
    from backend.app.tools.search import search_web
except ImportError:
    from app.tools.reader import read_pages  # type: ignore
    from app.tools.search import search_web  # type: ignore


async def main() -> None:
    query = "impact of AI on healthcare diagnostics"
    print(f"--- Searching: '{query}' ---")

    search_results = await search_web(query, max_results=5)
    if not search_results:
        print("No search results returned. Check if TAVILY_API_KEY is configured in backend/.env")
        return

    print(f"Found {len(search_results)} search results:")
    for idx, res in enumerate(search_results, 1):
        print(f"  [{idx}] {res['title']} -> {res['url']}")

    # Select top two URLs to extract
    top_urls = [res["url"] for res in search_results[:2]]
    print(f"\n--- Reading top 2 pages: {top_urls} ---")

    docs = await read_pages(top_urls, max_chars=6000)
    if not docs:
        print("No pages extracted or extraction failed.")
        return

    for idx, doc in enumerate(docs, 1):
        print(f"\n=== Page {idx}: {doc.title} ===")
        print(f"URL: {doc.url}")
        snippet_preview = doc.content[:200].replace("\n", " ").strip()
        print(f"Content Preview (first 200 chars):\n{snippet_preview}...")


if __name__ == "__main__":
    asyncio.run(main())
