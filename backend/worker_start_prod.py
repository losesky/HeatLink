#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

# Import worker tasks to ensure they are registered
from worker.tasks import *


def start_worker_prod():
    """
    Start Celery worker in production mode
    Always uses a non-root user for security
    """
    # Get number of workers from environment or use default (higher for production)
    concurrency = os.environ.get("CELERY_CONCURRENCY", "4")
    
    # Get queue name from environment or use default
    queue = os.environ.get("CELERY_QUEUE", "main-queue")
    
    # Get user ID from environment or use default (1000 is typically the first non-root user)
    uid = os.environ.get("CELERY_USER_ID", "1000")
    
    # Get group ID from environment or use default
    gid = os.environ.get("CELERY_GROUP_ID", "1000")
    
    # Build command
    cmd = [
        "celery",
        "-A", "worker.celery_app",
        "worker",
        "--loglevel=info",
        f"--concurrency={concurrency}",
        f"--queues={queue}",
        "--uid", uid,
        "--gid", gid,
    ]
    
    # Add beat if enabled
    if os.environ.get("CELERY_BEAT", "false").lower() == "true":
        cmd.append("--beat")
    
    # Start worker
    subprocess.run(cmd)


if __name__ == "__main__":
    # Set environment to production
    os.environ["ENVIRONMENT"] = "production"
    start_worker_prod() 