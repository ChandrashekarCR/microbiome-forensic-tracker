from fastapi import FastAPI, Request, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import sqlite3
import os
import subprocess
from pathlib import Path


# FastAPI app
app = FastAPI()

# Database setup
engine = create_engine("sqilte:///malmo_test.db", connect_args={"check_same_thread":False})
SessionLocal = sessionmaker(autcommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Model
class User(Base):
    __tablename__ = "users"
    id = Column()
    user = Column()
    email = Column()
    sample_name = Column()
    status = Column()
    r1_path = Column()
    r2_path = Column()
    date = Column()

# Database configuration
DB_PATH = "malmo.db"
UPLOAD_DIR = Path("uploads")
SNAKEFILE = Path("workflow/Snakefile")
UPLOAD_DIR.mkdir(parents=True,exist_ok=True)

templates = Jinja2Templates(directory="templates") # Name of the directory

posts: list[dict] = [
    {
        "id":1,
        "user":"chandru",
        "sample": "zr0392_1",
        "r1": "forward_read_path",
        "r2": "reverse_read_path",
        "date": "Feb 24, 2026"
    },
    {
        "id":2,
        "user":"eran",
        "sample": "zr0392_2",
        "r1": "forward_read_path",
        "r2": "reverse_read_path",
        "date": "Feb 23, 2026"
    }
]

@app.get("/", include_in_schema=False)
async def root():
    return {"message":"Microdentify"}

# 1) POST/samples - Upload R1 and R2, create a DB record, trigger snakemake
@app.post("/samples")
async def upload_sample(
    background_tasks: BackgroundTasks,
    sample_name: str,
    user: str,
    r1: UploadFile = File(..., description="Forward read (R1) fastq.gz"),
    r2: UploadFile = File(..., description="Reverse read (R2) fastq.gz")
):
    # Validate file extension
    pass

@app.get("/posts", include_in_schema=False)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"posts":posts, "title":"Home"})

@app.get("/api/posts")
def get_posts():
    return posts