import random
from enum import Enum, EnumMeta, IntEnum
from collections import Counter
import json
from functools import lru_cache

class ColorMeta(EnumMeta):
    def __init__(cls, name, bases, classdict):
        super().__init__(name, bases, classdict)
        # Automatically initialize the _map attribute when the class is created
        cls._map = {name[0]: member for name, member in cls.__members__.items()}

        cls._val_map = {member.value: member for member in cls.__members__.values()}

class Color(IntEnum, metaclass=ColorMeta):
    BLACK = 0
    YELLOW = 1
    GREEN = 2
    UNKNOWN = -1

    @staticmethod
    def map(c):
        return Color._map.get(c, Color.UNKNOWN)

    @staticmethod
    def from_value(color):
        return Color._val_map.get(color, Color.UNKNOWN)

    @staticmethod
    @lru_cache
    def ordinal(seq):
        if isinstance(seq, str):
            seq = tuple(Color(int(c)) for c in seq)
        return sum(d.value * (3 ** p) for p, d in enumerate(seq))

    @staticmethod
    def from_ordinal(n, length=5):
        seq = [Color.from_value(d % 3) for d in iter(lambda: n, 0) if (n := n // 3) >= 0]
        seq += [Color.BLACK] * max(0, length - len(seq))
        return tuple(seq)

    @staticmethod
    def seq_to_num_str(seq):
        return ''.join(str(c.value) for c in seq)

    @staticmethod
    @lru_cache
    def all_green(length=5):
        return Color.ordinal((Color.GREEN,)*length)
    

    # class ColorEncoder(json.JSONEncoder):

    #     def default(self, obj):
    #         if isinstance(obj, Color):
    #             return obj.value
    #         elif isinstance(obj, dict):
    #             # Convert dictionary keys if they are enums
    #             return {key.value if isinstance(key, Color) else key: value for key, value in obj.items()}
    #         return super().default(obj)


def get_clue_for_secret(pick, secret):

    feedback = [Color.BLACK] * len(secret)
    secret_counts = Counter(secret)

    rest = []
    # find where each letter is located for yellow

    for i, (g, s) in enumerate(zip(pick, secret)):
        if g == s:
            feedback[i] = Color.GREEN
            secret_counts[g] -= 1
        else:
            rest.append((i, g))

    for i, g in rest:
        if g in secret_counts and secret_counts[g] > 0:
            secret_counts[g] -= 1
            feedback[i] = Color.YELLOW

    return tuple(feedback)


class WordleGame:
    def __init__(self, word_list, max_attempts=6, secret=None):
        self.word_set = set(word.upper() for word in word_list)
        self.words = tuple(word.upper() for word in word_list)
        self.max_attempts = max_attempts
        self.reset_game()

    @classmethod
    def from_file(cls, filename, max_attempts=6, word_length=5, secret=None):
        with open(filename) as file:
            heads = (line[:word_length + 1] for line in file if line)
            words = tuple(word.strip() for word in heads if word.find(' ') == word_length)
            return cls(words, max_attempts)

    def guess(self, word):
        word = word.upper()
        if len(word) != len(self.secret_word):
            raise ValueError("Guess must be the same length as the secret word.")
        if word not in self.word_set:
            raise ValueError("Guess must be a valid word.")

        self.attempts += 1
        self.guesses.append(word)
        feedback = self._get_feedback(word)

        self.feedback.append(feedback)

        if word == self.secret_word:
            return True, feedback  # Correct guess
        elif self.attempts >= self.max_attempts:
            return False, feedback  # Max attempts reached
        else:
            return False, feedback  # Incorrect guess


    def _get_feedback_orig(self, guess):
        # this version is likely faster for word length 5
        feedback = [Color.BLACK] * len(self.secret_word)
        secret_word_list = list(self.secret_word)

        # First pass: Check for correct letters in the correct position
        for i, letter in enumerate(guess):
            if letter == self.secret_word[i]:
                feedback[i] = Color.GREEN
                secret_word_list[i] = None  # Remove from consideration

        # Second pass: Check for correct letters in the wrong position
        for i, letter in enumerate(guess):
            if feedback[i] == Color.BLACK:
                if letter in secret_word_list:
                    feedback[i] = Color.YELLOW
                    secret_word_list[secret_word_list.index(letter)] = None  # Remove to avoid double counting

        return feedback


    def _get_feedback(self, guess):
        return get_feedback_for_secret(guess, self.secret_word)

    def get_status(self):
        return {
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "guesses": self.guesses,
            "feedback": self.feedback,
            "secret_word": self.secret_word if self.attempts >= self.max_attempts else None
        }

    def reset_game(self, secret=None):
        self.secret_word = random.choice(self.words).upper()
        self._secret_counts = Counter(self.secret_word)
        self.attempts = 0
        self.guesses = []
        self.feedback = []


class WordleGameManager():
    ...

# Example usage
if __name__ == "__main__":
    game = WordleGame.from_file('default_words.txt')

    while True:
        guess = input("Enter your guess: ")
        try:
            correct, feedback = game.guess(guess)
            print("Feedback:", feedback)
            if correct:
                print("Congratulations! You've guessed the word!")
                break
            elif game.attempts >= game.max_attempts:
                print("Game over! The secret word was:", game.secret_word)
                break
        except ValueError as e:
            print(e)
