import asyncio
import aiohttp
from typing import List
import urllib.parse
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

from app.services.interfaces import BaseTrendTool, Topic
from app.core.config import Config

class GithubTrendsTool(BaseTrendTool):
    async def fetch_topics(self) -> List[Topic]:
        async with aiohttp.ClientSession() as session:
            # Query machine learning and AI topics created in the last week, sorted by stars
            last_week = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
            query = f"stars:>50 pushed:>{last_week} topic:machine-learning OR topic:artificial-intelligence"
            url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc"
            
            headers = {"Accept": "application/vnd.github.v3+json"}
            if Config.GITHUB_TOKEN:
                headers["Authorization"] = f"token {Config.GITHUB_TOKEN}"
                
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    
                    topics = []
                    for item in data.get('items', [])[:5]: # Top 5
                        name = item.get('name', '').replace('-', ' ').title()
                        stars = item.get('stargazers_count', 0)
                        # Normalize stars to a 0-1 scale loosely
                        trend_score = min(stars / 5000.0, 1.0) 
                        topics.append(Topic(
                            name=name,
                            source="github",
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
                        topics.append(Topic(
                            name=title,
                            source="arxiv",
                            trend_score=0.9, # ArXiv recent submissions represent cutting edge
                            novelty_score=0.9
                        ))
                    return topics
            except Exception:
                return []

class RedditTrendsTool(BaseTrendTool):
    async def fetch_topics(self) -> List[Topic]:
        async with aiohttp.ClientSession() as session:
            url = "https://www.reddit.com/r/MachineLearning/hot.json?limit=5"
            headers = {"User-Agent": Config.REDDIT_USER_AGENT}
            
            try:
                async with session.get(url, headers=headers) as response:
                    # Fallback to empty if Reddit blocks us
                    if response.status != 200:
                        return []
                    data = await response.json()
                    
                    topics = []
                    for child in data.get('data', {}).get('children', []):
                        post = child.get('data', {})
                        title = post.get('title', '')
                        ups = post.get('ups', 0)
                        
                        trend_score = min(ups / 1000.0, 1.0)
                        
                        # Filter out basic weekly threads based on title if necessary
                        if "Simple Questions" not in title:
                            topics.append(Topic(
                                name=title,
                                source="reddit",
                                trend_score=trend_score,
                                novelty_score=0.6
                            ))
                    return topics
            except Exception:
                return []
