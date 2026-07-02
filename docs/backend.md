# Backend Architecture: Asynchronous Snakemake Execution with Celery and Redis

## Overview

The microbiome-forensic-tracker consists of a metagenomics platform consists of a **Snakemake-based bioinformatics pipeline** exposed through a **FastAPI backend**.

The Snakemake workflow is designed to run on HPC infrastructure (LUNARC) using **SLURM**. However, directly executing a long-running Snakemake workflow inside a normal HTTP request is not reliable because HTTP requests are designed for short-lived operations.

A typical API request may timeout after approximately **30–60 seconds** depending on the client, proxy, or server configuration. Metagenomic processing can take several minutes to hours because it involves:

* Quality control
* Adapter removal
* Host read filtering
* Kraken2 classification
* Bracken abundance estimation
* Result processing

Therefore, the backend uses an asynchronous job architecture:

```
User
 |
 | HTTP request
 v
FastAPI
 |
 | Submit task
 v
Redis Queue
 |
 | Worker picks task
 v
Celery Worker
 |
 | Execute
 v
Snakemake
 |
 | Submit jobs
 v
SLURM Cluster
 |
 v
Results Database
 |
 v
FastAPI Response
```

---

# Why Celery and Redis are Required

## Problem

A naive implementation would execute Snakemake directly inside FastAPI:

```python
@app.post("/run")
def run_pipeline():
    subprocess.run(
        ["snakemake", "--profile", "production"]
    )

    return {"status": "done"}
```

This creates several problems:

1. The HTTP connection remains open until completion
2. Long jobs may exceed server timeout limits
3. Multiple users cannot submit jobs efficiently
4. The API process becomes blocked
5. Failed jobs are harder to retry

For metagenomic workflows, this is not suitable.

---

# Redis: Message Broker

Redis acts as a lightweight message queue.

Its responsibility is not running the pipeline.

It stores task messages waiting to be processed.

Example:

A user uploads a FASTQ file:

```
sample_001_R1.fastq.gz
sample_001_R2.fastq.gz
```

FastAPI creates a task:

```json
{
    "sample_id": "sample_001",
    "fastq_path": "/uploads/sample_001"
}
```

and pushes it into Redis.

Redis now contains:

```
Queue:

[
  run_snakemake(sample_001)
]
```

FastAPI immediately returns:

```json
{
    "status": "submitted",
    "job_id": "abc123"
}
```

The user does not wait.

---

# Celery: Task Worker

Celery is the background task processor.

Celery workers continuously monitor Redis:

```
Celery Worker

while True:

    check Redis

    if task exists:
        execute task
```

When a task appears:

```
Redis
 |
 v
Celery Worker
 |
 v
run_snakemake_pipeline()
 |
 v
Snakemake
 |
 v
SLURM jobs
```

The worker executes the expensive computation outside FastAPI.

---

# Service Responsibilities

## FastAPI

Responsible for:

* receiving uploads
* validating requests
* submitting jobs
* checking job status
* returning results

FastAPI should remain lightweight.

---

## Redis

Responsible for:

* storing queued tasks
* communicating between services
* storing task state

Redis does not execute computation.

---

## Celery Worker

Responsible for:

* consuming queued tasks
* running Snakemake
* monitoring execution
* updating task state

---

## Snakemake

Responsible for:

* workflow management
* dependency handling
* resource allocation
* submitting jobs to SLURM

---

# Example Execution Flow

## 1. User uploads FASTQ

Request:

```
POST /pipeline/run
```

FastAPI receives:

```
sample.fastq.gz
```

---

## 2. FastAPI creates Celery task

Example:

```python
task = run_pipeline.delay(
    sample_id="sample001",
    fastq_path="/uploads/sample001"
)
```

Celery returns:

```
job_id = "a8f91d"
```

---

## 3. Redis stores task

```
Redis Queue

a8f91d:
    run_pipeline(sample001)
```

---

## 4. Worker executes task

Celery worker receives:

```
run_pipeline(sample001)
```

and runs:

```bash
snakemake \
    --profile profiles/single_run \
    --config sample=sample001
```

---

## 5. Snakemake submits SLURM jobs

Example:

```
Snakemake
    |
    +-- fastp
    |
    +-- bowtie2
    |
    +-- kraken2
    |
    +-- bracken
```

SLURM manages compute resources.

---

# Current Deployment

The backend currently runs as three independent services.

## Terminal 1: Redis

```bash
# Load module (LUNARC-specific)
module load GCCcore/13.3.0
module load Redis/7.4.1

source .venv-all/bin/activate

redis-server \
    --port 6379 \
    --tcp-keepalive 60
```

Verify:

```bash
redis-cli ping
```

Expected:

```
PONG
```

---

## Terminal 2: Celery Worker

Activate environment:

```bash
# Load the environment
source .venv-all/bin/activate 

# All the paths configurations for the backend and snakefile for backend
# are in the .env.lunarc foler
set -a; source .env.lunarc; set +a

```

Start worker:

```bash
celery \
    -A src.backend.celery_app:celery_app \
    worker \
    --loglevel=info \
    --concurrency=2
```

Worker output:

```
[tasks]

src.backend.tasks.run_snakemake_pipeline

celery@node ready
```

---

## Terminal 3: FastAPI

Activate backend environment:

```bash
source .venv-all/bin/activate
```

Start API:

```bash
uvicorn \
    src.backend.main:app \
    --host 0.0.0.0 \
    --port 8000
```

API:

```
http://localhost:8000/docs
```

## Stopping Services

**Graceful shutdown:**

```bash
# Terminal 1 (Redis)
Ctrl+C

# Terminal 2 (Celery)
Ctrl+C

# Terminal 3 (FastAPI)
Ctrl+C
```

**Force kill (if stuck):**

```bash
pkill -f "redis-server"
pkill -f "celery worker"
pkill -f "uvicorn"
```

---

# Future Improvement: Startup Script

Instead of starting three terminals manually, the services can be launched using a single script.

Example:

`start_backend.sh`

```bash
#!/bin/bash

echo "Starting Redis..."

redis-server \
    --port 6379 \
    --daemonize yes


echo "Starting Celery worker..."

celery \
    -A src.backend.celery_app:celery_app \
    worker \
    --loglevel=info \
    --concurrency=2 \
    > logs/celery.log 2>&1 &


echo "Starting FastAPI..."

uvicorn \
    src.backend.main:app \
    --host 0.0.0.0 \
    --port 8000
```

Make executable:

```bash
chmod +x start_backend.sh
```

Run:

```bash
./start_backend.sh
```

---

# Cloud Migration

This architecture maps naturally to cloud services.

Example:

```
FastAPI
 |
Cloud Redis
 |
Celery Worker Container
 |
Snakemake Container
 |
Cloud Compute / HPC
```

The asynchronous design remains unchanged.

Only the execution environment changes.

---

# Summary

The backend separates responsibilities:

| Component | Purpose                      |
| --------- | ---------------------------- |
| FastAPI   | User interface and API layer |
| Redis     | Task queue and communication |
| Celery    | Background execution         |
| Snakemake | Bioinformatics workflow      |
| SLURM     | Compute scheduling           |

Celery and Redis act as the bridge between an interactive web application and a long-running HPC workflow.
