"""
Celery application configuration.

Celery is a distributed task queue. This file creates the Celery "app" object
that both the FastAPI server and the Celery worker import. The FastAPI side uses
it to SEND tasks (via .delay()). The worker side uses it to RECEIVE and EXECUTE tasks.

Redis acts as the message broker (task queue) and result backend (task results).
"""

from celery import Celery

from .config import settings

# Configure Celery to use Redis as the message broker
celery_app = Celery(
    "microdentify",  # This is the name of your celery application
    broker=settings.CELERY_BROKER_URL,  # This is the Redis connection string
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.backend.tasks"],
)  # Optional, for storing task results


celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="Europe/Stockholm",
    enable_utc=True,
    # Task tracking
    # track_started=True makes Celery emit a "STARTED" state when
    # the worker begins executing a task. Without this, tasks jump
    # straight from PENDING to SUCCESS/FAILURE.
    task_track_started=True,
    # Timeouts
    # Snakemake pipeline for metagenomcis sample process takes approx 40 min per sample on LUNARC systems.
    # We set generous limits.
    # soft_time_limit raises SoftTimeLimitExceeded (catchable).
    # time_limit does a hard SIGKILL (uncatchable safety net).
    task_soft_time_limit=7200,  # 2 hours soft limit
    task_time_limit=9000,  # 2.5 hours hard kill
    # Result expiry
    # How long Redis keeps the task result after completion.
    # 24 hours is more than enough for the real results are in the DB.
    result_expires=86400,
    # Reliability
    # acks_late=True: the task message is acknowledged AFTER the
    # worker finishes executing, not when it starts. This means
    # if the worker crashes mid-pipeline, the task goes BACK to
    # the Redis queue and another worker can retry it.
    task_acks_late=True,
    # Only fetch 1 task at a time per worker process.
    # Since each task runs for 40 min, prefetching more would
    # just hold them idle in memory.
    worker_prefetch_multiplier=1,
    # Concurrency
    # How many tasks one worker handles simultaneously.
    # Each task runs a Snakemake process that submits SLURM jobs.
    # Lunarc has limited SLURM fair-share; 2 concurrent pipelines
    # is a safe starting point. Increase if your allocation allows.
    worker_concurrency=2,
)
