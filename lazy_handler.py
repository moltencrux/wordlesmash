# import os
# import logging
# from logging.handlers import RotatingFileHandler
# import tempfile
# import glob
# 
# def setup_logger():
#     # Define the prefix for the temporary directory
#     prefix = "wordlesmash."
#     
#     # Check for existing directories with the specified prefix
#     existing_dirs = glob.glob(os.path.join(tempfile.gettempdir(), f"{prefix}*"))
#     
#     if existing_dirs:
#         # Use the first existing directory
#         temp_dir = existing_dirs[0]
#         print(f"Using existing directory: {temp_dir}")
#     else:
#         # Create a new randomized temporary directory with the custom prefix
#         temp_dir = tempfile.mkdtemp(prefix=prefix)
#         print(f"Created new directory: {temp_dir}")
# 
#     # Get the current process ID
#     pid = os.getpid()
# 
#     # Create a log file name that includes the PID
#     log_file = os.path.join(temp_dir, f"log_{pid}.log")
# 
#     # Set up the logger
#     logger = logging.getLogger("MyLogger")
#     logger.setLevel(logging.DEBUG)
# 
#     # Create a rotating file handler
#     handler = RotatingFileHandler(log_file, maxBytes=10*(1024 ** 2), backupCount=3)
#     logger.addHandler(handler)
# 
#     return logger, temp_dir
# 
# # Usage
# logger, log_directory = setup_logger()
# 
# # Log some messages
# for i in range(1000):
#     logger.debug(f"This is log message {i}")
# 
# print(f"Logs are being written to: {log_directory}")
# 
# 


# import os
# import logging
# from logging.handlers import RotatingFileHandler
# import tempfile
# import glob

# class LazyRotatingFileHandler(RotatingFileHandler):
    # def __init__(self, prefix=None, *args, **kwargs):
        # self.prefix = prefix
        # self.base_dir = None
        # super().__init__(*args, **kwargs)
        # self.is_initialized = False

    # def _create_temp_dir(self):
        # if self.prefix:
            # # Check for existing directories with the specified prefix
            # existing_dirs = glob.glob(os.path.join(tempfile.gettempdir(), f"{self.prefix}*"))
            # if existing_dirs:
                # # Use the first existing directory
                # self.base_dir = existing_dirs[0]
                # print(f"Using existing directory: {self.base_dir}")
            # else:
                # # Create a new randomized temporary directory with the custom prefix
                # self.base_dir = tempfile.mkdtemp(prefix=self.prefix)
                # print(f"Created new directory: {self.base_dir}")
        # else:
            # # Use the default temporary directory
            # self.base_dir = tempfile.gettempdir()

    # def emit(self, record):
        # # Create the directory if it doesn't exist
        # if self.base_dir is None:
            # self._create_temp_dir()

        # os.makedirs(self.base_dir, exist_ok=True)
        # # Update the log file path to include the base directory
        # self.baseFilename = os.path.join(self.base_dir, os.path.basename(self.baseFilename))

        # # Initialize the handler and create the file if it doesn't exist
        # if not self.is_initialized:
            # self.stream = self._open()
            # self.is_initialized = True
        # super().emit(record)

# def setup_logger(prefix=None):
    # # Get the current process ID
    # pid = os.getpid()

    # # Create a log file name that includes the PID
    # log_file = f"log_{pid}.log"

    # # Set up the logger
    # logger = logging.getLogger("MyLogger")
    # logger.setLevel(logging.DEBUG)

    # # Create a lazy rotating file handler with the optional prefix
    # handler = LazyRotatingFileHandler(prefix=prefix, filename=log_file, maxBytes=5*1024, backupCount=3)
    # logger.addHandler(handler)

    # return logger

# # Usage
# logger = setup_logger(prefix="wordlesmash.")

# # Log some messages
# for i in range(100):
    # logger.debug(f"This is log message {i}")

# print("Logs are being written to the temporary directory.")






# import os
# import logging
# from logging.handlers import RotatingFileHandler
# import tempfile
# import uuid
# import stat
# import re
# from threading import Lock
# import shutil
# 
# class LazyRotatingFileHandler(RotatingFileHandler):
#     def __init__(self, prefix=None, *args, **kwargs):
#         if prefix and not re.match(r'^[a-zA-Z0-9._-]+$', prefix):
#             raise ValueError("Prefix contains invalid characters")
#         self.prefix = prefix
#         self.base_dir = None
#         self.is_initialized = False
#         self._lock = Lock()
#         super().__init__(*args, **kwargs)
# 
#     def _create_temp_dir(self):
#         try:
#             unique_suffix = str(uuid.uuid4())[:8]
#             prefix = f"{self.prefix}{unique_suffix}_" if self.prefix else ""
#             self.base_dir = tempfile.mkdtemp(prefix=prefix)
#             os.chmod(self.base_dir, 0o700)
#             st = os.stat(self.base_dir)
#             if st.st_uid != os.getuid() or (st.st_mode & 0o777) != 0o700:
#                 raise OSError(f"Directory {self.base_dir} has insecure permissions or ownership")
#             print(f"Created new directory: {self.base_dir}")
#         except OSError as e:
#             raise OSError(f"Failed to create temporary directory: {e}")
# 
#     def _open(self):
#         fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
#         stream = os.fdopen(fd, 'a')
#         return stream
# 
#     def doRollover(self):
#         super().doRollover()
#         for i in range(1, self.backupCount + 1):
#             rotated_file = f"{self.baseFilename}.{i}"
#             if os.path.exists(rotated_file):
#                 os.chmod(rotated_file, 0o600)
# 
#     def emit(self, record):
#         with self._lock:
#             if self.base_dir is None:
#                 self._create_temp_dir()
#             self.baseFilename = os.path.join(self.base_dir, os.path.basename(self.baseFilename))
#             if not self.is_initialized:
#                 self.stream = self._open()
#                 self.is_initialized = True
#         super().emit(record)
# 
#     def close(self):
#         super().close()
#         if self.base_dir and os.path.exists(self.base_dir):
#             shutil.rmtree(self.base_dir, ignore_errors=True)
# 
# def setup_logger(prefix=None):
#     unique_id = str(uuid.uuid4())[:8]
#     log_file = f"log_{unique_id}.log"
#     logger = logging.getLogger("MyLogger")
#     logger.setLevel(logging.DEBUG)
#     handler = LazyRotatingFileHandler(prefix=prefix, filename=log_file, maxBytes=5*1024, backupCount=3)
#     logger.addHandler(handler)
#     return logger
# 
# # Usage
# logger = setup_logger(prefix="wordlesmash.")
# for i in range(100):
#     logger.debug(f"This is log message {i}")
# print("Logs are being written to the temporary directory.")
# 





import os
import logging
from logging.handlers import RotatingFileHandler
import tempfile
import glob
# import stat

class LazyRotatingFileHandler(RotatingFileHandler):
    def __init__(self, prefix='', *args, **kwargs):
        self.prefix = prefix
        self.base_dir = None
        self.is_initialized = False
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

    def _create_temp_dir(self):
    
        if self.prefix:
            existing_dirs = glob.glob(os.path.join(tempfile.gettempdir(), f"{self.prefix}*"))

            for existing_dir in existing_dirs:
                if self._tmpdir_usable(existing_dir):
                    self.base_dir = existing_dir
                    break

            else:
                self.base_dir = tempfile.mkdtemp(prefix=self.prefix)
                # os.chmod(self.base_dir, 0o700) # unecessary b/c mktemp already has these perms
                print(f"Created new directory: {self.base_dir}")

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

    def emit(self, record):
        if self.base_dir is None:
            self._create_temp_dir()
        # Ensure directory still exists
        if not os.path.isdir(self.base_dir):
            raise OSError(f"Directory {self.base_dir} no longer exists")
        self.baseFilename = os.path.join(self.base_dir, os.path.basename(self.baseFilename))
        if not self.is_initialized:
            self.stream = self._open()
            self.is_initialized = True
        super().emit(record)



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