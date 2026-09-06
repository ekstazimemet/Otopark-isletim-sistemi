import threading
import time
import sys
import uvicorn
import server
import plaka_okuyucu
import database

def run_server():
    ip = server.get_local_ip()
    server.print_banner(ip, 8000)
    # Uvicorn sunucusunu arka planda başlat
    config = uvicorn.Config(server.app, host="0.0.0.0", port=8000, log_level="warning")
    srv = uvicorn.Server(config)
    srv.run()

def main():
    print("Sistem hazırlanıyor...")
    database.init_db()

    # 1. Mobil Sunucu Thread'ini Başlat
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Sunucunun ayağa kalkması için kısa bekleme
    time.sleep(1.5)

    # 2. Kamera ve Plaka Okuma Döngüsünü Başlat
    try:
        plaka_okuyucu.kamera_baslat(kamera_id=0)
    except KeyboardInterrupt:
        print("\nSistem kapatiliyor...")
        return
    except Exception as e:
        print(f"\nKamera baslatilirken hata olustu: {e}")

    # Kamera kapansa veya bulunamasa bile Web ve Musteri Sunucusu calismaya devam etsin
    print("\n>> Web Sunucusu ve Musteri Portali aktif calismaya devam ediyor.")
    print(">> Kapatmak icin terminalde CTRL+C tuslarina basin.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nSistem kapatildi.")

if __name__ == "__main__":
    main()

