#!/usr/bin/env python
"""
runtests.py [MODULE]

Run all tests in the test rig.

"""
from __future__ import absolute_import, division, print_function

import sys
import os
import shutil
import argparse

CACHE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'cache')

EXTRA_PATH = [
    '/usr/lib/ccache',
    '/usr/local/lib/f90cache'
]

os.environ['PATH'] = os.pathsep.join(EXTRA_PATH + os.environ.get('PATH', '').split(os.pathsep))

def main():
    p = argparse.ArgumentParser(usage=__doc__.lstrip())
    p.add_argument('modules', nargs='*',
                   help="modules to try to run compatibility tests for")
    args = p.parse_args()

    env_dir = os.path.join(CACHE_DIR, 'env')
    if os.path.isdir(env_dir):
        shutil.rmtree(env_dir)

    log = os.path.join(CACHE_DIR, 'test.log')
    print("Logging to %r" % (log,), file=sys.stderr)

    import testrig
    testrig.run(args.modules, log=log)

if __name__ == "__main__":
    main()
