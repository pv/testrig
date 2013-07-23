from __future__ import absolute_import, division, print_function

import sys
import os
import shutil
import tempfile
import textwrap
import subprocess
import virtualenv
import pkgutil

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

    def __init__(self, name, cache_dir, log_fn, clean_build=True, log_prefix=False):
        self.name = name
        self.log = open(log_fn, 'wb')
        self.log_fn = log_fn
        self.log_prefix = log_prefix
        self.clean_build = clean_build
        self.download_dir = os.path.join(cache_dir, 'download')
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
        pass

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
        self.run_pip(['install', '--use-mirrors', '--download-cache', self.download_dir] + parts)

    def git_install(self, srcs, setup_py=None):
        for module, src_repo, branch in srcs:
            self._git_install_one(module, src_repo, branch)

    def _git_install_one(self, module, src_repo, branch, setup_py=None):
        if setup_py is None:
            setup_py = 'setup.py'

        repo = self.get_repo(module)

        if not os.path.isdir(repo):
            self.run_cmd(['git', 'clone', src_repo, repo])

        self.run_cmd(['git', 'fetch', 'origin'], cwd=repo)
        self.run_cmd(['git', 'reset', '--hard', 'origin/' + branch], cwd=repo)
        if self.clean_build:
            self.run_cmd(['git', 'clean', '-f', '-d', '-x'], cwd=repo)

        self.run_python_script([setup_py, 'install'], cwd=repo)

    def get_repo(self, module):
        return os.path.join(self.code_dir, module)

    def print_header(self, name):
        msg = ""
        msg += ("-"*79) + "\n"
        msg += ("Running test: %s" % name) + "\n"
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


def get_tests():
    import testrig
    path = testrig.__path__
    names = []
    for importer, modname, ispkg in pkgutil.iter_modules(path):
        if not modname.startswith('test_'):
            continue
        name = modname[5:]

        modname = 'testrig.test_' + name
        mod = __import__(modname, fromlist='x')
        if mod.__doc__:
            info = mod.__doc__.strip()
        else:
            info = ""

        names.append((name, info))

    return names


def run(name, base_dir, clean_build=True, log_prefix=False):
    modname = 'testrig.test_' + name
    try:
        mod = __import__(modname, fromlist='x')
    except ImportError:
        print("Test module %r does not exist" % (modname,))
        return False

    cache_dir = os.path.join(base_dir, name)
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)

    log_fn = os.path.join(cache_dir, 'test-%s.log' % name)
    fixture = Fixture(name,
                      cache_dir=cache_dir, log_fn=log_fn,
                      clean_build=clean_build,
                      log_prefix=log_prefix)
    fixture.print_header(name)
    try:
        fixture.setup()
        try:
            mod.run(fixture)
            fixture.print("OK")
            return True
        except Exception as exc:
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
