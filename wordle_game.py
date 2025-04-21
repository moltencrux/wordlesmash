import random

class WordleGame:
    def __init__(self, word_list, max_attempts=6):
        self.word_list = word_list
        self.max_attempts = max_attempts
        self.secret_word = random.choice(self.word_list).upper()
        self.attempts = 0
        self.guesses = []
        self.feedback = []

    def guess(self, word):
        word = word.upper()
        if len(word) != len(self.secret_word):
            raise ValueError("Guess must be the same length as the secret word.")
        if word not in self.word_list:
            raise ValueError("Guess must be a valid word.")

        self.attempts += 1
        self.guesses.append(word)
        feedback = self._provide_feedback(word)

        self.feedback.append(feedback)

        if word == self.secret_word:
            return True, feedback  # Correct guess
        elif self.attempts >= self.max_attempts:
            return False, feedback  # Max attempts reached
        else:
            return False, feedback  # Incorrect guess

    def _provide_feedback(self, guess):
        feedback = ['_'] * len(self.secret_word)
        secret_word_list = list(self.secret_word)

        # First pass: Check for correct letters in the correct position
        for i, letter in enumerate(guess):
            if letter == self.secret_word[i]:
                feedback[i] = 'G'  # Green
                secret_word_list[i] = None  # Remove from consideration

        # Second pass: Check for correct letters in the wrong position
        for i, letter in enumerate(guess):
            if feedback[i] == '_':
                if letter in secret_word_list:
                    feedback[i] = 'Y'  # Yellow
                    secret_word_list[secret_word_list.index(letter)] = None  # Remove to avoid double counting

        return feedback

    def get_status(self):
        return {
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "guesses": self.guesses,
            "feedback": self.feedback,
            "secret_word": self.secret_word if self.attempts >= self.max_attempts else None
        }

    def reset_game(self):
        self.secret_word = random.choice(self.word_list).upper()
        self.attempts = 0
        self.guesses = []
        self.feedback = []

# Example usage
if __name__ == "__main__":
    words = ["APPLE", "BANJO", "CRANE", "DANCE", "EAGLE"]
    game = WordleGame(words)

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
