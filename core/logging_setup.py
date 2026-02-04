import logging
import sys
import gzip
import shutil
import os
from logging.handlers import RotatingFileHandler

class CompressedRotatingFileHandler(RotatingFileHandler):
    def rotation_filename(self, default_name):
        return f"{default_name}.gz"

    def rotate(self, source, dest):
        with open(source, 'rb') as f_in:
            with gzip.open(dest, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)

def setup_logging(log_level: str = "INFO"):
    # Force UTF-8 encoding for console output on Windows
    # Use errors='replace' to avoid crashing on emoji characters
    
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create handlers
    log_path = os.path.join("logs", "faucet_bot.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    file_handler = CompressedRotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    
    # For Windows console, use errors='replace' to handle emoji gracefully
    if sys.platform == "win32":
        try:
            import io
            # Try to reconfigure stdout to UTF-8, but with error handling for emoji
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            else:
                # Fallback: wrap stdout with UTF-8 and replace errors
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except Exception as e:
            # If all else fails, just continue - logging will replace invalid chars
            pass

    stream_handler = logging.StreamHandler(sys.stdout)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[file_handler, stream_handler]
    )
