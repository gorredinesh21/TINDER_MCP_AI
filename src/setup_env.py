"""
One-click local-AI setup for the dashboard.

Automates the happy path — Python deps -> Ollama install -> server up -> pull the vision
model -> verify — and STREAMS progress as newline-delimited JSON events. Known failures are
classified into specific, actionable hints (we can't auto-fix network blocks, missing admin,
low disk/RAM, etc., but we can tell the user exactly what happened and what to do).

Events (one JSON object per line):
  {"type":"step","name":..,"status":"running|ok|warn|error","msg":..,"hint":..}
  {"type":"log","line":..}
  {"type":"done","ok":bool}

Commands are hardcoded (no user input reaches a shell). Intended to run locally, on the
machine the user already launched `app.py` on.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Iterator

# Strip ANSI/terminal control sequences (Ollama's progress bar emits spinner + cursor codes
# that look like garbage in a web console).
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[=>]|[\r\x08]")

OLLAMA_API = "http://127.0.0.1:11434"
ROOT = Path(__file__).resolve().parent.parent


# ---------- event helpers ----------
def _ev(**kw) -> str:
    return json.dumps(kw) + "\n"

def step(name, status, msg="", hint="") -> str:
    return _ev(type="step", name=name, status=status, msg=msg, hint=hint)

def log(line) -> str:
    return _ev(type="log", line=line.rstrip())

def done(ok) -> str:
    return _ev(type="done", ok=ok)


# ---------- platform / discovery ----------
def detect_os() -> str:
    s = platform.system().lower()
    return "windows" if "windows" in s else "macos" if "darwin" in s else "linux" if "linux" in s else s

def which_ollama() -> str | None:
    p = shutil.which("ollama")
    if p:
        return p
    # common per-OS install locations (PATH may not be refreshed in this process yet)
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path("C:/Program Files/Ollama/ollama.exe"),
        Path("/usr/local/bin/ollama"),
        Path("/opt/homebrew/bin/ollama"),
        Path("/usr/bin/ollama"),
        Path.home() / ".ollama" / "bin" / "ollama",
    ]
    for c in candidates:
        if c and c.exists():
            return str(c)
    return None

def server_up() -> bool:
    try:
        import requests
        return requests.get(f"{OLLAMA_API}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


# ---------- command running ----------
def _popen(cmd, shell=False):
    return subprocess.Popen(
        cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
    )

def stream_cmd(cmd, shell=False) -> Iterator[tuple[str, int | None]]:
    """Yield (line, None) for each output line, then ('', returncode) at the end."""
    try:
        proc = _popen(cmd, shell=shell)
    except FileNotFoundError as e:
        yield (f"command not found: {e}", 127)
        return
    for line in proc.stdout:  # type: ignore
        clean = _ANSI.sub("", line).strip()
        if clean:
            yield (clean, None)
    proc.wait()
    yield ("", proc.returncode)

def run(cmd, shell=False, timeout=900) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError as e:
        return 127, f"command not found: {e}"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


# ---------- the if/else "knowledge": classify a failure into a hint ----------
def classify(output: str) -> str:
    o = (output or "").lower()
    if any(k in o for k in ["proxy", "ssl", "certificate", "timed out", "timeout",
                            "could not resolve", "connection reset", "network is unreachable",
                            "failed to connect", "getaddrinfo"]):
        return ("Your network is blocking the download (corporate firewall/proxy is the usual cause). "
                "Try a personal/home network — or skip local AI and use the Hugging Face backend "
                "(set LLM_BACKEND=hf and put your key in .env).")
    if any(k in o for k in ["no space left", "not enough space", "disk full"]):
        return "Out of disk space. Free a few GB (moondream ≈ 830MB, llava ≈ 4.7GB) and retry."
    if any(k in o for k in ["permission denied", "access is denied", "requires administrator",
                            "must be run as root", "operation not permitted"]):
        return ("Needs permission to install. On macOS/Linux run the Ollama install once in a terminal "
                "(see ollama.com/download); on Windows allow the installer if your antivirus prompts.")
    if any(k in o for k in ["command not found", "not recognized", "no such file"]):
        return ("Ollama installed but isn't on PATH in this process yet. Fully quit and relaunch "
                "`python app.py` (or restart the machine), then click Set up again.")
    if "connection refused" in o or "11434" in o:
        return "The Ollama server isn't running. It should auto-start; if not, run `ollama serve` in a terminal."
    if "manifest" in o and ("not found" in o or "unknown" in o):
        return "That model name wasn't found. Use 'moondream' (small) or 'llava' (larger)."
    if any(k in o for k in ["out of memory", "cuda", "vram", "killed"]):
        return "Model too heavy for this machine's RAM/VRAM. Use the smaller 'moondream' model."
    return ""


# ---------- install Ollama (per OS) ----------
def _download(url: str, dest: Path) -> Iterator[str]:
    yield log(f"Downloading {url} …")
    with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length", 0))
        got = 0
        last = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            mb = got / 1e6
            if mb - last >= 50:  # log every ~50 MB
                last = mb
                pct = f" ({got*100//total}%)" if total else ""
                yield log(f"  …{mb:.0f} MB{pct}")
    yield log(f"  done ({dest.stat().st_size/1e6:.0f} MB)")

def install_ollama(osname: str) -> Iterator[str]:
    if osname == "windows":
        try:
            exe = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
            yield from _download("https://ollama.com/download/OllamaSetup.exe", exe)
            yield log("Running silent installer (per-user, no admin)…")
            rc, out = run([str(exe), "/VERYSILENT", "/NORESTART", "/SP-"], timeout=600)
            if rc != 0:
                yield step("ollama-install", "error", msg=out[-500:], hint=classify(out) or
                           "Installer returned an error; try running OllamaSetup.exe manually.")
            else:
                yield log("Installer finished.")
        except Exception as e:
            yield step("ollama-install", "error", msg=str(e), hint=classify(str(e)) or
                       "Download/install failed; install Ollama from ollama.com/download.")
    elif osname == "linux":
        yield log("Installing via official script: curl -fsSL https://ollama.com/install.sh | sh")
        for line, rc in stream_cmd("curl -fsSL https://ollama.com/install.sh | sh", shell=True):
            if rc is None:
                yield log(line)
            elif rc != 0:
                yield step("ollama-install", "error", hint=classify(line) or
                           "Install script failed; see ollama.com/download.")
    elif osname == "macos":
        if shutil.which("brew"):
            yield log("Installing via Homebrew: brew install ollama")
            for line, rc in stream_cmd(["brew", "install", "ollama"]):
                if rc is None:
                    yield log(line)
                elif rc != 0:
                    yield step("ollama-install", "error", hint=classify(line) or
                               "brew install failed; download Ollama from ollama.com/download.")
        else:
            yield step("ollama-install", "warn", msg="Homebrew not found.",
                       hint="On macOS without Homebrew, download Ollama from ollama.com/download, "
                            "open it once, then click Set up again.")
    else:
        yield step("ollama-install", "error", hint=f"Unsupported OS '{osname}'. See ollama.com/download.")


def start_server(ollama: str) -> None:
    try:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
        subprocess.Popen([ollama, "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **kwargs)
    except Exception:
        pass


# ---------- the orchestration ----------
def setup_steps(model: str | None = None) -> Iterator[str]:
    model = (model or os.getenv("VISION_MODEL") or "moondream").strip()
    osname = detect_os()
    yield step("detect", "ok", msg=f"OS: {osname} · Python {sys.version.split()[0]} · model: {model}")

    # 1) Python deps (idempotent — fast if already satisfied)
    yield step("deps", "running", msg="Ensuring Python libraries…")
    rc, out = run([sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], timeout=600)
    yield step("deps", "ok" if rc == 0 else "warn",
               msg="Libraries ready." if rc == 0 else "pip had issues (app may still work).",
               hint="" if rc == 0 else classify(out))

    # 2) Ollama present?
    yield step("ollama", "running", msg="Checking for Ollama…")
    path = which_ollama()
    if path:
        yield step("ollama", "ok", msg=f"Found: {path}")
    else:
        yield step("ollama", "warn", msg="Not installed — installing (this downloads ~1 GB on Windows)…")
        yield from install_ollama(osname)
        path = which_ollama()
        if not path:
            yield step("ollama", "error", msg="Ollama still not found after install.",
                       hint="Quit and relaunch `python app.py` so PATH refreshes, then click Set up again. "
                            "If it keeps failing, install from ollama.com/download.")
            yield done(False)
            return
        yield step("ollama", "ok", msg=f"Installed: {path}")

    # 3) server running?
    yield step("server", "running", msg="Starting the Ollama server…")
    if not server_up():
        start_server(path)
        for _ in range(15):
            if server_up():
                break
            time.sleep(1)
    yield (step("server", "ok", msg="Server is up.") if server_up()
           else step("server", "warn", msg="Couldn't reach the server.",
                     hint="Run `ollama serve` in a terminal, then retry the pull."))

    # 4) pull the model (streams; first time downloads it)
    yield step("pull", "running", msg=f"Pulling '{model}' (first run downloads the model)…")
    tail = ""
    last_pct = -10
    for line, rc in stream_cmd([path, "pull", model]):
        if rc is not None:
            continue
        tail = line
        m = re.search(r"(\d+)%", line)
        if m:  # progress line — only emit every ~5% so the console stays clean
            pct = int(m.group(1))
            if pct - last_pct >= 5 or pct >= 100:
                last_pct = pct
                yield log(line)
        else:  # status lines (manifest, verifying, writing, success)
            yield log(line)
    rc2, listed = run([path, "list"], timeout=30)
    if model.split(":")[0] in listed:
        yield step("pull", "ok", msg=f"'{model}' is installed and ready.")
        yield done(True)
    else:
        yield step("pull", "error", msg="Model not present after pull.", hint=classify(tail) or
                   "Pull didn't complete — check the log above and retry.")
        yield done(False)
