#!/usr/bin/env python

import sys
import os
import re
import subprocess

from setuptools import setup
from setuptools.command.test import test as TestCommand


version = '0.1.1'


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


def get_git_hash():
    """
    Get version from asv/__init__.py and generate asv/_version.py
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
    Get the number of revisions since the last tag.
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


def write_version_file(filename, version):
    # Write revision file (only if it needs to be changed)
    content = """\
__version__ = "{0}"
__release__ = {1}
""".format(version, 'dev' in version)

    old_content = None
    if os.path.isfile(filename):
        with open(filename, 'r') as f:
            old_content = f.read()
    if content != old_content:
        with open(filename, 'w') as f:
            f.write(content)


if __name__ == "__main__":
    # Update version (if development)
    version_file = os.path.join(basedir, 'testrig', '_version.py')

    if 'dev' in version:
        git_hash = get_git_hash()
        if git_hash:
            version = '{0}{1}+{2}'.format(
                version, get_git_revision(), git_hash[:8])
        elif os.path.isfile(version_file):
            with open(version_file, 'r') as f:
                text = f.read()
                m = re.search('__version__ = \"(.*)\"', text)
                if m:
                    version = m.group(1)

    write_version_file(version_file, version)

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
            'configparser',
        ],
        package_data = {
            'testrig': ['tests']
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
