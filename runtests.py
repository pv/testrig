#!/usr/bin/env python
"""
runtests.py [MODULE]

Run all tests in the test rig.

"""

import os
import shutil
import argparse

CACHE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'cache')

def main():
    p = argparse.ArgumentParser(usage=__doc__.lstrip())
    args = p.parse_args()

    env_dir = os.path.join(CACHE_DIR, 'env')
    if os.path.isdir(env_dir):
        shutil.rmtree(env_dir)

    import testrig
    testrig.run_all()

if __name__ == "__main__":
    main()
