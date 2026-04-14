import numpy as np
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.services.interfaces import Topic
import logging

logger = logging.getLogger(__name__)

def compute_clustering(topics: List[Topic], similarity_threshold: float = 0.6) -> List[Dict[str, Any]]:
    """CPU-intensive clustering using TF-IDF and Cosine Similarity."""
    if not topics:
        return []
        
    names = [t.name for t in topics]
    
    # Vectorize topic names
    vectorizer = TfidfVectorizer(stop_words='english')
    try:
        tfidf_matrix = vectorizer.fit_transform(names)
    except ValueError:
        # Fallback if vocabulary is empty
        return [{"topic": t.name, "score": t.trend_score, "sources": [t.source]} for t in topics]
        
    cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)
    
    visited = set()
    clusters = []
    
    for i in range(len(topics)):
        if i in visited:
            continue
            
        visited.add(i)
        
        # Start a new cluster
        current_cluster = {
            "topic": topics[i].name,
            "sources": [topics[i].source],
            "score": topics[i].trend_score,
            "novelty_sum": topics[i].novelty_score,
            "count": 1
        }
        
        # Find similar topics
        for j in range(i + 1, len(topics)):
            if j not in visited and cosine_sim[i][j] >= similarity_threshold:
                visited.add(j)
                current_cluster["sources"].append(topics[j].source)
                current_cluster["score"] += topics[j].trend_score
                current_cluster["novelty_sum"] += topics[j].novelty_score
                current_cluster["count"] += 1
                
                # Keep the shortest/cleanest name for the cluster core
                if len(topics[j].name) < len(current_cluster["topic"]):
                    current_cluster["topic"] = topics[j].name
                    
        clusters.append(current_cluster)
        
    return clusters

def compute_ranking(clustered: List[Dict[str, Any]], memory_failed: List[str]) -> Dict[str, Any]:
    """Scores based on TF-IDF clusters, filtering out past memory failures."""
    valid_topics = [c for c in clustered if c["topic"] not in memory_failed]
    if not valid_topics:
        return {}
    
    # Advanced logic: Weight sum by diversity of sources and average novelty
    for t in valid_topics:
        unique_sources = len(set(t["sources"]))
        avg_novelty = t["novelty_sum"] / t["count"]
        # Boost score if multiple platforms are talking about it
        t["final_score"] = (t["score"] * 0.6) + (unique_sources * 0.2) + (avg_novelty * 0.2)
        
    # Sort by the heuristically computed final score
    valid_topics.sort(key=lambda x: x["final_score"], reverse=True)
    best = valid_topics[0]
    
    return {
        "selected_topic": best["topic"],
        "reason": f"Top heuristic ranking ({best['final_score']:.2f}) across {len(set(best['sources']))} unique platforms.",
        "score": best["final_score"],
        "raw_cluster": best
    }

def compute_review_heuristics(draft: Dict[str, Any]) -> Dict[str, Any]:
    """CPU rules-based review prior to LLM."""
    content = draft.get("optimized_content", "")
    words = content.split()
    
    if len(words) < 200:
        return {"status": "reject", "feedback": "Content is suspiciously short. Must be at least 200 words.", "pass_heuristics": False}
        
    return {"pass_heuristics": True}

