from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "content_automation",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.jobs.pipeline_job"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Run pipeline every 2 days
celery_app.conf.beat_schedule = {
    "run-content-pipeline-every-2-days": {
        "task": "app.jobs.pipeline_job.run_pipeline",
        "schedule": 172800.0, # 2 days in seconds
    },
}
