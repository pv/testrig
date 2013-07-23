from .common import get_git_sources

def test_scipy_dev(fixture):
    """Scipy (dev version) on Numpy (dev version)"""
    fixture.pip_install("nose")
    fixture.git_install(get_git_sources(["numpy-dev", "scipy-dev"]))
    fixture.run_numpytest("scipy")

def test_scipy_rel(fixture):
    """Scipy (released) on Numpy (dev version)"""
    fixture.pip_install("nose")
    fixture.git_install(get_git_sources(["numpy-dev", "scipy-rel"]))
    fixture.run_numpytest("scipy")
