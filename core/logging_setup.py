import logging
import sys
import gzip
import shutil
import os
import io
from logging.handlers import RotatingFileHandler

class CompressedRotatingFileHandler(RotatingFileHandler):
    def rotation_filename(self, default_name):
        return f"{default_name}.gz"

    def rotate(self, source, dest):
        with open(source, 'rb') as f_in:
            with gzip.open(dest, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)

class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that safely handles Unicode on Windows by replacing unencodable chars."""
    
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # Replace any problematic characters for Windows console
            if sys.platform == "win32":
                try:
                    stream.write(msg + self.terminator)
                except UnicodeEncodeError:
                    # Fallback: encode with replacement then decode back
                    safe_msg = msg.encode('cp1252', errors='replace').decode('cp1252')
                    stream.write(safe_msg + self.terminator)
            else:
                stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

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
    
    # Use SafeStreamHandler to prevent Unicode crashes on Windows
    stream_handler = SafeStreamHandler(sys.stdout)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[file_handler, stream_handler]
    )
