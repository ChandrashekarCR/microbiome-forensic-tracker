from celery import Celery

celery_app = Celery("microdentify",
                    broker="redis://localhost:6379/0",
                    backend="redis://localhost:6379/0",
                    include=["backemd.tasks"]
                    )

celery_app.conf.update(
    task_seriailzer="json",
    result_serializer="json",
    accept_content=["jsom"],
    timezone="Europe/Stockholm",
    time_track_started =True
)