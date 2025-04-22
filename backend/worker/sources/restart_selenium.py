#!/usr/bin/env python3
import os
import signal
import time
import logging
import glob
import shutil
import subprocess
import platform
import psutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_chrome_processes():
    """Find all Chrome and ChromeDriver processes"""
    chrome_processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pname = proc.info['name']
            pcmd = proc.info.get('cmdline', [])
            
            # Filter out any Python processes or processes that might cause self-termination
            is_self_process = False
            if pcmd:
                for cmd_part in pcmd:
                    if cmd_part and ('python' in cmd_part.lower() or 'sources' in cmd_part.lower()):
                        is_self_process = True
                        break
            
            if not is_self_process and pname and ('chrome' in pname.lower() or 'chromedriver' in pname.lower()):
                chrome_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return chrome_processes

def terminate_chrome_processes():
    """Safely terminate Chrome and ChromeDriver processes"""
    chrome_processes = get_chrome_processes()
    
    terminated_count = 0
    for proc in chrome_processes:
        try:
            logger.info(f"Terminating Chrome process (PID: {proc.pid}, Name: {proc.name()})")
            proc.terminate()  # Try graceful termination first
            terminated_count += 1
        except Exception as e:
            logger.warning(f"Failed to terminate process {proc.pid} gracefully: {str(e)}")
            try:
                proc.kill()  # Force kill if terminate fails
                logger.info(f"Forcefully killed Chrome process (PID: {proc.pid})")
                terminated_count += 1
            except Exception as e2:
                logger.error(f"Failed to kill process {proc.pid}: {str(e2)}")
    
    # Give processes time to fully exit
    if terminated_count > 0:
        logger.info(f"Terminated {terminated_count} Chrome-related processes. Waiting for cleanup...")
        time.sleep(2)
    
    return terminated_count

def clean_chrome_user_data_dirs():
    """Clean up old Chrome user data directories"""
    chrome_dirs = glob.glob("/tmp/chrome_data_dir_*")
    removed_count = 0
    
    current_time = time.time()
    for dir_path in chrome_dirs:
        try:
            if os.path.isdir(dir_path):
                dir_mtime = os.path.getmtime(dir_path)
                # Remove directories older than 1 hour to avoid removing those in use
                if current_time - dir_mtime > 3600:  
                    logger.info(f"Removing old Chrome user data directory: {dir_path}")
                    shutil.rmtree(dir_path, ignore_errors=True)
                    removed_count += 1
        except Exception as e:
            logger.warning(f"Failed to remove directory {dir_path}: {str(e)}")
    
    return removed_count

def restart_celery_workers():
    """Restart Celery workers to refresh WebDriver connections"""
    try:
        # First stop the workers
        logger.info("Stopping Celery workers...")
        stop_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "stop_celery.sh")
        subprocess.run(["bash", stop_script], check=True)
        
        # Give processes time to fully stop
        time.sleep(5)
        
        # Then start the workers again
        logger.info("Starting Celery workers...")
        start_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "run_celery.sh")
        subprocess.run(["bash", start_script], check=True)
        
        logger.info("Celery workers restarted successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to restart Celery workers: {str(e)}")
        return False

def main():
    logger.info("=== Selenium WebDriver Reset Tool ===")
    
    # Step 1: Terminate Chrome processes
    term_count = terminate_chrome_processes()
    logger.info(f"Terminated {term_count} Chrome processes")
    
    # Step 2: Clean up Chrome user data directories
    dir_count = clean_chrome_user_data_dirs()
    logger.info(f"Removed {dir_count} old Chrome user data directories")
    
    # Step 3: Restart Celery workers
    if restart_celery_workers():
        logger.info("WebDriver reset process completed successfully")
    else:
        logger.error("WebDriver reset process completed with errors")

if __name__ == "__main__":
    main() 