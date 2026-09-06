import asyncio
import json
import socket
import io
import time
import sys
from typing import Set, Optional, Dict, List
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel
import qrcode

import database
import excel_manager
import mailer


# Windows konsol UTF-8 desteği
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

connected_websockets: Set[WebSocket] = set()

async def periodic_broadcast_loop():
    """Her 1 saniyede bir süre ve ücretlerin canlı akması için veriyi tüm telefonlara gönderir."""
    while True:
        await asyncio.sleep(1)
        if connected_websockets:
            durum_mesaji = json.dumps({
                "type": "DURUM_GUNCELLEME",
                "iceridekiler": database.get_icerideki_araclar(),
                "istatistikler": database.get_istatistikler(),
                "server_time": time.time()
            })
            dead = set()
            for ws in list(connected_websockets):
                try:
                    await ws.send_text(durum_mesaji)
                except Exception:
                    dead.add(ws)
            connected_websockets.difference_update(dead)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(periodic_broadcast_loop())
    yield
    task.cancel()

app = FastAPI(title="ParkOS - Akıllı Otopark İşletim Sistemi", lifespan=lifespan)

# Statik dosyaları bağla
app.mount("/static", StaticFiles(directory="static"), name="static")

class ManuelIslemReq(BaseModel):
    plaka: str
    islem: str = "toggle"  # "giris", "cikis", "toggle"
    zorla: bool = False


class TarifeReq(BaseModel):
    saniye: int
    ucret: float

class MusteriKayitKodReq(BaseModel):
    plaka: str
    email: str

class MusteriGirisKodReq(BaseModel):
    plaka: str

class MusteriKodDogrulaReq(BaseModel):
    plaka: str
    kod: str

class MusteriOdemeReq(BaseModel):
    plaka: str
    kart_no: str
    skt: str
    cvv: str
    kart_sahibi: str

class AbonmanSatinAlReq(BaseModel):
    plaka: str
    paket_tipi: str  # "haftalik" veya "aylik"
    email: Optional[str] = None
    kart_no: str = ""
    skt: str = ""
    cvv: str = ""
    kart_sahibi: str = ""


class PazarlamaEpostaReq(BaseModel):
    plaka: str

class KapasiteGuncelleReq(BaseModel):
    normal: int
    abonman: int

class KameraOlayReq(BaseModel):
    tip: str
    plaka: str
    kayit: Optional[Dict] = None
    mesaj: str = ""


def get_local_ip() -> str:
    """Cihazın yerel ağ IP adresini bulur."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

async def broadcast_event(event_type: str, data: dict):
    """Tüm bağlı mobil cihazlara anlık event gönderir."""
    if not connected_websockets:
        return
    message = json.dumps({
        "type": event_type,
        "timestamp": time.time(),
        "data": data
    })
    dead_sockets = set()
    for ws in list(connected_websockets):
        try:
            await ws.send_text(message)
        except Exception:
            dead_sockets.add(ws)
    connected_websockets.difference_update(dead_sockets)

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")

@app.get("/musteri")
async def get_musteri_page():
    return FileResponse("static/musteri.html")

@app.get("/api/durum")
async def get_durum():
    return {
        "iceridekiler": database.get_icerideki_araclar(),
        "istatistikler": database.get_istatistikler(),
        "server_time": time.time()
    }

@app.get("/api/gecmis")
async def get_gecmis(limit: int = 50):
    return {
        "gecmis": database.get_gecmis_araclar(limit=limit)
    }

@app.get("/api/bilgi")
async def get_bilgi():
    ip = get_local_ip()
    port = 8000
    mobil_url = f"http://{ip}:{port}"
    return {
        "local_ip": ip,
        "port": port,
        "mobil_url": mobil_url,
        "tarife": database.get_istatistikler()["tarife"]
    }

@app.post("/api/kamera-olay")
async def post_kamera_olay(req: KameraOlayReq):
    kapasite = database.kapasite_durumu_getir()
    await broadcast_event(req.tip, {
        "plaka": req.plaka,
        "kayit": req.kayit,
        "kapasite": kapasite,
        "mesaj": req.mesaj
    })
    return {"status": "ok"}

@app.post("/api/manuel-islem")
async def post_manuel_islem(req: ManuelIslemReq):
    plaka = req.plaka.strip().upper()
    if not plaka:
        return {"error": "Geçersiz plaka"}
    
    islem_turu = req.islem.lower()
    zorla = req.zorla
    
    if islem_turu == "giris":
        kayit, yeni = database.arac_giris_yap(plaka, zorla=zorla)
        if kayit and kayit.get("engellendi"):
            tip = "GIRIS_ENGELLENDI"
            mesaj = kayit.get("mesaj", "Otopark kapasitesi dolu!")
        else:
            tip = "GIRIS" if yeni else "ZATEN_ICERIDE"
            mesaj = f"{plaka} giriş yaptı!"
    elif islem_turu == "cikis":
        mevcut = database.plaka_durum_getir(plaka)
        if not mevcut:
            return {
                "durum": "ZATEN_DISARIDA",
                "mesaj": f"[{plaka}] plakalı araç otoparkta değil.",
                "kayit": None,
                "kapasite": database.kapasite_durumu_getir(),
                "iceridekiler": database.get_icerideki_araclar()
            }
        
        basarili, mesaj, kayit = database.arac_cikis_yap(plaka, zorla=zorla)
        if basarili:
            tip = "CIKIS"
        else:
            borc = kayit.get("odenecek_ucret", 0.0) if kayit else 0.0
            if borc > 0.05:
                tip = "CIKIS_ENGELLENDI"
            else:
                # Borç yoksa (0.00 TL) asla çıkışı engelleme!
                basarili, mesaj, kayit = database.arac_cikis_yap(plaka, zorla=True)
                tip = "CIKIS"
    elif islem_turu == "cikis_engellendi":
        mevcut = database.plaka_durum_getir(plaka)
        if not mevcut:
            tip = "ZATEN_DISARIDA"
            mesaj = f"[{plaka}] araç otoparkta değil."
            kayit = None
        else:
            detay = database.arac_ucret_ve_tolerans_hesapla(mevcut)
            kayit = {**mevcut, **detay}
            borc = kayit.get('odenecek_ucret', 0.0)
            if borc > 0.05:
                tip = "CIKIS_ENGELLENDI"
                mesaj = f"[{plaka}] Çıkış Engellendi! Ödenmemiş {borc:.2f} TL borç var."
            else:
                basarili, mesaj, kayit = database.arac_cikis_yap(plaka, zorla=True)
                tip = "CIKIS"
    else:  # toggle
        tip, kayit = database.toggle_plaka(plaka, zorla=zorla)
        mesaj = kayit.get("mesaj", "")
        
    # Anlık WebSocket Bildirimi Fırlat
    if tip in ["GIRIS", "CIKIS", "CIKIS_ENGELLENDI", "GIRIS_ENGELLENDI"]:
        await broadcast_event(tip, {
            "plaka": plaka,
            "kayit": kayit,
            "kapasite": database.kapasite_durumu_getir(),
            "mesaj": mesaj or (f"{plaka} giriş yaptı!" if tip == "GIRIS" else f"{plaka} çıkış yaptı! Tutar: {kayit.get('ucret', 0):.2f} TL")
        })

    return {
        "durum": tip,
        "mesaj": mesaj,
        "kayit": kayit,
        "kapasite": database.kapasite_durumu_getir(),
        "iceridekiler": database.get_icerideki_araclar()
    }

@app.get("/api/tarife")
async def get_tarife():
    saniye, ucret = database.tarife_getir()
    return {
        "saniye": saniye,
        "ucret": ucret,
        "tarife": f"Her {saniye} saniye = {ucret:.2f} TL"
    }

@app.post("/api/tarife")
async def post_tarife(req: TarifeReq):
    saniye, ucret = database.tarife_guncelle(req.saniye, req.ucret)
    yeni_tarife_str = f"Her {saniye} saniye = {ucret:.2f} TL"
    print(f"\n>> [TARIFE GUNCELLENDI] Aktif Tarife: {yeni_tarife_str}\n")
    
    # Tüm bağlı mobil cihazlara anında yayın yap
    await broadcast_event("TARIFE_GUNCELLEME", {
        "tarife_saniye": saniye,
        "tarife_ucret": ucret,
        "tarife": yeni_tarife_str,
        "mesaj": f"Tarife güncellendi: {yeni_tarife_str}"
    })
    
    return {
        "status": "ok",
        "saniye": saniye,
        "ucret": ucret,
        "tarife": yeni_tarife_str,
        "iceridekiler": database.get_icerideki_araclar(),
        "istatistikler": database.get_istatistikler()
    }

@app.get("/api/kapasite")
async def get_kapasite():
    return {
        "status": "ok",
        "kapasite": database.kapasite_durumu_getir()
    }

@app.post("/api/kapasite/guncelle")
async def post_kapasite_guncelle(req: KapasiteGuncelleReq):
    database.kapasite_ayarlari_guncelle(req.normal, req.abonman)
    durum = database.kapasite_durumu_getir()
    await broadcast_event("KAPASITE_GUNCELLEME", {
        "kapasite": durum,
        "mesaj": f"Kapasite güncellendi: {req.normal} Normal, {req.abonman} Abonman (Toplam: {durum['kapasite']['toplam']})"
    })
    return {
        "status": "ok",
        "kapasite": durum
    }

@app.get("/api/excel-indir")
async def get_excel_indir():
    # Veritabanındaki tüm güncel kayıtları çek
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM araclar ORDER BY id ASC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    # Eğer dosya kilitli değilse diske de kaydet
    database.excel_senkronize_et()

    # Excel programı açık olsa bile bellekten anında indir
    buffer = excel_manager.excel_bytes_uret(rows)
    headers = {
        'Content-Disposition': 'attachment; filename="otopark_kayitlari.xlsx"'
    }
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )

@app.post("/api/excel-senkronize")
async def post_excel_senkronize():
    toplam = database.excel_senkronize_et()
    return {
        "status": "ok",
        "mesaj": f"{toplam} adet kayıt Excel'e başarıyla senkronize edildi.",
        "dosya": excel_manager.EXCEL_DOSYA_ADI
    }

@app.post("/api/temizle")
async def post_temizle():
    database.sistemi_sifirla()
    await broadcast_event("TEMIZLE", {"mesaj": "Veritabanı ve Excel sıfırlandı."})
    return {
        "status": "ok",
        "mesaj": "Tüm veriler, sayaçlar ve Excel sıfırlandı.",
        "iceridekiler": [],
        "istatistikler": database.get_istatistikler()
    }

# =========================================================================
# MÜŞTERİ PANELİ API ROTALARI
# =========================================================================

@app.post("/api/musteri/kayit-kod-iste")
async def post_musteri_kayit_kod(req: MusteriKayitKodReq):
    basarili, mesaj, maskeli, test_kod = database.musteri_kod_talep_et(req.plaka, req.email, "kayit")
    return {
        "status": "ok" if basarili else "error",
        "mesaj": mesaj,
        "maskeli_email": maskeli,
        "test_kod": test_kod
    }

@app.post("/api/musteri/giris-kod-iste")
async def post_musteri_giris_kod(req: MusteriGirisKodReq):
    basarili, mesaj, maskeli, test_kod = database.musteri_kod_talep_et(req.plaka, None, "giris")
    return {
        "status": "ok" if basarili else "error",
        "mesaj": mesaj,
        "maskeli_email": maskeli,
        "test_kod": test_kod
    }

@app.post("/api/musteri/kod-dogrula")
async def post_musteri_kod_dogrula(req: MusteriKodDogrulaReq):
    basarili, mesaj, musteri = database.musteri_kod_dogrula(req.plaka, req.kod)
    return {
        "status": "ok" if basarili else "error",
        "mesaj": mesaj,
        "musteri": musteri
    }

@app.get("/api/musteri/durum")
async def get_musteri_durum(plaka: str):
    durum = database.musteri_arac_durum(plaka)
    return durum

@app.post("/api/musteri/odeme-yap")
async def post_musteri_odeme(req: MusteriOdemeReq):
    basarili, mesaj, makbuz = database.musteri_arac_odeme_yap(req.plaka, req.model_dump())
    if basarili:
        await broadcast_event("ODEME_YAPILDI", {
            "plaka": req.plaka,
            "makbuz": makbuz,
            "mesaj": f"{req.plaka} online ödemesini gerçekleştirdi."
        })
    return {
        "status": "ok" if basarili else "error",
        "mesaj": mesaj,
        "makbuz": makbuz
    }

# ================= ABONMAN & PAZARLAMA ENDPOINTS =================

@app.get("/api/abonman/paketler")
async def get_abonman_paketler():
    return {
        "status": "ok",
        "paketler": database.ABONMAN_PAKETLERI
    }

@app.get("/api/abonman/durum")
async def get_abonman_durum(plaka: str):
    plaka_temiz = plaka.strip().upper()
    abonman = database.abonman_kontrol(plaka_temiz)
    return {
        "status": "ok",
        "plaka": plaka_temiz,
        "abonman_mi": bool(abonman),
        "abonman": abonman
    }

@app.get("/api/abonman/aktifler")
async def get_abonman_aktifler():
    return {
        "status": "ok",
        "aktifler": database.tum_aktif_abonmanlar()
    }

@app.post("/api/abonman/satin-al")
async def post_abonman_satin_al(req: AbonmanSatinAlReq):
    basarili, mesaj, makbuz = database.abonman_satin_al(
        req.plaka, 
        req.paket_tipi, 
        req.model_dump(),
        email=req.email
    )
    if basarili:
        await broadcast_event("ABONMAN_AKTIF_EDILDI", {
            "plaka": req.plaka.strip().upper(),
            "makbuz": makbuz,
            "mesaj": f"{req.plaka.strip().upper()} için {makbuz.get('paket_ad', 'Abonman')} başlatıldı."
        })
    return {
        "status": "ok" if basarili else "error",
        "mesaj": mesaj,
        "makbuz": makbuz
    }

@app.get("/api/pazarlama/adaylar")
async def get_pazarlama_adaylar():
    adaylar = database.pazarlama_analizi_yap()
    return {
        "status": "ok",
        "aday_sayisi": len(adaylar),
        "adaylar": adaylar
    }

@app.post("/api/pazarlama/eposta-gonder")
async def post_pazarlama_eposta(req: PazarlamaEpostaReq):
    plaka_temiz = req.plaka.strip().upper()
    musteri = database.musteri_getir(plaka_temiz)
    if not musteri or not musteri.get("email"):
        return {
            "status": "error",
            "mesaj": f"{plaka_temiz} plakası için sistemde kayıtlı e-posta adresi bulunamadı."
        }
    
    # Aday analizini çek
    adaylar = database.pazarlama_analizi_yap()
    aday = next((a for a in adaylar if a["plaka"].replace(" ", "").upper() == plaka_temiz.replace(" ", "").upper()), None)
    if not aday:
        # Varsayılan öneri paketi oluştur
        aday = {
            "plaka": plaka_temiz,
            "ziyaret_sayisi": 3,
            "toplam_harcama": 150.0,
            "toplam_sure_sn": 7200,
            "onerilen_paket_ad": "Aylık Abonman (30 Gün)",
            "onerilen_paket_ucret": 750.0,
            "tasarruf_yuzdesi": 40
        }
    
    basarili, mesaj = mailer.pazarlama_epostasi_gonder(musteri["email"], plaka_temiz, aday)
    return {
        "status": "ok" if basarili else "error",
        "mesaj": mesaj,
        "alici": musteri["email"]
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    try:
        # Bağlanır bağlanmaz güncel durumu gönder
        ilk_durum = {
            "type": "DURUM_GUNCELLEME",
            "iceridekiler": database.get_icerideki_araclar(),
            "istatistikler": database.get_istatistikler(),
            "kapasite": database.kapasite_durumu_getir(),
            "server_time": time.time()
        }
        await websocket.send_text(json.dumps(ilk_durum))

        # İstemciden gelebilecek ping/komutları dinle
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                if payload.get("action") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        connected_websockets.discard(websocket)
    except Exception:
        connected_websockets.discard(websocket)

def print_banner(ip: str, port: int):
    url = f"http://{ip}:{port}"
    saniye, ucret = database.tarife_getir()
    print("\n" + "="*60)
    print(">> 🅿️ ParkOS - AKILLI OTOPARK ISLETIM SISTEMI BASLATILDI")
    print("="*60)
    print(f"[*] Yonetici Paneli   : http://localhost:{port}")
    print(f"[*] Musteri Portali   : http://localhost:{port}/musteri")
    print(f"[*] Mobil Yonetici    : {url}")
    print(f"[*] Mobil Musteri     : {url}/musteri")
    print(f"[*] Fiyat Tarifesi    : Her {saniye} Saniye = {ucret:.2f} TL")
    print("="*60)
    print("[*] TELEFONDAN ACMANIZ ICIN QR KOD:")
    print("-" * 60)
    try:
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception as e:
        print(f"QR Kod olusturulamadi: {e}")
    print("-" * 60)
    print("Kapatmak icin CTRL+C tuslarina basin.\n")

def start_server(host: str = "0.0.0.0", port: int = 8000):
    ip = get_local_ip()
    print_banner(ip, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")

if __name__ == "__main__":
    start_server()
