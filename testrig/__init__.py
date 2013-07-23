from __future__ import absolute_import, division, print_function

import sys
import nose
import os
import shutil
import tempfile
import textwrap
import subprocess
import virtualenv

CACHE_DIR = os.path.normpath(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'cache'))
DOWNLOAD_DIR = os.path.join(CACHE_DIR, 'download')
ENV_DIR = os.path.join(CACHE_DIR, 'env')
CODE_DIR = os.path.join(CACHE_DIR, 'code')

class TestIntegration(object):
    TEST_LOG = sys.stderr

    def __init__(self):
        self.tmp_virtualenv = None

        for d in [DOWNLOAD_DIR, ENV_DIR, CODE_DIR]:
            if not os.path.isdir(d):
                os.makedirs(d)

    def setup(self):
        if os.path.isdir(ENV_DIR):
            shutil.rmtree(ENV_DIR)
        self.tmp_virtualenv = ENV_DIR
        virtualenv.create_environment(self.tmp_virtualenv)

    def teardown(self):
        if self.tmp_virtualenv is not None:
            shutil.rmtree(self.tmp_virtualenv)

    def run_python_code(self, code):
        tmpd = os.path.abspath(tempfile.mkdtemp())
        cwd = os.getcwd()
        try:
            fn = os.path.join(tmpd, 'run.py')
            with open(fn, 'w') as f:
                f.write(code)
            os.chdir(tmpd)
            self.run_python_script([fn])
        finally:
            shutil.rmtree(tmpd)
            os.chdir(cwd)

    def run_python_script(self, cmd, **kwargs):
        assert self.tmp_virtualenv is not None
        cmd = [os.path.join(self.tmp_virtualenv, 'bin', 'python')] + cmd
        self.run_cmd(cmd, **kwargs)

    def run_cmd(self, cmd, **kwargs):
        msg = (' '.join(x if ' ' not in x else '"%s"' % x.replace('"', '\\"') for x in cmd))
        if 'cwd' in kwargs:
            msg = '(cd %r && %s)' % (kwargs['cwd'], msg)
        msg = '$ ' + msg

        print(msg, file=sys.stderr)
        if self.TEST_LOG is not sys.stderr:
            print(msg, file=self.TEST_LOG)

        p = subprocess.Popen(cmd, stdout=self.TEST_LOG, stderr=subprocess.STDOUT,
                             **kwargs)
        try:
            p.communicate()
            if p.returncode != 0:
                raise RuntimeError("Failed to run %r (see log)")
        except:
            p.terminate()
            raise

    def run_pip(self, cmd):
        assert self.tmp_virtualenv is not None
        cmd = [os.path.join(self.tmp_virtualenv, 'bin', 'pip')] + cmd
        return self.run_python_script(cmd)

    def run_numpytest(self, module):
        self.run_python_code(textwrap.dedent("""
        import sys
        import %s as t
        sys.exit(int(not t.test('full').wasSuccessful()))
        """) % (module,))

    def pip_install(self, requirements):
        with tempfile.NamedTemporaryFile() as f:
            f.write(requirements)
            f.flush()
            self.run_pip(['install', '-r', f.name, '--use-mirrors',
                          '--download-dir', DOWNLOAD_DIR])

    def git_install(self, srcs):
        for module, src_repo, branch in srcs:
            self._git_install_one(module, src_repo, branch)

    def _git_install_one(self, module, src_repo, branch):
        repo = self.get_repo(module)

        if not os.path.isdir(repo):
            self.run_cmd(['git', 'clone', src_repo, repo])

        self.run_cmd(['git', 'fetch', 'origin'], cwd=repo)
        self.run_cmd(['git', 'reset', '--hard', 'origin/' + branch], cwd=repo)
        self.run_cmd(['git', 'clean', '-f', '-d', '-x'], cwd=repo)

        self.run_python_script(['setup.py', 'install'], cwd=repo)

    def get_repo(self, module):
        return os.path.join(CODE_DIR, module)

    def print_message(self):
        msg = ""
        msg += ("-"*79) + "\n"
        msg += ("Running test: %s" % self.__class__.__name__) + "\n"
        msg += ("-"*79) + "\n"

        print(msg, file=sys.stderr)
        if self.TEST_LOG is not sys.stderr:
            print(msg, file=self.TEST_LOG)


def run(modules=None, log=None):
    if log is not None:
        if isinstance(log, str):
            TestIntegration.TEST_LOG = open(log, 'wb')
        else:
            TestIntegration.TEST_LOG = log

    if modules is None:
        nose.main(argv=['-vv'])
    else:
        targets = ['testrig.test_' + x for x in modules]
        nose.main(argv=['-vv'] + targets)
