from __future__ import absolute_import, division, print_function

# This __version__ assignment is parsed by setup.py; keep it in this form.
# Development versions end with ".dev" (suffix is added below).
__version__ = "0.2"
__release__ = not __version__.endswith(".dev")

try:
    from ._version import __githash__, __suffix__
except ImportError:
    __githash__ = None
    __suffix__ = "0"
if not __release__:
    __version__ += __suffix__
del __suffix__

from .cli import main
