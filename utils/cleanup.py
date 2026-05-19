import os
import shutil
import logging

logger = logging.getLogger(__name__)


def cleanup_file(filepath: str):
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            logger.info(f"Removed file: {filepath}")
        except Exception as e:
            logger.error(f"Failed to remove {filepath}: {e}")


def cleanup_directory(dirpath: str):
    if os.path.exists(dirpath):
        try:
            shutil.rmtree(dirpath)
            logger.info(f"Removed directory: {dirpath}")
        except Exception as e:
            logger.error(f"Failed to remove directory {dirpath}: {e}")


def cleanup_user_session(session_dir: str):
    if os.path.exists(session_dir):
        cleanup_directory(session_dir)
