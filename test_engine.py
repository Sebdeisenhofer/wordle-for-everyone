"""Quick checks for the game engine. Run with:  python test_engine.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "actions"))
import wordle_engine as wd

C, P, A = wd.CORRECT, wd.PRESENT, wd.ABSENT
failures = 0


def check(name, got, expected):
    global failures
    ok = got == expected
    if not ok:
        failures += 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   got {got}, expected {expected}"))


# Scoring, including repeated letters (G5)
check("all letters correct", wd.score_guess("crane", "crane"), [C] * 5)
check("guess has two Es, answer has one", wd.score_guess("speed", "abide"), [A, A, P, A, P])
check("extra Es after a correct E", wd.score_guess("geese", "those"), [A, A, A, C, C])
check("double L both correct", wd.score_guess("lolly", "hello"), [A, P, C, C, A])

# Validation (G3, G4)
ANS = "crane" if "crane" in wd.VALID_GUESSES else sorted(wd.VALID_GUESSES)[0]
check("too short is rejected", wd.check_guess("cat")[0], None)
check("too long is rejected", wd.check_guess("cranes")[0], None)
check("numbers are rejected", wd.check_guess("cr4ne")[0], None)
check("fake word is rejected", wd.check_guess("qzxvj")[0], None)
check("spelled out letters work", wd.check_guess(" ".join(ANS.upper()))[0], ANS)

# Invalid guesses never cost a guess (G4)
game = wd.new_game(answer=ANS)
after, msg, used = wd.submit_guess(game, "zz")
check("invalid guess not counted", (used, len(after["guesses"])), (False, 0))

# Win, loss, give up (G6)
won, msg, _ = wd.submit_guess(wd.new_game(answer=ANS), ANS)
check("win ends the game", won["status"], wd.WON)

lost = wd.new_game(answer=ANS)
for w in [w for w in sorted(wd.VALID_GUESSES) if w != ANS][:6]:
    lost, msg, _ = wd.submit_guess(lost, w)
check("six wrong guesses ends the game", lost["status"], wd.LOST)
check("loss message reveals the word", ANS.upper() in msg, True)

check("give up reveals the word", ANS.upper() in wd.give_up(wd.new_game(answer=ANS))[1], True)

# Answer pool (G7)
check("answer pool is not tiny", len(wd.ANSWERS) > 100, True)
check("every answer is a valid guess", all(a in wd.VALID_GUESSES for a in wd.ANSWERS), True)

print("\nAll tests passed!" if failures == 0 else f"\n{failures} test(s) failed.")