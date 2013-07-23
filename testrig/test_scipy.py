import textwrap
from .common import get_git_sources

def _check(fixture, scipyver):
    fixture.pip_install("nose")
    fixture.git_install(get_git_sources(["numpy-dev", scipyver]))
    fixture.run_python_code(textwrap.dedent("""
    import sys
    import scipy as t
    sys.exit(int(not t.test('full', raise_warnings=()).wasSuccessful()))
    """))

def test_scipy_dev(fixture):
    """Scipy (dev version) on Numpy (dev version)"""
    _check(fixture, "scipy-dev")

def test_scipy_rel(fixture):
    """Scipy (released) on Numpy (dev version)"""
    _check(fixture, "scipy-rel")
