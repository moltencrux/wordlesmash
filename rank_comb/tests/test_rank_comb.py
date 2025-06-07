import sys
import os
import logging

from math import comb
from itertools import permutations, combinations, combinations_with_replacement

import random

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# from rank_comb.main_functions import *
from ..main_functions import *
from ..safe import *

import unittest
from string import ascii_uppercase


logging.basicConfig(level=logging.INFO)  # Set the default logging level
logger = logging.getLogger(__name__)


class TestRankComb(unittest.TestCase):
    _alphabet = tuple(ascii_uppercase) + (None,)
    _element_map = {v:k for k, v in enumerate(_alphabet)}

    test_params = {
        'domain': _alphabet,
        'domain_map': _element_map,
        'num_tests': 100,
        'k': 5,
    }
    

    def test_rank_perm_cmp(self):
        self.rank_perm_cmp(**self.test_params)


    def rank_perm_cmp(self, k, num_tests, domain, **kwargs):

        samples = random.sample((*permutations(domain, k),), num_tests)
        
        for permutation in samples:
            rank = rank_perm(permutation, domain)
            rank_safe = rank_perm_safe(permutation, domain)
            self.assertEqual(rank, rank_safe, msg=f"Test failed: {rank} != {rank_safe} (safe) {permutation = }")
            logger.debug(f"Test passed: {permutation = } -> Rank: {rank} -> Rank(Safe): {rank_safe}")

    def test_generate_perm_cmp(self):
        self.generate_perm_cmp(**self.test_params)

    def generate_perm_cmp(self, domain, k, num_tests, **kwargs):

        # Generator for random sample values for which this test will run
        samples = random.sample(range(perm(len(domain), k)), num_tests)

        for rank in samples:
            result_perm_safe = generate_perm_safe(domain, k, rank)
            result_perm = generate_perm(domain, k, rank)
            self.assertEqual(result_perm, result_perm_safe,
                                msg=f"Test failed: {result_perm} != {result_perm_safe} (safe) {rank = }")
            logger.debug(f"Test passed: {rank} -> Result: {result_perm} -> Result Safe: {result_perm_safe}")

    def test_rank_multiset_cmp(self):
        self.rank_multiset_cmp(**self.test_params)


    def rank_multiset_cmp(self, k, num_tests, domain, **kwargs):

        samples = random.sample((*combinations_with_replacement(domain, k),), num_tests)
        
        for multiset in samples:
            rank = rank_multiset(multiset, domain)
            rank_safe = rank_multiset_safe(multiset, domain)
            self.assertEqual(rank, rank_safe, msg=f"Test failed: {rank} != {rank_safe} (safe) {multiset = }")
            logger.debug(f"Test passed: {multiset = } -> Rank: {rank} -> Rank(Safe): {rank_safe}")


    def test_rank_combination_cmp(self):
        self.rank_combination_cmp(**self.test_params)


    def rank_combination_cmp(self, domain, k, num_tests, **kwargs):

        # Generator for random sample values for which this test will run
        samples = random.sample((*combinations(domain, k),), num_tests)
            
        for combination in samples:
            rank_safe = rank_combination_safe(combination, domain)
            rank = rank_combination(combination, domain)
            self.assertEqual(rank, rank_safe, f"Test failed: {rank} != {rank_safe} (safe) {combination = }")
            logger.debug(f"Test passed: {combination = } -> Rank: {rank} -> Rank Safe: {rank_safe}")


    def test_generate_combination_cmp(self):
        self.generate_combination_cmp(**self.test_params)

    def generate_combination_cmp(self, domain, k, num_tests, **kwargs):

        # Generator for random sample values for which this test will run
        samples = random.sample(range(comb(len(domain), k)), num_tests)

        for rank in samples:
            result_combo_safe = generate_combination_safe(domain, k, rank)
            result_combo = generate_combination(domain, k, rank)
            self.assertEqual(result_combo, result_combo_safe,
                                msg=f"Test failed: {result_combo} != {result_combo_safe} (safe) {rank = }")
            logger.debug(f"Test passed: {rank} -> Result: {result_combo} -> Result Safe: {result_combo_safe}")


    def test_generate_multiset_cmp(self):
        self.generate_combination_cmp(**self.test_params)

    def generate_multiset_cmp(self, domain, k, num_tests, **kwargs):

        # Generator for random sample values for which this test will run
        samples = random.sample(range(comb(len(domain) + k - 1, k)), num_tests)

        for rank in random.sample(range(comb(len(domain), k)), num_tests):
            result_multiset_safe = generate_multiset_safe(domain, k, rank)
            result_multiset = generate_multiset(domain, k, rank)

            self.assertEqual(result_multiset, result_multiset_safe,
                                msg=f"Test failed: {result_multiset} != {result_multiest_safe} (safe) {rank = }")
            logger.debug(f"Test passed: {rank} -> Result: {result_multiset} -> Result Safe: {result_multiset_safe}")

    def test_rank_perm_and_undo(self):
        self.rank_perm_and_undo(**self.test_params)

    def rank_perm_and_undo(self, domain, k, num_tests, **kwargs):

        samples = random.sample((*permutations(domain, k),), num_tests)

        for permutation in samples:
            # Get the rank of the combination
            rank = rank_perm(permutation, domain)
            
            # Retrieve the combination from the rank
            result_perm = generate_perm(domain, k, rank)
            
            # Verify that the original combination matches the retrieved combination
            self.assertEqual(permutation, result_perm,
                             msg=f"Test failed: {permutation} != {result_perm}, ({rank = })")
            logger.debug(f"Test passed: -> Result: {permutation} -> Input: {result_perm} {permutation = }")


    def test_rank_combination_and_undo(self):
        self.rank_combination_and_undo(**self.test_params)

    def rank_combination_and_undo(self, domain, k, num_tests, **kwargs):

        samples = random.sample((*combinations(domain, k),), num_tests)

        for combination in samples:
            # Get the rank of the combination
            rank = rank_combination(combination, domain)
            
            # Retrieve the combination from the rank
            result_combo = generate_combination(domain, k, rank)
            
            # Verify that the original combination matches the retrieved combination
            self.assertEqual(combination, result_combo,
                             msg=f"Test failed: {combination} != {result_combo}, ({rank = })")
            logger.debug(f"Test passed: -> Result: {combination} -> Input: {result_combo} {combination = }")


    def test_rank_multiset_and_undo(self):
        self.rank_multiset_and_undo(**self.test_params)


    def rank_multiset_and_undo(self, domain, k, num_tests, **kwargs):

        domain_map = kwargs.get('domain_map')
        samples = (tuple(sorted((random.choice(domain) for _ in range(k)), key=domain_map.get)) for _ in range(num_tests))

        for multiset in samples:
            # Get the rank of the multiset
            rank = rank_multiset(multiset, domain)
            
            # Retrieve the multiset from the rank
            result_multiset = generate_multiset(domain, k, rank)
            
            # Verify that the original multiset matches the retrieved multiset
            self.assertEqual(multiset, result_multiset,
                             msg=f"Test failed: {multiset} != {result_multiset}, ({rank = })")
            logger.debug(f"Test passed: -> Result: {multiset} -> Input: {result_multiset} {multiset = }")





    def test_generate_combination_and_undo(self):
        self.generate_combination_and_undo(**self.test_params)


    def generate_combination_and_undo(self, domain, k, num_tests, **kwargs):
        
        samples = random.sample(range(comb(len(domain), k)), num_tests)
        
        for rank in samples:
            combination = generate_combination(domain, k, rank)
            result_rank = rank_combination(combination, domain)
            self.assertEqual(rank, result_rank, f"Test failed: {result_rank} != {rank}")
            logger.debug(f"Test passed: -> Rank: {rank} -> Result Rank: {result_rank}")


    def test_generate_multiset_and_undo(self):
        self.generate_multiset_and_undo(**self.test_params)

    def generate_multiset_and_undo(self, domain, k, num_tests, **kwargs):

        samples = random.sample(range(comb(len(domain) + k - 1, k)), num_tests)
        
        for rank in samples:
            multiset = generate_multiset(domain, k, rank)
            result_rank = rank_multiset(multiset, domain)
            self.assertEqual(rank, result_rank, f"Test failed: {result_rank} != {rank}")
            logger.debug(f"Test passed: -> Rank: {rank} -> Result Rank: {result_rank}")

















    def x_test_rank_multiset():
        # what if None is False?
        from string import ascii_uppercase
        alphabet = tuple(ascii_uppercase) + (None,)
        # rank = rank_multiset_alt(tuple('AAAAB'), alphabet)
        # rank2 = rank_multiset(tuple('AAAAB'), alphabet)
        # ms = (None, ) * 5
        ms = sorted(tuple('AAAAB'))

        rank = rank_multiset_alt(ms, alphabet)
        rank2 = rank_multiset(ms, alphabet)
        # print(alphabet)
        print(f'  {rank = }: {rank:b}, {len(bin(rank)[2:]) = }')
        print(f'{rank2 = }: {rank2:b}, {len(bin(rank2)[2:]) = }')
        print('recovering...')
        orig = generate_multiset_alt(alphabet, 5, rank)
        print(orig)
        orig2 = generate_multiset(alphabet, 5, rank2)
        print(orig2)

    def x_test_rank_combination():
        from string import ascii_uppercase
        alphabet = tuple(ascii_uppercase) + (None,)
        picks = sample(ascii_uppercase, 5)
        rank = rank_combination(picks, alphabet)
        recover = generate_combination(alphabet, 5, rank)
        print(f"{picks = }")
        print(f"{recover = }")
        ...

    def x_test_rank_combination_extensive():
        from string import ascii_uppercase
        alphabet = tuple(ascii_uppercase) + (None,)
        picks = sample(ascii_uppercase, 5)
        rank = rank_combination(picks, alphabet)
        recover = generate_combination(rank, alphabet, 5)
        print(f"{picks = }")
        print(f"{recover = }")
        ...






    # I was thikning about some kind of ranking scheme, maybe for permutations
    # or.. not sure what for, but it semed you could find a remainder of an arb number
    # by subtracing the greatest perm <= to it, then repeat recursively w/ the difference
    # altho not sure what it would achieve







if __name__ == '__main__':
    unittest.main()