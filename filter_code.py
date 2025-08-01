from itertools import batched, groupby, chain
from collections import namedtuple, Counter
from dataclasses import make_dataclass
from wordle_game import Color
from struct import pack
from base64 import b64decode, b64encode
from string import ascii_uppercase
import numpy as np
from rank_comb import generate_combination, rank_combination, rank_multiset, generate_multiset




class FilterCode:
    alphabet = dict.fromkeys(ascii_uppercase)
    domain = dict.fromkeys((*alphabet, None))
    char_ord = {c:i for i, c in enumerate(domain.keys())}
    ord_char = {v:k for k, v in char_ord.items()}
    char_bits_map = {c:tuple(b == '1' for b in f'{i:05b}') for i, c in enumerate(domain.keys())}
    bits_char_map = {v:k for k, v in char_bits_map.items()}

    def __init__(self, blacklist=None, known_chars=None, viable=None, confirmed=None):
        self.bits = np.zeros(76, dtype=bool)
        # Bit partitioning
        # 25, 25, 26: 76
        self.char_bits = self.bits[0:25].reshape((5, 5)) # Bits 0-17: Known letters (18 bits)
        self.presence = self.bits[25:50].reshape((5, 5)) # Bits 18-37: possible presense bitfield (25 bits, 5 letters)
        self.presence[:,:] = np.ones((5, 5), dtype=bool) # set presence to all ones
        # axis 0 is asociated w/ character, axis 1 is the column

        self.blacklist = self.bits[50:76]                # Bits 38-63: Blacklist (26 bits)

        # Initialize with provided values
        if known_chars is not None:
            self.set_known_chars(known_chars)
            if viable is not None and confirmed is not None:
                self.set_presence_flags(viable, confirmed)
        if blacklist is not None:
            self.set_blacklist_kw(**blacklist)

    def __eq__(self, other):
        if isinstance(other, FilterCode):
            return np.array_equal(self.bits, other.bits)
        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other) if isinstance(other, FilterCode) else NotImplemented

    def __lt__(self, other):
        if isinstance(other, FilterCode):
            return (self.blacklist, self.hit_chars, self.hit_mask) < (other.blacklist, other.hit_chars, other.hit_mask)
        return NotImplemented

    def __le__(self, other):
        if isinstance(other, FilterCode):
            return (self.blacklist, self.hit_chars, self.hit_mask) <= (other.blacklist, other.hit_chars, other.hit_mask)
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, FilterCode):
            return (self.blacklist, self.hit_chars, self.hit_mask) > (other.blacklist, other.hit_chars, other.hit_mask)
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, FilterCode):
            return (self.blacklist, self.hit_chars, self.hit_mask) >= (other.blacklist, other.hit_chars, other.hit_mask)
        return NotImplemented

    @classmethod
    def from_guess_filter(cls, guess):

        blacklist = {k:k in guess.blacklist for k in cls.alphabet}
        return cls(blacklist, guess.letters, guess.viable, guess.confirmed)

    # def to_guess_filter(self):

    #     # what about the dictionaries / lexicon?
    #     guess = GuessFilter()
    #     blacklist = {self.ord_char[pos] for pos in np.where(self.blacklist)[0]}
    #     guess.set_blacklist(blacklist)

    #     letters = self.unpack_known_chars()

    #     # Set known characters
    #     for c in filter(None, letters):
    #         guess.viable.setdefault(c, guess.viable[None].copy())
    #         guess.confirmed.setdefault(c, [False] * guess.length)

    #     for r, row in enumerate(self.presence):
    #         char = letters[r]
    #         guess.viable[char][:] = [v.item() for v in row]

    #     # axis 0 is char, axis 2 col/position
    #     for c, col in enumerate(self.presence.T):
    #         rows = np.where(col)[0]
    #         if len(rows) == 1:
    #             # Only one letter viable for a column indcates a green/verifeid position (column)
    #             r = rows[0]
    #             char = letters[r]
    #             guess.confirmed[char][c] = True
    #             guess.viable[char][c] = False

    #     # XXX delete this stuff, not necessary i think
    #     # guess.set_qty_mins()
    #     # guess._qty_mins[c] = max(self._qty_mins[c], min_qty, self.confirmed[c].count(True))

    #     return guess

    def is_fully_known(self):
        """Check if all 5 letters are known (multiplicity of 5)."""
        # return sum(1 for c in self.unpack_known_chars() if c is not None) == 5
        # return sum(1 for c in filter(None, self.unpack_known_chars())) == 5
        return None not in self.unpack_known_chars()

    def set_known_chars(self, charset):
        """Set known letters using combinatorial ranking."""

        letters = [item for c, n in charset.items() for item in [c] * n]
        letters += [None] * (5 - len(letters)) # add Nones to pad to length 5
        letters.sort(key=self.char_ord.get)

        # charset = sorted(charset, key=self.char_ord.get)
        # self.char_bits[:] = (b for b in self.char_bits_map(c) for c in charset)
        # self.char_bits[:] = [b for c in letters for b in self.char_bits_map[c]]

        self.char_bits[:,:] = [self.char_bits_map[c] for c in letters]


    def unpack_known_chars(self):
        """Unpack known letters from bit field."""
        # return [self.bits_char_map[tuple(bits)] for bits in self.char_bits.reshape(5, 5)]
        # known_chars = []
        #  
        # for bits in self.char_bits:
        #     known_chars.append(self.bits_char_map[tuple(bits)])

        # return known_chars
        return [self.bits_char_map[tuple(bits)] for bits in self.char_bits]

    def set_blacklist(self, bits):
        """Clear and set the blacklist to the specified characters. Letters in
        the blacklist will not have any further occurrences than those arlready
        known."""

        if len(self.bits) != 26:
            raise ValueError("blacklist bits must have length 26.")
        elif not self.is_fully_known():
            self.blacklist[:] = bits
        elif not all(bits):
            raise ValueError("blacklist must be all ones when all letters are known.")

    def set_blacklist_chars(self, *chars):
        """Clear and set the blacklist to the specified characters. Letters in
        the blacklist will not have any further occurrences than those arlready
        known."""

        if not self.is_fully_known():
            self.blacklist[:] = np.zeros_like(self.blacklist, dtype=bool)
            for c in chars:
                self.blacklist[self.char_ord[c]] = True
        elif set(chars) != set(self.alphabet):
            raise ValueError("blacklist must be all ones when all letters are known.")

    def set_blacklist_kw(self, **blacklist):
        """Clear and set the blacklist to the specified characters. Letters in
        the blacklist will not have any further occurrences than those arlready
        known."""

        if not self.is_fully_known():
            self.blacklist[:] = np.zeros_like(self.blacklist, dtype=bool)
            for c, val in blacklist.items():
                self.blacklist[self.char_ord[c]] = val
        elif not all(blacklist.values()):
            raise ValueError("blacklist must be all ones when all letters are known.")

    def update_blacklist_chars(self, *chars):
        """Adds one or more letters to the current blacklisted to prevent further occurrences if not fully known."""
        if not self.is_fully_known():
            for c in chars:
                index = self.ord_char[c]
                self.blacklist[index] = True

    def get_presence(self):
        """Return the bitfields representing the columns in which known letters
        could be present and confirmed to be present."""
        return self.presence

    def get_blacklist_chars(self):
        """Return a set of letters with no further occurrences allowed."""
        # np.where(self.blacklist)
        if self.is_fully_known():
            return {*self.alphabet}
        else:
            return {self.ord_char[pos] for pos in np.where(self.blacklist)[0]}

    def get_blacklist(self):
        """Return a bitfield representing letters with no further occurrences allowed."""
        if self.is_fully_known():
            return np.ones(26)
        else:
            return self.blacklist.copy()


    # XXX maybe irrelevant now
    def _get_sorted_positions(self, chars):
        """Return a list of (letter, sorted_index) for non-None letters in sorted order."""
        # Filter non-None letters and sort (None sorts last in alphabet)
        non_none = [c for c in chars if c is not None]
        sorted_chars = sorted(non_none)  # Sort lexicographically
        # Map each letter to its index in the sorted list
        positions = []
        for c in chars:
            if c is not None:
                # Find the index of this letter in sorted_chars (first occurrence)
                for i, sc in enumerate(sorted_chars):
                    if sc == c:
                        positions.append((c, i))
                        sorted_chars[i] = None  # Remove to handle duplicates
                        break
        return positions

    def set_presence_flags(self, viable, confirmed):
        """Sets the viable/confirmed presence flags"""
        # does viable on evertying encompass everything?
        # greens will be foudn when only 1 character had a 1 in the viable spot.
        # But what about Nones bitfield? 
        # a 1 for None means that a spot is viable for any not yet known characters
        # so if a green is found, it would be marked off of the None's flags, even though
        # so further instances of known characters will be mutually exclusive with Nones
        # 

        ### letters = sorted(letters, key=self.char_ord.get)

        # counts = Counter(letters)
        # bits = []
        letters = Counter(self.unpack_known_chars())

        #letters = letters.copy()
        # letters = [l for c, n in letters.items() for l in (c,) * n]
        # letters.sort(key=self.char_ord.get)

        # XXX maybe unecessary
        if letters.total() < 5:
            letters[None] = (5 - letters.total())
        # else:
        #     del letters[None]
            
        # need to figure out how many greens there are for each char

        # couldn't we just use counts.keys instead of groupby?
        # for c in sorted(counts.keys(), key=self.char_ord.get)):
        # XXX i think greens should be isolated
        # are they ME with yellows in the guess filter??
        # should they be?


        # this copies the viable / confirmed presence bits into the
        # columns for each character instance. For confirmed greens,
        # it copies all False values except its location. For unconfirmed
        # presence, it copies the viable bitfield

        # letgen = (c for l, n in letters.items() for c in l*n)
        rows = iter(self.presence)

        for letter, count in letters.items():
            conf_pos = [pos for pos, bit in enumerate(confirmed[letter]) if bit]
            for pos in conf_pos:
                row = next(rows)
                row[:] = viable[letter]
                row[pos] = True
                # next(cols)[:] = [i == pos for i in range(5)]
            for _ in range(count - len(conf_pos)):
                next(rows)[:] = viable[letter]


        # XXX SHIt, just thinking if we know a single green, and we had
        # previously seen a yellow on it at another spot. How do we record
        # that? b/c there may or may not be a dup later. but we lose that info
        # by only storing the green.
        # Sol: (i think)  We must still store the viable or(+) known green
        # but mark the known green pos out from all others (including unknown)
        # Q shoudl we store sth different for a pure yellow if paird w/ a green?
        # maybe.. like.. don't store gn
        # SO: For greens, we store viable bits also. But we know that no viable
        # bit for any other character will ever been set in that position


        # for pcol, c in zip(self.presence, letgen):
        # #for c, _ in groupby(sorted(letters, key=self.char_ord.get)):
        #     pcol[:] = [v or c for v, c in zip(viable[c], confirmed[c])]

        # counts = Counter(letters)
        # bits = []

        # for c, _ in groupby(sorted(letters)):
        #     # counts.update(c)

        #     remaining = counts[c]
        #     for pos in (pos for pos, bit in enumerate(confirmed[c]) if bit):
        #         conf = [False] * len(confirmed[c])
        #         conf[pos] = True
        #         bits.extend(conf)
        #         remaining -= 1
        #     for _ in range(remaining):
        #         bits.extend(v and not c for v, c in zip(viable[c], confirmed[c]))

        # first = min(len(bits), 20)
        # rest = max(len(bits) - 20, 0)

        # self.presence[:] = bits[:first] + [False] * (20 - len(bits))
        # self.fifth_letter_presence[:rest] = bits[20:]



    def set_presence_flags_old(self, viable, confirmed, letters):
        """Sets the viable/confirmed presence flags"""

        counts = Counter(letters)
        bits = []

        for c, _ in groupby(sorted(letters)):
            # counts.update(c)

            remaining = counts[c]
            for pos in (pos for pos, bit in enumerate(confirmed[c]) if bit):
                conf = [False] * len(confirmed[c])
                conf[pos] = True
                bits.extend(conf)
                remaining -= 1
            for _ in range(remaining):
                bits.extend(v and not c for v, c in zip(viable[c], confirmed[c]))

        first = min(len(bits), 20)
        rest = max(len(bits) - 20, 0)

        self.presence[:] = bits[:first] + [False] * (20 - len(bits))
        self.fifth_letter_presence[:rest] = bits[20:]

    # XXX don't know about this
    def add_yg(self, letter, green=False, slot=None):
        """Add a letter to the YG list and update presence with green/yellow constraints."""
        # Validate inputs
        if letter not in self.domain:
            raise ValueError(f"Letter must be in {self.alphabet[:-1]}")
        if slot is not None and (not isinstance(slot, int) or slot < 0 or slot > 4):
            raise ValueError("Slot must be an integer between 0 and 4")
        if green and slot is None:
            raise ValueError("Slot is required for green letters")
        if not green and slot is None and letter not in self.unpack_known_chars():
            raise ValueError("Slot is required for new yellow letters")

        # Get current known_chars and presence
        known_chars = list(self.unpack_known_chars())
        current_mask = self.get_presence()
        num_known = sum(1 for c in known_chars if c is not None)

        # If already 5 letters, no action needed
        if num_known >= 5:
            return

        # Store current sorted positions and masks
        old_positions = self._get_sorted_positions(known_chars)
        old_masks = {p[1]: current_mask[i] for p in old_positions for i in range(len(current_mask)) if i == p[1]}

        # Add the new letter
        if None in known_chars:
            known_chars[known_chars.index(None)] = letter
        self.set_known_chars(known_chars)

        # Get new sorted positions
        new_positions = self._get_sorted_positions(known_chars)
        new_letter_index = next(i for c, i in new_positions if c == letter)

        # Shift masks to align with new sorted positions
        new_mask = np.zeros((5, 5), dtype=bool)
        for c, new_idx in new_positions:
            if (c, new_idx) == (letter, new_letter_index):
                # Set mask for the new letter
                if green:
                    new_mask[new_idx] = [True] * 5
                    new_mask[new_idx, slot] = False  # Only slot is allowed
                else:
                    new_mask[new_idx, slot] = True  # Slot is forbidden
            else:
                # Copy old mask to new position
                old_idx = next(i for cc, i in old_positions if cc == c)
                new_mask[new_idx] = old_masks.get(old_idx, np.zeros(5, dtype=bool))

        # Update presence or fifth_letter_presence
        if num_known == 4:  # Adding 5th letter
            self.fifth_letter_presence[:] = new_mask[4]
            self.blacklist[5:] = False  # Clear remaining blacklist
        self.presence[:] = new_mask[:4].flatten()


    def construct_guess_filter(self):
        ...

    def pack_to_bytes(self):
        padding = np.zeros(((8 - len(self.bits) % 8) % 8), dtype=bool)
        bits = np.concat((padding, self.bits))
        return np.packbits(bits).tobytes()


    # XXX need to check if this works correctly
    def unpack_bytes(self, byte_str):
        alphabet = (*ascii_uppercase, None)
        # ord_char = {f'{i:0{5}b}':c for i, c in enumerate(alphabet)}
        bit_str = ''.join(f'{int.from_bytes(byte):0{8}b}' for byte in byte_str)

        blacklist = [bit == '1' for bit in bit_str[-76:-50]]
        hit_chars = generate_multiset(int(bit_str[-43:-25], 2), alphabet)
        hit_mask = [[bit == '1' for bit in b5] for b5 in batched(bit_str[-25:], 5)]

        return bit_str, hit_chars, hit_mask


    def convert_to_filter(self):
        ...


    def to_string(self):
        # this could be handy for a hash thing to index a dict
        return b64encode(self.pack_to_bytes()).decode()

    def __str__(self):
        # this could be handy for a hash thing to index a dict
        return self.to_string()


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







def main():
    # Example usage
    file_path = 'decision_tree.txt'  # Replace with your file path
    root = read_decision_tree(file_path)

def main_old():

    f1 = FilterCode()
    f2 = FilterCode()

    print(f"{f1 == f2 = }")
    print(f"{f1 = !s}")
    print(f"{f2 = !s}")


if __name__ == '__main__':
    main()

