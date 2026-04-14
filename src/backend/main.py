import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from . import crud
from .database import create_db_tables, get_async_session
from .schemas import SampleCreate, SampleResponse
from .tasks import run_pipeline

# Get the directory where main.py is located
BACKEND_DIR = Path(__file__).parent
TEMPLATES_DIR = BACKEND_DIR / "templates"

# Create all tables in the database on startup
# Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_tables()
    yield


# FastAPI app
app = FastAPI(
    title="Microdentify API",
    description="Metagenomic sample processing, location prediction and profile estimation",
    version="1.0.0",
    lifespan=lifespan,
)

# Create a directory to store the uploaded files
PROJECT_ROOT = Path("/home/chandru/binp51")
UPLOAD_DIR = PROJECT_ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", include_in_schema=False)
async def root():
    return {"status": "running", "message": "Microdentify"}


@app.get("/metrics")
def metrics():
    """Basic metrics endpoint to prevent 404 errors"""
    return {"status": "ok", "message": "Metrics endpoint"}


# Upload a new sample
@app.post("/samples", response_model=SampleResponse, status_code=201)
async def upload_sample(
    username: str = Form(..., description="Enter your username"),
    email: str = Form(..., description="Enter your email"),
    sample_name: str = Form(..., description="Enter the sample_name"),
    r1: UploadFile = File(..., description="Forward read R1.fastq.gz"),
    r2: UploadFile = File(..., description="Reverse read R2.fastq.gz"),
    db: AsyncSession = Depends(get_async_session),  # Keep AsyncSession
):
    """
    Upload paired FASTQ files and trigger Snakemake pipeline
    """

    # Validate using Pydantic
    sample_obj = SampleCreate(username=username, email=email, sample_name=sample_name)

    # Check if sample already exists
    existing_sample = await crud.get_sample_by_name(db, sample_obj.sample_name)  # await
    if existing_sample:
        raise HTTPException(status_code=400, detail=f"Sample '{sample_obj.sample_name}' already exists")

    # Validate file extensions
    for f, name in [(r1, "R1"), (r2, "R2")]:
        if not f.filename.endswith((".fastq.gz", ".fq.gz")):
            raise HTTPException(status_code=400, detail=f"{name} must be .fastq.gz or .fq.gz")

    # Save uploaded files to disk
    r1_path = UPLOAD_DIR / f"{sample_name}_R1.fastq.gz"
    r2_path = UPLOAD_DIR / f"{sample_name}_R2.fastq.gz"

    with open(r1_path, "wb") as f:
        shutil.copyfileobj(r1.file, f)
    with open(r2_path, "wb") as f:
        shutil.copyfileobj(r2.file, f)

    # Create database record
    new_sample = await crud.create_sample(  # await
        db=db,
        username=sample_obj.username,
        email=sample_obj.email,
        sample_name=sample_obj.sample_name,
        r1_path=str(r1_path),
        r2_path=str(r2_path),
    )

    # Queue Snakemake task with Celery
    task = run_pipeline.delay(
        sample_id=str(new_sample.id),
        sample_name=sample_name,
        r1_path=str(r1_path.resolve()),  # Absolute path
        r2_path=str(r2_path.resolve())   # Absolute path
    )

    # Store Celery task ID for tracking
    await crud.update_celery_task_id(db, str(new_sample.id), task.id)

    # Return immediately with "pending" status
    return new_sample


@app.get("/samples")
async def list_samples(db: AsyncSession = Depends(get_async_session)):  # make async
    """List all submitted samples"""
    samples = await crud.get_all_samples(db)  # await
    return {
        "total": len(samples),
        "samples": [
            {
                "id": str(s.id),
                "sample_name": s.sample_name,
                "user": s.username,
                "status": s.status,
                "submitted_at": s.submitted_at,
                "started_at": s.started_at,
                "completed_at": s.completed_at
            }
            for s in samples
        ],
    }


@app.get("/samples/{sample_id}")
async def get_sample_status(sample_id: str, db: AsyncSession = Depends(get_async_session)):
    """Get status of a specific sample"""
    sample = await crud.get_sample_by_id(db, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {
        "id": str(sample.id),
        "sample_name": sample.sample_name,
        "status": sample.status,
        "submitted_at": sample.submitted_at,
        "r1_path": sample.r1_path,
        "r2_path": sample.r2_path,
    }


# Interactive map for the user
@app.get("/map", response_class=HTMLResponse)
def interactive_map():
    """Serve the interactive Malmo map"""
    map_file = TEMPLATES_DIR / "malmo_interactive_map.html"

    if not map_file.exists():
        raise HTTPException(status_code=404, detail=f"Map file not found at {map_file}")

    # Read the HTML file and return as an HTMLResponse
    with open(map_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    return html_content
