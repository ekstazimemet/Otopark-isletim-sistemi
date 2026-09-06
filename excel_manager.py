import os
import time
import threading
from datetime import datetime
from io import BytesIO
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

EXCEL_DOSYA_ADI = "otopark_kayitlari.xlsx"
CANLI_YEDEK_DOSYA_ADI = "otopark_kayitlari_canli.xlsx"

# Stil Tanımları
BASLIK_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
BASLIK_FILL = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid") # Koyu Lacivert
VERI_FONT = Font(name="Calibri", size=11)
PLAKA_FONT = Font(name="Consolas", size=11, bold=True, color="0F172A")
ORTALA = Alignment(horizontal="center", vertical="center")
SOLA = Alignment(horizontal="left", vertical="center")
SAGA = Alignment(horizontal="right", vertical="center")

THIN_BORDER = Border(
    left=Side(style='thin', color='E2E8F0'),
    right=Side(style='thin', color='E2E8F0'),
    top=Side(style='thin', color='E2E8F0'),
    bottom=Side(style='thin', color='E2E8F0')
)

SUTUNLAR = [
    "Kayıt ID",
    "Plaka",
    "Tarih (Gün)",
    "Giriş Zamanı",
    "Çıkış Zamanı",
    "Kalış Süresi (Sn)",
    "Kalış Süresi (Formatlı)",
    "Ödenen Ücret (TL)",
    "Durum",
    "Müşteri Türü"
]

GENISLIKLER = {1: 12, 2: 18, 3: 15, 4: 22, 5: 22, 6: 18, 7: 22, 8: 18, 9: 18, 10: 22}

# Bekleyen senkronizasyon bayrağı
bekleyen_senkronizasyon = False
_lock = threading.Lock()

def format_zaman(epoch_time):
    if not epoch_time:
        return "-"
    return datetime.fromtimestamp(epoch_time).strftime("%Y-%m-%d %H:%M:%S")

def format_gun(epoch_time):
    if not epoch_time:
        return "-"
    return datetime.fromtimestamp(epoch_time).strftime("%Y-%m-%d")

def format_sure(saniye):
    if saniye is None or saniye < 0:
        return "-"
    s = int(saniye)
    saat = s // 3600
    dakika = (s % 3600) // 60
    sn = s % 60
    if saat > 0:
        return f"{saat}sa {dakika}dk {sn}sn"
    elif dakika > 0:
        return f"{dakika}dk {sn}sn"
    return f"{sn}sn"

def dosya_kilitli_mi(dosya_yolu: str) -> bool:
    """
    Excel veya başka bir program tarafından dosyanın kilitlenip kilitlenmediğini kontrol eder.
    Microsoft Excel açıkken Windows dosyayı kilitler ve open/rename işlemine PermissionError verir.
    """
    if not os.path.exists(dosya_yolu):
        return False
    try:
        with open(dosya_yolu, "a+b"):
            pass
        test_yolu = dosya_yolu + ".lock_check"
        os.rename(dosya_yolu, test_yolu)
        os.rename(test_yolu, dosya_yolu)
        return False
    except (PermissionError, OSError):
        return True

def olustur_workbook(tum_kayitlar) -> Workbook:
    """Tüm kayıtları içeren formatlanmış açık Workbook nesnesi üretir."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Otopark Kayıtları"
    
    ws.append(SUTUNLAR)
    ws.row_dimensions[1].height = 28
    
    for col_idx in range(1, len(SUTUNLAR) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = BASLIK_FONT
        cell.fill = BASLIK_FILL
        cell.alignment = ORTALA
        cell.border = THIN_BORDER

    for col_idx, width in GENISLIKLER.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    simdi = time.time()
    for row_idx, r in enumerate(tum_kayitlar, 2):
        is_abonman = bool(r.get("abonman_mi")) or ("Abonman" in (r.get("musteri_turu") or ""))
        musteri_turu = r.get("musteri_turu") or ("Abonman Müşterisi" if is_abonman else "Standart")
        
        if is_abonman:
            durum_str = "İçeride (Abonman)" if r["durum"] == "iceride" else "Çıkış Yaptı (Abonman)"
            ucret_val = 0.0
        else:
            durum_str = "İçeride" if r["durum"] == "iceride" else "Çıkış Yaptı"
            ucret_val = float(r.get("ucret", 0.0))

        giris_str = format_zaman(r["giris_zamani"])
        cikis_str = format_zaman(r.get("cikis_zamani")) if r["durum"] == "disarida" else "-"
        gun_str = format_gun(r["giris_zamani"])
        
        if r["durum"] == "disarida":
            sure_sn = r.get("toplam_sure_sn", 0)
        else:
            sure_sn = max(0, simdi - r["giris_zamani"])

        satir_verisi = [
            r["id"],
            r["plaka"],
            gun_str,
            giris_str,
            cikis_str,
            round(sure_sn, 1),
            format_sure(sure_sn),
            ucret_val,
            durum_str,
            musteri_turu
        ]
        ws.append(satir_verisi)
        ws.row_dimensions[row_idx].height = 22

        for col_idx in range(1, len(satir_verisi) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = THIN_BORDER
            cell.font = PLAKA_FONT if col_idx == 2 else VERI_FONT
            
            if col_idx in [1, 2, 3, 9, 10]:
                cell.alignment = ORTALA
            elif col_idx in [6, 8]:
                cell.alignment = SAGA
            else:
                cell.alignment = ORTALA

            # Durum Hücresi (Kolon 9)
            if col_idx == 9:
                if "İçeride" in durum_str:
                    cell.fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
                    cell.font = Font(name="Calibri", size=11, bold=True, color="166534")
                else:
                    cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
                    cell.font = Font(name="Calibri", size=11, color="475569")

            # Müşteri Türü Hücresi (Kolon 10)
            if col_idx == 10:
                if is_abonman:
                    cell.fill = PatternFill(start_color="EDE9FE", end_color="EDE9FE", fill_type="solid")
                    cell.font = Font(name="Calibri", size=11, bold=True, color="6D28D9")
                else:
                    cell.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
                    cell.font = Font(name="Calibri", size=11, color="64748B")

    return wb


def excel_bytes_uret(tum_kayitlar) -> BytesIO:
    """Excel bilgisayarda açık olsa bile doğrudan bellekten indirmek için byte stream üretir."""
    wb = olustur_workbook(tum_kayitlar)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output

def excel_dosyasini_hazirla():
    """Excel dosyası yoksa veya bozulmuşsa başlıklarıyla oluşturur."""
    if not os.path.exists(EXCEL_DOSYA_ADI):
        wb = Workbook()
        ws = wb.active
        ws.title = "Otopark Kayıtları"
        ws.append(SUTUNLAR)
        ws.row_dimensions[1].height = 28
        
        for col_idx, col_name in enumerate(SUTUNLAR, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = BASLIK_FONT
            cell.fill = BASLIK_FILL
            cell.alignment = ORTALA
            cell.border = THIN_BORDER

        for col_idx, width in GENISLIKLER.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        try:
            wb.save(EXCEL_DOSYA_ADI)
            print(f">> [EXCEL] '{EXCEL_DOSYA_ADI}' dosyası hazırlandı.")
        except Exception:
            pass
    return EXCEL_DOSYA_ADI

def excel_tum_veritabanindan_guncelle(tum_kayitlar) -> bool:
    """
    Tüm veritabanı kayıtlarını Excel dosyasına güvenle kaydeder.
    Eğer dosya Microsoft Excel'de açıksa PermissionError vermez,
    kullanıcıyı bilgilendirir ve canlı yedeğe yazar.
    """
    global bekleyen_senkronizasyon
    with _lock:
        wb = olustur_workbook(tum_kayitlar)
        
        # Ana dosyaya yazmayı dene
        try:
            wb.save(EXCEL_DOSYA_ADI)
            bekleyen_senkronizasyon = False
            return True
        except PermissionError:
            bekleyen_senkronizasyon = True
            # Dosya Microsoft Excel'de açık! Kullanıcıyı bilgilendir ve canlı kopyaya kaydet
            print(f">> [BILGI] '{EXCEL_DOSYA_ADI}' dosyası Microsoft Excel programında açık olduğu için kilitli.")
            print(f">> [BILGI] Veriler veritabanında güvende. Excel'i kapattığınızda otomatik olarak kaydedilecektir.")
            try:
                wb.save(CANLI_YEDEK_DOSYA_ADI)
            except Exception:
                pass
            return False
        except Exception as e:
            print(f">> [EXCEL UYARI] Kayıt hatası: {e}")
            return False

def excel_kayit_ekle_veya_guncelle(kayit, tum_kayitlar=None):
    """
    Tek bir kayıt geldiğinde güvenli güncelleme yapar.
    Dosya kilitliyse hata fırlatmaz, beklemeye alır.
    """
    global bekleyen_senkronizasyon
    with _lock:
        if dosya_kilitli_mi(EXCEL_DOSYA_ADI):
            bekleyen_senkronizasyon = True
            print(f">> [BILGI] '{EXCEL_DOSYA_ADI}' Microsoft Excel'de açık. Veritabanına işlendi, dosya kilitli.")
            return False

        # Dosya kilitli değilse doğrudan açıp güncelle
        try:
            if not os.path.exists(EXCEL_DOSYA_ADI):
                excel_dosyasini_hazirla()

            wb = load_workbook(EXCEL_DOSYA_ADI)
            ws = wb.active
        except PermissionError:
            bekleyen_senkronizasyon = True
            return False
        except Exception:
            excel_dosyasini_hazirla()
            try:
                wb = load_workbook(EXCEL_DOSYA_ADI)
                ws = wb.active
            except Exception:
                return False

        kayit_id = kayit["id"]
        bulunan_row = None

        for row in range(2, ws.max_row + 1):
            if ws.cell(row=row, column=1).value == kayit_id:
                bulunan_row = row
                break

        is_abonman = bool(kayit.get("abonman_mi")) or ("Abonman" in (kayit.get("musteri_turu") or ""))
        musteri_turu = kayit.get("musteri_turu") or ("Abonman Müşterisi" if is_abonman else "Standart")
        
        if is_abonman:
            durum_str = "İçeride (Abonman)" if kayit["durum"] == "iceride" else "Çıkış Yaptı (Abonman)"
            ucret = 0.0
        else:
            durum_str = "İçeride" if kayit["durum"] == "iceride" else "Çıkış Yaptı"
            ucret = float(kayit.get("ucret", 0.0))

        giris_str = format_zaman(kayit["giris_zamani"])
        cikis_str = format_zaman(kayit.get("cikis_zamani")) if kayit["durum"] == "disarida" else "-"
        gun_str = format_gun(kayit["giris_zamani"])
        sure_sn = kayit.get("toplam_sure_sn", 0)

        satir_verisi = [
            kayit_id,
            kayit["plaka"],
            gun_str,
            giris_str,
            cikis_str,
            round(sure_sn, 1),
            format_sure(sure_sn),
            ucret,
            durum_str,
            musteri_turu
        ]

        target_row = bulunan_row if bulunan_row else ws.max_row + 1
        ws.row_dimensions[target_row].height = 22

        for col_idx, val in enumerate(satir_verisi, 1):
            cell = ws.cell(row=target_row, column=col_idx, value=val)
            cell.border = THIN_BORDER
            cell.font = PLAKA_FONT if col_idx == 2 else VERI_FONT
            
            if col_idx in [1, 2, 3, 9, 10]:
                cell.alignment = ORTALA
            elif col_idx in [6, 8]:
                cell.alignment = SAGA
            else:
                cell.alignment = ORTALA

            if col_idx == 9:
                if "İçeride" in durum_str:
                    cell.fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
                    cell.font = Font(name="Calibri", size=11, bold=True, color="166534")
                else:
                    cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
                    cell.font = Font(name="Calibri", size=11, color="475569")

            if col_idx == 10:
                if is_abonman:
                    cell.fill = PatternFill(start_color="EDE9FE", end_color="EDE9FE", fill_type="solid")
                    cell.font = Font(name="Calibri", size=11, bold=True, color="6D28D9")
                else:
                    cell.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
                    cell.font = Font(name="Calibri", size=11, color="64748B")


        try:
            wb.save(EXCEL_DOSYA_ADI)
            bekleyen_senkronizasyon = False
            return True
        except PermissionError:
            bekleyen_senkronizasyon = True
            print(f">> [BILGI] Excel açık olduğu için kilitli. Kapattığınızda kaydedilecektir.")
            return False
        except Exception:
            return False

def periyodik_kilit_cozucu_dongusu(database_modulu):
    """
    Arka planda çalışarak Excel dosyası kapandığı anda bekleyen tüm
    kayıtları otomatik olarak ana Excel dosyasına yazar.
    """
    while True:
        time.sleep(3)
        global bekleyen_senkronizasyon
        if bekleyen_senkronizasyon:
            if not dosya_kilitli_mi(EXCEL_DOSYA_ADI):
                print(f">> [EXCEL KILIDI ACILDI] Excel kapatıldı! Bekleyen tüm veriler dosyaya yazılıyor...")
                try:
                    database_modulu.excel_senkronize_et()
                    print(f">> [EXCEL SENKRON] '{EXCEL_DOSYA_ADI}' başarıyla güncellendi.")
                except Exception as e:
                    print(f"Kilit çözme hatası: {e}")
