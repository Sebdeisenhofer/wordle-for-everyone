# Wordle for Everyone

An accessible word-guessing game designed with older adults in mind: large
text, clear colours with symbols, no timer, and help whenever you want it.

## Play online

**https://wordle-for-everyone.onrender.com**

Open the link in any web browser on a computer, tablet or phone. Nothing to
install and no account needed.

> The site is on a free hosting plan and goes to sleep when nobody has used it
> for a while. If the page takes up to a minute to load the first time, that
> is normal. After that it is fast.

## How to play

1. Find the hidden five letter word. You have **6 guesses** and there is
   **no timer**.
2. Type a word and press **Enter**. You can use your own keyboard, click the
   letters on the screen, or select **🎤 Say a guess** and speak it.
   **Backspace** (or the on-screen **Delete** key) removes a letter.
3. After each guess, every letter is marked:
   - **✓ Right spot**: the letter is in the word, in that exact place.
   - **↔ Wrong spot**: the letter is in the word, but somewhere else.
   - **✕ Not in the word**: you can rule that letter out.
4. Words that aren't real, or aren't five letters, **never use up a guess**.

## Help and settings

- **Hint**: gives a clue, a little stronger each time (up to 3 per game).
- **Read my guesses**: describes your board so far.
- **Words left**: tells you how many common words still fit your clues.
- **How to play**: explains the rules again.
- **🔊 Read aloud**: reads every message out loud.
- **Select any scored letter** on the board to hear why it got that result.
- **Display and sound settings**: choose larger text, a colourblind-friendly
  or high-contrast style, and a slower reading speed. Your choices are
  remembered next time.

## Run locally

The game uses the included Python word list and game engine. It does not need
Docker, Rasa, or a hosted language model. Optional browser voice recognition
may require an internet connection; typing works locally.

1. Open a terminal in this project folder.
2. Run `python3 server.py`.
3. Open the address printed in the terminal (by default
   [http://localhost:8001](http://localhost:8001)).
4. Leave the terminal open while you play. Press `Ctrl+C` there to stop the
   game server.

If port 8001 is already in use, start it on another port, for example:
`python3 server.py --port 8002`.

## Deploying

The included `Dockerfile` runs `server.py` and listens on the `PORT` the host
provides. The live site is a Render web service built from this repository;
every push to `main` redeploys it automatically. No environment variables or
API keys are needed.
