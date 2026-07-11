# Backend Architecture: Asynchronous Snakemake Execution with Celery and Redis

## Overview

The microbiome-forensic-tracker consists of a metagenomics platform consisting of a **Snakemake-based bioinformatics pipeline** exposed through a **FastAPI backend**.

The Snakemake workflow is designed to run on HPC infrastructure (LUNARC) using **SLURM**. However, directly executing a long-running Snakemake workflow inside a normal HTTP request is not reliable because HTTP requests are designed for short-lived operations.

A typical API request may timeout after approximately **30–60 seconds** depending on the client, proxy, or server configuration. Metagenomic processing can take several minutes to hours because it involves:

- Quality control
- Adapter removal
- Host read filtering
- Kraken2 classification
- Bracken abundance estimation
- Result processing

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

## Why Celery and Redis are Required

### Problem

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

## Redis: Message Broker

Redis acts as a lightweight message queue.

Its responsibility is **not** running the pipeline. It stores task messages waiting to be processed.

**Example:**

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

## Celery: Task Worker

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

## Service Responsibilities

| Component | Responsibility |
|-----------|----------------|
| FastAPI | User interface and API layer |
| Redis | Task queue and communication |
| Celery | Background execution |
| Snakemake | Bioinformatics workflow |
| SLURM | Compute scheduling |

---

## Example Execution Flow

### 1. User uploads FASTQ

Request:

```
POST /pipeline/run
```

FastAPI receives:

```
sample.fastq.gz
```

### 2. FastAPI creates Celery task

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

### 3. Redis stores task

```
Redis Queue
a8f91d: run_pipeline(sample001)
```

### 4. Worker executes task

Celery worker receives `run_pipeline(sample001)` and runs:

```bash
snakemake \
    --profile profiles/single_run \
    --config sample=sample001
```

### 5. Snakemake submits SLURM jobs

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

# PostgreSQL Migration from SQLite for LUNARC

## Why PostgreSQL?

- Multi-user access
- Network accessible
- Better concurrency
- Production-ready
- Required for cloud migration (Azure PostgreSQL)

## PostgreSQL Concepts Explained

### What is PostgreSQL?

PostgreSQL is a **relational database management system (RDBMS)** that runs as a separate server process. Unlike SQLite (which is just a file), PostgreSQL:

- Runs as a background service (daemon)
- Listens for network connections (port 5432 by default)
- Requires authentication (username/password)
- Supports multiple concurrent users

### What Each Command Does

| Command | What it does |
|---------|--------------|
| `initdb` | Creates an empty PostgreSQL system (data directory with system files) |
| `pg_ctl start` | Starts the PostgreSQL server process |
| `pg_ctl stop` | Stops the PostgreSQL server process |
| `pg_ctl status` | Checks if PostgreSQL is running |
| `createuser` | Creates a user account (like a login) for the database |
| `createdb` | Creates a database container (where your tables live) |
| `psql` | Interactive terminal to connect and run SQL commands |

### The Structure

```
PostgreSQL Server (running process)
│
├── Database 1 (malmo_backend_db)
│   ├── Table: samples
│   ├── Table: abundance
│   └── ...
│
├── Database 2 (other_db)
│   └── ...
│
├── User: chandru_malmo_backend (has password)
└── User: other_user
```

Your code (SQLAlchemy) creates the tables inside the database using your `models.py` definitions.

---

## Step-by-Step: Setting Up PostgreSQL on LUNARC

### 1. Load PostgreSQL Module

```bash
module load GCCcore/14.3.0
module load PostgreSQL/17.5

# Verify installation
which postgres
which psql
psql --version
```

### 2. Create PostgreSQL Data Directory

```bash
# Create a directory for PostgreSQL data (inside your project)
mkdir -p ~/binp51/postgres/data
mkdir -p ~/binp51/postgres/logs
mkdir -p ~/binp51/postgres/run

cd ~/binp51/postgres
```

### 3. Initialize the Database

```bash
# This creates the PostgreSQL system files in the data directory
initdb -D data/
```

**What this does:** Creates the file structure and default configuration files for PostgreSQL. It's a one-time setup step.

### 4. Start the PostgreSQL Server

```bash
# Start the server (runs in background)
pg_ctl -D data/ -l logs/logfile.log start

# Check if it's running
pg_ctl -D data/ status
```

**Expected output:**
```
pg_ctl: server is running (PID: 12345)
```

### 5. Create a Database User (with Password)

```bash
# Create a user with password prompt
createuser chandru_malmo_backend -P
```

You'll be prompted:
```
Enter password for new role: malmo_backend_microdentify
Enter it again: malmo_backend_microdentify
```

**Why a password?** PostgreSQL requires authentication. This password protects your data from unauthorized access on the shared system.

### 6. Create the Database

```bash
# Create database owned by the user
createdb -O chandru_malmo_backend malmo_backend_db
```

### 7. Grant Permissions

```bash
# Ensure the user has full access to the database
psql -d malmo_backend_db -c "GRANT ALL PRIVILEGES ON DATABASE malmo_backend_db TO chandru_malmo_backend;"
```

### 8. Test the Connection

```bash
# Connect to the database
psql -d malmo_backend_db -U chandru_malmo_backend -h localhost
```

Enter the password when prompted. You should see:

```
psql (17.5)
Type "help" for help.

malmo_backend_db=>
```

Type `\q` to quit.

### 9. Update `.env.lunarc`

Add or update this line in your `.env.lunarc`:

```bash
BACKEND_DB_URL=postgresql://chandru_malmo_backend:malmo_backend_microdentify@localhost:5432/malmo_backend_db
```

---

## PostgreSQL Management Commands

### Starting and Stopping

```bash
# Start the server
pg_ctl -D ~/binp51/postgres/data/ -l ~/binp51/postgres/logs/logfile.log start

# Stop the server
pg_ctl -D ~/binp51/postgres/data/ stop

# Restart the server
pg_ctl -D ~/binp51/postgres/data/ restart

# Check status
pg_ctl -D ~/binp51/postgres/data/ status
```

### Connecting to PostgreSQL

```bash
# Connect to your database
psql -d malmo_backend_db -U chandru_malmo_backend -h localhost
```

### Essential SQL Commands Inside psql

```sql
-- List all databases
\l

-- Select a databat
\c malmo_db

-- List all tables
\dt

-- Describe a table structure
\d samples

-- Quit psql
\q
```

### Querying the Database

```sql
-- See all samples
SELECT * FROM samples;

-- See all abundance records
SELECT * FROM abundance;

-- Filter samples by name
SELECT * FROM samples WHERE sample_name = 'your_sample_name';

-- See abundance for a specific sample
SELECT * FROM abundance WHERE sample_name = 'your_sample_name';

-- See samples with their abundance counts
SELECT 
    s.sample_name, 
    s.status, 
    COUNT(a.id) as abundance_count
FROM samples s
LEFT JOIN abundance a ON s.id = a.sample_id
GROUP BY s.sample_name, s.status;

-- Check if a sample has abundance data
SELECT 
    s.sample_name,
    s.status,
    CASE 
        WHEN COUNT(a.id) > 0 THEN 'Has abundance data'
        ELSE 'No abundance data yet'
    END as abundance_status
FROM samples s
LEFT JOIN abundance a ON s.id = a.sample_id
WHERE s.sample_name = 'your_sample_name'
GROUP BY s.sample_name, s.status;
```

---

## How to Check if Everything is Working

### 1. Check PostgreSQL is Running

```bash
pg_ctl -D ~/binp51/postgres/data/ status
```

### 2. Check Database Connection

```bash
psql -d malmo_backend_db -U chandru_malmo_backend -h localhost -c "SELECT 1;"
```

### 3. Check Tables Were Created

```bash
psql -d malmo_backend_db -U chandru_malmo_backend -h localhost -c "\dt"
```

If tables exist, you'll see:

```
              List of relations
 Schema |   Name    | Type  |  Owner
--------+-----------+-------+----------
 public | abundance | table | ...
 public | samples   | table | ...
```

### 4. After Uploading a Sample

```bash
# Check the sample was inserted
psql -d malmo_backend_db -U chandru_malmo_backend -h localhost -c "SELECT * FROM samples ORDER BY submitted_at DESC LIMIT 5;"

# Check if abundance data was added (after pipeline completes)
psql -d malmo_backend_db -U chandru_malmo_backend -h localhost -c "SELECT * FROM abundance WHERE sample_name = 'your_sample_name';"
```

---

## Resetting/Deleting Tables (Keep Database)

### Option 1: Drop All Tables (Keep Database)

```bash
# Connect to your database
psql -d malmo_backend_db -U chandru_malmo_backend -h localhost

# Inside psql, run:
DROP TABLE IF EXISTS abundance CASCADE;
DROP TABLE IF EXISTS samples CASCADE;

# Then quit
\q
```

Your application will recreate the tables on next startup via `create_db_tables()`.

### Option 2: Truncate Tables (Keep Structure, Delete Data)

```sql
-- Delete all data but keep table structure
TRUNCATE TABLE abundance;
TRUNCATE TABLE samples;
```

### Option 3: Delete All Tables (Including System)

```bash
# Connect to your database
psql -d malmo_backend_db -U chandru_malmo_backend -h localhost

# Drop all tables
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO chandru_malmo_backend;
GRANT ALL ON SCHEMA public TO public;
```

### Option 4: Delete Entire Database (Complete Reset)

```bash
# Delete the database
dropdb malmo_backend_db

# Recreate it
createdb -O chandru_malmo_backend malmo_backend_db
```

---

## Troubleshooting

### PostgreSQL Won't Start

```bash
# Check the logs
cat ~/binp51/postgres/logs/logfile.log

# Check if another PostgreSQL is running
ps aux | grep postgres

# Remove lock file if it exists
rm -f ~/binp51/postgres/data/postmaster.pid

# Try starting again
pg_ctl -D ~/binp51/postgres/data/ -l ~/binp51/postgres/logs/logfile.log start
```

### Connection Refused

```bash
# Check if PostgreSQL is running
pg_ctl -D ~/binp51/postgres/data/ status

# Check if port 5432 is in use
lsof -i :5432

# If a different PostgreSQL is running, stop it first or use a different port
# To use a different port (e.g., 5433):
pg_ctl -D ~/binp51/postgres/data/ -l logs/logfile.log start -o "-p 5433"
```

### Authentication Failed

```bash
# Reset the user password
psql -d postgres -c "ALTER USER chandru_malmo_backend WITH PASSWORD 'new_password';"
```

### MissingGreenlet Error

This happens when Celery tries to use an async database driver. Ensure:
1. `BACKEND_DB_URL` in `.env.lunarc` is `postgresql://` (without `+asyncpg`)
2. Your `database.py` creates separate engines with the appropriate driver
3. Celery worker is restarted after changes

### Database User Doesn't Exist

```bash
# Delete the user
dropuser --if-exists chandru_malmo_backend

# Recreate the user
createuser chandru_malmo_backend -P

# Recreate the database
dropdb malmo_backend_db
createdb -O chandru_malmo_backend malmo_backend_db
```

---

## Current Deployment (LUNARC)

The backend runs as three independent services.

### Terminal 1: Redis

```bash
# Load module
module load GCCcore/13.3.0
module load Redis/7.4.1

# Activate environment
source .venv-all/bin/activate

# Start Redis
redis-server --port 6379 --tcp-keepalive 60
```

Verify:

```bash
redis-cli ping
# Expected: PONG
```

### Terminal 2: Celery Worker

```bash
# Activate environment
source .venv-all/bin/activate

# Load environment
set -a; source .env.lunarc; set +a

# Start worker
celery -A src.backend.celery_app:celery_app worker --loglevel=info --concurrency=2
```

### Terminal 3: FastAPI

```bash
# Activate environment
source .venv-all/bin/activate

# Start API
uvicorn src.backend.main:app --host 0.0.0.0 --port 8000
```

### Stopping Services

**Graceful shutdown:**
```bash
# Redis: Ctrl+C
# Celery: Ctrl+C
# FastAPI: Ctrl+C
```

**Force kill:**
```bash
pkill -f "redis-server"
pkill -f "celery worker"
pkill -f "uvicorn"
```

---

## Quick Reference: PostgreSQL Setup Checklist

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `module load PostgreSQL/17.5` | Load PostgreSQL |
| 2 | `mkdir -p postgres/{data,logs,run}` | Create directories |
| 3 | `initdb -D data/` | Initialize PostgreSQL system |
| 4 | `pg_ctl -D data/ -l logs/logfile.log start` | Start the server |
| 5 | `createuser chandru_malmo_backend -P` | Create user with password |
| 6 | `createdb -O chandru_malmo_backend malmo_backend_db` | Create database |
| 7 | `psql -d malmo_backend_db -c "GRANT ALL PRIVILEGES ON DATABASE malmo_backend_db TO chandru_malmo_backend;"` | Grant permissions |
| 8 | `psql -d malmo_backend_db -U chandru_malmo_backend -h localhost` | Test connection |
| 9 | Update `.env.lunarc` with `BACKEND_DB_URL=...` | Configure application |

---


## Important Notes

1. **You MUST start PostgreSQL before running your application.** The application cannot create the database server itself.
2. **Tables are created automatically** by your `create_db_tables()` function when the app starts.
3. **The connection string tells your app where to find PostgreSQL**, but PostgreSQL must be running independently.
4. **The `.env.lunarc` file should NOT be committed to Git** – it contains passwords. Add it to `.gitignore`.
5. **Your code (SQLAlchemy) creates the tables** – you don't need to manually define them in SQL.

---

## Summary

The backend separates responsibilities:

| Component | Purpose |
|-----------|---------|
| FastAPI | User interface and API layer |
| Redis | Task queue and communication |
| Celery | Background execution |
| Snakemake | Bioinformatics workflow |
| SLURM | Compute scheduling |

Celery and Redis act as the bridge between an interactive web application and a long-running HPC workflow.