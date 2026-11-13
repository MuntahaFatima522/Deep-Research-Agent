import asyncio
import sys
from pathlib import Path

# Add root and backend directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

try:
    from backend.app.config import get_settings
    from backend.app.llm import get_llm
    from backend.app.tools.search import search_web
except ImportError:
    from app.config import get_settings  # type: ignore
    from app.llm import get_llm  # type: ignore
    from app.tools.search import search_web  # type: ignore


async def main() -> None:
    settings = get_settings()
    print("=" * 60)
    print("Deep Research Agent: Setup Verification")
    print("=" * 60)
    print(f"Provider: {settings.llm_provider}")
    print(f"Model:    {settings.llm_model}")
    print(f"App Env:  {settings.app_env}")
    print("-" * 60)

    # 1. Test LLM Call
    print("\n[1/2] Testing LLM call ('Say hello in five words')...")
    try:
        llm = get_llm(temperature=0)
        response = await llm.ainvoke("Say hello in five words")
        content = response.content
        if isinstance(content, list) and content and isinstance(content[0], dict):
            content = content[0].get("text", str(content))
        print(f"LLM Response:\n{content}")
    except Exception as exc:
        print(f"LLM call failed: {exc}")

    # 2. Test Tavily Search Call
    print("\n[2/2] Testing Tavily search call ('Python programming language')...")
    try:
        results = await search_web("Python programming language", max_results=1)
        if results:
            first = results[0]
            print(f"Tavily Search Result:\nTitle: {first['title']}\nURL:   {first['url']}\nSnippet: {first['snippet'][:150]}...")
        else:
            print("No search results returned (check TAVILY_API_KEY).")
    except Exception as exc:
        print(f"Tavily search failed: {exc}")

    print("\n" + "=" * 60)
    print("Setup Verification Completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
