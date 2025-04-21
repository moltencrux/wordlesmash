import os

def all_files_newer(set1, set2):
    "Returns True if all files in set1 are accessible and modification times are later than those in set2"

    try:
        # Get the latest modification time in set1
        latest_time_set1 = max(os.path.getmtime(file) for file in set1)

    except (FileNotFoundError, PermissionError):
        latest_time_set1 = -float('inf')

    try:
        # Get the earliest modification time in set2
        earliest_time_set2 = min(os.path.getmtime(file) for file in set2)

    except (FileNotFoundError, PermissionError):
        earliest_time_set2 = -float('inf')


    if latest_time_set1 == earliest_time_set2 == -float('inf'):
        return None
    else:
        return latest_time_set1 > earliest_time_set2

