import textwrap
from .common import get_git_sources

def _check(fixture, numpyver, scipyver):
    fixture.pip_install("nose \n Cython >=0.17")
    fixture.git_install(get_git_sources([numpyver, scipyver]))
    fixture.pip_install("scikits-image")
    fixture.run_python_code(textwrap.dedent("""
    import sys
    import skimage
    sys.exit(not skimage.test())
    """))

def test_numpy_dev_scipy_rel(fixture):
    """Scikit-image (released) on Numpy (dev version) and Scipy (released)"""
    _check(fixture, "numpy-dev", "scipy-rel")

def test_numpy_rel_scipy_dev(fixture):
    """Scikit-image (released) on Numpy (released) and Scipy (dev version)"""
    _check(fixture, "numpy-rel", "scipy-dev")

def test_numpy_dev_scipy_dev(fixture):
    """Scikit-image (released) on Numpy (dev version) and Scipy (dev version)"""
    _check(fixture, "numpy-dev", "scipy-dev")
