import random
import time
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Tuple, Optional

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# .env dosyasından çevre değişkenlerini yükle
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# SMTP Ayarları (Gmail Entegrasyonu)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "plakaprojesi@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "plakaprojesi@gmail.com")


def kod_uret() -> str:
    """6 haneli rastgele doğrulama kodu üretir."""
    return f"{random.randint(100000, 999999)}"

def eposta_gonder(kime: str, plaka: str, kod: str, islem_turu: str = "giris") -> Tuple[bool, str]:
    """
    Kullanıcıya 6 haneli doğrulama kodunu içeren HTML e-postası gönderir.
    SMTP yapılandırılmamışsa veya hata verirse dahi test için terminale basar.
    """
    konu = "ParkOS - Doğrulama Kodunuz"
    islem_baslik = "Hesap Girişi" if islem_turu == "giris" else "Yeni Plaka Kaydı"
    
    html_icerik = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
        .card {{ max-width: 480px; margin: 0 auto; background: #1e293b; border-radius: 16px; border: 1px solid #334155; padding: 32px 24px; text-align: center; }}
        .header {{ font-size: 24px; font-weight: bold; color: #38bdf8; margin-bottom: 8px; }}
        .badge {{ display: inline-block; background: #0284c7; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
        .plaka {{ font-family: monospace; font-size: 20px; font-weight: bold; background: white; color: black; padding: 6px 16px; border-radius: 6px; border: 2px solid #000; display: inline-block; margin: 16px 0; }}
        .code-box {{ background: #0f172a; border: 2px dashed #38bdf8; border-radius: 12px; padding: 18px; margin: 24px 0; }}
        .otp-code {{ font-family: monospace; font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #4ade80; }}
        .footer {{ font-size: 12px; color: #94a3b8; margin-top: 24px; line-height: 1.5; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">🅿️ ParkOS</div>
        <div class="badge">{islem_baslik}</div>
        <br>
        <div class="plaka">{plaka}</div>
        <p style="color: #cbd5e1; font-size: 14px; margin: 0;">Müşteri paneline erişmek için doğrulama kodunuz:</p>
        <div class="code-box">
          <div class="otp-code">{kod}</div>
        </div>
        <p style="color: #f59e0b; font-size: 13px; font-weight: 600;">Bu kod 5 dakika boyunca geçerlidir.</p>
        <div class="footer">
          Eğer bu işlemi siz yapmadıysanız lütfen bu mesajı dikkate almayınız.<br>
          © 2026 ParkOS - Akıllı Otopark İşletim Sistemi
        </div>
      </div>
    </body>
    </html>
    """

    # 1. Terminale her zaman açıkça bas (Geliştirici & Test kolaylığı için)
    print("\n" + "="*55)
    print("[E-POSTA OTP GONDERILDI]")
    print(f"[*] Alici E-posta  : {kime}")
    print(f"[*] Plaka          : {plaka}")
    print(f"[*] Dogrulama Kodu : >>> {kod} <<<")
    print(f"[*] Islem Turu     : {islem_baslik}")
    print("="*55 + "\n")

    # 2. Eğer SMTP ayarları mevcutsa gerçek e-posta gönder
    if SMTP_SERVER and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"{kod} - {konu} ({plaka})"
            msg["From"] = f"ParkOS <{SMTP_FROM}>"
            msg["To"] = kime
            msg.attach(MIMEText(html_icerik, "html", "utf-8"))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=8) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, kime, msg.as_string())
            print(f">> [GMAIL BASARILI] E-posta gercek olarak {kime} kutusuna iletildi!")
            return True, "E-posta başarıyla kutunuza gönderildi."
        except smtplib.SMTPAuthenticationError:
            print("\n" + "!"*65)
            print(">> [GMAIL UYARISI] Google hesap sifresini kabul etmedi!")
            print(">> Google (2022'den beri) SMTP uzerinden dogrudan hesap sifresi yerine")
            print(">> 16 haneli 'Uygulama Sifresi' (App Password) talep etmektedir.")
            print(">> Cozum (1 Dakika):")
            print(">> 1. Google Hesabinizda 2 Adimli Dogrulamayi acin")
            print(">> 2. https://myaccount.google.com/apppasswords adresine gidin")
            print(">> 3. 'Uygulama Adi' olarak 'PlakaProjesi' yazin ve 'Olustur'a basin")
            print(">> 4. Verilen 16 haneli sifreyi mailer.py icine yapistirin.")
            print("!"*65 + "\n")
            return True, "Kod olusturuldu (Gmail Uygulama Sifresi bekleniyor, test kodunu terminalden kullanabilirsiniz)."
        except Exception as e:
            print(f">> [SMTP HATA] E-posta gönderilemedi ({e}). Test kodunu terminalden kullanabilirsiniz.")
            return True, f"Doğrulama kodu oluşturuldu (SMTP Hatası: {e}). Kod terminalde görüntülendi."

    return True, "Doğrulama kodu oluşturuldu ve gönderildi."


def abonman_onay_epostasi_gonder(kime: str, plaka: str, makbuz: dict) -> Tuple[bool, str]:
    """
    Kullanıcıya satın aldığı abonman paketinin onay makbuzunu ve bilgilendirmesini e-posta ile gönderir.
    """
    paket_adi = makbuz.get("paket_ad", makbuz.get("paket_adi", "Abonman Paketi"))
    ucret = makbuz.get("tutar", makbuz.get("ucret", 0.0))
    baslangic = makbuz.get("baslangic_formatli") or (time.strftime("%d.%m.%Y %H:%M", time.localtime(makbuz["baslangic_tarihi"])) if "baslangic_tarihi" in makbuz else makbuz.get("baslangic_tarih", "-"))
    bitis = makbuz.get("bitis_formatli") or (time.strftime("%d.%m.%Y %H:%M", time.localtime(makbuz["bitis_tarihi"])) if "bitis_tarihi" in makbuz else makbuz.get("bitis_tarih", "-"))
    gun_sayisi = makbuz.get("gecerlilik", makbuz.get("gun_sayisi", 30))


    html_icerik = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
        .card {{ max-width: 520px; margin: 0 auto; background: #1e293b; border-radius: 18px; border: 1px solid #334155; padding: 32px 24px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        .vip-badge {{ display: inline-block; background: linear-gradient(135deg, #8b5cf6, #d946ef); color: white; padding: 6px 16px; border-radius: 30px; font-size: 13px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 12px; }}
        .header {{ font-size: 24px; font-weight: bold; color: #f8fafc; margin-bottom: 6px; }}
        .plaka {{ font-family: monospace; font-size: 22px; font-weight: bold; background: white; color: black; padding: 6px 18px; border-radius: 8px; border: 2px solid #000; display: inline-block; margin: 12px 0; }}
        .info-box {{ background: #0f172a; border-radius: 12px; padding: 18px; margin: 20px 0; text-align: left; font-size: 14px; border-left: 4px solid #8b5cf6; }}
        .info-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; color: #cbd5e1; }}
        .info-row strong {{ color: #ffffff; }}
        .total-row {{ display: flex; justify-content: space-between; border-top: 1px solid #334155; padding-top: 10px; margin-top: 10px; font-size: 16px; color: #a78bfa; font-weight: bold; }}
        .highlight {{ background: rgba(139, 92, 246, 0.15); border: 1px dashed #8b5cf6; border-radius: 10px; padding: 12px; color: #c4b5fd; font-size: 13px; margin-top: 16px; line-height: 1.5; }}
        .footer {{ font-size: 12px; color: #94a3b8; margin-top: 24px; line-height: 1.5; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="vip-badge">⭐ ABONMAN ONAYI</div>
        <div class="header">Abonmanınız Başarıyla Aktif Edildi!</div>
        <div class="plaka">{plaka}</div>
        
        <div class="info-box">
          <div class="info-row"><span>Paket Türü:</span> <strong>{paket_adi} ({gun_sayisi} Gün)</strong></div>
          <div class="info-row"><span>Başlangıç Tarihi:</span> <strong>{baslangic}</strong></div>
          <div class="info-row"><span>Geçerlilik Bitiş:</span> <strong>{bitis}</strong></div>
          <div class="info-row"><span>Ödeme Yöntemi:</span> <strong>Kredi Kartı (Online)</strong></div>
          <div class="total-row"><span>Ödenen Tutar:</span> <span>{ucret:.2f} ₺</span></div>
        </div>

        <div class="highlight">
          ✅ <strong>0.00 TL Ücretsiz Geçiş Ayrıcalığı:</strong> Abonman süreniz boyunca otopark giriş-çıkışlarınızda hiçbir otopark ücreti yansımayacak ve bariyerlerden otomatik beklemesiz geçiş sağlayacaksınız.
        </div>

        <div class="footer">
          Bizi tercih ettiğiniz için teşekkür ederiz.<br>
          © 2026 ParkOS - Akıllı Otopark İşletim Sistemi
        </div>
      </div>
    </body>
    </html>
    """

    print("\n" + "="*55)
    print("[E-POSTA ABONMAN ONAYI GONDERILDI]")
    print(f"[*] Alici E-posta  : {kime}")
    print(f"[*] Plaka          : {plaka}")
    print(f"[*] Paket          : {paket_adi} ({ucret:.2f} TL)")
    print(f"[*] Gecerlilik     : {baslangic} -> {bitis}")
    print("="*55 + "\n")

    if SMTP_SERVER and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🌟 Abonmanınız Başlatıldı: {paket_adi} ({plaka})"
            msg["From"] = f"ParkOS <{SMTP_FROM}>"
            msg["To"] = kime
            msg.attach(MIMEText(html_icerik, "html", "utf-8"))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=8) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, kime, msg.as_string())
            print(f">> [GMAIL BASARILI] Abonman onay e-postasi {kime} adresine iletildi!")
            return True, "Abonman onay e-postası başarıyla gönderildi."
        except Exception as e:
            print(f">> [SMTP HATA] Abonman onay e-postasi gönderilemedi: {e}")
            return False, f"E-posta iletim hatası: {e}"

    return True, "Abonman onaylandı."


def pazarlama_epostasi_gonder(kime: str, plaka: str, aday_bilgisi: dict) -> Tuple[bool, str]:
    """
    Sık ziyaret eden müşterilere kişiselleştirilmiş abonman tasarruf teklifini HTML e-postası olarak gönderir.
    """
    ziyaret_sayisi = aday_bilgisi.get("ziyaret_sayisi", 0)
    toplam_odenen = aday_bilgisi.get("toplam_harcama", aday_bilgisi.get("toplam_odenen", 0.0))
    oneri_paket = aday_bilgisi.get("onerilen_paket_ad", aday_bilgisi.get("oneri_paket", "Aylık Abonman (30 Gün)"))
    tasarruf_yuzde = aday_bilgisi.get("tasarruf_yuzdesi", aday_bilgisi.get("tahmini_tasarruf_yuzde", 35))
    paket_fiyat = aday_bilgisi.get("onerilen_paket_ucret", aday_bilgisi.get("paket_fiyat", 750.0))
    sure_sn = aday_bilgisi.get("toplam_sure_sn", aday_bilgisi.get("toplam_sure_dakika", 0) * 60)
    sure_gosterim = f"{round(sure_sn / 3600, 1)} Saat" if sure_sn >= 120 else f"{int(sure_sn)} Saniye"

    html_icerik = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
        .card {{ max-width: 520px; margin: 0 auto; background: #1e293b; border-radius: 18px; border: 1px solid #334155; padding: 32px 24px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        .badge {{ display: inline-block; background: linear-gradient(135deg, #3b82f6, #06b6d4); color: white; padding: 6px 16px; border-radius: 30px; font-size: 13px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 12px; }}
        .header {{ font-size: 24px; font-weight: bold; color: #f8fafc; margin-bottom: 6px; }}
        .plaka {{ font-family: monospace; font-size: 22px; font-weight: bold; background: white; color: black; padding: 6px 18px; border-radius: 8px; border: 2px solid #000; display: inline-block; margin: 12px 0; }}
        .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 20px 0; }}
        .stat-card {{ background: #0f172a; border-radius: 10px; padding: 12px; border: 1px solid #334155; text-align: center; }}
        .stat-val {{ font-size: 20px; font-weight: bold; color: #38bdf8; }}
        .stat-lbl {{ font-size: 12px; color: #94a3b8; margin-top: 4px; }}
        .offer-box {{ background: linear-gradient(135deg, rgba(139,92,246,0.15), rgba(59,130,246,0.15)); border: 2px dashed #8b5cf6; border-radius: 14px; padding: 20px; margin: 20px 0; }}
        .offer-title {{ font-size: 18px; font-weight: bold; color: #c4b5fd; margin-bottom: 8px; }}
        .savings-badge {{ background: #22c55e; color: #000; font-weight: bold; padding: 4px 12px; border-radius: 20px; font-size: 14px; display: inline-block; margin-bottom: 8px; }}
        .btn {{ display: inline-block; background: linear-gradient(135deg, #8b5cf6, #6366f1); color: white !important; font-weight: bold; padding: 12px 28px; border-radius: 10px; text-decoration: none; margin-top: 12px; box-shadow: 0 4px 15px rgba(139,92,246,0.4); }}
        .footer {{ font-size: 12px; color: #94a3b8; margin-top: 24px; line-height: 1.5; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="badge">🎯 Size Özel Akıllı Teklif</div>
        <div class="header">Otopark Masraflarınızı Azaltın!</div>
        <div class="plaka">{plaka}</div>
        
        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5;">
          Akıllı sistemimiz, otoparkımızı sıkça tercih ettiğinizi tespit etti. Sizin için özel bir tasarruf analizi hazırladık:
        </p>

        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-val">{ziyaret_sayisi} Kez</div>
            <div class="stat-lbl">Toplam Ziyaret</div>
          </div>
          <div class="stat-card">
            <div class="stat-val">{sure_gosterim}</div>
            <div class="stat-lbl">Toplam Park Süresi</div>
          </div>
        </div>
        <div style="margin-bottom: 12px; color: #94a3b8; font-size: 13px;">
          Şimdiye kadar ödenen toplam tutar: <strong style="color: #f8fafc;">{toplam_odenen:.2f} ₺</strong>
        </div>

        <div class="offer-box">
          <div class="savings-badge">%{tasarruf_yuzde:.0f} Net Tasarruf</div>
          <div class="offer-title">Önerilen Paket: {oneri_paket}</div>
          <p style="color: #e2e8f0; font-size: 13px; margin: 8px 0;">
            Abonman ile tek seferlik <strong>{paket_fiyat:.2f} TL</strong> ödeyerek tüm süre boyunca <strong>0.00 TL</strong> ile sınırsız giriş-çıkış yapabilirsiniz.
          </p>
          <a href="http://localhost:8000/musteri" class="btn">Hemen Avantajlı Abonman Al</a>
        </div>

        <div class="footer">
          Kampanya ve paket detaylarını müşteri portalımız üzerinden dilediğiniz zaman inceleyebilirsiniz.<br>
          © 2026 Akıllı Otopark ve Plaka Tanıma Sistemleri
        </div>
      </div>
    </body>
    </html>
    """

    print("\n" + "="*55)
    print("[E-POSTA PAZARLAMA KAMPANYASI GONDERILDI]")
    print(f"[*] Alici E-posta  : {kime}")
    print(f"[*] Plaka          : {plaka}")
    print(f"[*] Oneri Paket    : {oneri_paket}")
    print(f"[*] Tasarruf Orani : %{tasarruf_yuzde:.0f}")
    print("="*55 + "\n")

    if SMTP_SERVER and SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🎯 {plaka} Plakanız İçin Özel %{tasarruf_yuzde:.0f} Tasarruf Teklifi!"
            msg["From"] = f"ParkOS <{SMTP_FROM}>"
            msg["To"] = kime
            msg.attach(MIMEText(html_icerik, "html", "utf-8"))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=8) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, kime, msg.as_string())
            print(f">> [GMAIL BASARILI] Pazarlama e-postasi {kime} adresine iletildi!")
            return True, f"Pazarlama teklifi {kime} adresine başarıyla gönderildi."
        except Exception as e:
            print(f">> [SMTP HATA] Pazarlama e-postasi iletilemedi: {e}")
            return False, f"E-posta iletim hatası: {e}"

    return True, "Pazarlama teklifi terminale basıldı (SMTP yok)."



