#!/usr/bin/env python
"""
runtests.py [OPTIONS] [TESTS...]

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
    test_info = "\n  ".join("%-16s -- %s" % (name, t.info)
                            for name, t in sorted(tests.items()))
    usage = __doc__.lstrip()
    usage += "\navailable tests:\n  " + test_info

    # Parse arguments
    p = argparse.ArgumentParser(usage=usage)
    p.add_argument('--no-cleanup', '-n', action="store_false",
                   dest="cleanup", default=True,
                   help="don't clean up before or after")
    p.add_argument('--parallel', '-p', action="store", dest="parallel",
                   type=int, default=1, metavar="N",
                   help="run N tests in parallel")
    p.add_argument('tests', nargs='*', default=None, help="tests to run")
    args = p.parse_args()

    # Grab selected tests
    if args.tests is None:
        selected_tests = tests.values()
    else:
        selected_tests = []
        for name in args.tests:
            try:
                selected_tests.append(tests[name])
            except KeyError:
                p.error("No test %r exists" % (name,))

    # Run
    if args.parallel == 1:
        r = []
        for t in selected_tests:
            r.append(testrig.run(t, CACHE_DIR, cleanup=args.cleanup))
    else:
        import joblib
        r = joblib.Parallel(n_jobs=args.parallel)(
            joblib.delayed(testrig.run)(t, CACHE_DIR, cleanup=args.cleanup, log_prefix=True)
            for t in selected_tests)

    # Output summary
    print("\n"
          "Summary\n"
          "-------\n")
    for m, ok in zip(args.modules, r):
        if ok:
            print("- %s: OK" % m)
        else:
            print("- %s: FAIL" % m)
    print("")

    # Done.
    sys.exit(sum(map(int, r)))

if __name__ == "__main__":
    main()
