import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import requests
import time

def test_api():
    base_url = "http://127.0.0.1:8000"
    
    # 1. Bilgi endpoint'i
    r = requests.get(f"{base_url}/api/bilgi")
    assert r.status_code == 200
    print("[OK] /api/bilgi:", r.json())

    # 2. Temizle
    requests.post(f"{base_url}/api/temizle")

    # 3. Manuel Giriş (34TEST99)
    r = requests.post(f"{base_url}/api/manuel-islem", json={"plaka": "34TEST99", "islem": "giris"})
    assert r.status_code == 200
    print("[OK] Giris yapildi:", r.json()["kayit"]["plaka"])

    # 4. Durum kontrolü
    r = requests.get(f"{base_url}/api/durum")
    iceridekiler = r.json()["iceridekiler"]
    assert len(iceridekiler) == 1
    assert iceridekiler[0]["plaka"] == "34TEST99"
    print("[OK] Icerideki arac onaylandi:", iceridekiler[0]["plaka"])

    # 5. 6 saniye bekle (en az 1 TL ücret oluşmalı)
    print("Ucret hesabi icin 6 saniye bekleniyor (5sn=1TL)...")
    time.sleep(6)

    r = requests.get(f"{base_url}/api/durum")
    arac = r.json()["iceridekiler"][0]
    print(f"[OK] 6 saniye sonra: Sure = {arac['gecen_sure_sn']} sn, Ucret = {arac['anlik_ucret']} TL")
    assert arac['anlik_ucret'] >= 1.0

    # 6. Çıkış yap
    r = requests.post(f"{base_url}/api/manuel-islem", json={"plaka": "34TEST99", "islem": "cikis"})
    cikis = r.json()["kayit"]
    print(f"[OK] Cikis onaylandi: Sure = {cikis['toplam_sure_sn']:.1f} sn, Tahsilat = {cikis['ucret']:.2f} TL")
    assert cikis['ucret'] >= 1.0

    # 7. Geçmiş kontrolü
    r = requests.get(f"{base_url}/api/gecmis")
    gecmis = r.json()["gecmis"]
    assert len(gecmis) >= 1
    print("[OK] Gecmis listesi onaylandi. Kayit sayisi:", len(gecmis))

    # Test bitti, temizle
    requests.post(f"{base_url}/api/temizle")
    print("\n>>> TUM TESTLER BASARIYLA GECTI! <<<")

if __name__ == "__main__":
    test_api()
