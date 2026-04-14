import asyncio
import aiohttp
import urllib.parse
from typing import List
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

from app.services.interfaces import BaseResearchTool, Claim
from app.core.config import Config

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
                if Config.GITHUB_TOKEN:
                    headers["Authorization"] = f"token {Config.GITHUB_TOKEN}"
                
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

class RedditResearchTool(BaseResearchTool):
    async def fetch(self, query: str) -> List[Claim]:
        async def _fetch():
            async with aiohttp.ClientSession() as session:
                url = f"https://www.reddit.com/r/MachineLearning/search.json?q={urllib.parse.quote(query)}&restrict_sr=on&limit=3"
                headers = {"User-Agent": Config.REDDIT_USER_AGENT}
                
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    
                    claims = []
                    for child in data.get('data', {}).get('children', []):
                        post = child.get('data', {})
                        text = post.get('selftext', '')
                        if not text:
                            text = post.get('title', '')
                            
                        # Limiting length of claim text
                        text = text[:500] + "..." if len(text) > 500 else text
                        
                        claims.append(Claim(
                            text=text,
                            source=f"reddit.com{post.get('permalink')}",
                            confidence=0.7
                        ))
                    return claims
                    
        async with semaphore:
            return await safe_fetch(_fetch())
