from itertools import batched
from collections import namedtuple, Counter
from dataclasses import make_dataclass
from wordle_game import Color
from struct import pack
from base64 import b64decode, b64encode
from string import ascii_uppercase
import numpy as np
from rank_comb import generate_combination, rank_combination, rank_multiset

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


# Function to map an ordinal to the corresponding value
def map_ordinal_to_value(ordinal):
    if 0 <= ordinal < len(values):
        return values[ordinal]
    else:
        raise ValueError("Ordinal out of range")





def main_orig():
    # Example usage
    file_path = 'decision_tree.txt'  # Replace with your file path
    root = read_decision_tree(file_path)

def main():

    f1 = FilterCode()
    f2 = FilterCode()

    print(f"{f1 == f2 = }")
    print(f"{f1 = !s}")
    print(f"{f2 = !s}")


if __name__ == '__main__':
    main()
