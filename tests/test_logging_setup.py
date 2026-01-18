import pytest
import logging
import os
import gzip
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.logging_setup import CompressedRotatingFileHandler, setup_logging


class TestCompressedRotatingFileHandler:
    """Test suite for CompressedRotatingFileHandler."""
    
    def test_rotation_filename(self):
        """Test that rotation_filename returns correct .gz filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            handler = CompressedRotatingFileHandler(log_file, maxBytes=1024, backupCount=3)
            try:
                result = handler.rotation_filename("test.log.1")
                assert result == "test.log.1.gz"
                
                result = handler.rotation_filename("/path/to/file.log.2")
                assert result == "/path/to/file.log.2.gz"
            finally:
                handler.close()
    
    def test_rotate_compresses_file(self):
        """Test that rotate() compresses source file and removes original."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "source.log")
            dest_file = os.path.join(tmpdir, "dest.log.gz")
            
            # Create source file with content
            test_content = b"Test log content\nLine 2\nLine 3\n"
            with open(source_file, 'wb') as f:
                f.write(test_content)
            
            # Create handler and rotate
            log_file = os.path.join(tmpdir, "test.log")
            handler = CompressedRotatingFileHandler(log_file, maxBytes=1024, backupCount=3)
            try:
                handler.rotate(source_file, dest_file)
                
                # Verify source is removed
                assert not os.path.exists(source_file)
                
                # Verify dest exists and is compressed
                assert os.path.exists(dest_file)
                
                # Verify content is correct after decompression
                with gzip.open(dest_file, 'rb') as f:
                    decompressed = f.read()
                assert decompressed == test_content
            finally:
                handler.close()
    
    def test_rotate_creates_valid_gzip(self):
        """Test that rotated files are valid gzip archives."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "source.log")
            dest_file = os.path.join(tmpdir, "dest.log.gz")
            
            # Create source with multi-line content
            lines = [f"Log line {i}\n" for i in range(100)]
            with open(source_file, 'w') as f:
                f.writelines(lines)
            
            log_file = os.path.join(tmpdir, "test.log")
            handler = CompressedRotatingFileHandler(log_file, maxBytes=1024, backupCount=3)
            try:
                handler.rotate(source_file, dest_file)
                
                # Verify it's a valid gzip file
                with gzip.open(dest_file, 'rt') as f:
                    decompressed_lines = f.readlines()
                
                assert decompressed_lines == lines
            finally:
                handler.close()


class TestSetupLogging:
    """Test suite for setup_logging function."""
    
    def test_setup_logging_default_level(self):
        """Test setup_logging with default INFO level."""
        # Clear handlers before test
        logging.getLogger().handlers.clear()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                with patch('logging.basicConfig') as mock_basic_config:
                    setup_logging()
                    
                    # Verify basicConfig was called with INFO level
                    mock_basic_config.assert_called_once()
                    call_kwargs = mock_basic_config.call_args[1]
                    assert call_kwargs['level'] == logging.INFO
            finally:
                os.chdir(original_dir)
                logging.shutdown()
                for h in logging.getLogger().handlers[:]:
                    h.close()
                    logging.getLogger().removeHandler(h)
                logging.getLogger().handlers.clear()
    
    def test_setup_logging_custom_level(self):
        """Test setup_logging with custom log level."""
        logging.getLogger().handlers.clear()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Test DEBUG level
                with patch('logging.basicConfig') as mock_basic_config:
                    setup_logging("DEBUG")
                    call_kwargs = mock_basic_config.call_args[1]
                    assert call_kwargs['level'] == logging.DEBUG
            finally:
                os.chdir(original_dir)
                logging.shutdown()
                for h in logging.getLogger().handlers[:]:
                    h.close()
                    logging.getLogger().removeHandler(h)
                logging.getLogger().handlers.clear()
    
    def test_setup_logging_invalid_level_defaults_to_info(self):
        """Test that invalid log level defaults to INFO."""
        logging.getLogger().handlers.clear()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                with patch('logging.basicConfig') as mock_basic_config:
                    setup_logging("INVALID_LEVEL")
                    call_kwargs = mock_basic_config.call_args[1]
                    assert call_kwargs['level'] == logging.INFO
            finally:
                os.chdir(original_dir)
                logging.shutdown()
                for h in logging.getLogger().handlers[:]:
                    h.close()
                    logging.getLogger().removeHandler(h)
                logging.getLogger().handlers.clear()
    
    def test_setup_logging_creates_two_handlers(self):
        """Test that setup_logging creates file and stream handlers."""
        logging.getLogger().handlers.clear()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                with patch('logging.basicConfig') as mock_basic_config:
                    setup_logging()
                    
                    # Verify basicConfig was called with 2 handlers
                    call_kwargs = mock_basic_config.call_args[1]
                    assert 'handlers' in call_kwargs
                    assert len(call_kwargs['handlers']) == 2
            finally:
                os.chdir(original_dir)
                logging.shutdown()
                for h in logging.getLogger().handlers[:]:
                    h.close()
                    logging.getLogger().removeHandler(h)
                logging.getLogger().handlers.clear()
    
    def test_setup_logging_format(self):
        """Test that logging format is correctly configured."""
        logging.getLogger().handlers.clear()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                with patch('logging.basicConfig') as mock_basic_config:
                    setup_logging()
                    
                    # Verify format string contains expected elements
                    call_kwargs = mock_basic_config.call_args[1]
                    format_str = call_kwargs['format']
                    assert '%(asctime)s' in format_str
                    assert '%(levelname)s' in format_str
                    assert '%(name)s' in format_str
                    assert '%(message)s' in format_str
            finally:
                os.chdir(original_dir)
                logging.shutdown()
                for h in logging.getLogger().handlers[:]:
                    h.close()
                    logging.getLogger().removeHandler(h)
                logging.getLogger().handlers.clear()
    

