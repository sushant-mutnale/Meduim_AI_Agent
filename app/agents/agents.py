import json
from datetime import datetime
from app.utils.llm import run_llm, generate_structured_response

class TopicDiscoveryAgent:
    def discover(self):
        # In a real app, hit Reddit, Google News, ArXiv APIs here.
        # Fallback to LLM generating trend predictions if no internet
        prompt = """Identify 5 emerging, high-opportunity topics in AI, ML, or Computer Science.
Return as JSON with a list of "topics", each with "query" and "cluster_name"."""
        resp = generate_structured_response("You are a technical trend analyst.", prompt)
        data = json.loads(resp)
        return data.get("topics", [])

class RankingAgent:
    def rank(self, topics):
        prompt = f"""Score these topics on momentum, relevance, and competition from 0.0 to 1.0.
Pick the best one and explain why. Topics: {json.dumps(topics)}
Format as JSON with "best_topic" and "reason"."""
        resp = generate_structured_response("You are an SEO optimization agent.", prompt)
        return json.loads(resp)

class ResearchAgent:
    def research(self, topic_query: str):
        prompt = f"Provide a comprehensive, factual summary of the latest developments regarding: {topic_query}. Include dummy URL citations as structured data."
        resp = run_llm("You are an expert researcher collecting evidence.", prompt)
        return resp

class AnalysisAgent:
    def analyze(self, research_data: str):
        prompt = f"Find patterns, caveats, and core insights from this raw research:\n{research_data}"
        resp = run_llm("You are a data analyst.", prompt)
        return resp

class OutlineAgent:
    def create_outline(self, analysis: str):
        prompt = f"Create a structured Markdown outline optimized for Medium regarding these insights:\n{analysis}"
        resp = run_llm("You are a technical editor.", prompt)
        return resp

class WritingAgent:
    def draft_article(self, outline: str, research: str):
        sys = "You are a professional technical writer on Medium. Write clear, engaging, and accurate content without fluff."
        prompt = f"Write the full article using this outline:\n{outline}\n\nEvidence:\n{research}"
        resp = run_llm(sys, prompt, temperature=0.5) # Lower temp for factual writing
        
        title_prompt = f"Generate a JSON object with 'title' and 'subtitle' for this article:\n{resp[:500]}"
        meta_resp = generate_structured_response(sys, title_prompt)
        meta = json.loads(meta_resp)
        
        return {
            "title": meta.get("title", "Generated Article"),
            "subtitle": meta.get("subtitle", "Insights into AI"),
            "body": resp
        }

class ReviewAgent:
    def review(self, draft: dict):
        sys = "You are a senior technical editor doing a factual and tone review."
        prompt = f"""Review this article and score its confidence (quality, factual consistency, lack of hallucination) from 0.0 to 1.0.
Article Title: {draft['title']}
Body: {draft['body']}

Return JSON with "confidence_score" and "review_notes" (list of strings)."""
        resp = generate_structured_response(sys, prompt)
        return json.loads(resp)
