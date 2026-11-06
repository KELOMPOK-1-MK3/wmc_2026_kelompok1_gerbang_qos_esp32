@echo off
title Dashboard QoS ESP32 - T. Zain Wardana
cd /d "%~dp0"
echo.
echo ====================================================
echo   Dashboard QoS ESP32 - Kelompok 1 WMC 2026
echo   T. Zain Wardana - NIM 23210001
echo ====================================================
echo.
echo   Buka browser ke: http://127.0.0.1:8080
echo   Tekan Ctrl+C untuk berhenti.
echo.
"C:\Users\USER DK\AppData\Local\Programs\Python\Python312\python.exe" server_dashboard.py
pause
