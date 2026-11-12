"""Local web server for Wordle for Everyone.

Serves the browser game and runs its game actions with the local Wordle engine.
No Rasa server or hosted language model is required.
"""
import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from actions import wordle_engine as wd

PROJECT_DIR = Path(__file__).resolve().parent
GAMES: Dict[str, Dict[str, Any]] = {}


def _load_dotenv() -> None:
    """For local runs: read KEY=value lines from .env without overriding real
    environment variables. On a host, set the variables in its dashboard."""
    env_file = PROJECT_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()

# ---------- Voice: speech to text with Deepgram, key kept on the server ----------
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen?model=nova-3&language=en-US"
MAX_AUDIO_BYTES = 3_000_000          # about a minute of compressed audio
VOICE_LIMIT_PER_MINUTE = 20          # per visitor, so the key can't be abused
_voice_hits: Dict[str, List[float]] = {}
_voice_lock = threading.Lock()


def voice_allowed(client: str) -> bool:
    now = time.time()
    with _voice_lock:
        recent = [t for t in _voice_hits.get(client, []) if now - t < 60]
        if len(recent) >= VOICE_LIMIT_PER_MINUTE:
            _voice_hits[client] = recent
            return False
        recent.append(now)
        _voice_hits[client] = recent
        if len(_voice_hits) > 5000:   # forget old visitors
            for k in [k for k, v in _voice_hits.items() if now - v[-1] > 60]:
                del _voice_hits[k]
        return True


def transcribe(audio: bytes, content_type: str) -> str:
    """Send recorded audio to Deepgram and return what it heard."""
    request = urllib.request.Request(
        DEEPGRAM_URL,
        data=audio,
        method="POST",
        headers={
            "Authorization": "Token " + os.environ["DEEPGRAM_API_KEY"],
            "Content-Type": content_type or "application/octet-stream",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    alternatives = result["results"]["channels"][0]["alternatives"]
    return alternatives[0]["transcript"].strip() if alternatives else ""

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


def pick_guess(payload: Dict[str, Any]) -> str:
    """Choose the word to score.

    Voice input sends several things the browser thinks it heard
    ("guess_options"), often as sentences like "my guess is crane." Use the
    first one that contains a real five letter word; otherwise fall back to
    the first thing heard so the player gets a helpful message about it.
    """
    options = payload.get("guess_options")
    if not isinstance(options, list) or not options:
        options = [payload.get("guess", "")]
    options = [str(o) for o in options[:10] if isinstance(o, str)] or [""]
    for heard in options:
        word = wd.extract_guess(heard) or heard
        if wd.check_guess(word)[0]:
            return word
    return wd.extract_guess(options[0]) or options[0]


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
            state, message, _ = wd.submit_guess(state, pick_guess(payload))
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
        path = urlparse(self.path).path
        if path == "/api/transcribe":
            self._transcribe()
            return
        if path != "/api/game":
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

    def _transcribe(self) -> None:
        if not os.environ.get("DEEPGRAM_API_KEY"):
            # The page then falls back to the browser's own speech recognition
            self._send_json(503, {"error": "Voice service is not set up."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_AUDIO_BYTES:
            self._send_json(400, {"error": "The recording was empty or too long."})
            return
        forwarded = self.headers.get("X-Forwarded-For", "")
        client = forwarded.split(",")[0].strip() or self.client_address[0]
        if not voice_allowed(client):
            self.rfile.read(length)
            self._send_json(429, {"error": "Too many voice guesses in a minute. Please wait a moment."})
            return
        audio = self.rfile.read(length)
        try:
            text = transcribe(audio, self.headers.get("Content-Type", ""))
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as err:
            self.log_error("Deepgram request failed: %s", err)
            self._send_json(502, {"error": "The voice service did not answer."})
            return
        self._send_json(200, {"transcript": text})

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
