# Hasil Simulasi Pengujian QoS
**Mahasiswa:** T. Zain Wardana · NIM 23210001  
**Tanggal simulasi:** 06 November 2026  
**Mata kuliah:** MKKL1029 Wireless/Mobile Computing — Kelompok 1  

> ⚠️ **PENTING:** Semua angka di dokumen ini adalah **data simulasi (tiruan)**.  
> Wajib diganti dengan data dari pengujian fisik (papan ESP32 + telepon nyata) sebelum laporan dikumpulkan.

---

## Tabel Hasil (Median 3 Ulangan)

| Skenario | Perangkat | Latency | Jitter | Packet Loss | Throughput | Status |
|---|:---:|---:|---:|---:|---:|:---:|
| S1 — gulir media sosial | 1 | 33,0 ms | 6,5 ms | 0,74% | 1705 kbps | ✅ LULUS |
| S2 — unduh berkas besar | 1 | 39,7 ms | 8,9 ms | 0,90% | 7747 kbps | ✅ LULUS |
| S3 — gulir + unduh | 2 | 52,8 ms | 14,2 ms | 1,11% | 2344 kbps | ✅ LULUS |
| S4 — semua aktif | 4 | 89,7 ms | 20,1 ms | 2,72% | 1657 kbps | ⚠️ PERHATIAN |
| S5 — semua diam | 4 | 52,5 ms | 5,1 ms | 0,64% | 24 kbps | ⚠️ PERHATIAN* |

**Batas yang diharapkan:** Latency < 150 ms · Jitter < 50 ms · Packet Loss < 2% · Throughput > 800 kbps

*) S5 status PERHATIAN hanya karena throughput 24 kbps di bawah batas 800 kbps — ini **wajar** karena skenario S5 memang tidak ada kegiatan (idle/pembanding dasar).

---

## Analisis Tren

### Pengaruh Jumlah Perangkat terhadap QoS

| Parameter | S1 (1 perangkat) | S4 (4 perangkat) | Perubahan |
|---|---:|---:|---:|
| Latency | 33,0 ms | 89,7 ms | **+56,7 ms (+172%)** |
| Jitter | 6,5 ms | 20,1 ms | **+13,6 ms (+209%)** |
| Packet Loss | 0,74% | 2,72% | **+1,98% (+268%)** |
| Throughput total | 1705 kbps | 1657 kbps | -48 kbps (-3%) |

### Temuan Utama

**1. Latency meningkat signifikan seiring penambahan perangkat**  
Dari 33 ms (1 perangkat) menjadi 89,7 ms (4 perangkat). Penyebabnya adalah satu radio ESP32 harus melayani lebih banyak klien secara bergantian (half-duplex). Meski meningkat +172%, nilainya masih di bawah batas 150 ms.

**2. Jitter memburuk di kondisi 4 perangkat**  
Dari 6,5 ms naik ke 20,1 ms. Antrean paket di radio menjadi tidak teratur saat ada banyak klien, menyebabkan ketidakstabilan waktu antarpaket. Masih di bawah batas 50 ms.

**3. Packet loss melewati batas di S4**  
Di skenario 4 perangkat aktif bersamaan, packet loss mencapai 2,72% — melewati batas yang diharapkan (< 2%). Ini menunjukkan tabrakan di kanal 2,4 GHz yang dipakai bersama sudah mulai signifikan. **Perlu penjelasan di laporan.**

**4. Throughput total relatif stabil**  
Meskipun throughput *per perangkat* turun, total throughput tidak turun drastis (1705 vs 1657 kbps). Ini menunjukkan ESP32 sudah mendekati batas kapasitasnya (~1–2 Mbps total untuk satu radio).

**5. S5 sebagai dasar pembanding**  
Skenario idle menunjukkan angka dasar: latency 52,5 ms dan packet loss 0,64% saat tidak ada beban aktif. Angka ini berguna sebagai acuan "kondisi bersih" untuk perbandingan.

---

## Keterbatasan Pengukuran (Wajib Disebut di Laporan)

1. **Byte dari bingkai 802.11** — angka byte beberapa persen lebih besar dari kenyataan karena termasuk header radio, bukan hanya payload IP.
2. **Retry ≠ packet loss pasti** — yang diukur adalah bingkai yang ditandai ulang di radio; kehilangan yang tidak terdeteksi radio tidak terlihat.
3. **Latency ≠ ICMP ping** — yang diukur adalah `connect()` TCP ke 1.1.1.1:53, bukan round-trip ICMP. Angkanya mencerminkan kualitas jalur uplink, bukan latency end-to-end.
4. **Data simulasi** — seluruh angka ini bukan dari pengukuran fisik. Simulator tidak merepresentasikan kondisi radio nyata, interferensi kanal, atau variasi hotspot HP.

---

## Hal yang Masih Perlu Dilakukan

- [ ] Pengujian fisik S1–S5 dengan papan ESP32 dan 5 telepon nyata
- [ ] Uji variasi jarak (1 m, 4 m, 8 m dari ESP32)
- [ ] Uji penghalang (dinding, tubuh manusia)
- [ ] Uji kanal padat (ruangan ramai perangkat 2,4 GHz)
- [ ] Uji uplink putus (HP-1 dimatikan saat pengujian)
- [ ] Isi tabel hasil di `docs/pengujian.md` dengan data nyata

---

## File yang Dihasilkan Simulasi

| File | Isi |
|---|---|
| `data/hasil_simulasi.db` | Database SQLite lengkap: trafik per detik, RTT, semua sesi |
| `data/hasil_simulasi.json` | Ringkasan JSON per skenario |
| `src/penerima/simulasi_windows.py` | Script simulasi (Windows-compatible) |
