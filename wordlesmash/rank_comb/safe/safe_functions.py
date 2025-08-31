from itertools import permutations, combinations, combinations_with_replacement


def rank_perm_safe(perm, domain):
    for r, seq in enumerate(permutations(domain, len(perm))):
        if seq == perm:
            return r


def generate_perm_safe(domain, k, rank):
    '''slow but correct version of generate_perm'''
    for r, perm in enumerate(permutations(domain, k)):
        if rank == r:
            return perm


def rank_combination_safe(combination, elements):
    '''slow but correct version of rank_combination'''

    element_map = {v:k for k, v in enumerate(elements)}
    k = len(combination)
    n = len(elements)
    combination = tuple(sorted(element_map[e] for e in combination))
    for rank, elm in enumerate(combinations(range(n), k)):
        if elm == combination:
            return rank


def generate_combination_safe(elements, k, rank):
    '''slow but correct version of generate_combination'''
    for r, c in enumerate(combinations(elements, k)):
        if rank == r:
            return c


def generate_multiset_safe(elements, k, rank):
    '''slow but correct version of generate_multiset'''
    for r, c in enumerate(combinations_with_replacement(elements, k)):
        if rank == r:
            return c


def rank_multiset_safe(combination, elements):
    '''slow but correct version of rank_multiset'''
    element_map = {v:k for k, v in enumerate(elements)}
    k = len(combination)
    n = len(elements)
    multiset = tuple(sorted(element_map[e] for e in combination))
    for rank, elm in enumerate(combinations_with_replacement(range(n), k)):
        if elm == multiset:
            return rank



if __name__ == '__main__':
    # test_rank_combination()

    p1 = generate_perm_safe(range(5), 2, 1)
    p2 = generate_perm_raw(5, 2, 1)
    print(f'{p1 = }, {p2 = }')
