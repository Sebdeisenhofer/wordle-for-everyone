"""Local web server for Wordle for Everyone.

Serves the browser game and runs its game actions with the local Wordle engine.
No Rasa server or hosted language model is required.
"""
import argparse
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from actions import wordle_engine as wd

PROJECT_DIR = Path(__file__).resolve().parent
GAMES: Dict[str, Dict[str, Any]] = {}

HOW_TO_PLAY = (
    "Here's how to play. I'm thinking of a common five letter word, and you "
    "have 6 guesses. After each guess I'll tell you about every letter. Right "
    "spot means the letter is in the word and in the right place. Wrong spot "
    "means the letter is in the word but somewhere else. Not in the word means "
    "you can rule that letter out. Words that aren't real or aren't five "
    "letters never use up a guess, and there's no timer."
)


def _board_payload(state: Dict[str, Any], message: str) -> Dict[str, Any]:
    public = {key: value for key, value in state.items() if key != "answer"}
    if state["status"] != wd.PLAYING:
        public["answer"] = state["answer"]
    public["letter_status"] = wd.letter_status(state)
    public["guesses_left"] = wd.guesses_left(state)
    public["message"] = message
    return public


def play_action(
    sender: str, action: str, payload: Dict[str, Any]
) -> Tuple[int, List[Dict[str, Any]]]:
    state = GAMES.get(sender)
    if action == "new_game":
        state = wd.new_game()
        message = (
            f"New game! I'm thinking of a five letter word. You have "
            f"{state['max_guesses']} guesses. Type or say your first guess "
            "whenever you're ready."
        )
    else:
        if state is None:
            state = wd.new_game()

        if action == "guess":
            if state["status"] != wd.PLAYING:
                state = wd.new_game()
            state, message, _ = wd.submit_guess(state, str(payload.get("guess", "")))
        elif action == "hint":
            state, message = wd.get_hint(state)
        elif action == "give_up":
            if state["status"] != wd.PLAYING:
                message = "This game is already over. Select New game to play again."
            else:
                state, message = wd.give_up(state)
        elif action == "read_board":
            message = wd.board_summary(state)
        elif action == "count_candidates":
            if not state["guesses"]:
                message = "Make a guess first, and then I can tell you how many words still fit."
            else:
                count = len(wd.remaining_candidates(state))
                if count == 1:
                    message = "Only one common word still fits your clues. You're very close!"
                elif count == 0:
                    message = "Hmm, no common words in my list fit exactly. Try any word that matches your clues."
                else:
                    message = f"About {count} common words still fit your clues."
        elif action == "how_to_play":
            message = HOW_TO_PLAY
        else:
            return 400, [{"text": "Unknown game action."}]

    GAMES[sender] = state
    return 200, [{"text": message, "custom": {"wordle": _board_payload(state, message)}}]


class GameHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(PROJECT_DIR / "web"), **kwargs)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/status":
            self._send_json(200, {"status": "ok"})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/game":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "Invalid request length."})
            return
        if length <= 0 or length > 16_384:
            self._send_json(400, {"error": "Request must contain a small JSON body."})
            return

        try:
            request = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "Request body must be valid JSON."})
            return
        if not isinstance(request, dict):
            self._send_json(400, {"error": "Request body must be a JSON object."})
            return

        sender = request.get("sender")
        action = request.get("action")
        if not isinstance(sender, str) or not sender or not isinstance(action, str):
            self._send_json(400, {"error": "A sender and game action are required."})
            return

        status, response = play_action(sender, action, request)
        self._send_json(status, response)

    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Wordle for Everyone locally.")
    # Hosting services (Render, Railway, ...) set PORT and need the server to
    # listen on all addresses. Locally it stays on localhost:8001.
    hosted = "PORT" in os.environ
    parser.add_argument("--host", default="0.0.0.0" if hosted else "127.0.0.1", help="Address to listen on (default: localhost).")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8001)), help="Port to listen on (default: 8001).")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), GameHandler)
    print(f"Wordle for Everyone is ready at http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Wordle for Everyone.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
