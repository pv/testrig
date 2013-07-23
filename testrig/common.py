GIT_SOURCES = {
    'numpy-dev': ('numpy', 'git://github.com/numpy/numpy.git', 'origin/master'),
    'numpy-rel': ('numpy', 'git://github.com/numpy/numpy.git', 'v1.7.1'),
    'scipy-dev': ('scipy', 'git://github.com/scipy/scipy.git', 'origin/master'),
    'scipy-rel': ('scipy', 'git://github.com/scipy/scipy.git', 'v0.12.0'),
}

def get_git_sources(names):
    srcs = []
    for name in names:
        srcs.append(GIT_SOURCES[name])
    return srcs
