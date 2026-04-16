import asyncio
import aiohttp
from typing import List
import urllib.parse
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

from app.services.interfaces import BaseTrendTool, Topic
from app.core.config import settings


class GithubTrendsTool(BaseTrendTool):
    async def fetch_topics(self) -> List[Topic]:
        async with aiohttp.ClientSession() as session:
            # Query machine learning and AI topics created in the last week, sorted by stars
            last_week = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
            query = f"stars:>50 pushed:>{last_week} topic:machine-learning OR topic:artificial-intelligence"
            url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc"
            
            headers = {"Accept": "application/vnd.github.v3+json"}
            if settings.GITHUB_TOKEN:
                headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"
                
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    
                    topics = []
                    for item in data.get('items', [])[:5]: # Top 5
                        name = item.get('name', '').replace('-', ' ').title()
                        desc = item.get('description', '') or ''
                        pushed_at = item.get('pushed_at', '')
                        stars = item.get('stargazers_count', 0)
                        # Normalize stars to a 0-1 scale loosely
                        trend_score = min(stars / 5000.0, 1.0) 
                        topics.append(Topic(
                            name=name,
                            description=desc,
                            source="github",
                            timestamp=pushed_at,
                            trend_score=trend_score,
                            novelty_score=0.8 # New repos have high novelty
                        ))
                    return topics
            except Exception:
                return []


class ArxivTrendsTool(BaseTrendTool):
    async def fetch_topics(self) -> List[Topic]:
        async with aiohttp.ClientSession() as session:
            # Search for cs.AI and cs.LG (AI and Machine Learning)
            url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG&sortBy=submittedDate&sortOrder=desc&max_results=5"
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        return []
                    data = await response.text()
                    
                    # Parse generic XML from arXiv
                    root = ET.fromstring(data)
                    entries = root.findall('{http://www.w3.org/2005/Atom}entry')
                    
                    topics = []
                    for entry in entries:
                        title = entry.find('{http://www.w3.org/2005/Atom}title').text.replace('\\n', ' ').strip()
                        summary_el = entry.find('{http://www.w3.org/2005/Atom}summary')
                        summary = summary_el.text.strip() if summary_el is not None else ''
                        published_el = entry.find('{http://www.w3.org/2005/Atom}published')
                        published = published_el.text.strip() if published_el is not None else ''
                        topics.append(Topic(
                            name=title,
                            description=summary[:300],  # Truncate for embedding efficiency
                            source="arxiv",
                            timestamp=published,
                            trend_score=0.9, # ArXiv recent submissions represent cutting edge
                            novelty_score=0.9
                        ))
                    return topics
            except Exception:
                return []


class NewsApiTrendsTool(BaseTrendTool):
    """
    Replaces Reddit. Uses NewsAPI /v2/everything endpoint to fetch
    trending AI/ML articles from the last 3 days.
    """
    async def fetch_topics(self) -> List[Topic]:
        if not settings.NEWSAPI_KEY:
            return []

        async with aiohttp.ClientSession() as session:
            three_days_ago = (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d')
            params = {
                "q": "artificial intelligence OR machine learning OR LLM OR deep learning",
                "from": three_days_ago,
                "sortBy": "popularity",
                "language": "en",
                "pageSize": "10",
                "apiKey": settings.NEWSAPI_KEY,
            }
            url = f"https://newsapi.org/v2/everything?{urllib.parse.urlencode(params)}"

            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()

                    topics = []
                    for article in data.get("articles", [])[:5]:
                        title = article.get("title", "")
                        desc = article.get("description", "") or ""
                        published = article.get("publishedAt", "")
                        source_name = article.get("source", {}).get("name", "news")

                        # Skip non-English or empty titles
                        if not title or len(title) < 10:
                            continue

                        topics.append(Topic(
                            name=title,
                            description=desc[:300],
                            source=f"newsapi:{source_name}",
                            timestamp=published,
                            trend_score=0.75,  # News articles = moderate signal
                            novelty_score=0.7,
                        ))
                    return topics
            except Exception:
                return []


class GoogleTrendsTool(BaseTrendTool):
    """
    Uses pytrends (unofficial Google Trends API) to fetch
    currently trending searches related to AI/tech.
    Runs in thread pool since pytrends is synchronous.
    """
    async def fetch_topics(self) -> List[Topic]:
        loop = asyncio.get_running_loop()
        try:
            topics = await loop.run_in_executor(None, self._fetch_sync)
            return topics
        except Exception:
            return []

    def _fetch_sync(self) -> List[Topic]:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            return []

        try:
            pytrends = TrendReq(hl='en-US', tz=330)  # IST timezone offset

            # Get currently trending searches
            trending = pytrends.trending_searches(pn='india')

            topics = []
            for idx, row in trending.head(5).iterrows():
                term = row[0]
                # Filter: skip if not tech/AI related (basic heuristic)
                topics.append(Topic(
                    name=term,
                    description=f"Trending search term: {term}",
                    source="google_trends",
                    timestamp=datetime.utcnow().isoformat(),
                    trend_score=0.85,  # Google Trends = strong signal
                    novelty_score=0.6,  # May not be novel
                ))
            return topics
        except Exception:
            return []
