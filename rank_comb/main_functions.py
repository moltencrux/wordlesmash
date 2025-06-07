from math import comb, factorial, perm
from sortedcontainers import SortedSet
from itertools import permutations, combinations, pairwise, groupby, combinations_with_replacement
from collections import Counter
import random
from random import choice, sample

from string import ascii_uppercase


# def rank_combination_unrefined(combination, sorted_items):
#     '''refined rank combination'''
# 
#     n = len(sorted_items)  # Total number of possible elements
#     k = len(combination)   # Size of the combination
#     rank = 0
# 
#     index_map = {item: idx for idx, item in enumerate(sorted_items)}
#     combination = sorted(index_map[e] for e in combination)
# 
#     for i, (prev, current) in enumerate(pairwise((-1, *combination))):
#         for j in range(prev + 1, current):
#             rank += comb(n - j - 1, k - i - 1)
# 
#     return rank


def rank_combination(combination, sorted_items):
    '''refined rank combination'''

    n = len(sorted_items)  # Total number of possible elements
    index_map = {item: idx for idx, item in enumerate(sorted_items)}

    return rank_combination_raw(tuple(sorted(index_map[e] for e in combination)), n)


def rank_combination_raw(combination, n):
    '''refined rank combination'''

    k = len(combination)   # Size of the combination
    rank = 0

    for i, (prev, current) in enumerate(pairwise((-1, *combination))):
        for j in range(prev + 1, current):
            rank += comb(n - j - 1, k - i - 1)

    return rank


def generate_combination(sorted_items, k, rank):

    n = len(sorted_items)
    return tuple(sorted_items[i] for i in generate_combination_raw(n, k, rank))


def generate_combination_raw(n, k, rank):
    """assumes that items are integners 0..something"""
    combination = []
    index = 0

    while k > 0 and index < n:
        remaining = n - index - 1
        count = comb(remaining, k - 1)

        if rank < count:
            combination.append(index)
            k -= 1
        else:
            rank -= count

        index += 1

    return tuple(combination)


def rank_multiset(multiset, sorted_items):
    '''working!'''

    n = len(sorted_items)
    index_map = {item: idx for idx, item in enumerate(sorted_items)}
    
    return rank_multiset_raw(tuple(index_map[e] for e in multiset), n)


def rank_multiset_raw(multiset, n):
    '''working!'''
    # r and n
    # comb(n - 1 + r, r) == comb(n - 1 + r, n-1) n = 6 (sided die) 10 dice
    # so n is possible values.. in the letter scenario.. 26/7
    # r is # members in multiset

    r = len(multiset)
    counts = Counter(multiset)
    multiset_combo = [] # reduced multiset non-repeating combination

    offset = 0
    for (item, count) in sorted(counts.items()):
        multiset_combo.extend(range(item + offset, item + offset + count))
        offset += count
    return rank_combination(multiset_combo, tuple(range(n + r - 1)))


def generate_multiset(sorted_items, k, rank):
    sorted_items = list(sorted_items)
    n = len(sorted_items)

    return tuple(sorted_items[i] for i in generate_multiset_raw(n, k, rank))


def generate_multiset_raw(n, k, rank):
    combo = []

    offset = 0
    multiset_combo = generate_combination_raw(n + k - 1, k, rank)

    for v in multiset_combo:
        combo.append(v - offset)
        offset += 1

    return tuple(combo)


# def generate_combination_old(sorted_items, k, rank):
#     n = len(sorted_items)
#     combination = []
#     index = 0
# 
#     while k > 0 and index < n:
#         remaining = n - index - 1
#         count = comb(remaining, k - 1)
# 
#         if rank < count:
#             combination.append(sorted_items[index])
#             k -= 1
#         else:
#             rank -= count
# 
#         index += 1
# 
#     return tuple(combination)

# def rank_multiset_alt(multiset, sorted_items):
#     # stars & bars (2 items)
#     # comb(n - 1 + r, r) == comb(n - 1 + r, n-1) n = 6 (sided die) 10 dice
# 
#     multiset_combo = []
#     n = len(sorted_items)
#     r = len(multiset)
#     print(f'rank_multiset_alt: {n = }, {r = }')
#     index_map = {item: idx for idx, item in enumerate(sorted_items)}
#     print(f'{sorted_items = }')
#     print(f'{index_map = }')
#     print(f'{multiset = }')
#     multiset = sorted(index_map[e] for e in multiset)
#     counts = Counter(multiset)
#     print(f'{counts = }')
# 
#     offset = 0
#     for (item, count) in sorted(counts.items()):
#         print(f'{count = }, {item = }, {offset = }')
#         multiset_combo.extend(range(item + offset, item + offset + count))
#         print(f'tmp: {multiset_combo = }')
#         offset += count
#     print(f'{multiset_combo = }')
#     return rank_combination(multiset_combo, tuple(range(n + r - 1)))


# def rank_multiset_alt2(multiset, sorted_items):
#     """this one works i think"""
# 
#     multiset_combo = []
#     n = len(sorted_items)
#     r = len(multiset)
#     index_map = {item: idx for idx, item in enumerate(sorted_items)}
#     multiset = sorted(index_map[e] for e in multiset)
#     counts = Counter(multiset)
# 
#     offset = 0
#     for (item, count) in sorted(counts.items()):
#         multiset_combo.extend(range(item + offset, item + offset + count))
#         offset += count
#     return rank_combination(multiset_combo, tuple(range(n + r)))



# def rank_multiset_broken(multiset, sorted_items):
#     n = len(sorted_items)  # Total number of possible elements
#     k = len(multiset)      # Size of the multiset
#     rank = 0
# 
#     # Create a dictionary to map each item to its index
#     index_map = {item: idx for idx, item in enumerate(sorted_items)}
# 
#     # Sort the multiset based on the indices in sorted_items
#     # multiset = sorted(multiset, key=lambda x: index_map[x])
#     multiset = sorted(multiset, key=index_map.get)
# 
#     # Count occurrences of each element in the multiset
#     # counts = {}
#     # for item in multiset:
#     #     counts[item] = counts.get(item, 0) + 1
#     counts = Counter(multiset)
# 
#     # Iterate through each unique element in the multiset
#     for i, item in enumerate(multiset):
#         current_index = index_map[item]
# 
#         # Count how many multisets can be formed with elements before the current item
#         for j in range(current_index):
#             if j < n:  # Ensure we don't go out of bounds
#                 # Calculate the number of ways to choose the remaining items
#                 remaining_items = k - sum(counts.values()) + counts[item]  # Remaining slots to fill
#                 rank += comb(remaining_items + (n - j - 1), n - j - 1)
# 
#         # Decrease the count of the current item
#         counts[item] -= 1
#         if counts[item] == 0:
#             del counts[item]  # Remove the item if its count reaches zero
# 
#     return rank  # Return 1-based rank


# def generate_multiset_broken(sorted_items, k, rank):
#     n = len(sorted_items)  # Total number of possible elements
#     multiset = []
# 
#     # Adjust rank to be zero-based
# 
#     # Iterate through the sorted items
#     for i in range(n):
#         if len(multiset) == k:
#             break
#         
#         current_item = sorted_items[i]
#         
#         # Count how many combinations can be formed with the current item
#         for count in range(k + 1):  # Allow for 0 to k occurrences of the current item
#             # Calculate the number of multisets that can be formed with the remaining items
#             remaining_items = k - count  # Remaining slots to fill
#             if remaining_items < 0:
#                 break
#             
#             num_combinations = comb(remaining_items + (n - i - 1), n - i - 1)
# 
#             if rank < num_combinations:
#                 # If the rank is within the number of combinations, include the current item
#                 multiset.extend([current_item] * count)
#                 break
#             else:
#                 # Exclude the current item and adjust the rank
#                 rank -= num_combinations
# 
#     return multiset


# def generate_combination_orig(rank, sorted_items, k):
#     n = len(sorted_items)
#     combination = []
#     
#     # Adjust rank to be zero-based
#     rank -= 1
# 
#     for i in range(n):
#         if len(combination) == k:
#             break
#         
#         # Calculate the number of combinations that can be formed
#         # with the remaining items if we include sorted_items[i]
#         for j in range(i, n):
#             if len(combination) + 1 + (n - j - 1) < k:
#                 break  # Not enough items left to complete the combination
#             
#             num_combinations = comb(n - j - 1, k - len(combination) - 1)
#             
#             if rank < num_combinations:
#                 # Include the current item in the combination
#                 combination.append(sorted_items[i])
#                 break
#             else:
#                 # Exclude the current item and adjust the rank
#                 rank -= num_combinations
# 
#     return combination


# def rank_perm_orig(seq):
#     """Assigns a rank identifier to a given permutation"""
#     i=0
#     fact = 1
#     s = SortedSet()
#     rank = 0
#     for item in seq:
#         s.add(item)
#         rank += s.index(item) * fact
#         i += 1
#         fact *= i
# 
#     return rank

def rank_perm(perm, domain):
    n = len(domain)
    index_map = {item: idx for idx, item in enumerate(domain)}

    return rank_perm_raw(tuple(index_map[e] for e in perm), n)


def rank_perm_raw(seq, n):
    """
    Assigns a rank identifier to a given permutation
    Currently assumes the sequence to hold all items in the domain. Might make it more
    Generic to rank non-full permutations
    """
    k = len(seq)
    place_val = 1
    try:
        s = SortedSet({*range(n)} - {*seq})
    except TypeError as e:
        pass

    rank = 0
    for item in reversed(seq):
        s.add(item)
        rank += s.index(item) * place_val
        place_val *= len(s)

    return rank

# def generate_perm_orig(elements, rank):
#     """
#     Returns the permutation designated by the ordinal
#     this assumes the 'natural' order of the elements. Another approach might be
#     to assume the order in which they are given in the elements sequence.
#     Might should add some bounds checking on the ordinal to be sure it's
#     less than fact(len(s))? or something to that effect.
#     We don't even use item at all in the loop, so we might could make the sorted
#     set to be some tuples with the items as the second member
#     """
# 
#     seq = []
#     s = SortedSet(elements)
#     fact = factorial(len(s) - 1)
# 
# 
#     for item in elements:
#         index, rank = divmod(rank, fact)
#         seq.append(s[index])
#         fact //= max((len(s) - 1), 1)
#         del s[index]
# 
#     return tuple(reversed(seq))



def generate_perm(domain, k, rank):

    n = len(domain)
    index_map = {idx: item for idx, item in enumerate(domain)}
    return tuple(index_map[e] for e in generate_perm_raw(n, k, rank))


def generate_perm_raw(n, k, rank):
    # n is domain/population size

    permutation = []
    s = SortedSet(range(n))
    place_val = perm(n-1, k-1)

    for _ in range(k):
        index, rank = divmod(rank, place_val)
        permutation.append(s[index])
        place_val //= max(len(s) - 1, 1)
        del s[index]

    return tuple(permutation)



# def rank_combination(combination, elements):
#     # Sort the combination to ensure it matches the order of combinations
#     element_map = {v:k for k, v in enumerate(elements)}
# 
#     combination = sorted(combination)
#     
#     # Calculate the rank of the combination
#     rank = 0
#     n = len(elements)
#     k = len(combination)
#     
#     # Iterate through each element in the combination
#     for i in range(k):
#         # For each element in the combination, count how many combinations
#         # can be formed with the remaining elements
#         for j in range(elements.index(combination[i])):
#             if elements[j] not in combination[:i]:  # Ensure we don't count already chosen elements
#                 rank += comb(n - j - 1, k - i - 1)
#         n -= 1  # Reduce the size of the pool of elements
#     
#     return rank
# 
# def rank_combination(combination, elements):
#     # Sort the combination to ensure it matches the order of combinations
# 
#     element_map = {v:k for k, v in enumerate(elements)}
# 
#     combination = sorted(element_map[e] for e in combination)
#     
#     # Calculate the rank of the combination
#     rank = 0
#     n = len(elements)
#     k = len(combination)
#     
#     # Iterate through each element in the combination
#     for i in range(k):
#         # For each element in the combination, count how many combinations
#         # can be formed with the remaining elements
#         for j in range(i):
#             if j not in combination[:i]:  # Ensure we don't count already chosen elements
#                 rank += comb(n - j - 1, k - i - 1)
#         n -= 1  # Reduce the size of the pool of elements
#     
#     return rank
# 
# 
# def get_combination(elements, k, rank):
#     # Generate all combinations of the specified length k
#     all_combinations = list(combinations(sorted(elements), k))
#     
#     # Check if the rank is within the valid range
#     if rank < 0 or rank >= len(all_combinations):
#         return None  # or raise an exception, or return an error message
#     
#     # Return the combination at the specified rank
#     return all_combinations[rank]
# 
# 





"""

# I was thikning about some kind of ranking scheme, maybe for permutations
# or.. not sure what for, but it semed you could find a remainder of an arb number
# by subtracing the greatest perm <= to it, then repeat recursively w/ the difference
# altho not sure what it would achieve


def find_fact_factors(val):
    n = 1
    fact = 1
    fact_factors = []

    while fact < val:
        n += 1
        fact *= n
    
    while val > 0:
        if fact <= val:
            fact_factors.append(n)
        val -= fact
        fact //= n
        n -= 1

    return fact_factors
    


"""



if __name__ == '__main__':
    # test_rank_combination()

    p1 = generate_perm_safe(range(5), 2, 1)
    p2 = generate_perm_raw(5, 2, 1)
    print(f'{p1 = }, {p2 = }')

# 64 bit filter encoding 
# 18 bits for multiset of 5x27 + possible 28th type that denotes...
# math.comb(n -1 + 1+ k, k) + math.comb(n + k -2 + 1, k-1)
# or... 
# 20 bits for 1-4 mask
# 26 bits for blacklist?
# How do we know when 26 bits changes?  multiset has all known. and
# ??
# encode 26 values.  most are 1/0
# but up to 5 could be green/yellow
# 
# 
# we could do (27, C  5) and let the remaining 21 bits be in the black /max bitmask
# 17 + 21 = 38.  25 for the YG mask. 


# how can you count/rank non homogenous sets.. like, a set or multiset, but in which
# you can have at most one type of other thing.

# if we give 25 bits to the YG mask, we get 49 bits for everything else.

# just sorta count things.. say #'s in this range mean this.. and above mean that..
# 1st digit: 0-5 : # of known chars: < 3 bits.
# 2nd digit: multiset of up to 5 chars up to 18 bits. (15 bits in the case of 4)
# 3rd digit up to 26 bits (remaining letters blacklist)
# 44 bits at most for ms + blacklist

################################################################################
# 64 bit [18 Ms  + [20/25 if no Unk in MS] + 26/0 if no Unk in MS]             #
################################################################################
# encoding green & yellow letters
# 26 Y, 26 G,  + U
# what if we kept order.. nah
# masks.. 26 x 5 = 130
# what if all letters ahd a yellow & green mask.. or can we combine them somehow?
# 3 bits.. forbidden, required unknown?: 8 bits for that. 40 for 5.. 
# wa/ required, unkonwn/possible? can we duplicate black bit? or somehow imply
# a number of dups here? obviously many greens can't be encoded if it's over the max
# combo that indicates qty or max qty.. or black bit
#
# what other kind of info might we store?
# letters spots are eliminated by black or yellow or even green, but eliminated
# in different ways. a green might mark that spot off on the yellow mask, and
# it means no other letter can go in that column.
# 
# what if we had 5 unknown letters that repped the columns?
# or what if we had a set that contained refs to possible letters by slot ?
# is that just the masks? or can we do better? num indicates rank of KC that
# goes there: 5 spots, 32 poss vals, but is it really 32? Col where yellow seen
# would not include that yellow letter in its set. if you got a green, that slot
# would change immediately to point to the rank of that green char
# <= 31 values / slot. can't be empty, 24.77 bits
# a yellow can't be in every slot
# as a matrix..  cols = slot of the thing
# rows := rank of known letter that might be present. 
# so no 11111 rows.. 
# no 0 columns

# 15 bits ( 4 multiset) # could encode special last char to indicate repurposing
# 20 bits, mask
# 26 bits blacklist: repurpose if need 5 multiset
# 61 
# but you know.. if we reupurpose, then there should be no unknowns. (still under 15)

# what if we coded sth like a size 21 set: takes 24 bits.
# multiset?