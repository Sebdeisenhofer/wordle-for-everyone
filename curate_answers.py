"""
Builds actions/answers.txt, the curated answer pool (requirement G7).
Run once:  python curate_answers.py

Method:
  1. Start from every five letter, letters only word in english.py.
  2. Keep only common words: wordfreq Zipf frequency of at least MIN_ZIPF.
     (Zipf 3.5 means roughly 3 or more uses per million words of English.)
  3. Remove simple plurals and past tense forms (BOXES, ACTED) so answers
     are base words.
  4. Remove offensive words (better-profanity list) and anything listed
     in answer_blocklist.txt, which we add to after reviewing the list.
Every word in english.py is still accepted as a GUESS. Only the answers
are limited.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "actions"))

from better_profanity import profanity
from wordfreq import zipf_frequency

from wordle_engine import ALL_WORDS, ANSWER_FILE, VALID_GUESSES

MIN_ZIPF = 3.5
BLOCKLIST_FILE = ROOT / "answer_blocklist.txt"


def is_inflection(w):
    if w.endswith("es") and w[:-2] in ALL_WORDS:
        return True
    if w.endswith("s") and not w.endswith("ss") and w[:-1] in ALL_WORDS:
        return True
    if w.endswith("ed") and (w[:-2] in ALL_WORDS or w[:-1] in ALL_WORDS):
        return True
    return False


def main():
    profanity.load_censor_words()
    blocklist = set()
    if BLOCKLIST_FILE.exists():
        blocklist = {
            w.strip().lower()
            for w in BLOCKLIST_FILE.read_text().splitlines() if w.strip()
        }

    step1 = sorted(VALID_GUESSES)
    step2 = [w for w in step1 if zipf_frequency(w, "en") >= MIN_ZIPF]
    step3 = [w for w in step2 if not is_inflection(w)]
    step4 = [
        w for w in step3
        if not profanity.contains_profanity(w) and w not in blocklist
    ]

    header = [
        "# Curated answer pool for Wordle for Everyone. Built by curate_answers.py",
        f"# Five letter words in english.py: {len(step1)}",
        f"# After common word filter (Zipf >= {MIN_ZIPF}): {len(step2)}",
        f"# After removing plurals and past tense: {len(step3)}",
        f"# After removing offensive and blocklisted words: {len(step4)}",
    ]
    ANSWER_FILE.write_text("\n".join(header + step4) + "\n", encoding="utf-8")

    print("\n".join(h.lstrip("# ") for h in header))
    print(f"\nSaved to {ANSWER_FILE}")
    import random
    print("\nRandom sample:", ", ".join(random.sample(step4, min(30, len(step4)))))


if __name__ == "__main__":
    main()