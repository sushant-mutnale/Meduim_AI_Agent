from celery import shared_task
from app.db.session import SessionLocal
from app.db.models import RunLog
from app.jobs.graph import app_graph
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_pipeline(self):
    db = SessionLocal()
    run_log = RunLog(status="in_progress")
    db.add(run_log)
    db.commit()
    db.refresh(run_log)
    
    try:
        initial_state = {
            "timestamp": datetime.utcnow().isoformat(),
            "raw_topics": [],
            "clustered_topics": [],
            "ranking_data": {},
            "selected_topic": "",
            "queries": [],
            "arxiv_claims": [],
            "github_claims": [],
            "reddit_claims": [],
            "all_claims": [],
            "validated_claims": [],
            "insights": {},
            "outline": {},
            "visual_plan": [],
            "draft": {},
            "review_status": "in_progress",
            "revision_count": 0,
            "final_url": "",
            "abort_reason": ""
        }
        
        # Execute LangGraph natively using asyncio runner
        import asyncio
        loop = asyncio.get_event_loop()
        final_state = loop.run_until_complete(app_graph.ainvoke(initial_state))
        
        # Process the final state back to Database Log
        run_log.completed_at = datetime.utcnow()
        if final_state.get("final_url"):
            run_log.status = "published"
        else:
            run_log.status = f"aborted: {final_state.get('abort_reason', 'unknown')}"
            
        db.commit()

    except Exception as exc:
        run_log.status = "failed"
        run_log.error_message = str(exc)
        run_log.completed_at = datetime.utcnow()
        db.commit()
        raise self.retry(exc=exc)
    finally:
        db.close()
