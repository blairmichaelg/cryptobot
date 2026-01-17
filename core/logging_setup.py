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
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[
            CompressedRotatingFileHandler(
                'faucet_bot.log',
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding='utf-8'
            ),
            logging.StreamHandler(sys.stdout)
        ]
    )
