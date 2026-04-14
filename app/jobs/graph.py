from langgraph.graph import StateGraph, END
from app.jobs.graph_nodes import (
    AgentState,
    topic_fetch_node,
    topic_cluster_node,
    ranking_node,
    query_expand_node,
    research_arxiv,
    research_github,
    research_reddit,
    merge_research,
    fact_check_node,
    insight_node,
    chart_node,
    outline_node,
    writing_node,
    review_node,
    downgrade_node,
    publish_node
)

def build_graph():
    builder = StateGraph(AgentState)
    
    # 1. Discovery Phase
    builder.add_node("TopicFetch", topic_fetch_node)
    builder.add_node("TopicCluster", topic_cluster_node)
    builder.add_node("Ranking", ranking_node)
    builder.add_node("QueryExpand", query_expand_node)
    
    # 2. Parallel Research Phase
    builder.add_node("ResearchArxiv", research_arxiv)
    builder.add_node("ResearchGithub", research_github)
    builder.add_node("ResearchReddit", research_reddit)
    builder.add_node("MergeResearch", merge_research)
    
    # 3. Validation & Structuring Phase
    builder.add_node("FactCheck", fact_check_node)
    builder.add_node("Insight", insight_node)
    builder.add_node("Outline", outline_node)
    builder.add_node("Chart", chart_node)
    
    # 4. Writing & Review Loop Phase
    builder.add_node("Writing", writing_node)
    builder.add_node("Review", review_node)
    
    # 5. Final Sub-nodes
    builder.add_node("Downgrade", downgrade_node)
    builder.add_node("Publish", publish_node)
    
    # === Edges ===
    builder.set_entry_point("TopicFetch")
    builder.add_edge("TopicFetch", "TopicCluster")
    builder.add_edge("TopicCluster", "Ranking")
    
    # Abort early conditionally if ranking fails, otherwise expand queries
    def rank_to_expand(state: AgentState):
        if not state.get("selected_topic"):
            return "Downgrade"
        return "QueryExpand"
        
    builder.add_conditional_edges("Ranking", rank_to_expand)
    
    # Fan-out to Research
    builder.add_edge("QueryExpand", "ResearchArxiv")
    builder.add_edge("QueryExpand", "ResearchGithub")
    builder.add_edge("QueryExpand", "ResearchReddit")
    
    # Fan-in to MergeResearch (Execution proceeds when all nodes routing to it complete natively in LangGraph)
    builder.add_edge(["ResearchArxiv", "ResearchGithub", "ResearchReddit"], "MergeResearch")
    
    builder.add_edge("MergeResearch", "FactCheck")
    builder.add_edge("FactCheck", "Insight")
    builder.add_edge("Insight", "Outline")
    # Chart logic executes concurrently
    builder.add_edge("Insight", "Chart")
    builder.add_edge("Chart", "Writing")
    builder.add_edge("Outline", "Writing")
    
    builder.add_edge("Writing", "Review")
    
    # The Loop logic
    def review_logic(state: AgentState):
        status = state.get("review_status", "revise")
        count = state.get("revision_count", 0)
        
        if status == "pass":
            return "Publish"
        elif count >= 3: # Max 3 tries
            return "Downgrade"
        else:
            return "Writing" # Rewrite
            
    builder.add_conditional_edges("Review", review_logic)
    
    # Completion
    builder.add_edge("Publish", END)
    builder.add_edge("Downgrade", END)
    
    return builder.compile()

app_graph = build_graph()
