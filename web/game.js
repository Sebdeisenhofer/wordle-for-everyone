// The local app server runs the game engine directly; Rasa is optional.
const GAME_API = "/api/game";

const SYM = { correct: "✓", present: "↔", absent: "✕" };
const LABEL = { correct: "right spot", present: "in the word, wrong spot", absent: "not in the word" };

const COMMANDS = {
  "hint": "hint",
  "read my guesses": "read_board",
  "how many words are left": "count_candidates",
  "how to play": "how_to_play",
  "I give up": "give_up",
  "new game": "new_game"
};

// Saved settings (wrapped in try so the page works even if storage is blocked)
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
};
const prefs = {
  palette: store.get("wfe_palette", "classic"),
  size: store.get("wfe_size", "20"),
  rate: store.get("wfe_rate", "0.9"),
  readAloud: store.get("wfe_read_aloud", "off") === "on"
};

let senderId = store.get("wfe_sender", null);
if (!senderId) {
  senderId = "player-" + Math.random().toString(36).slice(2, 10);
  store.set("wfe_sender", senderId);
}

let game = null;
let busy = false;
const $ = (id) => document.getElementById(id);
const input = $("guess");

// ---------- Settings ----------
function applyPrefs() {
  document.body.dataset.palette = prefs.palette;
  document.documentElement.style.fontSize = prefs.size + "px";
  $("palette").value = prefs.palette;
  $("size").value = prefs.size;
  $("rate").value = prefs.rate;
  const btn = $("read-aloud");
  btn.setAttribute("aria-pressed", prefs.readAloud ? "true" : "false");
  btn.textContent = prefs.readAloud ? "🔊 Read aloud: On" : "🔊 Read aloud: Off";
}
$("palette").addEventListener("change", (e) => { prefs.palette = e.target.value; store.set("wfe_palette", prefs.palette); applyPrefs(); });
$("size").addEventListener("change", (e) => { prefs.size = e.target.value; store.set("wfe_size", prefs.size); applyPrefs(); });
$("rate").addEventListener("change", (e) => { prefs.rate = e.target.value; store.set("wfe_rate", prefs.rate); applyPrefs(); });
$("read-aloud").addEventListener("click", () => {
  prefs.readAloud = !prefs.readAloud;
  store.set("wfe_read_aloud", prefs.readAloud ? "on" : "off");
  applyPrefs();
  if (prefs.readAloud) speak("Read aloud is on.");
  else if ("speechSynthesis" in window) speechSynthesis.cancel();
});

// ---------- Speaking and messages ----------
function speak(text) {
  if (!prefs.readAloud || !("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = parseFloat(prefs.rate);
  u.lang = "en-US";
  speechSynthesis.speak(u);
}
function addLog(who, text) {
  const li = document.createElement("li");
  li.textContent = who + ": " + text;
  $("log").appendChild(li);
}
function say(text) {
  $("message").textContent = text;
  addLog("Game", text);
  speak(text);
}

// ---------- Talking to the local game server ----------
// options.display is what to show in the conversation history.
async function send(action, options = {}) {
  if (busy) {
    $("message").textContent = "Still working on your last move. One moment please.";
    return;
  }
  busy = true;
  if (options.show !== false) addLog("You", options.display || text);
  $("message").textContent = "One moment...";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(GAME_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sender: senderId, action, ...options.data }),
      signal: controller.signal
    });
    if (!res.ok) throw new Error("Server said " + res.status);
    const messages = await res.json();
    const wasPlaying = game && game.status === "playing";
    const texts = [];
    for (const m of messages) {
      if (m.custom && m.custom.wordle) game = m.custom.wordle;
      if (m.text) texts.push(m.text);
    }
    renderBoard();
    renderKeyboard();
    say(texts.length ? texts.join(" ") : "Sorry, I didn't get an answer. Please try again.");
    if (wasPlaying && game && game.status !== "playing") $("new-game").focus();
  } catch (err) {
    say("I couldn't reach the local game. Please start it with python3 server.py, then try again.");
  } finally {
    clearTimeout(timer);
    busy = false;
  }
}
function sendCommand(phrase) {
  send(COMMANDS[phrase] || phrase, { display: phrase });
}
function sendGuess(word) {
  send("guess", { display: word, data: { guess: word } });
}

// ---------- Board ----------
function typedLetters() {
  return input.value.toLowerCase().replace(/[^a-z]/g, "").slice(0, 5);
}

function renderBoard() {
  const board = $("board");
  board.innerHTML = "";
  const max = game ? game.max_guesses : 6;
  const guesses = game ? game.guesses : [];
  const results = game ? game.results : [];
  const playing = !game || game.status === "playing";

  for (let r = 0; r < max; r++) {
    const row = document.createElement("div");
    row.className = "row";
    row.setAttribute("role", "group");
    const word = guesses[r];

    if (word) {
      row.setAttribute("aria-label", "Guess " + (r + 1) + ": " + word.toUpperCase());
      for (let i = 0; i < 5; i++) {
        const st = results[r][i];
        const b = document.createElement("button");
        b.type = "button";
        b.className = "tile " + st;
        b.innerHTML = word[i].toUpperCase() + '<span class="sym" aria-hidden="true">' + SYM[st] + "</span>";
        b.setAttribute("aria-label",
          "Guess " + (r + 1) + ", letter " + (i + 1) + ": " + word[i].toUpperCase() +
          ", " + LABEL[st] + ". Select to hear why.");
        b.addEventListener("click", () => explain(r, i));
        row.appendChild(b);
      }
    } else {
      const isTypingRow = playing && r === guesses.length;
      const letters = isTypingRow ? typedLetters() : "";
      row.setAttribute("aria-hidden", "true");
      for (let i = 0; i < 5; i++) {
        const t = document.createElement("div");
        t.className = "tile" + (letters[i] ? " typing" : "");
        t.textContent = letters[i] ? letters[i].toUpperCase() : "";
        row.appendChild(t);
      }
    }
    board.appendChild(row);
  }

  if (game) {
    const left = game.guesses_left;
    const hintsLeft = 3 - (game.hints_used || 0);
    $("status").textContent = game.status === "playing"
      ? "Guesses left: " + left + ".  Hints left: " + hintsLeft + "."
      : "Game over. Select New game to play again.";
  }
}

// "Why this result?" explainer, worked out from the scored guess
function explain(r, i) {
  const word = game.guesses[r], res = game.results[r];
  const L = word[i].toUpperCase(), st = res[i];
  let t = "In guess " + (r + 1) + ", letter " + (i + 1) + " is " + L + ". ";
  if (st === "correct") {
    t += "It is marked right spot because the word has " + L + " in exactly that position.";
  } else if (st === "present") {
    t += "It is marked wrong spot because the word has " + L + ", but somewhere else. Try moving it.";
  } else {
    const otherCounted = [...word].some((c, j) => j !== i && c === word[i] && res[j] !== "absent");
    t += otherCounted
      ? "It is marked not in the word because the word has fewer " + L + "s than your guess. Your other " + L + " already counted for it."
      : "It is marked not in the word because the word has no " + L + ". You can rule it out.";
  }
  say(t);
}

// ---------- On screen keyboard ----------
function renderKeyboard() {
  const kb = $("keyboard");
  kb.innerHTML = "";
  const status = (game && game.letter_status) || {};
  const rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];
  rows.forEach((letters, idx) => {
    const row = document.createElement("div");
    row.className = "krow";
    if (idx === 2) row.appendChild(makeKey("Enter", "Submit guess", submitGuess, true));
    for (const ch of letters) {
      const st = status[ch.toLowerCase()];
      const label = "Letter " + ch + (st ? ", " + LABEL[st] : "");
      const key = makeKey(ch, label, () => addLetter(ch), false);
      if (st) {
        key.classList.add(st);
        key.insertAdjacentHTML("beforeend", '<span class="sym" aria-hidden="true">' + SYM[st] + "</span>");
      }
      row.appendChild(key);
    }
    if (idx === 2) row.appendChild(makeKey("Delete", "Delete last letter", deleteLetter, true));
    kb.appendChild(row);
  });
}
function makeKey(text, label, onClick, wide) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "key" + (wide ? " wide" : "");
  b.textContent = text;
  b.setAttribute("aria-label", label);
  b.addEventListener("click", onClick);
  return b;
}
function addLetter(ch) {
  if (typedLetters().length < 5) input.value = typedLetters() + ch.toLowerCase();
  renderBoard();
}
function deleteLetter() {
  input.value = typedLetters().slice(0, -1);
  renderBoard();
}

// ---------- Guess entry ----------
function submitGuess() {
  const value = input.value.trim();
  if (!value) {
    say("Please type a five letter word first.");
    input.focus();
    return;
  }
  if (busy) {
    $("message").textContent = "Still working on your last move. One moment please.";
    return;
  }
  input.value = "";
  renderBoard();
  sendGuess(value);
}
$("entry-form").addEventListener("submit", (e) => { e.preventDefault(); submitGuess(); });
// Keep the box in step with the board: letters only, at most 5, so Backspace
// always removes a letter you can see.
input.addEventListener("input", () => {
  const letters = typedLetters();
  if (input.value !== letters) input.value = letters;
  renderBoard();
});

// ---------- Help buttons ----------
document.querySelectorAll("[data-say]").forEach((b) =>
  b.addEventListener("click", () => sendCommand(b.dataset.say)));
$("new-game").addEventListener("click", () => sendCommand("new game"));
$("give-up").addEventListener("click", () => {
  if (confirm("Reveal the word and end this game?")) sendCommand("I give up");
});

// ---------- Voice input (speech recognition is used for guesses) ----------
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const NO_VOICE =
  "Voice input isn't available in this browser. On a phone, tap the guess box and use " +
  "the microphone button on your keyboard. On a computer, use Google Chrome, Microsoft Edge or Safari.";
// Say exactly what went wrong, so the player knows how to fix it
const MIC_ERRORS = {
  "not-allowed": "The microphone is blocked for this page. Select the icon next to the web address, " +
    "allow the microphone, then select Say a guess again. You can also type your guess.",
  "service-not-allowed": NO_VOICE,
  "audio-capture": "I couldn't find a microphone on this device. Please type your guess instead.",
  "network": "Voice input needs an internet connection. Please check the connection, or type your guess.",
  "no-speech": "I didn't hear anything. Select Say a guess, then say your word clearly."
};
let listening = null;      // browser speech recognition in progress
let recording = null;      // { stop() } while recording for the voice service
const micBtn = $("mic");
const MIC_LABEL = "🎤 Say a guess";

function guessFromSpeech(heard) {
  heard = heard.map((t) => t.trim()).filter(Boolean);
  if (!heard.length) {
    say("I didn't catch a word. Select Say a guess, then say your word clearly.");
    return;
  }
  send("guess", { display: "🎤 " + heard[0], data: { guess: heard[0], guess_options: heard } });
}

// Main voice path: record with the microphone, then the game server turns the
// recording into text. Works the same on phones and computers.
async function recordGuess() {
  const canRecord = navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder;
  if (!canRecord) return browserSpeech();

  // Create audio context during the click so phones allow it
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const ctx = AudioCtx ? new AudioCtx() : null;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    if (ctx) ctx.close();
    if (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) say(MIC_ERRORS["not-allowed"]);
    else if (err && err.name === "NotFoundError") say(MIC_ERRORS["audio-capture"]);
    else say("The microphone could not start. Please try again, or type your guess.");
    return;
  }

  const type = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg;codecs=opus"]
    .find((t) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t));
  const recorder = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
  const chunks = [];
  recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };

  // Stop by itself after the player stops talking (or after 8 seconds)
  let heardVoice = false, quietSince = 0, timer = null;
  const started = Date.now();
  let analyser = null, levels = null;
  if (ctx) {
    try {
      if (ctx.state === "suspended") ctx.resume();
      analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      levels = new Uint8Array(analyser.fftSize);
      ctx.createMediaStreamSource(stream).connect(analyser);
    } catch (e) { analyser = null; }
  }
  const finish = () => { if (recorder.state !== "inactive") recorder.stop(); };
  timer = setInterval(() => {
    const now = Date.now();
    // Only trust the level meter while audio is actually running; otherwise
    // record for a fixed time (or until the button is pressed again).
    const metering = analyser && ctx.state === "running";
    if (!metering && now - started > 6000) finish();
    if (metering) {
      analyser.getByteTimeDomainData(levels);
      let peak = 0;
      for (const v of levels) peak = Math.max(peak, Math.abs(v - 128));
      if (peak > 12) {
        heardVoice = true; quietSince = 0;
        micBtn.textContent = "🎤 Hearing you... (select to stop)";
      } else if (heardVoice) {
        quietSince = quietSince || now;
        if (now - quietSince > 1300) finish();
      }
    }
    if (now - started > 8000) finish();
  }, 100);

  recording = { stop: finish };
  micBtn.textContent = "🎤 Listening... (select to stop)";
  $("message").textContent = "Listening. Say a word, or spell it out one letter at a time.";

  recorder.onstop = async () => {
    clearInterval(timer);
    stream.getTracks().forEach((t) => t.stop());
    if (ctx) ctx.close();
    recording = null;
    micBtn.textContent = MIC_LABEL;
    const audio = new Blob(chunks, { type: recorder.mimeType || type || "audio/webm" });
    $("message").textContent = "One moment, working out your word...";
    try {
      const res = await fetch("/api/transcribe", {
        method: "POST",
        headers: { "Content-Type": audio.type || "application/octet-stream" },
        body: audio
      });
      if (res.status === 503) return browserSpeech();   // voice service not set up
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { say((data.error || "The voice service did not answer.") + " You can type your guess instead."); return; }
      if (!data.transcript) {
        say("I didn't hear a word. Check that your microphone is on, select Say a guess, and speak clearly.");
        return;
      }
      guessFromSpeech([data.transcript]);
    } catch (err) {
      say(MIC_ERRORS["network"]);
    }
  };
  recorder.start();
}

micBtn.addEventListener("click", () => {
  if (recording) { recording.stop(); return; }   // a second press stops
  if (listening) { listening.stop(); return; }
  recordGuess();
});

// Fallback: the browser's own speech recognition
function browserSpeech() {
  if (!Recognition) {
    say(NO_VOICE);
    input.focus();
    return;
  }
  const rec = new Recognition();
  rec.lang = "en-US";
  rec.interimResults = false;
  rec.maxAlternatives = 5;
  rec.onresult = (e) => {
    // Send everything the browser thinks it heard; the game picks the real word
    const heard = Array.from(e.results[0], (alt) => alt.transcript.trim()).filter(Boolean);
    if (!heard.length) { say(MIC_ERRORS["no-speech"]); return; }
    send("guess", { display: "🎤 " + heard[0], data: { guess: heard[0], guess_options: heard } });
  };
  rec.onerror = (e) => {
    if (e.error === "aborted") return;
    say(MIC_ERRORS[e.error] || "Voice input stopped. Please select Say a guess to try again, or type your guess.");
  };
  rec.onend = () => {
    listening = null;
    $("mic").textContent = "🎤 Say a guess";
  };
  try {
    rec.start();
    listening = rec;
    $("mic").textContent = "🎤 Listening... (select to stop)";
    $("message").textContent = "Listening. Say a word, or spell it out one letter at a time.";
  } catch (err) {
    say("Voice input could not start. Please try again, or type your guess.");
  }
}

// ---------- Physical keyboard anywhere on the page ----------
document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const t = e.target;
  if (t === input || t.tagName === "SELECT" || t.tagName === "SUMMARY") return;
  const onGameArea = t === document.body || t.classList.contains("key") || t.classList.contains("tile");

  if (/^[a-zA-Z]$/.test(e.key)) {
    e.preventDefault();
    addLetter(e.key.toUpperCase());
  } else if (e.key === "Backspace") {
    e.preventDefault();
    deleteLetter();
  } else if (e.key === "Enter" && (onGameArea || typedLetters().length > 0)) {
    // If letters are typed, Enter always submits them, wherever the focus is
    e.preventDefault();
    submitGuess();
  }
});

// ---------- Start ----------
applyPrefs();
renderBoard();
renderKeyboard();
if (store.get("wfe_started", "")) {
  sendCommand("read my guesses");
} else {
  store.set("wfe_started", "1");
  sendCommand("new game");
}

// After starting a new game, put the cursor back in the guess box
$("new-game").addEventListener("click", () => input.focus());