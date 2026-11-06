#!/usr/bin/env python3
# Launcher simulasi untuk Windows.
# Stub Unix-only modules (termios, select) lalu panggil utama() dari penerima.py

import sys
import types

# ── stub termios ──────────────────────────────────────────────────────────────
t = types.ModuleType("termios")
t.B115200 = 4098
t.CS8     = 48
t.CREAD   = 128
t.CLOCAL  = 2048
t.VMIN    = 16
t.VTIME   = 17
t.TCSANOW = 0
t.tcgetattr = lambda fd: [[0]*4, [0]*4, 0, 0, 0, 0, [0]*20]
t.tcsetattr = lambda fd, when, attrs: None
sys.modules["termios"] = t

# ── stub select ───────────────────────────────────────────────────────────────
s = types.ModuleType("select")
s.select = lambda r, w, x, to=None: ([], [], [])
sys.modules["select"] = s

# ── load penerima sebagai module, panggil utama() langsung ───────────────────
import importlib.util
from pathlib import Path

AKAR  = Path(__file__).resolve().parents[2]
SKRIP = AKAR / "src" / "penerima" / "penerima.py"

spec = importlib.util.spec_from_file_location("penerima", SKRIP)
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Override sys.argv sebelum memanggil utama()
sys.argv = [
    str(SKRIP),
    "--sim",
    "--sesi", "SimulasiZain",
    "--db",   str(AKAR / "data" / "qos.db"),
]

print("=" * 55)
print("  Penerima QoS -- mode simulasi (Windows)")
print("  Dashboard: http://127.0.0.1:8080")
print("  Tekan Ctrl+C untuk berhenti.")
print("=" * 55)

sys.exit(mod.utama())
