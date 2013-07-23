import textwrap

GIT_SOURCES = [
    ('numpy', 'git://github.com/numpy/numpy.git', 'master'),
    ('scipy', 'git://github.com/scipy/scipy.git', 'master')
]

def run(fixture):
    fixture.pip_install("nose\nCython >=0.17")
    fixture.git_install(GIT_SOURCES)
    fixture.pip_install("scikits-image")
    fixture.run_python_code(textwrap.dedent("""
    import sys
    import skimage
    sys.exit(not skimage.test())
    """))
