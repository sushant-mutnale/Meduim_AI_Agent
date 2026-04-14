from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class Topic(BaseModel):
    name: str
    source: str
    trend_score: float
    novelty_score: float

class Claim(BaseModel):
    text: str
    source: str
    confidence: float

class BaseTrendTool(ABC):
    @abstractmethod
    async def fetch_topics(self) -> List[Topic]:
        pass

class BaseResearchTool(ABC):
    @abstractmethod
    async def fetch(self, query: str) -> List[Claim]:
        pass

class BaseMemoryTool(ABC):
    @abstractmethod
    async def get_failed_topics(self) -> List[str]:
        pass
    
    @abstractmethod
    async def save_run(self, topic: str, status: str, feedback: str) -> bool:
        pass
