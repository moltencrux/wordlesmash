#!/usr/bin/env -S python3 -O
import sys
import os
import logging
from wordlesmash.lazy_handler import LazyRotatingFileHandler

def setup_logger(prefix, name=None):
    pid = os.getpid()
    log_file = f"log_{pid}.log"
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    handler = LazyRotatingFileHandler(tmpdir_prefix=prefix + '.', basename=log_file, maxBytes=10*(1024 ** 2), backupCount=3)
    logger.addHandler(handler)
    stderr_handler = logging.StreamHandler(sys.stderr)
    logger.addHandler(stderr_handler)
    return logger

logger = setup_logger('wordlesmash')

package_dir = os.path.dirname(__file__)
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)
    print("sys.path in wordlesmash.py:", sys.path)

from wordlesmash import __main__

if __name__ == '__main__':
    sys.exit(__main__.main())

