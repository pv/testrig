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
    test_base.Test64Bit.test_no_64(<class 'test_base.TestBSR'>, 'test_fancy_indexing_ndarray') ... SKIP: feature not implemented
    test_base.Test64Bit.test_no_64(<class 'test_base.TestBSR'>, 'test_fancy_indexing_randomized') ... /path/sparse/tests/test_base.py:2425: DeprecationWarning: This function is deprecated. Please call randint(-5, 5 + 1) instead
      I = np.random.random_integers(-M + 1, M - 1, size=NUM_SAMPLES)
    /path/sparse/tests/test_base.py:2426: DeprecationWarning: This function is deprecated. Please call randint(-3, 3 + 1) instead
      J = np.random.random_integers(-N + 1, N - 1, size=NUM_SAMPLES)
    SKIP: feature not implemented

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
    failures, warns, test_count, err_msg = parser(text, None)

    expected = {
        'test_bar': 'ERROR: test_bar\n----------------------------------------------------------------------\naaa\n',
        'test_foo': 'FAIL: test_foo\n----------------------------------------------------------------------\nbbb\n'
    }
    assert failures == expected, failures
    expected = {
        ("DeprecationWarning: This function is deprecated. Please call randint(-5, 5 + 1) instead\n"
         "    /path/sparse/tests/test_base.py:2425\n"
         "  I = np.random.random_integers(-M + 1, M - 1, size=NUM_SAMPLES)"):
        ("WARNING: DeprecationWarning: This function is deprecated. Please call randint(-5, 5 + 1) instead\n"
         "    /path/sparse/tests/test_base.py:2425\n"
         "  I = np.random.random_integers(-M + 1, M - 1, size=NUM_SAMPLES)\n"
         "test_base.Test64Bit.test_no_64(<class 'test_base.TestBSR'>, 'test_fancy_indexing_randomized')\n"
         "---"),
        ("DeprecationWarning: This function is deprecated. Please call randint(-3, 3 + 1) instead\n"
         "    /path/sparse/tests/test_base.py:2426\n"
         "  J = np.random.random_integers(-N + 1, N - 1, size=NUM_SAMPLES)"):
        ("WARNING: DeprecationWarning: This function is deprecated. Please call randint(-3, 3 + 1) instead\n"
         "    /path/sparse/tests/test_base.py:2426\n"
         "  J = np.random.random_integers(-N + 1, N - 1, size=NUM_SAMPLES)\n"
         "test_base.Test64Bit.test_no_64(<class 'test_base.TestBSR'>, 'test_fancy_indexing_randomized')\n"
         "---"),
    }
    assert warns == expected, warns
    assert test_count == 3, test_count
    assert err_msg is None
