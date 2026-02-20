#!/usr/bin/env python3
"""
SLURM status checker for Snakemake
Checks the status of SLURM jobs and returns appropriate exit codes
"""

import subprocess
import sys
import time
import os

def get_slurm_job_status(job_id):
    """Get the status of a SLURM job"""
    try:
        # Use sacct to get job status
        cmd = ["sacct", "-j", str(job_id), "--format=State", "--noheader", "--parsable2"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            status_line = result.stdout.strip()
            if status_line:
                # Get the first status (main job status)
                status = status_line.split('\n')[0].strip()
                return status
        
        # Fallback to squeue for running jobs
        cmd = ["squeue", "-j", str(job_id), "--format=%T", "--noheader"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
            
        return "UNKNOWN"
        
    except subprocess.TimeoutExpired:
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"

def main():
    if len(sys.argv) != 2:
        print("Usage: slurm-status.py <job_id>", file=sys.stderr)
        sys.exit(1)
    
    job_id = sys.argv[1]
    
    # Get job status
    status = get_slurm_job_status(job_id)
    
    # Map SLURM states to Snakemake expected exit codes
    if status in ["PENDING", "RUNNING", "COMPLETING"]:
        # Job is still active
        sys.exit(0)
    elif status in ["COMPLETED"]:
        # Job completed successfully  
        print("success")
        sys.exit(0)
    elif status in ["FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"]:
        # Job failed
        print("failed")
        sys.exit(1)
    else:
        # Unknown status - assume failed
        print("failed")
        sys.exit(1)

if __name__ == "__main__":
    main()