import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import requests
import time

def test_tarife():
    base_url = "http://127.0.0.1:8000"

    # 1. Mevcut tarifeyi oku
    r = requests.get(f"{base_url}/api/tarife")
    assert r.status_code == 200
    data = r.json()
    print("[OK] Mevcut Tarife:", data)

    # 2. Yeni tarifeyi ayarla: 2 saniye = 0.5 TL
    r = requests.post(f"{base_url}/api/tarife", json={"saniye": 2, "ucret": 0.5})
    assert r.status_code == 200
    assert r.json()["saniye"] == 2
    assert r.json()["ucret"] == 0.5
    print("[OK] Tarife 2sn = 0.5TL olarak guncellendi!")

    # 3. Araç sok
    r = requests.post(f"{base_url}/api/manuel-islem", json={"plaka": "34TARIFE01", "islem": "giris"})
    assert r.status_code == 200

    # 4. 4.5 saniye bekle (4 saniye / 2 = 2 adım * 0.5 = 1.0 TL olmalı)
    print("Yeni tarife hesabi icin 4.5 saniye bekleniyor...")
    time.sleep(4.5)

    r = requests.get(f"{base_url}/api/durum")
    arac = r.json()["iceridekiler"][0]
    print(f"[OK] 4.5 sn sonra ucret: {arac['anlik_ucret']} TL (Beklenen: 1.0 TL)")
    assert arac['anlik_ucret'] >= 1.0

    # 5. Çıkış yap
    r = requests.post(f"{base_url}/api/manuel-islem", json={"plaka": "34TARIFE01", "islem": "cikis"})
    cikis = r.json()["kayit"]
    print(f"[OK] Cikis yapildi: Sure = {cikis['toplam_sure_sn']:.1f} sn, Ucret = {cikis['ucret']:.2f} TL")

    # 6. Tarifeyi orijinal 5sn = 1.0 TL'ye geri getir
    requests.post(f"{base_url}/api/tarife", json={"saniye": 5, "ucret": 1.0})
    requests.post(f"{base_url}/api/temizle")
    print("[OK] Tarife tekrar 5sn = 1.0TL yapildi ve test verileri temizlendi.")
    print("\n>>> TARIFE TESTI BASARIYLA TAMAMLANDI! <<<")

if __name__ == "__main__":
    test_tarife()
