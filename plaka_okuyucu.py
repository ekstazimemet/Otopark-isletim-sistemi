import cv2
import pytesseract
import imutils
import numpy as np
import re
import time
import sys
import requests
import database

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tesseract yolunu kontrol etmeyi unutma
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

API_URL = "http://127.0.0.1:8000/api/manuel-islem"
OLAY_API_URL = "http://127.0.0.1:8000/api/kamera-olay"

def sunucuya_olay_bildir(tip: str, plaka: str, kayit: dict = None, mesaj: str = ""):
    """Kameradaki işlemi sunucuya ve bağlı tarayıcılara tekilleştirilmiş olarak duyurur."""
    try:
        requests.post(OLAY_API_URL, json={
            "tip": tip,
            "plaka": plaka,
            "kayit": kayit,
            "mesaj": mesaj
        }, timeout=0.8)
    except Exception:
        pass

def kamera_baslat(kamera_id=0):
    cap = cv2.VideoCapture(kamera_id)
    if not cap.isOpened():
        print(f"Hata: Kamera ({kamera_id}) açılamadı!")
        return

    BEKLEME_SURESI = 3 
    GEREKLI_OKUMA_SAYISI = 4  
    anlik_okumalar = {}
    son_okuma_zamani = time.time()
    son_islem_zamani = {} # Plaka bazlı çoklu tetiklemeyi önleme

    saniye, ucret = database.tarife_getir()
    print("\n" + "="*50)
    print(">> KAMERA PLAKA OKUMA & UCRET SISTEMI BASLATILDI")
    print(f">> Aktif Tarife: Her {saniye} saniye = {ucret:.2f} TL")
    print("Cikmak icin 'q' tusuna basin.")
    print("="*50 + "\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Görüntü İşleme
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        edged = cv2.Canny(gray, 30, 200)

        keypoints = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = imutils.grab_contours(keypoints)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

        location = None
        for contour in contours:
            approx = cv2.approxPolyDP(contour, 10, True)
            if len(approx) == 4:
                location = approx
                break

        su_an = time.time()
        
        if su_an - son_okuma_zamani > 2:
            anlik_okumalar.clear()

        # Ekranın üstüne Otopark Bilgi HUD'u ekle
        istatistik = database.get_istatistikler()
        kap = istatistik.get("kapasite", {})
        bos_str = f"BOS: {kap.get('bos', {}).get('toplam', 0)}/{kap.get('kapasite', {}).get('toplam', 0)} (Standart:{kap.get('bos', {}).get('normal', 0)} Abonman:{kap.get('bos', {}).get('abonman', 0)})"
        hud_text = f"{bos_str} | ICERIDE: {istatistik['icerideki_arac_sayisi']} | {istatistik['tarife']}"
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (20, 20, 30), -1)
        cv2.putText(frame, hud_text, (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 200), 2)

        if location is not None:
            mask = np.zeros(gray.shape, np.uint8)
            new_image = cv2.drawContours(mask, [location], 0, 255, -1)
            new_image = cv2.bitwise_and(frame, frame, mask=mask)

            (x, y) = np.where(mask == 255)
            if len(x) > 0 and len(y) > 0:
                (x1, y1) = (np.min(x), np.min(y))
                (x2, y2) = (np.max(x), np.max(y))
                cropped_image = gray[x1:x2+1, y1:y2+1]

                text = pytesseract.image_to_string(cropped_image, config='--psm 11')
                plaka = re.sub(r'[^A-Z0-9]', '', text.upper())

                if len(plaka) >= 6:
                    son_okuma_zamani = su_an 
                    anlik_okumalar[plaka] = anlik_okumalar.get(plaka, 0) + 1
                    
                    if anlik_okumalar[plaka] >= GEREKLI_OKUMA_SAYISI:
                        gecen_islem = su_an - son_islem_zamani.get(plaka, 0)
                        
                        if gecen_islem > BEKLEME_SURESI:
                            son_islem_zamani[plaka] = su_an
                            
                            # Veritabanı ve Ücretlendirme
                            mevcut = database.plaka_durum_getir(plaka)
                            if mevcut:
                                # Çıkış yapmayı dene
                                basarili, mesaj, kayit = database.arac_cikis_yap(plaka, su_an)
                                if basarili:
                                    sure = kayit.get('toplam_sure_sn', 0)
                                    ucret = kayit.get('ucret', 0)
                                    print(f"\n[CIKIS ONAYLANDI] [{plaka}] Sure: {sure:.1f} sn | Tahsil Edilen: {ucret:.2f} TL | Bariyer Acildi.")
                                    sunucuya_olay_bildir("CIKIS", plaka, kayit, f"{plaka} çıkış yaptı! Tutar: {ucret:.2f} TL")
                                else:
                                    borc = kayit.get("odenecek_ucret", 0.0) if kayit else 0.0
                                    if borc > 0.05:
                                        print(f"\n[CIKIS ENGELLENDI] [{plaka}] Odenmemis Borc: {borc:.2f} TL! Bariyer acilmadi.")
                                        sunucuya_olay_bildir("CIKIS_ENGELLENDI", plaka, kayit, f"[{plaka}] Çıkış Engellendi! Ödenmemiş {borc:.2f} TL borç var.")
                                    else:
                                        # Borç 0.05 TL ve altıysa çıkışa doğrudan izin ver
                                        _, _, kayit = database.arac_cikis_yap(plaka, su_an, zorla=True)
                                        print(f"\n[CIKIS ONAYLANDI] [{plaka}] Odenen: 0.00 TL | Bariyer Acildi.")
                                        sunucuya_olay_bildir("CIKIS", plaka, kayit, f"{plaka} çıkış yaptı!")
                            else:
                                # Giriş yap (Önce Kapasite Kontrolü)
                                kayit, yeni = database.arac_giris_yap(plaka, su_an)
                                if kayit and kayit.get("engellendi"):
                                    print(f"\n[GIRIS ENGELLENDI] [{plaka}] {kayit.get('mesaj')} Bariyer acilmadi.")
                                    sunucuya_olay_bildir("GIRIS_ENGELLENDI", plaka, kayit, kayit.get('mesaj'))
                                else:
                                    t_sn, t_tl = database.tarife_getir()
                                    print(f"\n[GIRIS] [{plaka}] Ucret sayaci basladi (Her {t_sn} sn = {t_tl:.2f} TL)")
                                    sunucuya_olay_bildir("GIRIS", plaka, kayit, f"{plaka} giriş yaptı!")
                                
                            anlik_okumalar.clear()

                    # Kamera üzerinde plaka çerçevesi ve anlık bilgi
                    cv2.drawContours(frame, [location], -1, (0, 255, 0), 3)
                    
                    # Eğer araç şu an içerideyse anlık süre, borç ve ödeme toleransını göster
                    aktif = database.plaka_durum_getir(plaka)
                    if aktif:
                        detay = database.arac_ucret_ve_tolerans_hesapla(aktif, su_an)
                        gecen_sn = detay["toplam_gecen_sn"]
                        borc = detay["odenecek_ucret"]
                        if detay["tolerans_aktif"]:
                            label = f"{plaka} [ODENDI] Cikis: {int(detay['kalan_tolerans_sn'])}sn"
                            renk = (0, 255, 0)
                        elif not detay["cikis_izni"]:
                            label = f"{plaka} [BORC: {borc:.1f}TL] CIKIS YASAK!"
                            renk = (0, 0, 255)
                        else:
                            label = f"{plaka} [ICERIDE] {gecen_sn:.0f}sn"
                            renk = (0, 255, 128)
                    else:
                        izin, mesaj, _ = database.kapasite_giris_izni_kontrol(plaka, su_an)
                        abn = database.abonman_kontrol(plaka, su_an)
                        if not izin:
                            label = f"{plaka} [DOLU! GIRIS YASAK]"
                            renk = (0, 0, 255)
                        elif abn:
                            label = f"{plaka} [ABONMANLI GIRIS]"
                            renk = (255, 0, 255)
                        else:
                            label = f"{plaka} [STANDART GIRIS]"
                            renk = (0, 255, 0)

                    pos_x = max(10, location[0][0][0])
                    pos_y = max(30, location[0][0][1] - 10)
                    cv2.putText(frame, label, (pos_x, pos_y), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, renk, 2)


        cv2.imshow("Plaka Okuma & Ucret Sistemi", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    kamera_baslat()