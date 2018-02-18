#!/usr/bin/env python

import sys
import os
import subprocess
import ast

from setuptools import setup
from setuptools.command.test import test as TestCommand


version = '0.2.dev'


# A py.test test command
class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test"),
                    ('coverage', 'c', "Generate coverage report")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ''
        self.coverage = False

    def finalize_options(self):
        TestCommand.finalize_options(self)

        # The following is required for setuptools<18.4
        try:
            self.test_args = []
        except AttributeError:
            # fails on setuptools>=18.4
            pass
        self.test_suite = 'unused'

    def run_tests(self):
        import pytest
        test_args = ['testrig']
        if self.pytest_args:
            test_args += self.pytest_args.split()
        if self.coverage:
            test_args += ['--cov', 'testrig']
        errno = pytest.main(test_args)
        sys.exit(errno)


basedir = os.path.abspath(os.path.dirname(__file__))


def get_version():
    """Parse current version number from __init__.py"""
    # Grab the first assignment to __version__
    version = None
    init_py = os.path.join(os.path.dirname(__file__),
                           'testrig', '__init__.py')
    with open(init_py, 'r') as f:
        source = f.read()
    tree = ast.parse(source)
    for statement in tree.body:
        if (isinstance(statement, ast.Assign) and
            len(statement.targets) == 1 and
            statement.targets[0].id == '__version__'):
            version = statement.value.s
            break

    if not version:
        raise RuntimeError("Failed to parse version from {}".format(init_py))

    if 'dev' in version and not version.endswith('.dev'):
        raise RuntimeError("Dev version string in {} doesn't end in .dev".format(
            init_py))

    return version


def get_git_hash():
    """
    Get version from testrig/__init__.py and generate testrig/_version.py
    """
    # Obtain git revision
    githash = ""
    if os.path.isdir(os.path.join(basedir, '.git')):
        try:
            proc = subprocess.Popen(
                ['git', '-C', basedir, 'rev-parse', 'HEAD'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            rev, err = proc.communicate()
            if proc.returncode == 0:
                githash = rev.strip().decode('ascii')
        except OSError:
            pass
    return githash


def get_git_revision():
    """
    Get the number of revisions since the beginning.
    """
    revision = "0"
    if os.path.isdir(os.path.join(basedir, '.git')):
        try:
            proc = subprocess.Popen(
                ['git', '-C', basedir, 'rev-list', '--count', 'HEAD'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            rev, err = proc.communicate()
            if proc.returncode == 0:
                revision = rev.strip().decode('ascii')
        except OSError:
            pass
    return revision


def write_version_file(filename, suffix, githash):
    # Write revision file (only if it needs to be changed)
    content = ('__suffix__ = "{0}"\n'
               '__githash__ = "{1}"\n'.format(suffix, githash))

    if not githash.strip():
        # Not in git repository; probably in sdist, so keep old
        # version file
        return

    old_content = None
    if os.path.isfile(filename):
        with open(filename, 'r') as f:
            old_content = f.read()

    if content != old_content:
        with open(filename, 'w') as f:
            f.write(content)


if __name__ == "__main__":
    # Update version (if development)
    version = get_version()
    git_hash = get_git_hash()

    if version.endswith('.dev'):
        suffix = '{0}+{1}'.format(get_git_revision(), git_hash[:8])
        version += suffix
    else:
        suffix = ''

    write_version_file(os.path.join(basedir, 'testrig', '_version.py'),
                       suffix, git_hash)

    # Read long description
    readme_fn = os.path.join(basedir, 'README.rst')
    with open(readme_fn, 'r') as f:
        long_description = f.read().strip()

    # Run setup
    setup(
        name = "testrig",
        version = version,
        packages = ['testrig'],
        entry_points = {'console_scripts': ['testrig = testrig:main']},
        install_requires = [
            'joblib',
        ],
        package_data = {
            'testrig': ['tests/*.py']
        },
        zip_safe = False,
        tests_require = ['pytest'],
        cmdclass = {'test': PyTest},
        author = "Pauli Virtanen",
        author_email = "pav@iki.fi",
        description = "testrig: running tests for dependent packages",
        long_description=long_description,
        license = "BSD",
        url = "http://github.com/pv/testrig",
        classifiers=[
            'Environment :: Console',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: BSD License',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 3',
            'Topic :: Software Development :: Testing',
        ]
    )
