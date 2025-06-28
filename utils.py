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



def diff_indexes(seq1, seq2):
    """yield indices of differing elements in two sequences"""
    yield from (i for i, (a, b) in enumerate(zip(seq1, seq2)) if a != b)



class LazyList(list):
    """List that fills itself lazily from an iterator"""
    def __init__(self, generator=None):
        self._is_filled = generator is None
        self._generator = generator
        # Not calling super().__init__, list population delayed

    def _fill(self):
        if not list.__getattribute__(self, '_is_filled'):
            list.extend(self, list.__getattribute__(self, '_generator'))
            list.__setattr__(self, '_is_filled', True)

    def __getitem__(self, index):
        super().__getattribute__('_fill')() # Populate the cache when an item is accessed
        return self._cache[index]

    def __len__(self):
        # self._fill()  # Populate the cache to get the length
        super().__getattribute__('_fill')() # Populate the cache when an item is accessed
        return list.__len__(self)

    def __iter__(self):
        # self._fill()  # Populate the cache for iteration
        super().__getattribute__('_fill')() # Populate the cache when an item is accessed
        return list.__iter__(self)

    def __repr__(self):
        # self._fill()  # Populate the cache for representation
        super().__getattribute__('_fill')() # Populate the cache when an item is accessed
        return f"LazyList({list.__repr__(self)})"

    def __getattribute__(self, name):
        # self._fill()
        super().__getattribute__('_fill')() # Populate the cache when an item is accessed
        return super().__getattribute__(name)


if __name__ == '__main__':

    def test_lazy_list():
        my_iter = (i for i in range(10))
        ll = LazyList(my_iter)
        print(f"getting an item first: {next(my_iter) = }")
        print(ll)

    test_lazy_list()