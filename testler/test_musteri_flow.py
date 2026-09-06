import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import requests
import time
import threading
import uvicorn
import server
import database

def baslat_test_sunucu():
    config = uvicorn.Config(server.app, host="127.0.0.1", port=8000, log_level="warning")
    srv = uvicorn.Server(config)
    srv.run()

def test_musteri_flow():
    base_url = "http://127.0.0.1:8000"
    
    # Sunucu çalışıyor mu kontrol et, çalışmıyorsa başlat
    try:
        requests.get(f"{base_url}/api/tarife", timeout=1)
    except Exception:
        t = threading.Thread(target=baslat_test_sunucu, daemon=True)
        t.start()
        time.sleep(2)

    print("\n" + "="*60)
    print(">> MUSTERI PORTALI, ODEME & 30 SN TOLERANS ENTEGRASYON TESTI")
    print("="*60)

    # 0. Veritabanını temizle ve tarife ayarla (5 sn = 1 TL)
    requests.post(f"{base_url}/api/temizle")
    requests.post(f"{base_url}/api/tarife", json={"saniye": 5, "ucret": 1.0})

    # 1. İlk Kayıt: Kod İste (34VIP34 + test@ornek.com)
    print("\n[ADIM 1] Ilk Kayit: 34VIP34 icin kod isteniyor...")
    r = requests.post(f"{base_url}/api/musteri/kayit-kod-iste", json={
        "plaka": "34VIP34",
        "email": "ahmet@gmail.com"
    })
    assert r.status_code == 200, f"Kayıt isteği başarısız: {r.text}"
    data = r.json()
    assert data["status"] == "ok"
    test_kod = data["test_kod"]
    print(f"[OK] Kod uretildi: {test_kod} (Alici: {data['maskeli_email']})")

    # 2. Kodu Doğrula ve Kaydı Tamamla
    print("\n[ADIM 2] OTP Kodu dogrulaniyor...")
    r = requests.post(f"{base_url}/api/musteri/kod-dogrula", json={
        "plaka": "34VIP34",
        "kod": test_kod
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["musteri"]["plaka"] == "34VIP34"
    print(f"[OK] Kayit tamamlandi! Musteri: {data['musteri']['plaka']} - {data['musteri']['email']}")

    # 3. Sonraki Giriş: Sadece Plaka Girerek Kod İste (Failed to fetch / Unicode hatası giderildi mi?)
    print("\n[ADIM 3] Sonraki Giris: Sadece plaka ile kod isteniyor...")
    r = requests.post(f"{base_url}/api/musteri/giris-kod-iste", json={"plaka": "34VIP34"})
    assert r.status_code == 200, f"Giriş kodu isteği başarısız: {r.text}"
    data = r.json()
    assert data["status"] == "ok"
    giris_kodu = data["test_kod"]
    print(f"[OK] Sadece plaka ile giris OTP kodu basariyla uretildi: {giris_kodu}")

    # Giriş kodunu doğrula
    r = requests.post(f"{base_url}/api/musteri/kod-dogrula", json={"plaka": "34VIP34", "kod": giris_kodu})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    print("[OK] Sadece plaka ile sifresiz giris basarili!")

    # 4. Araç Otoparka Giriş Yapsın
    print("\n[ADIM 4] 34VIP34 otoparka giriyor...")
    simdi = time.time()
    # 20 saniye önce girmiş gibi kaydedelim (4 TL borç biriksin)
    database.arac_giris_yap("34VIP34", giris_zamani=simdi - 20)

    # 5. KURAL 2 TESTİ: Ödeme Alınmadan Çıkış Denemesi -> ENGELLENMELİ!
    print("\n[ADIM 5 - KURAL 2] Odenmemis borc varken cikis deneniyor...")
    r = requests.post(f"{base_url}/api/manuel-islem", json={"plaka": "34VIP34", "islem": "cikis"})
    assert r.status_code == 200
    res_cikis = r.json()
    assert res_cikis["durum"] == "CIKIS_ENGELLENDI", f"Hata: Cikis engellenmedi! {res_cikis}"
    print(f"[OK] Cikis Basariyla Engellendi! Mesaj: {res_cikis['mesaj']}")

    # 6. Müşteri Canlı Durumunu Sorgula
    r = requests.get(f"{base_url}/api/musteri/durum?plaka=34VIP34")
    durum = r.json()
    assert durum["iceride_mi"] == True
    assert durum["cikis_izni"] == False
    assert durum["anlik_ucret"] >= 4.0
    print(f"[OK] Musteri Paneli: Borc={durum['anlik_ucret']} TL, Cikis Izni={durum['cikis_izni']}")

    # 7. Online Kredi Kartı ile Ödeme Yap (Dummy Payment)
    print("\n[ADIM 6 - KURAL 3] Musteri sanal kredi karti ile online odeme yapiyor...")
    r = requests.post(f"{base_url}/api/musteri/odeme-yap", json={
        "plaka": "34VIP34",
        "kart_no": "4543 1234 5678 9012",
        "kart_sahibi": "Ahmet Yilmaz",
        "skt": "12/28",
        "cvv": "321"
    })
    assert r.status_code == 200
    pay_res = r.json()
    assert pay_res["status"] == "ok"
    makbuz = pay_res["makbuz"]
    print(f"[OK] Odeme Alindi! Makbuz No: {makbuz['makbuz_no']}, Tutar: {makbuz['odenen_tutar']} TL")

    # 8. KURAL 3A TESTİ: Ödeme Sonrası 30 sn Tolerans Devrede Mi? (Ek Ücret Donduruldu Mu?)
    r = requests.get(f"{base_url}/api/musteri/durum?plaka=34VIP34")
    durum_odendi = r.json()
    assert durum_odendi["tolerans_aktif"] == True
    assert durum_odendi["anlik_ucret"] == 0.0  # ÜCRET DONDURULDU!
    assert durum_odendi["cikis_izni"] == True  # ÇIKIŞ SERBEST!
    assert durum_odendi["kalan_tolerans_sn"] > 25
    print(f"[OK] 30 sn Tolerans Aktif! Kalan Sure: {durum_odendi['kalan_tolerans_sn']}sn, Ek Ucret: {durum_odendi['anlik_ucret']} TL (Donduruldu)")

    # 9. KURAL 3B TESTİ: 30 Saniye İçinde Çıkış Yapılırsa -> Çıkış Başarılı Olmalı!
    # Başka bir araçla 30 sn içinde çıkışı doğrulayalım
    print("\n[ADIM 7] 30 sn icinde cikis testi yapiliyor...")
    r = requests.post(f"{base_url}/api/manuel-islem", json={"plaka": "34VIP34", "islem": "cikis"})
    assert r.json()["durum"] == "CIKIS"
    print("[OK] 30 saniye tolerans suresi icinde cikis basariyla tamamlandi, bariyer acildi!")

    # 10. KURAL 3C TESTİ: 30 Saniye Doldu ve Çıkış Yapılmadı Senaryosu!
    print("\n[ADIM 8 - KURAL 3C] 30 saniye icinde cikis YAPILMAYIP sure asilirsa ek borcun yazilmasi testi...")
    # Yeni bir araç sokalım: 34TEST99
    database.arac_giris_yap("34TEST99", giris_zamani=time.time() - 50) # 50 sn önce girdi (10 TL normal tarife)
    # Ödeme yapılmış ama üzerinden 35 saniye geçmiş (yani 30 sn tolerans aşılmış) simüle edelim
    conn = database.get_connection()
    c = conn.cursor()
    # Diyelim ki 35 sn önce 4.0 TL ödedi
    c.execute("""
        UPDATE araclar 
        SET odeme_durumu = 'odendi', odeme_zamani = ?, odenen_tutar = 4.0, ucret = 4.0
        WHERE plaka = '34TEST99'
    """, (time.time() - 35,))
    conn.commit()
    conn.close()

    # Şimdi durumunu sorgulayalım: 30 sn aşıldığı için o dondurulan süre de dahil normal tarifeden 4 TL düşülmeli
    r = requests.get(f"{base_url}/api/musteri/durum?plaka=34TEST99")
    durum_gecikmis = r.json()
    assert durum_gecikmis["tolerans_doldu"] == True
    assert durum_gecikmis["cikis_izni"] == False # Çıkış tekrar yasak!
    assert durum_gecikmis["anlik_ucret"] > 0     # Ek borç yazıldı!
    print(f"[OK] 30 sn tolerans asildi! Dondurulan sure dahil yeni toplam tarife hesaplandi, onceki odenen dusuldu.")
    print(f"[OK] Yeni Ek Borc: {durum_gecikmis['anlik_ucret']} TL, Cikis Izni: {durum_gecikmis['cikis_izni']} (Bariyer Kapali)")

    # 34TEST99 çıkış yapmaya kalkarsa ENGELLENMELİ!
    r = requests.post(f"{base_url}/api/manuel-islem", json={"plaka": "34TEST99", "islem": "cikis"})
    assert r.json()["durum"] == "CIKIS_ENGELLENDI"
    print(f"[OK] Ek borc odenmeden cikis yapilamadi! ({r.json()['mesaj']})")

    # Ek borcu ödesin:
    r = requests.post(f"{base_url}/api/musteri/odeme-yap", json={
        "plaka": "34TEST99",
        "kart_no": "4543 9999 8888 7777",
        "kart_sahibi": "Test Surucu",
        "skt": "05/29",
        "cvv": "999"
    })
    assert r.json()["status"] == "ok"
    print("[OK] Ek borc online kart ile odendi!")

    # Artık çıkış yapabilir:
    r = requests.post(f"{base_url}/api/manuel-islem", json={"plaka": "34TEST99", "islem": "cikis"})
    assert r.json()["durum"] == "CIKIS"
    print("[OK] Ek borc odendikten sonra cikis basariyla tamamlandi!")

    # Temizlik
    requests.post(f"{base_url}/api/temizle")
    print("\n" + "="*60)
    print(">>> TEBRIKLER! 3 KURALIN TAMAMI EKSIKSIZ VE HATASIZ TEST EDILDI! <<<")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_musteri_flow()
