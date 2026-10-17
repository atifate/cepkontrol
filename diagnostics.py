"""Small local connection log; no screens, messages, addresses or credentials."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

def configure_logging():
    try:
        directory = Path(os.environ.get('APPDATA', str(Path.home()))) / 'AcikDestek'
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory/'connection.log', maxBytes=256000, backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        logger = logging.getLogger('acikdestek')
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    except OSError:
        pass
