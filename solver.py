#! /usr/bin/env python


# we can use statistics to calculate the liklihood of a slot being a character
# say if we know that we have 'abc', or 'abcde' then we can defnitely mark out
# all remaining letters on the slot filters.  or in the case of 'abc' we know that
# any one of the slots has a higher probability of being a b or c  than the other
# choices... but we also know that the other choices must be there somewhere.
# so strategicly it might be good to pick a letter we know is included, but
# at a slot where it hasn't been tried.
# so how much could a choice narrow the field? how could we measure that..
# could we calculate it? say.. assume that each remaining word is equally likely
# then, calculate the narrowing effect for each one given the guess and the actual
# word.


import argparse
from collections import Counter
from string import ascii_uppercase
from heapq import nsmallest, nlargest
from call_counter import call_counter
from wordle_game import Color
from itertools import chain

# XXX question.. can we find a set of 4/5/6 words with maximum letter coverage?
# how might we do that?
#  level filters..

# problem tho.. multiple orders will be problematic

# 26 x spot(len)

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



letter_prop = {'E': 56.88, 'M': 15.36, 'A': 43.31, 'H': 15.31, 'R': 38.64, 'G':
12.59, 'I': 38.45, 'B': 10.56, 'O': 36.51, 'F': 9.24, 'T': 35.43, 'Y': 9.06,
'N': 33.92, 'W': 6.57, 'S': 29.23, 'K': 5.61, 'L': 27.98, 'V': 5.13, 'C': 23.13,
'X': 1.48, 'U': 18.51, 'Z': 1.39, 'D': 17.25, 'J': 1.0, 'P': 16.14, 'Q': 1.0}

starting_words = ['KIOEA', 'AOIFE', 'AUETO', 'AEONS', 'AOTES', 'STOAE', 'AROSE',
'OREAS', 'SEORA', 'AESIR', 'ARIES', 'ARISE', 'RAISE', 'SERAI', 'ALOES', 'ALOSE',
'OSELA', 'SOLEA', 'OUSIA', 'AUREI', 'URAEI', 'HOSEA', 'OSHEA', 'AISLE', 'ELIAS',
'SAITE', 'TAISE', 'ANISE', 'INSEA', 'SIENA', 'SINAE', 'ORIAS', 'ACIES', 'SAICE',
'AESOP', 'PASEO', 'PSOAE', 'OSAGE', 'OUABE', 'HEIAU']

def load_word_list(filename):
        with open(filename) as f:
            return tuple(line.split(maxsplit=1)[0] for line in f if line)



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

    def __init__(self, length=5, lexicon=None):

        self.length = length # length of the word
        self._lexicon = lexicon # the dictionary of words being considered as possibilities
        self.unplaced = length # ?number of letters that are still undetermined?
        self.qty_mins = {c: 0 for c in ascii_uppercase} # minimum number of each character that must be present for a guess to be valid
        self.qty_maxes = {c: length for c in ascii_uppercase} # maximum number of each letter that can be present and the word still be valid
        self.required = set() # letters that must be present for a word to be valid
        self.forbidden = set() # letters that must not be present for a word to be valid
        self.slots = [set(ascii_uppercase) for _ in range(length)] # sets of possibly valid characters for each position in the word
        self.char_slots = {c: set(range(length)) for c in ascii_uppercase} # XXX redundant?
        self.candidates = self._lexicon # remaining words that are still valid based on filters

    def clone_state(self, source):
        self.length = source.length
        self.unplaced = source.unplaced
        self.qty_mins = source.qty_mins.copy()
        self.qty_maxes = source.qty_maxes.copy()
        self.required = source.required.copy()
        self.forbidden = source.forbidden.copy()
        self.slots = [slot.copy() for slot in source.slots]
        self.char_slots = {c:s.copy() for (c, s) in source.char_slots.items()}
        self._lexicon = source._lexicon
        self.candidates = source.candidates


    @classmethod
    def from_source(cls, source):
        new = cls(length=source.length)
        new.clone_state(source)
        return new

    @staticmethod
    def make_colors(target, guess):
        target_counts = Counter(target)
        guess_counts = Counter(guess)

        # so if guess has qty above target, we need to have a black for that one
        # mark et green or orange first
        # so mark the rightmost non-green ones i guess
        black = {c: qty - target_counts.get(c, 0) for c, qty in guess_counts.items()}

        result = [Color.GREEN if t == c else Color.YELLOW for (t, c) in zip(target, guess)]

        for i in range(reversed(len(result))):
            if result[i] == Color.YELLOW and black[guess[i]] > 0:
                black[guess[i]] -= 1
                result[i] = Color.BLACK


        return result

    def matches_slot_map(self, word):
        '''
        Determines whether a word guess could be the target word according to
        the posititional whitelist
        '''
        return all(l in slot for (l, slot) in zip(word, self.slots))

    
    def fulfills_mins(self, word):
        '''
        Checks to see if a particular word contains all the minimum
        multiplicities for each letter that have been determined to be in the
        solution '''
        has = Counter(word)
        return all(has.get(c, 0) >= self.qty_mins[c] for c in self.required)


    def within_maxes(self, word):
        '''
        Checks to see if a particular word does not contain more than the
        maximum multiplicities of any letters that have been determined to be in
        the solution
        '''
        has = Counter(word)
        return all(qty <= self.qty_maxes[c] for (c, qty) in has.items())


    def guess_valid(self, word):
        '''
        Determines whether a particular guess could be the target word
        '''
        return (self.fulfills_mins(word) and self.within_maxes(word) and
                self.matches_slot_map(word))
        

    def score(self):
        return len(self.candidates)


    def update_candidates(self):
        backup = self.candidates
        self.candidates = tuple(filter(self.guess_valid, self.candidates))
        # self.update_frequencies()
        if len(self.candidates) == 0:
            pass

    def update_filters(self, word, colors):
        # XXX another idea, what if we kept both a slots, and
        # dict (c,set) of numercal slots possibly held by each letter?
        # the size would say something about the max count
        # maybe have a hard max tracker for any black squares seen

        # XXX ooo.. just thoght that maybe we should treat orange dff than blk in
        # update filters maybe.. cuz you could get a black on a letter, but 
        # not need to put it in forbidden if it's the 2nd or 3rd
        counts = Counter(word)
        match_count = {}
        mismatch_count  = {}
        if isinstance(colors, str):
            colors = [Color.map(c) for c in colors]

        for pos, (c, color, slot) in enumerate(zip(word, colors, self.slots)):
            if color == Color.GREEN:
                slot &= {c}
                match_count[c] = match_count.get(c, 0) + 1
            elif color == Color.BLACK:
                slot.discard(c)
                # for new maxes
                mismatch_count[c] = mismatch_count.get(c, counts[c]) - 1
                self.char_slots[c].discard(pos)
                # update restricted and requried maybe
            elif color == Color.YELLOW:
                slot.discard(c)
                match_count[c] = match_count.get(c, 0) + 1
                self.char_slots[c].discard(pos)
                # update required somehow

        # update required and restriction letter multiplicites
        for c, qty in match_count.items():
            self.qty_mins[c] = max(self.qty_mins.get(c, 0), qty)
            self.required.add(c)

        for c, qty in mismatch_count.items():
            qty = min(self.qty_maxes.get(c, len(self.char_slots[c])), qty)
            self.qty_maxes[c] = qty
            if qty == 0 and c not in self.forbidden:
                self.forbidden.add(c)
                self.char_slots[c].clear()
                for pos in self.char_slots[c]:
                    self.slots[pos].discard(c)
                # for slot in self.slots:
                #     slot.discard(c)

        # also need to check for the case that the multiplicites of each letter
        # is known completely, then we can update the slots to only include possible
        # leters.  so.. if all letters have a req in the required & excluded dicts

        #for c, count in slot_count.items():
        # c a can we jst look at slots that changed/ or chars?
        for c in ascii_uppercase: # can we restrict to just self.required/excluded?
            count = len(self.char_slots[c])


            if count > 0 and count == self.qty_mins.get(c, 0):
                for slot in self.slots:
                    if c in slot:
                        slot &= {c}




        # if all the letters and their quantites are known, trim down the
        # available letter slots
        if sum(self.qty_mins.values()) == self.length: # this works
            filter_set = {c for (c, val) in self.qty_mins.items() if val > 0}
            for slot in self.slots:
                slot &= filter_set

        elif sum(self.qty_maxes.get(c, self.length) for c in ascii_uppercase) == self.length:
            filter_set = {c for c in ascii_uppercase if self.qty_maxes.get(c, self.length) > 0}
            for slot in self.slots:
                slot &= filter_set
                ...


        # also, maybe update required to a minimum amount for a letter if it happens to be
        # less than the number of slots occupied soley by that letter

        occupied = Counter([*slot][0] for slot in self.slots if len(slot) == 1)
        for c, qty in occupied.items():
            self.qty_mins[c] = max(self.qty_mins.get(c, 0), qty )

        # XXX idea: the maxes have to be <= the total counts in the slots
        # how do we track that efficiently? lower it each time we see a new yellow/black?
        #

        # XXX how do we do that thing? 
        # Counter(c for c in slot for slot in self.slots)
        # but maybe we can just do this for required/forbidden for speed?
        # what if we keep a char slot count for each one?

        # update minimums? in exlude by slots that don't contain that letter
        ### XXX use char_slots to do this more effiiently i think
        occupied = Counter(c for c in slot for slot in self.slots)
        for c, qty in occupied.items():
            self.qty_maxes[c] = min(self.qty_maxes.get(c, self.length), qty)
            # but is that self.length really correct if some letters are known difinitively?
            # should we have a self.unplaced?
        if (self.required & self.forbidden):
            pass


    def update_guess_result(self, word, colors):
        self.update_filters(word, colors)
        self.update_candidates()
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


class GuessManager:

    def __init__(self, filename, length=5):
        self._catalog = load_word_list(filename)
        self.lexicon = tuple(w for w in self._catalog if len(w) == length) # the dictionary of words being considered as possibilities
        self.length = length
        self.reset()

    def reset(self):
        self.filter  = GuessFilter(length=self.length, lexicon=self.lexicon)
        self.history = []
        self.redo = []
        self.update_frequencies()

    def update_guess_result(self, word, colors):
        self.history.append(self.filter)
        self.filter = GuessFilter.from_source(self.filter)
        self.filter.update_guess_result(word, colors)
        self.update_frequencies()
        # need to update the filters
        # 

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

        clone = GuessFilter.from_source(self.filter)
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


# seems useful for something, maybe calculating letter frequency. But match
# liklihood.. b/c a second S could be matched by a single S in the guess.
# like if it's on the same spot.




if __name__ in '__main__':

    def parse_arguments():
        """Parses command-line arguments using argparse.

        Returns:
            Namespace: An object containing parsed arguments.
        """

        parser = argparse.ArgumentParser(description="Filter words by length from a dictionary")

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

