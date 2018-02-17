from __future__ import absolute_import, division, print_function

import sys
import os
import shutil
import locale
import subprocess
import multiprocessing
import json

try:
    from shlex import quote as shell_quote
except ImportError:
    from pipes import quote as shell_quote


VIRTUALENV_LOCK = multiprocessing.Lock()


class BaseFixture(object):
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
    get_repo
    print
    setup
    teardown

    """

    def __init__(self, cache_dir, log, print_logged=None, cleanup=True, git_cache=True, verbose=False,
                 extra_env=None, python=None):
        self.log = log
        self.cleanup = cleanup
        self.git_cache = git_cache
        self.verbose = verbose
        self.python = python

        if print_logged is None:
            self._print = print
        else:
            self._print = print_logged

        self.cache_dir = os.path.abspath(cache_dir)

        self.env_dir = os.path.join(self.cache_dir, 'env')
        self.code_dir = os.path.join(self.cache_dir, 'code')
        self.build_dir = os.path.join(self.cache_dir, 'build')
        self.repo_cache_dir = os.path.join(self.cache_dir, 'git-cache')
        if not extra_env:
            self.extra_env = {}
        else:
            self.extra_env = extra_env

    def setup(self):
        for d in (self.code_dir, self.build_dir, self.repo_cache_dir):
            if not os.path.isdir(d):
                os.makedirs(d)

        if os.path.isdir(self.env_dir):
            shutil.rmtree(self.env_dir)

    def teardown(self):
        if self.cleanup:
            for d in (self.env_dir, self.code_dir, self.build_dir):
                if os.path.isdir(d):
                    shutil.rmtree(d)

    def _decode(self, data):
        lang, encoding = locale.getdefaultlocale()
        try:
            return data.decode(encoding)
        except UnicodeError:
            try:
                return data.decode('utf-8')
            except UnicodeError:
                # Ultimate fallback
                return data.decode('latin1')

    def get_info(self):
        cmd = [os.path.join(self.env_dir, 'bin', 'pip'), 'freeze']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        if not isinstance(out, str):
            # Py3
            try:
                out = out.decode('ascii')
            except UnicodeError:
                out = self._decode(out)
        return " ".join(sorted(out.split()))

    def run_cmd(self, cmd, cwd=None, env=None):
        msg = " ".join(os.path.relpath(x) if os.path.exists(x) else x for x in cmd)
        if cwd is not None and os.path.relpath(cwd) != '.':
            msg = '(cd %r && %s)' % (os.path.relpath(cwd), msg)
        msg = '$ ' + msg

        self.print(msg, level=1)

        if env is None:
            env = dict(os.environ)
        else:
            env = dict(env)
        env['CCACHE_BASEDIR'] = self.env_dir
        env.update(self.extra_env)

        subprocess.check_call(cmd, stdout=self.log, stderr=self.log, cwd=cwd, env=env)

    def run_test_cmd(self, cmd, log):
        raise NotImplemented()

    def run_python_script(self, cmd, cwd=None):
        cmd = [os.path.join(self.env_dir, 'bin', 'python')] + cmd
        self.run_cmd(cmd, cwd=cwd)

    def run_pip(self, cmd, cwd=None):
        cmd = [os.path.join(self.env_dir, 'bin', 'pip')] + cmd
        return self.run_cmd(cmd, cwd=cwd)

    def install_spec(self, package_spec):
        """
        Install python packages, based on pip-like version specification string
        """
        binary_ok = True
        for part in package_spec:
            if part == '--binary':
                binary_ok = True
            elif part == '--no-binary':
                binary_ok = False
            elif part.startswith('git+'):
                if '@' in part:
                    url, branch = part.split('@', 1)
                else:
                    url = part
                    branch = 'master'
                module = url.strip('/').split('/')[-1]

                self._git_install(module, url[4:], branch)
            else:
                self._env_install([part], binary_ok)

    def _git_install(self, module, src_repo, branch, setup_py=None):
        if setup_py is None:
            setup_py = 'setup.py'

        repo = self.get_repo(module)

        if os.path.isdir(repo):
            shutil.rmtree(repo)

        if self.git_cache:
            cached_repo = self.get_cached_repo(module)

            if not os.path.isdir(cached_repo):
                self.run_cmd(['git', 'clone', '--bare', src_repo, cached_repo])
            else:
                self.run_cmd(['git', 'fetch', src_repo], cwd=cached_repo)

            self.run_cmd(['git', 'clone', '--reference', cached_repo, '-b', branch, src_repo, repo])
        else:
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
            self._print(msg)
        print(msg, file=self.log)
        self.log.flush()


class VirtualenvFixture(BaseFixture):
    name = "virtualenv"

    def setup(self):
        BaseFixture.setup(self)

        with VIRTUALENV_LOCK:
            self.run_cmd([self.python, '-mvirtualenv', self.env_dir])
            self._debian_fix()

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

    def _env_install(self, packages, binary_ok):
        # Specifying a constant build directory is better for ccache.
        # Can't use wheels, because the Numpy against which packages
        # are compiled may vary.
        if os.path.isdir(self.build_dir):
            shutil.rmtree(self.build_dir)
        os.makedirs(self.build_dir)
        try:
            if binary_ok:
                self.run_pip(['install', '-b', self.build_dir] + packages)
            else:
                self.run_pip(['install',
                              '--upgrade', '--upgrade-strategy', 'only-if-needed', '--force-reinstall',
                              '--no-binary', ':all:', '-b', self.build_dir] + packages)
        finally:
            if os.path.isdir(self.build_dir):
                shutil.rmtree(self.build_dir)

    def run_test_cmd(self, cmd, log):
        cmd = ". bin/activate; " + cmd
        cmd = "bash -c {0}".format(shell_quote(cmd))

        self.print("$ cd cache/env; " + cmd, level=1)

        subprocess.call(cmd, stdout=log, stderr=log, shell=True,
                        cwd=self.env_dir)


class CondaFixture(BaseFixture):
    name = "conda"

    def setup(self):
        BaseFixture.setup(self)
        py_ver = 'python={0}'.format(self.python)
        self.run_cmd(['conda', 'create', '-y', '-p', self.env_dir, py_ver, 'pip'])

    def install_spec(self, package_spec):
        conda_spec = []
        binary_ok = True
        for part in package_spec:
            if part == '--binary':
                binary_ok = True
            elif part == '--no-binary':
                binary_ok = False
            elif part.startswith('git+'):
                if conda_spec:
                    self._env_install(conda_spec, True)
                    conda_spec = []

                if '@' in part:
                    url, branch = part.split('@', 1)
                else:
                    url = part
                    branch = 'master'
                module = url.strip('/').split('/')[-1]

                self._git_install(module, url[4:], branch)
            elif part.startswith('pip+') or not binary_ok:
                if conda_spec:
                    self._env_install(conda_spec, True)
                    conda_spec = []
                if part.startswith('pip+'):
                    part = part[4:]
                self.pip_install([part])
            else:
                conda_spec.append(part)

        if conda_spec:
            self._env_install(conda_spec, True)
            conda_spec = []

    def _env_install(self, packages, binary_ok):
        assert binary_ok
        packages = [spec.replace('==', '=') for spec in packages]
        self.run_cmd(['conda', 'install', '--no-update-deps', '-y', '-p', self.env_dir] + packages)

    def run_cmd(self, cmd, cwd=None, env=None):
        if env is None:
            env = dict(os.environ)
        else:
            env = dict(env)

        def add_path(name, value):
            env[name] = os.pathsep.join([value] + env.get(name, '').split(os.pathsep))

        # Add environment variables to ensure correct BLAS etc. is linked
        add_path('PATH', os.path.join(self.env_dir, 'bin'))
        add_path('CPATH', os.path.join(self.env_dir, 'include'))
        add_path('LIBRARY_PATH', os.path.join(self.env_dir, 'lib'))
        add_path('LD_LIBRARY_PATH', os.path.join(self.env_dir, 'lib'))

        return BaseFixture.run_cmd(self, cmd, cwd=cwd, env=env)

    def pip_install(self, packages):
        if os.path.isdir(self.build_dir):
            shutil.rmtree(self.build_dir)
        os.makedirs(self.build_dir)
        try:
            self.run_pip(['install',
                          '--upgrade', '--upgrade-strategy', 'only-if-needed', '--force-reinstall',
                          '--no-binary', ':all:', '-b', self.build_dir] + packages)
        finally:
            if os.path.isdir(self.build_dir):
                shutil.rmtree(self.build_dir)

    def run_test_cmd(self, cmd, log):
        out = subprocess.check_output(['conda', 'info', '--json'])
        info = json.loads(out)
        activate_script = os.path.join(info['sys.prefix'], 'bin', 'activate')

        cmd = "source {0} {1} && {2}".format(
            shell_quote(os.path.abspath(activate_script)),
            shell_quote(self.env_dir),
            cmd)
        cmd = "bash -c {0}".format(shell_quote(cmd))

        self.print("$ cd cache/env; " + cmd, level=1)

        subprocess.call(cmd, stdout=log, stderr=log, shell=True,
                        cwd=self.env_dir)


def get_fixture_cls(env):
    types = {
        'virtualenv': VirtualenvFixture,
        'conda': CondaFixture,
    }
    try:
        return types[env]
    except KeyError:
        raise ValueError("unknown environment type: {0} [supported: {1}]".format(
            env, ", ".join(sorted(type.keys()))))
