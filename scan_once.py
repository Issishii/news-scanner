"""
scan_once.py
Runs the scanner exactly once and then exits. GitHub Actions calls this on a
schedule. The always-on loop in bot.py is left untouched.
"""

import logging
import storage
import bot  # importing bot does NOT start its loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scan_once")

if __name__ == "__main__":
    log.info("Single scan starting (GitHub Actions schedule).")
    storage.init_db()
    bot.process_once()
    log.info("Single scan finished.")
