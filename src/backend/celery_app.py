from celery import Celery
import time

# Configure Celery to use Redis as the message broker
celery_app = Celery("microdentify", # This is the name of your celery application
                    broker="redis://localhost:6379/0", # This is the Redis connection string
                    backend="redis://localhost:6379/0") # Optional, for storing task results


celery_app.conf.update(
    task_serializer = "json",
    result_serializer = "json",
    accept_content = ["json"],
    timezone = "Europe/Stockholm",
    task_track_started = True
)