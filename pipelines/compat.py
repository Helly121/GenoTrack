"""
pipelines/compat.py
Cross-platform compatibility layer ensuring Metaflow and POSIX-dependent modules
run smoothly across native Windows, Linux, and containerized Docker environments.
"""
import os
import sys
from types import ModuleType

def ensure_posix_compat():
    """Ensure fcntl and POSIX os attributes exist on Windows."""
    if sys.platform == "win32":
        if not hasattr(os, "O_NONBLOCK"):
            os.O_NONBLOCK = 0

        if "fcntl" not in sys.modules:
            m = ModuleType("fcntl")
            m.fcntl = lambda *args, **kwargs: 0
            m.ioctl = lambda *args, **kwargs: 0
            m.flock = lambda *args, **kwargs: 0
            m.lockf = lambda *args, **kwargs: 0
            m.F_SETFL = 0
            m.F_GETFL = 0
            m.LOCK_SH = 1
            m.LOCK_EX = 2
            m.LOCK_NB = 4
            m.LOCK_UN = 8
            sys.modules["fcntl"] = m

ensure_posix_compat()
