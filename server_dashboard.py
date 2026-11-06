#!/usr/bin/env python3
# server_dashboard.py
# Jalankan: python server_dashboard.py
# Dashboard: http://127.0.0.1:8080

import json, random, socket, sqlite3, sys, threading, time, webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

print(">> Memulai server...", flush=True)

AKAR      = Path(__file__).resolve().parent
DASHBOARD = AKAR / "src" / "dashboard" / "index.html"
DB_PATH   = AKAR / "data" / "sim_live.db"   # file baru, tidak bentrok dengan qos.db

print(f">> Folder proyek : {AKAR}", flush=True)
print(f">> Dashboard HTML: {'ADA' if DASHBOARD.exists() else 'TIDAK ADA'}", flush=True)

# ── skema DB ──────────────────────────────────────────────────────────────────
SKEMA = """
CREATE TABLE IF NOT EXISTS sesi (
  id INTEGER PRIMARY KEY, nama TEXT, mulai TEXT, mode TEXT);
CREATE TABLE IF NOT EXISTS trafik (
  id INTEGER PRIMARY KEY, sesi INTEGER, t REAL, mac TEXT, ip TEXT,
  naik_bps REAL, turun_bps REAL,
  bingkai_naik INTEGER, bingkai_turun INTEGER, bingkai_ulang INTEGER);
CREATE TABLE IF NOT EXISTS rtt (
  id INTEGER PRIMARY KEY, sesi INTEGER, t REAL, ms REAL);
"""

PERANGKAT = [
    {"mac": "3c:5a:b4:11:22:33", "ip": "192.168.4.2", "rssi": -48},
    {"mac": "8c:aa:b5:44:55:66", "ip": "192.168.4.3", "rssi": -61},
    {"mac": "e4:5f:01:77:88:99", "ip": "192.168.4.4", "rssi": -70},
    {"mac": "a0:b7:65:aa:bb:cc", "ip": "192.168.4.5", "rssi": -76},
]
DNS_CONTOH = ["tiktokcdn.com","googlevideo.com","i.instagram.com",
              "cdn.whatsapp.net","github.com","detik.com","spotify.com"]

# ── state bersama ─────────────────────────────────────────────────────────────
_kunci       = threading.Lock()
_t0          = time.monotonic()
_mulai       = datetime.now(timezone.utc).isoformat(timespec="seconds")
_histori     = []
_rtt_list    = []
_klien       = 0
_rssi_ul     = -52
_state_per   = {p["mac"]: {
    "mac": p["mac"], "ip": p["ip"], "rssi": p["rssi"],
    "naik_bps": 0.0, "turun_bps": 0.0,
    "bn": 0, "bt": 0, "bu": 0, "dns": [],
} for p in PERANGKAT}


def _elapsed():
    return round(time.monotonic() - _t0, 1)


# ── thread simulasi ───────────────────────────────────────────────────────────
def _simulasi(sesi_id: int, db: sqlite3.Connection, db_lock: threading.Lock):
    global _klien, _rssi_ul
    random.seed()
    kum = {p["mac"]: [0,0,0,0,0] for p in PERANGKAT}  # naik,turun,bn,bt,bu
    tick = 0

    while True:
        tick += 1
        n = min(1 + tick // 20, len(PERANGKAT))
        t = _elapsed()

        trafik_rows, rtt_rows, dns_rows = [], [], []

        with _kunci:
            _klien   = n
            _rssi_ul = -52 + random.randint(-3, 3)

        for i, p in enumerate(PERANGKAT[:n]):
            mac = p["mac"]
            k   = kum[mac]
            b   = random.uniform(0.4, 1.0) if i == 0 else random.uniform(0.1, 0.7)
            dn  = max(0, int(random.gauss(180_000, 40_000) * b))
            up  = max(0, int(random.gauss( 30_000,  8_000) * b))
            bt  = max(0, int(random.gauss(160, 20) * b))
            bn  = max(0, int(random.gauss(110, 15) * b))
            bu  = max(0, int(abs(random.gauss(2, 3)) * (1 + n / 3)))
            k[0]+=up; k[1]+=dn; k[2]+=bn; k[3]+=bt; k[4]+=bu

            with _kunci:
                s = _state_per[mac]
                s["naik_bps"] = up * 8
                s["turun_bps"] = dn * 8
                s["bn"] = bn; s["bt"] = bt; s["bu"] = bu
                if random.random() < 0.2:
                    d = random.choice(DNS_CONTOH)
                    if d not in s["dns"]:
                        s["dns"] = ([d] + s["dns"])[:6]
                    dns_rows.append((sesi_id, t, mac, p["ip"], d))

            trafik_rows.append((sesi_id, t, mac, p["ip"],
                                up*8, dn*8, bn, bt, bu))

        if tick % 2 == 0:
            rtt = max(5.0, random.gauss(35 + n*12, 6))
            with _kunci:
                _rtt_list.append(round(rtt, 1))
                if len(_rtt_list) > 60: del _rtt_list[0]
            rtt_rows.append((sesi_id, t, round(rtt,1)))

        with _kunci:
            naik_k  = sum(_state_per[p["mac"]]["naik_bps"]  for p in PERANGKAT[:n])/1000
            turun_k = sum(_state_per[p["mac"]]["turun_bps"] for p in PERANGKAT[:n])/1000
            _histori.append({"t": t, "naik": round(naik_k,1),
                             "turun": round(turun_k,1),
                             "rtt": _rtt_list[-1] if _rtt_list else None})
            if len(_histori) > 180: del _histori[0]

        try:
            with db_lock:
                if trafik_rows:
                    db.executemany(
                        "INSERT INTO trafik(sesi,t,mac,ip,naik_bps,turun_bps,"
                        "bingkai_naik,bingkai_turun,bingkai_ulang) VALUES(?,?,?,?,?,?,?,?,?)",
                        trafik_rows)
                if rtt_rows:
                    db.executemany("INSERT INTO rtt(sesi,t,ms) VALUES(?,?,?)", rtt_rows)
                db.commit()
        except Exception:
            pass

        time.sleep(1.0)


# ── buat JSON state ───────────────────────────────────────────────────────────
def _state_json(sesi_id: int) -> bytes:
    with _kunci:
        plist = []
        for p in PERANGKAT:
            s = _state_per[p["mac"]]
            if s["naik_bps"] == 0 and s["turun_bps"] == 0 and not s["dns"]:
                continue
            tot = s["bn"] + s["bt"]
            plist.append({
                "mac": s["mac"], "ip": s["ip"], "rssi": p["rssi"],
                "naik_kbps":  round(s["naik_bps"]  / 1000, 1),
                "turun_kbps": round(s["turun_bps"] / 1000, 1),
                "bingkai": tot,
                "ulang": s["bu"],
                "ulang_persen": round(100*s["bu"]/tot, 2) if tot else 0.0,
                "dns": s["dns"],
            })
        plist.sort(key=lambda d: d["turun_kbps"]+d["naik_kbps"], reverse=True)
        rtt_kini = _rtt_list[-1] if _rtt_list else 0
        data = {
            "mode": "sim",
            "detik": _elapsed(),
            "klien": _klien,
            "rssi_uplink": _rssi_ul,
            "rtt": {
                "sekarang": rtt_kini,
                "rata2": round(sum(_rtt_list)/len(_rtt_list),1) if _rtt_list else 0,
                "min":  min(_rtt_list) if _rtt_list else 0,
                "maks": max(_rtt_list) if _rtt_list else 0,
                "gagal": 0,
            },
            "perangkat": plist,
            "histori": list(_histori),
            "sesi": sesi_id,
            "mulai": _mulai,
        }
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


# ── HTTP handler ──────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    sesi_id: int = 1
    db_path: Path = DB_PATH

    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/state":
            return self._send(200, "application/json; charset=utf-8",
                              _state_json(self.sesi_id))
        if p == "/api/ekspor.csv":
            rows = ["t,mac,ip,naik_bps,turun_bps,bingkai_naik,bingkai_turun,bingkai_ulang"]
            try:
                c = sqlite3.connect(str(self.db_path))
                for r in c.execute(
                    "SELECT t,mac,ip,naik_bps,turun_bps,bingkai_naik,bingkai_turun,"
                    "bingkai_ulang FROM trafik WHERE sesi=? ORDER BY t",
                    (self.sesi_id,)):
                    rows.append(",".join(str(x) for x in r))
                c.close()
            except Exception:
                pass
            return self._send(200, "text/csv; charset=utf-8",
                              ("\n".join(rows)+"\n").encode())
        if p in ("/", "/index.html"):
            html = DASHBOARD
            if html.exists():
                return self._send(200, "text/html; charset=utf-8", html.read_bytes())
            return self._send(404, "text/plain", b"dashboard tidak ditemukan")
        self._send(404, "text/plain", b"tidak ada")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    # Inisialisasi DB
    print(">> Membuka database...", flush=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db      = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    db_lock = threading.Lock()
    db.executescript(SKEMA)
    db.execute("INSERT INTO sesi(nama,mulai,mode) VALUES(?,?,?)",
               ("SimulasiZain", _mulai, "sim"))
    sesi_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()
    print(f">> Database OK, sesi ID={sesi_id}", flush=True)

    # Cari port tersedia
    port = None
    for p in [8080, 8081, 8082, 8888, 9000, 9090]:
        try:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", p))
            s.close()
            port = p
            break
        except OSError:
            print(f"  port {p} dipakai, coba berikutnya...", flush=True)

    if port is None:
        print("GAGAL: tidak ada port tersedia!", flush=True)
        sys.exit(1)

    print(f">> Port tersedia: {port}", flush=True)

    # Pasang sesi_id ke handler
    _Handler.sesi_id = sesi_id
    _Handler.db_path = DB_PATH

    # Mulai simulasi di thread terpisah
    print(">> Memulai simulasi...", flush=True)
    threading.Thread(target=_simulasi, args=(sesi_id, db, db_lock),
                     daemon=True).start()

    # Buat server
    print(">> Membuat HTTP server...", flush=True)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    except OSError as e:
        print(f"GAGAL membuat server: {e}", flush=True)
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    print("", flush=True)
    print("=" * 52, flush=True)
    print("  Dashboard QoS ESP32 - Kelompok 1 WMC 2026", flush=True)
    print("  T. Zain Wardana - NIM 23210001", flush=True)
    print("=" * 52, flush=True)
    print(f"  >> Buka: {url}", flush=True)
    print("  Ctrl+C untuk berhenti.", flush=True)
    print("=" * 52, flush=True)

    # Buka browser otomatis
    def _buka():
        time.sleep(0.8)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_buka, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"\nERROR FATAL: {e}", flush=True)
        traceback.print_exc()
        input("\nTekan Enter untuk keluar...")
