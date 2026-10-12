"""
Centralized logging configuration for the phase association analysis.
Provides consistent logging across all modules.
"""

import logging
import sys
from constants import LOG_FORMAT, LOG_DATE_FORMAT

# Global logger instance
_logger = None

# ANSI color codes for terminal output
class ColorCodes:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright foreground colors
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'


class ColorizedFormatter(logging.Formatter):
    """Custom formatter that adds color to log messages based on level."""
    
    # Color mapping for different log levels
    LEVEL_COLORS = {
        logging.DEBUG: ColorCodes.CYAN,
        logging.INFO: ColorCodes.GREEN,
        logging.WARNING: ColorCodes.YELLOW,
        logging.ERROR: ColorCodes.RED,
        logging.CRITICAL: ColorCodes.BRIGHT_RED + ColorCodes.BOLD,
    }
    
    def format(self, record):
        """Format the log record with color codes."""
        # Save original levelname
        original_levelname = record.levelname
        
        # Add color to levelname
        color = self.LEVEL_COLORS.get(record.levelno, ColorCodes.RESET)
        record.levelname = f"{color}{record.levelname}{ColorCodes.RESET}"
        
        # Format the message
        formatted = super().format(record)
        
        # Restore original levelname
        record.levelname = original_levelname
        
        return formatted

def setup_logging(level=logging.INFO, log_file=None):
    """
    Setup logging configuration for the entire application.
    
    Args:
        level: Logging level (default: INFO)
        log_file: Optional file path to write logs to. If None, logs to console only.
    
    Returns:
        Configured logger instance
    """
    global _logger
    
    if _logger is not None:
        return _logger
    
    # Create logger
    _logger = logging.getLogger("phase_association")
    _logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    _logger.handlers.clear()
    
    # Create formatters
    # Colorized formatter for console
    console_formatter = ColorizedFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    # Plain formatter for file (no color codes in files)
    file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    
    # Console handler with colorized output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)
    _logger.addHandler(console_handler)
    
    # File handler (if specified) with plain formatting
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setLevel(level)
        file_handler.setFormatter(file_formatter)
        _logger.addHandler(file_handler)
    
    return _logger

def get_logger():
    """
    Get the configured logger instance.
    If not yet configured, sets up with default INFO level.
    
    Returns:
        Logger instance
    """
    global _logger
    if _logger is None:
        _logger = setup_logging()
    return _logger

# Convenience functions for common logging patterns
def log_error(message, exc_info=False):
    """Log an error message."""
    get_logger().error(message, exc_info=exc_info)

def log_warning(message):
    """Log a warning message."""
    get_logger().warning(message)

def log_info(message):
    """Log an info message."""
    get_logger().info(message)

def log_debug(message):
    """Log a debug message."""
    get_logger().debug(message)

def log_file_processed(file_name, status="OK"):
    """Log that a file has been processed."""
    get_logger().info(f"Processed {file_name}: {status}")

def log_file_skipped(file_name, reason):
    """Log that a file was skipped."""
    get_logger().warning(f"Skipped {file_name}: {reason}")

def log_normalization_warning(spectrum_idx, total, elements):
    """Log a normalization warning for unusual composition totals."""
    get_logger().warning(
        f"Spectrum {spectrum_idx}: Composition total {total:.2f}% (elements: {elements}). "
        f"Values normalized to 100%."
    )

def log_clustering_result(sample_name, n_clusters, score):
    """Log clustering results."""
    if score is not None:
        get_logger().info(
            f"Clustering for {sample_name}: {n_clusters} clusters, silhouette score: {score:.3f}"
        )
    else:
        get_logger().info(
            f"Clustering for {sample_name}: {n_clusters} clusters (custom selection)"
        )

def log_structure_created(path, entity_type="folder"):
    """Log that a folder/file structure was created."""
    get_logger().debug(f"Created {entity_type}: {path}")
