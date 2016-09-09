#!/usr/bin/env python

import sys

from setuptools import setup
from setuptools.command.test import test as TestCommand


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


# Run setup
setup(
    name = "testrig",
    version = "0.1",
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
    license = "BSD",
    url = "http://github.com/pv/testrig"
)
