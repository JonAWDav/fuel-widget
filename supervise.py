"""Keep the macOS GUI alive after crashes while respecting an intentional stop."""
import fcntl
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state'
STATE.mkdir(exist_ok=True)
logger = logging.getLogger('fuel.supervisor')
logger.setLevel(logging.INFO)
logger.addHandler(RotatingFileHandler(STATE / 'recovery.log', maxBytes=200000, backupCount=2))


def main():
    guard = (STATE / 'supervisor.lock').open('a+')
    try:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    while True:
        if (STATE / 'paused').exists():
            time.sleep(5)
            continue
        process = subprocess.Popen([sys.executable, str(ROOT / 'widget.py')], cwd=ROOT)
        code = process.wait()
        if not (STATE / 'paused').exists():
            logger.warning('Widget exited with code %s. Restarting in 3 seconds.', code)
            time.sleep(3)


if __name__ == '__main__':
    main()
