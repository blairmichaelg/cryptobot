"""Logging configuration for Cryptobot Gen 3.0.

Sets up a dual-handler logging pipeline:

1. **Console** -- :class:`SafeStreamHandler` that gracefully handles
   Unicode on Windows by falling back to ``cp1252`` replacement
   encoding.
2. **File** -- :class:`CompressedRotatingFileHandler` writing to
   ``logs/faucet_bot.log`` with automatic gzip rotation (10 MiB per
   file, 5 backups).

Usage::

    from core.logging_setup import setup_logging
    setup_logging("DEBUG")
"""

import gzip
import io
import logging
import os
import shutil
import sys
from logging.handlers import RotatingFileHandler


class CompressedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that gzip-compresses rotated log files.

    Rotated files are renamed with a ``.gz`` suffix and compressed
    in-place, keeping disk usage low for long-running bot sessions.
    """

    def rotation_filename(self, default_name: str) -> str:
        """Append ``.gz`` to the rotated file name.

        Args:
            default_name: Original rotation file path.

        Returns:
            Path with ``.gz`` suffix appended.
        """
        return f"{default_name}.gz"

    def rotate(self, source: str, dest: str) -> None:
        """Compress *source* into *dest* using gzip.

        The original *source* file is removed after successful
        compression.

        Args:
            source: Path to the uncompressed log file.
            dest: Destination path for the compressed file.
        """
        with open(source, 'rb') as f_in:
            with gzip.open(dest, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)


class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that safely handles Unicode on Windows.

    On Windows, console output defaults to a narrow code page that
    cannot represent emoji and many Unicode characters.  This handler
    catches :exc:`UnicodeEncodeError` and falls back to ``cp1252``
    with replacement characters so that logging never crashes the
    application.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record, handling encoding errors gracefully.

        Args:
            record: The log record to emit.
        """
        try:
            msg = self.format(record)
            stream = self.stream
            if sys.platform == "win32":
                try:
                    stream.write(msg + self.terminator)
                except UnicodeEncodeError:
                    safe_msg = msg.encode(
                        'cp1252', errors='replace',
                    ).decode('cp1252')
                    stream.write(safe_msg + self.terminator)
            else:
                stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the root logger with console and file handlers.

    On Windows the function first reconfigures ``sys.stdout`` and
    ``sys.stderr`` to use UTF-8 (with replacement for unencodable
    characters) before any handler is created.

    Args:
        log_level: Logging level name (e.g. ``"DEBUG"``,
            ``"INFO"``, ``"WARNING"``).  Defaults to ``"INFO"``.
    """
    # Force UTF-8 encoding for console output on Windows
    # CRITICAL: Must happen BEFORE creating StreamHandler
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(
                    encoding='utf-8', errors='replace',
                )
                sys.stderr.reconfigure(
                    encoding='utf-8', errors='replace',
                )
            else:
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.buffer,
                    encoding='utf-8',
                    errors='replace',
                    line_buffering=True,
                )
                sys.stderr = io.TextIOWrapper(
                    sys.stderr.buffer,
                    encoding='utf-8',
                    errors='replace',
                    line_buffering=True,
                )
        except Exception:
            # Last resort: set env var for future subprocesses
            os.environ['PYTHONIOENCODING'] = 'utf-8:replace'

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create handlers
    log_path = os.path.join("logs", "faucet_bot.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    file_handler = CompressedRotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )

    # Use SafeStreamHandler to prevent Unicode crashes on Windows
    stream_handler = SafeStreamHandler(sys.stdout)

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[file_handler, stream_handler],
    )
