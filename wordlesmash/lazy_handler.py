import os
import logging
from logging.handlers import RotatingFileHandler
import tempfile
import glob
# import stat

class LazyRotatingFileHandler(RotatingFileHandler):
    def __init__(self, tmpdir_prefix='', basename=None, *args, **kwargs):

        base_dir = self._create_temp_dir(tmpdir_prefix)
        kwargs['filename'] = os.path.join(base_dir, basename)
        super().__init__(*args, **kwargs)


    @staticmethod
    def _tmpdir_usable(path):

        st = os.stat(path)
        if st.st_uid != os.getuid() or (st.st_mode & 0o777) != 0o700:
            return False #raise OSError(f"Directory {path} has insecure ownership or permissions")
        # Check for symlinks in directory
        for item in os.listdir(path):
            if os.path.islink(os.path.join(path, item)):
                return False # raise OSError(f"Directory {path} contains symlink: {item}")
        print(f"Using existing directory: {path}")
        return True

    @classmethod
    def _create_temp_dir(cls, tmpdir_prefix):

        existing_dirs = []
        base_dir = None
        if tmpdir_prefix:
            existing_dirs.extend(glob.glob(os.path.join(tempfile.gettempdir(), f"{tmpdir_prefix}*")))

        for dir_ in existing_dirs:
            if cls._tmpdir_usable(dir_):
                base_dir = dir_
                break

        if base_dir is None:
            base_dir = tempfile.mkdtemp(prefix=tmpdir_prefix)
            # os.chmod(self.base_dir, 0o700) # unecessary b/c mktemp already has these perms
            print(f"Created new directory: {base_dir}")

        return base_dir

    # def _open(self):
    #     if os.path.islink(self.baseFilename):
    #         raise OSError(f"Log file {self.baseFilename} is a symlink")
    #     fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    #     stream = os.fdopen(fd, 'a')
    #     return stream

    # def doRollover(self):
    #     super().doRollover()
    #     # Ensure rotated files have restrictive permissions
    #     for i in range(1, self.backupCount + 1):
    #         rotated_file = f"{self.baseFilename}.{i}"
    #         if os.path.exists(rotated_file):
    #             os.chmod(rotated_file, 0o600)

    # def emit(self, record):
    #     if self.base_dir is None:
    #         self._create_temp_dir()
    #     # Ensure directory still exists
    #     if not os.path.isdir(self.base_dir):
    #         raise OSError(f"Directory {self.base_dir} no longer exists")
    #     self.baseFilename = os.path.join(self.base_dir, os.path.basename(self.baseFilename))
    #     if not self.is_initialized:
    #         self.stream = self._open()
    #         self.is_initialized = True
    #     super().emit(record)


    #     if self._real_filename is None:
    #         self._real_filename = self.get_full_path()
    #         self.baseFilename = self._real_filename
    #         self.doRollover()
    #     super().emit(record)


if __name__ == '__main__':

    def setup_logger(prefix=None):
        pid = os.getpid()
        log_file = f"log_{pid}.log"
        logger = logging.getLogger("MyLogger")
        logger.setLevel(logging.DEBUG)
        handler = LazyRotatingFileHandler(prefix=prefix, filename=log_file, maxBytes=10*(1024 ** 2), backupCount=3)
        logger.addHandler(handler)
        return logger

    # Usage
    logger = setup_logger(prefix="wordlesmash.")
    for i in range(100):
        logger.debug(f"This is log message {i}")
    print("Logs are being written to the temporary directory.")