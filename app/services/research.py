import asyncio
import aiohttp
import urllib.parse
from typing import List
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

from app.services.interfaces import BaseResearchTool, Claim
from app.core.config import settings

semaphore = asyncio.Semaphore(5)

async def safe_fetch(task, timeout=10):
    try:
        return await asyncio.wait_for(task, timeout)
    except asyncio.TimeoutError:
        return []
    except Exception as e:
        print(f"Research fetch failed: {e}")
        return []

class ArxivResearchTool(BaseResearchTool):
    async def fetch(self, query: str) -> List[Claim]:
        async def _fetch():
            async with aiohttp.ClientSession() as session:
                url = f"http://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query)}&max_results=3"
                async with session.get(url) as response:
                    if response.status != 200:
                        return []
                    data = await response.text()
                    
                    root = ET.fromstring(data)
                    entries = root.findall('{http://www.w3.org/2005/Atom}entry')
                    
                    claims = []
                    for entry in entries:
                        summary = entry.find('{http://www.w3.org/2005/Atom}summary').text.replace('\\n', ' ').strip()
                        claims.append(Claim(text=summary, source="arxiv.org", confidence=0.9))
                    return claims
                    
        async with semaphore:
            return await safe_fetch(_fetch())

class GithubResearchTool(BaseResearchTool):
    async def fetch(self, query: str) -> List[Claim]:
        async def _fetch():
            async with aiohttp.ClientSession() as session:
                url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc"
                headers = {"Accept": "application/vnd.github.v3+json"}
                if settings.GITHUB_TOKEN:
                    headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    
                    claims = []
                    for item in data.get('items', [])[:3]:
                        desc = item.get('description', '')
                        if desc:
                            claims.append(Claim(
                                text=desc,
                                source=f"github.com/{item.get('full_name')}",
                                confidence=0.85
                            ))
                    return claims
                    
        async with semaphore:
            return await safe_fetch(_fetch())


class NewsApiResearchTool(BaseResearchTool):
    """
    Replaces RedditResearchTool. Uses NewsAPI /v2/everything endpoint
    to search for articles related to a specific query, then extracts
    article descriptions as claims.
    """
    async def fetch(self, query: str) -> List[Claim]:
        async def _fetch():
            if not settings.NEWSAPI_KEY:
                return []

            async with aiohttp.ClientSession() as session:
                params = {
                    "q": query,
                    "sortBy": "relevancy",
                    "language": "en",
                    "pageSize": "5",
                    "apiKey": settings.NEWSAPI_KEY,
                }
                url = f"https://newsapi.org/v2/everything?{urllib.parse.urlencode(params)}"

                async with session.get(url) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()

                    claims = []
                    for article in data.get("articles", [])[:3]:
                        # Use article content if available, else description
                        text = article.get("content", "") or article.get("description", "")
                        if not text:
                            continue

                        # Clean up "[+N chars]" suffix from NewsAPI
                        if "[+" in text:
                            text = text[:text.rfind("[+")]

                        text = text.strip()
                        if len(text) < 30:
                            continue

                        source_url = article.get("url", "")
                        source_name = article.get("source", {}).get("name", "news")

                        claims.append(Claim(
                            text=text[:500],
                            source=f"newsapi:{source_name}|{source_url}",
                            confidence=0.7,
                        ))
                    return claims

        async with semaphore:
            return await safe_fetch(_fetch())
