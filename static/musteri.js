// Müşteri Portalı JavaScript Mantığı

let aktifPlaka = localStorage.getItem("musteri_plaka") || null;
let aktifEmail = localStorage.getItem("musteri_email") || null;
let aracDurum = null;
let otpGeriSayimInterval = null;
let canliSayacInterval = null;
let sonTestKodu = null;

// DOM Elementleri
const authSection = document.getElementById("authSection");
const dashboardSection = document.getElementById("dashboardSection");
const cikisYapKonteyner = document.getElementById("cikisYapKonteyner");
const cikisYapBtn = document.getElementById("cikisYapBtn");
const toastContainer = document.getElementById("toastContainer");

// Auth Giriş & Kayıt
const authTabBtns = document.querySelectorAll(".auth-tab-btn");
const authTabContents = document.querySelectorAll(".auth-tab-content");
const girisPlakaInput = document.getElementById("girisPlakaInput");
const kayitPlakaInput = document.getElementById("kayitPlakaInput");
const kayitEmailInput = document.getElementById("kayitEmailInput");
const girisKodGonderBtn = document.getElementById("girisKodGonderBtn");
const kayitKodGonderBtn = document.getElementById("kayitKodGonderBtn");

// OTP Modal
const otpModal = document.getElementById("otpModal");
const closeOtpModal = document.getElementById("closeOtpModal");
const otpInstructionText = document.getElementById("otpInstructionText");
const testCodeBox = document.getElementById("testCodeBox");
const testCodeVal = document.getElementById("testCodeVal");
const otpCodeInput = document.getElementById("otpCodeInput");
const otpTimerText = document.getElementById("otpTimerText");
const otpOnaylaBtn = document.getElementById("otpOnaylaBtn");

// Dashboard
const dashPlakaText = document.getElementById("dashPlakaText");
const dashEmailText = document.getElementById("dashEmailText");
const dashTarifeText = document.getElementById("dashTarifeText");
const dashDurumPill = document.getElementById("dashDurumPill");
const liveCard = document.getElementById("liveCard");
const emptyParkCard = document.getElementById("emptyParkCard");
const dashPulseDot = document.getElementById("dashPulseDot");
const dashDurumBaslik = document.getElementById("dashDurumBaslik");
const dashGirisSaati = document.getElementById("dashGirisSaati");
const dashSureText = document.getElementById("dashSureText");
const dashUcretText = document.getElementById("dashUcretText");
const odemeDurumAlani = document.getElementById("odemeDurumAlani");
const odemeYapModalBtn = document.getElementById("odemeYapModalBtn");

// Ödeme Modal
const odemeModal = document.getElementById("odemeModal");
const closeOdemeModal = document.getElementById("closeOdemeModal");
const payModalAmount = document.getElementById("payModalAmount");
const cardNumPreview = document.getElementById("cardNumPreview");
const cardNamePreview = document.getElementById("cardNamePreview");
const cardExpPreview = document.getElementById("cardExpPreview");
const payCardInput = document.getElementById("payCardInput");
const payHolderInput = document.getElementById("payHolderInput");
const payExpInput = document.getElementById("payExpInput");

// Makbuz Modal
const makbuzModal = document.getElementById("makbuzModal");
const receiptNo = document.getElementById("receiptNo");
const receiptPlaka = document.getElementById("receiptPlaka");
const receiptTutar = document.getElementById("receiptTutar");
const receiptYontem = document.getElementById("receiptYontem");
const receiptTarih = document.getElementById("receiptTarih");

// Toast Bildirimi
function showToast(title, desc, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div>
      <div style="font-weight:700; margin-bottom:2px;">${title}</div>
      <div style="font-size:12px; color:#cbd5e1;">${desc}</div>
    </div>
  `;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "all 0.3s";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Zaman Formatlayıcı
function formatDuration(seconds) {
  const s = Math.floor(seconds);
  const hours = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (hours > 0) return `${hours}sa ${mins}dk ${secs}sn`;
  if (mins > 0) return `${mins}dk ${secs}sn`;
  return `${secs} sn`;
}

function formatClock(epochSeconds) {
  if (!epochSeconds) return "--:--:--";
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleTimeString("tr-TR");
}

// Sekme Değiştirme
authTabBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    authTabBtns.forEach(b => b.classList.remove("active"));
    authTabContents.forEach(c => c.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.getAttribute("data-auth-tab");
    document.getElementById(target).classList.add("active");
  });
});

// Kod İsteme (Giriş)
girisKodGonderBtn.addEventListener("click", async () => {
  const plaka = girisPlakaInput.value.trim().toUpperCase();
  if (!plaka || plaka.length < 5) {
    showToast("Hata", "Lütfen geçerli bir plaka girin.", "cikis");
    return;
  }

  girisKodGonderBtn.disabled = true;
  girisKodGonderBtn.textContent = "Gönderiliyor...";

  try {
    const res = await fetch("/api/musteri/giris-kod-iste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plaka })
    });
    const data = await res.json();

    if (data.status === "ok") {
      aktifPlaka = plaka;
      sonTestKodu = data.test_kod;
      acOtpModal(data.maskeli_email, data.test_kod);
      showToast("Kod Gönderildi", data.mesaj, "giris");
    } else {
      showToast("Giriş Yapılamadı", data.mesaj, "cikis");
    }
  } catch (e) {
    showToast("Bağlantı Hatası", e.message, "cikis");
  } finally {
    girisKodGonderBtn.disabled = false;
    girisKodGonderBtn.textContent = "📩 Doğrulama Kodu Gönder";
  }
});

// Kod İsteme (Kayıt)
kayitKodGonderBtn.addEventListener("click", async () => {
  const plaka = kayitPlakaInput.value.trim().toUpperCase();
  const email = kayitEmailInput.value.trim();

  if (!plaka || plaka.length < 5) {
    showToast("Hata", "Lütfen geçerli bir plaka girin.", "cikis");
    return;
  }
  if (!email || !email.includes("@")) {
    showToast("Hata", "Lütfen geçerli bir e-posta adresi girin.", "cikis");
    return;
  }

  kayitKodGonderBtn.disabled = true;
  kayitKodGonderBtn.textContent = "Kaydediliyor...";

  try {
    const res = await fetch("/api/musteri/kayit-kod-iste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plaka, email })
    });
    const data = await res.json();

    if (data.status === "ok") {
      aktifPlaka = plaka;
      aktifEmail = email;
      sonTestKodu = data.test_kod;
      acOtpModal(data.maskeli_email, data.test_kod);
      showToast("Kod Gönderildi", data.mesaj, "giris");
    } else {
      showToast("Kayıt Yapılamadı", data.mesaj, "cikis");
    }
  } catch (e) {
    showToast("Bağlantı Hatası", e.message, "cikis");
  } finally {
    kayitKodGonderBtn.disabled = false;
    kayitKodGonderBtn.textContent = "✉️ Kaydol & Doğrulama Kodu Al";
  }
});

// OTP Modalı Aç
function acOtpModal(maskeliEmail, testKodu) {
  otpInstructionText.innerHTML = `Doğrulama kodunuz <strong>${maskeliEmail || "e-postanıza"}</strong> gönderildi.`;
  
  if (testKodu) {
    testCodeBox.style.display = "flex";
    testCodeVal.textContent = testKodu;
  } else {
    testCodeBox.style.display = "none";
  }

  otpCodeInput.value = "";
  otpModal.classList.add("open");

  // 5 Dakika Geri Sayım
  let kalan = 300;
  clearInterval(otpGeriSayimInterval);
  otpGeriSayimInterval = setInterval(() => {
    kalan--;
    const mins = Math.floor(kalan / 60);
    const secs = kalan % 60;
    otpTimerText.textContent = `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
    if (kalan <= 0) {
      clearInterval(otpGeriSayimInterval);
      otpTimerText.textContent = "Süre doldu!";
    }
  }, 1000);
}

function koduDoldur() {
  if (sonTestKodu) {
    otpCodeInput.value = sonTestKodu;
  }
}

// Kodu Doğrula ve Giriş Yap
otpOnaylaBtn.addEventListener("click", async () => {
  const kod = otpCodeInput.value.trim();
  if (!kod || kod.length < 6) {
    showToast("Hata", "Lütfen 6 haneli kodu eksiksiz girin.", "cikis");
    return;
  }

  otpOnaylaBtn.disabled = true;
  otpOnaylaBtn.textContent = "Doğrulanıyor...";

  try {
    const res = await fetch("/api/musteri/kod-dogrula", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plaka: aktifPlaka, kod })
    });
    const data = await res.json();

    if (data.status === "ok") {
      otpModal.classList.remove("open");
      clearInterval(otpGeriSayimInterval);
      
      localStorage.setItem("musteri_plaka", aktifPlaka);
      if (data.musteri && data.musteri.email) {
        localStorage.setItem("musteri_email", data.musteri.email);
      }

      showToast("Giriş Başarılı", "Müşteri paneline hoş geldiniz!", "giris");
      initDashboard();
    } else {
      showToast("Doğrulama Başarısız", data.mesaj, "cikis");
    }
  } catch (e) {
    showToast("Hata", e.message, "cikis");
  } finally {
    otpOnaylaBtn.disabled = false;
    otpOnaylaBtn.textContent = "✅ Kodu Doğrula ve Devam Et";
  }
});

closeOtpModal.addEventListener("click", () => {
  otpModal.classList.remove("open");
  clearInterval(otpGeriSayimInterval);
});

// Çıkış Yap
cikisYapBtn.addEventListener("click", () => {
  localStorage.removeItem("musteri_plaka");
  localStorage.removeItem("musteri_email");
  aktifPlaka = null;
  aktifEmail = null;
  clearInterval(canliSayacInterval);
  dashboardSection.style.display = "none";
  cikisYapKonteyner.style.display = "none";
  authSection.style.display = "block";
  showToast("Oturum Kapatıldı", "Güvenle çıkış yaptınız.", "info");
});

// Dashboard'u Başlat
async function initDashboard() {
  if (!aktifPlaka) return;

  authSection.style.display = "none";
  dashboardSection.style.display = "block";
  cikisYapKonteyner.style.display = "block";

  dashPlakaText.textContent = aktifPlaka;
  dashEmailText.textContent = localStorage.getItem("musteri_email") || "Kayıtlı Müşteri";

  await guncelleDurum();

  // Canlı Sayaç Döngüsü (Her saniye borç ve süreyi akıt)
  clearInterval(canliSayacInterval);
  canliSayacInterval = setInterval(async () => {
    if (aracDurum && aracDurum.iceride_mi) {
      const now = Date.now() / 1000;
      const gecen = Math.max(0, now - aracDurum.giris_zamani);
      dashSureText.textContent = formatDuration(gecen);

      // Eğer abonmanlıysa ücret daima 0.00 TL'dir
      if (aracDurum.abonman_mi) {
        dashUcretText.textContent = "0.00 ₺";
      } else if (aracDurum.tolerans_aktif && aracDurum.odeme_zamani) {
        // Tolerans aktifse geri sayım yap ve ücreti dondur
        const gecenTolerans = now - aracDurum.odeme_zamani;
        const kalanTolerans = Math.max(0, 30 - gecenTolerans);
        const badge = document.getElementById("toleransSayacBadge");
        if (badge) {
          badge.textContent = `⏱️ Çıkış İçin Kalan: ${Math.round(kalanTolerans)} sn (Donduruldu)`;
        }
        dashUcretText.textContent = "0.00 ₺";
        if (kalanTolerans <= 0) {
          // 30 saniye doldu! Sunucudan durumu yenile (ek borç hesaplanacak)
          aracDurum.tolerans_aktif = false;
          await guncelleDurum();
        }
      } else {
        dashUcretText.textContent = `${(aracDurum.anlik_ucret || 0).toFixed(2)} ₺`;
      }
    }
  }, 1000);

  // Her 3 saniyede bir sunucudan tam durumu çek
  setInterval(guncelleDurum, 3000);
}

// Durumu Sunucudan Çek
async function guncelleDurum() {
  if (!aktifPlaka) return;
  try {
    const res = await fetch(`/api/musteri/durum?plaka=${encodeURIComponent(aktifPlaka)}`);
    const data = await res.json();
    aracDurum = data;

    dashTarifeText.textContent = `⚡ ${data.tarife}`;

    // 1. Abonman & VIP Bilgileri
    const dashVipBadgeBox = document.getElementById("dashVipBadgeBox");
    const dashAbonmanCard = document.getElementById("dashAbonmanCard");
    const dashPromoBanner = document.getElementById("dashPromoBanner");

    if (data.abonman_mi && data.abonman) {
      if (dashVipBadgeBox) dashVipBadgeBox.style.display = "block";
      if (dashAbonmanCard) {
        dashAbonmanCard.style.display = "flex";
        document.getElementById("vipPaketAdi").textContent = data.abonman.paket_ad || "Abonman";
        document.getElementById("vipKalanGunBadge").textContent = `${data.abonman.kalan_gun} Gün Kaldı`;
        document.getElementById("vipBitisTarihi").textContent = data.abonman.bitis_formatli || "--.--.----";
      }
      if (dashPromoBanner) dashPromoBanner.style.display = "none";
    } else {
      if (dashVipBadgeBox) dashVipBadgeBox.style.display = "none";
      if (dashAbonmanCard) dashAbonmanCard.style.display = "none";

      // Pazarlama Önerisi varsa göster
      if (data.pazarlama_oneri && dashPromoBanner) {
        dashPromoBanner.style.display = "flex";
        const p = data.pazarlama_oneri;
        document.getElementById("promoBaslik").textContent = `${p.oneri_paket_ad} ile %${p.tasarruf_yuzdesi} Tasarruf Edin!`;
        document.getElementById("promoAciklama").textContent = `${p.ziyaret_sayisi} ziyaretiniz ve ${p.toplam_harcama.toFixed(2)} ₺ harcamanız tespit edildi. Avantajlı paketle durmadan geçin!`;
      } else if (dashPromoBanner) {
        dashPromoBanner.style.display = "none";
      }
    }

    if (data.iceride_mi) {
      // Araç Otoparkta
      dashDurumPill.className = "status-pill inside";
      dashDurumPill.textContent = data.abonman_mi ? "🅿️ Otoparkta (Abonman)" : "🅿️ Otoparkta";
      dashPulseDot.style.background = data.abonman_mi ? "#8b5cf6" : "#10b981";
      dashDurumBaslik.textContent = data.abonman_mi ? "Aracınız Otoparkta (Abonmanlı)" : "Aracınız Otoparkta";

      dashGirisSaati.textContent = formatClock(data.giris_zamani);
      dashSureText.textContent = formatDuration(data.anlik_sure_sn);

      liveCard.style.display = "flex";
      emptyParkCard.style.display = "none";

      if (data.abonman_mi) {
        // ABONMANLI: Ücret daima 0.00 TL ve çıkış her zaman serbest
        dashUcretText.textContent = "0.00 ₺";
        odemeDurumAlani.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:4px; align-items:flex-end;">
            <span class="paid-badge" style="background:rgba(139,92,246,0.25); border:1px solid #8b5cf6; color:#c4b5fd; font-weight:700; padding:6px 14px; border-radius:30px;">
              🌟 ABONMAN KAPSAMINDA ÜCRETSİZ
            </span>
            <span style="font-size:11px; color:#a78bfa;">Bariyer otomatik açılacaktır.</span>
          </div>
        `;
      } else if (data.tolerans_aktif) {
        // 30 saniye tolerans içinde - Ücret donduruldu, çıkış serbest
        dashUcretText.textContent = "0.00 ₺";
        odemeDurumAlani.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:6px; align-items:flex-end;">
            <span class="paid-badge" style="background:rgba(16,185,129,0.2); border:1px solid #10b981; color:#34d399; font-weight:700; padding:6px 14px; border-radius:30px;">
              ✅ ÖDENDİ (Bariyer Açılacak)
            </span>
            <span id="toleransSayacBadge" style="font-size:12px; font-weight:700; color:#38bdf8; background:#0f172a; padding:4px 10px; border-radius:8px; border:1px solid #0284c7;">
              ⏱️ Çıkış İçin Kalan: ${Math.max(0, Math.round(data.kalan_tolerans_sn))} sn (Donduruldu)
            </span>
          </div>
        `;
      } else if (data.tolerans_doldu) {
        // 30 saniye tolerans doldu ve ek borç var!
        dashUcretText.textContent = `${data.anlik_ucret.toFixed(2)} ₺`;
        odemeDurumAlani.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:6px; align-items:flex-end;">
            <span style="font-size:11px; font-weight:700; color:#f87171; background:rgba(239,68,68,0.15); padding:4px 8px; border-radius:6px; border:1px solid rgba(239,68,68,0.4);">
              ⚠️ 30 sn Çıkış Süreniz Doldu!
            </span>
            <button id="odemeYapModalBtn" class="btn btn-pay" onclick="acOdemeModal(${data.anlik_ucret})">
              💳 Ek Borcu Öde (${data.anlik_ucret.toFixed(2)} ₺)
            </button>
          </div>
        `;
      } else if (data.odendi_mi || data.anlik_ucret === 0) {
        dashUcretText.textContent = `${data.anlik_ucret.toFixed(2)} ₺`;
        odemeDurumAlani.innerHTML = `<span class="paid-badge">✅ ÖDENDİ (Bariyer Açılacak)</span>`;
      } else {
        // Henüz ödenmemiş
        dashUcretText.textContent = `${data.anlik_ucret.toFixed(2)} ₺`;
        odemeDurumAlani.innerHTML = `
          <button id="odemeYapModalBtn" class="btn btn-pay" onclick="acOdemeModal(${data.anlik_ucret})">
            💳 Hemen Öde (${data.anlik_ucret.toFixed(2)} ₺)
          </button>
        `;
      }

    } else {
      // Araç Dışarıda
      dashDurumPill.className = "status-pill outside";
      dashDurumPill.textContent = data.abonman_mi ? "Dışarıda (Abonman Aktif)" : "Dışarıda";
      liveCard.style.display = "none";
      emptyParkCard.style.display = "block";
    }

  } catch (e) {
    console.error("Durum çekme hatası:", e);
  }
}


// Ödeme Modalı
function acOdemeModal(tutar) {
  payModalAmount.textContent = `${tutar.toFixed(2)} ₺`;
  odemeModal.classList.add("open");
}

closeOdemeModal.addEventListener("click", () => {
  odemeModal.classList.remove("open");
});

// Kart İnteraktif Canlı Önizleme
payCardInput.addEventListener("input", (e) => {
  let v = e.target.value.replace(/\s+/g, '').replace(/[^0-9]/gi, '');
  let formatted = "";
  for (let i = 0; i < v.length; i++) {
    if (i > 0 && i % 4 === 0) formatted += " ";
    formatted += v[i];
  }
  e.target.value = formatted;
  cardNumPreview.textContent = formatted || "•••• •••• •••• ••••";
});

payHolderInput.addEventListener("input", (e) => {
  cardNamePreview.textContent = e.target.value.toUpperCase() || "AD SOYAD";
});

payExpInput.addEventListener("input", (e) => {
  let v = e.target.value.replace(/[^0-9]/gi, '');
  if (v.length >= 2) {
    v = v.substring(0, 2) + "/" + v.substring(2, 4);
  }
  e.target.value = v;
  cardExpPreview.textContent = v || "12/28";
});

// Online Ödemeyi Tamamla
async function onlineOdemeTamamla() {
  const payBtn = document.getElementById("paySubmitBtn");
  payBtn.disabled = true;
  payBtn.textContent = "🔒 3D Secure İşleniyor...";

  const kart_no = payCardInput.value.trim();
  const kart_sahibi = payHolderInput.value.trim();
  const skt = payExpInput.value.trim();
  const cvv = document.getElementById("payCvvInput").value.trim();

  try {
    const res = await fetch("/api/musteri/odeme-yap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plaka: aktifPlaka,
        kart_no,
        kart_sahibi,
        skt,
        cvv
      })
    });
    const data = await res.json();

    if (data.status === "ok") {
      odemeModal.classList.remove("open");
      
      // Makbuzu doldur
      receiptNo.textContent = data.makbuz.makbuz_no;
      receiptPlaka.textContent = data.makbuz.plaka;
      receiptTutar.textContent = `${data.makbuz.odenen_tutar.toFixed(2)} ₺`;
      receiptYontem.textContent = data.makbuz.odeme_yontemi;
      receiptTarih.textContent = new Date(data.makbuz.odeme_zamani * 1000).toLocaleString("tr-TR");

      makbuzModal.classList.add("open");
      guncelleDurum();
      showToast("Ödeme Alındı", "Otopark borcunuz başarıyla tahsil edildi.", "giris");
    } else {
      showToast("Ödeme Başarısız", data.mesaj, "cikis");
    }
  } catch (e) {
    showToast("Hata", e.message, "cikis");
  } finally {
    payBtn.disabled = false;
    payBtn.textContent = "🔒 Güvenli Ödemeyi Tamamla";
  }
}

function kapatMakbuz() {
  makbuzModal.classList.remove("open");
}

// ================= ABONMAN SATIN ALMA İŞLEMLERİ =================
let secilenPaketId = "aylik";
let secilenPaketTutar = 750;
let secilenPaketAd = "Aylık Abonman";

const abonmanModal = document.getElementById("abonmanModal");
const closeAbonmanModal = document.getElementById("closeAbonmanModal");

function secPaket(paketId, tutar, ad) {
  secilenPaketId = paketId;
  secilenPaketTutar = tutar;
  secilenPaketAd = ad;

  const pkgHaftalik = document.getElementById("pkgHaftalik");
  const pkgAylik = document.getElementById("pkgAylik");
  if (pkgHaftalik) pkgHaftalik.classList.remove("selected");
  if (pkgAylik) pkgAylik.classList.remove("selected");

  if (paketId === "haftalik" && pkgHaftalik) {
    pkgHaftalik.classList.add("selected");
  } else if (pkgAylik) {
    pkgAylik.classList.add("selected");
  }

  const nameEl = document.getElementById("abonmanSecilenPaketAdi");
  const tutarEl = document.getElementById("abonmanSecilenTutar");
  if (nameEl) nameEl.textContent = `${ad}:`;
  if (tutarEl) tutarEl.textContent = `${tutar.toFixed(2)} ₺`;
}

function acAbonmanModal() {
  if (abonmanModal) {
    abonmanModal.classList.add("open");
  }
}

if (closeAbonmanModal) {
  closeAbonmanModal.addEventListener("click", () => {
    abonmanModal.classList.remove("open");
  });
}

async function abonmanSatinAlTamamla() {
  const submitBtn = document.getElementById("abnSubmitBtn");
  submitBtn.disabled = true;
  submitBtn.textContent = "⭐ Abonman İşleniyor...";

  const kart_no = document.getElementById("abnCardInput").value.trim();
  const kart_sahibi = document.getElementById("abnHolderInput").value.trim();
  const skt = document.getElementById("abnExpInput").value.trim();
  const cvv = document.getElementById("abnCvvInput").value.trim();

  try {
    const res = await fetch("/api/abonman/satin-al", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plaka: aktifPlaka,
        paket_tipi: secilenPaketId,
        kart_no,
        kart_sahibi,
        skt,
        cvv
      })
    });
    const data = await res.json();

    if (data.status === "ok") {
      abonmanModal.classList.remove("open");

      // Makbuzu doldur
      receiptNo.textContent = data.makbuz.makbuz_no;
      receiptPlaka.textContent = data.makbuz.plaka;
      receiptTutar.textContent = `${data.makbuz.tutar.toFixed(2)} ₺`;
      receiptYontem.textContent = `Online Kredi Kartı (**** ${data.makbuz.kart_son4})`;
      receiptTarih.textContent = `${data.makbuz.gecerlilik} (Bitiş: ${data.makbuz.bitis_formatli})`;

      makbuzModal.classList.add("open");
      await guncelleDurum();
      showToast("Abonman Başlatıldı", `${data.makbuz.paket_ad} başarıyla aktif edildi!`, "giris");
    } else {
      showToast("İşlem Başarısız", data.mesaj, "cikis");
    }
  } catch (e) {
    showToast("Hata", e.message, "cikis");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "⭐ Abonmanı Aktif Et ve Öde";
  }
}

// ================= DOĞRUDAN ABONMAN AL (GİRİŞ EKRANI) =================
let directSecilenPaketId = "aylik";
let directSecilenPaketTutar = 750;
let directSecilenPaketAd = "Aylık Abonman";

function secDirectPaket(paketId, tutar, ad) {
  directSecilenPaketId = paketId;
  directSecilenPaketTutar = tutar;
  directSecilenPaketAd = ad;

  const pkgHaftalik = document.getElementById("directPkgHaftalik");
  const pkgAylik = document.getElementById("directPkgAylik");
  if (pkgHaftalik) pkgHaftalik.classList.remove("selected");
  if (pkgAylik) pkgAylik.classList.remove("selected");

  if (paketId === "haftalik" && pkgHaftalik) {
    pkgHaftalik.classList.add("selected");
  } else if (pkgAylik) {
    pkgAylik.classList.add("selected");
  }

  const nameEl = document.getElementById("directSecilenPaketAdi");
  const tutarEl = document.getElementById("directSecilenTutar");
  const btnEl = document.getElementById("directAbnSatinAlBtn");

  if (nameEl) nameEl.textContent = `${ad}:`;
  if (tutarEl) tutarEl.textContent = `${tutar.toFixed(2)} ₺`;
  if (btnEl) btnEl.textContent = `⭐ Abonmanı Satın Al ve Başlat (${tutar.toFixed(2)} ₺)`;
}

async function directAbonmanSatinAl() {
  const plakaInput = document.getElementById("directAbnPlakaInput");
  const emailInput = document.getElementById("directAbnEmailInput");
  const submitBtn = document.getElementById("directAbnSatinAlBtn");

  const plaka = plakaInput ? plakaInput.value.trim().toUpperCase() : "";
  const email = emailInput ? emailInput.value.trim().toLowerCase() : "";

  if (!plaka || plaka.length < 4) {
    showToast("Hata", "Lütfen geçerli bir araç plakası girin.", "cikis");
    return;
  }

  if (!email || !email.includes("@") || !email.includes(".")) {
    showToast("Hata", "Onay makbuzu için geçerli bir e-posta adresi girin.", "cikis");
    return;
  }

  const kart_no = document.getElementById("directCardInput").value.trim();
  const kart_sahibi = document.getElementById("directHolderInput").value.trim();
  const skt = document.getElementById("directExpInput").value.trim();
  const cvv = document.getElementById("directCvvInput").value.trim();

  submitBtn.disabled = true;
  submitBtn.textContent = "⭐ Abonman Başlatılıyor...";

  try {
    const res = await fetch("/api/abonman/satin-al", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plaka: plaka,
        paket_tipi: directSecilenPaketId,
        email: email,
        kart_no,
        kart_sahibi,
        skt,
        cvv
      })
    });
    const data = await res.json();

    if (data.status === "ok") {
      // Müşteri oturumunu aç
      aktifPlaka = plaka;
      aktifEmail = email;
      localStorage.setItem("musteri_plaka", plaka);
      localStorage.setItem("musteri_email", email);

      // Makbuzu doldur
      receiptNo.textContent = data.makbuz.makbuz_no;
      receiptPlaka.textContent = data.makbuz.plaka;
      receiptTutar.textContent = `${data.makbuz.tutar.toFixed(2)} ₺`;
      receiptYontem.textContent = `Online Kredi Kartı (**** ${data.makbuz.kart_son4})`;
      receiptTarih.textContent = `${data.makbuz.gecerlilik} (Bitiş: ${data.makbuz.bitis_formatli})`;

      makbuzModal.classList.add("open");
      initDashboard();
      showToast("Abonman Aktif!", `Tebrikler! ${data.makbuz.paket_ad} başarıyla aktif edildi.`, "giris");
    } else {
      showToast("Satın Alma Başarısız", data.mesaj, "cikis");
    }
  } catch (e) {
    showToast("Hata", e.message, "cikis");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = `⭐ Abonmanı Satın Al ve Başlat (${directSecilenPaketTutar.toFixed(2)} ₺)`;
  }
}

// Kapasite Bilgisini Çek ve Canlı Göster
async function guncelleMusteriKapasite() {
  try {
    const res = await fetch('/api/kapasite');
    const data = await res.json();
    if (data.status === 'ok' && data.kapasite) {
      const kap = data.kapasite;
      const bos = kap.bos || {};
      const toplamKap = kap.kapasite || {};
      const bosToplamEl = document.getElementById('musteriBosToplam');
      const bosDetayEl = document.getElementById('musteriBosDetay');
      const liveDotEl = document.getElementById('musteriLiveDot');

      if (bosToplamEl) {
        bosToplamEl.textContent = `${bos.toplam ?? 0} / ${toplamKap.toplam ?? 0} Boş`;
        if (bos.toplam <= 0) {
          bosToplamEl.style.color = '#ef4444';
          if (liveDotEl) {
            liveDotEl.style.background = '#ef4444';
            liveDotEl.style.boxShadow = '0 0 8px #ef4444';
          }
        } else if (bos.normal <= 0) {
          bosToplamEl.style.color = '#f59e0b';
          if (liveDotEl) {
            liveDotEl.style.background = '#f59e0b';
            liveDotEl.style.boxShadow = '0 0 8px #f59e0b';
          }
        } else {
          bosToplamEl.style.color = '#38bdf8';
          if (liveDotEl) {
            liveDotEl.style.background = '#10b981';
            liveDotEl.style.boxShadow = '0 0 8px #10b981';
          }
        }
      }
      if (bosDetayEl) {
        bosDetayEl.innerHTML = `Abonmansız: <strong>${bos.normal ?? 0} Boş</strong> | Abonmanlı: <strong>${bos.abonman ?? 0} Boş</strong>`;
      }
    }
  } catch (e) {
    console.warn("Müşteri kapasite bilgisi alınamadı:", e);
  }
}

// Başlangıç Kontrolü
if (aktifPlaka) {
  initDashboard();
}

guncelleMusteriKapasite();
setInterval(guncelleMusteriKapasite, 3500);

