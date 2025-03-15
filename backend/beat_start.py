import os
import subprocess
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

# Import worker tasks to ensure they are registered
from worker.tasks import *


def start_beat():
    """
    Start Celery beat scheduler
    """
    # Build command
    cmd = [
        "celery",
        "-A", "worker.celery_app",
        "beat",
        "--loglevel=info",
    ]
    
    # Add scheduler if specified
    scheduler = os.environ.get("CELERY_SCHEDULER")
    if scheduler:
        cmd.append(f"--scheduler={scheduler}")
    
    # Add schedule file if using file-based scheduler
    schedule_file = os.environ.get("CELERY_SCHEDULE_FILE")
    if schedule_file:
        cmd.append(f"--schedule={schedule_file}")
    
    # Start beat
    subprocess.run(cmd)


if __name__ == "__main__":
    start_beat() 