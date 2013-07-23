#!/usr/bin/env python
"""
runtests.py [OPTIONS] [MODULES...]

Run tests in the test rig.

"""
from __future__ import absolute_import, division, print_function

import os
import sys
import argparse
import testrig

CACHE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'cache')

EXTRA_PATH = [
    '/usr/lib/ccache',
    '/usr/local/lib/f90cache'
]

os.environ['PATH'] = os.pathsep.join(EXTRA_PATH + os.environ.get('PATH', '').split(os.pathsep))

def main():
    tests = testrig.get_tests()
    modinfo = "\n  ".join("%-10s -- %s" % (name, info) for name, info in tests)
    usage = __doc__.lstrip()
    usage += "\navailable modules:\n  " + modinfo

    p = argparse.ArgumentParser(usage=usage)
    p.add_argument('--no-clean-build', '-n', action="store_false",
                   dest="clean_build", default=True,
                   help="don't do clean rebuilds")
    p.add_argument('--parallel', '-p', action="store", dest="parallel", type=int,
                   default=1, metavar="N", help="run N tests in parallel")
    p.add_argument('modules', nargs='*', default=[m for m, _ in tests],
                   help="modules to try to run compatibility tests for")
    args = p.parse_args()

    if args.parallel == 1:
        r = []
        for m in args.modules:
            r.append(testrig.run(m, CACHE_DIR, clean_build=args.clean_build))
    else:
        import joblib
        r = joblib.Parallel(n_jobs=args.parallel)(
            joblib.delayed(testrig.run)(m, CACHE_DIR, clean_build=args.clean_build, log_prefix=True)
            for m in args.modules)

    print("\n"
          "Summary\n"
          "-------\n")
    for m, ok in zip(args.modules, r):
        if ok:
            print("- %s: OK" % m)
        else:
            print("- %s: FAIL" % m)

    sys.exit(sum(map(int, r)))

if __name__ == "__main__":
    main()
