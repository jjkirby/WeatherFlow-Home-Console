"""Nonblocking advisory locks on the shared writer-lock file."""

import errno
import os

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def acquire(stream, *, shared):
    if os.name == "nt":
        # Windows allows locking beyond EOF. Both readers and writers lock byte 0.
        stream.seek(0)
        mode = msvcrt.LK_NBRLCK if shared else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(stream.fileno(), mode, 1)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise BlockingIOError("Telemetry lock is busy") from error
            raise
    else:
        mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        fcntl.flock(stream, mode | fcntl.LOCK_NB)
    # Closing the caller-owned descriptor releases the lock on either platform.
