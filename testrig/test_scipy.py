from testrig import TestIntegration

REQUIREMENTS = """
nose
"""

GIT_SOURCES = [
    ('numpy', 'git://github.com/numpy/numpy.git', 'master'),
    ('scipy', 'git://github.com/scipy/scipy.git', 'master')
]

class TestScipy(TestIntegration):
    def test_run(rig):
        rig.pip_install(REQUIREMENTS)
        rig.git_install(GIT_SOURCES)
        rig.run_numpytest("numpy")
