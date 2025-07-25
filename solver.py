#! /usr/bin/env python

from collections import Counter
from string import ascii_uppercase
from heapq import nsmallest, nlargest
from call_counter import call_counter
from wordle_game import Color
from wordle_tree import WordleTree
from itertools import chain, islice
from abc import ABCMeta, abstractmethod, abstractclassmethod
from tree_utils import read_decision_tree, routes_to_dt, dt_to_routes
import numpy as np
from utils import diff_indexes, load_word_list
from or_matrix import compute_or_matrix, is_or_matrix, find_closed_components
from filter_code import FilterCode
from scipy.sparse import lil_matrix
from copy import deepcopy
import threading

# XXX question.. can we find a set of 4/5/6 words with maximum letter coverage?
# how might we do that?
#  level filters..

class CustomDict(dict):
    def __setitem__(self, key, value):
        if key is None:
            # Set a breakpoint here
            pass # import pdb; pdb.set_trace()  # This will start the debugger
        super().__setitem__(key, value)

class CustomList(list):
    def __setitem__(self, index, value):
        # Set a breakpoint here
        pass # import pdb; pdb.set_trace()  # This will start the debugger
        super().__setitem__(index, value)

# Example usage
if __name__ == "__main__":
    my_list = CustomList([1, 2, 3])
    my_list[None] = "This will trigger the breakpoint"  # This will raise an error


# Example usage
if __name__ == "__main__":
    my_dict = CustomDict()
    my_dict[None] = "This will trigger the breakpoint"


# what if each letter has a set of possible locations, and we remove it with each guess.
# a black woudl empty the set, maybe
# a green would not change the set necessarily
# a yellow would remove a spot from the set of that letter 
#######################################
# dict: letter: set(pos) # can derive this from polls
#         # by len could easily tell if a letter is placed definitiely? maybe not
# dict: letter: set(blacklist pos) # can derive this from polls
# list: set(letters)          # pools
# dict: letter: min,max  # required/exclude
# dict difinitive: letter:#
        # could easily tell if a letter qty is known
        #  & for which letters it is known
#######################################
# updating filters should be fairly quick

# but update_canddates / filtering could be slow, especially in the beginning
    # 1 clone(w/filter)  per word test

# why were we getting bad results when scoring on the full list?
# but they're going super fast.. so maybe no filter? XXX check
# there is a filter, but maybe it's not doing that much somehow?
# Hyp: the update is faster b/c the candidates list is much smaller
#      this seems likely to me


# QUESTION:  Would a len x 26 matrix be a better representation for our pools?
# disadvantage, hard to tell the # of chars in each pool. I dont' think so

# from itertools import 
#from decimal import Decimal

#lf_dict = {e[0]:float(Decimal(e[1].strip('%'))/100) for e in letter_frequency_list}
#lf_wt = {e[0]:float(e[2]) for e in letter_frequency_list}

#how did we determine that a yellow w in a particular position?
#we checked that it had been guessed in the others..
#and so it  could only be left those positions
# so maybe we can check the min # for any letter and see if the available spots in
# the pools is more than that. If it's equal, then we know for sure where it goes. 

# BRAINSTORM.. filter ALL possibilites.. and then from those.. maybe calculate
# what is likely to happen with a particular guess?
# i.e how many targets remain from a particular guess, lower is better
# but isn't that what we do already? seems so.. but where is the bulk of the processing from
# for a guess.. which candiates would be affected maybe?
# it's hard tho, because we can't say that sth will be 'caught' or not

# maybe we can say sth about the distribution of letters?


# is the number of definites actually 5 / len?
# for every letter, sub the exclude (upper limit) from required(lower limit)
# i.e. they should be =.
# and if they're =, we can remove everything else from the pools
# or if required >= len, then we have found all letters






# I'm thinking there should be a dictionary keyed by letters w/ values of
# possible indexes and another with forbidden indexes.  do we already have this? 
# what is .char_slots?
# ok, we have .slots. These cold be exactly that.
# well.. .slots is possible characters keyed by indexes
# so char_slots seems to be possible indexes..
# but what about a forbidden/restricted index?

# so it should be keyed by a-z, and have a set of 0-len-1.
# what do we call it? bad_char_slots?  but do we need it?
# 
# seems we already have it, but what is it we wanna know?
# when say we know that we have at least 1 of a char
# but let's say we know we have exactly 1. So we can probably x out one
# position. Then there are 4 other possible positions...
# 
# so if c is narrowed to 1 AND we know that it has exactly 1
# then we can remove it from the rest.
# so we should keep track of counts.... +1 if we see yellow or green
# I think if htere's only 1 of each latter & neither are green, then 1st will
# be yellow (i think) : but it probably doesn't matter if its 1st or not, b/c
# we're sure that only one will be yellow.
# XXX so if we know that for sure we have the same # of possile A in the mask
# as As we are sure is in the word, then we can narrow down the word.
# 


class GuessFilter:
    alphabet = dict.fromkeys(ascii_uppercase)
    domain = dict.fromkeys((*alphabet, None))
    char_ord = {c:i for i, c in enumerate(domain.keys())}
    ord_char = {v:k for k, v in char_ord.items()}
    char_bits_map = {c:tuple(b == '1' for b in f'{i:05b}') for i, c in enumerate(domain.keys())}
    bits_char_map = {v:k for k, v in char_bits_map.items()}

    def __init__(self, length=5, lexicon=None, candidates=None):

        self.length = length # length of the word
        self._lexicon = lexicon if lexicon is not None else () # the dictionary of words being considered as possibilities
        self.candidates = candidates if candidates is not None else self._lexicon # remaining words that are still valid based on filters
        self.viable = {None: [True] * length} # keys: known letters w/ list of Booleans that denotes a letter's possible presence at a position
        self.confirmed = {None: CustomList([False] * length)} # keys: known letters w/ list of Booleans that denotes greens (seen or implied) at a position
        self.blacklist = set()
        self.non_blacklist = set(self.alphabet)
        # blacklist means no more of a particular character will be in the word, outside
        # of what is known to be there.
        self.letters = Counter({None: self.length})
        self._qty_mins = {c: 0 for c in ascii_uppercase}
        # self.components = [0] * length
        self.picks = {word:word for word in lexicon} if lexicon else {}
        # This will be a dictionary of picks that will give a distinct result
        # if guessed. Equivalent guesses (i.e. disseparate guesses that will
        # produce the same updated filter state will be folded together.


    def clone_state(self, source):
        self.length = source.length
        self._lexicon = source._lexicon
        self.viable = deepcopy(source.viable)
        self.confirmed = deepcopy(source.confirmed)
        self.blacklist = source.blacklist.copy()
        self.letters = source.letters.copy()
        self._qty_mins = source._qty_mins.copy()
        self.candidates = source.candidates
        # self.components = source.components.copy()
        self.picks = source.picks.copy()

    @classmethod
    def from_source(cls, source, candidates=None):
        new = cls(length=source.length)
        new.clone_state(source)
        return new


    def to_filter_code(self):

        blacklist = {k:k in self.blacklist for k in self.alphabet}
        return FilterCode(blacklist, self.letters, self.viable, self.confirmed)


    @classmethod
    def from_filter_code(cls, fc, length=5, lexicon=None):

        gf = GuessFilter(length=length, lexicon=lexicon)

        blacklist = {fc.ord_char[pos] for pos in np.where(fc.blacklist)[0]}
        gf.set_blacklist(blacklist)

        letters = fc.unpack_known_chars()
        gf.letters = Counter(letters)

        if gf.get_unknown_count() == 0:
            gf.blacklist.update(gf.alphabet)

        # Set known characters
        for c in filter(None, letters):
            gf.viable.setdefault(c, gf.viable[None].copy())
            gf.confirmed.setdefault(c, [False] * gf.length)

        # Set the letter presence bitfields 
        for r, row in enumerate(fc.presence):
            char = letters[r]
            gf.viable[char][:] = [v.item() for v in row]

        # Axis 0 is char, Axis 1 is col/position for FilterCode presence matrix
        for c, col in enumerate(fc.presence.T):
            rows = np.where(col)[0]
            if len(rows) == 1:
                # Only one letter viable for a column indcates a green/verifeid position (column)
                r = rows[0]
                char = letters[r]
                if char is not None:
                    gf.confirmed[char][c] = True
                    for char in gf.viable: # XXX I think this is right.. 
                        gf.viable[char][c] = False


        return gf


    def dostuff(self):
        self.length = source.length
        self._lexicon = source._lexicon
        self.viable = source.viable.copy()
        self.confirmed = source.confirmed.copy()
        self.blacklist = source.blacklist.copy()
        self.letters = source.letters.copy()
        self._qty_mins = source._qty_mins.copy()
        self.candidates = source.candidates
        ...

    def set_presence(self, viable, confirmed):
        ...
    def set_blacklist(self, blacklist):
        self.blacklist = set(blacklist)


    def get_qty_min(self, c):
        return self.letters.get(c, 0)

    # def get_component(self, c):
    #     index = self.viable[c].find(True)
    #     return self.components[index]
    #     # careful/bc a single letter could be in multiple CCs

    def get_qty_max(self, c):
        """
        This is a definite upper bounds for instances of a character, but might
        conceviably not be the _least_ upper bounds in some cases.
        """
    
        if c in self.blacklist:
            return self.letters.get(c, 0)
        elif c in self.letters: 
            overlap = sum(np.bool(self.viable[c]) & np.bool(self.viable[None]))
            upper = [
                # sum(self.viable[c]) + sum(self.confirmed[c]),  # this is one upper bounds
                self.letters[c] + self.get_unknown_count(),    # This is another UB
                self.letters[c] + overlap, # ?
            ]

            # I think the true _least_ upper bounds for a character might be
            # sum(confirmed[c]) + the overlap of Nones within the character's CC
            # - other char instances confirmed in the CC?

            return min(upper)

        else:
            return self.get_unknown_count()

        # XXX possibly flawed..imagine long word.. imagine we have 1 gn, + 2 yellow 
        # # I _think_ it should be the overlap + confirmed/green
        # Imaigine we got Y____ for some guess on A : black for rest non-A
        # then A could be in any of the later slots. : qty at most 4
        # But.. the overlap would be 4, and also min qty 4, and unkown_ct would be 4
        #

        # M = self.get_matrix()
        # find_closed_components
        # XXX the qty_max for c is 'known_counts' + # of unknowns in its CC
        # need to be able to get the CC for a known letter (by its possible cols).
        # so we should get the CCs by the COLUMNS.
        # maybe just count open spots in its CC. no need to actually look at unknown
        # How many chars claim the spots in the CC columns?
        # but what about multiple chars possible in a CC?, like we saw 2 Yellows
        # we have char_allowed_slot
        # how are mult chars denoted in GF? just known chars? self.letters has the ct
        # what if in sep CCs? is it possible?
        # def possible for greens, but greens would unmark Yellows.

        # __a_a  # so we know that there are 2 As, in those 3
        # then how would we know about other CCs?
        # ___bc
        # ___cb  # so this would tell us that CB are def in the left cp
        #        # and we have known: AABC.  
        # but, we don't know whether the 2s on the left or 1a on the right
        # or do we....  actually, there cannnot be 2 as on the right, b/c
        # of PHP.  We can say for sure that there's an A on the right and
        # on the left in spot 4
        # A: [1, 1, 0, 1, 0],
        # A: [1, 1, 0, 1, 0],
        # B: [1, 1, 1, 0, 0],
        # C: [1, 1, 1, 0, 0],
        # ?: [1, 1, 1, 1, 1],
        #---------------------------
        # A: [1, 1, 0, 1, 0],
        # A: [1, 1, 0, 1, 0],
        # B: [1, 1, 1, 0, 0],
        # C: [1, 1, 1, 0, 0],
        # ?: [0, 0, 0, 0, 1]])
        # So, in our processing, we should be able to say that since
        # the 4th spot is only allowed by As, then there is definitely an A
        # there. so we shoud mark it green
        # does our code find this?
        # A: [1, 1, 0, 0, 1],
        # A: [1, 1, 0, 0, 1],
        # B: [1, 1, 1, 0, 1],
        # C: [1, 1, 1, 0, 1],
        # ?: [1, 1, 1, 1, 1],
        #---------------------------

    def get_non_blacklist(self):
        self.non_blacklist.difference_update(self.blacklist)
        return self.non_blacklist

    def get_unknown_count(self):
        """Returns the number of unknown characters in the solution"""
        return self.length - self.get_known_count()

    def get_known_count(self):
        # Works whether or not Nones are counted in self.letters
        return self.letters.total() - self.letters.get(None, 0)


    def charset_allowed_in_slot(self, slot):
        # is it a green slot?
        allowed = set()
        for c in self.letters.keys() - {None}:

            if self.confirmed[c][slot]:
                return {c}
            if self.viable[c][slot]:
                allowed.add(c)

        if self.viable[None][slot]:
            # allowed.update(self.alphabet.keys() - self.blacklist)
            allowed.update(self.get_non_blacklist())

        return allowed


    def char_allowed_slot(self, c, slot):
        """True if a letter could occupy a particular slot in a solution
        """
        
        if c in self.viable:
            return self.viable[c][slot] or self.confirmed[c][slot]
        else:
            return c not in self.blacklist and self.viable[None][slot]
        # why did we do this? if it's in viable, it really should match the slot
        # i think we were thinking that as long as it was not in the blacklist
        # that should be fne too.. but ACTUALLY, only if t's not in viable

    def matches_slot_map(self, word):
        '''
        Determines whether a word guess could be the target word according to
        the posititional restrictions
        '''
        return all(self.char_allowed_slot(c, slot) for slot, c in enumerate(word))

    
    def fulfills_mins(self, word):
        '''
        Checks to see if a particular word contains all the minimum
        multiplicities for each letter that have been determined to be in the
        solution '''

        counts = Counter(word)
        counts.subtract(self.letters)
        del counts[None]
        return all(val >= 0 for val in counts.values())

        # return all(count >= self.get_qty_min(c) for c, count in self._qty_max.items())
        # self._qty_mins.items()
        # [counts.get(c, 0) >= qty_min for c, qty_min in self._qty_mins.items()]


    def within_maxes(self, word):
        '''
        Checks to see if a particular word does not contain more than the
        maximum multiplicities of any letters that have been determined to be in
        the solution
        '''

        counts = Counter(word)
        return all(count <= self.get_qty_max(c) for c, count in counts.items())


    def guess_valid(self, word):
        '''
        Determines whether a particular guess could be the target word
        '''
        return (self.fulfills_mins(word) and self.within_maxes(word) and
                self.matches_slot_map(word))
        

    def score(self):
        return len(self.candidates)

    def mark_confirmed(self, c, pos):
        '''
        Confirm the presence of charcter c at position pos, which declares that
        no other letter can occupy this position. NOTE that this does not update
        the blacklist currently, but I'm considering changing that behavior.
        '''
        self.viable.setdefault(c, self.viable[None].copy())
        self.confirmed.setdefault(c, [False] * self.length)
        self.confirmed[c][pos] = True
        self.viable[c][pos] = False
        self.letters[c] = max(self.letters.get(c, 0), self.confirmed[c].count(True))

        for other, slots in self.viable.items():
            if other != c:
                slots[pos] = False


    def set_candidates(self, candidates):
        self.candidates = candidates

    def update_candidates(self):

        # maybe check if we're all green, and then just set candidates to that.
        # But I'm not sure if it offers any real savings
        # if False:
        #     letter_list = [None] * 5
        #     for c, fields in self.confirmed.items():
        #         for pos, present in enumerate(fields):
        #             if present:
        #                 letter_list[pos] = c
        #     if None not in letter_list:
        #         self.candidates = [''.join(letter_list)]

        backup = self.candidates
        self.candidates = tuple(filter(self.guess_valid, self.candidates))

    def update_picks(self):
        # collapses picks that are equiavlent given the filter state
        self.picks = {self.normalize_guess(word): word for word in self.picks.values()}

    def get_matrix_old_good(self):
        matrix = []
        counts = self.letters.copy() # is it necessary?


        for c in sorted(self.letters.keys(), key=self.char_ord.get):

            remaining = self.letters[c]
            for pos in (pos for pos, bit in enumerate(self.confirmed[c]) if bit):
                # Encode confirmed instances (greens) first
                matrix.append([pos == i for i in range(self.length)])
                remaining -= 1
            for _ in range(remaining):
                # Encode remaining unconfirmed (yellows)
                conf = [v and not c for v, c in zip(self.viable[c], self.confirmed[c])]
                matrix.append(conf)

        # for c in range(self.length - self.letters.total()):
        #     matrix.append(self.viable[None])

        matrix.extend([self.viable[None]]* (self.length - self.letters.total()))

        return np.array(matrix, dtype=bool)

    # NOTE this version is untested
    def get_matrix(self):

        matrix = np.zeros((self.length, self.length), dtype=bool)
        rows = iter(matrix)

        for c in sorted(self.letters.keys(), key=self.char_ord.get):

            # unconfirmed = max(0, self.length - self.confirmed[c].count(True))
            # unconfirmed = max(0, self.letters[c] - self.confirmed[c].count(True))
            unconfirmed = max(0, self.letters[c] - np.sum(self.confirmed[c]))

            # for pos in np.where(np.bool(self.confirmed[c])):
            for pos, row in zip(np.bool(self.confirmed[c]).nonzero()[0], rows):
                # Encode confirmed/green instances first
                # next(rows)[:] = [[pos == i for i in range(self.length)]]
                row[:] = [pos == i for i in range(self.length)]
            for row in islice(rows, unconfirmed):
                # Encode remaining unconfirmed/yellow
                # unconf = [v and not c for v, c in zip(self.viable[c], self.confirmed[c])]
                # next(rows)[:] = unconf
                # next(rows)[:] = np.bool(self.viable[c]) & ~ np.bool(self.confirmed[c])
                row[:] = np.bool(self.viable[c]) & ~ np.bool(self.confirmed[c])

        # XXX should this be a LIL matrix? Going with it for now
        return lil_matrix(matrix)

    def update_filters(self, word, colors):

        counts = Counter(word)
        new_mins = Counter()

        if isinstance(colors, str):
            # colors = [Color.map(c) for c in colors]
            colors = [*map(Color.map, colors)]

        # Initialize presence or blacklist flags for newly guessed characters
        for c, color in zip(word, colors):
            if color == Color.BLACK:
                self.blacklist.add(c)
            elif color in (Color.GREEN, Color.YELLOW):
                # Initialize viable and confirmed lists if necessary
                self.viable.setdefault(c, self.viable[None].copy())
                self.confirmed.setdefault(c, [False] * self.length)
                new_mins.update(c)


        # Update viable and confirmed lists
        for pos, (c, color) in enumerate(zip(word, colors)):
            if color == Color.GREEN:
                self.mark_confirmed(c, pos)

            elif color in (Color.YELLOW, Color.BLACK):
                if c in self.viable:
                    self.viable[c][pos] = False

        # Update known letters / minimum quantities for any yellows or greens
        for c, min_qty in new_mins.items():
            self.letters[c] = max(self.letters.get(c, 0), min_qty, self.confirmed[c].count(True))


        reduction_needed = True
        while reduction_needed:
            reduction_needed = False # do at least once
            # Reduce unknown character quantities
            if None in self.letters:
                self.letters[None] = self.get_unknown_count()
                if self.letters[None] <= 0:
                    del self.letters[None]
                    self.blacklist.update(self.alphabet.keys())  # No more new leters
                    reduction_needed = False # do at least once

            # Maps rows in the presence adjacency matrix to letters they represent

            # Update based on viable OR matrix bipartitate graph
            M = self.get_matrix()
            R = compute_or_matrix(M)
            # Q how do we make the matrix when there is a green?
            # A known greens will only have a single bit for presence in matrix
            #   This is different than in the FilterCode

            row_letter_map = sum(([c]*n for c, n in self.letters.items()), [])
            row_letter_map.sort(key=self.char_ord.get)
            # QUESTION do we need to do this inside the reduction loop?
            # I think that if a new letter is discovered, it could be incorrect
            # XXX anytime a new char could be discovered, i.e. green thing is called,
            # this needs to be updated. should it be a function?
            # Rows represent letter, cols represent guess pos
            # Process changes to the viable position flags
            for row, col in zip(*np.nonzero(M != R)):
                self.viable[row_letter_map[row]][col] = False
                reduction_needed = True
                # need to fix this for dups and confirmed greens
                # actually, maybe ok. cuz confirmed shouldn't from datetime import datetime
            # Q: could the row_letter_map change since last determined? possibly


            # Check each character to see if its positions can be pinned down
            # and/or their quantities maxed out such that they can be
            # blacklisted
            for c in self.letters.keys() - {None}:

                # Get all slots w/ possible presence, confirmed or viable
                confirmed = np.bool(self.confirmed[c])

                # Filtering confirmed to be safe, but might be uncessary, but
                # viable flags must be mutally exclusive with verified flags
                viable = np.bool(self.viable[c]) & ~ confirmed
                self.viable[c][:] = viable 

                # Check if the guaranteed minimum quantity of c is sufficient
                # to confirm all viable slots and some remain unconfirmed
                if np.any(viable) and np.sum([viable, confirmed]) == self.get_qty_min(c):
                    # There can be no further instances of c, and so all
                    # reamaining viable positions are confirmed/green
                    reduction_needed = True
                    for pos in viable.nonzero()[0]:
                        self.mark_confirmed(c, pos)

                # I think this just means we should blacklist, not confirm
                if self.get_qty_max(c) == self.get_qty_min(c) and c not in self.blacklist:
                    # Predicate implies no further instance of c are possible,
                    # so add c to the blacklist.
                    reduction_needed = True
                    self.blacklist.add(c)
                    # infinte loop??? be sure something actually changed

                    # Check if confirmed account for all possible instances of c
                    # MAYBE totally unecessary
                    if self.confirmed[c].count(True) == self.get_qty_max(c):
                        # All positions of possible instances are known
                        self.viable[c] = [False] * self.length


            # Check each slot to see if its contents can be confirmed
            for pos in range(self.length):
                # total = len([c_found := c for c in self.letters if self.viable[c][pos]])

                # Get list of known characters that are viable for this slot
                known_viable = [c for c in self.viable if self.viable[c][pos]]

                # Checking if only one slot is allowed currently
                if len(known_viable) == 1 and (c := known_viable[0]) is not None:
                    # New confimred/green was found
                    reduction_needed = True
                    self.mark_confirmed(c, pos)
                    # if condition implies all other chars at this pos marked not viable

                # Checks column to see if it can be occupied by exactly one
                # letter, even if preiously unguessed
                elif len(allowed := self.charset_allowed_in_slot(pos)) == 1:
                    c = next(iter(allowed))  # or pop
                    if not self.confirmed[c][pos]:
                        reduction_needed = True
                        self.mark_confirmed(c, pos)



    def update_guess_result(self, word, colors):
        self.update_filters(word, colors)
        self.update_candidates()
        self.update_picks()
        self.narrow_filters_by_candidates()


    def get_worst_case_guess_result(self, word):
        # seems to be getting a list of colors that would be generated by this word
        # in the worst possible case. I think for the purpose of heuristic scoring

        counts = Counter(word)
        # if a letter count in a word is over required, then 1 is guranetteed to be gray
        # but is it safter to assume gray? is it possible to prove yellow?
        # think about:
        # slot availabe
        # #required
        # # restricted - if over restricted, some of tha tletter must be gray
        # XXX idea.. check the candiates and see what colors if unknown could be?


        result = []
        for c, slot in zip(word, self.slots):
            if c in slot and len(slot) == 1:
                result.append(Color.GREEN)
            elif c in self.required and c in slot:
                result.append(Color.UNKNOWN)
            else:
                result.append(Color.BLACK)

        return result
        

        # assume gray, unless letter is in required. Then assume it is yellow as
        # long as there is more than one in the slot.


    def narrow_filters_by_candidates(self):
        ...
        # This will update the filters, slot_mins/maxes based on remaining candidates
        # max counts of ev lettter in each word
        # min counts of ev letter in each word.. might be 1 if all letters have s at some pos
        # slot letters
        # conflicts with guessd filter changes???
        # for word in self.candidates:
        #     ...
        #     counts = Counter(word)
        # But i'm not sure it's actually of any value yet. 

    def normalize_guess(self, word):
        """
        This method creates a key based on a guess against a particular filter,
        changing characters to _ that provide no info on the target and have no
        effect on the future state of the filter. Characters not allowed in a
        particular slot, but whose minimum or maximum quantities could be further
        determined will be appended to the resulting key in alphabetical order.
        In this way, distinct guesses with equivalent effects can be folded onto
        each other, reducing the search space
        """

        excluded = Counter()
        included = Counter()
        key = []

        for pos, c in enumerate(word):

            if (not self.char_allowed_slot(c, pos) or
                c in self.confirmed and self.confirmed[c][pos]):
                key.append('_')
                excluded.update(c)
            else:
                key.append(c)
                included.update(c)

        for c, qty in excluded.items():
            excluded[c] = max(min(qty, self.get_qty_max(c) - included[c]), 0)

        if excluded.total() > 0:
            key += [':'] + sorted(c for c, n in excluded.items() for _ in range(n))

        return ''.join(key)


    def get_allowed_colors_by_slot(self, pick):
        """
        Returns a list of sets, where slot_colors[i] contains the allowed colors
        for slot i in the guess `pick` using a bipartite matching approach.
        
        Args:
            pick (str or list): The current guess, e.g., "AAXXX".
        
        Returns:
            list[set[Color]]: List of sets of allowed colors for each slot.
        """
        # Convert pick to list
        if isinstance(pick, str):
            pick = list(pick)

        letters = self.letters.copy() 

        pick_counts = Counter(pick)
        extra_counts = pick_counts.copy()
        extra_counts.subtract(self.letters)

        extra_rows = sum(([c] * -n for c, n in extra_counts.items() if n < 0), [])
        extra_rows.sort(key=self.char_ord.get)
        extra_cols = sum(([c] * n for c, n in extra_counts.items() if n > 0), [])
        extra_cols.sort(key=lambda c: self.char_ord.get(c, float('inf')))
        extra = len(extra_rows)


        pick_rows = {}
        for r, c in enumerate(pick + extra_rows): # do we include extra here?
            pick_rows.setdefault(c, []).append(r)

        # np.fromiter((pick_counts[c] - self.get_qty_max(c) for c in pick_counts), dtype=int)

        # Initialize 5+nx5+n matrix
        M = np.ones((self.length + extra, self.length + extra), dtype=int)
        # M[self.length:,self.length:] = 0 # set extra rows to not be black
        # M[:self.length,:self.length] = self.viable[None] # Extra rows can only be linked with Unknown characters
        
        # Apply constraints
        for i, c in enumerate(pick + extra_rows):
            if c == ' ' or c == '':
                continue
                # spaces / empty strings should match anything I think. But also should
                # be able to be black. But do they get extra rows? maybe not match themselves?
                # only themselvels?
                # I think we'll match all for now

            # Confirmed green: only diagonal is 1
            if c in self.confirmed and i < self.length and self.confirmed[c][i]:
                M[i, :] = 0
                M[:, i] = 0
                M[i, i] = 1
            else:
                # Rule out slots where c is not allowed
                for j in range(self.length):
                    if not self.char_allowed_slot(c, j):
                        M[i, j] = 0
                for j in range(len(extra_cols)):
                    if c is None and i >= self.length:
                        #M[i, i] = 1  # mark diagonal for nones // mistaken
                        M[i, j] = int(extra_cols[j] not in self.blacklist)
                        # I think this should be 1 for anyting not in blacklist
                        # am i missing sth?
                    elif c != extra_cols[j]:
                        M[i, j + self.length] = 0


        # c is the letter, n is the multiplicity, must be > 1
        # sweeping left (or up) to reduce yellows (which matches them to the right)
        for c, n in [(c, n) for c, n in pick_counts.items() if n > 1]:
            # inner group just finds the place for multiple chars
            # probably a better wya to do this

            # for i in reversed(i for i, pc in enumerate(pick) if pc == c): # rows that are c
            #     ...
            for i in reversed(pick_rows[c]): # rows that are c
                qty_max = self.get_qty_max(c)
                if not self.char_allowed_slot(c, i) and n > qty_max:
                    # force black
                    M[i, self.length:] = 0
                elif c in self.confirmed and self.confirmed[c][i]:
                    qty_max -= 1
                elif self.char_allowed_slot(c, i) and n > qty_max:
                    M[i, self.length:] = 0 # remove yellows?
                    M[i, i] = 1
                n -= 1

        # Compute OR matrix
        R = compute_or_matrix(M)
        
        # Translate to colors
        slot_colors = [set() for _ in range(self.length)]
        for i, c in enumerate(pick):
            # if c == ' ':
            #     continue
            # Green if connected to any solution slot
            if R[i, i]:
                slot_colors[i].add(Color.GREEN)
            # Black if connected to any black column
            if any(R[i, j] for j in range(self.length, self.length + extra)):
                slot_colors[i].add(Color.BLACK)
            # Yellow is possible if any non-diagonal slot is 1
            if any(R[i, j] for j in (*range(0, i), *range(i + 1, self.length))):
                slot_colors[i].add(Color.YELLOW)

        print(f"M = {M}")
        print(f"R = {R}")

        return slot_colors




class AbstractGuessManager(metaclass=ABCMeta):

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def update_guess_result(self, word, colors):
        pass

    @abstractmethod
    def undo_last_guess(self):
        pass

    @abstractmethod
    def get_suggestions(self):
        pass

class DecisionTreeGuessManager(AbstractGuessManager):
    def __init__(self, lexicon, candidates, dt=None, length=5):
        # self.tree = read_decision_tree_set(filename)
        if isinstance(lexicon, str):
            lexicon = [w for w in load_word_list(lexicon) if len(w) == length]
        self.lexicon = tuple(sorted(set(lexicon)))

        if isinstance(candidates, str):
            candidates = [w for w in load_word_list(candidates) if len(w) == length]
        self.candidates = tuple(sorted(set(candidates)))

        if isinstance(dt, str):
            self.dt = read_decision_tree(dt)
        elif isinstance(dt, (list, tuple)):
            self.dt = routes_to_dt(dt)
        else:
            self.dt = dt if dt is not None else {}

        self.tree = None
        # self._cond = threading.Condition()
        self._stop = False
        self._stop_event = threading.Event()
        self._stop_lock = threading.Lock()
        self._search_in_progress = False

        self.reset() # sets self.filter

    def stop(self):
        with self._stop_lock:
            if self._search_in_progress:
                self._stop_event.set()
                self._search_in_progress = False
            else:
                ... # no search active. What do we do about this? No effect?

    def reset(self):
        # self.state = []
        self.pick_word_hist = []
        self.clue_color_hist = []
        self.filter = GuessFilter()

    def update_guess_result(self, word=None, colors=None):
        if word and colors:
            colors = tuple(colors)
            self.pick_word_hist.append(word)
            self.clue_color_hist.append(colors)
            self.filter.update_guess_result(word, colors)

    def undo_last_guess(self):
        if self.pick_word_hist and self.clue_color_hist:
            self.pick_word_hist.pop()
            self.clue_color_hist.pop()
        else:
            ...

        new_filter = GuessFilter()
        for word, colors in zip(self.pick_word_hist, self.clue_color_hist):
            new_filter.update_guess_result(word, colors)

        self.filter = new_filter

    def get_suggestions(self):

        with self._stop_lock:
            if self._search_in_progress:
                return None, None # is this right? or maybe error condition?
            else:
                self._search_in_progress = True

        # pick_word_hist, clue_color_hist = tuple(zip(*self.state)) or ((), ())

        if not self.tree:
            self.tree = WordleTree(self.candidates, self.lexicon, self.dt)

        def dt_lookup():
            branch = self.dt
            clue = ()

            for word, clue in zip(self.pick_word_hist, self.clue_color_hist):
                branch = branch.get(word, {}).get(clue, {})

            return [] if branch is None else [*branch.keys()]

        suggestions = dt_lookup()

        if not suggestions:
            self.regenerate_tree()
            suggestions = dt_lookup()

        rem_candidates = self.tree.get_valid_candidate_words(self.pick_word_hist,
                                                             self.clue_color_hist)
        
        with self._stop_lock:
            self._search_in_progress = False
            self._stop_event = threading.Event()

        return suggestions, rem_candidates

    def regenerate_tree(self):

        routes = self.tree.mod_dfs_beam_search(pick_hist=self.pick_word_hist,
                                               clue_hist=self.clue_color_hist,
                                               parallel=True,
                                               abort=self._stop_event)
                                               
        new_dt = routes_to_dt(dt_to_routes(self.dt) + list(routes))
        self.dt = new_dt

    def get_allowed_colors_by_slot(self, pick):
        return self.filter.get_allowed_colors_by_slot(pick)


class GuessManager(AbstractGuessManager):

    def __init__(self, filename, length=5):
        self._catalog = load_word_list(filename)
        self.lexicon = tuple(w for w in self._catalog if len(w) == length) # the dictionary of words being considered as possibilities
        self.length = length
        self.reset()

    def reset(self):
        self.filter = GuessFilter(length=self.length, lexicon=self.lexicon)
        self.history = []
        self.redo = []
        self.update_frequencies()

    def update_guess_result(self, word, colors):
        self.history.append(self.filter)

        self.filter = GuessFilter.from_source(self.filter)
        ##################################################
        # XXX Testing CODE
        tmp_fc = self.filter.to_filter_code()
        gf = GuessFilter.from_filter_code(tmp_fc, self.filter.length, self.lexicon)

        # checking filter equivalence
        if not (gf.viable == self.filter.viable and gf.confirmed == self.filter.confirmed and gf.blacklist == self.filter.blacklist):
            pass

        self.filter = gf
        ##################################################
        
        self.filter.update_guess_result(word, colors)
        self.update_frequencies()

    def update_frequencies(self):

        # letter_mult_ordered
        self.candidates_mult = [letter_mult_ordered(word) for word in self.filter.candidates]

        self.freq = Counter(c for c in chain.from_iterable(self.filter.candidates))
        self.freq_mult = Counter((c, n) for (c, n) in chain.from_iterable(self.candidates_mult))

        # occurances of each character (key)
        # sorted_chars = sorted(self.freq_candidates.keys(), key=lambda c: self.freq_candidates[c])
        # chars sorted by frequency (lowest first i think)

        # rank_map = lambda rank: abs(((len(sorted_chars) - 1)  - 2 * rank) // 2)
        # seems to be distance from the middle of sth?, b/c rank is also magnitude ~ len(sorted_chars)
        # could this be done more easily?  maybe i did it b/c we center it & we want 2 zeros or 2 ones

        # rank = {c:rank_map(r) for (r, c) in enumerate(sorted_chars)}
        # self.freq_candidates = rank

        # frequency a char per row (by multiplicity)
        self.freq_by_slot_mult = [letter_mult_ordered(col) for col in zip(*self.candidates_mult)]

        # >>> list(zip(*arr))


    def undo_last_guess(self):
        # self.redo.append(self.guess)
        self.filter = self.history.pop()
        self.update_frequencies()


    # just some ideas... but we could gather statistics about say... words that have 1 letter, how likely they are to have
    # another letter. but really we have that with the filtered candidates



    @call_counter(100)

    def rate_guess(self, word):
        # counts = Counter(word)
        # score = sum(letter_freq[letter] for letter in set(word))
        # if word == 'AEONS':
        #      pass

        clone = self.filter.from_source(self.filter)
        worst_guess_result = self.filter.get_worst_case_guess_result(word)
        clone.update_guess_result(word, worst_guess_result)
        # should we just update the filter here?
        return clone.score()

    def guess_heuristic_score(self, word):

        # guess = self.guess

        # canddate unguessed letter counts
        # maybe give a slight bonus for guess validity
        counts = Counter(word)

        char_pos = {}
        for i, c in enumerate(word):
            char_pos[c] = char_pos.get(c, set())
            char_pos[c].add(i)

        letter_scores = []

        # HOW many slots would this letter kill? count free instances in undetermined
        #  slots could be eliminated?
        #     How do we count it? if that char is in a definite slot, then you need
        #      >1 of them to determine anything
        # 
        # If it's not required, 
        # 
        # if the letter has det quantity, defintley mod =0

        for c, qty in counts.items():
            score = self.freq_candidates.get(c, 0)
            # on the fence about how to use this, b/c high freq chars won't narrow
            # the field all that much in the case of a hit, but they do in case of
            # a miss
            modifier = 0
            if c not in self.filter.forbidden:
                if c not in self.filter.required:
                    modifier += 19
                    modifier += min(qty, self.filter.qty_maxes[c], len(self.filter.char_slots[c]))
                    # possibly redundant min check above
                else:
                    for i in char_pos[c]:
                        if c in self.filter.slots[i] and len(self.filter.slots[i]) > 1:
                            modifier += 1
            else:
                modifier = 0

            letter_scores.append(score * modifier)
        return - sum(letter_scores)

        # for c, qty in counts.items():
        #     modifier = 1
        #     #self.char_slots[c]
        #     score = self.freq_candidates.get(c, 0)
        #     if c not in self.forbidden:
        #         if c not in self.required:
        #             modifier *= 20
        #             if qty > 1 and qty < len(self.char_slots[c]) and qty <= self.qty_maxes[c]:
        #                 modifier += 1
        #                 # XXX do i need to check both here?
        #         else:
        #             if all(len(self.slots[i]) > 1 for i in char_pos[c]):
        #                 modifier = 0
        #     else:
        #         modifier = 0

        #     letter_scores.append(score * modifier)
        # return - sum(letter_scores)

        # unguessed/unmaxed letters & their frequency

        # maybe look for a filter heuristic...
        # how many excluded / blacklisted letters
        # how many required letters?
        # how many yellow spots would we narrow down?
        # spots that are green can be used for other things. so words that match a singele spot
        # should not get any score


        # untested high frequencey  (not in excluded) # nbr of letters in word not in excluded
        # untested low frequency (not in excluded)
        # yellow letters w/ open upper limit 
        # yellow letters w/ definite quantity
        # green letters w/ open upper limit 
        # green letters w/ definite qty

    
    def get_suggestions_orig(self):


        # guess = self.guess


        if not self.history:
            print('setting first guesses')
            first_guesses = [ 'SALET', 'TARES', 'RATES', 'CRATE', 'SLANT', 'LEAST',
            'PRATE', 'ROAST',]

            heuristic_ratings = ((self.guess_heuristic_score(word), word) for word in first_guesses)
            candidate_ratings = ((self.guess_heuristic_score(word), word) for word in first_guesses)
        else:
            # ratings = ((self.rate_guess(word), word) for word in self.candidates)
            #ratings = ((self.rate_guess(word), word) for word in self._base_words)
            heuristic_ratings = ((self.guess_heuristic_score(word), word) for word in self.filter._lexicon)
            candidate_ratings = ((self.rate_guess(word), word) for word in self.filter.candidates)
            # XXX sth is happening here, and ratings are wrong, geting 0 for many things
            # somehow candidates maybe?
            #ratings = ((self.rate_guess(word), word) for word in self.candidates)
            # heapify

        best_heuristic = nsmallest(20, heuristic_ratings)
        best_candidates = nsmallest(20, candidate_ratings)

        return {'narrowers':[word for (_, word) in best_heuristic],
                'candidates':[word for (_, word) in best_candidates]}

        # we can concisder invalid guesses that might narrow the field much more,
        # but need to be sure that if we assume it will be marked bad in a spot, that it
        # is possible for it to be marked bad there.  So.. we need to be sure that the
        # letters int the guess conform to min/max? probably, otherwise it's a wasted letter
        # we might could still consider it, if there is some more compelling reason, ohwever
        # it should at least not increase the rating of that word.

        # no bonus for letter that is in self.exlude 0
        # slight bonus for letter that is in required, but only if not in bad pos
        # if not in either, than bonus according to letter frequency

    def get_suggestions_Y(self):


        # guess = self.guess
        heuristic_ratings = ((self.heuristic_Y(word), word) for word in self.filter._lexicon)
        candidate_ratings = ((self.heuristic_Y(word), word) for word in self.filter.candidates)

        best_heuristic = nlargest(20, heuristic_ratings)
        best_candidates = nlargest(20, candidate_ratings)

        return {'narrowers':[word + ' ' + str(_) for (_, word) in best_heuristic],
                'candidates':[word + ' ' + str(_) for (_, word) in best_candidates]}

        # we can concisder invalid guesses that might narrow the field much more,
        # but need to be sure that if we assume it will be marked bad in a spot, that it
        # is possible for it to be marked bad there.  So.. we need to be sure that the
        # letters int the guess conform to min/max? probably, otherwise it's a wasted letter
        # we might could still consider it, if there is some more compelling reason, ohwever
        # it should at least not increase the rating of that word.

        # no bonus for letter that is in self.exlude 0
        # slight bonus for letter that is in required, but only if not in bad pos
        # if not in either, than bonus according to letter frequency

    get_suggestions = get_suggestions_Y

    def heuristic_Y(self, guess):
        ...
        # here, gonna do just pure min (likelihood) of the letter (w / mults, being in/out the word.)
        # word_count = len(self.filter.candidates)
        #word_mult = self.freq_augmented

        # word_mult = letter_mult_ordered(word)

        total = 0
        for c, n in letter_mult_ordered(guess):
            if (c, n) in self.freq_mult:
                score = self.freq_mult[(c, n)]
                score = min(score, len(self.filter.candidates) - score)
                total += score

        return total


    def heuristic_X(self, guess):



        word_mult = self.freq_augmented
        ctr = Counter(guess)
        Counter([count_letter_util(word) for word in guess.candidates])

        l = []

        for letter, qty in ctr.items():
            for i in range(1, qty + 1):
                l.append((letter, i))

        set(l)

        # you were thikning about seeing how many wors have 1st Rs, vs 2nd Rs..

        # how many non-black chars?
        # how many untried chars? s/l chars w/ UL > 0 and LL = 0?
        # so.. we figure out the score for all the chars based on frequency
        # and add them up, but, if we know that a spot is green, then
        # we should specifically disallow that letter on it, i.e. any words
        # that match it should get 0 points for it, b/c we're not gaining any
        # knowledge from it.

        # what if it's only a choice between 2 chars? should we adjust the
        # reward? # maybe we should consider how many open spots that char has
        # in our pattern

        #  * how many spots that char could occupy
        #  * frequency of that char in possible solutions
        #  * so maybe.. lower choices shoudl reduce the score for that slot , or
        #    rather the possible letters that occupy that slot
        #  * so, the score should be adjusted by the # of possible slots it could
        #  * :: frequencey in candidates,  freq in slot filters, 

        # a problem with the green slots is, you'll get at least a yellow even
        # when you put that letter in another slot, unless it's a duplicate in the guesss
        # so you don't get as much info as a letter that has not been guessed at all.
        # so, letters not yet guessed will have no lower limit && should occur in
        #  multiple? other spots
        # * upper limit 1 & lower limit 1 mean no contribution 

        # so i'm thinking we shouldn't total all the char counts, b/c...
        # we don't want to weight chars for known slots.
        # what about the weights for a duplcated char?  i'm thinking combine them for weights from a particular slot..
        # but maybe just weight that slot 0...  on the count.. ? what does that mean
        # so i'm thinking.. 2nd s should have weight if we can place  a 1st s, but the 1st s should have no weight.
        # but should 1st s really be 0? it should probably be close. it shoudl definitely be 0 if in it's known slot
        # but maybe outside its slot could be of some use.
        # maybe.. figure out slot weight
        # but maybe a 1st s outside the slot has a 1/n chance of matching a 2nd s. so maybe weight it acc to probability
        # of matching a 2nd/3rd s 
        # so maybe the weight of a known slot should be acc to Pr(yellow), which woud be the totals of all Ys outside the 
        # slot (and all will be outside of the slot on the filter). So a cumulative count probably does have value.
        # for calculating letters in slots that are not matched to it.
        # if a green and maybe yellow are possibilities, then what? total Ys 
        # Pr(New yellow), # if in known spot, then just total frequency of yellow if no yellow before
        # # Pr(New green)
        # Pr(New yellow) - Pr(new green)
        # if we got yellow b4, then Pr(new green) would be 1/4 in another spot, at least
        # so let's assume the min qty is 0 & UL is 1-5
        #                  Pr(Yellow) = # words containing C - # words containgin C in this slot
        #                  Pr(Green) (all words containg C in this slot): so.. if 100% we ignore : do we use measure of entropy?
        #                  So maybe just add total Pr() of containing it to heuristic


        # seems to me that likelihood of in vs/ liklihood of out are both relavent, as they tell us info... and divide the trees
        # so.. maybe we could give it th min?

        for c, n in word_mult:

            if self.filter.qty_mins[c] == 0 and self.filter.qty_maxes[c] > 0 : # any Y/G square will be new
                ...
                slot_score = self.freq_candidates_augmented[c] # for all slots
                # pr of green...
                # also need to know... are we a c1? a c2?, so even if we're a c2, it tells us something..? yes?,but maybe not much more.
                # so maybe we only get a 'green bonuords' here

        # what if Min qty is 1?
        #           * got green b4
        #               * only consider Pr(C2)
        #           * got yellow b4
        #               *Pr(Green | No C2) +  Pr(green )
        #           * # so we should consdier guesses with 2nd occurances? might get UL
        #           # can we find Pr( G 2?)
        #           # also have a 1/n-1 chance of finding a green. How useful is that? It elimintaes all other possibilities on that slot
        #           # or 
        # what if mqty is 2+?
        #           * 2 green b4
        #               only consider Pr(C3)
        #           # 1 green, 1 yellow
        #               Pr(new green) #
        #           # 2 yellow
        #               Pr(new yellow) # this gives us 2 greens if len=5
        # what if mqty is 3+?
        #           * got 3 yellows is not possible
        #           * got 2 yellows i Green
        #                   othere greens are duducible if len=5
        #           * got 2 greens & 1 yellow
        #                   2 rem spots, 50/50 (1 guess will get it for sure)


def letter_mult_ordered(word):
    """
    Returns a tuple of each letter and the number of times it has occured from
    left to right.  separate characters
    """
    counter = Counter()
    return tuple((c, counter.update(c) or counter[c]) for c in word)




if __name__ in '__main__':
    from argparse import ArgumentParser

    def parse_arguments():
        """Parses command-line arguments using argparse.

        Returns:
            Namespace: An object containing parsed arguments.
        """

        parser = ArgumentParser(description="Filter words by length from a dictionary")

        # Optional argument for dictionary file
        parser.add_argument(
            "-d", "--dictionary", type=str, default='altdict.txt', help="Path to a dictionary file (optional)"
        )

        # Required argument for word length
        parser.add_argument("-l", "--length", type=int, default=None, help="Length of words to filter")

        parser.add_argument("-n", "--no-prompt", action="store_true", default=False, help="Disable prompting for initial guess (optional)")

        return parser.parse_args()


    args = parse_arguments()
    dictionary_file = args.dictionary
    word_length = args.length
    prompt = not args.no_prompt

    first_guesses = [ 'SALET', 'TARES', 'RATES', 'CRATE', 'SLANT', 'LEAST',
    'PRATE', 'ROAST',]


    while word_length is None:
        try:
            word_length = int(input("Enter the length of word to guess: "))
            break  # Exit the loop if input is valid
        except ValueError:
            print("Invalid input. Please enter an integer.")

    manager = GuessManager(length=word_length, filename=dictionary_file)

    while prompt:
        ans = input("Calculate initial guess? [Y/N]: ").upper()[:1]
        if ans:
            if ans == 'Y':
                print(f'Top guesses: {manager.get_suggestions()}')
            elif ans == 'N':
                break
        print(f"Invalid input. Please try again.")

    while True:

        while True:
            guess = input("Enter a word to try: ").upper()
            if len(guess) == word_length and guess.isalpha():
                break  # Exit the loop if input is valid
            elif guess == 'Q':
                raise SystemExit('exiting')
            print(f"Invalid input. Please enter a string of letters of length {word_length}.")

        while True:
            colors = input("Enter the colors : G: Green, B: Black, Y:Yellow: ").upper()
            if len(guess) == word_length and all(c in 'BGY' for c in colors):
                break  # Exit the loop if input is valid
            print(f"Invalid input. Please enter a string of letters 'AGY, length {word_length}.")
        manager.update_guess_result(guess, colors)
        print(f'Total candidates: {len(manager.guess.candidates)}')
        guesses = manager.get_suggestions()
        print(f'Top narrowing guesses: {guesses['narrowers']}')
        print(f'Top candidate guesses: {guesses['candidates']}')
        if (len(guesses['candidates'])) <= 1:
            break

