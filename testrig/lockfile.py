from __future__ import absolute_import, division, print_function

import os
import time


class LockFile(object):
    # XXX: posix-only

    def __init__(self, filename):
        self.filename = filename
        self.pid = os.getpid()
        self.count = 0

    def __enter__(self):
        self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def acquire(self, block=True):
        if self.count > 0:
            self.count += 1
            return True

        while True:
            try:
                lock_pid = os.readlink(self.filename)
                if not os.path.isdir('/proc/%s' % lock_pid):
                    # dead lock; delete under lock to avoid races
                    sublock = LockFile(self.filename + '.lock')
                    sublock.acquire()
                    try:
                        os.unlink(self.filename)
                    finally:
                        sublock.release()
            except OSError as exc:
                pass

            try:
                os.symlink(repr(self.pid), self.filename)
                break
            except OSError as exc:
                if exc.errno != 17: raise

            if not block:
                return False
            time.sleep(1)

        self.count += 1
        return True

    def release(self):
        if self.count == 1:
            if os.path.islink(self.filename):
                os.unlink(self.filename)
        elif self.count < 1:
            raise RuntimeError('Invalid lock nesting')
        self.count -= 1


