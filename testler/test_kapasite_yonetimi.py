import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import database
import server
from fastapi.testclient import TestClient

client = TestClient(server.app)

def test_kapasite_yonetimi():
    print("=" * 60)
    print(">> TEST: Otopark Kapasite & Park Yeri Yonetimi (Normal & Abonman)")
    print("=" * 60)

    # 1. Sistemi sıfırla
    database.sistemi_sifirla(musteriler_silinsin=True)
    print("[1] Sistem sifirlandi.")

    # 2. Varsayılan kapasiteyi doğrula (10 Normal + 5 Abonman = 15 Toplam)
    kap_durum = database.kapasite_durumu_getir()
    assert kap_durum["kapasite"]["normal"] == 10, f"Normal kapasite hatali: {kap_durum}"
    assert kap_durum["kapasite"]["abonman"] == 5, f"Abonman kapasite hatali: {kap_durum}"
    assert kap_durum["kapasite"]["toplam"] == 15
    assert kap_durum["bos"]["toplam"] == 15
    print(f"[2] Varsayilan Kapasite Basarili: {kap_durum['bos']['toplam']}/15 Bos (Normal: {kap_durum['bos']['normal']}, VIP: {kap_durum['bos']['abonman']})")

    # 3. Test için admin panelinden kapasiteyi 2 Normal + 1 Abonman olarak güncelle
    res_guncelle = client.post("/api/kapasite/guncelle", json={"normal": 2, "abonman": 1})
    assert res_guncelle.status_code == 200
    yeni_kap = res_guncelle.json()["kapasite"]
    assert yeni_kap["kapasite"]["normal"] == 2
    assert yeni_kap["kapasite"]["abonman"] == 1
    assert yeni_kap["kapasite"]["toplam"] == 3
    print(f"[3] Admin Kapasite Guncelleme Testi Basarili: 2 Normal + 1 VIP (Toplam: 3)")

    # 4. İki normal araç otoparka girsin (Normal kapasite dolsun: 2/2)
    res_g1 = client.post("/api/manuel-islem", json={"plaka": "34 NRM 01", "islem": "giris"})
    assert res_g1.json()["durum"] == "GIRIS"
    res_g2 = client.post("/api/manuel-islem", json={"plaka": "34 NRM 02", "islem": "giris"})
    assert res_g2.json()["durum"] == "GIRIS"

    durum_dolu_norm = database.kapasite_durumu_getir()
    assert durum_dolu_norm["dolu"]["normal"] == 2
    assert durum_dolu_norm["bos"]["normal"] == 0
    assert durum_dolu_norm["bos"]["abonman"] == 1
    print(f"[4] Normal yerler doldu: {durum_dolu_norm['dolu']['normal']}/2 Dolu, Kalan VIP: {durum_dolu_norm['bos']['abonman']}")

    # 5. Üçüncü normal araç girmeye çalışsın -> ENGELLENMELİ!
    res_g3 = client.post("/api/manuel-islem", json={"plaka": "34 NRM 03", "islem": "giris"})
    data_g3 = res_g3.json()
    print(f"[5] 3. Normal Arac Giris Denemesi: Durum={data_g3['durum']}, Mesaj={data_g3['mesaj']}")
    assert data_g3["durum"] == "GIRIS_ENGELLENDI", f"Hata: Normal kapasite doluyken arac alindi: {data_g3}"
    assert "abonmansız" in data_g3["mesaj"].lower() or "normal" in data_g3["mesaj"].lower()
    print("[5] Abonmansız kapasite doluyken standart aracin girisi basariyla ENGELLENDI!")

    # 6. Şimdi bir Abonman müşterisi gelsin (Haftalık Abonman) -> Abonman yer boş olduğu için GİREBİLMELİ!
    plaka_abn = "34 ABN 01"
    # Abonman satın al (Haftalık paket)
    client.post("/api/abonman/satin-al", json={
        "plaka": plaka_abn,
        "email": "abn@test.com",
        "paket_tipi": "haftalik",
        "kart_no": "4543 0000 1111 2222",
        "kart_sahibi": "Abonman Musteri",
        "skt": "01/30",
        "cvv": "123"
    })

    res_abn = client.post("/api/manuel-islem", json={"plaka": plaka_abn, "islem": "giris"})
    assert res_abn.json()["durum"] == "GIRIS", f"Haftalık abonmanlı aracın girisi engellenemez: {res_abn.json()}"
    print(f"[6] Haftalık Abonman araci, standart yerler dolu olsa dahi ayrilmis abonman yerine basariyla girdi!")

    # 7. Şimdi hem normal (2/2) hem abonman (1/1) dolu -> Otopark tamamen DOLU!
    durum_tam_dolu = database.kapasite_durumu_getir()
    assert durum_tam_dolu["tamamen_dolu_mu"] == True
    assert durum_tam_dolu["bos"]["toplam"] == 0
    print(f"[7] Otopark Tamamen Doldu: {durum_tam_dolu['dolu']['toplam']}/3 Dolu (%100)")

    # Başka bir araç gelince tamamen dolu uyarısı verilmeli
    res_tam_dolu = client.post("/api/manuel-islem", json={"plaka": "34 EXTRA 99", "islem": "giris"})
    assert res_tam_dolu.json()["durum"] == "GIRIS_ENGELLENDI"
    assert "dolu" in res_tam_dolu.json()["mesaj"].lower()
    print(f"[7] Tam dolu otoparkta giris basariyla reddedildi: {res_tam_dolu.json()['mesaj']}")

    # 8. Admin test amaciyla kapasiteyi artirsin: Normal 5, Abonman 3 (Toplam: 8)
    res_artir = client.post("/api/kapasite/guncelle", json={"normal": 5, "abonman": 3})
    assert res_artir.status_code == 200
    print("[8] Admin kapasiteyi artirdi (5 Normal + 3 VIP)")

    # 9. Reddedilen araç şimdi girmeyi denesin -> Başarılı olmalı!
    res_tekrar = client.post("/api/manuel-islem", json={"plaka": "34 EXTRA 99", "islem": "giris"})
    assert res_tekrar.json()["durum"] == "GIRIS"
    print("[9] Kapasite artirilinca bekleyen arac basariyla giris yapti!")

    # 10. Araç çıkış yapsın -> Boş yer sayısı artsın!
    client.post("/api/manuel-islem", json={"plaka": "34 EXTRA 99", "islem": "cikis", "zorla": True})
    durum_son = database.kapasite_durumu_getir()
    assert durum_son["dolu"]["normal"] == 2 # 34 NRM 01 ve 34 NRM 02 kaldi
    print(f"[10] Cikis sonrasi guncel bos yer: {durum_son['bos']['toplam']} / {durum_son['kapasite']['toplam']}")

    # Varsayılan kapasiteyi geri yükle
    database.kapasite_ayarlari_guncelle(10, 5)
    print("\n" + "=" * 60)
    print(">> TEBRIKLER! OTOPARK KAPASITE YONETIMI TESTI BASARIYLA GECTI! (10/10)")
    print("=" * 60)

if __name__ == "__main__":
    test_kapasite_yonetimi()
