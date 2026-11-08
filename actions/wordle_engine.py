"""
Wordle for Everyone: game engine.

Plain Python with no Rasa imports, so it can be tested by itself.
Rasa custom actions call these functions. Game state is a plain
dictionary so it can be stored in a Rasa slot.
"""
import importlib.util
import random
import re
from pathlib import Path

ACTIONS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ACTIONS_DIR.parent
WORD_FILE = PROJECT_DIR / "english.py"
ANSWER_FILE = ACTIONS_DIR / "answers.txt"

WORD_LENGTH = 5
DEFAULT_MAX_GUESSES = 6
MAX_HINTS = 3

CORRECT = "correct"
PRESENT = "present"
ABSENT = "absent"

PLAYING = "playing"
WON = "won"
LOST = "lost"
GAVE_UP = "gave_up"

PHRASES = {
    CORRECT: "is in the word and in the right spot",
    PRESENT: "is in the word, but in a different spot",
    ABSENT: "is not in the word",
}
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five"]


# ---------------------------------------------------------------
# Loading words
# ---------------------------------------------------------------
def _load_english_words():
    """Read every word from english.py, whatever format it uses."""
    if not WORD_FILE.exists():
        raise FileNotFoundError(
            f"english.py was not found at {WORD_FILE}. "
            "Put it in the main project folder."
        )
    words = []
    try:
        spec = importlib.util.spec_from_file_location("english", WORD_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for value in vars(module).values():
            if isinstance(value, dict):
                value = list(value.keys())
            if isinstance(value, (list, set, tuple, frozenset)):
                items = [v for v in value if isinstance(v, str)]
                if len(items) > len(words):
                    words = items
            elif isinstance(value, str) and len(value) > 10000:
                items = value.split()
                if len(items) > len(words):
                    words = items
    except Exception:
        words = []
    if not words:
        text = WORD_FILE.read_text(encoding="utf-8", errors="ignore")
        words = re.findall(r"[A-Za-z]+", text)
    return {w.strip().lower() for w in words if w.strip()}


ALL_WORDS = _load_english_words()
VALID_GUESSES = {
    w for w in ALL_WORDS
    if len(w) == WORD_LENGTH and w.isalpha() and w.isascii()
}


def load_answers():
    """Curated answer pool from answers.txt (see curate_answers.py)."""
    if ANSWER_FILE.exists():
        lines = ANSWER_FILE.read_text(encoding="utf-8").splitlines()
        answers = [
            w.strip().lower() for w in lines
            if w.strip() and not w.startswith("#")
        ]
        answers = [w for w in answers if w in VALID_GUESSES]
        if answers:
            return answers
    return sorted(VALID_GUESSES)


ANSWERS = load_answers()


# ---------------------------------------------------------------
# Checking and scoring guesses
# ---------------------------------------------------------------
def check_guess(raw_guess):
    """Return (word, None) if the guess is usable, or (None, kind message)."""
    cleaned = re.sub(r"[\s\-\.,]", "", raw_guess or "").lower()
    no_cost = "That did not use up a guess."
    if not cleaned:
        return None, "I didn't catch a word. Please type a five letter word."
    if not cleaned.isalpha() or not cleaned.isascii():
        return None, f"Please use letters only, no numbers or symbols. {no_cost}"
    if len(cleaned) < WORD_LENGTH:
        return None, (
            f"{cleaned.upper()} has {len(cleaned)} letters. "
            f"The word needs 5 letters. {no_cost}"
        )
    if len(cleaned) > WORD_LENGTH:
        return None, (
            f"{cleaned.upper()} has {len(cleaned)} letters. "
            f"The word needs exactly 5 letters. {no_cost}"
        )
    if cleaned not in VALID_GUESSES:
        return None, (
            f"I don't recognize {cleaned.upper()} as a word. "
            f"Please try another word. {no_cost}"
        )
    return cleaned, None


def score_guess(guess, answer):
    """Score a guess. Handles repeated letters correctly (requirement G5).

    Pass 1 marks letters in the right spot and counts the answer's
    leftover letters. Pass 2 marks a letter as present only while
    that letter still has leftovers, so extra copies are absent.
    """
    result = [ABSENT] * WORD_LENGTH
    leftover = {}
    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            result[i] = CORRECT
        else:
            leftover[a] = leftover.get(a, 0) + 1
    for i, g in enumerate(guess):
        if result[i] != CORRECT and leftover.get(g, 0) > 0:
            result[i] = PRESENT
            leftover[g] -= 1
    return result


def describe_result(guess, result):
    """Plain language result that a screen reader or voice can read."""
    return " ".join(
        f"{g.upper()} {PHRASES[r]}." for g, r in zip(guess, result)
    )


# ---------------------------------------------------------------
# Game state
# ---------------------------------------------------------------
def new_game(max_guesses=DEFAULT_MAX_GUESSES, answer=None):
    return {
        "answer": answer or random.choice(ANSWERS),
        "guesses": [],
        "results": [],
        "max_guesses": max_guesses,
        "status": PLAYING,
        "hints_used": 0,
    }


def guesses_left(state):
    return state["max_guesses"] - len(state["guesses"])


def _plural(n, word):
    if n == 1:
        return f"{n} {word}"
    if word.endswith("s"):
        return f"{n} {word}es"
    return f"{n} {word}s"


def submit_guess(state, raw_guess):
    """Return (new_state, message, guess_was_used)."""
    if state["status"] != PLAYING:
        return state, "This game is over. Say new game to play again.", False

    word, problem = check_guess(raw_guess)
    if problem:
        return state, problem, False
    if word in state["guesses"]:
        return state, (
            f"You already tried {word.upper()}. Please try a different "
            "word. That did not use up a guess."
        ), False

    result = score_guess(word, state["answer"])
    state = dict(state)
    state["guesses"] = state["guesses"] + [word]
    state["results"] = state["results"] + [result]
    n = len(state["guesses"])
    left = guesses_left(state)

    message = (
        f"Guess {n} of {state['max_guesses']}: {word.upper()}. "
        f"{describe_result(word, result)}"
    )
    if all(r == CORRECT for r in result):
        state["status"] = WON
        message += (
            f" You solved it in {_plural(n, 'guess')}. Wonderful work! "
            "Would you like to play again?"
        )
    elif left == 0:
        state["status"] = LOST
        message += (
            f" That was the last guess. The word was "
            f"{state['answer'].upper()}. That was a tricky one. "
            "Would you like to play again?"
        )
    else:
        message += f" You have {_plural(left, 'guess')} left."
    return state, message, True


def give_up(state):
    """Kindly reveal the word."""
    state = dict(state)
    state["status"] = GAVE_UP
    return state, (
        f"No problem at all. The word was {state['answer'].upper()}. "
        "Would you like to play another one?"
    )


# ---------------------------------------------------------------
# Help features (enhancements)
# ---------------------------------------------------------------
def get_hint(state):
    """Hints go from gentle to direct. Hints never use up a guess."""
    if state["status"] != PLAYING:
        return state, "There's no game in progress. Say new game to start one."
    used = state.get("hints_used", 0)
    if used >= MAX_HINTS:
        return state, (
            f"You've used all {MAX_HINTS} hints for this game. You can keep "
            "guessing, or say I give up to see the word."
        )

    answer = state["answer"]
    if used == 0:
        vowels = sum(1 for c in answer if c in "aeiou")
        if vowels == 0:
            text = "Gentle hint: the word has no A, E, I, O, or U. It may use Y."
        else:
            text = (
                f"Gentle hint: the word has {_plural(vowels, 'vowel')} "
                "(A, E, I, O, or U)."
            )
    elif used == 1:
        found = {
            g for word, res in zip(state["guesses"], state["results"])
            for g, r in zip(word, res) if r != ABSENT
        }
        hidden = [c for c in dict.fromkeys(answer) if c not in found]
        if hidden:
            text = (
                f"Medium hint: the letter {random.choice(hidden).upper()} "
                "is somewhere in the word."
            )
        else:
            text = (
                "Medium hint: you've already found every letter. "
                "Now it's just about the order."
            )
    else:
        solved = {
            i for res in state["results"]
            for i, r in enumerate(res) if r == CORRECT
        }
        open_spots = [i for i in range(WORD_LENGTH) if i not in solved] or [0]
        i = open_spots[0]
        text = f"Direct hint: letter {i + 1} is {answer[i].upper()}."

    state = dict(state)
    state["hints_used"] = used + 1
    left = MAX_HINTS - state["hints_used"]
    text += f" Hints never use up a guess. Hints left: {left}."
    return state, text


def explain_letter(state, guess_number, position):
    """Explain why one letter got its result. Numbers start at 1."""
    if not state["guesses"]:
        return "You haven't made a guess yet."
    if not 1 <= guess_number <= len(state["guesses"]):
        return f"Please pick a guess from 1 to {len(state['guesses'])}."
    if not 1 <= position <= WORD_LENGTH:
        return "Please pick a letter position from 1 to 5."

    guess = state["guesses"][guess_number - 1]
    result = state["results"][guess_number - 1][position - 1]
    letter = guess[position - 1]
    L = letter.upper()
    intro = f"In guess {guess_number}, letter {position} is {L}."

    if result == CORRECT:
        return f"{intro} It's in the right spot. The word also has {L} in spot {position}."
    if result == PRESENT:
        return f"{intro} The word has {L}, but not in spot {position}. Try it in another spot."
    count = state["answer"].count(letter)
    if count:
        return (
            f"{intro} The word has only {NUMBER_WORDS[count]} {L}, and your "
            f"other {L} already counted for it, so this extra {L} is marked "
            "not in the word."
        )
    return f"{intro} The word has no {L}, so you can rule it out."


def remaining_candidates(state):
    """Common words that still fit every clue so far."""
    pairs = list(zip(state["guesses"], state["results"]))
    return [
        w for w in ANSWERS
        if all(score_guess(g, w) == r for g, r in pairs)
    ]


def letter_status(state):
    """Best known result for each letter, for the on screen keyboard."""
    rank = {ABSENT: 0, PRESENT: 1, CORRECT: 2}
    best = {}
    for word, res in zip(state["guesses"], state["results"]):
        for c, r in zip(word, res):
            if c not in best or rank[r] > rank[best[c]]:
                best[c] = r
    return best


def board_summary(state):
    """Read back every guess so far (memory support)."""
    if not state["guesses"]:
        return (
            f"No guesses yet. You have {_plural(state['max_guesses'], 'guess')}. "
            "Type or say any five letter word to begin."
        )
    lines = [
        f"Guess {i}: {g.upper()}. {describe_result(g, r)}"
        for i, (g, r) in enumerate(zip(state["guesses"], state["results"]), 1)
    ]
    if state["status"] == PLAYING:
        lines.append(f"You have {_plural(guesses_left(state), 'guess')} left.")
    return " ".join(lines)


# ---------------------------------------------------------------
# Finding a guess inside a sentence (for voice and chatty players)
# ---------------------------------------------------------------
FILLER_WORDS = {
    "guess", "think", "maybe", "could", "would", "about", "there",
    "their", "which", "where", "thank", "thanks", "might", "sorry",
    "words", "first", "start", "again", "shall", "right", "wrong",
}


def extract_guess(text):
    """Pull a guess out of things like 'crane', 'C R A N E',
    'my guess is crane', or 'is it crane?'. Returns None if unsure."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if re.fullmatch(r"(?:[a-z][\s,\-\.]+){4}[a-z][\s\.]*", t):
        return re.sub(r"[^a-z]", "", t)
    words = re.findall(r"[a-z]+", t)
    if len(words) == 1:
        return words[0]
    five = {
        w for w in words
        if len(w) == WORD_LENGTH and w in VALID_GUESSES and w not in FILLER_WORDS
    }
    if len(five) == 1:
        return five.pop()
    return None