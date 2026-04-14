from fastapi import FastAPI, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.db.session import get_db, engine, Base
from app.db.models import RunLog, Topic, Draft, Publication

# Create tables for demonstration (in production, use Alembic)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Content Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production specify dashboard origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Content Automation API is running"}

@app.post("/trigger-pipeline")
def trigger_pipeline(background_tasks: BackgroundTasks):
    from app.jobs.pipeline_job import run_pipeline
    # Run synchronously in background for manual trigger
    # Or dispatch to Celery
    from app.core.celery_app import celery_app
    task = celery_app.send_task("app.jobs.pipeline_job.run_pipeline")
    return {"status": "dispatched", "task_id": task.id}

@app.get("/runs")
def get_runs(db: Session = Depends(get_db)):
    return db.query(RunLog).order_by(RunLog.id.desc()).limit(10).all()

@app.get("/drafts")
def get_drafts(db: Session = Depends(get_db)):
    return db.query(Draft).order_by(Draft.id.desc()).limit(10).all()

@app.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, db: Session = Depends(get_db)):
    draft = db.query(Draft).filter(Draft.id == draft_id).first()
    if not draft:
        return {"error": "not found"}
    draft.is_approved = True
    db.commit()
    
    # Trigger publication agent
    from app.core.celery_app import celery_app
    celery_app.send_task("app.jobs.pipeline_job.publish_draft", args=[draft_id])
    
    return {"status": "approved", "message": "Draft approved and publishing triggered"}
