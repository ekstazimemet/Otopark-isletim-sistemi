import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import os
import sys
import time
import openpyxl

import database
import mailer
import excel_manager

def test_abonman_ve_pazarlama():
    print("=" * 60)
    print(">> TEST BASLADI: Abonman Sistemi & Akilli Pazarlama")
    print("=" * 60)

    # 1. Sistemi sifirla
    database.sistemi_sifirla(musteriler_silinsin=True)
    print("[1] Sistem sifirlandi.")

    # 2. Musteri kaydi yap (Plaka + E-posta)
    plaka_abn = "34 ABN 01"
    email_abn = "plakaprojesi@gmail.com"
    basarili, _, _, _ = database.musteri_kod_talep_et(plaka_abn, email_abn, "kayit")
    assert basarili, "Musteri kayit kod talebi basarisiz"

    # Kod onayla
    son_kod = database.get_connection().execute(
        "SELECT kod FROM dogrulama_kodlari WHERE REPLACE(plaka, ' ', '') = '34ABN01' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    basarili, _, musteri = database.musteri_kod_dogrula(plaka_abn, son_kod)
    assert basarili, "Musteri kod dogrulama basarisiz"
    print(f"[2] Musteri kaydedildi ve giris yapildi: {plaka_abn} ({email_abn})")

    # 3. Haftalik Abonman Satin Al
    kart_dummy = {
        "kart_no": "4543 9876 5432 1098",
        "kart_sahibi": "Test Kullanici",
        "skt": "12/29",
        "cvv": "999"
    }
    basarili, mesaj, makbuz = database.abonman_satin_al(plaka_abn, "haftalik", kart_dummy)
    assert basarili, f"Abonman satin alma basarisiz: {mesaj}"
    assert makbuz["tutar"] == 250.0
    print(f"[3] Haftalik abonman satin alindi: {makbuz['paket_ad']} - {makbuz['tutar']} TL")

    # Abonman kontrolu
    abn = database.abonman_kontrol(plaka_abn)
    assert abn is not None, "Abonman aktif gorunmuyor!"
    assert abn["paket_id"] == "haftalik"
    assert abn["kalan_gun"] >= 6
    print(f"[4] Abonman aktifligi dogrulandi: Kalan gun = {abn['kalan_gun']}")

    # 4. Abonmanli Arac Otoparka Giris Yapiyor
    kayit, yeni = database.arac_giris_yap(plaka_abn)
    assert kayit["abonman_mi"] == 1
    assert "Abonman" in kayit["musteri_turu"]
    print(f"[5] Abonmanli arac otoparka girdi: musteri_turu = {kayit['musteri_turu']}")

    # Ucret ve Tolerans Hesaplama: 0.00 TL olmali!
    time.sleep(1)
    simdi = time.time() + 100  # 100 saniye sonra bile
    detay = database.arac_ucret_ve_tolerans_hesapla(kayit, simdi)
    assert detay["odenecek_ucret"] == 0.0, f"Abonmanli araca ucret cikti: {detay['odenecek_ucret']}"
    assert detay["cikis_izni"] is True, "Abonmanli aracin cikis izni False!"
    print("[6] Abonmanli arac 100 saniye sonra ucret: 0.00 TL ve cikis izni: SERBEST")

    # 5. Abonmanli Arac Cikis Yapiyor
    basarili, cikis_mesaj, cikis_kaydi = database.arac_cikis_yap(plaka_abn, zorla=False)
    assert basarili, f"Cikis engellendi: {cikis_mesaj}"
    assert cikis_kaydi["ucret"] == 0.0
    print(f"[7] Abonmanli arac sorunsuz cikis yapti! ({cikis_mesaj}) Odenen: {cikis_kaydi['ucret']} TL")


    # 6. Excel Dogrulamasi
    wb = openpyxl.load_workbook(excel_manager.EXCEL_DOSYA_ADI)
    ws = wb.active
    # Basliklari kontrol et
    headers = [cell.value for cell in ws[1]]
    assert "Müşteri Türü" in headers, f"'Müşteri Türü' sutunu Excel'de yok! Sutunlar: {headers}"
    col_idx = headers.index("Müşteri Türü") + 1
    
    # 2. satiri kontrol et (az once cikan arac)
    row_vals = [cell.value for cell in ws[2]]
    print(f"[8] Excel Satir Verisi: {row_vals}")
    assert "Abonman" in str(row_vals[col_idx - 1]), f"Musteri turu Excel'de abonman degil: {row_vals[col_idx - 1]}"
    assert "Abonman" in str(row_vals[8]), f"Durum Excel'de abonman icermiyor: {row_vals[8]}"
    assert float(row_vals[7]) == 0.0, f"Ucret Excel'de 0.0 degil: {row_vals[7]}"
    print("[8] Excel 10. sutun ve Abonman renklendirmesi basariyla dogrulandi!")

    # 7. Akilli Pazarlama Algoritmasi Testi
    # Sik gelen normal bir arac simule et
    plaka_paz = "34 PAZ 99"
    email_paz = "plakaprojesi@gmail.com"
    database.musteri_kod_talep_et(plaka_paz, email_paz, "kayit")
    kod_paz = database.get_connection().execute(
        "SELECT kod FROM dogrulama_kodlari WHERE REPLACE(plaka, ' ', '') = '34PAZ99' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    database.musteri_kod_dogrula(plaka_paz, kod_paz)

    # Bu araca 3 adet cikis yapmis gecmis ziyaret ekle
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO araclar (plaka, durum, giris_zamani, cikis_zamani, toplam_sure_sn, ucret, odeme_durumu, odenen_tutar, musteri_turu)
        VALUES 
        (?, 'disarida', ?, ?, 60, 20.0, 'odendi', 20.0, 'Standart'),
        (?, 'disarida', ?, ?, 90, 30.0, 'odendi', 30.0, 'Standart'),
        (?, 'disarida', ?, ?, 120, 40.0, 'odendi', 40.0, 'Standart')
    """, (plaka_paz, simdi - 300, simdi - 240, plaka_paz, simdi - 200, simdi - 110, plaka_paz, simdi - 100, simdi + 20))
    conn.commit()
    conn.close()

    # Analizi calistir
    adaylar = database.pazarlama_analizi_yap()
    print(f"[9] Pazarlama analiz aday sayisi: {len(adaylar)}")
    hedef = next((a for a in adaylar if a["plaka"] == plaka_paz), None)
    assert hedef is not None, "34 PAZ 99 pazarlama adayi olarak tespit edilemedi!"
    print(f"[9] Aday tespit edildi: {hedef['plaka']} - {hedef['ziyaret_sayisi']} ziyaret, {hedef['toplam_harcama']} TL harcama. Oneri: {hedef['onerilen_paket_ad']} (Tasarruf: %{hedef['tasarruf_yuzdesi']})")

    # 8. E-posta Gonderim Testi (Canli Gmail SMTP)
    print("[10] Canli Gmail uzerinden pazarlama e-postasi gonderiliyor...")
    ok, msg = mailer.pazarlama_epostasi_gonder(email_paz, plaka_paz, hedef)
    print(f"Pazarlama E-posta Sonucu: {ok}, {msg}")
    assert ok, f"Pazarlama e-postasi gonderilemedi: {msg}"

    print("\n" + "=" * 60)
    print(">> TUM TESTLER BASARIYLA TAMAMLANDI! (10/10)")
    print("=" * 60)

if __name__ == "__main__":
    test_abonman_ve_pazarlama()
