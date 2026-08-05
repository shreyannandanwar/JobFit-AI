import logging
import time
from typing import Any, Dict, List, Optional

from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5, retries: int = 2) -> List[Dict[str, str]]:
    """Search DuckDuckGo with exponential backoff."""
    for attempt in range(retries):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                logger.info(f"Search for '{query}' returned {len(results)} results.")
                return results
        except Exception as e:
            logger.warning(f"Search attempt {attempt+1} failed: {e}")
            time.sleep(2**attempt)
    return []


def extract_relevant_excerpts(
    results: List[Dict[str, str]],
    context_keywords: Optional[List[str]] = None,
    max_excerpts: int = 3,
) -> List[Dict[str, Any]]:
    """Filter search results to those containing relevant keywords and add confidence."""
    filtered = []
    keywords = [kw.lower() for kw in (context_keywords or [])]

    for res in results:
        text = (res.get("title", "") + " " + res.get("body", "")).lower()
        matches = sum(1 for kw in keywords if kw in text)
        confidence = min(1.0, matches / max(1, len(keywords) * 0.5))

        if confidence > 0.2:
            filtered.append(
                {
                    "source": res.get("href", ""),
                    "excerpt": res.get("body", "")[:500],
                    "title": res.get("title", ""),
                    "confidence": round(confidence, 2),
                }
            )

    return filtered[:max_excerpts]