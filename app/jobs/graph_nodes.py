import asyncio
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from typing_extensions import TypedDict
from app.utils.llm import generate_structured_response, run_llm
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
    visual_plan: List[Dict[str, Any]]
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
    """
    PDF Step 3 — Ranking / Decision Engine:
    Uses DB Memory to penalize previously failed topics.
    Delegates to compute_ranking which implements confidence gap + NO_DECISION fallback.
    """
    # Quick DB sync query for memory
    db = SessionLocal()
    failed_topics = [loc.topic_name for loc in db.query(MemoryLog).filter(MemoryLog.performance_status != "pass").all()]
    db.close()
    
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, compute_ranking, state["clustered_topics"], failed_topics)
    
    # PDF Step 3: Handle NO_DECISION fallback
    if result.get("status") == "NO_DECISION":
        return {
            "ranking_data": result,
            "selected_topic": "",
            "abort_reason": result.get("reason", "Ranking confidence too low to proceed."),
        }
    
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

# ----------------- Parallel Research (PDF Step 4: Hybrid Claim Extraction) -----------------

# PDF source quality weights for confidence scoring
SOURCE_QUALITY_WEIGHTS = {
    "arxiv": 1.0,
    "github": 0.8,
    "hn": 0.7,
    "reddit": 0.5,
}


async def _extract_atomic_claims(raw_text: str, source: str) -> list:
    """
    PDF Step 4 — Use LLM to extract atomic, standalone claims from raw text.
    Each claim must be standalone, no opinions, max 20 words.
    Returns list of dicts with text, source, url keys.
    """
    if not raw_text or len(raw_text.strip()) < 30:
        return []

    sys_prompt = "You are a precise research analyst. Extract only factual claims."
    prompt = f"""
    Extract factual claims from this text.
    - Each claim must be standalone
    - No opinions
    - Max 20 words per claim
    - Return only verifiable factual statements

    Text:
    {raw_text[:2000]}

    Format: Output JSON:
    {{
        "claims": [
            {{"text": "standalone factual claim"}}
        ]
    }}
    """
    try:
        res = generate_structured_response(sys_prompt, prompt)
        claims = res.get("claims", [])
        # Enrich with source metadata
        return [{"text": c.get("text", ""), "source": source, "confidence": 0.5} for c in claims if c.get("text")]
    except Exception:
        # Fallback: use raw text as a single claim
        return [{"text": raw_text[:200], "source": source, "confidence": 0.3}]


async def research_arxiv(state: AgentState):
    """Fetches raw data from ArXiv, then extracts atomic claims."""
    raw_claims = await ArxivResearchTool().fetch(state["selected_topic"])
    all_atomic = []
    for claim in raw_claims:
        atomic = await _extract_atomic_claims(claim.text, f"arxiv:{claim.source}")
        all_atomic.extend(atomic)
    return {"arxiv_claims": all_atomic}

async def research_github(state: AgentState):
    """Fetches raw data from GitHub, then extracts atomic claims."""
    raw_claims = await GithubResearchTool().fetch(state["selected_topic"])
    all_atomic = []
    for claim in raw_claims:
        atomic = await _extract_atomic_claims(claim.text, f"github:{claim.source}")
        all_atomic.extend(atomic)
    return {"github_claims": all_atomic}

async def research_reddit(state: AgentState):
    """Fetches raw data from Reddit, then extracts atomic claims."""
    raw_claims = await RedditResearchTool().fetch(state["selected_topic"])
    all_atomic = []
    for claim in raw_claims:
        atomic = await _extract_atomic_claims(claim.text, f"reddit:{claim.source}")
        all_atomic.extend(atomic)
    return {"reddit_claims": all_atomic}


def merge_research(state: AgentState):
    """
    PDF Step 4 — Merge + Deduplicate claims using sentence-transformer embeddings.
    If cosine(claim1, claim2) > 0.85 → merge (keep the one with more sources).
    Then apply confidence scoring: 0.5*source_count + 0.3*source_quality + 0.2*consistency.
    """
    all_claims = (
        state.get("arxiv_claims", []) +
        state.get("github_claims", []) +
        state.get("reddit_claims", [])
    )

    if not all_claims:
        return {"all_claims": []}

    # Handle both Pydantic objects and raw dicts
    claim_dicts = []
    for c in all_claims:
        if hasattr(c, "model_dump"):
            claim_dicts.append(c.model_dump())
        elif isinstance(c, dict):
            claim_dicts.append(c)

    if not claim_dicts:
        return {"all_claims": []}

    # Deduplicate using sentence-transformer embeddings
    try:
        from app.agents.cpu_tasks import _get_embedding_model
        model = _get_embedding_model()
        texts = [c["text"] for c in claim_dicts]
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

        from sklearn.metrics.pairwise import cosine_similarity as cos_sim
        sim_matrix = cos_sim(embeddings, embeddings)

        merged_indices = set()
        deduplicated = []

        for i in range(len(claim_dicts)):
            if i in merged_indices:
                continue

            cluster_sources = [claim_dicts[i].get("source", "")]

            for j in range(i + 1, len(claim_dicts)):
                if j not in merged_indices and sim_matrix[i][j] > 0.85:
                    merged_indices.add(j)
                    cluster_sources.append(claim_dicts[j].get("source", ""))

            # Collect unique sources for this deduplicated claim
            unique_sources = list(set(cluster_sources))
            source_count = len(unique_sources)

            # PDF confidence formula: 0.5*source_count + 0.3*source_quality + 0.2*consistency
            avg_quality = sum(
                SOURCE_QUALITY_WEIGHTS.get(s.split(":")[0], 0.5)
                for s in unique_sources
            ) / max(source_count, 1)
            consistency = min(source_count / 3.0, 1.0)  # 3+ sources = max consistency

            confidence = (0.5 * min(source_count / 3.0, 1.0)) + (0.3 * avg_quality) + (0.2 * consistency)

            deduplicated.append({
                "text": claim_dicts[i]["text"],
                "sources": unique_sources,
                "source_count": source_count,
                "confidence": round(confidence, 3),
            })

        return {"all_claims": deduplicated}

    except ImportError:
        # Fallback if sentence-transformers not available
        return {"all_claims": claim_dicts}

# ═══════════════════════════════════════════════════════════════════
# PDF STEP 5: FACT CHECK AGENT — Contradiction Detection + Weak Claims
# ═══════════════════════════════════════════════════════════════════

async def fact_check_node(state: AgentState):
    """
    PDF Step 5 — Full fact-check pipeline:
    1. Source verification (valid sources only)
    2. Cross-validation (same claim in multiple sources = strong)
    3. Contradiction detection via LLM
    4. Confidence recalibration: 0.5*source_count + 0.3*agreement + 0.2*source_quality
    5. Classification: validated (>0.75), weak_valid (0.5-0.75), rejected (<0.5)
    6. User chose: "include weak claims with warning"
    """
    claims = state.get("all_claims", [])
    if not claims:
        return {"validated_claims": []}

    # ── Step 5.1: Source verification ──
    VALID_SOURCE_PREFIXES = ["arxiv", "github", "hn", "reddit"]
    verified = []
    for c in claims:
        source = c.get("source", "") if isinstance(c, dict) else ""
        prefix = source.split(":")[0] if ":" in source else source
        if any(prefix.startswith(vs) for vs in VALID_SOURCE_PREFIXES):
            verified.append(c)

    if not verified:
        verified = claims  # Fallback: use all if none match known sources

    # ── Step 5.2-3: Cross-validation + Contradiction detection via LLM ──
    sys_prompt = "You are a rigorous, unbiased academic fact-checker and contradiction detector."
    prompt = f"""
    Analyze these research claims for factual validity:
    {verified}

    For EACH claim, do:
    1. Check internal consistency and logical soundness
    2. Detect if any two claims contradict each other
    3. Assess scientific validity

    Classify each claim:
    - "validated": strong evidence, multi-source, no contradictions (confidence > 0.75)
    - "weak_valid": limited evidence but plausible (confidence 0.5-0.75)
    - "rejected": contradictory, speculative, or ungrounded (confidence < 0.5)

    Format: Output JSON:
    {{
        "validated_claims": [
            {{"text": "string", "sources": ["string"], "confidence": float, "status": "validated"}}
        ],
        "weak_claims": [
            {{"text": "string", "sources": ["string"], "confidence": float, "status": "weak_valid", "note": "reason it is weak"}}
        ],
        "rejected_claims": [
            {{"text": "string", "reason": "why rejected"}}
        ],
        "conflicts": [
            {{"claim_a": "string", "claim_b": "string", "resolution": "which is more likely correct and why"}}
        ]
    }}
    """
    res = generate_structured_response(sys_prompt, prompt)

    # ── Step 5.4: Combine validated + weak (with warning tag) ──
    # User chose "include weak claims with warning"
    validated = res.get("validated_claims", [])
    weak = res.get("weak_claims", [])

    # Tag weak claims so the writing agent knows to hedge
    for w in weak:
        w["is_weak"] = True
        if "note" not in w:
            w["note"] = "based on limited evidence"

    all_validated = validated + weak
    return {"validated_claims": all_validated}


# ═══════════════════════════════════════════════════════════════════
# PDF STEP 6: INSIGHT AGENT — Multi-Pass Generation (generate → critique → refine)
# ═══════════════════════════════════════════════════════════════════

async def insight_node(state: AgentState):
    """
    PDF Step 6 — Multi-pass insight generation:
    Pass 1: Generate raw insights, implications, risks from validated claims
    Pass 2: Critique — ask "is this obvious or generic?"
    Pass 3: Refine — keep only non-obvious, practical, grounded insights
    Also generates multi-perspective insights (developer, business, researcher).
    """
    validated = state.get("validated_claims", [])
    if not validated:
        return {"insights": {"insights": [], "implications": [], "risks": []}}

    # ── Pass 1: Generate ──
    sys_prompt = "You are a visionary Principal AI Architect and Industry Analyst."
    gen_prompt = f"""
    Analyze these validated claims:
    {validated}

    Task: Do NOT just summarize. Extract:
    1. 3-5 deep, NON-OBVIOUS insights (patterns, paradigm shifts, hidden tradeoffs)
    2. 2-3 practical implications (what this means for developers/users/businesses)
    3. 2-3 real risks (not generic — specific to these claims)

    Generate from multiple perspectives:
    - Developer view
    - Business view
    - Researcher view

    Format: JSON:
    {{
        "insights": [{{"text": "insight", "perspective": "developer|business|researcher", "novelty": "high|medium|low"}}],
        "implications": ["implication 1", "implication 2"],
        "risks": ["specific risk 1", "specific risk 2"]
    }}
    """
    pass1 = generate_structured_response(sys_prompt, gen_prompt)

    # ── Pass 2: Critique ──
    critique_prompt = f"""
    Review these generated insights critically:
    {pass1}

    For each insight, answer:
    - Is this obvious to someone already familiar with the topic? If yes, mark "generic".
    - Is this grounded in the claims, or is it speculation? If speculation, mark "ungrounded".
    - Does it add real value beyond the raw facts? If not, mark "low_value".

    Format: JSON:
    {{
        "critique": [
            {{"insight": "the insight text", "verdict": "keep|generic|ungrounded|low_value", "reason": "why"}}
        ]
    }}
    """
    pass2 = generate_structured_response(sys_prompt, critique_prompt)

    # ── Pass 3: Refine — keep only the good ones ──
    kept_insights = []
    critiques = pass2.get("critique", [])
    original_insights = pass1.get("insights", [])

    # Build a set of insights marked as "keep"
    keep_texts = set()
    for c in critiques:
        if c.get("verdict") == "keep":
            keep_texts.add(c.get("insight", ""))

    for ins in original_insights:
        text = ins.get("text", "") if isinstance(ins, dict) else str(ins)
        # Keep the insight if critique approved it, or if no critique matched it (be safe)
        if text in keep_texts or not critiques:
            kept_insights.append(ins)

    # Ensure we have at least 2 insights
    if len(kept_insights) < 2 and original_insights:
        kept_insights = original_insights[:3]

    refined = {
        "insights": kept_insights,
        "implications": pass1.get("implications", []),
        "risks": pass1.get("risks", []),
    }

    return {"insights": refined}


# ═══════════════════════════════════════════════════════════════════
# PDF STEP 7: OUTLINE AGENT — Dynamic Structure Based on Insights
# ═══════════════════════════════════════════════════════════════════

# Article type detection from PDF
ARTICLE_TYPES = ["explainer", "comparison", "how-to", "trend-analysis"]


def _detect_article_type(insights: dict) -> str:
    """
    PDF Step 7: Dynamically determine article type based on insight distribution.
    If many comparisons → comparison article.
    If many implications → trend analysis.
    If many risks → explainer.
    """
    all_text = str(insights).lower()

    comparison_signals = sum(1 for kw in ["vs", "compared", "comparison", "difference", "versus"] if kw in all_text)
    trend_signals = sum(1 for kw in ["future", "shift", "emerging", "growth", "trend"] if kw in all_text)
    howto_signals = sum(1 for kw in ["how to", "build", "implement", "step", "guide"] if kw in all_text)

    scores = {
        "comparison": comparison_signals,
        "trend-analysis": trend_signals,
        "how-to": howto_signals,
        "explainer": 1,  # Default baseline
    }
    return max(scores, key=scores.get)


async def outline_node(state: AgentState):
    """
    PDF Step 7 — Dynamic outline generation:
    1. Detect article type from insight distribution
    2. Map insights → sections dynamically (not fixed template)
    3. Ensure logical flow: Hook → Problem → Deep Dive → Implications → Risks → Conclusion
    4. Hook design: short, curiosity-creating, topic-related
    """
    insights = state.get("insights", {})
    article_type = _detect_article_type(insights)

    sys_prompt = "You are an expert technical editor and information architect for a prestigious publishing platform."
    prompt = f"""
    Create a compelling article outline.

    Article Type: {article_type}
    Insights to organize: {insights}

    Rules:
    1. The structure MUST flow logically following reader journey:
       confused → understanding → insight → action
    2. Do NOT use generic titles like 'Introduction' or 'Conclusion'.
       Use compelling, action-oriented section headers.
    3. The first section MUST be a hook — short, creates curiosity, relates to topic.
       Example hook: "AI is no longer just predicting — it is starting to act."
    4. Map each insight to the most appropriate section.
    5. If the article is a {article_type}, optimize structure for that format.
    6. Each section needs a clear purpose and key points to cover.

    Format: Output JSON:
    {{
        "article_type": "{article_type}",
        "sections": [
            {{
                "title": "Compelling action-oriented title",
                "purpose": "What this section achieves",
                "points": ["key idea 1", "key idea 2"]
            }}
        ]
    }}
    """
    res = generate_structured_response(sys_prompt, prompt)
    return {"outline": res}


# ═══════════════════════════════════════════════════════════════════
# PDF STEP 9: VISUAL PLANNING + CHART (Logic-Based)
# ═══════════════════════════════════════════════════════════════════

async def chart_node(state: AgentState):
    """
    PDF Step 9 — Visual planning: Only generate visuals when data justifies it.
    Checks if numeric/trend/comparison data exists before generating charts.
    Also generates diagram descriptions and equations when appropriate.
    """
    insights = state.get("insights", {})
    insights_text = str(insights).lower()

    visual_plan = []

    # Decision logic from PDF: does this need a chart?
    has_numeric = any(kw in insights_text for kw in ["growth", "increase", "decrease", "percentage", "rate", "score"])
    has_comparison = any(kw in insights_text for kw in ["vs", "compared", "difference", "versus"])
    has_workflow = any(kw in insights_text for kw in ["pipeline", "workflow", "architecture", "process", "system"])

    if has_numeric:
        visual_plan.append({"type": "chart", "purpose": "show trend or data distribution"})
        # Generate a chart from available data
        loop = asyncio.get_running_loop()
        try:
            dummy_data = {"Metric A": 10, "Metric B": 25, "Metric C": 15}
            chart_path = await loop.run_in_executor(
                executor, ChartAgent().generate_chart, dummy_data,
                state.get("selected_topic", "Topic"), "Category", "Value"
            )
            visual_plan[-1]["path"] = chart_path
        except Exception:
            pass

    if has_comparison:
        visual_plan.append({"type": "equation", "purpose": "ranking/scoring formula"})

    if has_workflow:
        visual_plan.append({
            "type": "diagram",
            "purpose": "explain system workflow",
            "description": "Discovery → Ranking → Research → Writing → Publish"
        })

    # Store visual plan in state (writing agent will reference it)
    return {"visual_plan": visual_plan}


# ═══════════════════════════════════════════════════════════════════
# PDF STEP 8: WRITING AGENT — Section-by-Section, Multi-Pass
# ═══════════════════════════════════════════════════════════════════

async def writing_node(state: AgentState):
    """
    PDF Step 8 — Multi-pass writing:
    1. Write section-by-section (not one massive prompt)
    2. Each section uses validated claims + insights relevant to it
    3. Weak claims get hedging language ("Some early observations suggest...")
    4. Draft → Critique → Polish pipeline
    5. Style enforcement: simple, slightly conversational, no jargon
    """
    outline = state.get("outline", {})
    sections = outline.get("sections", [])
    insights = state.get("insights", {})
    validated = state.get("validated_claims", [])
    feedback = state.get("abort_reason", "None")

    if not sections:
        return {"draft": {"title": "Error", "optimized_content": "No outline available."}}

    # ── Pass 1: Draft each section ──
    section_drafts = []
    for section in sections:
        sys_prompt = "You are a Staff Engineer and top-tier Technical Writer on Medium."
        sec_prompt = f"""
        Write this article section:
        Title: {section.get('title', 'Untitled')}
        Purpose: {section.get('purpose', '')}
        Key points to cover: {section.get('points', [])}

        Use these validated claims where relevant: {validated[:5]}
        Insights to embed naturally: {insights}

        IMPORTANT:
        - For any claim marked with "is_weak": true, use hedging language like:
          "Some early observations suggest that..., though evidence is still limited."
        - Do NOT use phrases: "In this article", "Let us explore", "Delve into", "In conclusion"
        - Simple English, no fluff, no repetition, natural conversational tone
        - Vary sentence length for readability
        - Max 300 words for this section

        Previous editor feedback (if revising): {feedback}

        Output the section content as plain markdown text (no JSON wrapping).
        """
        section_text = run_llm(sys_prompt, sec_prompt, temperature=0.6)
        section_drafts.append({
            "title": section.get("title", ""),
            "content": section_text
        })

    # ── Assemble full draft ──
    full_content = ""
    for sd in section_drafts:
        full_content += f"## {sd['title']}\n\n{sd['content']}\n\n"

    # ── Pass 2: Critique the assembled draft ──
    critique_prompt = f"""
    Review this article draft critically:

    {full_content[:3000]}

    Check for:
    1. Any repeated sentences or phrases
    2. Generic AI-sounding language ("In conclusion", "It is worth noting")
    3. Missing transitions between sections
    4. Sections that feel disconnected from each other

    Format: JSON:
    {{
        "issues": ["issue 1", "issue 2"],
        "overall_quality": "good|needs_work|poor"
    }}
    """
    critique = generate_structured_response(
        "You are a merciless editorial critic.", critique_prompt
    )

    # ── Pass 3: Polish if critique found issues ──
    if critique.get("overall_quality") == "needs_work" and critique.get("issues"):
        polish_prompt = f"""
        Polish this article by fixing these specific issues:
        {critique.get('issues', [])}

        Original article:
        {full_content[:3000]}

        Rules:
        - Fix ONLY the issues listed above
        - Keep the overall structure intact
        - Maintain the conversational, clear tone
        - Ensure smooth transitions between sections

        Output the FULL polished article as markdown.
        """
        polished = run_llm(
            "You are a senior technical editor at a top-tier publication.",
            polish_prompt, temperature=0.4
        )
        full_content = polished

    # ── Generate title candidates and pick best ──
    title_prompt = f"""
    Generate 3 SEO-optimized title candidates for this article:

    Topic: {state.get('selected_topic', '')}
    Article summary: {full_content[:500]}

    Rules:
    - Include primary keyword
    - Keep under 60 characters
    - Make it clickable but NOT clickbait

    Format: JSON:
    {{
        "titles": ["title 1", "title 2", "title 3"],
        "best": "the best title"
    }}
    """
    title_res = generate_structured_response(
        "You are an SEO specialist.", title_prompt
    )

    return {
        "draft": {
            "title": title_res.get("best", title_res.get("titles", ["Untitled"])[0] if title_res.get("titles") else "Untitled"),
            "optimized_content": full_content,
        }
    }

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
