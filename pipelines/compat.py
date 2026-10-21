"""
pipelines/compat.py
Cross-platform compatibility layer ensuring Metaflow and POSIX-dependent modules
run smoothly across native Windows, Linux, and containerized Docker environments.
- Implements WindowsProcPoll using Win32 PeekNamedPipe to replace Unix select.poll().
- Patches LocalStorage._atomic_write and os.rename with os.replace to fix WinError 183.
"""
import os
import sys
import tempfile
from types import ModuleType

def ensure_posix_compat():
    """Ensure fcntl, POSIX os attributes, Windows pipe poller, and atomic write exist on Windows."""
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

        # Default builtins.open to utf-8 for text files on Windows to fix charmap/cp1252 errors
        import builtins
        _orig_open = builtins.open
        def _utf8_open(file, mode="r", *args, **kwargs):
            if "b" not in mode and "encoding" not in kwargs:
                kwargs["encoding"] = "utf-8"
            return _orig_open(file, mode, *args, **kwargs)
        builtins.open = _utf8_open

        # Patch os.rename to handle Windows destination file overwriting
        _orig_rename = os.rename
        def _safe_rename(src, dst):
            try:
                _orig_rename(src, dst)
            except FileExistsError:
                os.replace(src, dst)
        os.rename = _safe_rename

        # Patch os.remove and os.unlink to safely ignore Windows file lock issues during temp cleanup
        _orig_remove = os.remove
        def _safe_remove(path):
            try:
                _orig_remove(path)
            except (PermissionError, FileNotFoundError):
                pass
        os.remove = _safe_remove
        os.unlink = _safe_remove

        try:
            import msvcrt
            import ctypes
            from ctypes import byref, c_ulong
            import metaflow.procpoll
            from metaflow.procpoll import ProcPoll, ProcPollEvent

            class WindowsProcPoll(ProcPoll):
                def __init__(self):
                    self._fds = {}
                    self._kernel32 = ctypes.windll.kernel32

                def add(self, fd):
                    try:
                        self._fds[fd] = msvcrt.get_osfhandle(fd)
                    except Exception:
                        pass

                def remove(self, fd):
                    self._fds.pop(fd, None)

                def poll(self, timeout=0.1):
                    import time
                    start = time.time()
                    events = []
                    while True:
                        avail = c_ulong()
                        has_activity = False
                        for fd, handle in list(self._fds.items()):
                            res = self._kernel32.PeekNamedPipe(
                                handle, None, 0, None, byref(avail), None
                            )
                            if res:
                                if avail.value > 0:
                                    events.append(ProcPollEvent(fd=fd, can_read=True, is_terminated=False))
                                    has_activity = True
                            else:
                                err = ctypes.GetLastError()
                                # 109 = ERROR_BROKEN_PIPE, 6 = ERROR_INVALID_HANDLE
                                if err in (109, 6):
                                    events.append(ProcPollEvent(fd=fd, can_read=False, is_terminated=True))
                                    has_activity = True

                        if has_activity or (time.time() - start) >= timeout:
                            break
                        time.sleep(0.01)

                    for ev in events:
                        yield ev

            metaflow.procpoll.make_poll = lambda: WindowsProcPoll()

            # Patch Metaflow LocalStorage atomic write to use os.replace on Windows
            from metaflow.plugins.datastores.local_storage import LocalStorage

            def _atomic_write(full_path, data, mode="wb"):
                dir_name = os.path.dirname(full_path)
                fd, tmp_path = tempfile.mkstemp(dir=dir_name)
                success = False
                try:
                    with os.fdopen(fd, mode) as f:
                        f.write(data)
                    os.replace(tmp_path, full_path)
                    success = True
                finally:
                    if not success:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

            LocalStorage._atomic_write = staticmethod(_atomic_write)

            # Patch MetaflowObject pathspec on Windows to always use forward slashes
            try:
                import metaflow.client.core as _mclient
                _orig_pathspec_fget = _mclient.MetaflowObject.pathspec.fget

                def _clean_pathspec(self):
                    val = _orig_pathspec_fget(self)
                    return val.replace("\\", "/") if isinstance(val, str) else val

                _mclient.MetaflowObject.pathspec = property(_clean_pathspec)

                def _clean_path_components(self):
                    if self._path_components is None:
                        ids = self.pathspec.split("/")
                        self._path_components = ids
                    return list(self._path_components)

                _mclient.MetaflowObject.path_components = property(_clean_path_components)
            except Exception:
                pass
        except Exception:
            pass

ensure_posix_compat()
