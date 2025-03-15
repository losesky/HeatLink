import os
import subprocess
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

# Import worker tasks to ensure they are registered
from worker.tasks import *


def start_worker():
    """
    Start Celery worker
    """
    # Get number of workers from environment or use default
    concurrency = os.environ.get("CELERY_CONCURRENCY", "1")
    
    # Get queue name from environment or use default
    queue = os.environ.get("CELERY_QUEUE", "main-queue")
    
    # Build command
    cmd = [
        "celery",
        "-A", "worker.celery_app",
        "worker",
        "--loglevel=info",
        f"--concurrency={concurrency}",
        f"--queues={queue}",
    ]
    
    # Add beat if enabled
    if os.environ.get("CELERY_BEAT", "false").lower() == "true":
        cmd.append("--beat")
    
    # Start worker
    subprocess.run(cmd)


if __name__ == "__main__":
    start_worker() 