from __future__ import absolute_import, division, print_function

import sys
import os
import shutil
import tempfile
import textwrap
import subprocess
import virtualenv
import pkgutil
import multiprocessing

PARALLEL_LOCK = multiprocessing.Lock()

class Fixture(object):
    """
    Fixture for running test suites.

    Methods
    -------
    run_cmd
    run_python_code
    run_python_script
    run_pip
    run_numpytest
    pip_install
    git_install
    get_repo
    print
    print_header
    setup
    teardown

    """

    def __init__(self, name, cache_dir, log_fn,
                 repo_cache_dir,
                 download_cache_dir,
                 cleanup=True, log_prefix=False):
        self.name = name
        self.log = open(log_fn, 'wb')
        self.log_fn = log_fn
        self.log_prefix = log_prefix
        self.cleanup = cleanup
        self.repo_cache_dir = repo_cache_dir

        self.cache_dir = cache_dir
        self.download_dir = download_cache_dir
        self.env_dir = os.path.join(cache_dir, 'env')
        self.code_dir = os.path.join(cache_dir, 'code')

    def setup(self):
        for d in (self.download_dir, self.code_dir):
            if not os.path.isdir(d):
                os.makedirs(d)

        if os.path.isdir(self.env_dir):
            shutil.rmtree(self.env_dir)

        virtualenv.create_environment(self.env_dir)

    def teardown(self):
        if self.cleanup:
            if os.path.isdir(self.cache_dir):
                shutil.rmtree(self.cache_dir)

    def run_python_code(self, code):
        tmpd = os.path.abspath(tempfile.mkdtemp())
        cwd = os.getcwd()
        try:
            fn = os.path.join(tmpd, 'run.py')
            with open(fn, 'w') as f:
                f.write(code)
            os.chdir(tmpd)
            self.print(("$ cat <<__EOF__ > %s\n" % fn) + code + "\n__EOF__")
            self.run_python_script([fn])
        finally:
            shutil.rmtree(tmpd)
            os.chdir(cwd)

    def run_python_script(self, cmd, **kwargs):
        cmd = [os.path.join(self.env_dir, 'bin', 'python')] + cmd
        self.run_cmd(cmd, **kwargs)

    def run_cmd(self, cmd, **kwargs):
        msg = (' '.join(x if ' ' not in x else '"%s"' % x.replace('"', '\\"') for x in cmd))
        if 'cwd' in kwargs:
            msg = '(cd %r && %s)' % (kwargs['cwd'], msg)
        msg = '$ ' + msg

        self.print(msg)

        p = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT,
                             **kwargs)
        try:
            p.communicate()
            if p.returncode != 0:
                raise RuntimeError("Failed to run %r (see log)" % (cmd,))
        except:
            if p.returncode is None:
                p.terminate()
            raise

    def run_pip(self, cmd):
        cmd = [os.path.join(self.env_dir, 'bin', 'pip')] + cmd
        return self.run_python_script(cmd)

    def run_numpytest(self, module):
        self.run_python_code(textwrap.dedent("""
        import sys
        import %s as t
        sys.exit(int(not t.test('full').wasSuccessful()))
        """) % (module,))

    def pip_install(self, requirements):
        parts = [x.strip() for x in requirements.splitlines()
                 if x.strip()]

        PARALLEL_LOCK.acquire()
        try:
            self.run_pip(['install', '--use-mirrors', '--download-cache', self.download_dir] + parts)
        finally:
            PARALLEL_LOCK.release()

    def git_install(self, srcs, setup_py=None):
        for module, src_repo, branch in srcs:
            self._git_install_one(module, src_repo, branch)

    def _git_install_one(self, module, src_repo, branch, setup_py=None):
        if setup_py is None:
            setup_py = 'setup.py'

        repo = self.get_repo(module)
        cached_repo = self.get_cached_repo(module)

        PARALLEL_LOCK.acquire()
        try:
            if not os.path.isdir(cached_repo):
                self.run_cmd(['git', 'clone', '--bare', src_repo, cached_repo])
            else:
                self.run_cmd(['git', 'fetch', src_repo], cwd=cached_repo)
        finally:
            PARALLEL_LOCK.release()

        if not os.path.isdir(repo):
            self.run_cmd(['git', 'clone', '--reference', cached_repo, src_repo, repo])
        else:
            self.run_cmd(['git', 'fetch', 'origin'], cwd=repo)

        self.run_cmd(['git', 'reset', '--hard', branch], cwd=repo)
        if self.cleanup:
            self.run_cmd(['git', 'clean', '-f', '-d', '-x'], cwd=repo)

        self.run_python_script([setup_py, 'install'], cwd=repo)

    def get_repo(self, module):
        return os.path.join(self.code_dir, module)

    def get_cached_repo(self, module):
        return os.path.join(self.repo_cache_dir, module)

    def print_header(self):
        msg = ""
        msg += ("-"*79) + "\n"
        msg += ("Running test: %s" % self.name) + "\n"
        msg += ("-"*79) + "\n"
        msg += "Logging into: %r\n" % self.log_fn
        
        self.print(msg)

    def print(self, msg):
        if self.log_prefix:
            prefix = self.name + ": "
            out_msg = prefix + msg.replace("\n", "\n" + prefix)
            print(out_msg, file=sys.stderr)
        else:
            print(msg, file=sys.stderr)
        sys.stderr.flush()
        if self.log is not sys.stderr:
            print(msg, file=self.log)
            self.log.flush()


class Test(object):
    def __init__(self, name, func):
        self.func = func
        self.name = name
        if hasattr(func, '__doc__') and func.__doc__:
            self.info = textwrap.dedent(func.__doc__).strip()
        else:
            self.info = ""


def get_tests(selection=None):
    tests = {}

    import testrig
    path = testrig.__path__
    for importer, modname, ispkg in pkgutil.iter_modules(path):
        if not modname.startswith('test_'):
            continue

        fullmodname = 'testrig.' + modname
        mod = __import__(fullmodname, fromlist='x')

        for name in dir(mod):
            if not name.startswith('test_'):
                continue
            obj = getattr(mod, name)
            if not callable(obj):
                continue
            
            test_name = modname[5:] + '-' + name[5:]
            tests[test_name] = Test(test_name, obj)

    return tests


def run(test, base_dir, cleanup=True, log_prefix=False):
    cache_dir = os.path.join(base_dir, 'tests', test.name)
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)

    repo_cache_dir = os.path.join(base_dir, 'git-cache')
    try:
        os.makedirs(repo_cache_dir)
    except OSError:
        # probably already exists
        pass

    download_cache_dir = os.path.join(base_dir, 'download-cache')
    try:
        os.makedirs(download_cache_dir)
    except OSError:
        # probably already exists
        pass

    log_fn = os.path.join(base_dir, 'test-%s.log' % test.name)
    fixture = Fixture(test.name,
                      cache_dir=cache_dir, log_fn=log_fn,
                      cleanup=cleanup,
                      log_prefix=log_prefix,
                      repo_cache_dir=repo_cache_dir,
                      download_cache_dir=download_cache_dir)
    fixture.print_header()
    try:
        fixture.setup()
        try:
            test.func(fixture)
            fixture.print("OK")
            return True
        except BaseException as exc:
            import traceback
            fixture.print(traceback.format_exc())
            if isinstance(exc, AssertionError):
                fixture.print("FAILURE")
                return False
            else:
                fixture.print("ERROR")
                return False
    finally:
        fixture.teardown()
