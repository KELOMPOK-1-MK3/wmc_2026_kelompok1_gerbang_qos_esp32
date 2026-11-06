#!/usr/bin/env python3
"""
Simulasi Pengujian QoS — Windows Compatible
T. Zain Wardana (NIM 23210001)

Mensimulasikan skenario S1–S5 pengujian QoS menggunakan data tiruan dari
generator simulator (kompatibel Windows, tanpa termios/select/pty).

Cara pakai:
    py src/penerima/simulasi_windows.py
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AKAR = Path(__file__).resolve().parents[2]
DB_PATH = AKAR / "data" / "hasil_simulasi.db"

SKEMA = """
CREATE TABLE IF NOT EXISTS sesi (
  id INTEGER PRIMARY KEY, nama TEXT, mulai TEXT, mode TEXT, catatan TEXT
);
CREATE TABLE IF NOT EXISTS trafik (
  id INTEGER PRIMARY KEY, sesi INTEGER, t REAL, mac TEXT, ip TEXT,
  naik_bps REAL, turun_bps REAL, bingkai_naik INTEGER, bingkai_turun INTEGER, bingkai_ulang INTEGER
);
CREATE TABLE IF NOT EXISTS rtt (
  id INTEGER PRIMARY KEY, sesi INTEGER, t REAL, ms REAL
);
CREATE TABLE IF NOT EXISTS hasil_qos (
  id INTEGER PRIMARY KEY, sesi INTEGER, skenario TEXT,
  latency_ms REAL, jitter_ms REAL, packet_loss_pct REAL, throughput_kbps REAL,
  jumlah_perangkat INTEGER, durasi_detik INTEGER, catatan TEXT
);
"""

SKENARIO = [
    {"nama": "S1", "keterangan": "1 perangkat — menggulir media sosial",   "n_perangkat": 1, "beban": "ringan"},
    {"nama": "S2", "keterangan": "1 perangkat — mengunduh berkas besar",    "n_perangkat": 1, "beban": "berat"},
    {"nama": "S3", "keterangan": "2 perangkat — satu gulir, satu unduh",    "n_perangkat": 2, "beban": "sedang"},
    {"nama": "S4", "keterangan": "4 perangkat — semua aktif bersamaan",     "n_perangkat": 4, "beban": "penuh"},
    {"nama": "S5", "keterangan": "4 perangkat — diam (pembanding dasar)",   "n_perangkat": 4, "beban": "idle"},
]

PERANGKAT_TEMPLATE = [
    {"mac": "3c:5a:b4:11:22:33", "ip": "192.168.4.2", "nama": "HP-2"},
    {"mac": "8c:aa:b5:44:55:66", "ip": "192.168.4.3", "nama": "HP-3"},
    {"mac": "e4:5f:01:77:88:99", "ip": "192.168.4.4", "nama": "HP-4"},
    {"mac": "a0:b7:65:aa:bb:cc", "ip": "192.168.4.5", "nama": "HP-5"},
]

DURASI_SKENARIO = 30   # detik per skenario (simulasi dipercepat dari 5 menit)
ULANGAN = 3            # ulang tiap skenario, ambil median


def parameter_beban(beban: str, n: int) -> dict:
    """Kembalikan parameter distribusi acak berdasarkan beban dan jumlah perangkat."""
    # Makin banyak perangkat → throughput turun, latency naik, loss naik
    faktor_beban = 1 + (n - 1) * 0.35
    if beban == "idle":
        return {"turun_kb": 2,   "naik_kb": 1,   "rtt_base": 28,  "rtt_var": 4,  "retry_pct": 0.3}
    if beban == "ringan":
        return {"turun_kb": 180, "naik_kb": 30,  "rtt_base": 32,  "rtt_var": 6,  "retry_pct": 0.8}
    if beban == "sedang":
        return {"turun_kb": 250, "naik_kb": 40,  "rtt_base": 45,  "rtt_var": 10, "retry_pct": 1.5}
    if beban == "berat":
        return {"turun_kb": 900, "naik_kb": 80,  "rtt_base": 40,  "rtt_var": 8,  "retry_pct": 1.2}
    if beban == "penuh":
        return {"turun_kb": 180, "naik_kb": 28,  "rtt_base": 68,  "rtt_var": 18, "retry_pct": 3.5}
    return {"turun_kb": 100, "naik_kb": 20,  "rtt_base": 40,  "rtt_var": 10, "retry_pct": 2.0}


def jalankan_skenario(db: sqlite3.Connection, sesi_id: int, ske: dict, ulangan: int) -> dict:
    """Simulasikan satu skenario selama DURASI_SKENARIO detik. Kembalikan metrik QoS."""
    n   = ske["n_perangkat"]
    par = parameter_beban(ske["beban"], n)
    perangkat = PERANGKAT_TEMPLATE[:n]

    rtt_list: list[float] = []
    throughput_list: list[float] = []
    bingkai_total = 0
    bingkai_retry = 0

    kumulatif = [{"naik": 0, "turun": 0, "bn": 0, "bt": 0, "bu": 0} for _ in perangkat]
    t0 = time.monotonic()

    for detik in range(DURASI_SKENARIO):
        # RTT per 2 detik (mirip firmware)
        if detik % 2 == 0:
            rtt = max(5.0, random.gauss(par["rtt_base"] + (n - 1) * 8, par["rtt_var"]))
            rtt_list.append(round(rtt, 1))
            db.execute("INSERT INTO rtt (sesi,t,ms) VALUES (?,?,?)", (sesi_id, float(detik), rtt))

        total_bps_detik = 0.0
        for i, p in enumerate(perangkat):
            k = kumulatif[i]
            # variasi acak per perangkat, turun saat dibagi banyak perangkat
            share = 1.0 / n
            turun_bytes = int(random.gauss(par["turun_kb"] * 1000 * share, par["turun_kb"] * 300 * share))
            naik_bytes  = int(random.gauss(par["naik_kb"] * 1000 * share, par["naik_kb"] * 100 * share))
            turun_bytes = max(0, turun_bytes)
            naik_bytes  = max(0, naik_bytes)
            bt = max(0, int(random.gauss(160 * share, 20)))
            bn = max(0, int(random.gauss(110 * share, 15)))
            bu = max(0, int(abs(random.gauss(par["retry_pct"] * (bt + bn) / 100, 1))))

            k["turun"] += turun_bytes
            k["naik"]  += naik_bytes
            k["bt"] += bt
            k["bn"] += bn
            k["bu"] += bu

            naik_bps  = naik_bytes * 8
            turun_bps = turun_bytes * 8
            total_bps_detik += naik_bps + turun_bps

            bingkai_total += bt + bn
            bingkai_retry += bu

            db.execute(
                "INSERT INTO trafik (sesi,t,mac,ip,naik_bps,turun_bps,bingkai_naik,bingkai_turun,bingkai_ulang)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (sesi_id, float(detik), p["mac"], p["ip"],
                 naik_bps, turun_bps, bn, bt, bu))

        throughput_list.append(total_bps_detik / 1000)   # kbps

    db.commit()

    # --- Hitung metrik QoS ---
    latency_ms    = round(statistics.mean(rtt_list), 2) if rtt_list else 0
    jitter_ms     = round(statistics.mean(
        abs(rtt_list[i] - rtt_list[i-1]) for i in range(1, len(rtt_list))
    ), 2) if len(rtt_list) > 1 else 0
    packet_loss   = round(100 * bingkai_retry / bingkai_total, 2) if bingkai_total else 0
    throughput    = round(statistics.mean(throughput_list), 1) if throughput_list else 0

    return {
        "latency_ms": latency_ms,
        "jitter_ms": jitter_ms,
        "packet_loss_pct": packet_loss,
        "throughput_kbps": throughput,
    }


def status_nilai(nilai: float, batas: float, lebih_kecil: bool = True) -> str:
    """Kembalikan simbol status berdasarkan apakah nilai memenuhi batas."""
    ok = nilai < batas if lebih_kecil else nilai > batas
    return "✓ LULUS" if ok else "✗ GAGAL"


def cetak_tabel_hasil(semua_hasil: list[dict]) -> None:
    """Cetak tabel hasil lengkap ke terminal."""
    lebar = 110
    print("\n" + "=" * lebar)
    print(" TABEL HASIL PENGUJIAN QoS — SIMULASI")
    print(f" T. Zain Wardana · NIM 23210001 · {datetime.now().strftime('%d %B %Y %H:%M')}")
    print("=" * lebar)
    print(f"  {'Skenario':<38} {'Latency':>10} {'Jitter':>10} {'Loss':>10} {'Throughput':>13}  {'Status'}")
    print(f"  {'':38} {'(ms)':>10} {'(ms)':>10} {'(%)':>10} {'(kbps)':>13}")
    print(f"  {'Batas yg diharapkan':<38} {'< 150':>10} {'< 50':>10} {'< 2':>10} {'> 800':>13}")
    print("-" * lebar)

    for h in semua_hasil:
        lat_st  = "✓" if h["latency_ms"]       < 150  else "✗"
        jit_st  = "✓" if h["jitter_ms"]        < 50   else "✗"
        los_st  = "✓" if h["packet_loss_pct"]  < 2.0  else "✗"
        thr_st  = "✓" if h["throughput_kbps"]  > 800  else "✗"
        semua   = all([lat_st=="✓", jit_st=="✓", los_st=="✓", thr_st=="✓"])
        akhir   = "LULUS" if semua else "PERHATIAN"
        print(
            f"  {h['keterangan']:<38}"
            f" {h['latency_ms']:>9.1f}ms"
            f" {h['jitter_ms']:>9.1f}ms"
            f" {h['packet_loss_pct']:>9.2f}%"
            f" {h['throughput_kbps']:>10.1f}kbps"
            f"  [{lat_st}][{jit_st}][{los_st}][{thr_st}] {akhir}"
        )

    print("=" * lebar)
    print("  Legenda kolom status: [Latency][Jitter][Loss][Throughput]")
    print("  ✓ = memenuhi batas  ✗ = melewati batas")
    print("  CATATAN: Ini adalah data SIMULASI — wajib diulang dengan perangkat fisik sebelum laporan.\n")


def cetak_analisis(semua_hasil: list[dict]) -> None:
    """Cetak analisis singkat tren QoS."""
    print("=" * 80)
    print(" ANALISIS TREN QoS")
    print("=" * 80)

    s1 = next((h for h in semua_hasil if h["skenario"] == "S1"), None)
    s4 = next((h for h in semua_hasil if h["skenario"] == "S4"), None)

    if s1 and s4:
        d_lat = round(s4["latency_ms"]      - s1["latency_ms"], 1)
        d_jit = round(s4["jitter_ms"]       - s1["jitter_ms"], 1)
        d_los = round(s4["packet_loss_pct"] - s1["packet_loss_pct"], 2)
        d_thr = round(s4["throughput_kbps"] - s1["throughput_kbps"], 1)

        print(f"\n  Perbandingan S1 (1 perangkat) vs S4 (4 perangkat):")
        print(f"  {'Latency':20}: {s1['latency_ms']:.1f} ms → {s4['latency_ms']:.1f} ms  (Δ {d_lat:+.1f} ms)")
        print(f"  {'Jitter':20}: {s1['jitter_ms']:.1f} ms → {s4['jitter_ms']:.1f} ms  (Δ {d_jit:+.1f} ms)")
        print(f"  {'Packet Loss':20}: {s1['packet_loss_pct']:.2f} % → {s4['packet_loss_pct']:.2f} %  (Δ {d_los:+.2f} %)")
        print(f"  {'Throughput total':20}: {s1['throughput_kbps']:.1f} kbps → {s4['throughput_kbps']:.1f} kbps  (Δ {d_thr:+.1f} kbps)")

    print(f"""
  Kesimpulan simulasi:
  1. Latency naik seiring bertambahnya perangkat — satu radio ESP32 harus melayani
     lebih banyak klien secara bergantian (half-duplex).
  2. Jitter juga meningkat karena antrean paket di radio menjadi lebih tidak menentu.
  3. Packet loss (diukur dari retry bingkai) meningkat signifikan di S4 karena
     tabrakan di kanal 2.4 GHz yang dipakai bersama.
  4. Throughput per perangkat turun, meskipun total bisa tetap tinggi di S4 — ini
     menunjukkan batasan throughput ESP32 (~1-2 Mbps total) sudah mendekati jenuh.
  5. S5 (idle) menunjukkan angka dasar tanpa beban — berguna sebagai pembanding.
""")
    print("=" * 80)


def main() -> None:
    random.seed(42)   # seed tetap agar hasil reprodusibel

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH))
    db.executescript(SKEMA)

    print("\n" + "=" * 60)
    print("  SIMULASI PENGUJIAN QoS — Kelompok 1 WMC 2026")
    print("  T. Zain Wardana · NIM 23210001")
    print("=" * 60)
    print(f"  Basis data: {DB_PATH}")
    print(f"  Mulai     : {datetime.now().strftime('%d %B %Y %H:%M:%S')}")
    print(f"  Skenario  : {len(SKENARIO)} (S1–S5), {ULANGAN}x ulangan, {DURASI_SKENARIO} detik/ulangan")
    print("=" * 60 + "\n")

    semua_hasil: list[dict] = []

    for ske in SKENARIO:
        print(f"  ► {ske['nama']} — {ske['keterangan']}")
        ulangan_metrik: list[dict] = []

        for u in range(1, ULANGAN + 1):
            mulai = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.execute(
                "INSERT INTO sesi (nama, mulai, mode, catatan) VALUES (?,?,?,?)",
                (f"{ske['nama']}-U{u}", mulai, "simulasi",
                 f"Ulangan {u}/3 — {ske['keterangan']}"))
            sesi_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()

            metrik = jalankan_skenario(db, sesi_id, ske, u)
            ulangan_metrik.append(metrik)

            print(f"    Ulangan {u}: latency={metrik['latency_ms']:.1f}ms  "
                  f"jitter={metrik['jitter_ms']:.1f}ms  "
                  f"loss={metrik['packet_loss_pct']:.2f}%  "
                  f"throughput={metrik['throughput_kbps']:.0f}kbps")

        # Ambil median dari 3 ulangan (sesuai docs/pengujian.md)
        def median_kunci(kunci: str) -> float:
            vals = sorted(m[kunci] for m in ulangan_metrik)
            n = len(vals)
            return round((vals[n // 2 - 1] + vals[n // 2]) / 2 if n % 2 == 0 else vals[n // 2], 2)

        median_hasil = {
            "skenario":         ske["nama"],
            "keterangan":       ske["keterangan"],
            "jumlah_perangkat": ske["n_perangkat"],
            "latency_ms":       median_kunci("latency_ms"),
            "jitter_ms":        median_kunci("jitter_ms"),
            "packet_loss_pct":  median_kunci("packet_loss_pct"),
            "throughput_kbps":  median_kunci("throughput_kbps"),
        }
        semua_hasil.append(median_hasil)

        # Simpan ke DB
        db.execute(
            "INSERT INTO hasil_qos (sesi,skenario,latency_ms,jitter_ms,packet_loss_pct,"
            "throughput_kbps,jumlah_perangkat,durasi_detik,catatan) VALUES (?,?,?,?,?,?,?,?,?)",
            (sesi_id, ske["nama"], median_hasil["latency_ms"], median_hasil["jitter_ms"],
             median_hasil["packet_loss_pct"], median_hasil["throughput_kbps"],
             ske["n_perangkat"], DURASI_SKENARIO * ULANGAN,
             f"Median dari {ULANGAN} ulangan simulasi"))
        db.commit()

        print(f"    → MEDIAN: latency={median_hasil['latency_ms']}ms  "
              f"jitter={median_hasil['jitter_ms']}ms  "
              f"loss={median_hasil['packet_loss_pct']}%  "
              f"throughput={median_hasil['throughput_kbps']}kbps\n")

    # Ekspor JSON ringkasan
    json_path = AKAR / "data" / "hasil_simulasi.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "dibuat": datetime.now().isoformat(timespec="seconds"),
            "mode": "simulasi",
            "peringatan": "Data ini adalah SIMULASI — wajib diganti data pengukuran fisik sebelum laporan",
            "mahasiswa": "T. Zain Wardana (NIM 23210001)",
            "skenario": semua_hasil,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Ringkasan tersimpan: {json_path}")

    cetak_tabel_hasil(semua_hasil)
    cetak_analisis(semua_hasil)
    print(f"  Basis data lengkap : {DB_PATH}")
    print("  Selesai.\n")


if __name__ == "__main__":
    main()
