from fastapi import FastAPI, UploadFile, Form, File, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from pathlib import Path
from .database import engine, get_db
from .models import Base
from . import crud
from .schemas import UserCreate, SampleCreate, SampleResponse
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
import shutil
import json

# Get the directory where main.py is located
BACKEND_DIR = Path(__file__).parent
TEMPLATES_DIR = BACKEND_DIR / "templates"

# Create all tables in the database on startup
#Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(
    title="Microdentify API",
    description="Metagenomic sample processing, location prediction and profile estimation",
    version="1.0.0"
)

# Create a directory to store the uploaded files
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/", include_in_schema=False)
async def root():
    return {"status":"running",
            "message":"Microdentify"            
            }

# Upload a new sample
@app.post("/samples", response_model=SampleResponse, status_code=201)
async def upload_sample(
    background_task: BackgroundTasks,
    username: str = Form(..., description="Enter your username"),
    email: str = Form(..., description="Enter your email"),
    sample_name: str = Form(..., description="Enter the sample_name"),
    r1: UploadFile = File(..., description="Forward read R1.fastq.gz"),
    r2: UploadFile = File(..., description="Reverse read R2.fastq.gz"),
    db: Session = Depends(get_db)
):
    """
    Upload paired FASTQ files and trigger Snakemake pipeline
    """

    # Validate using Pydantic
    sample_obj = SampleCreate(username=username, email=email, sample_name=sample_name)

    # Check if sample already exists
    if crud.get_sample_by_name(db, sample_obj.sample_name):
        raise HTTPException(
            status_code=400,
            detail=f"Sample '{sample_obj.sample_name}' already exists"
        )

    # Validate file extensions
    for f, name in [(r1, "R1"), (r2, "R2")]:
        if not f.filename.endswith(('.fastq.gz', '.fq.gz')):
            raise HTTPException(
                status_code=400,
                detail=f"{name} must be .fastq.gz or .fq.gz"
            )

    # Save uploaded files to disk
    r1_path = UPLOAD_DIR / f"{sample_name}_R1.fastq.gz"
    r2_path = UPLOAD_DIR / f"{sample_name}_R2.fastq.gz"

    with open(r1_path, "wb") as f:
        shutil.copyfileobj(r1.file, f)
    with open(r2_path, "wb") as f:
        shutil.copyfileobj(r2.file, f)

    # Create database record
    new_sample = crud.create_sample(
        db=db,
        username=sample_obj.username,
        email=sample_obj.email,
        sample_name=sample_obj.sample_name,
        r1_path=str(r1_path),
        r2_path=str(r2_path)
    )

    # We need to run the background snakemake operation
    

    # Return immediately with "pending" status
    return new_sample

@app.get("/samples")
def list_samples(db: Session = Depends(get_db)):
    """List all submitted samples"""
    samples = crud.get_all_samples(db)
    return {
        "total": len(samples),
        "samples": [
            {
                "id": s.id,
                "sample_name": s.sample_name,
                "user": s.username,
                "status": s.status,
                "submitted_at": s.submitted_at
            }
            for s in samples
        ]
    }

# Interactive map for the user

@app.get("/map",response_class=HTMLResponse)
def interactive_map():
    """Serve the interactive Malmo map"""
    map_file = TEMPLATES_DIR / "malmo_interactive_map.html"
    
    if not map_file.exists():
        raise HTTPException(status_code=404, detail=f"Map file not found at {map_file}")
    
    # Read the HTML file and return as an HTMLResponse
    with open(map_file,"r",encoding="utf-8") as f:
        html_content = f.read()

    return html_content