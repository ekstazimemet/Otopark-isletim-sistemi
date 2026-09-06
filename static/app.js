// Akıllı Plaka Otopark & Ücret Takip - Mobil Frontend

let socket = null;
let iceridekiler = [];
let audioEnabled = true;
let audioCtx = null;
let previousPrices = {}; // Plaka -> önceki ücret (artış tespiti için)
let aktifTarifeSaniye = 5;
let aktifTarifeUcret = 1.0;

// DOM Elementleri
const connectionStatus = document.getElementById('connectionStatus');
const statIceride = document.getElementById('statIceride');
const statAnlikKasa = document.getElementById('statAnlikKasa');
const statToplamGelir = document.getElementById('statToplamGelir');
const statCikanSayisi = document.getElementById('statCikanSayisi');
const tabCountIceride = document.getElementById('tabCountIceride');
const aracListesi = document.getElementById('aracListesi');
const bosListe = document.getElementById('bosListe');
const gecmisTableBody = document.getElementById('gecmisTableBody');
const toastContainer = document.getElementById('toastContainer');
const audioToggleBtn = document.getElementById('audioToggleBtn');
const audioIcon = document.getElementById('audioIcon');
const qrBtn = document.getElementById('qrBtn');
const qrModal = document.getElementById('qrModal');
const closeQrModal = document.getElementById('closeQrModal');
const qrContainer = document.getElementById('qrContainer');
const mobilUrlText = document.getElementById('mobilUrlText');
const topTarifeText = document.getElementById('topTarifeText');
const aktifTarifePill = document.getElementById('aktifTarifePill');
const tarifeSaniyeInput = document.getElementById('tarifeSaniyeInput');
const tarifeUcretInput = document.getElementById('tarifeUcretInput');
const tarifeKaydetBtn = document.getElementById('tarifeKaydetBtn');

// Web Audio API ile Zilsesi (Harici dosya gerektirmez)
function initAudio() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
}

function playBeep(type = 'giris') {
  if (!audioEnabled) return;
  try {
    initAudio();
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    const now = audioCtx.currentTime;

    if (type === 'giris') {
      // Çift tonlu neşeli 'Hoş Geldiniz' melodisi (587Hz -> 880Hz)
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.setValueAtTime(880.00, now + 0.12); // A5
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
      osc.start(now);
      osc.stop(now + 0.4);
    } else if (type === 'cikis') {
      // Çıkış melodisi (880Hz -> 659Hz)
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(880.00, now);
      osc.frequency.setValueAtTime(659.25, now + 0.14);
      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.45);
      osc.start(now);
      osc.stop(now + 0.45);
    } else if (type === 'coin') {
      // Hafif para tıkırtısı (ücret arttığında)
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1200, now);
      gain.gain.setValueAtTime(0.05, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
      osc.start(now);
      osc.stop(now + 0.08);
    }
  } catch (e) {
    console.warn("Ses çalınamadı:", e);
  }
}

// Toast Bildirimi
function showToast(title, desc, type = 'giris') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div class="toast-icon">${type === 'giris' ? '🚗' : '👋'}</div>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      <div class="toast-desc">${desc}</div>
    </div>
  `;
  toastContainer.appendChild(toast);
  playBeep(type);

  // Telefonda titreşim desteği
  if (navigator.vibrate) {
    navigator.vibrate(type === 'giris' ? [100, 50, 100] : [200, 100, 200]);
  }

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Zaman Formatlayıcı (Saniye -> MM:SS veya SS sn)
function formatDuration(seconds) {
  const s = Math.floor(seconds);
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  if (mins > 0) {
    return `${mins}dk ${secs < 10 ? '0' : ''}${secs}sn`;
  }
  return `${secs} sn`;
}

function formatClock(epochSeconds) {
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// WebSocket Bağlantı Yönetimi
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    connectionStatus.className = 'status-badge connected';
    connectionStatus.querySelector('.status-text').textContent = 'Canlı Bağlantı';
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleSocketMessage(msg);
    } catch (e) {
      console.error("Mesaj ayrıştırma hatası:", e);
    }
  };

  socket.onclose = () => {
    connectionStatus.className = 'status-badge';
    connectionStatus.querySelector('.status-text').textContent = 'Koptu, Tekrar Deneniyor...';
    setTimeout(connectWebSocket, 2000);
  };

  socket.onerror = () => {
    socket.close();
  };
}

// Tarife UI ve Yönetimi
function guncelleTarifeUI(saniye, ucret) {
  if (!saniye || !ucret) return;
  aktifTarifeSaniye = parseInt(saniye);
  aktifTarifeUcret = parseFloat(ucret);
  
  if (topTarifeText) {
    topTarifeText.innerHTML = `Her <strong>${aktifTarifeSaniye} Saniyede ${aktifTarifeUcret.toFixed(2)} ₺</strong>`;
  }
  if (aktifTarifePill) {
    aktifTarifePill.textContent = `${aktifTarifeSaniye} sn = ${aktifTarifeUcret.toFixed(2)} ₺`;
  }
  if (tarifeSaniyeInput && document.activeElement !== tarifeSaniyeInput) {
    tarifeSaniyeInput.value = aktifTarifeSaniye;
  }
  if (tarifeUcretInput && document.activeElement !== tarifeUcretInput) {
    tarifeUcretInput.value = aktifTarifeUcret;
  }
}

async function tarifeKaydet(saniye, ucret) {
  try {
    const res = await fetch('/api/tarife', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ saniye: parseInt(saniye), ucret: parseFloat(ucret) })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      guncelleTarifeUI(data.saniye, data.ucret);
      showToast("Fiyat Tarifesi Güncellendi", data.tarife, "giris");
    }
  } catch (e) {
    alert("Tarife güncellenemedi: " + e.message);
  }
}

function hizliTarifeAyarla(saniye, ucret) {
  if (tarifeSaniyeInput) tarifeSaniyeInput.value = saniye;
  if (tarifeUcretInput) tarifeUcretInput.value = ucret;
  tarifeKaydet(saniye, ucret);
}

// Kapasite Yönetimi
function guncelleKapasiteUI(kap) {
  if (!kap) return;
  const bos = kap.bos || {};
  const kapasite = kap.kapasite || {};
  const statBosYer = document.getElementById('statBosYer');
  const statBosYerDetay = document.getElementById('statBosYerDetay');
  const aktifKapasitePill = document.getElementById('aktifKapasitePill');
  const kapasiteNormalInput = document.getElementById('kapasiteNormalInput');
  const kapasiteAbonmanInput = document.getElementById('kapasiteAbonmanInput');

  if (statBosYer) {
    statBosYer.textContent = `${bos.toplam ?? 0} / ${kapasite.toplam ?? 0}`;
    if (bos.toplam <= 0) {
      statBosYer.className = "stat-value text-red";
    } else if (bos.normal <= 0) {
      statBosYer.className = "stat-value text-amber";
    } else {
      statBosYer.className = "stat-value text-purple";
    }
  }
  if (statBosYerDetay) {
    statBosYerDetay.innerHTML = `Abonmansız: <strong>${bos.normal ?? 0} Boş</strong> | Abonmanlı: <strong>${bos.abonman ?? 0} Boş</strong>`;
  }
  if (aktifKapasitePill) {
    aktifKapasitePill.textContent = `Toplam: ${kapasite.toplam ?? 0} Yer (${kapasite.normal ?? 0} Standart + ${kapasite.abonman ?? 0} Abonmanlı)`;
  }
  if (kapasiteNormalInput && document.activeElement !== kapasiteNormalInput) {
    kapasiteNormalInput.value = kapasite.normal ?? 10;
  }
  if (kapasiteAbonmanInput && document.activeElement !== kapasiteAbonmanInput) {
    kapasiteAbonmanInput.value = kapasite.abonman ?? 5;
  }
}

async function kapasiteKaydet() {
  const normInput = document.getElementById('kapasiteNormalInput');
  const abnInput = document.getElementById('kapasiteAbonmanInput');
  const normal = parseInt(normInput ? normInput.value : 10) || 0;
  const abonman = parseInt(abnInput ? abnInput.value : 5) || 0;
  try {
    const res = await fetch('/api/kapasite/guncelle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ normal, abonman })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      guncelleKapasiteUI(data.kapasite);
      showToast("Kapasite Güncellendi", `${normal} Abonmansız, ${abonman} Abonmanlı Park Yeri`, "giris");
    }
  } catch (e) {
    alert("Kapasite güncellenemedi: " + e.message);
  }
}

function hizliKapasiteAyarla(normal, abonman) {
  const normInput = document.getElementById('kapasiteNormalInput');
  const abnInput = document.getElementById('kapasiteAbonmanInput');
  if (normInput) normInput.value = normal;
  if (abnInput) abnInput.value = abonman;
  kapasiteKaydet();
}

async function loadKapasite() {
  try {
    const res = await fetch('/api/kapasite');
    const data = await res.json();
    if (data.status === 'ok') {
      guncelleKapasiteUI(data.kapasite);
    }
  } catch (e) {
    console.warn("Kapasite yüklenemedi:", e);
  }
}

// WebSocket Mesaj İşleme
function handleSocketMessage(msg) {
  if (msg.type === 'DURUM_GUNCELLEME') {
    iceridekiler = msg.iceridekiler || [];
    guncelleIstatistikler(msg.istatistikler);
    if (msg.istatistikler && msg.istatistikler.tarife_saniye) {
      guncelleTarifeUI(msg.istatistikler.tarife_saniye, msg.istatistikler.tarife_ucret);
    }
    if (msg.kapasite || (msg.istatistikler && msg.istatistikler.kapasite)) {
      guncelleKapasiteUI(msg.kapasite || msg.istatistikler.kapasite);
    }
    renderAracListesi();
  } else if (msg.type === 'TARIFE_GUNCELLEME') {
    guncelleTarifeUI(msg.data.tarife_saniye, msg.data.tarife_ucret);
    showToast("Yeni Tarife Devrede", msg.data.tarife, "giris");
    renderAracListesi();
  } else if (msg.type === 'KAPASITE_GUNCELLEME') {
    guncelleKapasiteUI(msg.data.kapasite);
    showToast("🅿️ Kapasite Güncellendi", msg.data.mesaj, "giris");
  } else if (msg.type === 'GIRIS') {
    showToast(`Yeni Giriş: ${msg.data.plaka}`, "Otoparka giriş yaptı. Kronometre başladı.", 'giris');
    if (msg.data.kapasite) guncelleKapasiteUI(msg.data.kapasite);
  } else if (msg.type === 'GIRIS_ENGELLENDI') {
    showToast(`⛔ Giriş Engellendi: ${msg.data.plaka}`, msg.data.mesaj || "Otopark kapasitesi dolu!", 'cikis');
    if (msg.data.kapasite) guncelleKapasiteUI(msg.data.kapasite);
  } else if (msg.type === 'CIKIS') {
    const ucret = msg.data.kayit ? msg.data.kayit.ucret : 0;
    const sure = msg.data.kayit ? formatDuration(msg.data.kayit.toplam_sure_sn) : '';
    showToast(`Çıkış: ${msg.data.plaka}`, `Süre: ${sure} • Tahsilat: ${ucret.toFixed(2)} ₺`, 'cikis');
    if (msg.data.kapasite) guncelleKapasiteUI(msg.data.kapasite);
    loadGecmis();
  } else if (msg.type === 'CIKIS_ENGELLENDI') {
    const borc = msg.data.kayit ? (msg.data.kayit.odenecek_ucret || msg.data.kayit.anlik_ucret || 0) : 0;
    if (borc > 0.05) {
      showToast(`⛔ Çıkış Engellendi: ${msg.data.plaka}`, `Ödenmemiş Borç: ${borc.toFixed(2)} ₺! Bariyer açılmadı.`, 'cikis');
    }
  } else if (msg.type === 'ODEME_YAPILDI') {
    const makbuz = msg.data.makbuz || {};
    showToast(`💳 Online Ödeme: ${msg.data.plaka}`, `Tutar: ${(makbuz.odenen_tutar || 0).toFixed(2)} ₺ • 30 sn çıkış süresi devrede.`, 'giris');
  } else if (msg.type === 'ABONMAN_AKTIF_EDILDI') {
    showToast(`🌟 Abonman Başlatıldı: ${msg.data.plaka}`, msg.data.mesaj || "Abonman tanımlandı.", 'giris');
    renderAracListesi();
    loadAbonmanlar();
    loadPazarlamaAdaylari();
    loadKapasite();
  } else if (msg.type === 'TEMIZLE') {
    showToast("Sistem", "Veritabanı sıfırlandı.", "cikis");
    iceridekiler = [];
    renderAracListesi();
    loadGecmis();
    loadAbonmanlar();
    loadPazarlamaAdaylari();
    loadKapasite();
  }
}


// İstatistikleri Güncelle
function guncelleIstatistikler(stats) {
  if (!stats) return;
  statIceride.textContent = stats.icerideki_arac_sayisi;
  statAnlikKasa.textContent = `${stats.anlik_icerideki_tutar.toFixed(2)} ₺`;
  statToplamGelir.textContent = `${stats.toplam_tahsil_edilen.toFixed(2)} ₺`;
  statCikanSayisi.textContent = `${stats.cikis_yapan_arac_sayisi} Çıkış Yapıldı`;
  tabCountIceride.textContent = stats.icerideki_arac_sayisi;
  if (stats.kapasite) {
    guncelleKapasiteUI(stats.kapasite);
  }
}

// Canlı Araç Listesini Ekrana Bas
function renderAracListesi() {
  if (!iceridekiler || iceridekiler.length === 0) {
    aracListesi.innerHTML = '';
    bosListe.style.display = 'block';
    return;
  }

  bosListe.style.display = 'none';

  // Mevcut DOM öğelerini güncelle veya oluştur
  const existingCards = new Map();
  aracListesi.querySelectorAll('.arac-card').forEach(el => {
    existingCards.set(el.getAttribute('data-plaka'), el);
  });

  const activePlakalar = new Set(iceridekiler.map(a => a.plaka));

  // Artık içeride olmayanları kaldır
  existingCards.forEach((card, plaka) => {
    if (!activePlakalar.has(plaka)) {
      card.remove();
    }
  });

  const now = Date.now() / 1000;

function getOdemeRozetHtml(arac) {
  if (arac.abonman_mi || (arac.musteri_turu && arac.musteri_turu.includes('Abonman'))) {
    return `<span data-field="odeme-rozet" style="background:linear-gradient(135deg,#8b5cf6,#d946ef); color:#ffffff; padding:3px 10px; border-radius:10px; font-size:11px; font-weight:800; box-shadow:0 0 8px rgba(139,92,246,0.4);">⭐ Abonmanlı (0.00 ₺)</span>`;
  } else if (arac.tolerans_aktif) {
    return `<span data-field="odeme-rozet" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid #10b981; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700;">✅ Ödendi (${Math.round(arac.kalan_tolerans_sn || 0)}sn)</span>`;
  } else if (arac.tolerans_doldu) {
    return `<span data-field="odeme-rozet" style="background:rgba(239,68,68,0.15); color:#ef4444; border:1px solid #ef4444; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700;">⚠️ Süre Doldu</span>`;
  } else if (arac.odendi_mi) {
    return `<span data-field="odeme-rozet" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid #10b981; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700;">✅ Ödendi</span>`;
  } else {
    return `<span data-field="odeme-rozet" style="background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid #f59e0b; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700;">💳 Borç Var</span>`;
  }
}

  iceridekiler.forEach(arac => {
    const plaka = arac.plaka;
    const gecen = Math.max(0, now - arac.giris_zamani);
    const isAbonman = Boolean(arac.abonman_mi || (arac.musteri_turu && arac.musteri_turu.includes('Abonman')));
    const ucret = isAbonman ? 0 : (arac.tolerans_aktif ? 0 : (arac.anlik_ucret !== undefined ? arac.anlik_ucret : (Math.floor(gecen / aktifTarifeSaniye) * aktifTarifeUcret)));
    const prevUcret = previousPrices[plaka] || 0;
    const isPriceChanged = ucret > prevUcret;
    previousPrices[plaka] = ucret;

    let card = existingCards.get(plaka);

    if (!card) {
      card = document.createElement('div');
      card.className = 'arac-card';
      card.setAttribute('data-plaka', plaka);
      card.innerHTML = `
        <div class="arac-card-top">
          <div class="plaka-badge">
            <div class="plaka-tr">
              <span class="plaka-tr-stars">★★</span>
              <span>TR</span>
            </div>
            <div class="plaka-text">${plaka}</div>
          </div>
          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
            <div class="giris-etiket">
              <span class="label">Giriş</span>
              <span class="time">${formatClock(arac.giris_zamani)}</span>
            </div>
            ${getOdemeRozetHtml(arac)}
          </div>
        </div>

        <div class="arac-metrics">
          <div class="metric-item">
            <span class="metric-label">İçeride Kalınan Süre</span>
            <span class="metric-value timer" data-field="timer">${formatDuration(gecen)}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Ödenecek Borç (<span data-field="tarife-hint">${aktifTarifeSaniye}sn=${aktifTarifeUcret}₺</span>)</span>
            <span class="metric-value price" data-field="price">${ucret.toFixed(2)} ₺</span>
          </div>
        </div>

        <div class="arac-card-bottom">
          <button class="cikis-btn" onclick="araciCikart('${plaka}')">👋 Çıkış Yap</button>
        </div>
      `;
      aracListesi.appendChild(card);
    } else {
      // Mevcut kartı hafifçe güncelle
      const timerEl = card.querySelector('[data-field="timer"]');
      const priceEl = card.querySelector('[data-field="price"]');
      const hintEl = card.querySelector('[data-field="tarife-hint"]');
      const rozetEl = card.querySelector('[data-field="odeme-rozet"]');
      if (timerEl) timerEl.textContent = formatDuration(gecen);
      if (hintEl) hintEl.textContent = `${aktifTarifeSaniye}sn=${aktifTarifeUcret}₺`;
      if (rozetEl) rozetEl.outerHTML = getOdemeRozetHtml(arac);
      if (priceEl) {
        priceEl.textContent = `${ucret.toFixed(2)} ₺`;
        if (isPriceChanged) {
          priceEl.classList.remove('price-flash');
          void priceEl.offsetWidth; // Trigger reflow
          priceEl.classList.add('price-flash');
        }
      }
    }
  });
}

// Yerel canlı kronometre döngüsü (Sunucudan mesaj beklemeden her saniye akıcı sayaç)
setInterval(() => {
  if (!iceridekiler || iceridekiler.length === 0) return;
  const now = Date.now() / 1000;
  let toplamAnlik = 0;

  iceridekiler.forEach(arac => {
    const gecen = Math.max(0, now - arac.giris_zamani);
    const ucret = arac.tolerans_aktif ? 0 : (arac.anlik_ucret !== undefined ? arac.anlik_ucret : (Math.floor(gecen / aktifTarifeSaniye) * aktifTarifeUcret));
    toplamAnlik += ucret;

    const card = aracListesi.querySelector(`[data-plaka="${arac.plaka}"]`);
    if (card) {
      const timerEl = card.querySelector('[data-field="timer"]');
      const priceEl = card.querySelector('[data-field="price"]');
      const hintEl = card.querySelector('[data-field="tarife-hint"]');
      if (timerEl) timerEl.textContent = formatDuration(gecen);
      if (hintEl) hintEl.textContent = `${aktifTarifeSaniye}sn=${aktifTarifeUcret}₺`;
      if (priceEl) {
        const oldUcret = parseFloat(priceEl.textContent) || 0;
        priceEl.textContent = `${ucret.toFixed(2)} ₺`;
        if (ucret > oldUcret) {
          priceEl.classList.remove('price-flash');
          void priceEl.offsetWidth;
          priceEl.classList.add('price-flash');
          playBeep('coin');
        }
      }
    }
  });

  statAnlikKasa.textContent = `${toplamAnlik.toFixed(2)} ₺`;
}, 1000);

// API İstekleri
async function araciCikart(plaka) {
  try {
    const res = await fetch('/api/manuel-islem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plaka, islem: 'cikis' })
    });
    const data = await res.json();
    if (data.durum === 'CIKIS_ENGELLENDI') {
      const borc = data.kayit ? (data.kayit.odenecek_ucret || data.kayit.anlik_ucret || 0) : 0;
      if (borc > 0.05) {
        const onayla = confirm(`⛔ [${plaka}] ÇIKIŞ ENGELLENDİ!\n\nÖdenmemiş Borç: ${borc.toFixed(2)} ₺\nBariyer açılmadı.\n\nMüşteriden nakit tahsil edildiyse çıkış onaylansın mı?`);
        if (onayla) {
          await fetch('/api/manuel-islem', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plaka, islem: 'cikis', zorla: true })
          });
        }
      }
    }
  } catch (e) {
    alert("İşlem gerçekleştirilemedi: " + e.message);
  }
}


async function manuelGiris(plaka, islem) {
  if (!plaka) {
    alert("Lütfen bir plaka girin!");
    return;
  }
  try {
    const res = await fetch('/api/manuel-islem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plaka, islem })
    });
    const data = await res.json();
    document.getElementById('manuelPlakaInput').value = '';
    // Sekmeyi canlı listeye al
    document.querySelector('[data-tab="tab-iceride"]').click();
  } catch (e) {
    alert("Hata: " + e.message);
  }
}

async function loadGecmis() {
  try {
    const res = await fetch('/api/gecmis');
    const data = await res.json();
    gecmisTableBody.innerHTML = '';

    if (!data.gecmis || data.gecmis.length === 0) {
      gecmisTableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#64748b; padding:20px;">Henüz çıkış kaydı yok</td></tr>`;
      return;
    }

    data.gecmis.forEach(row => {
      const isAbonman = row.musteri_turu && row.musteri_turu.includes('Abonman');
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>
          <span style="font-weight:700; color:#60a5fa;">${row.plaka}</span>
          ${isAbonman ? `<span style="font-size:10px; background:rgba(139,92,246,0.25); color:#c4b5fd; padding:1px 6px; border-radius:4px; margin-left:4px; border:1px solid #8b5cf6;">${row.musteri_turu}</span>` : ''}
        </td>
        <td>${formatClock(row.giris_zamani)}</td>
        <td>${formatClock(row.cikis_zamani)}</td>
        <td>${formatDuration(row.toplam_sure_sn)}</td>
        <td style="color:${isAbonman ? '#c4b5fd' : '#34d399'}; font-weight:700;">
          ${row.ucret.toFixed(2)} ₺ ${isAbonman ? '<span style="font-size:10px; color:#a78bfa;">(Abonman)</span>' : ''}
        </td>
      `;
      gecmisTableBody.appendChild(tr);
    });
  } catch (e) {
    console.error("Geçmiş yükleme hatası:", e);
  }
}

// ================= ABONMAN & PAZARLAMA YÖNETİMİ =================
async function loadAbonmanlar() {
  const tbody = document.getElementById('abonmanTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#94a3b8; padding:14px;">Yükleniyor...</td></tr>';
  try {
    const res = await fetch('/api/abonman/aktifler');
    const data = await res.json();
    tbody.innerHTML = '';
    if (!data.aktifler || data.aktifler.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#64748b; padding:16px;">Şu an aktif abonman kaydı bulunmuyor.</td></tr>';
      return;
    }
    data.aktifler.forEach(a => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-weight:700; color:#c4b5fd;">${a.plaka}</td>
        <td>${a.email || '<span style="color:#64748b;">(Belirtilmemiş)</span>'}</td>
        <td><span style="background:rgba(139,92,246,0.2); color:#c4b5fd; border:1px solid #8b5cf6; padding:2px 8px; border-radius:6px; font-weight:700; font-size:11px;">${a.paket_ad}</span></td>
        <td>${a.baslangic_formatli || '-'}</td>
        <td>${a.bitis_formatli || '-'}</td>
        <td style="font-weight:700; color:#38bdf8;">${a.kalan_gun} Gün (${a.kalan_saat} sa)</td>
        <td><span style="color:#4ade80; font-weight:700; font-size:11px;">✅ 0.00 TL Ücretsiz Geçiş</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:#ef4444; text-align:center;">Hata: ${e.message}</td></tr>`;
  }
}

async function loadPazarlamaAdaylari() {
  const tbody = document.getElementById('pazarlamaTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#94a3b8; padding:14px;">Akıllı analiz çalıştırılıyor...</td></tr>';
  try {
    const res = await fetch('/api/pazarlama/adaylar');
    const data = await res.json();
    tbody.innerHTML = '';
    if (!data.adaylar || data.adaylar.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#64748b; padding:16px;">Şu an öneri kriterine uyan aday bulunamadı (Tüm sık gelenler zaten abonman veya yeterli geçmiş yok).</td></tr>';
      return;
    }
    data.adaylar.forEach(a => {
      const tr = document.createElement('tr');
      const emailText = a.email ? a.email : '<span style="color:#f59e0b; font-size:11px;">Müşteri Portalında Kayıtsız</span>';
      const btnDisabled = !a.email ? 'disabled title="Müşteri henüz e-postasını kaydetmedi"' : '';
      tr.innerHTML = `
        <td style="font-weight:700; color:#60a5fa;">${a.plaka}</td>
        <td>${emailText}</td>
        <td><strong>${a.ziyaret_sayisi} Ziyaret</strong> • ${a.toplam_harcama.toFixed(2)} ₺</td>
        <td><span style="background:rgba(59,130,246,0.15); color:#60a5fa; padding:2px 8px; border-radius:6px; font-weight:700; font-size:11px;">${a.onerilen_paket_ad}</span></td>
        <td style="color:#22c55e; font-weight:700;">~${a.tahmini_tasarruf_tl.toFixed(2)} ₺ (%${a.tasarruf_yuzdesi})</td>
        <td>
          <button onclick="pazarlamaTeklifGonder('${a.plaka}')" ${btnDisabled} class="action-sm-btn" style="background:linear-gradient(135deg,#8b5cf6,#3b82f6); color:white; font-weight:700;">
            📧 Teklif Gönder
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" style="color:#ef4444; text-align:center;">Hata: ${e.message}</td></tr>`;
  }
}

async function pazarlamaTeklifGonder(plaka) {
  try {
    showToast("E-Posta Gönderiliyor", `${plaka} için teklif hazırlanıyor...`, "giris");
    const res = await fetch('/api/pazarlama/eposta-gonder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plaka })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast("Kampanya Gönderildi", `${plaka} sahibine özel tasarruf e-postası başarıyla iletildi!`, "giris");
    } else {
      showToast("Gönderilemedi", data.mesaj, "cikis");
    }
  } catch (e) {
    showToast("Hata", e.message, "cikis");
  }
}

// Sekme Değiştirme
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    btn.classList.add('active');
    const target = btn.getAttribute('data-tab');
    document.getElementById(target).classList.add('active');

    if (target === 'tab-gecmis') {
      loadGecmis();
    } else if (target === 'tab-pazarlama') {
      loadAbonmanlar();
      loadPazarlamaAdaylari();
    }
  });
});

// Ses Aç/Kapa
audioToggleBtn.addEventListener('click', () => {
  audioEnabled = !audioEnabled;
  audioIcon.textContent = audioEnabled ? '🔔' : '🔕';
  audioToggleBtn.style.opacity = audioEnabled ? '1' : '0.5';
  if (audioEnabled) {
    initAudio();
    playBeep('giris');
  }
});

// QR Kod Modal ve Mobil Bağlantı
async function setupQrModal() {
  try {
    const res = await fetch('/api/bilgi');
    const info = await res.json();
    mobilUrlText.textContent = info.mobil_url;

    if (window.QRCode) {
      qrContainer.innerHTML = '';
      new QRCode(qrContainer, {
        text: info.mobil_url,
        width: 180,
        height: 180,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.M
      });
    }
  } catch (e) {
    console.error("QR modal hatası:", e);
  }
}

qrBtn.addEventListener('click', () => {
  setupQrModal();
  qrModal.classList.add('open');
});

closeQrModal.addEventListener('click', () => {
  qrModal.classList.remove('open');
});

qrModal.addEventListener('click', (e) => {
  if (e.target === qrModal) qrModal.classList.remove('open');
});

// Manuel Giriş / Çıkış butonları
document.getElementById('manuelGirisBtn').addEventListener('click', () => {
  const plaka = document.getElementById('manuelPlakaInput').value.trim();
  manuelGiris(plaka, 'giris');
});

document.getElementById('manuelCikisBtn').addEventListener('click', () => {
  const plaka = document.getElementById('manuelPlakaInput').value.trim();
  manuelGiris(plaka, 'cikis');
});

document.getElementById('yenileGecmisBtn').addEventListener('click', loadGecmis);

if (tarifeKaydetBtn) {
  tarifeKaydetBtn.addEventListener('click', () => {
    const saniye = parseInt(tarifeSaniyeInput.value) || 5;
    const ucret = parseFloat(tarifeUcretInput.value) || 1.0;
    tarifeKaydet(saniye, ucret);
  });
}

const excelSenkronizeBtn = document.getElementById('excelSenkronizeBtn');
if (excelSenkronizeBtn) {
  excelSenkronizeBtn.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/excel-senkronize', { method: 'POST' });
      const data = await res.json();
      showToast("Excel Güncellendi", data.mesaj, "giris");
    } catch (e) {
      alert("Hata: " + e.message);
    }
  });
}

async function tekTiklaSifirla() {
  try {
    const res = await fetch('/api/temizle', { method: 'POST' });
    const data = await res.json();
    showToast("🧹 Tertemiz!", "Tüm araçlar, kasa ve Excel sıfırlandı.", "cikis");
    iceridekiler = [];
    renderAracListesi();
    loadGecmis();
    // Hafifçe canlı listeye geç
    setTimeout(() => {
      document.querySelector('[data-tab="tab-iceride"]').click();
    }, 400);
  } catch (e) {
    alert("Sıfırlama hatası: " + e.message);
  }
}

document.getElementById('sifirlaBtn').addEventListener('click', tekTiklaSifirla);

function hizliPlakaSec(plaka) {
  document.getElementById('manuelPlakaInput').value = plaka;
}

// Başlangıç
connectWebSocket();
loadGecmis();
loadKapasite();

// Bildirim İzni İste (Mobil Tarayıcı için)
if ("Notification" in window && Notification.permission === "default") {
  Notification.requestPermission();
}
