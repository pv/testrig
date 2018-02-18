.. image:: https://travis-ci.org/pv/testrig.png?branch=master
   :target: https://travis-ci.org/pv/testrig

=======
testrig
=======

Python package integration testing.

Runs the test suite of some package against 'old' and 'new' versions
of given dependencies. Failures that appear in 'new' are reported.

Each test suite run is run in a virtualenv constructed from scratch.
You should install ``ccache`` (and possibly also ``f90cache``) to
avoid drinking too much coffee.

Alternatively, binary conda packages can be used --- however, binary
incompatibities may arise in this configuration.

Currently, this is POSIX-only, and tested only on Linux.

Usage
-----

Run::

    python -mtestrig --help
    python -mtestrig examples/testrig.ini pandas       # run tests
    python -mtestrig examples/testrig-conda.ini pandas # use conda packages
    python -mtestrig examples/testrig.ini -j           # run all packages parallel

The runs may take a long time, as it builds everything from source.

Configuration
-------------

Configuration is read from an ``.ini`` file.  It contains sections, one per
test environment.  Section named ``DEFAULT`` can be used to specify
(overridable) default values for the configuration items.

An example first (runs scipy test suite against old and new numpy
versions)::

  [DEFAULT]
  pkgs = nose tempita Cython==0.22 scipy==0.17.0
  old = numpy==1.7.2 {pkgs}
  new = Cython==0.22 git+https://github.com/numpy/numpy@master {pkgs}

  [scipy]
  pkgs = {pkgs} scipy
  run = python -mpytest --junit-xml=junit.xml --pyarg scipy
  parser = junit:junit.xml
  envvars =
      SETUPCFG=$DIR/mysetup.cfg

More examples can be found under the ``examples/`` folder.

The configuration items in each section are:

* ``env``: which environment to use

  - ``virtualenv``: virtualenv + pip, all packages are built from sources
  - ``conda``: conda, uses binary packages, except for ``git+`` urls
    and package names prefixed by ``pip+``.
    Note that you may need to write stuff like
    ``numpy git+https://github.com/numpy/numpy.git`` since conda only
    understand that packages installed by it are present.

* ``old``: package specifications for the 'old' configuration (see below).
* ``new``: package specifications for the 'new' configuration (see below).
* ``run``: command that runs the tests.
* ``parser``: parser for the test output. Available options:

  - ``junit:FILENAME``: parses xUnit/jUnit xml result output, stored in given
    filename. Both nose and py.test can produce this output:
    ``py.test --junit-xml=junit.xml ...`` and
    ``nosetests --with-xunit --xunit-file=junit.xml ...``.
  - ``nose``: parses nose stdout
* ``envvars``: additional environment variables to set (also for pip install).
  The text ``$DIR`` is replaced by an absolute path of the directory where the
  configuration file resides.

The values support string interpolation, and default values can be
specified in the ``DEFAULT`` section. For example::

  [DEFAULT]
  pre = foo
  post = quux

  [section]
  post = {post} quux2
  new = {pre} bar {post}

produces the value ``new = foo bar quux quux2``.

The package specifications are a string containing a list of pip (or
conda if using env=conda) packages version specifications, with the
following additional possible items:

* ``--no-binary``: do not install following packages via wheels or conda.
* ``--binary``: install following packages via wheels or conda, if possible.

By default, binary packages are used.
