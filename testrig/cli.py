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

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

from .fixture import Fixture
from .lockfile import LockFile
from .parser import get_parser


CACHE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'cache')

EXTRA_PATH = [
    '/usr/lib/ccache',
    '/usr/local/lib/f90cache'
]


def main():
    # Parse arguments
    p = argparse.ArgumentParser(usage=__doc__.lstrip())
    p.add_argument('--no-git-cache', '-g', action="store_false",
                   dest="git_cache", default=True,
                   help="don't cache git repositories")
    p.add_argument('--no-cleanup', '-n', action="store_false",
                   dest="cleanup", default=True,
                   help="don't clean up before or after")
    p.add_argument('--config', action="store",
                   dest="config", default='testrig.ini',
                   help="configuration file")
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

    # Run
    set_extra_env()

    if not EXTRA_PATH[0]:
        print("WARNING: ccache is not available -- this is going to be slow\n")

    cache_dir = CACHE_DIR
    try:
        os.makedirs(cache_dir)
    except OSError:
        # probably already exists
        pass

    results = []

    lock = LockFile(os.path.join(cache_dir, 'lock'))
    with lock:
        for t in selected_tests:
            r = t.run(CACHE_DIR, cleanup=args.cleanup, git_cache=args.git_cache)
            results.append(r)

    # Output summary
    msg = ""
    msg += ("="*79) + "\n"
    msg += "Summary\n"
    msg += ("="*79) + "\n"
    print(msg)
    ok = True
    for t, entry in zip(selected_tests, results):
        num, num_new_fail, num_old_fail = entry
        if num_new_fail == 0:
            print("- {0}: OK (ran {1} tests, {2} old failures)".format(t.name, num, num_old_fail))
            ok = False
        else:
            print("- {0}: FAIL (ran {1} tests, {2} new failures, {3} old failures)".format(t.name, num, num_new_fail, num_old_fail))
    print("")

    # Done
    if ok:
        sys.exit(0)
    else:
        sys.exit(1)


def set_extra_env():
    os.environ['PATH'] = os.pathsep.join(EXTRA_PATH + os.environ.get('PATH', '').split(os.pathsep))


def get_tests(config):
    """
    Parse testrig.ini and return a list of Test objects.
    """
    p = configparser.RawConfigParser()
    if not p.read(config):
        print("ERROR: configuration file {0} not found".format(config))
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
            print("testrig.ini: section {}: {}".format(section, err))
            sys.exit(1)

    return tests


class Test(object):
    def __init__(self, name, base_install, old_install, new_install, run_cmd, parser):
        self.name = name
        self.base_install = base_install.split()
        self.old_install = old_install.split()
        self.new_install = new_install.split()
        self.run_cmd = run_cmd
        self.parser = get_parser(parser)


    def run(self, cache_dir, cleanup=True, git_cache=True):
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

        msg = ""
        msg += "="*79 + "\n"
        msg += "{0}: running".format(self.name) + "\n"
        msg += "="*79 + "\n"
        print(msg, file=sys.stderr)

        for log_fn, test_log_fn, install in ((log_old_fn, test_log_old_fn, self.old_install),
                                             (log_new_fn, test_log_new_fn, self.new_install)):
            fixture = Fixture(cache_dir, log_fn,
                              cleanup=cleanup, git_cache=git_cache)
            fixture.print("Logging into: {0}".format(os.path.relpath(log_fn)))
            try:
                wait_printer.set_log_file(log_fn)
                try:
                    fixture.setup()
                    fixture.install_spec(install)
                    fixture.install_spec(self.base_install)
                except:
                    with open(log_fn, 'rb') as f:
                        print(f.read(), file=sys.stderr)
                    raise

                fixture.print("Logging into: {0}".format(os.path.relpath(test_log_fn)))
                with open(test_log_fn, 'wb') as f:
                    wait_printer.set_log_file(test_log_fn)
                    fixture.run_test_cmd(self.run_cmd, log=f)
            finally:
                wait_printer.set_log_file(None)
                fixture.teardown()

            with io.open(test_log_fn, 'r', encoding='utf-8', errors='replace') as f:
                data = f.read()
                fail, count = self.parser(data, os.path.join(cache_dir, 'env'))
                test_count.append(count)
                failures.append(fail)

                if count < 0:
                    print("ERROR: failed to parse test output", file=sys.stderr)
                    print(data, file=sys.stderr)

        wait_printer.stop()

        return self.check(failures, test_count)

    def check(self, failures, test_count):
        old, new = failures

        old_set = set(old.keys())
        new_set = set(new.keys()) - old_set

        if old:
            print("\n\n")
            print("="*79)
            print("{0}: old failures".format(self.name))
            print("="*79)

            for name, msg in sorted(old.items()):
                print(msg)

        if new_set:
            print("\n\n")
            print("="*79)
            print("{0}: new failures".format(self.name))
            print("="*79)

            for k in sorted(new_set):
                print(new[k])

        return test_count[1], len(new_set), len(old)
        

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
