from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message":"Microdentify"}

# Post method - Post the R1 and R2 fastq.gz files.

# Get method - Obtain the job status for the particular id 
@app.get("/samples/{sample_id}")
async def get_status(item_id: str):
    return {"item_id":item_id}

# Get method - Get the results for the job submission