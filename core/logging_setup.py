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
    # Alternatively, use a StreamHandler and hope for the best, 
    # but wrapping stdout is more reliable for emojis.
    
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
    
    # StreamHandler doesn't take encoding directly in older Python, 
    # but in 3.7+ it can be set via sys.stdout.reconfigure or just let it fail.
    # We will use a custom handler or try to reconfigure.
    if sys.platform == "win32":
        try:
            import io
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass

    stream_handler = logging.StreamHandler(sys.stdout)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[file_handler, stream_handler]
    )
