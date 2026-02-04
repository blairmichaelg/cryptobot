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
    # CRITICAL: Must happen BEFORE creating StreamHandler
    
    if sys.platform == "win32":
        try:
            # Reconfigure stdout/stderr to use UTF-8 with error replacement
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            else:
                import io
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        except Exception as e:
            # Last resort: set environment variable for future subprocesses
            os.environ['PYTHONIOENCODING'] = 'utf-8:replace'
    
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
    
    # Create stream handler AFTER reconfiguring stdout
    stream_handler = logging.StreamHandler(sys.stdout)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[file_handler, stream_handler]
    )
