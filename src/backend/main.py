from fastapi import FastAPI, Request, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
import sqlite3
import os
import subprocess
import shutil
from pathlib import Path


# FastAPI app
app = FastAPI()

# Database configuration
DB_PATH = "malmo.db"
UPLOAD_DIR = Path("uploads")
SNAKEFILE = Path("workflow/Snakefile")
UPLOAD_DIR.mkdir(parents=True,exist_ok=True)

# Database setup
engine = create_engine("sqilte:///malmo_test.db", connect_args={"check_same_thread":False})
SessionLocal = sessionmaker(autcommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Model
class Samples(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True) # Unique id
    user = Column(String(100), nullable=False)
    email = Column(String(100),nullable=False, unique=True)
    sample_name = Column(String(100),nullable=False)
    status = Column(String(100),default="Pending") # This should get update as th process is running
    r1_path = Column(String(100), nullable=False) # User will just upload the file
    r2_path = Column(String(100), nullable=False)
    date = Column(DateTime,nullable=False)

Base.metadata.create_all(engine)

# Pydantic Models (Dataclass)
class SampleCreate(BaseModel):
    user: str
    email: str
    sample_name: str
    status: str
    r1_path: str
    r2_path: str
    date: DateTime

class SampleResponse(BaseModel):
    id: int
    user: str
    email: str
    sample_name: str
    status: str
    r1_path: str
    r2_path: str
    date: DateTime

    class Config:
        from_attributes = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


get_db()



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
    for f in (r1,r2):
        if f.filename.endswith((".fastq.gz",".fq.gz")):
            raise HTTPException(
                status_code= 400,
                detail=f"File '{f.filename}' must be in fastq.gz or fq.gz format"
            )
        
    # Save the upload files
    sample_dir = UPLOAD_DIR / sample_name
    sample_dir.mkdir(parents=True, exist_ok=True)

    r1_path = sample_dir / r1.filename
    r2_path = sample_dir / r2.filename

    with open(r1_path, "wb") as r1_out:
        shutil.copyfileobj(r1.file, r1_out)
    with open(r2_path, "wb") as r2_out:
        shutil.copyfileobj(r2.file, r2_out)

    # Insert job record
    

