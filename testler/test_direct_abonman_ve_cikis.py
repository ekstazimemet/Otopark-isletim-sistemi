import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import database
import server
from fastapi.testclient import TestClient

client = TestClient(server.app)

def test_direct_abonman_ve_cikis():
    print("=" * 60)
    print(">> TEST: Direkt Abonman Alma & 0 TL Cikis Hatasi Kontrolu")
    print("=" * 60)

    # 1. Sistemi temizle
    database.sistemi_sifirla(musteriler_silinsin=True)
    print("[1] Sistem sifirlandi.")

    # 2. Direkt Müşteri GUI'dan Abonman Satın Alma Testi (E-posta beklemeden / Şifresiz)
    plaka_direct = "34 DIR 01"
    email_direct = "plakaprojesi@gmail.com"

    res_satinal = client.post("/api/abonman/satin-al", json={
        "plaka": plaka_direct,
        "email": email_direct,
        "paket_tipi": "aylik",
        "kart_no": "4543 1111 2222 3333",
        "kart_sahibi": "Direkt Musteri",
        "skt": "05/30",
        "cvv": "123"
    })
    data_satinal = res_satinal.json()
    assert data_satinal["status"] == "ok", f"Abonman satin alma basarisiz: {data_satinal}"
    print(f"[2] Direkt Abonman Basarili! Makbuz: {data_satinal['makbuz']['makbuz_no']}, Tutar: {data_satinal['makbuz']['tutar']} TL")

    # Müşterinin musteriler tablosuna otomatik kaydedildiğini doğrula
    musteri = database.musteri_getir(plaka_direct)
    assert musteri is not None, "Musteri musteriler tablosuna kaydedilmedi!"
    assert musteri["email"] == email_direct
    print(f"[3] Musteri otomatik kaydedildi: {musteri['plaka']} -> {musteri['email']}")

    # Abonmanın aktif olduğunu doğrula
    abn = database.abonman_kontrol(plaka_direct)
    assert abn is not None
    assert abn["paket_id"] == "aylik"
    assert abn["kalan_gun"] >= 29
    print(f"[4] Abonman aktif: {abn['paket_ad']} - Kalan: {abn['kalan_gun']} gun")

    # 3. 0 TL ile Cikis Testi (Abonmanli arac)
    # Arac giris yapsin
    res_giris = client.post("/api/manuel-islem", json={"plaka": plaka_direct, "islem": "giris"})
    assert res_giris.json()["durum"] == "GIRIS"

    # Arac cikis yapsin -> ASLA CIKIS_ENGELLENDI OLMAMALI!
    res_cikis = client.post("/api/manuel-islem", json={"plaka": plaka_direct, "islem": "cikis", "zorla": False})
    cikis_data = res_cikis.json()
    assert cikis_data["durum"] == "CIKIS", f"Abonmanli arac cikisi engellendi: {cikis_data}"
    assert cikis_data["kayit"]["ucret"] == 0.0
    print("[5] Abonmanli arac 0.00 TL ile hatasiz, engelsiz cikis yapti!")

    # 4. Normal Müşteri: Otoparka Giriyor -> Ücretini Ödüyor -> Çıkış Yapıyor
    plaka_norm = "34 NRM 77"
    email_norm = "plakaprojesi@gmail.com"
    # Kaydol
    database.musteri_kod_talep_et(plaka_norm, email_norm, "kayit")
    kod = database.get_connection().execute("SELECT kod FROM dogrulama_kodlari WHERE REPLACE(plaka, ' ', '') = '34NRM77'").fetchone()[0]
    database.musteri_kod_dogrula(plaka_norm, kod)

    # Giris
    client.post("/api/manuel-islem", json={"plaka": plaka_norm, "islem": "giris"})
    time.sleep(1)

    # 20 sn once girmis gibi yapalim boylece ucret olussun (4 birim borc = 4 * ucret TL)
    with database.get_connection() as conn:
        conn.execute("UPDATE araclar SET giris_zamani = ? WHERE REPLACE(plaka, ' ', '') = '34NRM77'", (time.time() - 20,))
        conn.commit()
    # Online odeme yap
    res_odeme = client.post("/api/musteri/odeme-yap", json={
        "plaka": plaka_norm,
        "kart_no": "4543 0000 0000 9999",
        "kart_sahibi": "Normal Musteri",
        "skt": "11/28",
        "cvv": "321"
    })
    assert res_odeme.json()["status"] == "ok", f"Odeme basarisiz: {res_odeme.json()}"
    print(f"[6] Normal musteri online odemesini yapti: {res_odeme.json()['makbuz']['odenen_tutar']} TL")

    # SIMDI CIKIS YAPIYOR -> ASLA "0 TL BORC VAR" DIYE CIKIS_ENGELLENDI VERMEMELI!
    res_norm_cikis = client.post("/api/manuel-islem", json={"plaka": plaka_norm, "islem": "cikis", "zorla": False})
    norm_cikis_data = res_norm_cikis.json()
    print(f"[7] Cikis Yaniti: Durum={norm_cikis_data['durum']}, Mesaj={norm_cikis_data['mesaj']}")
    assert norm_cikis_data["durum"] == "CIKIS", f"Hata: Ucretini odeyen aracin cikisi engellendi: {norm_cikis_data}"
    print("[7] Ucretini odeyen normal arac da '0 TL borc var' hatasi almadan basariyla cikis yapti!")

    print("\n" + "=" * 60)
    print(">> TEST BASARIYLA TAMAMLANDI! (HER IKI SORUN DA COZULDU)")
    print("=" * 60)

if __name__ == "__main__":
    test_direct_abonman_ve_cikis()
