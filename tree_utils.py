from itertools import batched, zip_longest
from collections import namedtuple, Counter
from dataclasses import make_dataclass
from wordle_game import Color
from struct import pack
from base64 import b64decode, b64encode
from string import ascii_uppercase
import numpy as np
from rank_comb import generate_combination, rank_combination, rank_multiset
from wordle_game import get_clue_for_secret

"""
so maybe 25 bits max for the yellow spot blacklist

 26 pure black blacklist
 29:30 5 char + 5 bits to denote yellow/green. can't use BL bits b/c dup chars 
 25 bits (5 for each Y)
-------------------------------------------- 
 81 bits total
 green in wrong slot? doesn't corresond to bitmask?
 76 bits if we don't use a Y/G mask & imply it from a 1 in bitmask


what if we put the green in a slot that is out of order?
dup letters in yg list should have same bitmask
"""


def bit_string_to_bytes(bit_string):
    # Ensure the bit string is a valid binary string
    if not all(bit in '01' for bit in bit_string):
        raise ValueError("Input must be a binary string containing only '0' and '1'.")

    # Pad the bit string with leading zeros if necessary
    padding_length = (8 - len(bit_string) % 8) % 8
    bit_string = '0' * padding_length + bit_string

    # Convert the bit string to bytes
    byte_array = bytearray()
    for i in range(0, len(bit_string), 8):
        byte = bit_string[i:i+8]
        byte_array.append(int(byte, 2))  # Convert each 8-bit segment to an integer and append to the byte array

    return bytes(byte_array)


def read_decision_tree(file):
    tree = {}

    with open(file, 'r') as f:

        for line in f:
            branch = tree
            for guess, clue in batched(line.upper().split(), 2):
                clue = tuple(Color(int(c)) for c in clue)
                clue_dict = branch.setdefault(guess, {})
                if all(c == Color.GREEN for c in clue):
                    branch = clue_dict.setdefault(clue, None)
                else:
                    branch = clue_dict.setdefault(clue, {})

    return tree

def read_decision_routes(file):

    routes = []
    with open(file, 'r') as f:
        # for line in f:
        # routes = []
        # for line in f:
        #     line = line.strip().upper()
        #     if line:
        #         route = line.split()[::2]
        #         routes.append(route)
        # fs = (line.strip() for line in f)

        # routes = tuple(tuple(line.upper().split()[::2]) for line in f if line)

        route_gen = (tuple(line.upper().split()[::2]) for line in f)
        routes = tuple(route for route in route_gen if route)

    return tuple(routes)

#def route_list_to_dt(routes):
def routes_to_dt(routes):

    tree = {}

    for path in routes:
        solution = path[-1]

        branch = tree
        for guess in path:
            clue = get_clue_for_secret(guess, solution)

            clue_dict = branch.setdefault(guess, {})

            if all(c == Color.GREEN for c in clue):
                branch = clue_dict.setdefault(clue, None)
            else:
                branch = clue_dict.setdefault(clue, {})

    return tree

def read_decision_tree_set(file):
    Node = namedtuple('Node', ['root', 'routes'])
    tree = Node({}, {})

    with open(file, 'r') as f:
        for line in f:
            branch = tree.root
            route = set()
            
            for decision, result in batched(line.upper().strip().split('\t'), 2):
                result = tuple(Color(int(c)) for c in result)
                route.add(decision)
                result_dict = tree.routes.setdefault(frozenset(route), {})
                branch.setdefault(decision, result_dict)
                branch = result_dict.setdefault(result, {})

    return tree


def read_decision_tree_working(file):
    Node = namedtuple('Node', ['choice', 'results'])
    # decision_tree = tn({}
    # Node = namedtuple('Node', ['choice', 'results'])
    # Node = make_dataclass('Node', ['play', 'results'])

    tree = {}

    with open(file, 'r') as f:
        for line in f:
            first_choice, *rest = [*line.strip().split('\t'), None]
            results = tree.setdefault(None, Node(first_choice, {})).results

            for result, choice in batched(rest, 2):
                results.setdefault(result, choice and Node(choice, {}))
                results = choice and results[result].results

    return tree[None]

def read_decision_tree_xxx(file):
    # so in the tree, how might we keep choices ranked?
    # ordered set? list?
    Node = namedtuple('Node', ['choices', 'results'])
    # decision_tree = tn({}
    # Node = namedtuple('Node', ['choice', 'results'])
    # Node = make_dataclass('Node', ['play', 'results'])

    tree = {}
    top = Node(set(), {})

    with open(file, 'r') as f:
        for line in f:
            node = top
            tokens = line.strip().split('\t')

            for choice, result, in batched(tokens, 2):
                node.choices.add(choice)
                result_key = (choice, result)
                prev_node = node
                node = node.results.setdefault(result_key, result, Node(set(), {}))

            prev_node.results[result] = None

    return top

def routes_to_text(routes):
    """
    """
    return ''.join(routes_to_text_gen(routes))

def routes_to_text_gen(routes):
    """
    """
    lines = []
    for path in routes:
        tokens = []
        solution = path[-1]

        for guess in path:
            clue_str = Color.seq_to_num_str(get_clue_for_secret(guess, solution))
            tokens += [guess, clue_str]

        yield '\t'.join(tokens) + '\n'

def verify_routes(routes, solutions):
    """
    Given a set of routes for a decision tree, verify the consitency against
    a set of solutions.
    """
    routes = sorted(routes)
    solutions = set(solutions)
    route_solution_words = set(route[-1] for route in routes)
    # Verify that there is a root to leaf route for every possible solution
    if solutions != route_solution_words:
        return False

    # Verify that there is only one possible word choice at any node, given the
    # clue for that node. dt_to_routes() only follows one word choice at each
    # level, so any inconcsistencies when converting back will result in missing
    # routes
    
    dt = routes_to_dt(routes)
    out_routes = sorted(dt_to_routes(dt))
    if routes != out_routes:
        return False

    return True

def dt_to_routes(root):

    stack = [((), root)]
    routes = []

    index = 0

    while stack:
        base, branch = stack.pop()
        for leg, clues in branch.items():
            path = base + (leg,)

            for clue, next_branch in clues.items():
                if all(v == Color.GREEN for v in clue) and next_branch is None:
                    routes.append(path)
                else:
                    stack.append((path, next_branch))

    return routes

def dt_to_text(tree):

    return routes_to_text(dt_to_routes(tree))

    # # Create a stack for the nodes to visit
    # stack = [start]
    # # Create a set to keep track of visited nodes
    # # visited = set()

    # while stack:
    #     # Pop a node from the stack
    #     node = stack.pop()
    #     # if node not in visited:

    #     # Mark the node as visited
    #     # visited.add(node)
    #     print(node)  # Process the node (e.g., print it)

    #     # Add all unvisited neighbors to the stack
    #     for neighbor in graph[node]:
    #         if neighbor not in visited:
    #             stack.append(neighbor)

def dt_bf_level_profile(dt):
    profile = []

    stack = [((), dt)]
    routes = []

    index = 0

    while stack:
        base, branch = stack.pop()
        leg, clues = next(iter(branch.items()))
        path = base + (leg,)

        for clue, next_branch in clues.items():
            if all(v == Color.GREEN for v in clue) and next_branch is None:
                routes.append(path)
            else:
                stack.append((path, next_branch))

    return routes
    ...

def dt_max_depth(root):
    """
    Finds the maximum depth of a decision tree. Currently assumes that only 1
    pick is recommended per clue.
    """

    max_depth = 0
    stack = [((), root)]

    while stack:
        base_picks, branch = stack.pop()
        pick, clues = next(iter(branch.items()))
        path = base_picks + (pick,)
        max_depth = max(max_depth, len(path)) 

        for clue, next_branch in clues.items():
            if next_branch is not None:
                stack.append((path, next_branch))

    return max_depth

def dt_max_depth_subtree(root, base_picks=(), base_clues=()):
    subtree = root
    top_depth = len(base_picks)

    for pick, clue in zip_longest(base_picks, base_clues):
        subtree = root[pick][clue]

    return top_depth + dt_max_depth(subtree)




def main():
    # Example usage
    file_path = 'decision_tree.txt'  # Replace with your file path
    root = read_decision_tree(file_path)


if __name__ == '__main__':
    main()
