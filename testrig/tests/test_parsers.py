from __future__ import absolute_import, division, print_function

import os
import textwrap
import shutil
import tempfile

from testrig.parser import get_parser


def test_nose_parser_basic():
    text = textwrap.dedent("""
    test_parsers.test_foo ... FAIL
    test_parsers.test_bar ... ERROR
    test_parsers.test_quux ... ok

    ======================================================================
    ERROR: test_bar
    ----------------------------------------------------------------------
    aaa

    ======================================================================
    FAIL: test_foo
    ----------------------------------------------------------------------
    bbb

    ----------------------------------------------------------------------
    Ran 3 tests in 0.002s

    FAILED (errors=1, failures=1)
    """)

    parser = get_parser('nose')
    failures, test_count = parser(text, None)

    expected = {
        'test_bar': 'ERROR: test_bar\n----------------------------------------------------------------------\naaa\n',
        'test_foo': 'FAIL: test_foo\n----------------------------------------------------------------------\nbbb\n'
    }
    assert failures == expected, failures
    assert test_count == 3, test_count


def test_pytest_log_parser_basic():
    text = ("F test/test_foo.py::test_bar\n"
            " def test_bar():\n"
            " >       assert False\n"
            " E       assert False\n"
            " \n"
            " test/test_foo.py:4: AssertionError\n"
            ". test/test_foo.py::test_asd\n")

    tmpdir = tempfile.mkdtemp()
    try:
        with open(os.path.join(tmpdir, 'pytest.log'), 'w') as f:
            f.write(text)
    
        parser = get_parser('pytest-log')
        failures, test_count = parser(text, tmpdir)
    finally:
        shutil.rmtree(tmpdir)

    expected = {
        'test/test_foo.py::test_bar': ("-------------------------------------------------------------------------------\n"
                                       "F test/test_foo.py::test_bar\n"
                                       "def test_bar():\n"
                                       ">       assert False\n"
                                       "E       assert False\n"
                                       "\n"
                                       "test/test_foo.py:4: AssertionError")
    }
    assert failures == expected, failures
    assert test_count == 2, test_count
