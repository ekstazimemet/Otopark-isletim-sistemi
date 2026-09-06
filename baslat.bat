@echo off
chcp 65001 > nul
title ParkOS - Akilli Otopark Isletim Sistemi
color 0B

echo ====================================================
echo      🅿️ ParkOS - AKILLI OTOPARK ISLETIM SISTEMI
echo ====================================================
echo.

:: 1. Python Kurulu mu Kontrol Et
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Bilgisayarinizda Python bulunamadi!
    echo Lutfen https://www.python.org adresinden Python'i indirin.
    echo KURULUM ESNASINDA "Add python.exe to PATH" KUTUCUGUNU MUTLAKA ISARETLEYIN!
    echo.
    pause
    exit /b
)

:: 2. Gerekli Kutuphaneleri Kontrol Et ve Otomatik Yukle
echo [*] Kutuphaneler kontrol ediliyor...
python -c "import fastapi, uvicorn, cv2, openpyxl, qrcode, requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Ilk calistirma algilandi. Gerekli kutuphaneler otomatik yukleniyor...
    echo Lutfen bekleyin, bu islem 1-2 dakika surebilir...
    echo.
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [HATA] Kutuphaneler yuklenirken bir sorun olustu.
        pause
        exit /b
    )
    echo [*] Tum kutuphaneler basariyla yuklendi!
    echo.
)

:: 3. Tarayiciyi 2 Saniye Sonra Otomatik Ac
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

:: 4. Sistemi Baslat
echo [*] Sistem ve Web Sunucusu baslatiliyor...
echo [*] Yonetici Paneli : http://localhost:8000
echo [*] Musteri Portali : http://localhost:8000/musteri
echo ====================================================
echo.
python main.py
pause
