import asyncio
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from typing_extensions import TypedDict
from app.utils.llm import generate_structured_response
from app.agents.cpu_tasks import compute_clustering, compute_ranking, compute_review_heuristics
from app.services.trends import GithubTrendsTool, ArxivTrendsTool, RedditTrendsTool
from app.services.research import ArxivResearchTool, GithubResearchTool, RedditResearchTool
from app.services.medium import MediumPublisher
from app.agents.visuals import ChartAgent
from app.db.session import SessionLocal
from app.db.models import MemoryLog

executor = ThreadPoolExecutor()

class AgentState(TypedDict):
    # State tracking across graph
    timestamp: str
    raw_topics: List[Any]
    clustered_topics: List[Dict[str, Any]]
    ranking_data: Dict[str, Any]
    selected_topic: str
    queries: List[Dict[str, Any]]
    
    # Parallel research
    arxiv_claims: List[Any]
    github_claims: List[Any]
    reddit_claims: List[Any]
    all_claims: List[Any]
    
    validated_claims: List[Any]
    insights: Dict[str, Any]
    outline: Dict[str, Any]
    draft: Dict[str, Any]
    
    # Control
    review_status: str
    revision_count: int
    final_url: str
    abort_reason: str

# ----------------- Discovery Layer -----------------
async def topic_fetch_node(state: AgentState):
    """Fetches topics using external MCP-like tools (Async I/O)"""
    t1, t2, t3 = await asyncio.gather(
        GithubTrendsTool().fetch_topics(),
        ArxivTrendsTool().fetch_topics(),
        RedditTrendsTool().fetch_topics()
    )
    all_raw = t1 + t2 + t3
    return {"raw_topics": all_raw}

async def topic_cluster_node(state: AgentState):
    """Clusters topics using CPU thread pool"""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, compute_clustering, state["raw_topics"])
    return {"clustered_topics": result}

async def ranking_node(state: AgentState):
    """Ranks topics utilizing DB Memory for failures and CPU pooling"""
    # Quick DB sync query for memory
    db = SessionLocal()
    failed_topics = [loc.topic_name for loc in db.query(MemoryLog).filter(MemoryLog.performance_status != "pass").all()]
    db.close()
    
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, compute_ranking, state["clustered_topics"], failed_topics)
    return {"ranking_data": result, "selected_topic": result.get("selected_topic", "")}

# ----------------- Query Expansion (PDF Step 2: Hybrid) -----------------
# Intent buckets and weights from the PDF
INTENT_WEIGHTS = {
    "problem": 1.3,
    "comparison": 1.2,
    "beginner": 1.1,
    "trend": 1.0,
    "intermediate": 1.0,
    "advanced": 0.9,
}

# Keywords that boost query quality (PDF Step 2: keyword strength)
STRONG_KEYWORDS = {"how to", "what is", "vs", "best", "why", "guide", "tutorial", "example"}


def _filter_queries(queries: list) -> list:
    """
    PDF Step 2 — Rule-based local filtering:
    - Max 10 words per query
    - No question marks
    - No near-duplicate queries (simple lowered check)
    """
    seen = set()
    filtered = []
    for q in queries:
        text = q.get("query", "")
        normalized = text.lower().strip()

        if len(text.split()) > 10:
            continue
        if "?" in text:
            continue
        if normalized in seen:
            continue

        seen.add(normalized)
        filtered.append(q)
    return filtered


def _score_queries(queries: list) -> list:
    """
    PDF Step 2 — Local scoring formula:
    score = 0.4 * simplicity + 0.3 * intent_weight + 0.3 * keyword_strength
    """
    scored = []
    for q in queries:
        text = q.get("query", "")
        intent = q.get("intent", "beginner")

        # Simplicity: shorter is better (inverse of word count)
        simplicity = 1.0 / max(len(text.split()), 1)

        # Intent weight from PDF table
        intent_weight = INTENT_WEIGHTS.get(intent, 1.0)

        # Keyword strength: check if any strong keyword pattern is present
        text_lower = text.lower()
        keyword_hits = sum(1 for kw in STRONG_KEYWORDS if kw in text_lower)
        keyword_strength = min(keyword_hits / 3.0, 1.0)  # Normalize to 0-1

        final_score = (0.4 * simplicity) + (0.3 * intent_weight) + (0.3 * keyword_strength)

        scored.append({
            "query": text,
            "intent": intent,
            "score": round(final_score, 4),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


async def query_expand_node(state: AgentState):
    """
    PDF Step 2 — Hybrid Query Expansion:
    1. LLM generates 3-5 queries per intent bucket (beginner, intermediate,
       advanced, comparison, problem, trend).
    2. Local rule-based filtering removes noisy/duplicate/long queries.
    3. Local scoring ranks remaining queries by simplicity + intent weight + keyword strength.
    """
    if not state.get("selected_topic"):
        return {"abort_reason": "No valid topic found"}

    sys_prompt = "You are an elite SEO strategist and search intent analyst."
    prompt = f"""
    Topic: '{state['selected_topic']}'

    Generate search queries for EACH of these intent categories:
    - beginner (e.g., "what is X")
    - intermediate (e.g., "how X works")
    - advanced (e.g., "X architecture deep dive")
    - comparison (e.g., "X vs Y")
    - problem (e.g., "how to build X for Y")
    - trend (e.g., "future of X")

    Rules:
    - Must sound like real Google queries
    - No long sentences
    - Max 10 words per query
    - Generate 3-5 queries per intent
    - No repetition

    Format: Output a JSON object exactly matching this structure:
    {{
        "queries": [
            {{"query": "string", "intent": "beginner|intermediate|advanced|comparison|problem|trend"}}
        ]
    }}
    """
    res = generate_structured_response(sys_prompt, prompt)
    raw_queries = res.get("queries", [])

    # PDF Step 2: Local filtering (rule-based)
    filtered = _filter_queries(raw_queries)

    # PDF Step 2: Local scoring (simplicity + intent_weight + keyword_strength)
    scored = _score_queries(filtered)

    return {"queries": scored}

# ----------------- Parallel Research -----------------
async def research_arxiv(state: AgentState):
    data = await ArxivResearchTool().fetch(state["selected_topic"])
    return {"arxiv_claims": data}

async def research_github(state: AgentState):
    data = await GithubResearchTool().fetch(state["selected_topic"])
    return {"github_claims": data}

async def research_reddit(state: AgentState):
    data = await RedditResearchTool().fetch(state["selected_topic"])
    return {"reddit_claims": data}

def merge_research(state: AgentState):
    claims = state.get("arxiv_claims", []) + state.get("github_claims", []) + state.get("reddit_claims", [])
    return {"all_claims": [c.model_dump() for c in claims]}

# ----------------- Fact & Insight -----------------
async def fact_check_node(state: AgentState):
    sys_prompt = "You are a rigorous, unbiased academic fact-checker."
    prompt = f"""
    Analyze the following research claims:
    {state.get('all_claims', [])}
    
    Task: Verify these claims for internal consistency, logical soundness, and scientific validity.
    Filter out any claims that appear contradictory, highly speculative, or lack substantive grounding.
    
    Format: Output a JSON object with:
    {{
        "validated_claims": [
            {{"text": "string", "source": "string", "confidence": float}}
        ]
    }}
    """
    res = generate_structured_response(sys_prompt, prompt)
    return {"validated_claims": res.get("validated_claims", [])}

async def insight_node(state: AgentState):
    sys_prompt = "You are a visionary Principal AI Architect and Industry Analyst."
    prompt = f"""
    Analyze the following validated claims:
    {state.get('validated_claims', [])}
    
    Task: Do not just summarize. Extract 3 deep, non-obvious insights, future implications, and potential underlying risks. 
    Look for paradigm shifts, cost/performance tradeoffs, or structural changes to the industry.
    
    Format: JSON containing:
    {{
        "insights": ["insight 1", "insight 2", "insight 3"],
        "implications": ["implication 1", "implication 2"],
        "risks": ["risk 1", "risk 2"]
    }}
    """
    res = generate_structured_response(sys_prompt, prompt)
    return {"insights": res}

# ----------------- Drafting -----------------
async def chart_node(state: AgentState):
    """CPU bound charting"""
    loop = asyncio.get_running_loop()
    # Dummy chart data since real is complex
    dummy_data = {"Metric A": 10, "Metric B": 25, "Metric C": 15}
    chart_path = await loop.run_in_executor(
        executor, ChartAgent().generate_chart, dummy_data, state["selected_topic"], "Items", "Value"
    )
    # Store path silently via side effect basically
    return {}

async def outline_node(state: AgentState):
    sys_prompt = "You are an expert technical editor for a prestigious publishing platform."
    prompt = f"""
    Develop a cohesive, engaging narrative outline using these insights:
    {state['insights']}
    
    Task: The article MUST flow logically: Hook -> Problem Statement -> Deep Dive -> Real-world Implications -> Conclusion.
    Do not use generic titles like 'Introduction' or 'Conclusion'. Use compelling, action-oriented section headers.
    
    Format: Output JSON:
    {{
        "sections": [
            {{"title": "Compelling Title", "purpose": "What this section achieves and what facts to include"}}
        ]
    }}
    """
    res = generate_structured_response(sys_prompt, prompt)
    return {"outline": res}

async def writing_node(state: AgentState):
    sys_prompt = "You are a Staff Engineer and top-tier Technical Writer on Medium."
    prompt = f"""
    Draft a final, publication-ready article.
    
    Topic: {state['selected_topic']}
    Outline Directives: {state['outline']}
    Key Insights to embed naturally: {state['insights']}
    Editor Feedback (if revising): {state.get('abort_reason', 'None')}
    
    Rules:
    1. Tone must be authoritative, clear, and human strictly devoid of robotic cliches (e.g., 'In conclusion', 'Delve into').
    2. Zero fluff. Maximize signal-to-noise ratio. Emphasize the 'Why' and the 'How'.
    3. Include bullet points or bolding for readability where appropriate.
    4. Provide an SEO-optimized Hook/Title.
    
    Format: Output JSON:
    {{
        "title": "A highly clickable, SEO-friendly title",
        "optimized_content": "The full markdown formatted body content"
    }}
    """
    res = generate_structured_response(sys_prompt, prompt)
    return {"draft": res}

# ----------------- Review & Publish -----------------
async def review_node(state: AgentState):
    """Hybrid Review: Local Heuristics -> LLM semantic check"""
    draft = state.get("draft", {})
    
    loop = asyncio.get_running_loop()
    h_result = await loop.run_in_executor(executor, compute_review_heuristics, draft)
    
    if not h_result["pass_heuristics"]:
        return {
            "review_status": "revise", 
            "abort_reason": h_result["feedback"], 
            "revision_count": state.get("revision_count", 0) + 1
        }
        
    # Pass heuristics, run LLM
    sys_prompt = "You are a strict, merciless Editorial Reviewer and Quality Gatekeeper."
    prompt = f"""
    Rate this drafted article strictly out of 1.0. 
    
    Draft content:
    {draft.get('optimized_content', 'No content')}
    
    Critique criteria:
    - Flow and Readability (Is it engaging?)
    - Technical Depth (Is it surface-level fluff?)
    - Hallucination (Are there unsupported claims disguised as facts?)
    
    If the content sounds like a generic AI response, penalize it heavily (<0.6).
    
    Format: JSON strictly:
    {{
        "score": float (0.0 to 1.0),
        "feedback": "Actionable feedback detailing exactly which paragraphs need rewriting and why."
    }}
    """
    res = generate_structured_response(sys_prompt, prompt)
    
    score = res.get("score", 0.0)
    if score >= 0.8:
        return {"review_status": "pass"}
    else:
        return {
            "review_status": "revise",
            "abort_reason": res.get("feedback"),
            "revision_count": state.get("revision_count", 0) + 1
        }

async def downgrade_node(state: AgentState):
    """Fallback node if revisions exceeded"""
    return {"abort_reason": "Max revisions exceeded. Downgraded to manual review."}

async def publish_node(state: AgentState):
    draft = state.get("draft", {})
    publisher = MediumPublisher()
    try:
        resp = publisher.publish(draft.get("title", "No Title"), draft.get("optimized_content", ""))
        return {"final_url": resp.get("data", {}).get("url")}
    except Exception as e:
        return {"abort_reason": f"Publish error: {str(e)}"}
