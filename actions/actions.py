"""
Rasa custom actions for Wordle for Everyone.
Each action loads the game from the game_state slot, calls the
engine in wordle_engine.py, replies, and saves the game back.

action_handle_free_text is a safety net: anything the LLM does not
understand comes here, and we look for a guess or a command ourselves.
"""
import os
import re
import sys
from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wordle_engine as wd  # noqa: E402

HELP_TEXT = (
    "I didn't catch a guess there. You can type a five letter word like "
    "CRANE, spell it out like C R A N E, or say hint, read my guesses, "
    "how to play, or new game."
)

# Words that look like guesses but are really requests
COMMAND_WORDS = {"rules", "hints", "clues"}

ROUTES = [
    ("hint", r"\bhints?\b|\bclues?\b|\bstuck\b"),
    ("give_up", r"give up|\bi quit\b|show me the (word|answer)|what was the (word|answer)|\breveal\b"),
    ("new_game", r"new game|play again|another (one|game|word)|start over|\brestart\b"),
    ("how_to_play", r"how (do i|to) play|\brules\b|\bhelp\b|instructions|what do the"),
    ("read_board", r"\bread\b|\brepeat\b|my guesses|what have i|so far|the board"),
    ("count", r"how many|words left|words remain"),
]


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def load_game(tracker: Tracker) -> Dict[Text, Any]:
    state = tracker.get_slot("game_state")
    if isinstance(state, dict) and state.get("answer"):
        return state
    return wd.new_game()


def board_payload(state: Dict[Text, Any], message: Text) -> Dict[Text, Any]:
    """Data for the web page. The answer is only included once the game ends."""
    public = {k: v for k, v in state.items() if k != "answer"}
    if state["status"] != wd.PLAYING:
        public["answer"] = state["answer"]
    public["letter_status"] = wd.letter_status(state)
    public["guesses_left"] = wd.guesses_left(state)
    public["message"] = message
    return {"wordle": public}


def reply(dispatcher: CollectingDispatcher, state: Dict[Text, Any], message: Text) -> None:
    dispatcher.utter_message(text=message, json_message=board_payload(state, message))


def route(text: Text):
    t = text.lower()
    for name, pattern in ROUTES:
        if re.search(pattern, t):
            return name
    return None


# ---------------------------------------------------------------
# Shared game moves (used by the normal actions and the safety net)
# ---------------------------------------------------------------
def do_new_game(dispatcher, tracker):
    state = wd.new_game()
    reply(dispatcher, state, (
        f"New game! I'm thinking of a five letter word. You have "
        f"{state['max_guesses']} guesses. Type or say your first guess "
        "whenever you're ready."
    ))
    return [SlotSet("game_state", state)]


def do_guess(dispatcher, tracker, raw_guess):
    state = load_game(tracker)
    prefix = ""
    if state["status"] != wd.PLAYING:
        state = wd.new_game()
        prefix = "Starting a new game for you. "
    state, message, _ = wd.submit_guess(state, raw_guess)
    reply(dispatcher, state, prefix + message)
    return [SlotSet("game_state", state), SlotSet("guess", None)]


def do_hint(dispatcher, tracker):
    state, message = wd.get_hint(load_game(tracker))
    reply(dispatcher, state, message)
    return [SlotSet("game_state", state)]


def do_give_up(dispatcher, tracker):
    state = load_game(tracker)
    if state["status"] != wd.PLAYING:
        reply(dispatcher, state, "This game is already over. Say new game to play again.")
        return []
    state, message = wd.give_up(state)
    reply(dispatcher, state, message)
    return [SlotSet("game_state", state)]


def do_read_board(dispatcher, tracker):
    state = load_game(tracker)
    reply(dispatcher, state, wd.board_summary(state))
    return [SlotSet("game_state", state)]


def do_count(dispatcher, tracker):
    state = load_game(tracker)
    if not state["guesses"]:
        message = "Make a guess first, and then I can tell you how many words still fit."
    else:
        n = len(wd.remaining_candidates(state))
        if n == 1:
            message = "Only one common word still fits your clues. You're very close!"
        elif n == 0:
            message = "Hmm, no common words in my list fit exactly. Try any word that matches your clues."
        else:
            message = f"About {n} common words still fit your clues."
    reply(dispatcher, state, message)
    return [SlotSet("game_state", state)]


# ---------------------------------------------------------------
# Rasa actions
# ---------------------------------------------------------------
class ActionNewGame(Action):
    def name(self) -> Text:
        return "action_new_game"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        return do_new_game(dispatcher, tracker)


class ActionSubmitGuess(Action):
    def name(self) -> Text:
        return "action_submit_guess"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        latest = tracker.latest_message.get("text") or ""
        raw = tracker.get_slot("guess") or wd.extract_guess(latest) or latest
        return do_guess(dispatcher, tracker, raw)


class ActionGetHint(Action):
    def name(self) -> Text:
        return "action_get_hint"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        return do_hint(dispatcher, tracker)


class ActionExplainLetter(Action):
    def name(self) -> Text:
        return "action_explain_letter"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        state = load_game(tracker)
        try:
            g = int(float(tracker.get_slot("guess_number")))
            p = int(float(tracker.get_slot("letter_position")))
            message = wd.explain_letter(state, g, p)
        except (TypeError, ValueError):
            message = "Sorry, I didn't catch which letter. Try saying something like explain letter 2 of guess 1."
        reply(dispatcher, state, message)
        return [SlotSet("guess_number", None), SlotSet("letter_position", None)]


class ActionGiveUp(Action):
    def name(self) -> Text:
        return "action_give_up"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        return do_give_up(dispatcher, tracker)


class ActionReadBoard(Action):
    def name(self) -> Text:
        return "action_read_board"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        return do_read_board(dispatcher, tracker)


class ActionCountCandidates(Action):
    def name(self) -> Text:
        return "action_count_candidates"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        return do_count(dispatcher, tracker)


class ActionHandleFreeText(Action):
    """Safety net for anything the LLM did not understand."""

    def name(self) -> Text:
        return "action_handle_free_text"

    def run(self, dispatcher, tracker, domain) -> List[Dict[Text, Any]]:
        text = tracker.latest_message.get("text") or ""
        words = re.findall(r"[a-z]+", text.lower())

        # A single five letter word is almost always a guess
        if len(words) == 1 and len(words[0]) == wd.WORD_LENGTH and words[0] not in COMMAND_WORDS:
            return do_guess(dispatcher, tracker, words[0])

        r = route(text)
        if r == "hint":
            return do_hint(dispatcher, tracker)
        if r == "give_up":
            return do_give_up(dispatcher, tracker)
        if r == "new_game":
            return do_new_game(dispatcher, tracker)
        if r == "how_to_play":
            dispatcher.utter_message(response="utter_how_to_play")
            return []
        if r == "read_board":
            return do_read_board(dispatcher, tracker)
        if r == "count":
            return do_count(dispatcher, tracker)

        raw = wd.extract_guess(text)
        if raw is None:
            reply(dispatcher, load_game(tracker), HELP_TEXT)
            return []
        return do_guess(dispatcher, tracker, raw)