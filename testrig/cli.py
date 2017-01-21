#!/usr/bin/env python
"""
testrig [OPTIONS] [TESTS...]

Run tests in the test rig.

"""
from __future__ import absolute_import, division, print_function

import os
import sys
import time
import fnmatch
import argparse
import subprocess
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

from .fixture import get_fixture_cls
from .lockfile import LockFile
from .parser import get_parser
from testrig import __version__

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
    p.add_argument('--version', action="version", version="%(prog)s " + __version__,
                   help="Print program version")
    p.add_argument('tests', nargs='*', default=[], metavar='TESTS',
                   help="Tests to run. Can also be a glob pattern, e.g., '*scipy_dev*'")
    args = p.parse_args()

    # Open log
    cache_dir = os.path.abspath(args.cache_dir)
    try:
        os.makedirs(cache_dir)
    except OSError:
        # probably already exists
        pass

    log_dir = cache_dir
    log_fn = os.path.join(log_dir, 'testrig.log')
    with text_open(log_fn, 'w'):
        pass
    LOG_STREAM = text_open(log_fn, 'a')

    # Grab selected tests
    tests = get_tests(args.config)

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

    try:
        if args.parallel > 0 and joblib is not None:
            jobs = []
            os.environ['NPY_NUM_BUILD_JOBS'] = str(max(1, multiprocessing.cpu_count()//min(len(selected_tests), args.parallel)))
            for t in selected_tests:
                job_cache_dir = os.path.join(cache_dir, 'parallel', t.name)
                jobs.append(joblib.delayed(do_run)(t, job_cache_dir, log_dir, cleanup=args.cleanup, git_cache=args.git_cache, verbose=args.verbose))
            job_results = joblib.Parallel(n_jobs=args.parallel, backend="threading")(jobs)
            results = dict(zip([t.name for t in selected_tests], job_results))
        else:
            if args.parallel:
                print_logged("WARNING: joblib not installed -- parallel run not possible\n")
            os.environ['NPY_NUM_BUILD_JOBS'] = str(multiprocessing.cpu_count())
            for t in selected_tests:
                r = do_run(t, cache_dir, log_dir, cleanup=args.cleanup, git_cache=args.git_cache, verbose=args.verbose)
                results[t.name] = r
    except KeyboardInterrupt:
        print_logged("Interrupted")
        sys.exit(1)

    # Output summary
    msg = "\n\n"
    msg += ("="*79) + "\n"
    msg += "Summary\n"
    msg += ("="*79) + "\n\n"
    ok = True
    for name, entry in sorted(results.items()):
        test_count, fail_new_count, fail_same_count, warn_new_count, warn_same_count = entry

        if fail_new_count < 0 or test_count < 0:
            msg += "- {0}: ERROR\n".format(name)
            ok = False
        elif fail_new_count == 0 and test_count > 0:
            msg += "- {0}: OK (ran {1} tests, {2} pre-existing failures, {3} warnings, {4} pre-existing warnings)\n".format(
                name, test_count, fail_same_count, warn_new_count, warn_same_count)
        else:
            ok = False
            msg += "- {0}: FAIL (ran {1} tests, {2} new failures, {3} pre-existing failures, {4} warnings, {5} pre-existing warnings))\n".format(
                name, test_count, fail_new_count, fail_same_count, warn_new_count, warn_same_count)
    msg += "\n"

    print_logged(msg)

    # Done
    if ok:
        sys.exit(0)
    else:
        sys.exit(1)


def text_open(filename, mode):
    if sys.version_info[0] >= 3:
        return open(filename, mode, encoding='utf-8', errors='replace')
    else:
        return open(filename, mode)


def do_run(test, cache_dir, log_dir, cleanup, git_cache, verbose):
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
        return test.run(cache_dir, log_dir, cleanup, git_cache, verbose)
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

    def get(section, name, default=None):
        if not p.has_option(section, name):
            if p.has_option('DEFAULT', name):
                return p.get('DEFAULT', name)
            if default is not None:
                return default
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
                     get(section, 'parser'),
                     get(section, 'env'),
                     get(section, 'envvars', ''),
                     os.path.abspath(os.path.dirname(config)))
            tests.append(t)
        except (ValueError, configparser.Error) as err:
            print_logged("testrig.ini: section {}: {}".format(section, err))
            sys.exit(1)

    return tests


class Test(object):
    def __init__(self, name, base_install, old_install, new_install, run_cmd, parser, environment,
                 envvars, config_dir):
        self.name = name
        self.base_install = base_install.split()
        self.old_install = old_install.split()
        self.new_install = new_install.split()
        self.run_cmd = run_cmd
        self.parser_name = parser
        self.parser = get_parser(parser)
        self.fixture_cls = get_fixture_cls(environment)
        self.env_name = environment
        self.environ = {}
        for line in envvars.splitlines():
            if not line.strip():
                continue
            if '=' not in line:
                raise ValueError("Invalid envvars line '{0}'".format(line))
            name, value = line.split('=', 1)
            value = value.replace('$DIR', config_dir)
            self.environ[name.strip()] = value

    def print_info(self):
        print_logged(("[{0}]\n"
                      "    base={1}\n"
                      "    old={2}\n"
                      "    new={3}\n"
                      "    run={4}\n"
                      "    parser={5}\n"
                      "    env={6}\n"
                      "    envvars={7}\n"
                      ).format(self.name, " ".join(self.base_install),
                               " ".join(self.old_install), " ".join(self.new_install),
                               self.run_cmd, self.parser_name, self.env_name,
                               "\n    ".join("{0}={1}".format(x, y) for x, y in sorted(self.environ.items()))))

    def run(self, cache_dir, log_dir, cleanup=True, git_cache=True, verbose=False):
        log_old_fn = os.path.join(log_dir, '%s-build-old.log' % self.name)
        log_new_fn = os.path.join(log_dir, '%s-build-new.log' % self.name)

        test_log_old_fn = os.path.join(log_dir, '%s-test-old.log' % self.name)
        test_log_new_fn = os.path.join(log_dir, '%s-test-new.log' % self.name)

        # Launch a thread that prints some output as long as something is
        # running, as long as that something produces output.
        wait_printer = WaitPrinter()
        wait_printer.start()

        test_count = []
        failures = []
        warns = []

        for log_fn, test_log_fn, install in ((log_old_fn, test_log_old_fn, self.old_install),
                                             (log_new_fn, test_log_new_fn, self.new_install)):
            log = text_open(log_fn, 'w')
            fixture = self.fixture_cls(cache_dir, log, print_logged=print_logged,
                                       cleanup=cleanup, git_cache=git_cache, verbose=verbose,
                                       extra_env=self.environ)
            try:
                # Run virtualenv setup + builds
                wait_printer.set_log_file(log_fn)
                try:
                    print_logged("{0}: setting up {1} at {2}...".format(
                        self.name, fixture.name, os.path.relpath(fixture.env_dir)))
                    fixture.setup()
                    print_logged("{0}: building (logging to {1})...".format(self.name, os.path.relpath(log_fn)))
                    fixture.install_spec(install + self.base_install)
                except BaseException as exc:
                    with text_open(log_fn, 'r') as f:
                        msg = "{0}: ERROR: build failed: {1}\n".format(self.name, str(exc))
                        msg += "    " + f.read().replace("\n", "\n    ")
                        print_logged(msg)

                    if not isinstance(exc, (subprocess.CalledProcessError, OSError)):
                        raise

                    if log_fn.endswith('-old.log'):
                        test_count.append(-1)
                        failures.append({})
                        warns.append({})
                        continue
                    else:
                        return -1, -1, -1, -1, -1

                info = fixture.get_info()
                fixture.print("{0}: installed {1}".format(self.name, info))

                # Run tests
                fixture.print("{0}: running tests (logging to {1})...".format(self.name, os.path.relpath(test_log_fn)))
                with text_open(test_log_fn, 'w') as f:
                    wait_printer.set_log_file(test_log_fn)
                    fixture.run_test_cmd(self.run_cmd, log=f)

                # Parse test results
                with text_open(test_log_fn, 'r') as f:
                    data = f.read()
                    fail, warn, count, err_msg = self.parser(data, os.path.join(cache_dir, 'env'))
                    test_count.append(count)
                    failures.append(fail)
                    warns.append(warn)

                    if err_msg is not None:
                        msg = "{0}: ERROR: failed to parse test output\n".format(self.name)
                        msg += "{0}: {1}\n".format(self.name, err_msg)
                        msg += "    " + data.replace("\n", "\n    ")
                        print_logged(msg)
                    continue
            finally:
                wait_printer.set_log_file(None)
                fixture.teardown()
                log.close()

        wait_printer.stop()

        fail_new_count, fail_same_count = self.check(failures, verbose, type_str="failures")
        warn_new_count, warn_same_count = self.check(warns, verbose, type_str="warnings")

        return test_count[1], fail_new_count, fail_same_count, warn_new_count, warn_same_count

    def check(self, items, verbose, type_str="failures"):
        old, new = items

        old_set = set(old.keys())
        new_set = set(new.keys())

        added_set = new_set - old_set
        same_set = new_set.intersection(old_set)

        msg = ""
        
        if same_set and verbose:
            msg += "\n\n\n"
            msg += "="*79 + "\n"
            msg += "{0}: pre-existing {1}\n".format(self.name, type_str)
            msg += "="*79 + "\n"

            for k in sorted(same_set):
                msg += new[k] + "\n"

        if added_set:
            msg += "\n\n\n"
            msg += "="*79 + "\n"
            msg += "{0}: new {1}\n".format(self.name, type_str)
            msg += "="*79 + "\n"

            for k in sorted(added_set):
                msg += new[k] + "\n"

        print_logged(msg)

        return len(added_set), len(same_set)
        

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
