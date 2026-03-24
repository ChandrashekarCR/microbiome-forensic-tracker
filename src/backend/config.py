import os 
from dotenv import load_dotenv

load_dotenv()

class Config:
    CELERY_BROKER_URL: str = os.environ.get("CELERY_BROKER_URL","redis://127.0.0.1:6379/0")
    CELERY_RESULT_BACKEND: str = os.environ.get("CELERY_RESULT_BACKEND","redis://127.0.0.1:6379/0")


settings = Config()