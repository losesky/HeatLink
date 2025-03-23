"""
ThePaper Selenium adapter logging configuration.
This module configures logging for the ThePaper Selenium adapter to reduce verbose output.
"""

import logging

# Configure root logger
def configure_thepaper_logging(level=logging.INFO):
    """Configure ThePaper adapter logging to reduce verbose output"""
    # Set ThePaper adapter logger to INFO level
    logger = logging.getLogger("worker.sources.sites.thepaper_selenium")
    logger.setLevel(level)
    
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