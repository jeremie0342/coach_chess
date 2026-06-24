"""XAMPP-style launcher for the coach_chess local stack.

A single-window tkinter GUI that shows the status of every service the project
depends on (Postgres, Memurai, Ollama, FastAPI backend, Arq worker, Next.js
web), and lets you start/stop each one with a button.

Run directly:
    pythonw scripts\\launcher.py

Or build a standalone .exe via:
    scripts\\build_launcher.ps1
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from typing import Callable

try:
    import pystray  # type: ignore
    from PIL import Image, ImageDraw  # type: ignore
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# --- Config --------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"

UV_BIN_DIR = r"C:\Users\KPS\.local\bin"
OLLAMA_BIN_DIR = r"C:\Users\KPS\AppData\Local\Programs\Ollama"
NPM_BIN_DIR = r"C:\Program Files\nodejs"

BACKEND_PORT = 8765
WEB_PORT = 3000
POSTGRES_PORT = 5432
MEMURAI_PORT = 6379
OLLAMA_PORT = 11434

POLL_INTERVAL_MS = 1500

SETTINGS_FILE = Path.home() / ".coach_chess_launcher.json"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
STARTUP_SHORTCUT = STARTUP_DIR / "coach_chess_launcher.lnk"


# --- Settings persistence -------------------------------------------------

DEFAULT_SETTINGS = {
    "autostart_windows": False,
    "start_minimized": False,
    "close_to_tray": True,
    "auto_start_all_on_launch": False,
}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return {**DEFAULT_SETTINGS, **data}
        except (OSError, json.JSONDecodeError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(s: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except OSError:
        pass


# --- Windows startup shortcut --------------------------------------------

_LAST_AUTOSTART_ERROR: str = ""


def _create_startup_shortcut() -> bool:
    """Create a .lnk in shell:startup pointing to this launcher.

    Uses pythoncom + win32com if available (most reliable), falling back to a
    temp .ps1 file executed via powershell. Errors are recorded into
    _LAST_AUTOSTART_ERROR so the GUI can surface them.
    """
    global _LAST_AUTOSTART_ERROR
    _LAST_AUTOSTART_ERROR = ""

    if not STARTUP_DIR.exists():
        try:
            STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            _LAST_AUTOSTART_ERROR = f"startup dir missing: {e}"
            return False

    target, args = _resolve_self_command()
    if not target:
        _LAST_AUTOSTART_ERROR = "couldn't resolve launcher path"
        return False

    # Try win32com first (no subprocess, no quoting issues).
    try:
        import win32com.client  # type: ignore
        sh = win32com.client.Dispatch("WScript.Shell")
        sc = sh.CreateShortcut(str(STARTUP_SHORTCUT))
        sc.TargetPath = target
        sc.Arguments = args
        sc.WorkingDirectory = str(PROJECT_ROOT)
        sc.IconLocation = target
        sc.Save()
        return STARTUP_SHORTCUT.exists()
    except ImportError:
        pass
    except Exception as e:
        _LAST_AUTOSTART_ERROR = f"win32com: {e}"
        # Fall through to PowerShell fallback

    # PowerShell fallback: write a script to disk and run it (avoids
    # command-line quoting hell with paths containing spaces or special chars).
    import tempfile
    ps_lines = [
        '$ws = New-Object -ComObject WScript.Shell',
        f'$sc = $ws.CreateShortcut([string]{json.dumps(str(STARTUP_SHORTCUT))})',
        f'$sc.TargetPath = [string]{json.dumps(target)}',
        f'$sc.Arguments = [string]{json.dumps(args)}',
        f'$sc.WorkingDirectory = [string]{json.dumps(str(PROJECT_ROOT))}',
        f'$sc.IconLocation = [string]{json.dumps(target)}',
        '$sc.Save()',
    ]
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ps1", delete=False, encoding="utf-8",
    )
    tmp.write("\n".join(ps_lines))
    tmp.close()
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp.name],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            _LAST_AUTOSTART_ERROR = f"powershell rc={r.returncode}: {r.stderr.strip()[:200]}"
            return False
        return STARTUP_SHORTCUT.exists()
    except (subprocess.SubprocessError, OSError) as e:
        _LAST_AUTOSTART_ERROR = f"subprocess: {e}"
        return False
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _remove_startup_shortcut() -> bool:
    try:
        if STARTUP_SHORTCUT.exists():
            STARTUP_SHORTCUT.unlink()
        return True
    except OSError:
        return False


def _resolve_self_command() -> tuple[str, str]:
    """Figure out how to relaunch this launcher.

    Returns (target_exe, arguments_string). If we were started from a frozen
    .exe (PyInstaller), uses sys.executable directly. Otherwise uses pythonw
    with the script path so no console window pops up.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, "--minimized"
    # Find pythonw next to the current python
    py_dir = Path(sys.executable).parent
    pythonw = py_dir / "pythonw.exe"
    if not pythonw.exists():
        # fallback to project venv
        pythonw = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        return "", ""
    return str(pythonw), f'"{Path(__file__).resolve()}" --minimized'


def is_autostart_enabled() -> bool:
    return STARTUP_SHORTCUT.exists()


# --- Helpers -------------------------------------------------------------

def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def windows_service_running(name: str) -> bool | None:
    """Return True/False if known, None if can't be determined."""
    try:
        out = subprocess.run(
            ["sc", "query", name],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode != 0:
            return None
        return "RUNNING" in out.stdout
    except (subprocess.TimeoutExpired, OSError):
        return None


def start_windows_service(name: str) -> bool:
    try:
        subprocess.run(["sc", "start", name], capture_output=True, timeout=10)
        return True
    except (subprocess.TimeoutExpired, OSError):
        return False


def stop_windows_service(name: str) -> bool:
    try:
        subprocess.run(["sc", "stop", name], capture_output=True, timeout=10)
        return True
    except (subprocess.TimeoutExpired, OSError):
        return False


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    extra = [UV_BIN_DIR, OLLAMA_BIN_DIR, NPM_BIN_DIR]
    env["PATH"] = ";".join([*extra, env.get("PATH", "")])
    return env


# --- Service definitions -------------------------------------------------

@dataclass
class Service:
    key: str
    label: str
    detail: str
    port: int | None = None
    is_windows_service: str | None = None  # service name
    start_cmd: list[str] | None = None
    cwd: Path | None = None
    process: subprocess.Popen | None = field(default=None, repr=False)
    log_lines: list[str] = field(default_factory=list, repr=False)
    auto_start: bool = True

    def is_running(self) -> bool:
        # Process we launched still alive?
        if self.process is not None and self.process.poll() is None:
            return True
        # Windows service check
        if self.is_windows_service:
            r = windows_service_running(self.is_windows_service)
            if r:
                return True
        # Port check (covers externally-launched services like Postgres)
        if self.port is not None:
            return port_open(self.port)
        return False


def make_services() -> list[Service]:
    return [
        Service(
            key="postgres",
            label="Postgres",
            detail=f"port {POSTGRES_PORT} (Windows service)",
            port=POSTGRES_PORT,
            is_windows_service="postgresql-x64-17",  # best effort, varies
            auto_start=False,  # usually always-on
        ),
        Service(
            key="memurai",
            label="Memurai (Redis)",
            detail=f"port {MEMURAI_PORT} (Windows service)",
            port=MEMURAI_PORT,
            is_windows_service="Memurai",
        ),
        Service(
            key="ollama",
            label="Ollama (LLM)",
            detail=f"port {OLLAMA_PORT}",
            port=OLLAMA_PORT,
            start_cmd=["ollama", "serve"],
            cwd=PROJECT_ROOT,
        ),
        Service(
            key="backend",
            label="FastAPI backend",
            detail=f"port {BACKEND_PORT}",
            port=BACKEND_PORT,
            start_cmd=["uv", "run", "python", "run_dev.py"],
            cwd=PROJECT_ROOT,
        ),
        Service(
            key="worker",
            label="Arq worker",
            detail="cron + background jobs",
            start_cmd=["uv", "run", "arq", "app.worker.settings.WorkerSettings"],
            cwd=PROJECT_ROOT,
        ),
        Service(
            key="web",
            label="Next.js web",
            detail=f"port {WEB_PORT}",
            port=WEB_PORT,
            start_cmd=["npm.cmd", "run", "dev"],
            cwd=WEB_DIR,
        ),
    ]


# --- Process management --------------------------------------------------

CREATE_NO_WINDOW = 0x08000000


def spawn_service(svc: Service) -> tuple[bool, str]:
    if svc.is_windows_service and not svc.start_cmd:
        ok = start_windows_service(svc.is_windows_service)
        return ok, "service start requested" if ok else "service start failed"

    if not svc.start_cmd:
        return False, "no start command"

    if svc.process is not None and svc.process.poll() is None:
        return True, "already running"

    svc.log_lines.clear()
    try:
        svc.process = subprocess.Popen(
            svc.start_cmd,
            cwd=str(svc.cwd or PROJECT_ROOT),
            env=build_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError as e:
        return False, f"spawn failed: {e}"

    # Drain stdout in a background thread so we can show recent logs.
    def _drain(p: subprocess.Popen, sink: list[str]) -> None:
        if p.stdout is None:
            return
        for line in p.stdout:
            sink.append(line.rstrip())
            if len(sink) > 400:
                del sink[: len(sink) - 400]
    threading.Thread(target=_drain, args=(svc.process, svc.log_lines), daemon=True).start()
    return True, "started"


def stop_service(svc: Service) -> tuple[bool, str]:
    if svc.process is not None and svc.process.poll() is None:
        try:
            svc.process.terminate()
            try:
                svc.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                svc.process.kill()
        except OSError as e:
            return False, f"stop failed: {e}"
        svc.process = None
        return True, "stopped"
    if svc.is_windows_service:
        ok = stop_windows_service(svc.is_windows_service)
        return ok, "service stop requested" if ok else "service stop failed"
    return False, "not running by launcher"


# --- GUI -----------------------------------------------------------------

class LauncherApp:
    def __init__(self, root: tk.Tk, start_minimized: bool = False) -> None:
        self.root = root
        self.root.title("coach_chess launcher")
        self.root.geometry("780x620")
        self.root.minsize(720, 540)
        try:
            self.root.tk.call("tk", "scaling", 1.2)
        except tk.TclError:
            pass

        self.services = make_services()
        self.rows: dict[str, dict] = {}
        self.settings = load_settings()
        self.tray: pystray.Icon | None = None  # type: ignore[name-defined]

        self._build_ui()
        self._poll()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Set up tray (background) capability
        if HAS_TRAY:
            self._setup_tray()

        # If launched with --minimized, hide window straight away
        if start_minimized or self.settings.get("start_minimized"):
            self.root.after(100, self._hide_window)

        # Auto-Start All on launch if configured
        if self.settings.get("auto_start_all_on_launch"):
            self.root.after(500, self.start_all)

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        header = ttk.Frame(self.root, padding=(16, 12))
        header.pack(fill="x")
        ttk.Label(
            header, text="coach_chess — local stack",
            font=("Segoe UI Semibold", 14),
        ).pack(side="left")

        btns = ttk.Frame(header)
        btns.pack(side="right")
        ttk.Button(btns, text="Start All", command=self.start_all).pack(side="left", padx=4)
        ttk.Button(btns, text="Stop All", command=self.stop_all).pack(side="left", padx=4)
        ttk.Button(btns, text="Open browser", command=self.open_browser).pack(side="left", padx=4)

        body = ttk.Frame(self.root, padding=(16, 8))
        body.pack(fill="both", expand=True)

        # Services list
        list_frame = ttk.LabelFrame(body, text="Services", padding=(8, 6))
        list_frame.pack(fill="x", pady=(0, 8))

        for svc in self.services:
            row = ttk.Frame(list_frame, padding=(4, 4))
            row.pack(fill="x", pady=2)

            dot = tk.Label(row, text="●", font=("Segoe UI", 14), fg="#888", width=2)
            dot.pack(side="left", padx=(0, 4))

            text = ttk.Frame(row)
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=svc.label, font=("Segoe UI Semibold", 10)).pack(anchor="w")
            ttk.Label(text, text=svc.detail, foreground="#777", font=("Segoe UI", 9)).pack(anchor="w")

            actions = ttk.Frame(row)
            actions.pack(side="right")
            start_btn = ttk.Button(actions, text="Start", width=8,
                                   command=lambda s=svc: self._start_one(s))
            start_btn.pack(side="left", padx=2)
            stop_btn = ttk.Button(actions, text="Stop", width=8,
                                  command=lambda s=svc: self._stop_one(s))
            stop_btn.pack(side="left", padx=2)
            logs_btn = ttk.Button(actions, text="Logs", width=6,
                                  command=lambda s=svc: self._show_logs(s))
            logs_btn.pack(side="left", padx=2)
            logs_btn.state(["disabled"] if not svc.start_cmd else ["!disabled"])

            self.rows[svc.key] = {"dot": dot, "start": start_btn, "stop": stop_btn}

        # Settings panel
        settings_frame = ttk.LabelFrame(body, text="Paramètres", padding=(8, 6))
        settings_frame.pack(fill="x", pady=(0, 8))

        self.var_autostart = tk.BooleanVar(value=is_autostart_enabled())
        self.var_start_min = tk.BooleanVar(value=self.settings.get("start_minimized", False))
        self.var_close_tray = tk.BooleanVar(value=self.settings.get("close_to_tray", True))
        self.var_auto_all = tk.BooleanVar(value=self.settings.get("auto_start_all_on_launch", False))

        ttk.Checkbutton(
            settings_frame,
            text="Lancer automatiquement au démarrage de Windows",
            variable=self.var_autostart,
            command=self._toggle_autostart,
        ).pack(anchor="w", pady=1)
        ttk.Checkbutton(
            settings_frame,
            text="Démarrer minimisé (icône uniquement dans la barre des tâches)",
            variable=self.var_start_min,
            command=self._save_settings,
        ).pack(anchor="w", pady=1)
        ttk.Checkbutton(
            settings_frame,
            text="Fermer la fenêtre = réduire à la barre des tâches (au lieu de quitter)",
            variable=self.var_close_tray,
            command=self._save_settings,
        ).pack(anchor="w", pady=1)
        ttk.Checkbutton(
            settings_frame,
            text="Démarrer tous les services dès l'ouverture du launcher",
            variable=self.var_auto_all,
            command=self._save_settings,
        ).pack(anchor="w", pady=1)
        if not HAS_TRAY:
            ttk.Label(
                settings_frame,
                text="(pystray non installé — pas de barre des tâches en arrière-plan)",
                foreground="#a06030",
            ).pack(anchor="w", pady=(4, 0))

        # Status bar / events
        events_frame = ttk.LabelFrame(body, text="Events", padding=(8, 6))
        events_frame.pack(fill="both", expand=True)
        self.events = tk.Text(
            events_frame, height=10, wrap="word",
            bg="#1e1e1e", fg="#e0e0e0", insertbackground="#fff",
            font=("Consolas", 9), borderwidth=0,
        )
        self.events.pack(fill="both", expand=True)
        self.events.configure(state="disabled")
        self._log("Launcher ready.")

    def _log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.events.configure(state="normal")
        self.events.insert("end", f"[{ts}] {msg}\n")
        self.events.see("end")
        self.events.configure(state="disabled")

    def _update_dots(self) -> None:
        for svc in self.services:
            running = svc.is_running()
            color = "#3fb950" if running else "#d04141"
            self.rows[svc.key]["dot"].configure(fg=color)

    def _poll(self) -> None:
        self._update_dots()
        self.root.after(POLL_INTERVAL_MS, self._poll)

    # Actions
    def _start_one(self, svc: Service) -> None:
        self._log(f"Starting {svc.label}…")
        threading.Thread(target=self._do_start, args=(svc,), daemon=True).start()

    def _do_start(self, svc: Service) -> None:
        ok, msg = spawn_service(svc)
        self.root.after(0, lambda: self._log(f"{svc.label}: {msg}"))

    def _stop_one(self, svc: Service) -> None:
        self._log(f"Stopping {svc.label}…")
        threading.Thread(target=self._do_stop, args=(svc,), daemon=True).start()

    def _do_stop(self, svc: Service) -> None:
        ok, msg = stop_service(svc)
        self.root.after(0, lambda: self._log(f"{svc.label}: {msg}"))

    def start_all(self) -> None:
        self._log("Start All — sequencing services…")

        def _runner() -> None:
            # Order: services first, then backend stack, then web.
            order = ["memurai", "ollama", "backend", "worker", "web"]
            svc_by_key = {s.key: s for s in self.services}
            for key in order:
                svc = svc_by_key.get(key)
                if svc is None:
                    continue
                if svc.is_running():
                    self.root.after(0, lambda s=svc: self._log(f"{s.label}: already running"))
                    continue
                ok, msg = spawn_service(svc)
                self.root.after(0, lambda s=svc, m=msg: self._log(f"{s.label}: {m}"))
                # Stagger so dependents see their deps up.
                if key in ("memurai", "ollama"):
                    time.sleep(0.5)
                elif key == "backend":
                    self._wait_port(BACKEND_PORT, 20)
            self.root.after(800, self.open_browser)

        threading.Thread(target=_runner, daemon=True).start()

    def _wait_port(self, port: int, timeout_s: int) -> bool:
        end = time.time() + timeout_s
        while time.time() < end:
            if port_open(port):
                return True
            time.sleep(0.5)
        return False

    def stop_all(self) -> None:
        self._log("Stop All — terminating launcher-owned processes…")
        for svc in self.services:
            if svc.process is not None and svc.process.poll() is None:
                ok, msg = stop_service(svc)
                self._log(f"{svc.label}: {msg}")

    def open_browser(self) -> None:
        webbrowser.open(f"http://localhost:{WEB_PORT}")

    def _show_logs(self, svc: Service) -> None:
        win = tk.Toplevel(self.root)
        win.title(f"{svc.label} — logs")
        win.geometry("780x460")
        txt = tk.Text(win, wrap="word", bg="#101010", fg="#d0d0d0",
                      font=("Consolas", 9))
        txt.pack(fill="both", expand=True)

        def refresh() -> None:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("end", "\n".join(svc.log_lines[-300:]))
            txt.see("end")
            txt.configure(state="disabled")
            if win.winfo_exists():
                win.after(1000, refresh)

        refresh()

    def _on_close(self) -> None:
        if self.settings.get("close_to_tray", True) and HAS_TRAY and self.tray is not None:
            self._log("Window hidden — launcher running in tray.")
            self._hide_window()
            return
        # Hard quit: kill child processes the launcher owns.
        self.stop_all()
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.destroy()

    # --- Settings -----------------------------------------------------
    def _save_settings(self) -> None:
        self.settings.update({
            "start_minimized": self.var_start_min.get(),
            "close_to_tray": self.var_close_tray.get(),
            "auto_start_all_on_launch": self.var_auto_all.get(),
        })
        save_settings(self.settings)

    def _toggle_autostart(self) -> None:
        want = self.var_autostart.get()
        if want:
            ok = _create_startup_shortcut()
            if ok:
                self._log(f"Auto-start activé -> {STARTUP_SHORTCUT}")
            else:
                err = _LAST_AUTOSTART_ERROR or "raison inconnue"
                self._log(f"Échec création du raccourci ({err})")
                self.var_autostart.set(False)
        else:
            ok = _remove_startup_shortcut()
            self._log("Auto-start désactivé." if ok else "Échec suppression du raccourci.")
        self.settings["autostart_windows"] = self.var_autostart.get()
        save_settings(self.settings)

    # --- Tray ---------------------------------------------------------
    def _setup_tray(self) -> None:
        img = self._make_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("Afficher", self._show_window, default=True),
            pystray.MenuItem("Start All", lambda: self.root.after(0, self.start_all)),
            pystray.MenuItem("Stop All", lambda: self.root.after(0, self.stop_all)),
            pystray.MenuItem("Ouvrir dans le navigateur", lambda: self.root.after(0, self.open_browser)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", self._quit_from_tray),
        )
        self.tray = pystray.Icon(
            "coach_chess", img, "coach_chess launcher", menu,
        )
        threading.Thread(target=self.tray.run, daemon=True).start()

    @staticmethod
    def _make_tray_icon() -> "Image.Image":
        size = 64
        img = Image.new("RGBA", (size, size), (30, 30, 30, 255))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 6, size - 6, size - 6), fill=(63, 185, 80, 255))
        # Subtle chess "knight" hint: two slashes
        d.line((20, 44, 30, 22), fill=(255, 255, 255, 220), width=4)
        d.line((30, 22, 44, 42), fill=(255, 255, 255, 220), width=4)
        return img

    def _hide_window(self) -> None:
        try:
            self.root.withdraw()
        except tk.TclError:
            pass

    def _show_window(self, *_args) -> None:
        try:
            self.root.after(0, self._do_show)
        except RuntimeError:
            pass

    def _do_show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit_from_tray(self, *_args) -> None:
        # Force a true exit even if close_to_tray is on.
        def _do():
            self.settings["close_to_tray"] = False
            self._on_close()
        self.root.after(0, _do)


def main() -> None:
    start_minimized = "--minimized" in sys.argv
    root = tk.Tk()
    LauncherApp(root, start_minimized=start_minimized)
    root.mainloop()


if __name__ == "__main__":
    main()
