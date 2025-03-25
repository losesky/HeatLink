"""
ThePaper Selenium adapter logging configuration.
This module configures logging for the ThePaper Selenium adapter to reduce verbose output.
"""

import logging

# Custom filter to remove specific log messages
class ThePaperFilter(logging.Filter):
    def filter(self, record):
        # Filter out the initialization messages
        if "首次初始化" in record.getMessage() or "初始化 澎湃新闻热榜 适配器" in record.getMessage():
            return False
        return True

# Configure root logger
def configure_thepaper_logging(level=logging.INFO):
    """Configure ThePaper adapter logging to reduce verbose output"""
    # Set ThePaper adapter logger to INFO level
    logger = logging.getLogger("worker.sources.sites.thepaper_selenium")
    logger.setLevel(level)
    
    # Add filter to remove specific messages
    logger.addFilter(ThePaperFilter())
    
    # Set related loggers to WARNING or higher to reduce noise
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("webdriver_manager").setLevel(logging.WARNING)
    
    # Create a custom formatter with simplified output
    formatter = logging.Formatter('[%(levelname)s] ThePaper: %(message)s')
    
    # Check if there are existing handlers, if so, update them
    if logger.handlers:
        for handler in logger.handlers:
            handler.setFormatter(formatter)
    else:
        # If no handlers exist, create a console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    # Prevent logs from propagating to parent loggers to avoid duplication
    logger.propagate = False
    
    return logger 