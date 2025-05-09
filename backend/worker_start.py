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
    
    # Get user ID from environment or use default (1000 is typically the first non-root user)
    uid = os.environ.get("CELERY_USER_ID", "1000")
    
    # Build command
    cmd = [
        "celery",
        "-A", "worker.celery_app",
        "worker",
        "--loglevel=info",
        f"--concurrency={concurrency}",
        f"--queues={queue}",
    ]
    
    # Add UID parameter if running as root and IGNORE_ROOT_WARNING is not set
    # This will handle the superuser warning in both development and production
    if os.geteuid() == 0 and os.environ.get("IGNORE_ROOT_WARNING", "false").lower() != "true":
        cmd.extend(["--uid", uid])
    
    # Add beat if enabled
    if os.environ.get("CELERY_BEAT", "false").lower() == "true":
        cmd.append("--beat")
    
    # Start worker
    subprocess.run(cmd)


if __name__ == "__main__":
    start_worker() 