import sqlite3
import time
import math
import os
import threading
from typing import List, Dict, Optional, Tuple
import excel_manager
import mailer

DB_PATH = "otopark.db"
VARSAYILAN_TARIFE_SANIYE = 5
VARSAYILAN_TARIFE_UCRET = 1.0

_kilit_cozucu_baslatildi = False

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS araclar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plaka TEXT NOT NULL,
            giris_zamani REAL NOT NULL,
            cikis_zamani REAL,
            durum TEXT NOT NULL DEFAULT 'iceride',
            toplam_sure_sn REAL DEFAULT 0,
            ucret REAL DEFAULT 0,
            tarih TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_plaka_durum ON araclar(plaka, durum)")
    
    # Müşteriler Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS musteriler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plaka TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            dogrulandi INTEGER DEFAULT 1,
            kayit_tarihi REAL NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_musteri_plaka ON musteriler(plaka)")

    # E-posta Doğrulama Kodları Tablosu (OTP)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dogrulama_kodlari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plaka TEXT NOT NULL,
            email TEXT NOT NULL,
            kod TEXT NOT NULL,
            son_gecerlilik REAL NOT NULL,
            kullanildi INTEGER DEFAULT 0,
            islem_turu TEXT DEFAULT 'giris',
            olusturma_zamani REAL NOT NULL
        )
    """)

    # Abonmanlar Tablosu (Haftalık & Aylık Paketler)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS abonmanlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plaka TEXT NOT NULL,
            paket_tipi TEXT NOT NULL,
            paket_ad TEXT NOT NULL,
            ucret REAL NOT NULL,
            baslangic_tarihi REAL NOT NULL,
            bitis_tarihi REAL NOT NULL,
            odeme_zamani REAL NOT NULL,
            kart_son4 TEXT,
            aktif INTEGER DEFAULT 1
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_abonman_plaka ON abonmanlar(plaka, bitis_tarihi)")

    # Araçlar tablosuna ödeme ve abonman kolonları ekle
    try:
        cursor.execute("ALTER TABLE araclar ADD COLUMN odeme_durumu TEXT DEFAULT 'odenmedi'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE araclar ADD COLUMN odeme_zamani REAL")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE araclar ADD COLUMN odenen_tutar REAL DEFAULT 0.0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE araclar ADD COLUMN abonman_mi INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE araclar ADD COLUMN musteri_turu TEXT DEFAULT 'Standart'")
    except Exception:
        pass

    # Ayarlar Tablosu
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ayarlar (
            anahtar TEXT PRIMARY KEY,
            deger TEXT NOT NULL
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO ayarlar (anahtar, deger) VALUES ('tarife_saniye', '5')")
    cursor.execute("INSERT OR IGNORE INTO ayarlar (anahtar, deger) VALUES ('tarife_ucret', '1.0')")
    cursor.execute("INSERT OR IGNORE INTO ayarlar (anahtar, deger) VALUES ('kapasite_normal', '10')")
    cursor.execute("INSERT OR IGNORE INTO ayarlar (anahtar, deger) VALUES ('kapasite_abonman', '5')")
    conn.commit()
    conn.close()



    # Excel dosyası yoksa veya silinmişse otomatik oluştur/senkronize et
    if not os.path.exists(excel_manager.EXCEL_DOSYA_ADI):
        excel_senkronize_et()

    # Arka planda Excel kapatılınca bekleyen verileri yazan nöbetçi thread
    global _kilit_cozucu_baslatildi
    if not _kilit_cozucu_baslatildi:
        _kilit_cozucu_baslatildi = True
        import sys
        t = threading.Thread(
            target=excel_manager.periyodik_kilit_cozucu_dongusu, 
            args=(sys.modules[__name__],), 
            daemon=True
        )
        t.start()

def tarife_getir() -> Tuple[int, float]:
    """Aktif tarife saniyesini ve birim ücretini döndürür."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT anahtar, deger FROM ayarlar WHERE anahtar IN ('tarife_saniye', 'tarife_ucret')")
    rows = dict(cursor.fetchall())
    conn.close()
    saniye = int(rows.get('tarife_saniye', VARSAYILAN_TARIFE_SANIYE))
    ucret = float(rows.get('tarife_ucret', VARSAYILAN_TARIFE_UCRET))
    return saniye, ucret

def tarife_guncelle(saniye: int, ucret: float) -> Tuple[int, float]:
    """Fiyat tarifesini günceller ve kaydeder."""
    saniye = max(1, int(saniye))
    ucret = max(0.0, float(ucret))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES ('tarife_saniye', ?)", (str(saniye),))
    cursor.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES ('tarife_ucret', ?)", (str(ucret),))
    conn.commit()
    conn.close()
    return saniye, ucret

# -------------------------------------------------------------
# OTOPARK KAPASİTE & PARK YERİ YÖNETİMİ (10 NORMAL + 5 ABONMAN)
# -------------------------------------------------------------
VARSAYILAN_KAPASITE_NORMAL = 10
VARSAYILAN_KAPASITE_ABONMAN = 5

def kapasite_ayarlari_getir() -> Dict[str, int]:
    """Kayıtlı normal ve abonman park kapasitelerini döndürür."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT anahtar, deger FROM ayarlar WHERE anahtar IN ('kapasite_normal', 'kapasite_abonman')")
    rows = dict(cursor.fetchall())
    conn.close()
    normal = int(rows.get('kapasite_normal', VARSAYILAN_KAPASITE_NORMAL))
    abonman = int(rows.get('kapasite_abonman', VARSAYILAN_KAPASITE_ABONMAN))
    return {
        "normal": normal,
        "abonman": abonman,
        "toplam": normal + abonman
    }

def kapasite_ayarlari_guncelle(normal: int, abonman: int) -> Dict[str, int]:
    """Otoparkın normal ve abonman park yeri kapasitelerini günceller."""
    normal = max(0, int(normal))
    abonman = max(0, int(abonman))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES ('kapasite_normal', ?)", (str(normal),))
    cursor.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES ('kapasite_abonman', ?)", (str(abonman),))
    conn.commit()
    conn.close()
    print(f">> [KAPASITE GUNCELLENDI] Normal: {normal}, Abonman: {abonman} (Toplam: {normal + abonman})")
    return {
        "normal": normal,
        "abonman": abonman,
        "toplam": normal + abonman
    }

def kapasite_durumu_getir() -> Dict:
    """İçerideki araçları sayarak güncel doluluk ve boş yer durumunu döner."""
    ayarlar = kapasite_ayarlari_getir()
    norm_kap = ayarlar["normal"]
    abn_kap = ayarlar["abonman"]
    toplam_kap = ayarlar["toplam"]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN abonman_mi = 1 OR musteri_turu LIKE '%Abonman%' THEN 1 ELSE 0 END), 0) as dolu_abn,
            COALESCE(SUM(CASE WHEN abonman_mi = 0 AND musteri_turu NOT LIKE '%Abonman%' THEN 1 ELSE 0 END), 0) as dolu_norm
        FROM araclar 
        WHERE durum = 'iceride'
    """)
    row = cursor.fetchone()
    conn.close()

    toplam_abn_arac = int(row["dolu_abn"] if row else 0)
    toplam_norm_arac = int(row["dolu_norm"] if row else 0)
    dolu_toplam = toplam_abn_arac + toplam_norm_arac

    # 1. Abonmanlı araçlar öncelikle kendilerine ayrılan abonman yerlerine yerleşir (en fazla abn_kap kadar)
    fiziksel_dolu_abn = min(toplam_abn_arac, abn_kap)
    
    # 2. Abonman yerlerini aşan fazla abonmanlı araçlar standart (abonmansız) alanlara yerleşir
    tasan_abn = max(0, toplam_abn_arac - abn_kap)
    
    # 3. Standart alanlardaki fiziksel doluluk: Standart araçlar + standart alana park eden abonmanlı araçlar
    fiziksel_dolu_norm = toplam_norm_arac + tasan_abn

    # Boş yer hesaplamaları (asla negatif olamaz):
    bos_abn = max(0, abn_kap - fiziksel_dolu_abn)
    bos_norm = max(0, norm_kap - fiziksel_dolu_norm)
    # Toplam boş yer: Toplam kapasiteden içerideki toplam araç sayısı çıkarılır
    bos_toplam = max(0, toplam_kap - dolu_toplam)

    doluluk_yuzdesi = round((min(dolu_toplam, toplam_kap) / toplam_kap) * 100, 1) if toplam_kap > 0 else 100.0

    return {
        "kapasite": {
            "normal": norm_kap,
            "abonman": abn_kap,
            "toplam": toplam_kap,
            "abonmansiz": norm_kap,
            "abonmanli": abn_kap
        },
        "dolu": {
            "normal": fiziksel_dolu_norm,
            "abonman": fiziksel_dolu_abn,
            "toplam": dolu_toplam,
            "abonmansiz": fiziksel_dolu_norm,
            "abonmanli": fiziksel_dolu_abn,
            "arac_sayilari": {
                "abonmanli": toplam_abn_arac,
                "abonmansiz": toplam_norm_arac
            }
        },
        "bos": {
            "normal": bos_norm,
            "abonman": bos_abn,
            "toplam": bos_toplam,
            "abonmansiz": bos_norm,
            "abonmanli": bos_abn
        },
        "doluluk_yuzdesi": doluluk_yuzdesi,
        "normal_dolu_mu": bos_norm <= 0,
        "abonman_dolu_mu": bos_abn <= 0,
        "tamamen_dolu_mu": bos_toplam <= 0 or (bos_norm <= 0 and bos_abn <= 0)
    }

def kapasite_giris_izni_kontrol(plaka: str, simdi: Optional[float] = None) -> Tuple[bool, str, str]:
    """
    Aracın otoparka giriş hakkı olup olmadığını anlık kapasiteye göre denetler.
    Kural:
    - Abonmanlılar: Tüm paketler (Haftalık / Aylık). Önce abonmanlı yerine, yer yoksa standart yere girer.
    - Abonmansızlar: Sadece standart yere girer. Standart yerler dolunca giremez.
    """
    plaka_norm = plaka.strip().upper().replace(" ", "")
    durum = kapasite_durumu_getir()
    
    # Otopark tamamen doluysa (içerideki araç sayısı >= toplam kapasite) kimse giremez!
    if durum["tamamen_dolu_mu"] or durum["bos"]["toplam"] <= 0:
        return False, f"Otopark tamamen dolu! (Toplam Kapasite: {durum['kapasite']['toplam']} Araç)", "yok"

    # Plakanın aktif abonmanı var mı?
    abn = abonman_kontrol(plaka_norm, simdi)
    
    if abn:
        # Abonmanlı müşteri (Haftalık veya Aylık fark etmeksizin)
        if durum["bos"]["abonman"] > 0:
            return True, f"Abonmanlı park alanına yönlendirildi. (Kalan Abonmanlı Yer: {durum['bos']['abonman']})", "abonman"
        elif durum["bos"]["normal"] > 0:
            return True, f"Abonmanlı park alanı dolu, standart alana yönlendirildi. (Kalan Standart Yer: {durum['bos']['normal']})", "normal"
        else:
            return False, f"Otopark tamamen dolu! (Toplam Kapasite: {durum['kapasite']['toplam']} Araç)", "yok"
    else:
        # Abonmansız standart müşteri
        if durum["bos"]["normal"] > 0:
            return True, f"Standart park alanına yönlendirildi. (Kalan Standart Yer: {durum['bos']['normal']})", "normal"
        else:
            abn_bos = durum["bos"]["abonman"]
            if abn_bos > 0:
                return False, f"Standart (abonmansız) park yerleri dolu ({durum['kapasite']['normal']}/{durum['kapasite']['normal']})! Kalan {abn_bos} yer abonmanlı müşterilere ayrılmıştır.", "yok"
            else:
                return False, f"Otopark tamamen dolu! (Toplam Kapasite: {durum['kapasite']['toplam']} Araç)", "yok"

def ucret_hesapla(gecen_saniye: float) -> float:
    """Aktif tarifeye göre ücret hesaplar."""
    if gecen_saniye < 0:
        return 0.0
    saniye, birim_ucret = tarife_getir()
    adim = int(gecen_saniye // saniye)
    return float(adim * birim_ucret)

ABONMAN_PAKETLERI = {
    "haftalik": {
        "id": "haftalik",
        "ad": "Haftalık Abonman",
        "gun": 7,
        "ucret": 250.0,
        "rozet": "7 Günlük • Sınırsız",
        "aciklama": "7 gün boyunca sınırsız giriş-çıkış. 0 TL otopark ücreti, bariyer otomatik açılır."
    },
    "aylik": {
        "id": "aylik",
        "ad": "Aylık Abonman",
        "gun": 30,
        "ucret": 750.0,
        "rozet": "30 Günlük • En Avantajlı",
        "aciklama": "30 gün boyunca sınırsız giriş-çıkış, 0 TL park ücreti ve garantili park hakkı."
    }
}

def abonman_kontrol(plaka: str, simdi: Optional[float] = None) -> Optional[Dict]:
    """
    Plakanın aktif bir haftalık/aylık abonmanı olup olmadığını kontrol eder.
    Aktifse paket detaylarını, kalan gün/saat bilgisini döner.
    """
    if not plaka:
        return None
    if simdi is None:
        simdi = time.time()
    plaka_norm = plaka.strip().upper().replace(" ", "")

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM abonmanlar 
        WHERE REPLACE(plaka, ' ', '') = ? AND aktif = 1 AND bitis_tarihi > ?
        ORDER BY bitis_tarihi DESC LIMIT 1
    """, (plaka_norm, simdi))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    d = dict(row)
    kalan_sn = max(0.0, d["bitis_tarihi"] - simdi)
    kalan_gun = int(kalan_sn // 86400)
    kalan_saat = int((kalan_sn % 86400) // 3600)

    d["paket_id"] = d.get("paket_tipi")
    d["kalan_saniye"] = round(kalan_sn, 1)
    d["kalan_gun"] = kalan_gun
    d["kalan_saat"] = kalan_saat
    d["kalan_metin"] = f"{kalan_gun} gün {kalan_saat} saat" if kalan_gun > 0 else f"{kalan_saat} saat"
    d["baslangic_formatli"] = time.strftime("%d.%m.%Y %H:%M", time.localtime(d["baslangic_tarihi"]))
    d["bitis_formatli"] = time.strftime("%d.%m.%Y %H:%M", time.localtime(d["bitis_tarihi"]))
    return d

def tum_aktif_abonmanlar() -> List[Dict]:
    """Sistemdeki tüm aktif abonmanları listeler."""
    simdi = time.time()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM abonmanlar 
        WHERE aktif = 1 AND bitis_tarihi > ?
        ORDER BY bitis_tarihi DESC
    """, (simdi,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for d in rows:
        d["paket_id"] = d.get("paket_tipi")
        kalan_sn = max(0.0, d["bitis_tarihi"] - simdi)
        d["kalan_gun"] = int(kalan_sn // 86400)
        d["kalan_saat"] = int((kalan_sn % 86400) // 3600)
        d["kalan_metin"] = f"{int(kalan_sn // 86400)} gün {int((kalan_sn % 86400) // 3600)} saat"
        d["baslangic_formatli"] = time.strftime("%d.%m.%Y %H:%M", time.localtime(d["baslangic_tarihi"]))
        d["bitis_formatli"] = time.strftime("%d.%m.%Y %H:%M", time.localtime(d["bitis_tarihi"]))
    return rows

ODEME_TOLERANS_SURESI_SN = 30  # Ödeme sonrası ek ücret yazılmayan çıkış toleransı

def arac_ucret_ve_tolerans_hesapla(arac: Dict, simdi: Optional[float] = None) -> Dict:
    """
    Aracın anlık borcunu, ödeme durumunu, 30 saniyelik toleransını ve çıkış iznini hesaplar.
    
    Kurallar:
    0. Aktif Abonman: Borç her zaman 0.00 TL, çıkış her zaman serbesttir (Kural: Abonman Muafiyeti).
    1. Ödeme yapılmadıysa ve borç > 0 ise çıkış engellenir.
    2. Ödeme yapıldıktan sonra 30 saniye boyunca ek ücret DONDURULUR (0 TL ek ücret).
       Bu 30 saniye içinde çıkış serbesttir (bariyer açılır).
    3. Eğer 30 saniye içinde çıkış yapılmazsa:
       Ücret yazmaya devam eder ve o dondurulan 30 saniye de dahil tüm süre normal tarifeden
       hesaplanıp önceden ödenen tutar düşülerek yeni ek borç ortaya çıkar.
       Yeni ek borç ödenene kadar çıkış tekrar ENGELLENİR.
    """
    if simdi is None:
        simdi = time.time()

    giris_zamani = arac.get("giris_zamani", simdi)
    toplam_gecen_sn = max(0.0, simdi - giris_zamani)
    toplam_normal_tarife_ucreti = ucret_hesapla(toplam_gecen_sn)

    # 0. ABONMAN KONTROLÜ: Abonmanlı araçlar için ücret 0 TL ve çıkış serbesttir
    plaka = arac.get("plaka", "")
    abonman = abonman_kontrol(plaka, simdi)
    if abonman:
        return {
            "toplam_gecen_sn": round(toplam_gecen_sn, 1),
            "toplam_normal_ucret": 0.0,
            "odenen_tutar": 0.0,
            "odenecek_ucret": 0.0,
            "odeme_durumu": "odendi",
            "odeme_zamani": simdi,
            "tolerans_aktif": False,
            "kalan_tolerans_sn": 0.0,
            "tolerans_doldu": False,
            "cikis_izni": True,
            "abonman_mi": True,
            "abonman": abonman,
            "durum_etiketi": "ABONMAN_UCRETSIZ",
            "mesaj": f"⭐ Aktif {abonman['paket_ad']} (Kalan: {abonman['kalan_metin']}) - Ücretsiz Geçiş"
        }

    odeme_durumu = arac.get("odeme_durumu") or "odenmedi"
    odeme_zamani = arac.get("odeme_zamani")
    odenen_tutar = float(arac.get("odenen_tutar") or 0.0)

    # Tolerans durumu
    tolerans_aktif = False
    kalan_tolerans_sn = 0.0
    tolerans_doldu = False

    if odeme_durumu == "odendi" and odeme_zamani is not None:
        odeme_sonrasi_gecen = max(0.0, simdi - odeme_zamani)
        if odeme_sonrasi_gecen <= ODEME_TOLERANS_SURESI_SN:
            # 30 SANİYE İÇİNDE: Ücret donduruldu, çıkış serbest!
            tolerans_aktif = True
            kalan_tolerans_sn = round(ODEME_TOLERANS_SURESI_SN - odeme_sonrasi_gecen, 1)
            odenecek_ucret = 0.0
            cikis_izni = True
            durum_etiketi = "ODENDI_TOLERANS_AKTIF"
            mesaj = f"Ödeme tamamlandı. Çıkış için kalan tolerans süresi: {int(kalan_tolerans_sn)} sn"
        else:
            # 30 SANİYE DOLDU! ÇIKIŞ YAPILMADI!
            # Dondurulmuş süre de dahil olmak üzere tarifeye göre ücret yazmaya devam eder.
            # Önceden ödenen tutar toplam ücretten düşülür.
            tolerans_doldu = True
            ek_borc = round(max(0.0, toplam_normal_tarife_ucreti - odenen_tutar), 2)
            if ek_borc > 0.05:
                odenecek_ucret = ek_borc
                cikis_izni = False  # Ödeme alınmadan çıkamaz!
                durum_etiketi = "TOLERANS_DOLDU_BORC_VAR"
                mesaj = f"30 saniyelik çıkış süresi doldu! Yeni ek borç: {odenecek_ucret:.2f} TL (Lütfen ödeyiniz)"
            else:
                odenecek_ucret = 0.0
                cikis_izni = True
                durum_etiketi = "ODENDI"
                mesaj = "Ödeme tamamlandı. Çıkış yapabilirsiniz."
    elif odeme_durumu == "odendi":
        odenecek_ucret = 0.0
        cikis_izni = True
        durum_etiketi = "ODENDI"
        mesaj = "Ödeme tamamlandı. Çıkış yapabilirsiniz."
    else:
        # Hiç ödeme yapılmamış
        kalan_borc = round(max(0.0, toplam_normal_tarife_ucreti - odenen_tutar), 2)
        if kalan_borc > 0.05:
            odenecek_ucret = kalan_borc
            cikis_izni = False  # Çıkış engellenir!
            durum_etiketi = "ODENMEDI"
            mesaj = f"Ödenmemiş borç: {odenecek_ucret:.2f} TL (Ödeme yapılmadan çıkış yapılamaz)"
        else:
            odenecek_ucret = 0.0
            cikis_izni = True
            durum_etiketi = "UCRETSIZ"
            mesaj = "0.00 TL - Çıkış serbest"

    return {
        "toplam_gecen_sn": round(toplam_gecen_sn, 1),
        "toplam_normal_ucret": round(toplam_normal_tarife_ucreti, 2),
        "odenen_tutar": round(odenen_tutar, 2),
        "odenecek_ucret": odenecek_ucret,
        "odeme_durumu": odeme_durumu,
        "odeme_zamani": odeme_zamani,
        "tolerans_aktif": tolerans_aktif,
        "kalan_tolerans_sn": kalan_tolerans_sn,
        "tolerans_doldu": tolerans_doldu,
        "cikis_izni": cikis_izni,
        "abonman_mi": False,
        "abonman": None,
        "durum_etiketi": durum_etiketi,
        "mesaj": mesaj
    }


def plaka_durum_getir(plaka: str) -> Optional[Dict]:
    plaka_norm = plaka.strip().upper().replace(" ", "")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM araclar 
        WHERE REPLACE(plaka, ' ', '') = ? AND durum = 'iceride' 
        ORDER BY id DESC LIMIT 1
    """, (plaka_norm,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def excel_senkronize_et() -> int:
    """Tüm SQLite veritabanı kayıtlarını Excel dosyasına aktarır."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM araclar ORDER BY id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    excel_manager.excel_tum_veritabanindan_guncelle(rows)
    return len(rows)

def arac_giris_yap(plaka: str, giris_zamani: Optional[float] = None, zorla: bool = False) -> Tuple[Dict, bool]:
    """
    Aracı otoparka alır.
    Zaten içerideyse mevcut kaydı döndürür (is_new=False).
    Kapasite doluysa girişi engeller (engellendi=True).
    Yeni girişse is_new=True.
    Abonmanlı araçları otomatik 'odendi' ve 0 TL olarak kaydeder.
    """
    plaka = plaka.strip().upper()
    mevcut = plaka_durum_getir(plaka)
    if mevcut:
        return mevcut, False

    simdi = giris_zamani if giris_zamani is not None else time.time()

    # Kapasite Kontrolü (Zorla giriş değilse)
    if not zorla:
        izin, mesaj, yerlesim = kapasite_giris_izni_kontrol(plaka, simdi)
        if not izin:
            engelleme_kaydi = {
                "plaka": plaka,
                "engellendi": True,
                "durum": "DOLU",
                "mesaj": mesaj,
                "ucret": 0.0,
                "odenecek_ucret": 0.0
            }
            return engelleme_kaydi, False

    abonman = abonman_kontrol(plaka, simdi)
    abonman_mi = 1 if abonman else 0
    musteri_turu = abonman["paket_ad"] if abonman else "Standart"
    odeme_durumu = "odendi" if abonman else "odenmedi"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO araclar (plaka, giris_zamani, durum, ucret, odenen_tutar, odeme_durumu, abonman_mi, musteri_turu)
        VALUES (?, ?, 'iceride', 0, 0, ?, ?, ?)
    """, (plaka, simdi, odeme_durumu, abonman_mi, musteri_turu))
    conn.commit()
    yeni_id = cursor.lastrowid
    
    cursor.execute("SELECT * FROM araclar WHERE id = ?", (yeni_id,))
    row = dict(cursor.fetchone())
    conn.close()

    # Excel'e anında satır ekle
    try:
        excel_manager.excel_kayit_ekle_veya_guncelle(row)
    except Exception as e:
        print(f">> [EXCEL HATA] Giriş kaydedilemedi: {e}")

    return row, True

def arac_cikis_yap(plaka: str, cikis_zamani: Optional[float] = None, zorla: bool = False) -> Tuple[bool, str, Optional[Dict]]:
    """
    İçerideki aracı çıkartır.
    Ödeme yapılmamışsa veya 30 sn tolerans dolup ek borç oluşmuşsa ÇIKIŞI ENGELLER!
    Abonmanlı araçlar doğrudan 0 TL ile çıkış yapar.
    Dönüş: (basarili: bool, mesaj: str, kayit_dict: Optional[Dict])
    """
    plaka = plaka.strip().upper()
    mevcut = plaka_durum_getir(plaka)
    if not mevcut:
        return False, f"[{plaka}] plakalı araç şu anda otoparkta değil.", None

    simdi = cikis_zamani if cikis_zamani is not None else time.time()
    detay = arac_ucret_ve_tolerans_hesapla(mevcut, simdi)

    # ÖDEME KONTROLÜ: Abonmanlılar veya borcu 0.05 TL'den az olanlar ASLA ENGELLENEMEZ!
    odenecek_borc = float(detay.get("odenecek_ucret", 0.0) or 0.0)
    is_abonman = bool(detay.get("abonman_mi")) or bool(abonman_kontrol(plaka, simdi))
    borc_engeli_var = (not is_abonman) and (odenecek_borc > 0.05) and (not detay.get("cikis_izni", True))
    if borc_engeli_var and not zorla:
        # ÇIKIŞ ENGELLENDİ!
        mevcut_guncel = dict(mevcut)
        mevcut_guncel.update(detay)
        return False, detay["mesaj"], mevcut_guncel

    # ÇIKIŞA İZİN VERİLDİ!
    gecen_sure = detay["toplam_gecen_sn"]
    nihai_ucret = 0.0 if detay.get("abonman_mi") else max(detay["toplam_normal_ucret"], detay["odenen_tutar"])
    musteri_turu = detay["abonman"]["paket_ad"] if (detay.get("abonman_mi") and detay.get("abonman")) else (mevcut.get("musteri_turu") or "Standart")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE araclar 
        SET cikis_zamani = ?, durum = 'disarida', toplam_sure_sn = ?, ucret = ?, odeme_durumu = 'odendi', musteri_turu = ?
        WHERE id = ?
    """, (simdi, gecen_sure, nihai_ucret, musteri_turu, mevcut["id"]))
    conn.commit()

    cursor.execute("SELECT * FROM araclar WHERE id = ?", (mevcut["id"],))
    guncel = dict(cursor.fetchone())
    conn.close()

    # Excel'deki satırı çıkış saati, süre ve ücret ile güncelle
    try:
        excel_manager.excel_kayit_ekle_veya_guncelle(guncel)
    except Exception as e:
        print(f">> [EXCEL HATA] Çıkış güncellenemedi: {e}")

    cikis_mesaj = f"⭐ Abonman Geçişi: 0.00 TL (Kalan: {detay['abonman']['kalan_metin']})" if detay.get("abonman_mi") else "Çıkış başarılı. İyi yolculuklar!"
    return True, cikis_mesaj, guncel

def abonman_satin_al(plaka: str, paket_tipi: str, kart_bilgisi: Dict, email: Optional[str] = None) -> Tuple[bool, str, Optional[Dict]]:
    """
    Sanal kredi kartı ile haftalık veya aylık abonman satın alır.
    Varsa mevcut abonmanın süresinin üstüne ekler.
    Eğer e-posta verilmişse müşteriyi sisteme otomatik kaydeder.
    """
    plaka_temiz = plaka.strip().upper()
    plaka_norm = plaka_temiz.replace(" ", "")
    paket = ABONMAN_PAKETLERI.get(paket_tipi.lower())
    if not paket:
        return False, f"Geçersiz abonman paketi: '{paket_tipi}'", None

    simdi = time.time()
    
    # Eğer müşteri kayıtlı değilse ve e-posta verildiyse müşteriler tablosuna kaydet/güncelle
    if email and "@" in email:
        email_temiz = email.strip().lower()
        conn_m = get_connection()
        c_m = conn_m.cursor()
        c_m.execute("""
            INSERT OR REPLACE INTO musteriler (plaka, email, dogrulandi, kayit_tarihi)
            VALUES (?, ?, 1, ?)
        """, (plaka_temiz, email_temiz, simdi))
        conn_m.commit()
        conn_m.close()

    # Eğer zaten aktif abonmanı varsa süresine ekle
    mevcut = abonman_kontrol(plaka_temiz, simdi)
    if mevcut:
        baslangic = mevcut["bitis_tarihi"]
        bitis = baslangic + (paket["gun"] * 86400)
    else:
        baslangic = simdi
        bitis = simdi + (paket["gun"] * 86400)

    kart_no = str(kart_bilgisi.get("kart_no", "4543 **** **** 1234")).replace(" ", "")
    son4 = kart_no[-4:] if len(kart_no) >= 4 else "1234"

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO abonmanlar (plaka, paket_tipi, paket_ad, ucret, baslangic_tarihi, bitis_tarihi, odeme_zamani, kart_son4, aktif)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (plaka_temiz, paket["id"], paket["ad"], paket["ucret"], baslangic, bitis, simdi, son4))
    abonman_id = c.lastrowid

    # Otoparkta içerideyse kaydını abonmana çevir
    c.execute("""
        UPDATE araclar 
        SET abonman_mi = 1, musteri_turu = ?, odeme_durumu = 'odendi', ucret = 0
        WHERE REPLACE(plaka, ' ', '') = ? AND durum = 'iceride'
    """, (paket["ad"], plaka_norm))

    conn.commit()
    conn.close()

    try:
        excel_senkronize_et()
    except Exception:
        pass

    makbuz = {
        "abonman_id": abonman_id,
        "makbuz_no": f"ABN-{int(simdi)}-{abonman_id}",
        "plaka": plaka_temiz,
        "paket_id": paket["id"],
        "paket_ad": paket["ad"],
        "tutar": paket["ucret"],
        "odeme_zamani": simdi,
        "baslangic_tarihi": baslangic,
        "bitis_tarihi": bitis,
        "gecerlilik": f"{paket['gun']} Gün",
        "bitis_formatli": time.strftime("%d.%m.%Y %H:%M", time.localtime(bitis)),
        "kart_son4": son4
    }

    # Gerçek e-posta gönderimi
    musteri = musteri_getir(plaka_temiz)
    hedef_email = (musteri.get("email") if musteri else None) or email
    if hedef_email:
        makbuz["email"] = hedef_email
        mailer.abonman_onay_epostasi_gonder(hedef_email, plaka_temiz, makbuz)

    print(f">> [ABONMAN SATIN ALINDI] [{plaka_temiz}] {paket['ad']} aktive edildi. Bitiş: {time.ctime(bitis)}")
    return True, f"{paket['ad']} başarıyla satın alındı! {paket['gun']} gün boyunca sınırsız ücretsiz geçiş hakkınız tanımlandı.", makbuz

def pazarlama_analizi_yap() -> List[Dict]:
    """
    Otopark geçmişini inceler.
    Abonmanı olmayan ancak sık gelen (veya yüksek süre/harcama yapan) araçları filtreler,
    onlara özel tasarruf analizi ve paket önerisi oluşturur.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT 
            plaka,
            COUNT(*) as ziyaret_sayisi,
            COALESCE(SUM(toplam_sure_sn), 0) as toplam_sure_sn,
            COALESCE(SUM(ucret), 0) as toplam_harcama,
            MAX(cikis_zamani) as son_ziyaret
        FROM araclar
        WHERE durum = 'disarida'
        GROUP BY plaka
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    simdi = time.time()
    adaylar = []

    for d in rows:
        plaka = d["plaka"]
        # Eğer zaten aktif abonmanı varsa listeye alma
        if abonman_kontrol(plaka, simdi):
            continue

        ziyaret = int(d["ziyaret_sayisi"])
        harcama = float(d["toplam_harcama"])
        sure_sn = float(d["toplam_sure_sn"])

        # Sık gelen kriteri: en az 2 ziyaret VEYA en az 10 TL harcama VEYA en az 30 sn kalış
        if ziyaret >= 2 or harcama >= 10.0 or sure_sn >= 30:
            musteri = musteri_getir(plaka)
            email = musteri["email"] if musteri else None

            # Öneri mantığı
            if ziyaret >= 4 or harcama >= 50.0:
                oneri = ABONMAN_PAKETLERI["aylik"]
                tahmini_aylik_masraf = max(harcama * 3, oneri["ucret"] * 1.5)
                tasarruf_tl = round(tahmini_aylik_masraf - oneri["ucret"], 2)
                tasarruf_yuzde = 40
            else:
                oneri = ABONMAN_PAKETLERI["haftalik"]
                tahmini_haftalik_masraf = max(harcama * 2, oneri["ucret"] * 1.3)
                tasarruf_tl = round(tahmini_haftalik_masraf - oneri["ucret"], 2)
                tasarruf_yuzde = 30

            adaylar.append({
                "plaka": plaka,
                "email": email,
                "kayitli_musteri_mi": bool(musteri),
                "ziyaret_sayisi": ziyaret,
                "toplam_harcama": round(harcama, 2),
                "toplam_sure_sn": round(sure_sn, 1),
                "onerilen_paket": oneri["id"],
                "onerilen_paket_ad": oneri["ad"],
                "onerilen_paket_ucret": oneri["ucret"],
                "tahmini_tasarruf_tl": max(45.0, tasarruf_tl),
                "tasarruf_yuzdesi": tasarruf_yuzde,
                "neden": f"{ziyaret} ziyaret • {harcama:.2f} ₺ harcama"
            })

    adaylar.sort(key=lambda x: (x["toplam_harcama"], x["ziyaret_sayisi"]), reverse=True)
    return adaylar


def toggle_plaka(plaka: str, zorla: bool = False) -> Tuple[str, Dict]:
    """
    Plaka içerideyse çıkış yapmayı dener (ödeme kontrolü ile).
    Dışarıdaysa veya hiç yoksa giriş yapar.
    Dönüş: ('GIRIS' | 'CIKIS' | 'CIKIS_ENGELLENDI' | 'GIRIS_ENGELLENDI', kayit_dict)
    """
    plaka = plaka.strip().upper()
    mevcut = plaka_durum_getir(plaka)
    if mevcut:
        basarili, mesaj, kayit = arac_cikis_yap(plaka, zorla=zorla)
        if not basarili:
            kayit_kopya = dict(kayit) if kayit else {}
            kayit_kopya["mesaj"] = mesaj
            return "CIKIS_ENGELLENDI", kayit_kopya
        return "CIKIS", kayit
    else:
        giris_kaydi, yeni = arac_giris_yap(plaka, zorla=zorla)
        if giris_kaydi and giris_kaydi.get("engellendi"):
            return "GIRIS_ENGELLENDI", giris_kaydi
        return "GIRIS", giris_kaydi

def get_icerideki_araclar() -> List[Dict]:
    """
    Halen içeride olan tüm araçları anlık süre, borç ve tolerans bilgisiyle listeler.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM araclar 
        WHERE durum = 'iceride' 
        ORDER BY giris_zamani DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    simdi = time.time()
    sonuclar = []
    for r in rows:
        d = dict(r)
        detay = arac_ucret_ve_tolerans_hesapla(d, simdi)
        d["gecen_sure_sn"] = detay["toplam_gecen_sn"]
        d["anlik_ucret"] = detay["odenecek_ucret"]
        d["toplam_normal_ucret"] = detay["toplam_normal_ucret"]
        d["odenen_tutar"] = detay["odenen_tutar"]
        d["tolerans_aktif"] = detay["tolerans_aktif"]
        d["kalan_tolerans_sn"] = detay["kalan_tolerans_sn"]
        d["tolerans_doldu"] = detay["tolerans_doldu"]
        d["cikis_izni"] = detay["cikis_izni"]
        d["durum_mesaj"] = detay["mesaj"]
        sonuclar.append(d)
    return sonuclar


def get_gecmis_araclar(limit: int = 50) -> List[Dict]:
    """Çıkış yapmış son araçlar."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM araclar 
        WHERE durum = 'disarida' 
        ORDER BY cikis_zamani DESC 
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_istatistikler() -> Dict:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM araclar WHERE durum = 'iceride'")
    icerideki_sayi = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*), COALESCE(SUM(ucret), 0) FROM araclar WHERE durum = 'disarida'")
    cikan_row = cursor.fetchone()
    cikan_sayi = cikan_row[0]
    toplam_hasilat = float(cikan_row[1])

    conn.close()

    # İçeridekilerin de anlık potansiyel hasılatı
    iceridekiler = get_icerideki_araclar()
    anlik_icerideki_tutar = sum(a["anlik_ucret"] for a in iceridekiler)

    saniye, birim_ucret = tarife_getir()
    kapasite = kapasite_durumu_getir()
    return {
        "icerideki_arac_sayisi": icerideki_sayi,
        "cikis_yapan_arac_sayisi": cikan_sayi,
        "toplam_tahsil_edilen": toplam_hasilat,
        "anlik_icerideki_tutar": anlik_icerideki_tutar,
        "tarife_saniye": saniye,
        "tarife_ucret": birim_ucret,
        "tarife": f"Her {saniye} saniye = {birim_ucret:.2f} TL",
        "kapasite": kapasite
    }

def sistemi_sifirla(musteriler_silinsin: bool = True):
    """Tüm araç kayıtlarını, sayaçları, doğrulama kodlarını, abonmanları ve Excel dosyasını sıfırlar."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM araclar")
    cursor.execute("DELETE FROM dogrulama_kodlari")
    cursor.execute("DELETE FROM abonmanlar")
    if musteriler_silinsin:
        cursor.execute("DELETE FROM musteriler")
    try:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('araclar', 'musteriler', 'dogrulama_kodlari', 'abonmanlar')")
    except Exception:
        pass
    conn.commit()
    conn.close()
    kapasite_ayarlari_guncelle(VARSAYILAN_KAPASITE_NORMAL, VARSAYILAN_KAPASITE_ABONMAN)
    excel_senkronize_et()
    print(">> [SIFIRLA] Tüm araç kayıtları, sayaçlar, abonmanlar ve Excel dosyası sıfırlandı.")



# =========================================================================
# MÜŞTERİ PANELİ & DOĞRULAMA (OTP) FONKSİYONLARI
# =========================================================================

def maskele_email(email: str) -> str:
    """E-postayı 'm***y@domain.com' şeklinde güvenli maskeler."""
    if not email or "@" not in email:
        return email
    kullanici, domain = email.split("@", 1)
    if len(kullanici) <= 2:
        maskeli_kullanici = kullanici[0] + "***"
    else:
        maskeli_kullanici = kullanici[0] + "***" + kullanici[-1]
    return f"{maskeli_kullanici}@{domain}"

def musteri_getir(plaka: str) -> Optional[Dict]:
    """Plakaya göre kayıtlı müşteriyi getirir (boşluk duyarsız)."""
    plaka_norm = plaka.strip().upper().replace(" ", "")
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM musteriler WHERE REPLACE(plaka, ' ', '') = ?", (plaka_norm,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def musteri_kod_talep_et(plaka: str, email: Optional[str] = None, islem_turu: str = "giris") -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Kayıt veya Giriş için 6 haneli doğrulama kodu üretir ve e-postaya gönderir.
    Dönüş: (basarili, mesaj, maskelenmis_email, kod)
    """
    plaka_temiz = plaka.strip().upper()
    plaka_norm = plaka_temiz.replace(" ", "")
    if not plaka_norm or len(plaka_norm) < 4:
        return False, "Geçersiz plaka formatı!", None, None

    mevcut_musteri = musteri_getir(plaka_temiz)

    if islem_turu == "giris":
        if not mevcut_musteri:
            return False, f"[{plaka_temiz}] plakalı araç henüz kayıtlı değil. Lütfen önce 'İlk Kayıt' sekmesinden kaydolun.", None, None
        hedef_email = mevcut_musteri["email"]
    else: # kayit
        if mevcut_musteri:
            return False, f"[{plaka_temiz}] plakası zaten kayıtlı! 'Giriş Yap' sekmesinden giriş yapabilirsiniz.", None, None
        if not email or "@" not in email:
            return False, "Lütfen geçerli bir e-posta adresi girin!", None, None
        hedef_email = email.strip().lower()

    # 6 Haneli OTP Kod Üret
    kod = mailer.kod_uret()
    simdi = time.time()
    son_gecerlilik = simdi + 300 # 5 Dakika geçerli

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO dogrulama_kodlari (plaka, email, kod, son_gecerlilik, kullanildi, islem_turu, olusturma_zamani)
        VALUES (?, ?, ?, ?, 0, ?, ?)
    """, (plaka_temiz, hedef_email, kod, son_gecerlilik, islem_turu, simdi))
    conn.commit()
    conn.close()

    # E-posta Gönder (veya test terminaline bas)
    mailer.eposta_gonder(hedef_email, plaka_temiz, kod, islem_turu)

    maskeli = maskele_email(hedef_email)
    return True, f"Doğrulama kodu {maskeli} adresine gönderildi.", maskeli, kod

def musteri_kod_dogrula(plaka: str, kod: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    Kullanıcının girdiği 6 haneli kodu kontrol eder.
    Doğruysa hesabı aktifleştirir ve müşteri bilgilerini döner.
    """
    plaka_temiz = plaka.strip().upper()
    plaka_norm = plaka_temiz.replace(" ", "")
    kod = kod.strip()
    simdi = time.time()

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM dogrulama_kodlari 
        WHERE REPLACE(plaka, ' ', '') = ? AND kod = ? AND kullanildi = 0 AND son_gecerlilik > ?
        ORDER BY id DESC LIMIT 1
    """, (plaka_norm, kod, simdi))
    kayit = c.fetchone()

    if not kayit:
        conn.close()
        return False, "Doğrulama kodu hatalı veya süresi (5 dk) dolmuş!", None

    kayit_dict = dict(kayit)
    # Kodu kullanıldı olarak işaretle
    c.execute("UPDATE dogrulama_kodlari SET kullanildi = 1 WHERE id = ?", (kayit_dict["id"],))

    # Eğer kayıt işlemiyse musteriler tablosuna ekle
    if kayit_dict["islem_turu"] == "kayit":
        c.execute("""
            INSERT OR REPLACE INTO musteriler (plaka, email, dogrulandi, kayit_tarihi)
            VALUES (?, ?, 1, ?)
        """, (plaka_temiz, kayit_dict["email"], simdi))

    conn.commit()

    # Güncel müşteri profilini getir
    c.execute("SELECT * FROM musteriler WHERE REPLACE(plaka, ' ', '') = ?", (plaka_norm,))
    musteri_row = c.fetchone()
    conn.close()

    return True, "Doğrulama başarılı. Giriş yapıldı!", dict(musteri_row) if musteri_row else None

def musteri_arac_durum(plaka: str) -> Dict:
    """Müşteri için aracının anlık otopark durumunu, canlı borcunu, 30 sn toleransını ve ödeme durumunu döner."""
    plaka_temiz = plaka.strip().upper()
    plaka_norm = plaka_temiz.replace(" ", "")
    musteri = musteri_getir(plaka_temiz)
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM araclar WHERE REPLACE(plaka, ' ', '') = ? ORDER BY id DESC LIMIT 1", (plaka_norm,))
    son_arac = c.fetchone()
    conn.close()

    simdi = time.time()
    saniye, birim_ucret = tarife_getir()
    abonman = abonman_kontrol(plaka_temiz, simdi)
    pazarlama_oneri = None
    if not abonman:
        for ad in pazarlama_analizi_yap():
            if ad["plaka"] == plaka_temiz:
                pazarlama_oneri = ad
                break

    if not son_arac:
        return {
            "kayitli_mi": bool(musteri),
            "plaka": plaka_temiz,
            "durum": "yok",
            "durum_metin": "Otoparkta Değil",
            "iceride_mi": False,
            "anlik_sure_sn": 0,
            "anlik_ucret": 0.0,
            "odeme_durumu": "yok",
            "cikis_izni": True,
            "tolerans_aktif": False,
            "kalan_tolerans_sn": 0,
            "tolerans_doldu": False,
            "abonman": abonman,
            "abonman_mi": bool(abonman),
            "pazarlama_oneri": pazarlama_oneri,
            "tarife": f"Her {saniye} sn = {birim_ucret:.2f} TL",
            "tarife_saniye": saniye,
            "tarife_ucret": birim_ucret
        }

    d = dict(son_arac)
    iceride_mi = (d["durum"] == "iceride")

    if iceride_mi:
        detay = arac_ucret_ve_tolerans_hesapla(d, simdi)
        gecen = detay["toplam_gecen_sn"]
        odenecek_ucret = detay["odenecek_ucret"]
        durum_metin = f"Şu An Otoparkta ({abonman['paket_ad']})" if abonman else "Şu An Otoparkta"
        tolerans_aktif = detay["tolerans_aktif"]
        kalan_tolerans = detay["kalan_tolerans_sn"]
        tolerans_doldu = detay["tolerans_doldu"]
        cikis_izni = detay["cikis_izni"]
        odeme_durumu = detay["odeme_durumu"]
        odendi_mi = (tolerans_aktif or (odeme_durumu == "odendi" and not tolerans_doldu) or bool(abonman))
    else:
        gecen = d.get("toplam_sure_sn", 0)
        odenecek_ucret = 0.0
        durum_metin = "Dışarıda (Son Park Tamamlandı)"
        tolerans_aktif = False
        kalan_tolerans = 0
        tolerans_doldu = False
        cikis_izni = True
        odeme_durumu = d.get("odeme_durumu") or "odendi"
        odendi_mi = True

    return {
        "kayitli_mi": bool(musteri),
        "plaka": plaka_temiz,
        "arac_id": d["id"],
        "durum": d["durum"],
        "durum_metin": durum_metin,
        "iceride_mi": iceride_mi,
        "giris_zamani": d["giris_zamani"],
        "cikis_zamani": d.get("cikis_zamani"),
        "anlik_sure_sn": round(gecen, 1),
        "anlik_ucret": round(odenecek_ucret, 2),
        "odeme_durumu": odeme_durumu,
        "odendi_mi": odendi_mi,
        "tolerans_aktif": tolerans_aktif,
        "kalan_tolerans_sn": kalan_tolerans,
        "tolerans_doldu": tolerans_doldu,
        "cikis_izni": cikis_izni,
        "abonman": abonman,
        "abonman_mi": bool(abonman),
        "pazarlama_oneri": pazarlama_oneri,
        "durum_mesaji": detay["mesaj"] if iceride_mi else "Tamamlandı",
        "tarife": f"Her {saniye} sn = {birim_ucret:.2f} TL",
        "tarife_saniye": saniye,
        "tarife_ucret": birim_ucret
    }


def musteri_arac_odeme_yap(plaka: str, kart_bilgisi: Dict) -> Tuple[bool, str, Optional[Dict]]:
    """
    Müşterinin içerideki aracının otopark borcunu sanal kredi kartı ile tahsil eder.
    Ödeme tamamlandıktan sonra 30 saniyelik tolerans süresi başlar.
    """
    plaka_temiz = plaka.strip().upper()
    plaka_norm = plaka_temiz.replace(" ", "")

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM araclar WHERE REPLACE(plaka, ' ', '') = ? AND durum = 'iceride' ORDER BY id DESC LIMIT 1", (plaka_norm,))
    son_arac = c.fetchone()
    conn.close()

    if not son_arac:
        return False, "Ödenecek aktif bir otopark kaydı bulunamadı (Araç otoparkta değil).", None

    arac_dict = dict(son_arac)
    simdi = time.time()
    detay = arac_ucret_ve_tolerans_hesapla(arac_dict, simdi)

    if detay["tolerans_aktif"]:
        return False, f"Ücretiniz zaten ödendi! Kalan çıkış süreniz: {int(detay['kalan_tolerans_sn'])} sn.", None

    odenecek = detay["odenecek_ucret"]
    if odenecek <= 0.0:
        return False, "Ödenecek bir otopark borcunuz bulunmuyor (0.00 TL).", None

    yeni_toplam_odenen = detay["odenen_tutar"] + odenecek

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE araclar 
        SET odeme_durumu = 'odendi', odeme_zamani = ?, odenen_tutar = ?, ucret = ?
        WHERE id = ?
    """, (simdi, yeni_toplam_odenen, yeni_toplam_odenen, arac_dict["id"]))
    conn.commit()
    conn.close()

    # Excel'e de yansıt
    try:
        excel_manager.excel_senkronize_et()
    except Exception:
        pass

    kart_no = str(kart_bilgisi.get("kart_no", "4543 **** **** 1234")).replace(" ", "")
    son4 = kart_no[-4:] if len(kart_no) >= 4 else "1234"

    makbuz = {
        "makbuz_no": f"MAK-{int(simdi)}-{arac_dict['id']}",
        "plaka": plaka_temiz,
        "odenen_tutar": odenecek,
        "toplam_odenen": yeni_toplam_odenen,
        "odeme_zamani": simdi,
        "odeme_yontemi": f"Kredi Kartı (**** {son4})",
        "tolerans_sn": ODEME_TOLERANS_SURESI_SN,
        "durum": "Ödendi"
    }

    print(f">> [ONLINE ODEME] [{plaka_temiz}] Sanal Kartla {odenecek:.2f} TL tahsil edildi. 30 sn tolerans basladi. Makbuz: {makbuz['makbuz_no']}")
    return True, f"{odenecek:.2f} TL tutarındaki ödemeniz başarıyla alındı. 30 saniye içinde çıkış yapabilirsiniz.", makbuz


init_db()
