import streamlit as st

# ── İL SÜTUNLARI — GLOBAL sabit (birden fazla sayfadan erişilir: Cari Liste
# tablosunda kolon olarak, Kullanıcılar sayfasındaki Kolon Ayarları'nda genişlik
# ayarı olarak). Tek bir sayfanın içinde tanımlanırsa diğer sayfa NameError alır.
_IL_SUTUN_LISTESI = ["İstanbul","Bursa","İzmir","Manisa","Tekirdağ","Kocaeli","Ankara","Konya",
                     "Denizli","Adana","Gaziantep","Kayseri","Antalya","Aydın","Balıkesir",
                     "Diyarbakır","Erzurum","Eskişehir","Hatay","Kahramanmaraş","Malatya",
                     "Mardin","Mersin","Muğla","Ordu","Sakarya","Samsun","Trabzon","Van",
                     "Şanlıurfa","Diğer"]

# "Diğer" başlığının altına, alt alta yazılacak iller (başlığı olmayan 50 il).
# "Varış İlleri" hızlı-girişinde bu illerden biri yazılırsa "Diğer" sütununa,
# üstteki 30 il de kendi sütununa gider.
_IL_DIGER_LISTESI = ["Adıyaman","Afyonkarahisar","Ağrı","Aksaray","Amasya","Ardahan","Artvin",
                     "Bartın","Batman","Bayburt","Bilecik","Bingöl","Bitlis","Bolu","Burdur",
                     "Çanakkale","Çankırı","Çorum","Düzce","Edirne","Elazığ","Erzincan",
                     "Giresun","Gümüşhane","Hakkari","Iğdır","Isparta","Karabük","Karaman",
                     "Kars","Kastamonu","Kırıkkale","Kırklareli","Kırşehir","Kilis","Kütahya",
                     "Muş","Nevşehir","Niğde","Osmaniye","Rize","Siirt","Sinop","Sivas",
                     "Şırnak","Tokat","Tunceli","Uşak","Yalova","Yozgat","Zonguldak"]

def _tr_buyuk(_s):
    """Türkçe karakterleri doğru büyüten upper() — Python'un varsayılan .upper()
    fonksiyonu 'i' harfini 'İ' değil 'I' yapar, bu yanlış Türkçe büyük harfe
    yol açar. Kargo Girişi gibi serbest metin alanlarını büyük harfe çevirmek
    için her yerde bu fonksiyon kullanılır."""
    return str(_s or "").replace("i", "İ").replace("ı", "I").upper()

import sqlite3
import pandas as pd
import shutil
import os
import io
import re
import json
import time
import concurrent.futures
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════════════
# 📌 PROJE_KURALLARI — MWCRMPRO geliştirme kuralları (Claude için otomatik bağlam)
# main.py yeni bir Claude sohbetine yüklendiğinde bu blok otomatik okunur.
# Aynı metin CRM içinde: Kullanıcı Yönetimi → 📌 Kurallar sekmesinde de görünür.
# ═══════════════════════════════════════════════════════════════════════════
KURALLAR_PIN = "1907"  # Kurallar sekmesi için erişim PIN'i — değiştirmek istersen söyle yeter

PROJE_KURALLARI = """
### 1) Git Komutları
Her kod teslimatının sonunda:
```
git add main.py
git commit -m "..."   (değişikliği özetleyen mesaj)
git push
```

### 2) Kesin Çalışma Kuralları
- Yeni SQL migration yok, sadece mevcut tabloları kullan.
- requirements.txt'e yeni pip paketi ekleme, sadece stdlib (urllib vb.).
- Kullanıcıya asla manuel/elle kod değişikliği yaptırma; her değişikliği tam çalışır main.py dosyası olarak ver.
- Stabilite önceliklidir, çalışan özellikleri bozma. (Not arşivleme özelliğinde geçmişte veri kaybı yaşandı — bu alanda ekstra dikkatli ol.)
- `cari_aciklamalar` tablosuna insert: sadece `cari_id`, `aciklama`, `olusturan` kolonları var; `tip` / `tarih` kolonu YOK.

### 3) Veri Güvenliği — KRİTİK
Asla veri silinmeyecek/kaybolmayacak. Silme gerektiren hiçbir işlem (toplu silme dahil) önce açık kullanıcı onayı olmadan YAPILMAZ.

### 4) MacroDroid Entegrasyonu
- Supabase proje: `asinwzxwmkkrcbtjrkoq.supabase.co` — tablolar: `islem_kaydi`, `cari_kartlar`, `kisiler`
- Amaç: Gelen/Giden Arama & SMS'te arayan/gönderen adını rehberden bulup CRM'e (`musteri_adi`) otomatik yazdırmak.
- Kullanıcı MacroDroid'i Türkçe arayüzde kullanıyor, teknik bilgisi sınırlı — adımlar tek tek, ekran görüntüsüyle doğrulanarak anlatılmalı.
- "Kişileri Al" + sözlük yöntemi ÇOK YAVAŞ (8000 kişide ~4 dk) — bunun yerine anılık sistem değişkenleri kullanılmalı: `*Çağrı ismi`, `*Gelen SMS kişisi`, `*Giden SMS kişisi`

### 5) Supabase Erişim Bilgileri
- `SUPABASE_URL` = `https://asinwzxwmkkrcbtjrkoq.supabase.co`
- `SUPABASE_ANON_KEY` = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFzaW53enh3bWtrcmNidGpya29xIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA3MzM4MzQsImV4cCI6MjA5NjMwOTgzNH0.7WNPNWG-uXO7COSOhzVyAbR-MTaP6RdSlOTI0IfyNAU`

### 6) Muhasebe (Paraşüt) Entegrasyonu
CRM arayüzünde **"Muhasebe"** adıyla görünür; **"Paraşüt"** ismi hiçbir yerde geçmez.
- `CLIENT_ID` = `Idqed6FhS1AFfc-VH9e7JFvB_vpwLJiMfWibaozKpbE`
- `CLIENT_SECRET` = `EHBUuu5JvCEgg48kcZ90cKYu2ZBHmO1eZVJMQhPalDg`
- `CALLBACK_URL` = `urn:ietf:wg:oauth:2.0:oob`
- `COMPANY_ID` = `843974`
- `API_BASE` = `https://api.parasut.com` (doğru yol: `/v4/{company_id}/...` — `companies/` YOK)
"""

# ── SUPABASE BAĞLANTISI ───────────────────────────────────────────────────────
def sb_or_sqlite():
    """Supabase varsa True, yoksa SQLite kullan"""
    try:
        url = st.secrets.get("SUPABASE_URL","")
        key = st.secrets.get("SUPABASE_KEY","")
        return bool(url and key)
    except:
        return False

@st.cache_resource
def get_sb_client():
    """Supabase client — tek seferlik oluştur, cache'le"""
    try:
        from supabase import create_client, ClientOptions
        url = st.secrets.get("SUPABASE_URL","")
        key = st.secrets.get("SUPABASE_KEY","")
        if url and key:
            try:
                # Max rows limitini kaldır
                opts = ClientOptions(postgrest_client_timeout=60)
                client = create_client(url, key, options=opts)
                client.postgrest.auth(key)
                return client
            except:
                return create_client(url, key)
    except:
        pass
    return None


# ── İL GÖNDERİM MATRİSİ — GLOBAL (Cari Liste tablosu VE Notlar&Randevu
# dialog'undaki "Varış/Fiyat" sekmesi AYNI fonksiyonu/önbelleği paylaşır.
# Ayrı ayrı tanımlanırsa, dialogdan kaydedince Cari Liste'nin önbelleği
# temizlenmiyor, yazılan iller tabloda hemen görünmüyordu.
@st.cache_data(ttl=30, show_spinner=False)
def _il_gonderim_matrisi_yukle():
    try:
        _sb_ilm = get_sb_client()
        if _sb_ilm:
            _r_ilm = _sb_ilm.table("kullanici_tercih").select("deger").eq(
                "kullanici", "__liste_ui__").eq("anahtar", "_il_gonderim_matrisi").execute()
            if _r_ilm.data:
                import json as _ilmj
                return _ilmj.loads(_r_ilm.data[0]["deger"])
    except Exception:
        pass
    return {}

def _il_gonderim_matrisi_kaydet(_matris):
    try:
        _sb_ilm2 = get_sb_client()
        if _sb_ilm2:
            import json as _ilmj2
            _deger = _ilmj2.dumps(_matris, ensure_ascii=False)
            _sb_ilm2.table("kullanici_tercih").delete().eq("kullanici", "__liste_ui__").eq("anahtar", "_il_gonderim_matrisi").execute()
            _sb_ilm2.table("kullanici_tercih").insert({"kullanici": "__liste_ui__", "anahtar": "_il_gonderim_matrisi", "deger": _deger}).execute()
    except Exception:
        pass


# ── MANUEL ALICI FİRMA HAFIZASI — Kargo Girişi'nde elle yazılan Alıcı Firma
# isimleri kalıcı olarak {firma: il} şeklinde saklanır. Bir daha o firma adı
# yazılınca ili otomatik gelir; yeni bir firma-il çifti girildikçe otomatik
# kaydedilir. cari_kartlar'a yeni kolon açılmaz (migration yok kuralı).
@st.cache_data(ttl=30, show_spinner=False)
def _kg_manuel_alici_yukle():
    try:
        _sb_ma = get_sb_client()
        if _sb_ma:
            _r_ma = _sb_ma.table("kullanici_tercih").select("deger").eq(
                "kullanici", "__liste_ui__").eq("anahtar", "_kargo_manuel_alici_firmalar").execute()
            if _r_ma.data:
                import json as _maj
                return _maj.loads(_r_ma.data[0]["deger"])
    except Exception:
        pass
    return {}

def _kg_manuel_alici_kaydet(_sozluk):
    try:
        _sb_ma2 = get_sb_client()
        if _sb_ma2:
            import json as _maj2
            _deger = _maj2.dumps(_sozluk, ensure_ascii=False)
            _sb_ma2.table("kullanici_tercih").delete().eq("kullanici", "__liste_ui__").eq("anahtar", "_kargo_manuel_alici_firmalar").execute()
            _sb_ma2.table("kullanici_tercih").insert({"kullanici": "__liste_ui__", "anahtar": "_kargo_manuel_alici_firmalar", "deger": _deger}).execute()
    except Exception:
        pass


@st.cache_resource
def get_sb_service():
    """Supabase service_role client — log ve admin işlemler için"""
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL","")
        # Önce service key dene, yoksa normal key
        key = st.secrets.get("SUPABASE_SERVICE_KEY","") or st.secrets.get("SUPABASE_KEY","")
        if url and key:
            return create_client(url, key)
    except:
        pass
    return None

def get_sb():
    return get_sb_client()

# ── MUHASEBE (harici muhasebe altyapısı) BAĞLANTISI ───────────────────────────
# NOT: Bu bilgiler kullanıcı tarafından verildi, sadece stdlib (urllib) ile
# çağrı yapılır — requirements.txt'e yeni paket eklenmedi.
_MUH_CLIENT_ID     = st.secrets.get("MUHASEBE_CLIENT_ID", "Idqed6FhS1AFfc-VH9e7JFvB_vpwLJiMfWibaozKpbE")
_MUH_CLIENT_SECRET = st.secrets.get("MUHASEBE_CLIENT_SECRET", "EHBUuu5JvCEgg48kcZ90cKYu2ZBHmO1eZVJMQhPalDg")
_MUH_REDIRECT_URI  = "urn:ietf:wg:oauth:2.0:oob"
_MUH_COMPANY_ID    = st.secrets.get("MUHASEBE_COMPANY_ID", "843974")
_MUH_API_BASE      = "https://api.parasut.com"
_MUH_UA            = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def _muh_token_oku():
    """Kayıtlı muhasebe bağlantı token'ını kullanici_tercih tablosundan okur (yeni tablo açılmadı)."""
    try:
        sb = get_sb_client()
        if sb:
            r = sb.table("kullanici_tercih").select("deger").eq("kullanici", "_sistem").eq("anahtar", "_muh_token").execute()
            if r.data:
                return json.loads(r.data[0]["deger"])
    except:
        pass
    return None

def _muh_token_yaz(token_dict):
    try:
        sb = get_sb_client()
        if sb:
            deger = json.dumps(token_dict)
            sb.table("kullanici_tercih").delete().eq("kullanici", "_sistem").eq("anahtar", "_muh_token").execute()
            sb.table("kullanici_tercih").insert({"kullanici": "_sistem", "anahtar": "_muh_token", "deger": deger}).execute()
            return True
    except:
        pass
    return False

def _muh_authorize_url():
    import urllib.parse
    params = {"client_id": _MUH_CLIENT_ID, "redirect_uri": _MUH_REDIRECT_URI, "response_type": "code"}
    return f"{_MUH_API_BASE}/oauth/authorize?" + urllib.parse.urlencode(params)

def _muh_token_istegi(form_data):
    """oauth/token uç noktasına POST atar — stdlib urllib ile."""
    import urllib.request, urllib.parse, urllib.error
    data = urllib.parse.urlencode(form_data).encode()
    req = urllib.request.Request(f"{_MUH_API_BASE}/oauth/token", data=data, method="POST",
                                  headers={"Content-Type": "application/x-www-form-urlencoded",
                                           "Accept": "application/json",
                                           "User-Agent": _MUH_UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token = json.loads(resp.read().decode())
            token["_alindigi_zaman"] = time.time()
            _muh_token_yaz(token)
            return token, None
    except urllib.error.HTTPError as e:
        try:
            detay = e.read().decode()[:300]
        except:
            detay = str(e)
        return None, f"HTTP {e.code}: {detay}"
    except Exception as e:
        return None, str(e)

def _muh_kod_ile_baglan(kod):
    return _muh_token_istegi({
        "grant_type": "authorization_code",
        "client_id": _MUH_CLIENT_ID,
        "client_secret": _MUH_CLIENT_SECRET,
        "redirect_uri": _MUH_REDIRECT_URI,
        "code": kod,
    })

def _muh_token_yenile(refresh_token):
    return _muh_token_istegi({
        "grant_type": "refresh_token",
        "client_id": _MUH_CLIENT_ID,
        "client_secret": _MUH_CLIENT_SECRET,
        "redirect_uri": _MUH_REDIRECT_URI,
        "refresh_token": refresh_token,
    })

def _muh_gecerli_token():
    """Kayıtlı token'ı döner; süresi dolmaya yakınsa otomatik yeniler."""
    tok = _muh_token_oku()
    if not tok:
        return None, "Muhasebe bağlantısı henüz kurulmamış."
    alindigi = tok.get("_alindigi_zaman", 0)
    expires_in = tok.get("expires_in", 7200)
    if time.time() - alindigi > (expires_in - 120):
        if not tok.get("refresh_token"):
            return None, "Oturum süresi dolmuş, yeniden bağlanmanız gerekiyor."
        yeni, hata = _muh_token_yenile(tok["refresh_token"])
        if yeni:
            return yeni, None
        return None, f"Bağlantı yenilenemedi: {hata}"
    return tok, None

def _muh_api_get(yol, params=None):
    """Muhasebe API'sinden GET isteği yapar. yol örn: /v4/843974/sales_invoices"""
    import urllib.request, urllib.parse, urllib.error
    tok, hata = _muh_gecerli_token()
    if not tok:
        return None, hata
    url = f"{_MUH_API_BASE}{yol}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok['access_token']}",
        "Accept": "application/json",
        "User-Agent": _MUH_UA,
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        try:
            detay = e.read().decode()[:300]
        except:
            detay = str(e)
        return None, f"HTTP {e.code}: {detay}"
    except Exception as e:
        return None, str(e)

def _muh_api_get_tumu(yol, params=None, sayfa_limiti=40):
    """Parasut sayfa başına en fazla 25 kayıt veriyor — 'ne varsa birebir' tüm kayıtları
    getirmek için sayfa sayfa gezip birleştirir. Çağıran kod tarafında değişiklik
    gerekmesin diye sonucu aynı {"data": [...]} JSON:API zarfı içinde döner.
    "include" parametresi verilmişse (örn. include=contact,details.product), Parasut'un
    döndüğü "included" (ilişkili kayıt: müşteri adı, ürün adı vb.) bilgisi de "included"
    anahtarı altında, sayfalar arası tekrarsız birleştirilerek döner."""
    _tum = []
    _tum_included = {}
    _sayfa = 1
    _params = dict(params or {})
    _params["page[size]"] = 25
    while _sayfa <= sayfa_limiti:
        _params["page[number]"] = _sayfa
        _veri, _hata = _muh_api_get(yol, params=_params)
        if _hata:
            if _tum:
                break  # bir kısmı gelmişse elimizdekiyle devam et, hatayı yutma
            return None, _hata
        _bu_sayfa = (_veri or {}).get("data", [])
        for _inc in (_veri or {}).get("included", []) or []:
            _tum_included[(_inc.get("type"), _inc.get("id"))] = _inc
        if not _bu_sayfa:
            break
        _tum.extend(_bu_sayfa)
        if len(_bu_sayfa) < 25:
            break
        _sayfa += 1
    return {"data": _tum, "included": list(_tum_included.values())}, None

def _muh_dahil_index(veri):
    """JSON:API "included" listesinden (type,id) -> kayıt sözlüğü oluşturur.
    Müşteri adı, ürün adı gibi ilişkili kayıtları hızlıca bulmak için kullanılır."""
    _idx = {}
    for _inc in (veri or {}).get("included", []) or []:
        _idx[(_inc.get("type"), _inc.get("id"))] = _inc
    return _idx

def _muh_iliski_kayit(kayit, iliski_adi, dahil_index):
    """Bir kaydın TEKİL ilişkisinin (örn. 'contact') included içindeki tam halini döner."""
    _ref = ((kayit.get("relationships") or {}).get(iliski_adi) or {}).get("data")
    if not _ref or not dahil_index:
        return None
    return dahil_index.get((_ref.get("type"), _ref.get("id")))

def _muh_iliski_liste(kayit, iliski_adi, dahil_index):
    """Bir kaydın ÇOĞUL ilişkisinin (örn. 'details') included içindeki tam hallerini liste olarak döner."""
    _refs = ((kayit.get("relationships") or {}).get(iliski_adi) or {}).get("data") or []
    if not dahil_index:
        return []
    _sonuc = []
    for _r in _refs:
        _bulunan = dahil_index.get((_r.get("type"), _r.get("id")))
        if _bulunan:
            _sonuc.append(_bulunan)
    return _sonuc

def _muh_kalem_detay_goster(kayit, dahil_index):
    """Bir fatura/teklif/gider kaydının kalemlerini (ürün/hizmet, miktar, fiyat, KDV) listeler."""
    _kalemler = _muh_iliski_liste(kayit, "details", dahil_index)
    if not _kalemler:
        st.caption("Kalem bilgisi bulunamadı (eski kayıt veya API'den include gelmedi).")
        return
    for _kl in _kalemler:
        _ka = _kl.get("attributes") or {}
        _urun = _muh_iliski_kayit(_kl, "product", dahil_index)
        _urun_ad = ((_urun or {}).get("attributes") or {}).get("name", "—") if _urun else "—"
        _miktar = _ka.get("quantity", "")
        _fiyat = _ka.get("unit_price", "")
        _kdv = _ka.get("vat_rate", "")
        _acik = _ka.get("description", "")
        st.markdown(f"- **{_urun_ad}** — {_acik} · {_miktar} × {_fiyat} ₺ · KDV %{_kdv}")

def _muh_api_istek(yol, method="POST", body=None):
    """Muhasebe API'sine POST/PUT/DELETE isteği yapar (JSON:API gövdesiyle)."""
    import urllib.request, urllib.error
    tok, hata = _muh_gecerli_token()
    if not tok:
        return None, hata
    url = f"{_MUH_API_BASE}{yol}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {tok['access_token']}",
        "Accept": "application/json",
        "Content-Type": "application/vnd.api+json",
        "User-Agent": _MUH_UA,
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            _ham = resp.read().decode()
            return (json.loads(_ham) if _ham.strip() else {}), None
    except urllib.error.HTTPError as e:
        try:
            detay = e.read().decode()[:500]
        except:
            detay = str(e)
        return None, f"HTTP {e.code}: {detay}"
    except Exception as e:
        return None, str(e)

def _muh_contact_id_bul_veya_olustur(cari_id, firma_adi):
    """CRM'deki cari için muhasebe sisteminde kayıtlı contact id'yi bulur, yoksa yeni oluşturur."""
    _anahtar = f"_muh_contact_{cari_id}"
    try:
        sb = get_sb_client()
        if sb:
            r = sb.table("kullanici_tercih").select("deger").eq("kullanici", "_sistem").eq("anahtar", _anahtar).execute()
            if r.data:
                return r.data[0]["deger"], None
    except:
        pass

    _sonuc, _hata = _muh_api_istek(
        f"/v4/{_MUH_COMPANY_ID}/contacts", method="POST",
        body={"data": {"type": "contacts", "attributes": {
            "name": firma_adi, "account_type": "customer", "contact_type": "company",
        }}}
    )
    if _hata:
        return None, f"Müşteri kaydı oluşturulamadı: {_hata}"
    _yeni_id = ((_sonuc or {}).get("data") or {}).get("id")
    if not _yeni_id:
        return None, "Müşteri kaydı oluşturuldu ama id alınamadı."
    try:
        sb = get_sb_client()
        if sb:
            sb.table("kullanici_tercih").insert({"kullanici": "_sistem", "anahtar": _anahtar, "deger": str(_yeni_id)}).execute()
    except:
        pass
    return _yeni_id, None

def _muh_urun_id_bul_veya_olustur(urun_adi, kdv_orani=18):
    """Fatura/teklif/gider kalemi (detail) için Parasut'ta ürün/hizmet kaydını bulur,
    yoksa yeni oluşturur. Parasut API'si her kalemde mutlaka bir 'product' ilişkisi
    istiyor — bu olmadan HTTP 422 'Ürün/hizmet doldurulmalı' hatası dönüyor.
    Kalemin 'Açıklama / Hizmet' alanı aynı zamanda ürün/hizmet adı olarak kullanılır;
    aynı isimle bir daha çağrıldığında tekrar ürün oluşturmaz, kaydı Supabase'te
    (kullanici_tercih) önbelleğe alır."""
    _ad_norm = (urun_adi or "").strip()[:200] or "Genel Hizmet"
    _anahtar = f"_muh_urun_{_ad_norm.lower()}"
    try:
        sb = get_sb_client()
        if sb:
            r = sb.table("kullanici_tercih").select("deger").eq("kullanici", "_sistem").eq("anahtar", _anahtar).execute()
            if r.data:
                return r.data[0]["deger"], None
    except:
        pass

    _veri, _hata = _muh_api_get(f"/v4/{_MUH_COMPANY_ID}/products",
                                 params={"filter[name]": _ad_norm, "page[size]": 5})
    if not _hata:
        for _d in (_veri or {}).get("data", []):
            if str((_d.get("attributes") or {}).get("name", "")).strip().lower() == _ad_norm.lower():
                _bulunan_id = _d.get("id")
                try:
                    sb = get_sb_client()
                    if sb:
                        sb.table("kullanici_tercih").insert({"kullanici": "_sistem", "anahtar": _anahtar, "deger": str(_bulunan_id)}).execute()
                except:
                    pass
                return _bulunan_id, None

    _sonuc, _hata2 = _muh_api_istek(
        f"/v4/{_MUH_COMPANY_ID}/products", method="POST",
        body={"data": {"type": "products", "attributes": {
            "name": _ad_norm, "vat_rate": float(kdv_orani or 18),
        }}}
    )
    if _hata2:
        return None, f"Ürün/hizmet kaydı oluşturulamadı: {_hata2}"
    _yeni_urun_id = ((_sonuc or {}).get("data") or {}).get("id")
    if not _yeni_urun_id:
        return None, "Ürün/hizmet kaydı oluşturuldu ama id alınamadı."
    try:
        sb = get_sb_client()
        if sb:
            sb.table("kullanici_tercih").insert({"kullanici": "_sistem", "anahtar": _anahtar, "deger": str(_yeni_urun_id)}).execute()
    except:
        pass
    return _yeni_urun_id, None

def _muh_fatura_olustur(contact_id, aciklama, miktar, birim_fiyat, kdv_orani, fatura_tarihi, vade_tarihi):
    """Yeni satış faturası oluşturur — tek kalemli basit fatura.
    NOT: Parasut, kalem (detail) verisini ayrı bir "included" bölümü ile DEĞİL,
    relationships.details.data[] içine doğrudan gömülü "attributes" ile bekliyor
    (resmi PHP istemci örneğinden doğrulandı). Ayrıca her kalemde bir "product"
    ilişkisi zorunlu (bkz. _muh_urun_id_bul_veya_olustur)."""
    _urun_id, _urun_hata = _muh_urun_id_bul_veya_olustur(aciklama, kdv_orani)
    if _urun_hata:
        return None, _urun_hata
    _govde = {
        "data": {
            "type": "sales_invoices",
            "attributes": {
                "item_type": "invoice",
                "description": aciklama or "",
                "issue_date": str(fatura_tarihi),
                "due_date": str(vade_tarihi),
                "currency": "TRL",
                "exchange_rate": 1,
            },
            "relationships": {
                "contact": {"data": {"type": "contacts", "id": str(contact_id)}},
                "details": {
                    "data": [
                        {
                            "type": "sales_invoice_details",
                            "attributes": {
                                "quantity": float(miktar),
                                "unit_price": float(birim_fiyat),
                                "vat_rate": float(kdv_orani),
                                "description": aciklama or "",
                            },
                            "relationships": {
                                "product": {"data": {"type": "products", "id": str(_urun_id)}}
                            },
                        }
                    ]
                },
            },
        },
    }
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/sales_invoices", method="POST", body=_govde)

def _muh_fatura_sil(invoice_id):
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/sales_invoices/{invoice_id}", method="DELETE")

# ── MUHASEBE — GENİŞLETİLMİŞ KAYNAKLAR (Teklifler/Müşteriler/Tedarikçiler/vb.) ─
# NOT: Bu fonksiyonlar Parasut API'sinin bilinen JSON:API kurallarına göre
# yazıldı ama gerçek uçlar bu ortamdan test edilemiyor (ağ kısıtı). Canlıda bir
# alan adı hatası çıkarsa (örn. sales_offers) hata mesajıyla birlikte hızlıca
# düzeltilecektir — mevcut hata gösterme yapısı zaten ham API hatasını ekranda
# gösteriyor, uygulama çökmüyor.

def _muh_contacts_getir(account_type=None, sayfa_boyutu=25):
    # NOT: Parasut contacts uç noktası "created_at" sıralamasını kabul etmiyor
    # (sadece id, balance, abs_balance, name, email) — en yeni ekleneni en üstte
    # göstermek için "-id" kullanılıyor (id arttıkça daha yeni kayıt demek).
    params = {"sort": "-id"}
    if account_type:
        params["filter[account_type]"] = account_type
    return _muh_api_get_tumu(f"/v4/{_MUH_COMPANY_ID}/contacts", params=params)

def _muh_contact_olustur(ad, account_type="customer", telefon="", email="", adres=""):
    _attrs = {"name": ad, "account_type": account_type, "contact_type": "company"}
    if telefon: _attrs["phone"] = telefon
    if email: _attrs["email"] = email
    if adres: _attrs["address"] = adres
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/contacts", method="POST",
                           body={"data": {"type": "contacts", "attributes": _attrs}})

def _muh_contact_sil(contact_id):
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/contacts/{contact_id}", method="DELETE")

def _muh_contact_ada_gore_bul_veya_olustur(ad, account_type="supplier"):
    """CRM'de karşılığı olmayan kayıtlar (örn. tedarikçi) için isme göre arar, bulamazsa oluşturur."""
    veri, hata = _muh_api_get(f"/v4/{_MUH_COMPANY_ID}/contacts",
                               params={"filter[name]": ad, "page[size]": 5})
    if not hata:
        for _d in (veri or {}).get("data", []):
            if str((_d.get("attributes") or {}).get("name", "")).strip().lower() == ad.strip().lower():
                return _d.get("id"), None
    return _muh_contact_olustur(ad, account_type)

def _muh_employees_getir():
    return _muh_api_get_tumu(f"/v4/{_MUH_COMPANY_ID}/employees")

def _muh_employee_olustur(ad, soyad, email="", tc_no=""):
    _attrs = {"name": ad, "surname": soyad}
    if email: _attrs["email"] = email
    if tc_no: _attrs["identity_number"] = tc_no
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/employees", method="POST",
                           body={"data": {"type": "employees", "attributes": _attrs}})

def _muh_employee_sil(emp_id):
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/employees/{emp_id}", method="DELETE")

def _muh_accounts_getir():
    return _muh_api_get_tumu(f"/v4/{_MUH_COMPANY_ID}/accounts")

def _muh_teklifler_getir():
    return _muh_api_get_tumu(f"/v4/{_MUH_COMPANY_ID}/sales_offers",
                              params={"sort": "-issue_date", "include": "contact,details.product"})

def _muh_teklif_olustur(contact_id, aciklama, miktar, birim_fiyat, kdv_orani, teklif_tarihi, gecerlilik_tarihi):
    """NOT: sales_invoices ile aynı gömülü-attributes yapısı kullanılıyor (bkz. _muh_fatura_olustur notu).
    Her kalemde bir "product" ilişkisi zorunlu (bkz. _muh_urun_id_bul_veya_olustur)."""
    _urun_id, _urun_hata = _muh_urun_id_bul_veya_olustur(aciklama, kdv_orani)
    if _urun_hata:
        return None, _urun_hata
    _govde = {
        "data": {
            "type": "sales_offers",
            "attributes": {
                "description": aciklama or "", "issue_date": str(teklif_tarihi),
                "expiry_date": str(gecerlilik_tarihi), "currency": "TRL", "exchange_rate": 1,
            },
            "relationships": {
                "contact": {"data": {"type": "contacts", "id": str(contact_id)}},
                "details": {
                    "data": [
                        {
                            "type": "sales_offer_details",
                            "attributes": {
                                "quantity": float(miktar), "unit_price": float(birim_fiyat),
                                "vat_rate": float(kdv_orani), "description": aciklama or "",
                            },
                            "relationships": {
                                "product": {"data": {"type": "products", "id": str(_urun_id)}}
                            },
                        }
                    ]
                },
            },
        },
    }
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/sales_offers", method="POST", body=_govde)

def _muh_teklif_sil(offer_id):
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/sales_offers/{offer_id}", method="DELETE")

def _muh_giderler_getir():
    return _muh_api_get_tumu(f"/v4/{_MUH_COMPANY_ID}/purchase_bills",
                              params={"sort": "-issue_date", "include": "contact,details.product"})

def _muh_gider_olustur(contact_id, aciklama, miktar, birim_fiyat, kdv_orani, fatura_tarihi, vade_tarihi):
    """NOT: sales_invoices ile aynı gömülü-attributes yapısı kullanılıyor (bkz. _muh_fatura_olustur notu).
    Her kalemde bir "product" ilişkisi zorunlu (bkz. _muh_urun_id_bul_veya_olustur)."""
    _urun_id, _urun_hata = _muh_urun_id_bul_veya_olustur(aciklama, kdv_orani)
    if _urun_hata:
        return None, _urun_hata
    _govde = {
        "data": {
            "type": "purchase_bills",
            "attributes": {
                "item_type": "invoice", "description": aciklama or "", "issue_date": str(fatura_tarihi),
                "due_date": str(vade_tarihi), "currency": "TRL", "exchange_rate": 1,
            },
            "relationships": {
                "contact": {"data": {"type": "contacts", "id": str(contact_id)}},
                "details": {
                    "data": [
                        {
                            "type": "purchase_bill_details",
                            "attributes": {
                                "quantity": float(miktar), "unit_price": float(birim_fiyat),
                                "vat_rate": float(kdv_orani), "description": aciklama or "",
                            },
                            "relationships": {
                                "product": {"data": {"type": "products", "id": str(_urun_id)}}
                            },
                        }
                    ]
                },
            },
        },
    }
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/purchase_bills", method="POST", body=_govde)

def _muh_gider_sil(bill_id):
    return _muh_api_istek(f"/v4/{_MUH_COMPANY_ID}/purchase_bills/{bill_id}", method="DELETE")

def _muh_cekler_getir():
    return _muh_api_get_tumu(f"/v4/{_MUH_COMPANY_ID}/checks")

def _muh_liste_render(kayitlar, kolonlar, sil_fn=None, key_prefix="ml", bos_mesaj="Kayıt bulunamadı.",
                       dahil_index=None, detay_fn=None):
    """Ortak liste render — kolonlar: [(baslik, attr_anahtari, formatter|None), ...]
    attr_anahtari "@iliski_adi" ile başlarsa (örn. "@contact"), o kaydın ilişkili
    kaydının adı dahil_index'ten bulunup gösterilir (Müşteri/Tedarikçi sütunu için).
    detay_fn(kayit, dahil_index) verilirse her satırın altına, "🔍" butonuna
    basılınca açılan bir kalem/detay paneli eklenir."""
    if not kayitlar:
        st.info(bos_mesaj)
        return
    _buton_sayisi = (1 if sil_fn else 0) + (1 if detay_fn else 0)
    _oranlar = [2] * len(kolonlar) + ([1] * _buton_sayisi if _buton_sayisi else [])
    _hc = st.columns(_oranlar)
    for _c, (_b, _k, _f) in zip(_hc, kolonlar):
        _c.markdown(f"**{_b}**")
    for _kk in kayitlar:
        _a = _kk.get("attributes", {}) or {}
        _rid = _kk.get("id")
        _rc = st.columns(_oranlar)
        for _c, (_b, _k, _f) in zip(_rc, kolonlar):
            if isinstance(_k, str) and _k.startswith("@"):
                _iliskili = _muh_iliski_kayit(_kk, _k[1:], dahil_index)
                _v = ((_iliskili or {}).get("attributes") or {}).get("name", "—") if _iliskili else "—"
            else:
                _v = _a.get(_k, "")
            try:
                _c.write(_f(_v) if _f else _v)
            except Exception:
                _c.write(_v)
        _buton_idx = len(kolonlar)
        if detay_fn:
            if _rc[_buton_idx].button("🔍", key=f"{key_prefix}_detay_btn_{_rid}", help="Kalemleri gör"):
                _dk = f"{key_prefix}_detay_acik_{_rid}"
                st.session_state[_dk] = not st.session_state.get(_dk, False)
                st.rerun()
            _buton_idx += 1
        if sil_fn:
            _bek = f"{key_prefix}_sil_bekliyor_{_rid}"
            if not st.session_state.get(_bek):
                if _rc[_buton_idx].button("🗑️", key=f"{key_prefix}_sil_btn_{_rid}"):
                    st.session_state[_bek] = True
                    st.rerun()
            else:
                st.warning("⚠️ Bu kaydı muhasebe sisteminden kalıcı olarak silmek üzeresiniz. Bu işlem GERİ ALINAMAZ.")
                _oc1, _oc2 = st.columns(2)
                if _oc1.button("✅ Evet, kalıcı sil", type="primary", key=f"{key_prefix}_sil_onay_{_rid}"):
                    with st.spinner("Siliniyor..."):
                        _s_sonuc, _s_hata = sil_fn(_rid)
                    st.session_state.pop(_bek, None)
                    if _s_hata:
                        st.error(f"Silinemedi: {_s_hata}")
                    else:
                        st.success("Silindi.")
                        st.rerun()
                if _oc2.button("Vazgeç", key=f"{key_prefix}_sil_vazgec_{_rid}"):
                    st.session_state.pop(_bek, None)
                    st.rerun()
        if detay_fn and st.session_state.get(f"{key_prefix}_detay_acik_{_rid}"):
            with st.container(border=True):
                detay_fn(_kk, dahil_index)

def _muh_baglanti_var_mi():
    return bool(_muh_token_oku())

def _muh_baglanti_uyar():
    st.warning("⚠️ Muhasebe sistemine henüz bağlı değilsiniz.")
    st.caption("Bağlantıyı 'Faturalar' sayfasından tek seferlik kurabilirsiniz.")
    if st.button("🔗 Faturalar sayfasına git ve bağlan", key="muh_baglan_yonlendir"):
        st.session_state["aktif_tab"] = "muhasebe_fatura"
        st.rerun()

def hesapla_segment(manuel_segment, gerceklesen_ciro):
    """Manuel segment varsa onu normalize et, yoksa ciroya göre otomatik hesapla"""
    # Normalize — eski kayıtlardaki farklı ikonları düzelt
    _norm = {"⭐ A+":"👑 A+","A+":"👑 A+","⭐ A-":"⭐ A","A":"⭐ A","A-":"⭐ A","B":"🔵 B","C":"⚪ C"}
    if manuel_segment:
        _m = str(manuel_segment).strip()
        if _m and _m not in ["","--","nan","None"]:
            # Önce tam eşleşme dene
            if _m in ["👑 A+","⭐ A","🔵 B","⚪ C"]: return _m
            # Sonra normalize
            for _k,_v in _norm.items():
                if _k in _m: return _v
            return _m
    ger = float(gerceklesen_ciro or 0)
    if ger >= 500000: return "👑 A+"
    if ger >= 200000: return "⭐ A"
    if ger >= 50000:  return "🔵 B"
    if ger > 0:       return "⚪ C"
    return ""

def segment_renk(seg):
    """Segment → arka plan ve yazı rengi"""
    s = str(seg or "")
    if "A+" in s: return "#fef3c7","#92400e","#f59e0b"  # bg, text, border
    if "A"  in s: return "#f1f5f9","#475569","#94a3b8"
    if "B"  in s: return "#eff6ff","#1e40af","#3b82f6"
    if "C"  in s: return "#f8fafc","#64748b","#cbd5e1"
    return "#ffffff","#374151","#e2e8f0"

def get_supabase():
    return get_sb_client()

def _tel_gruplu(s):
    """Ham rakamlardan '541 357 80 20' gibi gruplu, baştaki 0/90'sız görünüm
    oluşturur. 10 haneli bir GSM/sabit numarasına indirgenemiyorsa (eksik/
    hatalı veri), veri kaybı olmasın diye olduğu gibi bırakır.
    Float ".0" artığını (2163679000.0 gibi) da kendi içinde temizler —
    çağıran taraf ayrıca temizlemek zorunda değil."""
    if not s:
        return s
    _s = str(s).strip()
    if _s.endswith(".0"):
        _s = _s[:-2]
    _digits = "".join(ch for ch in _s if ch.isdigit())
    if _digits.startswith("90") and len(_digits) == 12:
        _digits = _digits[2:]
    elif _digits.startswith("0") and len(_digits) == 11:
        _digits = _digits[1:]
    if len(_digits) == 10:
        return f"{_digits[0:3]} {_digits[3:6]} {_digits[6:8]} {_digits[8:10]}"
    return s

def _telefon_temizle(seri):
    """5413578020.0 gibi float telefonları '541 357 80 20' gruplu gösterime çevirir"""
    def _tek(v):
        if v is None:
            return ""
        s = str(v).strip()
        if s.lower() in ["nan", "none", ""]:
            return ""
        # Float .0 temizle
        if s.endswith(".0"):
            s = s[:-2]
        # Bilimsel notasyon temizle (1e+10 gibi)
        try:
            if "e" in s.lower() or "E" in s:
                s = str(int(float(s)))
        except:
            pass
        return _tel_gruplu(s)
    return seri.apply(_tek)

def _no_temizle(v):
    """Tek değer için .0 ve float temizleyici — her yerde kullan"""
    if v is None: return ""
    s = str(v).strip()
    if s.lower() in ["nan","none",""]: return ""
    if s.endswith(".0"): s = s[:-2]
    try:
        if "e" in s.lower():
            s = str(int(float(s)))
    except: pass
    return s

def _get_atanmis_firmalar():
    """Giriş yapan kullanıcının atanmış firma adlarını döndürür. Admin için None (hepsi)."""
    try:
        _rol = st.session_state.get("rol","")
        _kul = st.session_state.get("kullanici","")
        if _rol == "admin" or not _kul:
            return None  # None = hepsini göster
        sb = get_sb_client()
        if sb:
            _res = sb.table("cari_kartlar").select("firma,id").eq("atanan_kullanici", _kul).neq("silindi",1).execute()
            if _res.data:
                return {
                    "firmalar": set(str(r.get("firma","")).strip().upper() for r in _res.data if r.get("firma")),
                    "idler": set(int(r.get("id",0)) for r in _res.data if r.get("id"))
                }
        return {"firmalar": set(), "idler": set()}  # boş — hiçbir şey görmesin
    except:
        return None  # hata durumunda hepsini göster (güvenli taraf)

def _atama_filtresi_uygula(df):
    """Admin hepsini görür, diğerleri sadece kendine atananları"""
    try:
        _rol = str(st.session_state.get("rol","")).strip().lower()
        _kul = str(st.session_state.get("kullanici","")).strip()
        # Admin veya kullanıcı yoksa hepsini göster
        if "admin" in _rol or _kul == "admin" or not _kul:
            return df
        if df.empty or "atanan_kullanici" not in df.columns:
            return df
        # Kullanıcıya atananlar VEYA atanmamışlar
        return df[
            (df["atanan_kullanici"].astype(str) == _kul) |
            (df["atanan_kullanici"].isna()) |
            (df["atanan_kullanici"].astype(str).isin(["None","nan",""]))
        ]
    except:
        return df

# ── BÖLGE EŞLEŞTİRME (il + ilçe → bölge adı) ────────────────────────────────
_BL_ISTANBUL_ANADOLU = {"adalar","atasehir","beykoz","cekmekoy","kadikoy","kartal",
    "maltepe","pendik","sancaktepe","sultanbeyli","sile","tuzla","umraniye","uskudar"}
_BL_ISTANBUL_AVRUPA = {"arnavutkoy","avcilar","bagcilar","bahcelievler","bakirkoy",
    "basaksehir","bayrampasa","besiktas","beylikduzu","beyoglu","buyukcekmece",
    "catalca","esenler","esenyurt","eyupsultan","fatih","gaziosmanpasa","gungoren",
    "kagithane","kucukcekmece","sariyer","silivri","sisli","zeytinburnu","sultangazi"}
# Yaygın mahalle/semt isimleri → resmi ilçe (kişiler genelde resmi ilçe yerine
# bilindik semt adını yazar, bunları da tanıyalım ki Havuz'da takılı kalmasınlar)
_BL_ISTANBUL_MAHALLE_ILCE = {
    "yenibosna":"bahcelievler","bahcesehir":"basaksehir","atakoy":"bakirkoy",
    "florya":"bakirkoy","yesilkoy":"bakirkoy","halkali":"kucukcekmece",
    "levent":"besiktas","etiler":"besiktas","ortakoy":"besiktas","bebek":"besiktas",
    "nisantasi":"sisli","mecidiyekoy":"sisli","maslak":"sariyer",
    "taksim":"beyoglu","karakoy":"beyoglu","cihangir":"beyoglu","galata":"beyoglu",
    "balat":"fatih","sultanahmet":"fatih","aksaray":"fatih","topkapi":"fatih",
    "merter":"gungoren","bostanci":"kadikoy","suadiye":"kadikoy",
    "fenerbahce":"kadikoy","kozyatagi":"kadikoy","acibadem":"uskudar",
    "camlica":"uskudar","kisikli":"uskudar","kavacik":"beykoz",
}
_BL_IL_ADI = {
    "tekirdag":"Tekirdağ","kocaeli":"Kocaeli","bursa":"Bursa","manisa":"Manisa",
    "ankara":"Ankara","konya":"Konya","eskisehir":"Eskişehir","denizli":"Denizli","aydin":"Aydın",
}
# 81 ilin TAMAMININ doğru yazımı — Türkçe .title() İ/I sorunu yüzünden yanlış
# yazılmasın (ör. "İZMİR".title() bozuk çıkar) diye .title() yerine bu kaynaktan okunur.
_BL_TUM_ILLER_DOGRU_YAZIM = ["Adana","Adıyaman","Afyonkarahisar","Ağrı","Amasya","Ankara",
    "Antalya","Artvin","Aydın","Balıkesir","Bilecik","Bingöl","Bitlis","Bolu","Burdur",
    "Bursa","Çanakkale","Çankırı","Çorum","Denizli","Diyarbakır","Edirne","Elazığ",
    "Erzincan","Erzurum","Eskişehir","Gaziantep","Giresun","Gümüşhane","Hakkari","Hatay",
    "Isparta","Mersin","İstanbul","İzmir","Kars","Kastamonu","Kayseri","Kırklareli",
    "Kırşehir","Kocaeli","Konya","Kütahya","Malatya","Manisa","Kahramanmaraş","Mardin",
    "Muğla","Muş","Nevşehir","Niğde","Ordu","Rize","Sakarya","Samsun","Siirt","Sinop",
    "Sivas","Tekirdağ","Tokat","Trabzon","Tunceli","Şanlıurfa","Uşak","Van","Yozgat",
    "Zonguldak","Aksaray","Bayburt","Karaman","Kırıkkale","Batman","Şırnak","Bartın",
    "Ardahan","Iğdır","Yalova","Karabük","Kilis","Osmaniye","Düzce"]

def _bl_sadelestir(s):
    s = str(s or "").strip().lower()
    for _k,_v in {"ı":"i","i̇":"i","ş":"s","ğ":"g","ü":"u","ö":"o","ç":"c"}.items():
        s = s.replace(_k,_v)
    return s

_BL_TUM_ILLER_ADI = {_bl_sadelestir(_ad): _ad for _ad in _BL_TUM_ILLER_DOGRU_YAZIM}

def il_ilce_bolge_bul(il, ilce):
    """il+ilçe bilgisinden bölge adı üretir. İl doluysa MUTLAKA bir bölge olur —
    tanımlı 11 bölgeden biriyse o isimle, değilse ilin kendi adıyla. Sadece il
    tamamen BOŞSA — veya İstanbul'un ilçesi Anadolu/Avrupa listesinde yoksa (manuel
    toplu atama için) — Havuz'a düşer."""
    _il = _bl_sadelestir(il)
    _ilce = _bl_sadelestir(ilce)
    if not _il:
        return None  # il tamamen boşsa Havuz
    if "istanbul" in _il:
        # Önce birebir eşleşme dene (hızlı ve kesin)
        _ilce_eslesen = _BL_ISTANBUL_MAHALLE_ILCE.get(_ilce, _ilce)
        if _ilce_eslesen in _BL_ISTANBUL_ANADOLU:
            return "İstanbul Anadolu"
        if _ilce_eslesen in _BL_ISTANBUL_AVRUPA:
            return "İstanbul Avrupa"
        # Birebir eşleşmediyse — hücrede ilçe adı GEÇİYOR mu diye bak
        # ("Sultanbeyli Mah.", "Sultanbeyli/İstanbul" gibi ekstra kelimeli hücreler için)
        if _ilce:
            for _resmi_ilce in _BL_ISTANBUL_ANADOLU:
                if _resmi_ilce in _ilce:
                    return "İstanbul Anadolu"
            for _resmi_ilce in _BL_ISTANBUL_AVRUPA:
                if _resmi_ilce in _ilce:
                    return "İstanbul Avrupa"
            for _mahalle, _resmi_ilce in _BL_ISTANBUL_MAHALLE_ILCE.items():
                if _mahalle in _ilce:
                    return "İstanbul Anadolu" if _resmi_ilce in _BL_ISTANBUL_ANADOLU else "İstanbul Avrupa"
        return None  # ilçe hiçbir şekilde eşleşmiyor — Havuz'da kalır, manuel toplu atama için
    if _il in _BL_IL_ADI:
        return _BL_IL_ADI[_il]
    # Tanımlı 11 bölgeden biri değil ama il doluysa — ilin kendi adı bölge olur.
    # 81 il listesindeyse doğru yazımıyla (ikon eşleşsin diye), değilse .title() ile.
    if _il in _BL_TUM_ILLER_ADI:
        return _BL_TUM_ILLER_ADI[_il]
    return str(il).strip().title()

@st.cache_data(ttl=60)
def get_cari_listesi():
    """60 sn cache'li cari listesi — HTTP Range ile limitsiz çek"""
    import requests as _rq
    _url = st.secrets.get("SUPABASE_URL","")
    _key = st.secrets.get("SUPABASE_SERVICE_KEY","") or st.secrets.get("SUPABASE_KEY","")
    _tum = []
    if _url and _key:
        try:
            _offset = 0
            while True:
                _hdrs = {
                    "apikey": _key,
                    "Authorization": f"Bearer {_key}",
                    "Range-Unit": "items",
                    "Range": f"{_offset}-{_offset+999}"
                }
                _r = _rq.get(
                    f"{_url}/rest/v1/cari_kartlar?select=*&order=id.asc",
                    headers=_hdrs, timeout=30
                )
                if _r.status_code not in [200, 206]:
                    break
                _batch = _r.json()
                if not _batch:
                    break
                _tum.extend(_batch)
                if len(_batch) < 1000:
                    break
                _offset += 1000
        except:
            pass
    if not _tum:
        try:
            sb = get_sb_client()
            if sb:
                _res = sb.table("cari_kartlar").select("*").order("id",desc=False).execute()
                _tum = _res.data or []
        except:
            pass
    _df_g = pd.DataFrame(_tum) if _tum else pd.DataFrame()
    if not _df_g.empty:
        if "silindi" in _df_g.columns:
            _df_g = _df_g[~(_df_g["silindi"].astype(str).str.strip().isin(["1","True","true","1.0"]))]
        for _tk in ["gsm","sabit"]:
            if _tk in _df_g.columns:
                _df_g[_tk] = _telefon_temizle(_df_g[_tk])
    return _df_g
    try:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM cari_kartlar WHERE silindi=0 OR silindi='0' OR silindi IS NULL ORDER BY firma", conn)
        conn.close()
        for _tk in ["gsm","sabit"]:
            if _tk in df.columns:
                df[_tk] = _telefon_temizle(df[_tk])
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=120)
def get_kullanici_listesi():
    """2 dk cache'li kullanıcı listesi"""
    return db_read("kullanicilar", extra_sql="")

@st.cache_data(ttl=120)
def _cached_placeholder(): pass  # cache decorator boş bırakılamaz


def _teklifler_oku():
    """teklifler tablosunu DOĞRUDAN Supabase client ile okur.
    NOT: db_read() bu tabloda bazı ortamlarda sessizce başarısız olup neredeyse
    boş yerel SQLite yedeğine düşüyordu (177 gerçek kayıt varken "6 kayıt"
    gösteriyordu) — bu fonksiyon o sorunu bypass eder, Kurallar sayfasındaki
    çalışan "Bağlantısız Teklif Onarımı" aracıyla AYNI, kanıtlanmış yöntemi kullanır."""
    try:
        sb = get_sb_client()
        if sb:
            _res = sb.table("teklifler").select("*").order("id", desc=True).execute()
            _data = _res.data or []
            return pd.DataFrame(_data) if _data else pd.DataFrame()
    except Exception:
        pass
    return db_read("teklifler", order_col="id")  # son çare

def _teklifler_tarih_normalize(df):
    """teklifler tablosunda gerçek Supabase şemasında 'tarih' kolonu olmayabilir
    (otomatik 'created_at' kullanılıyor olabilir, cari_aciklamalar'da olduğu gibi).
    Kod genelinde 'tarih' bekleyen onlarca yer bozulmasın diye burada normalize
    ediyoruz — böylece hem eski hem yeni şema ile çalışır."""
    if df is None or df.empty:
        return df
    if "tarih" not in df.columns and "created_at" in df.columns:
        df = df.copy()
        df["tarih"] = df["created_at"]
    return df

def db_read(table, filters=None, order_col="id", desc=True, limit=None, extra_sql=None):
    """Supabase veya SQLite'dan DataFrame döner"""
    sb = get_sb_client()
    if sb:
        try:
            q = sb.table(table).select("*")
            if filters:
                for k, v in filters.items():
                    if v == "NOT_NULL":
                        q = q.not_.is_(k, "null")
                    elif v == "neq_1":
                        q = q.neq(k, 1)
                    else:
                        q = q.eq(k, v)
            if order_col:
                q = q.order(order_col, desc=desc)
            if limit:
                q = q.limit(limit)
            res = q.execute()
            if res and res.data is not None:
                return pd.DataFrame(res.data) if res.data else pd.DataFrame()
            return pd.DataFrame()
        except Exception as _e_read:
            pass
    try:
        sql = f"SELECT * FROM {table}"
        if extra_sql:
            sql += f" {extra_sql}"
        conn = get_conn()
        df = pd.read_sql(sql, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()


def db_insert(table, data):
    """Insert — Supabase önce, SQLite fallback — firma_id otomatik eklenir"""
    sb = get_sb_client()
    _sb_hata = None
    if sb:
        try:
            res = sb.table(table).insert(data).execute()
            if res.data:
                return True
        except Exception as e:
            _sb_hata = str(e)
    # SQLite fallback
    try:
        conn = get_conn()
        cols = ", ".join(data.keys())
        vals = ", ".join(["?" for _ in data])
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals})", list(data.values()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.session_state["_last_db_error"] = f"Supabase: {_sb_hata} | SQLite: {e}"
        st.error(f"DB insert hatası ({table}): {e}")
    return False

def db_update(table, data, where_col, where_val):
    """Update — Supabase veya SQLite"""
    sb = get_sb_client()
    if sb:
        try:
            sb.table(table).update(data).eq(where_col, where_val).execute()
            return True
        except Exception as _e_up:
            # Supabase hata — SQLite'a dön
            pass
    try:
        conn = get_conn()
        sets = ", ".join([f"{k}=?" for k in data.keys()])
        conn.execute(f"UPDATE {table} SET {sets} WHERE {where_col}=?",
                    list(data.values()) + [where_val])
        conn.commit()
        conn.close()
        return True
    except Exception as _e_sq:
        pass
    return False

def db_query(sql, params=None):
    """SELECT sorgusu — Supabase veya SQLite"""
    if sb_or_sqlite():
        # Supabase için pandas read
        try:
            import sqlalchemy
            url = st.secrets.get("SUPABASE_URL","").replace("https://","postgresql://postgres.asinwzxwmkkrcbtjrkoq:")
            # Doğrudan supabase-py kullanalım
            sb = get_supabase()
            if sb:
                # Tabloyu sql'den çıkar
                tbl = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
                if tbl:
                    table_name = tbl.group(1)
                    res = sb.table(table_name).select("*").execute()
                    if res.data:
                        df = pd.DataFrame(res.data)
                        return df
                    return pd.DataFrame()
        except Exception as e:
            pass
    # SQLite fallback
    df = pd.read_sql(sql, conn)
    return df

def sb_insert(table, data):
    """INSERT — Supabase veya SQLite"""
    if sb_or_sqlite():
        try:
            sb = get_supabase()
            if sb:
                sb.table(table).insert(data).execute()
                return True
        except Exception as e:
            st.error(f"Supabase insert hatası: {e}")
    return False

def sb_update(table, data, match_col, match_val):
    """UPDATE — Supabase veya SQLite"""
    if sb_or_sqlite():
        try:
            sb = get_supabase()
            if sb:
                sb.table(table).update(data).eq(match_col, match_val).execute()
                return True
        except Exception as e:
            st.error(f"Supabase update hatası: {e}")
    return False

def sb_delete(table, match_col, match_val):
    """DELETE — Supabase"""
    if sb_or_sqlite():
        try:
            sb = get_supabase()
            if sb:
                sb.table(table).delete().eq(match_col, match_val).execute()
                return True
        except:
            pass
    return False

def sb_select(table, filters=None, order=None, limit=None):
    """Supabase tablo sorgusu — DataFrame döner"""
    if sb_or_sqlite():
        try:
            sb = get_supabase()
            if sb:
                q = sb.table(table).select("*")
                if filters:
                    for col, val in filters.items():
                        if val is not None:
                            q = q.eq(col, val)
                if order:
                    q = q.order(order, desc=True)
                if limit:
                    q = q.limit(limit)
                res = q.execute()
                return pd.DataFrame(res.data) if res.data else pd.DataFrame()
        except Exception as e:
            pass
    # SQLite fallback
    try:
        sql = f"SELECT * FROM {table}"
        if filters:
            where = " AND ".join([f"{k}=?" for k in filters.keys()])
            sql += f" WHERE {where}"
            df = pd.read_sql(sql, conn, params=list(filters.values()))
        else:
            df = pd.read_sql(sql, conn)
        return df
    except:
        return pd.DataFrame()


ILLER_ILCELER = {
    "Adana": ["Aladağ","Ceyhan","Çukurova","Feke","İmamoğlu","Karaisalı","Karataş","Kozan","Pozantı","Saimbeyli","Sarıçam","Seyhan","Tufanbeyli","Yumurtalık","Yüreğir"],
    "Adıyaman": ["Besni","Çelikhan","Gerger","Gölbaşı","Kahta","Merkez","Samsat","Sincik","Tut"],
    "Afyonkarahisar": ["Başmakçı","Bayat","Bolvadin","Çay","Çobanlar","Dazkırı","Dinar","Emirdağ","Evciler","Hocalar","İhsaniye","İscehisar","Kızılören","Merkez","Sandıklı","Sinanpaşa","Sultandağı","Şuhut"],
    "Ağrı": ["Diyadin","Doğubayazıt","Eleşkirt","Hamur","Merkez","Patnos","Taşlıçay","Tutak"],
    "Amasya": ["Göynücek","Gümüşhacıköy","Hamamözü","Merkez","Merzifon","Suluova","Taşova"],
    "Ankara": ["Akyurt","Altındağ","Ayaş","Bala","Beypazarı","Çamlıdere","Çankaya","Çubuk","Elmadağ","Etimesgut","Evren","Gölbaşı","Güdül","Haymana","Kalecik","Kahramankazan","Keçiören","Kızılcahamam","Mamak","Nallıhan","Polatlı","Pursaklar","Sincan","Şereflikoçhisar","Yenimahalle"],
    "Antalya": ["Akseki","Aksu","Alanya","Demre","Döşemealtı","Elmalı","Finike","Gazipaşa","Gündoğmuş","İbradı","Kaş","Kemer","Kepez","Konyaaltı","Korkuteli","Kumluca","Manavgat","Muratpaşa","Serik"],
    "Artvin": ["Ardanuç","Arhavi","Borçka","Hopa","Merkez","Murgul","Şavşat","Yusufeli"],
    "Aydın": ["Bozdoğan","Buharkent","Çine","Didim","Efeler","Germencik","İncirliova","Karacasu","Karpuzlu","Koçarlı","Köşk","Kuşadası","Kuyucak","Merkez","Nazilli","Söke","Sultanhisar","Yenipazar"],
    "Balıkesir": ["Altıeylül","Ayvalık","Balya","Bandırma","Bigadiç","Burhaniye","Dursunbey","Edremit","Erdek","Gömeç","Gönen","Havran","İvrindi","Karesi","Kepsut","Manyas","Marmara","Savaştepe","Sındırgı","Susurluk"],
    "Bilecik": ["Bozüyük","Gölpazarı","İnhisar","Merkez","Osmaneli","Pazaryeri","Söğüt","Yenipazar"],
    "Bingöl": ["Adaklı","Genç","Karlıova","Kiğı","Merkez","Solhan","Yayladere","Yedisu"],
    "Bitlis": ["Adilcevaz","Ahlat","Güroymak","Hizan","Merkez","Mutki","Tatvan"],
    "Bolu": ["Dörtdivan","Gerede","Göynük","Kıbrıscık","Mengen","Merkez","Mudurnu","Seben","Yeniçağa"],
    "Burdur": ["Ağlasun","Altınyayla","Bucak","Çavdır","Çeltikçi","Gölhisar","Karamanlı","Kemer","Merkez","Tefenni","Yeşilova"],
    "Bursa": ["Büyükorhan","Gemlik","Gürsu","Harmancık","İnegöl","İznik","Karacabey","Keles","Kestel","Mudanya","Mustafakemalpaşa","Nilüfer","Orhaneli","Orhangazi","Osmangazi","Yıldırım","Yenişehir"],
    "Çanakkale": ["Ayvacık","Bayramiç","Biga","Bozcaada","Çan","Eceabat","Ezine","Gelibolu","Gökçeada","Lapseki","Merkez","Yenice"],
    "Çankırı": ["Atkaracalar","Bayramören","Çerkeş","Eldivan","Ilgaz","Kızılırmak","Korgun","Kurşunlu","Merkez","Orta","Şabanözü","Yapraklı"],
    "Çorum": ["Alaca","Bayat","Boğazkale","Dodurga","İskilip","Kargı","Laçin","Mecitözü","Merkez","Oğuzlar","Ortaköy","Osmancık","Sungurlu","Uğurludağ"],
    "Denizli": ["Acıpayam","Babadağ","Baklan","Bekilli","Beyağaç","Bozkurt","Buldan","Çal","Çameli","Çardak","Çivril","Güney","Honaz","Kale","Merkezefendi","Pamukkale","Sarayköy","Serinhisar","Tavas"],
    "Diyarbakır": ["Bağlar","Bismil","Çermik","Çınar","Çüngüş","Dicle","Eğil","Ergani","Hani","Hazro","Kayapınar","Kocaköy","Kulp","Lice","Silvan","Sur","Yenişehir"],
    "Düzce": ["Akçakoca","Cumayeri","Çilimli","Gölyaka","Gümüşova","Kaynaşlı","Merkez","Yığılca"],
    "Edirne": ["Enez","Havsa","İpsala","Keşan","Lalapaşa","Merkez","Meriç","Süloğlu","Uzunköprü"],
    "Elazığ": ["Ağın","Alacakaya","Arıcak","Baskil","Karakoçan","Keban","Kovancılar","Maden","Merkez","Palu","Sivrice"],
    "Erzincan": ["Çayırlı","İliç","Kemah","Kemaliye","Merkez","Otlukbeli","Refahiye","Tercan","Üzümlü"],
    "Erzurum": ["Aşkale","Aziziye","Çat","Hinis","Horasan","İspir","Karakoçan","Karayazı","Köprüköy","Merkez","Narman","Oltu","Olur","Palandöken","Pasinler","Pazaryolu","Şenkaya","Tekman","Tortum","Uzundere","Yakutiye"],
    "Eskişehir": ["Alpu","Beylikova","Çifteler","Günyüzü","Han","İnönü","Mahmudiye","Mihalgazi","Mihalıççık","Merkez","Odunpazarı","Sarıcakaya","Seyitgazi","Sivrihisar","Tepebaşı"],
    "Gaziantep": ["Araban","İslahiye","Karkamış","Nizip","Nurdağı","Oğuzeli","Şahinbey","Şehitkamil","Yavuzeli"],
    "Giresun": ["Alucra","Bulancak","Çamoluk","Çanakçı","Dereli","Doğankent","Espiye","Eynesil","Görele","Güce","Keşap","Merkez","Piraziz","Şebinkarahisar","Tirebolu","Yağlıdere"],
    "Gümüşhane": ["Kelkit","Köse","Kürtün","Merkez","Şiran","Torul"],
    "Hakkari": ["Çukurca","Derecik","Merkez","Şemdinli","Yüksekova"],
    "Hatay": ["Altınözü","Antakya","Arsuz","Belen","Defne","Dörtyol","Erzin","Hassa","İskenderun","Kırıkhan","Kumlu","Payas","Reyhanlı","Samandağ","Yayladağı"],
    "Iğdır": ["Aralık","Karakoyunlu","Merkez","Tuzluca"],
    "Isparta": ["Aksu","Atabey","Eğirdir","Gelendost","Gönen","Keçiborlu","Merkez","Senirkent","Sütçüler","Şarkikaraağaç","Uluborlu","Yalvaç","Yenişarbademli"],
    "İstanbul": ["Adalar","Arnavutköy","Ataşehir","Avcılar","Bağcılar","Bahçelievler","Bakırköy","Başakşehir","Bayrampaşa","Beşiktaş","Beykoz","Beylikdüzü","Beyoğlu","Büyükçekmece","Çatalca","Çekmeköy","Esenler","Esenyurt","Eyüpsultan","Fatih","Gaziosmanpaşa","Güngören","Kadıköy","Kağıthane","Kartal","Küçükçekmece","Maltepe","Pendik","Sancaktepe","Sarıyer","Silivri","Sultanbeyli","Sultangazi","Şile","Şişli","Tuzla","Ümraniye","Üsküdar","Zeytinburnu"],
    "İzmir": ["Aliağa","Balçova","Bayındır","Bayraklı","Bergama","Beydağ","Bornova","Buca","Çeşme","Çiğli","Dikili","Foça","Gaziemir","Güzelbahçe","Karabağlar","Karaburun","Karşıyaka","Kemalpaşa","Kınık","Kiraz","Konak","Menderes","Menemen","Narlıdere","Ödemiş","Seferihisar","Selçuk","Tire","Torbalı","Urla"],
    "Kahramanmaraş": ["Afşin","Andırın","Çağlayancerit","Dulkadiroğlu","Ekinözü","Elbistan","Göksun","Merkez","Nurhak","Onikişubat","Pazarcık","Türkoğlu"],
    "Karabük": ["Eflani","Eskipazar","Merkez","Ovacık","Safranbolu","Yenice"],
    "Karaman": ["Ayrancı","Başyayla","Ermenek","Kazımkarabekir","Merkez","Sarıveliler"],
    "Kars": ["Akyaka","Arpaçay","Digor","Kağızman","Merkez","Sarıkamış","Selim","Susuz"],
    "Kastamonu": ["Abana","Ağlı","Araç","Azdavay","Bozkurt","Cide","Çatalzeytin","Daday","Devrekani","Doğanyurt","Hanönü","İhsangazi","İnebolu","Küre","Merkez","Pınarbaşı","Seydiler","Şenpazar","Taşköprü","Tosya"],
    "Kayseri": ["Akkışla","Bünyan","Develi","Felahiye","Hacılar","İncesu","Kocasinan","Melikgazi","Özvatan","Pınarbaşı","Sarıoğlan","Sarız","Talas","Tomarza","Yahyalı","Yeşilhisar"],
    "Kırıkkale": ["Bahşili","Balışeyh","Çelebi","Delice","Karakeçili","Keskin","Merkez","Sulakyurt","Yahşihan"],
    "Kırklareli": ["Babaeski","Demirköy","Kofçaz","Lüleburgaz","Merkez","Pehlivanköy","Pınarhisar","Vize"],
    "Kırşehir": ["Akçakent","Akpınar","Boztepe","Çiçekdağı","Kaman","Merkez","Mucur"],
    "Kilis": ["Elbeyli","Merkez","Musabeyli","Polateli"],
    "Kocaeli": ["Başiskele","Çayırova","Darıca","Derince","Dilovası","Gebze","Gölcük","İzmit","Kandıra","Karamürsel","Kartepe","Körfez"],
    "Konya": ["Ahırlı","Akören","Akşehir","Altınekin","Beyşehir","Bozkır","Cihanbeyli","Çeltik","Çumra","Derbent","Derebucak","Doğanhisar","Emirgazi","Ereğli","Güneysınır","Hadim","Halkapınar","Hüyük","Ilgın","Kadınhanı","Karapınar","Karatay","Kulu","Meram","Sarayönü","Selçuklu","Seydişehir","Taşkent","Tuzlukçu","Yalıhüyük","Yunak"],
    "Kütahya": ["Altıntaş","Aslanapa","Çavdarhisar","Domaniç","Dumlupınar","Emet","Gediz","Hisarcık","Merkez","Pazarlar","Simav","Şaphane","Tavşanlı"],
    "Malatya": ["Akçadağ","Arapgir","Arguvan","Battalgazi","Darende","Doğanyol","Doğanşehir","Hekimhan","Kale","Kuluncak","Merkez","Pütürge","Yazıhan","Yeşilyurt"],
    "Manisa": ["Ahmetli","Akhisar","Alaşehir","Demirci","Gölmarmara","Gördes","Kırkağaç","Köprübaşı","Kula","Merkez","Salihli","Sarıgöl","Saruhanlı","Selendi","Soma","Şehzadeler","Turgutlu","Yunusemre"],
    "Mardin": ["Artuklu","Dargeçit","Derik","Kızıltepe","Mazıdağı","Merkez","Midyat","Nusaybin","Ömerli","Savur","Yeşilli"],
    "Mersin": ["Akdeniz","Anamur","Aydıncık","Bozyazı","Çamlıyayla","Erdemli","Gülnar","Mezitli","Mut","Silifke","Tarsus","Toroslar","Yenişehir"],
    "Muğla": ["Bodrum","Dalaman","Datça","Fethiye","Kavaklıdere","Köyceğiz","Marmaris","Menteşe","Milas","Ortaca","Seydikemer","Ula","Yatağan"],
    "Muş": ["Bulanık","Hasköy","Korkut","Malazgirt","Merkez","Varto"],
    "Nevşehir": ["Acıgöl","Avanos","Derinkuyu","Gülşehir","Hacıbektaş","Kozaklı","Merkez","Ürgüp"],
    "Niğde": ["Altunhisar","Bor","Çamardı","Çiftlik","Merkez","Ulukışla"],
    "Ordu": ["Akkuş","Altınordu","Aybastı","Çamaş","Çatalpınar","Çaybaşı","Fatsa","Gölköy","Gülyalı","Gürgentepe","İkizce","Kabadüz","Kabataş","Korgan","Kumru","Mesudiye","Perşembe","Ulubey","Ünye"],
    "Osmaniye": ["Bahçe","Düziçi","Hasanbeyli","Kadirli","Merkez","Sumbas","Toprakkale"],
    "Rize": ["Ardeşen","Çamlıhemşin","Çayeli","Derepazarı","Fındıklı","Güneysu","Hemşin","İkizdere","İyidere","Kalkandere","Merkez","Pazar"],
    "Sakarya": ["Adapazarı","Akyazı","Arifiye","Erenler","Ferizli","Geyve","Hendek","Karapürçek","Karasu","Kaynarca","Kocaali","Mithatpaşa","Pamukova","Sapanca","Serdivan","Söğütlü","Taraklı"],
    "Samsun": ["Alaçam","Asarcık","Atakum","Ayvacık","Bafra","Canik","Çarşamba","İlkadım","Kavak","Ladik","Merkez","Ondokuzmayıs","Salıpazarı","Tekkeköy","Terme","Vezirköprü","Yakakent"],
    "Siirt": ["Baykan","Eruh","Kurtalan","Merkez","Pervari","Şirvan","Tillo"],
    "Sinop": ["Ayancık","Boyabat","Dikmen","Durağan","Erfelek","Gerze","Merkez","Saraydüzü","Türkeli"],
    "Sivas": ["Akıncılar","Altınyayla","Divriği","Doğanşar","Gemerek","Gölova","Gürun","Hafik","İmranlı","Kangal","Koyulhisar","Merkez","Suşehri","Şarkışla","Ulaş","Yıldızeli","Zara"],
    "Şanlıurfa": ["Akçakale","Birecik","Bozova","Ceylanpınar","Eyyübiye","Halfeti","Haliliye","Harran","Hilvan","Karaköprü","Merkez","Siverek","Suruç","Viranşehir"],
    "Şırnak": ["Beytüşşebap","Cizre","Güçlükonak","İdil","Merkez","Silopi","Uludere"],
    "Tekirdağ": ["Çerkezköy","Çorlu","Ergene","Hayrabolu","Malkara","Marmara Ereğlisi","Muratlı","Saray","Süleymanpaşa","Şarköy"],
    "Tokat": ["Almus","Artova","Başçiftlik","Erbaa","Merkez","Niksar","Pazar","Reşadiye","Sulusaray","Turhal","Yeşilyurt","Zile"],
    "Trabzon": ["Akçaabat","Araklı","Arsin","Beşikdüzü","Çarşıbaşı","Çaykara","Dernekpazarı","Düzköy","Hayrat","Köprübaşı","Maçka","Merkez","Of","Ortahisar","Sürmene","Şalpazarı","Tonya","Vakfıkebir","Yomra"],
    "Tunceli": ["Çemişgezek","Hozat","Mazgirt","Merkez","Nazımiye","Ovacık","Pertek","Pülümür"],
    "Uşak": ["Banaz","Eşme","Karahallı","Merkez","Sivaslı","Ulubey"],
    "Van": ["Bahçesaray","Başkale","Çaldıran","Çatak","Edremit","Erciş","Gevaş","Gürpınar","İpekyolu","Merkez","Muradiye","Özalp","Saray","Tuşba"],
    "Yalova": ["Altınova","Armutlu","Çınarcık","Çiftlikköy","Merkez","Termal"],
    "Yozgat": ["Akdağmadeni","Aydıncık","Boğazlıyan","Çandır","Çayıralan","Çekerek","Kadışehri","Merkez","Saraykent","Sarıkaya","Şefaatli","Sorgun","Yenifakılı","Yerköy"],
    "Zonguldak": ["Alaplı","Çaycuma","Devrek","Gökçebey","Kilimli","Kozlu","Merkez"],
}

# ── VERİTABANI ───────────────────────────────────────────────────────────────
def get_conn():
    return sqlite3.connect("mw_crm.db", check_same_thread=False)

def init_db():
    # SQLite her zaman yedek
    try:
        conn = get_conn()
        tables = [
        """CREATE TABLE IF NOT EXISTS kullanicilar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici_adi TEXT UNIQUE NOT NULL,
            sifre TEXT NOT NULL,
            rol TEXT DEFAULT 'kullanici')""",
        """CREATE TABLE IF NOT EXISTS cari_kartlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            firma TEXT, yetkili TEXT, gsm TEXT, sabit TEXT, email TEXT,
            adres TEXT, ilce TEXT, il TEXT, durum TEXT, temsilci TEXT,
            islem_asamasi TEXT, silindi INTEGER DEFAULT 0,
            olusturan TEXT, beklenen_ciro REAL DEFAULT 0,
            gerceklesen_ciro REAL DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS teklifler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            musteri_id INTEGER, musteri_adi TEXT,
            satirlar TEXT, toplam_tutar REAL,
            olusturan TEXT, notlar TEXT)""",
        """CREATE TABLE IF NOT EXISTS islem_kaydi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            musteri_id INTEGER, musteri_adi TEXT,
            islem_turu TEXT, icerik TEXT,
            gonderim_bilgisi TEXT, olusturan TEXT)""",
        """CREATE TABLE IF NOT EXISTS kullanici_tercih (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici TEXT, anahtar TEXT, deger TEXT,
            UNIQUE(kullanici, anahtar))""",
        """CREATE TABLE IF NOT EXISTS kod_deposu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            surum TEXT, aciklama TEXT, kod TEXT, olusturan TEXT)""",
        """CREATE TABLE IF NOT EXISTS mesajlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            gonderen TEXT, alici TEXT, mesaj TEXT,
            okundu INTEGER DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS duyurular (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            baslik TEXT, icerik TEXT, tip TEXT DEFAULT 'bilgi',
            olusturan TEXT, aktif INTEGER DEFAULT 1)""",
        """CREATE TABLE IF NOT EXISTS aktif_kullanicilar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici TEXT UNIQUE, son_gorulme TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS temsilciler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ad TEXT, soyad TEXT, telefon TEXT, email TEXT,
            bolge TEXT, unvan TEXT, aktif INTEGER DEFAULT 1)""",
        """CREATE TABLE IF NOT EXISTS kisiler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ad TEXT, soyad TEXT, telefon TEXT, email TEXT,
            firma TEXT, gorev TEXT, bolge TEXT,
            temsilci TEXT, notlar TEXT, kaynak TEXT)""",
        """CREATE TABLE IF NOT EXISTS sablon_mesajlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ad TEXT, metin TEXT, olusturan TEXT, aktif INTEGER DEFAULT 1)""",
        """CREATE TABLE IF NOT EXISTS kisiler_mesaj_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            kisi_id INTEGER, kisi_adi TEXT, telefon TEXT,
            sablon_adi TEXT, mesaj TEXT, gonderen TEXT)""",
        """CREATE TABLE IF NOT EXISTS cari_aciklamalar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cari_id INTEGER, cari_adi TEXT,
            aciklama TEXT, olusturan TEXT)""",
        """CREATE TABLE IF NOT EXISTS randevular (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            randevu_tarihi TEXT, randevu_saati TEXT,
            musteri_id INTEGER, musteri_adi TEXT,
            bolge TEXT, gorev TEXT, takip TEXT, adet INTEGER DEFAULT 0,
            aciklama TEXT, sonuc TEXT, temsilci TEXT,
            wa_gonderildi INTEGER DEFAULT 0, olusturan TEXT)""",
    ]
        for t in tables:
            try: conn.execute(t)
            except: pass
        for col in ["olusturan TEXT", "beklenen_ciro REAL DEFAULT 0", "gerceklesen_ciro REAL DEFAULT 0", "aciklama TEXT DEFAULT ''"]:
            try: conn.execute(f"ALTER TABLE cari_kartlar ADD COLUMN {col}")
            except: pass
        conn.execute("UPDATE cari_kartlar SET silindi=0 WHERE silindi IS NULL")
        conn.execute("UPDATE cari_kartlar SET id=rowid WHERE id IS NULL")
        try:
            conn.execute("INSERT INTO kullanicilar (kullanici_adi, sifre, rol) VALUES (?,?,?)",
                         ("admin", "admin123", "admin"))
        except: pass
        conn.commit()
        conn.close()
    except: pass

    # Supabase admin kullanicisi
    if sb_or_sqlite():
        try:
            sb = get_supabase()
            if sb:
                existing = sb.table("kullanicilar").select("id").eq("kullanici_adi","admin").execute()
                if not existing.data:
                    sb.table("kullanicilar").insert({"kullanici_adi":"admin","sifre":"admin123","rol":"admin"}).execute()
        except:
            pass

def otomatik_yedek():
    """Her gun otomatik yedek alir (sadece SQLite modunda)"""
    if sb_or_sqlite():
        return  # Supabase modunda yedek gerekmez
    try:
        if not os.path.exists("mw_crm.db"):
            return
        bugun = datetime.now().strftime("%Y-%m-%d")
        yedek_klasor = "backups"
        os.makedirs(yedek_klasor, exist_ok=True)
        db_yedek = os.path.join(yedek_klasor, f"mw_crm_{bugun}.db")
        if not os.path.exists(db_yedek):
            shutil.copy2("mw_crm.db", db_yedek)
    except:
        pass

otomatik_yedek()


# ── KULLANICI LOG FONKSİYONU ──────────────────────────────────────────────────
def kullanici_log_kaydet(islem, sayfa="", detay=""):
    """Her işlemi logla — service_role key ile Supabase'e yaz"""
    try:
        if not st.session_state.get("giris", False): return
        _sb_log = get_sb_service()
        if not _sb_log: return
        _sb_log.table("kullanici_log").insert({
            "kullanici": str(st.session_state.get("kullanici", "?")),
            "rol":       str(st.session_state.get("rol", "?")),
            "sayfa":     str(sayfa or st.session_state.get("aktif_tab", "")),
            "islem":     str(islem),
            "detay":     str(detay)[:500],
        }).execute()
    except:
        pass

def sayfa_log(sayfa):
    """Sayfa değişince logla — önceki sayfa farklıysa yaz"""
    try:
        _onceki = st.session_state.get("_son_sayfa", "")
        if _onceki != sayfa:
            st.session_state["_son_sayfa"] = sayfa
            kullanici_log_kaydet("SAYFA_GİRİŞİ", sayfa, f"→ {sayfa}")
    except:
        pass
    # Sekme başlığını güncelle
    _menu_adlari = {
        "yeni": "Yeni Kart", "liste": "Cari Liste",
        "randevu": "Randevular", "ozel_teklif": "Özel Teklif", "sozlesme": "Sözleşmeler",
        "rapor": "Raporlar", "excel": "Excel", "kullanici": "Kullanıcılar",
        "admin_rapor": "Admin Rapor", "harita": "Müşteri Haritası",
        "dis_nakliye": "Dış Nakliye", "dis_nakliye_toplu": "Dış Nakliyeler Listesi",
    }
    _ad = _menu_adlari.get(sayfa, sayfa)



def _tanimlar_yukle(tip):
    """sistem_tanimlar tablosundan aşama/durum listesi çek"""
    _sb = get_sb_client()
    _liste = []
    try:
        if _sb:
            _r = _sb.table("sistem_tanimlar").select("deger").eq("tip", tip).order("sira").execute()
            if _r.data:
                # Duplicate temizle — sırayı koru
                _goruldu = set()
                for d in _r.data:
                    _v = str(d["deger"] or "").strip()
                    if _v and _v not in _goruldu:
                        _liste.append(_v)
                        _goruldu.add(_v)
    except: pass

    # cari_kartlar'daki değerleri de ekle — eksik olanları sistem_tanimlar'a yaz
    try:
        if _sb:
            _kolon = "islem_asamasi" if tip == "asama" else "durum"
            _cr = _sb.table("cari_kartlar").select(_kolon).execute()
            if _cr.data:
                _mevcut_max = len(_liste)
                for _row in _cr.data:
                    _val = str(_row.get(_kolon,"") or "").strip()
                    if _val and _val != "nan" and _val not in _liste:
                        _liste.append(_val)
                        # sistem_tanimlar'a da ekle
                        try:
                            _mevcut_max += 1
                            _sb.table("sistem_tanimlar").insert({
                                "tip": tip,
                                "deger": _val,
                                "sira": _mevcut_max
                            }).execute()
                        except: pass
    except: pass

    if _liste:
        if tip == "durum":
            _gizli_durumlar = {"aktif", "pasif", "hedef"}
            _liste = [x for x in _liste if x.strip().lower() not in _gizli_durumlar]
        return _liste

    # Fallback
    if tip == "asama":
        return ["Arama","Tekrar Ara","Randevu","Teklif","Fiyat Hazırla","Deneme","Sözleşme","Kazanıldı","Kaybedildi","Devam Ediyor"]
    return []

def _tanim_ekle(tip, deger):
    try:
        _sb = get_sb_client()
        if _sb:
            # Mevcut max sıra
            _r = _sb.table("sistem_tanimlar").select("sira").eq("tip",tip).order("sira",desc=True).limit(1).execute()
            _sira = (_r.data[0]["sira"] + 1) if _r.data else 1
            _sb.table("sistem_tanimlar").insert({"tip":tip,"deger":deger,"sira":_sira}).execute()
            return True
    except: pass
    return False

def _tanim_sil(tip, deger):
    try:
        _sb = get_sb_client()
        if _sb:
            _sb.table("sistem_tanimlar").delete().eq("tip",tip).eq("deger",deger).execute()
            return True
    except: pass
    return False

def _tanim_guncelle(tip, eski, yeni):
    try:
        _sb = get_sb_client()
        if _sb:
            _sb.table("sistem_tanimlar").update({"deger":yeni}).eq("tip",tip).eq("deger",eski).execute()
            # cari_kartlar'da da güncelle
            kolon = "islem_asamasi" if tip == "asama" else "durum"
            _sb.table("cari_kartlar").update({kolon:yeni}).eq(kolon,eski).execute()
            return True
    except: pass
    return False

def giris_ekrani():
    # ── KÜÇÜK & YUKARIDA GÖRÜNÜM İÇİN CSS ──────────────────────────────────────
    st.markdown("""
<style>
header[data-testid="stHeader"]{display:none !important;}
section[data-testid="stMain"]{align-items:flex-start !important;}
div[data-testid="stAppViewContainer"]{align-items:flex-start !important;}
.block-container{padding-top:0.3rem !important;padding-bottom:0.5rem !important;}
div[data-testid="stVerticalBlock"]{gap:0.3rem !important;}
div[data-testid="stElementContainer"]:has(style){display:contents !important;}
div[data-testid="stElementContainer"]:has(script){display:contents !important;}
div[data-testid="stForm"]{border:none;padding:0;}
div[data-testid="stForm"] .stTextInput input{font-size:11px;padding:0.25rem 0.5rem;height:1.8rem;}
div[data-testid="stForm"] label{font-size:10px;}
div[data-testid="stForm"] button{font-size:11px;padding:0.25rem 0.5rem;height:1.8rem;min-height:1.8rem;}
div[data-testid="stRadio"] label{font-size:10px;}
div[data-testid="stRadio"] div[role="radiogroup"]{gap:0.4rem;}
</style>
""", unsafe_allow_html=True)

    # ── LOGO ──────────────────────────────────────────────────────────────────
    st.markdown("""
<div style="text-align:center;padding:0.1rem 0 0.3rem;">
  <div style="width:28px;height:28px;background:#1d4ed8;border-radius:8px;
       display:inline-flex;align-items:center;justify-content:center;margin-bottom:5px;">
    <svg width="16" height="16" viewBox="0 0 36 36" fill="none">
      <rect x="4" y="4" width="12" height="12" rx="2" fill="white" opacity=".9"/>
      <rect x="20" y="4" width="12" height="12" rx="2" fill="white" opacity=".7"/>
      <rect x="4" y="20" width="12" height="12" rx="2" fill="white" opacity=".7"/>
      <rect x="20" y="20" width="12" height="12" rx="2" fill="white" opacity=".5"/>
    </svg>
  </div>
  <div style="font-size:13px;font-weight:600;color:#0f172a;letter-spacing:-.5px;">MWCRMPRO</div>
  <div style="font-size:9px;color:#64748b;margin-top:2px;margin-bottom:8px;">Cari Yönetim Sistemi</div>
</div>
""", unsafe_allow_html=True)

    _gc1, _gc2, _gc3 = st.columns([5,2,5])
    with _gc2:
        # ── CİHAZ SEÇİMİ — radio buton ile, rerun YOK ────────────────────────
        st.markdown("""
<div style="background:white;border:0.5px solid #e2e8f0;border-radius:8px;
     padding:8px 8px 6px;margin-bottom:6px;">
  <div style="font-size:9px;color:#64748b;text-align:center;margin-bottom:6px;font-weight:500;">
    Hangi cihazdan bağlanıyorsunuz?
  </div>
</div>
""", unsafe_allow_html=True)
        _cihaz = st.radio(
            "Cihaz",
            options=["🖥️  Masaüstü / Laptop", "📱  Telefon / Tablet"],
            horizontal=True,
            label_visibility="collapsed",
            key="giris_cihaz_radio"
        )
        _mobil_secildi = "Telefon" in _cihaz

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        # ── GİRİŞ FORMU ────────────────────────────────────────────────────────
        with st.container(border=True):
            st.markdown("""
<div style="font-size:11px;font-weight:600;color:#0f172a;margin-bottom:10px;">Giriş Yap</div>
""", unsafe_allow_html=True)

            with st.form("giris_form", clear_on_submit=False):
                kullanici = st.text_input("Kullanıcı Adı", placeholder="kullanici_adi")
                sifre     = st.text_input("Şifre", type="password", placeholder="••••••••")
                _giris_btn = st.form_submit_button("Giriş Yap →", use_container_width=True, type="primary")

        if _giris_btn:
            row = None
            # 1. Supabase
            try:
                from supabase import create_client
                url = st.secrets.get("SUPABASE_URL","")
                key = st.secrets.get("SUPABASE_KEY","")
                if url and key:
                    sb = create_client(url, key)
                    res = sb.table("kullanicilar").select("*").eq("kullanici_adi", kullanici).eq("sifre", sifre).execute()
                    if res.data:
                        row = res.data[0]
            except: pass
            # 2. SQLite fallback
            if row is None:
                try:
                    conn = get_conn()
                    r = conn.execute("SELECT * FROM kullanicilar WHERE kullanici_adi=? AND sifre=?", (kullanici, sifre)).fetchone()
                    conn.close()
                    if r:
                        row = {"kullanici_adi": r[1], "sifre": r[2], "rol": r[3]}
                except: pass
            # 3. Hardcoded admin
            if row is None and kullanici == "admin" and sifre == "admin123":
                row = {"kullanici_adi": "admin", "sifre": "admin123", "rol": "admin"}

            if row:
                rol_val = str(row.get("rol") or "") if isinstance(row, dict) else ""
                if not rol_val or rol_val == "None":
                    rol_val = "admin" if kullanici == "admin" else "kullanici"
                try:
                    import json as _yjson
                    _yetki_val = str(row.get("yetkiler","tam") or "tam")
                    _yetki = "tam" if _yetki_val == "tam" else _yjson.loads(_yetki_val)
                except:
                    _yetki = "tam"
                _firma_id_giris = 1

                # Tüm state'i tek seferde set et — kopma olmasın
                st.session_state.update({
                    "giris":            True,
                    "kullanici":        kullanici,
                    "kullanici_ad":     kullanici,
                    "rol":              rol_val,
                    "aktif_tab":        "liste",
                    "_yetki_listesi":   _yetki,
                    "_mobil_mod":       _mobil_secildi,
                    "_ekran_kontrol":   True,
                    "giris_cihaz":      "mobil" if _mobil_secildi else "masaustu",
                })
                # localStorage'a kaydet — sayfa yenilenince otomatik giriş
                _ls_veri = json.dumps({"kullanici": kullanici, "sifre": sifre, "mobil": _mobil_secildi})
                st.markdown(f"""<script>
try{{localStorage.setItem('mwcrm_oturum', {repr(_ls_veri)});}}catch(e){{}}
</script>""", unsafe_allow_html=True)
                # Giriş logla
                try:
                    _sb_logi = get_sb_client()
                    if _sb_logi:
                        _sb_logi.table("kullanici_log").insert({
                            "kullanici": kullanici, "rol": rol_val,
                            "sayfa": "giris", "islem": "GİRİŞ_YAPILDI",
                            "detay": f"{kullanici} sisteme giriş yaptı",
                        }).execute()
                except: pass
                st.rerun()
            else:
                st.error("❌ Kullanıcı adı veya şifre hatalı!")

def cikis():
    try:
        _sb_logc = get_sb_client()
        if _sb_logc and st.session_state.get("kullanici"):
            _sb_logc.table("kullanici_log").insert({
                "kullanici": st.session_state.get("kullanici","?"),
                "rol":       st.session_state.get("rol","?"),
                "sayfa":     "cikis",
                "islem":     "ÇIKIŞ_YAPILDI",
                "detay":     f"{st.session_state.get('kullanici','?')} sistemden çıkış yaptı",
            }).execute()
    except: pass
    st.session_state.clear()
    st.markdown("""<script>
try{localStorage.removeItem('mwcrm_oturum');}catch(e){}
</script>""", unsafe_allow_html=True)
    st.rerun()

# ── SESSION STATE ─────────────────────────────────────────────────────────────
_sayfa_adlari_cfg = {
    "yeni":"Yeni Kart","liste":"Cari Liste",
    "randevu":"Randevular","ozel_teklif":"Özel Teklif","sozlesme":"Sözleşmeler",
    "rapor":"Raporlar","excel":"Excel","kullanici":"Kullanıcılar",
    "admin_rapor":"Admin Rapor","harita":"Müşteri Haritası",
    "dis_nakliye":"Dış Nakliye","dis_nakliye_toplu":"Dış Nakliyeler Listesi",
}
_aktif_cfg = st.session_state.get("aktif_tab","liste")
_baslik_cfg = "MWCRMPRO | " + _sayfa_adlari_cfg.get(_aktif_cfg,"MWCRMPRO")
st.set_page_config(page_title=_baslik_cfg, layout="wide", initial_sidebar_state="expanded")

# ── UYGULAMAYI HER ZAMAN AÇIK TEMADA SABİTLE ─────────────────────────────────
# Bazı bilgisayarlarda Windows/tarayıcı karanlık mod (dark mode) kullanıyor,
# Streamlit da otomatik koyu temaya geçiyor — ama uygulamanın tasarımı hep
# açık tema (beyaz zemin, koyu yazı) varsayımıyla yapıldı. Koyu modda bazı
# yazılar koyu zemin üstünde koyu kalıp okunmaz oluyordu. Bu blok, Streamlit'in
# kendi renk değişkenlerini zorla açık temaya sabitler — hangi bilgisayarda,
# hangi sistem/tarayıcı ayarıyla açılırsa açılsın görünüm hep aynı kalır.
st.markdown("""
<style>
:root, html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    color-scheme: light !important;
    --background-color: #ffffff !important;
    --secondary-background-color: #f8fafc !important;
    --text-color: #0f172a !important;
    --primary-color: #ef4444 !important;
}
[data-testid="stAppViewContainer"], [data-testid="stApp"], .main, .block-container,
section[data-testid="stMain"], section[data-testid="stSidebar"] {
    background-color: #ffffff !important;
    color: #0f172a !important;
}
section[data-testid="stSidebar"] {
    background-color: #f8fafc !important;
}

/* ── KOMPAKT MOD — tüm sistem genelinde gerçek küçültme ──────────────────
   NOT: Tablo (data_editor) canvas ile çizildiği için normal font-size CSS'i
   onu küçültemiyor. "zoom" özelliği tarayıcının PİKSEL bazında her şeyi
   (canvas dahil) küçültmesini sağlar — gerçek/kalıcı çözüm budur. */
[data-testid="stAppViewContainer"] { zoom: 0.95 !important; }
section[data-testid="stSidebar"] { zoom: 0.95 !important; }
html { font-size: 14px !important; }
.block-container { padding-top: 1.2rem !important; padding-bottom: 1.5rem !important; }
section[data-testid="stSidebar"] .block-container { padding-top: 1rem !important; }
/* Streamlit 1.40+ konteyner sınıfını değiştirdi — eski .block-container artık
   gerçek genişlik konteynerine denk gelmiyor, sayfa "wide" modda bile dar
   kalıyordu. Yeni gerçek konteyner buradaki data-testid — tüm sayfalarda
   tam genişlik için bunu da hedefliyoruz. */
[data-testid="stMainBlockContainer"] { max-width: 100% !important; padding-left: 1rem !important; padding-right: 1rem !important; }
[data-testid="stAppViewContainer"] { max-width: 100% !important; }
[data-testid="stAppViewContainer"] > .main { max-width: 100% !important; }
/* ── VERİ TABLOSU (data_editor/dataframe) TAM GENİŞLİK ────────────────────
   Glide tabanlı tablo bileşeni kendi dış kutusunun genişliğine göre kolon
   alanını hesaplıyor. use_container_width=True tek başına her zaman tam
   genişliğe ulaşmadığı için dış kapsayıcıyı burada CSS ile zorluyoruz —
   böylece rapor barındaki (GENEL/AŞAMA/...) tam genişlikli HTML tabloyla
   Cari Liste tablosunun sağ kenarı denk gelir, sağda boşluk kalmaz. */
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"],
[data-testid="stDataFrame"] > div, [data-testid="stDataFrameResizable"] > div {
    width: 100% !important;
    max-width: 100% !important;
}
/* Dış kapsayıcı, içindeki tablo canvas'ından daha dar kalınca KENDİ yatay
   kaydırma çubuğunu da gösteriyordu — tablonun asıl (alttaki) scrollbar'ıyla
   birlikte İKİ tane üst üste görünüyordu. Dış kapsayıcının kendi scrollbar'ını
   kapatıyoruz, asıl/doğru scrollbar (tablonun kendi iç scrollbar'ı) kalıyor. */
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {
    overflow-x: hidden !important;
}
/* ── TABLO ARAÇ ÇUBUĞU (göz/indir/ara/tam ekran) ÜST ÜSTE BİNMESİN ────────
   Streamlit, fare tablonun üzerine gelince sağ üst köşede yüzen bir araç
   çubuğu gösteriyor; bu çubuk tablonun kendi kutusunun biraz dışına taşıp
   hemen üstündeki elemanın üzerine biniyordu. NOT: Önceki çözümde tüm
   tablolara margin-top eklemiştik ama bu, Cari Liste'deki sticky üst bar ve
   buton satırlarının konumunu kaydırıp YENİ bir üst üste binmeye yol açtı —
   o yüzden tablonun kendi kutusuna DOKUNMUYORUZ, sadece araç çubuğunun
   kendi float konumunu nazikçe aşağı itiyoruz.
*/
div[data-testid="stElementToolbar"] {
    z-index: 999 !important;
    transform: translateY(8px);
}
h1 { font-size: 1.6rem !important; }
h2 { font-size: 1.35rem !important; }
h3 { font-size: 1.15rem !important; }
h4, h5, h6 { font-size: 1rem !important; }
.stButton button, .stDownloadButton button { padding: 0.35rem 0.75rem !important; font-size: 0.85rem !important; }
section[data-testid="stSidebar"] .stButton button { padding: 0.4rem 0.6rem !important; font-size: 0.85rem !important; }
[data-testid="stMetricValue"] { font-size: 1.3rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
.stTextInput input, .stSelectbox div[data-baseweb="select"], .stNumberInput input { font-size: 0.85rem !important; }
[data-testid="stExpander"] summary { font-size: 0.9rem !important; padding: 0.5rem 0.75rem !important; }
p, .stMarkdown, label { font-size: 0.9rem !important; }
</style>
""", unsafe_allow_html=True)

# Sekme başlığını aktif menüye göre güncelle
_sayfa_adlari = {
    "yeni":"Yeni Kart","liste":"Cari Liste",
    "randevu":"Randevular","ozel_teklif":"Özel Teklif","sozlesme":"Sözleşmeler",
    "rapor":"Raporlar","excel":"Excel","kullanici":"Kullanıcılar",
    "admin_rapor":"Admin Rapor","harita":"Müşteri Haritası",
    "dis_nakliye":"Dış Nakliye","dis_nakliye_toplu":"Dış Nakliyeler Listesi",
}
_aktif_sayfa = st.session_state.get("aktif_tab","liste")
_sayfa_adi = _sayfa_adlari.get(_aktif_sayfa, _aktif_sayfa)
st.markdown(f"<script>document.title='MWCRMPRO | {_sayfa_adi}'</script>", unsafe_allow_html=True)
st.markdown("""<style>
section[data-testid="stSidebar"]{transform:none!important;display:flex!important;}
button[data-testid="collapsedControl"]{display:none!important;}
[data-testid="stSidebarCollapseButton"]{display:none!important;}
button[kind="header"]{display:none!important;}
.st-emotion-cache-zq5wmm{display:none!important;}
.st-emotion-cache-1lna32f{display:none!important;}
.mw-not-wrap{display:inline-block;position:relative;cursor:pointer;}
.mw-not-ikon{display:inline-flex;align-items:center;gap:3px;font-size:12px;color:#2563eb;background:#eff6ff;padding:2px 8px;border-radius:20px;border:0.5px solid #bfdbfe;white-space:nowrap;user-select:none;}
.mw-not-ikon:hover{background:#dbeafe;}
.mw-not-tooltip{display:none;position:absolute;left:0;top:calc(100%% + 4px);z-index:9999;background:white;border:0.5px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:260px;max-width:340px;font-size:12px;color:#374151;}
.mw-not-wrap:hover .mw-not-tooltip{display:block;}
.mw-not-satir{padding:6px 0;border-bottom:0.5px solid #f1f5f9;line-height:1.5;}
.mw-not-satir:last-child{border-bottom:none;padding-bottom:0;}
.mw-not-meta{font-size:11px;color:#94a3b8;margin-bottom:2px;}
.mw-not-metin{color:#1e293b;}
.mw-not-daha{font-size:11px;color:#94a3b8;margin-top:6px;font-style:italic;}
</style>""", unsafe_allow_html=True)

st.markdown("""<script>
(function(){setInterval(function(){try{var _=window.parent.document.title;}catch(e){}},270000);})();
</script>""", unsafe_allow_html=True)

# ── TAKVİM TÜRKÇELEŞTİRME — tüm date_input bileşenleri için ──────────────────
st.markdown("""<script>
(function(){
  var AY_TR = {
    "January":"Ocak","February":"Şubat","March":"Mart","April":"Nisan",
    "May":"Mayıs","June":"Haziran","July":"Temmuz","August":"Ağustos",
    "September":"Eylül","October":"Ekim","November":"Kasım","December":"Aralık"
  };
  // Gün kısaltmaları sıralı dizi olarak — "Sa" hem Tuesday hem Saturday kısaltması olduğundan
  // object key çakışmasını önlemek için pozisyon bazlı eşleştirme kullanılır.
  // Streamlit/BaseWeb takvimi pazartesi başlangıçlı: Mo,Tu,We,Th,Fr,Sa,Su
  var GUN_KISA_SIRA = ["Mo","Tu","We","Th","Fr","Sa","Su"];
  var GUN_KISA_TR   = ["Pt","Sa","Ça","Pe","Cu","Ct","Pa"];
  var GUN_TAM_TR = {
    "Monday":"Pazartesi","Tuesday":"Salı","Wednesday":"Çarşamba",
    "Thursday":"Perşembe","Friday":"Cuma","Saturday":"Cumartesi","Sunday":"Pazar"
  };
  function turkceleştir(root){
    if(!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while(node = walker.nextNode()){
      var t = node.nodeValue;
      if(!t || !t.trim()) continue;
      var trimmed = t.trim();
      var degisti = false;

      // Ay isimleri — metin içinde geçebilir (örn. "30 June 2026")
      for(var ay in AY_TR){
        if(t.indexOf(ay) !== -1){ t = t.split(ay).join(AY_TR[ay]); degisti = true; }
      }

      // Tam gün isimleri (Monday, Tuesday...)
      for(var gunTam in GUN_TAM_TR){
        if(t.indexOf(gunTam) !== -1){ t = t.split(gunTam).join(GUN_TAM_TR[gunTam]); degisti = true; }
      }

      // Kısa gün başlıkları — SADECE node içeriği TAM OLARAK kısaltmaya eşitse değiştir
      // (içerik karışmasını önlemek için, örn. "Sa" hücre içinde tek başınaysa)
      if(!degisti){
        var idx = GUN_KISA_SIRA.indexOf(trimmed);
        if(idx !== -1 && trimmed === t.trim()){
          t = t.replace(trimmed, GUN_KISA_TR[idx]);
          degisti = true;
        }
      }

      if(degisti) node.nodeValue = t;
    }
  }
  function tumDokumani(){
    try { turkceleştir(document.body); } catch(e){}
    try { if(window.parent && window.parent.document) turkceleştir(window.parent.document.body); } catch(e){}
  }
  // İlk çalıştırma
  tumDokumani();
  // Takvim her açıldığında tekrar çalıştır (MutationObserver)
  try {
    var hedefDoc = (window.parent && window.parent.document) ? window.parent.document : document;
    var observer = new MutationObserver(function(mutations){
      tumDokumani();
    });
    observer.observe(hedefDoc.body, { childList: true, subtree: true });
  } catch(e){}
  // Periyodik yedek kontrol
  setInterval(tumDokumani, 800);
})();
</script>""", unsafe_allow_html=True)


# ── EKRAN AYARLARI UYGULA ────────────────────────────────────────────────────
_e_ust     = st.session_state.get("_ust_px", 32)
_e_alt     = st.session_state.get("_alt_px", 32)
_e_yan     = st.session_state.get("_yan_px", 16)

# Arka plan artık kullanıcı tarafından değiştirilemez — her cihazda/ekranda
# HER ZAMAN beyaz, tek renk. Takım teması / arka plan rengi seçimi özelliği
# kalıcı olarak kaldırıldı.
_bg_css = "body, .main { background-color: #ffffff !important; }"

st.markdown(f"""
<style>
/* Tüm olası selector'lar */
.main .block-container,
div[data-testid="stAppViewContainer"] > section > div,
div[data-testid="stAppViewContainer"] > .main > div,
section.main > div.block-container,
.block-container {{
    padding-top: {_e_ust}px !important;
    padding-bottom: {_e_alt}px !important;
    padding-left: {_e_yan}px !important;
    padding-right: {_e_yan}px !important;
}}
{_bg_css}
</style>
<script>
(function applyPadding() {{
    function apply() {{
        var bc = document.querySelector('.block-container') ||
                 document.querySelector('[data-testid="stAppViewBlockContainer"]') ||
                 document.querySelector('section.main > div');
        if (bc) {{
            bc.style.setProperty('padding-top', '{_e_ust}px', 'important');
            bc.style.setProperty('padding-bottom', '{_e_alt}px', 'important');
            bc.style.setProperty('padding-left', '{_e_yan}px', 'important');
            bc.style.setProperty('padding-right', '{_e_yan}px', 'important');
        }}
    }}
    apply();
    setTimeout(apply, 500);
    setTimeout(apply, 1500);
    var obs = new MutationObserver(apply);
    obs.observe(document.body, {{childList:true, subtree:true}});
}})();
</script>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* ── GENEL BUTON & DROPDOWN ── */
.stButton>button { border-radius: 8px !important; }
[data-baseweb="popover"] [data-baseweb="menu"] { max-height: 600px !important; overflow-y: auto !important; }
[data-baseweb="select"] [data-baseweb="menu"] { max-height: 600px !important; }

/* ── MOBİL NAV — her zaman tanımlanır, sadece .mw-mobil-aktif class'ı varsa görünür ── */
#mw-mobile-nav {
  display: none;
  position: fixed !important;
  bottom: 0 !important; left: 0 !important; right: 0 !important;
  z-index: 9999 !important;
  background: white !important;
  border-top: 0.5px solid #e2e8f0 !important;
  justify-content: space-around !important;
  align-items: center !important;
  padding: 6px 0 10px !important;
  box-shadow: 0 -2px 12px rgba(0,0,0,.07) !important;
}
body.mw-mobil-aktif #mw-mobile-nav { display: flex !important; }
#mw-mobile-nav a {
  display: flex !important; flex-direction: column !important;
  align-items: center !important; gap: 2px !important;
  text-decoration: none !important; color: #64748b !important;
  font-size: 10px !important; font-weight: 500 !important;
  padding: 4px 6px !important; border-radius: 8px !important;
  min-width: 52px !important; min-height: 44px !important;
  justify-content: center !important;
}
#mw-mobile-nav a.aktif { color: #2563eb !important; background: #eff6ff !important; }
#mw-mobile-nav a span.nav-ikon { font-size: 20px !important; line-height: 1 !important; }

/* ── MOBİL MOD — sadece body.mw-mobil-aktif varken ── */
body.mw-mobil-aktif .block-container {
  padding: 4px 6px 80px 6px !important;
  max-width: 100vw !important;
}
body.mw-mobil-aktif section[data-testid="stSidebar"] {
  display: none !important;
}
body.mw-mobil-aktif h1 { font-size: 1.2rem !important; margin-bottom: 6px !important; }
body.mw-mobil-aktif h2 { font-size: 1.05rem !important; margin-bottom: 5px !important; }
body.mw-mobil-aktif h3 { font-size: 0.95rem !important; margin-bottom: 4px !important; }
body.mw-mobil-aktif div[data-testid="column"] {
  width: 100% !important; min-width: 100% !important;
  flex: 0 0 100% !important;
  padding-left: 0 !important; padding-right: 0 !important;
}
body.mw-mobil-aktif div[data-testid="stHorizontalBlock"] {
  flex-wrap: wrap !important; gap: 6px !important;
}
body.mw-mobil-aktif .stButton>button {
  width: 100% !important; min-height: 44px !important;
  font-size: 14px !important; border-radius: 10px !important;
  padding: 10px 14px !important;
}
body.mw-mobil-aktif .stButton>button p {
  font-size: 14px !important; white-space: normal !important; text-align: left !important;
}
body.mw-mobil-aktif .stTextInput>div>div>input,
body.mw-mobil-aktif .stTextArea>div>div>textarea,
body.mw-mobil-aktif .stSelectbox>div>div,
body.mw-mobil-aktif .stNumberInput>div>div>input,
body.mw-mobil-aktif .stDateInput>div>div>input {
  font-size: 16px !important; min-height: 44px !important; border-radius: 8px !important;
}
body.mw-mobil-aktif div[data-baseweb="select"] > div {
  min-height: 44px !important; font-size: 14px !important;
}
body.mw-mobil-aktif .stDataFrame, body.mw-mobil-aktif [data-testid="stDataFrame"],
body.mw-mobil-aktif [data-testid="stDataEditor"] {
  overflow-x: auto !important; font-size: 11px !important; width: 100% !important;
}
body.mw-mobil-aktif div[data-testid="metric-container"] {
  background: white !important; border: 0.5px solid #e2e8f0 !important;
  border-radius: 10px !important; padding: 10px 12px !important; min-width: 0 !important;
}
body.mw-mobil-aktif div[data-testid="metric-container"] label { font-size: 11px !important; }
body.mw-mobil-aktif div[data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 18px !important; }
body.mw-mobil-aktif button[data-baseweb="tab"] {
  font-size: 12px !important; padding: 8px 10px !important; min-height: 40px !important;
}
body.mw-mobil-aktif div[data-baseweb="tab-list"] {
  overflow-x: auto !important; flex-wrap: nowrap !important; scrollbar-width: none !important;
}
body.mw-mobil-aktif div[data-baseweb="tab-list"]::-webkit-scrollbar { display: none !important; }
body.mw-mobil-aktif details > summary {
  font-size: 14px !important; padding: 12px !important; min-height: 44px !important;
}
body.mw-mobil-aktif .stCheckbox label, body.mw-mobil-aktif .stRadio label { font-size: 14px !important; }
body.mw-mobil-aktif .stSlider [role="slider"] { width: 24px !important; height: 24px !important; }
body.mw-mobil-aktif [data-testid="stDownloadButton"] button {
  min-height: 44px !important; font-size: 14px !important; width: 100% !important;
}
body.mw-mobil-aktif [data-testid="stAlert"] {
  font-size: 13px !important; padding: 10px 12px !important; border-radius: 8px !important;
}
body.mw-mobil-aktif footer { display: none !important; }
body.mw-mobil-aktif [data-testid="stHeader"] { display: none !important; }
body.mw-mobil-aktif iframe[src*="leaflet"], body.mw-mobil-aktif iframe[title*="harita"] {
  width: 100% !important; min-height: 320px !important; border-radius: 10px !important;
}
body.mw-mobil-aktif [data-testid="stModal"] > div {
  width: 95vw !important; max-width: 95vw !important;
  margin: 10px auto !important; border-radius: 14px !important;
}
body.mw-mobil-aktif div[data-testid="stHorizontalBlock"]:has(.an-kart-btn) > div:first-child {
  flex: 0 0 85% !important; min-width: 85% !important;
}
body.mw-mobil-aktif div[data-testid="stHorizontalBlock"]:has(.an-kart-btn) > div:last-child {
  flex: 0 0 13% !important; min-width: 13% !important;
}
</style>
""", unsafe_allow_html=True)

# ── MOBİL ALT NAVİGASYON ─────────────────────────────────────────────────────
st.markdown("""<div id="mw-mobile-nav">
  <a class="mw-nav-btn" id="mwnav-liste" href="?_nav=liste"><span class="nav-ikon">📋</span>Liste</a>
  <a class="mw-nav-btn" id="mwnav-analiz" href="?_nav=rapor"><span class="nav-ikon">📊</span>Rapor</a>
  <a class="mw-nav-btn" id="mwnav-randevu" href="?_nav=randevu"><span class="nav-ikon">📅</span>Randevu</a>
  <a class="mw-nav-btn" id="mwnav-harita" href="?_nav=harita"><span class="nav-ikon">🗺️</span>Harita</a>
</div>
<a href="?_masaustune_gec=1" style="
  position:fixed; top:8px; right:8px; z-index:100000;
  background:#0f172a; color:white; text-decoration:none;
  font-size:11px; font-weight:600; padding:7px 12px;
  border-radius:20px; box-shadow:0 2px 8px rgba(0,0,0,.25);
  display:none;" id="mw-masaustu-btn">🖥️ Masaüstüne geç</a>
<script>
(function(){
  var _b = window.parent ? window.parent.document.body : document.body;
  var _btn = document.getElementById('mw-masaustu-btn');
  if(_btn && _b.classList.contains('mw-mobil-aktif')){ _btn.style.display = 'block'; }
})();
</script>""", unsafe_allow_html=True)

# Mobilde menüye hiç girmeden tek dokunuşla masaüstü moduna geçiş
try:
    if st.query_params.get("_masaustune_gec", "") == "1":
        st.session_state["_mobil_mod"] = False
        st.markdown("""<script>
try{
  var _eski = localStorage.getItem('mwcrm_oturum');
  if(_eski){ var _o = JSON.parse(_eski); _o.mobil = false; localStorage.setItem('mwcrm_oturum', JSON.stringify(_o)); }
}catch(e){}
</script>""", unsafe_allow_html=True)
        st.query_params.clear()
        st.rerun()
except Exception:
    pass

# Gizli tab geçiş butonları — mobil nav bunları tetikler
# Mobil nav — query param ile tab geçişi (sadece mobil nav için)
try:
    _mob_nav_qp = st.query_params.get("_nav", "")
    _mob_nav_tablar = ["liste","rapor","randevu","harita","yeni"]
    if _mob_nav_qp and _mob_nav_qp in _mob_nav_tablar:
        st.session_state["aktif_tab"] = _mob_nav_qp
        st.query_params.clear()
        st.rerun()
except Exception:
    pass

st.markdown("""

<style>
.mw-nav-btn {
  display:flex !important; flex-direction:column !important;
  align-items:center !important; gap:2px !important;
  background:none !important; border:none !important;
  color:#64748b !important; font-size:10px !important;
  font-weight:500 !important; padding:4px 6px !important;
  border-radius:8px !important; min-width:52px !important;
  min-height:44px !important; cursor:pointer !important;
  justify-content:center !important;
}
.mw-nav-btn.aktif { color:#2563eb !important; background:#eff6ff !important; }
.mw-nav-btn .nav-ikon { font-size:20px !important; line-height:1 !important; }
/* Gizli streamlit nav butonları */
button[data-testid="baseButton-secondary"][kind="secondary"]:is(
  [data-key="mw_nav_st_liste"],
  [data-key="mw_nav_st_analiz"],
  [data-key="mw_nav_st_randevu"],
  [data-key="mw_nav_st_teklif"],
  [data-key="mw_nav_st_harita"]
) { display: none !important; }
div:has(> button[data-testid="baseButton-secondary"]:is(
  [data-key="mw_nav_st_liste"],
  [data-key="mw_nav_st_analiz"],
  [data-key="mw_nav_st_randevu"],
  [data-key="mw_nav_st_teklif"],
  [data-key="mw_nav_st_harita"]
)) { height: 0 !important; overflow: hidden !important; margin: 0 !important; padding: 0 !important; }
</style>
<script>
function mwTab(tab) {
  // Streamlit'in sidebar butonlarını bul ve tıkla — session state güvenli
  var btns = window.parent.document.querySelectorAll('section[data-testid="stSidebar"] button');
  var tabMap = {
    'liste':'Cari Liste','analiz':'Müşteri Analizi','randevu':'Randevular',
    'ozel_teklif':'Özel Teklif','sozlesme':'Sözleşmeler','harita':'Müşteri Haritası',
    'rapor':'Raporlar','yeni':'Yeni Kart'
  };
  var hedef = tabMap[tab] || tab;
  for(var i=0;i<btns.length;i++){
    if(btns[i].innerText && btns[i].innerText.indexOf(hedef.substring(0,6)) >= 0){
      btns[i].click();
      // Aktif class güncelle
      document.querySelectorAll('.mw-nav-btn').forEach(function(b){ b.classList.remove('aktif'); });
      event.currentTarget.classList.add('aktif');
      return;
    }
  }
}
</script>
""", unsafe_allow_html=True)


# ── MENÜ FONKSİYONLARI (sidebar'dan önce tanımlanmalı) ───────────────────────

def fmt_para(n):
    """Türk muhasebe formatı: 1.000.000,00 ₺"""
    try:
        n = float(n or 0)
        if n == int(n):
            s = f"{int(n):,}".replace(",",".")
        else:
            tam = int(n)
            kurus = round((n - tam) * 100)
            s = f"{tam:,}".replace(",",".") + f",{kurus:02d}"
        return s + " ₺"
    except:
        return "0 ₺"


def fmt_tel(n):
    """5544929309.0 → 554 492 93 09"""
    try:
        if not n or str(n).strip() in ["", "None", "nan", "-"]: return ""
        s = str(n).strip()
        # Float .0 temizle
        if s.endswith(".0"): s = s[:-2]
        # Bilimsel notasyon: 5.52e+09 gibi
        try:
            if "e" in s.lower(): s = str(int(float(s)))
        except: pass
        # Sadece rakam, +, boşluk, tire bırak
        import re as _re2
        s = _re2.sub(r"[^0-9\+\s\-]", "", s).strip()
        return _tel_gruplu(s)
    except: return ""

def _duzenleme_form_key_temizle(fid):
    """Belirli bir müşteri ID'sine ait düzenleme formu widget key'lerini
    session_state'ten siler. Düzenle her tıklandığında çağrılmalı —
    yoksa eskiden o key'e yapışmış (boş veya yanlış) değer, yeni
    value= parametresini görmezden gelip ekranda kalmaya devam eder."""
    _alanlar = ["yeni_il_dis","yeni_ilce_dis","yeni_durum_dis","yeni_temsilci_dis",
                "yeni_seg_dis","yeni_asama_dis","yeni_firma","yeni_yetkili",
                "yeni_gsm","yeni_sabit","yeni_email","yeni_adres","yeni_notlar",
                "bek_ciro_str","ger_ciro_str"]
    for _a in _alanlar:
        st.session_state.pop(f"{_a}_{fid}", None)

def parse_para(s):
    """1.000.000,50 → 1000000.50"""
    try:
        s = str(s).strip().replace(" ","").replace("₺","").replace("TL","")
        if not s: return 0.0
        if "," in s and "." in s:
            s = s.replace(".","").replace(",",".")
        elif "," in s:
            s = s.replace(",",".")
        else:
            s = s.replace(".","")
        return float(s)
    except:
        return 0.0

def fmt_tarih(v):
    """Herhangi bir tarih string'ini 22.06.2026 formatına çevirir"""
    if not v: return ""
    s = str(v).strip()
    if not s or s in ["nan","None",""]: return ""
    try:
        if len(s) >= 10 and s[4] == "-":
            return f"{s[8:10]}.{s[5:7]}.{s[:4]}"
        if len(s) >= 10 and s[2] == "." and s[5] == ".":
            return s[:10]
    except:
        pass
    return s[:10]

def _guncelleme_tarih_parse(s):
    """Farklı formatlardaki (ISO 'T', boşluklu, Türkçe nokta) tarih string'lerini
    gerçek datetime nesnesine çevirir. String karşılaştırması ('2026-08-12 ...' ile
    '2026-08-12T...' gibi farklı ayraçlar) yanlış sonuç verdiği için Güncelleme
    Tarihi hesabında SADECE bu fonksiyonla parse edilmiş datetime'lar karşılaştırılır."""
    if not s:
        return None
    s = str(s).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return None
    import re as _gtre
    _s_temiz = _gtre.sub(r"(\+\d{2}:\d{2}|Z)$", "", s.replace("Z", "+00:00").replace("+00:00", ""))
    for _cand in (_s_temiz, s):
        try:
            return datetime.fromisoformat(_cand)
        except Exception:
            continue
    for _fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, _fmt)
        except Exception:
            continue
    return None

def fmt_tarih_saat(v):
    """Herhangi bir tarih-saat string'ini '22.06.2026 14:23' formatına çevirir (sadece tarih+saat, başka bilgi yok)"""
    if not v: return ""
    s = str(v).strip()
    if not s or s in ["nan","None",""]: return ""
    try:
        _tarih_kismi = fmt_tarih(s)
        _saat_kismi = ""
        _ayrac = "T" if "T" in s else (" " if " " in s else None)
        if _ayrac:
            _saat_ham = s.split(_ayrac, 1)[1].strip()
            if len(_saat_ham) >= 5:
                _saat_kismi = _saat_ham[:5]
        if _tarih_kismi and _saat_kismi:
            return f"{_tarih_kismi} {_saat_kismi}"
        return _tarih_kismi or s[:16]
    except:
        return s[:16]

@st.cache_data(ttl=30, show_spinner=False)
def _notlar_yukle(cari_id):
    try:
        _sb = get_sb_client()
        if _sb:
            _r = _sb.table("cari_aciklamalar").select("*").eq("cari_id", int(cari_id)).execute()
            return _r.data or []
    except: pass
    return []

# ═══════════════════════════════════════════════════════════════════════════
# 🚚 DIŞ NAKLİYE — ortak kolon yapısı / yükleme / kaydetme
# Yeni SQL tablosu AÇILMIYOR — mevcut "kullanici_tercih" tablosunda tek bir
# JSON kayıt olarak saklanıyor (kullanici="__liste_ui__",
# anahtar="dis_nakliye_islemleri"). Her kayıt bir "cari_id" taşır (0 = belirli
# bir müşteriyle ilişkilendirilmemiş, toplu listeden eklenmiş demektir).
# Taşıyıcı (tedarikçi) master listesi de aynı şekilde ayrı bir anahtarda
# ("dis_nakliye_tasiyicilar") JSON olarak saklanır.
# ═══════════════════════════════════════════════════════════════════════════
_DIS_NAKLIYE_KOLONLAR = [
    "tarih", "gonderen_firma", "gonderici_tel", "gonderen_adres", "gonderen_il", "gonderen_ilce",
    "alici_firma", "alici_tel", "alici_adres", "alici_il", "alici_ilce",
    "vergi_dairesi", "vergi_no", "odeme_turu",
    "adet1", "fiyat1", "yekun1", "kdvli1", "odendi1",
    "tasiyici", "yetkili", "yetkili_tel",
    "adet2", "fiyat2", "yekun2", "kdvli2", "odendi2",
    "kar",
]
_DIS_NAKLIYE_BASLIKLAR = {
    "tarih": "TARİH",
    "gonderen_firma": "GÖNDEREN FİRMA", "gonderici_tel": "GÖNDERİCİ TEL", "gonderen_adres": "GÖNDEREN ADRESİ",
    "gonderen_il": "GÖNDEREN İL", "gonderen_ilce": "GÖNDEREN İLÇE",
    "alici_firma": "ALICI FİRMA", "alici_tel": "ALICI TEL", "alici_adres": "ALICI ADRES",
    "alici_il": "ALICI İL", "alici_ilce": "ALICI İLÇE",
    "vergi_dairesi": "VERGİ DAİRESİ", "vergi_no": "VERGİ NO", "odeme_turu": "ÖDEME TÜRÜ",
    "adet1": "ADET", "fiyat1": "BİRİM FİYAT", "yekun1": "YEKÜN", "kdvli1": "KDV'Lİ", "odendi1": "ÖDENDİ",
    "tasiyici": "TAŞIYICI", "yetkili": "YETKİLİ", "yetkili_tel": "YETKİLİ TEL",
    "adet2": "ADET", "fiyat2": "ADET FİYATI", "yekun2": "YEKÜN", "kdvli2": "KDV'Lİ", "odendi2": "ÖDENDİ",
    "kar": "KAR",
}
_DIS_NAKLIYE_GENISLIK = {
    "tarih": 85, "gonderen_firma": 120, "gonderici_tel": 95, "gonderen_adres": 120, "gonderen_il": 75, "gonderen_ilce": 75,
    "alici_firma": 120, "alici_tel": 95, "alici_adres": 120, "alici_il": 75, "alici_ilce": 75,
    "vergi_dairesi": 95, "vergi_no": 90, "odeme_turu": 90,
    "adet1": 55, "fiyat1": 85, "yekun1": 85, "kdvli1": 85, "odendi1": 65,
    "tasiyici": 110, "yetkili": 100, "yetkili_tel": 95,
    "adet2": 55, "fiyat2": 95, "yekun2": 85, "kdvli2": 85, "odendi2": 65,
    "kar": 90,
}
_DIS_NAKLIYE_SAYI_KOLON = {"adet1", "fiyat1", "adet2", "fiyat2"}
_DIS_NAKLIYE_HESAP_KOLON = {"yekun1", "kdvli1", "yekun2", "kdvli2", "kar"}
_DIS_NAKLIYE_CHECK_KOLON = {"odendi1", "odendi2"}

def _dis_nakliye_col_config():
    cfg = {}
    for k in _DIS_NAKLIYE_KOLONLAR:
        w = _DIS_NAKLIYE_GENISLIK.get(k, 90)
        baslik = _DIS_NAKLIYE_BASLIKLAR[k]
        if k in _DIS_NAKLIYE_CHECK_KOLON:
            cfg[k] = st.column_config.CheckboxColumn(baslik, width=w)
        elif k in _DIS_NAKLIYE_SAYI_KOLON:
            cfg[k] = st.column_config.NumberColumn(baslik, width=w, min_value=0, step=1)
        elif k in _DIS_NAKLIYE_HESAP_KOLON:
            cfg[k] = st.column_config.NumberColumn(
                baslik, width=w, format="%.2f ₺", disabled=True,
                help="Otomatik hesaplanır — Adet × Fiyat = Yekün, Yekün × %20 KDV = KDV'li, "
                     "Kar = Müşteri KDV'li − Taşıyıcı KDV'li. Kaydet'e basınca güncellenir.")
        else:
            cfg[k] = st.column_config.TextColumn(baslik, width=w)
    return cfg

def _dis_nakliye_hesapla(df):
    """Yekün / KDV'li / Kar kolonlarını Adet × Fiyat mantığıyla yeniden hesaplar (%20 KDV)."""
    for c in ["adet1", "fiyat1", "adet2", "fiyat2"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["yekun1"] = df["adet1"] * df["fiyat1"]
    df["kdvli1"] = df["yekun1"] * 1.20
    df["yekun2"] = df["adet2"] * df["fiyat2"]
    df["kdvli2"] = df["yekun2"] * 1.20
    df["kar"] = df["kdvli1"] - df["kdvli2"]
    # Metin kolonlarında None/nan yerine boş göster
    for _tk in _DIS_NAKLIYE_KOLONLAR:
        if _tk not in _DIS_NAKLIYE_SAYI_KOLON and _tk not in _DIS_NAKLIYE_HESAP_KOLON and _tk not in _DIS_NAKLIYE_CHECK_KOLON:
            df[_tk] = df[_tk].astype(str).replace(["None", "nan", "NaN", "none"], "")
    return df

def _dis_nakliye_yukle():
    if "_dn2_kayitlar" not in st.session_state:
        st.session_state["_dn2_kayitlar"] = []
        try:
            _sb = get_sb_client()
            if _sb:
                _r = _sb.table("kullanici_tercih").select("deger").eq(
                    "kullanici", "__liste_ui__").eq("anahtar", "dis_nakliye_islemleri").execute()
                if _r.data:
                    st.session_state["_dn2_kayitlar"] = json.loads(_r.data[0]["deger"])
        except Exception:
            pass
    return st.session_state["_dn2_kayitlar"]

def _dis_nakliye_kaydet(kayitlar):
    try:
        _sb = get_sb_client()
        if _sb:
            _sb.table("kullanici_tercih").upsert({
                "kullanici": "__liste_ui__", "anahtar": "dis_nakliye_islemleri",
                "deger": json.dumps(kayitlar, ensure_ascii=False)
            }, on_conflict="kullanici,anahtar").execute()
        st.session_state["_dn2_kayitlar"] = kayitlar
        return True
    except Exception:
        return False

def _dis_nakliye_tasiyici_yukle():
    if "_dn2_tasiyicilar" not in st.session_state:
        st.session_state["_dn2_tasiyicilar"] = []
        try:
            _sb = get_sb_client()
            if _sb:
                _r = _sb.table("kullanici_tercih").select("deger").eq(
                    "kullanici", "__liste_ui__").eq("anahtar", "dis_nakliye_tasiyicilar").execute()
                if _r.data:
                    st.session_state["_dn2_tasiyicilar"] = json.loads(_r.data[0]["deger"])
        except Exception:
            pass
    return st.session_state["_dn2_tasiyicilar"]

def _dis_nakliye_tasiyici_kaydet(liste):
    try:
        _sb = get_sb_client()
        if _sb:
            _sb.table("kullanici_tercih").upsert({
                "kullanici": "__liste_ui__", "anahtar": "dis_nakliye_tasiyicilar",
                "deger": json.dumps(liste, ensure_ascii=False)
            }, on_conflict="kullanici,anahtar").execute()
        st.session_state["_dn2_tasiyicilar"] = liste
        return True
    except Exception:
        return False

def _dis_nakliye_musteri_bilgisi(cari_id):
    """Seçilen müşterinin cari kartından Gönderen bloğu için otomatik bilgileri çeker."""
    try:
        _sb = get_sb_client()
        if _sb:
            _r = _sb.table("cari_kartlar").select("firma,gsm,sabit,adres,il,ilce").eq("id", int(cari_id)).execute()
            if _r.data:
                return _r.data[0]
    except Exception:
        pass
    return {}

def _dis_nakliye_tasiyici_secici(key_prefix):
    """Kayıtlı taşıyıcılar arasından seçim yapılabilen küçük bir bileşen —
    seçilirse (taşıyıcı, yetkili, yetkili_tel) döner, yoksa (None, None, None)."""
    _liste = _dis_nakliye_tasiyici_yukle()
    if not _liste:
        return None, None, None
    _secenekler = ["— Kayıtlı taşıyıcı seç (opsiyonel) —"] + [
        f"{t.get('tasiyici','')} — {t.get('yetkili','')}" for t in _liste
    ]
    _sec = st.selectbox("Kayıtlı Taşıyıcıdan Doldur", _secenekler, key=f"{key_prefix}_tasiyici_sec", label_visibility="collapsed")
    if _sec != _secenekler[0]:
        _idx = _secenekler.index(_sec) - 1
        _t = _liste[_idx]
        return _t.get("tasiyici",""), _t.get("yetkili",""), _t.get("yetkili_tel","")
    return None, None, None

@st.dialog("📋 Notlar & Randevu", width="large")
def not_dialog(cari_id, firma_adi=""):
    """Ekran ortasında açılan not + randevu + silme + düzenleme penceresi"""
    # ── AÇIK KALSIN — pencere içinde bir işlem yapılıp (Ayrıştır, Kaydet vb.)
    # st.rerun() tetiklenince, tabloyu yeniden oluşturan koşul bazen aynı
    # şekilde tekrar sağlanmayabiliyor ve pencere kapanıyordu. Bu yüzden
    # hangi firma için açık olduğu ayrıca session_state'te "kalıcı" tutuluyor —
    # sayfanın en başında bu kayıt varsa pencere garanti yeniden açılıyor.
    st.session_state["_not_dialog_kalici_id"] = cari_id
    st.session_state["_not_dialog_kalici_firma"] = firma_adi
    # ── PENCEREYİ GENİŞLET — Streamlit'in "large" seçeneği en fazla 1280px
    # veriyor, Dış Nakliye tablosundaki çok sayıda kolon için yetersiz
    # kalıyordu. CSS ile ekranın büyük kısmını kaplayacak şekilde zorluyoruz.
    st.markdown("""<style>
[data-testid="stDialog"] div[role="dialog"] {
    width: 96vw !important;
    max-width: 1900px !important;
}
</style>""", unsafe_allow_html=True)
    if st.button("❌ Bu Pencereyi Kapat", key=f"dlg_kapat_{cari_id}"):
        st.session_state.pop("_not_dialog_kalici_id", None)
        st.session_state.pop("_not_dialog_kalici_firma", None)
        st.rerun()
    _tab_not, _tab_rdv, _tab_yetkili, _tab_dn, _tab_kargo, _tab_teklif, _tab_sozlesme, _tab_varis, _tab_duz, _tab_sil = st.tabs(["📝 Notlar", "📅 Randevu Ekle", "👥 Yetkililer", "🚚 Dış Nakliye", "📦 Kargo Girişi", "⭐ Özel Teklif", "📜 Sözleşme Hazırla", "📦 Varış/Fiyat", "✏️ Cari Kartı Düzenle", "🗑️ Cari Sil"])
    with _tab_not:
        not_paneli(cari_id, firma_adi, key_prefix="dlg")
    with _tab_rdv:
        if firma_adi:
            st.markdown(f"**{firma_adi}** için randevu ekle")

        # ── Bu müşterinin ÖNCEKİ randevuları — hiçbiri silinmez, hepsi burada listelenir ──
        try:
            _rdv_sb_l = get_sb_client()
            _rdv_gecmis = pd.DataFrame(_rdv_sb_l.table("randevular").select("*").eq("musteri_id", int(cari_id)).order("randevu_tarihi", desc=True).execute().data) if _rdv_sb_l else pd.DataFrame()
        except Exception:
            _rdv_gecmis = pd.DataFrame()

        if not _rdv_gecmis.empty:
            st.caption(f"📌 {len(_rdv_gecmis)} randevu kayıtlı — yeni ekleme bunları silmez:")
            for _, _rg in _rdv_gecmis.iterrows():
                _rgc1, _rgc2, _rgc3, _rgc4 = st.columns([1.2, 1.2, 3, 0.6])
                _rgc1.caption(f"📅 {fmt_tarih(_rg.get('randevu_tarihi',''))} {_rg.get('randevu_saati','')}")
                _rgc2.caption(f"🏷️ {_rg.get('gorev','') or '—'}")
                _rgc3.caption(f"📝 {(_rg.get('aciklama','') or '—')[:60]}")
                if _rgc4.button("🗑", key=f"dlg_rdv_gecmis_sil_{cari_id}_{int(_rg['id'])}"):
                    try:
                        _rdv_sb_l.table("randevular").delete().eq("id", int(_rg["id"])).execute()
                        st.rerun()
                    except Exception as _rge:
                        st.error(f"Hata: {_rge}")
            st.divider()
        else:
            st.caption("Henüz randevu kaydı yok.")

        st.markdown("**➕ Yeni Randevu Ekle**")
        _dr1, _dr2 = st.columns(2)
        _rdv_t = _dr1.date_input("Tarih", key=f"dlg_rdv_t_{cari_id}")
        _rdv_s = _dr2.selectbox("Saat", [f"{h:02d}:{m:02d}" for h in range(8,21) for m in [0,30]], key=f"dlg_rdv_s_{cari_id}")
        _rdv_g = st.selectbox("Görev", ["Ziyaret","Toplantı","Online Görüşme","Telefon","Diğer"], key=f"dlg_rdv_g_{cari_id}")
        _rdv_n = st.text_area("Not", key=f"dlg_rdv_n_{cari_id}", placeholder="Randevu notu...", height=80)
        if st.button("📅 Randevu Kaydet", key=f"dlg_rdv_k_{cari_id}", type="primary", use_container_width=True):
            try:
                _sb_r = get_sb_client()
                if _sb_r:
                    _sb_r.table("randevular").insert({
                        "musteri_id":    cari_id,
                        "musteri_adi":   firma_adi,
                        "randevu_tarihi": str(_rdv_t),
                        "randevu_saati":  _rdv_s,
                        "gorev":          _rdv_g,
                        "aciklama":       _rdv_n,
                        "olusturan":      st.session_state.get("kullanici",""),
                    }).execute()
                    st.success(f"✅ Randevu eklendi!")
                    st.cache_data.clear()
                    st.rerun()
            except Exception as _re:
                st.error(f"Hata: {_re}")
    with _tab_yetkili:
        st.caption(f"**{firma_adi}** için birden fazla yetkili kişi ekleyebilirsiniz (ad, görev, email, GSM, sabit tel).")
        import json as _ykj
        _YK_ETIKET = "##YETKILI##"

        # ── Kart üzerindeki mevcut (eski) tek Yetkili alanını da listenin başında göster ──
        _yk_kart_liste = []
        try:
            _yk_sb0 = get_sb_client()
            _yk_kart_r = _yk_sb0.table("cari_kartlar").select("yetkili,gsm,sabit,email").eq("id", int(cari_id)).execute() if _yk_sb0 else None
            if _yk_kart_r and _yk_kart_r.data:
                _yk_kart = _yk_kart_r.data[0]
                if str(_yk_kart.get("yetkili","") or "").strip():
                    _yk_kart_liste.append({
                        "id": None, "ad": _yk_kart.get("yetkili",""), "gorev": "(Kart üzerindeki birincil yetkili)",
                        "email": _yk_kart.get("email","") or "", "gsm": _yk_kart.get("gsm","") or "",
                        "sabit_tel": _yk_kart.get("sabit","") or "", "kart_kaynakli": True,
                    })
        except Exception:
            pass

        try:
            _yk_sb = get_sb_client()
            _yk_ham = pd.DataFrame(_yk_sb.table("cari_aciklamalar").select("*").eq("cari_id", int(cari_id)).order("id").execute().data) if _yk_sb else pd.DataFrame()
        except Exception as _yke:
            _yk_ham = pd.DataFrame()
            st.caption(f"⚠️ Yetkililer yüklenemedi: {_yke}")

        _yk_liste = list(_yk_kart_liste)
        if not _yk_ham.empty and "aciklama" in _yk_ham.columns:
            for _, _hr in _yk_ham.iterrows():
                _metin = str(_hr.get("aciklama","") or "")
                if _metin.startswith(_YK_ETIKET):
                    try:
                        _kayit = _ykj.loads(_metin[len(_YK_ETIKET):])
                        _kayit["id"] = _hr.get("id")
                        _yk_liste.append(_kayit)
                    except Exception:
                        pass

        if _yk_liste:
            for _yk_r in _yk_liste:
                with st.container(border=True):
                    _yk_duzenleniyor = st.session_state.get("dlg_yk_duzenle_id") == _yk_r.get("id") and _yk_r.get("id") is not None

                    if _yk_duzenleniyor:
                        _dc1, _dc2, _dc3, _dc4, _dc5 = st.columns([2,1.4,2,1.4,1.4])
                        _d_ad    = _dc1.text_input("Ad Soyad", value=_yk_r.get("ad",""), key=f"dlg_yk_dad_{_yk_r['id']}")
                        _d_gorev = _dc2.text_input("Görev", value=_yk_r.get("gorev",""), key=f"dlg_yk_dgorev_{_yk_r['id']}")
                        _d_email = _dc3.text_input("Email", value=_yk_r.get("email",""), key=f"dlg_yk_demail_{_yk_r['id']}")
                        _d_gsm   = _dc4.text_input("GSM", value=_yk_r.get("gsm",""), key=f"dlg_yk_dgsm_{_yk_r['id']}")
                        _d_sabit = _dc5.text_input("Sabit Tel", value=_yk_r.get("sabit_tel",""), key=f"dlg_yk_dsabit_{_yk_r['id']}")
                        _de1, _de2 = st.columns(2)
                        if _de1.button("💾 Kaydet", key=f"dlg_yk_dkaydet_{_yk_r['id']}", type="primary", use_container_width=True):
                            try:
                                _yeni_json = _ykj.dumps({
                                    "ad": _d_ad.strip(), "gorev": _d_gorev.strip(), "email": _d_email.strip(),
                                    "gsm": _d_gsm.strip(), "sabit_tel": _d_sabit.strip(),
                                }, ensure_ascii=False)
                                _yk_sb.table("cari_aciklamalar").update({"aciklama": _YK_ETIKET + _yeni_json}).eq("id", int(_yk_r["id"])).execute()
                                st.session_state.pop("dlg_yk_duzenle_id", None)
                                st.success("✅ Güncellendi!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as _yue:
                                st.error(f"Hata: {_yue}")
                        if _de2.button("✖️ Vazgeç", key=f"dlg_yk_diptal_{_yk_r['id']}", use_container_width=True):
                            st.session_state.pop("dlg_yk_duzenle_id", None)
                            st.rerun()
                    else:
                        _yc1, _yc2, _yc3, _yc4, _yc5 = st.columns([2,1.4,2,1.4,1.4])
                        _yc1.markdown(f"**{_yk_r.get('ad','') or '—'}**")
                        _yc2.caption(f"🧩 {_yk_r.get('gorev','') or '—'}")
                        _yc3.caption(f"✉️ {_yk_r.get('email','') or '—'}")
                        _yc4.caption(f"📱 {_yk_r.get('gsm','') or '—'}")
                        _yc5.caption(f"☎️ {_yk_r.get('sabit_tel','') or '—'}")
                        if _yk_r.get("kart_kaynakli"):
                            st.caption("ℹ️ Bu kişi cari karttaki 'Yetkili' alanından otomatik geliyor — değiştirmek için 'Cari Kartı Düzenle' sekmesini kullanın.")
                        else:
                            _yb1, _yb2 = st.columns(2)
                            if _yb1.button("✏️ Düzenle", key=f"dlg_yk_duz_{cari_id}_{int(_yk_r['id'])}", use_container_width=True):
                                st.session_state["dlg_yk_duzenle_id"] = _yk_r["id"]
                                st.rerun()
                            if _yb2.button("🗑️ Sil", key=f"dlg_yk_sil_{cari_id}_{int(_yk_r['id'])}", use_container_width=True):
                                try:
                                    _yk_sb.table("cari_aciklamalar").delete().eq("id", int(_yk_r["id"])).execute()
                                    st.success("Silindi.")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as _yde:
                                    st.error(f"Hata: {_yde}")
        else:
            st.caption("Henüz yetkili eklenmemiş.")

        st.markdown("**➕ Yeni Yetkili Ekle**")
        _yn1, _yn2, _yn3, _yn4, _yn5 = st.columns([2,1.4,2,1.4,1.4])
        _yk_ad     = _yn1.text_input("", placeholder="Ad Soyad", key=f"dlg_yk_ad_{cari_id}", label_visibility="collapsed")
        _yk_gorev  = _yn2.text_input("", placeholder="Görev", key=f"dlg_yk_gorev_{cari_id}", label_visibility="collapsed")
        _yk_email  = _yn3.text_input("", placeholder="Email", key=f"dlg_yk_email_{cari_id}", label_visibility="collapsed")
        _yk_gsm    = _yn4.text_input("", placeholder="GSM", key=f"dlg_yk_gsm_{cari_id}", label_visibility="collapsed")
        _yk_sabit  = _yn5.text_input("", placeholder="Sabit Tel", key=f"dlg_yk_sabit_{cari_id}", label_visibility="collapsed")
        if st.button("👥 Yetkili Ekle", key=f"dlg_yk_ekle_{cari_id}", type="primary", use_container_width=True):
            if not _yk_ad.strip():
                st.warning("Ad Soyad gerekli.")
            else:
                try:
                    _yk_sb2 = get_sb_client()
                    _yk_json = _ykj.dumps({
                        "ad": _yk_ad.strip(), "gorev": _yk_gorev.strip(), "email": _yk_email.strip(),
                        "gsm": _yk_gsm.strip(), "sabit_tel": _yk_sabit.strip(),
                    }, ensure_ascii=False)
                    _yk_sb2.table("cari_aciklamalar").insert({
                        "cari_id": int(cari_id),
                        "aciklama": _YK_ETIKET + _yk_json,
                        "olusturan": st.session_state.get("kullanici",""),
                    }).execute()
                    st.success("✅ Yetkili eklendi!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as _yee:
                    st.error(f"Hata: {_yee}")
    with _tab_dn:
        st.caption(f"**{firma_adi}** için dış nakliye kaydı — Gönderen bilgileri bu müşteriden otomatik gelir.")
        _dn_tum = _dis_nakliye_yukle()
        _dn_bu_musteri = [r for r in _dn_tum if int(r.get("cari_id", 0) or 0) == int(cari_id)]

        with st.expander("➕ Yeni Dış Nakliye Kaydı Ekle", expanded=not _dn_bu_musteri):
            _dnt_ad, _dnt_yet, _dnt_tel = _dis_nakliye_tasiyici_secici(f"dlg_dn_{cari_id}")
            _dnf1, _dnf2 = st.columns(2)
            _dn_tasiyici_v = _dnf1.text_input("Taşıyıcı", value=_dnt_ad or "", key=f"dlg_dn_tasiyici_{cari_id}")
            _dn_yetkili_v = _dnf2.text_input("Yetkili", value=_dnt_yet or "", key=f"dlg_dn_yetkili_{cari_id}")
            _dn_yetkili_tel_v = st.text_input("Yetkili Tel", value=_dnt_tel or "", key=f"dlg_dn_yetkilitel_{cari_id}")
            _dn_tasiyici_kaydet_check = st.checkbox("Bu taşıyıcıyı ileride tekrar seçebilmek için kaydet",
                                                     key=f"dlg_dn_tas_kaydet_{cari_id}")
            if st.button("➕ Kaydı Oluştur", key=f"dlg_dn_ekle_btn_{cari_id}", type="primary", use_container_width=True):
                _musteri_bilgi = _dis_nakliye_musteri_bilgisi(cari_id)
                _yeni_id = int(max([int(r.get("id", 0) or 0) for r in _dn_tum], default=0)) + 1
                _yeni_kayit = {
                    "id": _yeni_id, "cari_id": int(cari_id), "tarih": str(datetime.now().date()),
                    "gonderen_firma": _musteri_bilgi.get("firma", firma_adi) or firma_adi,
                    "gonderici_tel": _musteri_bilgi.get("gsm") or _musteri_bilgi.get("sabit") or "",
                    "gonderen_adres": _musteri_bilgi.get("adres", "") or "",
                    "gonderen_il": _musteri_bilgi.get("il", "") or "",
                    "gonderen_ilce": _musteri_bilgi.get("ilce", "") or "",
                    "alici_firma": "", "alici_tel": "", "alici_adres": "", "alici_il": "", "alici_ilce": "",
                    "vergi_dairesi": "", "vergi_no": "", "odeme_turu": "",
                    "adet1": 0, "fiyat1": 0, "yekun1": 0, "kdvli1": 0, "odendi1": False,
                    "tasiyici": _dn_tasiyici_v, "yetkili": _dn_yetkili_v, "yetkili_tel": _dn_yetkili_tel_v,
                    "adet2": 0, "fiyat2": 0, "yekun2": 0, "kdvli2": 0, "odendi2": False,
                    "kar": 0,
                }
                _dn_tum.append(_yeni_kayit)
                if _dis_nakliye_kaydet(_dn_tum):
                    if _dn_tasiyici_kaydet_check and _dn_tasiyici_v.strip():
                        _tas_liste = _dis_nakliye_tasiyici_yukle()
                        if not any(t.get("tasiyici","").strip().lower() == _dn_tasiyici_v.strip().lower() for t in _tas_liste):
                            _tas_liste.append({"tasiyici": _dn_tasiyici_v, "yetkili": _dn_yetkili_v, "yetkili_tel": _dn_yetkili_tel_v})
                            _dis_nakliye_tasiyici_kaydet(_tas_liste)
                    st.success("✅ Dış nakliye kaydı eklendi — aşağıdaki tabloda diğer bilgileri (alıcı, adet, fiyat vb.) doldurup Kaydet'e basabilirsin.")
                    st.rerun()
                else:
                    st.error("❌ Kaydedilemedi, bağlantıyı kontrol et.")

        if _dn_bu_musteri:
            _dn_df = pd.DataFrame(_dn_bu_musteri)
            for _c in _DIS_NAKLIYE_KOLONLAR:
                if _c not in _dn_df.columns:
                    _dn_df[_c] = 0 if _c in _DIS_NAKLIYE_SAYI_KOLON or _c in _DIS_NAKLIYE_HESAP_KOLON else (False if _c in _DIS_NAKLIYE_CHECK_KOLON else "")
            _dn_df = _dis_nakliye_hesapla(_dn_df)
            _dn_df = _dn_df[["id", "cari_id"] + _DIS_NAKLIYE_KOLONLAR]
            _dn_df = _dn_df.reset_index(drop=True)
            _dn_df.insert(0, "Seç", False)
            _dn_df.index = _dn_df.index + 1
            _dn_df.index.name = "S.No"

            _dn_edited = st.data_editor(
                _dn_df, use_container_width=True, num_rows="fixed",
                column_config={
                    **_dis_nakliye_col_config(), "id": None, "cari_id": None,
                    "Seç": st.column_config.CheckboxColumn("Seç", default=False),
                },
                key=f"dlg_dn_editor_{cari_id}",
                height=min(400, 45 + (len(_dn_df) * 35) + 5),
            )

            _dn_secili = _dn_edited[_dn_edited["Seç"] == True]
            _dn_secili_sayi = len(_dn_secili)
            _dn_secili_idler = _dn_secili["id"].tolist() if not _dn_secili.empty else []

            _dnk1, _dnk2 = st.columns([1, 1])
            with _dnk1:
                if st.button("💾 Değişiklikleri Kaydet", key=f"dlg_dn_kaydet_{cari_id}", type="primary", use_container_width=True):
                    _dn_final = _dn_edited.drop(columns=["Seç"]).reset_index(drop=True).copy()
                    _dn_final = _dis_nakliye_hesapla(_dn_final)
                    for _c in ["id", "cari_id"]:
                        if _c not in _dn_final.columns:
                            _dn_final[_c] = 0
                    _dn_final["id"] = _dn_final["id"].apply(lambda x: int(x) if str(x).strip() not in ("", "nan", "None") and float(x) > 0 else 0)
                    _dn_final["cari_id"] = int(cari_id)
                    _yeni_id_sayac = int(max([int(r.get("id", 0) or 0) for r in _dn_tum], default=0)) + 1
                    _bu_musteri_yeni = []
                    for _, _row in _dn_final.iterrows():
                        _rd = _row.to_dict()
                        if not _rd.get("id"):
                            _rd["id"] = _yeni_id_sayac
                            _yeni_id_sayac += 1
                        _bu_musteri_yeni.append(_rd)
                    _diger_musteriler = [r for r in _dn_tum if int(r.get("cari_id", 0) or 0) != int(cari_id)]
                    _tam_liste = _diger_musteriler + _bu_musteri_yeni
                    if _dis_nakliye_kaydet(_tam_liste):
                        st.toast("✅ Dış nakliye kayıtları güncellendi!", icon="✅")
                        st.rerun()
                    else:
                        st.error("❌ Kaydedilemedi, bağlantıyı kontrol et.")
            with _dnk2:
                if _dn_secili_sayi > 0:
                    if not st.session_state.get(f"_dn_sil_onay_bekliyor_{cari_id}"):
                        if st.button(f"🗑️ Seçili {_dn_secili_sayi} Kaydı Sil", key=f"dlg_dn_sil_{cari_id}", use_container_width=True):
                            st.session_state[f"_dn_sil_onay_bekliyor_{cari_id}"] = True
                            st.rerun()
                else:
                    st.caption("Silmek için satırları soldaki Seç kutusuyla işaretle.")

            if _dn_secili_sayi > 0 and st.session_state.get(f"_dn_sil_onay_bekliyor_{cari_id}"):
                st.warning(f"⚠️ Seçili {_dn_secili_sayi} kayıt kalıcı olarak silinecek, geri alınamaz! Silmek istediğine emin misin?")
                _dnsa1, _dnsa2 = st.columns(2)
                with _dnsa1:
                    if st.button(f"✅ Evet, {_dn_secili_sayi} kaydı sil", type="primary", key=f"dlg_dn_sil_onay_{cari_id}", use_container_width=True):
                        _dn_silinecek_idler = set(int(x) for x in _dn_secili_idler)
                        _dn_kalan = [r for r in _dn_tum if int(r.get("id", 0) or 0) not in _dn_silinecek_idler]
                        if _dis_nakliye_kaydet(_dn_kalan):
                            st.session_state.pop(f"_dn_sil_onay_bekliyor_{cari_id}", None)
                            st.success(f"✅ {_dn_secili_sayi} kayıt silindi!")
                            st.rerun()
                        else:
                            st.error("❌ Silinemedi, bağlantıyı kontrol et.")
                with _dnsa2:
                    if st.button("❌ Vazgeç", key=f"dlg_dn_sil_vazgec_{cari_id}", use_container_width=True):
                        st.session_state.pop(f"_dn_sil_onay_bekliyor_{cari_id}", None)
                        st.rerun()
        else:
            st.caption("Bu müşteri için henüz dış nakliye kaydı yok.")
    with _tab_kargo:
        # ── KARGO GİRİŞİ — cari_kartlar'a yeni kolon açmadan (migration yok
        # kuralı), her müşterinin kargo çıkış kayıtları kullanici_tercih
        # tablosunda MÜŞTERİYE ÖZEL bir anahtarda (JSON liste) tutulur:
        # anahtar = "_kargo_kayitlari_<cari_id>"
        _kg_sb = get_sb_client()
        _kg_anahtar = f"_kargo_kayitlari_{int(cari_id)}"

        @st.cache_data(ttl=30, show_spinner=False)
        def _kg_kayitlari_yukle(_anahtar):
            try:
                _sb_kg = get_sb_client()
                if _sb_kg:
                    _r_kg = _sb_kg.table("kullanici_tercih").select("deger").eq(
                        "kullanici", "__liste_ui__").eq("anahtar", _anahtar).execute()
                    if _r_kg.data:
                        import json as _kgj
                        return _kgj.loads(_r_kg.data[0]["deger"])
            except Exception:
                pass
            return []

        def _kg_kayitlari_kaydet(_anahtar, _liste):
            try:
                _sb_kg2 = get_sb_client()
                if _sb_kg2:
                    import json as _kgj2
                    _deger = _kgj2.dumps(_liste, ensure_ascii=False)
                    _sb_kg2.table("kullanici_tercih").delete().eq("kullanici", "__liste_ui__").eq("anahtar", _anahtar).execute()
                    _sb_kg2.table("kullanici_tercih").insert({"kullanici": "__liste_ui__", "anahtar": _anahtar, "deger": _deger}).execute()
            except Exception:
                pass

        st.caption(f"**{firma_adi}** için kargo çıkış kaydı ekle:")
        # Kayıtlı müşteri listesi — Gönderen/Alıcı/Fatura Ödeyen alanlarında
        # elle yazmak yerine sistemdeki müşterilerden seçilebilsin diye.
        try:
            _kg_musteri_liste = sorted(get_cari_listesi()["firma"].dropna().astype(str).unique().tolist())
        except Exception:
            _kg_musteri_liste = []
        _kg_musteri_opts = ["-- Seç veya elle yaz --"] + _kg_musteri_liste
        _kg_il_opts = ["-- İl seçilir --"] + [_tr_buyuk(a) for a in (_IL_SUTUN_LISTESI[:-1] + _IL_DIGER_LISTESI)]
        try:
            _kg_tasiyici_opts = ["-- Seç veya elle yaz --"] + _dis_nakliye_tasiyici_yukle()
        except Exception:
            _kg_tasiyici_opts = ["-- Seç veya elle yaz --"]
        # Bu iller "yakın/yerel" sayılır — Alıcı İl bunlardan biriyse Dış Nakliye
        # alanları hiç gösterilmez (dış bölgeye çıkmıyor demektir).
        _KG_YEREL_ILLER = [_tr_buyuk(a) for a in ["İzmir", "Bursa", "Kocaeli", "Tekirdağ", "İstanbul", "Manisa"]]

        # NOT: st.form KULLANILMIYOR — "Alıcı İl" seçimine göre Dış Nakliye
        # bölümünün anlık (canlı) gösterilip gizlenmesi gerekiyor; form içindeki
        # widget'lar sadece gönderilince işlenir, canlı tepki veremez.
        _kgc1, _kgc2, _kgc3 = st.columns(3)
        _kg_tarih = _kgc1.date_input("Tarih *", key=f"kg_tarih_{cari_id}")
        _kg_takip = _kgc2.text_input("Takip No", key=f"kg_takip_{cari_id}")
        _kg_tur = _kgc3.text_input("Tür", key=f"kg_tur_{cari_id}", placeholder="Koli / Palet / ...")
        _kg_gonderen_idx = (_kg_musteri_opts.index(firma_adi) if firma_adi in _kg_musteri_opts else 0)
        _kg_gonderen_sec = _kgc1.selectbox("Gönderen Firma", _kg_musteri_opts, index=_kg_gonderen_idx, key=f"kg_gonderen_sec_{cari_id}")
        _kg_gonderen_elle = _kgc1.text_input("(Listede yoksa elle yaz)", key=f"kg_gonderen_elle_{cari_id}", label_visibility="collapsed", placeholder="Listede yoksa buraya elle yaz")
        _kg_alici_sec = _kgc2.selectbox("Alıcı Firma", _kg_musteri_opts, key=f"kg_alici_sec_{cari_id}")
        _kg_alici_elle = _kgc2.text_input("(Listede yoksa elle yaz)", key=f"kg_alici_elle_{cari_id}", label_visibility="collapsed", placeholder="Listede yoksa buraya elle yaz")
        # ── Fatura Ödeyen — "Ödeme Türü (Fatura)" seçimine göre OTOMATİK belirlenir:
        # PÖ veya CH ise Gönderen Firma, ÜA ise Alıcı Firma otomatik seçilir.
        # (O widget kodda daha aşağıda tanımlı olsa da, session_state'teki
        # ÖNCEKİ seçimi buradan okuyabiliyoruz — Streamlit rerun'da widget
        # değerleri kod çalışmadan ÖNCE zaten session_state'te hazır olur.)
        _kg_gonderen_hesaplanan = _kg_gonderen_elle.strip() or (_kg_gonderen_sec if _kg_gonderen_sec != "-- Seç veya elle yaz --" else "")
        _kg_alici_hesaplanan = _kg_alici_elle.strip() or (_kg_alici_sec if _kg_alici_sec != "-- Seç veya elle yaz --" else "")
        _kg_odeme_sekli_onceki = st.session_state.get(f"kg_fatura_odeme_sekli_{cari_id}", "")
        _kg_fatura_varsayilan_idx = 0
        if _kg_odeme_sekli_onceki in ("PÖ", "CH") and _kg_gonderen_hesaplanan in _kg_musteri_opts:
            _kg_fatura_varsayilan_idx = _kg_musteri_opts.index(_kg_gonderen_hesaplanan)
        elif _kg_odeme_sekli_onceki == "ÜA" and _kg_alici_hesaplanan in _kg_musteri_opts:
            _kg_fatura_varsayilan_idx = _kg_musteri_opts.index(_kg_alici_hesaplanan)
        _kg_fatura_sec = _kgc3.selectbox("Fatura Ödeyen *", _kg_musteri_opts, index=_kg_fatura_varsayilan_idx, key=f"kg_fatura_sec_{cari_id}")
        _kg_fatura_elle = _kgc3.text_input("(Listede yoksa elle yaz)", key=f"kg_fatura_elle_{cari_id}", label_visibility="collapsed", placeholder="Listede yoksa buraya elle yaz")
        _kg_gonderen_il = _kgc1.selectbox("Gönderen İl", _kg_il_opts, key=f"kg_gonderen_il_{cari_id}")
        # ── Alıcı İl — daha önce bu Alıcı Firma için kaydedilmiş bir il varsa
        # otomatik önerilir (elle her seferinde yazmaya gerek kalmasın diye).
        _kg_manuel_alici_hafiza = _kg_manuel_alici_yukle()
        _kg_alici_firma_hesaplanan = _kg_alici_elle.strip() or (_kg_alici_sec if _kg_alici_sec != "-- Seç veya elle yaz --" else "")
        _kg_alici_il_varsayilan_idx = 0
        if _kg_alici_firma_hesaplanan:
            _kg_hafizadaki_il = _kg_manuel_alici_hafiza.get(_tr_buyuk(_kg_alici_firma_hesaplanan))
            if _kg_hafizadaki_il and _kg_hafizadaki_il in _kg_il_opts:
                _kg_alici_il_varsayilan_idx = _kg_il_opts.index(_kg_hafizadaki_il)
        _kg_alici_il = _kgc2.selectbox("Alıcı İl", _kg_il_opts, index=_kg_alici_il_varsayilan_idx, key=f"kg_alici_il_{cari_id}")
        if _kg_alici_firma_hesaplanan and _kg_alici_il != "-- İl seçilir --" and _kg_manuel_alici_hafiza.get(_tr_buyuk(_kg_alici_firma_hesaplanan)):
            st.caption(f"💡 '{_kg_alici_firma_hesaplanan}' için daha önce kaydedilen il otomatik önerildi.")
        _kg_fatura_odeme_sekli = _kgc3.selectbox("Ödeme Türü (Fatura)", ["", "Faturasız", "PÖ", "ÜA", "CH"], key=f"kg_fatura_odeme_sekli_{cari_id}",
                                                  help="PÖ/CH seçilirse Fatura Ödeyen otomatik Gönderen olur, ÜA seçilirse otomatik Alıcı olur.")
        _kg_adet = _kgc1.number_input("Adet", min_value=0, step=1, key=f"kg_adet_{cari_id}")
        _kg_tutar = _kgc2.number_input("Tutar", min_value=0.0, step=0.01, key=f"kg_tutar_{cari_id}")
        _kg_kdv = _kgc3.number_input("KDV", min_value=0.0, step=0.01, key=f"kg_kdv_{cari_id}")
        _kg_sigorta = _kgc1.number_input("Sigorta", min_value=0.0, step=0.01, key=f"kg_sigorta_{cari_id}")
        _kg_toplam_fatura = _kgc2.number_input("Toplam Fatura", min_value=0.0, step=0.01, key=f"kg_toplam_fatura_{cari_id}")
        _kg_odeme_tur = _kgc3.selectbox("Ödeme Türü", ["", "Nakit", "Havale/EFT", "Çek", "Kredi Kartı", "Diğer"], key=f"kg_odeme_{cari_id}")
        _kg_tahsilat = _kgc1.selectbox("Tahsilat Durumu", ["", "Tahsil Edildi", "Bekliyor", "Kısmi Tahsilat"], key=f"kg_tahsilat_{cari_id}")

        # ── Dış Nakliye bölümü — SADECE Alıcı İl "yerel" iller dışında bir il
        # (dış bölge) ise gösterilir. Yerel il seçiliyse bu alanlar hiç görünmez.
        _kg_dis_bolge_mi = (_kg_alici_il != "-- İl seçilir --" and _kg_alici_il not in _KG_YEREL_ILLER)
        _kg_dn_firma, _kg_dn_fatura, _kg_dn_detay, _kg_dn_tutar, _kg_musteri_tutar, _kg_dn_odeme = "", "", "", 0.0, 0.0, ""
        if _kg_dis_bolge_mi:
            st.divider()
            st.caption(f"🚚 **{_kg_alici_il}** dış bölge sayıldığı için Dış Nakliye bilgileri gerekli:")
            _kgd1, _kgd2, _kgd3 = st.columns(3)
            _kg_dn_firma_sec = _kgd1.selectbox("Dış Nakliye Firma", _kg_tasiyici_opts, key=f"kg_dn_firma_sec_{cari_id}")
            _kg_dn_firma_elle = _kgd1.text_input("(Listede yoksa elle yaz)", key=f"kg_dn_firma_elle_{cari_id}", label_visibility="collapsed", placeholder="Listede yoksa buraya elle yaz")
            _kg_dn_fatura = _kgd2.text_input("Dış Nakliye Fatura", key=f"kg_dn_fatura_{cari_id}")
            _kg_dn_detay = _kgd3.text_input("Dış Nakliye Detay", key=f"kg_dn_detay_{cari_id}", placeholder="Örn: 2 Palet")
            _kg_dn_tutar = _kgd1.number_input("Dış Nakliye Tutar", min_value=0.0, step=0.01, key=f"kg_dn_tutar_{cari_id}")
            _kg_musteri_tutar = _kgd2.number_input("Müşteri Tutar", min_value=0.0, step=0.01, key=f"kg_musteri_tutar_{cari_id}")
            _kg_dn_odeme = _kgd3.selectbox("Dış Nakliye Ödeme Durumu", ["", "Ödendi", "Ödenmedi", "Kısmi Ödendi"], key=f"kg_dn_odeme_{cari_id}")
            _kgd3.caption("Kar, kaydedince otomatik hesaplanır: Dış Nakliye Tutar − Müşteri Tutar")
            _kg_dn_firma = _kg_dn_firma_elle.strip() or (_kg_dn_firma_sec if _kg_dn_firma_sec != "-- Seç veya elle yaz --" else "")
        else:
            st.caption("💡 Alıcı İl olarak yerel bir il (İstanbul, Bursa, İzmir, Kocaeli, Tekirdağ, Manisa) seçilmedi/seçilirse Dış Nakliye alanları burada görünmez.")

        st.divider()
        if st.button("💾 Kargo Girişini Kaydet", type="primary", key=f"kg_kaydet_btn_{cari_id}", use_container_width=True):
            # Elle yazılan varsa o, yoksa seçilen (seçim "-- Seç veya elle yaz --" ise boş) kullanılır
            _kg_gonderen = _kg_gonderen_elle.strip() or (_kg_gonderen_sec if _kg_gonderen_sec != "-- Seç veya elle yaz --" else "")
            _kg_alici = _kg_alici_elle.strip() or (_kg_alici_sec if _kg_alici_sec != "-- Seç veya elle yaz --" else "")
            _kg_fatura_odeyen = _kg_fatura_elle.strip() or (_kg_fatura_sec if _kg_fatura_sec != "-- Seç veya elle yaz --" else "")
            # ── ZORUNLU ALAN KONTROLÜ ──
            _kg_eksikler = []
            if not _kg_tarih:
                _kg_eksikler.append("Tarih")
            if not _kg_fatura_odeyen:
                _kg_eksikler.append("Fatura Ödeyen")
            if _kg_eksikler:
                st.error(f"⚠️ Zorunlu alan(lar) eksik: {', '.join(_kg_eksikler)}")
            else:
                _kg_gonderen_il_deger = _kg_gonderen_il if _kg_gonderen_il != "-- İl seçilir --" else ""
                _kg_alici_il_deger = _kg_alici_il if _kg_alici_il != "-- İl seçilir --" else ""
                _kg_kar = round(_kg_dn_tutar - _kg_musteri_tutar, 2)
                _kg_liste = list(_kg_kayitlari_yukle(_kg_anahtar))
                # Yazdığın her şey (il isimleri dahil) kaydedilirken otomatik
                # BÜYÜK HARFE çevrilir — Türkçe karaktere duyarlı şekilde.
                _kg_liste.append({
                    "tarih": str(_kg_tarih), "takip_no": _tr_buyuk(_kg_takip), "gonderen_firma": _tr_buyuk(_kg_gonderen),
                    "alici_firma": _tr_buyuk(_kg_alici), "fatura_firma": _tr_buyuk(_kg_fatura_odeyen),
                    "gonderen_il": _tr_buyuk(_kg_gonderen_il_deger), "alici_il": _tr_buyuk(_kg_alici_il_deger),
                    "fatura_odeme_sekli": _kg_fatura_odeme_sekli,
                    "adet": _kg_adet, "tur": _tr_buyuk(_kg_tur), "tutar": _kg_tutar, "kdv": _kg_kdv, "sigorta": _kg_sigorta,
                    "toplam_fatura": _kg_toplam_fatura, "odeme_tur": _kg_odeme_tur, "tahsilat_durumu": _kg_tahsilat,
                    "dis_nakliye_firma": _tr_buyuk(_kg_dn_firma), "dis_nakliye_fatura": _tr_buyuk(_kg_dn_fatura),
                    "dis_nakliye_detay": _tr_buyuk(_kg_dn_detay), "dis_nakliye_tutar": _kg_dn_tutar,
                    "musteri_tutar": _kg_musteri_tutar, "kar": _kg_kar, "dis_nakliye_odeme_durumu": _kg_dn_odeme,
                })
                _kg_kayitlari_kaydet(_kg_anahtar, _kg_liste)
                _kg_kayitlari_yukle.clear()
                # Alıcı Firma + Alıcı İl çiftini kalıcı hafızaya yaz — bir dahaki
                # sefere bu firma yazılınca ili otomatik gelsin.
                if _kg_alici and _kg_alici_il_deger:
                    _kg_hafiza_guncel = dict(_kg_manuel_alici_hafiza)
                    _kg_hafiza_guncel[_tr_buyuk(_kg_alici)] = _tr_buyuk(_kg_alici_il_deger)
                    _kg_manuel_alici_kaydet(_kg_hafiza_guncel)
                    _kg_manuel_alici_yukle.clear()
                st.toast("✅ Kargo girişi kaydedildi", icon="🚚")
                st.rerun()

        _kg_mevcut = _kg_kayitlari_yukle(_kg_anahtar)
        if _kg_mevcut:
            st.divider()
            st.caption(f"📋 Bu müşteri için {len(_kg_mevcut)} kargo kaydı — düzenleyebilir, seçip silebilirsin:")
            import pandas as _kg_pd
            _kg_df = _kg_pd.DataFrame(_kg_mevcut)
            _kg_df = _kg_df.fillna("")  # eski kayıtlarda olmayan alanlar "None" değil boş görünsün
            _kg_df.insert(0, "Seç", False)
            _kg_kolon_isim = {"tarih": "Tarih", "takip_no": "Takip No", "gonderen_firma": "Gönderen",
                               "alici_firma": "Alıcı", "fatura_firma": "Fatura Ödeyen",
                               "gonderen_il": "Gönderen İl", "alici_il": "Alıcı İl",
                               "adet": "Adet", "tur": "Tür", "tutar": "Tutar", "kdv": "KDV", "sigorta": "Sigorta",
                               "toplam_fatura": "Toplam Fatura", "odeme_tur": "Ödeme Türü", "tahsilat_durumu": "Tahsilat",
                               "dis_nakliye_firma": "Dış Nakliye Firma", "dis_nakliye_fatura": "Dış Nakliye Fatura",
                               "dis_nakliye_detay": "Dış Nakliye Detay", "dis_nakliye_tutar": "Dış Nakliye Tutar",
                               "musteri_tutar": "Müşteri Tutar", "kar": "Kar", "dis_nakliye_odeme_durumu": "Dış Nak. Ödeme", "fatura_odeme_sekli": "Fatura Ödeme Şekli"}
            _kg_df = _kg_df.rename(columns=_kg_kolon_isim)
            # Kolon Ayarları'nda ayarlanan (5-50 arası) genişlikleri burada da uygula —
            # yoksa tablo çok geniş açılıp okunması zorlaşıyordu.
            if "_kargo_kol_genislik" not in st.session_state:
                try:
                    _sb_kg_gen0 = get_sb_client()
                    if _sb_kg_gen0:
                        _r_kg_gen0 = _sb_kg_gen0.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kargo_kol_genislik").execute()
                        if _r_kg_gen0.data:
                            import json as _kggenj0
                            st.session_state["_kargo_kol_genislik"] = _kggenj0.loads(_r_kg_gen0.data[0]["deger"])
                except Exception:
                    pass
            _kg_kol_genislik = st.session_state.get("_kargo_kol_genislik", {})
            _kg_col_config = {"Seç": st.column_config.CheckboxColumn("Seç", default=False, width=40)}
            for _kg_kol_ad in _kg_df.columns:
                if _kg_kol_ad == "Seç":
                    continue
                _kg_gen = _kg_kol_genislik.get(_kg_kol_ad, 15)
                _kg_col_config[_kg_kol_ad] = st.column_config.Column(_kg_kol_ad, width=int(_kg_gen) * 8)
            _kg_duzenlenen = st.data_editor(_kg_df, use_container_width=True, hide_index=True,
                                             key=f"kg_editor_{cari_id}",
                                             column_config=_kg_col_config)
            _kgb1, _kgb2 = st.columns(2)
            with _kgb1:
                if st.button("💾 Değişiklikleri Kaydet", key=f"kg_duzenle_kaydet_{cari_id}", use_container_width=True):
                    _kg_ters_isim = {v: k for k, v in _kg_kolon_isim.items()}
                    _kg_yeni_liste = []
                    for _, _r in _kg_duzenlenen.iterrows():
                        if bool(_r.get("Seç")):
                            continue  # işaretli olanlar siliniyor sayılır
                        _kg_kayit = {}
                        for _kol, _val in _r.items():
                            if _kol == "Seç":
                                continue
                            _kg_kayit[_kg_ters_isim.get(_kol, _kol)] = _val
                        _kg_yeni_liste.append(_kg_kayit)
                    _kg_kayitlari_kaydet(_kg_anahtar, _kg_yeni_liste)
                    _kg_kayitlari_yukle.clear()
                    st.toast("✅ Kargo kayıtları güncellendi", icon="🚚")
                    st.rerun()
            with _kgb2:
                _kg_secili_sayi = int(_kg_duzenlenen["Seç"].sum()) if "Seç" in _kg_duzenlenen.columns else 0
                if st.button(f"🗑️ Seçili {_kg_secili_sayi} Kaydı Sil", key=f"kg_sil_btn_{cari_id}", use_container_width=True, disabled=_kg_secili_sayi == 0):
                    _kg_ters_isim2 = {v: k for k, v in _kg_kolon_isim.items()}
                    _kg_kalanlar = []
                    for _, _r in _kg_duzenlenen.iterrows():
                        if bool(_r.get("Seç")):
                            continue
                        _kg_kayit2 = {}
                        for _kol, _val in _r.items():
                            if _kol == "Seç":
                                continue
                            _kg_kayit2[_kg_ters_isim2.get(_kol, _kol)] = _val
                        _kg_kalanlar.append(_kg_kayit2)
                    _kg_kayitlari_kaydet(_kg_anahtar, _kg_kalanlar)
                    _kg_kayitlari_yukle.clear()
                    st.toast(f"🗑️ {_kg_secili_sayi} kayıt silindi", icon="🗑️")
                    st.rerun()
        else:
            st.caption("Bu müşteri için henüz kargo kaydı yok.")
    with _tab_teklif:
        st.caption(f"**{firma_adi}** için özel teklif oluştur — müşteri otomatik seçili şekilde Özel Teklif sayfası açılır.")
        if st.button("⭐ Özel Teklif Sayfasını Aç", key=f"dlg_ozel_teklif_{cari_id}", type="primary", use_container_width=True):
            st.session_state["aktif_tab"] = "ozel_teklif"
            st.session_state["teklif_musteri_onsel"] = firma_adi
            st.rerun()
    with _tab_sozlesme:
        st.caption(f"**{firma_adi}** için sözleşme hazırla — müşteri otomatik seçili şekilde Sözleşmeler sayfası açılır.")
        if st.button("📜 Sözleşmeler Sayfasını Aç", key=f"dlg_sozlesme_{cari_id}", type="primary", use_container_width=True):
            st.session_state["aktif_tab"] = "sozlesme"
            st.session_state["sozlesme_musteri_onsel"] = firma_adi
            st.rerun()
    with _tab_varis:
        st.caption("Karışık/serbest yazabilirsin — aynı Cari Liste'deki il sütunlarıyla birebir aynı şekilde çalışır.")

        def _vd_norm(_s):
            return (str(_s or "").strip().upper().replace("İ", "I").replace("Ş", "S")
                    .replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C"))

        # Global paylaşılan fonksiyon — Cari Liste tablosuyla AYNI önbelleği kullanır.
        _vd_tum_matris = _il_gonderim_matrisi_yukle()
        _vd_matris_firma = _vd_tum_matris.get(str(int(cari_id)), {})
        _vd_dolu = {k: v for k, v in _vd_matris_firma.items() if str(v).strip()}
        if _vd_dolu:
            _vd_dolu_metin = ", ".join(f"{k} ({str(v).replace(chr(10), '/')})" for k, v in _vd_dolu.items())
            st.caption(f"📍 Şu an işaretli iller: {_vd_dolu_metin}")
        else:
            st.caption("📍 Şu an hiç il işaretlenmemiş.")

        _vd_illeri = st.text_input("Varış İlleri", key=f"dlg_varis_illeri_{cari_id}",
                                    placeholder="Örn: istanbul ankara izmir (karışık yazabilirsin)")
        if st.button("💾 İlleri İşaretle", key=f"dlg_varis_illeri_kaydet_{cari_id}", use_container_width=True):
            if _vd_illeri.strip():
                try:
                    import re as _vd_re
                    _vd_tum_matris2 = dict(_il_gonderim_matrisi_yukle())
                    _vd_id_str = str(int(cari_id))
                    _vd_tum_matris2.setdefault(_vd_id_str, {})
                    # Kelime bazlı TAM eşleşme — böylece yazım hatası olan kelimeler
                    # de ayrıca gösterilip fark edilebiliyor (önceki "içeriyor mu"
                    # mantığı yazım hatalarını sessizce yutuyordu).
                    _vd_tokenler = [t for t in _vd_re.split(r"[,;\n]+|\s+", _vd_illeri.strip()) if t]
                    _vd_il_norm_map = {_vd_norm(a): a for a in _IL_SUTUN_LISTESI if a != "Diğer"}
                    _vd_diger_norm_map = {_vd_norm(a): a for a in _IL_DIGER_LISTESI}
                    _vd_eslesen = []
                    _vd_eslesmeyen = []
                    for _tok in _vd_tokenler:
                        _tok_n = _vd_norm(_tok)
                        _bulunan_il = _vd_il_norm_map.get(_tok_n)
                        _bulunan_diger = _vd_diger_norm_map.get(_tok_n)
                        if _bulunan_il:
                            if not str(_vd_tum_matris2[_vd_id_str].get(_bulunan_il, "")).strip():
                                _vd_tum_matris2[_vd_id_str][_bulunan_il] = _bulunan_il.upper()
                            if _bulunan_il not in _vd_eslesen:
                                _vd_eslesen.append(_bulunan_il)
                        elif _bulunan_diger:
                            # Başlığı olmayan il — "Diğer" sütununa ALT ALTA (üst üste
                            # eklenerek, birden fazla girilebilecek şekilde) yazılır.
                            _mevcut_diger = str(_vd_tum_matris2[_vd_id_str].get("Diğer", "") or "").strip()
                            _diger_satirlari = [s.strip() for s in _mevcut_diger.split("\n") if s.strip()]
                            if _bulunan_diger.upper() not in _diger_satirlari:
                                _diger_satirlari.append(_bulunan_diger.upper())
                            _vd_tum_matris2[_vd_id_str]["Diğer"] = "\n".join(_diger_satirlari)
                            if _bulunan_diger not in _vd_eslesen:
                                _vd_eslesen.append(_bulunan_diger)
                        else:
                            _vd_eslesmeyen.append(_tok)
                    _il_gonderim_matrisi_kaydet(_vd_tum_matris2)
                    _il_gonderim_matrisi_yukle.clear()  # Cari Liste tablosu da HEMEN güncel görsün
                    if _vd_eslesen:
                        st.toast(f"✅ İşaretlendi: {', '.join(_vd_eslesen)}", icon="📍")
                    if _vd_eslesmeyen:
                        st.warning(f"⚠️ Tanınmayan kelime(ler) — yazım hatası olabilir: **{', '.join(_vd_eslesmeyen)}**")
                    if not _vd_eslesen and not _vd_eslesmeyen:
                        st.warning("Yazdığın metinde tanınan bir il ismi bulunamadı.")
                    st.rerun()
                except Exception as _vd_hata:
                    st.error(f"Hata: {_vd_hata}")
            else:
                st.warning("Önce bir şey yazın.")

        st.divider()
        _vd_sb = get_sb_client()
        st.caption("Excel'den kopyaladığın gibi SATIR SATIR yapıştır — her satırda **Şehir, Desi Kg, Birim Fiyat** olsun "
                   "(örn. **'AMASYA 227 3.574'**). **TOPLAM = Desi × Birim Fiyat** olarak otomatik hesaplanır, sana bırakmaz. "
                   "100 desi'ye kadar otomatik **KOLİ**, üzeri otomatik **PALET** sayılır.")
        # Sayaçlı (suffix'li) key — "Yenile" butonu, Streamlit'in "widget zaten
        # oluşturulduktan sonra aynı key'e atama yapılamaz" kısıtı yüzünden
        # kutunun KENDİ key'ine doğrudan yazamıyor; bunun yerine sayaç artırılıp
        # bir sonraki çizimde TAMAMEN YENİ (boş) bir kutu oluşturuluyor.
        _fy_kutu_sfx = st.session_state.get(f"_fy_kutu_sfx_{cari_id}", 0)
        _vd_fiyat = st.text_area("Fiyatlandırma", key=f"dlg_fiyat_{cari_id}_{_fy_kutu_sfx}", height=140,
                                  placeholder="AMASYA 227 3.574\nAMASYA 300 3.531\nAMASYA 356 3.487")

        def _fy_norm(_s):
            return (str(_s or "").strip().upper().replace("İ", "I").replace("Ş", "S")
                    .replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C"))

        _fy_sira_liste = [a.upper() for a in _IL_SUTUN_LISTESI[:-1]] + [a.upper() for a in _IL_DIGER_LISTESI]

        def _fy_sira_no(_giris):
            return _fy_sira_liste.index(_giris[0]) if _giris[0] in _fy_sira_liste else 999

        # ── Hizalı TABLO formatı — en uzun değere göre tüm sütunlar aynı hizada,
        # şehir grupları arasında ayraç çizgisi.
        # Girişler: (sehir, tip, desi, birim_fiyat, toplam)
        def _fy_format_tablo(_girisler):
            if not _girisler:
                return ""
            _sehir_w = max(len("V.İLİ"), max(len(g[0]) for g in _girisler))
            _tur_metinleri = [f"- {g[1]}" for g in _girisler]
            _tur_w = max(len("TÜR"), max(len(t) for t in _tur_metinleri))
            _desi_sayi_w = max(len(str(g[2])) for g in _girisler)
            _desi_metinleri = [f"{str(g[2]).rjust(_desi_sayi_w)} DESİ -KG" for g in _girisler]
            _desi_w = max(len("DESİ-KG"), max(len(t) for t in _desi_metinleri))
            _birim_metinleri = [f"{g[3]:.3f}".rstrip("0").rstrip(".") for g in _girisler]
            _birim_sayi_w = max(len(t) for t in _birim_metinleri)
            _birim_metinleri = [f"{t.rjust(_birim_sayi_w)} TL" for t in _birim_metinleri]
            _birim_w = max(len("BİRİM FİYAT"), max(len(t) for t in _birim_metinleri))
            _toplam_metinleri = [f"{g[4]:.2f}" for g in _girisler]
            _toplam_sayi_w = max(len(t) for t in _toplam_metinleri)
            _toplam_metinleri = [f"{t.rjust(_toplam_sayi_w)} TL" for t in _toplam_metinleri]
            _toplam_w = max(len("TOPLAM"), max(len(t) for t in _toplam_metinleri))
            _baslik = (f"{'V.İLİ'.ljust(_sehir_w)}   {'TÜR'.ljust(_tur_w)}   {'DESİ-KG'.ljust(_desi_w)}   "
                       f"{'BİRİM FİYAT'.ljust(_birim_w)}   {'TOPLAM'.ljust(_toplam_w)}")
            _ayrac = "-" * len(_baslik)
            _satirlar = [_baslik, _ayrac]
            _onceki_sehir = None
            for _i, _g in enumerate(_girisler):
                if _onceki_sehir is not None and _g[0] != _onceki_sehir:
                    _satirlar.append(_ayrac)
                _satirlar.append(f"{_g[0].ljust(_sehir_w)}   {_tur_metinleri[_i].ljust(_tur_w)}   {_desi_metinleri[_i].ljust(_desi_w)}   "
                                  f"{_birim_metinleri[_i].ljust(_birim_w)}   {_toplam_metinleri[_i].ljust(_toplam_w)}")
                _onceki_sehir = _g[0]
            return "\n".join(_satirlar)

        _fyb1, _fyb2 = st.columns([3, 1])
        _fy_ayristir_tiklandi = _fyb1.button("🔍 Ayrıştır ve Hazırla", key=f"dlg_fiyat_ayristir_{cari_id}", use_container_width=True)
        if _fyb2.button("🔄 Yenile", key=f"dlg_fiyat_yenile_{cari_id}", use_container_width=True,
                        help="Kutuyu ve önizlemeyi temizler, sıfırdan başlarsın."):
            st.session_state.pop(f"_fy_hazir_{cari_id}", None)
            st.session_state[f"_fy_kutu_sfx_{cari_id}"] = _fy_kutu_sfx + 1
            st.rerun()
        if _fy_ayristir_tiklandi:
            if not _vd_fiyat.strip():
                st.warning("Önce bir şey yazın.")
            else:
                import re as _fy_re
                _fy_tum_iller = _IL_SUTUN_LISTESI[:-1] + _IL_DIGER_LISTESI
                _fy_il_norm_map = {_fy_norm(a): a.upper() for a in _fy_tum_iller}

                # ── SATIR SATIR ayrıştırma — her satırda: Şehir, Desi (tam sayı),
                # Birim Fiyat (ondalıklı sayı, örn. 3.574 ya da 3,574). Ondalık
                # nokta/virgül içeren sayı HER ZAMAN birim fiyat sayılır, tam sayı
                # ise desi sayılır — Excel'den satır satır kopyala-yapıştır içindir.
                _fy_yeni_girisler = []
                _fy_son_sehir = None  # şehir tekrarlanmadan alt alta yazılmışsa hatırla
                for _satir_ham in _vd_fiyat.strip().split("\n"):
                    _s = _satir_ham.strip()
                    if not _s:
                        continue
                    _s_norm = _fy_norm(_s)
                    if "SEHIRICI" in _s_norm:
                        _s_norm = _s_norm.replace("SEHIRICI", "ISTANBUL")
                    # Şehir bul
                    _sehir_bulundu = None
                    for _il_norm_fy, _il_ad_fy in _fy_il_norm_map.items():
                        if _il_norm_fy in _s_norm:
                            _sehir_bulundu = _il_ad_fy
                            break
                    if _sehir_bulundu:
                        _fy_son_sehir = _sehir_bulundu
                    _sehir = _sehir_bulundu or _fy_son_sehir
                    if not _sehir:
                        continue  # bu satırda ve öncesinde hiç şehir yoksa atla (muhtemelen başlık satırı)
                    # Sayıları bul — virgüllü/noktalı olan BİRİM FİYAT, düz tam sayı DESİ
                    _tum_sayi_m = _fy_re.findall(r"\d+[.,]\d+|\d+", _s)
                    if not _tum_sayi_m:
                        continue
                    _ondalikli = [x for x in _tum_sayi_m if "." in x or "," in x]
                    _tamsayi = [x for x in _tum_sayi_m if x not in _ondalikli]
                    if not _ondalikli or not _tamsayi:
                        continue  # hem desi hem birim fiyat yoksa (örn. sadece şehir adı yazılan satır) atla
                    _birim_fiyat = float(_ondalikli[0].replace(",", "."))
                    _desi = int(_tamsayi[0])
                    _toplam = round(_desi * _birim_fiyat, 2)
                    _tip = "KOLİ" if _desi <= 100 else "PALET"
                    _fy_yeni_girisler.append((_sehir, _tip, _desi, _birim_fiyat, _toplam))

                if not _fy_yeni_girisler:
                    st.warning("Yazdığın metinde tanınan bir il ismi + desi + birim fiyat bulunamadı.")
                else:
                    # ÖNEMLİ: eski/önceki kayıtlarla BİRLEŞTİRME yapılmıyor — sadece
                    # o an kutuya yazılan veri kullanılır (kullanıcı isteği: sistem
                    # eskileri "hatırlamasın", her seferinde sadece verileni kullansın).
                    _fy_yeni_girisler.sort(key=lambda g: (_fy_sira_no(g), g[2]))
                    # Kaydetmeden önce DÜZ/HİZALI TABLO olarak göster — kullanıcı
                    # üzerinde elle oynayabilsin, hazır metin dayatılmasın.
                    st.session_state[f"_fy_hazir_{cari_id}"] = _fy_format_tablo(_fy_yeni_girisler)
                    st.rerun()

        _fy_hazir = st.session_state.get(f"_fy_hazir_{cari_id}")
        if _fy_hazir is not None:
            st.markdown("**Hazırlanan tablo — istersen elle düzenle, sonra kaydet:**")
            st.markdown("""<style>
textarea[aria-label="Koli/Palet önizleme"] { font-family: 'Courier New', monospace !important; white-space: pre !important; }
</style>""", unsafe_allow_html=True)
            _fy_son_metin = st.text_area("Koli/Palet önizleme", value=_fy_hazir, height=200,
                                          key=f"_fy_son_metin_{cari_id}", label_visibility="collapsed")
            if st.button("💾 Kaydet", key=f"dlg_fiyat_kaydet_{cari_id}", type="primary", use_container_width=True):
                try:
                    _r_kpo2 = _vd_sb.table("kullanici_tercih").select("deger").eq(
                        "kullanici", "__liste_ui__").eq("anahtar", "_koli_palet_manuel").execute()
                    import json as _kpoj2
                    _kp_map2 = _kpoj2.loads(_r_kpo2.data[0]["deger"]) if _r_kpo2.data else {}
                    _kp_id_str2 = str(int(cari_id))
                    _kp_map2[_kp_id_str2] = _fy_son_metin.strip()
                    _vd_sb.table("kullanici_tercih").delete().eq("kullanici", "__liste_ui__").eq("anahtar", "_koli_palet_manuel").execute()
                    _vd_sb.table("kullanici_tercih").insert({"kullanici": "__liste_ui__", "anahtar": "_koli_palet_manuel",
                                                              "deger": _kpoj2.dumps(_kp_map2, ensure_ascii=False)}).execute()
                    st.session_state["_koli_palet_manuel"] = _kp_map2
                    st.session_state.pop(f"_fy_hazir_{cari_id}", None)
                    st.toast("✅ Koli/Palet güncellendi", icon="📦")
                    st.rerun()
                except Exception as _vd_hata2:
                    st.error(f"Hata: {_vd_hata2}")
    with _tab_duz:
        st.caption(f"**{firma_adi}** — kayıtlı tüm bilgilerle eksiksiz düzenleme ekranı açılır.")
        if st.button("✏️ Cari Kartı Düzenle", key=f"dlg_cari_duzenle_{cari_id}", type="primary", use_container_width=True):
            try:
                _df_duz = get_cari_listesi()
                _satir_duz = _df_duz[_df_duz["id"] == int(cari_id)]
                if _satir_duz.empty:
                    st.error("⚠️ Kayıt bulunamadı.")
                else:
                    kart_row = _satir_duz.iloc[0]
                    d2 = {str(k):(None if str(v) in ["nan","None","NaT"] else v) for k,v in kart_row.items()}
                    for _k in ["firma","yetkili","gsm","sabit","email","adres","il","ilce","durum","temsilci","islem_asamasi","aciklama"]:
                        if _k in d2: d2[_k] = "" if d2[_k] is None else str(d2[_k])
                    if not d2.get("gsm"):
                        d2["gsm"] = str(kart_row.get("telefon") or kart_row.get("tel") or "")
                    if not d2.get("sabit"):
                        d2["sabit"] = str(kart_row.get("sabit_hat") or "")
                    _duzenleme_form_key_temizle(str(cari_id))
                    st.session_state["duzenle_musteri"] = d2
                    st.session_state["aktif_tab"] = "yeni"
                    st.rerun()
            except Exception as _de:
                st.error(f"Hata: {_de}")
    with _tab_sil:
        st.caption(f"**{firma_adi}** kaydını komple sil — tıklayınca anında silinir, onay istenmez.")
        if st.button("🗑️ Cari Komple Sil", key=f"dlg_cari_sil_{cari_id}", type="primary", use_container_width=True):
            try:
                _sb_cs = get_sb_client()
                if _sb_cs:
                    _sb_cs.table("cari_kartlar").update({"silindi": 1}).eq("id", int(cari_id)).execute()
                else:
                    db_update("cari_kartlar", {"silindi": 1}, "id", int(cari_id))
                get_cari_listesi.clear()
                st.cache_data.clear()
                st.session_state.pop("cari_editor", None)
                st.toast(f"🗑️ '{firma_adi}' silindi", icon="🗑️")
                st.rerun()
            except Exception as _cse:
                st.error(f"Silme hatası: {_cse}")

def not_paneli(cari_id, firma_adi="", key_prefix="np"):
    """Her yerde kullanılan ortak not paneli — Model 5: ultra minimal"""
    _sb = get_sb_client()
    _notlar = _notlar_yukle(cari_id)
    _notlar = [n for n in _notlar if not str(n.get("aciklama","") or "").startswith("##YETKILI##")]

    try:
        _notlar = sorted(_notlar, key=lambda x: str(x.get("created_at","") or x.get("tarih","") or x.get("id",0)), reverse=True)
    except: pass

    st.caption(f"{len(_notlar)} not")

    # Model 5 — ultra minimal: tarih | metin | kim | 🗑
    _css5 = """<style>
.np5-satir{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:0.5px solid #e2e8f0;}
.np5-satir:last-child{border-bottom:none;}
.np5-tarih{font-size:11px;color:#64748b;min-width:68px;white-space:nowrap;}
.np5-txt{font-size:13px;color:#0f172a;flex:1;line-height:1.5;}
.np5-kim{font-size:11px;color:#94a3b8;white-space:nowrap;}
</style>"""
    st.markdown(_css5, unsafe_allow_html=True)

    for _nn in _notlar:
        _nid = _nn.get("id","")
        _txt = str(_nn.get("aciklama","") or _nn.get("metin","") or _nn.get("not","") or _nn.get("icerik","") or "")
        _kim = str(_nn.get("olusturan","") or _nn.get("kullanici","") or "")
        _tar = fmt_tarih(str(_nn.get("created_at","") or _nn.get("tarih","") or ""))
        if not _txt: continue

        _col1, _col2, _col3, _col4 = st.columns([0.9, 5, 1, 0.5])
        _col1.markdown(f"<div class='np5-tarih'>{_tar[:8]}</div>", unsafe_allow_html=True)
        _col2.markdown(f"<div class='np5-txt'>{_txt.replace('<','&lt;')}</div>", unsafe_allow_html=True)
        _col3.markdown(f"<div class='np5-kim'>{_kim}</div>", unsafe_allow_html=True)
        if _col4.button("🗑", key=f"{key_prefix}_sil_{_nid}_{cari_id}"):
            try:
                if _sb: _sb.table("cari_aciklamalar").delete().eq("id", int(_nid)).execute()
                try: _notlar_yukle.clear()
                except: pass
                st.rerun()
            except Exception as _se:
                st.error(f"Sil hatası: {_se}")

    # Yeni not — tek satır
    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
    _nc1, _nc2 = st.columns([5, 1])
    _yeni = _nc1.text_input("", key=f"{key_prefix}_yeni_{cari_id}", placeholder="Not yaz...", label_visibility="collapsed")
    if _nc2.button("Kaydet", key=f"{key_prefix}_kaydet_{cari_id}", type="primary", use_container_width=True):
        if _yeni and _yeni.strip():
            try:
                _yazar = st.session_state.get("kullanici","")
                _veri = {"cari_id": int(cari_id), "aciklama": _yeni.strip(), "olusturan": _yazar}
                if _sb: _sb.table("cari_aciklamalar").insert(_veri).execute()
                try: _notlar_yukle.clear()
                except: pass
                st.success("✅ Eklendi!")
                st.rerun()
            except Exception as _ne:
                st.error(f"Hata: {_ne}")
        else:
            st.warning("Not boş!")



_TAB_LISTESI_DEFAULT = ["yeni", "liste", "dis_nakliye_toplu", "randevu", "ozel_teklif", "sozlesme", "kayitli_teklifler", "rapor", "excel", "kullanici", "admin_rapor", "harita", "mukerrer", "kargolar"]
_TAB_ETIKETLER = {
    "yeni": "➕ Yeni Kart Ekle",
    "liste": "📋 Cari Liste / Düzenle",
    "rapor": "📊 Raporlar",
    "ozel_teklif": "⭐ Özel Teklif",
    "kayitli_teklifler": "📋 Kayıtlı Teklifler",
    "sozlesme": "📜 Sözleşmeler",
    "excel": "📥 Excel Aktar",
    "dis_nakliye": "🚚 Dış Nakliye",
    "dis_nakliye_toplu": "🚚 Dış Nakliyeler Listesi",
    
    "randevu": "📅 Randevular",
    "kullanici": "👥 Kullanıcı Yönetimi",
    "mesajlar": "💬 Mesajlar",
    "admin_rapor": "📊 Rapor Tasarla",
    "harita": "🗺️ Müşteri Haritası",
    "kargolar": "🚚 Kargolar",
    "mukerrer": "🔍 Mükerrer Bul",
    
}

def get_menu_tercihi(kullanici):
    def _temizle(liste):
        goruldu = []
        for t in liste:
            if t not in goruldu:
                goruldu.append(t)
        return goruldu

    try:
        sb_m = get_sb_client()
        if sb_m:
            res = sb_m.table("kullanici_tercih").select("deger").eq("kullanici", kullanici).eq("anahtar","menu_sirasi").execute()
            if res.data:
                kayitli = json.loads(res.data[0]["deger"])
                tam_liste = _TAB_LISTESI_DEFAULT.copy()
                if st.session_state.get("rol") == "admin":
                    tam_liste += ["kullanici","admin_rapor"]
                tam_liste = _temizle(tam_liste)
                # Eksik olanları tam_liste'deki sıraya göre doğru pozisyona ekle
                for i, t in enumerate(tam_liste):
                    if t not in kayitli:
                        # Önceki elemanın pozisyonundan sonraya ekle
                        onceki = next((x for x in reversed(tam_liste[:i]) if x in kayitli), None)
                        if onceki:
                            pos = kayitli.index(onceki) + 1
                        else:
                            pos = 0
                        kayitli.insert(pos, t)
                kayitli = [t for t in kayitli if t in tam_liste]
                return _temizle(kayitli)
        else:
            conn = get_conn()
            conn.execute("CREATE TABLE IF NOT EXISTS kullanici_tercih (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, anahtar TEXT, deger TEXT, UNIQUE(kullanici, anahtar))")
            conn.commit()
            row = conn.execute("SELECT deger FROM kullanici_tercih WHERE kullanici=? AND anahtar='menu_sirasi'", (kullanici,)).fetchone()
            conn.close()
            if row:
                kayitli = json.loads(row[0])
                tam_liste = _TAB_LISTESI_DEFAULT.copy()
                if st.session_state.get("rol") == "admin":
                    tam_liste += ["kullanici","admin_rapor"]
                tam_liste = _temizle(tam_liste)
                for i, t in enumerate(tam_liste):
                    if t not in kayitli:
                        onceki = next((x for x in reversed(tam_liste[:i]) if x in kayitli), None)
                        if onceki:
                            pos = kayitli.index(onceki) + 1
                        else:
                            pos = 0
                        kayitli.insert(pos, t)
                kayitli = [t for t in kayitli if t in tam_liste]
                return _temizle(kayitli)
    except: pass
    tam_liste = _TAB_LISTESI_DEFAULT.copy()
    if st.session_state.get("rol") == "admin":
        tam_liste += ["kullanici","admin_rapor"]
    return _temizle(tam_liste)

def save_menu_tercihi(kullanici, sira):
    try:
        sb_m = get_sb_client()
        if sb_m:
            sb_m.table("kullanici_tercih").upsert({
                "kullanici": kullanici,
                "anahtar": "menu_sirasi",
                "deger": json.dumps(sira)
            }, on_conflict="kullanici,anahtar").execute()
        else:
            conn = get_conn()
            conn.execute("CREATE TABLE IF NOT EXISTS kullanici_tercih (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, anahtar TEXT, deger TEXT, UNIQUE(kullanici, anahtar))")
            conn.execute("INSERT OR REPLACE INTO kullanici_tercih (kullanici, anahtar, deger) VALUES (?,?,?)",
                (kullanici, "menu_sirasi", json.dumps(sira)))
            conn.commit(); conn.close()
    except: pass

# ── SIDEBAR ───────────────────────────────────────────────────────────────────

# ── VERSİYON KONTROL SİSTEMİ ─────────────────────────────────────────────────
GUNCEL_SURUM = "v6.7"  # Bu kodun versiyonu — her güncellemede artır

def _surum_kontrol():
    """Kullanıcı stable sürümde mi kontrol et"""
    try:
        _sb_s = get_sb_client()
        if not _sb_s: return True  # Bağlantı yoksa geç
        _res = _sb_s.table("sistem_ayarlari").select("deger").eq("anahtar","stable_surum").execute()
        if _res.data:
            return _res.data[0]["deger"] == GUNCEL_SURUM
        return True
    except:
        return True  # Hata olursa engelleme

# Giriş kontrolü
if not st.session_state.get("giris", False):
    # ── ÖNCE localStorage'dan otomatik giriş dene ────────────────────────────
    _auto_giris_qp = st.query_params.get("_ag", "")
    if _auto_giris_qp:
        try:
            _ag_veri = json.loads(_auto_giris_qp)
            _ag_kul  = _ag_veri.get("kullanici","")
            _ag_sif  = _ag_veri.get("sifre","")
            _ag_mob  = _ag_veri.get("mobil", False)
            if _ag_kul and _ag_sif:
                _ag_row = None
                try:
                    from supabase import create_client as _agsc
                    _ag_sb = _agsc(st.secrets.get("SUPABASE_URL",""), st.secrets.get("SUPABASE_KEY",""))
                    _ag_res = _ag_sb.table("kullanicilar").select("*").eq("kullanici_adi", _ag_kul).eq("sifre", _ag_sif).execute()
                    if _ag_res.data: _ag_row = _ag_res.data[0]
                except: pass
                if _ag_row:
                    _ag_rol = str(_ag_row.get("rol","") or "kullanici")
                    try:
                        import json as _agj
                        _ag_yetki_val = str(_ag_row.get("yetkiler","tam") or "tam")
                        _ag_yetki = "tam" if _ag_yetki_val == "tam" else _agj.loads(_ag_yetki_val)
                    except: _ag_yetki = "tam"
                    st.session_state.update({
                        "giris": True, "kullanici": _ag_kul, "kullanici_ad": _ag_kul,
                        "rol": _ag_rol, "aktif_tab": "liste",
                        "_yetki_listesi": _ag_yetki,
                        "_mobil_mod": _ag_mob, "_ekran_kontrol": True,
                        "giris_cihaz": "mobil" if _ag_mob else "masaustu",
                    })
                    st.query_params.clear()
                    st.rerun()
        except: pass
        st.query_params.clear()

    # localStorage'dan oku ve query param ile gönder
    if not st.session_state.get("giris", False) and not st.session_state.get("_ls_denendi", False):
        st.session_state["_ls_denendi"] = True
        st.markdown("""<script>
(function(){
  try{
    var v = localStorage.getItem('mwcrm_oturum');
    if(v){
      var url = new URL(window.parent.location.href);
      url.searchParams.set('_ag', v);
      window.parent.location.replace(url.toString());
    }
  }catch(e){}
})();
</script>""", unsafe_allow_html=True)

    giris_ekrani()
    st.stop()




# ── SİSTEM AÇIK KALSIN — timeout yok ──────────────────────────────────────────
# Streamlit oturumu kullanıcı kapatana kadar aktif kalır; ekstra keep-alive gerekmez.
# st.session_state["giris"] = True zaten set, yeniden giriş istenmez.

# ── CARİ LİSTE KOLON DURUM BAŞLAT ────────────────────────────────────────────
if "_cl_kolon_genislik" not in st.session_state:
    st.session_state["_cl_kolon_genislik"] = {}
if "_cl_kolon_sira" not in st.session_state:
    st.session_state["_cl_kolon_sira"] = []

# Versiyon kontrolü — sadece admin olmayanlara
if st.session_state.get("rol") != "admin":
    try:
        _sb_s = get_sb_client()
        if _sb_s:
            _res = _sb_s.table("sistem_ayarlari").select("deger").eq("anahtar","stable_surum").execute()
            if _res.data:
                _stable = _res.data[0]["deger"]
                if _stable != GUNCEL_SURUM:
                    st.markdown("""
                    <div style='text-align:center;padding:60px 20px'>
                    <div style='font-size:3rem'>⏳</div>
                    <h2 style='color:#ff9800'>Güncelleme Hazırlanıyor</h2>
                    <p style='color:#888;font-size:1rem'>Sistem yeni sürüme hazırlanıyor.<br>
                    Yönetici onayı bekleniyor, kısa süre içinde devam edebilirsiniz.</p>
                    <p style='color:#666;font-size:0.85rem'>Verileriniz güvende — hiçbir şey kaybolmadı.</p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.stop()
    except:
        pass  # Bağlantı hatası olursa engelleme yapma


with st.sidebar:
    st.markdown("""
<style>
section[data-testid="stSidebar"] { 
    padding-top: 0.5rem !important; 
    transform: translateX(0px) !important;
    overflow-y: auto !important;
    height: 100vh !important;
}
section[data-testid="stSidebar"] > div:first-child {
    overflow-y: auto !important;
    height: 100% !important;
}
section[data-testid="stSidebar"] > div > div {
    overflow-y: auto !important;
}
/* Gereksiz boşlukları kaldır */
div[data-testid="stVerticalBlock"] > div:empty { display: none !important; }
div[data-testid="stVerticalBlock"] { gap: 0.3rem !important; }
hr { margin: 0.3rem 0 !important; }
div[data-testid="stHorizontalBlock"] { gap: 0.3rem !important; }
/* Scroll barlar: sidebar/menü gibi dar alanlarda gizli kalsın (eski görünüm),
   ama ana içerik alanı ve tablolarda mausla sürüklenebilsin diye görünür yapıldı.
   Not: st.data_editor/st.dataframe içeride kaydırma kutusunu birkaç seviye iç
   içe div ile sarabiliyor, bu yüzden "*" ile TÜM alt elemanlar hedeflendi. */
* { scrollbar-width: none !important; -ms-overflow-style: none !important; }
*::-webkit-scrollbar { display: none !important; width: 0 !important; height: 0 !important; }
section[data-testid="stMain"],
section[data-testid="stMain"] *,
div[data-testid="stDataEditor"],
div[data-testid="stDataEditor"] *,
div[data-testid="stDataFrame"],
div[data-testid="stDataFrame"] *,
div[data-testid="stElementContainer"]:has(div[data-testid="stDataEditor"]),
div[data-testid="stElementContainer"]:has(div[data-testid="stDataEditor"]) *,
div[data-baseweb="popover"],
div[data-baseweb="popover"] *,
div[data-baseweb="menu"],
div[data-baseweb="menu"] *,
ul[data-baseweb="menu"],
ul[data-baseweb="menu"] *,
[role="listbox"],
[role="listbox"] * {
    scrollbar-width: thin !important;
    -ms-overflow-style: auto !important;
}
section[data-testid="stMain"]::-webkit-scrollbar,
section[data-testid="stMain"] *::-webkit-scrollbar,
div[data-testid="stDataEditor"]::-webkit-scrollbar,
div[data-testid="stDataEditor"] *::-webkit-scrollbar,
div[data-testid="stDataFrame"]::-webkit-scrollbar,
div[data-testid="stDataFrame"] *::-webkit-scrollbar,
div[data-baseweb="popover"]::-webkit-scrollbar,
div[data-baseweb="popover"] *::-webkit-scrollbar,
div[data-baseweb="menu"]::-webkit-scrollbar,
div[data-baseweb="menu"] *::-webkit-scrollbar,
ul[data-baseweb="menu"]::-webkit-scrollbar,
ul[data-baseweb="menu"] *::-webkit-scrollbar,
[role="listbox"]::-webkit-scrollbar,
[role="listbox"] *::-webkit-scrollbar {
    display: block !important; width: 10px !important; height: 10px !important;
}
section[data-testid="stMain"]::-webkit-scrollbar-thumb,
section[data-testid="stMain"] *::-webkit-scrollbar-thumb,
div[data-testid="stDataEditor"]::-webkit-scrollbar-thumb,
div[data-testid="stDataEditor"] *::-webkit-scrollbar-thumb,
div[data-testid="stDataFrame"]::-webkit-scrollbar-thumb,
div[data-testid="stDataFrame"] *::-webkit-scrollbar-thumb,
div[data-baseweb="popover"]::-webkit-scrollbar-thumb,
div[data-baseweb="popover"] *::-webkit-scrollbar-thumb,
div[data-baseweb="menu"]::-webkit-scrollbar-thumb,
div[data-baseweb="menu"] *::-webkit-scrollbar-thumb,
ul[data-baseweb="menu"]::-webkit-scrollbar-thumb,
ul[data-baseweb="menu"] *::-webkit-scrollbar-thumb,
[role="listbox"]::-webkit-scrollbar-thumb,
[role="listbox"] *::-webkit-scrollbar-thumb {
    background: #94a3b8 !important; border-radius: 6px !important;
}
section[data-testid="stMain"]::-webkit-scrollbar-track,
div[data-testid="stDataEditor"]::-webkit-scrollbar-track,
div[data-testid="stDataFrame"]::-webkit-scrollbar-track,
div[data-baseweb="popover"]::-webkit-scrollbar-track,
div[data-baseweb="menu"]::-webkit-scrollbar-track,
ul[data-baseweb="menu"]::-webkit-scrollbar-track,
[role="listbox"]::-webkit-scrollbar-track {
    background: #f1f5f9 !important;
}
button[data-testid="collapsedControl"] { display: none !important; }
section[data-testid="stSidebar"] .stButton>button {
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 10px 14px !important;
    font-size: 13px !important;
    border-radius: 6px !important;
    margin: 0 !important;
    border: 1.5px solid #cbd5e1 !important;
    background: #ffffff !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06) !important;
    width: 100% !important;
}
section[data-testid="stSidebar"] .stButton>button p {
    text-align: left !important;
    color: inherit !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}
section[data-testid="stSidebar"] .stButton>button:hover {
    background: #f1f5f9 !important;
    border-color: #94a3b8 !important;
}
section[data-testid="stSidebar"] .stButton>button[kind="primary"] {
    background: #dbeafe !important;
    border-color: #3b82f6 !important;
    box-shadow: 0 1px 3px rgba(59,130,246,0.2) !important;
}
section[data-testid="stSidebar"] .stButton>button[kind="primary"] p {
    color: #1d4ed8 !important;
    font-weight: 600 !important;
}
section[data-testid="stSidebar"] .stButton { margin: 0 !important; padding: 0 !important; }
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div { gap: 4px !important; }
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] { gap: 4px !important; }
section[data-testid="stSidebar"] hr { margin: 8px 0 !important; }
section[data-testid="stSidebar"] div[data-testid="stExpander"] { margin: 0 !important; }
section[data-testid="stSidebar"] div[data-testid="stExpander"] > div { padding: 0 !important; }
#MainMenu { visibility: hidden !important; }
.main .block-container {
    padding-top: 0.3rem !important;
    padding-bottom: 0.3rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}
div[data-testid="stVerticalBlock"] > div { gap: 0.3rem !important; }
footer { visibility: hidden !important; }
header { visibility: hidden !important; }
div[data-testid="stToolbar"] { display: none !important; }
div[data-testid="stDecoration"] { display: none !important; }
div[data-testid="stStatusWidget"] { display: none !important; }
button[data-testid="manage-app-button"] { display: none !important; }
.stDeployButton { display: none !important; }
[data-testid="stBottom"] { display: none !important; }
.styles_viewerBadge__CvC9N { display: none !important; }
#stDecoration { display: none !important; }
</style>
""", unsafe_allow_html=True)

    st.markdown(
        "<div style='display:flex;align-items:center;gap:11px;font-size:17px;font-weight:700;color:#1a4f9e;"
        "padding:16px 10px 16px;letter-spacing:0.4px;border-bottom:2px solid #2568c7;margin-bottom:10px;'>"
        "<svg width='30' height='30' viewBox='0 0 100 100' style='flex:none'>"
        "<rect width='100' height='100' rx='22' fill='#1D4ED8'/>"
        "<rect x='20' y='20' width='26' height='26' rx='6' fill='#97AEED'/>"
        "<rect x='54' y='20' width='26' height='26' rx='6' fill='#97AEED'/>"
        "<rect x='20' y='54' width='26' height='26' rx='6' fill='#97AEED'/>"
        "<rect x='54' y='54' width='26' height='26' rx='6' fill='#97AEED'/>"
        "</svg>"
        "MWCRMPRO</div>",
        unsafe_allow_html=True
    )

    # ── MENÜ LİSTESİ ──────────────────────────────────────────────────────────
    _sb_liste = get_menu_tercihi(st.session_state.get("kullanici",""))
    if st.session_state.get("rol") == "admin":
        for _t in ["kullanici","admin_rapor"]:
            if _t not in _sb_liste:
                _sb_liste.append(_t)
    if st.session_state.get("rol") != "admin":
        try:
            import json as _yj
            _yk = f"yetki_{st.session_state['kullanici']}"
            if _yk not in st.session_state:
                _dfk = db_read("kullanicilar", extra_sql="")
                if not _dfk.empty and "yetkiler" in _dfk.columns:
                    _kr = _dfk[_dfk["kullanici_adi"] == st.session_state["kullanici"]]
                    if not _kr.empty:
                        st.session_state[_yk] = str(_kr.iloc[0].get("yetkiler","tam") or "tam")
            _yv = st.session_state.get(_yk, "tam")
            if _yv != "tam":
                _sb_liste = [t for t in _sb_liste if t in _yj.loads(_yv)]
        except: pass

    _sb_liste_temiz = []
    for _t in _sb_liste:
        if _t not in _sb_liste_temiz:
            _sb_liste_temiz.append(_t)
    _sb_liste = _sb_liste_temiz

    # ── ADMIN OLMAYAN KULLANICILARDAN GİZLENECEK SAYFALAR ─────────────────────
    _SADECE_ADMIN = {"admin_rapor", "kullanici", "excel"}
    if st.session_state.get("rol") != "admin":
        _sb_liste = [t for t in _sb_liste if t not in _SADECE_ADMIN]

    _TAB_RENKLER = {
        "yeni":        "#16a34a",
        "liste":       "#0369a1",
        "randevu":     "#1d4ed8",
        "ozel_teklif": "#7c3aed",
        "sozlesme":    "#9333ea",
        "rapor":       "#6d28d9",
        "excel":       "#047857",
        "kullanici":   "#be123c",
        "admin_rapor": "#0c4a6e",
        "mesajlar":    "#0891b2",
    }

    # Gizli menü öğelerini yükle
    if "_gizli_menu_list" not in st.session_state:
        try:
            _sb_gml = get_sb_client()
            if _sb_gml:
                import json as _gmlj
                _r_gml = _sb_gml.table("kullanici_tercih").select("deger").eq("kullanici", st.session_state["kullanici"]).eq("anahtar","_gizli_menu").execute()
                st.session_state["_gizli_menu_list"] = _gmlj.loads(_r_gml.data[0]["deger"]) if _r_gml.data else []
        except: st.session_state["_gizli_menu_list"] = []

    _gizli_menu_render = st.session_state.get("_gizli_menu_list", [])
    _sb_liste = [t for t in _sb_liste if t not in _gizli_menu_render]

    # Yetki bazlı menü gizleme — admin olmayan kullanıcılardan bazı menüler gizlenir
    _menu_rol = st.session_state.get("rol", "")
    # Sadece admin görebilecek menüler
    _sadece_admin_menuler = []
    if _menu_rol != "admin":
        _sb_liste = [t for t in _sb_liste if t not in _sadece_admin_menuler]

    # ── MENÜ GÖRÜNÜMÜ: Gruplu (akordeon) ────────────────────────────────────────
    st.markdown("""<style>
    section[data-testid='stSidebar'] { background-color:#ffffff; }
    section[data-testid='stSidebar'] hr { border-color:#eceae2; }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary'] {
        background:transparent; border:none; border-radius:8px;
        justify-content:flex-start !important; text-align:left !important;
        transition:background-color .15s ease, color .15s ease;
    }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary'] div[data-testid='stMarkdownContainer'] { width:100%; text-align:left !important; }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary'] p {
        color:#2c2c2a !important; font-weight:500 !important; text-align:left !important;
        width:100%; transition:color .15s ease;
    }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary']:hover { background:#f6f8fb; }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary']:hover p { color:#1a4f9e !important; }
    section[data-testid='stSidebar'] .stButton>button[kind='primary'] {
        background:#eef4fc; border:none; border-left:3px solid #2568c7; border-radius:8px;
        justify-content:flex-start !important; text-align:left !important;
        transition:background-color .15s ease;
    }
    section[data-testid='stSidebar'] .stButton>button[kind='primary'] div[data-testid='stMarkdownContainer'] { width:100%; text-align:left !important; }
    section[data-testid='stSidebar'] .stButton>button[kind='primary'] p {
        color:#1a4f9e !important; font-weight:600 !important; text-align:left !important; width:100%;
    }
    section[data-testid='stSidebar'] label p, section[data-testid='stSidebar'] .stMarkdown p { color:#3d3d3a; }
    section[data-testid='stSidebar'] summary p, section[data-testid='stSidebar'] summary span { color:#3d3d3a !important; }
    </style>""", unsafe_allow_html=True)

    _MENU_GRUPLARI = [
        ("🧾 Cari işlemleri",    ["yeni", "liste", "dis_nakliye_toplu", "excel", "mukerrer"]),
        ("📅 Randevu ve teklif", ["randevu", "ozel_teklif", "sozlesme", "kayitli_teklifler"]),
        ("🚚 Saha",              ["harita"]),
        ("📦 Kargo Takip",       ["kargolar"]),
        ("⚙️ Yönetim",          ["kullanici"]),
        ("📊 Raporlar",          ["admin_rapor", "rapor"]),
    ]

    if "_acik_grup" not in st.session_state:
        _varsayilan_acik = None
        for _g_ad, _g_keys in _MENU_GRUPLARI:
            if st.session_state["aktif_tab"] in _g_keys:
                _varsayilan_acik = _g_ad
                break
        st.session_state["_acik_grup"] = _varsayilan_acik or (_MENU_GRUPLARI[0][0] if _MENU_GRUPLARI else None)

    _gruplanan = set()
    for _g_ad, _g_keys in _MENU_GRUPLARI:
        _g_items = [t for t in _sb_liste if t in _g_keys]
        if not _g_items:
            continue
        _gruplanan.update(_g_items)

        if len(_g_items) == 1:
            # Tek sayfalı grup — kendisi tek olduğu gibi, direkt tıklanabilir tek buton
            _tek_key = _g_items[0]
            _etiket = _TAB_ETIKETLER.get(_tek_key, _tek_key)
            _aktif_mi = st.session_state["aktif_tab"] == _tek_key
            if st.button(_etiket, use_container_width=True,
                         type="primary" if _aktif_mi else "secondary",
                         key=f"sb_tek_{_tek_key}"):
                st.session_state["aktif_tab"] = _tek_key
                st.rerun()

            # ── BÖLGE — "Müşteri Haritası"nın hemen altında ──────────────────────
            # Cari Liste'nin kendi verisinden BAĞIMSIZ, hafif/önbellekli bir sorgu.
            # Tıklanınca/seçilince hem Cari Liste'ye geçer hem de bölgeye göre filtreler.
            # NOT: CSS ile buton görünümünü küçültme denemeleri güvenilir çalışmadı
            # (Streamlit sürümüyle DOM uyuşmazlığı). Bunun yerine: en çok kullanılan
            # birkaç bölge NATIVE buton, geri kalan tüm iller ise NATIVE bir
            # selectbox (açılır liste) içinde — ikisi de hiçbir özel CSS'e ihtiyaç
            # duymadan garanti okunur ve garanti tıklanır/seçilir.
            if _tek_key == "harita":
                try:
                    _bl_df_nav = _atama_filtresi_uygula(get_cari_listesi())
                except Exception:
                    _bl_df_nav = pd.DataFrame()
                if not _bl_df_nav.empty and "il" in _bl_df_nav.columns:
                    _bl_ilce_kol_nav = "ilce" if "ilce" in _bl_df_nav.columns else None
                    _bl_bolge_ham_nav = _bl_df_nav.apply(
                        lambda r: il_ilce_bolge_bul(r.get("il", ""), r.get(_bl_ilce_kol_nav, "") if _bl_ilce_kol_nav else ""), axis=1)
                    _bl_bolge_nav = _bl_bolge_ham_nav.fillna("Havuz (Bölgesiz)")
                    _bl_sayim_nav = _bl_bolge_nav.value_counts()
                    _bl_kisa_ad_nav = {"İstanbul Anadolu": "İst. Anadolu", "İstanbul Avrupa": "İst. Avrupa"}

                    def _bl_uygula(_bl_ad_sec):
                        """Seçilen bölgeye göre Cari Liste filtresini ayarlar ve oraya geçer."""
                        try:
                            if _bl_ad_sec == "Havuz (Bölgesiz)":
                                st.session_state["_bl_havuz_filtre"] = True
                                for _fk_nav in ["_cl_fil_il_multi", "_cl_fil_ilce_multi", "_bl_ilce_filtre"]:
                                    st.session_state.pop(_fk_nav, None)
                                st.session_state.pop("_bl_ilce_filtre_ad", None)
                            else:
                                st.session_state.pop("_bl_havuz_filtre", None)
                                _bl_chip_df = _bl_df_nav[_bl_bolge_nav == _bl_ad_sec]
                                _bl_il_listesi = sorted(_bl_chip_df["il"].dropna().astype(str).unique().tolist()) if "il" in _bl_chip_df.columns else []
                                st.session_state["_cl_fil_il_multi"] = _bl_il_listesi
                                st.session_state.pop("_cl_fil_ilce_multi", None)
                                if _bl_ilce_kol_nav and _bl_ad_sec in ("İstanbul Anadolu", "İstanbul Avrupa"):
                                    st.session_state["_bl_ilce_filtre"] = sorted(
                                        _bl_chip_df["ilce"].dropna().astype(str).unique().tolist())
                                    st.session_state["_bl_ilce_filtre_ad"] = _bl_ad_sec
                                else:
                                    st.session_state.pop("_bl_ilce_filtre", None)
                                    st.session_state.pop("_bl_ilce_filtre_ad", None)
                            st.session_state["_toplam_aktif"] = False
                            st.session_state["_asamasiz_aktif"] = False
                            st.session_state["_mesaj_gercek_aktif"] = False
                            for _fk_stale2 in ["_cl_fil_asama1", "_cl_fil_asama2", "_cl_fil_asama3", "_cl_fil_sonuc"]:
                                st.session_state.pop(_fk_stale2, None)
                            st.session_state["aktif_tab"] = "liste"
                        except Exception as _bl_hata:
                            st.error(f"⚠️ Bölge filtre hatası: {_bl_hata}")
                        st.rerun()

                    with st.expander(f"📍 Bölge  ·  {len(_bl_sayim_nav)} bölge", expanded=False):
                        # Sık kullanılan bölgeler — doğrudan buton
                        _bl_ana_bolgeler = ["İstanbul Anadolu", "İstanbul Avrupa", "İzmir", "Bursa",
                                            "Manisa", "Tekirdağ", "Kocaeli"]
                        for _bl_ana in _bl_ana_bolgeler:
                            if _bl_ana in _bl_sayim_nav.index and _bl_sayim_nav[_bl_ana] > 0:
                                _bl_kisa = _bl_kisa_ad_nav.get(_bl_ana, _bl_ana)
                                if st.button(f"{_bl_kisa}  ({_bl_sayim_nav[_bl_ana]})", key=f"nav_bolge_ana_{_bl_ana}", use_container_width=True):
                                    _bl_uygula(_bl_ana)

                        # Havuz (bölgesiz) — varsa ayrıca göster
                        if "Havuz (Bölgesiz)" in _bl_sayim_nav.index and _bl_sayim_nav["Havuz (Bölgesiz)"] > 0:
                            if st.button(f"📦 Havuz (Bölgesiz)  ({_bl_sayim_nav['Havuz (Bölgesiz)']})", key="nav_bolge_havuz", use_container_width=True):
                                _bl_uygula("Havuz (Bölgesiz)")

                        # Geri kalan TÜM iller — açılır liste (selectbox), okunur/aranabilir
                        _bl_diger = sorted([b for b in _bl_sayim_nav.index if b not in _bl_ana_bolgeler and b != "Havuz (Bölgesiz)" and _bl_sayim_nav[b] > 0])
                        if _bl_diger:
                            st.caption("Diğer iller")
                            _bl_diger_opts = ["-- İl seç --"] + [f"{b}  ({_bl_sayim_nav[b]})" for b in _bl_diger]
                            # ÖNEMLİ: selectbox butonun aksine değerini KALICI tutar — sıfırlamazsak
                            # her rerun'da aynı seçim tekrar tekrar tetiklenir. Streamlit, widget'ın
                            # KENDİ key'ine sonradan atama yapmaya izin vermiyor (hata verir) — bu yüzden
                            # sabit bir key yerine SAYAÇLI (suffix'li) key kullanılıyor: seçim yapılınca
                            # sayaç arttırılıp bir sonraki çizimde TAMAMEN YENİ (temiz/varsayılan) bir
                            # widget oluşuyor — Aşama/Durum filtrelerindeki ile aynı, kanıtlanmış yöntem.
                            _bl_sfx = st.session_state.get("_bl_diger_sfx", 0)
                            _bl_diger_sec = st.selectbox("Diğer iller", _bl_diger_opts, key=f"nav_bolge_diger_sec_{_bl_sfx}", label_visibility="collapsed")
                            if _bl_diger_sec != "-- İl seç --":
                                _bl_sec_ad = _bl_diger_sec.rsplit("  (", 1)[0]
                                st.session_state["_bl_diger_sfx"] = _bl_sfx + 1
                                _bl_uygula(_bl_sec_ad)
            continue

        _acik_mi = st.session_state["_acik_grup"] == _g_ad
        _ok = "▾" if _acik_mi else "▸"
        if st.button(f"{_g_ad}   {_ok}", use_container_width=True,
                     type="primary" if _acik_mi else "secondary",
                     key=f"grphdr_{_g_ad}"):
            st.session_state["_acik_grup"] = None if _acik_mi else _g_ad
            st.rerun()
        if _acik_mi:
            for _tab_key in _g_items:
                _etiket = _TAB_ETIKETLER.get(_tab_key, _tab_key)
                _aktif_mi = st.session_state["aktif_tab"] == _tab_key
                _c1, _c2 = st.columns([1, 6])
                with _c2:
                    if st.button(_etiket, use_container_width=True,
                                 type="primary" if _aktif_mi else "secondary",
                                 key=f"sb_{_g_ad}_{_tab_key}"):
                        st.session_state["aktif_tab"] = _tab_key
                        st.rerun()

    _kalanlar = [t for t in _sb_liste if t not in _gruplanan]
    if _kalanlar:
        _acik_mi = st.session_state["_acik_grup"] == "DİĞER"
        _ok = "▾" if _acik_mi else "▸"
        if st.button(f"Diğer   {_ok}", use_container_width=True,
                     type="primary" if _acik_mi else "secondary",
                     key="grphdr_DIGER"):
            st.session_state["_acik_grup"] = None if _acik_mi else "DİĞER"
            st.rerun()
        if _acik_mi:
            for _tab_key in _kalanlar:
                _etiket = _TAB_ETIKETLER.get(_tab_key, _tab_key)
                _aktif_mi = st.session_state["aktif_tab"] == _tab_key
                _c1, _c2 = st.columns([1, 6])
                with _c2:
                    if st.button(_etiket, use_container_width=True,
                                 type="primary" if _aktif_mi else "secondary",
                                 key=f"sb_diger_{_tab_key}"):
                        st.session_state["aktif_tab"] = _tab_key
                        st.rerun()

    # ── ALT BÖLÜM ─────────────────────────────────────────────────────────────
    st.divider()

    with st.expander("🖥️ Görünüm"):
        _gv_su_an_mobil = st.session_state.get("_mobil_mod", False)
        st.caption(f"Şu an: {'📱 Telefon/Tablet görünümü' if _gv_su_an_mobil else '🖥️ Masaüstü görünümü'}")
        _gv_yeni = st.toggle("Masaüstü görünümünü kullan (telefonda bile)", value=not _gv_su_an_mobil, key="gv_masaustu_toggle")
        if _gv_yeni == _gv_su_an_mobil:  # yani tersine dönmüş, değişiklik istendi
            st.session_state["_mobil_mod"] = not _gv_yeni
            # localStorage'daki kayıtlı cihaz tercihini de güncelle — bir dahaki
            # otomatik girişte eski (yanlış) tercih geri yüklenmesin.
            st.markdown(f"""<script>
try{{
  var _eski = localStorage.getItem('mwcrm_oturum');
  if(_eski){{
    var _o = JSON.parse(_eski);
    _o.mobil = {str(not _gv_yeni).lower()};
    localStorage.setItem('mwcrm_oturum', JSON.stringify(_o));
  }}
}}catch(e){{}}
</script>""", unsafe_allow_html=True)
            st.rerun()

    with st.expander("❓ Yardım"):
        st.markdown("📞 [5400344228](tel:05400344228)")
        st.button("📱 WhatsApp", use_container_width=True, disabled=True, help="Geçici olarak devre dışı")
        talep = st.text_area("Talep:", height=60, key="sidebar_talep")
        if st.button("📨 Gönder", key="sidebar_wa_btn"):
            if talep.strip():
                st.caption("👉 Gönder (geçici devre dışı)")

    if st.session_state.get("rol") == "admin":
        with st.expander("🎛️ Menü Sırası"):
            mevcut_sira_m = get_menu_tercihi(st.session_state["kullanici"])
            _gizli_menu = st.session_state.get("_gizli_menu_list", [])
            _goster = []
            for _t in mevcut_sira_m:
                if _t not in _goster:
                    _goster.append(_t)
            mevcut_sira_m = _goster
            for idx_m, tab_key in enumerate(mevcut_sira_m):
                c1, c2, c3, c4 = st.columns([3,1,1,1])
                _gizli_mi_m = tab_key in _gizli_menu
                c1.caption(("~~" if _gizli_mi_m else "") + _TAB_ETIKETLER.get(tab_key, tab_key))
                if c2.button("🙈" if not _gizli_mi_m else "👁", key=f"giz_{tab_key}"):
                    if _gizli_mi_m:
                        _gizli_menu.remove(tab_key)
                    else:
                        _gizli_menu.append(tab_key)
                    st.session_state["_gizli_menu_list"] = _gizli_menu
                    try:
                        _sb_gm = get_sb_client()
                        if _sb_gm:
                            import json as _gmj
                            _sb_gm.table("kullanici_tercih").upsert({
                                "kullanici": st.session_state["kullanici"],
                                "anahtar": "_gizli_menu",
                                "deger": _gmj.dumps(_gizli_menu)
                            }, on_conflict="kullanici,anahtar").execute()
                    except: pass
                    st.rerun()
                if idx_m > 0 and c3.button("▲", key=f"up_{tab_key}"):
                    yeni_s = mevcut_sira_m.copy()
                    yeni_s[idx_m], yeni_s[idx_m-1] = yeni_s[idx_m-1], yeni_s[idx_m]
                    save_menu_tercihi(st.session_state["kullanici"], yeni_s)
                    st.rerun()
                if idx_m < len(mevcut_sira_m)-1 and c4.button("▼", key=f"dn_{tab_key}"):
                    yeni_s = mevcut_sira_m.copy()
                    yeni_s[idx_m], yeni_s[idx_m+1] = yeni_s[idx_m+1], yeni_s[idx_m]
                    save_menu_tercihi(st.session_state["kullanici"], yeni_s)
                    st.rerun()
            if st.button("↺ Sıfırla", use_container_width=True, key="menu_sifirla"):
                save_menu_tercihi(st.session_state["kullanici"], _TAB_LISTESI_DEFAULT.copy() + ["kullanici","admin_rapor"])
                st.session_state["_gizli_menu_list"] = []
                st.rerun()

        with st.expander("📢 Duyuru"):
            with st.form("duyuru_form"):
                d_b = st.text_input("Başlık:")
                d_i = st.text_area("İçerik:", height=50)
                d_t = st.selectbox("Tip:", ["bilgi","uyari","hata"])
                if st.form_submit_button("📢 Yayınla") and d_b:
                    _sb_d = get_sb_client()
                    if _sb_d:
                        try:
                            _sb_d.table("duyurular").insert({
                                "baslik":d_b,"icerik":d_i,"tip":d_t,
                                "olusturan":st.session_state["kullanici"],"aktif":1
                            }).execute()
                            st.success("✅ Yayınlandı!")
                        except Exception as _ed:
                            st.error(f"Hata: {_ed}")
                    else:
                        db_insert("duyurular", {"baslik":d_b,"icerik":d_i,"tip":d_t,
                            "olusturan":st.session_state["kullanici"],"aktif":1})
                        st.success("✅ Yayınlandı!")
                    st.rerun()
            try:
                _sb_dy = get_sb_client()
                if _sb_dy:
                    _dy_res = _sb_dy.table("duyurular").select("*").eq("aktif",1).order("tarih",desc=True).execute()
                    _df_dy = pd.DataFrame(_dy_res.data) if _dy_res.data else pd.DataFrame()
                else:
                    _df_dy = db_read("duyurular", extra_sql="WHERE aktif=1 ORDER BY tarih DESC")
                if not _df_dy.empty:
                    for _, _dy in _df_dy.iterrows():
                        _tip = _dy.get("tip","bilgi")
                        _renk_d = "#1f6feb" if _tip=="bilgi" else "#ff9800" if _tip=="uyari" else "#f44336"
                        st.markdown(
                            f"<div style='border-left:3px solid {_renk_d};padding:4px 8px;margin:2px 0;font-size:11px;'>"
                            f"<b>{_dy.get('baslik','')}</b><br>{_dy.get('icerik','')}</div>",
                            unsafe_allow_html=True
                        )
                        if st.button("🗑️", key=f"dy_sil_{_dy.get('id',0)}"):
                            if _sb_dy:
                                _sb_dy.table("duyurular").update({"aktif":0}).eq("id",int(_dy.get("id",0))).execute()
                            st.rerun()
            except: pass

    st.divider()

    st.divider()

    # ── KULLANICI + ÇIKIŞ ─────────────────────────────────────────────────────
    _kc1, _kc2 = st.columns([3, 1])
    _kul_ad = st.session_state.get('kullanici','')
    _kul_bas_harf = (_kul_ad[:2].upper() if _kul_ad else "AD")
    _kc1.markdown(
        f"<div style='padding:4px 4px;display:flex;align-items:center;gap:9px;'>"
        f"<div style='width:26px;height:26px;border-radius:50%;background:#eef4fc;color:#1a4f9e;"
        f"display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;flex:none;'>{_kul_bas_harf}</div>"
        f"<div style='line-height:1.4;'>"
        f"<div style='font-size:12.5px;font-weight:500;color:#2c2c2a;'>{_kul_ad}</div>"
        f"<div style='font-size:11px;color:#8a8880;'>{st.session_state.get('rol','')}</div>"
        f"</div></div>",
        unsafe_allow_html=True
    )
    if _kc2.button("🚪", key="sidebar_cikis", use_container_width=True, help="Çıkış"):
        cikis()


# ── ANA UYGULAMA ──────────────────────────────────────────────────────────────
st.divider()

# Tab her zaman session_state'ten
if "aktif_tab" not in st.session_state:
    st.session_state["aktif_tab"] = "liste"
aktif = st.session_state["aktif_tab"]


# ── MOBİL MOD — body class + nav aktif ikon ──────────────────────────────────
_mobil_mod_aktif = st.session_state.get("_mobil_mod", False)
_aktif_tab_js = aktif
st.markdown(f"""
<script>
(function(){{
  var _body = window.parent ? window.parent.document.body : document.body;
  if({'true' if _mobil_mod_aktif else 'false'}){{
    _body.classList.add('mw-mobil-aktif');
  }} else {{
    _body.classList.remove('mw-mobil-aktif');
  }}
  // Nav butonlarında aktif class güncelle
  var _cur = '{_aktif_tab_js}';
  var _tabMap = {{'liste':'liste','analiz':'analiz','randevu':'randevu','harita':'harita'}};
  var _curNav = _tabMap[_cur] || _cur;
  document.querySelectorAll('.mw-nav-btn').forEach(function(b){{
    var _fn = b.getAttribute('onclick') || '';
    var _m = _fn.match(/mwTab\('([^']+)'\)/);
    if(_m && _m[1] === _curNav) b.classList.add('aktif');
    else b.classList.remove('aktif');
  }});
}})();
</script>
""", unsafe_allow_html=True)

# ── OTOMATİK SAYFA TAKİBİ ───────────────────────────────────────────────────
sayfa_log(aktif)


# ── YENİ KART EKLE / DÜZENLE ─────────────────────────────────────────────────
if aktif == "yeni":
    sayfa_log("yeni")

    # Müşteri ara ve düzenle
    st.markdown("### 🔍 Mevcut Müşteri Ara & Düzenle")
    col_ara1, col_ara2 = st.columns([3, 1])
    with col_ara1:
        musteri_ara = st.text_input("ID veya Firma Adı ile ara...", key="musteri_ara", placeholder="Örn: 5  veya  'ABC Ltd'")
    with col_ara2:
        st.markdown("<br>", unsafe_allow_html=True)
        ara_btn = st.button("🔎 Ara", use_container_width=True)

    bulunan = None
    if musteri_ara and ara_btn:
        df_ara_s = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")
        if not df_ara_s.empty:
            if musteri_ara.strip().isdigit():
                row_s = df_ara_s[df_ara_s["id"]==int(musteri_ara.strip())]
            else:
                row_s = df_ara_s[df_ara_s["firma"].str.contains(musteri_ara.strip(), case=False, na=False)]
            if not row_s.empty:
                r_d = row_s.iloc[0]
                bulunan = {str(k): ("" if str(v) in ["nan","None","NaT"] else str(v)) for k,v in r_d.items()}
                if not bulunan.get("gsm"):
                    bulunan["gsm"] = str(r_d.get("telefon") or r_d.get("tel") or "")
                if not bulunan.get("sabit"):
                    bulunan["sabit"] = str(r_d.get("sabit_hat") or "")
                _duzenleme_form_key_temizle(str(bulunan.get("id","")))
                st.session_state["duzenle_musteri"] = bulunan
                st.success(f"✅ **{bulunan.get('firma')}** (ID: {bulunan.get('id')})")
            else:
                st.error("Müşteri bulunamadı.")
                st.session_state.pop("duzenle_musteri", None)

    duzenle = st.session_state.get("duzenle_musteri")
    # Formdaki widget key'lerini düzenlenen müşterinin ID'sine bağlıyoruz.
    # Böylece farklı bir müşteriye geçildiğinde (veya yeni boş karta geçildiğinde)
    # Streamlit eski session_state değerini değil, müşterinin GERÇEK verisini gösterir.
    _form_id = str(duzenle.get("id")) if duzenle else "new"
    # Her düzenlemede form key'lerini temizle — eski değer yapışmasın
    _form_keys = [
        f"yeni_firma_{_form_id}", f"yeni_yetkili_{_form_id}",
        f"yeni_gsm_{_form_id}", f"yeni_sabit_{_form_id}", f"yeni_email_{_form_id}",
        f"yeni_adres_{_form_id}", f"yeni_notlar_{_form_id}",
        f"yeni_il_dis_{_form_id}", f"yeni_ilce_dis_{_form_id}",
        f"yeni_durum_dis_{_form_id}", f"yeni_temsilci_dis_{_form_id}",
        f"yeni_seg_dis_{_form_id}", f"yeni_asama_dis_{_form_id}",
    ]
    # Sadece müşteri değişince temizle
    _onceki_form_id = st.session_state.get("_onceki_form_id","")
    if _onceki_form_id != _form_id:
        for _fk in _form_keys:
            if _fk in st.session_state:
                del st.session_state[_fk]
        st.session_state["_onceki_form_id"] = _form_id

    st.divider()
    if duzenle:
        st.markdown(f"### ✏️ Düzenleniyor: **{duzenle.get('firma')}** (ID: {duzenle.get('id')})")
    else:
        st.markdown("### ➕ Yeni Cari Kart")

    il_listesi = sorted(ILLER_ILCELER.keys())
    _il_normalize_harita = {_bl_sadelestir(_ad): _ad for _ad in il_listesi}
    _kayitli_il_ham = duzenle.get("il","") if duzenle else ""
    # Büyük/küçük harf, yazım farkı toleranslı eşleştirme — kayıtlı değer varsa ASLA sessizce sıfırlanmaz
    mevcut_il = _il_normalize_harita.get(_bl_sadelestir(_kayitli_il_ham), il_listesi[0])
    if _kayitli_il_ham and _bl_sadelestir(_kayitli_il_ham) not in _il_normalize_harita:
        st.warning(f"⚠️ Kayıtlı il '{_kayitli_il_ham}' tanımlı 81 il listesinde bulunamadı — "
                   f"geçici olarak '{il_listesi[0]}' gösteriliyor. Doğru ili siz seçin, kaydedince güncellenir.")
    # Eski session key'lerini temizle — her durumda temizle ki eski değer yapışmasın
    for _dk in ["yeni_il_sec","yeni_ilce_sec","yeni_il_form","yeni_ilce_form",
                f"yeni_il_dis_{_form_id}", f"yeni_ilce_dis_{_form_id}"]:
        if _dk in st.session_state:
            del st.session_state[_dk]
    _asama_base = _tanimlar_yukle("asama")
    try:
        _df_as2 = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi IS NULL")
        if not _df_as2.empty and "islem_asamasi" in _df_as2.columns:
            for _a in _df_as2["islem_asamasi"].dropna().unique():
                if str(_a).strip() and str(_a) not in ["nan",""] and _a not in _asama_base:
                    _asama_base.append(str(_a))
    except: pass

    # ── İL / İLÇE form dışında — dinamik güncelleme için ───────────────────
    r2c1,r2c2,r2c3,r2c4,r2c5,r2c6 = st.columns(6)
    il_idx  = il_listesi.index(mevcut_il) if mevcut_il in il_listesi else 0
    il      = r2c1.selectbox("İl", il_listesi, index=il_idx, key=f"yeni_il_dis_{_form_id}")
    ilce_list_tum = ILLER_ILCELER.get(il, [""])
    _ilce_normalize_harita = {_bl_sadelestir(_ad): _ad for _ad in ilce_list_tum}
    _kayitli_ilce_ham = duzenle.get("ilce","") if duzenle else ""
    mevcut_ilce = _ilce_normalize_harita.get(_bl_sadelestir(_kayitli_ilce_ham), ilce_list_tum[0] if ilce_list_tum else "")
    # Streamlit'in yerleşik dropdown araması Türkçe karakterlerde (ş,ğ,ç,ı,ö,ü)
    # güvenilir eşleşmiyor ("baş" yazınca "Başakşehir" bulunamıyor). Bu yüzden
    # kendi Türkçe-toleranslı arama kutumuzu kullanıyoruz (_bl_sadelestir ile).
    _ilce_arama = r2c2.text_input("İlçe", key=f"yeni_ilce_arama_{_form_id}", placeholder="🔍 İlçe ara...")
    if _ilce_arama.strip():
        _arama_norm = _bl_sadelestir(_ilce_arama)
        ilce_list = [i for i in ilce_list_tum if _arama_norm in _bl_sadelestir(i)]
        if mevcut_ilce and mevcut_ilce not in ilce_list:
            ilce_list = [mevcut_ilce] + ilce_list
        if not ilce_list:
            ilce_list = ilce_list_tum  # arama sonuçsuzsa tam listeye düş, kullanıcı kilitlenmesin
    else:
        ilce_list = ilce_list_tum
    ilce_idx = ilce_list.index(mevcut_ilce) if mevcut_ilce in ilce_list else 0
    ilce    = r2c2.selectbox(" ", ilce_list, index=ilce_idx, key=f"yeni_ilce_dis_{_form_id}", label_visibility="collapsed")
    durum_opts = _tanimlar_yukle("durum") or ["Özel Müşteri","Portföy"]
    durum_idx  = durum_opts.index(duzenle.get("durum","")) if duzenle and duzenle.get("durum","") in durum_opts else 0
    durum   = r2c3.selectbox("Durum", durum_opts, index=durum_idx, key=f"yeni_durum_dis_{_form_id}")
    temsilci_dis = r2c4.text_input("Temsilci", value=duzenle.get("temsilci","") if duzenle else "", key=f"yeni_temsilci_dis_{_form_id}", placeholder="Temsilci adı")
    seg_opts = ["--","👑 A+","⭐ A","🔵 B","⚪ C"]
    seg_idx  = seg_opts.index(duzenle.get("segment","--")) if duzenle and duzenle.get("segment","--") in seg_opts else 0
    segment  = r2c5.selectbox("Segment", seg_opts, index=seg_idx, key=f"yeni_seg_dis_{_form_id}")
    _asama_default = duzenle.get("islem_asamasi") if duzenle else st.session_state.pop("varsayilan_asama", None)
    asama_idx = _asama_base.index(_asama_default) if _asama_default and _asama_default in _asama_base else 0
    asama    = r2c6.selectbox("İşlem Aşaması", _asama_base, index=asama_idx, key=f"yeni_asama_dis_{_form_id}")

    with st.form("yeni_kart_form"):
        # ── SATIR 1: Rakip Firma, Firma, Yetkili, GSM, Sabit Tel, E-Mail ─────
        r1c0,r1c1,r1c2,r1c3,r1c4,r1c5 = st.columns(6)
        rakip_firma = r1c0.text_input("Rakip Firma", value=duzenle.get("rakip_firma","") if duzenle else "", placeholder="Rakip firma adı", key=f"yeni_rakip_{_form_id}")
        firma   = r1c1.text_input("Firma Adı *", value=duzenle.get("firma","") if duzenle else "", placeholder="Firma adı", key=f"yeni_firma_{_form_id}")
        yetkili = r1c2.text_input("Yetkili",     value=duzenle.get("yetkili","") if duzenle else "", placeholder="Ad Soyad", key=f"yeni_yetkili_{_form_id}")
        gsm     = r1c3.text_input("GSM",         value=fmt_tel(duzenle.get("gsm","")) if duzenle else "", placeholder="05xx xxx xx xx", key=f"yeni_gsm_{_form_id}")
        sabit   = r1c4.text_input("Sabit Tel",   value=fmt_tel(duzenle.get("sabit","")) if duzenle else "", placeholder="0212 xxx xx xx", key=f"yeni_sabit_{_form_id}")
        email   = r1c5.text_input("E-Mail",      value=duzenle.get("email","") if duzenle else "", placeholder="mail@firma.com", key=f"yeni_email_{_form_id}")
        temsilci = temsilci_dis  # form dışından al

        # ── SATIR 3: Adres, Açıklama ─────────────────────────────────────────
        r3c1, r3c2 = st.columns(2)
        adres    = r3c1.text_area("Adres", value=duzenle.get("adres","") if duzenle else "", height=70, key=f"yeni_adres_{_form_id}")
        notlar_v = r3c2.text_area("📝 Açıklama", value=str(duzenle.get("aciklama","") or "") if duzenle else "", height=70, key=f"yeni_notlar_{_form_id}")

        # ── SATIR 4: Ciro ────────────────────────────────────────────────────
        cc1,cc2,cc3,cc4 = st.columns(4)
        bek_val = duzenle.get("beklenen_ciro",0) if duzenle else 0
        ger_val = duzenle.get("gerceklesen_ciro",0) if duzenle else 0
        bek_str = cc1.text_input("Beklenen Ciro (₺)", value=fmt_para(bek_val).replace(" ₺",""), placeholder="0", key=f"bek_ciro_str_{_form_id}")
        ger_str = cc2.text_input("Gerçekleşen Ciro (₺)", value=fmt_para(ger_val).replace(" ₺",""), placeholder="0", key=f"ger_ciro_str_{_form_id}")
        beklenen_ciro    = parse_para(bek_str)
        gerceklesen_ciro = parse_para(ger_str)
        fark  = gerceklesen_ciro - beklenen_ciro
        yuzde = (gerceklesen_ciro/beklenen_ciro*100) if beklenen_ciro>0 else 0
        cc3.metric("Fark (₺)", fmt_para(fark))
        cc4.metric("Gerçekleşme %", f"%{yuzde:.1f}".replace(".",","))

        btn_label = "💾 Güncelle" if duzenle else "💾 Cari Kartı Kaydet"
        if st.form_submit_button(btn_label, type="primary", use_container_width=True):
            # Form dışındaki değerleri session_state'den al
            _il_kayit    = st.session_state.get(f"yeni_il_dis_{_form_id}", il)
            _ilce_kayit  = st.session_state.get(f"yeni_ilce_dis_{_form_id}", ilce)
            _durum_kayit = st.session_state.get(f"yeni_durum_dis_{_form_id}", durum)
            _seg_kayit   = st.session_state.get(f"yeni_seg_dis_{_form_id}", "--")
            _asama_kayit = st.session_state.get(f"yeni_asama_dis_{_form_id}", asama)
            _tem_kayit   = st.session_state.get(f"yeni_temsilci_dis_{_form_id}", temsilci)

            # ── CİRO'YA GÖRE DURUM OTOMATİK BELİRLE ──────────────────────────
            # 100.000₺ altı → Portföy | 100.000₺ ve üzeri → Özel Müşteri
            if beklenen_ciro > 0:
                _durum_kayit = "Özel Müşteri" if beklenen_ciro >= 100000 else "Portföy"
            if not firma:
                st.warning("Firma adı boş bırakılamaz!")
            else:
                # Ekranda "541 357 80 20" gruplu görünse de veritabanına her zaman
                # sade rakamlarla yazılır (WhatsApp vb. entegrasyonlar boşluksuz
                # rakam bekliyor).
                gsm = "".join(ch for ch in str(gsm or "") if ch.isdigit())
                sabit = "".join(ch for ch in str(sabit or "") if ch.isdigit())
            if not firma:
                pass
            elif duzenle:
                ok = db_update("cari_kartlar", {
                    "firma": firma, "rakip_firma": rakip_firma, "yetkili": yetkili, "gsm": gsm,
                    "sabit": sabit, "email": email, "adres": adres,
                    "ilce": _ilce_kayit, "il": _il_kayit, "durum": _durum_kayit,
                    "temsilci": _tem_kayit, "islem_asamasi": _asama_kayit,
                    "segment": _seg_kayit, "aciklama": notlar_v,
                    "beklenen_ciro": beklenen_ciro, "gerceklesen_ciro": gerceklesen_ciro
                }, "id", duzenle.get("id"))
                try: db_read.clear()
                except: pass
                st.session_state.pop("duzenle_musteri", None)
                st.session_state["aktif_tab"] = "liste"
                st.session_state["kayit_mesaj"] = f"✅ '{firma}' güncellendi!"
                st.rerun()
            else:
                ok = db_insert("cari_kartlar", {
                    "tarih": datetime.now().isoformat(),
                    "firma": firma, "rakip_firma": rakip_firma, "yetkili": yetkili, "gsm": gsm,
                    "sabit": sabit, "email": email, "adres": adres,
                    "ilce": _ilce_kayit, "il": _il_kayit, "durum": _durum_kayit,
                    "temsilci": _tem_kayit, "islem_asamasi": _asama_kayit,
                    "segment": _seg_kayit, "aciklama": notlar_v,
                    "silindi": 0, "olusturan": st.session_state["kullanici"],
                    "beklenen_ciro": beklenen_ciro, "gerceklesen_ciro": gerceklesen_ciro,
                    "atanan_kullanici": st.session_state.get("kullanici","")
                })
                try: db_read.clear()
                except: pass
                st.session_state["aktif_tab"] = "liste"
                st.session_state["kayit_mesaj"] = f"✅ '{firma}' kaydedildi!"
                st.rerun()

    if duzenle:
        if st.button("❌ Düzenlemeyi İptal Et", use_container_width=True):
            st.session_state.pop("duzenle_musteri", None)
            st.rerun()

# ── CARİ LİSTE ───────────────────────────────────────────────────────────────
elif aktif == "mukerrer":
    sayfa_log("mukerrer")
    st.markdown("## 🔍 Mükerrer (Aynı İsimli) Müşterileri Bul ve Birleştir")

    _mk_df = get_cari_listesi()
    if not _mk_df.empty and "silindi" in _mk_df.columns:
        _mk_df = _mk_df[~(_mk_df["silindi"].astype(str).str.strip().isin(["1","True","true","1.0"]))]
    _mk_df = _atama_filtresi_uygula(_mk_df)

    if _mk_df.empty or "firma" not in _mk_df.columns:
        st.caption("Veri yok.")
    else:
        _mk_firma_gruplari = _mk_df.groupby(_mk_df["firma"].astype(str).str.strip().str.upper())["id"].apply(list)
        _mk_mukerrerler = {k: v for k, v in _mk_firma_gruplari.items() if len(v) > 1 and k not in ["", "NAN", "NONE"]}
        if not _mk_mukerrerler:
            st.success("✅ Mükerrer müşteri bulunamadı.")
        else:
            _mk_tum_idler = [int(i) for _v in _mk_mukerrerler.values() for i in _v]
            st.warning(f"{len(_mk_mukerrerler)} mükerrer firma adı bulundu — toplam {len(_mk_tum_idler)} kayıt.")
            st.caption("Hücrelere tıklayıp elle düzenleyin, \"💾 Kaydet\" ile kaydedin. "
                       "Silmek istediklerinizi \"Seç\" kutusuyla işaretleyip \"🗑️ Seçilenleri Sil\"e basın.")

            _mk_kolonlar = [c for c in ["id","rakip_firma","firma","yetkili","gsm","sabit","email","il","ilce",
                                         "durum","islem_asamasi","beklenen_ciro","gerceklesen_ciro"]
                             if c in _mk_df.columns]
            _mk_tablo = _mk_df[_mk_df["id"].astype(int).isin(_mk_tum_idler)][_mk_kolonlar].copy()
            _mk_tablo = _mk_tablo.sort_values("firma").reset_index(drop=True)

            # ── Not / Analiz / Randevu bilgisi — diğer tablolardan hesaplanır (salt okunur) ──
            _mk_sb_ek = get_sb_client()
            _mk_not_sayac, _mk_rand_sayac, _mk_analiz_set = {}, {}, set()
            if _mk_sb_ek:
                try:
                    _mk_not_ham = _mk_sb_ek.table("cari_aciklamalar").select("cari_id,aciklama").in_(
                        "cari_id", _mk_tum_idler).execute().data or []
                    for _r in _mk_not_ham:
                        if str(_r.get("aciklama","") or "").startswith("##YETKILI##"):
                            continue
                        _cid = int(_r.get("cari_id", 0) or 0)
                        _mk_not_sayac[_cid] = _mk_not_sayac.get(_cid, 0) + 1
                except Exception: pass
                try:
                    _mk_rand_ham = _mk_sb_ek.table("randevular").select("musteri_id").in_(
                        "musteri_id", _mk_tum_idler).execute().data or []
                    for _r in _mk_rand_ham:
                        _cid = int(_r.get("musteri_id", 0) or 0)
                        _mk_rand_sayac[_cid] = _mk_rand_sayac.get(_cid, 0) + 1
                except Exception: pass
                try:
                    _mk_firmalar_upper = set(_mk_tablo["firma"].astype(str).str.strip().str.upper())
                    _mk_analiz_ham = _mk_sb_ek.table("musteri_analiz").select("firma").execute().data or []
                    _mk_analiz_set = {str(a.get("firma","")).strip().upper() for a in _mk_analiz_ham
                                       if str(a.get("firma","")).strip().upper() in _mk_firmalar_upper}
                except Exception: pass

            _mk_tablo["Notlar"] = _mk_tablo["id"].apply(lambda x: _mk_not_sayac.get(int(x), 0))
            _mk_tablo["Randevu"] = _mk_tablo["id"].apply(lambda x: _mk_rand_sayac.get(int(x), 0))
            _mk_tablo["Analiz"] = _mk_tablo["firma"].apply(
                lambda x: "✅" if str(x).strip().upper() in _mk_analiz_set else "")

            _mk_tablo.insert(0, "Seç", False)

            # Kolon genişlik ayarlarını (Kolon Ayarları panelinde kaydedilen) burada da uygula
            _mk_KG = st.session_state.get("_kol_genislik", {})
            _mk_VARSAYILAN = {
                "firma":90,"rakip_firma":90,"yetkili":90,"gsm":100,"sabit":90,"email":90,
                "il":70,"ilce":60,"durum":80,"islem_asamasi":80,
                "beklenen_ciro":70,"gerceklesen_ciro":70,
                "id":40,"Seç":40,"Notlar":50,"Randevu":170,"Analiz":70,
            }
            def _mk_w(k):
                return int(_mk_KG.get(k, _mk_VARSAYILAN.get(k, 100)))

            _mk_col_config = {
                "Seç": st.column_config.CheckboxColumn("Seç", default=False, width=_mk_w("Seç")),
                "id": st.column_config.NumberColumn("ID", disabled=True, width=_mk_w("id")),
                "rakip_firma": st.column_config.TextColumn("Rakip Firma", width=_mk_w("rakip_firma")),
                "firma": st.column_config.TextColumn("Firma", width=_mk_w("firma")),
                "yetkili": st.column_config.TextColumn("Yetkili", width=_mk_w("yetkili")),
                "gsm": st.column_config.TextColumn("GSM", width=_mk_w("gsm")),
                "sabit": st.column_config.TextColumn("Sabit", width=_mk_w("sabit")),
                "email": st.column_config.TextColumn("Email", width=_mk_w("email")),
                "il": st.column_config.TextColumn("İl", width=_mk_w("il")),
                "ilce": st.column_config.TextColumn("İlçe", width=_mk_w("ilce")),
                "durum": st.column_config.TextColumn("Durum", width=_mk_w("durum")),
                "islem_asamasi": st.column_config.TextColumn("Aşama", width=_mk_w("islem_asamasi")),
                "beklenen_ciro": st.column_config.NumberColumn("Hedef ₺", format="%,.0f ₺", width=_mk_w("beklenen_ciro")),
                "gerceklesen_ciro": st.column_config.NumberColumn("Gerçek ₺", format="%,.0f ₺", width=_mk_w("gerceklesen_ciro")),
                "Notlar": st.column_config.NumberColumn("📨 Notlar", disabled=True, width=_mk_w("Notlar")),
                "Randevu": st.column_config.NumberColumn("📅 Randevu", disabled=True, width=_mk_w("Randevu")),
                "Analiz": st.column_config.TextColumn("✅ Analiz", disabled=True, width=_mk_w("Analiz")),
            }

            _mk_edited = st.data_editor(
                _mk_tablo, use_container_width=True, hide_index=True,
                column_config=_mk_col_config, key="mk_editor",
                height=min(600, 80 + 35 * len(_mk_tablo)))

            _mkc1, _mkc2 = st.columns([2,1])
            with _mkc1:
                if st.button("💾 Kaydet", type="primary", use_container_width=True, key="mk_kaydet_btn"):
                    _mk_sb = get_sb_client()
                    _mk_kaydedilen = 0
                    for _, _mkr in _mk_edited.iterrows():
                        _mk_id = int(_mkr["id"])
                        _mk_orig = _mk_tablo[_mk_tablo["id"] == _mk_id].iloc[0]
                        _mk_guncel = {}
                        for _mkk in _mk_kolonlar:
                            if _mkk == "id": continue
                            _yeni_v = _mkr.get(_mkk, "")
                            _eski_v = _mk_orig.get(_mkk, "")
                            if _mkk in ("gsm", "sabit"):
                                # Ekranda gruplu görünüyor ama veritabanına sade rakam yazılır.
                                _yeni_v = "".join(ch for ch in str(_yeni_v or "") if ch.isdigit())
                            if str(_yeni_v) != str(_eski_v):
                                _mk_guncel[_mkk] = _yeni_v
                        if _mk_guncel:
                            try:
                                if _mk_sb:
                                    _mk_sb.table("cari_kartlar").update(_mk_guncel).eq("id", _mk_id).execute()
                                else:
                                    db_update("cari_kartlar", _mk_guncel, "id", _mk_id)
                                _mk_kaydedilen += 1
                            except Exception:
                                pass
                    if _mk_kaydedilen:
                        try: get_cari_listesi.clear()
                        except: pass
                        st.session_state.pop("mk_editor", None)
                        st.toast(f"✅ {_mk_kaydedilen} kayıt güncellendi", icon="✅")
                        st.rerun()
                    else:
                        st.info("Değişiklik yok.")
            with _mkc2:
                _mk_secili = _mk_edited[_mk_edited["Seç"] == True]
                if st.button(f"🗑️ Seçilenleri Sil ({len(_mk_secili)})", use_container_width=True,
                             key="mk_sil_btn", disabled=(len(_mk_secili) == 0)):
                    _mk_sb2 = get_sb_client()
                    _mk_silinen = 0
                    for _mid in _mk_secili["id"].tolist():
                        try:
                            if _mk_sb2:
                                _mk_sb2.table("cari_kartlar").update({"silindi": 1}).eq("id", int(_mid)).execute()
                            else:
                                db_update("cari_kartlar", {"silindi": 1}, "id", int(_mid))
                            _mk_silinen += 1
                        except Exception:
                            pass
                    if _mk_silinen:
                        try: get_cari_listesi.clear()
                        except: pass
                        st.session_state.pop("mk_editor", None)
                        st.toast(f"🗑️ {_mk_silinen} kayıt silindi", icon="🗑️")
                        st.rerun()

elif aktif == "liste":
    sayfa_log("liste")
    st.markdown("""<style>
.block-container { padding-left: 0.6rem !important; padding-right: 0.6rem !important; max-width: 100% !important; }
[data-testid="stAppViewContainer"] { max-width: 100% !important; }
[data-testid="stMainBlockContainer"] { max-width: 100% !important; padding-left: 0.6rem !important; padding-right: 0.6rem !important; }
</style>""", unsafe_allow_html=True)

    # ── KAYDETME SONRASI ONAY BANNER'I — toast kaçırılırsa diye burada da göster ──
    _son_kaydet_msg = st.session_state.pop("_son_kaydet_ozeti", None)
    if _son_kaydet_msg:
        st.success(_son_kaydet_msg, icon="✅")

    # NOT (ÖNEMLİ KURAL): Geçici teşhis/debug panelleri asla önbelleksiz (cache'siz)
    # tam tablo taraması yapıp HER sayfa yenilemesinde (rerun) otomatik ("expanded=True")
    # çalışacak şekilde eklenmez — bu, sayfayı fark edilir şekilde yavaşlatır ve
    # yanıp sönme/kayma hissi verir. Bir önceki "BARSAN/CRN ham sorgu" paneli bu
    # yüzden kaldırıldı. Gerekirse: sadece bir BUTONA basılınca çalışan, sonucu
    # session_state'te tutan, tek seferlik bir kontrol olarak eklenmeli.

    # ── MOBİL KART GÖRÜNÜMÜ ──────────────────────────────────────────────────
    if st.session_state.get("_mobil_mod", False):
        st.markdown("""
<style>
/* Mobil liste sayfası — masaüstü elementleri gizle */
.mw-mob-only { display: block !important; }
.mw-desk-only { display: none !important; }
section[data-testid="stSidebar"] { display: none !important; }
.block-container { padding: 4px 6px 80px 6px !important; }
/* Kart stilleri */
.mw-firma-card {
  background: white;
  border: 0.5px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: box-shadow .15s;
}
.mw-firma-card:active { background: #f8fafc; }
.mw-kart-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px; }
.mw-kart-adi { font-size: 14px; font-weight: 600; color: #0f172a; }
.mw-kart-badge { font-size: 11px; padding: 2px 8px; border-radius: 20px; font-weight: 500; white-space: nowrap; }
.mw-kart-meta { font-size: 12px; color: #64748b; margin-bottom: 6px; }
.mw-kart-foot { display: flex; justify-content: space-between; align-items: center; border-top: 0.5px solid #f1f5f9; padding-top: 6px; }
.mw-kart-ciro { font-size: 13px; font-weight: 600; color: #0f172a; }
.mw-kart-acts { display: flex; gap: 6px; }
.mw-act-btn { width: 34px; height: 34px; border-radius: 8px; border: 0.5px solid #e2e8f0; background: #f8fafc; display: flex; align-items: center; justify-content: center; font-size: 16px; text-decoration: none; }
.mw-analiz-tag { font-size: 11px; color: #16a34a; background: #dcfce7; padding: 2px 7px; border-radius: 20px; }
/* Alt nav */
#mw-mobile-nav { display: flex !important; }
</style>
""", unsafe_allow_html=True)

        # Veri yükle
        _sb_m = get_sb_client()
        try:
            if _sb_m:
                _res_m = _sb_m.table("cari_kartlar").select("*").neq("silindi",1).order("tarih",desc=True).execute()
                _df_m = pd.DataFrame(_res_m.data) if _res_m.data else pd.DataFrame()
            else:
                raise Exception()
        except:
            _df_m = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi IS NULL ORDER BY tarih DESC")

        if not _df_m.empty:
            for _tk in ["gsm","sabit"]:
                if _tk in _df_m.columns:
                    _df_m[_tk] = _telefon_temizle(_df_m[_tk])

        # Analiz yapılmış firmalar
        _analiz_set = set()
        try:
            if _sb_m:
                _an_r = _sb_m.table("musteri_analiz").select("firma").execute().data or []
                def _nm(s): return str(s or "").strip().upper().replace("İ","I").replace("Ş","S").replace("Ğ","G").replace("Ü","U").replace("Ö","O").replace("Ç","C")
                _analiz_set = set(_nm(x.get("firma","")) for x in _an_r if x.get("firma"))
        except: pass

        # Arama & filtre
        _mc1, _mc2 = st.columns([3,1])
        _mob_ara = _mc1.text_input("🔍 Ara", placeholder="Firma, yetkili, il...", key="mob_ara", label_visibility="collapsed")
        _mob_durum = _mc2.selectbox("Durum", ["Tümü","Portföy","Özel Müşteri","Randevu","Tekrar Ara","Fiyat Hazırla","Teklif","Pasif"], key="mob_dur", label_visibility="collapsed")

        # Filtrele
        _df_mob = _df_m.copy() if not _df_m.empty else pd.DataFrame()
        if not _df_mob.empty:
            if _mob_ara:
                _mask = (
                    _df_mob.get("firma", pd.Series()).astype(str).str.contains(_mob_ara, case=False, na=False) |
                    _df_mob.get("yetkili", pd.Series()).astype(str).str.contains(_mob_ara, case=False, na=False) |
                    _df_mob.get("il", pd.Series()).astype(str).str.contains(_mob_ara, case=False, na=False)
                )
                _df_mob = _df_mob[_mask]
            if _mob_durum != "Tümü":
                if "durum" in _df_mob.columns:
                    _df_mob = _df_mob[_df_mob["durum"].astype(str).str.contains(_mob_durum, case=False, na=False)]

        st.caption(f"{len(_df_mob)} müşteri")

        # Durum renk & badge
        _DURUM_RENK = {
            "Portföy":         ("#dcfce7","#166534"),
            "Özel Müşteri":    ("#eff6ff","#1d4ed8"),
            "Randevu":         ("#dbeafe","#1e40af"),
            "Tekrar Ara":      ("#fef9c3","#854d0e"),
            "Fiyat Hazırla":   ("#ede9fe","#5b21b6"),
            "Teklif":          ("#fef3c7","#92400e"),
            "Pasif":           ("#f1f5f9","#475569"),
            "Kazanıldı":       ("#dcfce7","#14532d"),
        }

        # Kartları render et
        if not _df_mob.empty:
            for _, _row in _df_mob.iterrows():
                _firma   = str(_row.get("firma","") or "?")
                _yetkili = str(_row.get("yetkili","") or "")
                _gsm     = str(_row.get("gsm","") or "")
                _il      = str(_row.get("il","") or "")
                _ilce    = str(_row.get("ilce","") or "")
                _durum   = str(_row.get("durum","") or "")
                _asama   = str(_row.get("islem_asamasi","") or "")
                _bek     = float(_row.get("beklenen_ciro",0) or 0)
                _ger     = float(_row.get("gerceklesen_ciro",0) or 0)
                _seg     = str(_row.get("segment","") or "")
                _cari_id = _row.get("id","")

                # Segment dot
                _dot = "🟢" if "A" in _seg else ("🔵" if "B" in _seg else ("⚪" if "C" in _seg else ""))
                # Analiz var mı
                def _nrm(s): return str(s or "").strip().upper().replace("İ","I").replace("Ş","S").replace("Ğ","G").replace("Ü","U").replace("Ö","O").replace("Ç","C")
                _analiz_var = _nrm(_firma) in _analiz_set
                # Badge renk
                _bg, _tc = _DURUM_RENK.get(_durum, ("#f1f5f9","#475569"))
                # Telefon link
                _gsm_clean = _gsm.replace(" ","").replace("-","").replace("(","").replace(")","")
                if _gsm_clean and not _gsm_clean.startswith("90"): _gsm_clean = "90" + _gsm_clean.lstrip("0")

                # Kart HTML — değişkenler önceden hesapla
                _meta_html = ""
                if _il:
                    _meta_html += f"📍 {_il}" + (f"/{_ilce}" if _ilce else "")
                if _yetkili and _yetkili not in ["nan","None",""]:
                    _meta_html += f"  👤 {_yetkili}"
                if _asama and _asama not in ["nan","None",""]:
                    _meta_html += f"  🏭 {_asama}"
                _analiz_html = "<span class='mw-analiz-tag'>✅</span>" if _analiz_var else ""
                _tel_html = f"<a class='mw-act-btn' href='tel:{_gsm_clean}'>📞</a>" if _gsm_clean else ""
                _wa_html  = f"<span class='mw-act-btn' style='opacity:0.35;cursor:not-allowed' title='Geçici devre dışı'>💬</span>" if _gsm_clean else ""
                _ciro_str = f"{int(_bek):,}₺ / {int(_ger):,}₺"

                st.markdown(f"""<div class="mw-firma-card">
  <div class="mw-kart-top">
    <div class="mw-kart-adi">{_dot} {_firma}</div>
    <span class="mw-kart-badge" style="background:{_bg};color:{_tc};">{_durum}</span>
  </div>
  <div class="mw-kart-meta">{_meta_html}</div>
  <div class="mw-kart-foot">
    <div>
      <div style="font-size:10px;color:#94a3b8;">Hedef / Gerçek</div>
      <div class="mw-kart-ciro">{_ciro_str}</div>
    </div>
    <div class="mw-kart-acts">{_analiz_html}{_tel_html}{_wa_html}</div>
  </div>
</div>""", unsafe_allow_html=True)

                # Nota git butonu
                if st.button(f"📋 Not / Detay — {_firma[:25]}", key=f"mob_det_{_cari_id}", use_container_width=True):
                    st.session_state["mob_secili_id"] = _cari_id
                    st.session_state["mob_secili_firma"] = _firma
                    st.rerun()
        else:
            st.info("Müşteri bulunamadı.")
        st.stop()
    # ── MASAÜSTÜ — normal liste devam eder ──────────────────────────────────
    # Kolon genişliklerini localStorage'a kaydet ve geri yükle
    st.markdown("""<script>
(function(){
  const STORE_KEY = 'mwcrm_col_widths';
  function saveWidths(){
    try {
      const headers = document.querySelectorAll('[data-testid="stDataEditor"] th');
      if(!headers.length) return;
      const widths = {};
      headers.forEach(th => {
        const label = th.innerText.trim();
        if(label) widths[label] = th.offsetWidth;
      });
      localStorage.setItem(STORE_KEY, JSON.stringify(widths));
    } catch(e){}
  }
  function restoreWidths(){
    try {
      const saved = localStorage.getItem(STORE_KEY);
      if(!saved) return;
      const widths = JSON.parse(saved);
      const headers = document.querySelectorAll('[data-testid="stDataEditor"] th');
      headers.forEach(th => {
        const label = th.innerText.trim();
        if(widths[label]){
          th.style.width = widths[label]+'px';
          th.style.minWidth = widths[label]+'px';
          th.style.maxWidth = widths[label]+'px';
        }
      });
    } catch(e){}
  }
  // Resize observer — genişlik değişince kaydet
  const obs = new MutationObserver(() => {
    restoreWidths();
    setTimeout(saveWidths, 500);
  });
  function init(){
    const editor = document.querySelector('[data-testid="stDataEditor"]');
    if(editor){
      restoreWidths();
      obs.observe(editor, {childList:true, subtree:true, attributes:true});
      editor.addEventListener('mouseup', () => setTimeout(saveWidths, 300));
    } else {
      setTimeout(init, 500);
    }
  }
  setTimeout(init, 1000);
})();
</script>""", unsafe_allow_html=True)
    if st.session_state.get("kayit_mesaj"):
        st.success(st.session_state["kayit_mesaj"])
        st.session_state["kayit_mesaj"] = ""

    # ── VERİ YÜKLE ──────────────────────────────────────────────────────────────
    sb_liste = get_sb_client()
    # NOT: Burada eskiden HER render'da (yani her tek hücre düzenlemesinde bile)
    # get_cari_listesi.clear() ile önbellek zorla temizlenip TÜM müşteri
    # tablosu (3700+ kayıt) yeniden Supabase'den çekiliyordu. Bu, düzenleme
    # yaparken her hücre değişiminde gözle görülür bir "sorgu çalışıyor" gecikmesi
    # ve ekran titremesine sebep oluyordu. Artık önbellek SADECE gerçek bir
    # kayıt/silme/arşivleme işleminden SONRA (ilgili yerlerde zaten çağrılıyor)
    # temizleniyor; salt düzenleme sırasında 60 saniyelik önbellek kullanılıyor.
    df = get_cari_listesi()

    # ── Güncelleme Tarihi ön-hesabı — ÇOKLU TARİH filtre kutusu için burada
    # (filtrelemeden önce) hesaplanmalı. ÖNEMLİ: bir müşterinin sadece "EN SON"
    # tarihine bakılmıyor — o müşteriye ait HER işlemin (her not, her teklif,
    # her mesaj/arama, her kart düzenlemesi, ilk kayıt) kendi tarihi ayrı ayrı
    # toplanıyor. Böylece "8 Temmuz" seçilince, en son işlemi daha sonraki bir
    # tarihte olsa bile 8 Temmuz'da GERÇEKTEN işlem görmüş her müşteri gelir —
    # sadece "en son işlemi tam o gün olan" tek bir müşteri değil. SAATSİZ.
    if "_cari_son_guncelleme" not in st.session_state:
        st.session_state["_cari_son_guncelleme"] = {}
        try:
            _sb_sg_erken = get_sb_client()
            if _sb_sg_erken:
                import json as _sgj_erken
                _r_sg_erken = _sb_sg_erken.table("kullanici_tercih").select("deger").eq(
                    "kullanici","__liste_ui__").eq("anahtar","_cari_son_guncelleme").execute()
                if _r_sg_erken.data:
                    st.session_state["_cari_son_guncelleme"] = _sgj_erken.loads(_r_sg_erken.data[0]["deger"])
        except:
            pass
    _cari_son_guncelleme_erken = st.session_state.get("_cari_son_guncelleme", {})

    @st.cache_data(ttl=60, show_spinner=False)
    def _tum_aktivite_tarihleri_yukle_erken():
        """id_str -> o müşteriye ait TÜM işlem günlerinin kümesi (set of date)."""
        import collections as _colae
        _kume = _colae.defaultdict(set)
        _sb_ae = get_sb_client()
        if not _sb_ae:
            return dict(_kume)

        def _ekle_ae(_mid_ham, _tarih_ham):
            if not _mid_ham or not _tarih_ham:
                return
            _dt = _guncelleme_tarih_parse(_tarih_ham)
            if _dt is None:
                return
            _kume[str(_mid_ham)].add(_dt.date())

        # 1) Notlar/açıklamalar
        try:
            _rae1 = _sb_ae.table("cari_aciklamalar").select("cari_id,created_at").execute()
            for _rw in (_rae1.data or []):
                _ekle_ae(_rw.get("cari_id"), _rw.get("created_at"))
        except Exception:
            pass
        # 2) Teklifler
        try:
            _rae2 = _sb_ae.table("teklifler").select("musteri_id,created_at").execute()
            for _rw in (_rae2.data or []):
                _ekle_ae(_rw.get("musteri_id"), _rw.get("created_at"))
        except Exception:
            pass
        # 3) Mesaj/arama/whatsapp kayıtları
        try:
            _rae3 = _sb_ae.table("islem_kaydi").select("musteri_id,tarih").execute()
            for _rw in (_rae3.data or []):
                _ekle_ae(_rw.get("musteri_id"), _rw.get("tarih"))
        except Exception:
            pass
        return {k: v for k, v in _kume.items()}

    _tum_aktivite_erken = {}
    try:
        _tum_aktivite_erken = _tum_aktivite_tarihleri_yukle_erken()
    except Exception:
        _tum_aktivite_erken = {}

    # id_str -> {date, date, ...} — aktivite günleri + cari kartı düzenleme
    # günleri + ilk kayıt günü, HEPSİ BİRDEN (tek bir "en son" değil)
    _id_tum_gunler = {}
    if not df.empty and "id" in df.columns:
        for _gidx, _grow in df.iterrows():
            try:
                _grid = str(int(_grow["id"]))
            except Exception:
                continue
            _gunler = set(_tum_aktivite_erken.get(_grid, set()))
            _sg_ham = _cari_son_guncelleme_erken.get(_grid)
            if _sg_ham:
                _sg_dt = _guncelleme_tarih_parse(_sg_ham)
                if _sg_dt:
                    _gunler.add(_sg_dt.date())
            _gr_ilk = _grow.get("tarih") or _grow.get("created_at")
            if _gr_ilk:
                _ilk_dt = _guncelleme_tarih_parse(str(_gr_ilk))
                if _ilk_dt:
                    _gunler.add(_ilk_dt.date())
            if _gunler:
                _id_tum_gunler[_grid] = _gunler

    # Filtre kutusu seçenekleri — sistemde görülen TÜM tarihler, en yeni en üstte
    _guncelleme_tarih_opts_set = set()
    for _gset in _id_tum_gunler.values():
        _guncelleme_tarih_opts_set.update(_gset)
    _guncelleme_tarih_opts = sorted(_guncelleme_tarih_opts_set, reverse=True)
    _guncelleme_tarih_opts_str = [d.strftime("%d.%m.%Y") for d in _guncelleme_tarih_opts]
    # id_str -> {"08.07.2026","12.08.2026",...} — string haline çevrilmiş tam küme
    _id_tum_gunler_str = {k: {d.strftime("%d.%m.%Y") for d in v} for k, v in _id_tum_gunler.items()}

    # NOT: "tarih" (İşlem Tarih) sütunu tablonun içinde DÜZENLENEBİLİR bir alan.
    # Eskiden her rerun'da canlı "tarih" değerine göre yeniden sıralanıyordu —
    # yani bir müşterinin İşlem Tarihini değiştirip kaydetmek o müşterinin
    # satırını kaydırıyordu. Streamlit'te "Seç" işareti satır POZİSYONUNA göre
    # tutulduğu için, sıra kayınca işaret başka bir müşteride kalmış gibi
    # görünüyordu. Çözüm: sıralamayı sadece müşteri KÜMESİ değiştiğinde
    # (yeni/silinen kayıt) yeniden hesapla, aynı kümede kalan bir düzenleme +
    # kayıt sırasında sırayı SABİT tut.
    if not df.empty and "tarih" in df.columns and "id" in df.columns:
        _cl_id_kume = tuple(sorted(int(x) for x in df["id"].tolist()))
        if st.session_state.get("_cl_sira_id_kume") != _cl_id_kume or not st.session_state.get("_cl_sabit_sira"):
            _cl_sirali_idler = df.sort_values("tarih", ascending=False)["id"].tolist()
            st.session_state["_cl_sabit_sira"] = _cl_sirali_idler
            st.session_state["_cl_sira_id_kume"] = _cl_id_kume
        else:
            _cl_sirali_idler = st.session_state["_cl_sabit_sira"]
        _cl_sira_map = {v: i for i, v in enumerate(_cl_sirali_idler)}
        df["_cl_sira_key"] = df["id"].map(_cl_sira_map).fillna(len(_cl_sirali_idler))
        df = df.sort_values("_cl_sira_key").drop(columns=["_cl_sira_key"]).reset_index(drop=True)

    if not df.empty:
        for _tk in ["gsm","sabit"]:
            if _tk in df.columns:
                df[_tk] = _telefon_temizle(df[_tk])

    # ── ATAMA FİLTRESİ — admin hepsini görür, kullanıcı sadece kendine atananları ──
    df = _atama_filtresi_uygula(df)

    for _kol in ["aciklama","adres","notlar"]:
        if _kol not in df.columns: df[_kol] = ""
    df["aciklama"] = df["aciklama"].fillna("").astype(str)
    df["aciklama"] = df["aciklama"].replace("nan","")

    # Supabase'de notlar kolonu yoksa ekle
    if sb_liste:
        try:
            _test = sb_liste.table("cari_kartlar").select("aciklama").limit(1).execute()
        except:
            pass  # Kolon yoksa update sırasında hata alırız, onu da yakalayacağız

    # ── ASAMA & DURUM LİSTELERİ — sistem_tanimlar tablosundan ──────────────────
    tum_asama_opts = _tanimlar_yukle("asama")
    tum_durum_opts = _tanimlar_yukle("durum")
    # SONUÇ rozetlerinden biri (Devam Ediyor) tanımlar tablosunda eksik olsa bile
    # filtre kutusunda seçilebilir olsun diye garanti ediyoruz
    if "Devam Ediyor" not in tum_asama_opts:
        tum_asama_opts.append("Devam Ediyor")
    # NOT: df'de olan ama tanımlardan silinmiş durum/aşamalar eklenmez
    # Sadece tanımlar tablosundakiler gösterilir

    # ── ÜST METRİKLER — TÜM DURUM VE AŞAMALAR ──────────────────────────────
    # Durum emoji haritası
    _DURUM_EMOJI = {
        "Toplam":       "📊",
        "Portföy":      "💼",
        "Hedef":        "🎯",
        "Aktif":        "✅",
        "Deneme":       "🧪",
        "Takip":        "👁️",
        "Tekrar Ara":   "📞",
        "Pasif":        "⚫",
    }
    # Aşama emoji haritası
    _ASAMA_EMOJI = {
                "Teklif":           "📄",
        "Deneme":           "🧪",
        "Sözleşme":         "📝",
        "Kazanıldı":        "🏆",
        "Kaybedildi":       "❌",
                "Gereksizler":      "🗑️",
    }

    # Durum butonu sırası — hafızada tut
    # ── DURUM & AŞAMA BUTONLARI ───────────────────────────────────────────────
    def _rapor_satir(veri_listesi, sira_key, gizli_key, fil_key, emoji_map, satir_label, d_adlar=None):
        """Genel buton satırı: sıralama + gizle/göster"""
        _veri_dict = {ad: sayi for ad, sayi in veri_listesi}
        _adlar = [ad for ad, _ in veri_listesi]

        def _tercih_yukle(anahtar, varsayilan):
            """DB'den tercih yükle"""
            try:
                _sb = get_sb_client()
                if _sb:
                    _r = _sb.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar",anahtar).execute()
                    if _r.data:
                        import json as _tj
                        return _tj.loads(_r.data[0]["deger"])
            except: pass
            return varsayilan

        def _tercih_kaydet(anahtar, deger):
            """DB'ye tercih kaydet"""
            try:
                _sb = get_sb_client()
                if _sb:
                    import json as _tj
                    _sb.table("kullanici_tercih").upsert({
                        "kullanici":"__liste_ui__","anahtar":anahtar,
                        "deger":_tj.dumps(deger, ensure_ascii=False)
                    }, on_conflict="kullanici,anahtar").execute()
            except: pass

        # Sıra — session_state'te yoksa DB'den yükle
        if sira_key not in st.session_state:
            st.session_state[sira_key] = _tercih_yukle(sira_key, _adlar.copy())
        _sira = st.session_state[sira_key]
        for _a in _adlar:
            if _a not in _sira: _sira.append(_a)
        _sira = [x for x in _sira if x in _adlar]
        st.session_state[sira_key] = _sira

        # Gizli — session_state'te yoksa DB'den yükle
        if gizli_key not in st.session_state:
            st.session_state[gizli_key] = _tercih_yukle(gizli_key, [])
        _gizli_list = st.session_state.get(gizli_key, [])
        if not isinstance(_gizli_list, list): _gizli_list = list(_gizli_list)
        _gizli = set(_gizli_list)

        # Düzenleme modu
        _mode = st.session_state.get(f"_{sira_key}_mode", False)

        if _mode:
            # Düzenleme modu — başında ✓ sonra her buton
            st.caption("← → taşı · 🙈 gizle · ✓ bitir")
            _tum = _sira.copy()
            _edit_cols = st.columns([0.4] + [1]*len(_tum))
            # İlk kolona ✓ butonu
            if _edit_cols[0].button("✓", key=f"{sira_key}_bitti", use_container_width=True):
                st.session_state[f"_{sira_key}_mode"] = False; st.rerun()
            for i, _ad in enumerate(_tum):
                _sayi = _veri_dict.get(_ad, 0)
                _em = emoji_map.get(_ad, "🔹")
                _gizli_mi = _ad in _gizli
                with _edit_cols[i+1]:
                    _r1, _r2, _r3 = st.columns(3)
                    if _r1.button("←", key=f"{sira_key}_sol_{i}", use_container_width=True):
                        if i > 0:
                            _sira[i], _sira[i-1] = _sira[i-1], _sira[i]
                            st.session_state[sira_key] = _sira
                            _tercih_kaydet(sira_key, _sira); st.rerun()
                    if _r2.button("→", key=f"{sira_key}_sag_{i}", use_container_width=True):
                        if i < len(_tum)-1:
                            _sira[i], _sira[i+1] = _sira[i+1], _sira[i]
                            st.session_state[sira_key] = _sira
                            _tercih_kaydet(sira_key, _sira); st.rerun()
                    if _r3.button("🙈" if not _gizli_mi else "👁", key=f"{sira_key}_giz_{i}", use_container_width=True):
                        if _gizli_mi: _gizli.discard(_ad)
                        else: _gizli.add(_ad)
                        st.session_state[gizli_key] = list(_gizli)
                        _tercih_kaydet(gizli_key, list(_gizli)); st.rerun()
                    st.button(f"{_em} {_ad}\n{_sayi}", key=f"{sira_key}_prev_{i}",
                              use_container_width=True, disabled=True)
                    if _gizli_mi:
                        st.markdown("<div style='text-align:center;font-size:10px;color:#94a3b8'>gizli</div>", unsafe_allow_html=True)
        else:
            # Normal mod — sadece görünen butonlar + başında ⚙️
            _gorunen = [(_ad, _veri_dict.get(_ad, 0)) for _ad in _sira if _ad not in _gizli]
            if _gorunen:
                _btn_cols = st.columns([0.4] + [1]*len(_gorunen))
                if _btn_cols[0].button("⚙️", key=f"{sira_key}_toggle2", use_container_width=True):
                    st.session_state[f"_{sira_key}_mode"] = True; st.rerun()
                for i, (_ad, _sayi) in enumerate(_gorunen):
                    _em = emoji_map.get(_ad, "🔹")
                    if _btn_cols[i+1].button(f"{_em} {_ad}\n{_sayi}", key=f"{sira_key}_btn_{i}", use_container_width=True):
                        if fil_key == "durum":
                            st.session_state["_cl_fil_durum_multi"] = [] if _ad == "Toplam" else [_ad]
                        elif fil_key == "asama":
                            st.session_state["_cl_fil_asama_multi"] = [_ad]
                        else:  # tek — durum+asama birleşik
                            if _ad == "Toplam":
                                st.session_state["_toplam_aktif"] = True
                                for _fk in ["_cl_fil_durum_multi","_cl_fil_asama_multi",
                                            "_cl_fil_il_multi","_cl_fil_ilce_multi",
                                            "_cl_fil_temsilci_multi","_cl_sec_kart"]:
                                    if _fk in st.session_state: del st.session_state[_fk]
                                st.session_state["_filtre_reset_sayac"] = st.session_state.get("_filtre_reset_sayac", 0) + 1
                            elif d_adlar and _ad in d_adlar:
                                st.session_state["_toplam_aktif"] = False
                                st.session_state["_cl_fil_durum_multi"] = [_ad]
                                st.session_state["_cl_fil_asama_multi"] = []
                            else:
                                st.session_state["_toplam_aktif"] = False
                                st.session_state["_cl_fil_asama_multi"] = [_ad]
                                st.session_state["_cl_fil_durum_multi"] = []
                        st.rerun()

    # Toplam basınca tüm filtreleri sıfırla
    if st.session_state.get("_tek_sec_tek") == "Toplam" or st.session_state.get("_tek_fil") == "Toplam":
        for _fk in ["_cl_fil_asama_multi","_cl_fil_durum_multi","_cl_sec_kart",
                    "_cl_fil_il_multi","_cl_fil_ilce_multi","_tek_sec_tek"]:
            if _fk in st.session_state: del st.session_state[_fk]
        st.session_state["_tek_fil"] = None
        st.rerun()

    # ── TEK SATIR: Durum + Aşama birleşik ───────────────────────────────────
    _d_veri = [("Toplam", len(df))]
    for _dn in tum_durum_opts:
        if str(_dn).upper() in ["NONE","NAN",""]: continue
        _dc = len(df[df["durum"]==_dn]) if "durum" in df.columns else 0
        _d_veri.append((_dn, _dc))
    _a_veri = [(a, len(df[df["islem_asamasi"]==a]) if "islem_asamasi" in df.columns else 0) for a in tum_asama_opts if str(a).upper() not in ["NONE","NAN",""]] if tum_asama_opts else []
    _tum_veri = _d_veri + _a_veri
    _d_adlar = {x[0] for x in _d_veri}

    # ── AŞAMA GRUPLARI — gerçek aşama adlarına göre ──────────────────────────
    # ── AŞAMA GRUPLARI — Supabase'deki GERÇEK değerler ──────────────────────
    # islem_asamasi kolonundaki tam değerler:
    # Arama, Tekrar Ara, E-Mail, Randevu, Teklif, Fiyat Hazırla, Deneme, Sözleşme, TAKİP
    # Kazanıldı, Kaybedildi, Devam Ediyor

    # AŞAMA grubu — iletişim aşamaları
    _grp1_asama = [a for a in tum_asama_opts if a in ["Arama","Tekrar Ara","E-Mail","Mail","Mesaj","Whatsapp Mesaj"]]

    # 1. AŞAMA — Randevu
    _grp2_asama = [a for a in tum_asama_opts if a in ["Randevu"]]

    # 2. AŞAMA — Teklif
    # NOT: tanımlarda aynı isim (büyük/küçük harf farklı vb.) birden fazla kez
    # kayıtlıysa çift sayıma yol açabiliyordu — normalize edilmiş isme göre
    # TEKİLLEŞTİRİLİYOR, "Teklif" sadece BİR kutu olarak sayılır.
    _grp3_asama_ham = [a for a in tum_asama_opts if a in ["Teklif"]]
    _grp3_asama = list(dict.fromkeys(_grp3_asama_ham))  # sırayı koruyarak tekilleştir

    # 3. AŞAMA — Deneme, TAKİP, Sözleşme, Fiyat Hazırla (aynı tekilleştirme)
    _grp4_asama_ham = [a for a in tum_asama_opts if a in ["Deneme","TAKİP","Sözleşme","Fiyat Hazırla"]]
    _grp4_asama = list(dict.fromkeys(_grp4_asama_ham))

    # SONUÇ
    _grp5_asama = [a for a in tum_asama_opts if a in ["Kazanıldı","Kaybedildi","Devam Ediyor"]]
    if "Devam Ediyor" not in _grp5_asama: _grp5_asama.append("Devam Ediyor")

    _tum_grp = set(_grp1_asama+_grp2_asama+_grp3_asama+_grp4_asama+_grp5_asama)
    # İlk Temas = Aşamasız sayılır — gruplara dahil edilmez
    # Diğer grubu YOK
    _tum_grp = set(_grp1_asama+_grp2_asama+_grp3_asama+_grp4_asama+_grp5_asama)


    def _asama_sayi(ad):
        if "islem_asamasi" not in df.columns: return 0
        return len(df[df["islem_asamasi"]==ad])

    def _durum_sayi(ad):
        if ad == "Toplam": return len(df)
        if "durum" not in df.columns: return 0
        return len(df[df["durum"]==ad])

    def _asamasiz_sayi():
        if "islem_asamasi" not in df.columns: return 0
        _tum_asama = [a for grp in [_grp1_asama,_grp2_asama,_grp3_asama,_grp4_asama,_grp5_asama] for a in grp]
        return len(df[~df["islem_asamasi"].isin(_tum_asama) | df["islem_asamasi"].isna()])

    _grp1_toplam = sum(_asama_sayi(a) for a in _grp1_asama)
    _grp2_toplam = sum(_asama_sayi(a) for a in _grp2_asama)
    _grp3_toplam = sum(_asama_sayi(a) for a in _grp3_asama)
    _grp4_toplam = sum(_asama_sayi(a) for a in _grp4_asama)
    _grp5_toplam = sum(_asama_sayi(a) for a in _grp5_asama)

    # ── HTML RAPOR SATIRI ─────────────────────────────────────────────────────
    import json as _rjson
    _aktif_fil_durum = st.session_state.get("_cl_fil_durum_multi", [])
    _aktif_fil_asama = st.session_state.get("_cl_fil_asama_multi", [])
    _toplam_aktif_flag = st.session_state.get("_toplam_aktif", False)
    _grp_gizli = set(st.session_state.get("_rbar_grp_gizli", []))
    _grp_sira_def = ["genel","iletisim","asama1","asama2","asama3","sonuc"]
    _grp_sira = list(st.session_state.get("_rbar_grp_sira", _grp_sira_def.copy()))
    for _gs in _grp_sira_def:
        if _gs not in _grp_sira: _grp_sira.append(_gs)
    _ayar_modu = st.session_state.get("_rbar_ayar_modu", False)

    def _asama_ikon(a):
        _m = {"arama":"📞","tekrar ara":"📲","mesaj":"💬","mail":"📧","e-mail":"📧",
              "whatsapp":"💬","takip":"📌","randevu":"📅","ilk temas":"👋",
              "teklif":"📄","fiyat hazırla":"💰","fiyat":"💰","deneme":"🧪",
              "sözleşme":"📝","devam ediyor":"⏳","kazanıldı":"🏆","kazanildi":"🏆",
              "kaybedildi":"❌","negatif":"👎"}
        for k,v in _m.items():
            if k in a.lower(): return v
        return "🔹"

    def _durum_ikon(d):
        return {"Portföy":"📦","Özel Müşteri":"⭐","Aşamasız":"📋","Toplam":"📊"}.get(d,"🔹")

    def _asama_norm(s):
        """Büyük/küçük harf ve Türkçe karakter farkını yok sayarak karşılaştırma için normalize eder"""
        return (str(s or "").strip().upper()
                .replace("İ","I").replace("Ş","S").replace("Ğ","G")
                .replace("Ü","U").replace("Ö","O").replace("Ç","C"))

    def _asama_sayi(ad):
        """islem_asamasi kolonundan say — AŞAMA grubu (Arama vs.)"""
        if "islem_asamasi" not in df.columns: return 0
        _ad_n = _asama_norm(ad)
        return len(df[df["islem_asamasi"].apply(_asama_norm) == _ad_n])

    def _kolon_sayi(kolon, ad):
        """Belirtilen kolonda değeri say (büyük/küçük harf farkı yok sayılır)"""
        if kolon not in df.columns: return 0
        _ad_n = _asama_norm(ad)
        return len(df[df[kolon].apply(_asama_norm) == _ad_n])

    def _durum_sayi(ad):
        if ad == "Toplam": return len(df)
        if "durum" not in df.columns: return 0
        return len(df[df["durum"]==ad])

    def _asamasiz_sayi():
        if df.empty: return 0
        _mask = pd.Series([True]*len(df), index=df.index)
        for _k in ["islem_asamasi","asama1","asama2","asama3"]:
            if _k in df.columns:
                _mask = _mask & (df[_k].isna() | df[_k].astype(str).str.strip().isin(["","None","nan"]))
        return int(_mask.sum())

    # grp1 = islem_asamasi (Arama, Tekrar Ara, E-Mail)
    _grp1_toplam = sum(_asama_sayi(a) for a in _grp1_asama)
    # grp2 = asama1 (Randevu)
    _grp2_toplam = sum(_kolon_sayi("asama1", a) for a in _grp2_asama)
    # grp3 = asama2 (Teklif)
    _grp3_toplam = sum(_kolon_sayi("asama2", a) for a in _grp3_asama)
    # grp4 = asama3 (Takip, Fiyat Hazırla, Deneme, Sözleşme)
    _grp4_toplam = sum(_kolon_sayi("asama3", a) for a in _grp4_asama)
    # grp5 = sonuc (Kazanıldı, Kaybedildi, Devam Ediyor)
    _grp5_toplam = sum(_kolon_sayi("sonuc", a) for a in _grp5_asama)

    # Genel grup
    _genel_items = [
        ("📊","Toplam", len(df), "toplam", _toplam_aktif_flag),
        ("📦","Portföy", _durum_sayi("Portföy"), "durum_Portföy", "Portföy" in _aktif_fil_durum),
        ("⭐","Özel Müşteri", _durum_sayi("Özel Müşteri"), "durum_Özel Müşteri", "Özel Müşteri" in _aktif_fil_durum),
        ("📋","Aşamasız", _asamasiz_sayi(), "asamasiz", st.session_state.get("_asamasiz_aktif",False)),
    ]
    for _dn in tum_durum_opts:
        if str(_dn).upper() in ["NONE","NAN",""] or _dn in ["Portföy","Özel Müşteri"]: continue
        _dn_sayi = _durum_sayi(_dn)
        if _dn_sayi <= 0: continue  # 0 kayıtlı durum tipleri üst raporda gösterilmez
        _genel_items.append((_durum_ikon(_dn), _dn, _dn_sayi, f"durum_{_dn}", _dn in _aktif_fil_durum))

    # ── Gerçek Mesaj sayısı — islem_kaydi tablosundan (WhatsApp/Email gönderim
    # kayıtları) + Cari Liste'de MANUEL yazılan override değerleri. Cari
    # Liste'de görünen "💬 N" değerleriyle BİREBİR aynı toplamı versin diye
    # override'lar da dahil ediliyor (sadece gerçek kayıt sayısı değil).
    @st.cache_data(ttl=60, show_spinner=False)
    def _rbar_mesaj_toplam_yukle():
        _toplam = 0
        try:
            _sb_rbm = get_sb_client()
            if not _sb_rbm:
                return 0
            # 1) Her müşterinin GERÇEK mesaj sayısı (islem_kaydi'den)
            _r_rbm = _sb_rbm.table("islem_kaydi").select("musteri_id,islem_turu").in_(
                "islem_turu", ["WhatsApp Teklif", "Email Teklif"]).execute()
            import collections as _rbmcol
            _gercek_sayac = _rbmcol.Counter([str(r.get("musteri_id","")) for r in (_r_rbm.data or [])])
            # 2) Manuel override'lar (Cari Liste'de elle yazılmış değerler)
            _override_map = {}
            try:
                _r_rbov = _sb_rbm.table("kullanici_tercih").select("deger").eq(
                    "kullanici","__liste_ui__").eq("anahtar","_mesaj_manuel_override").execute()
                if _r_rbov.data:
                    import json as _rbovj
                    _override_map = _rbovj.loads(_r_rbov.data[0]["deger"])
            except Exception:
                pass
            # 3) Sistemdeki TÜM müşteri id'leri üzerinden — override varsa onu,
            # yoksa gerçek sayıyı topla (Cari Liste'de gösterilenle aynı mantık)
            _tum_idler = set(_gercek_sayac.keys()) | set(_override_map.keys())
            for _mid in _tum_idler:
                if _mid in _override_map:
                    try: _toplam += int("".join(ch for ch in str(_override_map[_mid]) if ch.isdigit()) or 0)
                    except Exception: pass
                else:
                    _toplam += _gercek_sayac.get(_mid, 0)
        except Exception:
            return 0
        return _toplam
    _mesaj_gercek_toplam = _rbar_mesaj_toplam_yukle()

    @st.cache_data(ttl=60, show_spinner=False)
    def _rbar_mesaj_id_seti_yukle():
        """'💬 Mesaj' kutusuna tıklanınca filtrelemek için — mesaj toplamıyla
        AYNI mantık (gerçek islem_kaydi + manuel override), ama toplam yerine
        hangi müşteri id'lerinin dahil olduğunu (id seti) döndürür."""
        try:
            _sb_rbm2 = get_sb_client()
            if not _sb_rbm2:
                return set()
            _r_rbm2 = _sb_rbm2.table("islem_kaydi").select("musteri_id,islem_turu").in_(
                "islem_turu", ["WhatsApp Teklif", "Email Teklif"]).execute()
            _gercek_idler = {str(r.get("musteri_id","")) for r in (_r_rbm2.data or []) if r.get("musteri_id")}
            _override_idler = set()
            try:
                _r_rbov2 = _sb_rbm2.table("kullanici_tercih").select("deger").eq(
                    "kullanici","__liste_ui__").eq("anahtar","_mesaj_manuel_override").execute()
                if _r_rbov2.data:
                    import json as _rbovj2
                    _override_map2 = _rbovj2.loads(_r_rbov2.data[0]["deger"])
                    _override_idler = set(_override_map2.keys())
            except Exception:
                pass
            return _gercek_idler | _override_idler
        except Exception:
            return set()


    # ── "2. AŞAMA — Teklif" sayısı — Cari Liste'deki "🧾 Teklif" kolonunda
    # görünen TÜM sayıların TOPLAMI (tekil firma sayısı DEĞİL). Bir firmanın
    # 4 teklifi varsa 4 olarak, 2 teklifi varsa 2 olarak sayılır, hepsi
    # toplanır. Kaynak: gerçek teklifler tablosu + manuel override (hangisi
    # varsa o kullanılır — Cari Liste'de gösterilenle birebir aynı mantık).
    # ÖNEMLİ: sadece AKTİF (silinmemiş, Cari Liste'de görünen) müşterilerle
    # sınırlanır — aksi halde silinmiş/eski müşterilere ait yetim teklif
    # kayıtları da toplama karışıp sayıyı şişiriyordu (232 gibi yanlış sayı).
    _aktif_id_seti = set(str(int(x)) for x in df["id"].dropna().tolist()) if not df.empty and "id" in df.columns else set()

    @st.cache_data(ttl=60, show_spinner=False)
    def _rbar_teklif_toplam_yukle(_aktif_idler):
        # ID'leri normalize eden yardımcı — bazı kayıtlarda musteri_id "123" yerine
        # "123.0" gibi ondalıklı/farklı biçimde saklanmış olabilir; bu farklar
        # eşleşmeyi kaçırıp gerçek teklifleri toplamdan düşürüyordu (rapor düşük
        # çıkıyordu). Her ID'yi aynı sade tam sayı metnine çeviriyoruz.
        def _id_norm_f(_v):
            _s = str(_v).strip()
            try:
                return str(int(float(_s)))
            except Exception:
                return _s
        _toplam = 0
        try:
            _sb_rbf = get_sb_client()
            if not _sb_rbf:
                return 0
            _r_rbf = _sb_rbf.table("teklifler").select("musteri_id").execute()
            import collections as _rbfcol
            _gercek_sayac_f = _rbfcol.Counter([_id_norm_f(r.get("musteri_id","")) for r in (_r_rbf.data or [])])
            _override_map_f_ham = {}
            try:
                _r_rbfov = _sb_rbf.table("kullanici_tercih").select("deger").eq(
                    "kullanici","__liste_ui__").eq("anahtar","_teklif_manuel_override").execute()
                if _r_rbfov.data:
                    import json as _rbfovj
                    _override_map_f_ham = _rbfovj.loads(_r_rbfov.data[0]["deger"])
            except Exception:
                pass
            _override_map_f = {_id_norm_f(k): v for k, v in _override_map_f_ham.items()}
            _aktif_idler_norm = set(_id_norm_f(x) for x in _aktif_idler)
            _tum_idler_f = (set(_gercek_sayac_f.keys()) | set(_override_map_f.keys())) & _aktif_idler_norm
            for _mid in _tum_idler_f:
                if _mid in _override_map_f:
                    try: _toplam += int("".join(ch for ch in str(_override_map_f[_mid]) if ch.isdigit()) or 0)
                    except Exception: pass
                else:
                    _toplam += _gercek_sayac_f.get(_mid, 0)
        except Exception:
            return 0
        return _toplam
    _teklif_firma_sayisi = _rbar_teklif_toplam_yukle(frozenset(_aktif_id_seti))

    # "Tekrar Ara" ve aşama-bazlı "Mesaj" kutuları kullanıcı isteğiyle KALDIRILDI —
    # NOT: bu sadece görünümden kaldırma; _grp1_asama'nın kendisine dokunulmadı,
    # çünkü o değişken "Aşamasız" hesabında da kullanılıyor (o kayıtlar hâlâ
    # aşamalı sayılmaya devam etsin, "aşamasız"a düşmesinler diye).
    _grp1_asama_goster = [a for a in _grp1_asama if a not in ["Tekrar Ara", "Mesaj"]]
    _mesaj_gercek_aktif_flag = st.session_state.get("_mesaj_gercek_aktif", False)

    _grp_data = {
        "genel":    ("📊","GENEL",    None, _genel_items),
        "genel":    ("📊","GENEL",    None, _genel_items),
        "iletisim": ("🤝","İlk Temas",    None, [((_asama_ikon(a),a,_asama_sayi(a),f"asama_{a}",a in _aktif_fil_asama)) for a in _grp1_asama_goster] + [("💬","Mesaj",_mesaj_gercek_toplam,"mesaj_gercek",_mesaj_gercek_aktif_flag)]),
        "asama1":   ("📅","1. AŞAMA", None, [((_asama_ikon(a),a,_kolon_sayi("asama1",a),f"asama1_{a}",False)) for a in _grp2_asama]),
        "asama2":   ("📄","2. AŞAMA", None, [((_asama_ikon(a),a,_kolon_sayi("asama2",a),f"asama2_{a}",False)) for a in _grp3_asama]),
        "asama3":   ("🧪","3. AŞAMA", None, [((_asama_ikon(a),a,_kolon_sayi("asama3",a),f"asama3_{a}",False)) for a in _grp4_asama]),
        "sonuc":    ("🏆","SONUÇ",    None, [((_asama_ikon(a),a,_kolon_sayi("sonuc",a),f"sonuc_{a}",False)) for a in _grp5_asama]),
    }
    # HTML oluştur - 2 satırlı tablo
    # ── Rapor barı SABİT %100 genişlikte kalır, kendi başına kaymaz/kaydırılmaz.
    # Cari Liste tablosu, kendi ayrı kolon-genişliği formülüyle (aşağıda _w())
    # buna uymaya çalışır; rapor barı bunun için değişken hale getirilmez.
    _html = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.19.0/dist/tabler-icons.min.css">'
    _html += '<div style="overflow-x:hidden;margin-bottom:4px;"><table style="border-collapse:separate;border-spacing:0;font-family:inherit;font-size:12px;width:100%;">'

    # 1. SATIR — grup başlıkları
    _html += '<thead><tr>'
    _ilk = True
    for _gid in _grp_sira:
        if _gid not in _grp_data or _gid in _grp_gizli: continue
        _ikon,_lbl,_top,_items = _grp_data[_gid]
        if not _items: continue
        _span = len(_items)
        _top_txt = f" {_top}" if _top is not None else ""
        # Grup arası boşluk
        _border_l = "border-left:2px solid #cbd5e1;" if not _ilk else ""
        _ilk = False
        if _ayar_modu:
            _idx = _grp_sira.index(_gid)
            _n = len([g for g in _grp_sira if g in _grp_data and _grp_data[g][3] and g not in _grp_gizli])
            _sol = "opacity:.3;" if _idx==0 else "cursor:pointer;"
            _sag = "opacity:.3;" if _idx>=_n-1 else "cursor:pointer;"
            _h  = f'<th colspan="{_span}" style="border:0.5px solid #e2e8f0;{_border_l}padding:0;background:#fef9c3;text-align:center;">'
            _h += f'<div style="display:flex;align-items:center;justify-content:space-between;padding:2px 4px;">'
            _h += f'<span onclick="gs(\'{_gid}\',\'l\')" style="font-size:10px;{_sol}">◀</span>'
            _h += f'<b style="font-size:10px;color:#374151;">{_ikon} {_lbl}{_top_txt}</b>'
            _h += f'<span onclick="gs(\'{_gid}\',\'r\')" style="font-size:10px;{_sag}">▶</span>'
            _h += f'<span onclick="gg(\'{_gid}\')" style="font-size:11px;cursor:pointer;">🙈</span>'
            _h += '</div></th>'
        else:
            _h = f'<th colspan="{_span}" style="border:0.5px solid #e2e8f0;{_border_l}padding:4px 10px;background:#f8fafc;text-align:center;font-size:12px;font-weight:700;color:#374151;white-space:nowrap;">{_ikon} {_lbl}{_top_txt}</th>'
        _html += _h

    # Gizli gruplar için ayar modunda göster
    if _ayar_modu:
        for _gid in _grp_sira:
            if _gid in _grp_gizli and _gid in _grp_data:
                _ikon,_lbl,_top,_items = _grp_data[_gid]
                _html += "<th onclick=\"gg('" + _gid + "')\" style=\"border:0.5px solid #e2e8f0;padding:3px 5px;background:#fee2e2;cursor:pointer;font-size:9px;white-space:nowrap;\">👁 " + _lbl + "</th>"

    _cl_view2 = st.session_state.get("_cl_view","liste")
    _gear_bg = "#fef9c3" if _ayar_modu else "#f8fafc"
    _html += '</tr></thead>'

    # 2. SATIR — sayılar
    _html += '<tbody><tr>'
    _ilk2 = True
    for _gid in _grp_sira:
        if _gid not in _grp_data or _gid in _grp_gizli: continue
        _ikon,_lbl,_top,_items = _grp_data[_gid]
        if not _items: continue
        _grp_ilk = True
        for _ic, _ad, _sayi, _key, _aktif in _items:
            _bg = "background:#dbeafe;" if _aktif else "background:#fff;"
            _tc = "color:#1d4ed8;font-weight:700;" if _aktif else "color:#0f172a;"
            _border_l2 = ("border-left:2px solid #cbd5e1;" if not _ilk2 and _grp_ilk else "")
            _td_onclick = f"sf('{_key}')"
            _html += f'<td onclick="{_td_onclick}" style="border:0.5px solid #f1f5f9;{_border_l2}padding:4px 7px;text-align:center;cursor:pointer;white-space:nowrap;{_bg}vertical-align:middle;min-width:50px;">'
            _html += f'<div style="font-size:18px;line-height:1;margin-bottom:4px;">{_ic}</div>'
            _html += f'<div style="font-size:14px;font-weight:600;{_tc};line-height:1;">{_sayi}</div>'
            _html += f'<div style="font-size:14px;font-weight:500;color:#374151;line-height:1;">{_ad}</div>'
            _html += '</td>'
            _grp_ilk = False
            _ilk2 = False

    _cl_view2 = st.session_state.get("_cl_view","liste")
    _html += '</tr></tbody></table></div>'
    import json as _rjson2
    _html += f"""<script>
var _s={_rjson2.dumps(_grp_sira)};
function sf(k){{
  if(k==='_ayar_toggle'){{
    var u=new URL(window.parent.location.href);
    u.searchParams.set("_rfil","_ayar_toggle");
    window.parent.location.replace(u.toString());
    return;
  }}
  var u=new URL(window.parent.location.href);u.searchParams.set("_rfil",k);window.parent.location.replace(u.toString());
}}
function gg(id){{var u=new URL(window.parent.location.href);var g=JSON.parse(u.searchParams.get("_grp_gizli")||"[]");if(g.includes(id))g=g.filter(x=>x!==id);else g.push(id);u.searchParams.set("_grp_gizli",JSON.stringify(g));window.parent.location.replace(u.toString());}}
function gs(id,dir){{var u=new URL(window.parent.location.href);var s=JSON.parse(u.searchParams.get("_grp_sira")||JSON.stringify(_s));var i=s.indexOf(id);if(dir==="l"&&i>0){{var t=s[i-1];s[i-1]=s[i];s[i]=t;}}else if(dir==="r"&&i<s.length-1){{var t=s[i+1];s[i+1]=s[i];s[i]=t;}}u.searchParams.set("_grp_sira",JSON.stringify(s));window.parent.location.replace(u.toString());}}
</script>"""
    st.markdown(_html, unsafe_allow_html=True)


    # Grup ayar param
    _qp_grp_gizli = st.query_params.get("_grp_gizli","")
    _qp_grp_sira  = st.query_params.get("_grp_sira","")
    if _qp_grp_gizli or _qp_grp_sira:
        if _qp_grp_gizli:
            try: st.session_state["_rbar_grp_gizli"] = _rjson.loads(_qp_grp_gizli)
            except: pass
        if _qp_grp_sira:
            try: st.session_state["_rbar_grp_sira"] = _rjson.loads(_qp_grp_sira)
            except: pass
        st.query_params.clear(); st.rerun()

    # Query param'dan filtre oku
    _qp_rfil = st.query_params.get("_rfil", "")
    if _qp_rfil:
        st.query_params.clear()
        _fk_sfx_now = st.session_state.get("_filtre_reset_sayac", 0)

        def _rapor_kutuya_ekle(_hedef_key, _deger):
            """Üst rapor rozetine tıklanınca değeri ilgili filtre kutusuna (Aşama.../Durum...) ekler.
            Kutuda zaten varsa tekrar eklemez — hem tek tek hem toplu tıklama birikerek çalışır."""
            _cur = list(st.session_state.get(_hedef_key, []))
            if _deger not in _cur:
                _cur.append(_deger)
            st.session_state[_hedef_key] = _cur
            st.session_state[f"{_hedef_key}_{_fk_sfx_now}"] = _cur

        def _tekli_asama_temizle():
            """Eski tekli-kolon (1/2/3. Aşama) yedek filtrelerini temizler — genel kutuyla çakışmasın diye"""
            for _fk in ["_cl_fil_asama1", "_cl_fil_asama2", "_cl_fil_asama3", "_cl_fil_sonuc"]:
                st.session_state.pop(_fk, None)

        if _qp_rfil == "toplam":
            st.session_state["_toplam_aktif"] = True
            st.session_state["_asamasiz_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = False
            st.session_state["_filtre_reset_sayac"] = st.session_state.get("_filtre_reset_sayac",0)+1
            _tekli_asama_temizle()
            for _fk in ["_cl_fil_durum_multi","_cl_fil_asama_multi","_cl_fil_il_multi","_cl_fil_ilce_multi","_cl_fil_temsilci_multi"]:
                st.session_state.pop(_fk, None)
        elif _qp_rfil == "asamasiz":
            st.session_state["_asamasiz_aktif"] = True
            st.session_state["_toplam_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = False
            _tekli_asama_temizle()
            st.session_state.pop("_cl_fil_durum_multi", None)
            st.session_state["_cl_fil_asama_multi"] = []
        elif _qp_rfil == "mesaj_gercek":
            # "💬 Mesaj" kutusuna tıklanınca — gerçekten mesaj/whatsapp/email
            # kaydı olan (veya manuel override edilmiş) müşterileri filtrele.
            st.session_state["_toplam_aktif"] = False
            st.session_state["_asamasiz_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = True
            _tekli_asama_temizle()
            st.session_state.pop("_cl_fil_durum_multi", None)
            st.session_state["_cl_fil_asama_multi"] = []
        elif _qp_rfil.startswith("durum_"):
            _d = _qp_rfil[6:]
            st.session_state["_toplam_aktif"] = False
            st.session_state["_asamasiz_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = False
            _rapor_kutuya_ekle("_cl_fil_durum_multi", _d)
        elif _qp_rfil.startswith("asama_"):
            _a = _qp_rfil[6:]
            st.session_state["_toplam_aktif"] = False
            st.session_state["_asamasiz_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = False
            _rapor_kutuya_ekle("_cl_fil_asama_multi", _a)
        elif _qp_rfil.startswith("asama1_"):
            _a = _qp_rfil[7:]
            st.session_state["_toplam_aktif"] = False
            st.session_state["_asamasiz_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = False
            _tekli_asama_temizle()
            st.session_state["_cl_fil_asama1"] = _a
            _rapor_kutuya_ekle("_cl_fil_asama_multi", _a)
        elif _qp_rfil.startswith("asama2_"):
            _a = _qp_rfil[7:]
            st.session_state["_toplam_aktif"] = False
            st.session_state["_asamasiz_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = False
            _tekli_asama_temizle()
            st.session_state["_cl_fil_asama2"] = _a
            _rapor_kutuya_ekle("_cl_fil_asama_multi", _a)
        elif _qp_rfil.startswith("asama3_"):
            _a = _qp_rfil[7:]
            st.session_state["_toplam_aktif"] = False
            st.session_state["_asamasiz_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = False
            _tekli_asama_temizle()
            st.session_state["_cl_fil_asama3"] = _a
            _rapor_kutuya_ekle("_cl_fil_asama_multi", _a)
        elif _qp_rfil.startswith("sonuc_"):
            _a = _qp_rfil[6:]
            st.session_state["_toplam_aktif"] = False
            st.session_state["_asamasiz_aktif"] = False
            st.session_state["_mesaj_gercek_aktif"] = False
            _tekli_asama_temizle()
            st.session_state["_cl_fil_sonuc"] = _a
            _rapor_kutuya_ekle("_cl_fil_asama_multi", _a)
        st.rerun()

    # Kanban view
    _cl_view = st.session_state.get("_cl_view", "liste")

    if _cl_view == "kanban":
        # ── KART TIKLAMASI — query param ile müşteri seç ─────────────────────
        try:
            if "kb_not_id" in st.query_params:
                _kb_qid2 = int(st.query_params["kb_not_id"])
                st.query_params.clear()
                _kb_row2 = df[df["id"] == _kb_qid2]
                if not _kb_row2.empty:
                    _kb_firma2 = str(_kb_row2.iloc[0]["firma"])
                    st.session_state["kb_alt_sec"] = f"[{_kb_qid2}] {_kb_firma2}"
                st.rerun()
        except: pass
        # ── KANBAN GÖRÜNÜMÜ ───────────────────────────────────────────────────
        import streamlit.components.v1 as _kb_comp
        import json as _kbj

        # Veriyi hazırla — silindi olmayanlar
        _kb_df = df.copy() if not df.empty else pd.DataFrame()
        if not _kb_df.empty and "silindi" in _kb_df.columns:
            _kb_df = _kb_df[_kb_df["silindi"].astype(str).isin(["0","False","","nan","None"]) | _kb_df["silindi"].isna()]

        _kanban_asama_listesi = tum_asama_opts if tum_asama_opts else (sorted(_kb_df["islem_asamasi"].dropna().unique().tolist()) if "islem_asamasi" in _kb_df.columns else [])
        _kanban_renk = ["#f59e0b","#2563eb","#16a34a","#7c3aed","#0891b2","#dc2626","#f97316","#0d9488","#6366f1","#84cc16","#ec4899","#14b8a6"]

        # Not sayılarını al
        try:
            _sb_kbn = get_sb_client()
            _kb_not_data = _sb_kbn.table("cari_aciklamalar").select("cari_id,aciklama").execute().data or [] if _sb_kbn else []
            _kb_not_data = [r for r in _kb_not_data if not str(r.get("aciklama","") or "").startswith("##YETKILI##")]
            import collections as _kbc2
            _kb_not_sayac = _kbc2.Counter([str(r["cari_id"]) for r in _kb_not_data])
        except: _kb_not_sayac = {}

        _kanban_kolonlar = []
        for _ki, _ka in enumerate(_kanban_asama_listesi):
            _kdf = _kb_df[_kb_df["islem_asamasi"] == _ka] if "islem_asamasi" in _kb_df.columns else pd.DataFrame()
            _kartlar = []
            for _, _kr in _kdf.iterrows():
                try: _hedef = float(_kr.get("beklenen_ciro",0) or 0)
                except: _hedef = 0
                _kid = int(_kr.get("id",0) or 0)
                _kartlar.append({
                    "id": _kid,
                    "firma": str(_kr.get("firma","") or "")[:30],
                    "yetkili": str(_kr.get("yetkili","") or "")[:20],
                    "gsm": _tel_gruplu(str(_kr.get("gsm","") or "")),
                    "il": str(_kr.get("il","") or ""),
                    "ilce": str(_kr.get("ilce","") or ""),
                    "durum": str(_kr.get("durum","") or ""),
                    "hedef": f"{_hedef:,.0f}".replace(",",".") if _hedef > 0 else "",
                    "not_sayi": int(_kb_not_sayac.get(str(_kid), 0)),
                })
            _kanban_kolonlar.append({
                "asama": _ka,
                "renk": _kanban_renk[_ki % len(_kanban_renk)],
                "sayi": len(_kartlar),
                "kartlar": _kartlar[:50]
            })

        _kanban_filtreli = _kanban_kolonlar
        _kanban_json = _kbj.dumps(_kanban_filtreli, ensure_ascii=False)

        _kanban_html = ("""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,sans-serif;}
html,body{height:100%;overflow:hidden;}
body{background:#f1f5f9;padding:6px;}
.board{display:flex;gap:6px;height:calc(100vh - 16px);overflow-x:auto;overflow-y:hidden;}
.board::-webkit-scrollbar{height:5px;}
.board::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:3px;}
.col{flex:1 1 0;min-width:160px;background:#f8fafc;border-radius:10px;border:0.5px solid #e2e8f0;display:flex;flex-direction:column;height:100%;overflow:hidden;}
.col-hdr{padding:9px 11px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;}
.col-name{font-size:11px;font-weight:700;color:white;word-break:break-word;}
.col-badge{background:rgba(255,255,255,.3);color:white;border-radius:20px;padding:1px 7px;font-size:10px;font-weight:700;flex-shrink:0;margin-left:4px;}
.col-body{padding:6px;display:flex;flex-direction:column;gap:4px;overflow-y:auto;flex:1;min-height:0;}
.col-body::-webkit-scrollbar{width:2px;}
.col-body::-webkit-scrollbar-thumb{background:#e2e8f0;}
.kart{background:white;border-radius:7px;padding:9px;border:0.5px solid #e2e8f0;}
.kart:hover{border-color:#93c5fd;box-shadow:0 1px 6px rgba(0,0,0,.08);}
.firma{font-size:11px;font-weight:700;color:#0f172a;margin-bottom:2px;line-height:1.3;}
.ytkl{font-size:10px;color:#64748b;margin-bottom:1px;}
.gsm{font-size:10px;color:#2563eb;margin-bottom:2px;font-weight:500;}
.yer{font-size:9px;color:#94a3b8;margin-bottom:3px;}
.dchip{display:inline-block;padding:1px 6px;border-radius:20px;font-size:9px;background:#f1f5f9;color:#374151;margin-bottom:3px;}
.footer{display:flex;justify-content:space-between;align-items:center;padding-top:5px;border-top:0.5px solid #f1f5f9;}
.hedef{font-size:10px;font-weight:700;color:#16a34a;}
.nbtn{background:#eff6ff;color:#2563eb;border:none;border-radius:4px;padding:2px 7px;font-size:9px;cursor:pointer;font-weight:600;}
.nbtn:hover{background:#dbeafe;}
.bos{padding:12px;text-align:center;font-size:11px;color:#cbd5e1;}
</style></head><body>
<div class="board" id="board"></div>
<script>
var data=""" + _kanban_json + """;
var board=document.getElementById('board');
if(!data||!data.length){board.innerHTML='<div class="bos">Veri yok</div>';}
data.forEach(function(kol){
  var col=document.createElement('div');col.className='col';
  var h='<div class="col-hdr" style="background:'+kol.renk+'"><span class="col-name">'+kol.asama+'</span><span class="col-badge">'+kol.sayi+'</span></div>';
  var b='<div class="col-body">';
  if(!kol.kartlar.length) b+='<div class="bos">Boş</div>';
  kol.kartlar.forEach(function(k){
    var yer=[k.il,k.ilce].filter(Boolean).join('/');
    b+='<div class="kart" onclick="kartSec('+k.id+')">';
    b+='<div class="firma">'+k.firma+'</div>';
    if(k.yetkili) b+='<div class="ytkl">👤 '+k.yetkili+'</div>';
    if(k.gsm) b+='<div class="gsm">📞 '+k.gsm+'</div>';
    if(yer) b+='<div class="yer">📍 '+yer+'</div>';
    if(k.durum) b+='<span class="dchip">'+k.durum+'</span><br>';
    b+='<div class="footer">';
    b+=k.hedef?'<span class="hedef">'+k.hedef+' ₺</span>':'<span></span>';
    var notLbl=k.not_sayi>0?'📋 '+k.not_sayi+' not':'📋 Not';
    b+='<span class="nbtn">'+notLbl+'</span>';
    b+='</div></div>';
  });
  b+='</div>';
  col.innerHTML=h+b;
  board.appendChild(col);
});
function kartSec(id){
  var base=window.parent.location.href.split('?')[0];
  window.parent.location.href=base+'?kb_not_id='+id;
}
</script></body></html>""")

        import streamlit.components.v1 as _kbc
        _kbc.html(_kanban_html, height=640, scrolling=False)


        # Not butonu — query param ile dialog açıldı (yukarda)
        _ = None

        # ── KANBAN ALT PANEL — tek satır ─────────────────────────────────────
        st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
        _kb_opts = ["— Müşteri seçin —"] + [f"[{int(r['id'])}] {r.get('firma','')}" for _, r in _kb_df.sort_values("firma").iterrows()]
        _kb_sec_def = st.session_state.get("kb_alt_sec", "— Müşteri seçin —")
        if _kb_sec_def not in _kb_opts: _kb_sec_def = "— Müşteri seçin —"

        _kp1, _kp2, _kp3, _kp4 = st.columns([3, 2, 1, 1])
        _kb_sec = _kp1.selectbox("m", _kb_opts, index=_kb_opts.index(_kb_sec_def), key="kb_alt_sec", label_visibility="collapsed")

        if _kb_sec != "— Müşteri seçin —":
            _kb_sel_id = int(_kb_sec.split("]")[0].replace("[","").strip())
            _kb_sel_row = _kb_df[_kb_df["id"] == _kb_sel_id]
            _kb_sel_firma = str(_kb_sel_row.iloc[0]["firma"]) if not _kb_sel_row.empty else ""
            _kb_sel_asama = str(_kb_sel_row.iloc[0].get("islem_asamasi","") or "") if not _kb_sel_row.empty else ""

            _asama_idx = tum_asama_opts.index(_kb_sel_asama) if _kb_sel_asama in tum_asama_opts else 0
            _kb_yeni_asama = _kp2.selectbox("a", tum_asama_opts, index=_asama_idx, key="kb_asama_sec", label_visibility="collapsed")

            if _kp3.button("✅ Kaydet", key="kb_asama_kaydet", use_container_width=True, type="primary"):
                try:
                    _sb_kba = get_sb_client()
                    if _sb_kba:
                        _sb_kba.table("cari_kartlar").update({"islem_asamasi": _kb_yeni_asama}).eq("id", _kb_sel_id).execute()
                    try: db_read.clear()
                    except: pass
                    st.toast(f"✅ {_kb_sel_firma} → {_kb_yeni_asama}", icon="✅")
                    st.rerun()
                except Exception as _kbae:
                    st.error(f"Hata: {_kbae}")

            if _kp4.button("📋 Not", key="kb_not_ac", use_container_width=True):
                not_dialog(_kb_sel_id, _kb_sel_firma)

        st.caption(f"📋 Kanban — {len(_kb_df)} müşteri · {len(_kanban_filtreli)} sütun")
        st.stop()

    # ── GELİŞMİŞ FİLTRE PANEL ────────────────────────────────────────────────
    _cok_secili_idler = set()
    with st.expander("🔍 Filtreler & Arama", expanded=False):
        # ── TEK SATIR FİLTRE ───────────────────────────────────────────────────
        if st.session_state.get("kart_sec_reset"):
            st.session_state.pop("kart_sec_reset", None)
            st.session_state.pop("kart_sec", None)

        kart_opts_inline = ["-- Müşteri Seçin --", "🔵 Tüm Firmalar"]
        if not df.empty and "firma" in df.columns and "id" in df.columns:
            kart_opts_inline += [f"[{int(i)}] {f}" for i, f in zip(df["id"], df["firma"]) if str(f) not in ["","nan","None"]]
        if st.session_state.get("kart_sec_reset"):
            st.session_state.pop("kart_sec_reset", None)
            st.session_state.pop("kart_sec", None)

        # ── TEK SATIR — hepsi aynı hizada, eşit genişlikte: Yeni firma kontrol,
        # Özel, Aşama, Durum, İl, İlçe, Çoklu firma, Güncelleme Tarihi ─────────
        _fc = st.columns(8)

        # ── YENİ FİRMA KONTROLÜ — "Satır Ekle" ile elle firma adı yazmadan önce,
        # aynı/benzer isimde zaten kayıtlı müşteri var mı diye anlık arama.
        # ÖNEMLİ: Kelime kelime ayrı ayrı arama YAPILMAZ — yazılan ifade (boşluk/nokta
        # farkları yok sayılarak) ART ARDA/BÜTÜN olarak firma adında geçiyor mu diye
        # bakılır. Örn. "KAPKA HEDİ" yazınca sadece "KAPKA HEDİYELİK..." gibi bu ifadeyi
        # ard arda içeren firmalar gelir; sadece "HEDİ" geçen alakasız firmalar gelmez.
        _yf_ara = _fc[0].text_input("yf", placeholder="🔍 Yeni firma kontrol...", key="_cl_yeni_firma_ara", label_visibility="collapsed")
        _ozel_opts = sorted(df["rakip_firma"].dropna().astype(str).unique().tolist()) if "rakip_firma" in df.columns else []
        _ozel_opts = [x for x in _ozel_opts if x not in ["", "nan", "None"]]
        _ozel_sec = _fc[1].multiselect("oz", _ozel_opts, key="_cl_fil_ozel_multi", placeholder="🔍 Özel filtrele...", label_visibility="collapsed")

        # "Müşteri Seçin" kutusu kullanıcı isteğiyle kaldırıldı — sabit nötr
        # değerde tutuluyor (aşağıdaki tekli-müşteri seçim mantığı bu değere
        # bağlı olduğu için değişkeni koruyoruz, sadece görünür kutuyu kaldırdık).
        secili_kart_inline = "-- Müşteri Seçin --"
        # Genel serbest metin arama kutusu kullanıcı isteğiyle kaldırıldı — ara_txt
        # boş sabit tutuluyor (aşağıdaki filtreleme mantığı buna bağlı olduğu için
        # değişkeni koruyoruz, sadece görünür arama kutusunu kaldırdık).
        ara_txt = ""

        _fk_sfx = st.session_state.get("_filtre_reset_sayac", 0)
        _asama_def = [] if st.session_state.get("_filtre_sifirla_flag") else [x for x in st.session_state.get("_cl_fil_asama_multi",[]) if x in tum_asama_opts]
        _asama_sec = _fc[2].multiselect("a", tum_asama_opts, default=_asama_def, key=f"_cl_fil_asama_multi_{_fk_sfx}", placeholder="Aşama...", label_visibility="collapsed")
        st.session_state["_cl_fil_asama_multi"] = _asama_sec
        # Kutudan çıkarılmış/değiştirilmiş bir değer için eski tekli-kolon yedeği (asama1/2/3/sonuc) takılı kalmasın
        for _fk_stale in ["_cl_fil_asama1", "_cl_fil_asama2", "_cl_fil_asama3", "_cl_fil_sonuc"]:
            _fv_stale = st.session_state.get(_fk_stale)
            if _fv_stale and _fv_stale not in _asama_sec:
                st.session_state.pop(_fk_stale, None)

        _fk_sfx = st.session_state.get("_filtre_reset_sayac", 0)
        _durum_opts_tumu = [x for x in tum_durum_opts if str(x).upper() not in ["NONE","NAN",""]]
        _durum_def = [] if st.session_state.get("_filtre_sifirla_flag") else [x for x in st.session_state.get("_cl_fil_durum_multi",[]) if x in _durum_opts_tumu]
        _durum_sec_raw = _fc[3].multiselect("d", _durum_opts_tumu, default=_durum_def, key=f"_cl_fil_durum_multi_{_fk_sfx}", placeholder="Durum...", label_visibility="collapsed")
        st.session_state["_cl_fil_durum_multi"] = _durum_sec_raw
        _durum_sec = _durum_sec_raw

        filtre_seg = "Tümü"

        _il_opts = sorted(df["il"].dropna().astype(str).unique().tolist()) if "il" in df.columns else []
        _il_def  = [x for x in st.session_state.get("_cl_fil_il_multi",[]) if x in _il_opts]
        _il_sec  = _fc[4].multiselect("i", _il_opts, default=_il_def, key="_cl_fil_il_multi", placeholder="İl...", label_visibility="collapsed")

        _ilce_opts = sorted((df[df["il"].astype(str).isin(_il_sec)] if _il_sec else df)["ilce"].dropna().astype(str).unique().tolist()) if "ilce" in df.columns else []
        _ilce_opts = [x for x in _ilce_opts if x not in ["nan","None",""]]
        _ilce_sec  = _fc[5].multiselect("ilce", _ilce_opts, default=[x for x in st.session_state.get("_cl_fil_ilce_multi",[]) if x in _ilce_opts], key="_cl_fil_ilce_multi", placeholder="İlçe...", label_visibility="collapsed")

        _tem_sec = []
        siralama_kol = "Tarih↓"

        # ── Güncelleme Tarihi filtresi — ÇOKLU seçim, saatsiz (sadece gün).
        # "Çoklu firma" ile aynı mantık: seçenekler alt alta açılır, birden
        # fazla tarih seçilebilir. Filtre satırının en sonunda. ──────────────
        _guncelleme_tarih_sec = _fc[7].multiselect(
            "gt", _guncelleme_tarih_opts_str, key="_cl_fil_guncelleme_tarih_multi",
            placeholder="🔍 Güncelleme Tarihi...", label_visibility="collapsed"
        )

        # Manuel filtre kutularından biri (Aşama, Durum, Arama, İl, İlçe, Tarih) kullanıldıysa
        # 'Toplam' modu otomatik kapanır — aksi halde seçim görünür ama uygulanmaz
        if ara_txt or _asama_sec or _durum_sec or _il_sec or _ilce_sec or _guncelleme_tarih_sec or _ozel_sec:
            st.session_state["_toplam_aktif"] = False

        # Çoklu firma seçimi — filtre satırında son sütun
        _cok_sec_opts = [f"[{int(i)}] {f}" for i, f in zip(df["id"], df["firma"]) if str(f) not in ["","nan","None"]] if not df.empty and "firma" in df.columns else []
        # Taslak "Yükle" butonundan gelen bekleyen değeri — widget OLUŞTURULMADAN ÖNCE uygulanmalı
        # (Streamlit, widget instantiate edildikten SONRA aynı key'e session_state ataması yapılmasına izin vermiyor)
        if "_cok_tsk_bekleyen" in st.session_state:
            _bekleyen_idler = set(st.session_state.pop("_cok_tsk_bekleyen"))
            st.session_state["_cl_cok_secim"] = [o for o in _cok_sec_opts if int(o.split("]")[0].replace("[","").strip()) in _bekleyen_idler]
        _cok_secili_ham = _fc[6].multiselect("c", _cok_sec_opts, key="_cl_cok_secim", placeholder="🔍 Çoklu firma...", label_visibility="collapsed")
        _cok_secili_idler = set()
        for _cs in _cok_secili_ham:
            try: _cok_secili_idler.add(int(_cs.split("]")[0].replace("[","").strip()))
            except: pass

        # ── YENİ FİRMA KONTROLÜ SONUCU — arama kutusu artık tek satırlık filtre
        # barının içinde (yer kaplamasın diye); eşleşme bulununca sonuç/düzenleme
        # tablosu burada, filtre satırının hemen altında gösteriliyor.
        if _yf_ara and _yf_ara.strip() and "firma" in df.columns:
            def _yf_norm(_s):
                return (str(_s).upper().replace("İ", "I").replace("Ş", "S")
                        .replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C"))
            _yf_q_bosluksuz = _yf_norm(_yf_ara.strip()).replace(" ", "").replace(".", "")
            _yf_kaynak = df.copy()
            _yf_kaynak["_yf_norm_bs"] = (_yf_kaynak["firma"].apply(_yf_norm)
                                          .str.replace(" ", "", regex=False).str.replace(".", "", regex=False))
            _yf_eslesen = _yf_kaynak[_yf_kaynak["_yf_norm_bs"].apply(
                lambda _tam: bool(_yf_q_bosluksuz) and _yf_q_bosluksuz in _tam
            )]
            if not _yf_eslesen.empty:
                st.caption(f"⚠️ {len(_yf_eslesen)} eşleşen kayıt bulundu — kontrol edin.")
                _yf_kol = [c for c in ["id", "firma", "yetkili", "rakip_firma", "gsm", "sabit", "email", "adres", "ilce", "il", "aciklama"] if c in _yf_eslesen.columns]
                _yf_gosterilecek = _yf_eslesen[_yf_kol].head(15).copy()
                _yf_gosterilecek.insert(0, "Seç", False)
                _yf_duzenlenen = st.data_editor(
                    _yf_gosterilecek, use_container_width=True, hide_index=True,
                    disabled=["id"], key="_yf_duzenle_editor", num_rows="dynamic",
                    column_config={
                        "Seç": st.column_config.CheckboxColumn("Seç", default=False, width="small"),
                        "id": st.column_config.NumberColumn("ID", width="small"),
                        "firma": st.column_config.TextColumn("firma", width="small"),
                        "yetkili": st.column_config.TextColumn("yet", width="small"),
                        "rakip_firma": st.column_config.TextColumn("Öze", width="small"),
                        "gsm": st.column_config.TextColumn("gsm", width="small"),
                        "sabit": st.column_config.TextColumn("sabit", width="small"),
                        "email": st.column_config.TextColumn("em", width="small"),
                        "adres": st.column_config.TextColumn("adres", width="small"),
                        "ilce": st.column_config.TextColumn("ilce", width="small"),
                        "il": st.column_config.TextColumn("il", width="small"),
                        "aciklama": st.column_config.TextColumn("Açıklama", width="small"),
                    }
                )
                # ── NOT PANELİ — ana Cari Liste tablosuyla AYNI davranış: tek
                # satır "Seç" işaretlenince o müşterinin not paneli açılır. ──
                _yf_secili_satirlar = _yf_duzenlenen[_yf_duzenlenen["Seç"] == True]
                if len(_yf_secili_satirlar) == 1 and pd.notna(_yf_secili_satirlar.iloc[0].get("id")):
                    _yf_sel_id = int(_yf_secili_satirlar.iloc[0]["id"])
                    _yf_sel_firma = str(_yf_secili_satirlar.iloc[0].get("firma", ""))
                    not_dialog(_yf_sel_id, _yf_sel_firma)
                if st.button("💾 Değişiklikleri Kaydet", key="_yf_duzenle_kaydet_btn"):
                    _yf_guncellenen = 0
                    _yf_eklenen = 0
                    _yf_kayit_hatasi = []
                    _sb_yf = get_sb_client()
                    _yf_eski_idler = set(_yf_gosterilecek["id"].dropna().astype(int).tolist())
                    for _yi in range(len(_yf_duzenlenen)):
                        _satir_yeni = _yf_duzenlenen.iloc[_yi]
                        _yf_id_ham = _satir_yeni.get("id")
                        _yf_mevcut_mi = pd.notna(_yf_id_ham) and int(_yf_id_ham) in _yf_eski_idler
                        if _yf_mevcut_mi:
                            _satir_eski = _yf_gosterilecek[_yf_gosterilecek["id"] == int(_yf_id_ham)].iloc[0]
                            _yf_fark = {}
                            for _yc in _yf_kol:
                                if _yc == "id": continue
                                _yv, _ev = _satir_yeni[_yc], _satir_eski[_yc]
                                _yv_str = "" if pd.isna(_yv) else str(_yv)
                                _ev_str = "" if pd.isna(_ev) else str(_ev)
                                if _yv_str != _ev_str:
                                    _yf_fark[_yc] = _yv_str
                            if _yf_fark and _sb_yf:
                                try:
                                    _sb_yf.table("cari_kartlar").update(_yf_fark).eq("id", int(_yf_id_ham)).execute()
                                    _yf_guncellenen += 1
                                except Exception as _yf_hata:
                                    _yf_kayit_hatasi.append(f"ID {int(_yf_id_ham)}: {_yf_hata}")
                        else:
                            _yf_yeni_kayit = {}
                            for _yc in _yf_kol:
                                if _yc == "id": continue
                                _yv = _satir_yeni[_yc]
                                if pd.notna(_yv) and str(_yv).strip():
                                    _yf_yeni_kayit[_yc] = str(_yv).strip()
                            if _yf_yeni_kayit.get("firma") and _sb_yf:
                                try:
                                    _sb_yf.table("cari_kartlar").insert(_yf_yeni_kayit).execute()
                                    _yf_eklenen += 1
                                except Exception as _yf_hata:
                                    _yf_kayit_hatasi.append(f"Yeni satır ({_yf_yeni_kayit.get('firma')}): {_yf_hata}")
                            elif not _yf_yeni_kayit.get("firma") and any(_yf_yeni_kayit.values()):
                                _yf_kayit_hatasi.append("Yeni satır: 'firma' adı boş olamaz, kaydedilmedi.")
                    if _yf_guncellenen or _yf_eklenen:
                        _mesaj_parca = []
                        if _yf_guncellenen: _mesaj_parca.append(f"{_yf_guncellenen} kayıt güncellendi")
                        if _yf_eklenen: _mesaj_parca.append(f"{_yf_eklenen} yeni firma eklendi")
                        st.toast(f"💾 {' · '.join(_mesaj_parca)}", icon="✅")
                        st.cache_data.clear()
                        st.rerun()
                    if _yf_kayit_hatasi:
                        st.error("Bazı satırlar kaydedilemedi:\n" + "\n".join(_yf_kayit_hatasi))
                    if not _yf_guncellenen and not _yf_eklenen and not _yf_kayit_hatasi:
                        st.info("Herhangi bir değişiklik bulunamadı.")
            else:
                st.caption(f"✅ '{_yf_ara}' ile eşleşen kayıtlı müşteri yok — yeni firma olarak güvenle eklenebilir.")

        # ── Çoklu Firma Taslakları — seçili firmaları isimle kaydet, sonra tek tıkla geri yükle ──
        if "_cok_firma_taslaklar" not in st.session_state:
            st.session_state["_cok_firma_taslaklar"] = {}
            try:
                _sb_tsk0 = get_sb_client()
                if _sb_tsk0:
                    import json as _tskj0
                    _r_tsk0 = _sb_tsk0.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_cok_firma_taslaklar").execute()
                    if _r_tsk0.data:
                        st.session_state["_cok_firma_taslaklar"] = _tskj0.loads(_r_tsk0.data[0]["deger"])
            except:
                pass

        def _cok_firma_taslak_kaydet_db():
            try:
                _sb_tsk1 = get_sb_client()
                if _sb_tsk1:
                    import json as _tskj1
                    _deger_tsk1 = _tskj1.dumps(st.session_state["_cok_firma_taslaklar"], ensure_ascii=False)
                    # NOT: upsert(on_conflict=...) kullanılmıyor — "kullanici_tercih" tablosunda
                    # (kullanici, anahtar) için unique constraint olmadığından upsert sessizce
                    # başarısız olabiliyor. Bunun yerine önce sil, sonra ekle (diğer modüllerdeki
                    # _muh_token deseniyle aynı, kanıtlanmış yöntem).
                    _sb_tsk1.table("kullanici_tercih").delete().eq("kullanici", "__liste_ui__").eq("anahtar", "_cok_firma_taslaklar").execute()
                    _sb_tsk1.table("kullanici_tercih").insert({
                        "kullanici": "__liste_ui__", "anahtar": "_cok_firma_taslaklar",
                        "deger": _deger_tsk1
                    }).execute()
            except Exception as _tsk_db_hata:
                st.error(f"⚠️ Taslak veritabanına kaydedilemedi: {_tsk_db_hata}")

        if st.session_state.get("_filtre_sifirla_flag"):
            del st.session_state["_filtre_sifirla_flag"]

        # Eski sistemle uyumluluk
        _df_il  = df["il"]  if "il"  in df.columns else pd.Series([""] * len(df))
        _df_asa = df["islem_asamasi"] if "islem_asamasi" in df.columns else pd.Series([""] * len(df))
        kart_opts = ["-- Müşteri Seçin --"] + [
            f"[{int(i)}] {f} | {il} | {a}"
            for i, f, il, a in zip(df["id"], df["firma"], _df_il, _df_asa)
            if str(f) not in ["","nan","None"]
        ] if not df.empty and "firma" in df.columns else ["-- Müşteri Seçin --"]
        if secili_kart_inline == "🔵 Tüm Firmalar":
            secili_kart = "-- Müşteri Seçin --"
            # Query param ile tam sıfırlama — widget değerleri de temizlenir
            _u = st.query_params.to_dict()
            _u["_rfil"] = "toplam"
            st.query_params.update(_u)
            st.rerun()
        elif secili_kart_inline != "-- Müşteri Seçin --":
            _id_str = secili_kart_inline.split("]")[0].replace("[","").strip()
            _esles = [o for o in kart_opts if f"[{_id_str}]" in o]
            secili_kart = _esles[0] if _esles else "-- Müşteri Seçin --"
        else:
            secili_kart = "-- Müşteri Seçin --"

    # Varsayılan: hiçbir filtre seçilmemişse tüm liste gelsin
    if not st.session_state.get("_toplam_aktif") and \
       not st.session_state.get("_cl_fil_durum_multi") and \
       not st.session_state.get("_cl_fil_asama_multi") and \
       not st.session_state.get("_asamasiz_aktif") and \
       not st.session_state.get("_mesaj_gercek_aktif") and \
       not st.session_state.get("_cl_fil_asama1") and \
       not st.session_state.get("_cl_fil_asama2") and \
       not st.session_state.get("_cl_fil_asama3") and \
       not st.session_state.get("_cl_fil_sonuc") and \
       not st.session_state.get("_cl_fil_il_multi") and \
       not st.session_state.get("_cl_fil_ilce_multi") and \
       not st.session_state.get("_cl_fil_ozel_multi") and \
       not st.session_state.get("_cl_fil_guncelleme_tarih_multi"):
        st.session_state["_toplam_aktif"] = True

    # Filtre uygula
    df_f = df.copy()
    # Toplam aktifse tüm filtreleri zorla sıfırla
    if st.session_state.get("_toplam_aktif", False):
        ara_txt = ""; _asama_sec = []; _durum_sec = []; _il_sec = []; _ilce_sec = []; _tem_sec = []; filtre_seg = "Tümü"; _guncelleme_tarih_sec = []; _ozel_sec = []
        for _fk in ["_cl_fil_asama1","_cl_fil_asama2","_cl_fil_asama3","_cl_fil_sonuc"]:
            st.session_state.pop(_fk, None)
    # Aşamasız filtresi
    if st.session_state.get("_asamasiz_aktif", False):
        _tum_asama_set = set(_grp1_asama + _grp2_asama + _grp3_asama + _grp4_asama + _grp5_asama)
        if "islem_asamasi" in df_f.columns:
            df_f = df_f[df_f["islem_asamasi"].isna() | ~df_f["islem_asamasi"].isin(_tum_asama_set)]
    # "💬 Mesaj" kutusuna tıklanınca — gerçek mesaj/whatsapp/email kaydı olan
    # (veya manuel override edilmiş) müşterilerle filtrele.
    elif st.session_state.get("_mesaj_gercek_aktif", False):
        if "id" in df_f.columns:
            _mg_idler = _rbar_mesaj_id_seti_yukle()
            df_f = df_f[df_f["id"].astype(str).isin(_mg_idler)]
    # Toplam butonuna basıldıysa hiçbir filtre uygulanmaz
    elif not st.session_state.get("_toplam_aktif", False):
        if ara_txt:
            df_f = df_f[df_f.apply(lambda r: ara_txt.lower() in str(r).lower(), axis=1)]
        if _asama_sec:
            # Aşama değerleri (Randevu, Teklif, TAKİP, Sözleşme...) ile Sonuç değerlerini (Kazanıldı, Kaybedildi, Devam Ediyor)
            # ayrı gruplar olarak ele alıyoruz: kendi grubu içinde VEYA (OR), gruplar arasında VE (AND).
            # Örn: "TAKİP" + "Devam Ediyor" seçilince -> 3. aşaması TAKİP OLAN VE sonucu Devam Ediyor OLAN kayıtlar gelir.
            _sonuc_kategori_n = {_asama_norm(x) for x in ["Kazanıldı", "Kaybedildi", "Devam Ediyor"]}
            _asama_sec_n = [_asama_norm(x) for x in _asama_sec]
            _stage_vals_n = [x for x in _asama_sec_n if x not in _sonuc_kategori_n]
            _sonuc_vals_n = [x for x in _asama_sec_n if x in _sonuc_kategori_n]

            _stage_mask = None
            if _stage_vals_n:
                _stage_mask = df_f["islem_asamasi"].apply(_asama_norm).isin(_stage_vals_n) if "islem_asamasi" in df_f.columns else pd.Series([False] * len(df_f), index=df_f.index)
                for _acol in ["asama1", "asama2", "asama3"]:
                    if _acol in df_f.columns:
                        _stage_mask = _stage_mask | df_f[_acol].apply(_asama_norm).isin(_stage_vals_n)

            _sonuc_mask = None
            if _sonuc_vals_n:
                _sonuc_mask = df_f["sonuc"].apply(_asama_norm).isin(_sonuc_vals_n) if "sonuc" in df_f.columns else pd.Series([False] * len(df_f), index=df_f.index)

            if _stage_mask is not None and _sonuc_mask is not None:
                _asama_mask = _stage_mask & _sonuc_mask
            elif _stage_mask is not None:
                _asama_mask = _stage_mask
            else:
                _asama_mask = _sonuc_mask
            df_f = df_f[_asama_mask]
        # asama1/2/3/sonuc filtresi — hangi kolonda olduğuna bakılmaksızın, büyük/küçük harf farkı yok sayılarak eşleşeni yakalar
        _tekli_asama_hedef = (st.session_state.get("_cl_fil_asama1") or
                               st.session_state.get("_cl_fil_asama2") or
                               st.session_state.get("_cl_fil_asama3"))
        if _tekli_asama_hedef:
            _tekli_hedef_n = _asama_norm(_tekli_asama_hedef)
            _tek_mask = pd.Series([False] * len(df_f), index=df_f.index)
            for _acol in ["islem_asamasi", "asama1", "asama2", "asama3"]:
                if _acol in df_f.columns:
                    _tek_mask = _tek_mask | (df_f[_acol].apply(_asama_norm) == _tekli_hedef_n)
            df_f = df_f[_tek_mask]
        if st.session_state.get("_cl_fil_sonuc") and "sonuc" in df_f.columns:
            df_f = df_f[df_f["sonuc"].apply(_asama_norm) == _asama_norm(st.session_state["_cl_fil_sonuc"])]
        if _durum_sec:
            df_f = df_f[df_f["durum"].isin(_durum_sec)]
        if filtre_seg != "Tümü":
            df_f["_seg_tmp"] = df_f.apply(lambda r: hesapla_segment(r.get("segment",""), r.get("gerceklesen_ciro",0)), axis=1)
            if filtre_seg == "Segmentsiz": df_f = df_f[df_f["_seg_tmp"]==""]
            else: df_f = df_f[df_f["_seg_tmp"]==filtre_seg]
        if _il_sec:
            df_f = df_f[df_f["il"].astype(str).isin(_il_sec)]
        if _ilce_sec:
            df_f = df_f[df_f["ilce"].astype(str).isin(_ilce_sec)]
        if _ozel_sec and "rakip_firma" in df_f.columns:
            df_f = df_f[df_f["rakip_firma"].astype(str).isin(_ozel_sec)]
        if _tem_sec:
            df_f = df_f[df_f["temsilci"].astype(str).isin(_tem_sec)]
        if _guncelleme_tarih_sec:
            # Güncelleme Tarihi — ÇOKLU seçim, saatsiz. Bir müşteri, seçilen
            # tarihlerden HERHANGİ BİRİNDE gerçekten işlem görmüşse gelir
            # (sadece "en son işlemi" o tarihte olan değil — _id_tum_gunler_str
            # o müşterinin TÜM işlem günlerini tutar, kesişim kontrolü yapılır).
            _sec_tarih_set = set(_guncelleme_tarih_sec)
            df_f = df_f[df_f["id"].apply(lambda x: bool(_id_tum_gunler_str.get(str(int(x)), set()) & _sec_tarih_set))]

    # Bölgeler ekranından gelen gizli bölge filtresi (ilçe pill'leri taşmasın diye görünmez uygulanır)
    if st.session_state.get("_bl_ilce_filtre") and "ilce" in df_f.columns:
        _bl_hedef_ilceler = set(st.session_state["_bl_ilce_filtre"])
        df_f = df_f[df_f["ilce"].astype(str).isin(_bl_hedef_ilceler)]

    # Mükerrer bölümünden gelen filtre — tüm mükerrer kayıtları tabloda gösterir
    if st.session_state.get("_mr_liste_filtre") and "id" in df_f.columns:
        _mr_hedef_idler = set(st.session_state["_mr_liste_filtre"])
        df_f = df[df["id"].isin(_mr_hedef_idler)].reset_index(drop=True) if "id" in df.columns else df_f
        _mrf1, _mrf2 = st.columns([5,1])
        with _mrf1:
            st.info(f"🔍 Mükerrer kayıtlar gösteriliyor — {len(df_f)} kayıt. Düzenleyip Kaydet'e basabilir, "
                    "Seç kutusunu işaretleyip silebilirsiniz.")
        with _mrf2:
            if st.button("✕ Kaldır", key="_mr_liste_filtre_kaldir", use_container_width=True):
                st.session_state.pop("_mr_liste_filtre", None)
                st.rerun()

    # Havuz (Bölgesiz) filtresi — hiçbir tanımlı bölgeye uymayan (il boş veya tanımsız) kayıtlar
    if st.session_state.get("_bl_havuz_filtre") and not df_f.empty:
        _hv_ilce_kol = "ilce" if "ilce" in df_f.columns else None
        df_f = df_f[df_f.apply(
            lambda r: il_ilce_bolge_bul(r.get("il",""), r.get(_hv_ilce_kol,"") if _hv_ilce_kol else "") is None,
            axis=1)]
        if not df_f.empty and "id" in df_f.columns:
            _hv_kolonlar = [c for c in ["id","firma","il","ilce"] if c in df_f.columns]
            _hv_edit_df = df_f[_hv_kolonlar].copy().reset_index(drop=True)

            _hv_col_config = {
                "id":     st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "firma":  st.column_config.TextColumn("Firma", disabled=True, width="medium"),
                "il":     st.column_config.TextColumn("İl (yazın)", width="small"),
                "ilce":   st.column_config.TextColumn("İlçe (yazın)", width="small"),
            }
            with st.expander(f"✏️ Bu {len(df_f)} kaydı düzelt (kaydırmadan)", expanded=True):
                # Form içinde — siz "Kaydet"e basana kadar sayfa hiç yeniden hesaplanmaz,
                # yazarken ekran oynayıp durmaz.
                with st.form(key="hv_form", clear_on_submit=False):
                    _hv_edited = st.data_editor(
                        _hv_edit_df, use_container_width=True, hide_index=True,
                        column_config=_hv_col_config, key="hv_editor", height=300,
                        column_order=["firma","il","ilce","id"])
                    _hv_submit = st.form_submit_button("💾 Kaydet ve Bölgelere Dağıt",
                                                        type="primary", use_container_width=True)

                if _hv_submit:
                    _hv_basarili = 0
                    _hv_hala_havuzda = 0
                    _sb_hv = get_sb_client()
                    with st.spinner("Kaydediliyor ve bölgelere dağıtılıyor..."):
                        for _, _hv_row in _hv_edited.iterrows():
                            _hv_orig_satir = df_f[df_f["id"] == _hv_row["id"]]
                            if _hv_orig_satir.empty:
                                continue
                            _hv_orig = _hv_orig_satir.iloc[0]
                            _hv_yeni_il = str(_hv_row.get("il","")).strip()
                            _hv_yeni_ilce = str(_hv_row.get("ilce","")).strip()
                            if _hv_yeni_il != str(_hv_orig.get("il","") or "").strip() or _hv_yeni_ilce != str(_hv_orig.get("ilce","") or "").strip():
                                try:
                                    if _sb_hv:
                                        _sb_hv.table("cari_kartlar").update({"il": _hv_yeni_il, "ilce": _hv_yeni_ilce}).eq("id", int(_hv_row["id"])).execute()
                                    else:
                                        db_update("cari_kartlar", {"il": _hv_yeni_il, "ilce": _hv_yeni_ilce}, "id", int(_hv_row["id"]))
                                    _hv_basarili += 1
                                    if il_ilce_bolge_bul(_hv_yeni_il, _hv_yeni_ilce) is None:
                                        _hv_hala_havuzda += 1
                                except Exception:
                                    pass
                    if _hv_basarili:
                        try: get_cari_listesi.clear()
                        except: pass
                        try: db_read.clear()
                        except: pass
                        st.session_state.pop("hv_editor", None)
                        _hv_ozet = f"✅ {_hv_basarili} kayıt güncellendi."
                        if _hv_hala_havuzda:
                            _hv_ozet += f" ({_hv_hala_havuzda} tanesi yazdığınız il/ilçeyle hâlâ eşleşmedi, Havuz'da kaldı — kontrol edin.)"
                        st.toast(_hv_ozet, icon="✅")
                        st.rerun()
                    else:
                        st.info("Hiçbir değişiklik yapılmadı.")

    # ── HİÇ FİLTRE SEÇİLİ DEĞİLKEN — sadece işlem görmemiş (Özel Müşteri/Portföy) göster ──
    # Bir müşteriye durum atanınca (Randevu, Teklif, Tekrar Ara vb.) artık burada görünmesin,
    # Segment hesapla ve sırala
    if df_f.empty or "firma" not in df_f.columns:
        df_f = pd.DataFrame()
    else:
        df_f["_seg_goster"] = df_f.apply(lambda r: hesapla_segment(r.get("segment",""), r.get("gerceklesen_ciro",0)), axis=1)
        _seg_sira = {"👑 A+":0,"⭐ A":1,"🔵 B":2,"⚪ C":3,"":4}
        df_f["_seg_sira"] = df_f["_seg_goster"].map(lambda s: _seg_sira.get(s,4))
        df_f = df_f.sort_values(["_seg_sira","firma"], ascending=[True,True]).reset_index(drop=True)
        if siralama_kol == "Firma A-Z":      df_f = df_f.sort_values("firma", ascending=True)
        elif siralama_kol == "Firma Z-A":    df_f = df_f.sort_values("firma", ascending=False)
        elif siralama_kol == "İl A-Z" and "il" in df_f.columns:       df_f = df_f.sort_values("il", ascending=True)
        elif siralama_kol == "Temsilci A-Z" and "temsilci" in df_f.columns: df_f = df_f.sort_values("temsilci", ascending=True)
        elif siralama_kol == "Hedef ₺↓" and "beklenen_ciro" in df_f.columns:
            df_f = df_f.copy(); df_f["_s"] = pd.to_numeric(df_f["beklenen_ciro"], errors="coerce").fillna(0)
            df_f = df_f.sort_values("_s", ascending=False).drop(columns=["_s"])
        elif siralama_kol == "Hedef ₺↑" and "beklenen_ciro" in df_f.columns:
            df_f = df_f.copy(); df_f["_s"] = pd.to_numeric(df_f["beklenen_ciro"], errors="coerce").fillna(0)
            df_f = df_f.sort_values("_s", ascending=True).drop(columns=["_s"])
        elif siralama_kol == "Gerçek ₺↓" and "gerceklesen_ciro" in df_f.columns:
            df_f = df_f.copy(); df_f["_s"] = pd.to_numeric(df_f["gerceklesen_ciro"], errors="coerce").fillna(0)
            df_f = df_f.sort_values("_s", ascending=False).drop(columns=["_s"])
        elif siralama_kol == "Gerçek ₺↑" and "gerceklesen_ciro" in df_f.columns:
            df_f = df_f.copy(); df_f["_s"] = pd.to_numeric(df_f["gerceklesen_ciro"], errors="coerce").fillna(0)
            df_f = df_f.sort_values("_s", ascending=True).drop(columns=["_s"])
        df_f = df_f.reset_index(drop=True)

    # Çoklu firma seçimi yapıldıysa — diğer filtreler ne olursa olsun sadece seçilenler gösterilir
    if _cok_secili_idler and "id" in df_f.columns:
        df_f = df.copy()  # tüm listeden (mevcut il/durum filtrelerinden bağımsız) seçilenleri bul
        df_f = df_f[df_f["id"].isin(_cok_secili_idler)].reset_index(drop=True)
        st.info(f"🔍 {len(df_f)} firma karşılaştırma için seçili — temizlemek için yukarıdaki kutudan kaldırın.")
        # ── ŞEFFAFLIK: Seçilen ID sayısı ile bulunan satır sayısı farklıysa
        # (örn. arşivlenmiş/silinmiş bir firma seçiliyse) bunu SESSİZCE
        # gizlemiyoruz — hangi ID'lerin bulunamadığını açıkça gösteriyoruz.
        # Burada uygulanan HİÇBİR sayısal sınır/limit yok; "isin()" filtresi
        # seçilen TÜM ID'leri arıyor.
        _bulunmayan_idler = _cok_secili_idler - set(df_f["id"].astype(int).tolist())
        if _bulunmayan_idler:
            st.warning(f"⚠️ Seçtiğin {len(_bulunmayan_idler)} firma listede bulunamadı (ID: {sorted(_bulunmayan_idler)}) — "
                       "muhtemelen arşivlenmiş/silinmiş ya da başka bir kullanıcı tarafından kaldırılmış. "
                       "Bu bir gösterim sınırı değil, o kayıtlar artık mevcut değil.")

    _aktif_fil_sayisi = sum([bool(ara_txt),bool(_asama_sec),bool(_durum_sec),filtre_seg!="Tümü",bool(_il_sec),bool(_ilce_sec),bool(_tem_sec),bool(_guncelleme_tarih_sec),bool(_ozel_sec)])
    if secili_kart != "-- Müşteri Seçin --" and "[" in secili_kart:
        try:
            kart_id = int(secili_kart.split("]")[0].replace("[","").strip())
            # Önce filtrelenmiş listede ara, yoksa tüm listede ara
            _km = df_f[df_f["id"]==kart_id]
            if _km.empty:
                _km = get_cari_listesi()
                _km = _km[_km["id"]==kart_id]
            if _km.empty:
                st.warning("⚠️ Seçili müşteri bulunamadı. Filtreyi temizleyip tekrar deneyin.")
                st.stop()
            kart_row = _km.iloc[0]
            bek = float(kart_row.get("beklenen_ciro",0) or 0)
            ger = float(kart_row.get("gerceklesen_ciro",0) or 0)
            _seg_val = str(kart_row.get("segment","") or "")
            def _temiz(v):
                s = str(v or "").strip()
                return s if s and s not in ["nan","None","-",""] else "-"
            _gsm     = _tel_gruplu(_temiz(kart_row.get("gsm","") or kart_row.get("telefon","") or kart_row.get("tel","")))
            _sabit   = _tel_gruplu(_temiz(kart_row.get("sabit","") or kart_row.get("sabit_hat","")))
            _email   = _temiz(kart_row.get("email","") or kart_row.get("eposta",""))
            _yetkili = _temiz(kart_row.get("yetkili","") or kart_row.get("yetkili_adi",""))
            _il = str(kart_row.get("il","") or "-")
            _ilce = str(kart_row.get("ilce","") or "-")
            _durum = str(kart_row.get("durum","") or "-")
            _asama = str(kart_row.get("islem_asamasi","") or "-")
            _temsilci = str(kart_row.get("temsilci","") or "-")
            _yuzde = round((ger/bek)*100) if bek > 0 else 0
            _fark = ger - bek
            _fark_renk = "#16a34a" if _fark >= 0 else "#dc2626"

            # ── BAŞLIK ───────────────────────────────────────────────────────
            _seg_auto = hesapla_segment(kart_row.get("segment",""), kart_row.get("gerceklesen_ciro",0))
            _sbg, _stxt, _sbrd = segment_renk(_seg_auto)
            _baslik_renk = {"👑 A+":"#92400e","⭐ A":"#374151","🔵 B":"#1e3a8a","⚪ C":"#334155"}.get(_seg_auto,"#1e293b")
            st.markdown(f"""
<div style='background:{_baslik_renk};color:white;padding:12px 20px;border-radius:10px 10px 0 0;display:flex;align-items:center;justify-content:space-between'>
  <div style='display:flex;align-items:center;gap:12px'>
    <span style='font-size:28px'>🏢</span>
    <div>
      <div style='font-size:11px;color:rgba(255,255,255,0.6)'>Müşteri Detay Paneli</div>
      <div style='font-size:20px;font-weight:800;letter-spacing:0.5px'>{kart_row.get('firma','').upper()}</div>
    </div>
  </div>
  {f"<div style='background:rgba(255,255,255,0.2);padding:4px 14px;border-radius:20px;font-size:14px;font-weight:700'>{_seg_auto}</div>" if _seg_auto else ""}
</div>""", unsafe_allow_html=True)

            # ── 3 PANEL ──────────────────────────────────────────────────────
            _p1, _p2, _p3 = st.columns(3)

            with _p1:
                st.markdown(f"""
<div style='border:1px solid #e2e8f0;border-radius:0 0 0 10px;padding:16px;height:100%'>
  <div style='font-weight:700;font-size:13px;margin-bottom:10px;color:#374151'>📋 İletişim & Konum</div>
  <div style='font-size:13px;line-height:2;color:#374151'>
    <div>👤 {_yetkili}</div>
    <div>📱 {_gsm}</div>
    <div>☎️ {_sabit}</div>
    <div>✉️ {"<a href='mailto:"+_email+"' style='color:#3b82f6'>"+_email+"</a>" if "@" in _email else _email}</div>
  </div>
</div>""", unsafe_allow_html=True)

            with _p2:
                st.markdown(f"""
<div style='border:1px solid #e2e8f0;border-top:none;padding:16px;height:100%'>
  <div style='font-weight:700;font-size:13px;margin-bottom:10px;color:#374151'>📍 Konum & Durum</div>
  <div style='font-size:13px;line-height:2;color:#374151'>
    <div>🏙️ {_il} / {_ilce}</div>
    <div>📊 {_durum}</div>
    <div>🔄 {_asama}</div>
    <div>👔 {_temsilci}</div>
    {f"<div><span style='background:#eff6ff;color:#1d4ed8;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600'>{_seg_val}</span></div>" if _seg_val and _seg_val not in ["--",""] else ""}
  </div>
</div>""", unsafe_allow_html=True)

            with _p3:
                st.markdown(f"""
<div style='border:1px solid #e2e8f0;border-radius:0 0 10px 0;border-top:none;padding:16px;height:100%'>
  <div style='font-weight:700;font-size:13px;margin-bottom:10px;color:#374151'>💰 Özet Finans</div>
  <div style='display:flex;align-items:center;gap:16px'>
    <div style='text-align:center'>
      <svg width='80' height='80' viewBox='0 0 80 80'>
        <circle cx='40' cy='40' r='32' fill='none' stroke='#e2e8f0' stroke-width='8'/>
        <circle cx='40' cy='40' r='32' fill='none' stroke='{"#22c55e" if _yuzde>=100 else "#3b82f6"}' stroke-width='8'
          stroke-dasharray='{min(_yuzde,100)*2.01} 201' stroke-dashoffset='50' stroke-linecap='round'/>
      </svg>
      <div style='font-size:12px;color:#64748b;margin-top:-8px'>%{_yuzde}</div>
    </div>
    <div>
      <div style='font-size:11px;color:#94a3b8'>Beklenen:</div>
      <div style='font-size:18px;font-weight:800;color:#1e40af'>{fmt_para(bek)}</div>
      <div style='font-size:11px;color:#94a3b8;margin-top:6px'>Gerçekleşen:</div>
      <div style='font-size:16px;font-weight:700;color:#374151'>{fmt_para(ger)}</div>
      <div style='margin-top:4px;background:{"#f0fdf4" if _fark>=0 else "#fef2f2"};color:{_fark_renk};padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600;display:inline-block'>
        {"▲" if _fark>=0 else "▼"} {fmt_para(abs(_fark))}
      </div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

            # ── AKSİYONLAR ───────────────────────────────────────────────────
            st.markdown("<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-top:12px'>", unsafe_allow_html=True)
            _ax1,_ax2,_ax3,_ax4,_ax5 = st.columns([1,1,1.2,1,1])
            if _ax1.button("✏️ Düzenle", key=f"kd_{kart_id}", use_container_width=True):
                d2 = {str(k):(None if str(v) in ["nan","None","NaT"] else v) for k,v in kart_row.items()}
                for _k in ["firma","yetkili","gsm","sabit","email","adres","il","ilce","durum","temsilci","islem_asamasi","aciklama"]:
                    if _k in d2: d2[_k] = "" if d2[_k] is None else str(d2[_k])
                # GSM/Sabit bazı eski kayıtlarda farklı sütunlarda olabiliyor (telefon/tel/sabit_hat) —
                # detay kartındaki gösterimle aynı fallback'i burada da uyguluyoruz, yoksa form boş açılır.
                if not d2.get("gsm"):
                    d2["gsm"] = str(kart_row.get("telefon") or kart_row.get("tel") or "")
                if not d2.get("sabit"):
                    d2["sabit"] = str(kart_row.get("sabit_hat") or "")
                _duzenleme_form_key_temizle(str(kart_id))
                st.session_state["duzenle_musteri"] = d2
                st.session_state["aktif_tab"] = "yeni"; st.rerun()
            if _ax2.button("📅 Randevu", key=f"kr_{kart_id}", use_container_width=True, type="primary"):
                st.session_state["aktif_tab"] = "randevu"
                st.session_state["rand_musteri_onsel"] = kart_id; st.rerun()
            _gsm_raw = str(kart_row.get("gsm","") or "").replace(" ","").replace("-","")
            if _gsm_raw.startswith("0"): _gsm_raw = "90" + _gsm_raw[1:]
            if _gsm_raw and _ax3.button("💬 WhatsApp", key=f"kwa_{kart_id}", use_container_width=True):
                st.markdown(f"<span style='opacity:0.4;cursor:not-allowed' title='Geçici devre dışı'>WhatsApp aç (devre dışı)</span>", unsafe_allow_html=True)
            if _ax4.button("💾 Kaydet", key=f"kkaydet_{kart_id}", use_container_width=True, type="primary"):
                try:
                    _g = {"firma":str(kart_row.get("firma","")), "yetkili":str(kart_row.get("yetkili","")), "gsm":str(kart_row.get("gsm","")), "sabit":str(kart_row.get("sabit","")), "email":str(kart_row.get("email","")), "il":str(kart_row.get("il","")), "ilce":str(kart_row.get("ilce","")), "durum":str(kart_row.get("durum","")), "temsilci":str(kart_row.get("temsilci","")), "islem_asamasi":str(kart_row.get("islem_asamasi",""))}
                    if sb_liste: sb_liste.table("cari_kartlar").update(_g).eq("id",kart_id).execute()
                    else: db_update("cari_kartlar",_g,"id",kart_id)
                    try: db_read.clear()
                    except: pass
                    st.success("✅ Kaydedildi!")
                except Exception as _ke: st.error(f"Hata: {_ke}")
            if _ax5.button("🗑️ Arşive", key=f"ka_{kart_id}", use_container_width=True):
                if sb_liste: sb_liste.table("cari_kartlar").update({"silindi":1}).eq("id",kart_id).execute()
                else: db_update("cari_kartlar",{"silindi":1},"id",kart_id)
                try: db_read.clear()
                except: pass
                st.success("Arşive gönderildi!"); st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

            # ── AÇIKLAMA SİSTEMİ ──────────────────────────────────────────────
            st.markdown("---")
            st.markdown(f"#### 📝 Açıklamalar")

            # Notlar — ortak panel
            st.markdown("---")
            not_paneli(kart_id, str(kart_row.get("firma","")), key_prefix=f"ck_{kart_id}")

        except Exception as e:
            st.error(f"Kart hatası: {e}")

    st.divider()

    # ── DURUM LİSTESİ — Supabase'den yükle (col_config için) ─────────────────
    def _durum_listesi_yukle():
        try:
            _sb_d = get_sb_client()
            if _sb_d:
                _res = _sb_d.table("kullanici_tercih").select("deger") \
                    .eq("kullanici","__sistem__").eq("anahtar","ekstra_durumlar").execute()
                if _res.data:
                    import json as _jdl
                    return _jdl.loads(_res.data[0]["deger"])
        except: pass
        return []
    _ekstra_d = _durum_listesi_yukle()
    _durum_temel = _tanimlar_yukle("durum") or ["Özel Müşteri","Portföy"]
    _tum_durumlar = _durum_temel + [d for d in _ekstra_d if d not in _durum_temel]

    # ── KOLON AYARLARI ──────────────────────────────────────────────────────────
    # ── KOLON GENİŞLİKLERİ — DB'den oku ─────────────────────────────────────
    _KOL_VARSAYILAN = {
        "tarih":90,"guncelleme_tarihi":100,
        "firma":90,"rakip_firma":90,"yetkili":90,"gsm":100,"sabit":90,"email":90,
        "adres":110,"il":70,"ilce":60,"durum":80,"temsilci":80,
        "islem_asamasi":80,"aciklama":110,"📅 Son Randevu":170,"📨 Notlar":50,"id":40,
        "beklenen_ciro":70,"gerceklesen_ciro":70,"✅ Analiz":70,"Varış İli":90,"Koli/Palet":110,
        "🧾 Teklif":70,"💬 Mesaj":70,
        "asama1":90,"asama2":90,"asama3":90,"sonuc":90,"ara_islem":90
    }
    for _il_vars in _IL_SUTUN_LISTESI:
        _KOL_VARSAYILAN[_il_vars] = 10
    # Gizli kolonları DB'den yükle
    if "_kol_genislik_init" not in st.session_state:
        try:
            _sb_kg = get_sb_client()
            if _sb_kg:
                import json as _kgj
                _r_kg = _sb_kg.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kol_genislik").execute()
                if _r_kg.data:
                    _kg_loaded = _kgj.loads(_r_kg.data[0]["deger"])
                    # Varsayılanlarla birleştir — eksik kolonlar olabilir
                    _kg_merged = _KOL_VARSAYILAN.copy()
                    _kg_merged.update(_kg_loaded)
                    st.session_state["_kol_genislik"] = _kg_merged
                else:
                    st.session_state["_kol_genislik"] = _KOL_VARSAYILAN.copy()
                _r_gizli_cl = _sb_kg.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kol_gizli").execute()
                if _r_gizli_cl.data:
                    st.session_state["_kol_gizli"] = _kgj.loads(_r_gizli_cl.data[0]["deger"])
                else:
                    st.session_state["_kol_gizli"] = []
        except:
            st.session_state["_kol_genislik"] = _KOL_VARSAYILAN.copy()
            st.session_state["_kol_gizli"] = []
        st.session_state["_kol_genislik_init"] = True

    _KG = st.session_state.get("_kol_genislik", _KOL_VARSAYILAN.copy())
    _GIZLI_KOLONLAR = set(st.session_state.get("_kol_gizli", []))

    # Firma'ya kadarki (ve GSM/S.Tel'e kadar) kolonlar küçük/okunur kalsın diye
    # ayrı bir grup — bunlar büyütülürse Firma ilk görünümden çıkıyordu.
    # Bu grubun SONRASINDAKİ kolonlar daha fazla büyütülüyor ki toplam genişlik
    # üst rapor barına ulaşsın (aradaki fark bu "geç" kolonlara dağıtılıyor).
    _KOL_ERKEN = {"tarih","guncelleme_tarihi","id","rakip_firma","firma","yetkili","gsm","sabit"}

    def _w(k):
        # Gerçek piksel genişliği kullan — small/medium/large'a yuvarlarsak
        # 10 ile 79 arası tüm değerler görsel olarak aynı görünüyordu.
        _carpan = 4.5 if k in _KOL_ERKEN else 8.5
        return int(int(_KG.get(k, _KOL_VARSAYILAN.get(k, 100))) * _carpan)

    # Asama1/2/3 sabit seçenek listeleri — mevcut veride bu listede olmayan bir
    # değer varsa açılır kutu bozulmasın diye otomatik listeye eklenir.
    def _asama_secenek_guvenli(_kol, _sabit_liste):
        _liste = list(_sabit_liste)
        if _kol in df.columns:
            for _v in df[_kol].dropna().astype(str).unique():
                _v = _v.strip()
                if _v and _v not in _liste and _v.lower() not in ["nan","none"]:
                    _liste.append(_v)
        return _liste

    # ── İL SÜTUNLARI — global sabit (dosyanın en başında tanımlı), burada tekrar tanımlanmaz ──

    col_config = {
        "Seç":           st.column_config.CheckboxColumn("Seç", default=False, width=_w("Seç")),
        "tarih":         st.column_config.TextColumn("İşlem Tarih", disabled=True, width=_w("tarih")),
        "guncelleme_tarihi": st.column_config.TextColumn("Güncelleme Tarihi", disabled=True, width=_w("guncelleme_tarihi"), help="Bu müşteriye en son ne zaman not, teklif veya mesaj/işlem eklendiğini gösterir."),
        "id":            st.column_config.NumberColumn("ID", disabled=True, width=_w("id")),
        "olusturan": None, "silindi": None,
        "beklenen_ciro":    st.column_config.NumberColumn("Hedef ₺",  format="%,.0f ₺", width=_w("beklenen_ciro")),
        "gerceklesen_ciro": st.column_config.NumberColumn("Gerçek ₺", format="%,.0f ₺", width=_w("gerceklesen_ciro")),
        "rakip_firma":   st.column_config.TextColumn("Özel", width=_w("rakip_firma")),
        "firma":         st.column_config.TextColumn("Firma",     width=_w("firma")),
        "yetkili":       st.column_config.TextColumn("Yetkili",   width=_w("yetkili")),
        "gsm":           st.column_config.TextColumn("GSM",       width=_w("gsm")),
        "sabit":         st.column_config.TextColumn("S. Tel",    width=_w("sabit")),
        "email":         st.column_config.TextColumn("Email",     width=_w("email")),
        "adres":         st.column_config.TextColumn("Adres",     width=_w("adres")),
        "il":            st.column_config.TextColumn("İl",        width=_w("il")),
        "ilce":          st.column_config.TextColumn("İlçe",      width=_w("ilce")),
        "durum":         st.column_config.SelectboxColumn("Durum", options=["Tümü"] + [x for x in tum_durum_opts if str(x).upper() not in ["NONE","NAN",""]], width=_w("durum")),
        "temsilci":      st.column_config.TextColumn("Temsilci",  width=_w("temsilci")),
        "islem_asamasi": st.column_config.SelectboxColumn("İlk Temas", options=["Tümü", "Arama", "Tekrar Ara", "Mesaj", "E-Mail"], width=_w("islem_asamasi")),
        "aciklama":      st.column_config.TextColumn("Açıklama",  width=_w("aciklama")),
        "📅 Son Randevu": st.column_config.TextColumn("📅 Son Randevu", disabled=False, width=_w("📅 Son Randevu"), help="Manuel tarih yazıp kaydedebilirsin (örn. 15.08.2026 veya 15.08.2026 14:00) — gerçek bir randevu kaydı oluşturulur."),
        "📨 Notlar":     st.column_config.TextColumn("📨 Notlar", disabled=True, width=_w("📨 Notlar")),
        "✅ Analiz":     st.column_config.TextColumn("✅ Analiz", disabled=False, width=_w("✅ Analiz"), help="Herhangi bir şey yazıp kaydedin (örn. bir nokta) — ✅ ikonu manuel olarak gösterilir. Boş bırakırsan otomatik eşleşme geri döner."),
        "🧾 Teklif":     st.column_config.TextColumn("🧾 Teklif", disabled=False, width=_w("🧾 Teklif"), help="Sadece rakam girin (örn. 5). İkon otomatik eklenir. Boş bırakırsan otomatik hesaplanan sayı geri döner."),
        "💬 Mesaj":      st.column_config.TextColumn("💬 Mesaj", disabled=False, width=_w("💬 Mesaj"), help="Sadece rakam girin (örn. 3). İkon otomatik eklenir. Boş bırakırsan otomatik hesaplanan sayı geri döner."),
        "Varış İli":     st.column_config.TextColumn("Varış İli", disabled=False, width=_w("Varış İli"), help="Müşterinin kargo varış ili — manuel serbest metin. Buraya veya Koli/Palet'e bir şey yazılırsa Analiz otomatik ✅ olur."),
        "Koli/Palet":    st.column_config.TextColumn("Koli/Palet", disabled=False, width=_w("Koli/Palet"), help="Koli, palet vb. bilgiler — manuel, sınırsız serbest metin."),
        "asama1":        st.column_config.SelectboxColumn("1. Aşama", options=_asama_secenek_guvenli("asama1", ["", "Randevu"]), width=_w("asama1")),
        "asama2":        st.column_config.SelectboxColumn("2. Aşama", options=_asama_secenek_guvenli("asama2", ["", "Teklif"]), width=_w("asama2")),
        "asama3":        st.column_config.SelectboxColumn("3. Aşama", options=_asama_secenek_guvenli("asama3", ["Tümü", "Deneme", "TAKİP", "Fiyat Hazırla", "Sözleşme"]), width=_w("asama3")),
        "ara_islem":     st.column_config.TextColumn("Ara İşlem", width=_w("ara_islem")),
        "sonuc":         st.column_config.SelectboxColumn("Sonuç", options=_asama_secenek_guvenli("sonuc", ["Tümü", "Kazanıldı", "Kaybedildi", "Devam Ediyor"]), width=_w("sonuc")),
    }
    _IL_KISA_ETIKET = {"İstanbul":"İst","Bursa":"Brs","İzmir":"İzm","Manisa":"Man","Tekirdağ":"Tek",
                        "Kocaeli":"Koc","Ankara":"Ank","Konya":"Kon","Denizli":"Den","Adana":"Ada",
                        "Gaziantep":"Gaz","Kayseri":"Kay","Antalya":"Ant","Aydın":"Ayd","Balıkesir":"Bal",
                        "Diyarbakır":"Diy","Erzurum":"Erz","Eskişehir":"Esk","Hatay":"Hat","Kahramanmaraş":"Kah",
                        "Malatya":"Mal","Mardin":"Mar","Mersin":"Mrs","Muğla":"Muğ","Ordu":"Ord",
                        "Sakarya":"Sak","Samsun":"Sam","Trabzon":"Tra","Van":"Van","Şanlıurfa":"Şan","Diğer":"Diğ"}
    for _il_kol_cfg in _IL_SUTUN_LISTESI:
        col_config[_il_kol_cfg] = st.column_config.TextColumn(
            _IL_KISA_ETIKET.get(_il_kol_cfg, _il_kol_cfg[:3]), width=_w(_il_kol_cfg),
            help=f"{_il_kol_cfg} — Bu firmanın bu ile ne gönderdiğini serbestçe yazın (sayı veya metin).")
    # Sütun sırası — sizin verdiğiniz şablonla birebir: Seç, İşlem Tarih, Id, Firma, Yetkili,
    # Gsm, S.Tel, E-Mail, Adres, İlçe, İl, Hedef(+Gerçek), Durum, Analiz, Aşama, 1-2-3.Aşama,
    # Açıklama, Notlar, Son Randevu, Teklif, Mesaj, Sonuç. Temsilci silinmedi, en sona eklendi.
    # ── SATIR SIRASINI DONDUR — segment/ciro gibi kayıt sırasında değişebilen
    # alanlara göre yapılan sıralama (yukarıda), her kayıttan sonra o müşterinin
    # segmenti/cirosu değiştiği için satırın yerini kaydırıyordu. Bu da "Seç"
    # işaretinin ve genel çalışma sırasının bir kayıttan diğerine kaymasına
    # sebep oluyordu. Çözüm: GÖRÜNEN (filtrelenmiş) müşteri KÜMESİ değişmediği
    # sürece (yeni/silinen/filtre dışı kalan müşteri yoksa) sırayı burada
    # sabitliyoruz — bir alanı düzenleyip kaydetmek artık satırların yerini
    # değiştirmiyor.
    if not df_f.empty and "id" in df_f.columns:
        _cl2_id_kume = tuple(sorted(int(x) for x in df_f["id"].tolist()))  # SIRASIZ küme — sadece hangi müşteriler görünüyor, onu karşılaştırır
        _cl2_anahtar = (str(siralama_kol), _cl2_id_kume)
        if st.session_state.get("_cl2_son_anahtar") != _cl2_anahtar or not st.session_state.get("_cl2_sabit_sira"):
            st.session_state["_cl2_sabit_sira"] = df_f["id"].tolist()
            st.session_state["_cl2_son_anahtar"] = _cl2_anahtar
        else:
            _cl2_sirali = st.session_state["_cl2_sabit_sira"]
            _cl2_map = {v: i for i, v in enumerate(_cl2_sirali)}
            df_f = df_f.copy()
            df_f["_cl2_key"] = df_f["id"].map(_cl2_map).fillna(len(_cl2_sirali))
            df_f = df_f.sort_values("_cl2_key").drop(columns=["_cl2_key"]).reset_index(drop=True)

    col_order = ["Seç","tarih","guncelleme_tarihi","id","rakip_firma","firma","yetkili","gsm","sabit","email","adres","ilce","il",
                 "beklenen_ciro","gerceklesen_ciro","durum","✅ Analiz","Varış İli","Koli/Palet","islem_asamasi",
                 "asama1","asama2","asama3","aciklama","📨 Notlar","📅 Son Randevu",
                 "🧾 Teklif","💬 Mesaj","ara_islem","sonuc","temsilci"] + _IL_SUTUN_LISTESI
    # Gizli kolonları çıkar
    _kol_gizli_map = {"firma":"firma","rakip_firma":"rakip_firma","yetkili":"yetkili","gsm":"gsm","sabit":"sabit","email":"email",
                      "adres":"adres","il":"il","ilce":"ilce","durum":"durum","temsilci":"temsilci",
                      "islem_asamasi":"islem_asamasi","aciklama":"aciklama","tarih":"tarih","guncelleme_tarihi":"guncelleme_tarihi",
                      "📅 Son Randevu":"📅 Son Randevu","📨 Notlar":"📨 Notlar","id":"id",
                      "beklenen_ciro":"beklenen_ciro","gerceklesen_ciro":"gerceklesen_ciro","✅ Analiz":"✅ Analiz",
                      "🧾 Teklif":"🧾 Teklif","💬 Mesaj":"💬 Mesaj","Varış İli":"Varış İli","Koli/Palet":"Koli/Palet",
                      "asama1":"asama1","asama2":"asama2","asama3":"asama3","sonuc":"sonuc","ara_islem":"ara_islem"}
    col_order = [c for c in col_order if not any(c == _kol_gizli_map.get(g,g) for g in _GIZLI_KOLONLAR)]

    # ── SAYFALAMA KALDIRILDI — kullanıcı isteği üzerine, liste artık her zaman
    # tam (Tümü) gösteriliyor, sayfa butonları tamamen kaldırıldı. ────────────
    _cl_toplam_kayit = len(df_f)
    df_f_sayfali = df_f

    df_edit = df_f_sayfali.copy()
    # "None" / "nan" string değerlerini temizle — boş göster
    for _col in df_edit.columns:
        if df_edit[_col].dtype == object:
            df_edit[_col] = df_edit[_col].replace({"None": "", "nan": "", "NaN": "", "none": ""})
    # aciklama kolonu kesinlikle olsun
    if "aciklama" not in df_edit.columns:
        df_edit["aciklama"] = ""
    df_edit["aciklama"] = df_edit["aciklama"].fillna("").astype(str).replace("nan","")
    # rakip_firma kolonu kesinlikle olsun
    if "rakip_firma" not in df_edit.columns:
        df_edit["rakip_firma"] = ""
    df_edit["rakip_firma"] = df_edit["rakip_firma"].fillna("").astype(str).replace("nan","")
    # ara_islem kolonu kesinlikle olsun
    if "ara_islem" not in df_edit.columns:
        df_edit["ara_islem"] = ""
    df_edit["ara_islem"] = df_edit["ara_islem"].fillna("").astype(str).replace("nan","")

    # ── İL SÜTUNLARI — global fonksiyonlar (dosya başında tanımlı) kullanılıyor,
    # burada tekrar tanımlanmaz — hem burası hem Notlar&Randevu dialog'u AYNI
    # önbelleği paylaşır, biri kaydedince diğeri de hemen güncel görür.
    _il_gonderim_matrisi = _il_gonderim_matrisi_yukle()
    if "id" in df_edit.columns:
        for _il_kol in _IL_SUTUN_LISTESI:
            df_edit[_il_kol] = df_edit["id"].apply(
                lambda _rid: (_il_gonderim_matrisi.get(str(int(_rid)), {}).get(_il_kol, "") or "") if pd.notna(_rid) else "")

    # Son randevu bilgisini ekle (tarih + saat + bölge) — normalize edilmiş eşleştirme
    try:
        _df_rand_join = db_read("randevular", extra_sql="ORDER BY randevu_tarihi DESC, randevu_saati DESC")
        if not _df_rand_join.empty and "musteri_adi" in _df_rand_join.columns:
            def _norm_rand(s):
                return (str(s or "").strip()
                        .upper()
                        .replace("İ","I").replace("Ş","S").replace("Ğ","G")
                        .replace("Ü","U").replace("Ö","O").replace("Ç","C")
                        .replace("  "," "))
            _son_rand = {}
            for _, _rj in _df_rand_join.iterrows():
                _mn_norm = _norm_rand(_rj.get("musteri_adi",""))
                if _mn_norm and _mn_norm not in _son_rand:
                    _dt = fmt_tarih(str(_rj.get("randevu_tarihi","") or ""))
                    _st = str(_rj.get("randevu_saati","") or "")[:5]
                    _bl = str(_rj.get("bolge","") or "")
                    _sc = str(_rj.get("sonuc","") or "")
                    _son_rand[_mn_norm] = f"📅 {_dt} {_st}"
            df_edit["📅 Son Randevu"] = df_edit["firma"].apply(lambda x: _son_rand.get(_norm_rand(x),""))
    except:
        df_edit["📅 Son Randevu"] = ""
    # Aşama 1-4 ve Sonuç kolonları — yoksa boş ekle
    for _ak in ["asama1","asama2","asama3","sonuc"]:
        if _ak not in df_edit.columns:
            df_edit[_ak] = ""

    # Ciro kolonlarını sayısal tut — başlığa tıklayınca doğru sıralar
    if "beklenen_ciro" in df_edit.columns:
        df_edit["beklenen_ciro"] = pd.to_numeric(df_edit["beklenen_ciro"], errors="coerce").fillna(0)
    if "gerceklesen_ciro" in df_edit.columns:
        df_edit["gerceklesen_ciro"] = pd.to_numeric(df_edit["gerceklesen_ciro"], errors="coerce").fillna(0)
    # ── Manuel Analiz / Çıkış İli / Koli-Palet override'ları — DB'den yükle ──
    # (Analiz hesabından ÖNCE yüklenmeli — aşağıda kullanılıyor)
    for _ov_key in ["_analiz_manuel_override", "_cikis_ili_manuel", "_koli_palet_manuel"]:
        if _ov_key not in st.session_state:
            st.session_state[_ov_key] = {}
    if not st.session_state.get("_ekstra_override_yuklendi"):
        st.session_state["_ekstra_override_yuklendi"] = True
        try:
            _sb_ex0 = get_sb_client()
            if _sb_ex0:
                import json as _exj0
                _r_ex0 = _sb_ex0.table("kullanici_tercih").select("anahtar,deger").eq("kullanici","__liste_ui__").in_(
                    "anahtar", ["_analiz_manuel_override", "_cikis_ili_manuel", "_koli_palet_manuel"]).execute()
                for _row_ex in (_r_ex0.data or []):
                    st.session_state[_row_ex["anahtar"]] = _exj0.loads(_row_ex["deger"])
        except:
            pass
    _analiz_override = st.session_state.get("_analiz_manuel_override", {})
    _cikis_ili_map   = st.session_state.get("_cikis_ili_manuel", {})
    _koli_palet_map  = st.session_state.get("_koli_palet_manuel", {})

    try:
        # Analiz yapılmış firmaları işaretle
        try:
            _sb_an = get_sb_client()
            if _sb_an:
                _an_raw = _sb_an.table("musteri_analiz").select("firma").execute().data or []
                def _norm_firma(s):
                    return (str(s or "").strip()
                            .upper()
                            .replace("İ","I").replace("Ş","S").replace("Ğ","G")
                            .replace("Ü","U").replace("Ö","O").replace("Ç","C")
                            .replace("  "," "))
                _analiz_firma_list = [
                    _norm_firma(_ar.get("firma",""))
                    for _ar in _an_raw
                    if _ar.get("firma")
                ]
                _analiz_firma_set = set(_analiz_firma_list)
                def _analiz_esles(firma_adi):
                    _n = _norm_firma(firma_adi)
                    if not _n:
                        return ""
                    # 1) Tam eşleşme
                    if _n in _analiz_firma_set:
                        return "✅"
                    # 2) Kısmi eşleşme — biri diğerinin içinde mi
                    for _af in _analiz_firma_list:
                        if not _af:
                            continue
                        if _n in _af or _af in _n:
                            return "✅"
                        # 3) İlk 8 karakter eşleşmesi
                        if len(_n) >= 8 and len(_af) >= 8 and _n[:8] == _af[:8]:
                            return "✅"
                    return ""
                df_edit["✅ Analiz"] = df_edit["firma"].apply(_analiz_esles)
            else:
                df_edit["✅ Analiz"] = ""
        except Exception as _ane:
            df_edit["✅ Analiz"] = ""
    except:
        df_edit["✅ Analiz"] = ""

    # Manuel Analiz override — otomatik eşleşme olmasa bile hücreye bir şey
    # yazılırsa (örn. "." veya "ok") ✅ ikonu manuel olarak gösterilir. Ayrıca
    # Varış İli veya Koli/Palet'e bir şey yazılırsa (Analiz'e hiç dokunulmasa
    # bile) "analiz yapılmış" kabul edilip ✅ otomatik gösterilir.
    if "id" in df_edit.columns:
        df_edit["Varış İli"] = [(_cikis_ili_map.get(str(int(rid)), "") or "") for rid in df_edit["id"]]
        df_edit["Koli/Palet"] = [(_koli_palet_map.get(str(int(rid)), "") or "") for rid in df_edit["id"]]
        df_edit["✅ Analiz"] = [
            ("✅" if (str(int(rid)) in _analiz_override or str(otomatik or "").strip()
                      or str(varis or "").strip() or str(koli or "").strip()) else "")
            for rid, otomatik, varis, koli in zip(df_edit["id"], df_edit["✅ Analiz"], df_edit["Varış İli"], df_edit["Koli/Palet"])
        ]
    else:
        df_edit["Varış İli"] = ""
        df_edit["Koli/Palet"] = ""

    _not_detay = {}
    _not_sayac = {}
    if sb_liste:
        try:
            @st.cache_data(ttl=60, show_spinner=False)
            def _tum_notlari_yukle():
                _sb2 = get_sb_client()
                if _sb2:
                    _r2 = _sb2.table("cari_aciklamalar").select("*").execute()
                    return _r2.data or []
                return []
            _res_notlar_data = _tum_notlari_yukle()
            # NOT: Yetkililer sekmesi de aynı cari_aciklamalar tablosuna "##YETKILI##"
            # etiketiyle kayıt atıyor — bunlar gerçek not değil, rozet sayısına dahil
            # edilmemeli (Notlar penceresindeki sayıyla tutarlı olsun diye).
            _res_notlar_data = [r for r in _res_notlar_data
                                 if not str(r.get("aciklama","") or "").startswith("##YETKILI##")]
            if _res_notlar_data:
                import collections
                _not_sayac = collections.Counter([str(r["cari_id"]) for r in _res_notlar_data])
                for _nr in _res_notlar_data:
                    _ncid = str(_nr.get("cari_id",""))
                    if _ncid not in _not_detay:
                        _not_detay[_ncid] = []
                    _not_detay[_ncid].append({
                        "id": _nr.get("id",""),
                        "tarih": fmt_tarih(_nr.get("created_at","") or _nr.get("tarih","")),
                        "kim": str(_nr.get("olusturan","") or ""),
                        "metin": str(_nr.get("aciklama","") or ""),
                    })
                if "id" in df_edit.columns:
                    df_edit["📨 Notlar"] = df_edit["id"].apply(lambda x: f"📨 {_not_sayac.get(str(int(x)),0)}" if _not_sayac.get(str(int(x)),0) > 0 else "")
                else:
                    df_edit["📨 Notlar"] = ""
                # NOT: burada eskiden "_not_sayi"ye göre azalan sıralama yapılıyordu.
                # Bu sıralama not sayısı DEĞİŞTİKÇE (yani tam olarak bir not kaydedince)
                # satır sırasını kaydırıyordu — ve "Seç" işareti Streamlit'te satır
                # POZİSYONUNA göre tutulduğu için, sıra kayınca işaret başka bir
                # müşteriye "geçmiş" gibi görünüyordu. Sıralama kaldırıldı ki satır
                # sırası bir işlemden diğerine SABİT kalsın, Seç işareti doğru
                # müşteride kalsın.
            else:
                df_edit["📨 Notlar"] = ""
        except Exception as _not_err:
            df_edit["📨 Notlar"] = ""
            st.warning(f"Not yükleme hatası: {_not_err}")
    else:
        df_edit["📨 Notlar"] = ""

    # ── Manuel Teklif/Mesaj override'ları — DB'den yükle (bir kere) ──
    if "_teklif_manuel_override" not in st.session_state or "_mesaj_manuel_override" not in st.session_state:
        st.session_state["_teklif_manuel_override"] = {}
        st.session_state["_mesaj_manuel_override"] = {}
        try:
            _sb_ov0 = get_sb_client()
            if _sb_ov0:
                import json as _ovj0
                _r_ov0 = _sb_ov0.table("kullanici_tercih").select("anahtar,deger").eq("kullanici","__liste_ui__").in_(
                    "anahtar", ["_teklif_manuel_override", "_mesaj_manuel_override"]).execute()
                for _row_ov in (_r_ov0.data or []):
                    st.session_state[_row_ov["anahtar"]] = _ovj0.loads(_row_ov["deger"])
        except:
            pass
    _teklif_override = st.session_state.get("_teklif_manuel_override", {})
    _mesaj_override  = st.session_state.get("_mesaj_manuel_override", {})

    # ── Cari kartında GERÇEKTEN yapılan her kaydetme (aşama/durum/alan
    # değişikliği vb.) burada iz bırakır — "Güncelleme Tarihi" bunun üzerinden
    # hesaplanır. cari_kartlar'da updated_at kolonu/tetikleyicisi olmadığı için
    # (yeni kolon açmadan) kullanici_tercih'te ayrı bir JSON haritada tutulur:
    # {cari_id_str: "YYYY-MM-DD HH:MM:SS"}.
    if "_cari_son_guncelleme" not in st.session_state:
        st.session_state["_cari_son_guncelleme"] = {}
        try:
            _sb_sg0 = get_sb_client()
            if _sb_sg0:
                import json as _sgj0
                _r_sg0 = _sb_sg0.table("kullanici_tercih").select("deger").eq(
                    "kullanici","__liste_ui__").eq("anahtar","_cari_son_guncelleme").execute()
                if _r_sg0.data:
                    st.session_state["_cari_son_guncelleme"] = _sgj0.loads(_r_sg0.data[0]["deger"])
        except:
            pass
    _cari_son_guncelleme = st.session_state.get("_cari_son_guncelleme", {})

    # ── Teklif sayısı (yeni sütun, Notlar ile aynı mantık) ──

    _tek_sayac_cl = {}
    if sb_liste:
        try:
            @st.cache_data(ttl=60, show_spinner=False)
            def _tum_teklif_sayac_yukle():
                _sb3 = get_sb_client()
                if _sb3:
                    _r3 = _sb3.table("teklifler").select("musteri_id").execute()
                    return _r3.data or []
                return []
            def _id_norm_cl(_v):
                _s = str(_v).strip()
                try:
                    return str(int(float(_s)))
                except Exception:
                    return _s
            _res_tek_data_cl = _tum_teklif_sayac_yukle()
            if _res_tek_data_cl:
                import collections as _coltek_cl
                _tek_sayac_cl = _coltek_cl.Counter([_id_norm_cl(r.get("musteri_id","")) for r in _res_tek_data_cl])
        except Exception:
            _tek_sayac_cl = {}
    if "id" in df_edit.columns:
        # Manuel override varsa onu göster, yoksa otomatik hesaplanan sayıyı göster
        df_edit["🧾 Teklif"] = df_edit["id"].apply(
            lambda x: (f"🧾 {_teklif_override.get(str(int(x)))}" if str(int(x)) in _teklif_override
            else (f"🧾 {_tek_sayac_cl.get(str(int(x)),0)}" if _tek_sayac_cl.get(str(int(x)),0) > 0 else "")))
    else:
        df_edit["🧾 Teklif"] = ""

    # ── Mesaj (yeni sütun) — gerçek WhatsApp/Email gönderim kayıtları (islem_kaydi
    # tablosu, musteri_id ile bağlı) — WhatsApp Teklif ve Email Teklif türleri sayılır ──
    _mesaj_sayac_cl = {}
    if sb_liste:
        try:
            @st.cache_data(ttl=60, show_spinner=False)
            def _tum_mesaj_sayac_yukle():
                _sb4 = get_sb_client()
                if _sb4:
                    _r4 = _sb4.table("islem_kaydi").select("musteri_id,islem_turu").in_(
                        "islem_turu", ["WhatsApp Teklif", "Email Teklif"]).execute()
                    return _r4.data or []
                return []
            _res_mesaj_data_cl = _tum_mesaj_sayac_yukle()
            if _res_mesaj_data_cl:
                import collections as _colmsg_cl
                _mesaj_sayac_cl = _colmsg_cl.Counter([str(r.get("musteri_id","")) for r in _res_mesaj_data_cl])
        except Exception:
            _mesaj_sayac_cl = {}
    if "id" in df_edit.columns:
        # Manuel override varsa onu göster, yoksa otomatik hesaplanan sayıyı göster
        df_edit["💬 Mesaj"] = df_edit["id"].apply(
            lambda x: (f"💬 {_mesaj_override.get(str(int(x)))}" if str(int(x)) in _mesaj_override
            else (f"💬 {_mesaj_sayac_cl.get(str(int(x)),0)}" if _mesaj_sayac_cl.get(str(int(x)),0) > 0 else "")))
    else:
        df_edit["💬 Mesaj"] = ""

    # ── İşlem Tarih — sadece tarih+saat gösterir, ham/karışık format değil ──
    if "tarih" in df_edit.columns:
        df_edit["tarih_ham_ilk_kayit"] = df_edit["tarih"]  # güncelleme hesabı için ham hali sakla
        df_edit["tarih"] = df_edit["tarih"].apply(fmt_tarih_saat)

    # ── Güncelleme Tarihi — bu müşteriye ait EN SON aktiviteyi gösterir:
    # yeni not/açıklama, yeni teklif, ya da mesaj/arama kaydı eklenmişse en
    # güncel tarih burada görünür. Hiçbiri yoksa ilk kayıt (İşlem Tarih) tarihi
    # gösterilir. cari_kartlar'da yeni kolon açmadan, mevcut ilişkili
    # tablolardan (cari_aciklamalar, teklifler, islem_kaydi) hesaplanır.
    @st.cache_data(ttl=60, show_spinner=False)
    def _son_aktivite_tarihleri_yukle():
        _sonuc = {}
        _sb5 = get_sb_client()
        if not _sb5:
            return _sonuc

        def _guncelle(_mid_ham, _tarih_ham):
            if not _mid_ham or not _tarih_ham:
                return
            _mid = str(_mid_ham)
            _yeni_dt = _guncelleme_tarih_parse(_tarih_ham)
            if _yeni_dt is None:
                return
            _mevcut_dt = _guncelleme_tarih_parse(_sonuc.get(_mid)) if _mid in _sonuc else None
            if _mevcut_dt is None or _yeni_dt > _mevcut_dt:
                _sonuc[_mid] = str(_tarih_ham)

        # 1) Notlar/açıklamalar — created_at Supabase'in otomatik alanı
        try:
            _r5 = _sb5.table("cari_aciklamalar").select("cari_id,created_at").execute()
            for _row in (_r5.data or []):
                _guncelle(_row.get("cari_id"), _row.get("created_at"))
        except Exception:
            pass

        # 2) Teklifler — created_at varsa kullan (tarih kolonu production'da güvenilir değil)
        try:
            _r6 = _sb5.table("teklifler").select("musteri_id,created_at").execute()
            for _row in (_r6.data or []):
                _guncelle(_row.get("musteri_id"), _row.get("created_at"))
        except Exception:
            pass

        # 3) Mesaj/arama/whatsapp kayıtları — islem_kaydi.tarih güvenilir
        try:
            _r7 = _sb5.table("islem_kaydi").select("musteri_id,tarih").execute()
            for _row in (_r7.data or []):
                _guncelle(_row.get("musteri_id"), _row.get("tarih"))
        except Exception:
            pass

        return _sonuc

    _son_aktivite = {}
    if sb_liste:
        try:
            _son_aktivite = _son_aktivite_tarihleri_yukle()
        except Exception:
            _son_aktivite = {}

    if "id" in df_edit.columns:
        def _guncelleme_tarihi_hesapla(_rid, _ilk_kayit_ham):
            _sid = str(int(_rid))
            _aday1 = _son_aktivite.get(_sid, "")          # not/teklif/mesaj kaydı
            _aday2 = _cari_son_guncelleme.get(_sid, "")   # gerçek alan/aşama/durum düzenlemesi
            _ilk = str(_ilk_kayit_ham or "")
            _adaylar = [t for t in [_aday1, _aday2, _ilk] if t]
            if not _adaylar:
                return ""
            # ÖNEMLİ: düz string karşılaştırması (max()) farklı tarih formatlarını
            # (ISO 'T' ayraçlı vs boşluklu) yanlış sıralıyordu — gerçek datetime'a
            # çevirip öyle karşılaştırıyoruz.
            _en_son = max(_adaylar, key=lambda t: _guncelleme_tarih_parse(t) or datetime.min)
            return fmt_tarih_saat(_en_son)
        df_edit["guncelleme_tarihi"] = [
            _guncelleme_tarihi_hesapla(rid, ilk) for rid, ilk in zip(df_edit["id"], df_edit.get("tarih_ham_ilk_kayit", df_edit["id"]*0))
        ]
    else:
        df_edit["guncelleme_tarihi"] = ""
    if "tarih_ham_ilk_kayit" in df_edit.columns:
        df_edit.drop(columns=["tarih_ham_ilk_kayit"], inplace=True)

    df_edit.insert(0, "Seç", False)

    import json as _json_ls

    # ── TÜMÜ GÖSTER — tablo sol, not paneli sağ ──────────────────────────────
    _kayitli_sira = st.session_state.get("_cl_kolon_sira", [])
    if _kayitli_sira and "🎨 Renk" in _kayitli_sira:
        # Renk artık ana tabloda bir sütun değil — eski kayıtlı sıralamada
        # kalmış olabilir, temizle (yoksa olmayan bir sütuna referans hatası verir).
        _kayitli_sira = [c for c in _kayitli_sira if c != "🎨 Renk"]
        st.session_state["_cl_kolon_sira"] = _kayitli_sira
        try:
            _sb_ko = get_sb_client()
            if _sb_ko:
                _sb_ko.table("kullanici_tercih").upsert({
                    "kullanici": "__liste_ui__", "anahtar": "_cl_kolon_sira",
                    "deger": json.dumps(_kayitli_sira)
                }, on_conflict="kullanici,anahtar").execute()
        except Exception:
            pass
    _aktif_col_order = _kayitli_sira if _kayitli_sira else col_order

    # ── KAYITLI SIRAYI GEÇERLİ/GÖRÜNÜR KOLONLARLA TEMİZLE ────────────────────
    # _kayitli_sira (kullanıcının sürükleyip kaydettiği kolon sırası) eski
    # olabilir: sonradan gizlenmiş bir kolonu hâlâ içerebilir, ya da sonradan
    # eklenmiş yeni bir kolonu (örn. Varış İli) hiç içermeyebilir. Bu durumda
    # "son kolon" araması aşağıda GERÇEKTE görünmeyen bir kolonu bulup onun
    # genişliğini kaldırıyordu — asıl görünen son kolon sabit genişlikte
    # kalıp sağda boşluk bırakıyordu. Burada kayıtlı sırayı güncel "col_order"
    # (görünür kolonlar) ile kesiştirip, yeni/eksik kolonları sona ekliyoruz.
    if _kayitli_sira:
        _kayitli_temiz = [c for c in _kayitli_sira if c in col_order]
        _eksik_yeni = [c for c in col_order if c not in _kayitli_temiz]
        _aktif_col_order = _kayitli_temiz + _eksik_yeni

    # ── SAĞ TARAFTAKİ BOŞLUĞU KAPAT ─────────────────────────────────────────
    # Tüm kolonlara sabit piksel genişliği verildiğinde, toplam genişlik ekran
    # genişliğinden az kalırsa tablonun sağında boş bir alan kalıyordu (ekran
    # boyutuna göre değişiyordu). Çözüm: en sondaki GÖRÜNÜR kolonun piksel
    # genişliğini sabitlemiyoruz — Streamlit o kolonu kalan boş alanı
    # dolduracak şekilde otomatik büyütüyor, böylece hangi ekran/monitör
    # olursa olsun sağda boşluk kalmıyor.
    for _son_kol in reversed(_aktif_col_order):
        if _son_kol != "Seç" and _son_kol in col_config and isinstance(col_config[_son_kol], dict):
            col_config[_son_kol] = dict(col_config[_son_kol])
            col_config[_son_kol].pop("width", None)
            break

    # NOT: Eskiden burada notlu satırları sarı yapan bir CSS triki vardı
    # (ilk N satır notluydu, çünkü tablo not sayısına göre sıralanıyordu).
    # Sıralama kaldırıldığı için bu trik artık rastgele satırları sarı
    # yapardı — bu yüzden kaldırıldı. Notlu müşteriler "📨 Notlar" sütunundaki
    # sayıdan hâlâ görülebiliyor.

    # Sağda not paneli açık mı?
    _not_panel_id = st.session_state.get("_cl_not_panel_id")

    # ── KAYDET BUTONU — TABLONUN ÜSTÜNDE, STICKY ───────────────────────────────
    st.markdown("""<style>
.cl-sticky-bar{
    position: sticky; top: 0; z-index: 999;
    background: white; padding: 8px 0 6px;
    border-bottom: 1px solid #e2e8f0;
    margin-bottom: 6px;
}
</style>""", unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="cl-sticky-bar">', unsafe_allow_html=True)
        _sb1, _sb2, _sb3, _sb4, _sb_bos = st.columns([1.4, 1.1, 1.1, 1.3, 3.7])
        with _sb1:
            if st.button("💾 Değişiklikleri Kaydet", type="primary", key="liste_kaydet_ust"):
                st.session_state["_kaydet_flag"] = True
        with _sb2:
            if st.button("➕ Satır Ekle", key="cl_hizli_ekle_btn_ust"):
                st.session_state["_cl_taslak_sayisi"] = st.session_state.get("_cl_taslak_sayisi", 0) + 1
                st.rerun()
        with _sb3:
            if st.button("🔄 Kolon Sıfırla", key="cl_kolon_sifirla_ust"):
                st.session_state.pop("_cl_kolon_sira", None)
                st.rerun()
        with _sb4:
            # Gerçek .xlsx (openpyxl) — virgülle ayrılmış CSV DEĞİL, Excel'de doğrudan
            # sorunsuz açılan binary Excel formatı. Ekrandaki (filtrelenmiş) liste iner.
            import io as _cl_xio
            _cl_xl_buf = _cl_xio.BytesIO()
            df_f.to_excel(_cl_xl_buf, index=False, engine="openpyxl")
            _cl_xl_buf.seek(0)
            st.download_button("📥 Excel İndir", data=_cl_xl_buf,
                                file_name=f"cari_liste_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="cl_excel_indir_ust", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)


    _tbl_col = st.container()
    _not_col = None

    # ── TASLAK SATIR(LAR) — "➕ Satır Ekle" ile açılan, henüz DB'ye YAZILMAMIŞ
    # boş satır(lar). id=0 ile işaretlenir. Firma alanı doldurulup "Kaydet"
    # edilirse gerçek bir müşteri kaydı oluşturulur (kaydetmezsen hiçbir şey
    # yazılmaz).
    # ÖNEMLİ (kritik veri kaybı hatası düzeltmesi): Eskiden bu blok bir BOOLEAN
    # bayrağa (_cl_taslak_aktif) bakıyordu ve bayrak True olduğu SÜRECE HER
    # rerun'da (yani kullanıcı bir hücreye yazıp Tab/Enter'a bastığında bile)
    # YENİDEN bir boş satır ekliyordu. Bu da her hücre düzenlemesinde tabloya
    # yeni bir boş satır girip önceki satırları kaydırıyordu — kullanıcının o
    # ana kadar yazdığı bilgiler artık YANLIŞ satıra karışıyor, bazı hücreler
    # kaybolmuş gibi görünüyordu. Şimdi kaç taslak satır isteneceği SABİT bir
    # sayaçta (_cl_taslak_sayisi) tutuluyor — bu sayaç SADECE "Satır Ekle"
    # butonuna basınca 1 artıyor, başka hiçbir rerun'da değişmiyor. Böylece
    # satır sayısı ve sırası, kullanıcı yazarken stabil kalıyor.
    _cl_taslak_sayisi = int(st.session_state.get("_cl_taslak_sayisi", 0) or 0)
    if _cl_taslak_sayisi > 0:
        _tas_bos_liste = []
        for _ in range(_cl_taslak_sayisi):
            _tas_bos = {c: "" for c in df_edit.columns}
            _tas_bos["id"] = 0
            if "Seç" in df_edit.columns:
                _tas_bos["Seç"] = False
            if "beklenen_ciro" in df_edit.columns:
                _tas_bos["beklenen_ciro"] = 0
            if "gerceklesen_ciro" in df_edit.columns:
                _tas_bos["gerceklesen_ciro"] = 0
            _tas_bos_liste.append(_tas_bos)
        df_edit = pd.concat([pd.DataFrame(_tas_bos_liste), df_edit], ignore_index=True)

    # Tablo yüksekliğini görünen satır sayısına göre hesapla — sabit 800px'lik
    # yükseklik, sayfa başına 12 satır varken altında boş satırlar bırakıyordu.
    # "Tümü" modunda (binlerce satır) yükseklik 800px'de sabit kalıp iç kaydırma kullanır.
    _cl_editor_yukseklik = min(800, 38 + (len(df_edit) * 35) + 3)

    # ── Sol Index Kolonu — "Sıra No" başlıklı, temiz sıralı (1,2,3...) numara.
    # Streamlit'te index kolonu zaten otomatik olarak sol tarafta SABİT kalır
    # (kaydırmada kaymaz). Eskiden burada firma id'sinin ham/karışık index'i
    # görünüyordu (17, 1692, 0, 5...) — artık temiz 1'den başlayan sıra no var.
    df_edit = df_edit.reset_index(drop=True)
    df_edit.index = df_edit.index + 1
    df_edit.index.name = "S.No"

    with _tbl_col:
        edited_df = st.data_editor(
            df_edit,
            use_container_width=True,
            num_rows="fixed",
            column_config=col_config,
            column_order=_aktif_col_order,
            height=_cl_editor_yukseklik,
            key="cari_editor"
        )

    # (not paneli artık tablonun altında expander olarak açılıyor)


    # Kolon sırası değiştiyse kaydet — hem session_state hem DB
    try:
        _editor_meta = st.session_state.get("cari_editor", {})
        _col_order_now = _editor_meta.get("column_order", [])
        if _col_order_now and _col_order_now != st.session_state.get("_cl_kolon_sira"):
            st.session_state["_cl_kolon_sira"] = _col_order_now
            try:
                _sb_ko = get_sb_client()
                if _sb_ko:
                    import json as _koj
                    _sb_ko.table("kullanici_tercih").upsert({
                        "kullanici":"__liste_ui__","anahtar":"_cl_kolon_sira",
                        "deger":_koj.dumps(_col_order_now, ensure_ascii=False)
                    }, on_conflict="kullanici,anahtar").execute()
            except: pass
    except: pass

    # İlk yüklemede kolon sırasını DB'den al
    if "_cl_kolon_sira_init" not in st.session_state:
        try:
            _sb_ki = get_sb_client()
            if _sb_ki:
                import json as _kij
                _r_ko = _sb_ki.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_cl_kolon_sira").execute()
                if _r_ko.data:
                    st.session_state["_cl_kolon_sira"] = _kij.loads(_r_ko.data[0]["deger"])
        except: pass
        st.session_state["_cl_kolon_sira_init"] = True

    # Her render'da tüm tabloyu session_state'e kaydet
    try:
        _kv = edited_df.copy()
        if "aciklama" not in _kv.columns:
            _kv["aciklama"] = ""
        _kv["aciklama"] = _kv["aciklama"].fillna("").astype(str).replace("nan","")
        _kayit_kolonlar = ["id","firma","yetkili","gsm","sabit","email","il","ilce","durum","temsilci","islem_asamasi","aciklama","asama1","asama2","asama3","sonuc"]
        _mevcut = [c for c in _kayit_kolonlar if c in _kv.columns]
        st.session_state["_ls_tablo"] = _kv[_mevcut].to_json(orient="records", force_ascii=False)
    except:
        pass

    # NOT: Burada eskiden "anında not arşivleme" vardı — Açıklama hücresine her
    # yazıldığında (Kaydet'e basılmadan) otomatik olarak sorgu atıp sayfayı
    # yeniliyordu. Bu, kullanıcı henüz TÜM değişikliklerini bitirmeden ekranın
    # yanıp sönmesine ve işlemin yarıda kalmasına sebep oluyordu. Kaldırıldı —
    # artık hiçbir şey otomatik çalışmıyor, arşivleme sadece "Değişiklikleri
    # Kaydet" butonuna basılınca yapılıyor.

    secili_df = edited_df[edited_df["Seç"] == True]
    secili_sayi = len(secili_df)
    secili_idler = secili_df["id"].tolist() if not secili_df.empty else []

    # ── "Seç" işaretli firmaları taslak olarak kaydetme paneli kullanıcı
    # isteğiyle kaldırıldı (arşivleme/silme butonlarıyla birlikte, aşağıda) ──

    # ── NOT DİALOG — sadece seçili olunca açılır ────────────────────────────
    if secili_sayi == 1:
        _sel_id = int(secili_idler[0])
        _sel_rows = df_edit[df_edit["id"] == _sel_id]
        _sel_firma = str(_sel_rows.iloc[0].get("firma","")) if not _sel_rows.empty else ""
        not_dialog(_sel_id, _sel_firma)




    # ── BUTONLAR ──────────────────────────────────────────────────────────────
    # NOT: "Değişiklikleri Kaydet" ve "Kolon Sıfırla" butonları artık SADECE
    # üst toolbar'da (sticky bar) gösteriliyor — burada tekrar render edilmiyor,
    # ama kaydetme mantığı (_kaydet_flag üzerinden) aynen çalışmaya devam ediyor.
    btn_k, btn_a, btn_s, btn_kolon = st.columns(4)
    _do_kaydet = st.session_state.pop("_kaydet_flag", False)
    with btn_k:
        if _do_kaydet:
            _editor_state = st.session_state.get("cari_editor", {})
            _edited_rows  = dict(_editor_state.get("edited_rows", {}))
            # ── GÜVENLİK AĞI: session_state'teki edited_rows bazen son hücreyi
            # kaçırabiliyor (widget'ın kendi zamanlama davranışı). Bu yüzden HER
            # zaman df_edit ile edited_df'i satır satır karşılaştırıp gerçek
            # farkı da hesaplıyoruz ve edited_rows ile BİRLEŞTİRİYORUZ — sadece
            # edited_rows boşsa değil, her durumda. edited_df zaten ekranda o an
            # görünen/kaydedilmiş son hâl olduğu için bu karşılaştırma en güvenilir
            # kaynak.
            if "edited_df" in dir():
                try:
                    _orig = df_edit.reset_index(drop=True)
                    _ed   = edited_df.reset_index(drop=True)
                    for _ei in range(min(len(_orig), len(_ed))):
                        _rd = dict(_edited_rows.get(str(_ei), {}))
                        for _ec in _ed.columns:
                            if str(_orig.at[_ei,_ec]) != str(_ed.at[_ei,_ec]):
                                _rd[_ec] = _ed.at[_ei,_ec]
                        if _rd: _edited_rows[str(_ei)] = _rd
                except: pass
            _tablo_json   = st.session_state.get("_ls_tablo")
            kayit_sayi = 0
            hata_list  = []
            if not _edited_rows:
                st.info("Değişiklik yok.")
            else:
              with st.spinner(f"💾 {len(_edited_rows)} satır kaydediliyor..."):
                try:
                    _rows = _json_ls.loads(_tablo_json) if _tablo_json else []
                except:
                    _rows = []

                # ── TASLAK SATIRLAR (id=0) işleme — "Satır Ekle" ile açılan boş
                # satır(lar) burada gerçek kayda dönüşür. Firma alanı hâlâ boşsa
                # o taslak için hiçbir şey yapılmaz, ekranda kalmaya devam eder.
                # ÖNEMLİ (hata düzeltmesi): Eskiden kod sadece İLK id=0 satırını
                # işleyip duruyordu (break ile) — birden fazla yeni satır eklenip
                # doldurulduğunda ikinciden itibaren TÜMÜ sessizce kayboluyordu.
                # Şimdi TÜM id=0 satırları tek tek işleniyor, hiçbiri atlanmıyor.
                _taslak_idxler = []
                for _ti, _trow in enumerate(_rows):
                    try:
                        if int(float(str(_trow.get("id", -1)))) == 0:
                            _taslak_idxler.append(_ti)
                    except Exception:
                        continue
                _taslak_basarili_sayisi = 0
                for _taslak_idx in _taslak_idxler:
                    _taslak_idx_str = str(_taslak_idx)
                    _taslak_firma = ""
                    _ed_tas = None
                    if "edited_df" in dir():
                        try:
                            _ed_tas = edited_df.reset_index(drop=True)
                            if _taslak_idx < len(_ed_tas) and "firma" in _ed_tas.columns:
                                _taslak_firma = str(_ed_tas.at[_taslak_idx, "firma"] or "").strip()
                        except Exception:
                            _ed_tas = None
                    if not _taslak_firma:
                        # Firma boş — DB'ye hiçbir şey yazma, taslağı olduğu gibi bırak
                        _edited_rows.pop(_taslak_idx_str, None)
                    else:
                        def _tas_al(_kol, _varsayilan="", _idx=_taslak_idx, _df=_ed_tas):
                            try:
                                if _df is not None and _kol in _df.columns:
                                    _v = _df.at[_idx, _kol]
                                    return str(_v) if _v not in [None, "nan", "None"] else _varsayilan
                            except Exception:
                                pass
                            return _varsayilan
                        _yeni_kayit = {
                            "tarih": datetime.now().isoformat(),
                            "firma": _taslak_firma,
                            "rakip_firma": _tas_al("rakip_firma"),
                            "yetkili": _tas_al("yetkili"),
                            "gsm": _tas_al("gsm").strip(),
                            "sabit": _tas_al("sabit").strip(),
                            "email": _tas_al("email"),
                            "adres": _tas_al("adres"),
                            "ilce": _tas_al("ilce"),
                            "il": _tas_al("il", "İstanbul"),
                            "durum": _tas_al("durum", "Portföy"),
                            "temsilci": _tas_al("temsilci", st.session_state.get("kullanici","")),
                            "islem_asamasi": _tas_al("islem_asamasi"),
                            "segment": "--",
                            "aciklama": _tas_al("aciklama"),
                            "silindi": 0, "olusturan": st.session_state.get("kullanici",""),
                            "beklenen_ciro": 0, "gerceklesen_ciro": 0,
                            "atanan_kullanici": st.session_state.get("kullanici","")
                        }
                        _taslak_basarili = False
                        _taslak_hata = ""
                        try:
                            _sb_tas = get_sb_client()
                            if _sb_tas:
                                _res_tas = _sb_tas.table("cari_kartlar").insert(_yeni_kayit).execute()
                                _taslak_basarili = bool(_res_tas.data)
                            else:
                                _taslak_hata = "Supabase bağlantısı yok."
                        except Exception as _tas_e:
                            _taslak_hata = str(_tas_e)
                        if _taslak_basarili:
                            kayit_sayi += 1
                            _taslak_basarili_sayisi += 1
                            try: get_cari_listesi.clear()
                            except: pass
                        else:
                            hata_list.append(f"Yeni satır ({_taslak_firma}): {_taslak_hata}")
                        _edited_rows.pop(_taslak_idx_str, None)
                if _taslak_basarili_sayisi:
                    # Sadece BAŞARIYLA kaydedilen taslak sayısı kadar azalt —
                    # firma alanı boş bırakılan taslak(lar) ekranda kalmaya devam etsin.
                    st.session_state["_cl_taslak_sayisi"] = max(0, _cl_taslak_sayisi - _taslak_basarili_sayisi)

                # ── Teklif/Mesaj manuel override'ları — cari_kartlar'da bu isimde
                # kolon yok, bu yüzden ayrı kullanici_tercih JSON'unda saklanır.
                # Hücre boş bırakılırsa override silinir, otomatik sayı geri döner.
                _teklif_ov_guncel = dict(st.session_state.get("_teklif_manuel_override", {}))
                _mesaj_ov_guncel  = dict(st.session_state.get("_mesaj_manuel_override", {}))
                _ov_degisti = False
                for _idx_str_ov, _deg_ov in _edited_rows.items():
                    _idxn_ov = int(_idx_str_ov)
                    if _idxn_ov >= len(_rows):
                        continue
                    _rid_ov = int(float(str(_rows[_idxn_ov].get("id", 0))))
                    if not _rid_ov:
                        continue
                    if "🧾 Teklif" in _deg_ov:
                        _v_ov_ham = str(_deg_ov["🧾 Teklif"] or "")
                        _v_ov = "".join(ch for ch in _v_ov_ham if ch.isdigit())  # sadece rakam — ikon zaten otomatik eklenir
                        if _v_ov:
                            _teklif_ov_guncel[str(_rid_ov)] = _v_ov
                        else:
                            _teklif_ov_guncel.pop(str(_rid_ov), None)
                        _ov_degisti = True
                    if "💬 Mesaj" in _deg_ov:
                        _v_ov_ham = str(_deg_ov["💬 Mesaj"] or "")
                        _v_ov = "".join(ch for ch in _v_ov_ham if ch.isdigit())  # sadece rakam — ikon zaten otomatik eklenir
                        if _v_ov:
                            _mesaj_ov_guncel[str(_rid_ov)] = _v_ov
                        else:
                            _mesaj_ov_guncel.pop(str(_rid_ov), None)
                        _ov_degisti = True
                if _ov_degisti:
                    st.session_state["_teklif_manuel_override"] = _teklif_ov_guncel
                    st.session_state["_mesaj_manuel_override"] = _mesaj_ov_guncel
                    try:
                        _sb_ov1 = get_sb_client()
                        if _sb_ov1:
                            import json as _ovj1
                            _sb_ov1.table("kullanici_tercih").upsert([
                                {"kullanici": "__liste_ui__", "anahtar": "_teklif_manuel_override",
                                 "deger": _ovj1.dumps(_teklif_ov_guncel, ensure_ascii=False)},
                                {"kullanici": "__liste_ui__", "anahtar": "_mesaj_manuel_override",
                                 "deger": _ovj1.dumps(_mesaj_ov_guncel, ensure_ascii=False)},
                            ], on_conflict="kullanici,anahtar").execute()
                    except:
                        pass
                    # Üst AŞAMA raporundaki Mesaj toplam kutusu ve 2.AŞAMA'daki
                    # Teklif firma sayısı 60 sn önbellekli — kaydettikten hemen
                    # sonra güncel görünsün diye önbellek burada da temizlenir.
                    try: _rbar_mesaj_toplam_yukle.clear()
                    except: pass
                    try: _rbar_teklif_toplam_yukle.clear()
                    except: pass

                # ── Analiz / Çıkış İli / Koli-Palet manuel override'ları ────────────────
                _analiz_ov_guncel = dict(st.session_state.get("_analiz_manuel_override", {}))
                _cikis_ov_guncel  = dict(st.session_state.get("_cikis_ili_manuel", {}))
                _koli_ov_guncel   = dict(st.session_state.get("_koli_palet_manuel", {}))
                _ex_degisti = False
                for _idx_str_ex, _deg_ex in _edited_rows.items():
                    _idxn_ex = int(_idx_str_ex)
                    if _idxn_ex >= len(_rows):
                        continue
                    _rid_ex = int(float(str(_rows[_idxn_ex].get("id", 0))))
                    if not _rid_ex:
                        continue
                    if "✅ Analiz" in _deg_ex:
                        _v_ex = str(_deg_ex["✅ Analiz"] or "").strip()
                        if _v_ex:
                            _analiz_ov_guncel[str(_rid_ex)] = "1"
                        else:
                            _analiz_ov_guncel.pop(str(_rid_ex), None)
                        _ex_degisti = True
                    if "Varış İli" in _deg_ex:
                        _v_ex = str(_deg_ex["Varış İli"] or "").strip()
                        if _v_ex:
                            _cikis_ov_guncel[str(_rid_ex)] = _v_ex
                        else:
                            _cikis_ov_guncel.pop(str(_rid_ex), None)
                        _ex_degisti = True
                    if "Koli/Palet" in _deg_ex:
                        _v_ex = str(_deg_ex["Koli/Palet"] or "").strip()
                        if _v_ex:
                            _koli_ov_guncel[str(_rid_ex)] = _v_ex
                        else:
                            _koli_ov_guncel.pop(str(_rid_ex), None)
                        _ex_degisti = True
                    # ── "Fiyatlandırma" hızlı-giriş — yazılan her şey Koli/Palet'e eklenir ──
                    if "Fiyatlandırma" in _deg_ex:
                        _v_fiyat = str(_deg_ex["Fiyatlandırma"] or "").strip()
                        if _v_fiyat:
                            _mevcut_koli = _koli_ov_guncel.get(str(_rid_ex), "").strip()
                            _koli_ov_guncel[str(_rid_ex)] = (_mevcut_koli + "\n" + _v_fiyat).strip() if _mevcut_koli else _v_fiyat
                            _ex_degisti = True
                if _ex_degisti:
                    st.session_state["_analiz_manuel_override"] = _analiz_ov_guncel
                    st.session_state["_cikis_ili_manuel"] = _cikis_ov_guncel
                    st.session_state["_koli_palet_manuel"] = _koli_ov_guncel
                    try:
                        _sb_ex1 = get_sb_client()
                        if _sb_ex1:
                            import json as _exj1
                            _sb_ex1.table("kullanici_tercih").upsert([
                                {"kullanici": "__liste_ui__", "anahtar": "_analiz_manuel_override",
                                 "deger": _exj1.dumps(_analiz_ov_guncel, ensure_ascii=False)},
                                {"kullanici": "__liste_ui__", "anahtar": "_cikis_ili_manuel",
                                 "deger": _exj1.dumps(_cikis_ov_guncel, ensure_ascii=False)},
                                {"kullanici": "__liste_ui__", "anahtar": "_koli_palet_manuel",
                                 "deger": _exj1.dumps(_koli_ov_guncel, ensure_ascii=False)},
                            ], on_conflict="kullanici,anahtar").execute()
                    except:
                        pass

                # ── "📅 Son Randevu" hücresine manuel tarih yazılırsa GERÇEK bir
                # randevu kaydı (randevular tablosu) oluşturulur — override değil,
                # gerçek veri. Format: "15.08.2026" veya "15.08.2026 14:00".
                import re as _rndre
                for _idx_str_rn, _deg_rn in _edited_rows.items():
                    if "📅 Son Randevu" not in _deg_rn:
                        continue
                    _rn_ham = str(_deg_rn["📅 Son Randevu"] or "").strip()
                    if not _rn_ham:
                        continue  # boşaltma = randevu silme değil, sadece görmezden gel
                    _idxn_rn = int(_idx_str_rn)
                    if _idxn_rn >= len(_rows):
                        continue
                    _rid_rn = int(float(str(_rows[_idxn_rn].get("id", 0))))
                    _firma_rn = str(_rows[_idxn_rn].get("firma", "") or "")
                    if not _rid_rn:
                        continue
                    # Emoji/etiket kalıntılarını temizle (örn. "📅 15.08.2026 14:00")
                    _rn_temiz = _rndre.sub(r"[^\d.:/ ]", "", _rn_ham).strip()
                    _rn_saat_m = _rndre.search(r"(\d{1,2}):(\d{2})", _rn_temiz)
                    _rn_saat = f"{_rn_saat_m.group(1).zfill(2)}:{_rn_saat_m.group(2)}" if _rn_saat_m else "10:00"
                    _rn_tarih_str = _rndre.sub(r"\d{1,2}:\d{2}", "", _rn_temiz).strip()
                    _rn_dt = _guncelleme_tarih_parse(_rn_tarih_str) or _guncelleme_tarih_parse(_rn_temiz)
                    if not _rn_dt:
                        # Doğrudan DD.MM.YYYY formatını dene (parse edemediyse)
                        _rn_m = _rndre.match(r"(\d{1,2})[.\/](\d{1,2})[.\/](\d{2,4})", _rn_tarih_str)
                        if _rn_m:
                            try:
                                _gg, _aa, _yy = int(_rn_m.group(1)), int(_rn_m.group(2)), int(_rn_m.group(3))
                                if _yy < 100: _yy += 2000
                                _rn_dt = datetime(_yy, _aa, _gg)
                            except Exception:
                                _rn_dt = None
                    if not _rn_dt:
                        continue  # anlaşılamayan tarih — sessizce atla, veri bozma
                    _rn_basarili = False
                    _rn_hata = ""
                    try:
                        _sb_rn = get_sb_client()
                        if _sb_rn:
                            _res_rn = _sb_rn.table("randevular").insert({
                                "randevu_tarihi": _rn_dt.strftime("%Y-%m-%d"),
                                "randevu_saati": _rn_saat,
                                "musteri_id": _rid_rn, "musteri_adi": _firma_rn,
                                "bolge": "", "gorev": "", "takip": "",
                                "adet": 1, "aciklama": "Cari Liste'den hızlı eklendi",
                                "sonuc": "", "temsilci": st.session_state.get("kullanici",""),
                                "olusturan": st.session_state.get("kullanici","")
                            }).execute()
                            _rn_basarili = bool(_res_rn.data)
                        else:
                            _rn_hata = "Supabase bağlantısı yok."
                    except Exception as _rn_e:
                        _rn_hata = str(_rn_e)
                    if _rn_basarili:
                        try: db_read.clear()
                        except: pass
                        # Randevu tarihi eklenince, müşterinin "1. Aşama"sı henüz
                        # boşsa otomatik "Randevu" yapılır — Kanban'daki "1. AŞAMA"
                        # sayacına yansısın diye (aksi halde sayaç hiç değişmiyordu).
                        _mevcut_asama1 = str(_rows[_idxn_rn].get("asama1","") or "").strip()
                        if not _mevcut_asama1:
                            try:
                                if _sb_rn:
                                    _sb_rn.table("cari_kartlar").update({"asama1":"Randevu"}).eq("id", _rid_rn).execute()
                                    try: get_cari_listesi.clear()
                                    except: pass
                            except Exception:
                                pass
                    else:
                        st.error(f"❌ Randevu kaydedilemedi ({_firma_rn}): {_rn_hata}")

                # ── Güncelleme Tarihi izi — gerçekten bir alan (aşama, durum, açıklama,
                # ciro vb.) değişen HER satır için "şu an" damgası basılır. "Seç"
                # (checkbox işaretleme) tek başına değişiklik sayılmaz. ISO format
                # kullanılıyor (diğer tarih kaynaklarıyla — cari_kartlar.tarih,
                # created_at — aynı ayraç/biçim, karşılaştırma tutarlı olsun diye).
                _sg_guncel = dict(st.session_state.get("_cari_son_guncelleme", {}))
                _sg_simdi = datetime.now().isoformat()
                _sg_degisti = False
                for _idx_str_sg, _deg_sg in _edited_rows.items():
                    _gercek_degisiklik = any(k not in ("Seç", "🗑️ Sil") for k in _deg_sg.keys())
                    if not _gercek_degisiklik:
                        continue
                    _idxn_sg = int(_idx_str_sg)
                    if _idxn_sg >= len(_rows):
                        continue
                    _rid_sg = int(float(str(_rows[_idxn_sg].get("id", 0))))
                    if not _rid_sg:
                        continue
                    _sg_guncel[str(_rid_sg)] = _sg_simdi
                    _sg_degisti = True
                if _sg_degisti:
                    st.session_state["_cari_son_guncelleme"] = _sg_guncel
                    try:
                        _sb_sg1 = get_sb_client()
                        if _sb_sg1:
                            import json as _sgj1
                            _sb_sg1.table("kullanici_tercih").upsert({
                                "kullanici": "__liste_ui__", "anahtar": "_cari_son_guncelleme",
                                "deger": _sgj1.dumps(_sg_guncel, ensure_ascii=False)
                            }, on_conflict="kullanici,anahtar").execute()
                    except:
                        pass

                # ── İL SÜTUNLARI kaydı — cari_kartlar'a değil, ayrı JSON haritaya
                # yazılır (kullanici_tercih._il_gonderim_matrisi). "Hangi ile ne
                # gönderiyor" bilgisi firma bazlı olarak burada tutulur.
                _ilm_degisti = False
                _ilm_guncel = dict(_il_gonderim_matrisi)

                def _vi_norm(_s):
                    return (str(_s or "").strip().upper().replace("İ", "I").replace("Ş", "S")
                            .replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O").replace("Ç", "C"))

                for _idx_str_ilm, _deg_ilm in _edited_rows.items():
                    _ilm_fark = {k: v for k, v in _deg_ilm.items() if k in _IL_SUTUN_LISTESI}
                    _varis_illeri_metni = str(_deg_ilm.get("Varış İlleri", "") or "").strip()
                    if not _ilm_fark and not _varis_illeri_metni:
                        continue
                    _idxn_ilm = int(_idx_str_ilm)
                    if _idxn_ilm >= len(_rows):
                        continue
                    _rid_ilm = int(float(str(_rows[_idxn_ilm].get("id", 0))))
                    if not _rid_ilm:
                        continue
                    _rid_ilm_str = str(_rid_ilm)
                    _ilm_guncel.setdefault(_rid_ilm_str, {})
                    for _ilk, _ilv in _ilm_fark.items():
                        _ilm_guncel[_rid_ilm_str][_ilk] = str(_ilv) if _ilv is not None else ""
                        _ilm_degisti = True
                    # ── "Varış İlleri" hızlı-giriş — karışık/serbest yazılan il
                    # isimlerini ayırıp, eşleşen il sütununu (boşsa) "✓" ile işaretler.
                    if _varis_illeri_metni:
                        _vi_metin_norm = _vi_norm(_varis_illeri_metni)
                        for _il_ad_vi in _IL_SUTUN_LISTESI:
                            if _il_ad_vi == "Diğer":
                                continue
                            if _vi_norm(_il_ad_vi) in _vi_metin_norm:
                                _mevcut_deg = _ilm_guncel[_rid_ilm_str].get(_il_ad_vi, "")
                                if not str(_mevcut_deg).strip():
                                    _ilm_guncel[_rid_ilm_str][_il_ad_vi] = _il_ad_vi.upper()
                                    _ilm_degisti = True
                if _ilm_degisti:
                    _il_gonderim_matrisi_kaydet(_ilm_guncel)
                    try: _il_gonderim_matrisi_yukle.clear()
                    except: pass

                def _tek_satir_guncelle(idx_str, degisiklikler):
                    """Tek bir satırı DB'ye yazar — paralel çalıştırılabilsin diye ayrı fonksiyon."""
                    idx = int(idx_str)
                    if idx >= len(_rows):
                        return None
                    rid = int(float(str(_rows[idx].get("id", 0))))
                    if not rid:
                        return None
                    guncelle = {}
                    for k, v in degisiklikler.items():
                        if k in ("Seç", "🗑️ Sil", "🧾 Teklif", "💬 Mesaj", "✅ Analiz", "Varış İli", "Koli/Palet", "📅 Son Randevu", "Varış İlleri", "Fiyatlandırma") or k in _IL_SUTUN_LISTESI: continue
                        if k in ("beklenen_ciro", "gerceklesen_ciro"):
                            try: guncelle[k] = float(v or 0)
                            except: guncelle[k] = 0
                        elif k in ("Hedef ₺",):
                            try: guncelle["beklenen_ciro"] = float(str(v or "").replace(".","").replace("₺","").replace(",",".").strip() or 0)
                            except: guncelle["beklenen_ciro"] = 0
                        elif k in ("Gerçek ₺",):
                            try: guncelle["gerceklesen_ciro"] = float(str(v or "").replace(".","").replace("₺","").replace(",",".").strip() or 0)
                            except: guncelle["gerceklesen_ciro"] = 0
                        elif k in ("gsm", "sabit"):
                            # KULLANICI İSTEĞİ: Artık otomatik "sadece rakam" temizliği
                            # YAPILMIYOR — birden fazla numarayı "533 405 55 18 - 539 266
                            # 42 86" gibi kendi ayracıyla tek hücrede tutabilmek için,
                            # kullanıcı ne yazarsa AYNEN kaydediliyor. (Eskiden boşluk/tire
                            # gibi her şey silinip iki numara birbirine yapışıyordu.)
                            guncelle[k] = str(v).strip() if v is not None else ""
                        else:
                            guncelle[k] = str(v) if v is not None else ""
                    if not guncelle:
                        return None
                    if sb_liste:
                        sb_liste.table("cari_kartlar").update(guncelle).eq("id", rid).execute()
                    else:
                        conn_u = get_conn()
                        sets = ", ".join([f"{k}=?" for k in guncelle])
                        conn_u.execute(f"UPDATE cari_kartlar SET {sets} WHERE id=?",
                            list(guncelle.values()) + [rid])
                        conn_u.commit(); conn_u.close()
                    return True

                # ── SATIRLARI PARALEL KAYDET — sıra sıra beklemek yerine aynı anda
                # gönderilir, N satır için toplam süre ~1 satırlık süreye yakın olur.
                _kaydedilen_firmalar = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as _havuz:
                    _gelecekler = {
                        _havuz.submit(_tek_satir_guncelle, idx_str, degisiklikler): idx_str
                        for idx_str, degisiklikler in _edited_rows.items()
                    }
                    for _gelecek in concurrent.futures.as_completed(_gelecekler):
                        _idx_str_g = _gelecekler[_gelecek]
                        try:
                            if _gelecek.result():
                                kayit_sayi += 1
                                try:
                                    _idxn_g = int(_idx_str_g)
                                    if _idxn_g < len(_rows):
                                        _kaydedilen_firmalar.append(str(_rows[_idxn_g].get("firma","") or "(isimsiz)"))
                                except Exception:
                                    pass
                        except Exception as e_row:
                            hata_list.append(str(e_row))

                try: db_read.clear()
                except: pass
                try: get_cari_listesi.clear()
                except: pass
                # ── AÇIKLAMA HÜCRESI DOLUYSA ARŞİVLE ─────────────────────────
                _arsiv_sayi = 0
                try:
                    _tablo_json2 = st.session_state.get("_ls_tablo")
                    _rows2 = _json_ls.loads(_tablo_json2) if _tablo_json2 else []
                    _arsivlenecekler = []
                    for _row2 in _rows2:
                        _rid2 = _row2.get("id")
                        _ac2 = str(_row2.get("aciklama","") or "").strip()
                        if not _rid2 or not _ac2 or _ac2 == "nan": continue
                        _arsivlenecekler.append((int(float(str(_rid2))), str(_row2.get("firma",""))," ".join([_ac2])))

                    def _tek_not_arsivle(rid2, firma2, ac2):
                        if sb_liste:
                            sb_liste.table("cari_aciklamalar").insert({
                                "cari_id": rid2, "aciklama": ac2,
                                "olusturan": st.session_state.get("kullanici",""),
                            }).execute()
                            sb_liste.table("cari_kartlar").update({"aciklama":""}).eq("id",rid2).execute()
                        else:
                            _cx = get_conn()
                            _cx.execute("INSERT INTO cari_aciklamalar (cari_id,cari_adi,aciklama,olusturan) VALUES (?,?,?,?)",
                                (rid2, firma2, ac2, st.session_state.get("kullanici","")))
                            _cx.execute("UPDATE cari_kartlar SET aciklama='' WHERE id=?", (rid2,))
                            _cx.commit(); _cx.close()
                        return True

                    if _arsivlenecekler:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as _havuz2:
                            _gelecekler2 = [_havuz2.submit(_tek_not_arsivle, *_a) for _a in _arsivlenecekler]
                            for _g2 in concurrent.futures.as_completed(_gelecekler2):
                                try:
                                    if _g2.result():
                                        _arsiv_sayi += 1
                                except Exception:
                                    pass
                except: pass
                st.session_state.pop("_ls_tablo", None)
                # Widget'ın eski edited_rows durumunu temizle — kaydedilenler artık
                # veritabanında, bir sonraki render'da taze veriyle baştan başlasın.
                # Bu, eski izlerin yeni bir düzenlemeyi maskelemesini de önler.
                st.session_state.pop("cari_editor", None)
                if kayit_sayi > 0:
                    _ozet_msg = f"{kayit_sayi} satır kaydedildi!" + (f" · {_arsiv_sayi} not arşivlendi!" if _arsiv_sayi > 0 else "")
                    if _kaydedilen_firmalar:
                        _ozet_msg += " → " + ", ".join(_kaydedilen_firmalar[:8]) + (" ..." if len(_kaydedilen_firmalar) > 8 else "")
                elif _arsiv_sayi > 0:
                    _ozet_msg = f"{_arsiv_sayi} not arşivlendi!"
                else:
                    _ozet_msg = "Değişiklik kaydedildi."
                # Toast rerun sonrası da görünür ama kalıcı bir banner için ayrıca sakla —
                # kullanıcı notunun/kaydının gerçekten kaydedildiğini rerun sonrası da görsün.
                st.session_state["_son_kaydet_ozeti"] = "✅ " + _ozet_msg
                st.toast("✅ " + _ozet_msg, icon="✅")
                if hata_list:
                    st.error(f"Hata: {'; '.join(hata_list[:2])}")
                st.rerun()
    with btn_a:
        pass  # (Seçili → Arşive butonu kullanıcı isteğiyle kaldırıldı)

    with btn_s:
        pass  # (Seçili → Sil butonu kullanıcı isteğiyle kaldırıldı)



    # ── SAYFALAMA KONTROLLERİ KALDIRILDI — kullanıcı isteği üzerine ──────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    if _cl_toplam_kayit > 0:
        st.caption(f"Seçmek için Seç kolonunu işaretleyin · **Tümü** gösteriliyor — {_cl_toplam_kayit} kayıt")

    st.divider()


elif aktif == "dis_nakliye_toplu":
    sayfa_log("dis_nakliye_toplu")
    st.markdown("## 🚚 Dış Nakliyeler Listesi")
    st.caption("Tüm müşterilerin dış nakliye kayıtları, cari ekstre ve taşıyıcı yönetimi. Müşteri bazlı ekleme/düzenleme, o müşterinin 'Notlar & Randevu' penceresindeki 🚚 Dış Nakliye sekmesinden yapılır.")

    _dnb_tab_liste, _dnb_tab_ekstre, _dnb_tab_tasiyici = st.tabs(["📦 Tüm Kayıtlar", "🧾 Cari Ekstre", "🚛 Taşıyıcı Yönetimi"])

    with _dnb_tab_liste:
        _dnb_tum = _dis_nakliye_yukle()
        if _dnb_tum:
            _dnb_df = pd.DataFrame(_dnb_tum)
            for _c in _DIS_NAKLIYE_KOLONLAR:
                if _c not in _dnb_df.columns:
                    _dnb_df[_c] = 0 if _c in _DIS_NAKLIYE_SAYI_KOLON or _c in _DIS_NAKLIYE_HESAP_KOLON else (False if _c in _DIS_NAKLIYE_CHECK_KOLON else "")
            _dnb_df = _dis_nakliye_hesapla(_dnb_df)
            _dnb_df = _dnb_df[["id", "cari_id"] + _DIS_NAKLIYE_KOLONLAR]
            _dnb_df = _dnb_df.reset_index(drop=True)
            _dnb_df.insert(0, "Seç", False)
            _dnb_df.index = _dnb_df.index + 1
            _dnb_df.index.name = "S.No"

            st.caption(f"📌 {len(_dnb_df)} kayıt — toplam kar: {_dnb_df['kar'].sum():,.2f} ₺".replace(",", "."))
            _dnb_edited = st.data_editor(
                _dnb_df, use_container_width=True, num_rows="fixed",
                column_config={
                    **_dis_nakliye_col_config(), "id": None, "cari_id": None,
                    "Seç": st.column_config.CheckboxColumn("Seç", default=False),
                },
                key="dnb_editor",
                height=min(650, 45 + (len(_dnb_df) * 35) + 5),
            )

            _dnb_secili = _dnb_edited[_dnb_edited["Seç"] == True]
            _dnb_secili_sayi = len(_dnb_secili)
            _dnb_secili_idler = _dnb_secili["id"].tolist() if not _dnb_secili.empty else []

            _dnb_bk1, _dnb_bk2 = st.columns([1, 1])
            with _dnb_bk1:
                if st.button("💾 Değişiklikleri Kaydet", key="dnb_kaydet_btn", type="primary", use_container_width=True):
                    _dnb_final = _dnb_edited.drop(columns=["Seç"]).reset_index(drop=True).copy()
                    _dnb_final = _dis_nakliye_hesapla(_dnb_final)
                    for _c in ["id", "cari_id"]:
                        if _c not in _dnb_final.columns:
                            _dnb_final[_c] = 0
                    _dnb_final["id"] = _dnb_final["id"].apply(lambda x: int(x) if str(x).strip() not in ("", "nan", "None") and float(x) > 0 else 0)
                    _dnb_final["cari_id"] = _dnb_final["cari_id"].apply(lambda x: int(x) if str(x).strip() not in ("", "nan", "None") else 0)
                    _yeni_id_sayac_b = int(max([int(r.get("id", 0) or 0) for r in _dnb_tum], default=0)) + 1
                    _tum_yeni = []
                    for _, _row in _dnb_final.iterrows():
                        _rd = _row.to_dict()
                        if not _rd.get("id"):
                            _rd["id"] = _yeni_id_sayac_b
                            _yeni_id_sayac_b += 1
                        _tum_yeni.append(_rd)
                    if _dis_nakliye_kaydet(_tum_yeni):
                        st.toast("✅ Dış nakliye kayıtları güncellendi!", icon="✅")
                        st.rerun()
                    else:
                        st.error("❌ Kaydedilemedi, bağlantıyı kontrol et.")
            with _dnb_bk2:
                if _dnb_secili_sayi > 0:
                    if not st.session_state.get("_dnb_sil_onay_bekliyor"):
                        if st.button(f"🗑️ Seçili {_dnb_secili_sayi} Kaydı Sil", key="dnb_sil_btn", use_container_width=True):
                            st.session_state["_dnb_sil_onay_bekliyor"] = True
                            st.rerun()
                else:
                    st.caption("Silmek için satırları soldaki Seç kutusuyla işaretle.")

            if _dnb_secili_sayi > 0 and st.session_state.get("_dnb_sil_onay_bekliyor"):
                st.warning(f"⚠️ Seçili {_dnb_secili_sayi} kayıt kalıcı olarak silinecek, geri alınamaz! Silmek istediğine emin misin?")
                _dnb_sa1, _dnb_sa2 = st.columns(2)
                with _dnb_sa1:
                    if st.button(f"✅ Evet, {_dnb_secili_sayi} kaydı sil", type="primary", key="dnb_sil_onay", use_container_width=True):
                        _dnb_silinecek_idler = set(int(x) for x in _dnb_secili_idler)
                        _dnb_kalan = [r for r in _dnb_tum if int(r.get("id", 0) or 0) not in _dnb_silinecek_idler]
                        if _dis_nakliye_kaydet(_dnb_kalan):
                            st.session_state.pop("_dnb_sil_onay_bekliyor", None)
                            st.success(f"✅ {_dnb_secili_sayi} kayıt silindi!")
                            st.rerun()
                        else:
                            st.error("❌ Silinemedi, bağlantıyı kontrol et.")
                with _dnb_sa2:
                    if st.button("❌ Vazgeç", key="dnb_sil_vazgec", use_container_width=True):
                        st.session_state.pop("_dnb_sil_onay_bekliyor", None)
                        st.rerun()
        else:
            st.caption("Henüz hiç dış nakliye kaydı yok. Bir müşterinin 'Notlar & Randevu' penceresindeki 🚚 Dış Nakliye sekmesinden veya aşağıdaki taşıyıcı yönetiminden başlayabilirsin.")

    with _dnb_tab_ekstre:
        st.caption("Bir müşteri seç, o müşterinin dış nakliye üzerinden tüm cari hareketini (tarih, tutar, KDV'li, ödendi durumu, kar) tek ekranda gör.")
        _dnb_ekstre_kaynak = _dis_nakliye_yukle()
        if _dnb_ekstre_kaynak:
            _dnb_ekstre_df_tum = pd.DataFrame(_dnb_ekstre_kaynak)
            for _c in _DIS_NAKLIYE_KOLONLAR:
                if _c not in _dnb_ekstre_df_tum.columns:
                    _dnb_ekstre_df_tum[_c] = 0 if _c in _DIS_NAKLIYE_SAYI_KOLON or _c in _DIS_NAKLIYE_HESAP_KOLON else (False if _c in _DIS_NAKLIYE_CHECK_KOLON else "")
            _dnb_ekstre_df_tum = _dis_nakliye_hesapla(_dnb_ekstre_df_tum)
            _dnb_ekstre_df_tum["cari_id"] = pd.to_numeric(_dnb_ekstre_df_tum.get("cari_id", 0), errors="coerce").fillna(0).astype(int)
            _dnb_musteri_map = {}
            for _, _r in _dnb_ekstre_df_tum[_dnb_ekstre_df_tum["cari_id"] > 0].iterrows():
                _dnb_musteri_map[int(_r["cari_id"])] = str(_r.get("gonderen_firma", "")).strip() or f"Müşteri #{int(_r['cari_id'])}"
            if _dnb_musteri_map:
                _dnb_secenek_idler = sorted(_dnb_musteri_map.keys(), key=lambda cid: _dnb_musteri_map[cid])
                _dnb_secili_cid = st.selectbox(
                    "Müşteri", _dnb_secenek_idler, key="dnb_ekstre_musteri_sec",
                    format_func=lambda cid: _dnb_musteri_map.get(cid, str(cid)),
                )
                _dnb_ekstre_df = _dnb_ekstre_df_tum[_dnb_ekstre_df_tum["cari_id"] == _dnb_secili_cid].copy()
                _dnb_ekstre_df = _dnb_ekstre_df.sort_values("tarih")
                _dnb_ekstre_df["bakiye"] = (_dnb_ekstre_df["kdvli1"] * (~_dnb_ekstre_df["odendi1"].astype(bool))).cumsum()

                _ek1, _ek2, _ek3, _ek4 = st.columns(4)
                _ek1.metric("Toplam İşlem", len(_dnb_ekstre_df))
                _ek2.metric("Toplam Tutar (KDV'li)", f"{_dnb_ekstre_df['kdvli1'].sum():,.2f} ₺".replace(",", "."))
                _ek3.metric("Ödenmemiş Tutar", f"{_dnb_ekstre_df.loc[~_dnb_ekstre_df['odendi1'].astype(bool), 'kdvli1'].sum():,.2f} ₺".replace(",", "."))
                _ek4.metric("Toplam Kar", f"{_dnb_ekstre_df['kar'].sum():,.2f} ₺".replace(",", "."))

                _dnb_ekstre_goster = _dnb_ekstre_df[[
                    "tarih", "alici_firma", "adet1", "fiyat1", "yekun1", "kdvli1", "odendi1", "bakiye", "kar"
                ]].rename(columns={
                    "tarih": "Tarih", "alici_firma": "Alıcı Firma", "adet1": "Adet", "fiyat1": "Birim Fiyat",
                    "yekun1": "Yekün", "kdvli1": "KDV'li Tutar", "odendi1": "Ödendi",
                    "bakiye": "Ödenmemiş Bakiye (Kümülatif)", "kar": "Kar",
                })
                _dnb_ekstre_goster = _dnb_ekstre_goster.reset_index(drop=True)
                _dnb_ekstre_goster.index = _dnb_ekstre_goster.index + 1
                _dnb_ekstre_goster.index.name = "S.No"
                st.dataframe(
                    _dnb_ekstre_goster, use_container_width=True,
                    column_config={
                        "Birim Fiyat": st.column_config.NumberColumn(format="%.2f ₺"),
                        "Yekün": st.column_config.NumberColumn(format="%.2f ₺"),
                        "KDV'li Tutar": st.column_config.NumberColumn(format="%.2f ₺"),
                        "Ödenmemiş Bakiye (Kümülatif)": st.column_config.NumberColumn(format="%.2f ₺"),
                        "Kar": st.column_config.NumberColumn(format="%.2f ₺"),
                    },
                )
            else:
                st.caption("Kayıtlarda müşteri bilgisi bulunamadı.")
        else:
            st.caption("Henüz hiç dış nakliye kaydı yok.")

    with _dnb_tab_tasiyici:
        st.caption("Sık kullanılan taşıyıcıları (tedarikçileri) burada kaydet — dış nakliye kaydı eklerken listeden seçip otomatik doldurabilirsin.")
        _dnb_tas = _dis_nakliye_tasiyici_yukle()
        if _dnb_tas:
            _dnb_tas_df = pd.DataFrame(_dnb_tas)
            for _c in ["tasiyici", "yetkili", "yetkili_tel"]:
                if _c not in _dnb_tas_df.columns:
                    _dnb_tas_df[_c] = ""
            _dnb_tas_df = _dnb_tas_df[["tasiyici", "yetkili", "yetkili_tel"]]
            _dnb_tas_df = _dnb_tas_df.reset_index(drop=True)
            _dnb_tas_df.index = _dnb_tas_df.index + 1
            _dnb_tas_df.index.name = "S.No"
            _dnb_tas_edited = st.data_editor(
                _dnb_tas_df, use_container_width=True, num_rows="dynamic",
                column_config={
                    "tasiyici": st.column_config.TextColumn("Taşıyıcı", width=150),
                    "yetkili": st.column_config.TextColumn("Yetkili", width=130),
                    "yetkili_tel": st.column_config.TextColumn("Yetkili Tel", width=110),
                },
                key="dnb_tasiyici_editor",
            )
            if st.button("💾 Taşıyıcıları Kaydet", key="dnb_tas_kaydet_btn", type="primary"):
                _dnb_tas_final = _dnb_tas_edited.reset_index(drop=True).to_dict(orient="records")
                if _dis_nakliye_tasiyici_kaydet(_dnb_tas_final):
                    st.toast("✅ Taşıyıcılar güncellendi!", icon="✅")
                    st.rerun()
                else:
                    st.error("❌ Kaydedilemedi, bağlantıyı kontrol et.")
        else:
            st.caption("Henüz kayıtlı taşıyıcı yok.")
            _dnbt1, _dnbt2, _dnbt3 = st.columns(3)
            _dnb_yeni_tas = _dnbt1.text_input("Taşıyıcı", key="dnb_yeni_tas")
            _dnb_yeni_yet = _dnbt2.text_input("Yetkili", key="dnb_yeni_yet")
            _dnb_yeni_tel = _dnbt3.text_input("Yetkili Tel", key="dnb_yeni_tel")
            if st.button("➕ Taşıyıcı Ekle", key="dnb_yeni_tas_ekle") and _dnb_yeni_tas.strip():
                _dis_nakliye_tasiyici_kaydet([{"tasiyici": _dnb_yeni_tas, "yetkili": _dnb_yeni_yet, "yetkili_tel": _dnb_yeni_tel}])
                st.rerun()

elif aktif == "dis_nakliye":
    sayfa_log("dis_nakliye")
    st.markdown("""<style>
.block-container { padding-left: 0.6rem !important; padding-right: 0.6rem !important; max-width: 100% !important; }
[data-testid="stAppViewContainer"] { max-width: 100% !important; }
div[data-testid="stHorizontalBlock"] { gap: 0.3rem !important; justify-content: flex-start !important; }
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] { padding: 0 !important; }
div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(1) {
    flex: 0 1 auto !important; max-width: none !important; width: auto !important;
}
div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(2) {
    max-width: 260px !important; flex: 0 0 260px !important; width: 260px !important;
}
</style>""", unsafe_allow_html=True)

    _dn_kolonlar = [
        "tarih", "gonderen_firma", "gonderici_tel", "gonderen_adres", "gonderen_il", "gonderen_ilce",
        "alici_firma", "alici_tel", "alici_adres", "alici_il", "alici_ilce",
        "odeme_yapacak_musteri", "fatura_adresi", "vergi_dairesi", "vergi_no", "yetkili_tel", "odeme_turu",
        "adet", "tur", "tasiyici", "tasiyici_fatura", "tasiyici_odendi",
        "stf_faturasi", "stf_odendi", "kar"
    ]
    _dn_basliklar = {
        "tarih": "TARİH",
        "gonderen_firma": "GÖNDEREN FİRMA", "gonderici_tel": "GÖNDERİCİ TEL", "gonderen_adres": "GÖNDEREN ADRESİ",
        "gonderen_il": "GÖNDEREN İL", "gonderen_ilce": "GÖNDEREN İLÇE",
        "alici_firma": "ALICI FİRMA", "alici_tel": "ALICI TEL", "alici_adres": "ALICI ADRES",
        "alici_il": "ALICI İL", "alici_ilce": "ALICI İLÇE",
        "odeme_yapacak_musteri": "ÖDEME YAPACAK MÜŞTERİ", "fatura_adresi": "FATURA ADRESİ",
        "vergi_dairesi": "VERGİ DAİRESİ", "vergi_no": "VERGİ NO", "yetkili_tel": "YETKİLİ TEL",
        "odeme_turu": "ÖDEME TÜRÜ", "adet": "ADET", "tur": "TÜR", "tasiyici": "TAŞIYICI",
        "tasiyici_fatura": "TAŞIYICI FATURA", "tasiyici_odendi": "ÖDENDİ",
        "stf_faturasi": "STF FATURASI", "stf_odendi": "ÖDENDİ", "kar": "KAR"
    }
    # Cari Liste ile AYNI ölçekte kompakt piksel genişlikleri — tüm kolonlar
    # tek ekrana sığsın diye iyice daraltıldı
    _dn_pixel_genislik = {
        "tarih":85,"gonderen_firma":115,"gonderici_tel":95,"gonderen_adres":115,"gonderen_il":80,"gonderen_ilce":80,
        "alici_firma":115,"alici_tel":95,"alici_adres":115,"alici_il":80,"alici_ilce":80,
        "odeme_yapacak_musteri":135,"fatura_adresi":115,"vergi_dairesi":95,"vergi_no":85,"yetkili_tel":95,
        "odeme_turu":85,"adet":60,"tur":80,"tasiyici":95,"tasiyici_fatura":100,"tasiyici_odendi":70,
        "stf_faturasi":100,"stf_odendi":70,"kar":85
    }

    # ── Yükle — kullanici_tercih tablosunda TEK bir JSON kayıt olarak
    # saklanır (yeni tablo açmadan). Sayfa açılışında bir kere çekilir. ──────
    if "_dn_kayitlar" not in st.session_state:
        st.session_state["_dn_kayitlar"] = []
        try:
            _sb_dn0 = get_sb_client()
            if _sb_dn0:
                import json as _dnj0
                _r_dn0 = _sb_dn0.table("kullanici_tercih").select("deger").eq(
                    "kullanici", "__liste_ui__").eq("anahtar", "dis_nakliye_kayitlari").execute()
                if _r_dn0.data:
                    st.session_state["_dn_kayitlar"] = _dnj0.loads(_r_dn0.data[0]["deger"])
        except Exception:
            pass

    _dn_liste = st.session_state["_dn_kayitlar"]
    if _dn_liste:
        _dn_df = pd.DataFrame(_dn_liste)
        for _k in _dn_kolonlar:
            if _k not in _dn_df.columns:
                _dn_df[_k] = 0 if _k in ("adet", "kar", "tasiyici_fatura", "stf_faturasi") else ("" if _k not in ("tasiyici_odendi","stf_odendi") else False)
        _dn_df = _dn_df[_dn_kolonlar]
    else:
        _dn_df = pd.DataFrame(columns=_dn_kolonlar)

    if _dn_df.empty:
        _dn_df = pd.DataFrame([{c: (0 if c in ("adet","kar","tasiyici_fatura","stf_faturasi") else (False if c in ("tasiyici_odendi","stf_odendi") else "")) for c in _dn_kolonlar}]).iloc[0:0]
    _dn_df["adet"] = pd.to_numeric(_dn_df["adet"], errors="coerce").fillna(0).astype(int)
    _dn_df["tasiyici_fatura"] = pd.to_numeric(_dn_df["tasiyici_fatura"], errors="coerce").fillna(0.0)
    _dn_df["stf_faturasi"] = pd.to_numeric(_dn_df["stf_faturasi"], errors="coerce").fillna(0.0)
    # KAR otomatik hesaplanır — STF Faturası TUTARI eksi Taşıyıcı Fatura TUTARI.
    # Manuel yazılamaz (disabled), kaydettikçe otomatik güncellenir.
    _dn_df["kar"] = _dn_df["stf_faturasi"] - _dn_df["tasiyici_fatura"]
    _dn_df["tasiyici_odendi"] = _dn_df["tasiyici_odendi"].apply(lambda x: bool(x) if str(x).strip() not in ["", "nan", "None"] else False)
    _dn_df["stf_odendi"] = _dn_df["stf_odendi"].apply(lambda x: bool(x) if str(x).strip() not in ["", "nan", "None"] else False)
    for _tk in ["tarih","gonderen_firma","gonderici_tel","gonderen_adres","gonderen_il","gonderen_ilce",
                "alici_firma","alici_tel","alici_adres","alici_il","alici_ilce",
                "odeme_yapacak_musteri","fatura_adresi","vergi_dairesi","vergi_no","yetkili_tel","odeme_turu","tur","tasiyici"]:
        _dn_df[_tk] = _dn_df[_tk].astype(str).replace(["nan","None"], "")

    _dn_df = _dn_df.reset_index(drop=True)
    _dn_df.index = _dn_df.index + 1
    _dn_df.index.name = "S.No"

    _dn_col_config = {}
    for _k in _dn_kolonlar:
        _dn_w = _dn_pixel_genislik.get(_k, 90)
        if _k == "adet":
            _dn_col_config[_k] = st.column_config.NumberColumn(_dn_basliklar[_k], min_value=0, step=1, width=_dn_w)
        elif _k == "kar":
            _dn_col_config[_k] = st.column_config.NumberColumn(_dn_basliklar[_k], format="%.2f ₺", width=_dn_w, disabled=True, help="Otomatik hesaplanır: STF Faturası − Taşıyıcı Fatura")
        elif _k in ("tasiyici_fatura", "stf_faturasi"):
            _dn_col_config[_k] = st.column_config.NumberColumn(_dn_basliklar[_k], format="%.2f ₺", width=_dn_w, min_value=0)
        elif _k in ("tasiyici_odendi", "stf_odendi"):
            _dn_col_config[_k] = st.column_config.CheckboxColumn(_dn_basliklar[_k], width=_dn_w)
        else:
            _dn_col_config[_k] = st.column_config.TextColumn(_dn_basliklar[_k], width=_dn_w)

    _dn_ana_col, _dn_yan_col = st.columns([2.6, 1], gap="small")
    with _dn_ana_col:
        _dn_yukseklik = max(650, min(800, 38 + (max(len(_dn_df), 3) * 35) + 3))
        _dn_edited = st.data_editor(
            _dn_df,
            use_container_width=True,
            num_rows="dynamic",
            column_config=_dn_col_config,
            key="dn_editor",
            height=_dn_yukseklik
        )

        _dn_k1, _dn_k2, _dn_k3 = st.columns([1, 1, 4])
        with _dn_k1:
            if st.button("💾 Kaydet", type="primary", key="dn_kaydet_btn"):
                _dn_final_df = _dn_edited.reset_index(drop=True).copy()
                # KAR'ı en güncel Taşıyıcı Fatura / STF Faturası değerlerinden
                # yeniden hesapla — disabled kolon canlı güncellenmediği için
                # kaydetme anında kesin doğru değeri burada üretiyoruz.
                _dn_final_df["tasiyici_fatura"] = pd.to_numeric(_dn_final_df["tasiyici_fatura"], errors="coerce").fillna(0.0)
                _dn_final_df["stf_faturasi"] = pd.to_numeric(_dn_final_df["stf_faturasi"], errors="coerce").fillna(0.0)
                _dn_final_df["kar"] = _dn_final_df["stf_faturasi"] - _dn_final_df["tasiyici_fatura"]
                _dn_kayit_listesi = _dn_final_df.to_dict(orient="records")
                _dn_kaydedildi = False
                _dn_hata_msg = ""
                try:
                    _sb_dn1 = get_sb_client()
                    if _sb_dn1:
                        import json as _dnj1
                        _dn_json_str = _dnj1.dumps(_dn_kayit_listesi, ensure_ascii=False)
                        _sb_dn1.table("kullanici_tercih").upsert({
                            "kullanici": "__liste_ui__", "anahtar": "dis_nakliye_kayitlari",
                            "deger": _dn_json_str
                        }, on_conflict="kullanici,anahtar").execute()
                        # Doğrulama — gerçekten yazıldı mı diye geri okuyoruz
                        _dn_dogrula = _sb_dn1.table("kullanici_tercih").select("deger").eq(
                            "kullanici", "__liste_ui__").eq("anahtar", "dis_nakliye_kayitlari").execute()
                        if _dn_dogrula.data and _dn_dogrula.data[0]["deger"] == _dn_json_str:
                            _dn_kaydedildi = True
                        else:
                            _dn_hata_msg = "Yazma işlemi doğrulanamadı — veritabanına ulaşmamış olabilir."
                    else:
                        _dn_hata_msg = "Supabase bağlantısı yok."
                except Exception as _dn_e:
                    _dn_hata_msg = str(_dn_e)

                if _dn_kaydedildi:
                    st.session_state["_dn_kayitlar"] = _dn_kayit_listesi
                    st.toast(f"✅ {len(_dn_kayit_listesi)} kayıt kaydedildi!", icon="✅")
                    st.success(f"✅ {len(_dn_kayit_listesi)} kayıt kaydedildi ve doğrulandı!")
                    st.rerun()
                else:
                    st.error(f"❌ Kaydedilemedi: {_dn_hata_msg}")
        with _dn_k2:
            if st.button("➕ Satır Ekle", key="dn_satir_ekle_btn"):
                _dn_bos_satir = {c: (0 if c in ("adet","kar","tasiyici_fatura","stf_faturasi") else (False if c in ("tasiyici_odendi","stf_odendi") else "")) for c in _dn_kolonlar}
                _dn_guncel_liste = _dn_edited.reset_index(drop=True).to_dict(orient="records")
                _dn_guncel_liste.append(_dn_bos_satir)
                st.session_state["_dn_kayitlar"] = _dn_guncel_liste
                st.rerun()
    with _dn_yan_col:
        st.markdown("**🧮 KDV Hesaplayıcı**")
        _dn_h_adet = st.number_input("Adet", min_value=0, value=0, step=1, key="dn_hesap_adet")
        _dn_h_birim = st.number_input("Birim Fiyat", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="dn_hesap_birim")
        _dn_h_kdv = st.number_input("KDV (%)", min_value=0.0, value=20.0, step=1.0, key="dn_hesap_kdv")
        _dn_h_toplam = _dn_h_adet * _dn_h_birim
        _dn_h_kdvli = _dn_h_toplam * (1 + _dn_h_kdv / 100)
        st.divider()
        st.metric("Toplam Tutar", f"{_dn_h_toplam:,.2f} ₺")
        st.metric("KDV'li Tutar", f"{_dn_h_kdvli:,.2f} ₺")


elif aktif == "kullanici":
    sayfa_log("kullanici")
    st.markdown("## 👥 Kullanıcı & Firma Yönetimi")

    _ben = st.session_state.get("kullanici","")
    _rol = st.session_state.get("rol","")

    # ── NORMAL KULLANICI — sadece şifre + kendi logu ──────────────────────────
    if _rol != "admin":
        ut1, ut2 = st.tabs(["🔑 Şifre Değiştir", "📊 Aktivitelerim"])

        with ut1:
            st.markdown(f"**👤 {_ben}** — Şifrenizi değiştirin")
            with st.form("kendi_sifre_form"):
                _eski = st.text_input("Mevcut Şifre:", type="password")
                _yeni1 = st.text_input("Yeni Şifre:", type="password")
                _yeni2 = st.text_input("Yeni Şifre Tekrar:", type="password")
                if st.form_submit_button("💾 Şifremi Değiştir", type="primary", use_container_width=True):
                    if not _eski or not _yeni1 or not _yeni2:
                        st.warning("Tüm alanları doldurun!")
                    elif _yeni1 != _yeni2:
                        st.error("Yeni şifreler eşleşmiyor!")
                    elif len(_yeni1) < 4:
                        st.warning("Şifre en az 4 karakter olmalı!")
                    else:
                        # Eski şifreyi doğrula
                        _df_ben = db_read("kullanicilar", extra_sql="")
                        if not _df_ben.empty:
                            _satir = _df_ben[_df_ben["kullanici_adi"]==_ben]
                            if not _satir.empty:
                                if str(_satir.iloc[0].get("sifre","")) == _eski:
                                    db_update("kullanicilar",{"sifre":_yeni1},"kullanici_adi",_ben)
                                    try: db_read.clear()
                                    except: pass
                                    kullanici_log_kaydet("SIFRE_DEGISTIRDI","kullanici","Kendi şifresini değiştirdi")
                                    st.success("✅ Şifreniz güncellendi!")
                                else:
                                    st.error("❌ Mevcut şifre hatalı!")

        with ut2:
            st.markdown(f"**📊 {_ben} — Aktivite Geçmişim**")
            _sb_ut = get_sb_client()
            try:
                _r_klog = _sb_ut.table("kullanici_log").select("*") \
                    .eq("kullanici",_ben).order("tarih",desc=True).limit(100).execute()
                _df_klog = pd.DataFrame(_r_klog.data) if _r_klog.data else pd.DataFrame()
            except:
                _df_klog = pd.DataFrame()

            if _df_klog.empty:
                st.info("Henüz aktivite kaydı yok.")
            else:
                km1,km2,km3 = st.columns(3)
                km1.metric("Toplam İşlem", len(_df_klog))
                _bugun_k = len(_df_klog[pd.to_datetime(_df_klog["tarih"],errors="coerce").dt.date == pd.Timestamp.now().date()])
                km2.metric("Bugün", _bugun_k)
                km3.metric("Son Giriş", str(_df_klog[_df_klog["islem"]=="GİRİŞ_YAPILDI"]["tarih"].max())[:16] if "GİRİŞ_YAPILDI" in _df_klog["islem"].values else "—")
                st.dataframe(
                    _df_klog[["tarih","sayfa","islem","detay"]].rename(
                        columns={"tarih":"Tarih","sayfa":"Sayfa","islem":"İşlem","detay":"Detay"}
                    ).assign(Tarih=_df_klog["tarih"].astype(str).str[:16]),
                    use_container_width=True, hide_index=True
                )
        st.stop()

    # ── ADMİN — tam yetki ─────────────────────────────────────────────────────
    TUM_MENULER = {
        "yeni":"➕ Yeni Kart","liste":"📋 Cari Liste","randevu":"📅 Randevular",
        "rapor":"📊 Raporlar",
        "excel":"📥 Excel","mesajlar":"💬 Mesajlar",
        "admin_rapor":"📊 Rapor Tasarla","kullanici_log":"📊 Kullanıcı Log",
        "surum_yonetimi":"🚀 Sürüm Yönetimi"
    }

    # Sürüm Yönetimi sekmesi: sadece admin VEYA yetkisi olan kullanıcı
    _surum_yetkisi = (
        st.session_state.get("rol") == "admin" or
        "surum_yonetimi" in str(st.session_state.get("_yetki_listesi",""))
    )

    if st.session_state.get("rol") == "admin":
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5, kul_tab5_ekran, kul_tab_tanim, kul_tab_kolon, kul_tab_toplu, kul_tab_font, kul_tab_kural = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi","🎨 Ekran Ayarları","⚙️ Tanımlar","📐 Kolon Ayarları","🔄 Toplu Değiştir","🔤 Fontlar","📌 Kurallar"])
    elif _surum_yetkisi:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5, kul_tab5_ekran, kul_tab_tanim, kul_tab_kolon, kul_tab_toplu, kul_tab_font, kul_tab_kural = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi","🎨 Ekran Ayarları","⚙️ Tanımlar","📐 Kolon Ayarları","🔄 Toplu Değiştir","🔤 Fontlar","📌 Kurallar"])
    else:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5_ekran, kul_tab_tanim, kul_tab_kolon, kul_tab_toplu, kul_tab_font, kul_tab_kural = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🎨 Ekran Ayarları","⚙️ Tanımlar","📐 Kolon Ayarları","🔄 Toplu Değiştir","🔤 Fontlar","📌 Kurallar"])
        kul_tab5 = None

    with kul_tab1:
        df_kul = db_read("kullanicilar", extra_sql="")
        if not df_kul.empty:
            goster_k = [c for c in ["id","kullanici_adi","ad","soyad","email","telefon","rol","yetkiler"] if c in df_kul.columns]
            st.dataframe(df_kul[goster_k], use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("#### 🔑 Şifre Değiştir")
            sp1,sp2,sp3 = st.columns(3)
            s_opts = [f"[{int(r['id'])}] {r['kullanici_adi']}" for _,r in df_kul.iterrows()]
            s_sec = sp1.selectbox("Kullanıcı:",s_opts,key="sifre_kul")
            s1 = sp2.text_input("Yeni Şifre:",type="password",key="yeni_sif1")
            s2 = sp3.text_input("Tekrar:",type="password",key="yeni_sif2")
            if st.button("🔑 Şifreyi Güncelle", use_container_width=True):
                if s1 and s1 == s2:
                    try:
                        _sb_sf = get_sb_client()
                        _sf_id = int(s_sec.split("]")[0].replace("[",""))
                        if _sb_sf:
                            _sb_sf.table("kullanicilar").update({"sifre": s1}).eq("id", _sf_id).execute()
                        try: db_read.clear()
                        except: pass
                        st.success("✅ Şifre güncellendi! Yeni şifre ile giriş yapabilirsiniz.")
                    except Exception as _sfe:
                        st.error(f"Hata: {_sfe}")
                else:
                    st.error("Şifreler eşleşmiyor veya boş!")

            st.divider()
            st.markdown("#### 🗑️ Kullanıcı Sil")
            sil_opts = [f"[{int(r['id'])}] {r['kullanici_adi']}" for _,r in df_kul.iterrows() if r["kullanici_adi"]!="admin"]
            if sil_opts:
                sil_sec = st.selectbox("Silinecek:",sil_opts,key="sil_kul")
                if st.button("🗑️ Sil",type="primary"):
                    sil_id = int(sil_sec.split("]")[0].replace("[",""))
                    sb_s = get_sb_client()
                    if sb_s:
                        sb_s.table("kullanicilar").delete().eq("id",sil_id).execute()
                    st.success("Silindi!"); st.rerun()

    with kul_tab2:
        st.markdown("#### ➕ Yeni Kullanıcı")
        with st.form("yeni_kul_form"):
            f1,f2 = st.columns(2)
            yk_ad      = f1.text_input("Ad*")
            yk_soyad   = f2.text_input("Soyad")
            yk_kadi    = f1.text_input("Kullanıcı Adı*")
            yk_sifre   = f2.text_input("Şifre*", type="password")
            yk_email   = f1.text_input("Email")
            yk_tel     = f2.text_input("Telefon", placeholder="05xxxxxxxxx")
            yk_rol     = f1.selectbox("Rol:", ["kullanici","admin"])

            st.markdown("#### 🔐 Menü Yetkileri")
            tam = st.checkbox("✅ Tam Yetki (Tümü)", value=True, key="yk_tam")
            secili_m = []
            if not tam:
                mc = st.columns(3)
                for i,(k,v) in enumerate(TUM_MENULER.items()):
                    if mc[i%3].checkbox(v, value=True, key=f"yk_m_{k}"):
                        secili_m.append(k)

            if st.form_submit_button("💾 Kaydet", use_container_width=True, type="primary"):
                if yk_kadi and yk_sifre:
                    _kadi_cakisiyor = False
                    try:
                        _df_mevcut = db_read("kullanicilar", extra_sql="")
                        if not _df_mevcut.empty and "kullanici_adi" in _df_mevcut.columns:
                            _kadi_cakisiyor = yk_kadi.strip().lower() in _df_mevcut["kullanici_adi"].astype(str).str.strip().str.lower().values
                    except Exception:
                        _kadi_cakisiyor = False

                    if _kadi_cakisiyor:
                        st.error(f"⚠️ '{yk_kadi}' kullanıcı adı zaten kayıtlı. Lütfen başka bir kullanıcı adı seçin.")
                        st.stop()

                    yetki = "tam" if tam else json.dumps(secili_m)
                    # Önce temel kolonlarla dene
                    veri = {"kullanici_adi": yk_kadi, "sifre": yk_sifre, "rol": yk_rol}
                    # Ek kolonları tek tek ekle
                    sb_k = get_sb_client()
                    if sb_k:
                        try:
                            # Tam veri ile dene
                            sb_k.table("kullanicilar").insert({
                                **veri, "ad": yk_ad, "soyad": yk_soyad,
                                "email": yk_email, "telefon": yk_tel, "yetkiler": yetki
                            }).execute()
                            st.success(f"✅ '{yk_kadi}' eklendi!")
                            st.rerun()
                        except Exception as e1:
                            if "duplicate key" in str(e1).lower() or "23505" in str(e1):
                                st.error(f"⚠️ '{yk_kadi}' kullanıcı adı zaten kayıtlı. Lütfen başka bir kullanıcı adı seçin.")
                            else:
                                try:
                                    # Sadece temel kolonlarla dene
                                    sb_k.table("kullanicilar").insert(veri).execute()
                                    st.success(f"✅ '{yk_kadi}' eklendi! (Ek bilgiler için Supabase'e kolon ekleyin)")
                                    st.rerun()
                                except Exception as e2:
                                    if "duplicate key" in str(e2).lower() or "23505" in str(e2):
                                        st.error(f"⚠️ '{yk_kadi}' kullanıcı adı zaten kayıtlı. Lütfen başka bir kullanıcı adı seçin.")
                                    else:
                                        st.error(f"Hata: {e2}")
                    else:
                        try:
                            conn_k = get_conn()
                            conn_k.execute("INSERT INTO kullanicilar (kullanici_adi,sifre,rol) VALUES (?,?,?)",
                                (yk_kadi, yk_sifre, yk_rol))
                            conn_k.commit(); conn_k.close()
                            st.success(f"✅ '{yk_kadi}' eklendi!")
                            st.rerun()
                        except Exception as e3:
                            if "unique" in str(e3).lower() or "duplicate" in str(e3).lower():
                                st.error(f"⚠️ '{yk_kadi}' kullanıcı adı zaten kayıtlı. Lütfen başka bir kullanıcı adı seçin.")
                            else:
                                st.error(f"Hata: {e3}")
                else:
                    st.warning("Kullanıcı adı ve şifre zorunlu!")

    with kul_tab3:
        st.markdown("#### 🔐 Yetki Düzenle")
        df_kul3 = db_read("kullanicilar", extra_sql="")
        if not df_kul3.empty:
            k3_opts = [f"[{int(r['id'])}] {r['kullanici_adi']}" for _,r in df_kul3.iterrows()]
            k3_sec  = st.selectbox("Kullanıcı:", k3_opts, key="yetki_sec")
            k3_id   = int(k3_sec.split("]")[0].replace("[",""))
            _k3m = df_kul3[df_kul3["id"]==k3_id]
            if _k3m.empty: raise Exception("Kullanıcı bulunamadı")
            k3_row = _k3m.iloc[0]

            mv = str(k3_row.get("yetkiler","tam") or "tam")
            try:
                mv_liste = json.loads(mv) if mv!="tam" else list(TUM_MENULER.keys())
                tam2 = mv=="tam"
            except:
                mv_liste = list(TUM_MENULER.keys()); tam2 = True

            tam2_cb = st.checkbox("✅ Tam Yetki", value=tam2, key="yetki_tam2")
            yeni_liste = []
            if not tam2_cb:
                mc2 = st.columns(3)
                for i,(k,v) in enumerate(TUM_MENULER.items()):
                    if mc2[i%3].checkbox(v, value=k in mv_liste, key=f"yetki2_{k}"):
                        yeni_liste.append(k)

            if st.button("💾 Yetkileri Kaydet", use_container_width=True, type="primary"):
                ystr = "tam" if tam2_cb else json.dumps(yeni_liste)
                db_update("kullanicilar",{"yetkiler":ystr},"id",k3_id)
                try: db_read.clear()
                except: pass
                st.success("✅ Yetkiler güncellendi!"); st.rerun()

    with kul_tab4:
        st.markdown("### 📊 Kullanıcı Aktivite Logu")
        st.caption("Kim giriş yaptı, hangi sayfaya girdi, ne yaptı — tarih saat ile")

        _sb_log = get_sb_service()
        _df_log = pd.DataFrame()
        _log_hata = ""

        try:
            if _sb_log:
                _r_log = _sb_log.table("kullanici_log").select("*").order("tarih", desc=True).limit(1000).execute()
                _df_log = pd.DataFrame(_r_log.data) if _r_log.data else pd.DataFrame()
            else:
                _log_hata = "Supabase bağlantısı yok"
        except Exception as _e_log:
            _log_hata = str(_e_log)
            st.error(f"Log yüklenemedi: {_e_log}")

        # Test log butonu
        col_test1, col_test2 = st.columns(2)
        with col_test1:
            if st.button("🔄 Logları Yenile", key="log_yenile", use_container_width=True):
                kullanici_log_kaydet("LOG_SAYFASI_YENİLENDİ", "kullanici", "Admin log sayfasını yeniledi")
                st.rerun()
        with col_test2:
            if st.button("🧪 Test Log Yaz", key="log_test", use_container_width=True):
                try:
                    _sb_log.table("kullanici_log").insert({
                        "kullanici": st.session_state.get("kullanici","admin"),
                        "rol": st.session_state.get("rol","admin"),
                        "sayfa": "test",
                        "islem": "TEST_LOG",
                        "detay": "Manuel test logu yazıldı",
                    }).execute()
                    st.success("✅ Test logu yazıldı! Şimdi yenile.")
                except Exception as _et:
                    st.error(f"Test log hatası: {_et}")

        if _log_hata:
            st.warning(f"⚠️ {_log_hata}")

        if _df_log.empty:
            st.warning("Log kaydı yok. 'Test Log Yaz' butonuna basıp 'Logları Yenile' dene.")
            st.info("Eğer test logu da yazılmıyorsa Supabase'de tablo/izin sorunu var.")
        else:
            # Filtreler
            lf1, lf2, lf3, lf4 = st.columns(4)
            _log_kullar = ["Tümü"] + sorted(_df_log["kullanici"].dropna().unique().tolist())
            _log_islemler = ["Tümü"] + sorted(_df_log["islem"].dropna().unique().tolist())
            _fil_kul  = lf1.selectbox("Kullanıcı:", _log_kullar, key="log_fil_kul")
            _fil_isl  = lf2.selectbox("İşlem:", _log_islemler, key="log_fil_isl")
            _fil_gun  = lf3.date_input("Tarihten:", key="log_fil_gun", value=None)
            _fil_ara  = lf4.text_input("🔍 Ara:", key="log_fil_ara", placeholder="Detay ara...")

            _df_fil = _df_log.copy()
            if _fil_kul  != "Tümü": _df_fil = _df_fil[_df_fil["kullanici"] == _fil_kul]
            if _fil_isl  != "Tümü": _df_fil = _df_fil[_df_fil["islem"] == _fil_isl]
            if _fil_gun: _df_fil = _df_fil[pd.to_datetime(_df_fil["tarih"], errors="coerce").dt.date >= _fil_gun]
            if _fil_ara: _df_fil = _df_fil[_df_fil.apply(lambda r: _fil_ara.lower() in str(r).lower(), axis=1)]

            st.caption(f"**{len(_df_fil)} kayıt**")

            # Özet metrikler
            lm1,lm2,lm3,lm4,lm5 = st.columns(5)
            lm1.metric("Toplam İşlem", len(_df_log))
            lm2.metric("Aktif Kullanıcı", _df_log["kullanici"].nunique())
            _bugun = pd.Timestamp.now().date()
            _bugun_log = _df_log[pd.to_datetime(_df_log["tarih"],errors="coerce").dt.date == _bugun]
            lm3.metric("Bugün", len(_bugun_log))
            _giris_say = len(_df_log[_df_log["islem"]=="GİRİŞ_YAPILDI"])
            lm4.metric("Toplam Giriş", _giris_say)
            lm5.metric("Filtrede", len(_df_fil))

            st.divider()

            # Kullanıcı bazlı özet
            with st.expander("👤 Kullanıcı Bazlı Özet"):
                _kul_oz = _df_log.groupby("kullanici").agg(
                    İşlem=("id","count"),
                    SonGiriş=("tarih","max"),
                    Sayfalar=("sayfa", lambda x: ", ".join(x.dropna().unique()[:5]))
                ).reset_index().sort_values("İşlem", ascending=False)
                _kul_oz["SonGiriş"] = _kul_oz["SonGiriş"].astype(str).str[:16]
                st.dataframe(_kul_oz, use_container_width=True, hide_index=True)

            # Sayfa bazlı özet
            with st.expander("📄 Sayfa Bazlı Ziyaret"):
                _sayfa_oz = _df_log.groupby("sayfa").agg(
                    Ziyaret=("id","count"),
                    Kullanıcı=("kullanici","nunique")
                ).reset_index().sort_values("Ziyaret", ascending=False)
                st.dataframe(_sayfa_oz, use_container_width=True, hide_index=True)

            # İşlem bazlı özet
            with st.expander("⚡ İşlem Bazlı Özet"):
                _isl_oz = _df_log.groupby("islem").agg(
                    Adet=("id","count"),
                    Kullanıcı=("kullanici","nunique")
                ).reset_index().sort_values("Adet", ascending=False)
                st.dataframe(_isl_oz, use_container_width=True, hide_index=True)

            st.divider()

            # Detay tablo
            st.markdown("**📋 Detaylı Log:**")
            _gos_kol = [c for c in ["tarih","kullanici","rol","sayfa","islem","detay"] if c in _df_fil.columns]
            _df_gos = _df_fil[_gos_kol].copy()
            _df_gos["tarih"] = _df_gos["tarih"].astype(str).str[:16]
            st.dataframe(_df_gos, use_container_width=True, hide_index=True)

            # Excel indir
            import io as _log_io
            _buf_log = _log_io.BytesIO()
            _df_fil.to_excel(_buf_log, index=False); _buf_log.seek(0)
            st.download_button(
                "📥 Log Excel İndir",
                data=_buf_log,
                file_name=f"kullanici_log_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                use_container_width=True
            )

            # Log temizle (sadece admin)
            with st.expander("🗑️ Log Temizle"):
                st.warning("Dikkat: Bu işlem geri alınamaz!")
                _sil_gun = st.number_input("Kaç günden eski logları sil:", min_value=7, value=30, step=1)
                if st.button("🗑️ Eski Logları Sil", type="primary"):
                    try:
                        from datetime import timedelta
                        _esik = (pd.Timestamp.now() - timedelta(days=int(_sil_gun))).isoformat()
                        _sb_log.table("kullanici_log").delete().lt("tarih", _esik).execute()
                        st.success(f"✅ {_sil_gun} günden eski loglar silindi!")
                        st.rerun()
                    except Exception as _e_del:
                        st.error(f"Silinemedi: {_e_del}")

    with kul_tab5_ekran:
        st.markdown("### 🎨 Ekran Ayarları")
        _sb_ekran = get_sb_client()
        _ekran_kul = st.session_state.get("kullanici","")

        def _ekran_yukle():
            try:
                if _sb_ekran:
                    _r = _sb_ekran.table("kullanici_tercih").select("deger").eq("kullanici",_ekran_kul).eq("anahtar","ekran_ayar").execute()
                    if _r.data:
                        import json as _ej
                        return _ej.loads(_r.data[0]["deger"])
            except: pass
            return {"bosluk":"normal","tema":"beyaz"}

        def _ekran_kaydet(ayar):
            try:
                import json as _ej
                if _sb_ekran:
                    _sb_ekran.table("kullanici_tercih").upsert({
                        "kullanici":_ekran_kul,"anahtar":"ekran_ayar",
                        "deger":_ej.dumps(ayar,ensure_ascii=False)
                    },on_conflict="kullanici,anahtar").execute()
                    return True
            except: pass
            return False

        _mevcut = _ekran_yukle()

        # ── SAYFA BOŞLUĞU ───────────────────────────────────────────────────
        # ── EKRAN ANALİZİ + BOŞLUK AYARI ────────────────────────────────────
        st.markdown("#### 🖥️ Ekran Analizi & Boşluk Ayarı")

        # Mevcut px değerlerini session veya Supabase'den al
        if "_ust_px" not in st.session_state:
            _kayitli_b = _mevcut.get("ust_px", 32)
            st.session_state["_ust_px"] = int(_kayitli_b)
            st.session_state["_alt_px"] = int(_mevcut.get("alt_px", 32))
            st.session_state["_yan_px"] = int(_mevcut.get("yan_px", 16))
        _ust_px  = st.session_state.get("_ust_px", 32)
        _alt_px  = st.session_state.get("_alt_px", 32)
        _yan_px  = st.session_state.get("_yan_px", 16)

        # Ekran bilgi kartları — JS ile dolduruluyor
        st.markdown(f"""
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;">
  <div style="background:var(--color-background-secondary);border-radius:8px;padding:10px;border:0.5px solid var(--color-border-tertiary);text-align:center;">
    <div style="font-size:10px;color:gray;margin-bottom:4px;">Ekran Genişliği</div>
    <div style="font-size:16px;font-weight:500;" id="sw_val">—</div>
    <div style="font-size:10px;color:gray;">px</div>
  </div>
  <div style="background:var(--color-background-secondary);border-radius:8px;padding:10px;border:0.5px solid var(--color-border-tertiary);text-align:center;">
    <div style="font-size:10px;color:gray;margin-bottom:4px;">Ekran Yüksekliği</div>
    <div style="font-size:16px;font-weight:500;" id="sh_val">—</div>
    <div style="font-size:10px;color:gray;">px</div>
  </div>
  <div style="background:var(--color-background-secondary);border-radius:8px;padding:10px;border:0.5px solid var(--color-border-tertiary);text-align:center;">
    <div style="font-size:10px;color:gray;margin-bottom:4px;">Üst Boşluk</div>
    <div style="font-size:16px;font-weight:500;" id="pt_val">{_ust_px}</div>
    <div style="font-size:10px;color:gray;">px</div>
  </div>
  <div style="background:var(--color-background-secondary);border-radius:8px;padding:10px;border:0.5px solid var(--color-border-tertiary);text-align:center;">
    <div style="font-size:10px;color:gray;margin-bottom:4px;">Alt Boşluk</div>
    <div style="font-size:16px;font-weight:500;" id="pb_val">{_alt_px}</div>
    <div style="font-size:10px;color:gray;">px</div>
  </div>
</div>

<!-- Görsel temsil -->
<div style="border:0.5px solid var(--color-border-tertiary);border-radius:8px;overflow:hidden;margin-bottom:12px;">
  <div style="background:#1f6feb;height:4px;"></div>
  <div id="top_vis" style="background:#e8f4ff;display:flex;align-items:center;justify-content:center;font-size:11px;color:#1f6feb;height:{_ust_px}px;min-height:16px;transition:height 0.2s;">
    ↕ üst: <b id="top_lbl" style="margin-left:4px;">{_ust_px}px</b>
  </div>
  <div style="background:white;padding:8px 14px;font-size:12px;border-top:0.5px solid #eee;border-bottom:0.5px solid #eee;">📊 İçerik alanı</div>
  <div id="bot_vis" style="background:#e8f4ff;display:flex;align-items:center;justify-content:center;font-size:11px;color:#1f6feb;height:{_alt_px}px;min-height:16px;transition:height 0.2s;">
    ↕ alt: <b id="bot_lbl" style="margin-left:4px;">{_alt_px}px</b>
  </div>
  <div style="background:#f0f2f6;height:4px;"></div>
</div>
<script>
document.getElementById('sw_val').textContent = window.screen.width;
document.getElementById('sh_val').textContent = window.screen.height;
function updateTop(v){{
  document.getElementById('top_lbl').textContent=v+'px';
  document.getElementById('top_vis').style.height=Math.max(16,parseInt(v))+'px';
  document.getElementById('pt_val').textContent=v;
}}
function updateBot(v){{
  document.getElementById('bot_lbl').textContent=v+'px';
  document.getElementById('bot_vis').style.height=Math.max(16,parseInt(v))+'px';
  document.getElementById('pb_val').textContent=v;
}}
</script>
""", unsafe_allow_html=True)

        # Sliderlar
        _yeni_ust = st.slider("⬆️ Üst Boşluk (px)", 0, 100, _ust_px, key="slider_ust")
        _yeni_alt = st.slider("⬇️ Alt Boşluk (px)", 0, 100, _alt_px, key="slider_alt")
        _yeni_yan = st.slider("↔️ Yan Boşluk (px)", 0, 100, _yan_px, key="slider_yan")

        _bs1, _bs2 = st.columns(2)
        if _bs1.button("💾 Boşlukları Kaydet", use_container_width=True, type="primary", key="bosluk_kaydet"):
            st.session_state["_ust_px"] = _yeni_ust
            st.session_state["_alt_px"] = _yeni_alt
            st.session_state["_yan_px"] = _yeni_yan
            st.session_state["_ekran_bosluk"] = f"{_yeni_ust}px"
            st.session_state["_ekran_altbosluk"] = f"{_yeni_alt}px"
            st.session_state["_ekran_yanbosluk"] = f"{_yeni_yan}px"
            _mevcut["ust_px"] = _yeni_ust
            _mevcut["alt_px"] = _yeni_alt
            _mevcut["yan_px"] = _yeni_yan
            _ekran_kaydet(_mevcut)
            st.success("✅ Kaydedildi!")
            st.rerun()
        if _bs2.button("↺ Sıfırla", use_container_width=True, key="bosluk_sifirla"):
            st.session_state["_ust_px"] = 32
            st.session_state["_alt_px"] = 32
            st.session_state["_yan_px"] = 16
            st.session_state["_ekran_bosluk"] = "32px"
            st.session_state["_ekran_altbosluk"] = "32px"
            st.session_state["_ekran_yanbosluk"] = "16px"
            st.rerun()

        st.divider()

        if st.button("↺ Boşlukları Varsayılana Sıfırla", use_container_width=True, key="ekran_sifirla"):
            _ekran_kaydet({"bosluk": "normal"})
            st.session_state.pop("_ekran_bosluk", None)
            st.rerun()

    if kul_tab5 and (st.session_state.get("rol") == "admin" or _surum_yetkisi):
        with kul_tab5:
            st.markdown("### 🚀 Sürüm Yönetimi")

            _sb_sv = get_sb_client()
            _simdi = pd.Timestamp.now().strftime("%d.%m.%Y %H:%M")

            # Supabase'den stable bilgilerini çek
            try:
                _res_stable = _sb_sv.table("sistem_ayarlari").select("deger").eq("anahtar","stable_surum").execute()
                _stable_v = _res_stable.data[0]["deger"] if _res_stable.data else GUNCEL_SURUM
            except:
                _stable_v = GUNCEL_SURUM

            # Son yayın tarihini çek
            try:
                _res_ytar = _sb_sv.table("kullanici_log").select("tarih,kullanici").eq("islem","SURUM_YAYINLANDI").order("tarih",desc=True).limit(1).execute()
                _son_yayin = _res_ytar.data[0]["tarih"][:16].replace("T"," ") if _res_ytar.data else "—"
                _son_yayin_kim = _res_ytar.data[0]["kullanici"] if _res_ytar.data else "—"
            except:
                _son_yayin = "—"
                _son_yayin_kim = "—"

            st.markdown("---")
            _col_a, _col_b = st.columns(2)

            # ── ADMİN KARTI ──────────────────────────────────────────────────
            with _col_a:
                st.markdown(f"""
                <div style='background:#0d1117;border:2px solid #1f6feb;border-radius:12px;padding:20px'>
                <div style='font-size:0.85rem;color:#888;margin-bottom:8px'>👑 ADMİN — Son Geliştirme Sürümü</div>
                <div style='font-size:2.2rem;font-weight:bold;color:#1f6feb;margin-bottom:4px'>{GUNCEL_SURUM}</div>
                <div style='font-size:0.8rem;color:#666'>📅 Şu an: {_simdi}</div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown("")
                # Yayınla butonu — her zaman görünür
                if _stable_v == GUNCEL_SURUM:
                    st.success(f"✅ Son sürüm ({GUNCEL_SURUM}) zaten yayında")
                else:
                    st.info(f"📢 Kullanıcılar **{_stable_v}** sürümünde. **{GUNCEL_SURUM}** hazır.")

                if st.button(f"🚀 {GUNCEL_SURUM} Sürümünü Yayınla",
                            type="primary", use_container_width=True, key="surum_yayinla"):
                    try:
                        _sb_sv.table("sistem_ayarlari").upsert(
                            {"anahtar":"stable_surum","deger":GUNCEL_SURUM},
                            on_conflict="anahtar").execute()
                        kullanici_log_kaydet("SURUM_YAYINLANDI","kullanici",
                            f"{_stable_v} → {GUNCEL_SURUM} yayınlandı")
                        st.success(f"✅ {GUNCEL_SURUM} yayınlandı!")
                        st.balloons()
                        st.rerun()
                    except Exception as _esv:
                        st.error(f"Hata: {_esv}")

                # Geri yükle — önceki sürüme dön
                st.markdown("")
                with st.expander("🔄 Önceki Sürüme Geri Al"):
                    try:
                        _res_gecmis = _sb_sv.table("kullanici_log").select("tarih,detay").eq("islem","SURUM_YAYINLANDI").order("tarih",desc=True).limit(10).execute()
                        if _res_gecmis.data and len(_res_gecmis.data) > 1:
                            _gecmis_opts = [r["detay"] for r in _res_gecmis.data[1:6]]
                            _geri_sec = st.selectbox("Sürüm seç:", _gecmis_opts, key="geri_yukle_sec")
                            if st.button("🔄 Geri Yükle", key="geri_yukle_btn", use_container_width=True):
                                # Sürüm adını parse et
                                import re as _re_sv
                                _match = _re_sv.search(r'→ (v[\d.]+)', _geri_sec)
                                if _match:
                                    _geri_v = _match.group(1)
                                    _sb_sv.table("sistem_ayarlari").upsert(
                                        {"anahtar":"stable_surum","deger":_geri_v},
                                        on_conflict="anahtar").execute()
                                    kullanici_log_kaydet("SURUM_GERİ_ALINDI","kullanici",f"→ {_geri_v}")
                                    st.success(f"✅ {_geri_v} geri yüklendi!")
                                    st.rerun()
                        else:
                            st.caption("Geri alınabilecek sürüm yok.")
                    except Exception as _eg:
                        st.caption(f"Hata: {_eg}")

            # ── KULLANICI KARTI ───────────────────────────────────────────────
            with _col_b:
                _renk = "#28a745" if _stable_v == GUNCEL_SURUM else "#ff9800"
                _durum_yazi = "✅ Güncel" if _stable_v == GUNCEL_SURUM else "⏳ Güncelleme Hazır"
                st.markdown(f"""
                <div style='background:#0d1117;border:2px solid {_renk};border-radius:12px;padding:20px'>
                <div style='font-size:0.85rem;color:#888;margin-bottom:8px'>👥 KULLANICILAR — Yayındaki Sürüm</div>
                <div style='font-size:2.2rem;font-weight:bold;color:{_renk};margin-bottom:4px'>{_stable_v}</div>
                <div style='font-size:0.8rem;color:#666'>📅 Son yayın: {_son_yayin}</div>
                <div style='font-size:0.8rem;color:#666'>👤 Yayınlayan: {_son_yayin_kim}</div>
                <div style='font-size:0.85rem;color:{_renk};margin-top:8px'>{_durum_yazi}</div>
                </div>
                """, unsafe_allow_html=True)

                # Yayınlama geçmişi
                st.markdown("")
                with st.expander("📋 Yayınlama Geçmişi"):
                    try:
                        _res_log_sv = _sb_sv.table("kullanici_log").select("*")                             .in_("islem",["SURUM_YAYINLANDI","SURUM_GERİ_ALINDI"])                             .order("tarih",desc=True).limit(15).execute()
                        if _res_log_sv.data:
                            _df_sv = pd.DataFrame(_res_log_sv.data)[["tarih","kullanici","islem","detay"]]
                            _df_sv["tarih"] = _df_sv["tarih"].astype(str).str[:16].str.replace("T"," ")
                            _df_sv.columns = ["Tarih","Kim","İşlem","Detay"]
                            st.dataframe(_df_sv, use_container_width=True, hide_index=True)
                        else:
                            st.caption("Henüz yayın geçmişi yok.")
                    except:
                        st.caption("Yüklenemedi.")

            st.divider()
            with st.expander("📖 Nasıl Çalışır?"):
                st.markdown(f"""
**Kullanıcılar hiç durmaz — iş kesilmez.**

| | Admin | Kullanıcılar |
|---|---|---|
| Sürüm | **{GUNCEL_SURUM}** | **{_stable_v}** |
| Durum | Son geliştirme | Kararlı yayın |

1. Kodu değiştir → push yap *(kullanıcılar etkilenmez)*
2. Admin olarak test et
3. **🚀 Yayınla** → kullanıcılar yeni sürüme geçer
4. Sorun çıkarsa **🔄 Geri Al** → önceki sürüme dön
                """)

    # ── 📐 KOLON AYARLARI ─────────────────────────────────────────────────────
    with kul_tab_kolon:
        st.markdown("### 📐 Cari Liste Kolon Ayarları")
        st.caption("Genişlik ayarlayın, gizlemek istediklerinizi kapatın → Kaydet")
        _KOL_VARS_UI = {
            "Seç":40,"tarih":90,"guncelleme_tarihi":100,
            "firma":100,"rakip_firma":100,"yetkili":100,"gsm":110,"sabit":100,"email":100,
            "adres":120,"il":80,"ilce":70,"durum":90,"temsilci":90,
            "islem_asamasi":90,"aciklama":120,"📅 Son Randevu":180,"📨 Notlar":60,"id":50,
            "asama1":100,"asama2":100,"asama3":100,"sonuc":100,"ara_islem":100,
            "beklenen_ciro":80,"gerceklesen_ciro":80,"✅ Analiz":80,"Varış İli":100,"Koli/Palet":120,
            "🧾 Teklif":70,"💬 Mesaj":70
        }
        for _il_kv in _IL_SUTUN_LISTESI:
            _KOL_VARS_UI[_il_kv] = 60
        _KG_UI_ETIKET = {
            "Seç":"Seç (işaret kutusu)","tarih":"İşlem Tarih","guncelleme_tarihi":"Güncelleme Tarihi",
            "firma":"Firma","rakip_firma":"Özel","yetkili":"Yetkili","gsm":"GSM","sabit":"S.Tel",
            "email":"Email","adres":"Adres","il":"İl","ilce":"İlçe",
            "durum":"Durum","temsilci":"Temsilci","islem_asamasi":"İlk Temas",
            "aciklama":"Açıklama","📅 Son Randevu":"Randevu","📨 Notlar":"Notlar","id":"ID",
            "asama1":"1. Aşama","asama2":"2. Aşama","asama3":"3. Aşama","sonuc":"Sonuç","ara_islem":"Ara İşlem",
            "beklenen_ciro":"Hedef ₺","gerceklesen_ciro":"Gerçek ₺","✅ Analiz":"Analiz","Varış İli":"Varış İli","Koli/Palet":"Koli/Palet",
            "🧾 Teklif":"Teklif","💬 Mesaj":"Mesaj"
        }
        for _il_ke in _IL_SUTUN_LISTESI:
            _KG_UI_ETIKET[_il_ke] = _il_ke
        # ÖNEMLİ: Ana listenin de kullandığı session_state["_kol_genislik"] tek doğruluk kaynağıdır.
        # Burada AYRI bir DB sorgusu yapmıyoruz — aksi halde iki farklı kaynak birbirini
        # ezip "ayarladığım gibi kalmıyor" sorununa yol açıyordu.
        # NOT (hata düzeltmesi): _sb_kg_ui ve _kguj burada, session_state zaten
        # doluysa (yani aşağıdaki "else" dalı çalışıyorsa) TANIMLANMIYORDU.
        # Bu yüzden "Gizle/Göster" butonuna basınca (sayfa ilk açılıştan sonra,
        # yani hep) sessizce NameError alıp hiçbir şey kaydetmiyordu — "çalışmıyor"
        # sorununun kök nedeni buydu. Şimdi her ikisi de KOŞULDAN BAĞIMSIZ,
        # her zaman tanımlanıyor.
        import json as _kguj
        _sb_kg_ui = get_sb_client()
        if "_kol_genislik" not in st.session_state or "_kol_gizli" not in st.session_state:
            try:
                _kg_ui_mevcut = _KOL_VARS_UI.copy()
                _gizli_ui = []
                if _sb_kg_ui:
                    _r_kgu = _sb_kg_ui.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kol_genislik").execute()
                    if _r_kgu.data:
                        _kg_ui_mevcut = _kguj.loads(_r_kgu.data[0]["deger"])
                    _r_gizli = _sb_kg_ui.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kol_gizli").execute()
                    if _r_gizli.data:
                        _gizli_ui = _kguj.loads(_r_gizli.data[0]["deger"])
            except:
                _kg_ui_mevcut = _KOL_VARS_UI.copy()
                _gizli_ui = []
            st.session_state["_kol_genislik"] = {**_KOL_VARS_UI.copy(), **_kg_ui_mevcut}
            st.session_state["_kol_gizli"] = _gizli_ui
        else:
            _kg_ui_mevcut = st.session_state["_kol_genislik"]
            _gizli_ui = st.session_state["_kol_gizli"]

        _yeni_kg_ui = {}
        _yeni_gizli_ui = []
        _ui_cols = st.columns(len(_KOL_VARS_UI))
        for _i, _k in enumerate(_KOL_VARS_UI.keys()):
            _etiket = _KG_UI_ETIKET.get(_k, _k)
            _gizli_mi = _k in _gizli_ui
            with _ui_cols[_i]:
                # Göz ikonu — tıklayınca gizle/göster
                _goz = "🙈" if _gizli_mi else "👁"
                if st.button(_goz, key=f"ui_giz_{_i}_{_k[:4]}", use_container_width=True,
                             help="Gizle/Göster"):
                    if _gizli_mi:
                        _gizli_ui = [x for x in _gizli_ui if x != _k]
                    else:
                        _gizli_ui.append(_k)
                    # Oturum içinde HEMEN uygula — DB yazımı başarısız olsa bile
                    # buton görsel olarak tepkisiz kalmasın.
                    st.session_state["_kol_gizli"] = _gizli_ui
                    st.session_state.pop("_kol_genislik_init", None)
                    # Kalıcı olması için DB'ye de yaz (upsert+on_conflict yerine
                    # sil+ekle — kullanici_tercih tablosunda bu kısıt olmadığı
                    # için upsert sessizce başarısız oluyordu, ayarlar hiç
                    # kalıcı olmuyordu).
                    try:
                        _sb_kg_ui.table("kullanici_tercih").delete().eq("kullanici","__liste_ui__").eq("anahtar","_kol_gizli").execute()
                        _sb_kg_ui.table("kullanici_tercih").insert({
                            "kullanici":"__liste_ui__","anahtar":"_kol_gizli",
                            "deger":_kguj.dumps(_gizli_ui, ensure_ascii=False)
                        }).execute()
                    except Exception as _kgize:
                        st.toast(f"⚠️ Gizle/Göster kaydedilemedi: {_kgize}", icon="⚠️")
                    st.rerun()
                # Slider — gizliyse devre dışı.
                _yeni_kg_ui[_k] = st.slider(
                    f"{'~~' if _gizli_mi else ''}{_etiket}",
                    min_value=5, max_value=400,
                    value=max(int(_kg_ui_mevcut.get(_k, _KOL_VARS_UI.get(_k,100))), 5),
                    step=5, key=f"ui_kg_{_k}",
                    disabled=_gizli_mi
                )
                if _gizli_mi:
                    _yeni_gizli_ui.append(_k)

        # Canlı önizleme: Kaydet'e basmadan slider'ı hareket ettirir ettirmez
        # ana listedeki tablo hemen bu genişlikleri kullanır (henüz DB'ye yazılmaz,
        # sayfayı/oturumu tamamen kapatıp açarsan Kaydet basılmayan değişiklik kaybolur)
        st.session_state["_kol_genislik"] = {**st.session_state.get("_kol_genislik", {}), **_yeni_kg_ui}
        st.session_state["_kol_genislik_init"] = True  # liste sayfası DB'den tekrar çekip ezmesin
        st.caption("👆 Değerler anında canlı önizlenir. Kalıcı olması (herkeste, her oturumda) için **Kaydet**'e basın.")

        if st.button("💾 Kaydet", type="primary", key="ui_kg_kaydet"):
            try:
                _sb_kg_s = get_sb_client()
                if _sb_kg_s:
                    import json as _kgsj2
                    # NOT: upsert(on_conflict=...) yerine sil+ekle — aynı bilinen
                    # kısıt sorununu (sessiz başarısızlık) önlemek için.
                    _sb_kg_s.table("kullanici_tercih").delete().eq("kullanici","__liste_ui__").eq("anahtar","_kol_genislik").execute()
                    _sb_kg_s.table("kullanici_tercih").insert({
                        "kullanici":"__liste_ui__","anahtar":"_kol_genislik",
                        "deger":_kgsj2.dumps(_yeni_kg_ui, ensure_ascii=False)
                    }).execute()
                    _sb_kg_s.table("kullanici_tercih").delete().eq("kullanici","__liste_ui__").eq("anahtar","_kol_gizli").execute()
                    _sb_kg_s.table("kullanici_tercih").insert({
                        "kullanici":"__liste_ui__","anahtar":"_kol_gizli",
                        "deger":_kgsj2.dumps(_gizli_ui, ensure_ascii=False)
                    }).execute()
                st.session_state["_kol_genislik"] = _yeni_kg_ui
                st.session_state["_kol_gizli"] = _gizli_ui
                st.session_state.pop("_kol_genislik_init", None)
                st.toast("✅ Kolon ayarları kaydedildi!", icon="✅")
                st.rerun()
            except Exception as _kgue:
                st.error(f"Hata: {_kgue}")

        # ── 📦 KARGO GİRİŞİ KOLON AYARLARI — ayrı, bağımsız bir ayar seti.
        # Ana Cari Liste'nin kolon genişlik mantığına dokunmaz, kendi anahtarında
        # ("_kargo_kol_genislik") saklanır. Genişlik aralığı: 5 – 50.
        st.divider()
        st.markdown("### 📦 Kargo Girişi Kolon Ayarları")
        _KARGO_KOL_ETIKET = {
            "Müşteri":"Müşteri","Tarih":"Tarih","Takip No":"Takip No","Gönderen":"Gönderen","Alıcı":"Alıcı",
            "Fatura Ödeyen":"Fatura Ödeyen","Gönderen İl":"Gönderen İl","Alıcı İl":"Alıcı İl","Adet":"Adet",
            "Tür":"Tür","Tutar":"Tutar","KDV":"KDV","Sigorta":"Sigorta","Toplam Fatura":"Toplam Fatura",
            "Ödeme Türü":"Ödeme Türü","Fatura Ödeme Şekli":"Fatura Ödeme Şekli","Tahsilat":"Tahsilat",
            "Dış Nakliye Firma":"Dış Nak. Firma",
            "Dış Nakliye Fatura":"Dış Nak. Fatura","Dış Nakliye Detay":"Dış Nak. Detay",
            "Dış Nakliye Tutar":"Dış Nak. Tutar","Müşteri Tutar":"Müşteri Tutar","Kar":"Kar",
            "Dış Nak. Ödeme":"Dış Nak. Ödeme",
        }
        _KARGO_KOL_VARSAYILAN = {k: 15 for k in _KARGO_KOL_ETIKET}
        try:
            _sb_kg2 = get_sb_client()
            _kargo_kg_mevcut = _KARGO_KOL_VARSAYILAN.copy()
            if _sb_kg2:
                _r_kargokg = _sb_kg2.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kargo_kol_genislik").execute()
                if _r_kargokg.data:
                    import json as _kkgj
                    _kargo_kg_mevcut = {**_KARGO_KOL_VARSAYILAN, **_kkgj.loads(_r_kargokg.data[0]["deger"])}
        except Exception:
            _kargo_kg_mevcut = _KARGO_KOL_VARSAYILAN.copy()

        _yeni_kargo_kg = {}
        _kargo_ui_cols = st.columns(6)
        for _ki, _kk_ad in enumerate(_KARGO_KOL_ETIKET.keys()):
            with _kargo_ui_cols[_ki % 6]:
                _yeni_kargo_kg[_kk_ad] = st.slider(
                    _KARGO_KOL_ETIKET[_kk_ad], min_value=5, max_value=50,
                    value=int(_kargo_kg_mevcut.get(_kk_ad, 15)), step=1, key=f"kargo_kg_{_ki}"
                )
        if st.button("💾 Kargo Kolon Ayarlarını Kaydet", type="primary", key="kargo_kg_kaydet_btn"):
            try:
                _sb_kg3 = get_sb_client()
                if _sb_kg3:
                    import json as _kkgj2
                    _sb_kg3.table("kullanici_tercih").delete().eq("kullanici","__liste_ui__").eq("anahtar","_kargo_kol_genislik").execute()
                    _sb_kg3.table("kullanici_tercih").insert({
                        "kullanici":"__liste_ui__","anahtar":"_kargo_kol_genislik",
                        "deger":_kkgj2.dumps(_yeni_kargo_kg, ensure_ascii=False)
                    }).execute()
                st.session_state["_kargo_kol_genislik"] = _yeni_kargo_kg
                st.toast("✅ Kargo kolon ayarları kaydedildi!", icon="✅")
                st.rerun()
            except Exception as _kkgue:
                st.error(f"Hata: {_kkgue}")

    # ── 🔄 TOPLU DEĞİŞTİR ────────────────────────────────────────────────────
    with kul_tab_toplu:
        st.markdown("### 🔄 Toplu Aşama / Durum Değiştir")
        st.caption("Seçili aşama veya durumu toplu olarak değiştirin")

        _sb_toplu = get_sb_client()
        _df_toplu = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")

        if not _df_toplu.empty:
            _tc1, _tc2, _tc3 = st.columns(3)

            # Filtrele
            _t_tem_opts = ["Tümü"] + sorted(_df_toplu["temsilci"].dropna().astype(str).unique().tolist()) if "temsilci" in _df_toplu.columns else ["Tümü"]
            _t_tem = _tc1.selectbox("Temsilci filtrele", _t_tem_opts, key="toplu_tem")
            if _t_tem != "Tümü":
                _df_toplu = _df_toplu[_df_toplu["temsilci"] == _t_tem]

            _t_asama_l = _tanimlar_yukle("asama")
            _t_durum_l  = _tanimlar_yukle("durum")

            _t_asama_opts = ["Tümü"] + _t_asama_l
            _t_asama_fil = _tc2.selectbox("Mevcut Aşama filtrele", _t_asama_opts, key="toplu_asama_fil")
            if _t_asama_fil != "Tümü":
                _df_toplu = _df_toplu[_df_toplu["islem_asamasi"] == _t_asama_fil]

            _t_durum_opts = ["Tümü"] + _t_durum_l
            _t_durum_fil = _tc3.selectbox("Mevcut Durum filtrele", _t_durum_opts, key="toplu_durum_fil")
            if _t_durum_fil != "Tümü":
                _df_toplu = _df_toplu[_df_toplu["durum"] == _t_durum_fil]

            st.caption(f"**{len(_df_toplu)} müşteri** seçili")

            st.divider()
            st.markdown("#### Ne Değiştirilsin?")
            _tc4, _tc5 = st.columns(2)

            _degistir_ne = _tc4.radio("Değiştirilecek alan:", ["Aşama", "Durum"], horizontal=True, key="toplu_ne")

            if _degistir_ne == "Aşama":
                _yeni_deger = _tc5.selectbox("Yeni Aşama:", ["— Boş (Temizle) —"] + _t_asama_l, key="toplu_yeni_asama")
                _alan = "islem_asamasi"
                _yeni_deger_db = "" if _yeni_deger == "— Boş (Temizle) —" else _yeni_deger
            else:
                _yeni_deger = _tc5.selectbox("Yeni Durum:", ["— Boş (Temizle) —"] + _t_durum_l, key="toplu_yeni_durum")
                _alan = "durum"
                _yeni_deger_db = "" if _yeni_deger == "— Boş (Temizle) —" else _yeni_deger

            _secim_gecerli = True  # Boş da geçerli seçim

            # Önizleme
            with st.expander(f"👁 Etkilenecek {len(_df_toplu)} müşteriyi gör", expanded=False):
                st.dataframe(_df_toplu[["id","firma","durum","islem_asamasi","temsilci"]].head(50),
                           use_container_width=True, hide_index=True)

            _onay = st.checkbox(f"✅ **{len(_df_toplu)} müşterinin {_degistir_ne} değerini '{_yeni_deger}' yapmayı onaylıyorum**", key="toplu_onay", disabled=not _secim_gecerli)

            if st.button("🔄 Toplu Değiştir", type="primary", key="toplu_kaydet", disabled=not (_onay and _secim_gecerli)):
                _basarili = 0
                _hatali = 0
                for _, _tr in _df_toplu.iterrows():
                    try:
                        if _sb_toplu:
                            _sb_toplu.table("cari_kartlar").update({_alan: _yeni_deger_db}).eq("id", int(_tr["id"])).execute()
                        _basarili += 1
                    except:
                        _hatali += 1
                try: db_read.clear()
                except: pass
                st.session_state.pop("toplu_onay", None)
                if _basarili:
                    st.success(f"✅ {_basarili} müşteri güncellendi!" + (f" ⚠️ {_hatali} hata" if _hatali else ""))
                    st.rerun()
                else:
                    st.error("Güncelleme başarısız!")
        else:
            st.info("Müşteri verisi bulunamadı.")
    with kul_tab_tanim:
        st.markdown("### ⚙️ Aşama & Durum Tanımları")
        _sb_tan = get_sb_client()

        def _tan_liste(tip):
            try:
                if _sb_tan:
                    r = _sb_tan.table("sistem_tanimlar").select("deger").eq("tip",tip).order("sira").execute()
                    # Deduplicate — sırayı koru
                    _goruldu = set()
                    _liste = []
                    for d in (r.data or []):
                        v = str(d["deger"] or "").strip()
                        if v and v not in _goruldu:
                            _liste.append(v)
                            _goruldu.add(v)
                    return _liste
            except: return []

        def _tan_ekle(tip, deger):
            try:
                if _sb_tan:
                    # Önce duplicate kontrolü
                    mevcut_kayit = _sb_tan.table("sistem_tanimlar").select("id").eq("tip",tip).eq("deger",deger.strip()).execute()
                    if mevcut_kayit.data:
                        return False  # Zaten var
                    mevcut_sira = _sb_tan.table("sistem_tanimlar").select("sira").eq("tip",tip).order("sira",desc=True).limit(1).execute()
                    sira = (mevcut_sira.data[0]["sira"] + 1) if mevcut_sira.data else 1
                    _sb_tan.table("sistem_tanimlar").insert({"tip":tip,"deger":deger.strip(),"sira":sira}).execute()
                    return True
            except: return False

        def _tan_sil(tip, deger):
            try:
                if _sb_tan:
                    # Aynı isimde TÜM kayıtları sil (duplicate temizler)
                    _sb_tan.table("sistem_tanimlar").delete().eq("tip",tip).eq("deger",deger).execute()
                    return True
            except: return False

        def _tan_temizle(tip):
            """Duplicate kayıtları temizle — her değerden sadece birini bırak"""
            try:
                if _sb_tan:
                    r = _sb_tan.table("sistem_tanimlar").select("id,deger,sira").eq("tip",tip).order("sira").execute()
                    if not r.data: return
                    _goruldu = set()
                    _silinecek = []
                    for d in r.data:
                        v = str(d["deger"] or "").strip()
                        if v in _goruldu:
                            _silinecek.append(d["id"])
                        else:
                            _goruldu.add(v)
                    for _sid in _silinecek:
                        _sb_tan.table("sistem_tanimlar").delete().eq("id",_sid).execute()
                    return len(_silinecek)
            except: return 0

        _ta1, _ta2 = st.columns(2)

        # AŞAMA
        with _ta1:
            st.markdown("**🔄 Aşama Yönetimi**")
            _asama_listesi = _tan_liste("asama")
            _asama_unique = list(dict.fromkeys(_asama_listesi))
            if len(_asama_unique) < len(_asama_listesi):
                st.warning(f"⚠️ {len(_asama_listesi) - len(_asama_unique)} tekrar var!")
                if st.button("🧹 Tekrarları Temizle", key="asama_temizle", type="primary"):
                    _silinen = _tan_temizle("asama")
                    st.success(f"✅ {_silinen} tekrar silindi!"); st.rerun()
            _ea1, _ea2 = st.columns([3,1])
            _yeni_asama = _ea1.text_input("", placeholder="Yeni aşama adı...", key="kul_yeni_asama", label_visibility="collapsed")
            if _ea2.button("➕ Ekle", key="kul_asama_ekle", use_container_width=True):
                if _yeni_asama.strip():
                    if _yeni_asama.strip() in _asama_unique:
                        st.warning("Bu aşama zaten var!")
                    elif _tan_ekle("asama", _yeni_asama.strip()):
                        st.success(f"✅ '{_yeni_asama}' eklendi!"); st.rerun()
            st.caption(f"{len(_asama_unique)} aşama")
            for _ai, _a in enumerate(_asama_unique):
                _ac1, _ac2 = st.columns([4,1])
                _ac1.markdown(f"🔸 **{_a}**")
                if _ac2.button("🗑", key=f"asil_{_ai}_{_a[:8]}", use_container_width=True, help="Sil"):
                    if _tan_sil("asama", _a):
                        st.success(f"'{_a}' silindi!"); st.rerun()

        # DURUM
        with _ta2:
            st.markdown("**📊 Durum Yönetimi**")
            _durum_listesi = _tan_liste("durum")
            # Duplicate temizle butonu
            _durum_unique = list(dict.fromkeys(_durum_listesi))
            if len(_durum_unique) < len(_durum_listesi):
                st.warning(f"⚠️ {len(_durum_listesi) - len(_durum_unique)} tekrar var!")
                if st.button("🧹 Tekrarları Temizle", key="durum_temizle", type="primary"):
                    _silinen = _tan_temizle("durum")
                    st.success(f"✅ {_silinen} tekrar silindi!"); st.rerun()
            _ed1, _ed2 = st.columns([3,1])
            _yeni_durum = _ed1.text_input("", placeholder="Yeni durum adı...", key="kul_yeni_durum", label_visibility="collapsed")
            if _ed2.button("➕ Ekle", key="kul_durum_ekle", use_container_width=True):
                if _yeni_durum.strip():
                    if _yeni_durum.strip() in _durum_listesi:
                        st.warning("Bu durum zaten var!")
                    elif _tan_ekle("durum", _yeni_durum.strip()):
                        st.success(f"✅ '{_yeni_durum}' eklendi!"); st.rerun()
            st.caption(f"{len(_durum_unique)} durum")
            for _di, _d in enumerate(_durum_listesi):
                _dc1, _dc2 = st.columns([4,1])
                _dc1.markdown(f"🔹 **{_d}**")
                if _dc2.button("🗑", key=f"dsil2_{_di}_{_d[:8]}", use_container_width=True, help="Sil"):
                    if _tan_sil("durum", _d):
                        st.success(f"'{_d}' silindi!"); st.rerun()

    with kul_tab_font:
        st.markdown("### 🔤 Sözleşme PDF Fontları")
        st.caption("Sözleşme PDF'lerinin Türkçe karakterleri (ş, ğ, ı, ç, ö, ü, İ) doğru basabilmesi için gereken "
                   "font dosyaları. Başka bir bilgisayarda kuruluma ihtiyaç olursa buradan indirilebilir; "
                   "`fonts/` klasörüne konup GitHub'a yüklenmesi gerekir.")
        import os as _fnt_os
        _fnt_dir = None
        for _aday in ["fonts", "./fonts", "/mount/src/mwcrmpro/fonts"]:
            if _fnt_os.path.isdir(_aday):
                _fnt_dir = _aday; break
        if not _fnt_dir:
            st.warning("⚠️ Sunucuda `fonts/` klasörü henüz yok — önce font dosyalarını repo'ya eklemeniz gerekiyor.")
        else:
            _fnt1, _fnt2 = st.columns(2)
            _fnt_normal = _fnt_os.path.join(_fnt_dir, "DejaVuSans.ttf")
            _fnt_bold   = _fnt_os.path.join(_fnt_dir, "DejaVuSans-Bold.ttf")
            if _fnt_os.path.isfile(_fnt_normal):
                with open(_fnt_normal, "rb") as _f:
                    _fnt1.download_button("⬇️ DejaVuSans.ttf indir", data=_f.read(),
                        file_name="DejaVuSans.ttf", mime="font/ttf", use_container_width=True, key="fnt_dl_normal")
            else:
                _fnt1.warning("DejaVuSans.ttf bulunamadı")
            if _fnt_os.path.isfile(_fnt_bold):
                with open(_fnt_bold, "rb") as _f:
                    _fnt2.download_button("⬇️ DejaVuSans-Bold.ttf indir", data=_f.read(),
                        file_name="DejaVuSans-Bold.ttf", mime="font/ttf", use_container_width=True, key="fnt_dl_bold")
            else:
                _fnt2.warning("DejaVuSans-Bold.ttf bulunamadı")

    with kul_tab_kural:
        st.markdown("### 🔧 Bağlantısız Teklif Onarımı")
        st.caption("Eskiden bazı teklifler hiçbir cari karta bağlanmadan (musteri_id=0) kaydediliyordu — bu yüzden Cari Liste'deki '🧾 Teklif' rozetinde hiç görünmüyorlardı. Bu araç, teklif üzerindeki müşteri adını cari kartlardaki firma adıyla eşleştirip düzeltir.")
        if st.button("🔍 Bağlantısız Teklifleri Tara", key="kural_teklif_tara"):
            _tor_sb = get_sb_client()
            if _tor_sb:
                with st.spinner("Taranıyor..."):
                    _tor_tek = _tor_sb.table("teklifler").select("id,musteri_id,musteri_adi").execute().data or []
                    _tor_cari = _tor_sb.table("cari_kartlar").select("id,firma").execute().data or []
                _tor_bagsiz = [t for t in _tor_tek if not t.get("musteri_id")]
                _tor_firma_map = {str(c.get("firma","")).strip().lower(): c.get("id") for c in _tor_cari if c.get("firma")}
                _tor_eslesen = []
                for _t in _tor_bagsiz:
                    _ad = str(_t.get("musteri_adi","")).strip().lower()
                    _bulunan_id = _tor_firma_map.get(_ad)
                    if _bulunan_id:
                        _tor_eslesen.append({"teklif_id": _t["id"], "musteri_adi": _t.get("musteri_adi",""), "bulunan_cari_id": _bulunan_id})
                st.session_state["_tor_eslesen"] = _tor_eslesen
                st.session_state["_tor_bagsiz_sayi"] = len(_tor_bagsiz)
        if "_tor_eslesen" in st.session_state:
            _tor_e = st.session_state["_tor_eslesen"]
            st.info(f"Toplam {st.session_state.get('_tor_bagsiz_sayi',0)} bağlantısız teklif bulundu, {len(_tor_e)} tanesi isimden otomatik eşleşti.")
            if _tor_e:
                st.dataframe(pd.DataFrame(_tor_e), use_container_width=True, hide_index=True)
                if st.button(f"✅ {len(_tor_e)} teklifi düzelt", type="primary", key="kural_teklif_onar"):
                    _tor_sb2 = get_sb_client()
                    _tor_ok = 0
                    for _e in _tor_e:
                        try:
                            _tor_sb2.table("teklifler").update({"musteri_id": _e["bulunan_cari_id"]}).eq("id", _e["teklif_id"]).execute()
                            _tor_ok += 1
                        except Exception:
                            pass
                    st.success(f"✅ {_tor_ok} teklif düzeltildi. Cari Liste'yi yenileyince rozetlerde görünecek.")
                    st.session_state.pop("_tor_eslesen", None)
                    st.session_state.pop("_tor_bagsiz_sayi", None)
        st.divider()
        st.markdown("### 📌 Proje Kuralları & Bilgileri")
        if not st.session_state.get("kurallar_pin_dogru", False):
            st.caption("Bu alanda hassas bilgiler var (Supabase anahtarı, Paraşüt secret vb.) — devam etmek için PIN girin.")
            _kp1, _kp2 = st.columns([2,1])
            _kural_pin_giris = _kp1.text_input("PIN:", type="password", key="kurallar_pin_input", label_visibility="collapsed", placeholder="PIN girin")
            if _kp2.button("🔓 Aç", key="kurallar_pin_btn", use_container_width=True):
                if _kural_pin_giris == KURALLAR_PIN:
                    st.session_state["kurallar_pin_dogru"] = True
                    st.rerun()
                else:
                    st.error("❌ PIN hatalı!")
        else:
            st.caption("Bu kurallar Claude ile yeni bir sohbet başlatıldığında main.py'nin en üstünden otomatik okunur — kodla birebir aynıdır. Sadece admin görür.")
            st.markdown(PROJE_KURALLARI)
            if st.button("🔒 Kilitle", key="kurallar_kilitle_btn"):
                st.session_state["kurallar_pin_dogru"] = False
                st.rerun()

elif aktif == "rapor":
    sayfa_log("rapor")
    import io as _rio2

    # Veri yükle
    df_rapor = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi=\'0\' OR silindi IS NULL)")
    df_rapor = _atama_filtresi_uygula(df_rapor)
    df_rand_r = db_read("randevular", extra_sql="ORDER BY randevu_tarihi DESC")
    df_tek_r  = _teklifler_tarih_normalize(_teklifler_oku())
    # Randevu ve teklifleri de filtrele
    if not df_rand_r.empty and "musteri_adi" in df_rand_r.columns:
        _rp_atanan = _get_atanmis_firmalar()
        if _rp_atanan is not None and "firmalar" in _rp_atanan:
            df_rand_r = df_rand_r[df_rand_r["musteri_adi"].apply(lambda x: str(x or "").strip().upper() in _rp_atanan["firmalar"])]

    if not df_rapor.empty:
        for col in ["beklenen_ciro","gerceklesen_ciro"]:
            if col not in df_rapor.columns: df_rapor[col] = 0
            df_rapor[col] = pd.to_numeric(df_rapor[col], errors="coerce").fillna(0)
        for col in ["durum","islem_asamasi","temsilci","il","firma","yetkili","id","ilce","gsm","email"]:
            if col not in df_rapor.columns: df_rapor[col] = ""
        df_rapor["fark"]  = df_rapor["gerceklesen_ciro"] - df_rapor["beklenen_ciro"]
        df_rapor["yuzde"] = df_rapor.apply(lambda r: (r["gerceklesen_ciro"]/r["beklenen_ciro"]*100) if r["beklenen_ciro"]>0 else 0, axis=1)
        toplam = len(df_rapor)
        toplam_beklenen = df_rapor["beklenen_ciro"].sum()
        toplam_gercek   = df_rapor["gerceklesen_ciro"].sum()
    else:
        toplam = 0; toplam_beklenen = 0; toplam_gercek = 0

    if not df_rand_r.empty and "adet" in df_rand_r.columns:
        df_rand_r["adet"] = pd.to_numeric(df_rand_r["adet"], errors="coerce").fillna(0)

    # ── ÖZET SATIRI ───────────────────────────────────────────────────────────
    _aktif_say  = len(df_rapor[df_rapor["durum"]=="Aktif"]) if not df_rapor.empty else 0
    _hedef_say  = len(df_rapor[df_rapor["durum"]=="Hedef"]) if not df_rapor.empty else 0
    _rand_say   = len(df_rand_r) if not df_rand_r.empty else 0
    _bitti_say  = len(df_rand_r[df_rand_r["sonuc"]=="Bitti"]) if not df_rand_r.empty and "sonuc" in df_rand_r.columns else 0
    _devam_say  = len(df_rand_r[df_rand_r["sonuc"]=="Devam Ediyor"]) if not df_rand_r.empty and "sonuc" in df_rand_r.columns else 0
    _gidilmedi  = len(df_rand_r[df_rand_r["sonuc"]=="Gidilmedi"]) if not df_rand_r.empty and "sonuc" in df_rand_r.columns else 0
    st.markdown(
        f"🏢 **Cari:** {toplam} kayıt &nbsp;·&nbsp; Aktif: **{_aktif_say}** &nbsp;·&nbsp; Hedef: **{_hedef_say}** &nbsp;·&nbsp; "
        f"Beklenen: **{fmt_para(toplam_beklenen)}** &nbsp;·&nbsp; Gerçekleşen: **{fmt_para(toplam_gercek)}** "
        f"&nbsp;&nbsp;|&nbsp;&nbsp; "
        f"📅 **Randevu:** {_rand_say} &nbsp;·&nbsp; ✅ Bitti: **{_bitti_say}** &nbsp;·&nbsp; "
        f"🔄 Devam: **{_devam_say}** &nbsp;·&nbsp; ❌ Gidilmedi: **{_gidilmedi}**"
    )
    st.divider()

    # ── RAPOR SIRALAMA SİSTEMİ ────────────────────────────────────────────────
    _RAPOR_LISTESI = [
        "tarih_gorev", "bolge", "asama_durum",
        "il_bazli", "musteri_ciro", "wa_email"
    ]
    _RAPOR_ETIKET = {
        "tarih_gorev": "📅 Tarih & Görev Raporu",
        "bolge":       "🗺️ Bölge Raporu",
        "asama_durum": "🔄 Aşama & Durum Bazlı Detay Raporu",
        "il_bazli":    "🗺️ İl Bazlı Rapor (Top 15)",
        "musteri_ciro":"💰 Müşteri Bazlı Ciro Detayı (Top 20)",
        "wa_email":    "📱 WhatsApp & Email Gönderim Raporu",
    }

    def _rapor_sira_yukle():
        try:
            _sb = get_sb_client()
            if _sb:
                _r = _sb.table("kullanici_tercih").select("deger") \
                    .eq("kullanici", st.session_state.get("kullanici","")) \
                    .eq("anahtar","rapor_sirasi").execute()
                if _r.data:
                    import json as _rj
                    _kayitli = _rj.loads(_r.data[0]["deger"])
                    # Yeni raporlar varsa sona ekle
                    for _k in _RAPOR_LISTESI:
                        if _k not in _kayitli: _kayitli.append(_k)
                    return [k for k in _kayitli if k in _RAPOR_LISTESI]
        except: pass
        return _RAPOR_LISTESI.copy()

    def _rapor_sira_kaydet(sira):
        try:
            import json as _rj
            _sb = get_sb_client()
            if _sb:
                _sb.table("kullanici_tercih").upsert({
                    "kullanici": st.session_state.get("kullanici",""),
                    "anahtar": "rapor_sirasi",
                    "deger": _rj.dumps(sira)
                }, on_conflict="kullanici,anahtar").execute()
        except: pass

    _rapor_sira = _rapor_sira_yukle()

    # ── RAPOR SIRALAMA ────────────────────────────────────────────────────────
    _RAPOR_LISTESI = ["tarih_gorev","bolge","asama_durum","il_bazli","musteri_ciro","wa_email"]
    _RAPOR_ETIKET = {
        "tarih_gorev": "📅 Tarih & Görev Raporu",
        "bolge":       "🗺️ Bölge Raporu",
        "asama_durum": "🔄 Aşama & Durum Bazlı Detay Raporu",
        "il_bazli":    "🗺️ İl Bazlı Rapor (Top 15)",
        "musteri_ciro":"💰 Müşteri Bazlı Ciro Detayı (Top 20)",
        "wa_email":    "📱 WhatsApp & Email Gönderim Raporu",
    }
    def _rapor_sira_yukle():
        try:
            import json as _rj
            _sb = get_sb_client()
            if _sb:
                _r = _sb.table("kullanici_tercih").select("deger").eq("kullanici",st.session_state.get("kullanici","")).eq("anahtar","rapor_sirasi").execute()
                if _r.data:
                    _k = _rj.loads(_r.data[0]["deger"])
                    for _x in _RAPOR_LISTESI:
                        if _x not in _k: _k.append(_x)
                    return [x for x in _k if x in _RAPOR_LISTESI]
        except: pass
        return _RAPOR_LISTESI.copy()
    def _rapor_sira_kaydet(sira):
        try:
            import json as _rj
            _sb = get_sb_client()
            if _sb:
                _sb.table("kullanici_tercih").upsert({"kullanici":st.session_state.get("kullanici",""),"anahtar":"rapor_sirasi","deger":_rj.dumps(sira)},on_conflict="kullanici,anahtar").execute()
        except: pass
    _rapor_sira = _rapor_sira_yukle()
    with st.expander("⚙️ Rapor Sırası"):
        for _ri, _rk in enumerate(_rapor_sira):
            _rc1,_rc2,_rc3 = st.columns([5,1,1])
            _rc1.caption(_RAPOR_ETIKET.get(_rk,_rk))
            if _ri > 0 and _rc2.button("▲", key=f"raporsira_up_{_rk}"):
                _rapor_sira[_ri],_rapor_sira[_ri-1] = _rapor_sira[_ri-1],_rapor_sira[_ri]
                _rapor_sira_kaydet(_rapor_sira); st.rerun()
            if _ri < len(_rapor_sira)-1 and _rc3.button("▼", key=f"raporsira_dn_{_rk}"):
                _rapor_sira[_ri],_rapor_sira[_ri+1] = _rapor_sira[_ri+1],_rapor_sira[_ri]
                _rapor_sira_kaydet(_rapor_sira); st.rerun()

    for _rk in _rapor_sira:
        if _rk == "tarih_gorev":
            with st.expander("📅 Tarih & Görev Raporu"):
                if df_rand_r.empty:
                    st.info("Randevu yok.")
                else:
                    _rg = df_rand_r.copy()
                    if not df_rapor.empty:
                        _rg = _rg.merge(df_rapor[["firma","beklenen_ciro","gerceklesen_ciro"]], left_on="musteri_adi", right_on="firma", how="left")
                        _rg["beklenen_ciro"] = pd.to_numeric(_rg["beklenen_ciro"], errors="coerce").fillna(0)
                        _rg["gerceklesen_ciro"] = pd.to_numeric(_rg["gerceklesen_ciro"], errors="coerce").fillna(0)
                    else:
                        _rg["beklenen_ciro"] = 0; _rg["gerceklesen_ciro"] = 0
                    _gc = ["randevu_tarihi","gorev"] if "gorev" in _rg.columns else ["randevu_tarihi"]
                    _tg = _rg.groupby(_gc).agg(Randevu=("id","count"),Musteri=("musteri_adi","nunique"),Bitti=("sonuc",lambda x:(x=="Bitti").sum()),Beklenen=("beklenen_ciro","sum"),Gerceklesen=("gerceklesen_ciro","sum")).reset_index().sort_values("randevu_tarihi",ascending=False)
                    _tg["Fark"] = _tg["Gerceklesen"] - _tg["Beklenen"]
                    for _col in ["Beklenen","Gerceklesen","Fark"]: _tg[_col] = _tg[_col].apply(fmt_para)
                    _tg.rename(columns={"randevu_tarihi":"Tarih","gorev":"Görev","Musteri":"Müşteri","Beklenen":"Beklenen Ciro","Gerceklesen":"Gerçekleşen"},inplace=True)
                    st.dataframe(_tg, use_container_width=True, hide_index=True)
                    _buf=_rio2.BytesIO(); _tg.to_excel(_buf,index=False); _buf.seek(0)
                    st.download_button("📥 İndir",data=_buf,file_name="tarih_gorev.xlsx",use_container_width=True)

        elif _rk == "bolge":
            with st.expander("🗺️ Bölge Raporu"):
                if df_rand_r.empty or "bolge" not in df_rand_r.columns:
                    st.info("Randevu yok.")
                else:
                    _rc = df_rand_r[["bolge","musteri_adi"]].drop_duplicates()
                    if not df_rapor.empty:
                        _rc = _rc.merge(df_rapor[["firma","beklenen_ciro","gerceklesen_ciro"]],left_on="musteri_adi",right_on="firma",how="left")
                        _rc["beklenen_ciro"] = pd.to_numeric(_rc["beklenen_ciro"],errors="coerce").fillna(0)
                        _rc["gerceklesen_ciro"] = pd.to_numeric(_rc["gerceklesen_ciro"],errors="coerce").fillna(0)
                        b_oz = _rc.groupby("bolge").agg(Musteri=("musteri_adi","nunique"),Beklenen=("beklenen_ciro","sum"),Gerceklesen=("gerceklesen_ciro","sum")).reset_index().sort_values("Beklenen",ascending=False)
                        b_oz["Beklenen"] = b_oz["Beklenen"].apply(fmt_para)
                        b_oz["Gerceklesen"] = b_oz["Gerceklesen"].apply(fmt_para)
                        b_oz.columns = ["Bölge","Müşteri","Beklenen Ciro","Gerçekleşen"]
                    else:
                        b_oz = df_rand_r.groupby("bolge").agg(Musteri=("musteri_adi","nunique")).reset_index()
                        b_oz.columns = ["Bölge","Müşteri"]
                    st.dataframe(b_oz, use_container_width=True, hide_index=True)
                    _buf=_rio2.BytesIO(); b_oz.to_excel(_buf,index=False); _buf.seek(0)
                    st.download_button("📥 İndir",data=_buf,file_name="bolge.xlsx",use_container_width=True)

        elif _rk == "asama_durum":
            with st.expander("🔄 Aşama & Durum Bazlı Detay Raporu", expanded=False):
                if df_rapor.empty:
                    st.info("Veri yok.")
                else:
                    _rb1,_rb2,_rb3 = st.columns(3)
                    _trbas = _rb1.date_input("Başlangıç:", key="rp_asama_bas", value=None)
                    _trbit = _rb2.date_input("Bitiş:", key="rp_asama_bit", value=None)
                    _tdur_opts = _tanimlar_yukle("durum")
                    _fil_dur = _rb3.selectbox("Durum:", ["Tümü"]+_tdur_opts, key="rp_asama_durum")
                    _drf = df_rapor.copy()
                    if _trbas or _trbit:
                        _drf["_dt"] = pd.to_datetime(_drf["tarih"],errors="coerce").dt.date
                        if _trbas: _drf = _drf[_drf["_dt"] >= _trbas]
                        if _trbit: _drf = _drf[_drf["_dt"] <= _trbit]
                    if _fil_dur != "Tümü": _drf = _drf[_drf["durum"]==_fil_dur]
                    _tum_as = sorted(_drf["islem_asamasi"].dropna().unique().tolist())
                    _s1,_s2 = st.columns(2)
                    with _s1:
                        st.caption(f"**Aşama Özeti** — {len(_drf)} kayıt")
                        _aoz = _drf.groupby("islem_asamasi").agg(Firma=("firma","count"),Beklenen=("beklenen_ciro","sum"),Gerceklesen=("gerceklesen_ciro","sum")).reset_index().sort_values("Firma",ascending=False)
                        _aoz["Başarı%"] = _aoz.apply(lambda r: f"{r['Gerceklesen']/r['Beklenen']*100:.0f}%" if r["Beklenen"]>0 else "—",axis=1)
                        _aoz["Beklenen"] = _aoz["Beklenen"].apply(fmt_para)
                        _aoz["Gerceklesen"] = _aoz["Gerceklesen"].apply(fmt_para)
                        _aoz.columns = ["Aşama","Firma","Beklenen","Gerçekleşen","Başarı%"]
                        st.dataframe(_aoz, use_container_width=True, hide_index=True)
                    with _s2:
                        st.caption("**Durum Özeti**")
                        _doz = _drf.groupby("durum").agg(Firma=("firma","count"),Beklenen=("beklenen_ciro","sum"),Gerceklesen=("gerceklesen_ciro","sum")).reset_index().sort_values("Firma",ascending=False)
                        _doz["Beklenen"] = _doz["Beklenen"].apply(fmt_para)
                        _doz["Gerceklesen"] = _doz["Gerceklesen"].apply(fmt_para)
                        _doz.columns = ["Durum","Firma","Beklenen","Gerçekleşen"]
                        st.dataframe(_doz, use_container_width=True, hide_index=True)
                    st.divider()
                    if _tum_as:
                        _atabs = st.tabs([f"🔹 {a}" for a in _tum_as])
                        for _ti, _an in enumerate(_tum_as):
                            with _atabs[_ti]:
                                _dar = _drf[_drf["islem_asamasi"]==_an]
                                _do = " · ".join([f"{r['durum']}: {r['Adet']}" for _,r in _dar.groupby("durum").size().reset_index(name="Adet").iterrows()]) if "durum" in _dar.columns else ""
                                st.caption(f"**{len(_dar)} firma** · {_do} · Beklenen: {fmt_para(_dar['beklenen_ciro'].sum())} · Gerçekleşen: {fmt_para(_dar['gerceklesen_ciro'].sum())}")
                                _gc2 = [c for c in ["id","tarih","firma","yetkili","gsm","il","durum","temsilci","beklenen_ciro","gerceklesen_ciro"] if c in _dar.columns]
                                _ds = _dar[_gc2].copy()
                                if "beklenen_ciro" in _ds.columns: _ds["beklenen_ciro"] = _ds["beklenen_ciro"].apply(fmt_para)
                                if "gerceklesen_ciro" in _ds.columns: _ds["gerceklesen_ciro"] = _ds["gerceklesen_ciro"].apply(fmt_para)
                                if "tarih" in _ds.columns: _ds["tarih"] = _ds["tarih"].astype(str).str[:10]
                                st.dataframe(_ds, use_container_width=True, hide_index=True)
                                _buf=_rio2.BytesIO(); _dar.to_excel(_buf,index=False); _buf.seek(0)
                                st.download_button("📥 Excel",data=_buf,file_name=f"asama_{_an}.xlsx",use_container_width=True,key=f"dl_asama_{_an}")

        elif _rk == "il_bazli":
            with st.expander("🗺️ İl Bazlı Rapor (Top 15)"):
                if df_rapor.empty: st.info("Veri yok.")
                else:
                    _il = df_rapor.groupby("il").agg(Musteri=("firma","count"),Beklenen=("beklenen_ciro","sum"),Gerceklesen=("gerceklesen_ciro","sum")).reset_index().sort_values("Musteri",ascending=False).head(15)
                    _il["Beklenen"] = _il["Beklenen"].apply(fmt_para)
                    _il["Gerceklesen"] = _il["Gerceklesen"].apply(fmt_para)
                    st.dataframe(_il, use_container_width=True, hide_index=True)

        elif _rk == "musteri_ciro":
            with st.expander("💰 Müşteri Bazlı Ciro Detayı (Top 20)"):
                if df_rapor.empty: st.info("Veri yok.")
                else:
                    _t20 = df_rapor.sort_values("beklenen_ciro",ascending=False).head(20)
                    _sc = [c for c in ["firma","temsilci","il","durum","islem_asamasi","beklenen_ciro","gerceklesen_ciro","yuzde"] if c in _t20.columns]
                    _dt = _t20[_sc].copy()
                    if "beklenen_ciro" in _dt.columns: _dt["beklenen_ciro"] = _dt["beklenen_ciro"].apply(fmt_para)
                    if "gerceklesen_ciro" in _dt.columns: _dt["gerceklesen_ciro"] = _dt["gerceklesen_ciro"].apply(fmt_para)
                    if "yuzde" in _dt.columns: _dt["yuzde"] = _dt["yuzde"].apply(lambda x: f"{x:.1f}%")
                    st.dataframe(_dt, use_container_width=True, hide_index=True)
                    _buf=_rio2.BytesIO(); _dt.to_excel(_buf,index=False); _buf.seek(0)
                    st.download_button("📥 İndir",data=_buf,file_name="ciro_top20.xlsx",use_container_width=True)

        elif _rk == "wa_email":
            with st.expander("📱 WhatsApp & Email Gönderim Raporu"):
                try:
                    _dik = db_read("islem_kaydi", order_col="tarih", limit=1000)
                    if not _dik.empty and "islem_turu" in _dik.columns:
                        _dik = _dik[_dik["islem_turu"].str.contains("WhatsApp|Email|WA|Teklif|Randevu|Uyarı",case=False,na=False)]
                    if not _dik.empty:
                        _dik = _dik.rename(columns={"musteri_adi":"Müşteri","islem_turu":"Kanal","gonderim_bilgisi":"Numara/Email","olusturan":"Gönderen","icerik":"Detay","tarih":"Tarih"})
                        _dik["Kaynak"] = "Sistem"
                        _dik = _dik[["Tarih","Müşteri","Kanal","Detay","Numara/Email","Gönderen","Kaynak"]]
                    _dkml = db_read("kisiler_mesaj_log", order_col="tarih", limit=1000)
                    if not _dkml.empty:
                        _dkml = _dkml.rename(columns={"kisi_adi":"Müşteri","sablon_adi":"Kanal","mesaj":"Detay","telefon":"Numara/Email","gonderen":"Gönderen","tarih":"Tarih"})
                        _dkml["Kanal"] = "📱 WA Kişi — " + _dkml["Kanal"].astype(str)
                        _dkml["Kaynak"] = "Kişiler"
                        _dkml = _dkml[["Tarih","Müşteri","Kanal","Detay","Numara/Email","Gönderen","Kaynak"]]
                    _pp = [d for d in [_dik, _dkml] if not d.empty]
                    if not _pp:
                        st.info("Henüz WA/Email gönderim kaydı yok.")
                    else:
                        _dtum = pd.concat(_pp, ignore_index=True)
                        _dtum["Tarih"] = pd.to_datetime(_dtum["Tarih"], errors="coerce")
                        _dtum = _dtum.sort_values("Tarih", ascending=False)
                        _dtum["Tarih"] = _dtum["Tarih"].astype(str).str[:16]
                        _wt = len(_dtum[_dtum["Kanal"].str.contains("WhatsApp Teklif|WA Teklif",na=False)])
                        _we = len(_dtum[_dtum["Kanal"].str.contains("Email",na=False)])
                        _wr = len(_dtum[_dtum["Kanal"].str.contains("Randevu|Uyarı",na=False)])
                        _wk = len(_dtum[_dtum["Kanal"].str.contains("WA Kişi",na=False)])
                        st.markdown(f"📊 Toplam: **{len(_dtum)}** &nbsp;·&nbsp; 📱 WA Teklif: **{_wt}** &nbsp;·&nbsp; ✉️ Email: **{_we}** &nbsp;·&nbsp; 📅 Randevu WA: **{_wr}** &nbsp;·&nbsp; 👤 Kişi WA: **{_wk}**")
                        _wf1,_wf2,_wf3 = st.columns(3)
                        _fk = _wf1.selectbox("Kanal:",["Tümü"]+sorted(_dtum["Kanal"].dropna().unique().tolist()),key="wa_fil_kanal")
                        _fg = _wf2.selectbox("Gönderen:",["Tümü"]+sorted(_dtum["Gönderen"].dropna().unique().tolist()),key="wa_fil_gon")
                        _fa = _wf3.text_input("🔍 Müşteri ara:",key="wa_fil_ara")
                        _dg = _dtum.copy()
                        if _fk != "Tümü": _dg = _dg[_dg["Kanal"]==_fk]
                        if _fg != "Tümü": _dg = _dg[_dg["Gönderen"]==_fg]
                        if _fa: _dg = _dg[_dg["Müşteri"].str.contains(_fa,case=False,na=False)]
                        st.caption(f"**{len(_dg)} kayıt**")
                        _dg2 = _dg.copy(); _dg2["Detay"] = _dg2["Detay"].astype(str).str[:80]
                        st.dataframe(_dg2[["Tarih","Müşteri","Kanal","Numara/Email","Gönderen","Detay"]], use_container_width=True, hide_index=True)
                        _buf=_rio2.BytesIO(); _dg.to_excel(_buf,index=False); _buf.seek(0)
                        st.download_button("📥 Excel İndir",data=_buf,file_name=f"wa_email_{datetime.now().strftime('%Y%m%d')}.xlsx",use_container_width=True)
                except Exception as _e:
                    st.error(f"Hata: {_e}")




elif aktif == "ozel_teklif":
    sayfa_log("ozel_teklif")
    import json as _ozj, re as _ozre

    st.markdown("## ⭐ Özel Teklif")
    if st.session_state.pop("_oz2_kopyalandi", False):
        st.info("📋 Teklif kopyalandı — fiyatlar yüklendi. Müşteriyi seçip kaydedin.")
    if st.button("🔄 Formu Sıfırla", key="oz2_sifirla"):
        for _k in ["oz2_grp","oz2_duz_id","oz2_duz_musteri","oz2_hedef","oz2_son_sec","oz2_musteri","oz2_wa_mesaj","oz2_fil"]:
            st.session_state.pop(_k, None)
        st.rerun()

    _OZ_URUN_VARSAYILAN = ["Koli","Sandık","Top","Çuval","Kasa","Palet","Diğer"]

    def _oz_urun_listesi():
        _liste = _OZ_URUN_VARSAYILAN.copy()
        try:
            _sb = get_sb_client()
            if _sb:
                import json as _oj
                _r = _sb.table("kullanici_tercih").select("deger").eq("kullanici","__oz_urun__").eq("anahtar","ekstra_urunler").execute()
                if _r.data:
                    _ekstra = _oj.loads(_r.data[0]["deger"])
                    for _d in _ekstra:
                        if _d not in _liste: _liste.append(_d)
        except: pass
        return _liste

    def _oz_urun_kaydet(liste):
        try:
            import json as _oj
            _sb = get_sb_client()
            if _sb:
                _ekstra = [x for x in liste if x not in _OZ_URUN_VARSAYILAN]
                _sb.table("kullanici_tercih").upsert({
                    "kullanici":"__oz_urun__","anahtar":"ekstra_urunler",
                    "deger":_oj.dumps(_ekstra,ensure_ascii=False)
                },on_conflict="kullanici,anahtar").execute()
                return True
        except: pass
        return False

    _OZ_URUN = _oz_urun_listesi()

    _OZ_ILLER = ["İstanbul","Ankara","İzmir","Bursa","Antalya","Adana","Konya",
        "Gaziantep","Mersin","Kayseri","Eskişehir","Diyarbakır","Samsun","Trabzon",
        "Erzurum","Şanlıurfa","Manisa","Balıkesir","Tekirdağ","Kocaeli","Sakarya",
        "Denizli","Muğla","Hatay","Malatya","Kahramanmaraş","Van","Elazığ","Aydın",
        "Edirne","Çanakkale","Isparta","Bolu","Düzce","Yalova","Kırklareli",
        "Karaman","Burdur","Rize","Giresun","Artvin","Mardin","Batman","Zonguldak",
        "Sinop","Kastamonu","Karabük","Ordu","Sivas","Erzincan","Tokat","Çorum"]

    # ── MÜŞTERİ + BİLGİLER — TEK SATIR ─────────────────────────────────────
    _oz_dfm = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")

    # Analiz sayfasından gelen otomatik seçim
    _oz_onsel = st.session_state.pop("teklif_musteri_onsel", None)
    if _oz_onsel:
        _oz_onsel_rows = _oz_dfm[_oz_dfm["firma"] == _oz_onsel]
        if not _oz_onsel_rows.empty:
            _oz_onsel_row = _oz_onsel_rows.iloc[0]
            st.session_state["oz2_musteri"] = f"[{int(_oz_onsel_row['id'])}] {_oz_onsel_row['firma']} ({_oz_onsel_row['durum']})"

    if st.session_state.get("oz2_mus_reset"):
        st.session_state.pop("oz2_mus_reset", None)
        st.session_state.pop("oz2_musteri", None)
        st.session_state.pop("oz2_hedef", None)
        st.session_state.pop("oz2_son_sec", None)

    _ozr = st.columns([1, 2.5, 0.3, 1.5, 1, 1, 1, 1])
    _oz_fil = _ozr[0].selectbox("", ["Tümü"], key="oz2_fil", label_visibility="collapsed")
    _oz_mf  = _oz_dfm if _oz_fil=="Tümü" else _oz_dfm[_oz_dfm["durum"]==_oz_fil]
    _oz_opts = ["-- Müşteri Seçin --"] + [f"[{int(r['id'])}] {r['firma']} ({r['durum']})" for _,r in _oz_mf.iterrows()]
    _oz_sec  = _ozr[1].selectbox("", _oz_opts, key="oz2_musteri", label_visibility="collapsed")
    if _oz_sec != "-- Müşteri Seçin --":
        if _ozr[2].button("❌", key="oz2_mus_temizle", use_container_width=True, help="Temizle"):
            st.session_state["oz2_mus_reset"] = True
            st.rerun()

    _oz_mus = None; _oz_gsm=""; _oz_eml=""; _oz_sec_id = None
    if _oz_sec != "-- Müşteri Seçin --" and "[" in _oz_sec:
        try:
            _mid = int(_oz_sec.split("]")[0].replace("[","").strip())
            _oz_sec_id = _mid
            _mr  = _oz_dfm[_oz_dfm["id"]==_mid]
            if not _mr.empty:
                _oz_mus = _mr.iloc[0]
                _oz_gsm = _no_temizle(_oz_mus.get("gsm","") or "")
                _oz_eml = str(_oz_mus.get("email","") or "")
        except: pass

    _oz_gsm = ""; _oz_eml = ""; _oz_sabit = ""
    if _oz_mus is not None:
        _oz_gsm   = _no_temizle(_oz_mus.get("gsm","") or "")
        _oz_eml   = str(_oz_mus.get("email","") or "")
        _oz_sabit = _no_temizle(_oz_mus.get("sabit","") or "")
        if not _oz_gsm:
            _oz_gsm = _oz_sabit  # GSM boşsa sabit telefonu göster

    _oz_fdef = str(_oz_mus["firma"]) if _oz_mus is not None else ""
    if "oz2_duz_musteri" in st.session_state:
        _oz_fdef = st.session_state.pop("oz2_duz_musteri")
        st.session_state["oz2_hedef"] = _oz_fdef
        st.session_state["oz2_son_sec"] = _oz_sec
    elif st.session_state.get("oz2_son_sec") != _oz_sec:
        st.session_state["oz2_hedef"]   = _oz_fdef
        st.session_state["oz2_son_sec"] = _oz_sec

    _oz_gsm_key   = f"oz2_wa_{_oz_sec}"
    _oz_email_key = f"oz2_email_{_oz_sec}"

    _oz_hedef = _ozr[3].text_input("", key="oz2_hedef", placeholder="Hedef Müşteri", label_visibility="collapsed")
    _oz_vade  = _ozr[4].text_input("", placeholder="Vade...", key="oz2_vade", label_visibility="collapsed")
    _oz_not   = _ozr[5].text_input("", placeholder="Not...", key="oz2_not", label_visibility="collapsed")
    _oz_wa_no = _ozr[6].text_input("", value=_oz_gsm, placeholder="05xxxxxxxxx", key=_oz_gsm_key, label_visibility="collapsed")
    _oz_email = _ozr[7].text_input("", value=_oz_eml, placeholder="Email", key=_oz_email_key, label_visibility="collapsed")

    # ── MÜŞTERİYE AİT TÜM BİLGİLER — Yetkili, adres, il/ilçe, durum, temsilci ──
    if _oz_mus is not None:
        _oz_yetkili  = str(_oz_mus.get("yetkili","") or "") or "—"
        _oz_il       = str(_oz_mus.get("il","") or "")
        _oz_ilce     = str(_oz_mus.get("ilce","") or "")
        _oz_adres    = str(_oz_mus.get("adres","") or "") or "—"
        _oz_durum_b  = str(_oz_mus.get("durum","") or "") or "—"
        _oz_temsilci = str(_oz_mus.get("temsilci","") or "") or "—"
        _oz_ic1, _oz_ic2, _oz_ic3, _oz_ic4, _oz_ic5 = st.columns(5)
        _oz_ic1.caption(f"👤 **Yetkili:** {_oz_yetkili}")
        _oz_ic2.caption(f"📍 **İl/İlçe:** {(_oz_il + '/' + _oz_ilce) if (_oz_il or _oz_ilce) else '—'}")
        _oz_ic3.caption(f"🏠 **Adres:** {_oz_adres[:40]}{'…' if len(_oz_adres) > 40 else ''}")
        _oz_ic4.caption(f"📌 **Durum:** {_oz_durum_b}")
        _oz_ic5.caption(f"🧑‍💼 **Temsilci:** {_oz_temsilci}")

        # ── DAHA ÖNCE BU MÜŞTERİYE ÖZEL TEKLİF VERİLMİŞ Mİ? ────────────────────
        try:
            _oz_gecmis_df = _teklifler_tarih_normalize(_teklifler_oku())
            if not _oz_gecmis_df.empty and "satirlar" in _oz_gecmis_df.columns:
                _oz_gecmis_ozel = _oz_gecmis_df[_oz_gecmis_df["satirlar"].str.contains('ozel', case=False, na=False)]
                _oz_gecmis_bu = _oz_gecmis_ozel[_oz_gecmis_ozel["musteri_adi"].astype(str).str.strip().str.upper() == _oz_hedef.strip().upper()] if not _oz_gecmis_ozel.empty else pd.DataFrame()
            else:
                _oz_gecmis_bu = pd.DataFrame()
        except Exception:
            _oz_gecmis_bu = pd.DataFrame()

        if not _oz_gecmis_bu.empty:
            _oz_gecmis_bu = _oz_gecmis_bu.sort_values("tarih", ascending=False)
            _oz_son_teklif = _oz_gecmis_bu.iloc[0]
            st.warning(f"⚠️ **{_oz_hedef}** için daha önce **{fmt_tarih(_oz_son_teklif.get('tarih',''))}** tarihinde teklif verilmiş ({len(_oz_gecmis_bu)} kayıt).")
            with st.expander(f"📋 {_oz_hedef} — Önceki Teklif(ler)i Gör", expanded=True):
                for _og_idx, _og_row in _oz_gecmis_bu.iterrows():
                    st.caption(f"📅 {fmt_tarih(_og_row.get('tarih',''))} · 👤 {_og_row.get('olusturan','')} · 📝 {_og_row.get('notlar','')}")
                    try:
                        _oz_gecmis_data = _ozj.loads(_og_row.get("satirlar","{}"))
                        for _og2 in _oz_gecmis_data.get("grp",[]):
                            for _os2 in _og2.get("satirlar",[]):
                                _cv2 = _os2.get("cikis","")
                                _vv2 = _os2.get("varis","")
                                _cv2s = ", ".join(_cv2) if isinstance(_cv2,list) else (_cv2 or "—")
                                _vv2s = ", ".join(_vv2) if isinstance(_vv2,list) else (_vv2 or "—")
                                _tur2 = ", ".join(_os2.get("tur",[]) or []) or "—"
                                st.caption(f"　• {_cv2s} → {_vv2s} | {_tur2} | {int(_os2.get('bas',0) or 0)}-{int(_os2.get('bit',0) or 0)} desi | {fmt_para(float(_os2.get('fiyat',0) or 0))}")
                    except Exception:
                        pass
                    if st.button("✏️ Bu Teklifi Düzenlemek İçin Yükle", key=f"oz2_gecmis_yukle_{int(_og_row['id'])}", use_container_width=True):
                        try:
                            _oz_data3 = _ozj.loads(_og_row.get("satirlar","{}"))
                            st.session_state["oz2_grp"] = _oz_data3.get("grp",[])
                            st.session_state["oz2_duz_id"] = int(_og_row["id"])
                            st.session_state["oz2_duz_musteri"] = str(_og_row.get("musteri_adi",""))
                            st.rerun()
                        except Exception as _oge:
                            st.error(f"Yüklenemedi: {_oge}")
                    st.divider()

    st.divider()

    # ── VERİ YAPISI ───────────────────────────────────────────────────────────
    if "oz2_grp" not in st.session_state:
        st.session_state["oz2_grp"] = [
            {"satirlar": [
                {"cikis":[], "varis":[], "tur":["Koli"], "bas":0, "bit":5, "kg":0, "fiyat":0}
            ]}
        ]
    grp = st.session_state["oz2_grp"]

    if st.button("➕ Yeni Grup Ekle", type="primary", key="oz2_grp_ekle"):
        grp.append({"satirlar":[
            {"cikis":[],"varis":[],"tur":["Koli"],"bas":0,"bit":5,"kg":0,"fiyat":0}
        ]})
        st.rerun()

    _CW = [1.8, 1.8, 1.8, 0.9, 0.9, 0.7, 1.2, 0.4]

    for gi, g in enumerate(grp):
        st.markdown(f"---\n**Grup {gi+1}**")

        _bh = st.columns(_CW)
        for _txt,_col in zip(["Çıkış İlleri","Varış İlleri","Tür","Baş Desi","Bit Desi","KG","Fiyat ₺",""],_bh):
            _col.caption(f"**{_txt}**")

        satirlar = g.get("satirlar", [])
        new_satirlar = []

        for si, s in enumerate(satirlar):
            _rc = st.columns(_CW)

            _cikis_def = s.get("cikis","")
            _cikis_def_list = _cikis_def if isinstance(_cikis_def, list) else ([_cikis_def] if _cikis_def and _cikis_def in _OZ_ILLER else [])
            _cikis = _rc[0].multiselect("", _OZ_ILLER,
                default=_cikis_def_list,
                key=f"oz2_c_{gi}_{si}", label_visibility="collapsed")

            _varis_def = s.get("varis","")
            _varis_def_list = _varis_def if isinstance(_varis_def, list) else ([_varis_def] if _varis_def and _varis_def in _OZ_ILLER else [])
            _varis = _rc[1].multiselect("", _OZ_ILLER,
                default=_varis_def_list,
                key=f"oz2_v_{gi}_{si}", label_visibility="collapsed")

            _tur_saved = s.get("tur",[]) or []
            _tur_listesi = _OZ_URUN.copy()
            for _tx in _tur_saved:
                if _tx and _tx not in _tur_listesi: _tur_listesi.append(_tx)
            _tur_def = [x for x in _tur_saved if x]
            if not _tur_def and _tur_listesi: _tur_def = [_tur_listesi[0]]
            _tur = _rc[2].multiselect("", _tur_listesi,
                default=_tur_def,
                key=f"oz2_tur_{gi}_{si}", label_visibility="collapsed")

            _bas = _rc[3].number_input("", min_value=0.0, step=1.0,
                value=float(s.get("bas",0) or 0),
                key=f"oz2_bas_{gi}_{si}", label_visibility="collapsed", format="%.0f")
            _bit = _rc[4].number_input("", min_value=0.0, step=1.0,
                value=float(s.get("bit",0) or 0),
                key=f"oz2_bit_{gi}_{si}", label_visibility="collapsed", format="%.0f")
            _kg  = _rc[5].number_input("", min_value=0.0, step=1.0,
                value=float(s.get("kg",0) or 0),
                key=f"oz2_kg_{gi}_{si}", label_visibility="collapsed", format="%.0f")
            _fiy = _rc[6].number_input("", min_value=0.0, step=1.0,
                value=float(s.get("fiyat",0) or 0),
                key=f"oz2_fiy_{gi}_{si}", label_visibility="collapsed", format="%.0f")

            _sil = _rc[7].button("➖", key=f"oz2_ssil_{gi}_{si}")
            if not _sil or len(satirlar) <= 1:
                new_satirlar.append({"cikis":_cikis,"varis":_varis,"tur":_tur,
                    "bas":_bas,"bit":_bit,"kg":_kg,"fiyat":_fiy})
            else:
                satirlar.pop(si)
                g["satirlar"] = satirlar
                st.rerun()

        g["satirlar"] = new_satirlar

        _ba1, _ba2 = st.columns([1.2, 1.5])
        if _ba1.button("➕ Satır Ekle", key=f"oz2_sekle_{gi}", use_container_width=True):
            g["satirlar"].append({"cikis":[],"varis":[],"tur":["Koli"],"bas":0,"bit":0,"kg":0,"fiyat":0})
            st.rerun()
        if _ba2.button("🗑️ Grubu Sil", key=f"oz2_gsil_{gi}", use_container_width=True) and len(grp) > 1:
            grp.pop(gi); st.rerun()

    st.session_state["oz2_grp"] = grp

    # ── MESAJ FONKSİYONU ─────────────────────────────────────────────────────
    def _oz_mesaj_olustur(_grp, _hedef, _vade):
        _msg = f"Sayın {_hedef} yetkilisi,\n\nSize özel kargo fiyat teklifimiz:\n\n"
        for _g in _grp:
            _c_all, _v_all = [], []
            for _s in _g.get("satirlar",[]):
                _cv = _s.get("cikis","")
                _vv = _s.get("varis","")
                if isinstance(_cv, list): _c_all += _cv
                elif _cv: _c_all.append(_cv)
                if isinstance(_vv, list): _v_all += _vv
                elif _vv: _v_all.append(_vv)
            _c_all = list(dict.fromkeys(_c_all))
            _v_all = list(dict.fromkeys(_v_all))
            _urun_satirlar = []
            for _s in _g.get("satirlar",[]):
                _tt = ", ".join(_s.get("tur",[]) or []) or ""
                _b1 = int(_s.get("bas",0) or 0)
                _b2 = int(_s.get("bit",0) or 0)
                _kk = int(_s.get("kg",0) or 0)
                _ff = float(_s.get("fiyat",0) or 0)
                if not _tt: continue  # sadece ürün adı boşsa atla, fiyat 0 olsa da göster
                _ds = f"{_b1}–{_b2} desi" if _b1 or _b2 else ""
                _ks = f"{_kk} kg" if _kk else ""
                _satir = f"  • {_tt}"
                if _ds: _satir += f" | {_ds}"
                if _ks: _satir += f" | {_ks}"
                _satir += f" → {fmt_para(_ff)}"
                _urun_satirlar.append(_satir)
            if not _c_all and not _v_all and not _urun_satirlar: continue
            _msg += f"*{', '.join(_c_all) or '—'} → {', '.join(_v_all) or '—'}*\n"
            _msg += "\n".join(_urun_satirlar) + "\n\n"
        if _vade: _msg += f"Vade: {_vade}\n"
        _msg += "\n7/24 ulaşabilirsiniz."
        return _msg

    # ── ÖZET ─────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📋 Özet")
    for _og in grp:
        _c_all2, _v_all2 = [], []
        for _s in _og.get("satirlar",[]):
            _cv = _s.get("cikis","")
            _vv = _s.get("varis","")
            if isinstance(_cv, list): _c_all2 += _cv
            elif _cv: _c_all2.append(_cv)
            if isinstance(_vv, list): _v_all2 += _vv
            elif _vv: _v_all2.append(_vv)
        _c_all2 = list(dict.fromkeys(_c_all2))
        _v_all2 = list(dict.fromkeys(_v_all2))
        _has = any(_s.get("tur") or float(_s.get("fiyat",0) or 0) for _s in _og.get("satirlar",[]))
        if not _c_all2 and not _v_all2 and not _has: continue
        st.markdown(f"**{', '.join(_c_all2) or '—'} → {', '.join(_v_all2) or '—'}**")
        for _os in _og.get("satirlar",[]):
            _ott = ", ".join(_os.get("tur",[]) or []) or ""
            _ob1 = int(_os.get("bas",0) or 0)
            _ob2 = int(_os.get("bit",0) or 0)
            _okk = int(_os.get("kg",0) or 0)
            _off = float(_os.get("fiyat",0) or 0)
            if not _ott and not _off: continue
            _ods = f"{_ob1}–{_ob2} desi" if _ob1 or _ob2 else "—"
            _oks = f"{_okk} kg" if _okk else "—"
            st.caption(f"&nbsp;&nbsp; • {_ott} | {_ods} | KG: {_oks} | **{fmt_para(_off)}**")

    # ── KAYDET + MESAJ ────────────────────────────────────────────────────────
    st.divider()
    _ks1, _ks2, _ks3 = st.columns(3)
    if _ks1.button("💾 Teklifi Kaydet", use_container_width=True, type="primary", key="oz2_kaydet"):
        if not _oz_hedef:
            st.warning("Müşteri adı boş!")
        else:
            if _oz_mus is None and not _oz_sec_id:
                # NOT: Eskiden burada müşteri eşleşmediğinde musteri_id sessizce 0
                # yazılıyordu — bu da teklifin o müşteriyle hiç ilişkilendirilmemesine
                # ve Cari Liste'deki "🧾 Teklif" rozetinde hiç görünmemesine sebep
                # oluyordu (özellikle yeni eklenen müşterilerde, 2 dakikalık önbellek
                # onları henüz listeye almamış olabiliyordu). "-- Müşteri Seçin --"
                # kutusundan seçim yapılmadıysa (serbest metin girişi) bunu bilerek
                # yapıyor olabilirsiniz, o yüzden burada sadece uyarıyoruz, engellemiyoruz.
                st.warning("⚠️ Müşteri listeden seçilmedi — bu teklif hiçbir cari karta bağlanmayacak, Cari Liste'deki teklif sayısında görünmeyecek. Bağlanmasını istiyorsanız 'Müşteri Seçin' kutusundan seçip tekrar deneyin (yeni eklediyseniz sayfayı yenilemeniz gerekebilir).")
            _oz_veri = {
                "musteri_id": int(_oz_mus["id"]) if _oz_mus is not None else (int(_oz_sec_id) if _oz_sec_id else 0),
                "musteri_adi": _oz_hedef,
                "satirlar": _ozj.dumps({"tip":"ozel","grp":grp}, ensure_ascii=False),
                "toplam_tutar": sum(float(s.get("fiyat",0) or 0) for g in grp for s in g.get("satirlar",[])),
                "olusturan": st.session_state["kullanici"],
                "notlar": f"Vade:{_oz_vade} | Not:{_oz_not}"
            }
            _duz_id = st.session_state.get("oz2_duz_id")
            if _duz_id:
                db_update("teklifler",{
                    "musteri_adi":_oz_veri["musteri_adi"],
                    "satirlar":_oz_veri["satirlar"],
                    "toplam_tutar":_oz_veri["toplam_tutar"],
                    "notlar":_oz_veri["notlar"]
                },"id",_duz_id)
                st.success("✅ Teklif güncellendi!")
                st.session_state.pop("oz2_duz_id",None)
            else:
                db_insert("teklifler", _oz_veri)
                st.success("✅ Kaydedildi!")
            # NOT: db_read 2 dakika önbellekli — kaydettikten hemen sonra temizlemezsek
            # yeni teklif "Kayıtlı Teklifler"/"Kayıtlı Özel Teklifler" listelerinde
            # 2 dakika boyunca görünmez, sanki kaydedilmemiş gibi görünürdü.
            try: db_read.clear()
            except: pass
            st.session_state["oz2_wa_mesaj"] = _oz_mesaj_olustur(grp, _oz_hedef, _oz_vade)
            st.session_state.pop("oz2_grp",None)
            st.rerun()

    if _ks2.button("📱 WA Mesajı Oluştur", use_container_width=True, key="oz2_wa_olustur"):
        st.session_state["oz2_wa_mesaj"] = _oz_mesaj_olustur(grp, _oz_hedef, _oz_vade)
        st.rerun()

    if _ks3.button("📜 Sözleşme Hazırla", use_container_width=True, key="oz2_sozlesme_git"):
        if not _oz_hedef:
            st.warning("Müşteri adı boş!")
        else:
            st.session_state["aktif_tab"] = "sozlesme"
            st.session_state["sozlesme_musteri_onsel"] = _oz_hedef
            st.rerun()

    if st.session_state.get("oz2_wa_mesaj"):
        _wtxt = st.text_area("WA Mesajı:", value=st.session_state["oz2_wa_mesaj"], height=220, key="oz2_wa_txt")
        _wno  = _ozre.sub(r"[\s\-\(\)+]","", _oz_wa_no)
        if _wno.startswith("0") and len(_wno)==11: _wno = "90"+_wno[1:]
        elif len(_wno)==10: _wno = "90"+_wno
        if len(_wno)==12 and _wno.isdigit():
            from urllib.parse import quote as _ozq
            st.button("📱 WhatsApp'ta Aç", use_container_width=True, type="primary", disabled=True, help="Geçici olarak devre dışı", key="wa_btn_ozel1")
            if st.button("✅ WA Gönderildi Kaydet", use_container_width=True, key="oz2_wa_log"):
                db_insert("islem_kaydi",{
                    "musteri_id": int(_oz_mus["id"]) if _oz_mus is not None else 0,
                    "musteri_adi": _oz_hedef, "islem_turu": "WhatsApp Teklif",
                    "icerik": _wtxt, "gonderim_bilgisi": _wno,
                    "olusturan": st.session_state["kullanici"]
                })
                st.success("✅ Kaydedildi!")
        else:
            st.warning("Geçerli WA numarası girin.")

    # ── KAYITLI TEKLİFLER ────────────────────────────────────────────────────
    with st.expander("📋 Kayıtlı Özel Teklifler"):
        try:
            _oz_df_tek = _teklifler_tarih_normalize(_teklifler_oku())
            if not _oz_df_tek.empty and "satirlar" in _oz_df_tek.columns:
                _oz_df_tek2 = _oz_df_tek[_oz_df_tek["satirlar"].str.contains('ozel', case=False, na=False)]
            else:
                _oz_df_tek2 = pd.DataFrame()

            # Sadece o an seçili olan müşterinin tekliflerini göster.
            _oz_aktif_id = int(_oz_mus["id"]) if _oz_mus is not None else (int(_oz_sec_id) if _oz_sec_id else None)
            if _oz_aktif_id and not _oz_df_tek2.empty and "musteri_id" in _oz_df_tek2.columns:
                _oz_df_tek2 = _oz_df_tek2[pd.to_numeric(_oz_df_tek2["musteri_id"], errors="coerce") == _oz_aktif_id]

            if not _oz_aktif_id:
                st.caption("Tekliflerini görmek için yukarıdan bir müşteri seçin.")
            if _oz_df_tek2.empty:
                st.info("Henüz kayıtlı özel teklif yok.")
            else:
                _oz_tek_opts = ["-- Teklif Seçin --"] + [
                    f"[{int(r['id'])}] {r.get('musteri_adi','')} | {fmt_tarih(r.get('tarih',''))}"
                    for _,r in _oz_df_tek2.iterrows()]
                _oz_tek_sec = st.selectbox("Teklif Seç:", _oz_tek_opts, key="oz2_tek_sec")

                if _oz_tek_sec != "-- Teklif Seçin --" and "[" in _oz_tek_sec:
                    _oz_tid = int(_oz_tek_sec.split("]")[0].replace("[","").strip())
                    _oztmatch = _oz_df_tek2[_oz_df_tek2["id"]==_oz_tid]
                    if _oztmatch.empty: raise Exception("Teklif bulunamadı")
                    _oz_trow = _oztmatch.iloc[0]
                    st.caption(f"📅 {fmt_tarih(_oz_trow.get('tarih',''))} · 👤 {_oz_trow.get('olusturan','')} · 📝 {_oz_trow.get('notlar','')}")
                    try:
                        _oz_data = _ozj.loads(_oz_trow.get("satirlar","{}"))
                        _oz_grp_k = _oz_data.get("grp",[])
                        _bh2 = st.columns([1.5,1.5,1.8,0.9,0.9,0.7,1.2])
                        for _txt,_col in zip(["Çıkış","Varış","Tür","Baş D","Bit D","KG","Fiyat ₺"],_bh2):
                            _col.caption(f"**{_txt}**")
                        for _og2 in _oz_grp_k:
                            for _os2 in _og2.get("satirlar",[]):
                                _sr = st.columns([1.5,1.5,1.8,0.9,0.9,0.7,1.2])
                                _cv2 = _os2.get("cikis","")
                                _vv2 = _os2.get("varis","")
                                _sr[0].caption(", ".join(_cv2) if isinstance(_cv2,list) else (_cv2 or "—"))
                                _sr[1].caption(", ".join(_vv2) if isinstance(_vv2,list) else (_vv2 or "—"))
                                _sr[2].caption(", ".join(_os2.get("tur",[]) or []) or "—")
                                _sr[3].caption(str(int(_os2.get("bas",0) or 0)))
                                _sr[4].caption(str(int(_os2.get("bit",0) or 0)))
                                _sr[5].caption(str(int(_os2.get("kg",0) or 0)))
                                _sr[6].caption(fmt_para(float(_os2.get("fiyat",0) or 0)))
                    except: pass

                    _eak1,_eak2,_eak3,_eak4 = st.columns(4)
                    if _eak1.button("✏️ Düzenle", key="oz2_duzenle_btn", use_container_width=True, type="primary"):
                        try:
                            _oz_data2 = _ozj.loads(_oz_trow.get("satirlar","{}"))
                            st.session_state["oz2_grp"] = _oz_data2.get("grp",[])
                            st.session_state["oz2_duz_id"] = _oz_tid
                            st.session_state["oz2_duz_musteri"] = str(_oz_trow.get("musteri_adi",""))
                            st.session_state.pop("oz2_hedef",None)
                            st.session_state.pop("oz2_son_sec",None)
                            st.rerun()
                        except Exception as _oe: st.error(f"Hata: {_oe}")

                    if _eak2.button("📋 Kopyala", key=f"oz2_kopyala_{_oz_tid}", use_container_width=True):
                        try:
                            _oz_data_kop = _ozj.loads(_oz_trow.get("satirlar","{}"))
                            # Aynı satırları yükle ama ID sıfırla — yeni müşteri seçilecek
                            st.session_state["oz2_grp"] = _oz_data_kop.get("grp",[])
                            st.session_state.pop("oz2_duz_id", None)       # yeni kayıt olarak
                            st.session_state.pop("oz2_duz_musteri", None)
                            st.session_state.pop("oz2_hedef", None)
                            st.session_state.pop("oz2_son_sec", None)
                            st.session_state.pop("oz2_musteri", None)
                            st.session_state["_oz2_kopyalandi"] = True
                            st.rerun()
                        except Exception as _oe: st.error(f"Kopyalama hatası: {_oe}")

                    with _eak3.expander("📝 Not Güncelle"):
                        _oz_yn = st.text_area("Not:",value=str(_oz_trow.get("notlar","")),height=70,key=f"oz2_not_up_{_oz_tid}")
                        if st.button("💾 Kaydet",key=f"oz2_not_btn_{_oz_tid}",use_container_width=True):
                            db_update("teklifler",{"notlar":_oz_yn},"id",_oz_tid)
                            st.success("✅"); st.rerun()
                    if _eak4.button("🗑️ Sil",key="oz2_tek_sil",use_container_width=True):
                        _sb_d=get_sb_client()
                        if _sb_d: _sb_d.table("teklifler").delete().eq("id",_oz_tid).execute()
                        st.success("🗑️ Silindi!"); st.rerun()
                    if st.session_state.get("oz2_duz_id") == _oz_tid:
                        st.info("⚠️ Düzenleme modu aktif — yukarıda değişiklik yapıp kaydedin.")
                        if st.button("❌ İptal", key="oz2_duz_iptal"):
                            st.session_state.pop("oz2_duz_id",None)
                            st.session_state.pop("oz2_grp",None)
                            st.rerun()
        except Exception as _oz_e: st.error(f"Hata: {_oz_e}")

    with st.expander("⚙️ Ürün Listesi Yönetimi"):
        st.caption("Varsayılan ürünlere ek olarak yeni ürün ekleyebilirsiniz.")
        _tam_liste = _oz_urun_listesi()
        _ekstra_liste = [x for x in _tam_liste if x not in _OZ_URUN_VARSAYILAN]
        st.markdown("**Varsayılan** (değiştirilemez):")
        st.caption(" · ".join(_OZ_URUN_VARSAYILAN))
        if _ekstra_liste:
            st.markdown("**Ekstra ürünler:**")
            for _ui,_un in enumerate(_ekstra_liste):
                _uc1,_uc2 = st.columns([5,1])
                _uc1.caption(f"🔹 {_un}")
                if _uc2.button("🗑️",key=f"oz_urun_sil_{_ui}"):
                    _ekstra_liste.remove(_un)
                    _oz_urun_kaydet(_OZ_URUN_VARSAYILAN+_ekstra_liste); st.rerun()
        st.divider()
        _ya1,_ya2 = st.columns([4,1])
        _yeni_urun = _ya1.text_input("",placeholder="Yeni ürün adı...",key="oz_yeni_urun",label_visibility="collapsed")
        if _ya2.button("➕ Ekle",key="oz_urun_ekle_btn",use_container_width=True):
            if _yeni_urun and _yeni_urun.strip():
                if _yeni_urun.strip() in _tam_liste:
                    st.warning("Bu ürün zaten var!")
                else:
                    _ekstra_liste.append(_yeni_urun.strip())
                    if _oz_urun_kaydet(_OZ_URUN_VARSAYILAN+_ekstra_liste):
                        st.success(f"✅ '{_yeni_urun}' eklendi!"); st.rerun()
                    else: st.error("Kaydedilemedi!")


elif aktif == "kayitli_teklifler":
    sayfa_log("kayitli_teklifler")
    st.markdown("## 📋 Kayıtlı Teklifler")
    st.caption("Kendisine teklif hazırlanmış tüm müşteriler — cari ana liste ile aynı kolon yapısında.")

    with st.spinner("Yükleniyor..."):
        _kt_tek_df = _teklifler_tarih_normalize(_teklifler_oku())
        _kt_cari_df = get_cari_listesi()

    # ── DOĞRULAMA: veritabanındaki HAM kayıt sayısı — hiçbir filtre/eşleştirme
    # yok, doğrudan "teklifler" tablosunda kaç satır var, onu gösteriyor.
    st.info(f"🔎 Doğrulama: `teklifler` tablosunda toplam **{len(_kt_tek_df)}** kayıt var (hiçbir filtre uygulanmadan, veritabanından direkt sayım).")

    if _kt_tek_df.empty or "musteri_id" not in _kt_tek_df.columns:
        st.info("Henüz hiçbir müşteriye teklif hazırlanmamış.")
    else:
        _kt_tek_df = _kt_tek_df.copy()
        _kt_tek_df["musteri_id"] = pd.to_numeric(_kt_tek_df["musteri_id"], errors="coerce")
        _kt_tek_df = _kt_tek_df[_kt_tek_df["musteri_id"] > 0]  # bağlantısız (0) teklifler hariç
        if _kt_tek_df.empty or _kt_cari_df.empty:
            st.info("Henüz hiçbir müşteriye bağlı teklif yok.")
        else:
            _kt_grup = _kt_tek_df.groupby("musteri_id").agg(
                teklif_sayisi=("id", "count"),
                son_teklif_tarihi=("tarih", "max"),
            ).reset_index()
            _kt_grup["musteri_id"] = _kt_grup["musteri_id"].astype(int)

            _kt_birlesik = _kt_grup.merge(_kt_cari_df, left_on="musteri_id", right_on="id", how="left")
            _kt_birlesik = _kt_birlesik.dropna(subset=["firma"])  # cari kartı silinmiş olabilir

            for _tk in ["gsm", "sabit"]:
                if _tk in _kt_birlesik.columns:
                    _kt_birlesik[_tk] = _telefon_temizle(_kt_birlesik[_tk])

            _kt_ara = st.text_input("🔍 Firma / yetkili ara", key="kt_ara")
            if _kt_ara:
                _m = pd.Series(False, index=_kt_birlesik.index)
                if "firma" in _kt_birlesik.columns:
                    _m = _m | _kt_birlesik["firma"].astype(str).str.contains(_kt_ara, case=False, na=False)
                if "yetkili" in _kt_birlesik.columns:
                    _m = _m | _kt_birlesik["yetkili"].astype(str).str.contains(_kt_ara, case=False, na=False)
                _kt_birlesik = _kt_birlesik[_m]

            _kt_birlesik = _kt_birlesik.sort_values("son_teklif_tarihi", ascending=False).reset_index(drop=True)
            st.markdown(f"**{len(_kt_birlesik)} müşteri**")

            _kt_kolonlar = [c for c in ["firma", "yetkili", "gsm", "il", "ilce", "durum", "teklif_sayisi", "son_teklif_tarihi"] if c in _kt_birlesik.columns]
            _kt_goster = _kt_birlesik[_kt_kolonlar].copy()
            if "son_teklif_tarihi" in _kt_goster.columns:
                _kt_goster["son_teklif_tarihi"] = _kt_goster["son_teklif_tarihi"].apply(fmt_tarih)
            _kt_baslik_map = {"firma": "Firma", "yetkili": "Yetkili", "gsm": "GSM", "il": "İl", "ilce": "İlçe",
                               "durum": "Durum", "teklif_sayisi": "Teklif Sayısı", "son_teklif_tarihi": "Son Teklif"}
            _kt_goster.columns = [_kt_baslik_map.get(c, c) for c in _kt_kolonlar]

            st.dataframe(_kt_goster, use_container_width=True, hide_index=True, height=560)

            st.divider()
            st.markdown("#### 🔍 Detay — Bu müşterinin tüm teklif kayıtları")
            _kt_opts = ["-- Müşteri Seçin --"] + [f"[{int(r['musteri_id'])}] {r.get('firma','')}" for _, r in _kt_birlesik.iterrows()]
            _kt_sec = st.selectbox("", _kt_opts, key="kt_detay_sec", label_visibility="collapsed")
            if _kt_sec != "-- Müşteri Seçin --" and "[" in _kt_sec:
                _kt_id = int(_kt_sec.split("]")[0].replace("[", "").strip())
                _kt_firma_ad = _kt_sec.split("]", 1)[1].strip()
                if st.button("📋 Notlar & Randevu Aç", key="kt_detay_btn"):
                    not_dialog(_kt_id, _kt_firma_ad)

                # Bu müşteriye ait HAM teklif kayıtlarını tek tek göster — şüpheli
                # yüksek sayıları (28 gibi) incelemek ve istenirse tek tek silmek için.
                _kt_bu_musteri = _kt_tek_df[_kt_tek_df["musteri_id"] == _kt_id].copy()
                st.markdown(f"**{len(_kt_bu_musteri)} ham teklif/sözleşme kaydı bulundu:**")
                _kt_bu_musteri = _kt_bu_musteri.sort_values("id", ascending=False)
                for _, _ktr in _kt_bu_musteri.iterrows():
                    _ktr_id = int(_ktr.get("id", 0))
                    _ktr_tip = "?"
                    try:
                        _ktr_tip = json.loads(_ktr.get("satirlar", "{}")).get("tip", "?")
                    except: pass
                    _ktr_tarih = fmt_tarih(_ktr.get("tarih", ""))
                    _ktr_tutar = _ktr.get("toplam_tutar", 0)
                    _ktr_yazan = _ktr.get("olusturan", "")
                    _c1, _c2, _c3, _c4, _c5, _c6 = st.columns([0.7, 1.3, 1.3, 1.3, 1.5, 0.8])
                    _c1.caption(f"#{_ktr_id}")
                    _c2.caption(_ktr_tip)
                    _c3.caption(_ktr_tarih)
                    _c4.caption(fmt_para(float(_ktr_tutar or 0)))
                    _c5.caption(_ktr_yazan)
                    _kt_sil_bek = f"kt_sil_bekliyor_{_ktr_id}"
                    if not st.session_state.get(_kt_sil_bek):
                        if _c6.button("🗑️", key=f"kt_sil_btn_{_ktr_id}"):
                            st.session_state[_kt_sil_bek] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ #{_ktr_id} kaydını kalıcı olarak silmek üzeresiniz — GERİ ALINAMAZ.")
                        _oc1, _oc2 = st.columns(2)
                        if _oc1.button("✅ Evet, sil", type="primary", key=f"kt_sil_onay_{_ktr_id}"):
                            _kt_sb_sil = get_sb_client()
                            if _kt_sb_sil:
                                _kt_sb_sil.table("teklifler").delete().eq("id", _ktr_id).execute()
                            try: db_read.clear()
                            except: pass
                            st.session_state.pop(_kt_sil_bek, None)
                            st.success("Silindi.")
                            st.rerun()
                        if _oc2.button("Vazgeç", key=f"kt_sil_vazgec_{_ktr_id}"):
                            st.session_state.pop(_kt_sil_bek, None)
                            st.rerun()

elif aktif == "sozlesme":
    sayfa_log("sozlesme")
    import json as _szj
    from datetime import date as _szdate

    st.markdown("## 📜 Sözleşmeler")

    # ══════════════════════════════════════════════════════════════════════
    # YARDIMCI FONKSİYONLAR — fiyat gruplama + docx/pdf üretimi
    # ══════════════════════════════════════════════════════════════════════
    def _sz_fiyat_grupla(teklif_veri):
        """Özel Teklif JSON'unu MADDE 3 formatına (başlık + madde listesi) çevirir"""
        try:
            data = _szj.loads(teklif_veri) if isinstance(teklif_veri, str) else (teklif_veri or {})
        except Exception:
            return []
        gruplar, sira = {}, []
        for grp in data.get("grp", []):
            for s in grp.get("satirlar", []):
                _cikis = s.get("cikis", [])
                _varis = s.get("varis", [])
                _cikis_s = ", ".join(_cikis) if isinstance(_cikis, list) else str(_cikis or "")
                _varis_s = ", ".join(_varis) if isinstance(_varis, list) else str(_varis or "")
                if not _cikis_s and not _varis_s:
                    continue
                _baslik = f"{_cikis_s} → {_varis_s}"
                _tur = ", ".join(s.get("tur", []) or []) or "—"
                try: _bas = int(float(s.get("bas", 0) or 0))
                except: _bas = 0
                try: _bit = int(float(s.get("bit", 0) or 0))
                except: _bit = 0
                try: _fiyat = float(s.get("fiyat", 0) or 0)
                except: _fiyat = 0.0
                _satir_txt = f"{_tur} | {_bas}-{_bit} desi → {fmt_para(_fiyat)}"
                if _baslik not in gruplar:
                    gruplar[_baslik] = []
                    sira.append(_baslik)
                gruplar[_baslik].append(_satir_txt)
        return [{"baslik": b, "satirlar": gruplar[b]} for b in sira]

    _SZ_KOSULLAR = [
        "STF KARGO her gün kargo İhbarlarını adresten alır ve ertesi gün teslim eder.",
        "Kargo taşımaları STF KARGO'nun kurallarına göre yapılır.",
        "Kargo taşıma sonunda alıcı veya vekiline yada temsilcisine hüviyet ve imzası karşılığında teslim edilir. "
        "Teslimden sonra STF KARGO'nun her türlü sorumluluğu sona erer.",
        "Harp ve harbe benzer hareket. Grev, kargaşalık, halk hareketleri ve hareketlerle ilgili olarak alınan "
        "önlemlerden doğan gecikme ve hasardan STF KARGO sorumlu değildir.",
        "Gelen kargo alıcısına en kısa zamanda bildirilecek iki gün bekletilir. Bu süre içerisinde kargonun teslim "
        "alınmaması halinde göndericisinden talimat istenir. Üç gün içerisinde talimat gelmezse, kargo "
        "göndericisine iade edilerek taşıma ücreti ve masrafları kendisinden tahsil edilir.",
        "İrsaliye ve faturası STF KARGO'ya verilmiş ve değer beyanı yapılmış tüm kargo taşıma YURT İÇİ TAŞIYICI "
        "MALİ MESULİYET SİGORTA SÖZLEŞMESİ hükümlerine göre sigortalıdır.",
        "Bulundurulması yasalarla men edilmiş veya ruhsat ve izne tabi olanlarla, çabuk bozulabilecek, fena ve "
        "ağır koku veren, yanıcı, patlayıcı, parlayıcı, zehirli, yakıcı aşındırıcı maddeler taşınmaz.",
        "Çek, senet, hisse senedi vb kıymetli kağıtlar taşınmaz.",
        "Gönderenin taşınan eşyanın mutad evsafına göre yeterli veya uygun olmayan ambalajlanmasının neden "
        "olduğu hasar, ziyan ve masraflardan STF KARGO sorumlu değildir.",
        "Üzerinde tahrifat yapılmış, oynanmış, silinti, kazıntı bulunan ambar tesellüm fişleri hükümsüzdür.",
        "Üç ay içersinde aranmayan kargolardan sorumluluk kabul edilmez.",
        "Bazı mal çeşitlerinin nitelikleri itibarıyla bozulma, aşınma, normal çürüme, kuruma vb. nedenlerden "
        "meydan gelen hasarlardan STF KARGO sorumlu değildir.",
        "İş bu sözleşme taraflarının ihtilafı vukuunda İSTANBUL mahkemeleri ve icra daireleri yetkilidir.",
        "Sigorta ücreti fatura edilmeyen taşımalarda meydana gelebilecek hasar veya kayıp durumunda ödenecek "
        "tazminat tutarı taşıma bedelinin 3 (üç) katıdır.",
    ]
    _SZ_YASAKLAR = [
        "Her türlü patlayıcı, yanıcı, zehirleyici, fena kokulu kargolar. Ayrıca dolu ve boş gaz tüpleri "
        "(yangın söndürme cihazı hariç)",
        "Kısa sürede bozulabilecek; et, tavuk, balık, bağırsak, ham deri, mutfak yağları ve yumurta, sıvı "
        "deterjan, makine yağları, plastik ve yağlı boyalar.",
        "Yüklenip indirilmesi zor, diğer kargolara zarar verme ihtimali yüksek olan 100 kg'dan ağır tek parça "
        "kargolarla, uzunluğu üç metreden fazla sandık veya demir malzemeler.",
        "Kapalı zarf veya başka bir muhafaza içine konmuş para ve senet, yemek çeki, piyango bileti ile altın "
        "ve ziynet eşyası taşınmaz.",
        "Ambalajından dolayı delinme, parçalanma, dağılma, kırılma sonucunda kendine veya diğer kargolara "
        "zarar verme ihtimali yüksek olan kargolar.",
        "Zarf içinde ağır, sivri, zarfı yırtabilecek maddeler.",
    ]

    def _sz_docx_uret(v):
        """Hiçbir pip paketi gerektirmeden (sadece Python stdlib zipfile) .docx üretir"""
        import zipfile as _szzip
        import io as _szio
        from xml.sax.saxutils import escape as _szesc

        _CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>')
        _RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
        _DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>')

        def _run(text, bold=False, size=22):
            props = f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
            if bold: props = "<w:b/><w:bCs/>" + props
            return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{_szesc(str(text))}</w:t></w:r>'

        def _para(runs_xml="", after=120, before=0, align=None, indent=None):
            pPr = f'<w:spacing w:after="{after}" w:before="{before}"/>'
            if align: pPr += f'<w:jc w:val="{align}"/>'
            if indent: pPr += f'<w:ind w:left="{indent}"/>'
            return f'<w:p><w:pPr>{pPr}</w:pPr>{runs_xml}</w:p>'

        def _page_break():
            return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'

        def _two_col(left, right, bold=True, size=22, after=60):
            pPr = f'<w:tabs><w:tab w:val="left" w:pos="5040"/></w:tabs><w:spacing w:after="{after}"/>'
            r1 = _run(left, bold=bold, size=size)
            r2 = '<w:r><w:tab/></w:r>' + _run(right, bold=bold, size=size)
            return f'<w:p><w:pPr>{pPr}</w:pPr>{r1}{r2}</w:p>'

        def _imza_bloklari():
            return (_two_col("STF KARGO NAKLİYAT VE TİCARET LTD. ŞTİ.", v["musteri_kisa"], bold=True, size=22)
                  + _two_col("KAŞE-İMZA", "KAŞE-İMZA", bold=False, size=21)
                  + _two_col("", v["musteri_uzun"], bold=False, size=16))

        P = []
        P.append(_para(_run("MADDE 1: TARAFLAR", bold=True, size=26), after=160))
        P.append(_para(_run("Taşıyıcı", bold=True) + _run(" : ") + _run("STF KARGO NAKLİYAT TİCARET LTD.ŞTİ", bold=True)))
        P.append(_para(_run("Adres", bold=True) + _run(" : Halkalı Merkez Mah.Dereboyu Caddesi No:56 KÜÇÜKÇEKMECE/İSTANBUL"), after=200))
        P.append(_para(_run("Taşıtıcı", bold=True) + _run(" : ") + _run(v["musteri_uzun"], bold=True)))
        P.append(_para(_run("Adres", bold=True) + _run(" : " + (v["adres"] or "—"))))
        P.append(_para(_run("V.D: ", bold=True) + _run(v["vd"] or "—") + _run("   V.No: ", bold=True) + _run(v["vno"] or "—"), after=200))
        P.append(_para(_run(f"Bir tarafta Stf Kargo Nakliyat ve Ticaret Ltd. Şti. (kısaca STF KARGO olarak "
                             f"anılacaktır.) diğer tarafta {v['musteri_uzun']} (kısaca {v['musteri_kisa']} olarak "
                             f"anılacaktır) arasında akdedilen bu sözleşme tarafların İstanbul geneli yapılacak "
                             f"taşımacılık faaliyetine ilişkin karşılıklı hak ve yükümlülüklerini belirler.", size=21), after=220))

        P.append(_para(_run("MADDE 2: GEÇERLİLİK SÜRESİ:", bold=True, size=24), after=100))
        P.append(_para(_run(f"İşbu sözleşme {v['gecerlilik_tarihi']} tarihine kadar geçerlidir. Bitiminde "
                             f"karşılıklı mutabakat ile yenilenir.", size=21)))
        P.append(_para(_run("Taraflardan herhangi biri bir ay önceden yazılı bildirim yapmak koşulu ile veya bu "
                             "sözleşme hükümlerine aykırı hareket edilmesi halinde sözleşme tek taraflı "
                             "feshedilebilir.", size=21), after=220))

        P.append(_para(_run("MADDE 3: UYGULANACAK FİYAT TARİFESİ:", bold=True, size=24), after=100))
        P.append(_para(_run(f"Geçerlilik süresi içerisinde STF KARGO {v['musteri_kisa']}'nin aşağıdaki tabloda "
                             f"belirtilen ebattaki kargolarını yazılı fiyatlarla taşımayı kabul eder.", size=21), after=140))
        if v["fiyat_gruplari"]:
            for grp in v["fiyat_gruplari"]:
                P.append(_para(_run(grp["baslik"], bold=True, size=21), after=60))
                for satir in grp["satirlar"]:
                    P.append(_para(_run("•  " + satir, size=20), after=40, indent=280))
                P.append(_para("", after=60))
        else:
            P.append(_para(_run("(Bu müşteri için tanımlı fiyat bulunamadı — Özel Teklif oluşturulunca burada "
                                 "listelenir.)", size=19), after=100))
        P.append(_para(_run("Taşıma fiyatlarında KDV ayrıca eklenecektir.", bold=True, size=21), after=220))

        P.append(_para(_run("MADDE 4: ÖDEME ŞEKLİ VE ZAMANI", bold=True, size=24), after=100))
        P.append(_para(_run(f"{v['musteri_kisa']} kendisine gelen ürünlere ait ücret alıcı faturalar ile "
                             f"gönderdiği ürünlere ait ücret gönderen faturaları tarihlerinden itibaren "
                             f"{v['vade']} eft-havale olarak öder.", size=21), after=220))

        P.append(_para(_run("MADDE 5: YAKIT KLOZU", bold=True, size=24), after=100))
        P.append(_para(_run("Ay sonunda oluşan yakıt artış farkı %50 oranında fiyatlara yansıtılır", size=21), after=220))

        P.append(_para(_run("MADDE 6: HİZMET ŞUBESİ ve YETKİLİSİ: İstanbul-Merkez Şubesi: Koray Ertaş", bold=True, size=24), after=100))
        P.append(_para(_run("0 212 671 50 35-36 / 0 212 671 96 51-444 77 83", size=21), after=40))
        P.append(_para(_run("Halkalı Merkez Mah.Dereboyu Caddesi No:56 K.Çekmece-İSTANBUL", size=21), after=40))
        P.append(_para(_run("koray.ertas@stflojistik.com", size=21), after=220))

        P.append(_para(_run("MADDE 7: TAŞIMA KOŞULLARI:", bold=True, size=24), after=100))
        P.append(_para(_run("Genel taşıma koşulları ikinci sayfada 14 madde halinde açıklanmış olup tarafları "
                             "tamamen bağlayıcı nitelik taşır.", size=21), after=220))

        P.append(_para(_run("MADDE 8:", bold=True, size=24), after=100))
        P.append(_para(_run(f"İşbu taşıma sözleşmesi toplam sekiz maddeden ibaret olup taraflarca kabul edilerek "
                             f"{v['imza_tarihi']} tarihinde imza altına alınmıştır.", size=21), after=220))

        P.append(_para(_run("Ekleri:", bold=True, size=21), after=40))
        P.append(_para(_run("1) Taşıma Koşulları", size=21), after=40))
        P.append(_para(_run("2) Taşınması yasak olan kargolar ve taşınması şarta bağlı kargolar", size=21), after=280))

        P.append(_imza_bloklari())
        P.append(_page_break())

        P.append(_para(_run("TAŞIMA KOŞULLARI", bold=True, size=26), after=200, align="center"))
        for i, k in enumerate(_SZ_KOSULLAR, 1):
            P.append(_para(_run(f"{i}.  {k}", size=20), after=80, indent=240))
        P.append(_para("", after=100))
        P.append(_para(_run("TAŞIMASI YASAK OLAN KARGOLAR", bold=True, size=24), after=140))
        for i, y in enumerate(_SZ_YASAKLAR, 1):
            P.append(_para(_run(f"{i}.  {y}", size=20), after=80, indent=240))
        P.append(_para("", after=200))
        P.append(_imza_bloklari())

        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body>' + "".join(P) +
            '<w:sectPr><w:pgSz w:w="11907" w:h="16840"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
            '</w:body></w:document>'
        )
        _buf = _szio.BytesIO()
        with _szzip.ZipFile(_buf, "w", _szzip.ZIP_DEFLATED) as _z:
            _z.writestr("[Content_Types].xml", _CONTENT_TYPES)
            _z.writestr("_rels/.rels", _RELS)
            _z.writestr("word/document.xml", document_xml)
            _z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        return _buf.getvalue()

    def _sz_pdf_uret(v):
        """Hiçbir pip paketi gerektirmeden (sadece Python stdlib) PDF üretir.
        Standart PDF Helvetica fontu İ/ı/Ş/ş/Ğ/ğ desteklemediği için bu harfler
        PDF'e özel en yakın Latin harfe çevrilir (Word tarafı tam Türkçe kalır)."""
        import io as _szio2

        _TR_MAP = str.maketrans({
            "İ": "I", "ı": "i", "Ş": "S", "ş": "s", "Ğ": "G", "ğ": "g",
            "\u2192": "->", "\u20ba": "TL", "\u2013": "-", "\u2014": "-",
            "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        })

        def _tr(text): return str(text).translate(_TR_MAP)

        def _pdf_esc(text):
            text = _tr(text).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            return text.encode("cp1252", errors="replace").decode("latin1")

        def _text_w(text, size, bold=False):
            w = 0
            for ch in text:
                if ch == " ": w += 278
                elif ch.isupper(): w += 722
                elif ch in "iIl.,'": w += 260
                else: w += 556
            return w * size / 1000.0 * (1.05 if bold else 1.0)

        def _wrap(text, size, max_w, bold=False):
            words = text.split(" "); lines, cur = [], ""
            for w in words:
                trial = (cur + " " + w).strip()
                if _text_w(trial, size, bold) <= max_w or not cur:
                    cur = trial
                else:
                    lines.append(cur); cur = w
            if cur: lines.append(cur)
            return lines

        class _SimplePDF:
            def __init__(self, pw=595, ph=842, margin=56):
                self.pw, self.ph, self.margin = pw, ph, margin
                self.pages = []; self._new_page()
            def _new_page(self):
                self.pages.append([]); self.y = self.ph - self.margin
            def _ensure(self, need):
                if self.y - need < self.margin: self._new_page()
            def line(self, text, size=10.5, bold=False, gap=13, indent=0, center=False):
                max_w = self.pw - 2*self.margin - indent
                for ln in _wrap(text, size, max_w, bold):
                    self._ensure(gap)
                    font = "/F2" if bold else "/F1"
                    xpos = self.margin + indent
                    if center: xpos = (self.pw - _text_w(ln, size, bold)) / 2
                    esc = _pdf_esc(ln)
                    self.pages[-1].append(f"BT {font} {size} Tf {xpos:.2f} {self.y:.2f} Td ({esc}) Tj ET")
                    self.y -= gap
            def gap(self, n=8): self.y -= n
            def two_col(self, left, right, size=11, bold=True, gap=14):
                self._ensure(gap)
                font = "/F2" if bold else "/F1"
                le, re_ = _pdf_esc(left), _pdf_esc(right)
                self.pages[-1].append(f"BT {font} {size} Tf {self.margin:.2f} {self.y:.2f} Td ({le}) Tj ET")
                rx = self.pw/2 + 20
                self.pages[-1].append(f"BT {font} {size} Tf {rx:.2f} {self.y:.2f} Td ({re_}) Tj ET")
                self.y -= gap
            def page_break(self): self._new_page()
            def output(self):
                objs = []
                objs.append("<< /Type /Catalog /Pages 2 0 R >>")
                kids = " ".join(f"{4+2*i} 0 R" for i in range(len(self.pages)))
                objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(self.pages)} >>")
                objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
                obj_num = 4
                for ops in self.pages:
                    content = "\n".join(ops)
                    content_bytes = content.encode("latin1", errors="replace")
                    objs.append(
                        f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R "
                        f"/F2 {3+2*len(self.pages)+1} 0 R >> >> /MediaBox [0 0 {self.pw} {self.ph}] "
                        f"/Contents {obj_num+1} 0 R >>"
                    )
                    obj_num += 1
                    objs.append(("STREAM", content_bytes))
                    obj_num += 1
                objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
                buf = _szio2.BytesIO()
                buf.write(b"%PDF-1.4\n")
                offsets = [0]
                for idx, o in enumerate(objs, start=1):
                    offsets.append(buf.tell())
                    if isinstance(o, tuple) and o[0] == "STREAM":
                        data = o[1]
                        buf.write(f"{idx} 0 obj\n<< /Length {len(data)} >>\nstream\n".encode("latin1"))
                        buf.write(data)
                        buf.write(b"\nendstream\nendobj\n")
                    else:
                        buf.write(f"{idx} 0 obj\n{o}\nendobj\n".encode("latin1"))
                xref_pos = buf.tell()
                n = len(objs) + 1
                buf.write(f"xref\n0 {n}\n0000000000 65535 f \n".encode("latin1"))
                for off in offsets[1:]:
                    buf.write(f"{off:010d} 00000 n \n".encode("latin1"))
                buf.write(f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode("latin1"))
                return buf.getvalue()

        pdf = _SimplePDF()
        pdf.line("MADDE 1: TARAFLAR", size=14, bold=True, gap=20)
        pdf.line("Taşıyıcı : STF KARGO NAKLİYAT TİCARET LTD.ŞTİ", bold=True)
        pdf.line("Adres : Halkalı Merkez Mah.Dereboyu Caddesi No:56 KÜÇÜKÇEKMECE/İSTANBUL")
        pdf.gap(6)
        pdf.line(f"Taşıtıcı : {v['musteri_uzun']}", bold=True)
        pdf.line(f"Adres : {v['adres'] or '—'}")
        pdf.line(f"V.D: {v['vd'] or '—'}   V.No: {v['vno'] or '—'}")
        pdf.gap(10)
        pdf.line(f"Bir tarafta Stf Kargo Nakliyat ve Ticaret Ltd. Şti. (kısaca STF KARGO olarak anılacaktır.) "
                 f"diğer tarafta {v['musteri_uzun']} (kısaca {v['musteri_kisa']} olarak anılacaktır) arasında "
                 f"akdedilen bu sözleşme tarafların İstanbul geneli yapılacak taşımacılık faaliyetine ilişkin "
                 f"karşılıklı hak ve yükümlülüklerini belirler.")
        pdf.gap(14)
        pdf.line("MADDE 2: GEÇERLİLİK SÜRESİ:", size=12, bold=True, gap=16)
        pdf.line(f"İşbu sözleşme {v['gecerlilik_tarihi']} tarihine kadar geçerlidir. Bitiminde karşılıklı "
                 f"mutabakat ile yenilenir.")
        pdf.line("Taraflardan herhangi biri bir ay önceden yazılı bildirim yapmak koşulu ile veya bu sözleşme "
                 "hükümlerine aykırı hareket edilmesi halinde sözleşme tek taraflı feshedilebilir.")
        pdf.gap(14)
        pdf.line("MADDE 3: UYGULANACAK FİYAT TARİFESİ:", size=12, bold=True, gap=16)
        pdf.line(f"Geçerlilik süresi içerisinde STF KARGO {v['musteri_kisa']}'nin aşağıdaki tabloda belirtilen "
                 f"ebattaki kargolarını yazılı fiyatlarla taşımayı kabul eder.")
        if v["fiyat_gruplari"]:
            for grp in v["fiyat_gruplari"]:
                pdf.line(grp["baslik"], bold=True, gap=16)
                for s in grp["satirlar"]:
                    pdf.line("• " + s, size=10, indent=20)
                pdf.gap(6)
        else:
            pdf.line("(Bu müşteri için tanımlı fiyat bulunamadı.)", size=10)
        pdf.gap(6)
        pdf.line("Taşıma fiyatlarında KDV ayrıca eklenecektir.", bold=True)
        pdf.gap(14)
        pdf.line("MADDE 4: ÖDEME ŞEKLİ VE ZAMANI", size=12, bold=True, gap=16)
        pdf.line(f"{v['musteri_kisa']} kendisine gelen ürünlere ait ücret alıcı faturalar ile gönderdiği "
                 f"ürünlere ait ücret gönderen faturaları tarihlerinden itibaren {v['vade']} eft-havale olarak öder.")
        pdf.gap(14)
        pdf.line("MADDE 5: YAKIT KLOZU", size=12, bold=True, gap=16)
        pdf.line("Ay sonunda oluşan yakıt artış farkı %50 oranında fiyatlara yansıtılır")
        pdf.gap(14)
        pdf.line("MADDE 6: HİZMET ŞUBESİ ve YETKİLİSİ: İstanbul-Merkez Şubesi: Koray Ertaş", size=12, bold=True, gap=16)
        pdf.line("0 212 671 50 35-36 / 0 212 671 96 51-444 77 83 · koray.ertas@stflojistik.com")
        pdf.gap(14)
        pdf.line("MADDE 7: TAŞIMA KOŞULLARI:", size=12, bold=True, gap=16)
        pdf.line("Genel taşıma koşulları ekte 14 madde halinde açıklanmış olup tarafları tamamen bağlayıcı "
                 "nitelik taşır.")
        pdf.gap(14)
        pdf.line("MADDE 8:", size=12, bold=True, gap=16)
        pdf.line(f"İşbu taşıma sözleşmesi toplam sekiz maddeden ibaret olup taraflarca kabul edilerek "
                 f"{v['imza_tarihi']} tarihinde imza altına alınmıştır.")
        pdf.gap(26)
        pdf.two_col("STF KARGO NAKLİYAT VE TİCARET LTD. ŞTİ.", v["musteri_kisa"], bold=True)
        pdf.two_col("KAŞE-İMZA", "KAŞE-İMZA", bold=False)
        pdf.two_col("", v["musteri_uzun"], bold=False, size=9)

        pdf.page_break()
        pdf.line("TAŞIMA KOŞULLARI", size=14, bold=True, gap=20, center=True)
        for i, k in enumerate(_SZ_KOSULLAR, 1):
            pdf.line(f"{i}. {k}", size=10, gap=13, indent=14)
        pdf.gap(10)
        pdf.line("TAŞIMASI YASAK OLAN KARGOLAR", size=12, bold=True, gap=16)
        for i, y in enumerate(_SZ_YASAKLAR, 1):
            pdf.line(f"{i}. {y}", size=10, gap=13, indent=14)
        pdf.gap(20)
        pdf.two_col("STF KARGO NAKLİYAT VE TİCARET LTD. ŞTİ.", v["musteri_kisa"], bold=True)
        pdf.two_col("KAŞE-İMZA", "KAŞE-İMZA", bold=False)
        pdf.two_col("", v["musteri_uzun"], bold=False, size=9)

        return pdf.output()


    # ══════════════════════════════════════════════════════════════════════
    # SEKMELER
    # ══════════════════════════════════════════════════════════════════════
    _sz_tab1, _sz_tab2 = st.tabs(["📝 Yeni Sözleşme", "📚 Geçmiş Sözleşmeler"])

    with _sz_tab1:
        _sz_dfm = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")
        _sz_opts = ["-- Müşteri Seçin --"] + [f"[{int(r['id'])}] {r['firma']}" for _, r in _sz_dfm.iterrows()] if not _sz_dfm.empty else ["-- Müşteri Seçin --"]

        _sz_onsel = st.session_state.pop("sozlesme_musteri_onsel", None)
        _sz_index = 0
        if _sz_onsel:
            for _i, _o in enumerate(_sz_opts):
                if _o.endswith(f"] {_sz_onsel}"):
                    _sz_index = _i; break

        _sz_sec = st.selectbox("Müşteri Seç", _sz_opts, index=_sz_index, key="sz_musteri_sec")

        _sz_mus = None; _sz_id = None
        if _sz_sec != "-- Müşteri Seçin --" and "[" in _sz_sec:
            try:
                _sz_id = int(_sz_sec.split("]")[0].replace("[","").strip())
                _mr = _sz_dfm[_sz_dfm["id"] == _sz_id]
                if not _mr.empty:
                    _sz_mus = _mr.iloc[0]
            except Exception:
                pass

        if _sz_mus is None:
            st.info("Sözleşme hazırlamak için önce bir müşteri seçin.")
        else:
            _sz_uzun = str(_sz_mus.get("firma",""))
            _sz_adres_oto = str(_sz_mus.get("adres","") or "")
            _sz_kisa_tahmin = " ".join(_sz_uzun.split()[:2]).upper()

            st.markdown(f"### 📄 {_sz_uzun}")

            _szc1, _szc2 = st.columns(2)
            _sz_kisa = _szc1.text_input("Kısa Ad (sözleşme metninde kullanılacak)", value=_sz_kisa_tahmin, key="sz_kisa")
            _sz_adres = _szc2.text_input("Adres", value=_sz_adres_oto, key="sz_adres")

            st.caption("Vergi Dairesi / Vergi No — yoksa boş bırakıp geçebilirsiniz")
            _szv1, _szv2, _szv3 = st.columns([1.5, 1.5, 1])
            _sz_vd = _szv1.text_input("V.D", key="sz_vd", placeholder="Vergi Dairesi...")
            _sz_vno = _szv2.text_input("V.No", key="sz_vno", placeholder="Vergi No...")
            _sz_gec = _szv3.checkbox("Geç (V.D/V.No girme)", key="sz_gec")

            st.markdown("---")
            st.markdown("**MADDE 2 — Geçerlilik Tarihi** 🔴 *(zorunlu)*")
            _sz_gecerlilik = st.date_input("Sözleşme Geçerlilik Tarihi", value=_szdate.today().replace(year=_szdate.today().year+1),
                                            key="sz_gecerlilik", format="DD/MM/YYYY")

            st.markdown("**MADDE 3 — Fiyat Tarifesi** (son Özel Teklif'ten otomatik çekilir)")
            _sz_teklif_df = pd.DataFrame()
            try:
                _sz_tekliflerdf = _teklifler_tarih_normalize(_teklifler_oku())
                if not _sz_tekliflerdf.empty and "satirlar" in _sz_tekliflerdf.columns:
                    _sz_ozel = _sz_tekliflerdf[_sz_tekliflerdf["satirlar"].str.contains("ozel", case=False, na=False)]
                    _sz_teklif_df = _sz_ozel[_sz_ozel["musteri_adi"].astype(str).str.strip().str.upper() == _sz_uzun.strip().upper()]
            except Exception:
                pass

            _sz_fiyat_gruplari = []
            if not _sz_teklif_df.empty:
                _sz_teklif_df = _sz_teklif_df.sort_values("tarih", ascending=False)
                _sz_son_teklif = _sz_teklif_df.iloc[0]
                _sz_fiyat_gruplari = _sz_fiyat_grupla(_sz_son_teklif.get("satirlar", "{}"))
                st.success(f"✅ {fmt_tarih(_sz_son_teklif.get('tarih',''))} tarihli Özel Teklif'ten {len(_sz_fiyat_gruplari)} fiyat grubu bulundu.")
                with st.expander("Fiyat tablosunu önizle", expanded=False):
                    for _g in _sz_fiyat_gruplari:
                        st.markdown(f"**{_g['baslik']}**")
                        for _s in _g["satirlar"]:
                            st.caption("• " + _s)
            else:
                st.warning("⚠️ Bu müşteri için Özel Teklif bulunamadı. MADDE 3 fiyat tablosu boş oluşturulacak — "
                           "önce '⭐ Özel Teklif' sayfasından fiyat oluşturmanız önerilir.")
                if st.button(f"⭐ {_sz_uzun} için Özel Teklif Oluştur", key="sz_teklife_git", use_container_width=True):
                    st.session_state["aktif_tab"] = "ozel_teklif"
                    st.session_state["teklif_musteri_onsel"] = _sz_uzun
                    st.rerun()

            st.markdown("---")
            st.markdown("**MADDE 4 — Vade** 🔴 *(zorunlu)*")
            _sz_vade = st.text_input("Ödeme Vadesi (örn: 45 GÜN)", key="sz_vade", placeholder="Örn: 45 GÜN")

            st.markdown("**MADDE 8 — Sözleşme İmza Tarihi**")
            _sz_imza_tarihi = st.date_input("İmza Tarihi (varsayılan bugün)", value=_szdate.today(),
                                             key="sz_imza_tarihi", format="DD/MM/YYYY")

            st.markdown("---")
            if st.button("📜 Sözleşme Oluştur", type="primary", use_container_width=True, key="sz_olustur"):
                _sz_hata = []
                if not _sz_gecerlilik:
                    _sz_hata.append("Geçerlilik tarihi seçilmedi (MADDE 2 zorunlu).")
                if not _sz_vade or not _sz_vade.strip():
                    _sz_hata.append("Vade girilmedi (MADDE 4 zorunlu).")
                if not _sz_gec and (not _sz_vd.strip() and not _sz_vno.strip()):
                    st.info("ℹ️ V.D/V.No girilmedi ve 'Geç' işaretlenmedi — sözleşmede boş (—) olarak görünecek.")

                if _sz_hata:
                    for _h in _sz_hata:
                        st.error(f"❌ {_h}")
                else:
                    _sz_veri = {
                        "musteri_uzun": _sz_uzun,
                        "musteri_kisa": _sz_kisa.strip() or _sz_kisa_tahmin,
                        "adres": _sz_adres,
                        "vd": _sz_vd.strip(),
                        "vno": _sz_vno.strip(),
                        "gecerlilik_tarihi": _sz_gecerlilik.strftime("%d/%m/%Y"),
                        "vade": _sz_vade.strip() if "gün" in _sz_vade.strip().lower() else f"{_sz_vade.strip()} GÜN",
                        "imza_tarihi": _sz_imza_tarihi.strftime("%d/%m/%Y"),
                        "fiyat_gruplari": _sz_fiyat_gruplari,
                    }
                    try:
                        _sz_docx_bytes = _sz_docx_uret(_sz_veri)
                        _sz_pdf_bytes = _sz_pdf_uret(_sz_veri)

                        # Arşivle — YENİ TABLO GEREKMEZ, var olan "teklifler" tablosunu kullanıyoruz
                        # (Özel Teklif'in "tip":"ozel" işaretlemesiyle aynı mantık, "tip":"sozlesme" ile ayırt edilir)
                        _sz_sb = get_sb_client()
                        if _sz_sb:
                            _sz_sb.table("teklifler").insert({
                                "musteri_id": _sz_id or 0,
                                "musteri_adi": _sz_uzun,
                                "satirlar": _szj.dumps({"tip": "sozlesme", "veri": _sz_veri}, ensure_ascii=False),
                                "toplam_tutar": 0,
                                "olusturan": st.session_state.get("kullanici",""),
                                "notlar": f"Sözleşme · Vade:{_sz_veri['vade']} · Geçerlilik:{_sz_veri['gecerlilik_tarihi']} · İmza:{_sz_veri['imza_tarihi']}",
                            }).execute()
                            st.toast("✅ Sözleşme arşivlendi!", icon="✅")

                        st.success(f"✅ {_sz_uzun} için sözleşme oluşturuldu ve arşivlendi!")
                        _szd1, _szd2 = st.columns(2)
                        _szd1.download_button("⬇️ Word (.docx) indir", data=_sz_docx_bytes,
                            file_name=f"Sozlesme_{_sz_kisa.strip() or _sz_kisa_tahmin}_{_sz_imza_tarihi.strftime('%Y%m%d')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True, key="sz_dl_docx")
                        if _sz_pdf_bytes:
                            _szd2.download_button("⬇️ PDF indir", data=_sz_pdf_bytes,
                                file_name=f"Sozlesme_{_sz_kisa.strip() or _sz_kisa_tahmin}_{_sz_imza_tarihi.strftime('%Y%m%d')}.pdf",
                                mime="application/pdf", use_container_width=True, key="sz_dl_pdf")
                        else:
                            _szd2.warning("PDF için fonts/DejaVuSans.ttf bulunamadı — repo'ya eklenmesi gerekiyor.")
                    except Exception as _sz_e:
                        st.error(f"⚠️ Sözleşme oluşturulamadı: {_sz_e}")

    with _sz_tab2:
        st.markdown("### 📚 Geçmiş Sözleşmeler")
        try:
            _sz_sb2 = get_sb_client()
            _sz_ham = pd.DataFrame(_sz_sb2.table("teklifler").select("*").order("id", desc=True).execute().data) if _sz_sb2 else pd.DataFrame()
            if not _sz_ham.empty and "satirlar" in _sz_ham.columns:
                _sz_arsiv_ham = _sz_ham[_sz_ham["satirlar"].astype(str).str.contains("sozlesme", case=False, na=False)].copy()
            else:
                _sz_arsiv_ham = pd.DataFrame()
        except Exception:
            _sz_arsiv_ham = pd.DataFrame()

        # Ham satırları sözleşme veri sözlüğüne çeviriyoruz
        _sz_arsiv_liste = []
        for _, _ar in _sz_arsiv_ham.iterrows():
            try:
                _parsed = _szj.loads(_ar.get("satirlar", "{}"))
                if _parsed.get("tip") != "sozlesme":
                    continue
                _vv = _parsed.get("veri", {})
                _vv["id"] = _ar.get("id")
                _vv["olusturan"] = _ar.get("olusturan", "")
                _sz_arsiv_liste.append(_vv)
            except Exception:
                continue

        if not _sz_arsiv_liste:
            st.info("Henüz sözleşme arşivlenmemiş.")
        else:
            _sz_ara = st.text_input("🔍 Müşteri ara", key="sz_arsiv_ara")
            if _sz_ara:
                _sz_arsiv_liste = [x for x in _sz_arsiv_liste if _sz_ara.lower() in str(x.get("musteri_uzun","")).lower()]
            for _sa in _sz_arsiv_liste:
                with st.container(border=True):
                    _sac1, _sac2, _sac3 = st.columns([2.5, 1.3, 1.3])
                    _sac1.markdown(f"**{_sa.get('musteri_uzun','')}**")
                    _sac1.caption(f"Vade: {_sa.get('vade','—')} · Geçerlilik: {_sa.get('gecerlilik_tarihi','—')}")
                    _sac2.caption(f"📅 İmza: {_sa.get('imza_tarihi','—')}")
                    _sac3.caption(f"👤 {_sa.get('olusturan','')}")
                    if st.button("📥 Yeniden indir", key=f"sz_yeniden_{int(_sa['id'])}"):
                        try:
                            _dbytes = _sz_docx_uret(_sa)
                            st.download_button("⬇️ Word indir", data=_dbytes,
                                file_name=f"Sozlesme_{_sa.get('musteri_kisa','')}_{_sa.get('imza_tarihi','').replace('/','')}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key=f"sz_yeniden_dl_{int(_sa['id'])}")
                        except Exception as _sz_e2:
                            st.error(f"Hata: {_sz_e2}")


elif aktif == "excel":
    sayfa_log("excel")
    import io

    st.markdown("## 📥 Excel ile Toplu Veri Aktarımı")

    sablon_kolonlar = ["firma","yetkili","gsm","sabit","email","adres","ilce","il","durum","temsilci","islem_asamasi","beklenen_ciro","gerceklesen_ciro"]

    sablon_buf = io.BytesIO()
    pd.DataFrame(columns=sablon_kolonlar).to_excel(sablon_buf, index=False)
    sablon_buf.seek(0)
    st.download_button("📥 Şablonu İndir", data=sablon_buf, file_name="cari_sablon.xlsx", key="dl_sablon")

    st.divider()

    yukl_dosya = st.file_uploader("Excel dosyası yükle", type=["xlsx","xls"], key="excel_yukle")

    if yukl_dosya is not None:
        df_yukl = pd.read_excel(yukl_dosya)
        df_yukl.columns = [str(c).strip().lower().replace(" ","_") for c in df_yukl.columns]
    else:
        df_yukl = None

    if df_yukl is not None:

        # Hedef/Gerçek ciro sütunları farklı isimlerle gelebilir — hepsini "beklenen_ciro" /
        # "gerceklesen_ciro" olarak tanı, ilk eşleşen sütunu kullan (sessizce 0 atmasın diye).
        _hedef_takma_adlar = ["beklenen_ciro","hedef","hedef_ciro","hedef_₺","hedefciro",
                               "hedef_tl","target","hedef_tutar"]
        _gercek_takma_adlar = ["gerceklesen_ciro","gerçekleşen_ciro","gerçek","gercek",
                                "gerçek_ciro","gercek_ciro","gerçek_₺","gerceklesen"]
        for _hedef_ad in _hedef_takma_adlar:
            if _hedef_ad in df_yukl.columns:
                if _hedef_ad != "beklenen_ciro":
                    df_yukl["beklenen_ciro"] = df_yukl[_hedef_ad]
                break
        for _gercek_ad in _gercek_takma_adlar:
            if _gercek_ad in df_yukl.columns:
                if _gercek_ad != "gerceklesen_ciro":
                    df_yukl["gerceklesen_ciro"] = df_yukl[_gercek_ad]
                break

        if "firma" not in df_yukl.columns:
            st.error("❌ Zorunlu sütun eksik: firma")
        else:
            if "beklenen_ciro" not in df_yukl.columns:
                st.warning("⚠️ Hedef ciro sütunu bulunamadı — dosyanızdaki sütun başlığını "
                           f"şunlardan biri yapın: {', '.join(_hedef_takma_adlar)}. "
                           "Bulunamazsa tüm satırlar 0 ₺ hedef ile eklenir.")
            st.success(f"{len(df_yukl)} satır okundu.")

            def _ex_temiz_str(v):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return ""
                return str(v)

            def _ex_temiz_tel(v):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return ""
                s = str(v).strip()
                if s.endswith(".0"):
                    s = s[:-2]
                return s

            def _ex_temiz_float(v):
                try:
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        return 0.0
                    return float(v)
                except:
                    return 0.0

            # ── ID ALMADAN ÖNCE MÜKERRER TESPİTİ ──────────────────────────────
            # Her müşterinin ID'si kalıcıdır, asla değişmez — bu yüzden sisteme
            # ID vererek eklemeden önce, firma adı VEYA telefon numarası
            # hâlihazırda var mı diye bakılır (ikisinden biri eşleşirse şüpheli
            # mükerrer sayılır, onaylanmadan sisteme eklenmez).
            _ex_mevcut_df = get_cari_listesi()
            _ex_mevcut_isimler = {}
            _ex_mevcut_telefonlar = {}

            def _ex_tel_norm(_v):
                _s = str(_v or "").strip()
                _s = "".join(ch for ch in _s if ch.isdigit())
                if _s.endswith(".0"):  # ihtimale karşı, zaten yukarıda digit filtrelendi ama garanti olsun
                    _s = _s[:-2]
                # Baştaki 0/90 farklarını yok say — son 10 haneyi karşılaştır
                return _s[-10:] if len(_s) >= 10 else _s

            if not _ex_mevcut_df.empty and "firma" in _ex_mevcut_df.columns:
                for _, _mr in _ex_mevcut_df.iterrows():
                    _ex_ad = str(_mr.get("firma","")).strip().upper()
                    if _ex_ad:
                        _ex_mevcut_isimler.setdefault(_ex_ad, []).append(_mr.to_dict())
                    for _tel_kol in ["gsm", "sabit"]:
                        _ex_tel_n = _ex_tel_norm(_mr.get(_tel_kol, ""))
                        if _ex_tel_n:
                            _ex_mevcut_telefonlar.setdefault(_ex_tel_n, []).append(_mr.to_dict())

            _ex_temiz_kayitlar = []
            _ex_taslak_kayitlar = []
            _ex_dosya_icinde_gorulen = set()
            _ex_dosya_icinde_telefon = set()

            for _ei, _row in df_yukl.iterrows():
                _ex_firma = str(_row.get("firma","") or "").strip()
                if not _ex_firma:
                    continue
                _ex_kayit = {
                    "firma": _ex_firma,
                    "yetkili": _ex_temiz_str(_row.get("yetkili","")),
                    "gsm": _ex_temiz_tel(_row.get("gsm","")),
                    "sabit": _ex_temiz_tel(_row.get("sabit","")),
                    "email": _ex_temiz_str(_row.get("email","")),
                    "adres": _ex_temiz_str(_row.get("adres","")),
                    "ilce": _ex_temiz_str(_row.get("ilce","")),
                    "il": _ex_temiz_str(_row.get("il","")),
                    "durum": _ex_temiz_str(_row.get("durum","Hedef")) or "Hedef",
                    "temsilci": _ex_temiz_str(_row.get("temsilci","")),
                    "islem_asamasi": _ex_temiz_str(_row.get("islem_asamasi","")) or "",
                    "beklenen_ciro": _ex_temiz_float(_row.get("beklenen_ciro",0)),
                    "gerceklesen_ciro": _ex_temiz_float(_row.get("gerceklesen_ciro",0)),
                    "olusturan": st.session_state.get("kullanici",""),
                    "silindi": 0,
                }
                _ex_ad_norm = _ex_firma.upper()
                _ex_gsm_norm = _ex_tel_norm(_ex_kayit["gsm"])
                _ex_sabit_norm = _ex_tel_norm(_ex_kayit["sabit"])

                if _ex_ad_norm in _ex_mevcut_isimler:
                    _ex_taslak_kayitlar.append({**_ex_kayit, "_sebep": "Firma adı sistemde zaten var",
                                                 "_eslesen": _ex_mevcut_isimler[_ex_ad_norm]})
                elif _ex_gsm_norm and _ex_gsm_norm in _ex_mevcut_telefonlar:
                    _ex_taslak_kayitlar.append({**_ex_kayit, "_sebep": "Telefon (GSM) numarası sistemde başka bir firmada kayıtlı",
                                                 "_eslesen": _ex_mevcut_telefonlar[_ex_gsm_norm]})
                elif _ex_sabit_norm and _ex_sabit_norm in _ex_mevcut_telefonlar:
                    _ex_taslak_kayitlar.append({**_ex_kayit, "_sebep": "Sabit telefon numarası sistemde başka bir firmada kayıtlı",
                                                 "_eslesen": _ex_mevcut_telefonlar[_ex_sabit_norm]})
                elif _ex_ad_norm in _ex_dosya_icinde_gorulen:
                    _ex_taslak_kayitlar.append({**_ex_kayit, "_sebep": "Excel dosyasında tekrar ediyor",
                                                 "_eslesen": []})
                elif _ex_gsm_norm and _ex_gsm_norm in _ex_dosya_icinde_telefon:
                    _ex_taslak_kayitlar.append({**_ex_kayit, "_sebep": "Excel dosyasında aynı telefon başka satırda da var",
                                                 "_eslesen": []})
                else:
                    _ex_dosya_icinde_gorulen.add(_ex_ad_norm)
                    if _ex_gsm_norm: _ex_dosya_icinde_telefon.add(_ex_gsm_norm)
                    _ex_temiz_kayitlar.append(_ex_kayit)

            _ex_c1, _ex_c2 = st.columns(2)
            _ex_c1.metric("✅ Temiz (yeni) kayıt", len(_ex_temiz_kayitlar))
            _ex_c2.metric("⚠️ Şüpheli mükerrer (taslakta bekliyor)", len(_ex_taslak_kayitlar))

            if st.button("✅ Temiz Olanları Sisteme Aktar", type="primary", key="excel_aktar_btn_v2"):
                sb = get_sb_client()
                if not sb:
                    st.error("Supabase bağlantısı yok!")
                elif not _ex_temiz_kayitlar:
                    st.info("Aktarılacak temiz (yeni) kayıt yok.")
                else:
                    kayitlar = _ex_temiz_kayitlar

                    toplam = len(kayitlar)
                    basarili = 0
                    hatalar = []
                    BATCH = 25
                    bar = st.progress(0)
                    durum_text = st.empty()

                    for i in range(0, toplam, BATCH):
                        parca = kayitlar[i:i+BATCH]
                        try:
                            sb.table("cari_kartlar").insert(parca).execute()
                            basarili += len(parca)
                        except Exception as e:
                            hatalar.append(f"Satır {i+1}-{i+len(parca)}: {e}")
                        bar.progress(min((i+BATCH)/toplam, 1.0))
                        durum_text.text(f"{min(i+BATCH,toplam)}/{toplam} işlendi, {basarili} eklendi")

                    st.success(f"🎉 Tamamlandı! {basarili}/{toplam} kayıt eklendi.")
                    if hatalar:
                        st.error(f"❌ {len(hatalar)} grup hata verdi:")
                        for h in hatalar:
                            st.code(h)

            # ── TASLAK: Şüpheli Mükerrer Kayıtlar — henüz sisteme ID almadılar ──
            if "_ex_tas_gecilen" not in st.session_state:
                st.session_state["_ex_tas_gecilen"] = set()
            _ex_taslak_kayitlar = [tk for _ti0, tk in enumerate(_ex_taslak_kayitlar)
                                    if f"{tk['firma']}_{_ti0}" not in st.session_state["_ex_tas_gecilen"]]
            if _ex_taslak_kayitlar:
                st.divider()
                st.warning(f"⚠️ {len(_ex_taslak_kayitlar)} kayıt taslakta bekliyor — bunlara henüz ID verilmedi, sisteme eklenmedi. "
                           "Aşağıda mevcut kayıtla karşılaştırıp siz karar verin: aynen ekleyin, düzenleyip ekleyin, ya da vazgeçin.")

                # ── Şüpheli mükerrer karşılaştırma listesini Excel olarak indir ──
                _ex_indir_satirlar = []
                for _tk_i in _ex_taslak_kayitlar:
                    _es_i = _tk_i["_eslesen"][0] if _tk_i["_eslesen"] else {}
                    _ex_indir_satirlar.append({
                        "Sebep": _tk_i.get("_sebep", ""),
                        "Excel - Firma": _tk_i.get("firma", ""),
                        "Excel - Yetkili": _tk_i.get("yetkili", ""),
                        "Excel - GSM": _tk_i.get("gsm", ""),
                        "Excel - Sabit": _tk_i.get("sabit", ""),
                        "Excel - İl": _tk_i.get("il", ""),
                        "Excel - İlçe": _tk_i.get("ilce", ""),
                        "Excel - Hedef Ciro": _tk_i.get("beklenen_ciro", 0),
                        "Sistem - ID": _es_i.get("id", ""),
                        "Sistem - Firma": _es_i.get("firma", ""),
                        "Sistem - Yetkili": _es_i.get("yetkili", ""),
                        "Sistem - GSM": _es_i.get("gsm", ""),
                        "Sistem - Sabit": _es_i.get("sabit", ""),
                        "Sistem - İl": _es_i.get("il", ""),
                        "Sistem - İlçe": _es_i.get("ilce", ""),
                        "Sistem - Hedef Ciro": _es_i.get("beklenen_ciro", 0),
                    })
                _ex_indir_buf = io.BytesIO()
                pd.DataFrame(_ex_indir_satirlar).to_excel(_ex_indir_buf, index=False, engine="openpyxl")
                _ex_indir_buf.seek(0)
                st.download_button("📥 Şüpheli Mükerrer Listesini Excel Olarak İndir", data=_ex_indir_buf,
                                    file_name=f"mukerrer_karsilastirma_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key="ex_tas_excel_indir")

                with st.expander(f"🔍 Taslaktaki {len(_ex_taslak_kayitlar)} şüpheli kaydı incele", expanded=True):
                    for _ti, _tk in enumerate(_ex_taslak_kayitlar):
                        _ex_tas_anahtar = f"{_tk['firma']}_{_ti}"
                        st.markdown(f"**{_tk['firma']}** — *{_tk['_sebep']}*")
                        _tc1, _tc2 = st.columns(2)
                        with _tc1:
                            st.caption("📄 Excel'den gelen (henüz ID yok)")
                            st.text(f"Yetkili: {_tk.get('yetkili','—')}\n"
                                    f"GSM: {_tk.get('gsm','—')}\n"
                                    f"İl/İlçe: {_tk.get('il','—')} / {_tk.get('ilce','—')}\n"
                                    f"Hedef ciro: {_tk.get('beklenen_ciro',0):,.0f} ₺")
                        with _tc2:
                            if _tk["_eslesen"]:
                                _es = _tk["_eslesen"][0]
                                st.caption(f"💾 Sistemde kayıtlı (id {_es.get('id')})")
                                st.text(f"Yetkili: {_es.get('yetkili') or '—'}\n"
                                        f"GSM: {_es.get('gsm') or '—'}\n"
                                        f"İl/İlçe: {_es.get('il') or '—'} / {_es.get('ilce') or '—'}\n"
                                        f"Hedef ciro: {float(_es.get('beklenen_ciro') or 0):,.0f} ₺")
                            else:
                                st.caption("💾 Excel dosyasının kendi içinde tekrar ediyor")

                        _ex_duzenle_flag_key = f"_ex_tas_duzenle_acik_{_ex_tas_anahtar}"
                        _tb1, _tb2, _tb3 = st.columns(3)
                        with _tb1:
                            if st.button("✅ Aynen Ekle", key=f"ex_tas_ekle_{_ex_tas_anahtar}", use_container_width=True):
                                _sb_tas = get_sb_client()
                                if _sb_tas:
                                    try:
                                        _tk_temiz = {k: v for k, v in _tk.items() if not k.startswith("_")}
                                        _sb_tas.table("cari_kartlar").insert(_tk_temiz).execute()
                                        try: get_cari_listesi.clear()
                                        except: pass
                                        st.toast(f"✅ '{_tk['firma']}' yeni kayıt olarak eklendi (yeni ID verildi)", icon="✅")
                                        st.rerun()
                                    except Exception as _tase:
                                        st.error(f"Hata: {_tase}")
                        with _tb2:
                            if st.button("✏️ Düzenle", key=f"ex_tas_duzenle_btn_{_ex_tas_anahtar}", use_container_width=True):
                                st.session_state[_ex_duzenle_flag_key] = not st.session_state.get(_ex_duzenle_flag_key, False)
                                st.rerun()
                        with _tb3:
                            if st.button("❌ Vazgeç (atla)", key=f"ex_tas_vazgec_{_ex_tas_anahtar}", use_container_width=True):
                                st.session_state["_ex_tas_gecilen"].add(_ex_tas_anahtar)
                                st.toast(f"❌ '{_tk['firma']}' atlandı — bir daha bu incelemede görünmeyecek", icon="❌")
                                st.rerun()

                        if st.session_state.get(_ex_duzenle_flag_key, False):
                            with st.form(key=f"ex_tas_duzenle_form_{_ex_tas_anahtar}"):
                                st.caption("Kaydetmeden önce alanları düzenleyebilirsin:")
                                _dc1, _dc2 = st.columns(2)
                                _dz_firma = _dc1.text_input("Firma", value=_tk.get("firma",""))
                                _dz_yetkili = _dc2.text_input("Yetkili", value=_tk.get("yetkili",""))
                                _dz_gsm = _dc1.text_input("GSM", value=_tk.get("gsm",""))
                                _dz_sabit = _dc2.text_input("Sabit", value=_tk.get("sabit",""))
                                _dz_email = _dc1.text_input("Email", value=_tk.get("email",""))
                                _dz_adres = _dc2.text_input("Adres", value=_tk.get("adres",""))
                                _dz_il = _dc1.text_input("İl", value=_tk.get("il",""))
                                _dz_ilce = _dc2.text_input("İlçe", value=_tk.get("ilce",""))
                                _dz_hedef = _dc1.number_input("Hedef ciro", value=float(_tk.get("beklenen_ciro",0) or 0))
                                if st.form_submit_button("💾 Düzenlediğimi Kaydet ve Ekle", type="primary"):
                                    _sb_tas2 = get_sb_client()
                                    if _sb_tas2:
                                        try:
                                            _tk_duzenlenmis = {k: v for k, v in _tk.items() if not k.startswith("_")}
                                            _tk_duzenlenmis.update({
                                                "firma": _dz_firma, "yetkili": _dz_yetkili, "gsm": _dz_gsm,
                                                "sabit": _dz_sabit, "email": _dz_email, "adres": _dz_adres,
                                                "il": _dz_il, "ilce": _dz_ilce, "beklenen_ciro": _dz_hedef,
                                            })
                                            _sb_tas2.table("cari_kartlar").insert(_tk_duzenlenmis).execute()
                                            try: get_cari_listesi.clear()
                                            except: pass
                                            st.session_state["_ex_tas_gecilen"].add(_ex_tas_anahtar)
                                            st.toast(f"✅ '{_dz_firma}' düzenlenmiş haliyle eklendi (yeni ID verildi)", icon="✅")
                                            st.rerun()
                                        except Exception as _tase2:
                                            st.error(f"Hata: {_tase2}")
                        else:
                            st.caption("Hiçbir şey yapmazsanız bu kayıt sisteme eklenmez, taslakta kalır.")
                        st.markdown("---")


elif aktif == "whatsapp":
    import requests as _wa_req

    st.markdown("## 💬 WhatsApp Entegrasyonu")

    # ── BAĞLANTI AYARLARI ──────────────────────────────────────────────────────
    with st.expander("📡 Waha Bağlantı Ayarları"):
        waha_url = st.text_input("Waha URL:", value=st.session_state.get("waha_url","http://localhost:3000"), key="waha_url_input")
        waha_session = st.text_input("Session:", value=st.session_state.get("waha_session","default"), key="waha_session_input")
        if st.button("💾 Kaydet", key="waha_kaydet"):
            st.session_state["waha_url"] = waha_url
            st.session_state["waha_session"] = waha_session
            st.success("Kaydedildi!")

    WAHA_URL = st.session_state.get("waha_url", "http://localhost:3000")
    WAHA_SESSION = st.session_state.get("waha_session", "default")

    def waha_get(endpoint):
        try:
            r = _wa_req.get(f"{WAHA_URL}{endpoint}", timeout=5)
            return r.json()
        except:
            return None

    def waha_post(endpoint, data):
        try:
            r = _wa_req.post(f"{WAHA_URL}{endpoint}", json=data, timeout=10)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def wa_numara_formatla(numara):
        n = re.sub(r"[\s\-\(\)\+]", "", str(numara or ""))
        if n.startswith("0") and len(n) == 11:
            n = "90" + n[1:]
        elif n.startswith("9") and len(n) == 12:
            pass
        elif len(n) == 10:
            n = "90" + n
        return n + "@c.us" if n else ""

    # ── BAĞLANTI DURUMU ────────────────────────────────────────────────────────
    st.markdown("### 📡 Bağlantı Durumu")
    durum_col, qr_col = st.columns([1, 1])

    with durum_col:
        durum_data = waha_get(f"/api/sessions/{WAHA_SESSION}")
        if durum_data is None:
            st.error("❌ Waha'ya bağlanılamıyor. Docker çalışıyor mu?")
            st.code("docker run -it -p 3000:3000/tcp devlikeapro/waha", language="bash")
            st.info("Yukarıdaki komutu terminale yapıştırın, Docker Desktop açık olsun.")
        else:
            status = durum_data.get("status","UNKNOWN")
            if status == "WORKING":
                st.success(f"✅ Bağlı — {WAHA_SESSION}")
                me = waha_get(f"/api/sessions/{WAHA_SESSION}/me")
                if me:
                    st.info(f"📱 {me.get('pushName','')} — {me.get('id','').replace('@c.us','')}")
            elif status == "SCAN_QR_CODE":
                st.warning("📷 QR Okutun")
            else:
                st.warning(f"⏳ Durum: {status}")

    with qr_col:
        if st.button("🔄 QR Yenile / Bağlan", use_container_width=True):
            # Session başlat
            waha_post(f"/api/sessions/{WAHA_SESSION}/start", {})
            st.rerun()
        qr_data = waha_get(f"/api/sessions/{WAHA_SESSION}/screenshot")
        if qr_data and "data" in str(qr_data):
            st.image(f"data:image/png;base64,{qr_data.get('data','')}", width=200)

    st.divider()

    # ── TABS ──────────────────────────────────────────────────────────────────
    wa_tab1, wa_tab2, wa_tab3, wa_tab4 = st.tabs(["📤 Mesaj Gönder", "👥 Toplu Gönder", "💬 Görüşme Kaydet", "📋 Geçmiş"])

    # ── TEK MESAJ ─────────────────────────────────────────────────────────────
    with wa_tab1:
        st.markdown("### 📤 Tek Mesaj Gönder")

        df_wa = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) AND gsm != '' ORDER BY firma")

        wa_yontem = st.radio("Alıcı:", ["Sistemden Seç", "Manuel Numara"], horizontal=True, key="wa_yontem")

        wa_numara = ""
        wa_firma = ""

        if wa_yontem == "Sistemden Seç":
            musteri_opts_wa = ["-- Seçin --"] + [f"[{int(r['id'])}] {r['firma']} — {r['gsm']}" for _, r in df_wa.iterrows()]
            wa_secim = st.selectbox("Müşteri:", musteri_opts_wa, key="wa_musteri_sec")
            if wa_secim != "-- Seçin --":
                wa_mid = int(wa_secim.split("]")[0].replace("[","").strip())
                _wam = df_wa[df_wa["id"] == wa_mid]
                if _wam.empty: raise Exception("WA bulunamadı")
                wa_row = _wam.iloc[0]
                wa_numara = wa_numara_formatla(wa_row["gsm"])
                wa_firma = str(wa_row["firma"])
                st.info(f"📱 {wa_numara} — {wa_firma}")
        else:
            manuel_no = st.text_input("Telefon No:", placeholder="05xxxxxxxxx", key="wa_manuel_no")
            wa_firma = st.text_input("Kişi/Firma Adı:", key="wa_manuel_ad")
            wa_numara = wa_numara_formatla(manuel_no)
            if manuel_no:
                if wa_numara and "@c.us" in wa_numara:
                    st.success(f"✅ {wa_numara}")
                else:
                    st.error("Geçersiz numara")

        # Şablon seç veya serbest yaz
        sablon_sec = st.selectbox("Şablon:", [
            "Serbest Yaz",
            "Merhaba tanışma",
            "Teklif hatırlatma",
            "Teşekkür mesajı",
            "Ödeme hatırlatma"
        ], key="wa_sablon")

        sablon_metinler = {
            "Merhaba tanışma": f"Merhaba {wa_firma} yetkilisi,\n\nBen MW Kargo'dan arıyorum. Kargo ihtiyaçlarınız için size özel fiyat teklifimiz var. Uygun bir zamanda görüşebilir miyiz?\n\nSaygılarımızla",
            "Teklif hatırlatma": f"Sayın {wa_firma} yetkilisi,\n\nDaha önce gönderdiğimiz teklifimizi incelediniz mi? Sorularınız için buradayız.\n\nSaygılarımızla",
            "Teşekkür mesajı": f"Sayın {wa_firma} yetkilisi,\n\nBize gösterdiğiniz ilgi için teşekkür ederiz. Çalışmalarımızı sürdürmeyi bekliyoruz.\n\nSaygılarımızla",
            "Ödeme hatırlatma": f"Sayın {wa_firma} yetkilisi,\n\nHesap dönemi gelmiş olup ödeme konusunda bilgilendirmek istedik. Detaylar için iletişime geçebilirsiniz.\n\nSaygılarımızla",
        }

        default_metin = sablon_metinler.get(sablon_sec, "")
        wa_mesaj = st.text_area("Mesaj:", value=default_metin, height=150, key="wa_mesaj_tek")

        col_wa_gonder, col_wa_link = st.columns(2)
        with col_wa_gonder:
            if st.button("📤 Waha ile Gönder", use_container_width=True, type="primary"):
                if not wa_numara or "@c.us" not in wa_numara:
                    st.error("Geçerli numara girin!")
                elif not wa_mesaj.strip():
                    st.error("Mesaj boş!")
                else:
                    sonuc = waha_post("/api/sendText", {
                        "session": WAHA_SESSION,
                        "chatId": wa_numara,
                        "text": wa_mesaj
                    })
                    if sonuc and "id" in str(sonuc):
                        db_insert("islem_kaydi", {"musteri_id": 0, "musteri_adi": "kayit", "islem_turu": "kayit", "icerik": "kayit", "gonderim_bilgisi": "kayit", "olusturan": st.session_state["kullanici"]})
                    else:
                        st.error(f"Gönderim hatası: {sonuc}")

        with col_wa_link:
            if wa_numara and "@c.us" in wa_numara:
                wa_no_link = wa_numara.replace("@c.us","")
                st.button("🔗 WhatsApp Web'de Aç", use_container_width=True, disabled=True, help="Geçici olarak devre dışı", key="wa_btn_web1")

    # ── TOPLU GÖNDER ──────────────────────────────────────────────────────────
    with wa_tab2:
        st.markdown("### 👥 Toplu Mesaj Gönder")
        st.warning("⚠️ Spam yapmayın — WhatsApp toplu mesaj için kısıtlama uygulayabilir.")

        filtre_durum_wa = st.selectbox("Müşteri Filtresi:", ["Tümü"], key="toplu_filtre")
        df_toplu = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")
        if filtre_durum_wa != "Tümü":
            df_toplu = df_toplu[df_toplu["durum"] == filtre_durum_wa]

        st.markdown(f"**{len(df_toplu)} müşteri** bu filtrede")
        df_toplu["Seç"] = False
        edited_toplu = st.data_editor(
            df_toplu[["Seç","firma","gsm","il","durum"]],
            column_config={"Seç": st.column_config.CheckboxColumn("Seç", default=False)},
            use_container_width=True, hide_index=True, key="toplu_editor"
        )
        secili_toplu = edited_toplu[edited_toplu["Seç"] == True]
        st.markdown(f"**{len(secili_toplu)} müşteri seçildi**")

        toplu_sablon = st.text_area("Toplu Mesaj Şablonu:", height=120, key="toplu_mesaj",
            placeholder="Merhaba {firma} yetkilisi,\n\nSize özel teklifimiz için iletişime geçiyoruz...\n\n{firma} yazarsanız otomatik firma adı gelir.")

        bekleme = st.slider("Mesajlar arası bekleme (saniye):", 3, 30, 5, key="toplu_bekleme")

        if st.button(f"📤 {len(secili_toplu)} Müşteriye Gönder", use_container_width=True,
                     type="primary", disabled=len(secili_toplu)==0):
            if not toplu_sablon.strip():
                st.error("Mesaj şablonu boş!")
            else:
                import time as _time
                progress = st.progress(0)
                basarili = 0; hatali = 0
                for i, (_, row) in enumerate(secili_toplu.iterrows()):
                    numara = wa_numara_formatla(row["gsm"])
                    mesaj = toplu_sablon.replace("{firma}", str(row["firma"]))
                    if numara and "@c.us" in numara:
                        sonuc = waha_post("/api/sendText", {
                            "session": WAHA_SESSION,
                            "chatId": numara,
                            "text": mesaj
                        })
                        if sonuc and "id" in str(sonuc):
                            db_insert("islem_kaydi", {"musteri_id": 0, "musteri_adi": "kayit", "islem_turu": "kayit", "icerik": "kayit", "gonderim_bilgisi": "kayit", "olusturan": st.session_state["kullanici"]})
                        else:
                            hatali += 1
                        _time.sleep(bekleme)
                    else:
                        hatali += 1
                    progress.progress((i+1)/len(secili_toplu))
                st.success(f"✅ {basarili} gönderildi, {hatali} hatalı")

    # ── GÖRÜŞME KAYDET ────────────────────────────────────────────────────────
    with wa_tab3:
        st.markdown("### 💬 Görüşme Kaydet")
        st.info("WhatsApp görüşmelerinizi sisteme not olarak kaydedin.")

        df_gkayit = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")

        gkayit_opts = ["-- Müşteri Seçin --"] + [f"[{int(r['id'])}] {r['firma']}" for _, r in df_gkayit.iterrows()]
        gkayit_secim = st.selectbox("Müşteri:", gkayit_opts, key="gkayit_musteri")

        gkayit_musteri_id = 0
        gkayit_firma = ""
        if gkayit_secim != "-- Müşteri Seçin --":
            gkayit_musteri_id = int(gkayit_secim.split("]")[0].replace("[","").strip())
            gkayit_firma = gkayit_secim.split("] ")[1] if "] " in gkayit_secim else ""

        gc1, gc2 = st.columns(2)
        gorusme_tarihi = gc1.date_input("Görüşme Tarihi:", value=datetime.now().date(), key="gorusme_tarihi")
        gorusme_turu = gc2.selectbox("Görüşme Türü:", ["WhatsApp", "Telefon", "Yüz Yüze", "Email", "Diğer"], key="gorusme_turu")

        gorusme_notu = st.text_area("Görüşme Notu:", height=150, key="gorusme_notu",
            placeholder="Müşteri ne istedi? Ne konuştunuz? Sonraki adım nedir?")

        sonraki_adim = st.text_input("Sonraki Adım:", placeholder="Fiyat teklifi gönder, takip ara...", key="sonraki_adim")
        hatirlatma = st.date_input("Hatırlatma Tarihi:", key="hatirlatma_tarihi")

        if st.button("💾 Görüşmeyi Kaydet", use_container_width=True, type="primary"):
            if not gkayit_firma:
                st.error("Müşteri seçin!")
            elif not gorusme_notu.strip():
                st.error("Not boş olamaz!")
            else:
                icerik = f"[{gorusme_turu}] {gorusme_notu}\nSonraki: {sonraki_adim}\nHatırlatma: {hatirlatma}"
                db_insert("islem_kaydi", {"musteri_id": 0, "musteri_adi": "kayit", "islem_turu": "kayit", "icerik": "kayit", "gonderim_bilgisi": "kayit", "olusturan": st.session_state["kullanici"]})

        # Hatırlatmalar
        st.divider()
        st.markdown("#### ⏰ Yaklaşan Hatırlatmalar")
        try:
            df_hat = db_read("islem_kaydi", order_col="tarih", limit=20)
            if not df_hat.empty:
                st.dataframe(df_hat, use_container_width=True, hide_index=True)
            else:
                st.info("Hatırlatma yok.")
        except:
            st.info("Henüz kayıt yok.")

    # ── GEÇMİŞ ───────────────────────────────────────────────────────────────
    with wa_tab4:
        st.markdown("### 📋 WhatsApp Mesaj Geçmişi")

        ara_wa = st.text_input("Müşteri veya mesaj ara:", key="wa_gecmis_ara")
        try:
            df_gecmis = db_read("islem_kaydi", order_col="tarih", limit=100)
            if ara_wa:
                mask = df_gecmis.apply(lambda r: ara_wa.lower() in str(r).lower(), axis=1)
                df_gecmis = df_gecmis[mask]
            if not df_gecmis.empty:
                st.markdown(f"**{len(df_gecmis)} kayıt**")
                df_gecmis.columns = ["Tarih","Müşteri","Tür","İçerik","Numara/Tarih","Kullanıcı"]
                st.dataframe(df_gecmis, use_container_width=True, hide_index=True)

                import io as _io2
                buf = _io2.BytesIO()
                df_gecmis.to_excel(buf, index=False)
                buf.seek(0)
                st.download_button("📥 Excel İndir", data=buf,
                    file_name=f"wa_gecmis_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.ms-excel", use_container_width=True)
            else:
                st.info("Kayıt bulunamadı.")
        except Exception as e:
            st.error(f"Hata: {e}")

elif aktif == "randevu":
    sayfa_log("randevu")
    import io as _rio
    st.markdown("## 📅 Randevular")

    # ── TÜM RANDEVULARI YİKLE ────────────────────────────────────────────────
    df_rand_all = db_read("randevular", extra_sql="ORDER BY randevu_tarihi ASC, randevu_saati ASC")
    # Atama filtresi — kullanıcı sadece kendi müşterilerinin randevularını görür
    if not df_rand_all.empty and "musteri_adi" in df_rand_all.columns:
        _rand_atanan = _get_atanmis_firmalar()
        if _rand_atanan is not None and "firmalar" in _rand_atanan:
            def _norm_r(s): return str(s or "").strip().upper()
            df_rand_all = df_rand_all[df_rand_all["musteri_adi"].apply(lambda x: _norm_r(x) in _rand_atanan["firmalar"])]
    bugun_str = datetime.now().strftime("%Y-%m-%d")

    # ── iki sekme ─────────────────────────────────────────────────────────────
    r_tab1, r_tab2, r_tab3, r_tab4, r_tab_rut = st.tabs(["📋 Liste & Düzenle", "➕ Yeni Randevu", "📂 Aşama Sayfaları", "⚙️ Yönetim", "🗺️ Rut Haritası"])

    with r_tab1:
        # Filtreler
        rf1,rf2,rf3,rf4 = st.columns(4)
        _fil_tem   = rf1.text_input("Temsilci:", key="rand_fil_tem")
        _fil_sonuc = rf2.selectbox("Sonuç:", ["Tümü","Bitti","Devam Ediyor","Gidilmedi","İptal","—"], key="rand_sonuc")
        _fil_ara   = rf3.text_input("🔍 Ara:", key="rand_fil_ara")
        _siralama  = rf4.selectbox("Sırala:", ["Tarih ↑","Tarih ↓","Müşteri A-Z","Müşteri Z-A","Temsilci A-Z"], key="rand_siralama")

        df_rand = df_rand_all.copy() if not df_rand_all.empty else pd.DataFrame()
        if not df_rand.empty:
            if _fil_tem: df_rand = df_rand[df_rand["temsilci"].str.contains(_fil_tem,case=False,na=False)]
            if _fil_sonuc != "Tümü": df_rand = df_rand[df_rand["sonuc"]==_fil_sonuc]
            if _fil_ara: df_rand = df_rand[df_rand.apply(lambda r: _fil_ara.lower() in str(r).lower(),axis=1)]
            # Sıralama
            if _siralama == "Tarih ↑": df_rand = df_rand.sort_values("randevu_tarihi", ascending=True)
            elif _siralama == "Tarih ↓": df_rand = df_rand.sort_values("randevu_tarihi", ascending=False)
            elif _siralama == "Müşteri A-Z": df_rand = df_rand.sort_values("musteri_adi", ascending=True)
            elif _siralama == "Müşteri Z-A": df_rand = df_rand.sort_values("musteri_adi", ascending=False)
            elif _siralama == "Temsilci A-Z": df_rand = df_rand.sort_values("temsilci", ascending=True)
            df_rand = df_rand.reset_index(drop=True)

        if df_rand.empty:
            st.info("Randevu bulunamadı.")
        else:
            # ── 10 METRİK TEK SATIR ───────────────────────────────────────────
            _toplam   = len(df_rand)
            _bitti    = len(df_rand[df_rand["sonuc"]=="Bitti"]) if "sonuc" in df_rand.columns else 0
            _devam    = len(df_rand[df_rand["sonuc"]=="Devam Ediyor"]) if "sonuc" in df_rand.columns else 0
            _gidilmedi= len(df_rand[df_rand["sonuc"]=="Gidilmedi"]) if "sonuc" in df_rand.columns else 0
            _bugun    = len(df_rand[df_rand["randevu_tarihi"]==bugun_str]) if "randevu_tarihi" in df_rand.columns else 0
            _bu_hafta_bitis = (datetime.now()+pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            _hafta    = len(df_rand[(df_rand["randevu_tarihi"]>=bugun_str)&(df_rand["randevu_tarihi"]<=_bu_hafta_bitis)]) if "randevu_tarihi" in df_rand.columns else 0
            _bu_ay_bitis = datetime.now().strftime("%Y-%m-") + "31"
            _ay       = len(df_rand[(df_rand["randevu_tarihi"]>=bugun_str)&(df_rand["randevu_tarihi"]<=_bu_ay_bitis)]) if "randevu_tarihi" in df_rand.columns else 0
            _acik_say = len(df_rand[(df_rand["randevu_tarihi"]<bugun_str)&(~df_rand["sonuc"].isin(["Bitti","İptal","Gidilmedi"]))]) if "sonuc" in df_rand.columns else 0
            _basari   = f"%{int(_bitti/_toplam*100)}" if _toplam > 0 else "—"
            # Beklenen ciro — randevusu olan müşterilerden
            try:
                _df_cari_r = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")
                _mus_listesi = df_rand["musteri_adi"].dropna().unique().tolist()
                _beklenen = _df_cari_r[_df_cari_r["firma"].isin(_mus_listesi)]["beklenen_ciro"].sum() if not _df_cari_r.empty else 0
            except: _beklenen = 0

            # ── ÜST RAPOR — başlıklarla aynı kolon genişliğinde ─────────────
            _CW = [0.4,1.1,1.8,1.3,1.3,1.1,1.1,1.1,1.1,0.4]
            _CW9 = [1.1,1.1,1.1,1.2,1.1,1.2,1.1,1.1,1.8]
            _rc_rapor = st.columns(_CW9)
            _rapor_etiketler = ["Toplam","✅ Bitti","🔄 Devam","❌ Gidilmedi","📅 Bugün","📆 Hafta","📆 Ay","⚠️ Açık","💰 Beklenen"]
            _rapor_degerler  = [_toplam, _bitti, _devam, _gidilmedi, _bugun, _hafta, _ay, _acik_say, fmt_para(_beklenen)]
            _rapor_filtreler = ["toplam","bitti","devam","gidilmedi","bugun","hafta","ay","acik","beklenen"]

            for _col, _lbl, _val, _fil in zip(_rc_rapor, _rapor_etiketler, _rapor_degerler, _rapor_filtreler):
                if _col.button(f"{_lbl}\n{_val}", key=f"rp_fil_{_fil}", use_container_width=True):
                    if st.session_state.get("rp_aktif_fil") == _fil:
                        st.session_state.pop("rp_aktif_fil", None)
                    else:
                        st.session_state["rp_aktif_fil"] = _fil
                    st.rerun()

            # Aktif filtre varsa uygula ve detay göster
            _aktif_fil = st.session_state.get("rp_aktif_fil")
            _df_detay = df_rand.copy()
            if _aktif_fil == "bitti":      _df_detay = df_rand[df_rand["sonuc"]=="Bitti"]
            elif _aktif_fil == "devam":    _df_detay = df_rand[df_rand["sonuc"]=="Devam Ediyor"]
            elif _aktif_fil == "gidilmedi":_df_detay = df_rand[df_rand["sonuc"]=="Gidilmedi"]
            elif _aktif_fil == "bugun":    _df_detay = df_rand[df_rand["randevu_tarihi"]==bugun_str]
            elif _aktif_fil == "hafta":
                _hf_bitis = (datetime.now()+pd.Timedelta(days=7)).strftime("%Y-%m-%d")
                _df_detay = df_rand[(df_rand["randevu_tarihi"]>=bugun_str)&(df_rand["randevu_tarihi"]<=_hf_bitis)]
            elif _aktif_fil == "ay":
                _ay_bitis = datetime.now().strftime("%Y-%m-") + "31"
                _df_detay = df_rand[(df_rand["randevu_tarihi"]>=bugun_str)&(df_rand["randevu_tarihi"]<=_ay_bitis)]
            elif _aktif_fil == "acik":
                _df_detay = df_rand[(df_rand["randevu_tarihi"]<bugun_str)&(~df_rand["sonuc"].isin(["Bitti","İptal","Gidilmedi"]))]

            if _aktif_fil and _aktif_fil not in ["toplam","basari","beklenen"]:
                _aktif_lbl = _rapor_etiketler[_rapor_filtreler.index(_aktif_fil)]
                st.markdown(f"<div style='background:#1f6feb11;border-radius:4px;padding:4px 8px;font-size:0.8rem;color:#1f6feb'>🔍 <b>{_aktif_lbl}</b> — {len(_df_detay)} kayıt &nbsp; <small>(tekrar tıkla = kapat)</small></div>", unsafe_allow_html=True)
                df_rand = _df_detay

            # Ciro bilgilerini cari kartlardan çek
            try:
                _df_cari_join = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")
                _ciro_map = {}
                if not _df_cari_join.empty:
                    for _, _cr in _df_cari_join.iterrows():
                        _ciro_map[str(_cr.get("firma",""))] = {
                            "hedef": float(_cr.get("beklenen_ciro",0) or 0),
                            "gercek": float(_cr.get("gerceklesen_ciro",0) or 0)
                        }
            except: _ciro_map = {}

            # ── DÜZENLENEBILIR RANDEVU LİSTESİ ──────────────────────────────
            _sonuc_opts = ["—","Bitti","Devam Ediyor","Gidilmedi","İptal"]
            _gorev_opts = ["Ziyaret","Arama","Değerlendirme","Kazanıldı","Kaybedildi","Devam Ediyor","Whatsapp Mesaj","E-mail","Yeni Tarihe Ertele"]
            _saat_opts  = [f"{h:02d}:{m:02d}" for h in range(9,21) for m in (0,15,30,45)]

            # Müşteri adres/il/ilçe bilgilerini cari listeden çek
            _adres_map = {}
            try:
                _df_cari_adres = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")
                if not _df_cari_adres.empty:
                    for _, _ca in _df_cari_adres.iterrows():
                        _adres_map[str(_ca.get("firma",""))] = {
                            "il":    str(_ca.get("il","")    or ""),
                            "ilce":  str(_ca.get("ilce","")  or ""),
                            "adres": str(_ca.get("adres","") or ""),
                        }
            except: pass

            # ── GELECEK / GEÇMİŞ AYRIMI ───────────────────────────────────────
            _gg_secim = st.radio(
                "Randevu Zamanı",
                ["📅 Gelecek", "📜 Geçmiş", "🔁 Tümü"],
                horizontal=True,
                key="rand_gg_secim",
                label_visibility="collapsed"
            )
            if _gg_secim == "📅 Gelecek":
                df_rand = df_rand[df_rand["randevu_tarihi"] >= bugun_str]
            elif _gg_secim == "📜 Geçmiş":
                df_rand = df_rand[df_rand["randevu_tarihi"] < bugun_str]
            st.caption(f"{len(df_rand)} randevu gösteriliyor")

            # Sıralama artık sabit: Tarih'e göre artan (yakından uzağa) — seçim kutusuna gerek yok
            _sort_col = "Tarih"
            _sort_asc = True
            _row_h_px = 35  # her zaman kompakt

            _df_goster = pd.DataFrame([{
                "ID":       int(r.get("id",0) or 0),
                "Tarih":    fmt_tarih(r.get("randevu_tarihi","")),
                "Saat":     str(r.get("randevu_saati","") or "09:00")[:5],
                "Müşteri":  str(r.get("musteri_adi","") or ""),
                "İl":       _adres_map.get(str(r.get("musteri_adi","")),{}).get("il",""),
                "İlçe":     _adres_map.get(str(r.get("musteri_adi","")),{}).get("ilce",""),
                "Adres":    _adres_map.get(str(r.get("musteri_adi","")),{}).get("adres",""),
                "Bölge":    str(r.get("bolge","") or ""),
                "Görev":    str(r.get("gorev","") or ""),
                "Sonuç":    str(r.get("sonuc","") or "—"),
                "Açıklama": str(r.get("aciklama","") or ""),
                "Temsilci": str(r.get("temsilci","") or ""),
                "Hedef ₺":  float(_ciro_map.get(str(r.get("musteri_adi","")),{"hedef":0})["hedef"]),
                "Gerçek ₺": float(_ciro_map.get(str(r.get("musteri_adi","")),{"gercek":0})["gercek"]),
                "Fark ₺":   float(_ciro_map.get(str(r.get("musteri_adi","")),{"gercek":0})["gercek"]) - float(_ciro_map.get(str(r.get("musteri_adi","")),{"hedef":0})["hedef"]),
            } for _,r in df_rand.iterrows()]) if not df_rand.empty else pd.DataFrame(columns=[
                "ID","Tarih","Saat","Müşteri","İl","İlçe","Adres","Bölge","Görev",
                "Sonuç","Açıklama","Temsilci","Hedef ₺","Gerçek ₺","Fark ₺"
            ])

            # Sıralama uygula — hafızadan
            if _sort_col in _df_goster.columns:
                _df_goster = _df_goster.sort_values(_sort_col, ascending=_sort_asc).reset_index(drop=True)
                # id listesini de aynı sırayla yenile
                _rand_id_list = list(_df_goster["ID"])

            # id→index map (kaydetmek için)
            _rand_id_list = list(_df_goster["ID"])

            # Seç kolonu ekle
            if "Seç" not in _df_goster.columns:
                _df_goster.insert(0, "Seç", False)

            _edited_rand = st.data_editor(
                _df_goster,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                row_height=_row_h_px,
                column_config={
                    "Seç":      st.column_config.CheckboxColumn("Seç", default=False, width="small"),
                    "ID":       st.column_config.NumberColumn("ID", width="small", disabled=True),
                    "Tarih":    st.column_config.TextColumn("Tarih", width="small", help="GG.AA.YYYY"),
                    "Saat":     st.column_config.SelectboxColumn("Saat", options=_saat_opts, width="small"),
                    "Müşteri":  st.column_config.TextColumn("Müşteri", width="large"),
                    "İl":       st.column_config.TextColumn("İl", width="small", disabled=True),
                    "İlçe":     st.column_config.TextColumn("İlçe", width="small", disabled=True),
                    "Adres":    st.column_config.TextColumn("Adres", width="large", disabled=True),
                    "Bölge":    st.column_config.TextColumn("Bölge"),
                    "Görev":    st.column_config.SelectboxColumn("Görev", options=_gorev_opts, width="medium"),
                    "Sonuç":    st.column_config.SelectboxColumn("Sonuç", options=_sonuc_opts, width="small"),
                    "Açıklama": st.column_config.TextColumn("Açıklama", width="large"),
                    "Temsilci": st.column_config.TextColumn("Temsilci", width="medium"),
                    "Hedef ₺":  st.column_config.NumberColumn("Hedef ₺", format="%.0f ₺", disabled=True),
                    "Gerçek ₺": st.column_config.NumberColumn("Gerçek ₺", format="%.0f ₺", disabled=True),
                    "Fark ₺":   st.column_config.NumberColumn("Fark ₺", format="%.0f ₺", disabled=True),
                },
                key="rand_editor"
            )

            # Seçili satırlar
            _rand_secili_df = _edited_rand[_edited_rand["Seç"] == True] if "Seç" in _edited_rand.columns else pd.DataFrame()
            _rand_secili_ids = []
            for _si in _rand_secili_df.index:
                _pos = list(_df_goster.index).index(_si) if _si in list(_df_goster.index) else _si
                if _pos < len(_rand_id_list):
                    _rand_secili_ids.append(int(_rand_id_list[_pos]))

            # Seçilince aksiyon butonları
            if len(_rand_secili_ids) > 0:
                st.markdown(f"**{len(_rand_secili_ids)} randevu seçili**")
                _ak1, _ak2, _ak3 = st.columns([1,1,4])

                # Silme
                if _ak1.button(f"🗑 Sil ({len(_rand_secili_ids)})", key="rand_sec_sil", use_container_width=True, type="primary"):
                    st.session_state["rand_sil_onay_ids"] = _rand_secili_ids

                if st.session_state.get("rand_sil_onay_ids"):
                    _sil_ids = st.session_state["rand_sil_onay_ids"]
                    st.warning(f"⚠️ {len(_sil_ids)} randevu silinecek. Emin misin?")
                    _oc1, _oc2 = st.columns(2)
                    if _oc1.button("✅ Evet, Sil", key="rand_sil_evet2", use_container_width=True):
                        _sb_rsil = get_sb_client()
                        for _rsil_id in _sil_ids:
                            try:
                                if _sb_rsil:
                                    _sb_rsil.table("randevular").delete().eq("id", _rsil_id).execute()
                            except: pass
                        st.session_state.pop("rand_sil_onay_ids", None)
                        try: db_read.clear()
                        except: pass
                        st.success(f"✅ {len(_sil_ids)} randevu silindi!")
                        st.rerun()
                    if _oc2.button("❌ Vazgeç", key="rand_sil_vazgec2", use_container_width=True):
                        st.session_state.pop("rand_sil_onay_ids", None)
                        st.rerun()

                # Toplu sonuç değiştir
                _yeni_sonuc = _ak2.selectbox("Sonuç değiştir:", ["—"] + _sonuc_opts, key="rand_toplu_sonuc")
                if _yeni_sonuc != "—":
                    if _ak3.button(f"✅ {len(_rand_secili_ids)} randevuya '{_yeni_sonuc}' yaz", key="rand_toplu_kaydet", use_container_width=True):
                        _sb_rts = get_sb_client()
                        for _rts_id in _rand_secili_ids:
                            try:
                                if _sb_rts:
                                    _sb_rts.table("randevular").update({"sonuc": _yeni_sonuc}).eq("id", _rts_id).execute()
                            except: pass
                        try: db_read.clear()
                        except: pass
                        st.success(f"✅ {len(_rand_secili_ids)} randevu güncellendi!")
                        st.rerun()

            # Kaydet butonu
            if st.button("💾 Değişiklikleri Kaydet", type="primary", use_container_width=True, key="rand_kaydet"):
                _rand_editor_state = st.session_state.get("rand_editor", {})
                _rand_edited_rows  = _rand_editor_state.get("edited_rows", {})
                _rand_kayit = 0
                for _idx_s, _degis in _rand_edited_rows.items():
                    try:
                        _idx = int(_idx_s)
                        _rid = _rand_id_list[_idx] if _idx < len(_rand_id_list) else 0
                        if not _rid: continue
                        _guncelle = {}
                        if "Tarih" in _degis:
                            _t = str(_degis["Tarih"]).strip()
                            if len(_t) == 10 and _t[2] == "." and _t[5] == ".":
                                _guncelle["randevu_tarihi"] = f"{_t[6:]}-{_t[3:5]}-{_t[:2]}"
                            else:
                                _guncelle["randevu_tarihi"] = _t
                        if "Saat" in _degis:     _guncelle["randevu_saati"] = str(_degis["Saat"])
                        if "Bölge" in _degis:    _guncelle["bolge"] = str(_degis["Bölge"])
                        if "Görev" in _degis:    _guncelle["gorev"] = str(_degis["Görev"])
                        if "Sonuç" in _degis:    _guncelle["sonuc"] = str(_degis["Sonuç"]) if _degis["Sonuç"] != "—" else ""
                        if "Açıklama" in _degis: _guncelle["aciklama"] = str(_degis["Açıklama"])
                        if "Temsilci" in _degis: _guncelle["temsilci"] = str(_degis["Temsilci"])
                        if not _guncelle: continue
                        _sb_rand = get_sb_client()
                        if _sb_rand:
                            _sb_rand.table("randevular").update(_guncelle).eq("id", _rid).execute()
                        else:
                            db_update("randevular", _guncelle, "id", _rid)
                        _rand_kayit += 1
                    except Exception as _re:
                        st.error(f"Hata (satır {_idx_s}): {_re}")
                if _rand_kayit:
                    try: db_read.clear()
                    except: pass
                    st.success(f"✅ {_rand_kayit} randevu güncellendi!")
                    st.rerun()
                else:
                    st.info("Değişiklik yok.")

            # ── SİLME KISMI ──────────────────────────────────────────────────
            with st.expander("🗑 Randevu Sil", expanded=False):
                st.caption("Silmek istediğiniz randevunun ID'sini seçin:")
                _sil_id_opts = [f"ID:{r.get('id','')} · {fmt_tarih(r.get('randevu_tarihi',''))} · {r.get('musteri_adi','')} · {r.get('bolge','')}" for _,r in df_rand.iterrows()]
                _sil_id_map  = {f"ID:{r.get('id','')} · {fmt_tarih(r.get('randevu_tarihi',''))} · {r.get('musteri_adi','')} · {r.get('bolge','')}": int(r.get("id",0)) for _,r in df_rand.iterrows()}
                if _sil_id_opts:
                    _sil_sec = st.selectbox("Randevu seç:", _sil_id_opts, key="rand_sil_sec")
                    _sc1, _sc2 = st.columns(2)
                    if _sc1.button("🗑 Sil", key="rand_sil_btn", use_container_width=True, type="primary"):
                        st.session_state["rand_sil_onay"] = True
                    if st.session_state.get("rand_sil_onay"):
                        st.warning(f"⚠️ **{_sil_sec}** silinecek. Emin misin?")
                        _oc1, _oc2 = st.columns(2)
                        if _oc1.button("✅ Evet, Sil", key="rand_sil_evet", use_container_width=True):
                            _sil_rid = _sil_id_map.get(_sil_sec, 0)
                            if _sil_rid:
                                try:
                                    _sb_sil = get_sb_client()
                                    if _sb_sil:
                                        _sb_sil.table("randevular").delete().eq("id", _sil_rid).execute()
                                    else:
                                        db_exec(f"DELETE FROM randevular WHERE id={_sil_rid}")
                                    st.session_state.pop("rand_sil_onay", None)
                                    try: db_read.clear()
                                    except: pass
                                    st.success("✅ Randevu silindi!")
                                    st.rerun()
                                except Exception as _se:
                                    st.error(f"Hata: {_se}")
                        if _oc2.button("❌ Hayır", key="rand_sil_hayir", use_container_width=True):
                            st.session_state.pop("rand_sil_onay", None)
                            st.rerun()
                else:
                    st.info("Silinecek randevu yok.")

            # Excel
            _buf_r = _rio.BytesIO(); df_rand.to_excel(_buf_r,index=False); _buf_r.seek(0)
            st.download_button("📥 Excel İndir",data=_buf_r,
                file_name=f"randevular_{datetime.now().strftime('%Y%m%d')}.xlsx",
                use_container_width=True)

    with r_tab2:
        df_mrand = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")
        musteri_rand_opts = ["-- Müşteri Seçin --"] + [f"[{int(r['id'])}] {r['firma']} ({r['durum']})" for _,r in df_mrand.iterrows()]

        _onsel_id = st.session_state.pop("rand_musteri_onsel", None)
        _onsel_idx = 0
        if _onsel_id:
            for i,opt in enumerate(musteri_rand_opts):
                if f"[{_onsel_id}]" in opt: _onsel_idx = i; break

        if st.session_state.get("rand_mus_reset"):
            st.session_state.pop("rand_mus_reset",None)
            st.session_state.pop("rand_musteri_sec",None)

        _rm1,_rm2 = st.columns([6,1])
        _rand_mus_sec = _rm1.selectbox("Müşteri*:", musteri_rand_opts, index=_onsel_idx, key="rand_musteri_sec")
        if _rand_mus_sec != "-- Müşteri Seçin --":
            if _rm2.button("❌", key="rand_mus_temizle", use_container_width=True):
                st.session_state["rand_mus_reset"] = True; st.rerun()

        # ── MÜŞTERİ ÖZET KARTI — adres, telefon, son not, son teklif ──────────────
        _rand_musteri_satir = None
        _rand_bolge_oto = ""
        _rand_tem_tel_oto = ""
        if _rand_mus_sec != "-- Müşteri Seçin --" and "[" in _rand_mus_sec:
            try:
                _rmid = int(_rand_mus_sec.split("]")[0].replace("[","").strip())
                _rmrow = df_mrand[df_mrand["id"] == _rmid]
                if not _rmrow.empty:
                    _rand_musteri_satir = _rmrow.iloc[0] if not _rmrow.empty else None
            except: pass

        if _rand_musteri_satir is not None:
            _rm = _rand_musteri_satir
            _rm_firma   = str(_rm.get("firma","") or "")
            _rm_yetkili = str(_rm.get("yetkili","") or "")
            _rm_sektor  = str(_rm.get("sektor","") or "")
            _rm_durum   = str(_rm.get("durum","") or "")
            _rm_il      = str(_rm.get("il","") or "")
            _rm_ilce    = str(_rm.get("ilce","") or "")
            _rm_adres   = str(_rm.get("adres","") or "")
            _rm_gsm     = str(_rm.get("gsm","") or "")
            _rm_bek     = float(_rm.get("beklenen_ciro",0) or 0)

            _rand_bolge_oto = f"{_rm_il} {_rm_ilce}".strip()
            _rand_tem_tel_oto = _rm_gsm

            # Son not çek
            _rm_son_not = ""
            _rm_not_tarih = ""
            try:
                _sb_rmn = get_sb_client()
                if _sb_rmn:
                    _rmn_r = _sb_rmn.table("cari_aciklamalar").select("aciklama,created_at").eq("cari_id", int(_rmid)).order("id", desc=True).limit(5).execute()
                    if _rmn_r.data:
                        for _rmn_row in _rmn_r.data:
                            if str(_rmn_row.get("aciklama","") or "").startswith("##YETKILI##"):
                                continue
                            _rm_son_not = str(_rmn_row.get("aciklama","") or "")
                            _rm_not_tarih = str(_rmn_row.get("created_at","") or "")[:10]
                            break
            except: pass

            # Son teklif çek
            _rm_son_teklif = ""
            try:
                _sb_rmt = get_sb_client()
                if _sb_rmt:
                    _rmt_r = _sb_rmt.table("teklifler").select("toplam_tutar,durum,tarih").eq("cari_id", int(_rmid)).order("id", desc=True).limit(1).execute()
                    if _rmt_r.data:
                        _tt = _rmt_r.data[0].get("toplam_tutar", 0) or 0
                        _td = str(_rmt_r.data[0].get("durum","") or "")
                        _rm_son_teklif = f"{float(_tt):,.0f}₺ · {_td}" if _tt else ""
            except: pass

            _durum_renkler = {
                "Portföy": ("#dcfce7","#166534","🟢"),
                "Özel Müşteri": ("#eff6ff","#1d4ed8","🔵"),
                "Tekrar Ara": ("#fef9c3","#854d0e","🟡"),
            }
            _rbg, _rtc, _remo = _durum_renkler.get(_rm_durum, ("#f1f5f9","#475569","⚪"))

            st.markdown(f"""
<div style="background:linear-gradient(135deg,#eff6ff,#f0f9ff);border:1px solid #bfdbfe;border-radius:14px;padding:16px 18px;margin-bottom:14px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
    <div style="font-size:16px;font-weight:600;color:#0f172a;">🏢 {_rm_firma}</div>
    <span style="font-size:11px;padding:3px 10px;border-radius:20px;background:{_rbg};color:{_rtc};font-weight:500;white-space:nowrap;">{_remo} {_rm_durum}</span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;">
    <div style="background:white;border:0.5px solid #e2e8f0;border-radius:8px;padding:7px 10px;display:flex;gap:7px;">
      <span style="font-size:13px;">👤</span>
      <div><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;">Yetkili</div>
      <div style="font-size:12px;color:#0f172a;font-weight:500;">{_rm_yetkili if _rm_yetkili and _rm_yetkili not in ['nan','None',''] else '—'}</div></div>
    </div>
    <div style="background:white;border:0.5px solid #e2e8f0;border-radius:8px;padding:7px 10px;display:flex;gap:7px;">
      <span style="font-size:13px;">📞</span>
      <div><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;">Telefon</div>
      <div style="font-size:12px;color:#0f172a;font-weight:500;">{_rm_gsm if _rm_gsm and _rm_gsm not in ['nan','None',''] else '—'}</div></div>
    </div>
    <div style="background:white;border:0.5px solid #e2e8f0;border-radius:8px;padding:7px 10px;display:flex;gap:7px;">
      <span style="font-size:13px;">🗺️</span>
      <div><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;">Bölge</div>
      <div style="font-size:12px;color:#0f172a;font-weight:500;">{(_rm_il + ' / ' + _rm_ilce) if _rm_il else '—'}</div></div>
    </div>
    <div style="background:white;border:0.5px solid #e2e8f0;border-radius:8px;padding:7px 10px;display:flex;gap:7px;">
      <span style="font-size:13px;">🏭</span>
      <div><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;">Sektör</div>
      <div style="font-size:12px;color:#0f172a;font-weight:500;">{_rm_sektor if _rm_sektor and _rm_sektor not in ['nan','None',''] else '—'}</div></div>
    </div>
  </div>
  {"<div style='background:white;border:0.5px solid #e2e8f0;border-radius:8px;padding:8px 11px;margin-bottom:10px;display:flex;gap:7px;'><span style='font-size:13px'>📍</span><div><div style='font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:1px;'>Açık Adres</div><div style='font-size:12px;color:#334155;line-height:1.4;'>" + (_rm_adres if _rm_adres and _rm_adres not in ['nan','None',''] else (_rm_il + ' / ' + _rm_ilce)) + "</div></div></div>" if (_rm_adres and _rm_adres not in ['nan','None','']) or _rm_il else ""}
  {"<div style='background:white;border:0.5px solid #e2e8f0;border-radius:8px;padding:9px 11px;margin-bottom:10px;'><div style='font-size:9px;color:#94a3b8;text-transform:uppercase;margin-bottom:3px;display:flex;justify-content:space-between;'><span>📝 Son Not</span><span>" + _rm_not_tarih + "</span></div><div style='font-size:12px;color:#334155;line-height:1.55;'>" + _rm_son_not[:220] + ("..." if len(_rm_son_not) > 220 else "") + "</div></div>" if _rm_son_not else ""}
</div>
""", unsafe_allow_html=True)

        if "rand_tarih_deger" not in st.session_state:
            st.session_state["rand_tarih_deger"] = datetime.now().date()

        _rand_saat_opts = [f"{h:02d}:{m:02d}" for h in range(9,21) for m in (0,15,30,45)]
        _ay_tr_liste = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
        _gun_adlari = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]

        _td_deger = st.session_state["rand_tarih_deger"]
        _td_gun = _gun_adlari[_td_deger.weekday()]
        _td_ay  = _ay_tr_liste[_td_deger.month - 1]
        _tarih_okunur = f"{_td_deger.day} {_td_ay} {_td_deger.year} {_td_gun}"

        st.markdown(f"""<style>
.rand-tarih-lbl{{font-size:13px;color:#475569;font-weight:500;margin-bottom:4px;}}
/* date_input'u görünür ama metnini gizleyip yerine Türkçe metni overlay olarak koyuyoruz */
div[data-testid="stHorizontalBlock"]:has(.rand-tarih-marker) [data-testid="stDateInput"] {{
    position: relative !important;
}}
div[data-testid="stHorizontalBlock"]:has(.rand-tarih-marker) [data-testid="stDateInput"] input {{
    color: transparent !important;
}}
</style>""", unsafe_allow_html=True)

        _tlbl1, _tlbl2 = st.columns([3,1])
        _tlbl1.markdown("<div class='rand-tarih-lbl'>Tarih*</div>", unsafe_allow_html=True)
        _tlbl2.markdown("<div class='rand-tarih-lbl'>Saat*</div>", unsafe_allow_html=True)

        _ptd2, _ptd4 = st.columns([3,1.6])

        with _ptd2:
            st.markdown('<span class="rand-tarih-marker"></span>', unsafe_allow_html=True)
            _secilen_tarih = st.date_input(
                "Tarih", value=_td_deger,
                key="rand_tarih_secim", label_visibility="collapsed"
            )
            st.markdown(
                f'<div style="position:relative;margin-top:-38px;pointer-events:none;'
                f'font-size:13px;color:#0f172a;padding:9px 14px;'
                f'background:transparent;text-align:left;">📅 {_tarih_okunur}</div>',
                unsafe_allow_html=True)
            if _secilen_tarih != _td_deger:
                st.session_state["rand_tarih_deger"] = _secilen_tarih
                st.rerun()

        rand_saat = _ptd4.selectbox("Saat", _rand_saat_opts, index=4, key="rand_saat", label_visibility="collapsed")

        st.caption("👆 Tarih kutusuna tıklayarak takvimden de seçim yapabilirsiniz")

        with st.form("randevu_form"):
            st.caption(f"Seçili müşteri: **{_rand_mus_sec}**" if _rand_mus_sec != "-- Müşteri Seçin --" else "⚠️ Yukarıdan müşteri seçin")
            rand_musteri = _rand_mus_sec  # üstteki seçimi kullan, form içinde tekrar gösterme
            rand_tarih = st.session_state["rand_tarih_deger"]
            rand_bolge = st.text_input("Bölge:", value=_rand_bolge_oto, placeholder="İstanbul Beykoz")
            rc4,rc5 = st.columns(2)
            rand_gorev    = rc4.selectbox("Görev*:", ["Ziyaret","Arama","Değerlendirme","Kazanıldı","Kaybedildi","Devam Ediyor","Whatsapp Mesaj","E-mail","Yeni Tarihe Ertele"])
            rand_takip    = rc5.selectbox("Takip:", ["Gidildi","Gidilmedi","Devam Ediyor","Ertelendi"])
            rand_adet     = 0
            rand_temsilci = st.text_input("Satış Temsilcisi*:", key="rand_tem")
            rand_tem_tel  = st.text_input("Temsilci WA No:", value=_rand_tem_tel_oto, placeholder="05xxxxxxxxx", key="rand_tem_tel")
            rand_aciklama = st.text_area("Açıklama:", height=70, key="rand_aciklama", help="Bu not, randevu kaydedilince müşterinin cari kartına da otomatik eklenir.")
            rand_sonuc    = st.selectbox("Sonuç:", ["—","Bitti","Devam Ediyor","Gidilmedi","İptal"])

            if st.form_submit_button("💾 Randevu Kaydet", use_container_width=True, type="primary"):
                if rand_musteri == "-- Müşteri Seçin --":

                    st.warning("Müşteri seçin!")
                else:
                    musteri_id=0; musteri_adi=rand_musteri
                    if "[" in rand_musteri:
                        try:
                            musteri_id = int(rand_musteri.split("]")[0].replace("[","").strip())
                            musteri_adi = rand_musteri.split("] ")[1].split(" (")[0]
                        except: pass

                    # Mükerrer kontrolü — sadece uyar, engelleme
                    if musteri_id > 0:
                        _df_muk = db_read("randevular", filters={"musteri_id":musteri_id})
                        if not _df_muk.empty and "sonuc" in _df_muk.columns:
                            _aktif = _df_muk[~_df_muk["sonuc"].isin(["Bitti","İptal","Gidilmedi"])]
                            if not _aktif.empty:
                                st.warning(f"⚠️ Bu müşterinin aktif randevusu var: {_aktif.iloc[0].get('randevu_tarihi','')} — {_aktif.iloc[0].get('gorev','')}")

                    kullanici_log_kaydet("RANDEVU_EKLE","randevu",f"Müşteri: {musteri_adi}")
                    db_insert("randevular",{
                        "randevu_tarihi":str(rand_tarih),"randevu_saati":str(rand_saat),
                        "musteri_id":musteri_id,"musteri_adi":musteri_adi,
                        "bolge":rand_bolge,"gorev":rand_gorev,"takip":rand_takip,
                        "adet":int(rand_adet),"aciklama":rand_aciklama,
                        "sonuc":rand_sonuc if rand_sonuc!="—" else "",
                        "temsilci":rand_temsilci,"olusturan":st.session_state["kullanici"]
                    })
                    try: db_read.clear()
                    except: pass
                    st.success("✅ Randevu kaydedildi!")

                    # ── Açıklama doluysa cari müşteri notlarına da otomatik kaydet ──
                    if rand_aciklama and rand_aciklama.strip() and musteri_id > 0:
                        try:
                            _sb_rn = get_sb_client()
                            _yazar_rn = st.session_state.get("kullanici_ad", st.session_state.get("kullanici",""))
                            _not_metni = f"📅 Randevu notu ({rand_tarih.strftime('%d.%m.%Y')} {rand_saat}): {rand_aciklama.strip()}"
                            _rn_veri = {"cari_id": int(musteri_id), "aciklama": _not_metni, "olusturan": _yazar_rn}
                            if _sb_rn:
                                _sb_rn.table("cari_aciklamalar").insert(_rn_veri).execute()
                        except Exception:
                            pass  # not kaydı başarısız olsa bile randevu kaydı bozulmasın

                    if rand_tem_tel.strip():
                        import re as _re_r3
                        _tw3 = _re_r3.sub(r"[\s\-\(\)+]","",rand_tem_tel.strip())
                        if _tw3.startswith("0"): _tw3 = "90"+_tw3[1:]
                        elif len(_tw3)==10: _tw3 = "90"+_tw3
                        _msg3 = f"🗓️ YENİ RANDEVU\nMüşteri: {musteri_adi}\nTarih: {rand_tarih} {rand_saat}\nBölge: {rand_bolge}\nGörev: {rand_gorev}\nİyi çalışmalar!"
                        st.form_submit_button("📱 Temsilciye WA Gönder", use_container_width=True, type="primary",
                            disabled=True, help="Geçici olarak devre dışı")
                        db_insert("islem_kaydi",{"musteri_id":musteri_id,"musteri_adi":musteri_adi,
                            "islem_turu":"📅 WA Temsilci Uyarısı",
                            "icerik":f"Temsilci: {rand_temsilci} | Tarih: {rand_tarih} {rand_saat} | Bölge: {rand_bolge}",
                            "gonderim_bilgisi":_tw3,"olusturan":st.session_state.get("kullanici","")})
                    st.rerun()

    with r_tab3:
        import json as _json_ls_r
        st.markdown("### 📂 Aşama Sayfaları")

        # Cari verileri yükle
        _sb_as = get_sb_client()
        try:
            if _sb_as:
                _res_as = _sb_as.table("cari_kartlar").select("*").neq("silindi",1).order("tarih",desc=True).execute()
                _df_as = pd.DataFrame(_res_as.data) if _res_as.data else pd.DataFrame()
            else:
                raise Exception()
        except:
            _df_as = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi='0' OR silindi IS NULL ORDER BY tarih DESC")

        _tum_asama_r = _tanimlar_yukle("asama")
        _tum_durum_r = _tanimlar_yukle("durum")
        if "rakip_firma" not in _df_as.columns:
            _df_as["rakip_firma"] = ""
        _df_as["rakip_firma"] = _df_as["rakip_firma"].fillna("").astype(str).replace("nan","")
        if not _df_as.empty and "islem_asamasi" in _df_as.columns:
            for _da in _df_as["islem_asamasi"].dropna().unique():
                if str(_da).strip() and str(_da) not in ["nan",""] and _da not in _tum_asama_r:
                    _tum_asama_r.append(str(_da))

        _KOL_VARSAYILAN_R = {
            "id":40,"firma":90,"rakip_firma":90,"yetkili":90,"gsm":100,"sabit":90,"email":90,
            "adres":110,"il":70,"ilce":60,"durum":80,"temsilci":80,
            "islem_asamasi":80,"beklenen_ciro":70,"gerceklesen_ciro":70,
        }
        _KG_R = st.session_state.get("_kol_genislik", _KOL_VARSAYILAN_R)
        def _w(k):
            return int(_KG_R.get(k, _KOL_VARSAYILAN_R.get(k, 100)))

        _col_config_r = {
            "Seç":           st.column_config.CheckboxColumn("Seç", default=False),
            "id":            st.column_config.NumberColumn("ID", disabled=True, width=_w("id")),
            "tarih":         None, "olusturan": None, "silindi": None,
            "beklenen_ciro": st.column_config.NumberColumn("Hedef ₺", format="%,.0f ₺", width=_w("beklenen_ciro")),
            "gerceklesen_ciro": st.column_config.NumberColumn("Gerçek ₺", format="%,.0f ₺", width=_w("gerceklesen_ciro")),
            "rakip_firma":   st.column_config.TextColumn("Rakip Firma", width=_w("rakip_firma")),
            "firma":         st.column_config.TextColumn("Firma",    width=_w("firma")),
            "yetkili":       st.column_config.TextColumn("Yetkili",  width=_w("yetkili")),
            "gsm":           st.column_config.TextColumn("GSM",      width=_w("gsm")),
            "sabit":         st.column_config.TextColumn("S. Tel",   width=_w("sabit")),
            "email":         st.column_config.TextColumn("Email",    width=_w("email")),
            "adres":         st.column_config.TextColumn("Adres",    width=_w("adres")),
            "il":            st.column_config.TextColumn("İl",       width=_w("il")),
            "ilce":          st.column_config.TextColumn("İlçe",     width=_w("ilce")),
            "durum":         st.column_config.SelectboxColumn("Durum", options=_tum_durum_r, width=_w("durum")),
            "temsilci":      st.column_config.TextColumn("Temsilci", width=_w("temsilci")),
            "islem_asamasi": st.column_config.SelectboxColumn("Aşama", options=_tum_asama_r, width=_w("islem_asamasi")),
            "aciklama":      st.column_config.TextColumn("Açıklama", width=_w("aciklama")),
            "📅 Son Randevu": st.column_config.TextColumn("📅 Son Randevu", disabled=True, width=_w("📅 Son Randevu")),
            "📨 Notlar":     st.column_config.TextColumn("📨 Notlar", disabled=True, width=_w("📨 Notlar")),
        }
        # Gizli kolonları col_order'dan çıkar
        _col_order_r = ["Seç","id","rakip_firma","firma","yetkili","gsm","sabit","email","adres","il","ilce","durum","temsilci","islem_asamasi","aciklama","beklenen_ciro","gerceklesen_ciro","📅 Son Randevu","📨 Notlar"]
        _kol_gizli_map_r = {"firma":"firma","rakip_firma":"rakip_firma","yetkili":"yetkili","gsm":"gsm","sabit":"sabit","email":"email","adres":"adres","il":"il","ilce":"ilce","durum":"durum","temsilci":"temsilci","islem_asamasi":"islem_asamasi","aciklama":"aciklama",
                            "📅 Son Randevu":"📅 Son Randevu","📨 Notlar":"📨 Notlar","id":"id",
                            "beklenen_ciro":"beklenen_ciro","gerceklesen_ciro":"gerceklesen_ciro"}
        _GIZLI_KOLONLAR = set(st.session_state.get("_kol_gizli", []))
        _col_order_r = ["Seç"] + [c for c in _col_order_r[1:] if not any(c == _kol_gizli_map_r.get(g,g) for g in _GIZLI_KOLONLAR)]

        _secili_asama = st.selectbox("Aşama Seç:", _tum_asama_r, key="asama_sayfa_sec")
        _df_asama = _df_as[_df_as["islem_asamasi"]==_secili_asama].copy() if not _df_as.empty else pd.DataFrame()
        _df_asama = _df_asama.reset_index(drop=True)
        st.markdown(f"**{_secili_asama} — {len(_df_asama)} kayıt**")

        if _df_asama.empty:
            st.info("Bu aşamada kayıt yok.")
            if st.button("➕ Bu Aşamaya Kart Ekle", use_container_width=True, type="primary", key="asama_yeni_btn"):
                st.session_state["aktif_tab"] = "yeni"
                st.session_state["varsayilan_asama"] = _secili_asama; st.rerun()
        else:
            _df_asama_edit = _df_asama.copy()
            _df_asama_edit.insert(0, "Seç", False)
            _asama_key_r = f"aed_r_{_secili_asama[:10].replace(' ','_')}"

            _edited_asama = st.data_editor(
                _df_asama_edit,
                use_container_width=True,
                num_rows="fixed",
                column_config=_col_config_r,
                column_order=_col_order_r,
                key=_asama_key_r
            )
            try:
                st.session_state[f"_as_tablo_{_asama_key_r}"] = _edited_asama[[c for c in _col_order_r[1:] if c in _edited_asama.columns]].to_json(orient="records", force_ascii=False)
            except: pass

            _secili_asama_df = _edited_asama[_edited_asama["Seç"]==True]
            _secili_asama_idler = _secili_asama_df["id"].tolist() if not _secili_asama_df.empty else []

            _aa1, _aa2, _aa3 = st.columns(3)
            with _aa1:
                if st.button("💾 Kaydet", key=f"asv_r_{_asama_key_r}", use_container_width=True, type="primary"):
                    _tj = st.session_state.get(f"_as_tablo_{_asama_key_r}")
                    _ks = 0
                    if _tj:
                        _arows = _json_ls_r.loads(_tj)
                        for _row in _arows:
                            _rid = _row.get("id")
                            if not _rid or str(_rid) in ["nan","None",""]: continue
                            try:
                                _rid = int(float(str(_rid)))
                                _gd = {k: str(_row.get(k,"") or "") for k in ["firma","yetkili","gsm","sabit","email","il","ilce","durum","temsilci","islem_asamasi"]}
                                if _sb_as:
                                    _sb_as.table("cari_kartlar").update(_gd).eq("id",_rid).execute()
                                else:
                                    _cn=get_conn(); _sets=", ".join([f"{k}=?" for k in _gd])
                                    _cn.execute(f"UPDATE cari_kartlar SET {_sets} WHERE id=?",list(_gd.values())+[_rid])
                                    _cn.commit(); _cn.close()
                                _ks += 1
                            except: pass
                    try: db_read.clear()
                    except: pass
                    st.success(f"✅ {_ks} kaydedildi!"); st.rerun()

            with _aa2:
                _hedef_asama = st.selectbox("→ Taşı:", _tum_asama_r, key=f"tasi_r_{_asama_key_r}")
                if st.button("🔄 Seçilileri Taşı", key=f"tasibtn_r_{_asama_key_r}", use_container_width=True):
                    if _secili_asama_idler:
                        for _rid in _secili_asama_idler:
                            try:
                                if _sb_as: _sb_as.table("cari_kartlar").update({"islem_asamasi":_hedef_asama}).eq("id",int(_rid)).execute()
                                else: db_update("cari_kartlar",{"islem_asamasi":_hedef_asama},"id",int(_rid))
                            except: pass
                        try: db_read.clear()
                        except: pass
                        st.success(f"✅ {len(_secili_asama_idler)} → {_hedef_asama}"); st.rerun()
                    else:
                        st.warning("Önce Seç kolonunu işaretleyin!")

            with _aa3:
                if st.button("➕ Bu Aşamaya Ekle", key=f"aaekle_r_{_asama_key_r}", use_container_width=True):
                    st.session_state["aktif_tab"] = "yeni"
                    st.session_state["varsayilan_asama"] = _secili_asama; st.rerun()


    with r_tab4:
        st.markdown("### ⚙️ Yönetim Araçları")

        _yt_sec = st.radio("", [
            "⚙️ Aşama & Durum Yönetimi",
            "📊 Rapor & Durum Yönetimi",
            "📨 Firma Not Arşivi"
        ], horizontal=True, key="yt_sec", label_visibility="collapsed")

        st.divider()

        if _yt_sec == "⚙️ Aşama & Durum Yönetimi":
            # Cari verileri yükle
            _sb_yt = get_sb_client()
            try:
                if _sb_yt:
                    _res_yt = _sb_yt.table("cari_kartlar").select("*").neq("silindi",1).execute()
                    df = pd.DataFrame(_res_yt.data) if _res_yt.data else pd.DataFrame()
                else:
                    raise Exception()
            except:
                df = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi='0' OR silindi IS NULL")
            sb_liste = _sb_yt
            tum_asama_opts = _tanimlar_yukle("asama")
            tum_durum_opts = _tanimlar_yukle("durum")
            if not df.empty:
                if "islem_asamasi" in df.columns:
                    for _da in df["islem_asamasi"].dropna().unique():
                        if str(_da).strip() and str(_da) not in ["nan",""] and _da not in tum_asama_opts:
                            tum_asama_opts.append(str(_da))
                if "durum" in df.columns:
                    for _dd in df["durum"].dropna().unique():
                        if str(_dd).strip() and str(_dd) not in ["nan",""] and _dd not in tum_durum_opts:
                            tum_durum_opts.append(str(_dd))
            
            # ── AŞAMA & DURUM YÖNETİMİ — Supabase'e kayıtlı ─────────────────────────
            import json as _ydj
            
            def _sb_tercih_yukle(anahtar):
                try:
                    _sb = get_sb_client()
                    if _sb:
                        r = _sb.table("kullanici_tercih").select("deger") \
                            .eq("kullanici","__sistem__").eq("anahtar",anahtar).execute()
                        if r.data: return _ydj.loads(r.data[0]["deger"])
                except: pass
                return []
            
            def _sb_tercih_kaydet(anahtar, liste):
                try:
                    _sb = get_sb_client()
                    if _sb:
                        _sb.table("kullanici_tercih").upsert({
                            "kullanici":"__sistem__","anahtar":anahtar,
                            "deger":_ydj.dumps(liste,ensure_ascii=False)
                        }, on_conflict="kullanici,anahtar").execute()
                        return True
                except: pass
                return False
            
            yc1, yc2 = st.columns(2)
            
            # ── AŞAMA YÖNETİMİ ────────────────────────────────────────────────────
            with yc1:
                st.markdown("**🔄 Aşama Yönetimi**")
            
                _mevcut_asamalar = _tanimlar_yukle("asama")
            
                # Yeni aşama ekle
                _ya1, _ya2 = st.columns([3,1])
                _yeni_a = _ya1.text_input("", key="yeni_asama_ekle",
                    placeholder="Yeni aşama adı...", label_visibility="collapsed")
                if _ya2.button("➕ Ekle", key="asama_ekle_sb", use_container_width=True):
                    if _yeni_a and _yeni_a.strip():
                        if _yeni_a.strip() in _mevcut_asamalar:
                            st.warning("Bu aşama zaten var!")
                        elif _tanim_ekle("asama", _yeni_a.strip()):
                            st.success(f"✅ '{_yeni_a}' eklendi!")
                            st.rerun()
                        else:
                            st.error("Eklenemedi!")
            
                st.caption("Tüm aşamalar — sırala:")
                for _ai, _a in enumerate(_mevcut_asamalar):
                    _adet = len(df[df["islem_asamasi"]==_a]) if not df.empty and "islem_asamasi" in df.columns else 0
                    _ac1, _ac2, _ac3, _ac4, _ac5 = st.columns([3,1,1,1,1])
                    _ac1.caption(f"{'🔹' if _adet>0 else '⬜'} **{_a}** ({_adet})")
            
                    # Sırala ▲▼
                    if _ai > 0:
                        if _ac2.button("▲", key=f"asm_up_{_ai}", help="Yukarı"):
                            try:
                                _sb_s = get_sb_client()
                                if _sb_s:
                                    # Sıra değerlerini al
                                    _r1 = _sb_s.table("sistem_tanimlar").select("id,sira").eq("tip","asama").eq("deger",_a).execute()
                                    _r2 = _sb_s.table("sistem_tanimlar").select("id,sira").eq("tip","asama").eq("deger",_mevcut_asamalar[_ai-1]).execute()
                                    if _r1.data and _r2.data:
                                        _s1, _s2 = _r1.data[0]["sira"], _r2.data[0]["sira"]
                                        _sb_s.table("sistem_tanimlar").update({"sira":_s2}).eq("id",_r1.data[0]["id"]).execute()
                                        _sb_s.table("sistem_tanimlar").update({"sira":_s1}).eq("id",_r2.data[0]["id"]).execute()
                            except: pass
                            st.rerun()
                    else:
                        _ac2.caption("")
            
                    if _ai < len(_mevcut_asamalar)-1:
                        if _ac3.button("▼", key=f"asm_dn_{_ai}", help="Aşağı"):
                            try:
                                _sb_s = get_sb_client()
                                if _sb_s:
                                    _r1 = _sb_s.table("sistem_tanimlar").select("id,sira").eq("tip","asama").eq("deger",_a).execute()
                                    _r2 = _sb_s.table("sistem_tanimlar").select("id,sira").eq("tip","asama").eq("deger",_mevcut_asamalar[_ai+1]).execute()
                                    if _r1.data and _r2.data:
                                        _s1, _s2 = _r1.data[0]["sira"], _r2.data[0]["sira"]
                                        _sb_s.table("sistem_tanimlar").update({"sira":_s2}).eq("id",_r1.data[0]["id"]).execute()
                                        _sb_s.table("sistem_tanimlar").update({"sira":_s1}).eq("id",_r2.data[0]["id"]).execute()
                            except: pass
                            st.rerun()
                    else:
                        _ac3.caption("")
            
                    if _ac4.button("✏️", key=f"asm_duz_{_ai}", help="Düzenle"):
                        st.session_state[f"asm_edit_{_a}"] = True
            
                    if _adet == 0:
                        if _ac5.button("🗑️", key=f"asm_sil_{_ai}", help="Sil"):
                            if _tanim_sil("asama", _a):
                                st.rerun()
                    else:
                        _ac5.caption("—")
            
                    if st.session_state.get(f"asm_edit_{_a}"):
                        with st.form(f"asm_form_{_a}"):
                            _yeni_asm = st.text_input("Yeni ad:", value=_a, key=f"asm_inp_{_a}")
                            _f1, _f2 = st.columns(2)
                            if _f1.form_submit_button("💾 Kaydet", use_container_width=True):
                                if _yeni_asm and _yeni_asm.strip() != _a:
                                    if _tanim_guncelle("asama", _a, _yeni_asm.strip()):
                                        st.session_state.pop(f"asm_edit_{_a}", None)
                                        st.success(f"✅ '{_a}' → '{_yeni_asm}' güncellendi!")
                                        st.rerun()
                            if _f2.form_submit_button("İptal", use_container_width=True):
                                st.session_state.pop(f"asm_edit_{_a}", None)
                                st.rerun()
            
            # ── DURUM YÖNETİMİ ────────────────────────────────────────────────────
            with yc2:
                st.markdown("**📊 Durum Yönetimi**")
            
                _mevcut_durumlar = _tanimlar_yukle("durum")
            
                # Yeni durum ekle
                _yd1, _yd2 = st.columns([3,1])
                _yeni_d = _yd1.text_input("", key="yeni_durum_ekle",
                    placeholder="Yeni durum adı...", label_visibility="collapsed")
                if _yd2.button("➕ Ekle", key="durum_ekle_sb", use_container_width=True):
                    if _yeni_d and _yeni_d.strip():
                        if _yeni_d.strip() in _mevcut_durumlar:
                            st.warning("Bu durum zaten var!")
                        elif _tanim_ekle("durum", _yeni_d.strip()):
                            st.success(f"✅ '{_yeni_d}' eklendi!")
                            st.rerun()
                        else:
                            st.error("Eklenemedi!")
            
                st.caption("Tüm durumlar — sırala:")
                for _di, _d in enumerate(_mevcut_durumlar):
                    _dadet = len(df[df["durum"]==_d]) if not df.empty and "durum" in df.columns else 0
                    _dc1, _dc2, _dc3, _dc4, _dc5 = st.columns([3,1,1,1,1])
                    _dc1.caption(f"{'🔹' if _dadet>0 else '⬜'} **{_d}** ({_dadet})")
            
                    # Sırala ▲▼
                    if _di > 0:
                        if _dc2.button("▲", key=f"dur_up_{_di}", help="Yukarı"):
                            try:
                                _sb_sd = get_sb_client()
                                if _sb_sd:
                                    _r1 = _sb_sd.table("sistem_tanimlar").select("id,sira").eq("tip","durum").eq("deger",_d).execute()
                                    _r2 = _sb_sd.table("sistem_tanimlar").select("id,sira").eq("tip","durum").eq("deger",_mevcut_durumlar[_di-1]).execute()
                                    if _r1.data and _r2.data:
                                        _s1, _s2 = _r1.data[0]["sira"], _r2.data[0]["sira"]
                                        _sb_sd.table("sistem_tanimlar").update({"sira":_s2}).eq("id",_r1.data[0]["id"]).execute()
                                        _sb_sd.table("sistem_tanimlar").update({"sira":_s1}).eq("id",_r2.data[0]["id"]).execute()
                            except: pass
                            st.rerun()
                    else:
                        _dc2.caption("")
            
                    if _di < len(_mevcut_durumlar)-1:
                        if _dc3.button("▼", key=f"dur_dn_{_di}", help="Aşağı"):
                            try:
                                _sb_sd = get_sb_client()
                                if _sb_sd:
                                    _r1 = _sb_sd.table("sistem_tanimlar").select("id,sira").eq("tip","durum").eq("deger",_d).execute()
                                    _r2 = _sb_sd.table("sistem_tanimlar").select("id,sira").eq("tip","durum").eq("deger",_mevcut_durumlar[_di+1]).execute()
                                    if _r1.data and _r2.data:
                                        _s1, _s2 = _r1.data[0]["sira"], _r2.data[0]["sira"]
                                        _sb_sd.table("sistem_tanimlar").update({"sira":_s2}).eq("id",_r1.data[0]["id"]).execute()
                                        _sb_sd.table("sistem_tanimlar").update({"sira":_s1}).eq("id",_r2.data[0]["id"]).execute()
                            except: pass
                            st.rerun()
                    else:
                        _dc3.caption("")
            
                    if _dc4.button("✏️", key=f"dur_duz_{_di}", help="Düzenle"):
                        st.session_state[f"dur_edit_{_d}"] = True
            
                    if _dadet == 0:
                        if _dc5.button("🗑️", key=f"dur_sil_{_di}", help="Sil"):
                            if _tanim_sil("durum", _d):
                                st.rerun()
                    else:
                        _dc5.caption("—")
            
                    if st.session_state.get(f"dur_edit_{_d}"):
                        with st.form(f"dur_form_{_d}"):
                            _yeni_dur = st.text_input("Yeni ad:", value=_d, key=f"dur_inp_{_d}")
                            _f1, _f2 = st.columns(2)
                            if _f1.form_submit_button("💾 Kaydet", use_container_width=True):
                                if _yeni_dur and _yeni_dur.strip() != _d:
                                    if _tanim_guncelle("durum", _d, _yeni_dur.strip()):
                                        st.session_state.pop(f"dur_edit_{_d}", None)
                                        st.success(f"✅ '{_d}' → '{_yeni_dur}' güncellendi!")
                                        st.rerun()
                            if _f2.form_submit_button("İptal", use_container_width=True):
                                st.session_state.pop(f"dur_edit_{_d}", None)
                                st.rerun()
            
            
            
            st.divider()
            
        elif _yt_sec == "📊 Rapor & Durum Yönetimi":
            _sb_yt2 = get_sb_client()
            try:
                if _sb_yt2:
                    _res_yt2 = _sb_yt2.table("cari_kartlar").select("*").neq("silindi",1).execute()
                    df = pd.DataFrame(_res_yt2.data) if _res_yt2.data else pd.DataFrame()
                else:
                    raise Exception()
            except:
                df = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi='0' OR silindi IS NULL")
            sb_liste = _sb_yt2
            tum_asama_opts = _tanimlar_yukle("asama")
            tum_durum_opts = _tanimlar_yukle("durum")
            df_f = df.copy()

            # ── SAYFA RAPORU ─────────────────────────────────────────────────────────

            # ── VERİ HAZIRLA — silinmiş kayıtlar hariç ──────────────────────────
            _df_r = df.copy()
            # silindi=1 olanları çıkar
            if "silindi" in _df_r.columns:
                _df_r = _df_r[~_df_r["silindi"].astype(str).isin(["1","True"])]

            # ── ÜST METRİKLER ────────────────────────────────────────────────────
            rm1,rm2,rm3,rm4 = st.columns(4)
            rm1.metric("Toplam", len(_df_r))
            rm2.metric("Beklenen", fmt_para(_df_r["beklenen_ciro"].sum()) if "beklenen_ciro" in _df_r.columns else "—")
            rm3.metric("Gerçekleşen", fmt_para(_df_r["gerceklesen_ciro"].sum()) if "gerceklesen_ciro" in _df_r.columns else "—")
            rm4.metric("Filtrede", len(df_f))

            st.divider()

            # ── DURUM YÖNETİMİ — Supabase'e kaydet ─────────────────────────────
            _sb_r = get_sb_client()

            def _durum_yukle():
                try:
                    if _sb_r:
                        _res = _sb_r.table("kullanici_tercih").select("deger")                         .eq("kullanici","__sistem__").eq("anahtar","ekstra_durumlar").execute()
                        if _res.data:
                            import json as _jd
                            return _jd.loads(_res.data[0]["deger"])
                except: pass
                return []

            def _durum_kaydet(liste):
                try:
                    import json as _jd
                    _veri = _jd.dumps(liste, ensure_ascii=False)
                    if _sb_r:
                        _sb_r.table("kullanici_tercih").upsert({
                            "kullanici":"__sistem__",
                            "anahtar":"ekstra_durumlar",
                            "deger":_veri
                        }, on_conflict="kullanici,anahtar").execute()
                except: pass

            _ekstra_durumlar = _durum_yukle()
            _varsayilan = _tanimlar_yukle("durum") or ["Özel Müşteri","Portföy"]
            _tum_durumlar = _varsayilan.copy()
            for _d in _ekstra_durumlar:
                if _d not in _tum_durumlar:
                    _tum_durumlar.append(_d)

            # ── AŞAMA + DURUM TABLOLARI ──────────────────────────────────────────
            col_asama, col_durum = st.columns(2)

            with col_asama:
                st.markdown("**🔄 Aşama Dağılımı**")
                if "islem_asamasi" in _df_r.columns:
                    _adf = _df_r[
                        _df_r["islem_asamasi"].notna() &
                        (_df_r["islem_asamasi"].astype(str).str.strip() != "") &
                        (_df_r["islem_asamasi"].astype(str) != "nan")
                    ].groupby("islem_asamasi").agg(
                        Firma=("firma","count"),
                        Beklenen=("beklenen_ciro","sum"),
                        Gerceklesen=("gerceklesen_ciro","sum")
                    ).reset_index().sort_values("Firma", ascending=False)

                    if not _adf.empty:
                        _adf["Başarı%"] = _adf.apply(
                            lambda r: f"%{r['Gerceklesen']/r['Beklenen']*100:.0f}"
                            if r["Beklenen"]>0 else "—", axis=1)
                        _adf["Beklenen"]    = _adf["Beklenen"].apply(fmt_para)
                        _adf["Gerceklesen"] = _adf["Gerceklesen"].apply(fmt_para)
                        st.dataframe(
                            _adf.rename(columns={"islem_asamasi":"Aşama","Firma":"Firma"}),
                            use_container_width=True, hide_index=True
                        )
                    else:
                        st.caption("Henüz aşama verisi yok")

            with col_durum:
                st.markdown("**📊 Durum Dağılımı**")
                if "durum" in _df_r.columns:
                    _ddf = _df_r[
                        _df_r["durum"].notna() &
                        (_df_r["durum"].astype(str).str.strip() != "") &
                        (_df_r["durum"].astype(str) != "nan")
                    ].groupby("durum").agg(
                        Firma=("firma","count"),
                        Beklenen=("beklenen_ciro","sum"),
                        Gerceklesen=("gerceklesen_ciro","sum")
                    ).reset_index().sort_values("Firma", ascending=False)

                    if not _ddf.empty:
                        _ddf["Beklenen"]    = _ddf["Beklenen"].apply(fmt_para)
                        _ddf["Gerceklesen"] = _ddf["Gerceklesen"].apply(fmt_para)
                        st.dataframe(
                            _ddf.rename(columns={"durum":"Durum","Firma":"Firma"}),
                            use_container_width=True, hide_index=True
                        )
                    else:
                        st.caption("Henüz durum verisi yok")

                # Durum ekle/sil
                st.markdown("**⚙️ Durum Ekle / Sil:**")
                _dc1, _dc2 = st.columns([3,1])
                _yeni_d = _dc1.text_input("", placeholder="VIP, Potansiyel...", key="yeni_durum_inp", label_visibility="collapsed")
                if _dc2.button("➕", key="durum_ekle_btn", use_container_width=True):
                    if _yeni_d and _yeni_d.strip() and _yeni_d.strip() not in _tum_durumlar:
                        _ekstra_durumlar.append(_yeni_d.strip())
                        _durum_kaydet(_ekstra_durumlar)
                        st.success(f"✅ '{_yeni_d}' eklendi!")
                        st.rerun()
                    elif _yeni_d.strip() in _tum_durumlar:
                        st.warning("Bu durum zaten var!")

                # Mevcut durumları listele
                for _d in _tum_durumlar:
                    _adet = len(_df_r[_df_r["durum"].astype(str)==_d]) if "durum" in _df_r.columns else 0
                    if _adet > 0:  # VERİ OLANLAR
                        _lc1, _lc2 = st.columns([4,1])
                        _lc1.caption(f"🔹 **{_d}** — {_adet} firma")
                        if _d not in _varsayilan:
                            if _lc2.button("🗑️", key=f"dsil_v_{_d[:10]}", help="Sil (önce veri silinmeli)"):
                                st.warning(f"'{_d}' durumunda {_adet} firma var, önce firmalar başka duruma taşınmalı!")
                        else:
                            _lc2.caption("—")
                    # VERİ OLMAYANLAR — ekstra ise silinebilir
                    elif _d in _ekstra_durumlar:
                        _lc1, _lc2 = st.columns([4,1])
                        _lc1.caption(f"⬜ {_d} — 0 firma")
                        if _lc2.button("🗑️", key=f"dsil_e_{_d[:10]}"):
                            _ekstra_durumlar.remove(_d)
                            _durum_kaydet(_ekstra_durumlar)
                            st.rerun()

            st.divider()

            # ── TEMSİLCİ + İL ────────────────────────────────────────────────────
            _tc1, _tc2 = st.columns(2)
            with _tc1:
                st.markdown("**👤 Temsilci:**")
                if "temsilci" in _df_r.columns:
                    _tdf = _df_r[
                        _df_r["temsilci"].notna() &
                        (_df_r["temsilci"].astype(str).str.strip() != "") &
                        (_df_r["temsilci"].astype(str) != "nan")
                    ].groupby("temsilci").agg(Firma=("firma","count")).reset_index().sort_values("Firma",ascending=False).head(10)
                    if not _tdf.empty:
                        st.dataframe(_tdf.rename(columns={"temsilci":"Temsilci","Firma":"Firma"}),
                                     use_container_width=True, hide_index=True)
            with _tc2:
                st.markdown("**🗺️ İl:**")
                if "il" in _df_r.columns:
                    _idf = _df_r[
                        _df_r["il"].notna() &
                        (_df_r["il"].astype(str).str.strip() != "") &
                        (_df_r["il"].astype(str) != "nan")
                    ].groupby("il").agg(Firma=("firma","count")).reset_index().sort_values("Firma",ascending=False).head(10)
                    if not _idf.empty:
                        st.dataframe(_idf.rename(columns={"il":"İl","Firma":"Firma"}),
                                     use_container_width=True, hide_index=True)

            # ── EXCEL ─────────────────────────────────────────────────────────────
            _buf_rp = __import__("io").BytesIO()
            df.to_excel(_buf_rp, index=False); _buf_rp.seek(0)
            st.download_button("📥 Excel'e Aktar", data=_buf_rp,
                file_name=f"cari_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                use_container_width=True, key="liste_excel_indir")



        elif _yt_sec == "📨 Firma Not Arşivi":
            _sb_yt3 = get_sb_client()
            sb_liste = _sb_yt3

            # ── 📨 NOT ARŞİVİ — tıkla aç ─────────────────────────────────────────────
            st.markdown("#### 📨 Firma Not Arşivi")
            st.caption("Açıklama sütununa yaz → Kaydet → not arşivlenir. Aşağıdan firmayı seç → notlarını gör.")

            # Not olan firmaları getir
            _df_notlu = pd.DataFrame()
            if sb_liste:
                try:
                    _rn = sb_liste.table("cari_aciklamalar").select("cari_id,aciklama").execute()
                    if _rn.data:
                        import collections as _col
                        _rn_data_filtreli = [r for r in _rn.data if not str(r.get("aciklama","") or "").startswith("##YETKILI##")]
                        _sayac = _col.Counter([r["cari_id"] for r in _rn_data_filtreli])
                        # NOT: cari_aciklamalar'da "cari_adi" kolonu yok — firma adını
                        # cari_kartlar'dan eşleştiriyoruz.
                        _cari_ad_map = {}
                        try:
                            _df_ck_map = db_read("cari_kartlar")
                            if not _df_ck_map.empty and "id" in _df_ck_map.columns and "firma" in _df_ck_map.columns:
                                _cari_ad_map = dict(zip(_df_ck_map["id"], _df_ck_map["firma"]))
                        except Exception:
                            pass
                        _df_notlu = pd.DataFrame([
                            {"cari_id": k, "firma": _cari_ad_map.get(k, f"#{k}"), "not_sayi": v}
                            for k, v in _sayac.items()
                        ]).sort_values("not_sayi", ascending=False)
                except:
                    pass

            if _df_notlu.empty:
                st.info("Henüz arşivlenmiş not yok. Açıklama sütununa yaz ve kaydet.")
            else:
                # Firma seç
                _firma_opts = [f"📨{r['not_sayi']}  {r['firma']}" for _, r in _df_notlu.iterrows()]
                _sec = st.selectbox("Firma seç:", _firma_opts, key="not_arsiv_sec")
                _sec_idx = _firma_opts.index(_sec)
                _sec_cari_id = int(_df_notlu.iloc[_sec_idx]["cari_id"])
                _sec_firma = str(_df_notlu.iloc[_sec_idx]["firma"])

                # Seçili firmanın notlarını çek
                try:
                    _rnotlar = sb_liste.table("cari_aciklamalar").select("*").eq("cari_id", _sec_cari_id).order("id", desc=True).execute()
                    _df_notlar = pd.DataFrame(_rnotlar.data) if _rnotlar.data else pd.DataFrame()
                    if not _df_notlar.empty and "aciklama" in _df_notlar.columns:
                        _df_notlar = _df_notlar[~_df_notlar["aciklama"].astype(str).str.startswith("##YETKILI##")]
                except:
                    _df_notlar = pd.DataFrame()

                st.markdown(f"**{_sec_firma} — {len(_df_notlar)} not:**")

                if not _df_notlar.empty:
                    for _, _nr in _df_notlar.iterrows():
                        _nid   = _nr.get("id", 0)
                        _ntarih = fmt_tarih(str(_nr.get("created_at","") or _nr.get("tarih","") or ""))
                        _nkim  = str(_nr.get("olusturan",""))
                        _nmetin = str(_nr.get("aciklama",""))
                        _nozet = _nmetin[:60] + ("..." if len(_nmetin)>60 else "")
                        with st.expander(f"📅 {_ntarih}  👤 {_nkim}  —  {_nozet}"):
                            st.markdown(
                                f"<div style='background:#f0f4ff;border-left:4px solid #1f6feb;"
                                f"padding:12px 16px;border-radius:6px;line-height:1.7'>"
                                f"{_nmetin.replace(chr(10),'<br>')}"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                            if st.button("🗑️ Sil", key=f"narsil_{_nid}"):
                                try:
                                    sb_liste.table("cari_aciklamalar").delete().eq("id", int(_nid)).execute()
                                    st.rerun()
                                except: pass

            st.divider()

    with r_tab_rut:
        st.markdown("### 🗺️ Günlük Rut Haritası")
        import streamlit.components.v1 as _rut_comp
        import json as _rj

        _rc1, _rc2, _rc3 = st.columns([1,1,2])
        _rut_tarih = _rc1.date_input("Tarih", value=datetime.now().date(), key="rut_tarih")
        _rut_tem_list = ["Tüm Temsilciler"]
        if not df_rand_all.empty and "temsilci" in df_rand_all.columns:
            _rut_tem_list += sorted(df_rand_all["temsilci"].dropna().unique().tolist())
        _rut_tem = _rc2.selectbox("Temsilci", _rut_tem_list, key="rut_tem")

        # Başlangıç konumu
        _bas_konum_tipi = _rc3.selectbox("🏁 Başlangıç Konumu",
            ["— Seçiniz —", "📍 Mevcut Konumumu Kullan", "🏢 Ofis / Manuel Adres"],
            key="rut_bas_tip")

        _bas_lat, _bas_lng, _bas_adi = None, None, ""
        if _bas_konum_tipi == "📍 Mevcut Konumumu Kullan":
            st.info("📍 Harita açılınca sağ üstteki **📍 Konumumu Kullan** butonuna basın.")
        elif _bas_konum_tipi == "🏢 Ofis / Manuel Adres":
            _ba1, _ba2, _ba3 = st.columns(3)
            _bas_adi  = _ba1.text_input("Başlangıç adı", value=st.session_state.get("rut_bas_adi","Ofis"), key="rut_bas_adi")
            _bas_ilce = _ba2.text_input("İlçe", value=st.session_state.get("rut_bas_ilce",""), key="rut_bas_ilce")
            _bas_il   = _ba3.text_input("İl", value=st.session_state.get("rut_bas_il","İstanbul"), key="rut_bas_il")

        # Seçili tarihin randevularını filtrele — gelecek ve bugün
        _rut_df = df_rand_all.copy()
        if "randevu_tarihi" in _rut_df.columns:
            _rut_df = _rut_df[_rut_df["randevu_tarihi"].astype(str).str[:10] == str(_rut_tarih)]
        if _rut_tem != "Tüm Temsilciler" and "temsilci" in _rut_df.columns:
            _rut_df = _rut_df[_rut_df["temsilci"] == _rut_tem]
        if "randevu_saati" in _rut_df.columns:
            _rut_df = _rut_df.sort_values("randevu_saati")

        # İlçe koordinatları
        _RUT_ILCE = {
            "tuzla":[40.821,29.310],"pendik":[40.876,29.256],"kartal":[40.889,29.183],
            "maltepe":[40.933,29.150],"ataşehir":[40.982,29.120],"kadıköy":[40.990,29.030],
            "üsküdar":[41.022,29.025],"beykoz":[41.118,29.097],"ümraniye":[41.015,29.124],
            "çekmeköy":[41.034,29.172],"sancaktepe":[41.000,29.231],"sultanbeyli":[40.963,29.262],
            "gebze":[40.800,29.432],"izmit":[40.764,29.917],"darıca":[40.760,29.570],
            "dilovası":[40.753,29.528],"körfez":[40.745,29.787],"kocaeli":[40.765,29.940],
            "fatih":[41.013,28.940],"beyoğlu":[41.031,28.975],"şişli":[41.058,28.985],
            "beşiktaş":[41.042,29.009],"sarıyer":[41.166,29.053],"bakırköy":[40.979,28.875],
            "bağcılar":[41.042,28.855],"bahçelievler":[41.000,28.858],"zeytinburnu":[40.999,28.900],
            "küçükçekmece":[41.003,28.778],"avcılar":[40.979,28.720],"esenyurt":[41.033,28.668],
            "beylikdüzü":[40.981,28.642],"büyükçekmece":[41.019,28.583],"silivri":[41.072,28.243],
            "başakşehir":[41.090,28.800],"eyüpsultan":[41.073,28.935],"gaziosmanpaşa":[41.065,28.906],
            "sultangazi":[41.105,28.872],"arnavutköy":[41.182,28.735],"çatalca":[41.143,28.459],
            "nilüfer":[40.213,28.963],"osmangazi":[40.196,29.057],"yıldırım":[40.189,29.100],
            "çerkezköy":[41.289,27.988],"çorlu":[41.160,27.801],"lüleburgaz":[41.404,27.351],
        }
        _RUT_IL = {
            "istanbul":[41.050,28.900],"kocaeli":[40.765,29.940],"bursa":[40.183,29.067],
            "ankara":[39.920,32.854],"izmir":[38.423,27.143],"tekirdağ":[40.978,27.515],
            "sakarya":[40.769,30.394],"gebze":[40.800,29.432],
        }

        def _tr_low(s):
            return (s.replace("İ","i").replace("I","ı").replace("Ş","ş").replace("Ğ","ğ")
                     .replace("Ü","ü").replace("Ö","ö").replace("Ç","ç").lower().strip())

        # Pin listesi oluştur
        _rut_pins = []
        import random as _rnd, hashlib as _rh
        for _idx, (_, _rr) in enumerate(_rut_df.iterrows()):
            _firma = str(_rr.get("musteri_adi","") or "?")
            _saat  = str(_rr.get("randevu_saati","") or "")[:5]
            _bolge = str(_rr.get("bolge","") or "")
            _gorev = str(_rr.get("gorev","") or "Ziyaret")
            _sonuc = str(_rr.get("sonuc","") or "")
            _tem   = str(_rr.get("temsilci","") or "")
            _aciklama = str(_rr.get("aciklama","") or "")

            # Bölgeden il/ilçe çıkar
            _bolge_lower = _tr_low(_bolge)
            _lat, _lng = None, None
            for _k,_v in _RUT_ILCE.items():
                if _k in _bolge_lower:
                    _lat,_lng = _v; break
            if _lat is None:
                for _k,_v in _RUT_IL.items():
                    if _k in _bolge_lower:
                        _lat,_lng = _v; break
            if _lat is None:
                _lat,_lng = 41.050,28.900  # default İstanbul

            _rnd.seed(int(_rh.md5(_firma.encode()).hexdigest()[:8],16))
            _lat += _rnd.uniform(-0.005,0.005)
            _lng += _rnd.uniform(-0.005,0.005)

            _rut_pins.append({
                "idx":_idx+1,"lat":round(_lat,5),"lng":round(_lng,5),
                "firma":_firma.replace("'","&#39;"),
                "saat":_saat,"bolge":_bolge.replace("'","&#39;"),
                "gorev":_gorev,"sonuc":_sonuc,"tem":_tem,
                "aciklama":_aciklama.replace("'","&#39;")[:80]
            })

        _pins_json = _rj.dumps(_rut_pins, ensure_ascii=False)
        _tarih_str = _rut_tarih.strftime("%d %B %Y")

        # Başlangıç konumu — manuel adres ile koordinat bul
        _bas_pin_json = "null"
        if _bas_konum_tipi == "🏢 Ofis / Manuel Adres":
            _bas_ilce_v = _tr_low(st.session_state.get("rut_bas_ilce",""))
            _bas_il_v   = _tr_low(st.session_state.get("rut_bas_il","istanbul"))
            _bas_lat_v, _bas_lng_v = None, None
            if _bas_ilce_v and _bas_ilce_v in _RUT_ILCE:
                _bas_lat_v, _bas_lng_v = _RUT_ILCE[_bas_ilce_v]
            elif _bas_il_v and _bas_il_v in _RUT_IL:
                _bas_lat_v, _bas_lng_v = _RUT_IL[_bas_il_v]
            if _bas_lat_v:
                _bas_pin_json = _rj.dumps({
                    "lat": _bas_lat_v, "lng": _bas_lng_v,
                    "adi": st.session_state.get("rut_bas_adi","Ofis")
                }, ensure_ascii=False)

        if not _rut_pins:
            st.info(f"📅 {_tarih_str} tarihinde randevu bulunamadı.")
        else:
            st.caption(f"📅 {_tarih_str} · {len(_rut_pins)} randevu")

            _rut_html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,sans-serif;}
body{display:grid;grid-template-columns:1fr 280px;height:520px;overflow:hidden;}
#map{height:520px;}
#sidebar{height:520px;overflow-y:auto;border-left:0.5px solid #e2e8f0;display:flex;flex-direction:column;}
.s-hdr{padding:9px 12px;background:#f8fafc;border-bottom:0.5px solid #e2e8f0;font-size:11px;font-weight:600;color:#64748b;flex-shrink:0;}
.s-list{flex:1;overflow-y:auto;}
.s-item{display:flex;align-items:flex-start;gap:8px;padding:9px 12px;border-bottom:0.5px solid #f1f5f9;cursor:pointer;transition:.1s;}
.s-item:hover{background:#fef2f2;}
.s-item.act{background:#fef2f2;border-left:3px solid #dc2626;}
.s-num{width:24px;height:24px;border-radius:50%;background:#dc2626;color:white;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;}
.s-inf{flex:1;min-width:0;}
.s-saat{font-size:12px;font-weight:700;color:#dc2626;}
.s-firma{font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.s-bolge{font-size:10px;color:#64748b;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.s-foot{padding:8px;border-top:0.5px solid #e2e8f0;display:flex;gap:5px;flex-shrink:0;}
.btn{flex:1;padding:7px;border:none;border-radius:7px;font-size:11px;font-weight:500;cursor:pointer;}
.btn-m{background:#1d4ed8;color:white;}
.btn-w{background:#25d366;color:white;}
.pp{font-family:-apple-system,sans-serif;}
.pp-hdr{background:#dc2626;color:white;padding:8px 12px;margin:-8px -12px 8px;border-radius:3px 3px 0 0;font-weight:600;font-size:13px;}
.pp table{font-size:11px;width:100%;border-collapse:collapse;}
.pp td{padding:3px 4px;} .pp td:first-child{color:#94a3b8;width:65px;}
.pp td:last-child{font-weight:500;}
</style></head>
<body>
<div id="map"></div>
<div id="sidebar">
  <div class="s-hdr">📋 """ + _tarih_str + """ · """ + str(len(_rut_pins)) + """ randevu</div>
  <div class="s-list" id="slist"></div>
  <div class="s-foot">
    <button class="btn btn-m" onclick="mapsAc()">🗺️ Navigasyon</button>
    <button class="btn btn-w" onclick="waGonder()">💬 WA</button>
  </div>
</div>
<script>
var pins = """ + _pins_json + """;
var basPinData = """ + _bas_pin_json + """;
var map = L.map('map').setView([40.9,29.1],11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap',maxZoom:18}).addTo(map);
var markers=[], latlngs=[], rutLine=null, arrowMarkers=[], basMarker=null;

// Konumumu Kullan butonu
var locBtn = L.control({position:'topright'});
locBtn.onAdd=function(){
  var d=L.DomUtil.create('button','');
  d.innerHTML='📍 Konumumu Kullan';
  d.style.cssText='background:white;border:1px solid #ccc;border-radius:6px;padding:6px 12px;cursor:pointer;font-size:12px;font-weight:600;';
  d.onclick=function(){
    if(navigator.geolocation){
      navigator.geolocation.getCurrentPosition(function(pos){
        basPinEkle(pos.coords.latitude,pos.coords.longitude,'Ben');
        map.setView([pos.coords.latitude,pos.coords.longitude],13);
      },function(){alert('Konum alınamadı. Tarayıcı iznini kontrol edin.');});
    }else{alert('Tarayıcınız konum desteklemiyor.');}
  };
  return d;
};
locBtn.addTo(map);

function basPinEkle(lat,lng,adi){
  if(basMarker) map.removeLayer(basMarker);
  var svg='<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">'
    +'<path d="M17 0C7.6 0 0 7.6 0 17c0 12.7 17 27 17 27s17-14.3 17-27C34 7.6 26.4 0 17 0z" fill="#16a34a" stroke="white" stroke-width="2"/>'
    +'<circle cx="17" cy="17" r="10" fill="white"/>'
    +'<text x="17" y="21" text-anchor="middle" fill="#16a34a" font-size="11" font-weight="700">🏁</text></svg>';
  var ic=L.divIcon({html:svg,className:'',iconSize:[34,44],iconAnchor:[17,44],popupAnchor:[0,-46]});
  basMarker=L.marker([lat,lng],{icon:ic}).bindPopup('<b>🏁 '+adi+'</b><br>Başlangıç').addTo(map);
}
if(basPinData){ basPinEkle(basPinData.lat,basPinData.lng,basPinData.adi); }

// Liste oluştur
var html='';
pins.forEach(function(p,i){
  html+='<div class="s-item" id="si'+i+'" onclick="secPin('+i+')">'
    +'<div class="s-num">'+p.idx+'</div>'
    +'<div class="s-inf">'
    +'<div class="s-saat">'+p.saat+'</div>'
    +'<div class="s-firma">'+p.firma+'</div>'
    +'<div class="s-bolge">📍 '+p.bolge+'</div>'
    +'</div></div>';
});
document.getElementById('slist').innerHTML=html;

// Pinler ve rut
pins.forEach(function(p,i){
  latlngs.push([p.lat,p.lng]);
  var svg='<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">'
    +'<path d="M17 0C7.6 0 0 7.6 0 17c0 12.7 17 27 17 27s17-14.3 17-27C34 7.6 26.4 0 17 0z" fill="#dc2626" stroke="white" stroke-width="2"/>'
    +'<circle cx="17" cy="17" r="10" fill="white"/>'
    +'<text x="17" y="22" text-anchor="middle" fill="#dc2626" font-size="12" font-weight="700">'+p.idx+'</text>'
    +'</svg>';
  var ic=L.divIcon({html:svg,className:'',iconSize:[34,44],iconAnchor:[17,44],popupAnchor:[0,-46]});
  var pop='<div class="pp"><div class="pp-hdr">'+p.idx+'. Durak · '+p.saat+'</div>'
    +'<table><tr><td>Firma</td><td>'+p.firma+'</td></tr>'
    +'<tr><td>Bölge</td><td>'+p.bolge+'</td></tr>'
    +'<tr><td>Görev</td><td>'+p.gorev+'</td></tr>'
    +'<tr><td>Temsilci</td><td>'+p.tem+'</td></tr>'
    +(p.aciklama?'<tr><td>Not</td><td>'+p.aciklama+'</td></tr>':'')
    +'</table></div>';
  var m=L.marker([p.lat,p.lng],{icon:ic}).bindPopup(pop,{maxWidth:260}).addTo(map);
  m.on('click',function(){secPin(i);});
  markers.push(m);
});

// Rut çizgisi
rutLine=L.polyline(latlngs,{color:'#dc2626',weight:3,dashArray:'8,5',opacity:0.8}).addTo(map);

// Oklar
for(var i=0;i<latlngs.length-1;i++){
  var f=latlngs[i],t=latlngs[i+1];
  var ml=(f[0]+t[0])/2, mn=(f[1]+t[1])/2;
  var ang=Math.atan2(t[1]-f[1],t[0]-f[0])*180/Math.PI;
  var asvg='<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18" style="transform:rotate('+ang+'deg)">'
    +'<polygon points="0,4 0,14 18,9" fill="#dc2626" opacity="0.85"/></svg>';
  L.marker([ml,mn],{icon:L.divIcon({html:asvg,className:'',iconSize:[18,18],iconAnchor:[9,9]}),interactive:false}).addTo(map);
}

if(latlngs.length>0) map.fitBounds(L.latLngBounds(latlngs),{padding:[40,40]});

function secPin(i){
  document.querySelectorAll('.s-item').forEach(function(el,j){el.classList.toggle('act',j===i);});
  map.setView([pins[i].lat,pins[i].lng],14);
  markers[i].openPopup();
}

function mapsAc(){
  if(pins.length===0) return;
  var origin = basPinData ? basPinData.lat+','+basPinData.lng : (basMarker ? basMarker.getLatLng().lat+','+basMarker.getLatLng().lng : pins[0].lat+','+pins[0].lng);
  var d=pins[pins.length-1].lat+','+pins[pins.length-1].lng;
  var wp=pins.slice(basPinData||basMarker?0:1,-1).map(function(p){return p.lat+','+p.lng;}).join('|');
  window.open('https://www.google.com/maps/dir/?api=1&origin='+origin+'&destination='+d+(wp?'&waypoints='+wp:'')+'&travelmode=driving','_blank');
}

function waGonder(){
  var msg='🗺️ *Rut Planı — """ + _tarih_str + """*\\n\\n';
  pins.forEach(function(p){msg+=p.idx+'. '+p.saat+' — *'+p.firma+'*\\n📍 '+p.bolge+'\\n\\n';});
  alert('WhatsApp gönderimi geçici olarak devre dışı.');
}
</script></body></html>"""

            _rut_comp.html(_rut_html, height=525, scrolling=False)

elif aktif == "admin_rapor":
    sayfa_log("admin_rapor")

    import json as _arj
    import io as _ario

    st.markdown("## 📊 Rapor Tasarla")
    st.caption("Veri kaynağı seç → Sütunları seç → Filtrele → Sırala → Kaydet → Excel/CSV indir")

    _ar_sb  = get_sb_client()
    _ar_kul = st.session_state.get("kullanici", "admin")

    # ── KAYDET / YÜKLE FONKSİYONLARI ────────────────────────────────────────
    def _ar_yukle():
        try:
            if _ar_sb:
                r = _ar_sb.table("kullanici_tercih").select("deger") \
                    .eq("kullanici", _ar_kul).eq("anahtar", "rapor_tasarimlari").execute()
                if r.data:
                    return _arj.loads(r.data[0]["deger"])
            else:
                c = get_conn()
                row = c.execute("SELECT deger FROM kullanici_tercih WHERE kullanici=? AND anahtar='rapor_tasarimlari'",
                                (_ar_kul,)).fetchone()
                c.close()
                if row: return _arj.loads(row[0])
        except: pass
        return {}

    def _ar_kaydet(raporlar):
        try:
            veri = _arj.dumps(raporlar, ensure_ascii=False)
            if _ar_sb:
                _ar_sb.table("kullanici_tercih").upsert(
                    {"kullanici": _ar_kul, "anahtar": "rapor_tasarimlari", "deger": veri},
                    on_conflict="kullanici,anahtar").execute()
            else:
                c = get_conn()
                c.execute("INSERT OR REPLACE INTO kullanici_tercih (kullanici,anahtar,deger) VALUES (?,?,?)",
                          (_ar_kul, "rapor_tasarimlari", veri))
                c.commit(); c.close()
            return True
        except Exception as _e:
            st.error(f"Kayıt hatası: {_e}")
            return False

    # ── VERİ YÜKLE — CACHE YOK, HER ZAMAN TAZE ──────────────────────────────
    _TABLOLAR = {
        "🏢 Cari Kartlar":    "cari_kartlar",
        "📅 Randevular":      "randevular",
        "📄 Teklifler":       "teklifler",
        "📝 Açıklamalar":     "cari_aciklamalar",
        "📋 İşlem Kayıtları": "islem_kaydi",
        "👥 Kullanıcılar":    "kullanicilar",
        "👔 Temsilciler":     "temsilciler",
        "📬 Mesajlar":        "mesajlar",
        "📢 Duyurular":       "duyurular",
    }

    # Sütun başlıkları sözlüğü — tüm tablolardan
    _KOLON_BASLIKLARI = {
        # Cari kartlar
        "id":"ID", "firma":"Firma Adı", "yetkili":"Yetkili", "gsm":"GSM",
        "sabit":"Sabit Tel", "email":"Email", "adres":"Adres",
        "il":"İl", "ilce":"İlçe", "durum":"Durum", "temsilci":"Temsilci",
        "islem_asamasi":"Aşama", "aciklama":"Açıklama",
        "beklenen_ciro":"Beklenen Ciro", "gerceklesen_ciro":"Gerçekleşen Ciro",
        "tarih":"Tarih", "olusturan":"Oluşturan", "silindi":"Silindi",
        # Randevular
        "randevu_tarihi":"Randevu Tarihi", "randevu_saati":"Saat",
        "musteri_id":"Müşteri ID", "musteri_adi":"Müşteri Adı",
        "bolge":"Bölge", "gorev":"Görev", "takip":"Takip",
        "adet":"Adet", "sonuc":"Sonuç", "aciklama":"Açıklama",
        # Kişiler
        "ad":"Ad", "soyad":"Soyad", "telefon":"Telefon",
        "bolge":"Bölge", "kaynak":"Kaynak", "notlar":"Notlar",
        # Teklifler
        "satirlar":"Satırlar", "toplam_tutar":"Toplam Tutar",
        # İşlem kaydı
        "islem_turu":"İşlem Türü", "icerik":"İçerik",
        "gonderim_bilgisi":"Gönderim Bilgisi",
        # Açıklamalar
        "cari_id":"Cari ID", "cari_adi":"Cari Adı",
    }

    def _veri_getir(tablo_adi):
        """Cache yok — her çağrıda taze veri"""
        tbl = _TABLOLAR.get(tablo_adi, "")
        if not tbl: return pd.DataFrame()
        try:
            if _ar_sb:
                # Limit yok — tüm veri
                r = _ar_sb.table(tbl).select("*").execute()
                df = pd.DataFrame(r.data) if r.data else pd.DataFrame()
            else:
                c = get_conn()
                df = pd.read_sql(f"SELECT * FROM {tbl}", c)
                c.close()
            # Sütun adlarını Türkçe göster (opsiyonel)
            return df
        except Exception as _e_vg:
            return pd.DataFrame()

    # ── SESSION STATE BAŞLAT ─────────────────────────────────────────────────
    for _k, _v in [
        ("ar_tablo",   list(_TABLOLAR.keys())[0]),
        ("ar_kolonlar", []),
        ("ar_siralama", ""),
        ("ar_yon",      True),
        ("ar_filtreler", {}),
        ("ar_son_rapor", ""),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    # ── KAYITLI RAPORLAR ─────────────────────────────────────────────────────
    _raporlar = _ar_yukle()

    # Üst toolbar
    tb1, tb2, tb3, tb4 = st.columns([2, 2, 3, 1])

    with tb1:
        st.markdown("**💾 Raporu Kaydet:**")
        _ar_ad = st.text_input("", placeholder="Rapor adı...", key="ar_rapor_adi_inp", label_visibility="collapsed")

    with tb2:
        st.markdown("&nbsp;")
        if st.button("💾 Kaydet", use_container_width=True, type="primary", key="ar_kaydet_btn"):
            _ad = st.session_state.get("ar_rapor_adi_inp","").strip()
            if _ad:
                _raporlar[_ad] = {
                    "tablo":    st.session_state["ar_tablo"],
                    "kolonlar": st.session_state["ar_kolonlar"],
                    "siralama": st.session_state["ar_siralama"],
                    "yon":      st.session_state["ar_yon"],
                }
                if _ar_kaydet(_raporlar):
                    st.session_state["ar_son_rapor"] = _ad
                    st.success(f"✅ '{_ad}' kaydedildi!")
                    st.rerun()
            else:
                st.warning("⚠️ Rapor adı girin!")

    with tb3:
        st.markdown("**📂 Kayıtlı Rapor Yükle:**")
        if _raporlar:
            _sec = st.selectbox("", ["— Seçin —"] + list(_raporlar.keys()),
                                key="ar_yukle_sec", label_visibility="collapsed")
            if _sec != "— Seçin —" and st.button("📂 Yükle", key="ar_yukle_btn", use_container_width=True):
                _r = _raporlar[_sec]
                st.session_state["ar_tablo"]    = _r.get("tablo", list(_TABLOLAR.keys())[0])
                st.session_state["ar_kolonlar"] = _r.get("kolonlar", [])
                st.session_state["ar_siralama"] = _r.get("siralama", "")
                st.session_state["ar_yon"]      = _r.get("yon", True)
                st.success(f"✅ '{_sec}' yüklendi!")
                st.rerun()
            # Sil
            if _raporlar:
                _sil_sec = st.selectbox("Sil:", ["— Seçin —"] + list(_raporlar.keys()), key="ar_sil_sec")
                if _sil_sec != "— Seçin —" and st.button("🗑️ Raporu Sil", key="ar_sil_btn"):
                    del _raporlar[_sil_sec]
                    _ar_kaydet(_raporlar)
                    st.rerun()
        else:
            st.caption("Henüz kayıtlı rapor yok")

    with tb4:
        st.markdown("&nbsp;")
        if st.button("🔄 Yenile", use_container_width=True, key="ar_yenile_btn", help="Verileri yenile"):
            # Tüm cache'leri temizle
            try: db_read.clear()
            except: pass
            st.rerun()

    st.divider()

    # ── ANA TASARIM ALANI ────────────────────────────────────────────────────
    sol, sag = st.columns([1, 3])

    with sol:
        st.markdown("### ⚙️ Tasarım")

        # Veri kaynağı
        st.markdown("**📊 Veri Kaynağı:**")
        _tablo_idx = list(_TABLOLAR.keys()).index(st.session_state["ar_tablo"]) \
                     if st.session_state["ar_tablo"] in _TABLOLAR else 0
        _sec_tablo = st.selectbox("", list(_TABLOLAR.keys()),
                                  index=_tablo_idx, key="ar_tablo",
                                  label_visibility="collapsed")

        # Veriyi getir — cache yok, her zaman taze
        _df_ham = _veri_getir(_sec_tablo)

        if _df_ham.empty:
            st.warning(f"Bu kaynakta veri yok.")
            st.info(f"Tablo: {_TABLOLAR.get(_sec_tablo,'?')}")
        else:
            _tum_kol = list(_df_ham.columns)
            st.caption(f"✅ {len(_df_ham)} satır · {len(_tum_kol)} sütun")

            # Sütun seçimi — Türkçe adlarıyla
            st.markdown("**📌 Sütunlar:**")
            _onceki = [k for k in st.session_state.get("ar_kolonlar",[]) if k in _tum_kol]
            _varsayilan = _onceki if _onceki else _tum_kol[:min(7, len(_tum_kol))]
            _sec_kol = st.multiselect(
                "",
                options=_tum_kol,
                default=_varsayilan,
                format_func=lambda k: _KOLON_BASLIKLARI.get(k, k),
                key="ar_kolonlar",
                label_visibility="collapsed"
            )
            tc1, tc2 = st.columns(2)
            if tc1.button("✅ Tümü", key="ar_tumu", use_container_width=True):
                st.session_state["ar_kolonlar"] = _tum_kol; st.rerun()
            if tc2.button("🗑️ Sıfırla", key="ar_temizle_kol", use_container_width=True):
                st.session_state["ar_kolonlar"] = []; st.rerun()


            # Sıralama
            st.markdown("**🔢 Sırala:**")
            _kol_opts = ["—"] + (_sec_kol if _sec_kol else _tum_kol)
            _sir_idx = _kol_opts.index(st.session_state["ar_siralama"]) \
                       if st.session_state["ar_siralama"] in _kol_opts else 0
            _siralama = st.selectbox("", _kol_opts, index=_sir_idx,
                                     key="ar_siralama", label_visibility="collapsed")
            _yon = st.radio("", ["⬆️ Artan", "⬇️ Azalan"],
                            index=0 if st.session_state.get("ar_yon", True) else 1,
                            horizontal=True, key="ar_yon_radio")
            st.session_state["ar_yon"] = (_yon == "⬆️ Artan")

            # Filtreler
            st.markdown("**🔍 Filtreler:**")
            _aktif_fil = {}
            _fil_kolonlar = _sec_kol[:6] if _sec_kol else _tum_kol[:4]
            for _fk in _fil_kolonlar:
                if _fk not in _df_ham.columns: continue
                _vals = _df_ham[_fk].dropna().astype(str).unique().tolist()
                if len(_vals) <= 15:
                    _f = st.multiselect(f"{_fk}:", _vals, key=f"ar_fil_{_fk}")
                    if _f: _aktif_fil[_fk] = _f
                else:
                    _f = st.text_input(f"{_fk} ara:", key=f"ar_fil_{_fk}", placeholder="...")
                    if _f: _aktif_fil[_fk] = _f

            # Gruplama
            st.markdown("**🧮 Grupla:**")
            _grup = st.selectbox("", ["—"] + (_sec_kol if _sec_kol else []),
                                 key="ar_grup", label_visibility="collapsed")
            _say_kols = [k for k in (_sec_kol if _sec_kol else [])
                         if _df_ham[k].dtype in ['int64','float64']] if _sec_kol else []
            _toplam = []
            if _grup != "—" and _say_kols:
                _toplam = st.multiselect("Toplam:", _say_kols, key="ar_toplam")

    with sag:
        if _df_ham.empty:
            st.info("Sol taraftan veri kaynağı seçin.")
        else:
            # Raporu hazırla
            _df_rapor = _df_ham.copy()

            # Filtre
            for _fk, _fv in _aktif_fil.items():
                if _fk in _df_rapor.columns:
                    if isinstance(_fv, list):
                        _df_rapor = _df_rapor[_df_rapor[_fk].astype(str).isin(_fv)]
                    else:
                        _df_rapor = _df_rapor[_df_rapor[_fk].astype(str).str.contains(_fv, case=False, na=False)]

            # Sütun seç
            if _sec_kol:
                _gkol = [k for k in _sec_kol if k in _df_rapor.columns]
                _df_rapor = _df_rapor[_gkol] if _gkol else _df_rapor

            # Sıralama
            if _siralama != "—" and _siralama in _df_rapor.columns:
                _df_rapor = _df_rapor.sort_values(_siralama, ascending=st.session_state.get("ar_yon", True))

            # Gruplama
            if _grup != "—" and _grup in _df_rapor.columns and _toplam:
                _tl = [k for k in _toplam if k in _df_rapor.columns]
                if _tl:
                    _df_rapor = _df_rapor.groupby(_grup)[_tl].sum().reset_index()

            # Metrikler
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Satır", len(_df_rapor))
            mc2.metric("Sütun", len(_df_rapor.columns))
            mc3.metric("Kaynak", _sec_tablo.split()[1] if len(_sec_tablo.split())>1 else _sec_tablo)
            _son = st.session_state.get("ar_son_rapor","")
            mc4.metric("Aktif Rapor", _son if _son else "—")

            st.markdown(f"**{_sec_tablo} · {len(_df_rapor)} satır**")

            # Düzenlenebilir tablo
            _edited = st.data_editor(
                _df_rapor,
                use_container_width=True,
                num_rows="dynamic",
                key="ar_editor"
            )

            # Alt işlem butonları
            a1, a2, a3, a4 = st.columns(4)

            with a1:
                _buf = _ario.BytesIO()
                _edited.to_excel(_buf, index=False); _buf.seek(0)
                st.download_button("📥 Excel", data=_buf,
                    file_name=f"rapor_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    use_container_width=True)
            with a2:
                st.download_button("📄 CSV",
                    data=_edited.to_csv(index=False).encode("utf-8-sig"),
                    file_name="rapor.csv", mime="text/csv",
                    use_container_width=True)
            with a3:
                if st.button("🔄 Sıfırla", key="ar_sifirla", use_container_width=True):
                    for _k in ["ar_kolonlar","ar_siralama","ar_yon","ar_son_rapor"]:
                        st.session_state.pop(_k, None)
                    st.rerun()
            with a4:
                if st.button("📊 İstatistik", key="ar_istat", use_container_width=True):
                    st.session_state["ar_istat_ac"] = not st.session_state.get("ar_istat_ac", False)

            if st.session_state.get("ar_istat_ac"):
                _skols = [k for k in _edited.columns if pd.api.types.is_numeric_dtype(_edited[k])]
                if _skols:
                    st.dataframe(_edited[_skols].describe().T.round(2), use_container_width=True)
                else:
                    st.info("Sayısal sütun yok.")

            # Kayıtlı raporlar listesi
            if _raporlar:
                with st.expander(f"📂 Kayıtlı Raporlar ({len(_raporlar)})"):
                    for _rn, _rv in list(_raporlar.items()):
                        _r1, _r2 = st.columns([5, 1])
                        _r1.markdown(f"**{_rn}** · {_rv.get('tablo','')} · {len(_rv.get('kolonlar',[]))} sütun")
                        if _r2.button("🗑️", key=f"ar_rsil_{_rn}"):
                            del _raporlar[_rn]
                            _ar_kaydet(_raporlar)
                            st.rerun()



elif aktif == "harita":
    sayfa_log("harita")
    import json as _hj
    st.markdown("## 🗺️ Müşteri Haritası")
    _hdf_raw = db_read("cari_kartlar", extra_sql="ORDER BY firma")
    _hdf_raw = _atama_filtresi_uygula(_hdf_raw)
    if not _hdf_raw.empty and "silindi" in _hdf_raw.columns:
        _hdf = _hdf_raw[~_hdf_raw["silindi"].isin([1, "1", True, "true"])]
    else:
        _hdf = _hdf_raw
    if _hdf.empty:
        st.warning("Cari listede müşteri bulunamadı.")
    else:
        _hc1,_hc2,_hc3,_hc4,_hc5 = st.columns(5)
        _h_il    = _hc1.multiselect("İl filtrele", sorted(_hdf["il"].dropna().unique().tolist()) if "il" in _hdf.columns else [], key="h_il")
        _h_ilce_opts = sorted(_hdf[_hdf["il"].isin(_h_il)]["ilce"].dropna().unique().tolist()) if _h_il and "ilce" in _hdf.columns else (sorted(_hdf["ilce"].dropna().unique().tolist()) if "ilce" in _hdf.columns else [])
        _h_ilce  = _hc2.multiselect("İlçe filtrele", _h_ilce_opts, key="h_ilce")
        _h_durum = _hc3.multiselect("Durum filtrele", sorted(_hdf["durum"].dropna().unique().tolist()) if "durum" in _hdf.columns else [], key="h_durum")
        _h_seg   = _hc4.multiselect("Segment", sorted(_hdf["segment"].dropna().unique().tolist()) if "segment" in _hdf.columns else [], key="h_seg")
        _h_tem   = _hc5.multiselect("Temsilci", sorted(_hdf["temsilci"].dropna().unique().tolist()) if "temsilci" in _hdf.columns else [], key="h_tem")
        _hdf_f = _hdf.copy()
        if _h_il    and "il" in _hdf_f.columns: _hdf_f = _hdf_f[_hdf_f["il"].isin(_h_il)]
        if _h_ilce  and "ilce" in _hdf_f.columns: _hdf_f = _hdf_f[_hdf_f["ilce"].isin(_h_ilce)]
        if _h_durum and "durum" in _hdf_f.columns: _hdf_f = _hdf_f[_hdf_f["durum"].isin(_h_durum)]
        if _h_seg   and "segment" in _hdf_f.columns: _hdf_f = _hdf_f[_hdf_f["segment"].isin(_h_seg)]
        if _h_tem   and "temsilci" in _hdf_f.columns: _hdf_f = _hdf_f[_hdf_f["temsilci"].isin(_h_tem)]
        _il_col = "il" if "il" in _hdf_f.columns else ("sehir" if "sehir" in _hdf_f.columns else None)
        _hm1,_hm2,_hm3,_hm4 = st.columns(4)
        _hm1.metric("Toplam", len(_hdf_f))
        if _il_col:
            _hm2.metric("Aktif İl", int(_hdf_f[_il_col].dropna().nunique()))
            _en_yogun = _hdf_f[_il_col].value_counts().index[0] if not _hdf_f[_il_col].dropna().empty else "—"
            _hm3.metric("En Yoğun", _en_yogun)
        _hm4.metric("Filtrelenen", len(_hdf_f))
        import streamlit.components.v1 as _hcomp
        import json as _hj, random, hashlib

        _il_col = "il" if "il" in _hdf_f.columns else None

        # Randevu verilerini çek
        _rdf = db_read("randevular", extra_sql="ORDER BY randevu_tarihi DESC")
        _rand_acik = set()   # Devam ediyor
        _rand_var  = set()   # Randevu olan (bitti dahil)
        if not _rdf.empty:
            for _, _rr in _rdf.iterrows():
                _mn = str(_rr.get("musteri_adi","") or "").strip()
                if not _mn: continue
                _rand_var.add(_mn)
                if str(_rr.get("sonuc","") or "") in ["Devam Ediyor","","—"] and str(_rr.get("sonuc","") or "") != "Bitti":
                    _rand_acik.add(_mn)

        _IL_KOOR = {
            "adana":[37.000,35.321],"adıyaman":[37.764,38.276],"afyonkarahisar":[38.757,30.540],
            "ağrı":[39.720,43.051],"aksaray":[38.369,34.036],"amasya":[40.655,35.833],
            "ankara":[39.920,32.854],"antalya":[36.897,30.713],"artvin":[41.182,41.818],
            "aydın":[37.856,27.845],"balıkesir":[39.648,27.882],"bartın":[41.635,32.337],
            "batman":[37.881,41.132],"bilecik":[40.142,29.979],"bolu":[40.576,31.579],
            "burdur":[37.720,30.291],"bursa":[40.183,29.067],"çanakkale":[40.144,26.408],
            "çankırı":[40.601,33.613],"çorum":[40.549,34.955],"denizli":[37.774,29.086],
            "diyarbakır":[37.914,40.230],"düzce":[40.844,31.157],"edirne":[41.677,26.556],
            "elazığ":[38.674,39.223],"erzincan":[39.750,39.492],"erzurum":[39.905,41.270],
            "eskişehir":[39.776,30.521],"gaziantep":[37.066,37.383],"giresun":[40.912,38.390],
            "hatay":[36.406,36.341],"ısparta":[37.764,30.556],"istanbul":[41.050,28.900],
            "izmir":[38.423,27.143],"kahramanmaraş":[37.575,36.922],"karabük":[41.200,32.627],
            "karaman":[37.181,33.215],"kars":[40.608,43.097],"kastamonu":[41.376,33.776],
            "kayseri":[38.732,35.487],"kırıkkale":[39.847,33.516],"kırklareli":[41.735,27.225],
            "kırşehir":[39.145,34.160],"kilis":[36.718,37.121],"kocaeli":[40.765,29.940],
            "konya":[37.872,32.485],"kütahya":[39.424,29.983],"malatya":[38.355,38.309],
            "manisa":[38.619,27.429],"mardin":[37.313,40.735],"mersin":[36.812,34.641],
            "muğla":[37.215,28.364],"muş":[38.744,41.501],"nevşehir":[38.625,34.724],
            "niğde":[37.969,34.679],"ordu":[40.984,37.877],"osmaniye":[37.074,36.247],
            "rize":[41.024,40.523],"sakarya":[40.769,30.394],"samsun":[41.286,36.330],
            "sinop":[42.023,35.154],"sivas":[39.748,37.015],"şanlıurfa":[37.158,38.791],
            "şırnak":[37.418,42.491],"tekirdağ":[40.978,27.515],"tokat":[40.313,36.554],
            "trabzon":[41.002,39.716],"tunceli":[39.108,39.547],"uşak":[38.682,29.408],
            "van":[38.494,43.380],"yalova":[40.655,29.277],"yozgat":[39.818,34.815],
            "zonguldak":[41.456,31.789],"gebze":[40.802,29.430],"izmit":[40.765,29.940],
            "afyon":[38.757,30.540],"antep":[37.066,37.383],"maraş":[37.575,36.922],
        }
        _ILCE_KOOR = {
            # İstanbul Avrupa
            "bakırköy":[40.979,28.875],"bağcılar":[41.042,28.855],"bahçelievler":[41.000,28.858],
            "bayrampaşa":[41.048,28.912],"beşiktaş":[41.042,29.009],"beylikdüzü":[40.981,28.642],
            "beyoğlu":[41.031,28.975],"büyükçekmece":[41.019,28.583],"esenler":[41.044,28.875],
            "esenyurt":[41.033,28.668],"eyüpsultan":[41.073,28.935],"fatih":[41.013,28.940],
            "gaziosmanpaşa":[41.065,28.906],"güngören":[41.017,28.870],"küçükçekmece":[41.003,28.778],
            "şişli":[41.058,28.985],"sultangazi":[41.105,28.872],"zeytinburnu":[40.999,28.900],
            "arnavutköy":[41.182,28.735],"avcılar":[40.979,28.720],"başakşehir":[41.090,28.800],
            "çatalca":[41.143,28.459],"silivri":[41.072,28.243],"sarıyer":[41.166,29.053],
            # İstanbul Anadolu
            "ataşehir":[40.982,29.120],"beykoz":[41.118,29.097],"çekmeköy":[41.034,29.172],
            "kadıköy":[40.990,29.030],"kartal":[40.889,29.183],"maltepe":[40.933,29.150],
            "pendik":[40.876,29.256],"sancaktepe":[40.998,29.231],"sultanbeyli":[40.963,29.262],
            "tuzla":[40.820,29.298],"ümraniye":[41.015,29.124],"üsküdar":[41.022,29.025],
            # Kocaeli
            "gebze":[40.800,29.432],"izmit":[40.764,29.917],"darıca":[40.760,29.570],
            "dilovası":[40.753,29.528],"körfez":[40.745,29.787],"gölcük":[40.651,29.823],
            # Bursa
            "nilüfer":[40.213,28.963],"osmangazi":[40.196,29.057],"yıldırım":[40.189,29.100],
            # Tekirdağ
            "çerkezköy":[41.289,27.988],"çorlu":[41.160,27.801],"lüleburgaz":[41.404,27.351],
            # Diğer
            "bornova":[38.466,27.215],"buca":[38.381,27.152],"karşıyaka":[38.459,27.108],
        }
        _DURUM_RENK = {
            "Portföy":"#1d4ed8","Hedef":"#15803d","Tekrar Ara":"#d97706",
            "İlk Temas":"#0891b2","Pasif":"#6b7280","Teklif":"#7c3aed",
            "Aktif":"#15803d","Kaybedildi":"#dc2626","Kazanıldı":"#16a34a",
        }
        def _tr_lower(s):
            """Türkçe karakterleri doğru küçült"""
            return (s.replace("İ","i").replace("I","ı").replace("Ş","ş")
                     .replace("Ğ","ğ").replace("Ü","ü").replace("Ö","ö")
                     .replace("Ç","ç").lower().strip())

        # ── ÜCRETSİZ ADRES BAZLI KONUM BULMA (GEOCODING) — Google Maps API
        # gerektirmez, OpenStreetMap'in ücretsiz Nominatim servisini kullanır.
        # Sonuçlar kalıcı olarak önbelleğe alınır (bir adres bir daha asla
        # tekrar sorgulanmaz) — bu yüzden ilk seferden sonra çok hızlıdır.
        @st.cache_data(ttl=3600, show_spinner=False)
        def _harita_geo_cache_yukle():
            try:
                _sb_g = get_sb_client()
                if _sb_g:
                    _r_g = _sb_g.table("kullanici_tercih").select("deger").eq(
                        "kullanici", "__liste_ui__").eq("anahtar", "_harita_geocode_cache").execute()
                    if _r_g.data:
                        return _hj.loads(_r_g.data[0]["deger"])
            except Exception:
                pass
            return {}

        def _harita_geo_cache_kaydet(_cache):
            try:
                _sb_g2 = get_sb_client()
                if _sb_g2:
                    _deger = _hj.dumps(_cache, ensure_ascii=False)
                    _sb_g2.table("kullanici_tercih").delete().eq("kullanici", "__liste_ui__").eq("anahtar", "_harita_geocode_cache").execute()
                    _sb_g2.table("kullanici_tercih").insert({"kullanici": "__liste_ui__", "anahtar": "_harita_geocode_cache", "deger": _deger}).execute()
            except Exception:
                pass

        def _harita_geo_sorgu(_adres, _ilce, _il):
            """OpenStreetMap Nominatim (ücretsiz, anahtar gerektirmez) ile
            adresi lat/lng koordinatına çevirir. Bulamazsa None döner."""
            import requests as _hreq
            _q = ", ".join([p for p in [_adres, _ilce, _il, "Türkiye"] if p and p != "—"])
            try:
                _resp = _hreq.get("https://nominatim.openstreetmap.org/search",
                                   params={"q": _q, "format": "json", "limit": 1, "countrycodes": "tr"},
                                   headers={"User-Agent": "MWCRMPRO-Musteri-Haritasi/1.0"}, timeout=8)
                _sonuc = _resp.json()
                if _sonuc:
                    return float(_sonuc[0]["lat"]), float(_sonuc[0]["lon"])
            except Exception:
                pass
            return None

        _geo_cache = _harita_geo_cache_yukle()
        _harita_geo_sfx = st.session_state.get("_harita_geo_sfx", 0)

        _gorulen_firmalar = set()
        _pins = []
        _hassas_sayi = 0
        _yaklasik_kayitlar = []  # (anahtar, adres, ilce, il) — henüz geocode edilmemişler
        for _, _hr in _hdf_f.iterrows():
            _il   = _tr_lower(str(_hr.get("il","")   or ""))
            _ilce = _tr_lower(str(_hr.get("ilce","") or ""))
            _firma_ham = str(_hr.get("firma","") or "?")
            if _firma_ham in _gorulen_firmalar: continue
            _gorulen_firmalar.add(_firma_ham)
            _firma= _firma_ham.replace("'","&#39;").replace('"','&quot;')
            _durum= str(_hr.get("durum","") or "—")
            _seg  = str(_hr.get("segment","") or "—")
            _tem  = str(_hr.get("temsilci","") or "—")
            _tel  = str(_hr.get("gsm","")   or "—")
            _adres_ham = str(_hr.get("adres","") or "").strip()
            _adrs = str(_hr.get("adres","") or "—").replace("'","&#39;").replace('"','&quot;')
            _lat, _lng = None, None
            _hassas = False

            # 1) ÖNCE önbellekte gerçek adres bazlı koordinat var mı bak (hassas)
            _geo_anahtar = _tr_lower(f"{_adres_ham}|{_hr.get('ilce','')}|{_hr.get('il','')}")
            if _adres_ham and _geo_anahtar in _geo_cache and _geo_cache[_geo_anahtar]:
                _lat, _lng = _geo_cache[_geo_anahtar]
                _hassas = True
                _hassas_sayi += 1
            elif _adres_ham:
                _yaklasik_kayitlar.append(_geo_anahtar)

            # 2) Yoksa eski yöntem — il/ilçe merkezine yaklaşık (jitter'lı)
            if _lat is None:
                if _ilce:
                    if _ilce in _ILCE_KOOR:
                        _lat, _lng = _ILCE_KOOR[_ilce]
                    else:
                        for _k in _ILCE_KOOR:
                            if _tr_lower(_k) == _ilce:
                                _lat, _lng = _ILCE_KOOR[_k]; break
                if _lat is None and _il:
                    if _il in _IL_KOOR:
                        _lat, _lng = _IL_KOOR[_il]
                    else:
                        for _k in _IL_KOOR:
                            if _tr_lower(_k) == _il or _il[:5] == _tr_lower(_k)[:5]:
                                _lat, _lng = _IL_KOOR[_k]; break
                if _lat is None: continue
                _seed = int(hashlib.md5(_firma_ham.encode()).hexdigest()[:8], 16)
                random.seed(_seed)
                _lat += random.uniform(-0.008, 0.008)
                _lng += random.uniform(-0.008, 0.008)

            _renk = _DURUM_RENK.get(_durum, "#64748b")
            # Randevu varsa kırmızı override
            if _firma_ham in _rand_acik:
                _renk = "#dc2626"   # Açık randevu — parlak kırmızı
                _rand_etiketi = "🔴 Açık Randevu"
            elif _firma_ham in _rand_var:
                _renk = "#f87171"   # Geçmiş randevu — açık kırmızı
                _rand_etiketi = "🟠 Randevu Var"
            else:
                _rand_etiketi = ""
            _pins.append({"lat":round(_lat,5),"lng":round(_lng,5),"firma":_firma,
                "durum":_durum,"renk":_renk,"seg":_seg,"tem":_tem,"tel":_tel,
                "il":str(_hr.get("il","")).title(),"ilce":str(_hr.get("ilce","")).title(),
                "adres":_adrs,"rand":_rand_etiketi,"hassas":_hassas})

        # ── Adres bazlı konum bulma paneli ──────────────────────────────────
        _yaklasik_kayitlar = list(dict.fromkeys(_yaklasik_kayitlar))  # tekilleştir
        _hgc1, _hgc2, _hgc3 = st.columns([2, 1, 1])
        _hgc1.caption(f"📍 {_hassas_sayi} müşteri TAM ADRESİNDEN, {len(_yaklasik_kayitlar)} müşteri il/ilçe merkezinden (yaklaşık) gösteriliyor.")
        if _yaklasik_kayitlar and _hgc2.button(f"🔍 Sıradaki 15 Adresi Bul", key="_harita_geo_bul_btn", use_container_width=True):
            import time as _htime
            _bulunan = 0
            with st.spinner(f"Adresler OpenStreetMap üzerinden aranıyor (yaklaşık {min(15,len(_yaklasik_kayitlar))*1.1:.0f} saniye sürer)..."):
                for _anahtar in _yaklasik_kayitlar[:15]:
                    _parcalar = _anahtar.split("|")
                    _sonuc = _harita_geo_sorgu(_parcalar[0], _parcalar[1] if len(_parcalar) > 1 else "", _parcalar[2] if len(_parcalar) > 2 else "")
                    _geo_cache[_anahtar] = list(_sonuc) if _sonuc else None
                    if _sonuc: _bulunan += 1
                    _htime.sleep(1.1)  # Nominatim kullanım kuralı: saniyede en fazla 1 istek
            _harita_geo_cache_kaydet(_geo_cache)
            _harita_geo_cache_yukle.clear()
            st.toast(f"📍 {_bulunan} adres bulundu, {15-_bulunan} adres eşleşmedi (yaklaşık konumda kalacak)", icon="✅")
            st.rerun()
        if _yaklasik_kayitlar:
            _hgc3.caption(f"Tahmini süre: ~{len(_yaklasik_kayitlar)*1.1/60:.1f} dk (tamamı için)")

        _pins_json = _hj.dumps(_pins, ensure_ascii=False)
        _harita_html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.Default.css"/>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
#map{width:100%;height:580px;}
.pp{font-family:-apple-system,sans-serif;min-width:220px;}
.pp h4{font-size:13px;font-weight:600;color:#0f172a;margin-bottom:6px;border-bottom:1px solid #f1f5f9;padding-bottom:5px;}
.pp table{font-size:11px;width:100%;border-collapse:collapse;}
.pp td{padding:3px 4px;} .pp td:first-child{color:#94a3b8;width:70px;}
.pp td:last-child{font-weight:500;color:#1e293b;}
#leg{position:absolute;bottom:24px;right:8px;z-index:1000;background:white;border-radius:8px;padding:10px 14px;font-size:11px;box-shadow:0 2px 8px rgba(0,0,0,.12);}
.li{display:flex;align-items:center;gap:6px;margin-top:4px;}
.ld{width:10px;height:10px;border-radius:50%;}
</style></head><body>
<div id="map"></div><div id="leg"><b>Durum</b></div>
<script>
var pins = """ + _pins_json + """;
var map = L.map('map').setView([39.5,33.0],6);
// OpenStreetMap standart tile — tamamen ücretsiz, anahtar gerektirmez.
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
  attribution:'© OpenStreetMap', maxZoom:19
}).addTo(map);
var cl = L.markerClusterGroup({maxClusterRadius:45,spiderfyOnMaxZoom:true,showCoverageOnHover:false});
var rnk={};
pins.forEach(function(p){
  rnk[p.durum]=p.renk;
  var boyut = p.hassas ? 30 : 24;  // hassas (gerçek adres) pin'ler biraz daha büyük/belirgin
  var svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+boyut+'" height="'+(boyut*4/3)+'" viewBox="0 0 24 32">'
    +'<path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 20 12 20s12-11 12-20C24 5.4 18.6 0 12 0z" fill="'+p.renk+'" stroke="white" stroke-width="1.5"/>'
    +'<circle cx="12" cy="12" r="5" fill="white" opacity="0.9"/></svg>';
  var ic=L.divIcon({html:svg,className:'',iconSize:[boyut,boyut*4/3],iconAnchor:[boyut/2,boyut*4/3],popupAnchor:[0,-boyut]});
  var pop='<div class="pp"><h4>'+p.firma+(p.rand?' <span style="font-size:11px;color:#dc2626">'+p.rand+'</span>':'')+'</h4><table>'
    +'<tr><td>İl/İlçe</td><td>'+p.il+(p.ilce?' / '+p.ilce:'')+'</td></tr>'
    +'<tr><td>Adres</td><td>'+p.adres+(p.hassas?' <span style="color:#16a34a;font-size:10px;">📍 hassas</span>':' <span style="color:#d97706;font-size:10px;">~yaklaşık</span>')+'</td></tr>'
    +'<tr><td>Durum</td><td>'+p.durum+'</td></tr>'
    +'<tr><td>Segment</td><td>'+p.seg+'</td></tr>'
    +'<tr><td>Temsilci</td><td>'+p.tem+'</td></tr>'
    +'<tr><td>Tel</td><td>'+p.tel+'</td></tr>'
    +(p.rand?'<tr><td>Randevu</td><td><b style="color:#dc2626">'+p.rand+'</b></td></tr>':'')
    +'</table></div>';
  L.marker([p.lat,p.lng],{icon:ic}).bindPopup(pop,{maxWidth:280}).addTo(cl);
});
map.addLayer(cl);
var leg=document.getElementById('leg');
leg.innerHTML='<b>Durum</b><div class="li"><div class="ld" style="background:#dc2626"></div><span>🔴 Açık Randevu</span></div><div class="li"><div class="ld" style="background:#f87171"></div><span>Randevu Var</span></div>';
Object.entries(rnk).forEach(function(e){
  leg.innerHTML+='<div class="li"><div class="ld" style="background:'+e[1]+'"></div><span>'+e[0]+'</span></div>';
});
</script></body></html>"""
        _hcomp.html(_harita_html, height=590, scrolling=False)
        if _il_col and not _hdf_f.empty:
            st.divider()
            with st.expander("📊 İl / İlçe Bazlı Özet", expanded=False):
                _grp_cols = [c for c in [_il_col, "ilce"] if c in _hdf_f.columns]
                _il_g = (_hdf_f.groupby(_grp_cols).size()
                         .reset_index(name="Müşteri Sayısı")
                         .sort_values(["Müşteri Sayısı"] + _grp_cols[:1], ascending=[False, True])
                         .head(50))
                st.markdown("""<style>
                .mh-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:6px;margin-top:6px;}
                .mh-kart{background:#ffffff;border:0.5px solid #e2e8f0;border-radius:8px;padding:7px 9px;}
                .mh-il{font-size:9px;color:#94a3b8;font-weight:600;letter-spacing:.2px;text-transform:uppercase;}
                .mh-ilce{font-size:11.5px;color:#0f172a;font-weight:600;margin:1px 0 3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
                .mh-sayi{font-size:14px;font-weight:700;color:#1d4ed8;}
                .mh-etiket{font-size:9px;color:#64748b;margin-left:3px;}
                </style>""", unsafe_allow_html=True)
                _mh_kartlar = ""
                for _, _mhr in _il_g.iterrows():
                    _mh_il = str(_mhr.get(_il_col, ""))
                    _mh_ilce = str(_mhr.get("ilce", "")) if "ilce" in _il_g.columns else ""
                    _mh_sayi = int(_mhr["Müşteri Sayısı"])
                    _mh_kartlar += (
                        f'<div class="mh-kart"><div class="mh-il">{_mh_il}</div>'
                        f'<div class="mh-ilce">{_mh_ilce}</div>'
                        f'<span class="mh-sayi">{_mh_sayi}</span><span class="mh-etiket">müşteri</span></div>'
                    )
                st.markdown(f'<div class="mh-grid">{_mh_kartlar}</div>', unsafe_allow_html=True)

elif aktif == "kargolar":
    sayfa_log("kargolar")
    st.markdown("## 🚚 Kargolar — Tüm Müşteriler")
    st.caption("Tüm müşterilerin kargo giriş kayıtları burada birleşik olarak görünür. "
               "'Seç' işaretleyip düzenleyebilir veya silebilirsin.")

    @st.cache_data(ttl=30, show_spinner=False)
    def _kargolar_tumunu_yukle():
        try:
            _sb_kt = get_sb_client()
            if not _sb_kt:
                return []
            _r_kt = _sb_kt.table("kullanici_tercih").select("anahtar,deger").eq(
                "kullanici", "__liste_ui__").like("anahtar", "_kargo_kayitlari_%").execute()
            import json as _ktj
            _tum_kayitlar = []
            for _row in (_r_kt.data or []):
                try:
                    _cid = int(str(_row["anahtar"]).replace("_kargo_kayitlari_", ""))
                except Exception:
                    continue
                try:
                    _liste = _ktj.loads(_row["deger"])
                except Exception:
                    _liste = []
                for _i, _kayit in enumerate(_liste):
                    _kayit_kopya = dict(_kayit)
                    _kayit_kopya["_cari_id"] = _cid
                    _kayit_kopya["_satir_no"] = _i
                    _tum_kayitlar.append(_kayit_kopya)
            return _tum_kayitlar
        except Exception:
            return []

    def _kargolar_yaz(_cari_id, _yeni_liste_o_musteri):
        try:
            _sb_kt2 = get_sb_client()
            if _sb_kt2:
                import json as _ktj2
                _anahtar = f"_kargo_kayitlari_{int(_cari_id)}"
                _deger = _ktj2.dumps(_yeni_liste_o_musteri, ensure_ascii=False)
                _sb_kt2.table("kullanici_tercih").delete().eq("kullanici", "__liste_ui__").eq("anahtar", _anahtar).execute()
                _sb_kt2.table("kullanici_tercih").insert({"kullanici": "__liste_ui__", "anahtar": _anahtar, "deger": _deger}).execute()
        except Exception:
            pass

    if "_kargo_kol_genislik" not in st.session_state:
        try:
            _sb_kkg0 = get_sb_client()
            if _sb_kkg0:
                _r_kkg0 = _sb_kkg0.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kargo_kol_genislik").execute()
                if _r_kkg0.data:
                    import json as _kkgj0
                    st.session_state["_kargo_kol_genislik"] = _kkgj0.loads(_r_kkg0.data[0]["deger"])
        except Exception:
            pass

    _kl_tum_kayitlar = _kargolar_tumunu_yukle()
    if not _kl_tum_kayitlar:
        st.info("💡 Henüz hiçbir müşteride kargo kaydı yok. Cari Liste'de bir firmayı seçip (Seç işareti) açılan pencereden '📦 Kargo Girişi' sekmesiyle ekleyebilirsin.")
    else:
        try:
            _kl_musteri_map = dict(zip(get_cari_listesi()["id"], get_cari_listesi()["firma"]))
        except Exception:
            _kl_musteri_map = {}
        for _kk in _kl_tum_kayitlar:
            _kk["Müşteri"] = _kl_musteri_map.get(_kk.get("_cari_id"), f"(ID {_kk.get('_cari_id')})")

        # ── BİR KERELİK DOLDURMA — geçmişte girilmiş tüm (Alıcı Firma, Alıcı İl)
        # çiftlerini kalıcı hafızaya aktarır. Sonrasında her yeni girişte zaten
        # otomatik güncelleniyor, bu buton sadece ESKİ kayıtları yakalamak için.
        if st.button("🔄 Geçmiş Kayıtlardan Alıcı-İl Hafızasını Doldur (bir kerelik)", key="kl_hafiza_doldur_btn"):
            _kl_hafiza_yeni = dict(_kg_manuel_alici_yukle())
            _kl_eklenen = 0
            for _kk2 in _kl_tum_kayitlar:
                _af = str(_kk2.get("alici_firma", "")).strip()
                _ai = str(_kk2.get("alici_il", "")).strip()
                if _af and _ai and _tr_buyuk(_af) not in _kl_hafiza_yeni:
                    _kl_hafiza_yeni[_tr_buyuk(_af)] = _tr_buyuk(_ai)
                    _kl_eklenen += 1
            _kg_manuel_alici_kaydet(_kl_hafiza_yeni)
            _kg_manuel_alici_yukle.clear()
            st.toast(f"✅ {_kl_eklenen} yeni firma-il çifti hafızaya eklendi (toplam {len(_kl_hafiza_yeni)})", icon="💾")

        _kl_df = pd.DataFrame(_kl_tum_kayitlar)
        _kl_df = _kl_df.fillna("")  # eski kayıtlarda olmayan alanlar "None" değil boş görünsün
        # Müşteri alfabetik, kendi içinde tarihe göre sırala
        _kl_df = _kl_df.sort_values(by=["Müşteri", "tarih"], kind="stable").reset_index(drop=True)

        # ── GENEL MÜŞTERİ FİLTRESİ — sistemdeki TÜM müşteriler seçilebilir,
        # buradan doğrudan o müşteri için Kargo Girişi açılabilir (kaydı olmasa bile).
        _kl_musteri_secenekler = ["-- Tüm Müşteriler --"] + sorted(_kl_musteri_map.values())
        _kl_fc1, _kl_fc2 = st.columns([3, 1], vertical_alignment="bottom")
        _kl_secili_musteri_genel = _kl_fc1.selectbox("Genel Müşteri Seç (kargo girişi için)", _kl_musteri_secenekler, key="kargolar_musteri_filtre")
        with _kl_fc2:
            if _kl_secili_musteri_genel != "-- Tüm Müşteriler --":
                _kl_sec_cari_id = None
                for _cid_ara, _fad_ara in _kl_musteri_map.items():
                    if _fad_ara == _kl_secili_musteri_genel:
                        _kl_sec_cari_id = _cid_ara
                        break
                if st.button("📦 Kargo Girişi Ekle", key="kargolar_giris_ac_btn", use_container_width=True, disabled=_kl_sec_cari_id is None):
                    not_dialog(_kl_sec_cari_id, _kl_secili_musteri_genel)

        # ── MUHASEBESEL FİLTRELER — Gönderen / Alıcı / Fatura Ödeyen AYRI AYRI.
        # Tek bir "Müşteri" filtresi bu 3 farklı rolü karıştırıp ödeme takibini
        # yanlış gösteriyordu; artık her rol kendi filtresiyle daraltılıyor.
        st.caption("Aşağıdaki 3 filtre, listedeki kayıtları rol bazında daraltır (muhasebesel takip için):")
        _kl_gc1, _kl_gc2, _kl_gc3 = st.columns(3)
        _kl_gonderen_opts = ["-- Tümü --"] + sorted([x for x in _kl_df["gonderen_firma"].dropna().unique().tolist() if str(x).strip()]) if "gonderen_firma" in _kl_df.columns else ["-- Tümü --"]
        _kl_alici_opts = ["-- Tümü --"] + sorted([x for x in _kl_df["alici_firma"].dropna().unique().tolist() if str(x).strip()]) if "alici_firma" in _kl_df.columns else ["-- Tümü --"]
        _kl_fatura_opts = ["-- Tümü --"] + sorted([x for x in _kl_df["fatura_firma"].dropna().unique().tolist() if str(x).strip()]) if "fatura_firma" in _kl_df.columns else ["-- Tümü --"]
        _kl_sec_gonderen = _kl_gc1.selectbox("Gönderen Filtrele", _kl_gonderen_opts, key="kargolar_gonderen_filtre")
        _kl_sec_alici = _kl_gc2.selectbox("Alıcı Filtrele", _kl_alici_opts, key="kargolar_alici_filtre")
        _kl_sec_fatura = _kl_gc3.selectbox("Fatura Ödeyen Filtrele", _kl_fatura_opts, key="kargolar_fatura_filtre")
        if _kl_sec_gonderen != "-- Tümü --":
            _kl_df = _kl_df[_kl_df["gonderen_firma"] == _kl_sec_gonderen]
        if _kl_sec_alici != "-- Tümü --":
            _kl_df = _kl_df[_kl_df["alici_firma"] == _kl_sec_alici]
        if _kl_sec_fatura != "-- Tümü --":
            _kl_df = _kl_df[_kl_df["fatura_firma"] == _kl_sec_fatura]

        # Panel/özet gösterimi hâlâ "genel müşteri seçimi"ne bağlı çalışıyor
        _kl_secili_musteri = _kl_secili_musteri_genel
        if _kl_secili_musteri != "-- Tüm Müşteriler --":
            _kl_df = _kl_df[_kl_df["Müşteri"] == _kl_secili_musteri]

        _kl_df.insert(0, "Seç", False)
        _kl_kolon_isim = {"Müşteri": "Müşteri", "tarih": "Tarih", "takip_no": "Takip No", "gonderen_firma": "Gönderen",
                           "alici_firma": "Alıcı", "fatura_firma": "Fatura Ödeyen",
                           "gonderen_il": "Gönderen İl", "alici_il": "Alıcı İl",
                           "adet": "Adet", "tur": "Tür", "tutar": "Tutar", "kdv": "KDV", "sigorta": "Sigorta",
                           "toplam_fatura": "Toplam Fatura", "odeme_tur": "Ödeme Türü", "tahsilat_durumu": "Tahsilat",
                           "dis_nakliye_firma": "Dış Nakliye Firma", "dis_nakliye_fatura": "Dış Nakliye Fatura",
                           "dis_nakliye_detay": "Dış Nakliye Detay", "dis_nakliye_tutar": "Dış Nakliye Tutar",
                           "musteri_tutar": "Müşteri Tutar", "kar": "Kar", "dis_nakliye_odeme_durumu": "Dış Nak. Ödeme", "fatura_odeme_sekli": "Fatura Ödeme Şekli"}
        _kl_gorunur_kolonlar = ["Seç", "Müşteri"] + [c for c in _kl_kolon_isim if c in _kl_df.columns and c != "Müşteri"]
        _kl_df = _kl_df.reset_index(drop=True)  # filtrelerden sonra index'ler boşluklu kalmasın (iloc hatası önlenir)
        _kl_df_goster = _kl_df[_kl_gorunur_kolonlar + ["_cari_id", "_satir_no"]].rename(columns=_kl_kolon_isim)
        st.caption(f"Toplam {len(_kl_df)} kargo kaydı, {_kl_df['_cari_id'].nunique()} müşteride.")

        # ── EXCEL İNDİR — tek sayfalık, bölünmemiş tam liste ──────────────────
        _kl_excel_buf = io.BytesIO()
        _kl_df_goster.drop(columns=["Seç", "_cari_id", "_satir_no"]).to_excel(_kl_excel_buf, index=False, engine="openpyxl")
        _kl_excel_buf.seek(0)
        st.download_button("📥 Listeyi Excel Olarak İndir", data=_kl_excel_buf,
                            file_name=f"kargolar_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="kargolar_excel_indir")

        # ── MÜŞTERİ ÖZETİ — Genel Müşteri, Gönderen, Alıcı ya da Fatura Ödeyen
        # filtrelerinden HERHANGİ biri seçiliyse gösterilir (sadece "Genel
        # Müşteri Seç"e bağlı değil — 3 role de aynı özet/ekstre çalışsın diye).
        _kl_aktif_filtre_etiketi = None
        if _kl_secili_musteri_genel != "-- Tüm Müşteriler --":
            _kl_aktif_filtre_etiketi = f"Müşteri: {_kl_secili_musteri_genel}"
        elif _kl_sec_gonderen != "-- Tümü --":
            _kl_aktif_filtre_etiketi = f"Gönderen: {_kl_sec_gonderen}"
        elif _kl_sec_alici != "-- Tümü --":
            _kl_aktif_filtre_etiketi = f"Alıcı: {_kl_sec_alici}"
        elif _kl_sec_fatura != "-- Tümü --":
            _kl_aktif_filtre_etiketi = f"Fatura Ödeyen: {_kl_sec_fatura}"

        _kl_detay = None
        _kl_detay_toplam_adet = 0
        _kl_detay_toplam_tutar = 0.0
        if _kl_aktif_filtre_etiketi and not _kl_df.empty:
            with st.expander(f"📊 Özet / Ekstre — {_kl_aktif_filtre_etiketi}", expanded=True):
                # "Toplam Fatura" doldurulmamışsa (genelde durum bu — sadece "Tutar"
                # kullanılıyor) satır bazında "Toplam Fatura varsa o, yoksa Tutar" alınır.
                _kl_df = _kl_df.copy()
                _kl_df["_efektif_tutar"] = pd.to_numeric(_kl_df.get("toplam_fatura", 0), errors="coerce").fillna(0)
                _kl_tutar_num = pd.to_numeric(_kl_df.get("tutar", 0), errors="coerce").fillna(0)
                _kl_df.loc[_kl_df["_efektif_tutar"] == 0, "_efektif_tutar"] = _kl_tutar_num
                _oz_toplam_ciro = float(_kl_df["_efektif_tutar"].sum())
                _ozm1, _ozm2 = st.columns(2)
                _ozm1.metric("💰 Toplam Ciro", f"{_oz_toplam_ciro:,.0f} ₺")
                if "tahsilat_durumu" in _kl_df.columns:
                    _oz_tahsil_edilen = float(_kl_df.loc[_kl_df["tahsilat_durumu"] == "Tahsil Edildi", "_efektif_tutar"].sum())
                    _oz_kalan_borc = _oz_toplam_ciro - _oz_tahsil_edilen
                    _ozm2.metric("⏳ Kalan Borç", f"{_oz_kalan_borc:,.0f} ₺")

                # ── AY | HAT | ALICI İL | FİRMA | TÜR | ADET | DESİ-KG | TUTAR ──
                # Kullanıcının verdiği tam formata göre: önce DETAY satırları (her
                # kargo kaydı kendi satırında, aya göre sıralı), sonra GENEL TOPLAM
                # (Hat+İl+Tür bazında, tüm aylar toplanmış), en altta HEPSİ (dip toplam).
                if "alici_il" in _kl_df.columns and "tur" in _kl_df.columns and "tarih" in _kl_df.columns:
                    _kl_ana_il_liste = [_tr_buyuk(a) for a in ["İzmir", "Bursa", "Manisa", "Tekirdağ", "İstanbul", "Kocaeli"]]
                    _kl_ay_ad_map = {"01":"OCAK","02":"ŞUBAT","03":"MART","04":"NİSAN","05":"MAYIS","06":"HAZİRAN",
                                      "07":"TEMMUZ","08":"AĞUSTOS","09":"EYLÜL","10":"EKİM","11":"KASIM","12":"ARALIK"}
                    _kl_rapor = _kl_df.copy()
                    _kl_rapor["_tarih_dt"] = pd.to_datetime(_kl_rapor["tarih"], errors="coerce")
                    _kl_rapor = _kl_rapor[_kl_rapor["alici_il"].astype(str).str.strip() != ""]
                    _kl_rapor["Ay"] = _kl_rapor["_tarih_dt"].dt.strftime("%m").map(_kl_ay_ad_map).fillna("(Tarihsiz)")
                    _kl_rapor["_ay_sira"] = _kl_rapor["_tarih_dt"].dt.strftime("%Y-%m")
                    _kl_rapor["Hat"] = _kl_rapor["alici_il"].astype(str).str.upper().apply(
                        lambda x: "NORMAL" if x in _kl_ana_il_liste else "DIŞ BÖLGE")
                    _kl_rapor["Tür"] = _kl_rapor["tur"].astype(str).str.strip().str.upper().replace("", "(TÜR BELİRTİLMEMİŞ)")
                    # "FİRMA" sütunu, HANGİ filtre aktifse onun seçtiği gerçek firma
                    # adı olmalı (kaydın "sahibi" olan müşteri değil — örn. Gönderen
                    # filtrelenmişse Gönderen firma adı yazılır).
                    _kl_secili_firma_adi = (_kl_aktif_filtre_etiketi.split(": ", 1)[1]
                                             if _kl_aktif_filtre_etiketi and ": " in _kl_aktif_filtre_etiketi else "")
                    _kl_rapor["Firma"] = _kl_secili_firma_adi

                    if not _kl_rapor.empty:
                        # DETAY — her kayıt kendi satırında, aya göre sıralı.
                        # "ADET" = o satırdaki iş/paket miktarı (kaç adet eşya).
                        # "KARGO ADETİ" = her satır 1 kargo işlemi sayılır — toplanınca
                        # kaç AYRI kargo/iş yapıldığını gösterir (ikisi karıştırılmasın).
                        _kl_detay = _kl_rapor.sort_values(["_ay_sira"])[["Ay", "Hat", "alici_il", "Firma", "Tür", "adet", "_efektif_tutar"]].copy()
                        _kl_detay.columns = ["AY", "HAT", "ALICI İL", "FİRMA", "TÜR", "ADET", "TUTAR"]
                        _kl_detay.insert(6, "KARGO ADETİ", 1)
                        _kl_detay.insert(7, "DESİ-KG", "")  # şu an ayrı bir desi/kg alanı tutulmuyor
                        _kl_detay["TUTAR"] = pd.to_numeric(_kl_detay["TUTAR"], errors="coerce").fillna(0).apply(lambda x: f"{x:,.0f} ₺")
                        # NOT: Streamlit iç içe expander desteklemediği için bu tablo
                        # burada SAKLANIP, dış "Özet/Ekstre" paneli kapandıktan SONRA
                        # kendi bağımsız açılır/kapanır panelinde gösteriliyor (aşağıda).
                        _kl_detay_toplam_adet = int(pd.to_numeric(_kl_rapor["adet"], errors="coerce").fillna(0).sum())
                        _kl_detay_toplam_tutar = float(_kl_rapor["_efektif_tutar"].sum())
                st.markdown("#### 🚚 Dış Nakliye Özeti")
                _oz_dn_tutar = float(pd.to_numeric(_kl_df.get("dis_nakliye_tutar", 0), errors="coerce").fillna(0).sum())
                if "dis_nakliye_odeme_durumu" in _kl_df.columns:
                    _oz_dn_odenen = float(pd.to_numeric(
                        _kl_df.loc[_kl_df["dis_nakliye_odeme_durumu"] == "Ödendi", "dis_nakliye_tutar"], errors="coerce").fillna(0).sum())
                else:
                    _oz_dn_odenen = 0.0
                _oz_dn_borc = _oz_dn_tutar - _oz_dn_odenen
                _ozn1, _ozn2 = st.columns(2)
                _ozn1.metric("🚚 Toplam Dış Nakliye", f"{_oz_dn_tutar:,.0f} ₺")
                _ozn2.metric("⏳ Ödenmemiş (Borç)", f"{_oz_dn_borc:,.0f} ₺")
                _oz_toplam_kar = float(pd.to_numeric(_kl_df.get("kar", 0), errors="coerce").fillna(0).sum())
                st.caption(f"📈 Toplam Kar: **{_oz_toplam_kar:,.0f} ₺**")
                if "dis_nakliye_odeme_durumu" not in _kl_df.columns or _kl_df.get("dis_nakliye_odeme_durumu", pd.Series(dtype=str)).eq("").all():
                    st.caption("💡 Ödendi/Ödenmedi takibi için Kargo Girişi formuna 'Dış Nakliye Ödeme Durumu' alanını dolduman yeterli.")
            st.divider()

        # ── DETAY RAPORU — kendi bağımsız açılır/kapanır paneli. Hangi müşteri
        # (Gönderen/Alıcı/Fatura Ödeyen/Genel) seçilirse seçilsin aynı şekilde çalışır.
        if _kl_detay is not None and not _kl_detay.empty:
            with st.expander(f"📋 Detay Raporu — {_kl_aktif_filtre_etiketi} ({len(_kl_detay)} kayıt)", expanded=True):
                st.dataframe(_kl_detay, use_container_width=True, hide_index=True,
                             height=min(38 * (len(_kl_detay) + 1) + 25, 500))
                st.caption(f"Toplam: **{_kl_detay_toplam_adet} adet** ({len(_kl_detay)} ayrı kargo işlemi) — **{_kl_detay_toplam_tutar:,.0f} ₺**")

        # ── TÜM MÜŞTERİLER GENEL RAPORU — filtrelerden bağımsız, sistemdeki
        # HERKESİ kapsar. Firma + Gönderen İl + Alıcı İl + Tür kırılımlı, altında
        # genel toplam satırı. Aylık ya da tüm zaman seçilebilir.
        with st.expander("📊 Tüm Müşteriler — Genel Rapor", expanded=False):
            _tg_df = pd.DataFrame(_kl_tum_kayitlar).fillna("") if _kl_tum_kayitlar else pd.DataFrame()
            if _tg_df.empty:
                st.caption("Henüz hiçbir kayıt yok.")
            else:
                _tg_df["Müşteri"] = _tg_df["_cari_id"].map(_kl_musteri_map).fillna("(Bilinmiyor)")
                _tg_df["_efektif_tutar"] = pd.to_numeric(_tg_df.get("toplam_fatura", 0), errors="coerce").fillna(0)
                _tg_tutar_num = pd.to_numeric(_tg_df.get("tutar", 0), errors="coerce").fillna(0)
                _tg_df.loc[_tg_df["_efektif_tutar"] == 0, "_efektif_tutar"] = _tg_tutar_num
                _tg_df["_tarih_dt"] = pd.to_datetime(_tg_df.get("tarih", ""), errors="coerce")

                _tgc1, _tgc2 = st.columns([1, 2])
                _tg_zaman_secim = _tgc1.radio("Zaman Aralığı", ["Tüm Zaman", "Belirli Ay"], key="tg_zaman_secim", horizontal=True)
                if _tg_zaman_secim == "Belirli Ay":
                    _tg_ay_secenekleri = sorted(_tg_df["_tarih_dt"].dropna().dt.strftime("%Y-%m").unique().tolist(), reverse=True)
                    if _tg_ay_secenekleri:
                        _tg_sec_ay = _tgc2.selectbox("Ay seç", _tg_ay_secenekleri, key="tg_sec_ay")
                        _tg_df = _tg_df[_tg_df["_tarih_dt"].dt.strftime("%Y-%m") == _tg_sec_ay]
                    else:
                        st.caption("Tarihli kayıt yok.")

                _tg_df["_tur_norm"] = _tg_df.get("tur", "").astype(str).str.strip().str.upper().replace("", "(TÜR BELİRTİLMEMİŞ)")
                _tg_grup = (_tg_df.groupby(["Müşteri", "gonderen_il", "alici_il", "_tur_norm"])
                            .agg(Adet=("_tur_norm", "size"), Tutar=("_efektif_tutar", "sum"))
                            .reset_index()
                            .rename(columns={"gonderen_il": "Gönderen İl", "alici_il": "Alıcı İl", "_tur_norm": "Tür"})
                            .sort_values(["Müşteri", "Adet"], ascending=[True, False]))

                if _tg_grup.empty:
                    st.caption("Bu aralıkta kayıt yok.")
                else:
                    _tg_grup_goster = _tg_grup.copy()
                    _tg_grup_goster["Tutar"] = _tg_grup_goster["Tutar"].apply(lambda x: f"{x:,.0f} ₺")
                    st.dataframe(_tg_grup_goster, use_container_width=True, hide_index=True,
                                 height=min(38 * (len(_tg_grup_goster) + 1) + 25, 600))

                    _tg_genel_adet = int(_tg_grup["Adet"].sum())
                    _tg_genel_tutar = float(_tg_grup["Tutar"].sum())
                    st.markdown(f"#### 🧮 GENEL TOPLAM: {_tg_genel_adet} adet — {_tg_genel_tutar:,.0f} ₺")

        # Butonlar tablonun ÜSTÜNDE görünsün diye önce boş bir kutu (container)
        # ayrılıyor, düzenlenen tablo aşağıda oluşuyor, butonlar en son bu
        # kutunun İÇİNE render ediliyor — ama DOM'da (ekranda) yeri en üstte kalıyor.
        _kl_btn_kutu = st.container()

        # Tablo yüksekliği: TÜM satırlar tek seferde, kaydırmaya gerek kalmadan
        # görünsün diye satır sayısına göre otomatik büyütülüyor (üst sınırla).
        _kl_yukseklik = min(38 * (len(_kl_df_goster) + 1) + 25, 900)
        # Kolon Ayarları (Kullanıcılar sayfası) sekmesinde ayarlanan genişlikler
        _kl_kol_genislik = st.session_state.get("_kargo_kol_genislik", {})
        _kl_col_config = {"Seç": st.column_config.CheckboxColumn("Seç", default=False)}
        for _kl_kol_ad in _kl_df_goster.columns:
            if _kl_kol_ad in ("Seç", "_cari_id", "_satir_no"):
                continue
            _kl_gen = _kl_kol_genislik.get(_kl_kol_ad)
            if _kl_gen:
                _kl_col_config[_kl_kol_ad] = st.column_config.Column(_kl_kol_ad, width=int(_kl_gen) * 8)
        _kl_duzenlenen = st.data_editor(
            _kl_df_goster.drop(columns=["_cari_id", "_satir_no"]), use_container_width=True, hide_index=True,
            key="kargolar_editor", height=_kl_yukseklik,
            column_config=_kl_col_config
        )

        with _kl_btn_kutu:
            _klb1, _klb2 = st.columns(2)
            with _klb1:
                if st.button("💾 Değişiklikleri Kaydet", key="kargolar_kaydet_btn", type="primary", use_container_width=True):
                    _kl_ters = {v: k for k, v in _kl_kolon_isim.items()}
                    # Her müşteri için kendi listesini ayrı ayrı yeniden oluştur
                    _kl_musteri_gruplari = {}
                    for _idx, _r in _kl_duzenlenen.iterrows():
                        _cid = int(_kl_df_goster.iloc[_idx]["_cari_id"])
                        if bool(_r.get("Seç")):
                            continue  # işaretliler siliniyor sayılır
                        _kayit = {}
                        for _kol, _val in _r.items():
                            if _kol in ("Seç", "Müşteri"):
                                continue
                            _kayit[_kl_ters.get(_kol, _kol)] = _val
                        _kl_musteri_gruplari.setdefault(_cid, []).append(_kayit)
                    # Kayıtları hiç kalmayan (tamamı silinmiş/güncellenmiş) müşteriler için de boş liste yaz
                    for _cid_hepsi in _kl_df["_cari_id"].unique():
                        _kargolar_yaz(int(_cid_hepsi), _kl_musteri_gruplari.get(int(_cid_hepsi), []))
                    _kargolar_tumunu_yukle.clear()
                    st.toast("✅ Kargo kayıtları güncellendi", icon="🚚")
                    st.rerun()
            with _klb2:
                _kl_secili_sayi = int(_kl_duzenlenen["Seç"].sum()) if "Seç" in _kl_duzenlenen.columns else 0
                if st.button(f"🗑️ Seçili {_kl_secili_sayi} Kaydı Sil", key="kargolar_sil_btn", use_container_width=True, disabled=_kl_secili_sayi == 0):
                    _kl_ters2 = {v: k for k, v in _kl_kolon_isim.items()}
                    _kl_musteri_gruplari2 = {}
                    for _idx, _r in _kl_duzenlenen.iterrows():
                        _cid = int(_kl_df_goster.iloc[_idx]["_cari_id"])
                        if bool(_r.get("Seç")):
                            continue
                        _kayit2 = {}
                        for _kol, _val in _r.items():
                            if _kol in ("Seç", "Müşteri"):
                                continue
                            _kayit2[_kl_ters2.get(_kol, _kol)] = _val
                        _kl_musteri_gruplari2.setdefault(_cid, []).append(_kayit2)
                    for _cid_hepsi2 in _kl_df["_cari_id"].unique():
                        _kargolar_yaz(int(_cid_hepsi2), _kl_musteri_gruplari2.get(int(_cid_hepsi2), []))
                    _kargolar_tumunu_yukle.clear()
                    st.toast(f"🗑️ {_kl_secili_sayi} kayıt silindi", icon="🗑️")
                    st.rerun()

elif aktif == "bolgeler":
    sayfa_log("bolgeler")
    import io as _bl_io
    st.markdown("## 📍 Bölgeler")

    _bl_raw = db_read("cari_kartlar", extra_sql="ORDER BY firma")
    if not _bl_raw.empty and "silindi" in _bl_raw.columns:
        _bl_raw = _bl_raw[~_bl_raw["silindi"].isin([1, "1", True, "true"])]
    _bl_raw = _atama_filtresi_uygula(_bl_raw)

    if _bl_raw.empty:
        st.info("Henüz müşteri kaydı yok.")
    else:
        _bl_df = _bl_raw.copy()
        _il_kol = "il" if "il" in _bl_df.columns else None
        _ilce_kol = "ilce" if "ilce" in _bl_df.columns else None
        _bl_df["_bolge"] = _bl_df.apply(
            lambda r: il_ilce_bolge_bul(
                r.get(_il_kol, "") if _il_kol else "",
                r.get(_ilce_kol, "") if _ilce_kol else ""
            ), axis=1
        )
        _bl_df["_bolge"] = _bl_df["_bolge"].fillna("Havuz (Bölgesiz)")

        # ── Üst toplam: kullanıcının TÜM bölgeleri birlikte toplamı, admin için genel toplam ──
        _bl_rol = str(st.session_state.get("rol","")).strip().lower()
        _bl_toplam_baslik = "🌍 Genel toplam (tüm bölgeler, tüm kullanıcılar)" if _bl_rol == "admin" else "📊 Toplamım (tüm bölgelerim birlikte)"
        st.markdown(f"#### {_bl_toplam_baslik}")
        _t1, _t2, _t3 = st.columns(3)
        _t1.metric("Müşteri sayısı", len(_bl_df))
        if "beklenen_ciro" in _bl_df.columns:
            _t2.metric("Hedef ciro", f"{pd.to_numeric(_bl_df['beklenen_ciro'], errors='coerce').fillna(0).sum():,.0f} ₺")
        if "gerceklesen_ciro" in _bl_df.columns:
            _t3.metric("Gerçekleşen", f"{pd.to_numeric(_bl_df['gerceklesen_ciro'], errors='coerce').fillna(0).sum():,.0f} ₺")
        st.caption("Bu toplam, kaç bölgeye dağılmış olursa olsun senin (veya admin için herkesin) tüm müşterilerini kapsar." if _bl_rol != "admin"
                   else "Bu toplam, tüm kullanıcıların tüm bölgelerdeki tüm müşterilerini kapsar.")
        st.divider()
        st.caption("Yeni müşteri eklemek için mevcut 📥 Excel Aktar sayfasını kullanabilirsiniz — il/ilçe bilgisi girildiğinde bölgesi otomatik hesaplanır. Tek tek bölge listesi için Cari Liste ekranının en üstündeki 📍 Bölgeler kutucuklarını kullanın.")

# ── MUHASEBE – FATURALAR ──────────────────────────────────────────────────────
elif aktif == "muhasebe_fatura":
    sayfa_log("muhasebe_fatura")
    st.markdown("## 💰 Muhasebe – Faturalar")
    st.caption("Fatura oluşturma/silme işlemleri gerçek muhasebe sistemine anında yansır — dikkatli kullanın.")

    _muh_tok = _muh_token_oku()
    if not _muh_tok:
        st.warning("⚠️ Muhasebe sistemine henüz bağlı değilsiniz.")
        st.markdown("**Bağlantı kurmak için:**")
        st.markdown(f"1️⃣ Aşağıdaki bağlantıya tıklayın, muhasebe hesabınızla giriş yapıp erişime izin verin:")
        st.markdown(f"[🔗 Bağlantı kur]({_muh_authorize_url()})")
        st.markdown("2️⃣ Ekranda size gösterilen kodu kopyalayıp aşağıya yapıştırın:")
        _muh_kod = st.text_input("Doğrulama kodu", key="muh_kod_input")
        if st.button("Bağlan", key="muh_baglan_btn"):
            if _muh_kod.strip():
                with st.spinner("Bağlanılıyor..."):
                    _muh_yeni, _muh_hata = _muh_kod_ile_baglan(_muh_kod.strip())
                if _muh_yeni:
                    st.success("✅ Bağlantı başarılı!")
                    st.rerun()
                else:
                    st.error(f"❌ Bağlantı kurulamadı: {_muh_hata}")
            else:
                st.info("Lütfen önce kodu girin.")
    else:
        st.success("✅ Muhasebe sistemine bağlı.")
        _muh_c1, _muh_c2 = st.columns([1, 5])
        with _muh_c1:
            if st.button("🔄 Yenile", key="muh_yenile_btn"):
                st.rerun()

        # ── YENİ FATURA OLUŞTUR (CRM'den Parasut'a gönderir) ─────────────────
        with st.expander("➕ Yeni Fatura Oluştur"):
            st.caption("Kaydettiğinde fatura gerçekten muhasebe sisteminde oluşturulur. Test amaçlı kullanmayın.")
            _muh_cari_df = db_read("cari_kartlar", extra_sql="ORDER BY firma")
            if not _muh_cari_df.empty and "silindi" in _muh_cari_df.columns:
                _muh_cari_df = _muh_cari_df[~_muh_cari_df["silindi"].isin([1, "1", True, "true"])]
            if _muh_cari_df.empty or "firma" not in _muh_cari_df.columns:
                st.info("Fatura kesilecek cari bulunamadı. Önce bir cari kartı oluşturun.")
            else:
                _muh_cari_secim = st.selectbox(
                    "Cari", options=_muh_cari_df["id"].tolist(),
                    format_func=lambda x: _muh_cari_df.loc[_muh_cari_df["id"] == x, "firma"].values[0]
                                 if x in _muh_cari_df["id"].values else str(x),
                    key="muh_yeni_cari"
                )
                _muh_f1, _muh_f2 = st.columns(2)
                _muh_aciklama = _muh_f1.text_input("Açıklama / Hizmet", key="muh_yeni_aciklama")
                _muh_miktar = _muh_f2.number_input("Miktar", min_value=0.0, value=1.0, step=1.0, key="muh_yeni_miktar")
                _muh_f3, _muh_f4 = st.columns(2)
                _muh_birim_fiyat = _muh_f3.number_input("Birim Fiyat (₺)", min_value=0.0, value=0.0, step=100.0, key="muh_yeni_fiyat")
                _muh_kdv = _muh_f4.selectbox("KDV Oranı (%)", options=[0, 1, 8, 10, 18, 20], index=5, key="muh_yeni_kdv")
                _muh_f5, _muh_f6 = st.columns(2)
                _muh_f_tarih = _muh_f5.date_input("Fatura Tarihi", value=datetime.now().date(), key="muh_yeni_ftarih")
                _muh_v_tarih = _muh_f6.date_input("Vade Tarihi", value=datetime.now().date() + timedelta(days=30), key="muh_yeni_vtarih")

                if st.button("💾 Fatura Oluştur ve Gönder", type="primary", key="muh_yeni_kaydet_btn"):
                    if not _muh_aciklama.strip():
                        st.warning("Açıklama boş olamaz.")
                    elif _muh_birim_fiyat <= 0:
                        st.warning("Birim fiyat 0'dan büyük olmalı.")
                    else:
                        _muh_firma_adi = _muh_cari_df.loc[_muh_cari_df["id"] == _muh_cari_secim, "firma"].values[0]
                        with st.spinner("Müşteri kontrol ediliyor ve fatura oluşturuluyor..."):
                            _muh_contact_id, _muh_c_hata = _muh_contact_id_bul_veya_olustur(_muh_cari_secim, _muh_firma_adi)
                            if _muh_c_hata:
                                st.error(_muh_c_hata)
                            else:
                                _muh_sonuc, _muh_f_hata = _muh_fatura_olustur(
                                    _muh_contact_id, _muh_aciklama, _muh_miktar, _muh_birim_fiyat,
                                    _muh_kdv, _muh_f_tarih, _muh_v_tarih
                                )
                                if _muh_f_hata:
                                    st.error(f"Fatura oluşturulamadı: {_muh_f_hata}")
                                else:
                                    st.success("✅ Fatura başarıyla oluşturuldu.")
                                    st.rerun()

        with st.spinner("Faturalar alınıyor..."):
            _muh_veri, _muh_hata = _muh_api_get_tumu(
                f"/v4/{_MUH_COMPANY_ID}/sales_invoices",
                params={"sort": "-issue_date", "include": "contact,details.product"}
            )

        if _muh_hata:
            st.error(f"Faturalar alınamadı: {_muh_hata}")
            st.caption("Bağlantı süresi dolmuş olabilir — 'Yenile'ye basıp tekrar deneyin, sorun devam ederse yeniden bağlanmanız gerekebilir.")
        else:
            _muh_kayitlar = (_muh_veri or {}).get("data", [])
            st.markdown(f"**{len(_muh_kayitlar)} fatura**")
            _muh_index = _muh_dahil_index(_muh_veri)
            _muh_liste_render(_muh_kayitlar, [
                ("Fatura No", "invoice_no", None), ("Müşteri", "@contact", None),
                ("Tarih", "issue_date", None), ("Vade", "due_date", None),
                ("Net Tutar", "net_total", None), ("Toplam", "gross_total", None),
                ("Durum", "payment_status", None),
            ], sil_fn=_muh_fatura_sil, key_prefix="muh", dahil_index=_muh_index,
               detay_fn=_muh_kalem_detay_goster, bos_mesaj="Kayıtlı fatura bulunamadı.")

# ═══════════════════════════════════════════════════════════════════════════
# MUHASEBE — GENİŞLETİLMİŞ NATIVE SAYFALAR
# Her sayfa: açılışta muhasebe sisteminden anlık veri çeker (Parasut'ta yapılan
# değişiklik hemen görünür), CRM'den eklenen/silinen kayıt da anında muhasebe
# sistemine yazılır. Harici link / yeni sekme YOK — tamamı CRM içinde çalışır.
# ═══════════════════════════════════════════════════════════════════════════

elif aktif == "muhasebe_teklifler":
    sayfa_log("muhasebe_teklifler")
    st.markdown("## 📝 Muhasebe – Teklifler")
    st.caption("Teklif oluşturma/silme gerçek muhasebe sistemine anında yansır.")
    if not _muh_baglanti_var_mi():
        _muh_baglanti_uyar()
    else:
        if st.button("🔄 Yenile", key="mt_yenile"):
            st.rerun()
        with st.expander("➕ Yeni Teklif Oluştur"):
            _mt_cari_df = db_read("cari_kartlar", extra_sql="ORDER BY firma")
            if not _mt_cari_df.empty and "silindi" in _mt_cari_df.columns:
                _mt_cari_df = _mt_cari_df[~_mt_cari_df["silindi"].isin([1, "1", True, "true"])]
            if _mt_cari_df.empty or "firma" not in _mt_cari_df.columns:
                st.info("Önce bir cari kartı oluşturun.")
            else:
                _mt_cari = st.selectbox("Cari", options=_mt_cari_df["id"].tolist(),
                    format_func=lambda x: _mt_cari_df.loc[_mt_cari_df["id"] == x, "firma"].values[0]
                                 if x in _mt_cari_df["id"].values else str(x), key="mt_cari_sec")
                _mtc1, _mtc2 = st.columns(2)
                _mt_aciklama = _mtc1.text_input("Açıklama / Hizmet", key="mt_aciklama")
                _mt_miktar = _mtc2.number_input("Miktar", min_value=0.0, value=1.0, step=1.0, key="mt_miktar")
                _mtc3, _mtc4 = st.columns(2)
                _mt_fiyat = _mtc3.number_input("Birim Fiyat (₺)", min_value=0.0, value=0.0, step=100.0, key="mt_fiyat")
                _mt_kdv = _mtc4.selectbox("KDV Oranı (%)", options=[0, 1, 8, 10, 18, 20], index=5, key="mt_kdv")
                _mtc5, _mtc6 = st.columns(2)
                _mt_tarih = _mtc5.date_input("Teklif Tarihi", value=datetime.now().date(), key="mt_tarih")
                _mt_gecerlilik = _mtc6.date_input("Geçerlilik Tarihi", value=datetime.now().date() + timedelta(days=15), key="mt_gecerlilik")
                if st.button("💾 Teklif Oluştur ve Gönder", type="primary", key="mt_kaydet"):
                    if not _mt_aciklama.strip():
                        st.warning("Açıklama boş olamaz.")
                    elif _mt_fiyat <= 0:
                        st.warning("Birim fiyat 0'dan büyük olmalı.")
                    else:
                        _mt_firma = _mt_cari_df.loc[_mt_cari_df["id"] == _mt_cari, "firma"].values[0]
                        with st.spinner("Müşteri kontrol ediliyor ve teklif oluşturuluyor..."):
                            _mt_cid, _mt_ch = _muh_contact_id_bul_veya_olustur(_mt_cari, _mt_firma)
                            if _mt_ch:
                                st.error(_mt_ch)
                            else:
                                _mt_s, _mt_h = _muh_teklif_olustur(_mt_cid, _mt_aciklama, _mt_miktar, _mt_fiyat, _mt_kdv, _mt_tarih, _mt_gecerlilik)
                                if _mt_h:
                                    st.error(f"Teklif oluşturulamadı: {_mt_h}")
                                else:
                                    st.success("✅ Teklif oluşturuldu.")
                                    st.rerun()
        with st.spinner("Teklifler alınıyor..."):
            _mt_veri, _mt_hata = _muh_teklifler_getir()
        if _mt_hata:
            st.error(f"Teklifler alınamadı: {_mt_hata}")
        else:
            _mt_kayit = (_mt_veri or {}).get("data", [])
            st.markdown(f"**{len(_mt_kayit)} teklif**")
            _mt_index = _muh_dahil_index(_mt_veri)
            _muh_liste_render(_mt_kayit, [
                ("Teklif No", "invoice_no", None), ("Müşteri", "@contact", None),
                ("Tarih", "issue_date", None), ("Geçerlilik", "expiry_date", None),
                ("Net Tutar", "net_total", None), ("Toplam", "gross_total", None),
                ("Durum", "status", None),
            ], sil_fn=_muh_teklif_sil, key_prefix="mt", dahil_index=_mt_index,
               detay_fn=_muh_kalem_detay_goster, bos_mesaj="Kayıtlı teklif bulunamadı.")

elif aktif == "muhasebe_musteriler":
    sayfa_log("muhasebe_musteriler")
    st.markdown("## 👥 Muhasebe – Müşteriler")
    st.caption("Buradan eklenen müşteri anında muhasebe sisteminde de oluşur.")
    if not _muh_baglanti_var_mi():
        _muh_baglanti_uyar()
    else:
        if st.button("🔄 Yenile", key="mm_yenile"):
            st.rerun()
        with st.expander("➕ Yeni Müşteri Ekle"):
            _mm_ad = st.text_input("Firma / Ad Soyad", key="mm_ad")
            _mmc1, _mmc2 = st.columns(2)
            _mm_tel = _mmc1.text_input("Telefon", key="mm_tel")
            _mm_email = _mmc2.text_input("Email", key="mm_email")
            _mm_adres = st.text_input("Adres", key="mm_adres")
            if st.button("💾 Kaydet", type="primary", key="mm_kaydet"):
                if not _mm_ad.strip():
                    st.warning("Ad/firma boş olamaz.")
                else:
                    with st.spinner("Kaydediliyor..."):
                        _mm_s, _mm_h = _muh_contact_olustur(_mm_ad.strip(), "customer", _mm_tel, _mm_email, _mm_adres)
                    if _mm_h:
                        st.error(f"Kaydedilemedi: {_mm_h}")
                    else:
                        st.success("✅ Müşteri eklendi.")
                        st.rerun()
        with st.spinner("Müşteriler alınıyor..."):
            _mm_veri, _mm_hata = _muh_contacts_getir(account_type="customer")
        if _mm_hata:
            st.error(f"Müşteriler alınamadı: {_mm_hata}")
        else:
            _mm_kayit = (_mm_veri or {}).get("data", [])
            st.markdown(f"**{len(_mm_kayit)} müşteri**")
            _muh_liste_render(_mm_kayit, [
                ("Ad / Firma", "name", None), ("Telefon", "phone", None),
                ("Email", "email", None), ("Bakiye", "trl_balance", None),
            ], sil_fn=_muh_contact_sil, key_prefix="mm", bos_mesaj="Kayıtlı müşteri bulunamadı.")

elif aktif == "muhasebe_gider_listesi":
    sayfa_log("muhasebe_gider_listesi")
    st.markdown("## 🧾 Muhasebe – Gider Listesi")
    st.caption("Gider kaydı oluşturma/silme gerçek muhasebe sistemine anında yansır.")
    if not _muh_baglanti_var_mi():
        _muh_baglanti_uyar()
    else:
        if st.button("🔄 Yenile", key="mg_yenile"):
            st.rerun()
        with st.expander("➕ Yeni Gider Ekle"):
            _mg_tedarikci = st.text_input("Tedarikçi Adı", key="mg_tedarikci",
                help="Muhasebe sisteminde bu isimle kayıtlı tedarikçi varsa kullanılır, yoksa otomatik oluşturulur.")
            _mgc1, _mgc2 = st.columns(2)
            _mg_aciklama = _mgc1.text_input("Açıklama", key="mg_aciklama")
            _mg_miktar = _mgc2.number_input("Miktar", min_value=0.0, value=1.0, step=1.0, key="mg_miktar")
            _mgc3, _mgc4 = st.columns(2)
            _mg_fiyat = _mgc3.number_input("Birim Fiyat (₺)", min_value=0.0, value=0.0, step=100.0, key="mg_fiyat")
            _mg_kdv = _mgc4.selectbox("KDV Oranı (%)", options=[0, 1, 8, 10, 18, 20], index=5, key="mg_kdv")
            _mgc5, _mgc6 = st.columns(2)
            _mg_tarih = _mgc5.date_input("Fatura Tarihi", value=datetime.now().date(), key="mg_tarih")
            _mg_vade = _mgc6.date_input("Vade Tarihi", value=datetime.now().date() + timedelta(days=30), key="mg_vade")
            if st.button("💾 Gider Kaydet ve Gönder", type="primary", key="mg_kaydet"):
                if not _mg_tedarikci.strip():
                    st.warning("Tedarikçi adı boş olamaz.")
                elif not _mg_aciklama.strip():
                    st.warning("Açıklama boş olamaz.")
                elif _mg_fiyat <= 0:
                    st.warning("Birim fiyat 0'dan büyük olmalı.")
                else:
                    with st.spinner("Tedarikçi kontrol ediliyor ve gider oluşturuluyor..."):
                        _mg_cid, _mg_ch = _muh_contact_ada_gore_bul_veya_olustur(_mg_tedarikci.strip(), "supplier")
                        if _mg_ch:
                            st.error(_mg_ch)
                        else:
                            _mg_s, _mg_h = _muh_gider_olustur(_mg_cid, _mg_aciklama, _mg_miktar, _mg_fiyat, _mg_kdv, _mg_tarih, _mg_vade)
                            if _mg_h:
                                st.error(f"Gider oluşturulamadı: {_mg_h}")
                            else:
                                st.success("✅ Gider kaydedildi.")
                                st.rerun()
        with st.spinner("Giderler alınıyor..."):
            _mg_veri, _mg_hata = _muh_giderler_getir()
        if _mg_hata:
            st.error(f"Giderler alınamadı: {_mg_hata}")
        else:
            _mg_kayit = (_mg_veri or {}).get("data", [])
            st.markdown(f"**{len(_mg_kayit)} gider kaydı**")
            _mg_index = _muh_dahil_index(_mg_veri)
            _muh_liste_render(_mg_kayit, [
                ("Fiş No", "invoice_no", None), ("Tedarikçi", "@contact", None),
                ("Tarih", "issue_date", None), ("Vade", "due_date", None),
                ("Net Tutar", "net_total", None), ("Toplam", "gross_total", None),
                ("Durum", "payment_status", None),
            ], sil_fn=_muh_gider_sil, key_prefix="mg", dahil_index=_mg_index,
               detay_fn=_muh_kalem_detay_goster, bos_mesaj="Kayıtlı gider bulunamadı.")
            if _mg_kayit:
                with st.expander("🔍 Teknik Detay (ilk kaydın ham verisi)"):
                    st.caption("Gider oluşturma hatası devam ederse bu ham veriyi ekran görüntüsüyle paylaşın — "
                               "gerçek alan adlarını görüp oluşturma isteğini buna göre düzeltebiliriz.")
                    st.json(_mg_kayit[0])

elif aktif == "muhasebe_tedarikciler":
    sayfa_log("muhasebe_tedarikciler")
    st.markdown("## 🚚 Muhasebe – Tedarikçiler")
    st.caption("Buradan eklenen tedarikçi anında muhasebe sisteminde de oluşur.")
    if not _muh_baglanti_var_mi():
        _muh_baglanti_uyar()
    else:
        if st.button("🔄 Yenile", key="mtd_yenile"):
            st.rerun()
        with st.expander("➕ Yeni Tedarikçi Ekle"):
            _mtd_ad = st.text_input("Firma / Ad Soyad", key="mtd_ad")
            _mtdc1, _mtdc2 = st.columns(2)
            _mtd_tel = _mtdc1.text_input("Telefon", key="mtd_tel")
            _mtd_email = _mtdc2.text_input("Email", key="mtd_email")
            _mtd_adres = st.text_input("Adres", key="mtd_adres")
            if st.button("💾 Kaydet", type="primary", key="mtd_kaydet"):
                if not _mtd_ad.strip():
                    st.warning("Ad/firma boş olamaz.")
                else:
                    with st.spinner("Kaydediliyor..."):
                        _mtd_s, _mtd_h = _muh_contact_olustur(_mtd_ad.strip(), "supplier", _mtd_tel, _mtd_email, _mtd_adres)
                    if _mtd_h:
                        st.error(f"Kaydedilemedi: {_mtd_h}")
                    else:
                        st.success("✅ Tedarikçi eklendi.")
                        st.rerun()
        with st.spinner("Tedarikçiler alınıyor..."):
            _mtd_veri, _mtd_hata = _muh_contacts_getir(account_type="supplier")
        if _mtd_hata:
            st.error(f"Tedarikçiler alınamadı: {_mtd_hata}")
        else:
            _mtd_kayit = (_mtd_veri or {}).get("data", [])
            st.markdown(f"**{len(_mtd_kayit)} tedarikçi**")
            _muh_liste_render(_mtd_kayit, [
                ("Ad / Firma", "name", None), ("Telefon", "phone", None),
                ("Email", "email", None), ("Bakiye", "trl_balance", None),
            ], sil_fn=_muh_contact_sil, key_prefix="mtd", bos_mesaj="Kayıtlı tedarikçi bulunamadı.")

elif aktif == "muhasebe_calisanlar":
    sayfa_log("muhasebe_calisanlar")
    st.markdown("## 👔 Muhasebe – Çalışanlar")
    st.caption("Buradan eklenen çalışan anında muhasebe sisteminde de oluşur.")
    if not _muh_baglanti_var_mi():
        _muh_baglanti_uyar()
    else:
        if st.button("🔄 Yenile", key="mc_yenile"):
            st.rerun()
        with st.expander("➕ Yeni Çalışan Ekle"):
            _mcc1, _mcc2 = st.columns(2)
            _mc_ad = _mcc1.text_input("Ad", key="mc_ad")
            _mc_soyad = _mcc2.text_input("Soyad", key="mc_soyad")
            _mcc3, _mcc4 = st.columns(2)
            _mc_email = _mcc3.text_input("Email", key="mc_email")
            _mc_tc = _mcc4.text_input("TC Kimlik No", key="mc_tc")
            if st.button("💾 Kaydet", type="primary", key="mc_kaydet"):
                if not _mc_ad.strip() or not _mc_soyad.strip():
                    st.warning("Ad ve soyad zorunlu.")
                else:
                    with st.spinner("Kaydediliyor..."):
                        _mc_s, _mc_h = _muh_employee_olustur(_mc_ad.strip(), _mc_soyad.strip(), _mc_email, _mc_tc)
                    if _mc_h:
                        st.error(f"Kaydedilemedi: {_mc_h}")
                    else:
                        st.success("✅ Çalışan eklendi.")
                        st.rerun()
        with st.spinner("Çalışanlar alınıyor..."):
            _mc_veri, _mc_hata = _muh_employees_getir()
        if _mc_hata:
            st.error(f"Çalışanlar alınamadı: {_mc_hata}")
        else:
            _mc_kayit = (_mc_veri or {}).get("data", [])
            st.markdown(f"**{len(_mc_kayit)} çalışan**")
            _muh_liste_render(_mc_kayit, [
                ("Ad", "name", None), ("Soyad", "surname", None),
                ("Email", "email", None),
            ], sil_fn=_muh_employee_sil, key_prefix="mc", bos_mesaj="Kayıtlı çalışan bulunamadı.")

elif aktif == "muhasebe_kasa_banka":
    sayfa_log("muhasebe_kasa_banka")
    st.markdown("## 🏦 Muhasebe – Kasa ve Bankalar")
    st.caption("Bakiyeler muhasebe sisteminden anlık okunur (salt okunur — hesap açma/kapama Parasut'tan yapılır).")
    if not _muh_baglanti_var_mi():
        _muh_baglanti_uyar()
    else:
        if st.button("🔄 Yenile", key="mkb_yenile"):
            st.rerun()
        with st.spinner("Hesaplar alınıyor..."):
            _mkb_veri, _mkb_hata = _muh_accounts_getir()
        if _mkb_hata:
            st.error(f"Hesaplar alınamadı: {_mkb_hata}")
        else:
            _mkb_kayit = (_mkb_veri or {}).get("data", [])
            st.markdown(f"**{len(_mkb_kayit)} hesap**")
            _muh_liste_render(_mkb_kayit, [
                ("Hesap Adı", "name", None), ("Tür", "account_type", None),
                ("Para Birimi", "currency", None), ("Bakiye", "balance", None),
            ], bos_mesaj="Kayıtlı hesap bulunamadı.")

elif aktif == "muhasebe_cekler":
    sayfa_log("muhasebe_cekler")
    st.markdown("## 📑 Muhasebe – Çekler")
    st.caption("Bu sayfa muhasebe sisteminden anlık veri çeker (salt okunur).")
    if not _muh_baglanti_var_mi():
        _muh_baglanti_uyar()
    else:
        if st.button("🔄 Yenile", key="mck_yenile"):
            st.rerun()
        with st.spinner("Çekler alınıyor..."):
            _mck_veri, _mck_hata = _muh_cekler_getir()
        if _mck_hata:
            st.error(f"Çekler alınamadı: {_mck_hata}")
            st.caption("Bu özellik muhasebe hesabınızda aktif değilse veya API desteklemiyorsa bu hata normaldir.")
        else:
            _mck_kayit = (_mck_veri or {}).get("data", [])
            st.markdown(f"**{len(_mck_kayit)} çek**")
            _muh_liste_render(_mck_kayit, [
                ("Çek No", "check_no", None), ("Vade", "due_date", None),
                ("Tutar", "amount", None), ("Durum", "status", None),
            ], bos_mesaj="Kayıtlı çek bulunamadı.")

elif aktif in ("muhasebe_satis_raporu", "muhasebe_tahsilat_raporu", "muhasebe_gelirgider_raporu",
               "muhasebe_gider_raporu", "muhasebe_odeme_raporu", "muhasebe_kdv_raporu",
               "muhasebe_kasabanka_raporu", "muhasebe_nakit_raporu"):
    _mr_baslik = {
        "muhasebe_satis_raporu": "📊 Satışlar Raporu", "muhasebe_tahsilat_raporu": "💵 Tahsilatlar Raporu",
        "muhasebe_gelirgider_raporu": "📈 Gelir Gider Raporu", "muhasebe_gider_raporu": "📉 Giderler Raporu",
        "muhasebe_odeme_raporu": "💳 Ödemeler Raporu", "muhasebe_kdv_raporu": "🧮 KDV Raporu",
        "muhasebe_kasabanka_raporu": "🏦 Kasa / Banka Raporu", "muhasebe_nakit_raporu": "💧 Nakit Akışı Raporu",
    }[aktif]
    sayfa_log(aktif)
    st.markdown(f"## {_mr_baslik}")
    st.caption("Bu rapor, CRM'e muhasebe sisteminden anlık çekilen verilerden hesaplanır — "
               "Parasut'un kendi rapor ekranındaki tutarlarla küçük yuvarlama farkları olabilir.")
    if not _muh_baglanti_var_mi():
        _muh_baglanti_uyar()
    else:
        if st.button("🔄 Yenile", key=f"{aktif}_yenile"):
            st.rerun()

        _mr_donem = st.radio("Dönem", ["Bu Ay", "Bu Yıl", "Tümü"], horizontal=True, key=f"{aktif}_donem")
        _mr_bugun = datetime.now().date()
        if _mr_donem == "Bu Ay":
            _mr_bas = _mr_bugun.replace(day=1).isoformat()
        elif _mr_donem == "Bu Yıl":
            _mr_bas = _mr_bugun.replace(month=1, day=1).isoformat()
        else:
            _mr_bas = "0000-00-00"

        def _mr_tarih_filtrele(kayitlar, alan="issue_date"):
            if _mr_donem == "Tümü":
                return kayitlar
            return [k for k in kayitlar if str((k.get("attributes") or {}).get(alan, "")) >= _mr_bas]

        def _mr_sayi(v):
            try:
                return float(str(v).replace(",", ".") or 0)
            except Exception:
                return 0.0

        _mr_satis_veri, _mr_satis_hata = _muh_api_get_tumu(
            f"/v4/{_MUH_COMPANY_ID}/sales_invoices",
            params={"sort": "-issue_date", "include": "contact,details.product"})
        _mr_gider_veri, _mr_gider_hata = _muh_giderler_getir()

        if _mr_satis_hata or _mr_gider_hata:
            if _mr_satis_hata: st.error(f"Satış verisi alınamadı: {_mr_satis_hata}")
            if _mr_gider_hata: st.error(f"Gider verisi alınamadı: {_mr_gider_hata}")
        else:
            _mr_satis_index = _muh_dahil_index(_mr_satis_veri)
            _mr_gider_index = _muh_dahil_index(_mr_gider_veri)
            _mr_satislar = _mr_tarih_filtrele((_mr_satis_veri or {}).get("data", []))
            _mr_giderler = _mr_tarih_filtrele((_mr_gider_veri or {}).get("data", []))

            _mr_satis_net = sum(_mr_sayi((k.get("attributes") or {}).get("net_total")) for k in _mr_satislar)
            _mr_satis_brut = sum(_mr_sayi((k.get("attributes") or {}).get("gross_total")) for k in _mr_satislar)
            _mr_gider_net = sum(_mr_sayi((k.get("attributes") or {}).get("net_total")) for k in _mr_giderler)
            _mr_gider_brut = sum(_mr_sayi((k.get("attributes") or {}).get("gross_total")) for k in _mr_giderler)
            _mr_tahsil = sum(_mr_sayi((k.get("attributes") or {}).get("gross_total"))
                              for k in _mr_satislar if (k.get("attributes") or {}).get("payment_status") == "paid")
            _mr_odeme = sum(_mr_sayi((k.get("attributes") or {}).get("gross_total"))
                             for k in _mr_giderler if (k.get("attributes") or {}).get("payment_status") == "paid")
            _mr_kdv_satis = _mr_satis_brut - _mr_satis_net
            _mr_kdv_gider = _mr_gider_brut - _mr_gider_net

            if aktif == "muhasebe_satis_raporu":
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric("Toplam Fatura", len(_mr_satislar))
                _c2.metric("Net Tutar", f"{_mr_satis_net:,.2f} ₺")
                _c3.metric("Brüt Tutar", f"{_mr_satis_brut:,.2f} ₺")
                _muh_liste_render(_mr_satislar, [
                    ("Fatura No", "invoice_no", None), ("Müşteri", "@contact", None),
                    ("Tarih", "issue_date", None), ("Net Tutar", "net_total", None),
                    ("Toplam", "gross_total", None), ("Durum", "payment_status", None),
                ], dahil_index=_mr_satis_index, detay_fn=_muh_kalem_detay_goster,
                   key_prefix="mrsr", bos_mesaj="Kayıt bulunamadı.")

            elif aktif == "muhasebe_tahsilat_raporu":
                _c1, _c2 = st.columns(2)
                _c1.metric("Tahsil Edilen", f"{_mr_tahsil:,.2f} ₺")
                _c2.metric("Bekleyen (Tahmini)", f"{max(_mr_satis_brut - _mr_tahsil, 0):,.2f} ₺")
                _mr_odenmis = [k for k in _mr_satislar if (k.get("attributes") or {}).get("payment_status") == "paid"]
                _muh_liste_render(_mr_odenmis, [
                    ("Fatura No", "invoice_no", None), ("Müşteri", "@contact", None),
                    ("Tarih", "issue_date", None), ("Toplam", "gross_total", None),
                    ("Durum", "payment_status", None),
                ], dahil_index=_mr_satis_index, detay_fn=_muh_kalem_detay_goster,
                   key_prefix="mrth", bos_mesaj="Tahsil edilmiş kayıt bulunamadı.")

            elif aktif == "muhasebe_gelirgider_raporu":
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric("Gelir (Satış)", f"{_mr_satis_brut:,.2f} ₺")
                _c2.metric("Gider", f"{_mr_gider_brut:,.2f} ₺")
                _c3.metric("Net", f"{_mr_satis_brut - _mr_gider_brut:,.2f} ₺")

            elif aktif == "muhasebe_gider_raporu":
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric("Toplam Gider Kaydı", len(_mr_giderler))
                _c2.metric("Net Tutar", f"{_mr_gider_net:,.2f} ₺")
                _c3.metric("Brüt Tutar", f"{_mr_gider_brut:,.2f} ₺")
                _muh_liste_render(_mr_giderler, [
                    ("Fiş No", "invoice_no", None), ("Tedarikçi", "@contact", None),
                    ("Tarih", "issue_date", None), ("Net Tutar", "net_total", None),
                    ("Toplam", "gross_total", None), ("Durum", "payment_status", None),
                ], dahil_index=_mr_gider_index, detay_fn=_muh_kalem_detay_goster,
                   key_prefix="mrgd", bos_mesaj="Kayıt bulunamadı.")

            elif aktif == "muhasebe_odeme_raporu":
                _c1, _c2 = st.columns(2)
                _c1.metric("Ödenen", f"{_mr_odeme:,.2f} ₺")
                _c2.metric("Bekleyen (Tahmini)", f"{max(_mr_gider_brut - _mr_odeme, 0):,.2f} ₺")
                _mr_odenmis_g = [k for k in _mr_giderler if (k.get("attributes") or {}).get("payment_status") == "paid"]
                _muh_liste_render(_mr_odenmis_g, [
                    ("Fiş No", "invoice_no", None), ("Tedarikçi", "@contact", None),
                    ("Tarih", "issue_date", None), ("Toplam", "gross_total", None),
                    ("Durum", "payment_status", None),
                ], dahil_index=_mr_gider_index, detay_fn=_muh_kalem_detay_goster,
                   key_prefix="mrod", bos_mesaj="Ödenmiş kayıt bulunamadı.")

            elif aktif == "muhasebe_kdv_raporu":
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric("Hesaplanan KDV (Satış)", f"{_mr_kdv_satis:,.2f} ₺")
                _c2.metric("İndirilecek KDV (Gider)", f"{_mr_kdv_gider:,.2f} ₺")
                _c3.metric("Ödenecek/Devreden KDV", f"{_mr_kdv_satis - _mr_kdv_gider:,.2f} ₺")
                st.caption("Yaklaşık hesaplama: brüt tutar - net tutar farkı üzerinden. Kesin KDV beyanı için Parasut'un kendi KDV raporunu esas alın.")

            elif aktif == "muhasebe_kasabanka_raporu":
                with st.spinner("Hesaplar alınıyor..."):
                    _mr_hesap_veri, _mr_hesap_hata = _muh_accounts_getir()
                if _mr_hesap_hata:
                    st.error(f"Hesaplar alınamadı: {_mr_hesap_hata}")
                else:
                    _mr_hesaplar = (_mr_hesap_veri or {}).get("data", [])
                    _mr_toplam_bakiye = sum(_mr_sayi((k.get("attributes") or {}).get("balance")) for k in _mr_hesaplar)
                    st.metric("Toplam Bakiye (Tüm Hesaplar)", f"{_mr_toplam_bakiye:,.2f} ₺")
                    _muh_liste_render(_mr_hesaplar, [
                        ("Hesap Adı", "name", None), ("Tür", "account_type", None),
                        ("Para Birimi", "currency", None), ("Bakiye", "balance", None),
                    ], bos_mesaj="Kayıtlı hesap bulunamadı.")

            elif aktif == "muhasebe_nakit_raporu":
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric("Nakit Giriş (Tahsilat)", f"{_mr_tahsil:,.2f} ₺")
                _c2.metric("Nakit Çıkış (Ödeme)", f"{_mr_odeme:,.2f} ₺")
                _c3.metric("Net Nakit Akışı", f"{_mr_tahsil - _mr_odeme:,.2f} ₺")

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='position:fixed;bottom:0;left:0;right:0;background:#f0f2f6;padding:6px;text-align:center;font-size:11px;color:#888;z-index:999;'>"
    "MWCRMPRO v6.7 &nbsp;|&nbsp; "
    "<a href='tel:05400344228' style='color:#888;text-decoration:none;'>📞 5400344228</a>"
    " &nbsp;|&nbsp; "
    "<a href='mailto:osnenufu@gmail.com' style='color:#888;text-decoration:none;'>✉️ osnenufu@gmail.com</a>"
    " &nbsp;|&nbsp; "
    "<span style='color:#9ca3af;'>💬 WhatsApp (devre dışı)</span>"
    "</div>",
    unsafe_allow_html=True
)