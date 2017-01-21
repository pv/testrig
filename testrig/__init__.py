from __future__ import absolute_import, division, print_function

try:
    from ._version import __version__
except ImportError:
    __version__ = "Unknown"

from .cli import main
