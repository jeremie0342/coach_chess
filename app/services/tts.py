"""Text-to-speech via Windows SAPI.

We shell out to PowerShell using System.Speech.Synthesis — no extra Python
deps. Works on any Windows install. Voice picked is the first French voice
available; falls back to the system default.

The whole thing degrades gracefully if PowerShell is unavailable (Linux,
Docker) — `speak()` becomes a no-op so callers don't need to branch.
"""
from __future__ import annotations

import asyncio
import logging
import platform
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
# Pick a French voice if available
$voices = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }
$fr = $voices | Where-Object { $_.Culture.Name -like 'fr*' } | Select-Object -First 1
if ($fr) { $synth.SelectVoice($fr.Name) }
$synth.Rate = {RATE}
$synth.Volume = {VOLUME}
$synth.Speak({TEXT})
"""


@dataclass
class TtsResult:
    spoken: bool
    backend: str
    reason: str | None = None


def _can_run_powershell() -> bool:
    if platform.system() != "Windows":
        return False
    return shutil.which("powershell") is not None or shutil.which("pwsh") is not None


def _escape_ps(text: str) -> str:
    """Wrap text safely in single-quoted PS string."""
    return "'" + text.replace("'", "''") + "'"


def speak(text: str, *, rate: int = 0, volume: int = 90) -> TtsResult:
    """Block until the text finishes speaking. rate ∈ [-10, 10]."""
    if not text.strip():
        return TtsResult(spoken=False, backend="none", reason="empty text")
    if not _can_run_powershell():
        logger.info("TTS skipped (PowerShell unavailable)")
        return TtsResult(spoken=False, backend="none", reason="not Windows or no PS")
    ps = _PS_SCRIPT.replace("{RATE}", str(rate))\
                   .replace("{VOLUME}", str(volume))\
                   .replace("{TEXT}", _escape_ps(text))
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=False, capture_output=True, timeout=120,
        )
        return TtsResult(spoken=True, backend="sapi")
    except subprocess.TimeoutExpired:
        return TtsResult(spoken=False, backend="sapi", reason="timeout")
    except Exception as e:
        return TtsResult(spoken=False, backend="sapi", reason=repr(e))


async def aspeak(text: str, *, rate: int = 0, volume: int = 90) -> TtsResult:
    """Async wrapper — runs speak in a thread so we don't block the loop."""
    return await asyncio.to_thread(speak, text, rate=rate, volume=volume)
