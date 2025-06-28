import os
import sys
import numpy as np

from itertools import batched, count, chain
from collections import namedtuple, Counter, deque, defaultdict
from dataclasses import dataclass, field
from functools import partial, cmp_to_key
import tempfile
import heapq
import logging
from lazy_handler import LazyRotatingFileHandler

from base64 import b64decode, b64encode
from string import ascii_uppercase

from wordle_game import Color
from rank_comb import generate_combination, rank_combination, rank_multiset, generate_multiset
from solver import GuessFilter, load_word_list
from filter_code import FilterCode
from tree_utils import read_decision_tree, route_list_to_dt, routes_to_text, routes_to_text_gen, dt_to_routes
from wordle_game import get_clue_for_secret
from utils import LazyList
import cProfile
import pstats
import json
from operator import itemgetter
import hashlib
from traceback import format_exception_only
from textwrap import dedent
# from joblib import Parallel, delayed
from concurrent.futures import ProcessPoolExecutor, as_completed

def dict_gen(seq, store):
    for key, value in seq:
        store[key] = value
        yield (key, value)


def setup_logger(prefix=None):
    pid = os.getpid()
    log_file = f"log_{pid}.log"
    logger = logging.getLogger("Wordle Tree Logger")
    logger.setLevel(logging.DEBUG)
    handler = LazyRotatingFileHandler(prefix=prefix, filename=log_file, maxBytes=10*(1024 ** 2), backupCount=3)
    logger.addHandler(handler)
    stderr_handler = logging.StreamHandler(sys.stderr)
    logger.addHandler(stderr_handler)
    return logger

logger = setup_logger()
logger.warning()

class StateNode:
    # Keys a single filter state where various word options will be explored,
    # evaluated and unltmitely decided on.
    # This node isn't uniquely identified by the order of word choices that
    # produced it. It could have been produced by the same set of words in a
    # different order, or even a disparate set of words that collectively have
    # the same letters in the same positions and the same quantites per word.

    def __init__(self, state_store=None, option_store=None, filter_=None, id_=None):
        self.state_store = state_store if state_store is not None else {} # keyed by filter
        self.option_store = option_store if option_store is not None else {}
        self.filter = filter_ # guess filter
        self.id = id_ if id_ is not None else self.filter.to_filter_code().to_string()
        self._option_by_guess_code = {} # {guess_code : OptionNode} # possible words to try
        self.top = [] # top ranked choices: OptionNodes?
        self._depth = float('inf')
        self._filter_picks_updated = False

        self.top_picks = None
        self.prev_opts = []
        self.cur_results = None
        self.cur_opt_node = None
        self.cur_routes = []
        self.pick = None
        self.routes = None


    def get_option_by_guess(guess):
        guess_code = self.filter.normalize_guess(guess)
        return self.get_component(guess_code)


    def get_option_by_guess_code(self, guess_code):
        return self._option_by_guess_code.get(guess_code)

    def max_depth():
        # I'm thiking we need to change depth each time top is changed
        # also, we should just return 1 if the state is solved

        if self.is_solved():
            return 1
        elif self._max_depth != float('inf'):
            return self._depth
        elif not top:
            self._max_depth = float('inf')
        else:
            self._max_depth = 1 + max(node.depth() for node in top)

        return self._max_depth

        # I don't think cycles will be a problem here, but check

    def child_count():
        if self._child_count is None:
            ...
            for node in self.top:
                self._child_count = sum(opt.child_count for opt in self.top)

        return self._child_count

    def is_solved(self):
        return self.filter is not None and len(self.filter.candidates) == 1


    def get_guess_dict(self):
        return self.filter.picks # after some kind of ranking, maybe truncate

    def expand_guess_code(self, guess_code):
        guess = self.get_guess_dict()[guess_code]
        return self.expand_guess(guess)


    def expand_guess(self, guess):

        if not self._filter_picks_updated:
           self.filter.update_picks()
           self._filter_picks_updated = True

        ## on = self.option_store.setdefault((guess_code, self.id), None)


        ##if on is None:
            ## on = OptionNode(self.option_store, self.state_store, self, guess)
        on = OptionNode(self.option_store, self.state_store, self, guess)
        # else:
        #     pass # I kind of feel this should never hanppen. Why?...
        #     # if the option has already been expanded.. from the state
        #     # then the StateNode must exist alreday in the state_store
        #     # and thus, we're needlessly recreating an OptionNode


        ## self.option_store[(guess_code, self.id)] = on

        ## self.option_by_guess_code[guess_code] = on

        # guess_code = self.filter.normalize_guess(guess_word)
        return on


    def expand_all_guesses(self):
        # expand all guesses

        for guess_code, guess in self.get_guess_dict().items():

            if guess_code.count('_') == len(guess_code):
                continue # feel like there should be a slightly better way

            if guess_code not in self.option_by_guess_code:
                self.expand_guess_code(guess_code)
                pass

    def _debug_hook(self):
        self.expand_all_guesses()
        for code, option, in self.option_by_guess_code.items():
            option.expand()
        pass # takes about 33s to do 100 passes of this.. so ~1.5h to expand allxall 1 level
        # maybe do a subset..{of pos solutions? or answers?} say 10%  and then 
        # kinda feel like possible solutions won't increase it that much, just
        # maybe make it go deeper slightly
        # but need to think about the heuristic, so that we don't expand too much
        # the other hueristic picked the word with the most # of diff color codes
        # so big branch factor was seen as an advantage



class OptionNode:
    # Node that represents the expansion from a filter state given an option
    # It will link to other StateNodes based on the result of the option

    # holds a set of possible states from which heruistics will be calculated.
    # so i know that a StateNode can only have 3^5 possible sets in its id set
    # hmm... that's like 2k.  is it too much?

    def __init__(self, option_store=None, state_store=None, source=None, guess=None):


        self.source = source # Source state filter code spawned the results represented by this node
        self.option_store = option_store
        self.state_store = state_store

        self.source_key = self.source.id if source else None
        self.guess_key = self.source.filter.normalize_guess(guess) if source else None
        # self.guess_key = self.source.get_guess_dict()[guess] if source else None
        self.id_key = (self.guess_key, source.id) # 2-tuple of (self.source, guess_key) (unique identifier)
        # if source is not None
        self.guess_set = {guess} # actual guesses that were normalized to the guess key

        self.state_by_result = {}
        self.result_by_state_id = {}

        # can we partially apply a guess w/o any vocab? I think yes/maybe

        # state + response_set
        # what if we have the word, but w/ some blanks.  
        # can we find other words that will be guaranteed the same id_set?
        # or same amt of info


    def depth():
        max(sn.depth for sn in self.state_by_result.values())


    def expand(self):
        # likely inefficient due to the overhead of filter replication
        # can we maybe delay the calculation of actual new resutls and just get?
        # theoretical result states, say if candidates is quite large?

        #  equiv of word_ns? self.source.filter.candidates (picks are words to try)
        # and it groups all of them by result. how is that helpful/efficient?
        # do we filter each child? If so, we could save on that.

        # self.source.filter.update_candidates() # kinda feel this is unecssary
        # maybe a kluge and should have been done already.. but where?
        # when it was expanded by its OptionNode, or at the root

        guess = next(iter(self.guess_set))
        unique_results = {}

        # group canddiates by their result code against the current guess
        for secret in self.source.filter.candidates:
            clue = tuple(get_clue_for_secret(guess, secret))
            unique_results.setdefault(clue, [])
            unique_results[clue].append(secret)

        # now, where do we 

        for clue, candidates in unique_results.items():
            new_filter = GuessFilter().from_source(self.source.filter)
            new_filter.update_filters(guess, clue)
            new_filter.update_picks() # XXX fixes sth, but possibly slow
            fc = new_filter.to_filter_code().to_string()

            ## if fc not in self.state_store:
            ##     new_filter.set_candidates(tuple(candidates))
            ##     sn = StateNode(self.state_store, self.option_store, new_filter, fc) # XXX
            ##     self.state_store[fc] = sn
            ## else:
            ##     sn = self.state_store[fc]
            
            new_filter.set_candidates(tuple(candidates))
            sn = StateNode(self.state_store, self.option_store, new_filter, fc) # XXX

            self.state_by_result[clue] = sn
            self.result_by_state_id[sn.id] = clue

        return self.state_by_result


class WordleTree():
    def __init__(self, all_candidates, all_picks, dt=None):

        # Remove duplicates and maintaining order, while guaranteeing picks
        # are the first candidates
        all_candidates = dict.fromkeys(all_candidates)
        non_candidate_picks = dict.fromkeys(p for p in all_picks if p not in all_candidates)
        all_picks = (*all_candidates, *non_candidate_picks,)
        all_candidates = (*all_candidates,)

        self._all_candidates = all_candidates
        self._non_candidate_picks = non_candidate_picks
        self._all_picks = all_picks

        self.word_idx = {c:i for i, c in enumerate(all_picks)}
        self.idx_word = {i:c for i, c in enumerate(all_picks)}

        filename = self.gen_matrix_filename()

        try:
            self.clue_matrix = np.load(filename)
        except FileNotFoundError as e:
            logger.warning(f"No saved matrix data found, generating: {filename}")
        except (OSError, ValueError) as e:
            logger.warning(dedent(f"""
                           Warning: Unable to read matrix data.
                           {format_exception_only(e)}
                           Falling back to generation""").strip())

        if not hasattr(self, 'clue_matrix'):
            self.clue_matrix = self.precompute_clues(all_picks, all_candidates)

        try:
            os.makedirs(os.path.split(filename)[0], exist_ok=True)
            np.save(filename, self.clue_matrix)
        except OSError as e:
            logger.warning(dedent(f"""
                           Warning: Unable to save matrix data.
                           {format_exception_only(e)}""").strip())

        self.dt = dt

    @staticmethod
    def precompute_clues(picks, solutions):
        clue_matrix = np.empty((len(picks), len(solutions)), dtype=np.uint8)

        for i, pick in enumerate(picks):
            for j, secret in enumerate(solutions):
                clue = get_clue_for_secret(pick, secret)
                clue_matrix[i, j] = Color.ordinal(clue)
        return clue_matrix

    def gen_matrix_filename(self, template='.cache/wordle_matrix_{}.npy'):
        ''' Hash word lists to create a suffix for a np matrix name
        '''
        candidates = sorted(set(self._all_candidates))
        picks = sorted(set(self._all_picks))
        data = (' '.join(candidates) + '\n' + ' '.join(picks)).encode('utf-8')
        suffix = hashlib.sha256(data).hexdigest()
        return template.format(suffix)


    def mod_beam_search(self, candidates=None, picks=None, dt=None):
        ''' Iterative version of mod beam search using a stack '''

        # Set up solution candidates and strategic picks
        if candidates is not None:
            candidates = [*map(self.word_idx.get, candidates)]
        else:
            candidates = [self.word_idx[word] for word in self.all_candidates]

        if picks is not None:
            picks = [*map(self.word_idx.get, picks)]
        else:
            picks = [self.word_idx[word] for word in self.all_picks]

        # Set up decision tree to model 
        dt = self.dt if dt is None else dt

        all_routes = [] # Collection of root to leaf routes
        paths = [((), (), all_routes, [], candidates, picks)]
        c = Counter()


        # lambda e: (e in seen or bool(seen.add(e)))

        while paths and (path := paths.pop()):
            pick_hist, clue_hist, routes, top_subroutes, candidates, picks = path

            if len(candidates) == 1:
                # We've reached a solution
                solution = pick_hist
                if not clue_hist or clue_hist[-1] != Color.all_green():
                    solution += (*candidates,) # avoids extra on expansion

                c.update([len(pick_hist)])
                routes.append(solution)

            elif not top_subroutes:
                # No immediate solution, need to deepen search
                paths.append(path) # reque current path to revisit after subroutes found
                print(f"adding top picks, level = {len(pick_hist)}, {len(candidates) = }")

                # Create an iterator of candidates to consider for top picks
                # results = Parallel(n_jobs=4)(delayed(process_item)(i) for i in range(10))
                candidate_rank = list(self.rank_expand_picks(candidates,
                                                             candidates, pick_hist))

                # Create an iterator of strategic picks to consider for top picks
                pick_rank = LazyList(filter(self.pick_valid,
                                       self.rank_expand_picks(candidates, picks,
                                                              pick_hist)))

                # Capture the filtered picks in a delayed manner
                new_picks = LazyList(pick for _, pick, _ in pick_rank)

                # tee those streams if we still need them for something
                for pick, clue_part in self.get_top_picks(pick_rank, candidate_rank, pick_hist, dt):
                    top_subroutes.append([])

                    new_pick_hist = pick_hist + (pick,)
                    for clue, new_candidates in clue_part.items():
                        new_clue_hist = clue_hist + (clue,)
                        paths.append((new_pick_hist, new_clue_hist,
                            top_subroutes[-1], [], new_candidates, new_picks))
                        # continue # maybe unecessary XXX to delete
                        # WTF should new_picks be?

            else:
                # Pick the subroute set with the lowest average depth
                #routes.extend(min(top_subroutes, key=result_score))
                routes.extend(min(top_subroutes, key=cmp_to_key(depth_cmp)))

        return tuple(tuple(self.idx_word[pick] for pick in route) for route in all_routes)



    @staticmethod
    def _get_distribution(candidates, pick, clue_matrix):
        ''' get list of sizes of resulting wordlist, after splitting
        word_list by guess guess_word
        '''
        counts = Counter(clue_matrix[pick, secret] for secret in candidates)
        return [count * 2 for count in counts.values()]

    @staticmethod
    def cull_picks(pick_rank):
        surviving_picks = []
        for pick, (rank, clue_part) in pick_rank.items():
            # the or part might not be necessary, but probably doesn't hurt
            if len(clue_part) > 1 or Color.all_green() in clue_part:
                surviving_picks.append(pick)
                # Might make an exception for all green picks, but those should
                # be separete as they would all be candidate (solutions)

        return surviving_picks

    @staticmethod
    def pick_valid(item):
        '''Method that returns true if a pick should be culled according to its
        clue distribution'''
        rank, pick, clue_part = item
        return len(clue_part) > 1 or Color.all_green() in clue_part


    @staticmethod
    def cull_picks_gen(pick_rank_gen):

        for pick, rank, clue_part in pick_rank_gen:
            if len(clue_part) > 1 or Color.all_green() in clue_part:
                yield (pick, rank, clue_part)



    def get_distribution(self, candidates, pick): #, word_ns, guess_word_n, matrix):

        return self._get_distribution(candidates, pick, self.clue_matrix)

    def split_candidates_by_clue(self, candidates, pick):
        ''' Return dict of {clue: list[candidate]} that are valid for this
        initial list and guess
        '''
        candidates_by_clue = {}

        for secret in candidates:
            clue = self.clue_matrix[pick, secret]
            candidates_by_clue.setdefault(clue, []).append(secret)

        # WTF, why was this necessary?
        # for clue, words in [*candidates_by_clue.items()]:
        #     if not words:
        #         del candidates_by_clue[clue]

        return candidates_by_clue

    def split_candidates_by_clue_alt(self, candiates, pick):
        ''' Return dict of {clue: list[candidate]} that are valid for this
        initial list and guess
        '''
        candidates_by_clue = defaultdict(default_factory=list)

        for pick in candidates:
            candidates_by_clue[self.clue_matrix[pick, secret]].append(secret)

        return candidates_by_clue

    # ok.. we need 'both' but we can call it twice.
    # gen_rank_group_pick


    def rank_expand_picks_par(self, candidates, picks, pick_hist):
        '''Generate picks along with its heuristic score and a dict of
        candidates partitioned by clue. Elements are a 3-tuple of
        (pick, score, {clue:[candidates]})
        '''
        def split_and_score(pick):
            clue_part = self.split_candidates_by_clue(candidates, pick)
            score = score_distribution(clue_part)
            return score, pick, clue_part

        delayed_calls = [delayed(split_and_score)(pick) for pick in picks]
        
        with ProcessPoolExecutor(max_workers=4) as executor:
            # Submit tasks to the executor
            future_to_item = {executor.submit(split_and_score, pick): pick for pick in picks}
            
            # Yield results as they complete
            for future in as_completed(future_to_item):
                yield future.result()

        # # currently pick_hist is not used, but maybe it should be
        # for pick in picks:
        #     clue_part = self.split_candidates_by_clue(candidates, pick)
        #     score = score_distribution(clue_part)
        #     # score = compute_heuristic(clue_part)
        #     yield (score, pick, clue_part)

    def rank_expand_picks(self, candidates, picks, pick_hist):
        '''Generate picks along with its heuristic score and a dict of
        candidates partitioned by clue. Elements are a 3-tuple of
        (pick, score, {clue:[candidates]})
        '''

        # currently pick_hist is not used, but maybe it should be
        for pick in picks:
            clue_part = self.split_candidates_by_clue(candidates, pick)
            score = score_distribution(clue_part)
            # score = compute_heuristic(clue_part)
            yield (score, pick, clue_part)


    def rank_and_group_picks(self, candidates, picks, pick_hist, dt=None, depth=2):
        ''' Return top "tops" distributions with highest scores, but gives the
        recomendations from a pre-defined decision tree for the first view levels
        '''
        # currently pick_hist is not used, but maybe it should be

        # (pick, rank, distribution, future_candidates?)
        candidate_rank = {}
        pick_rank = {}

        print(f"{pick_hist = }, {len(candidates) = }, {len(picks) = }")
        # Rank picks as candidates first as these can generate an ideal solution
        for pick in candidates:
            distribution = self.split_candidates_by_clue(candidates, pick)
            score = score_distribution(distribution)
            candidate_rank[pick] = (score, distribution)
            # allpicks.append((score, pick))

        # Now rank strategic picks
        for pick in picks:
            distribution = self.split_candidates_by_clue(candidates, pick)
            score = score_distribution(distribution)
            pick_rank[pick] = (score, distribution)
            # allpicks.append((score, pick))

        # Return the respective rankings
        return candidate_rank, pick_rank
        
    def get_top_picks(self, pick_rank, candidate_rank, pick_hist, dt=None, depth=2):
        '''Return top picks as ranked by a heruistic along with a dict of
        partitioned solution candidates, keyed by clue.
        XXX
        recomendations from a pre-defined decision tree for the first view levels
        '''

        if dt and len(pick_hist) <= depth:
            secret, score, pick, clue_part = next(iter(candidates_rank), None)
            branch = dt
            best_guess = next(iter(dt))

            for pick in pick_hist:
                clue = self.clue_matrix(pick, secret)
                branch = branch[pick][clue]
                best_guess = next(iter(branch))
            return [best_guess] 

        # # Number of bests to check.
        # # Minimum parameters for best result are: 3,5,10,20
        # if len(candidate_rank) > 300:
        #     options = 3
        # elif len(candidate_rank) >= 10:
        #     options = 10
        # else:
        #     options = 20

        # Minimum parameters for best result are: 3,5,10,20
        # so when there are more candidates, we actually branch less???
        if len(candidate_rank) > 300:
            options = 3
        elif len(candidate_rank) >= 10:
            options = 10
        else:
            options = 20
        
        # print(f"{options = }, {len(candidate_rank) = }, {len(picks) = }")

        allpicks = []
        # Evaluate canddiates as pick, while checkng for an ideal solution

        for score, pick, clue_part in candidate_rank:
            # If the solution is ideal, return it immediately
            if (len(candidate_rank) <= len(clue_part) and all(len(n) == 1 for
                n in clue_part.values())):
                return [(pick, clue_part)]
            allpicks.append((score, pick, clue_part))

        seen = {pick for _, pick, _ in allpicks}
        # If no ideal solution was found, add in strategic picks to consider 
        for score, pick, clue_part in pick_rank:
            if pick not in seen:
                allpicks.append((score, pick, clue_part))
        
        print(f"{len(allpicks) =}")

        # Collect the largest n=options values
        best_n = heapq.nlargest(options, allpicks)
        
        return [(pick, clue_part) for score, pick, clue_part in best_n]

    def get_top_picks_old(self, candidates, pick_hist, picks, dt=None, depth=2, clue_matrix=None):
        ''' Return top "tops" distributions with highest scores, but gives the
        recomendations from a pre-defined decision tree for the first view levels
        '''

        if dt and len(pick_hist) <= depth:
            secret = next(iter(candidates), None)
            branch = dt
            best_guess = next(iter(dt))
            # clue = get_clue_for_secret(guess, secret)
            for pick in pick_hist:
                # clue = get_clue_for_secret(pick, secret)
                clue = clue_matrix(pick, secret)
                branch = branch[pick][clue]
                best_guess = next(iter(branch))
            return [best_guess]

        def unique(seq, seen=set()):
            for item in seq:
                if item in seen:
                    continue
                seen.add(item)
                yield item

        def gen_picks(source):

            for pick in source:
                # if all(c == '_' for c in pick):
                #     continue
                distribution = self.get_distribution(candidates, pick) # word_ns, guess_n, matrix)
                score = score_distribution(distribution)
                yield (score, pick, distribution)

        # Number of bests to check.
        # Minimum parameters for best result are: 3,5,10,20
        if len(candidates) > 300:
            options = 3
        elif len(candidates) >= 10:
            options = 10
        else:
            options = 20
        
        print(f"{options = }, {len(candidates) = }, {len(picks) = }")

        allpicks = []
        bad_picks = []

        # check for an ideal candidate solution first
        for score, pick, distribution in gen_picks(candidates):
            if len(candidates) <= len(distribution) and all(n == 1 for n in distribution):
                return [guess] # I dont' like this b/c if n is 2, then it might not be optimal
            allpicks.append((score, pick))

        # If no ideal solution was found, add in strategic picks to consider 
        for score, pick, distribution in gen_picks(picks):
            if len(distribution) == 1: # this is a bad pick and needs to be culled
                bad_picks.append(pick)
            allpicks.append((score, pick))

        # Collect the largest n values
        best_n = [guess for (score, guess) in heapq.nlargest(options, allpicks)]
        
        return best_n



def split_candidates_by_clue_alt(candiates, pick):
    ''' Return dict of {clue: candidate} that are valid for this
    initial list and guess
    '''
    candidates_by_clue = defaultdict(default_factory=list)

    for pick in candidates:
        candidates_by_clue[get_clue_for_secret(secret)].append(secret)

    return candidates_by_clue




def score_distribution(distribution):
    ''' Return a score of distribution
    Update this one to test other strategies
    '''
    return len(distribution)

def compute_heuristic(clue_part):

        # Compute entropy
        # counts = np.bincount(clues, minlength=243)  # 243 possible clues
        # counts = counts[counts > 0]  # Non-zero counts
        counts = np.fromiter((len(v) for k, v in clue_part.items()), dtype=int)

        if len(counts) <= 1:  # Single clue pattern
            return 0.0
        probs = counts / np.sum(counts)
        entropy = -np.sum(probs * np.log2(probs))
        return entropy



def mod_beam_search_rec(state, previous_guesses, ct=Counter()):
    ''' main recursive function
    '''

    final_result = None
    print (f"Starting new node for the list of {len(state.filter.candidates)}")
    best_guesses = get_top_picks(state) # , previous_guesses, guess_words_ns)
    print (f"Best  are: {best_guesses}")
    for i, best_guess in enumerate(best_guesses):
    
        out = []
    
        on = state.expand_guess(best_guess)
        answers = on.expand()
    
        #           new_list
        for answer, new_state in answers.items():
            if len(new_state.filter.candidates) == 1 or answer == (Color.GREEN,) * 5:
                out.append(list(previous_guesses))
        
                if answer != (Color.GREEN,) * 5:
                    out[-1].append(best_guess)
                out[-1].append(new_state.filter.candidates[0])
                ct.update([len(out[-1])])

            else:
                new_state.filter.update_picks()
                out += mod_beam_search_rec(new_state,
                                tuple(list(previous_guesses) + [best_guess]))

        if final_result is None or result_length(out) < result_length(final_result):
            final_result = out

    return final_result


def result_score(results):
    return (result_max_depth(results), (result_length(results)))

# comparator
def depth_cmp(r1, r2):
    c1 = Counter(len(path) for path in r1)
    c2 = Counter(len(path) for path in r1)

    for key in sorted(c1.keys() | c2.keys(), reverse=True):
        if s1.get(key, 0) > s2.get(key, 0):
            return 1
        elif s1.get(key, 0) < s2.get(key, 0):
            return -1
    return 0



def result_length(results):
    ''' Len of this result (sum of the 2nd levels lengths)
    '''
    return sum(len(r) for r in results)
    # This is essentially the average depth # or average depth * total branches
    # can we speed it up?

def result_max_depth(results):
    return max(len(r) for r in results)


def main():

    state_store = {}
    option_store = {}

    def timeit_capture(stmt):
        import timeit
        return_vals = []
        time_result = timeit.timeit(lambda: return_vals.append(stmt()), number=1)
        return return_vals[0], time_result


    dt = read_decision_tree('tmp/decision_tree.txt')

    # lexicon = load_word_list('wordle_words.txt') # 14855 words
    candidates = load_word_list('wordle_solutions.txt') # 2315 words


    lexicon = load_word_list('default_words.txt')
    # lexicon = load_word_list('wordle_solutions.txt') # 2315 words

    # lexicon = load_word_list('wordle_sample.txt') # 232 words
    # candidates = load_word_list('wordle_sample.txt') # 232 words

    tree = WordleTree(candidates, lexicon, None)

    # gf = GuessFilter(length=5, lexicon=lexicon, candidates=candidates)
    # gf.update_candidates() # unecessary.. instantiation should do it
    # root = StateNode(state_store, option_store, gf)
    # state_store[root.id] = root
    # result = mod_beam_search_rec(root, [])
    results = []
    # print("Starting search...")
    # result, time = timeit_capture(stmt=lambda: mod_beam_search(root, dt))
    # print(f"Search complete. Time: {time}")
    # results.append(result)

    # print("Starting search recursive...")
    # result, time = timeit_capture(stmt=lambda: mod_beam_search_rec(root, []))
    # print(f"Search complete. Time: {time}")
    # results.append(result)

    print("Starting search new...")
    #result, time = timeit_capture(stmt=lambda: mod_beam_search_opt(candidates, lexicon, dt))
    result, time = timeit_capture(stmt=lambda: tree.mod_beam_search(candidates, lexicon, None))
    print(f"Search complete. Time: {time}")
    print(json.dumps(result))
    results.append(result)
    dt_out = route_list_to_dt(result)
    # print(json.dumps(dt_out)) # fix this.. problem of tuples, not Enum
    out_routes = dt_to_routes(dt_out)
    print ("Average depth:", sum(len(r) for r in out_routes) / len(out_routes))
    with open('output_dt.txt', 'wt') as f:
        f.writelines(routes_to_text_gen(out_routes))
    pass


if __name__ == '__main__':
    cProfile.run('main()', 'output.prof')

    p = pstats.Stats('output.prof')
    p.strip_dirs().sort_stats('cumulative').print_stats(35)  # Show top 10 functions

    # main()
