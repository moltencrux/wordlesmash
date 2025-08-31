import os
import sys
import numpy as np

from itertools import count, chain
from collections import namedtuple, Counter, defaultdict
from functools import partial, cmp_to_key
import tempfile
import heapq
import logging
from .lazy_handler import LazyRotatingFileHandler

from string import ascii_uppercase

from .wordle_game import Color
from .filter_code import FilterCode
from .tree_utils import (read_decision_tree, read_decision_routes, dt_to_routes,
                        routes_to_dt, routes_to_text, routes_to_text_gen,
                        verify_routes)

from .wordle_game import get_clue_for_secret
from .utils import LazyList, load_word_list
import cProfile
import pstats
import hashlib
from traceback import format_exception_only
from textwrap import dedent
from joblib import Parallel, delayed, parallel_backend

from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Event, get_context, Manager, Process
from sortedcontainers import SortedDict
from math import inf
import threading
from pathlib import Path


class CompoundEvent:
    def __init__(self, *events):
        self.events = events

    def is_set(self):
        return any(event.is_set() for event in self.events)

    def set(self):
        for event in self.events:
            event.set()

    def clear(self):
        for event in self.events:
            event.clear()

def setup_logger(prefix=None):
    pid = os.getpid()
    log_file = f"log_{pid}.log"
    logger = logging.getLogger("Wordle Tree Logger")
    logger.setLevel(logging.DEBUG)
    handler = LazyRotatingFileHandler(tmpdir_prefix=prefix, basename=log_file, maxBytes=10*(1024 ** 2), backupCount=3)
    logger.addHandler(handler)
    stderr_handler = logging.StreamHandler(sys.stderr)
    logger.addHandler(stderr_handler)
    return logger

logger = setup_logger('wordlesmash.')

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
    def __init__(self, all_candidates, all_picks, dt=None, branch_rules=None, cache_path=None):

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

        # Minimum parameters for best result are: 3,5,10,20
        if branch_rules is None:
            self.branch_rules = SortedDict({300:5, 10:10, 0:20}) # these were the default paramaters
        else:
            self.branch_rules = SortedDict(branch_rules) # these were the default paramaters

        filename = Path(cache_path) / self.gen_matrix_filename()

        try:
            self.clue_matrix = np.load(filename)
        except FileNotFoundError as e:
            logger.warning(f"No saved matrix data found, generating: {filename}")
        except (OSError, ValueError, EOFError) as e:
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


    def set_branch_rules(self, branch_rules):
        '''
        Set the rules for the way branching occurs in the beam search. 
        branch_rules is a dictionary, keyed by the lower limit of candidates
        with the value of the number of picks (branch factor) that will be
        searched.  The upper limit will be next largest key (non inclusive).
        '''
        self.branch_rules = SortedDict(branch_rules)

    def gen_matrix_filename(self, template='word_matrix_{}.npy'):
        ''' Hash word lists to create a suffix for a np matrix name
        '''
        candidates = sorted(set(self._all_candidates))
        picks = sorted(set(self._all_picks))
        data = (' '.join(candidates) + '\n' + ' '.join(picks)).encode('utf-8')
        suffix = hashlib.sha256(data).hexdigest()
        return template.format(suffix)

    def _fix_candidates_and_picks(self, candidates, picks):
        '''
        Set up solution candidates and strategic picks, converting to numeric
        indices if a set of words was specified. Otherwise, use all posible
        candidates and picks.
        '''
        if candidates is not None:
            candidates = frozenset(map(self.word_idx.get, candidates))
        else:
            candidates = frozenset(map(self.word_idx.get, self._all_candidates))

        if picks is not None:
            picks = frozenset(map(self.word_idx.get, (*candidates, *picks)))
        else:
            # XXX it might should be this instead
            picks = frozenset(map(self.word_idx.get, self._all_candidates))
            # picks = frozenset(map(self.word_idx.get, self._all_picks))
        
        return candidates, picks


    def mod_dfs_beam_search(self, candidates=None, picks=None, pick_hist=(),
                            clue_hist=(), dt=None, dt_depth=1, parallel=False,
                            abort=None):
        ''' Top level wrapper for searching the Wordle pick/solution space
        '''
        candidates, picks = self._fix_candidates_and_picks(candidates, picks)

        # Convert to numeric representation
        pick_hist = tuple(self.word_idx[word] for word in pick_hist)
        clue_hist = tuple(Color.ordinal(clue_str) for clue_str in clue_hist)

        # Create a chain of filters to filter candidates that match only the
        # previous picks and clues.
        pipe = candidates
        for pick, clue in zip(pick_hist, clue_hist):
            pipe = filter((lambda secret, pick=pick, clue=clue: self.clue_matrix[pick, secret] == clue), pipe)

        candidates = frozenset(pipe)

        # Filter invalid picks and deduplicate redundant picks due to
        # pick_hist/clue_hist
        picks = [pick for _, pick, _ in
                 filter(self.pick_valid,
                        self.rank_expand_picks(candidates, picks)
                        )
                 ]


        dt = self.dt if dt is None else dt

        all_routes = self.mod_dfs_beam_rec(candidates, picks, pick_hist,
                                            clue_hist, dt, dt_depth,
                                            parallel=parallel, abort=abort)

        if abort is not None:
            abort.set() # signal monitor thread to terminate

        if all_routes is None:
            return ()
        else:
            return tuple(sorted(tuple(self.idx_word[pick] for pick in route)
                                for route in all_routes))


    def mod_dfs_beam_rec(self, candidates, picks, pick_hist=(), clue_hist=(),
                         dt=None, dt_depth=1, best_profile=[], parallel=False,
                         abort=None):

        ''' Recursive version of a modified beam search
        '''
        # Check to be sure if we're at the goal already
        if next(iter(clue_hist[-1:]), None) == Color.all_green():
            return []

        # XXX I'm thiking we should check best_profile here if it's not checked
        # b4 call and... the last nonzero should be +

        if best_profile: 
            max_depth = len(best_profile)
            max_depth_count = best_profile[-1]
        else:
            max_depth = float('inf')
            max_depth_count = float('inf')

        logger.debug(f"Starting node for candidates: {len(candidates)}")

        # Create an iterator of candidates to consider for top picks
        seen = {} # use this for folding redundant picks
        candidate_rank = [*self.rank_expand_picks(candidates, candidates, seen, pick_hist)]
        # XXX The seen thing.. frozenset for folding.  needs to happen accrsoss calls
        # BUT, we wanna do canddidates first and picks in a lazy manner
        # is REP? seen is in REP, but frozenset in Split.
        # move frozenset gen to REP?

        # Create an iterator of strategic picks to consider for top picks
        unranked_picks = (pick for pick in picks if pick not in candidates)

        # careful about scope.. candidates could be different maybe
        pipe = self.rank_expand_picks(candidates, unranked_picks, seen)
        for pred in [self.pick_valid]:
            pipe = filter(pred, pipe)

        # Q: why did we collapse this previously?
        # A: b/c i think we get it into new picks before it is passed to
        # get_top_picks
        pick_rank = LazyList(pipe)

        # should filter out candidates to expand
        # so then can we just look at the values of _seen_ for newpicks? ? or maybe 1st
        # value in the list? if we use _seen_ there might be a chance it gets modified
        # before collapse.. or a r/cond or something

        new_picks = LazyList(pick for _, pick, _ in chain(candidate_rank, pick_rank))
        final_route_sets = []
        final_branch = best_profile and len(pick_hist) + 1 == len(best_profile)
        logger.debug(f'{len(pick_hist) = } {len(best_profile) = }')

        for pick, clue_part in self.get_top_picks(pick_rank, candidate_rank,
                                                  pick_hist, clue_hist, dt,
                                                  dt_depth, final_branch):
            if abort and abort.is_set():
                return None # Received signal from above to abort

            routes = []
            working_profile = best_profile.copy()
            new_pick_hist = pick_hist + (pick,)

            batch_args = []

            if not within_l2_bounds(candidates, best_profile, new_pick_hist, clue_part):
                # should skip
                logger.debug(f"dropping redundant pick: {pick}")
                continue #? or break? # continue should be good.. but maybe even break?
                # XXX but break might not save us much really, the test is fast
                # And I'm not sure that all subsequent picks will fail

            for clue, rem_candidates in clue_part.items():

                if len(rem_candidates) == 1:
                    # We've reached a solution
                    solution = new_pick_hist
                    if clue != Color.all_green():
                        solution += (*rem_candidates,) # avoids extra on expansion

                    routes.append(solution)
                    if not tally_and_test([solution], working_profile):
                        routes = None
                        break
                else:
                    # No immediate solution, need to deepen search
                    ... # This conditional breakpoint should never happen
                    new_clue_hist = clue_hist + (clue,)

                    logger.debug(f"Eval pick: level = {len(new_pick_hist)}, " +
                                 f"    {len(rem_candidates) = }\n" + 
                                 f"    {[self.idx_word[p] for p in new_pick_hist]}\n" +
                                 f"    {[Color.seq_to_num_str(Color.from_ordinal(c)) for c in new_clue_hist]}")

                    # prepare a batch job: 
                    batch_args.append((rem_candidates, frozenset(new_picks),
                                       new_pick_hist, new_clue_hist, dt,
                                       dt_depth)) # , abort))

            else:

                for result in self._beam_batch_helper(batch_args, working_profile,
                                                    parallel, abort):
                
                    if abort and abort.is_set():
                        return None # Received signal from above to abort
                    elif result is not None:
                        routes.extend(result)
                    else:
                        routes = None  # this is rq/ because we test routes
                        break

                if routes:
                    final_route_sets.append(tuple(routes))
                    # Keep the best lot of routes, although we might do this outside
                    # the loop instead for parallellism later.
                    route_depth = route_max_depth(routes)
                    # max_path = min(max_path, route_depth)
                    final_route_sets = [(min(final_route_sets, key=cmp_to_key(depth_cmp)))]
                    best_profile = depth_profile(final_route_sets[0]) # get best profile here
                    max_depth = len(best_profile)
                    max_depth_count = best_profile[-1]

        return next(iter(final_route_sets), None)


    def _beam_batch_helper(self, batch_args, working_profile, parallel, abort):

        if parallel:

            with Manager() as manager:
                stop_workers = manager.Event()
                all_abort = CompoundEvent(stop_workers)

                monitor_started = False
                processing_finished = False

                with ProcessPoolExecutor(max_workers=5) as executor:
                    futures = []

                    for args in batch_args:
                        futures.append(executor.submit(self.mod_dfs_beam_rec,
                                                       *args, working_profile,
                                                       abort=all_abort))
                    
                    for future in as_completed(futures):
                        result = future.result()
                        if (not (abort and abort.is_set())) and result is not None and tally_and_test(result, working_profile):
                            yield result
                        else:
                            stop_workers.set()
                            yield None
                            # break
                # executor.shutdown(wait=True)

        else:
            for args in batch_args:

                result = self.mod_dfs_beam_rec(*args, working_profile, parallel, abort)

                if (not (abort and abort.is_set())) and result is not None and tally_and_test(result, working_profile):
                    yield result
                else:
                    yield None
                    break


    def get_valid_candidates(self, pick_hist=(), clue_hist=(), candidates=None):

        if candidates is None:
            candidates = map(self.word_idx.get, self._all_candidates)

        candidates = list(candidates)
        if None in candidates:
            raise ValueError

        pipe = candidates
        for pick, clue in zip(pick_hist, clue_hist):
            pipe = filter((lambda secret, pick=pick, clue=clue: self.clue_matrix[pick, secret] == clue), pipe)

        return frozenset(pipe)

    def get_valid_candidate_words(self, pick_word_hist=(), clue_color_hist=(),
                                  candidates=None):
        pick_hist = tuple(map(self.word_idx.get, pick_word_hist))
        clue_hist = tuple(map(Color.ordinal, clue_color_hist))
        if candidates is not None:
            candidates = map(self.word_idx.get, candidates)

        rem_candidates = self.get_valid_candidates(pick_hist, clue_hist, candidates)

        return frozenset(map(self.idx_word.get, rem_candidates))




    @staticmethod
    def _get_distribution(candidates, pick, clue_matrix):
        ''' get list of sizes of resulting wordlist, after splitting
        word_list by guess guess_word
        '''
        counts = Counter(clue_matrix[pick, secret] for secret in candidates)
        return [count * 2 for count in counts.values()]


    @staticmethod
    def pick_valid(item):
        '''Method that returns true if a pick should be culled according to its
        clue distribution'''
        rank, pick, clue_part = item
        return len(clue_part) > 1 or Color.all_green() in clue_part


    def get_distribution(self, candidates, pick): #, word_ns, guess_word_n, matrix):

        return self._get_distribution(candidates, pick, self.clue_matrix)

    def split_candidates_by_clue(self, candidates, pick):
        ''' Return dict of {clue: set[candidate]} that are valid for this
        initial list and guess
        '''
        candidates_by_clue = {}

        for secret in candidates:
            clue = self.clue_matrix[pick, secret]
            candidates_by_clue.setdefault(clue, []).append(secret)

        # Freeze all values
        for clue, can in candidates_by_clue.items():
            candidates_by_clue[clue] = frozenset(can)

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
            clue_part, _ = self.split_candidates_by_clue(candidates, pick)
            score = score_distribution(clue_part)
            return score, pick, clue_part

        delayed_calls = [delayed(split_and_score)(pick) for pick in picks]
        
        with ProcessPoolExecutor(max_workers=4) as executor:
            # Submit tasks to the executor
            future_to_item = {executor.submit(split_and_score, pick): pick for pick in picks}
            
            # Yield results as they complete/best
            for future in as_completed(future_to_item):
                yield future.result()

        # # currently pick_hist is not used, but maybe it should be
        # for pick in picks:
        #     clue_part = self.split_candidates_by_clue(candidates, pick)
        #     score = score_distribution(clue_part)
        #     # score = compute_heuristic(clue_part)
        #     yield (score, pick, clue_part)

    def rank_expand_picks(self, candidates, picks, seen=None, pick_hist=None):
        '''
        Generate picks along with its heuristic score and a dict of
        candidates partitioned by clue. Elements are a 3-tuple of
        (pick, score, {clue:[candidates]})
        '''
        seen = seen if seen is not None else {}
        # currently pick_hist is not used, but maybe it should be
        # for pick in {*picks} - seen:
        for pick in filter(lambda p: p not in seen, picks):
            clue_part = self.split_candidates_by_clue(candidates, pick)
            part_sig = frozenset(clue_part.items())
            # XXX I am consdering leaving out the specific clue for the part_sig
            # part_sig = frozenset(clue_part.values())
            # because I _think_ that the clue that led to that subset of picks is
            # not relevant, as distinct guesses with different clues could lead to
            # the same subset, and probably the same information is known about them
            # But I'm not sure if that could lead to problems with route generation
            #

            pool = seen.setdefault(part_sig, [])
            pool.append(pick)

            if len(pool) == 1: # this pick is not folded into another yet
                # score = score_distribution(clue_part)
                # score = compute_heuristic(clue_part)
                score = sorted((len(v) for v in clue_part.values()), reverse=True)
                yield (score, pick, clue_part)


    def rank_and_group_picks(self, candidates, picks, pick_hist, dt=None, depth=2):
        ''' Return top "tops" distributions with highest scores, but gives the
        recomendations from a pre-defined decision tree for the first view levels
        '''
        # currently pick_hist is not used, but maybe it should be

        # (pick, rank, distribution, future_candidates?)
        candidate_rank = {}
        pick_rank = {}

        logger.debug(f"{pick_hist = }, {len(candidates) = }, {len(picks) = }")
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
        
    def get_top_picks(self, pick_rank, candidate_rank, pick_hist, clue_hist,
                      dt=None, depth=2, final_branch=False):
        '''
        Return top picks as ranked by a heruistic along with a dict of
        partitioned solution candidates, keyed by clue. The dt parameter can
        optionally specifiy a decision tree, which will override top picks up
        to the specified depth.
        '''

        # depth means we follow the dt only. Otherwise, we recommend the dt
        # suggestion first

        dt_picks = {}
        if dt and candidate_rank:
            _, secret, _ = next(iter(candidate_rank), None)
            branch = dt
            best_guess = self.word_idx[next(iter(branch))]

            for pick in pick_hist:
                clue = Color.from_ordinal(self.clue_matrix[pick, secret])
                # i think this is right
                key = self.idx_word[pick]
                if key not in branch or clue not in branch[key]:
                    break
                branch = branch[self.idx_word[pick]][clue]
                best_guess = self.word_idx[next(iter(branch))]

            else:
                candidates = [candidate for _, candidate, _ in candidate_rank]
                clue_part = self.split_candidates_by_clue(candidates, best_guess)
                # score = score_distribution(clue_part)
                logger.debug(f"perfect solution found at level {len(pick_hist) + 1}")
                if len(pick_hist) < depth:
                    return [(best_guess, clue_part)] 
                else:
                    dt_picks[best_guess] = clue_part

        # # Number of bests to check.
        rule_index = self.branch_rules.bisect_right(len(candidate_rank)) - 1
        options = self.branch_rules.values()[rule_index]


        logger.debug(f"total (non-candidate) picks: {len(pick_rank)} {options = }")
        if options > (len(pick_rank) + len(candidate_rank)):
            logger.debug(f"search exhuasting picks & candidates at level {len(pick_hist) + 1}")

        allpicks = []
        # Evaluate canddiates as pick, while checkng for an ideal solution

        for score, pick, clue_part in candidate_rank:
            # If the solution is ideal, return it immediately
            if (len(candidate_rank) == len(clue_part) and all(len(n) == 1 for
                n in clue_part.values())):
                return [(pick, clue_part)]
            allpicks.append((score, pick, clue_part))

        # seen = {pick for _, pick, _ in allpicks}

        # If no ideal solution was found, add in strategic picks to consider 
        for score, pick, clue_part in pick_rank:
            # Check for near-ideal solution
            if (len(candidate_rank) == len(clue_part) and all(len(n) == 1 for
                n in clue_part.values())):
                logger.debug(f"near perfect solution found at level {len(pick_hist) + 1}")
                return [(pick, clue_part)]

            allpicks.append((score, pick, clue_part))

        if final_branch:  # This is the final level that will be explored, so
            return []     # any solution must be perfect or near-perfect
        
        logger.debug(f"{options = }, {len(candidate_rank) = }, {len(pick_rank) = }")

        logger.debug(f"{len(allpicks) = }")

        # Filter any picks that are already DT recommendations
        allpicks = [p for p in allpicks if p[1] not in dt_picks]

        # dt_tip = [(pick, clue_part) for (pick, clue_part) in dt_pick.items()]

        # Collect the largest n=options values
        if options == float('inf'):
            best_n = allpicks
            best_n.sort()
            # key=cmp_to_key(lambda x, y: dist_cmp(x[2], y[2])))
        else:
            best_n = sorted(heapq.nsmallest(options, allpicks))
            # key=cmp_to_key(lambda x, y: dist_cmp(x[2], y[2])))

        return [*dt_picks.items()] + [(pick, clue_part) for score, pick, clue_part in best_n]


    def gen_routes(self, pick, abort=None):

        dt = {pick:{}}
        routes = self.mod_dfs_beam_search(dt=dt, dt_depth=1, parallel=True,
                                          abort=abort)
        
        return routes



def score_distribution(distribution):
    ''' Return a score of distribution
    Update this one to test other strategies
    '''
    return len(distribution)

def compute_heuristic(clue_part):

        # Compute entropy
        counts = np.fromiter((len(v) for k, v in clue_part.items()), dtype=int)

        if len(counts) <= 1:  # Single clue pattern
            return 0.0
        probs = counts / np.sum(counts)
        entropy = -np.sum(probs * np.log2(probs))
        return entropy

def dist_cmp(clue_part1, clue_part2):
    """
    A heuristic comparison of two pick distributions. Less than is considered
    better.
    """
    cp1 = sorted((len(v) for v in clue_part1.values()), reverse=True)
    cp2 = sorted((len(v) for v in clue_part2.values()), reverse=True)
    return cp1 < cp2



def result_score(results):
    return (route_max_depth(results), (result_length(results)))

# comparator
def depth_cmp(r1, r2):
    # A None in the routes will be regarded as an aborted route

    if r2 is None or None in r2:
        if r1 is None or None in r1:
            return 0
        else:
            return -1
    elif r1 is None or None in r1:
        return 1

    r1_cts = Counter(len(path) for path in r1)
    r2_cts = Counter(len(path) for path in r2)

    return depth_counts_cmp(r1_cts, r2_cts)


def depth_counts_cmp(r1_cts, r2_cts):

    for key in sorted(r1_cts.keys() | r2_cts.keys(), reverse=True):
        if r1_cts.get(key, 0) > r2_cts.get(key, 0):
            return 1
        elif r1_cts.get(key, 0) < r2_cts.get(key, 0):
            return -1
    return 0

def depth_profile(routes):
    """
    Calculate the distribution of path lengths in a set of decision tree routes.

    Args:
        routes (list): A list of decision tree routes, where each route is a
        list of nodes.
    
    Returns:
        list: A list where the i-th element represents the number of paths of
        length i.
    """
    counts = Counter(len(path) for path in routes)
    # can / should we make this a tuple?
    # return [counts.get(i, 0) for i in range(max(counts.keys()) + 1)]
    return [counts.get(i, 0) for i in range(1, max(counts.keys()) + 1)]

def depth_profile_dt(dt, pick_prefix=(), clue_prefix=()):

    routes = dt_to_routes(dt)
    return depth_profile(routes)

    # I was thinking that the prefix didn't need clues, however it's possible
    # that it is ambiguous since we don't know what the ultimate goal is and
    # can't imply the clues b/c the solution is unknown.
    ...

    # _, secret, _ = next(iter(candidate_rank), None)

    branch = dt
    # best_guess = self.word_idx[next(iter(branch))]
    start_depth = len(pick_prefix)

    for pick, clue in zip(pick_prefix, clue_prefix):
        # clue = Color.from_ordinal(self.clue_matrix[pick, secret])
        # i think this is right
        branch = branch[self.idx_word[pick]][clue]
        # best_guess = self.word_idx[next(iter(branch))]

    counts = Counter()

    queue = []
    while queue:
        ...

    candidates = [candidate for _, candidate, _ in candidate_rank]
    clue_part, _ = self.split_candidates_by_clue(candidates, best_guess)
    # score = score_distribution(clue_part)
    logger.debug(f"perfect solution found at level {len(pick_hist) + 1}")
    return [(best_guess, clue_part)] 

def routes_can_expand(rem_profile):
    '''
    Returns True if the route set for the specified profile can still be
    expanded. False indicates that the partial route set is already worse
    worse than the best known route set, and no further work should be done
    to find out how much worse.
    '''
    return next((val > 0 for val in reversed(rem_profile) if val != 0), True)


def tally_and_test(new_routes, working_profile):

    if working_profile == []:
        return True

    for route in new_routes:
        if len(route) > len(working_profile) - 1:
            working_profile.extend([0] * (len(route) - len(working_profile)))
            
        working_profile[len(route) - 1] -= 1

    return routes_can_expand(working_profile)

def within_l2_bounds(candidates, profile, pick_hist, clue_part):
    """
    Check if the lower bounds on the number routes two levels deeper for this pick
    is greater than the number for the best route set o far. If the lower bounds is
    greater, then there is no need to explore it, as it could not displace the
    current reigning pick/route set even if every sub-pick has a perfect solution.
    """
    # A similar funciton could also be made to test lower bounds of average depth


    return (len(pick_hist) != len(profile)- 2 or
            len(candidates) - len(clue_part) < profile[-1])

def within_l2_bounds_avg(candidates, pick_hist, max_depth, max_depth_count, clue_part):


    return (depth != max_depth - 2) # or
    # Q: at a particular layer in the dt search, will there be any routes found that
    # are shorter than the current depth?
    # A: almost surely no. new_pick_hist is appended, which is 1 longer that pick_hist
    # also a solution is appended, which could be 2 longer 
    # but best_profile passed in might be different.

    #        (len(candidates) - len(clue_count) < max_depth_count))


def result_length(results):
    ''' Len of this result (sum of the 2nd levels lengths)
    '''
    return sum(len(r) for r in results)
    # This is essentially the average depth # or average depth * total branches
    # can we speed it up?

def route_max_depth(results):
    if results is None:
        return float('inf')
    return max(len(r) for r in results)

def test_setup(picks_file='wordle_picks.txt',
               solutions_file='wordle_candidates.txt', dt=None):

    if isinstance(dt, str):
        dt = read_decision_tree(dt)

    lexicon = load_word_list(picks_file) # 14855 words
    candidates = load_word_list(solutions_file) # 2315 words
    tree = WordleTree(candidates, lexicon, dt)
    return tree

def run_test(tree, pick_hist=(), clue_hist=(), dt=None, dt_depth=1, parallel=True,
             filename='output_dt.txt'):

    def timeit_capture(stmt):
        import timeit
        return_vals = []
        time_result = timeit.timeit(lambda: return_vals.append(stmt()), number=1)
        return return_vals[0], time_result
    logger.debug("Starting new search...")

    stmt = lambda: tree.mod_dfs_beam_search(None, None, pick_hist,
                                            clue_hist, dt=dt, dt_depth=dt_depth,
                                            parallel=parallel)

    routes, time = timeit_capture(stmt=stmt)
    logger.debug(f"Search complete. Time elapsed: {time:.4}")

    if not verify_routes(routes, tree._all_candidates):
        logger.debug("Routes not verified, incomplete.")
    else:
        logger.debug("Routes verified.")

    prof = depth_profile(routes)
    prof_dict = {i + 1:prof[i] for i in range(len(prof))} # offset by one

    logger.debug('='* 72 + '\n' +
                 dedent(f'''
                 Average depth: {sum(len(r) for r in routes) / len(routes):.6}
                 Maximum depth: {max(len(r) for r in routes)}
                 Profile {prof_dict}
                 ''').strip() + '\n' +
                 '=' * 72)

    with open(filename, 'wt') as f:
        f.writelines(routes_to_text_gen(routes))
    pass


def exp_main():

    # dt = {'CARNE':{}}
    # dt = {'RANCE':{ Color.from_ordinal(Color.ordinal('10001')):{'FOIST':{}}}}


    # lexicon = load_word_list('default_words.txt')
    # lexicon = load_word_list('wordle_candidates.txt') # 2315 words
    # lexicon = load_word_list('wordle_sample.txt') # 232 words
    # candidates = load_word_list('wordle_sample.txt') # 232 words

    # lexicon = load_word_list('default_words.txt')
    # lexicon = load_word_list('wordle_candidates.txt') # 2315 words

    # lexicon = load_word_list('wordle_sample.txt') # 232 words
    # candidates = load_word_list('wordle_sample.txt') # 232 words

    tree = test_setup('wordle_picks.txt', 'wordle_candidates.txt',
                      dt='dtree/output_dt_rance.5.txt')
    tree.set_branch_rules({0:float('inf')})


    pick_hist = ('RANCE',)
    clue_sub_hist = ('00000', '00001', '00002', '00010', '00011', '00012',
                     '00020', '00021', '00022', '00100', '00101', '00102',
                     '00110', '00111', '00112', '00120', '00122', '00200',
                     '00201', '00202', '00210', '00220', '00221', '00222',
                     '01000', '01001', '01002', '01010', '01011', '01012',
                     '01020', '01021', '01022', '01100', '01101', '01102',
                     '01110', '01111', '01120', '01121', '01200', '01201',
                     '02000', '02001', '02002', '02010', '02011', '02012',
                     '02020', '02022', '02100', '02101', '02102', '02110',
                     '02200', '02201', '02202', '02210', '02212', '02220',
                     '02222', '10000', '10001', '10002', '10010', '10011',
                     '10012', '10020', '10021', '10022', '10100', '10101',
                     '10102', '10110', '10111', '10112', '10200', '10201',
                     '10202', '11000', '11001', '11002', '11010', '11011',
                     '11012', '11020', '11022', '11100', '11101', '11102',
                     '11110', '11112', '11200', '12000', '12001', '12002',
                     '12010', '12011', '12012', '12020', '12022', '12100',
                     '12110', '12200', '12201', '20000', '20001', '20002',
                     '20010', '20011', '20021', '20100', '20101', '20201',
                     '20202', '21000', '21001', '21011', '21020', '21021',
                     '21201', '22000', '22001', '22002', '22011', '22100',
                     '22101', '22200', '22202', '22220')
                

    for clue in clue_sub_hist:
        print("=" * 72)
        run_test(tree, pick_hist, (clue,), dt_depth=1, parallel=False,
                 filename=f'output_dt_rance_{clue}.txt')
        print("=" * 72)


def main():

    # dt = read_decision_tree('dtree/output_dt_rance.5.txt')
    pick = 'BONES'
    dt = {pick:{}}

    # dt = read_decision_tree('dtree/output_dt_rance.txt')
    tree = test_setup('wordle_picks.txt', 'wordle_candidates.txt', dt)
    # tree.set_branch_rules({0:float('inf')})
    run_test(tree, dt=dt, dt_depth=1, parallel=True,
                 filename=f'output_dt_{pick.lower()}.txt')


if __name__ == '__main__' and False:

    cProfile.run('main()', 'output.prof')

    p = pstats.Stats('output.prof')
    p.strip_dirs().sort_stats('cumulative').print_stats(35)  # Show top 10 functions

