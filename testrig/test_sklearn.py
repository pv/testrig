from .common import get_git_sources

def _check(fixture, numpyver, scipyver):
    fixture.pip_install("nose")
    fixture.git_install(get_git_sources([numpyver, scipyver]))
    fixture.pip_install("scikit-learn")
    fixture.run_numpytest("sklearn")

def test_numpy_dev_scipy_rel(fixture):
    """Scikit-learn (released) on Numpy (dev version) and Scipy (released)"""
    _check(fixture, "numpy-dev", "scipy-rel")

def test_numpy_rel_scipy_dev(fixture):
    """Scikit-learn (released) on Numpy (released) and Scipy (dev version)"""
    _check(fixture, "numpy-rel", "scipy-dev")

def test_numpy_dev_scipy_dev(fixture):
    """Scikit-learn (released) on Numpy (dev version) and Scipy (dev version)"""
    _check(fixture, "numpy-dev", "scipy-dev")
