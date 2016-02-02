from __future__ import absolute_import, division, print_function

import sys
import os
import shutil
import subprocess
import virtualenv


class Fixture(object):
    """
    Fixture for running test suites.

    Sets up a virtualenv and knows how to install Python packages via
    pip and from git installs. Knows how to cache git repositories on
    disk.

    Parameters
    ----------
    

    Methods
    -------
    run_cmd
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

    def __init__(self, cache_dir, log_fn, cleanup=True, git_cache=True, verbose=False):
        self.log = open(log_fn, 'wb')
        self.log_fn = os.path.abspath(log_fn)
        self.cleanup = cleanup
        self.git_cache = git_cache
        self.verbose = verbose

        self.cache_dir = os.path.abspath(cache_dir)

        self.env_dir = os.path.join(self.cache_dir, 'env')
        self.code_dir = os.path.join(self.cache_dir, 'code')
        self.build_dir = os.path.join(self.cache_dir, 'build')
        self.repo_cache_dir = os.path.join(self.cache_dir, 'git-cache')

    def setup(self):
        for d in (self.code_dir, self.build_dir, self.repo_cache_dir):
            if not os.path.isdir(d):
                os.makedirs(d)

        if os.path.isdir(self.env_dir):
            shutil.rmtree(self.env_dir)

        self.print("Setting up virtualenv at {0}...".format(os.path.relpath(self.env_dir)))
        virtualenv.create_environment(self.env_dir)
        self._debian_fix()
        self.pip_install(['pip==8.0.2'])

    def _debian_fix(self):
        # Remove numpy/ symlink under include/python* added by debian
        # --- it causes wrong headers to be used

        py_ver = 'python{0}.{1}'.format(sys.version_info[0], sys.version_info[1])
        inc_dir = os.path.join(self.env_dir, 'include', py_ver)
        numpy_inc_dir = os.path.join(inc_dir, 'numpy')

        if not (os.path.islink(inc_dir) and os.path.islink(numpy_inc_dir)):
            # no problem
            return

        # Fix it up
        real_inc_dir = os.path.abspath(os.readlink(inc_dir))
        os.unlink(inc_dir)
        os.makedirs(inc_dir)

        for fn in os.listdir(real_inc_dir):
            src = os.path.join(real_inc_dir, fn)
            dst = os.path.join(inc_dir, fn)
            if fn != 'numpy':
                os.symlink(src, dst)

        # Double-patch distutils
        distutils_init_py = os.path.join(self.env_dir,
                                         'lib', py_ver, 'distutils', '__init__.py')
        if os.path.isfile(distutils_init_py):
            with open(distutils_init_py, 'a') as f:
                f.write("""\n
def _xx_get_python_inc(plat_specific=0, prefix=None):
    return '{0}'
sysconfig.get_python_inc = _xx_get_python_inc
""".format(inc_dir))

            distutils_init_pyc = distutils_init_py + 'c'
            if os.path.isfile(distutils_init_pyc):
                os.unlink(distutils_init_pyc)

    def teardown(self):
        if self.cleanup:
            for d in (self.env_dir, self.code_dir, self.build_dir):
                if os.path.isdir(d):
                    shutil.rmtree(d)

    def run_cmd(self, cmd, **kwargs):
        msg = " ".join(os.path.relpath(x) if os.path.exists(x) else x for x in cmd)
        if kwargs.get('cwd', None) is not None and os.path.relpath(kwargs['cwd']) != '.':
            msg = '(cd %r && %s)' % (os.path.relpath(kwargs['cwd']), msg)
        msg = '$ ' + msg

        self.print(msg, level=1)

        p = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT,
                             **kwargs)
        try:
            p.communicate()
            if p.returncode != 0:
                raise RuntimeError("Failed to run {0} (see log)".format(cmd))
        except:
            if p.returncode is None:
                p.terminate()
            raise

    def run_test_cmd(self, cmd, log):
        cmd = ". bin/activate; " + cmd

        self.print("$ cd cache/env; " + cmd, level=1)

        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, shell=True,
                             cwd=self.env_dir)
        try:
            p.communicate()
        except:
            if p.returncode is None:
                p.terminate()
            raise

    def run_python_script(self, cmd, **kwargs):
        cmd = [os.path.join(self.env_dir, 'bin', 'python')] + cmd
        self.run_cmd(cmd, **kwargs)

    def run_pip(self, cmd, cwd=None):
        cmd = [os.path.join(self.env_dir, 'bin', 'pip')] + cmd
        return self.run_cmd(cmd, cwd=cwd)

    def install_spec(self, package_spec):
        """
        Install python packages, based on pip-like version specification string
        """
        pip_install = []
        git_install = []

        for part in package_spec:
            if part.startswith('git+'):
                if '@' in part:
                    url, branch = part.split('@', 1)
                else:
                    url = part
                    branch = 'master'
                module = url.strip('/').split('/')[-1]
                git_install.append((module, url[4:], branch))
            else:
                pip_install.append(part)

        if pip_install:
            self.pip_install(pip_install)

        for module, url, branch in git_install:
            self.git_install(module, url, branch)

    def pip_install(self, packages):
        # Specifying a constant build directory is better for ccache.
        # Can't use wheels, because the Numpy against which packages
        # are compiled may vary.
        if os.path.isdir(self.build_dir):
            shutil.rmtree(self.build_dir)
        os.makedirs(self.build_dir)
        try:
            self.run_pip(['install', '--no-use-wheel', '-b', self.build_dir] + packages)
        finally:
            if os.path.isdir(self.build_dir):
                shutil.rmtree(self.build_dir)

    def git_install(self, module, src_repo, branch, setup_py=None):
        if setup_py is None:
            setup_py = 'setup.py'

        repo = self.get_repo(module)

        if self.git_cache:
            cached_repo = self.get_cached_repo(module)

            if not os.path.isdir(cached_repo):
                self.run_cmd(['git', 'clone', '--bare', src_repo, cached_repo])
            else:
                self.run_cmd(['git', 'fetch', src_repo], cwd=cached_repo)

            if not os.path.isdir(repo):
                self.run_cmd(['git', 'clone', '--reference', cached_repo, src_repo, repo])
            else:
                self.run_cmd(['git', 'fetch', 'origin'], cwd=repo)
        else:
            if os.path.isdir(repo):
                shutil.rmtree(repo)
            self.run_cmd(['git', 'clone', '--depth', '1', '-b', branch, src_repo, repo])

        self.run_cmd(['git', 'reset', '--hard', branch], cwd=repo)
        self.run_cmd(['git', 'clean', '-f', '-d', '-x'], cwd=repo)

        # Do it in a way better for ccache
        self.run_python_script([setup_py, 'build'], cwd=repo)
        self.run_pip(['install', '.'], cwd=repo)

    def get_repo(self, module):
        return os.path.join(self.code_dir, module)

    def get_cached_repo(self, module):
        return os.path.join(self.repo_cache_dir, module)

    def print(self, msg, level=0):
        if self.verbose or level == 0:
            print(msg, file=sys.stderr)
            sys.stderr.flush()
        print(msg, file=self.log)
        self.log.flush()
