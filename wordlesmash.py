#!/usr/bin/env -S python3 -O
import sys
import os

package_dir = os.path.dirname(__file__)
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)
    print("sys.path in wordlesmash.py:", sys.path)

from wordlesmash import __main__

if __name__ == '__main__':
    sys.exit(__main__.main())

