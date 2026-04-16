import numpy as np
import math
from typing import List, Dict, Any
from datetime import datetime, timezone
from sklearn.cluster import AgglomerativeClustering
from app.services.interfaces import Topic
import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
# Lazy-loaded sentence-transformer model (loaded once)
# PDF Step 1: "Use sentence embeddings" with all-MiniLM-L6-v2
# ──────────────────────────────────────────────────────
_embedding_model = None

def _get_embedding_model():
    """Lazy-load the SentenceTransformer to avoid import-time GPU/CPU overhead."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Loaded sentence-transformers model: all-MiniLM-L6-v2")
    return _embedding_model


# ──────────────────────────────────────────────────────
# PDF Source Weights — different signals carry different weight
# ──────────────────────────────────────────────────────
SOURCE_WEIGHTS: Dict[str, float] = {
    "arxiv": 1.2,
    "github": 1.0,
    "hn": 1.1,
    "reddit": 0.8,
}


def _compute_time_decay(timestamp_str: str, half_life_hours: float = 72.0) -> float:
    """
    PDF Step 1 Advanced: Time Decay — recent data matters more.
    Uses exponential decay: score *= exp(-lambda * time_delta_hours)
    A half-life of 72h means a 3-day-old signal is worth ~50% of a fresh one.
    """
    if not timestamp_str:
        return 0.5  # Unknown timestamp gets a neutral decay

    try:
        # Handle various ISO formats
        ts = timestamp_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta_hours = max((now - dt).total_seconds() / 3600.0, 0.0)
        decay_lambda = math.log(2) / half_life_hours
        return math.exp(-decay_lambda * delta_hours)
    except (ValueError, TypeError):
        return 0.5


def compute_clustering(topics: List[Topic], distance_threshold: float = 0.3) -> List[Dict[str, Any]]:
    """
    PDF Step 1 — Full clustering pipeline:
    1. Sentence embeddings (all-MiniLM-L6-v2) on "name + description"
    2. AgglomerativeClustering with cosine metric + average linkage
    3. Cluster naming via most descriptive item
    4. Per-cluster scoring: trend + source_diversity + novelty + recency (time decay)
    5. Source weighting applied per item

    Args:
        topics: List of normalized Topic objects from multi-source discovery.
        distance_threshold: Cosine distance threshold for AgglomerativeClustering.
                            0.3 = relatively tight clusters (PDF recommended).
    Returns:
        List of cluster dicts sorted by final_score descending.
    """
    if not topics:
        return []

    if len(topics) == 1:
        t = topics[0]
        sw = SOURCE_WEIGHTS.get(t.source, 1.0)
        td = _compute_time_decay(t.timestamp)
        return [{
            "topic": t.name,
            "sources": [t.source],
            "items": [{"name": t.name, "source": t.source}],
            "trend_score": t.trend_score * sw,
            "source_diversity": 1,
            "novelty_avg": t.novelty_score,
            "recency": td,
            "count": 1,
            "final_score": t.trend_score * sw * td,
        }]

    # ── Step 1: Generate sentence embeddings ──
    model = _get_embedding_model()
    # PDF: "texts = [t['title'] + ' ' + t['description'] for t in data]"
    texts = [f"{t.name} {t.description}".strip() for t in topics]
    # PDF: "normalize_embeddings=True" — important for cosine metric
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    # ── Step 2: AgglomerativeClustering ──
    # PDF: AgglomerativeClustering(n_clusters=None, metric="cosine",
    #       linkage="average", distance_threshold=0.3)
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )
    labels = clustering.fit_predict(embeddings)

    # ── Step 3: Build cluster objects ──
    cluster_map: Dict[int, List[int]] = {}
    for idx, label in enumerate(labels):
        cluster_map.setdefault(label, []).append(idx)

    clusters: List[Dict[str, Any]] = []
    for label, indices in cluster_map.items():
        cluster_topics = [topics[i] for i in indices]

        # ── Step 4: Cluster naming — pick the item with longest description (most representative) ──
        # PDF: "cluster_name = max(cluster_items, key=lambda x: len(x['description']))"
        representative = max(cluster_topics, key=lambda t: len(t.description))

        # ── Source weighting & time decay per item ──
        weighted_trend = sum(
            t.trend_score * SOURCE_WEIGHTS.get(t.source, 1.0)
            for t in cluster_topics
        )
        novelty_avg = sum(t.novelty_score for t in cluster_topics) / len(cluster_topics)
        recency_avg = sum(_compute_time_decay(t.timestamp) for t in cluster_topics) / len(cluster_topics)
        unique_sources = list(set(t.source for t in cluster_topics))
        source_diversity = len(unique_sources)

        # ── Step 5: Final score — exact PDF formula ──
        # score = w1*trend_score + w2*source_diversity + w3*novelty + w4*recency
        final_score = (
            0.35 * weighted_trend +
            0.25 * source_diversity +
            0.20 * novelty_avg +
            0.20 * recency_avg
        )

        clusters.append({
            "topic": representative.name,
            "sources": [t.source for t in cluster_topics],
            "items": [{"name": t.name, "source": t.source} for t in cluster_topics],
            "trend_score": weighted_trend,
            "source_diversity": source_diversity,
            "novelty_avg": novelty_avg,
            "recency": recency_avg,
            "count": len(cluster_topics),
            "final_score": final_score,
        })

    # Sort by final_score descending
    clusters.sort(key=lambda c: c["final_score"], reverse=True)
    return clusters


def compute_ranking(clustered: List[Dict[str, Any]], memory_failed: List[str]) -> Dict[str, Any]:
    """
    PDF Step 3 — Ranking / Decision Engine:
    1. Filter out past memory failures (novelty penalty from Memory Agent).
    2. Compute final score using exact PDF weights:
       score = 0.25*trend + 0.20*query_score + 0.15*source_score +
               0.15*novelty + 0.15*content_score + 0.10*competition_score
       (query_score and content_score/competition_score are not available yet at
        this stage, so we use the cluster's pre-computed score and source_diversity.)
    3. Confidence = gap between top two scores.
    4. Fallback: If confidence < threshold or max_score is too low → NO_DECISION.
    """
    valid_topics = [c for c in clustered if c["topic"] not in memory_failed]
    if not valid_topics:
        return {"selected_topic": "", "status": "NO_DECISION", "reason": "All candidate topics were previously failed."}

    # Re-score using available features (pre-query-expansion ranking)
    for t in valid_topics:
        unique_sources = t.get("source_diversity", len(set(t["sources"])))
        avg_novelty = t.get("novelty_avg", t.get("novelty_sum", 0) / max(t.get("count", 1), 1))
        recency = t.get("recency", 0.5)

        # Weighted composite (adapted from PDF; query/content/competition not yet available)
        t["final_score"] = (
            0.35 * t.get("trend_score", t.get("score", 0)) +
            0.25 * unique_sources +
            0.20 * avg_novelty +
            0.20 * recency
        )

    valid_topics.sort(key=lambda x: x["final_score"], reverse=True)

    best = valid_topics[0]
    second_score = valid_topics[1]["final_score"] if len(valid_topics) > 1 else 0.0

    # PDF Step 3: Confidence = top_score - second_score
    confidence = best["final_score"] - second_score

    # PDF Step 3: Fallback — if confidence < threshold → NO_DECISION
    MIN_CONFIDENCE = 0.05
    MIN_ABSOLUTE_SCORE = 0.3

    if best["final_score"] < MIN_ABSOLUTE_SCORE:
        return {
            "selected_topic": "",
            "status": "NO_DECISION",
            "reason": f"Best topic score ({best['final_score']:.2f}) is below minimum threshold ({MIN_ABSOLUTE_SCORE}).",
            "score": best["final_score"],
            "confidence": confidence,
            "alternatives": [t["topic"] for t in valid_topics[:3]],
        }

    if confidence < MIN_CONFIDENCE and len(valid_topics) > 1:
        return {
            "selected_topic": "",
            "status": "NO_DECISION",
            "reason": f"Confidence gap too small ({confidence:.3f}). Risk of picking wrong topic.",
            "score": best["final_score"],
            "confidence": confidence,
            "alternatives": [t["topic"] for t in valid_topics[:3]],
        }

    return {
        "selected_topic": best["topic"],
        "status": "DECIDED",
        "reason": f"Top ranking ({best['final_score']:.2f}), confidence gap {confidence:.3f}, across {len(set(best['sources']))} sources.",
        "score": best["final_score"],
        "confidence": confidence,
        "alternatives": [t["topic"] for t in valid_topics[1:4]],
        "raw_cluster": best,
    }


def compute_review_heuristics(draft: Dict[str, Any]) -> Dict[str, Any]:
    """
    CPU rules-based review prior to LLM.
    PDF Step 10: Local heuristic checks — repetition, sentence quality, missing sections, length.
    """
    content = draft.get("optimized_content", "")
    words = content.split()
    feedback_items = []

    # Length check
    if len(words) < 200:
        feedback_items.append("Content is suspiciously short. Must be at least 200 words.")

    # Repetition detection — flag if any sentence appears more than once
    sentences = [s.strip() for s in content.split('.') if s.strip()]
    seen = set()
    for s in sentences:
        normalized = s.lower().strip()
        if normalized in seen and len(normalized) > 20:
            feedback_items.append(f"Repeated sentence detected: '{s[:60]}...'")
        seen.add(normalized)

    # Banned phrases (PDF: avoid "In this article", "Let us explore", etc.)
    BANNED_PHRASES = [
        "in this article", "let us explore", "let's explore",
        "delve into", "in conclusion", "it is worth noting",
    ]
    content_lower = content.lower()
    for phrase in BANNED_PHRASES:
        if phrase in content_lower:
            feedback_items.append(f"Banned robotic phrase detected: '{phrase}'")

    if feedback_items:
        return {
            "status": "revise",
            "feedback": " | ".join(feedback_items),
            "pass_heuristics": False,
        }

    return {"pass_heuristics": True}
