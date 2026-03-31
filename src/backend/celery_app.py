from celery import Celery

from .config import settings

# Configure Celery to use Redis as the message broker
celery_app = Celery(
    "microdentify",  # This is the name of your celery application
    broker=settings.CELERY_BROKER_URL,  # This is the Redis connection string
    backend=settings.CELERY_RESULT_BACKEND,
)  # Optional, for storing task results


celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Stockholm",
    task_track_started=True,
)


@celery.task
def run_snakemake():
    pass
