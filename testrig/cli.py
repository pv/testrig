#!/usr/bin/env python
"""
run.py [OPTIONS] [TESTS...]

Run tests in the test rig.

"""
from __future__ import absolute_import, division, print_function

import os
import sys
import io
import time
import fnmatch
import argparse
import threading
import multiprocessing

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

try:
    import joblib
except ImportError:
    joblib = None

from .fixture import Fixture
from .lockfile import LockFile
from .parser import get_parser


EXTRA_PATH = [
    '/usr/lib/ccache',
    '/usr/local/lib/f90cache'
]

LOG_STREAM = None
LOG_LOCK = multiprocessing.Lock()


def main():
    global LOG_STREAM

    # Parse arguments
    p = argparse.ArgumentParser(usage=__doc__.lstrip())
    p.add_argument('--no-git-cache', '-g', action="store_false",
                   dest="git_cache", default=True,
                   help="don't cache git repositories")
    p.add_argument('--no-cleanup', '-n', action="store_false",
                   dest="cleanup", default=True,
                   help="don't clean up afterward")
    p.add_argument('--config', action="store",
                   dest="config", default='testrig.ini',
                   help="configuration file")
    p.add_argument('--cache', action="store",
                   dest="cache_dir", default='cache',
                   help="cache directory")
    p.add_argument('--parallel', '-j', action="store", type=int, nargs='?',
                   metavar='NUM_PROC',
                   dest="parallel", default=0, const=-1,
                   help="build and run tests in parallel")
    p.add_argument('--verbose', '-v', action="store_true",
                   dest="verbose", help="be more verbose")
    p.add_argument('tests', nargs='*', default=[], metavar='TESTS',
                   help="Tests to run. Can also be a glob pattern, e.g., '*scipy_dev*'")
    args = p.parse_args()

    tests = get_tests(args.config)

    # Grab selected tests
    if not args.tests:
        selected_tests = tests
    else:
        selected_tests = []
        for t in tests:
            for sel in args.tests:
                if fnmatch.fnmatch(t.name, sel):
                    selected_tests.append(t)
                    break

    if not selected_tests:
        p.error('no tests to run')

    # Open log
    cache_dir = os.path.abspath(args.cache_dir)
    try:
        os.makedirs(cache_dir)
    except OSError:
        # probably already exists
        pass

    log_fn = os.path.join(cache_dir, 'testrig.log')
    with open(log_fn, 'wb'):
        pass
    LOG_STREAM = open(log_fn, 'a')

    # Run
    set_extra_env()

    if not EXTRA_PATH[0]:
        print_logged("WARNING: ccache is not available -- this is going to be slow\n")

    for t in selected_tests:
        t.print_info()

    print_logged("Logging to: {0}\n".format(os.path.relpath(log_fn)))

    results = {}

    if args.parallel < 0:
        args.parallel = multiprocessing.cpu_count() + 1 + args.parallel

    if args.parallel > 0 and joblib is not None:
        jobs = []
        os.environ['NPY_NUM_BUILD_JOBS'] = str(max(1, multiprocessing.cpu_count()//min(len(selected_tests), args.parallel)))
        for t in selected_tests:
            job_cache_dir = os.path.join(cache_dir, 'parallel', t.name)
            jobs.append(joblib.delayed(do_run)(t, job_cache_dir, cleanup=args.cleanup, git_cache=args.git_cache, verbose=args.verbose))
        job_results = joblib.Parallel(n_jobs=args.parallel, backend="threading")(jobs)
        results = dict(zip([t.name for t in selected_tests], job_results))
    else:
        if args.parallel:
            print_logged("WARNING: joblib not installed -- parallel run not possible\n")
        os.environ['NPY_NUM_BUILD_JOBS'] = str(multiprocessing.cpu_count())
        for t in selected_tests:
            r = do_run(t, cache_dir, cleanup=args.cleanup, git_cache=args.git_cache, verbose=args.verbose)
            results[t.name] = r

    # Output summary
    msg = "\n\n"
    msg += ("="*79) + "\n"
    msg += "Summary\n"
    msg += ("="*79) + "\n\n"
    ok = True
    for name, entry in sorted(results.items()):
        num, num_new_fail, num_old_fail = entry
        if num_new_fail == 0:
            msg += "- {0}: OK (ran {1} tests, {2} pre-existing failures)\n".format(name, num, num_old_fail)
        elif num_new_fail < 0:
            msg += "- {0}: ERROR\n".format(name)
            ok = False
        else:
            ok = False
            msg += "- {0}: FAIL (ran {1} tests, {2} new failures, {3} pre-existing failures)\n".format(name, num, num_new_fail, num_old_fail)
    msg += "\n"

    print_logged(msg)

    # Done
    if ok:
        sys.exit(0)
    else:
        sys.exit(1)


def do_run(test, cache_dir, cleanup, git_cache, verbose):
    cache_dir = os.path.abspath(cache_dir)
    try:
        os.makedirs(cache_dir)
    except OSError:
        # probably already exists
        pass

    lock = LockFile(os.path.join(cache_dir, 'lock'))
    ok = lock.acquire(block=False)
    if not ok:
        print_logged("ERROR: another process is already using the cache directory '{0}'".format(os.path.relpath(cache_dir)))
        sys.exit(1)
    try:
        return test.run(cache_dir, cleanup, git_cache, verbose)
    finally:
        lock.release()


def print_logged(*a):
    assert LOG_STREAM is not None
    with LOG_LOCK:
        print(*a)
        sys.stdout.flush()
        print(*a, file=LOG_STREAM)
        LOG_STREAM.flush()


def set_extra_env():
    os.environ['PATH'] = os.pathsep.join(EXTRA_PATH + os.environ.get('PATH', '').split(os.pathsep))


def get_tests(config):
    """
    Parse testrig.ini and return a list of Test objects.
    """
    p = configparser.RawConfigParser()
    if not p.read(config):
        print_logged("ERROR: configuration file {0} not found".format(config))
        sys.exit(1)

    tests = []

    def get(section, name):
        if not p.has_option(section, name):
            if p.has_option('DEFAULT', name):
                return p.get('DEFAULT', name)
        return p.get(section, name)

    for section in p.sections():
        if section == 'DEFAULT':
            continue

        try:
            t = Test(section,
                     get(section, 'base'),
                     get(section, 'old'),
                     get(section, 'new'),
                     get(section, 'run'),
                     get(section, 'parser'))
            tests.append(t)
        except (ValueError, configparser.Error) as err:
            print_logged("testrig.ini: section {}: {}".format(section, err))
            sys.exit(1)

    return tests


class Test(object):
    def __init__(self, name, base_install, old_install, new_install, run_cmd, parser):
        self.name = name
        self.base_install = base_install.split()
        self.old_install = old_install.split()
        self.new_install = new_install.split()
        self.run_cmd = run_cmd
        self.parser_name = parser
        self.parser = get_parser(parser)

    def print_info(self):
        print_logged(("[{0}]\n"
                      "    base={1}\n"
                      "    old={2}\n"
                      "    new={3}\n"
                      "    run={4}\n"
                      "    parser={5}\n"
                      ).format(self.name, " ".join(self.base_install),
                               " ".join(self.old_install), " ".join(self.new_install),
                               self.run_cmd, self.parser_name))

    def run(self, cache_dir, cleanup=True, git_cache=True, verbose=False):
        log_old_fn = os.path.join(cache_dir, '%s-build-old.log' % self.name)
        log_new_fn = os.path.join(cache_dir, '%s-build-new.log' % self.name)

        test_log_old_fn = os.path.join(cache_dir, '%s-test-old.log' % self.name)
        test_log_new_fn = os.path.join(cache_dir, '%s-test-new.log' % self.name)

        # Launch a thread that prints some output as long as something is
        # running, as long as that something produces output.
        wait_printer = WaitPrinter()
        wait_printer.start()

        test_count = []
        failures = []

        for log_fn, test_log_fn, install in ((log_old_fn, test_log_old_fn, self.old_install),
                                             (log_new_fn, test_log_new_fn, self.new_install)):
            fixture = Fixture(cache_dir, log_fn, print_logged=print_logged,
                              cleanup=cleanup, git_cache=git_cache, verbose=verbose)
            try:
                wait_printer.set_log_file(log_fn)
                try:
                    print_logged("{0}: setting up virtualenv at {1}...".format(
                        self.name, os.path.relpath(fixture.env_dir)))
                    fixture.setup()
                    print_logged("{0}: building (logging to {1})...".format(self.name, os.path.relpath(log_fn)))
                    fixture.install_spec(install)
                    fixture.install_spec(self.base_install)
                except:
                    with open(log_fn, 'rb') as f:
                        msg = "{0}: ERROR: build failed\n".format(self.name)
                        msg += "    " + f.read().replace("\n", "\n    ")
                        print_logged(msg)
                    return -1, -1, -1

                fixture.print("{0}: running tests (logging to {1})...".format(self.name, os.path.relpath(test_log_fn)))
                with open(test_log_fn, 'wb') as f:
                    wait_printer.set_log_file(test_log_fn)
                    fixture.run_test_cmd(self.run_cmd, log=f)

                # Parse result
                with io.open(test_log_fn, 'r', encoding='utf-8', errors='replace') as f:
                    data = f.read()
                    fail, count, err_msg = self.parser(data, os.path.join(cache_dir, 'env'))
                    test_count.append(count)
                    failures.append(fail)

                    if err_msg is not None:
                        msg = "{0}: ERROR: failed to parse test output\n".format(self.name)
                        msg += "{0}: {1}\n".format(self.name, err_msg)
                        msg += "    " + data.replace("\n", "\n    ")
                        print_logged(msg)
                        return -1, -1, -1
            finally:
                wait_printer.set_log_file(None)
                fixture.teardown()

        wait_printer.stop()

        return self.check(failures, test_count, verbose)

    def check(self, failures, test_count, verbose):
        old, new = failures

        old_set = set(old.keys())
        new_set = set(new.keys())

        added_set = new_set - old_set
        same_set = new_set.intersection(old_set)

        msg = ""
        
        if same_set and verbose:
            msg += "\n\n\n"
            msg += "="*79 + "\n"
            msg += "{0}: pre-existing failures\n".format(self.name)
            msg += "="*79 + "\n"

            for k in sorted(same_set):
                msg += new[k] + "\n"

        if added_set:
            msg += "\n\n\n"
            msg += "="*79 + "\n"
            msg += "{0}: new failures\n".format(self.name)
            msg += "="*79 + "\n"

            for k in sorted(added_set):
                msg += new[k]

        print_logged(msg)

        return test_count[1], len(added_set), len(same_set)
        

class WaitPrinter(object):
    def __init__(self):
        self.log_file = None
        self.waiting = False
        self.last_time = 0
        self.last_log_size = 0
        self.thread = None

    def set_log_file(self, log_file):
        self.last_time = time.time()
        self.last_log_size = 0
        self.log_file = log_file

    def start(self):
        if self.thread is not None:
            return

        self.waiting = True
        self.last_time = time.time()
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.waiting = False

    def _run(self):
        while self.waiting:
            time.sleep(61)
            if time.time() - self.last_time >= 60:
                self.last_time = time.time()
                try:
                    size = os.stat(self.log_file).st_size
                except (TypeError, OSError):
                    continue
                if size > self.last_log_size:
                    print("    ... still running", file=sys.stderr)
                    sys.stderr.flush()
                self.last_log_size = size


if __name__ == "__main__":
    main()
