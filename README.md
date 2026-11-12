# Wordle for Everyone

## Run locally

The browser game uses the included Python word list and game engine. It does
not need Docker, Rasa, or a hosted language model. Optional browser voice
recognition may require an internet connection; typing works locally.

1. Open a terminal in this project folder.
2. Run `python3 server.py`.
3. Open the address printed in the terminal (by default
   [http://localhost:8001](http://localhost:8001)).
4. Leave the terminal open while you play. Press `Ctrl+C` there to stop the
   game server.

If port 8001 is already in use, start it on another port, for example:
`python3 server.py --port 8002`.
