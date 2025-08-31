#!/usr/bin/env python3

from solver import GuessManager, GuessFilter
from wordle_game import WordleGame
from random import sample
from collections import namedtuple
import json
from datetime import datetime

class WordleAnalyzer():
    def __init__(self, filename):
        self.game = WordleGame.from_file(filename=filename)
        self.words = self.game.words

    def analyze(self):

        secrets = sample(self.words, 50)
        self.stats_by_guess = {}

        for initial_guess in self.words:

            guess_stats = {'total':0, 'by_secret':{}}
            self.stats_by_guess[initial_guess] = guess_stats
            print(f'pass {initial_guess= }')

            total = 0
            for secret in secrets:
                self.game.reset_game(secret=secret)
                result, feedback = self.game.guess(initial_guess)
                self.filter = GuessFilter(length=5, lexicon=self.words)
                self.filter.update_guess_result(initial_guess, feedback)
                
                remaining = len(self.filter.candidates)
                guess_stats['by_secret'][secret] = remaining
                total += remaining

            guess_stats['total'] = total


    def print_stats(self):
        for guess in sorted(self.stats_by_guess, key=lambda guess: self.stats_by_guess[guess]['total']):
            total = self.stats_by_guess[guess]['total']
            print(f"{guess = }, :{total}")

    def dump_stats(self, filename_base):

        timestamp = datetime.now().strftime("-%Y-%m-%d-%H%M%S")
        with open(filename_base + timestamp + '.json', 'w') as f:
            json.dump(self.stats_by_guess, f, indent=4)


if __name__ == '__main__':
    analyzer = WordleAnalyzer("default_words.txt")
    analyzer.analyze()
    analyzer.print_stats()
    analyzer.dump_stats('stats')

