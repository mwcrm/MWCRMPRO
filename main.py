import streamlit as st
import sqlite3
import pandas as pd
import shutil
import os
import io
import re
import json
from datetime import datetime, timedelta

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

def _telefon_temizle(seri):
    """5413578020.0 gibi float telefonları 5413578020 string'ine çevirir"""
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
        return s
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
        if _rol in ["admin","admin "] or not _kul:
            return df
        if df.empty or "atanan_kullanici" not in df.columns:
            return df
        return df[df["atanan_kullanici"].astype(str) == _kul]
    except:
        return df

# ── BÖLGE EŞLEŞTİRME (il + ilçe → bölge adı) ────────────────────────────────
_BL_ISTANBUL_ANADOLU = {"adalar","atasehir","beykoz","cekmekoy","kadikoy","kartal",
    "maltepe","pendik","sancaktepe","sultanbeyli","sile","tuzla","umraniye","uskudar"}
_BL_ISTANBUL_AVRUPA = {"arnavutkoy","avcilar","bagcilar","bahcelievler","bakirkoy",
    "basaksehir","bayrampasa","besiktas","beylikduzu","beyoglu","buyukcekmece",
    "catalca","esenler","esenyurt","eyupsultan","fatih","gaziosmanpasa","gungoren",
    "kagithane","kucukcekmece","sariyer","silivri","sisli","zeytinburnu"}
_BL_IL_ADI = {
    "tekirdag":"Tekirdağ","kocaeli":"Kocaeli","bursa":"Bursa","manisa":"Manisa",
    "ankara":"Ankara","konya":"Konya","eskisehir":"Eskişehir","denizli":"Denizli","aydin":"Aydın",
}

def _bl_sadelestir(s):
    s = str(s or "").strip().lower()
    for _k,_v in {"ı":"i","i̇":"i","ş":"s","ğ":"g","ü":"u","ö":"o","ç":"c"}.items():
        s = s.replace(_k,_v)
    return s

def il_ilce_bolge_bul(il, ilce):
    """il+ilçe bilgisinden bölge adı üretir. Sadece tanımlı 11 bölgeden biriyse eşleşir,
    diğer her şey (tanımsız il, İstanbul'un tanımsız ilçesi, boş veri) Havuz'a düşer."""
    _il = _bl_sadelestir(il)
    _ilce = _bl_sadelestir(ilce)
    if not _il:
        return None
    if "istanbul" in _il:
        if _ilce in _BL_ISTANBUL_ANADOLU:
            return "İstanbul Anadolu"
        if _ilce in _BL_ISTANBUL_AVRUPA:
            return "İstanbul Avrupa"
        return None
    return _BL_IL_ADI.get(_il)

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
        "yeni": "Yeni Kart", "liste": "Cari Liste", "analiz": "Müşteri Analizi",
        "randevu": "Randevular", "teklif": "Spot Teklif", "ozel_teklif": "Özel Teklif",
        "rota_analiz": "Rota Analiz", "operasyon": "Operasyon", "kisiler": "Telefon Kişiler",
        "rapor": "Raporlar", "excel": "Excel", "kullanici": "Kullanıcılar",
        "admin_rapor": "Admin Rapor", "harita": "Müşteri Haritası", "patron": "Patron",
        "musteri_atama": "Müşteri Atama", "islem_takip": "İşlem Takip",
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
        return ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]
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
    # ── LOGO ──────────────────────────────────────────────────────────────────
    st.markdown("""
<div style="text-align:center;padding:2rem 0 1.5rem;">
  <div style="width:64px;height:64px;background:#1d4ed8;border-radius:16px;
       display:inline-flex;align-items:center;justify-content:center;margin-bottom:12px;">
    <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
      <rect x="4" y="4" width="12" height="12" rx="2" fill="white" opacity=".9"/>
      <rect x="20" y="4" width="12" height="12" rx="2" fill="white" opacity=".7"/>
      <rect x="4" y="20" width="12" height="12" rx="2" fill="white" opacity=".7"/>
      <rect x="20" y="20" width="12" height="12" rx="2" fill="white" opacity=".5"/>
    </svg>
  </div>
  <div style="font-size:26px;font-weight:600;color:#0f172a;letter-spacing:-.5px;">MWCRMPRO</div>
  <div style="font-size:13px;color:#64748b;margin-top:4px;">Cari Yönetim Sistemi</div>
</div>
""", unsafe_allow_html=True)

    _gc1, _gc2, _gc3 = st.columns([1,2,1])
    with _gc2:
        # ── CİHAZ SEÇİMİ — radio buton ile, rerun YOK ────────────────────────
        st.markdown("""
<div style="background:white;border:0.5px solid #e2e8f0;border-radius:16px;
     padding:20px 20px 16px;margin-bottom:12px;">
  <div style="font-size:13px;color:#64748b;text-align:center;margin-bottom:14px;font-weight:500;">
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

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ── GİRİŞ FORMU ────────────────────────────────────────────────────────
        st.markdown("""
<div style="background:white;border:0.5px solid #e2e8f0;border-radius:16px;padding:20px 20px 4px;">
  <div style="font-size:16px;font-weight:600;color:#0f172a;margin-bottom:4px;">Giriş Yap</div>
</div>
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
    "yeni":"Yeni Kart","liste":"Cari Liste","analiz":"Müşteri Analizi",
    "randevu":"Randevular","teklif":"Spot Teklif","ozel_teklif":"Özel Teklif",
    "rota_analiz":"Rota Analiz","operasyon":"Operasyon","kisiler":"Telefon Kişiler",
    "rapor":"Raporlar","excel":"Excel","kullanici":"Kullanıcılar",
    "admin_rapor":"Admin Rapor","harita":"Müşteri Haritası","patron":"Patron",
    "musteri_atama":"Müşteri Atama","islem_takip":"İşlem Takip",
}
_aktif_cfg = st.session_state.get("aktif_tab","liste")
_baslik_cfg = "MWCRMPRO | " + _sayfa_adlari_cfg.get(_aktif_cfg,"MWCRMPRO")
st.set_page_config(page_title=_baslik_cfg, layout="wide", initial_sidebar_state="expanded")

# Sekme başlığını aktif menüye göre güncelle
_sayfa_adlari = {
    "yeni":"Yeni Kart","liste":"Cari Liste","analiz":"Müşteri Analizi",
    "randevu":"Randevular","teklif":"Spot Teklif","ozel_teklif":"Özel Teklif",
    "rota_analiz":"Rota Analiz","operasyon":"Operasyon","kisiler":"Telefon Kişiler",
    "rapor":"Raporlar","excel":"Excel","kullanici":"Kullanıcılar",
    "admin_rapor":"Admin Rapor","harita":"Müşteri Haritası","patron":"Patron",
    "musteri_atama":"Müşteri Atama","islem_takip":"İşlem Takip",
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
_e_r1      = st.session_state.get("_ekran_r1","")
_e_r2      = st.session_state.get("_ekran_r2","")
_e_tema_bg = st.session_state.get("_ekran_tema","")
_e_ust     = st.session_state.get("_ust_px", 32)
_e_alt     = st.session_state.get("_alt_px", 32)
_e_yan     = st.session_state.get("_yan_px", 16)

_takim_css = ""
if _e_r1 and _e_r2:
    _takim_css = f"""
section[data-testid="stSidebar"] {{ background: {_e_r2} !important; }}
section[data-testid="stSidebar"] .stButton>button {{ border-color: {_e_r1} !important; color: {_e_r2} !important; background: {_e_r2} !important; }}
section[data-testid="stSidebar"] .stButton>button p {{ color: {_e_r1} !important; }}
section[data-testid="stSidebar"] .stButton>button[kind="primary"] {{ background: {_e_r1} !important; }}
section[data-testid="stSidebar"] .stButton>button[kind="primary"] p {{ color: {_e_r2} !important; }}
section[data-testid="stSidebar"] div[style*="font-size:15px"], section[data-testid="stSidebar"] div[style*="font-size:14px"] {{ color: {_e_r1} !important; }}
"""
_bg_css = f"body, .main {{ background-color: {_e_tema_bg} !important; }}" if _e_tema_bg and not _e_r1 else ""

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
{_takim_css}
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
  <a class="mw-nav-btn" id="mwnav-analiz" href="?_nav=analiz"><span class="nav-ikon">🔍</span>Analiz</a>
  <a class="mw-nav-btn" id="mwnav-randevu" href="?_nav=randevu"><span class="nav-ikon">📅</span>Randevu</a>
  <a class="mw-nav-btn" id="mwnav-teklif" href="?_nav=teklif"><span class="nav-ikon">📄</span>Teklif</a>
  <a class="mw-nav-btn" id="mwnav-harita" href="?_nav=harita"><span class="nav-ikon">🗺️</span>Harita</a>
</div>""", unsafe_allow_html=True)

# Gizli tab geçiş butonları — mobil nav bunları tetikler
# Mobil nav — query param ile tab geçişi (sadece mobil nav için)
try:
    _mob_nav_qp = st.query_params.get("_nav", "")
    _mob_nav_tablar = ["liste","analiz","randevu","teklif","harita","rapor","yeni","harita"]
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
    'teklif':'Spot Teklif','ozel_teklif':'Özel Teklif','harita':'Müşteri Haritası',
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
    """5544929309.0 → 5544929309"""
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
        return s
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

@st.cache_data(ttl=30, show_spinner=False)
def _notlar_yukle(cari_id):
    try:
        _sb = get_sb_client()
        if _sb:
            _r = _sb.table("cari_aciklamalar").select("*").eq("cari_id", int(cari_id)).execute()
            return _r.data or []
    except: pass
    return []

@st.dialog("📋 Notlar & Randevu", width="large")
def not_dialog(cari_id, firma_adi=""):
    """Ekran ortasında açılan not + randevu + silme penceresi"""
    _tab_not, _tab_rdv, _tab_sil = st.tabs(["📝 Notlar", "📅 Randevu Ekle", "🗑️ Cari Sil"])
    with _tab_not:
        not_paneli(cari_id, firma_adi, key_prefix="dlg")
    with _tab_rdv:
        if firma_adi:
            st.markdown(f"**{firma_adi}** için randevu ekle")
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
            except Exception as _re:
                st.error(f"Hata: {_re}")
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
                _veri = {"cari_id": int(cari_id), "aciklama": _yeni.strip(), "olusturan": _yazar, "cari_adi": str(firma_adi)}
                if _sb: _sb.table("cari_aciklamalar").insert(_veri).execute()
                try: _notlar_yukle.clear()
                except: pass
                st.success("✅ Eklendi!")
                st.rerun()
            except Exception as _ne:
                st.error(f"Hata: {_ne}")
        else:
            st.warning("Not boş!")



_TAB_LISTESI_DEFAULT = ["yeni", "liste", "analiz", "islem_takip", "randevu", "teklif", "ozel_teklif", "rota_analiz", "operasyon", "kisiler", "rapor", "excel", "kullanici", "admin_rapor", "harita", "patron", "musteri_atama"]
_TAB_ETIKETLER = {
    "yeni": "➕ Yeni Kart Ekle",
    "liste": "📋 Cari Liste / Düzenle",
    "rapor": "📊 Raporlar",
    "teklif": "📄 Spot Teklif",
    "ozel_teklif": "⭐ Özel Teklif",
    "excel": "📥 Excel Aktar",
    "kisiler": "📞 Telefon Kişiler",
    "analiz": "🔍 Müşteri Analizi",
    "islem_takip": "📋 İşlem Takip",
    
    "randevu": "📅 Randevular",
    "kullanici": "👥 Kullanıcı Yönetimi",
    "mesajlar": "💬 Mesajlar",
    "admin_rapor": "📊 Rapor Tasarla",
    "harita": "🗺️ Müşteri Haritası",
    "rota_analiz": "🚚 Rota Analiz",
    "operasyon": "🚛 Operasyon",
    "patron": "👑 Yönetim Paneli",
    "musteri_atama": "🎯 Müşteri Atama",
    
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
                    tam_liste += ["kullanici","admin_rapor","patron"]
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
                    tam_liste += ["kullanici","admin_rapor","patron"]
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
        tam_liste += ["kullanici","admin_rapor","patron"]
    return _temizle(tam_liste)

def save_menu_tercihi(kullanici, sira):
    # Analiz her zaman listede olsun
    if "analiz" not in sira:
        try:
            idx = sira.index("liste") + 1
            sira.insert(idx, "analiz")
        except: sira.append("analiz")
    if "detay_cari" not in sira:
        try:
            idx = sira.index("analiz") + 1
            sira.insert(idx, "detay_cari")
        except: sira.append("detay_cari")

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
/* Tüm scroll barları gizle */
* { scrollbar-width: none !important; -ms-overflow-style: none !important; }
*::-webkit-scrollbar { display: none !important; width: 0 !important; height: 0 !important; }
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
        "<div style='display:flex;align-items:center;gap:9px;font-size:15px;font-weight:700;color:#1a4f9e;"
        "padding:14px 10px 14px;letter-spacing:0.4px;border-bottom:2px solid #2568c7;margin-bottom:10px;'>"
        "🏢 MWCRMPRO</div>",
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
    _SADECE_ADMIN = {"patron", "admin_rapor", "kullanici", "musteri_atama", "excel"}
    if st.session_state.get("rol") != "admin":
        _sb_liste = [t for t in _sb_liste if t not in _SADECE_ADMIN]

    _TAB_RENKLER = {
        "yeni":        "#16a34a",
        "liste":       "#0369a1",
        "randevu":     "#1d4ed8",
        "teklif":      "#b45309",
        "ozel_teklif": "#7c3aed",
        "kisiler":     "#0f766e",
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
    _sadece_admin_menuler = ["kisiler"]
    if _menu_rol != "admin":
        _sb_liste = [t for t in _sb_liste if t not in _sadece_admin_menuler]

    # ── MENÜ GÖRÜNÜMÜ: Gruplu (akordeon) ────────────────────────────────────────
    st.markdown("""<style>
    section[data-testid='stSidebar'] { background-color:#ffffff; }
    section[data-testid='stSidebar'] hr { border-color:#eceae2; }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary'] {
        background:transparent; border:none; border-radius:8px;
        justify-content:flex-start; text-align:left;
        transition:background-color .15s ease, color .15s ease;
    }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary'] p { color:#3d3d3a !important; font-weight:500; transition:color .15s ease; }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary']:hover { background:#f6f8fb; }
    section[data-testid='stSidebar'] .stButton>button[kind='secondary']:hover p { color:#1a4f9e !important; }
    section[data-testid='stSidebar'] .stButton>button[kind='primary'] {
        background:#eef4fc; border:none; border-left:3px solid #2568c7; border-radius:8px;
        justify-content:flex-start; text-align:left;
        transition:background-color .15s ease;
    }
    section[data-testid='stSidebar'] .stButton>button[kind='primary'] p { color:#1a4f9e !important; font-weight:600; }
    section[data-testid='stSidebar'] label p, section[data-testid='stSidebar'] .stMarkdown p { color:#3d3d3a; }
    section[data-testid='stSidebar'] summary p, section[data-testid='stSidebar'] summary span { color:#3d3d3a !important; }
    </style>""", unsafe_allow_html=True)

    _MENU_GRUPLARI = [
        ("Cari işlemleri",    ["yeni", "liste", "excel"]),
        ("Analiz ve takip",   ["analiz", "islem_takip"]),
        ("Randevu ve teklif", ["randevu", "teklif", "ozel_teklif"]),
        ("Saha",              ["rota_analiz", "operasyon", "harita"]),
        ("Yönetim",           ["kullanici", "patron", "musteri_atama"]),
        ("Raporlar",          ["admin_rapor", "rapor"]),
        ("Telefon Kişiler",   ["kisiler"]),
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
                _c1, _c2 = st.columns([1, 8])
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
                _c1, _c2 = st.columns([1, 8])
                with _c2:
                    if st.button(_etiket, use_container_width=True,
                                 type="primary" if _aktif_mi else "secondary",
                                 key=f"sb_diger_{_tab_key}"):
                        st.session_state["aktif_tab"] = _tab_key
                        st.rerun()


    # ── ALT BÖLÜM ─────────────────────────────────────────────────────────────
    st.divider()

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
    _kc1.markdown(
        f"<div style='padding:2px 4px;line-height:1.5;'>"
        f"<span style='font-size:12px;font-weight:500;'>👤 {st.session_state.get('kullanici','')}</span>"
        f" <span style='font-size:11px;color:#64748b;'>· {st.session_state.get('rol','')}</span>"
        f"</div>",
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
  var _tabMap = {{'liste':'liste','analiz':'analiz','randevu':'randevu',
    'teklif':'teklif','ozel_teklif':'teklif','harita':'harita'}};
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
    mevcut_il   = duzenle.get("il","") if duzenle and duzenle.get("il","") in il_listesi else il_listesi[0]
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
    ilce_list = ILLER_ILCELER.get(il, [""])
    mevcut_ilce = duzenle.get("ilce","") if duzenle else ""
    if mevcut_ilce not in ilce_list: mevcut_ilce = ilce_list[0] if ilce_list else ""
    ilce_idx = ilce_list.index(mevcut_ilce) if mevcut_ilce in ilce_list else 0
    ilce    = r2c2.selectbox("İlçe", ilce_list, index=ilce_idx, key=f"yeni_ilce_dis_{_form_id}")
    durum_opts = ["Aktif","Hedef","Pasif"]
    durum_idx  = durum_opts.index(duzenle.get("durum","Aktif")) if duzenle and duzenle.get("durum","") in durum_opts else 0
    durum   = r2c3.selectbox("Durum", durum_opts, index=durum_idx, key=f"yeni_durum_dis_{_form_id}")
    temsilci_dis = r2c4.text_input("Temsilci", value=duzenle.get("temsilci","") if duzenle else "", key=f"yeni_temsilci_dis_{_form_id}", placeholder="Temsilci adı")
    seg_opts = ["--","👑 A+","⭐ A","🔵 B","⚪ C"]
    seg_idx  = seg_opts.index(duzenle.get("segment","--")) if duzenle and duzenle.get("segment","--") in seg_opts else 0
    segment  = r2c5.selectbox("Segment", seg_opts, index=seg_idx, key=f"yeni_seg_dis_{_form_id}")
    _asama_default = duzenle.get("islem_asamasi") if duzenle else st.session_state.pop("varsayilan_asama", None)
    asama_idx = _asama_base.index(_asama_default) if _asama_default and _asama_default in _asama_base else 0
    asama    = r2c6.selectbox("İşlem Aşaması", _asama_base, index=asama_idx, key=f"yeni_asama_dis_{_form_id}")

    with st.form("yeni_kart_form"):
        # ── SATIR 1: Firma, Yetkili, GSM, Sabit Tel, E-Mail ─────────────────
        r1c1,r1c2,r1c3,r1c4,r1c5 = st.columns(5)
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
            if not firma:
                st.warning("Firma adı boş bırakılamaz!")
            elif duzenle:
                ok = db_update("cari_kartlar", {
                    "firma": firma, "yetkili": yetkili, "gsm": gsm,
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
                    "firma": firma, "yetkili": yetkili, "gsm": gsm,
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
elif aktif == "liste":
    sayfa_log("liste")

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
            "Negatif Portföy": ("#fee2e2","#991b1b"),
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
    df = get_cari_listesi()
    if not df.empty and "tarih" in df.columns:
        df = df.sort_values("tarih", ascending=False).reset_index(drop=True)

    if not df.empty:
        for _tk in ["gsm","sabit"]:
            if _tk in df.columns:
                df[_tk] = _telefon_temizle(df[_tk])

    # ── ATAMA FİLTRESİ — admin hepsini görür, kullanıcı sadece kendine atananları ──
    df = _atama_filtresi_uygula(df)

    # ── BÖLGELER — açılır/kapanır, kısa etiketli kutucuklar, il/ilçe'den otomatik hesaplanır ──
    if not df.empty and "il" in df.columns:
        _bl_kisa_ad = {"İstanbul Anadolu": "İst And", "İstanbul Avrupa": "İst Avr"}
        _bl_ikon = {
            "İstanbul Anadolu": "🌉", "İstanbul Avrupa": "🕌", "Havuz (Bölgesiz)": "📦",
            "Adana": "🌶️", "Adıyaman": "🏔️", "Afyonkarahisar": "🍬", "Ağrı": "🏔️",
            "Amasya": "🍎", "Ankara": "🏛️", "Antalya": "🏖️", "Artvin": "🌲",
            "Aydın": "🍈", "Balıkesir": "🫒", "Bartın": "🌲", "Batman": "🛢️",
            "Bayburt": "🏔️", "Bilecik": "🏭", "Bingöl": "🏔️", "Bitlis": "🏔️",
            "Bolu": "🌲", "Burdur": "🌸", "Bursa": "🏔️", "Çanakkale": "🐎",
            "Çankırı": "🧂", "Çorum": "🫘", "Denizli": "🐓", "Diyarbakır": "🍉",
            "Düzce": "🌲", "Edirne": "🕌", "Elazığ": "🍒", "Erzincan": "🏔️",
            "Erzurum": "❄️", "Eskişehir": "🎓", "Gaziantep": "🥙", "Giresun": "🌰",
            "Gümüşhane": "⛏️", "Hakkari": "🏔️", "Hatay": "🍊", "Iğdır": "🏔️",
            "Isparta": "🌹", "İzmir": "🌊", "Kahramanmaraş": "🍦", "Karabük": "⚒️",
            "Karaman": "🐑", "Kars": "🧀", "Kastamonu": "🌲", "Kayseri": "🌋",
            "Kırıkkale": "🏭", "Kırklareli": "🌾", "Kırşehir": "🌾", "Kilis": "🕌",
            "Kocaeli": "⚓", "Konya": "🌀", "Kütahya": "🍇", "Malatya": "🍑",
            "Manisa": "🍇", "Mardin": "🕌", "Mersin": "🍋", "Muğla": "🏖️",
            "Muş": "🏔️", "Nevşehir": "🎈", "Niğde": "🥔", "Ordu": "🌰",
            "Osmaniye": "🌶️", "Rize": "🍵", "Sakarya": "🌲", "Samsun": "⚓",
            "Siirt": "🐐", "Sinop": "⚓", "Sivas": "🏔️", "Şanlıurfa": "🍆",
            "Şırnak": "🏔️", "Tekirdağ": "🍷", "Tokat": "🍎", "Trabzon": "🌊",
            "Tunceli": "🏔️", "Uşak": "🧵", "Van": "🐈", "Yalova": "🌡️",
            "Yozgat": "🌾", "Zonguldak": "⛏️",
        }
        _bl_ilce_kol_cl = "ilce" if "ilce" in df.columns else None
        _bl_chip_bolge_ham = df.apply(
            lambda r: il_ilce_bolge_bul(r.get("il",""), r.get(_bl_ilce_kol_cl,"") if _bl_ilce_kol_cl else ""), axis=1)
        # Tanımsız il/ilçe'ler tek tek kutucuk olmaz, hepsi "Havuz (Bölgesiz)" altında toplanır
        _bl_chip_bolge = _bl_chip_bolge_ham.fillna("Havuz (Bölgesiz)")
        _bl_chip_sayim = _bl_chip_bolge.value_counts()
        if not _bl_chip_sayim.empty:
            with st.expander(f"📍 Bölgeler  ·  {len(_bl_chip_sayim)} bölge", expanded=False):
                _bl_chip_cols = st.columns(min(len(_bl_chip_sayim), 8) or 1)
                for _ci, (_bl_ad, _bl_adet) in enumerate(_bl_chip_sayim.items()):
                    if _bl_adet <= 0:
                        continue  # müşterisi olmayan bölge asla gösterilmez
                    _bl_kisa = _bl_kisa_ad.get(_bl_ad, _bl_ad)
                    _bl_ic = _bl_ikon.get(_bl_ad, "📍")
                    _bl_etiket = f"{_bl_ic} {_bl_kisa} {_bl_adet}"
                    with _bl_chip_cols[_ci % len(_bl_chip_cols)]:
                        if st.button(_bl_etiket, key=f"cl_bolge_chip_{_bl_ad}", use_container_width=True):
                            if _bl_ad == "Havuz (Bölgesiz)":
                                # Havuz'daki kayıtların çoğu boş/tanımsız il içerebilir — gerçek il
                                # değerlerine dayanmayan, "hiçbir tanımlı bölgeye uymayanlar" filtresi kullanılır.
                                st.session_state["_bl_havuz_filtre"] = True
                                if "_cl_fil_il_multi" in st.session_state:
                                    del st.session_state["_cl_fil_il_multi"]
                                if "_cl_fil_ilce_multi" in st.session_state:
                                    del st.session_state["_cl_fil_ilce_multi"]
                                if "_bl_ilce_filtre" in st.session_state:
                                    del st.session_state["_bl_ilce_filtre"]
                                st.session_state.pop("_bl_ilce_filtre_ad", None)
                            else:
                                st.session_state.pop("_bl_havuz_filtre", None)
                                _bl_chip_df = df[_bl_chip_bolge == _bl_ad]
                                if "il" in _bl_chip_df.columns:
                                    st.session_state["_cl_fil_il_multi"] = sorted(
                                        _bl_chip_df["il"].dropna().astype(str).unique().tolist())
                                if "_cl_fil_ilce_multi" in st.session_state:
                                    del st.session_state["_cl_fil_ilce_multi"]
                                if _bl_ilce_kol_cl and _bl_ad in ("İstanbul Anadolu", "İstanbul Avrupa"):
                                    st.session_state["_bl_ilce_filtre"] = sorted(
                                        _bl_chip_df["ilce"].dropna().astype(str).unique().tolist())
                                    st.session_state["_bl_ilce_filtre_ad"] = _bl_ad
                                elif "_bl_ilce_filtre" in st.session_state:
                                    del st.session_state["_bl_ilce_filtre"]
                                    st.session_state.pop("_bl_ilce_filtre_ad", None)
                            st.rerun()

    with st.expander("🔍 Mükerrer (Aynı İsimli) Müşterileri Bul ve Birleştir"):
        if df.empty or "firma" not in df.columns:
            st.caption("Veri yok.")
        else:
            _firma_gruplari = df.groupby(df["firma"].str.strip().str.upper())["id"].apply(list)
            _mukerrerler = {k: v for k, v in _firma_gruplari.items() if len(v) > 1}
            if not _mukerrerler:
                st.caption("Mükerrer müşteri bulunamadı.")
            else:
                st.warning(f"{len(_mukerrerler)} mükerrer firma adı bulundu.")
                _mr_tab1, _mr_tab2 = st.tabs(["📋 Toplu Karşılaştırma (hepsi)", "🔎 Tek Seçerek Karşılaştır"])

                with _mr_tab1:
                    st.caption("Her grupta iki kayıt gösterilir. Hangisini silmek istediğinize siz karar verin. Silinen kayıt listeden kalkar, diğeri kalır.")
                    _silinen_t = 0
                    _goster_kolon = [c for c in ["id","firma","gsm","il","ilce","temsilci","segment","notlar"] if c in df.columns]
                    for _fname, _fids in list(_mukerrerler.items()):
                        st.markdown("---")
                        st.markdown(f"**{_fname}** — {len(_fids)} kayıt")
                        for _did in _fids:
                            _satir = df[df["id"] == _did]
                            if _satir.empty:
                                continue
                            _s = _satir.iloc[0]
                            _kc1, _kc2 = st.columns([5,1])
                            with _kc1:
                                _detay = " | ".join([f"**{c}:** {_s.get(c,'')}" for c in _goster_kolon if str(_s.get(c,"")).strip() not in ["","nan","None"]])
                                st.markdown(f"🔹 {_detay}")
                            with _kc2:
                                if st.button("🗑 Sil", key=f"mr_sil_{_did}", use_container_width=True):
                                    try:
                                        _sb_mr = get_sb_client()
                                        if _sb_mr:
                                            _sb_mr.table("cari_kartlar").update({"silindi":1}).eq("id", int(_did)).execute()
                                            _silinen_t += 1
                                    except: pass
                    if _silinen_t:
                        try: get_cari_listesi.clear()
                        except: pass
                        st.success(f"✅ {_silinen_t} kayıt silindi!")
                        st.rerun()

                with _mr_tab2:
                    _mukerrer_opts = [f"{k} ({len(v)} kayıt)" for k, v in _mukerrerler.items()]
                    _secilen_grup = st.selectbox("İncelenecek grup", ["-- Seçin --"] + _mukerrer_opts, key="dc_mukerrer_grup_sec")
                    if _secilen_grup != "-- Seçin --":
                        _grup_adi = list(_mukerrerler.keys())[_mukerrer_opts.index(_secilen_grup)]
                        _grup_idler = _mukerrerler[_grup_adi]
                        _grup_satirlar = df[df["id"].isin(_grup_idler)]
                        st.dataframe(_grup_satirlar[["id","firma","yetkili","gsm","il","durum"]].reset_index(drop=True), use_container_width=True)
                        _birles_hedef = st.selectbox("Ana kayıt (diğerleri silinecek)", _grup_idler, key="mr_birles_hedef")
                        if st.button("🔗 Birleştir — diğerlerini sil", type="primary", use_container_width=True, key="mr_birles_btn"):
                            try:
                                _sb_br = get_sb_client()
                                if _sb_br:
                                    for _bid in _grup_idler:
                                        if int(_bid) != int(_birles_hedef):
                                            _sb_br.table("cari_kartlar").update({"silindi":1}).eq("id", int(_bid)).execute()
                                    try: get_cari_listesi.clear()
                                    except: pass
                                    st.success("✅ Birleştirildi!")
                                    st.rerun()
                            except Exception as _bre:
                                st.error(f"❌ {_bre}")

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
        "İlk Temas":        "👋",
        "Teklif":           "📄",
        "Deneme":           "🧪",
        "Sözleşme":         "📝",
        "Kazanıldı":        "🏆",
        "Kaybedildi":       "❌",
        "Negatif Portföy":  "👎",
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
                                # Tüm filtreleri sıfırla
                                for _fk in ["_cl_fil_durum_multi","_cl_fil_asama_multi",
                                            "_cl_fil_il_multi","_cl_fil_ilce_multi",
                                            "_cl_fil_temsilci_multi","_cl_sec_kart"]:
                                    if _fk in st.session_state:
                                        del st.session_state[_fk]
                            elif d_adlar and _ad in d_adlar:
                                st.session_state["_cl_fil_durum_multi"] = [_ad]
                                st.session_state["_cl_fil_asama_multi"] = []
                            else:
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
        if str(_dn).upper() in ["NONE","NAN",""]: continue  # NONE gösterme
        _dc = len(df[df["durum"]==_dn]) if "durum" in df.columns else 0
        _d_veri.append((_dn, _dc))
    _a_veri = [(a, len(df[df["islem_asamasi"]==a]) if "islem_asamasi" in df.columns else 0) for a in tum_asama_opts if str(a).upper() not in ["NONE","NAN",""]] if tum_asama_opts else []
    _tum_veri = _d_veri + _a_veri
    _tum_emoji = {**_DURUM_EMOJI, **_ASAMA_EMOJI}
    _d_adlar = {x[0] for x in _d_veri}

    # Kanban butonu — buton satırında sağ tarafta
    _cl_view = st.session_state.get("_cl_view", "liste")
    _bsatir1, _bsatir2 = st.columns([9, 1])
    with _bsatir1:
        _rapor_satir(_tum_veri, "_tek_sirasi", "_tek_gizlisi", "tek", _tum_emoji, "", d_adlar=_d_adlar)
    with _bsatir2:
        if st.button("📋 Kanban", key="cl_view_kanban", type="primary" if _cl_view=="kanban" else "secondary", use_container_width=True):
            st.session_state["_cl_view"] = "kanban" if _cl_view=="liste" else "liste"
            st.rerun()

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
            _kb_not_data = _sb_kbn.table("cari_aciklamalar").select("cari_id").execute().data or [] if _sb_kbn else []
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
                    "gsm": str(_kr.get("gsm","") or ""),
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

        _kb_gizli = st.session_state.get("_kb_gizli_asama", [])
        # DB'den yükle
        if "_kb_gizli_init" not in st.session_state:
            try:
                _sb_kbi = get_sb_client()
                if _sb_kbi:
                    import json as _kbij
                    _r_kbi = _sb_kbi.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kb_gizli_asama").execute()
                    if _r_kbi.data:
                        st.session_state["_kb_gizli_asama"] = _kbij.loads(_r_kbi.data[0]["deger"])
            except: pass
            st.session_state["_kb_gizli_init"] = True
            _kb_gizli = st.session_state.get("_kb_gizli_asama", [])

        _kanban_filtreli = [k for k in _kanban_kolonlar if k["asama"] not in _kb_gizli]
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
    with st.expander("🔍 Filtreler & Arama", expanded=st.session_state.get("_cl_fil_acik", True)):
        st.session_state["_cl_fil_acik"] = True  # expander açık kalsın
        # ── TEK SATIR FİLTRE ───────────────────────────────────────────────────
        if st.session_state.get("kart_sec_reset"):
            st.session_state.pop("kart_sec_reset", None)
            st.session_state.pop("kart_sec", None)

        kart_opts_inline = ["-- Müşteri Seçin --"] + [
            f"[{int(r['id'])}] {r.get('firma','')}" for _, r in df.iterrows()
        ]
        if st.session_state.get("kart_sec_reset"):
            st.session_state.pop("kart_sec_reset", None)
            st.session_state.pop("kart_sec", None)

        _fc = st.columns([2, 1.5, 1.2, 1.2, 0.7, 1.6, 0.8, 0.9])

        secili_kart_inline = _fc[0].selectbox("m", kart_opts_inline, key="kart_sec_inline", label_visibility="collapsed")
        ara_txt = _fc[1].text_input("a", placeholder="🔍 Firma, yetkili, il...", key="ara_liste", label_visibility="collapsed")

        _asama_def = [x for x in st.session_state.get("_cl_fil_asama_multi",[]) if x in tum_asama_opts]
        _asama_sec = _fc[2].multiselect("a", tum_asama_opts, default=_asama_def, key="_cl_fil_asama_multi", placeholder="Aşama...", label_visibility="collapsed")

        _durum_opts_tumu = ["Tümü"] + [x for x in tum_durum_opts if str(x).upper() not in ["NONE","NAN",""]]
        _durum_def = [x for x in st.session_state.get("_cl_fil_durum_multi",[]) if x in _durum_opts_tumu]
        _durum_sec_raw = _fc[3].multiselect("d", _durum_opts_tumu, default=_durum_def, key="_cl_fil_durum_multi", placeholder="Durum...", label_visibility="collapsed")
        if "Tümü" in _durum_sec_raw:
            for _fk2 in ["_cl_fil_durum_multi","_cl_fil_asama_multi","_cl_fil_il_multi","_cl_fil_ilce_multi"]:
                if _fk2 in st.session_state: del st.session_state[_fk2]
            st.rerun()
        _durum_sec = _durum_sec_raw

        filtre_seg = _fc[4].selectbox("s", ["Tümü","👑 A+","⭐ A","🔵 B","⚪ C"], key="fil_seg", label_visibility="collapsed")

        _il_opts = ["🌍 Tümü / Hepsi"] + (sorted(df["il"].dropna().astype(str).unique().tolist()) if "il" in df.columns else [])
        _il_def  = [x for x in st.session_state.get("_cl_fil_il_multi",[]) if x in _il_opts]
        _il_sec_raw = _fc[5].multiselect("i", _il_opts, default=_il_def, key="_cl_fil_il_multi", placeholder="İl...", label_visibility="collapsed")
        if "🌍 Tümü / Hepsi" in _il_sec_raw:
            for _fk3 in ["_cl_fil_il_multi", "_cl_fil_ilce_multi", "_bl_ilce_filtre", "_bl_havuz_filtre"]:
                if _fk3 in st.session_state: del st.session_state[_fk3]
            st.session_state.pop("_bl_ilce_filtre_ad", None)
            st.rerun()
        _il_sec = _il_sec_raw

        _ilce_opts = sorted((df[df["il"].astype(str).isin(_il_sec)] if _il_sec else df)["ilce"].dropna().astype(str).unique().tolist()) if "ilce" in df.columns else []
        _ilce_opts = [x for x in _ilce_opts if x not in ["nan","None",""]]
        _ilce_sec  = _fc[6].multiselect("ilce", _ilce_opts, default=[x for x in st.session_state.get("_cl_fil_ilce_multi",[]) if x in _ilce_opts], key="_cl_fil_ilce_multi", placeholder="İlçe...", label_visibility="collapsed")

        _tem_opts = sorted(df["temsilci"].dropna().astype(str).unique().tolist()) if "temsilci" in df.columns else []
        _tem_def  = [x for x in st.session_state.get("_cl_fil_temsilci_multi",[]) if x in _tem_opts]
        _tem_sec  = _fc[7].multiselect("t", _tem_opts, default=_tem_def, key="_cl_fil_temsilci_multi", placeholder="Temsilci...", label_visibility="collapsed")

        siralama_kol = "Tarih↓"  # Sıralama kutusu kaldırıldı, varsayılan sıralama sabit kaldı

        # Eski sistemle uyumluluk
        kart_opts = ["-- Müşteri Seçin --"] + [
            f"[{int(r['id'])}] {r.get('firma','')} | {r.get('il','')} | {r.get('islem_asamasi','')}"
            for _, r in df.iterrows()
        ]
        if secili_kart_inline != "-- Müşteri Seçin --":
            _id_str = secili_kart_inline.split("]")[0].replace("[","").strip()
            _esles = [o for o in kart_opts if f"[{_id_str}]" in o]
            secili_kart = _esles[0] if _esles else "-- Müşteri Seçin --"
        else:
            secili_kart = "-- Müşteri Seçin --"

    # Filtre uygula
    df_f = df.copy()
    if ara_txt:
        df_f = df_f[df_f.apply(lambda r: ara_txt.lower() in str(r).lower(), axis=1)]
    if _asama_sec:
        df_f = df_f[df_f["islem_asamasi"].isin(_asama_sec)]
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
    if _tem_sec:
        df_f = df_f[df_f["temsilci"].astype(str).isin(_tem_sec)]

    # Bölgeler ekranından gelen gizli bölge filtresi (ilçe pill'leri taşmasın diye görünmez uygulanır)
    if st.session_state.get("_bl_ilce_filtre") and "ilce" in df_f.columns:
        _bl_hedef_ilceler = set(st.session_state["_bl_ilce_filtre"])
        df_f = df_f[df_f["ilce"].astype(str).isin(_bl_hedef_ilceler)]

    # Havuz (Bölgesiz) filtresi — hiçbir tanımlı bölgeye uymayan (il boş veya tanımsız) kayıtlar
    if st.session_state.get("_bl_havuz_filtre") and not df_f.empty:
        _hv_ilce_kol = "ilce" if "ilce" in df_f.columns else None
        df_f = df_f[df_f.apply(
            lambda r: il_ilce_bolge_bul(r.get("il",""), r.get(_hv_ilce_kol,"") if _hv_ilce_kol else "") is None,
            axis=1)]
        st.info(f"📦 Havuz (Bölgesiz) — hiçbir tanımlı bölgeye uymayan {len(df_f)} kayıt. "
                "Bu kayıtların İl/İlçe bilgisini aşağıdaki tablodan düzeltirseniz, otomatik doğru bölgeye geçerler.")
        if not df_f.empty:
            _hv_onizleme_kol = [c for c in ["firma","il","ilce","durum"] if c in df_f.columns]
            with st.expander(f"👁️ Bu {len(df_f)} kaydı hemen gör (kaydırmadan)", expanded=True):
                st.dataframe(df_f[_hv_onizleme_kol].reset_index(drop=True),
                             use_container_width=True, hide_index=True, height=300)

    # ── HİÇ FİLTRE SEÇİLİ DEĞİLKEN — sadece işlem görmemiş (Özel Müşteri/Portföy) göster ──
    # Bir müşteriye durum atanınca (Randevu, Teklif, Tekrar Ara vb.) artık burada görünmesin,
    # sadece kendi durum filtresinde görünsün. Karışıklığı önler.
    # NOT: Bir İl/Bölge seçiliyken bu gizleme devre dışı — o zaman amaç "oradaki HERKESİ göster".
    _bl_bolge_secili = bool(_il_sec) or bool(st.session_state.get("_bl_ilce_filtre")) or bool(st.session_state.get("_bl_havuz_filtre"))
    if not _durum_sec and not _asama_sec and not _bl_bolge_secili and "durum" in df_f.columns:
        _varsayilan_durumlar = ["Özel Müşteri", "Portföy"]
        df_f = df_f[df_f["durum"].isin(_varsayilan_durumlar)]

    # ── AŞAMA İÇİN AYNI MANTIK — sadece "İlk Temas" (varsayılan) aşamasındakiler kalsın ──
    # Aşaması değişen (Teklif, Sözleşme, Kazanıldı, Negatif Portföy vb.) müşteriler
    # ana listeden çıkıp sadece kendi aşama filtresinde görünür.
    if not _durum_sec and not _asama_sec and not _bl_bolge_secili and "islem_asamasi" in df_f.columns:
        _varsayilan_asama = "İlk Temas"
        df_f = df_f[
            (df_f["islem_asamasi"] == _varsayilan_asama) |
            (df_f["islem_asamasi"].isna()) |
            (df_f["islem_asamasi"].astype(str).str.strip() == "")
        ]

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

    _aktif_fil_sayisi = sum([bool(ara_txt),bool(_asama_sec),bool(_durum_sec),filtre_seg!="Tümü",bool(_il_sec),bool(_ilce_sec),bool(_tem_sec)])
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
            _gsm     = _temiz(kart_row.get("gsm","") or kart_row.get("telefon","") or kart_row.get("tel",""))
            _sabit   = _temiz(kart_row.get("sabit","") or kart_row.get("sabit_hat",""))
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
            _ax1,_ax2,_ax3,_ax4,_ax5,_ax6 = st.columns([1,1,1,1,1.2,1])
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
            if _ax2.button("📄 Teklif", key=f"kt_{kart_id}", use_container_width=True, type="primary"):
                st.session_state["aktif_tab"] = "teklif"
                st.session_state["hedef_mus"] = str(kart_row.get("firma",""))
                st.session_state["son_secili_id"] = None; st.rerun()
            if _ax3.button("📅 Randevu", key=f"kr_{kart_id}", use_container_width=True, type="primary"):
                st.session_state["aktif_tab"] = "randevu"
                st.session_state["rand_musteri_onsel"] = kart_id; st.rerun()
            _gsm_raw = str(kart_row.get("gsm","") or "").replace(" ","").replace("-","")
            if _gsm_raw.startswith("0"): _gsm_raw = "90" + _gsm_raw[1:]
            if _gsm_raw and _ax4.button("💬 WhatsApp", key=f"kwa_{kart_id}", use_container_width=True):
                st.markdown(f"<span style='opacity:0.4;cursor:not-allowed' title='Geçici devre dışı'>WhatsApp aç (devre dışı)</span>", unsafe_allow_html=True)
            if _ax5.button("💾 Kaydet", key=f"kkaydet_{kart_id}", use_container_width=True, type="primary"):
                try:
                    _g = {"firma":str(kart_row.get("firma","")), "yetkili":str(kart_row.get("yetkili","")), "gsm":str(kart_row.get("gsm","")), "sabit":str(kart_row.get("sabit","")), "email":str(kart_row.get("email","")), "il":str(kart_row.get("il","")), "ilce":str(kart_row.get("ilce","")), "durum":str(kart_row.get("durum","")), "temsilci":str(kart_row.get("temsilci","")), "islem_asamasi":str(kart_row.get("islem_asamasi",""))}
                    if sb_liste: sb_liste.table("cari_kartlar").update(_g).eq("id",kart_id).execute()
                    else: db_update("cari_kartlar",_g,"id",kart_id)
                    try: db_read.clear()
                    except: pass
                    st.success("✅ Kaydedildi!")
                except Exception as _ke: st.error(f"Hata: {_ke}")
            if _ax6.button("🗑️ Arşive", key=f"ka_{kart_id}", use_container_width=True):
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
    _tum_durumlar = ["Aktif","Hedef","Pasif"] + [d for d in _ekstra_d if d not in ["Aktif","Hedef","Pasif"]]

    # ── KOLON AYARLARI ──────────────────────────────────────────────────────────
    # ── KOLON GENİŞLİKLERİ — DB'den oku ─────────────────────────────────────
    _KOL_VARSAYILAN = {
        "firma":100,"yetkili":100,"gsm":110,"sabit":100,"email":100,
        "adres":120,"il":80,"ilce":70,"durum":90,"temsilci":90,
        "islem_asamasi":90,"aciklama":120,"📅 Son Randevu":180,"📨 Notlar":60,"id":50,
        "beklenen_ciro":80,"gerceklesen_ciro":80,"✅ Analiz":80,
        "asama1":100,"asama2":100,"asama3":100,"asama4":100,"sonuc":100
    }
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

    def _w(k):
        px = int(_KG.get(k, _KOL_VARSAYILAN.get(k, 100)))
        if px <= 80:    return "small"
        elif px <= 150: return "medium"
        else:           return "large"

    col_config = {
        "Seç":           st.column_config.CheckboxColumn("Seç", default=False),
        "id":            st.column_config.NumberColumn("ID", disabled=True, width=_w("id")),
        "tarih":         None, "olusturan": None, "silindi": None,
        "beklenen_ciro":    st.column_config.NumberColumn("Hedef ₺",  format="%,.0f ₺", width=_w("beklenen_ciro")),
        "gerceklesen_ciro": st.column_config.NumberColumn("Gerçek ₺", format="%,.0f ₺", width=_w("gerceklesen_ciro")),
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
        "islem_asamasi": st.column_config.SelectboxColumn("Aşama", options=tum_asama_opts, width=_w("islem_asamasi")),
        "aciklama":      st.column_config.TextColumn("Açıklama",  width=_w("aciklama")),
        "📅 Son Randevu": st.column_config.TextColumn("📅 Son Randevu", disabled=True, width=_w("📅 Son Randevu")),
        "📨 Notlar":     st.column_config.TextColumn("📨 Notlar", disabled=True, width=_w("📨 Notlar")),
        "✅ Analiz":     st.column_config.TextColumn("✅ Analiz", disabled=True, width=_w("✅ Analiz")),
        "asama1":        st.column_config.TextColumn("Aşama 1", width=_w("asama1")),
        "asama2":        st.column_config.TextColumn("Aşama 2", width=_w("asama2")),
        "asama3":        st.column_config.TextColumn("Aşama 3", width=_w("asama3")),
        "asama4":        st.column_config.TextColumn("Aşama 4", width=_w("asama4")),
        "sonuc":         st.column_config.TextColumn("Sonuç",   width=_w("sonuc")),
    }
    col_order = ["Seç","id","firma","yetkili","gsm","sabit","email","adres","il","ilce","durum","temsilci","islem_asamasi","beklenen_ciro","gerceklesen_ciro","✅ Analiz","📅 Son Randevu","aciklama","📨 Notlar","asama1","asama2","asama3","asama4","sonuc"]
    # Gizli kolonları çıkar
    _kol_gizli_map = {"firma":"firma","yetkili":"yetkili","gsm":"gsm","sabit":"sabit","email":"email",
                      "adres":"adres","il":"il","ilce":"ilce","durum":"durum","temsilci":"temsilci",
                      "islem_asamasi":"islem_asamasi","aciklama":"aciklama",
                      "📅 Son Randevu":"📅 Son Randevu","📨 Notlar":"📨 Notlar","id":"id",
                      "beklenen_ciro":"beklenen_ciro","gerceklesen_ciro":"gerceklesen_ciro","✅ Analiz":"✅ Analiz",
                      "asama1":"asama1","asama2":"asama2","asama3":"asama3","asama4":"asama4","sonuc":"sonuc"}
    col_order = [c for c in col_order if not any(c == _kol_gizli_map.get(g,g) for g in _GIZLI_KOLONLAR)]

    # ── DATA EDITOR ─────────────────────────────────────────────────────────────
    df_edit = df_f.copy()
    # aciklama kolonu kesinlikle olsun
    if "aciklama" not in df_edit.columns:
        df_edit["aciklama"] = ""
    df_edit["aciklama"] = df_edit["aciklama"].fillna("").astype(str).replace("nan","")

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
                    _son_rand[_mn_norm] = f"📅 {_dt} {_st}" + (f" · {_bl}" if _bl else "") + (f" [{_sc}]" if _sc else "")
            df_edit["📅 Son Randevu"] = df_edit["firma"].apply(lambda x: _son_rand.get(_norm_rand(x),""))
    except:
        df_edit["📅 Son Randevu"] = ""
    # Aşama 1-4 ve Sonuç kolonları — yoksa boş ekle
    for _ak in ["asama1","asama2","asama3","asama4","sonuc"]:
        if _ak not in df_edit.columns:
            df_edit[_ak] = ""

    # Ciro kolonlarını sayısal tut — başlığa tıklayınca doğru sıralar
    if "beklenen_ciro" in df_edit.columns:
        df_edit["beklenen_ciro"] = pd.to_numeric(df_edit["beklenen_ciro"], errors="coerce").fillna(0)
    if "gerceklesen_ciro" in df_edit.columns:
        df_edit["gerceklesen_ciro"] = pd.to_numeric(df_edit["gerceklesen_ciro"], errors="coerce").fillna(0)
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
                    df_edit["_not_sayi"] = df_edit["id"].apply(lambda x: _not_sayac.get(str(int(x)),0))
                else:
                    df_edit["📨 Notlar"] = ""
                    df_edit["_not_sayi"] = 0
                if "_not_sayi" in df_edit.columns:
                    df_edit = df_edit.sort_values("_not_sayi", ascending=False).drop(columns=["_not_sayi"]).reset_index(drop=True)
            else:
                df_edit["📨 Notlar"] = ""
        except Exception as _not_err:
            df_edit["📨 Notlar"] = ""
            st.warning(f"Not yükleme hatası: {_not_err}")
    else:
        df_edit["📨 Notlar"] = ""

    df_edit.insert(0, "Seç", False)

    import json as _json_ls

    # ── TÜMÜ GÖSTER — tablo sol, not paneli sağ ──────────────────────────────
    _kayitli_sira = st.session_state.get("_cl_kolon_sira", [])
    _aktif_col_order = _kayitli_sira if _kayitli_sira else col_order

    # Notlu satırları sarı yap — kaç tane notlu var
    _notlu_kac = len(df_edit[df_edit["📨 Notlar"] != ""]) if "📨 Notlar" in df_edit.columns else 0
    if _notlu_kac > 0:
        # data_editor'da ilk N satır notlu — CSS ile sarı yap
        st.markdown(f"""<style>
/* İlk {_notlu_kac} veri satırı — notlu müşteriler sarı */
div[data-testid="stDataEditor"] table tbody tr:nth-child(-n+{_notlu_kac}) td {{
    background-color: #fefce8 !important;
}}
div[data-testid="stDataEditor"] table tbody tr:nth-child(-n+{_notlu_kac}):hover td {{
    background-color: #fef9c3 !important;
}}
</style>""", unsafe_allow_html=True)

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
        _sb1, _sb2, _sb3 = st.columns([2, 1, 1])
        with _sb1:
            if st.button("💾 Değişiklikleri Kaydet", use_container_width=True, type="primary", key="liste_kaydet_ust"):
                st.session_state["_kaydet_flag"] = True
        with _sb3:
            if st.button("🔄 Kolon Sıfırla", use_container_width=True, key="cl_kolon_sifirla_ust"):
                st.session_state.pop("_cl_kolon_sira", None)
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    _tbl_col = st.container()
    _not_col = None

    with _tbl_col:
        edited_df = st.data_editor(
            df_edit,
            use_container_width=True,
            num_rows="fixed",
            column_config=col_config,
            column_order=_aktif_col_order,
            height=max(500, min(len(df_edit) * 35 + 80, 1800)),
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
        _kayit_kolonlar = ["id","firma","yetkili","gsm","sabit","email","il","ilce","durum","temsilci","islem_asamasi","aciklama","asama1","asama2","asama3","asama4","sonuc"]
        _mevcut = [c for c in _kayit_kolonlar if c in _kv.columns]
        st.session_state["_ls_tablo"] = _kv[_mevcut].to_json(orient="records", force_ascii=False)
    except:
        pass

    secili_df = edited_df[edited_df["Seç"] == True]
    secili_sayi = len(secili_df)
    secili_idler = secili_df["id"].tolist() if not secili_df.empty else []

    # ── NOT DİALOG — sadece seçili olunca açılır ────────────────────────────
    if secili_sayi == 1:
        _sel_id = int(secili_idler[0])
        _sel_rows = df_edit[df_edit["id"] == _sel_id]
        _sel_firma = str(_sel_rows.iloc[0].get("firma","")) if not _sel_rows.empty else ""
        not_dialog(_sel_id, _sel_firma)




    # ── BUTONLAR ──────────────────────────────────────────────────────────────
    btn_k, btn_a, btn_s, btn_kolon = st.columns(4)
    with btn_kolon:
        if st.button("🔄 Kolon Sırasını Sıfırla", use_container_width=True, key="cl_kolon_sifirla"):
            st.session_state.pop("_cl_kolon_sira", None)
            st.rerun()
    _do_kaydet = st.session_state.pop("_kaydet_flag", False)
    with btn_k:
        if st.button("💾 Değişiklikleri Kaydet", use_container_width=True, type="primary", key="liste_kaydet"):
            _do_kaydet = True
        if _do_kaydet:
            _editor_state = st.session_state.get("cari_editor", {})
            _edited_rows  = _editor_state.get("edited_rows", {})
            # edited_rows yoksa edited_df'ten al
            if not _edited_rows and "edited_df" in dir():
                try:
                    _orig = df_edit.reset_index(drop=True)
                    _ed   = edited_df.reset_index(drop=True)
                    _edited_rows = {}
                    for _ei in range(min(len(_orig), len(_ed))):
                        _rd = {}
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
                try:
                    _rows = _json_ls.loads(_tablo_json) if _tablo_json else []
                except:
                    _rows = []
                for idx_str, degisiklikler in _edited_rows.items():
                    try:
                        idx = int(idx_str)
                        if idx >= len(_rows): continue
                        rid = int(float(str(_rows[idx].get("id",0))))
                        if not rid: continue
                        guncelle = {}
                        for k, v in degisiklikler.items():
                            if k in ("Seç", "🗑️ Sil"): continue
                            if k in ("beklenen_ciro", "gerceklesen_ciro"):
                                try: guncelle[k] = float(v or 0)
                                except: guncelle[k] = 0
                            elif k in ("Hedef ₺",):
                                try: guncelle["beklenen_ciro"] = float(str(v or "").replace(".","").replace("₺","").replace(",",".").strip() or 0)
                                except: guncelle["beklenen_ciro"] = 0
                            elif k in ("Gerçek ₺",):
                                try: guncelle["gerceklesen_ciro"] = float(str(v or "").replace(".","").replace("₺","").replace(",",".").strip() or 0)
                                except: guncelle["gerceklesen_ciro"] = 0
                            else:
                                guncelle[k] = str(v) if v is not None else ""
                        if not guncelle: continue
                        if sb_liste:
                            sb_liste.table("cari_kartlar").update(guncelle).eq("id", rid).execute()
                        else:
                            conn_u = get_conn()
                            sets = ", ".join([f"{k}=?" for k in guncelle])
                            conn_u.execute(f"UPDATE cari_kartlar SET {sets} WHERE id=?",
                                list(guncelle.values()) + [rid])
                            conn_u.commit(); conn_u.close()
                        kayit_sayi += 1
                    except Exception as e_row:
                        hata_list.append(str(e_row))
                try: db_read.clear()
                except: pass
                # ── AÇIKLAMA HÜCRESI DOLUYSA ARŞİVLE ─────────────────────────
                _arsiv_sayi = 0
                try:
                    _tablo_json2 = st.session_state.get("_ls_tablo")
                    _rows2 = _json_ls.loads(_tablo_json2) if _tablo_json2 else []
                    for _row2 in _rows2:
                        _rid2 = _row2.get("id")
                        _ac2 = str(_row2.get("aciklama","") or "").strip()
                        if not _rid2 or not _ac2 or _ac2 == "nan": continue
                        _rid2 = int(float(str(_rid2)))
                        if sb_liste:
                            sb_liste.table("cari_aciklamalar").insert({
                                "cari_id": _rid2,
                                "cari_adi": str(_row2.get("firma","")),
                                "aciklama": _ac2,
                                "olusturan": st.session_state.get("kullanici",""),
                            }).execute()
                            sb_liste.table("cari_kartlar").update({"aciklama":""}).eq("id",_rid2).execute()
                        else:
                            _cx = get_conn()
                            _cx.execute("INSERT INTO cari_aciklamalar (cari_id,cari_adi,aciklama,olusturan) VALUES (?,?,?,?)",
                                (_rid2, str(_row2.get("firma","")), _ac2, st.session_state.get("kullanici","")))
                            _cx.execute("UPDATE cari_kartlar SET aciklama='' WHERE id=?", (_rid2,))
                            _cx.commit(); _cx.close()
                        _arsiv_sayi += 1
                except: pass
                st.session_state.pop("_ls_tablo", None)
                if kayit_sayi > 0:
                    st.toast(f"✅ {kayit_sayi} satır kaydedildi!" + (f" · {_arsiv_sayi} not arşivlendi!" if _arsiv_sayi > 0 else ""), icon="✅")
                elif _arsiv_sayi > 0:
                    st.toast(f"✅ {_arsiv_sayi} not arşivlendi!", icon="📨")
                else:
                    st.toast("Değişiklik kaydedildi.", icon="ℹ️")
                if hata_list:
                    st.error(f"Hata: {'; '.join(hata_list[:2])}")
                st.rerun()
    with btn_a:
        if secili_sayi > 0:
            if st.button(f"🗑️ Seçili {secili_sayi} → Arşive", use_container_width=True, key="liste_arsiv"):
                for rid in secili_idler:
                    try:
                        if sb_liste: sb_liste.table("cari_kartlar").update({"silindi":1}).eq("id",int(rid)).execute()
                        else: db_update("cari_kartlar",{"silindi":1},"id",int(rid))
                    except: pass
                try: db_read.clear()
                except: pass
                try: get_cari_listesi.clear()
                except: pass
                st.session_state.pop("cari_editor", None)
                st.success(f"✅ {secili_sayi} arşive gönderildi!"); st.rerun()
        else:
            st.caption("Seçmek için Seç kolonunu işaretleyin")

    with btn_s:
        if secili_sayi > 0:
            if st.button(f"❌ Seçili {secili_sayi} → Sil", use_container_width=True, key="liste_sil"):
                for rid in secili_idler:
                    try:
                        if sb_liste: sb_liste.table("cari_kartlar").delete().eq("id",int(rid)).execute()
                        else:
                            conn_s = get_conn()
                            conn_s.execute("DELETE FROM cari_kartlar WHERE id=?", (int(rid),))
                            conn_s.commit(); conn_s.close()
                    except: pass
                try: db_read.clear()
                except: pass
                st.success("✅ Silindi!"); st.rerun()



    st.divider()
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
        "teklif":"📄 Teklif","kisiler":"📞 Kişiler","rapor":"📊 Raporlar",
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
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5, kul_tab5_ekran, kul_tab_tanim, kul_tab_kolon, kul_tab_toplu = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi","🎨 Ekran Ayarları","⚙️ Tanımlar","📐 Kolon Ayarları","🔄 Toplu Değiştir"])
    elif _surum_yetkisi:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5, kul_tab5_ekran, kul_tab_tanim, kul_tab_kolon, kul_tab_toplu = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi","🎨 Ekran Ayarları","⚙️ Tanımlar","📐 Kolon Ayarları","🔄 Toplu Değiştir"])
    else:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5_ekran, kul_tab_tanim, kul_tab_kolon, kul_tab_toplu = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🎨 Ekran Ayarları","⚙️ Tanımlar","📐 Kolon Ayarları","🔄 Toplu Değiştir"])
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

        # ── ARKA PLAN ────────────────────────────────────────────────────────
        st.markdown("#### 🎨 Arka Plan Rengi")
        _temalar = {
            "beyaz":    ("#ffffff","Beyaz"),
            "acik_mavi":("#e8f4ff","Açık Mavi"),
            "gri":      ("#f1f5f9","Gri"),
            "yesil":    ("#f0fdf4","Açık Yeşil"),
            "krem":     ("#fff7ed","Krem"),
            "koyu":     ("#1e293b","Koyu"),
        }
        _t_cols = st.columns(6)
        for _ti, (_tk, (_tren, _tad)) in enumerate(_temalar.items()):
            _aktif_t = _mevcut.get("tema","beyaz") == _tk
            _t_cols[_ti].markdown(
                f"<div onclick='' style='cursor:pointer;text-align:center;'>"
                f"<div style='width:36px;height:36px;border-radius:6px;background:{_tren};"
                f"border:{"2px solid #3b82f6" if _aktif_t else "0.5px solid #cbd5e1"};"
                f"margin:0 auto 4px;'></div>"
                f"<span style='font-size:10px;'>{_tad}</span></div>",
                unsafe_allow_html=True
            )
            if _t_cols[_ti].button("●", key=f"tema_{_tk}", use_container_width=True, help=_tad):
                _mevcut["tema"] = _tk
                _ekran_kaydet(_mevcut)
                st.session_state["_ekran_tema"] = _tren
                st.rerun()

        st.divider()

        # ── TAKIM TEMALARI ───────────────────────────────────────────────────
        st.markdown("#### ⚽ Takım Teması")

        _TUM_TAKIMLAR = {
            "fenerbahce":    ("#ffef03","#004684","Fenerbahçe"),
            "galatasaray":   ("#e30613","#fcb514","Galatasaray"),
            "besiktas":      ("#000000","#ffffff","Beşiktaş"),
            "trabzonspor":   ("#ffffff","#722f37","Trabzonspor"),
            "giresunspor":   ("#2d8c2d","#ffffff","Giresunspor"),
            "samsunspor":    ("#cc0000","#000000","Samsunspor"),
            "rizespor":      ("#0055a5","#008000","Rizespor"),
            "kayserispor":   ("#cc9900","#cc0000","Kayserispor"),
            "sivasspor":     ("#cc0000","#ffffff","Sivasspor"),
            "antalyaspor":   ("#cc0000","#ffffff","Antalyaspor"),
            "konyaspor":     ("#006600","#ffffff","Konyaspor"),
            "bursaspor":     ("#006600","#ffffff","Bursaspor"),
            "alanyaspor":    ("#ff6600","#006600","Alanyaspor"),
            "kasimpasa":     ("#003399","#ffffff","Kasımpaşa"),
            "ankaragucu":    ("#ffef03","#003399","Ankaragücü"),
            "basaksehir":    ("#ff6600","#003399","Başakşehir"),
            "gaziantep":     ("#cc0000","#000000","Gaziantep FK"),
            "hatayspor":     ("#cc0000","#ffffff","Hatayspor"),
            "adanaspor":     ("#ff6600","#ffffff","Adanaspor"),
            "denizlispor":   ("#003399","#ffffff","Denizlispor"),
            "boluspor":      ("#cc0000","#ffffff","Boluspor"),
            "eyupspor":      ("#006600","#cc0000","Eyüpspor"),
            "goztepe":       ("#cc9900","#cc0000","Göztepe"),
            "kocaelispor":   ("#cc0000","#000000","Kocaelispor"),
            "sakaryaspor":   ("#cc0000","#000000","Sakaryaspor"),
            "orduspor":      ("#6600cc","#ffffff","Orduspor"),
            "genclerbirligi":("#cc0000","#000000","Gençlerbirliği"),
            "erzurumspor":   ("#003399","#cc0000","Erzurumspor"),
            "malatyaspor":   ("#cc9900","#000000","Malatyaspor"),
            "bandirmaspor":  ("#003399","#ffffff","Bandırmaspor"),
            "izmirspor":     ("#cc0000","#ffffff","İzmirspor"),
        }

        # 4 büyük — önizlemeli
        _4buyuk = ["fenerbahce","galatasaray","besiktas","trabzonspor","giresunspor"]
        _tk4 = st.columns(5)
        for _tki, _tkk in enumerate(_4buyuk):
            _r1, _r2, _tad = _TUM_TAKIMLAR[_tkk]
            _aktif_tk = _mevcut.get("takim","") == _tkk
            _border = "3px solid #3b82f6" if _aktif_tk else f"2px solid {_r1}"
            _tk4[_tki].markdown(
                f"<div style='border-radius:8px;overflow:hidden;border:{_border};margin-bottom:4px;'>"
                f"<div style='background:{_r2};padding:5px 7px;color:{_r1};font-size:11px;font-weight:700;'>🏢 MWCRMPRO</div>"
                f"<div style='background:white;padding:3px 5px;display:flex;flex-direction:column;gap:2px;'>"
                f"<div style='background:{_r2};color:{_r1};font-size:10px;padding:3px 5px;border-radius:3px;font-weight:600;'>📋 Cari Liste</div>"
                f"<div style='background:white;color:{_r2};font-size:10px;padding:3px 5px;border-radius:3px;border:1px solid {_r2};'>📅 Randevular</div>"
                f"</div>"
                f"<div style='background:{_r1};padding:3px;text-align:center;font-size:10px;font-weight:700;color:{_r2};'>{_tad}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            if _tk4[_tki].button("✓ Seçili" if _aktif_tk else "Seç", key=f"takim_{_tkk}",
                                  use_container_width=True, type="primary" if _aktif_tk else "secondary"):
                _mevcut["takim"] = _tkk
                _ekran_kaydet(_mevcut)
                st.session_state["_ekran_r1"] = _r1
                st.session_state["_ekran_r2"] = _r2
                st.rerun()



        if st.button("↺ Varsayılana Sıfırla", use_container_width=True, key="ekran_sifirla"):
            _ekran_kaydet({"bosluk":"normal","tema":"beyaz"})
            st.session_state.pop("_ekran_tema", None)
            st.session_state.pop("_ekran_tema2", None)
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
            "firma":100,"yetkili":100,"gsm":110,"sabit":100,"email":100,
            "adres":120,"il":80,"ilce":70,"durum":90,"temsilci":90,
            "islem_asamasi":90,"aciklama":120,"📅 Son Randevu":180,"📨 Notlar":60,"id":50,
            "asama1":100,"asama2":100,"asama3":100,"asama4":100,"sonuc":100,
            "beklenen_ciro":80,"gerceklesen_ciro":80,"✅ Analiz":80
        }
        _KG_UI_ETIKET = {
            "firma":"Firma","yetkili":"Yetkili","gsm":"GSM","sabit":"S.Tel",
            "email":"Email","adres":"Adres","il":"İl","ilce":"İlçe",
            "durum":"Durum","temsilci":"Temsilci","islem_asamasi":"Aşama",
            "aciklama":"Açıklama","📅 Son Randevu":"Randevu","📨 Notlar":"Notlar","id":"ID",
            "asama1":"Aşama 1","asama2":"Aşama 2","asama3":"Aşama 3","asama4":"Aşama 4","sonuc":"Sonuç",
            "beklenen_ciro":"Hedef ₺","gerceklesen_ciro":"Gerçek ₺","✅ Analiz":"Analiz"
        }
        try:
            _sb_kg_ui = get_sb_client()
            _kg_ui_mevcut = _KOL_VARS_UI.copy()
            _gizli_ui = []
            if _sb_kg_ui:
                import json as _kguj
                _r_kgu = _sb_kg_ui.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kol_genislik").execute()
                if _r_kgu.data:
                    _kg_ui_mevcut = _kguj.loads(_r_kgu.data[0]["deger"])
                _r_gizli = _sb_kg_ui.table("kullanici_tercih").select("deger").eq("kullanici","__liste_ui__").eq("anahtar","_kol_gizli").execute()
                if _r_gizli.data:
                    _gizli_ui = _kguj.loads(_r_gizli.data[0]["deger"])
        except:
            _kg_ui_mevcut = _KOL_VARS_UI.copy()
            _gizli_ui = []

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
                    # Anında kaydet
                    try:
                        _sb_kg_ui.table("kullanici_tercih").upsert({
                            "kullanici":"__liste_ui__","anahtar":"_kol_gizli",
                            "deger":_kguj.dumps(_gizli_ui, ensure_ascii=False)
                        }, on_conflict="kullanici,anahtar").execute()
                        st.session_state["_kol_gizli"] = _gizli_ui
                        st.session_state.pop("_kol_genislik_init", None)
                    except: pass
                    st.rerun()
                # Slider — gizliyse devre dışı
                _yeni_kg_ui[_k] = st.slider(
                    f"{'~~' if _gizli_mi else ''}{_etiket}",
                    min_value=20, max_value=400,
                    value=int(_kg_ui_mevcut.get(_k, _KOL_VARS_UI.get(_k,100))),
                    step=10, key=f"ui_kg_{_k}",
                    disabled=_gizli_mi
                )
                if _gizli_mi:
                    _yeni_gizli_ui.append(_k)

        if st.button("💾 Kaydet", type="primary", key="ui_kg_kaydet"):
            try:
                _sb_kg_s = get_sb_client()
                if _sb_kg_s:
                    import json as _kgsj2
                    _sb_kg_s.table("kullanici_tercih").upsert({
                        "kullanici":"__liste_ui__","anahtar":"_kol_genislik",
                        "deger":_kgsj2.dumps(_yeni_kg_ui, ensure_ascii=False)
                    }, on_conflict="kullanici,anahtar").execute()
                    _sb_kg_s.table("kullanici_tercih").upsert({
                        "kullanici":"__liste_ui__","anahtar":"_kol_gizli",
                        "deger":_kgsj2.dumps(_gizli_ui, ensure_ascii=False)
                    }, on_conflict="kullanici,anahtar").execute()
                st.session_state["_kol_genislik"] = _yeni_kg_ui
                st.session_state["_kol_gizli"] = _gizli_ui
                st.session_state.pop("_kol_genislik_init", None)
                st.toast("✅ Kolon ayarları kaydedildi!", icon="✅")
                st.rerun()
            except Exception as _kgue:
                st.error(f"Hata: {_kgue}")

        st.divider()
        st.markdown("### 📋 Kanban Sütun Görünürlüğü")
        st.caption("Kanban'da görünmesini istemediğiniz aşamaları kapatın")
        _kb_gizli_ui = list(st.session_state.get("_kb_gizli_asama", []))
        _all_asama = _tanimlar_yukle("asama")
        if _all_asama:
            _kb_cols = st.columns(4)
            for _kbi, _kba in enumerate(_all_asama):
                _kb_gorunsun = _kba not in _kb_gizli_ui
                _kb_tog = _kb_cols[_kbi % 4].toggle(
                    _kba, value=_kb_gorunsun, key=f"kb_giz_{_kbi}"
                )
                if not _kb_tog and _kba not in _kb_gizli_ui:
                    _kb_gizli_ui.append(_kba)
                elif _kb_tog and _kba in _kb_gizli_ui:
                    _kb_gizli_ui.remove(_kba)
            if st.button("💾 Kanban Ayarlarını Kaydet", key="kb_giz_kaydet", type="primary"):
                st.session_state["_kb_gizli_asama"] = _kb_gizli_ui
                try:
                    _sb_kbg = get_sb_client()
                    if _sb_kbg:
                        import json as _kbgj
                        _sb_kbg.table("kullanici_tercih").upsert({
                            "kullanici":"__liste_ui__","anahtar":"_kb_gizli_asama",
                            "deger":_kbgj.dumps(_kb_gizli_ui, ensure_ascii=False)
                        }, on_conflict="kullanici,anahtar").execute()
                    st.success("✅ Kaydedildi!")
                except Exception as _kbge:
                    st.error(f"Hata: {_kbge}")

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

elif aktif == "rapor":
    sayfa_log("rapor")
    import io as _rio2

    # Veri yükle
    df_rapor = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi=\'0\' OR silindi IS NULL)")
    df_rapor = _atama_filtresi_uygula(df_rapor)
    df_rand_r = db_read("randevular", extra_sql="ORDER BY randevu_tarihi DESC")
    df_tek_r  = db_read("teklifler", order_col="tarih")
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



elif aktif == "teklif":
    sayfa_log("teklif")
    import json, re, io

    _tt1, _tt2 = st.columns(2)
    if _tt1.button("📄 Spot Teklif", use_container_width=True, type="primary", key="tt_spot"):
        pass  # zaten burdayız
    if _tt2.button("⭐ Özel Teklif", use_container_width=True, key="tt_ozel"):
        st.session_state["aktif_tab"] = "ozel_teklif"
        # Seçili müşteriyi taşı
        if st.session_state.get("teklif_musteri","") != "-- Müşteri Seçin --":
            _tt_firma = st.session_state.get("hedef_mus","")
            if _tt_firma:
                st.session_state["teklif_musteri_onsel"] = _tt_firma
        st.rerun()

    st.markdown("## 📄 Spot Teklif")

    if st.session_state.pop("_tek_kopyalandi", False):
        st.info("📋 Teklif kopyalandı — fiyatlar yüklendi. Müşteriyi seçip kaydedin.")

    # ── TEK SATIR: FİLTRE + MÜŞTERİ + BİLGİLER ──────────────────────────────
    _df_cari_tek = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")
    _df_cari_tek = _atama_filtresi_uygula(_df_cari_tek)

    if st.session_state.get("tek_mus_reset"):
        st.session_state.pop("tek_mus_reset", None)
        st.session_state.pop("teklif_musteri", None)
        st.session_state.pop("hedef_mus", None)

    _df_m  = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")

    # ── Analiz sayfasından gelen otomatik müşteri seçimi ─────────────────────
    _onsel_firma = st.session_state.pop("teklif_musteri_onsel", None)
    if _onsel_firma:
        _onsel_rows = _df_m[_df_m["firma"] == _onsel_firma]
        if not _onsel_rows.empty:
            _onsel_row = _onsel_rows.iloc[0]
            _onsel_val = f"[{int(_onsel_row['id'])}] {_onsel_row['firma']} ({_onsel_row['durum']})"
            st.session_state["teklif_musteri"] = _onsel_val
            st.session_state.pop("son_secili_id", None)  # force update

    _tr = st.columns([1, 2.5, 0.3, 1.5, 1, 1, 1])
    _t_fil = _tr[0].selectbox("", ["Tümü"], key="teklif_fil", label_visibility="collapsed")
    _df_mf = _df_m if _t_fil == "Tümü" else _df_m[_df_m["durum"] == _t_fil]
    _m_opts = ["-- Müşteri Seçin --"] + [f"[{int(r['id'])}] {r['firma']} ({r['durum']})" for _,r in _df_mf.iterrows()]
    _secim  = _tr[1].selectbox("", _m_opts, key="teklif_musteri", label_visibility="collapsed")
    if _secim != "-- Müşteri Seçin --":
        if _tr[2].button("❌", key="tek_mus_temizle", use_container_width=True, help="Temizle"):
            st.session_state["tek_mus_reset"] = True
            st.rerun()

    secili_musteri = None
    gsm_kayitli = ""; email_kayitli = ""
    if _secim != "-- Müşteri Seçin --" and "[" in _secim:
        try:
            _mid = int(_secim.split("]")[0].replace("[","").strip())
            _mrow = _df_m[_df_m["id"]==_mid]
            if not _mrow.empty:
                secili_musteri = _mrow.iloc[0]
                gsm_kayitli   = str(secili_musteri.get("gsm","") or "")
                email_kayitli = str(secili_musteri.get("email","") or "")
        except Exception as _e: st.error(f"Seçim hatası: {_e}")

    _firma_def = str(secili_musteri["firma"]) if secili_musteri is not None else ""
    if st.session_state.get("son_secili_id") != _secim:
        st.session_state["hedef_mus"]     = _firma_def
        st.session_state["son_secili_id"] = _secim

    # GSM/Email — müşteri başına unique key ile value= her zaman çalışır
    _gsm_key   = f"gsm_manuel_{_secim}"
    _email_key = f"email_manuel_{_secim}"

    hedef_musteri = _tr[3].text_input("", key="hedef_mus", placeholder="Müşteri Adı", label_visibility="collapsed")
    vade          = _tr[4].text_input("", placeholder="Vade...", key="vade", label_visibility="collapsed")
    gsm_manuel    = _tr[5].text_input("", value=gsm_kayitli, placeholder="05xxxxxxxxx", key=_gsm_key, label_visibility="collapsed")
    email_manuel  = _tr[6].text_input("", value=email_kayitli, placeholder="Email", key=_email_key, label_visibility="collapsed")

    # WA numara işle
    gsm_temiz = re.sub(r"[\s\-\(\)+]","", gsm_manuel)
    if gsm_temiz.startswith("0") and len(gsm_temiz)==11: gsm_wa_final = "90"+gsm_temiz[1:]
    elif len(gsm_temiz)==10: gsm_wa_final = "90"+gsm_temiz
    elif len(gsm_temiz)==12 and gsm_temiz.startswith("90"): gsm_wa_final = gsm_temiz
    else: gsm_wa_final = gsm_temiz
    wa_final_gecerli = len(gsm_wa_final)==12 and gsm_wa_final.isdigit()

    st.divider()

    # ── SATIR SİSTEMİ ─────────────────────────────────────────────────────────
    URUN_TIPLERI = ["Koli","Sandık","Top","Çuval","Kasa","Palet","Diğer","Manuel"]
    IL_LISTESI = ["","İstanbul","Ankara","İzmir","Bursa","Antalya","Adana","Konya",
        "Gaziantep","Mersin","Kayseri","Eskişehir","Diyarbakır","Samsun","Trabzon",
        "Erzurum","Şanlıurfa","Manisa","Balıkesir","Tekirdağ","Kocaeli","Sakarya",
        "Denizli","Muğla","Hatay","Malatya","Kahramanmaraş","Van","Elazığ","Aydın",
        "Edirne","Çanakkale","Isparta","Bolu","Düzce","Yalova","Kırklareli",
        "Karaman","Burdur","Rize","Giresun","Artvin","Mardin","Batman","Zonguldak"]

    IL_KM_TR = {
        ("İstanbul","Ankara"):454,("Ankara","İstanbul"):454,
        ("İstanbul","İzmir"):479,("İzmir","İstanbul"):479,
        ("İstanbul","Bursa"):154,("Bursa","İstanbul"):154,
        ("İstanbul","Antalya"):725,("Antalya","İstanbul"):725,
        ("İstanbul","Konya"):664,("Konya","İstanbul"):664,
        ("İstanbul","Adana"):939,("Adana","İstanbul"):939,
        ("İstanbul","Gaziantep"):1130,("Gaziantep","İstanbul"):1130,
        ("İstanbul","Kayseri"):770,("Kayseri","İstanbul"):770,
        ("İstanbul","Mersin"):930,("Mersin","İstanbul"):930,
        ("İstanbul","Samsun"):730,("Samsun","İstanbul"):730,
        ("İstanbul","Trabzon"):1100,("Trabzon","İstanbul"):1100,
        ("İstanbul","Eskişehir"):330,("Eskişehir","İstanbul"):330,
        ("İstanbul","Tekirdağ"):135,("Tekirdağ","İstanbul"):135,
        ("İstanbul","Kocaeli"):100,("Kocaeli","İstanbul"):100,
        ("İstanbul","Sakarya"):160,("Sakarya","İstanbul"):160,
        ("İstanbul","Yalova"):80,("Yalova","İstanbul"):80,
        ("Ankara","İzmir"):590,("İzmir","Ankara"):590,
        ("Ankara","Antalya"):480,("Antalya","Ankara"):480,
        ("Ankara","Konya"):260,("Konya","Ankara"):260,
        ("Ankara","Adana"):490,("Adana","Ankara"):490,
        ("Ankara","Bursa"):390,("Bursa","Ankara"):390,
        ("Ankara","Kayseri"):320,("Kayseri","Ankara"):320,
        ("İzmir","Antalya"):490,("Antalya","İzmir"):490,
        ("İzmir","Bursa"):330,("Bursa","İzmir"):330,
        ("İzmir","Manisa"):40,("Manisa","İzmir"):40,
        ("Konya","Adana"):330,("Adana","Konya"):330,
        ("Adana","Gaziantep"):220,("Gaziantep","Adana"):220,
        ("Adana","Mersin"):70,("Mersin","Adana"):70,
    }

    def get_km(c, v):
        if not c or not v or c==v: return ""
        k = (c.strip(), v.strip())
        if k in IL_KM_TR: return str(IL_KM_TR[k])
        if (v.strip(),c.strip()) in IL_KM_TR: return str(IL_KM_TR[(v.strip(),c.strip())])
        return "?"

    _se1, _se2 = st.columns([1,5])
    if _se1.button("➕ Satır Ekle", use_container_width=True, type="primary", key="tek_satir_ekle"):
        st.session_state["teklif_satir_n"] = st.session_state.get("teklif_satir_n",1) + 1
        st.rerun()
    if st.session_state.get("teklif_satir_n",1) > 1:
        if _se2.button("➖ Son Satırı Sil", use_container_width=True, key="tek_satir_sil"):
            st.session_state["teklif_satir_n"] -= 1
            st.rerun()

    if "teklif_satir_n" not in st.session_state:
        st.session_state["teklif_satir_n"] = 1
    n = st.session_state["teklif_satir_n"]

    hesap_desi=[]; hesap_bf=[]; hesap_urun=[]
    for i in range(n):
        _en_v  = float(st.session_state.get(f"h_en_{i}",0) or 0)
        _boy_v = float(st.session_state.get(f"h_boy_{i}",0) or 0)
        _yuk_v = float(st.session_state.get(f"h_yuk_{i}",0) or 0)
        _bf_v  = float(st.session_state.get(f"h_bf_{i}",0) or 0)
        _tip_v = st.session_state.get(f"h_tip_{i}", URUN_TIPLERI[0])
        _desi_v = round((_en_v*_boy_v*_yuk_v)/3000,2) if (_en_v and _boy_v and _yuk_v) else 0.0
        hesap_desi.append(_desi_v); hesap_bf.append(_bf_v); hesap_urun.append(_tip_v)
        st.session_state[f"t_bit_{i}"] = _desi_v
        if f"t_tur_{i}" not in st.session_state: st.session_state[f"t_tur_{i}"] = _tip_v

    hesap_sonuclar=[]; teklif_sonuclar=[]; toplam_tutar=0.0
    left, right = st.columns(2)

    with left:
        st.markdown("#### 🔢 Hesaplama")
        _hh = st.columns([1.5,0.7,0.7,0.7,0.8,1.2])
        for _txt,_col in zip(["Ürün","En","Boy","Yük","Desi","Birim Fiyat"],_hh):
            _col.markdown(f"**{_txt}**")
        for i in range(n):
            _hc = st.columns([1.5,0.7,0.7,0.7,0.8,1.2])
            _urun_tip = _hc[0].selectbox("",URUN_TIPLERI,key=f"h_tip_{i}",label_visibility="collapsed")
            _en  = _hc[1].number_input("",min_value=0.0,step=1.0,key=f"h_en_{i}",label_visibility="collapsed",format="%.0f")
            _boy = _hc[2].number_input("",min_value=0.0,step=1.0,key=f"h_boy_{i}",label_visibility="collapsed",format="%.0f")
            _yuk = _hc[3].number_input("",min_value=0.0,step=1.0,key=f"h_yuk_{i}",label_visibility="collapsed",format="%.0f")
            _desi = round((_en*_boy*_yuk)/3000,2) if (_en and _boy and _yuk) else 0.0
            _hc[4].markdown(f"**{_desi}**")
            _bf = _hc[5].number_input("",min_value=0.0,step=0.5,key=f"h_bf_{i}",label_visibility="collapsed")
            _urun_adi = st.text_input(f"Ürün adı {i+1}:",key=f"h_adi_{i}",placeholder="Ürün adı") if _urun_tip=="Manuel" else _urun_tip
            hesap_sonuclar.append({"urun":_urun_adi,"en":_en,"boy":_boy,"yuk":_yuk,"desi":_desi,"birim_fiyat":_bf})
            hesap_desi[i]=_desi; hesap_bf[i]=_bf; hesap_urun[i]=_urun_tip

    with right:
        st.markdown("#### 📋 Teklifimiz")
        _th = st.columns([1.2,1.2,0.6,0.9,0.8,0.8,0.7,1.0])
        for _txt,_col in zip(["Çıkış","Varış","KM","Tür","Baş D","Bit D","KG","Tutar"],_th):
            _col.markdown(f"**{_txt}**")
        for i in range(n):
            _h_desi=hesap_desi[i]; _h_bf=hesap_bf[i]; _h_urun=hesap_urun[i]
            if _h_urun in URUN_TIPLERI: st.session_state[f"t_tur_{i}"] = _h_urun
            _tc = st.columns([1.2,1.2,0.6,0.9,0.8,0.8,0.7,1.0])
            _cil = _tc[0].selectbox("",IL_LISTESI,key=f"t_cil_{i}",label_visibility="collapsed")
            _vil = _tc[1].selectbox("",IL_LISTESI,key=f"t_vil_{i}",label_visibility="collapsed")
            _km  = get_km(_cil,_vil)
            _tc[2].markdown(f"**{_km or '—'}**")
            _tur = _tc[3].selectbox("",URUN_TIPLERI,key=f"t_tur_{i}",label_visibility="collapsed")
            _bas = _tc[4].number_input("",min_value=0.0,step=0.5,key=f"t_bas_{i}",label_visibility="collapsed")
            _tc[5].markdown(f"**{_h_desi}**")
            _kg  = _tc[6].number_input("",min_value=0.0,step=0.5,key=f"t_kg_{i}",label_visibility="collapsed")
            _buyuk = max(_kg, _h_desi)
            _tutar = round(_buyuk*_h_bf,2)
            _tc[7].markdown(f"**{fmt_para(_tutar)}**")
            toplam_tutar += _tutar
            teklif_sonuclar.append({"cikis_il":_cil,"varis_il":_vil,"km":_km,"tur":_tur,
                "bas_desi":_bas,"bit_desi":_h_desi,"kg":_kg,"buyuk":_buyuk,
                "birim_fiyat":_h_bf,"tutar":_tutar})

    # ── BUTONLAR ─────────────────────────────────────────────────────────────
    st.divider()
    _b1,_b2,_b3 = st.columns(3)

    if _b1.button("💾 Teklifi Kaydet", use_container_width=True, type="primary", key="tek_kaydet"):
        if not hedef_musteri:
            st.warning("Müşteri adı boş!")
        else:
            kullanici_log_kaydet("TEKLİF_KAYDET","teklif",f"Müşteri: {hedef_musteri}")
            db_insert("teklifler",{
                "musteri_id": int(secili_musteri["id"]) if secili_musteri is not None else 0,
                "musteri_adi": hedef_musteri,
                "satirlar": json.dumps({"hesap":hesap_sonuclar,"teklif":teklif_sonuclar},ensure_ascii=False),
                "toplam_tutar": toplam_tutar,
                "olusturan": st.session_state["kullanici"],
                "notlar": f"Vade:{vade}"
            })
            st.success("✅ Teklif kaydedildi!")

    teklif_ozet_str = "\n".join([
        f"- {t['cikis_il']} → {t['varis_il']} ({t['km']} km): {t['tur']} | {t['bas_desi']}–{t['bit_desi']} desi | {t['buyuk']} kg | {fmt_para(t['tutar'])}"
        for t in teklif_sonuclar if t["birim_fiyat"]>0])
    musteri_ili = str(secili_musteri["il"]) if secili_musteri is not None else ""

    def _sablon_wa(firma,ozet,vade_):
        return (f"Sayın {firma} yetkilisi,\n\nSize özel kargo teklifimiz:\n\n{ozet}\n"
                f"{f'Vade: {vade_}' if vade_ else ''}\n\n7/24 ulaşabilirsiniz.")
    def _sablon_email(firma,ozet,vade_):
        return (f"Konu: {firma} - Kargo Fiyat Teklifi\n\nSayın {firma} Yetkilisi,\n\n"
                f"Teklif Detayları:\n{ozet}\n{f'Vade: {vade_}' if vade_ else ''}\n\nSaygılarımızla")

    if _b2.button("📝 Şablon Mesaj", use_container_width=True, key="tek_sablon"):
        st.session_state["ai_whatsapp"] = _sablon_wa(hedef_musteri,teklif_ozet_str,vade)
        st.session_state["ai_email"]    = _sablon_email(hedef_musteri,teklif_ozet_str,vade)
        st.rerun()

    _api_key = ""
    try: _api_key = st.secrets.get("ANTHROPIC_API_KEY","")
    except: pass
    if _b3.button("🤖 AI Mesaj" if _api_key else "🤖 AI (API Key Gerekli)",
                  use_container_width=True, type="primary", disabled=not bool(_api_key), key="tek_ai"):
        with st.spinner("AI yazıyor..."):
            try:
                import requests as _req
                _prompt = (f"Sen kargo şirketi satış temsilcisisin.\nMüşteri: {hedef_musteri} ({musteri_ili})\n"
                           f"Teklif:\n{teklif_ozet_str}\nVade: {vade}\n\n"
                           f"Önce WhatsApp (3 paragraf, samimi, ikna edici).\n"
                           f"Sonra ---AYIRAC--- yaz.\nSonra email (Konu: ile başla).")
                _resp = _req.post("https://api.anthropic.com/v1/messages",
                    headers={"Content-Type":"application/json","x-api-key":_api_key,"anthropic-version":"2023-06-01"},
                    json={"model":"claude-sonnet-4-6","max_tokens":1200,
                          "messages":[{"role":"user","content":_prompt}]},timeout=30)
                _ai = _resp.json()["content"][0]["text"]
                _par = _ai.split("---AYIRAC---")
                st.session_state["ai_whatsapp"] = _par[0].strip()
                st.session_state["ai_email"]    = _par[1].strip() if len(_par)>1 else _ai
                st.rerun()
            except Exception as _ae:
                st.error(f"AI hatası: {_ae}")
                st.session_state["ai_whatsapp"] = _sablon_wa(hedef_musteri,teklif_ozet_str,vade)
                st.session_state["ai_email"]    = _sablon_email(hedef_musteri,teklif_ozet_str,vade)
                st.rerun()

    # ── MESAJ GÖRÜNTÜLE + GÖNDER ──────────────────────────────────────────────
    if st.session_state.get("ai_whatsapp"):
        _mc1,_mc2 = st.columns(2)
        with _mc1:
            st.markdown("**📱 WhatsApp**")
            _wa_txt = st.text_area("",value=st.session_state["ai_whatsapp"],height=180,key="wa_metin")
            if wa_final_gecerli:
                from urllib.parse import quote as _tq
                st.button("📱 WhatsApp'ta Aç", use_container_width=True, type="primary", disabled=True, help="Geçici olarak devre dışı", key="wa_btn_teklif1")
                if st.button("✅ WA Gönderildi Kaydet",use_container_width=True,key="wa_log"):
                    db_insert("islem_kaydi",{"musteri_id":int(secili_musteri["id"]) if secili_musteri else 0,
                        "musteri_adi":hedef_musteri,"islem_turu":"WhatsApp Teklif",
                        "icerik":_wa_txt,"gonderim_bilgisi":gsm_wa_final,"olusturan":st.session_state["kullanici"]})
                    st.success("✅ Kaydedildi!")
            else:
                st.warning("Geçerli WA numarası yok.")
        with _mc2:
            st.markdown("**✉️ Email**")
            _em_txt = st.text_area("",value=st.session_state["ai_email"],height=180,key="email_metin")
            if email_manuel.strip():
                _em_lines = _em_txt.split("\n")
                _konu = _em_lines[0].replace("Konu:","").strip() if _em_lines else "Teklif"
                _govde = "\n".join(_em_lines[1:]).strip()
                from urllib.parse import quote as _eq
                st.link_button("✉️ Email Aç",f"mailto:{email_manuel}?subject={_eq(_konu)}&body={_eq(_govde)}",use_container_width=True)
                if st.button("✅ Email Gönderildi Kaydet",use_container_width=True,key="email_log"):
                    db_insert("islem_kaydi",{"musteri_id":int(secili_musteri["id"]) if secili_musteri else 0,
                        "musteri_adi":hedef_musteri,"islem_turu":"Email Teklif",
                        "icerik":_em_txt,"gonderim_bilgisi":email_manuel,"olusturan":st.session_state["kullanici"]})
                    st.success("✅ Kaydedildi!")
            else:
                st.warning("Email yok.")

    # ── KAYITLI TEKLİFLER ────────────────────────────────────────────────────
    with st.expander("📋 Kayıtlı Teklifler"):
        try:
            df_tek = db_read("teklifler", order_col="tarih")
            if df_tek.empty:
                st.info("Henüz kayıtlı teklif yok.")
            else:
                _tek_opts = ["-- Teklif Seçin --"] + [
                    f"[{int(r['id'])}] {r.get('musteri_adi','')} | {fmt_tarih(r.get('tarih',''))}"
                    for _,r in df_tek.iterrows()]
                _sec_tek = st.selectbox("Teklif Seç:", _tek_opts, key="tek_sec")
                if _sec_tek != "-- Teklif Seçin --" and "[" in _sec_tek:
                    _tek_id = int(_sec_tek.split("]")[0].replace("[","").strip())
                    _tkmatch = df_tek[df_tek["id"]==_tek_id]
                    if _tkmatch.empty: raise Exception("Teklif bulunamadı")
                    _tek_row = _tkmatch.iloc[0]
                    st.caption(f"📅 {fmt_tarih(_tek_row.get('tarih',''))} · 👤 {_tek_row.get('olusturan','')} · 📝 {_tek_row.get('notlar','')}")
                    try:
                        _data = json.loads(_tek_row.get("satirlar","{}"))
                        if "teklif" in _data and _data["teklif"]:
                            _df_t = pd.DataFrame(_data["teklif"])
                            if "tutar" in _df_t.columns: _df_t["tutar"] = _df_t["tutar"].apply(lambda x: fmt_para(float(x or 0)))
                            if "birim_fiyat" in _df_t.columns: _df_t["birim_fiyat"] = _df_t["birim_fiyat"].apply(lambda x: fmt_para(float(x or 0)))
                            st.dataframe(_df_t, use_container_width=True, hide_index=True)
                    except: st.text(str(_tek_row.get("satirlar","")))
                    _ak1,_ak2,_ak3,_ak4 = st.columns(4)
                    with _ak1.expander("✏️ Not Güncelle"):
                        _yn = st.text_area("Not:",value=str(_tek_row.get("notlar","")),height=70,key=f"tek_not_{_tek_id}")
                        if st.button("💾 Kaydet",key=f"tek_not_btn_{_tek_id}",use_container_width=True):
                            db_update("teklifler",{"notlar":_yn},"id",_tek_id); st.success("✅"); st.rerun()
                    if _ak2.button("📋 Kopyala", key=f"tek_kopyala_{_tek_id}", use_container_width=True):
                        try:
                            import json as _tkj
                            _kop_data = _tkj.loads(_tek_row.get("satirlar","{}"))
                            # Spot teklif satırlarını session'a yükle, müşteri sıfırla
                            st.session_state["_tek_kop_data"] = _kop_data
                            st.session_state.pop("teklif_musteri", None)
                            st.session_state.pop("hedef_mus", None)
                            st.session_state.pop("son_secili_id", None)
                            st.session_state["_tek_kopyalandi"] = True
                            st.rerun()
                        except Exception as _ke: st.error(f"Kopyalama hatası: {_ke}")
                    if _ak3.button("🗃️ Arşivle",key=f"tek_arsiv_{_tek_id}",use_container_width=True):
                        db_update("teklifler",{"arsivlendi":1},"id",_tek_id); st.success("✅ Arşivlendi!"); st.rerun()
                    if _ak4.button("🗑️ Sil",key=f"tek_sil_{_tek_id}",use_container_width=True,type="primary"):
                        _sb_d=get_sb_client()
                        if _sb_d: _sb_d.table("teklifler").delete().eq("id",_tek_id).execute()
                        st.success("🗑️ Silindi!"); st.rerun()
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

    _oz_mus = None; _oz_gsm=""; _oz_eml=""
    if _oz_sec != "-- Müşteri Seçin --" and "[" in _oz_sec:
        try:
            _mid = int(_oz_sec.split("]")[0].replace("[","").strip())
            _mr  = _oz_dfm[_oz_dfm["id"]==_mid]
            if not _mr.empty:
                _oz_mus = _mr.iloc[0]
                _oz_gsm = str(_oz_mus.get("gsm","") or "")
                _oz_eml = str(_oz_mus.get("email","") or "")
        except: pass

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
    _ks1, _ks2 = st.columns(2)
    if _ks1.button("💾 Teklifi Kaydet", use_container_width=True, type="primary", key="oz2_kaydet"):
        if not _oz_hedef:
            st.warning("Müşteri adı boş!")
        else:
            _oz_veri = {
                "musteri_id": int(_oz_mus["id"]) if _oz_mus is not None else 0,
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
            st.session_state["oz2_wa_mesaj"] = _oz_mesaj_olustur(grp, _oz_hedef, _oz_vade)
            st.session_state.pop("oz2_grp",None)
            st.rerun()

    if _ks2.button("📱 WA Mesajı Oluştur", use_container_width=True, key="oz2_wa_olustur"):
        st.session_state["oz2_wa_mesaj"] = _oz_mesaj_olustur(grp, _oz_hedef, _oz_vade)
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
            _oz_df_tek = db_read("teklifler", order_col="tarih")
            if not _oz_df_tek.empty and "satirlar" in _oz_df_tek.columns:
                _oz_df_tek2 = _oz_df_tek[_oz_df_tek["satirlar"].str.contains('ozel', case=False, na=False)]
            else:
                _oz_df_tek2 = pd.DataFrame()

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

        if "firma" not in df_yukl.columns:
            st.error("❌ Zorunlu sütun eksik: firma")
        else:
            st.success(f"{len(df_yukl)} satır okundu.")

            if st.button("✅ Sisteme Aktar", type="primary", key="excel_aktar_btn_v2"):
                sb = get_sb_client()
                if not sb:
                    st.error("Supabase bağlantısı yok!")
                else:
                    kayitlar = []
                    for _, row in df_yukl.iterrows():
                        firma = str(row.get("firma","") or "").strip()
                        if not firma:
                            continue

                        def _temiz_str(v):
                            if v is None or (isinstance(v, float) and pd.isna(v)):
                                return ""
                            return str(v)

                        def _temiz_tel(v):
                            if v is None or (isinstance(v, float) and pd.isna(v)):
                                return ""
                            s = str(v).strip()
                            if s.endswith(".0"):
                                s = s[:-2]
                            return s

                        def _temiz_float(v):
                            try:
                                if v is None or (isinstance(v, float) and pd.isna(v)):
                                    return 0.0
                                return float(v)
                            except:
                                return 0.0

                        kayitlar.append({
                            "firma": firma,
                            "yetkili": _temiz_str(row.get("yetkili","")),
                            "gsm": _temiz_tel(row.get("gsm","")),
                            "sabit": _temiz_tel(row.get("sabit","")),
                            "email": _temiz_str(row.get("email","")),
                            "adres": _temiz_str(row.get("adres","")),
                            "ilce": _temiz_str(row.get("ilce","")),
                            "il": _temiz_str(row.get("il","")),
                            "durum": _temiz_str(row.get("durum","Hedef")) or "Hedef",
                            "temsilci": _temiz_str(row.get("temsilci","")),
                            "islem_asamasi": _temiz_str(row.get("islem_asamasi","İlk Temas")) or "İlk Temas",
                            "beklenen_ciro": _temiz_float(row.get("beklenen_ciro",0)),
                            "gerceklesen_ciro": _temiz_float(row.get("gerceklesen_ciro",0)),
                            "olusturan": st.session_state.get("kullanici",""),
                            "silindi": 0
                        })

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


elif aktif == "analiz":
    sayfa_log("analiz")
    import json as _aj
    from datetime import date, time as _time

    # ── CSS ───────────────────────────────────────────────────────────────────
    st.markdown("""<style>
.an-irow{background:white;border:1px solid #e2e8f0;border-radius:12px;margin-bottom:8px;overflow:visible;}
.an-irow.done{border-color:#bbf7d0;}
.an-hdr{display:flex;align-items:center;justify-content:space-between;padding:11px 16px;cursor:pointer;gap:8px;border-radius:12px;}
.an-hdr:hover{background:#f8fafc;}
.an-title{font-size:13px;font-weight:600;color:#374151;}
.an-status{font-size:11px;color:#94a3b8;flex-shrink:0;}
.an-status.ok{color:#16a34a;font-weight:500;}
.an-body{padding:14px 16px;border-top:1px solid #f1f5f9;}
.an-label{font-size:11px;color:#64748b;font-weight:500;margin:8px 0 4px;display:block;}
.an-label:first-child{margin-top:0;}
.an-pills{display:flex;flex-wrap:wrap;gap:4px;align-items:center;}
.an-pill{padding:4px 11px;border-radius:20px;font-size:12px;cursor:pointer;border:1px solid #e2e8f0;background:#f8fafc;color:#64748b;user-select:none;display:inline-flex;align-items:center;gap:3px;}
.an-pill:hover{border-color:#93c5fd;}
.an-pill.on{background:#eff6ff;border-color:#93c5fd;color:#1d4ed8;font-weight:500;}
.an-pill.custom{background:#fef9c3;border-color:#fde047;color:#92400e;}
.an-pill.custom.on{background:#fef08a;}
.an-plus{width:26px;height:26px;border-radius:50%;border:1.5px dashed #93c5fd;background:#f0f9ff;color:#3b82f6;font-size:16px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;vertical-align:middle;}
.an-plus:hover{background:#dbeafe;}
.an-addinp{display:none;align-items:center;gap:5px;margin-top:6px;}
.an-addinp.open{display:flex;}
.an-inp{border:1.5px solid #3b82f6;border-radius:20px;padding:4px 12px;font-size:12px;outline:none;width:170px;}
.an-ok{padding:4px 12px;background:#3b82f6;color:white;border:none;border-radius:20px;font-size:12px;cursor:pointer;}
.an-no{padding:4px 8px;background:white;color:#94a3b8;border:1px solid #e2e8f0;border-radius:20px;font-size:12px;cursor:pointer;}
.an-sopts{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px;}
.an-sopt{padding:5px 12px;border-radius:20px;font-size:12px;cursor:pointer;border:1px solid #e2e8f0;background:#f8fafc;color:#64748b;}
.an-sopt.on{background:#0f172a;color:white;border-color:#0f172a;}
.an-tbl{width:100%%;border-collapse:collapse;font-size:12px;margin-top:6px;}
.an-tbl th{background:#f8fafc;color:#64748b;padding:6px 8px;text-align:left;border-bottom:1px solid #e2e8f0;font-size:11px;}
.an-tbl td{padding:4px 5px;border-bottom:1px solid #f1f5f9;}
.an-tbl td input,.an-tbl td select{border:1px solid #e2e8f0;border-radius:6px;padding:4px 7px;font-size:12px;width:100%%;outline:none;}
.an-save-bar{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:12px 16px;display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap;}
</style>""", unsafe_allow_html=True)

    # ── DB FONKSIYONLARI ──────────────────────────────────────────────────────
    def _sb(): return get_sb_service() or get_sb_client()

    def _an_kaydet(firma, veri):
        try:
            sb = _sb()
            if sb:
                ex = sb.table("musteri_analiz").select("id").eq("firma", firma).execute()
                if ex.data:
                    sb.table("musteri_analiz").update(veri).eq("firma", firma).execute()
                else:
                    veri["firma"] = firma
                    sb.table("musteri_analiz").insert(veri).execute()
                return True, ""
        except Exception as e:
            return False, str(e)
        return False, "Bağlantı yok"

    def _an_getir(firma):
        try:
            sb = _sb()
            if sb:
                r = sb.table("musteri_analiz").select("*").eq("firma", firma).execute()
                return r.data[0] if r.data else None
        except: pass
        return None

    def _an_liste():
        try:
            sb = _sb()
            if sb:
                r = sb.table("musteri_analiz").select("id,firma,potansiyel,sonuc,tarih,yetkili,iletisim,sektor,kaynak,kargo,beklenti,engel,not_alan,sonraki_adim,takip_tar,bek_ciro,ger_ciro").order("tarih", desc=True).limit(500).execute()
                if r.data:
                    df = pd.DataFrame(r.data)
                    df = df[df["firma"].notna() & (df["firma"] != "")]
                    # Atama filtresi
                    _atanan = _get_atanmis_firmalar()
                    if _atanan is not None and "firmalar" in _atanan:
                        def _norm(s): return str(s or "").strip().upper()
                        df = df[df["firma"].apply(lambda x: _norm(x) in _atanan["firmalar"])]
                    return df
        except Exception as e:
            st.error(f"Liste hatası: {e}")
        return pd.DataFrame()

    def _an_sil(firma):
        try:
            sb = _sb()
            if sb:
                sb.table("musteri_analiz").delete().eq("firma", firma).execute()
                return True
        except: pass
        return False

    def _gs(key): return ", ".join(st.session_state.get(key, []))
    def _mv(k, d=""):  return (_mv_data or {}).get(k) or d
    def _mvl(k):
        v = _mv(k, "")
        return [x.strip() for x in v.split(",") if x.strip()] if v else []
    def _mvj(k):
        try: return _aj.loads(_mv(k, "[]") or "[]")
        except: return []

    # ── PILL HTML YARDIMCISI ──────────────────────────────────────────────────
    def _pill_html(group_key, defaults, custom_key=None, label=""):
        """HTML tabanlı pill widget — Streamlit components.html ile render edilir"""
        sel = st.session_state.get(group_key, defaults)
        customs = st.session_state.get(custom_key or f"{group_key}_custom", [])
        all_opts = defaults + [c for c in customs if c not in defaults]
        pills_html = ""
        for o in all_opts:
            is_on = o in sel
            is_custom = o not in defaults
            cls = "an-pill" + (" on" if is_on else "") + (" custom" if is_custom else "")
            x = f' <span style="font-size:10px;cursor:pointer;opacity:.6" onclick="rmCustom(this,\'{group_key}\',\'{o}\')">✕</span>' if is_custom else ""
            pills_html += f'<div class="{cls}" onclick="tp(this,\'{group_key}\',\'{o}\')">{o}{x}</div>\n'
        add_id = f"addinp_{group_key}"
        html = f"""
<div style="font-size:11px;color:#64748b;font-weight:500;margin-bottom:5px">{label}</div>
<div class="an-pills" id="pg_{group_key}">
{pills_html}
<button class="an-plus" onclick="oa('{add_id}')">+</button>
</div>
<div class="an-addinp" id="{add_id}">
  <input class="an-inp" id="inp_{group_key}" placeholder="ekle..." onkeydown="if(event.key==='Enter')addp('{group_key}','{add_id}')">
  <button class="an-ok" onclick="addp('{group_key}','{add_id}')">Ekle</button>
  <button class="an-no" onclick="ca('{add_id}')">İptal</button>
</div>"""
        return html

    # ── SEKME SİSTEMİ ─────────────────────────────────────────────────────────
    st.markdown("## 🔍 Müşteri Görüşme Analizi")
    st.markdown("""<style>
/* Analiz liste satır butonları - sola dayalı */
section.main div[data-testid="stHorizontalBlock"]:has(button[data-testid="baseButton-secondary"]) 
  div:first-child button {
    text-align: left !important;
    justify-content: flex-start !important;
    padding-left: 14px !important;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
section.main div[data-testid="stHorizontalBlock"]:has(button[data-testid="baseButton-secondary"])
  div:first-child button p {
    text-align: left !important;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}
</style>""", unsafe_allow_html=True)

    _an_tab1, _an_tab2 = st.tabs(["📋 Analiz Listesi", "✏️ Yeni / Düzenle"])

    # ── YARDIMCI FONKSİYONLAR (her yerde kullanılır) ─────────────────────────
    def _pill_html2(txt, renk="gray"):
        _renkler = {"blue":"#e6f1fb;color:#185fa5","green":"#eaf3de;color:#3b6d11",
                    "red":"#fcebeb;color:#a32d2d","amber":"#faeeda;color:#854f0b",
                    "gray":"#f1f5f9;color:#64748b"}
        _stl = _renkler.get(renk, _renkler["gray"])
        pills = [x.strip() for x in str(txt or "").split(",") if x.strip() and x.strip() not in ["nan","None"]]
        if not pills: return "<span style='color:#94a3b8;font-style:italic'>— henüz girilmedi</span>"
        _bg = _stl.split(";")[0]; _tc = _stl.split("color:")[1]
        return "".join([f"<span style='display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;background:{_bg};color:{_tc};margin:2px'>{p}</span>" for p in pills])

    def _val_html(v):
        s = str(v or "").strip()
        if s in ["","nan","None","—","--"]: return "<span style='color:#94a3b8;font-style:italic'>— henüz girilmedi</span>"
        return f"<span style='color:var(--color-text-primary,#1e293b)'>{s}</span>"

    def _analiz_pdf(_ar):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
            import io, json as _pj
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4,
                leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            story = []
            W = A4[0] - 4*cm
            def _s(name, **kw):
                base = {"fontName":"Helvetica","fontSize":10,"leading":14,"textColor":colors.HexColor("#1e293b")}
                base.update(kw); return ParagraphStyle(name, **base)
            def _p(txt, style): return Paragraph(str(txt or "").replace("&","&amp;").replace("<","&lt;"), style)
            def _clean(v):
                s = str(v or "").strip()
                return "—" if s in ["","nan","None","—","--"] else s
            def _pills(txt): return " · ".join([x.strip() for x in str(txt or "").split(",") if x.strip()]) or "—"
            ST_TITLE  = _s("t", fontSize=16, fontName="Helvetica-Bold", leading=20, textColor=colors.HexColor("#0f172a"))
            ST_SECTION= _s("sec", fontSize=10, fontName="Helvetica-Bold", textColor=colors.HexColor("#1d4ed8"), leading=14)
            ST_KEY    = _s("key", fontSize=9, textColor=colors.HexColor("#64748b"), leading=12)
            ST_VAL    = _s("val", fontSize=10, textColor=colors.HexColor("#1e293b"), leading=14)
            ST_SMALL  = _s("sm", fontSize=8, textColor=colors.HexColor("#94a3b8"), leading=11)
            _ar_d = _ar.to_dict() if hasattr(_ar, "to_dict") else _ar
            _firma_pdf = _clean(_ar_d.get("firma",""))
            _tarih_pdf = fmt_tarih(_ar_d.get("tarih",""))
            _pot_pdf   = _clean(_ar_d.get("potansiyel",""))
            _sonuc_pdf = _clean(_ar_d.get("sonuc",""))
            _bek_pdf   = f"{float(_ar_d.get('bek_ciro',0) or 0):,.0f} TL"
            _ger_pdf   = f"{float(_ar_d.get('ger_ciro',0) or 0):,.0f} TL"
            story.append(_p(_firma_pdf, ST_TITLE))
            story.append(Spacer(1,4))
            story.append(_p(f"Analiz: {_tarih_pdf}  |  Potansiyel: {_pot_pdf}  |  Sonuç: {_sonuc_pdf}", ST_SMALL))
            story.append(HRFlowable(width=W, thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=8, spaceBefore=4))
            _met = [["Beklenen Ciro","Gerçekleşen","Potansiyel","Sonuç"],[_bek_pdf,_ger_pdf,_pot_pdf,_sonuc_pdf]]
            _mt = Table(_met, colWidths=[W/4]*4)
            _mt.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f8fafc")),
                ("FONTNAME",(0,0),(-1,0),"Helvetica"),("FONTSIZE",(0,0),(-1,0),8),
                ("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#64748b")),
                ("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),("FONTSIZE",(0,1),(-1,1),11),
                ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("PADDING",(0,0),(-1,-1),7),("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e2e8f0")),
            ]))
            story.append(_mt); story.append(Spacer(1,8))
            def _bolum(baslik, satirlar):
                story.append(_p(baslik, ST_SECTION)); story.append(Spacer(1,3))
                tdata = [[_p(k,ST_KEY),_p(v,ST_VAL)] for k,v in satirlar]
                t = Table(tdata, colWidths=[3.5*cm, W-3.5*cm])
                t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,-1),0.3,colors.HexColor("#f1f5f9")),("LEFTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
                story.append(t); story.append(Spacer(1,6))
            _bolum("1 — ANALİZ AMACI",[("Görüşme amacı",_pills(_ar_d.get("amac",""))),("Müşteri durumu",_clean(_ar_d.get("mdurum","")))])
            _bolge_raw2 = {}
            try:
                _br2 = _ar_d.get("bolge","")
                if _br2: _bolge_raw2 = _pj.loads(_br2) if isinstance(_br2,str) else _br2
            except: pass
            _urun_pdf = _bolge_raw2.get("urun","") if isinstance(_bolge_raw2,dict) else ""
            _bolum("2 — KAYNAK & MÜŞTERİ",[("Firma",_clean(_ar_d.get("firma",""))),("Yetkili",_clean(_ar_d.get("yetkili",""))),("İletişim",_clean(_ar_d.get("iletisim",""))),("Sektör",_clean(_ar_d.get("sektor",""))),("Kaynak",_clean(_ar_d.get("kaynak",""))),("Gönderi türü",_urun_pdf or _pills(_ar_d.get("urun","")))])
            story.append(_p("3 — ÜRÜN, HACİM & CİRO", ST_SECTION)); story.append(Spacer(1,3))
            _bolge_rows2 = []
            if isinstance(_bolge_raw2, dict):
                _bolge_rows2 = _bolge_raw2.get("satirlar",[])
                if not _bolge_rows2:
                    for _g in _bolge_raw2.get("gruplar",[]): _bolge_rows2 += _g.get("satirlar",[])
            elif isinstance(_bolge_raw2, list): _bolge_rows2 = _bolge_raw2
            if _bolge_rows2:
                _tbl_data = [["Güzergah","Tip","Adet","Rakip Fiyatı (TL)","Bizim Fiyatımız (TL)","Fark","Periyot"]]
                for _br in _bolge_rows2:
                    _rak = str(_br.get("rakip_fiyat","") or _br.get("fiyat","") or "—")
                    _biz = str(_br.get("bizim_fiyat","") or _br.get("bizim","") or _br.get("ciro","") or "—")
                    _fark_pdf = "—"
                    try:
                        _rv2=float(_rak.replace(",",".").replace("₺","")); _bv2=float(_biz.replace(",",".").replace("₺",""))
                        if _rv2>0 and _bv2>0:
                            _fd=_rv2-_bv2; _fp=(_fd/_rv2)*100
                            _fark_pdf=f"{'▼' if _fd>0 else '▲'} {abs(_fd):,.0f} (%{abs(_fp):.0f})"
                    except: pass
                    _il_str = str(_br.get("il","") or ", ".join((_br.get("cikis",[]) or [])+["→"]+(_br.get("varis",[]) or [])) or "—")
                    _tbl_data.append([_il_str,str(_br.get("urun","") or ", ".join(_br.get("tur",[]) or []) or "—"),str(_br.get("adet","") or "—"),_rak,_biz,_fark_pdf,str(_br.get("siklik","") or "—")])
                _bt = Table(_tbl_data, colWidths=[W*0.28,W*0.07,W*0.07,W*0.14,W*0.14,W*0.16,W*0.14])
                _bt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f8fafc")),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#e2e8f0")),("PADDING",(0,0),(-1,-1),5),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
                story.append(_bt)
            else: story.append(_p("— veri girilmedi", ST_VAL))
            story.append(Spacer(1,8))
            _bolum("4 — BEKLENTİ & SONUÇ",[("Beklenti",_pills(_ar_d.get("beklenti",""))),("Engel",_pills(_ar_d.get("engel",""))),("Sonuç",_clean(_ar_d.get("sonuc",""))),("Sonraki adım",_pills(_ar_d.get("sonraki_adim",""))),("Takip",fmt_tarih(_ar_d.get("takip_tar","")))])
            _bolum("5 — NOT & ÖZET",[("Görüşme notu",_clean(_ar_d.get("not_alan",""))),("Olusturan",_clean(_ar_d.get("olusturan","")))])
            doc.build(story); buf.seek(0); return buf.read()
        except Exception as _pe:
            return None

    # ── TAB 1: LİSTE ──────────────────────────────────────────────────────────
    with _an_tab1:
        # Detay sayfası açıksa onu göster
        _detay_firma = st.session_state.get("an_detay_firma")
        if _detay_firma:
            _detay_ar = _an_getir(_detay_firma)
            if _detay_ar:
                _da = _detay_ar
                _bek_v = float(_da.get("bek_ciro",0) or 0)
                _ger_v = float(_da.get("ger_ciro",0) or 0)
                _doluluk = int(_ger_v/_bek_v*100) if _bek_v > 0 else 0

                # Rakip JSON parse
                try:
                    _rakip_list = __import__("json").loads(_da.get("rakip","[]") or "[]")
                    _rakip_list = _rakip_list if isinstance(_rakip_list, list) else []
                except: _rakip_list = []
                _ilk_rakip = _rakip_list[0] if _rakip_list else {}
                _rak_firma = str(_ilk_rakip.get("firma","") or "—")
                _rak_fiyat = str(_ilk_rakip.get("fiyat","") or "—")

                def _v(k): return str(_da.get(k,"") or "").strip() or "—"
                def _pills(k): return " · ".join([x.strip() for x in str(_da.get(k,"") or "").split(",") if x.strip()]) or "—"

                # Sinyal renkleri
                _pot = _v("potansiyel").lower()
                _sonuc = _v("sonuc").lower()
                _s_pot = "🟢" if "yüksek" in _pot else ("🟡" if "orta" in _pot else "🔴")
                _s_sonuc = "🟢" if _sonuc in ["teklif verildi","anlaşma yapıldı"] else ("🟡" if "takip" in _sonuc or "bekle" in _sonuc else "🔴")
                _s_ciro = "🟢" if _doluluk>=80 else ("🟡" if _doluluk>=40 else "🔴")

                # Telefon
                _tel2 = str(_da.get("iletisim","") or "").replace(" ","").replace("-","")
                if _tel2 and "@" not in _tel2 and _tel2.startswith("0"):
                    _tel2 = "90" + _tel2[1:]

                # ── HEADER ────────────────────────────────────────────────────
                if st.button("← Listeye Dön", key="an_detay_geri"):
                    st.session_state.pop("an_detay_firma", None); st.rerun()

                def _satir(lbl, val):
                    return f"""<div style="padding:7px 0;border-bottom:0.5px solid #f1f5f9;display:flex;justify-content:space-between;align-items:flex-start;gap:8px;font-size:12px;"><span style="color:#94a3b8;flex-shrink:0;">{lbl}</span><span style="font-weight:500;color:#0f172a;text-align:right;">{val}</span></div>"""
                def _kt(ikon, baslik):
                    return f"""<div style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #f1f5f9;">{ikon} {baslik}</div>"""

                st.markdown(f"""<div style="background:white;border-radius:12px;border:0.5px solid #e2e8f0;padding:16px 20px;margin-bottom:10px;">
<div style="font-size:20px;font-weight:800;color:#0f172a;margin-bottom:6px;">{_detay_firma}</div>
<div style="font-size:12px;color:#64748b;display:flex;gap:16px;flex-wrap:wrap;">
<span>📅 {fmt_tarih(_da.get("tarih",""))}</span><span>👤 {_v("olusturan")}</span><span>🏭 {_v("sektor")}</span>
</div></div>""", unsafe_allow_html=True)

                st.markdown(f"""<div style="background:white;border-radius:12px;border:0.5px solid #e2e8f0;overflow:hidden;margin-bottom:10px;">
<div style="display:grid;grid-template-columns:repeat(6,1fr);">
<div style="padding:14px 8px;text-align:center;border-right:1px solid #f1f5f9;">
<div style="font-size:28px;margin-bottom:6px;">{_s_sonuc}</div>
<div style="font-size:12px;font-weight:700;color:#0f172a;">{_v("sonuc").title()}</div>
<div style="font-size:10px;color:#94a3b8;margin-top:2px;">Sonuç</div></div>
<div style="padding:14px 8px;text-align:center;border-right:1px solid #f1f5f9;">
<div style="font-size:28px;margin-bottom:6px;">{_s_pot}</div>
<div style="font-size:12px;font-weight:700;color:#0f172a;">{_v("potansiyel").title()}</div>
<div style="font-size:10px;color:#94a3b8;margin-top:2px;">Potansiyel</div></div>
<div style="padding:14px 8px;text-align:center;border-right:1px solid #f1f5f9;">
<div style="font-size:28px;margin-bottom:6px;">{_s_ciro}</div>
<div style="font-size:12px;font-weight:700;color:#0f172a;">%{_doluluk}</div>
<div style="font-size:10px;color:#94a3b8;margin-top:2px;">Ciro Doluluk</div></div>
<div style="padding:14px 8px;text-align:center;border-right:1px solid #f1f5f9;">
<div style="font-size:28px;margin-bottom:6px;">{"🟠" if _rak_firma != "—" else "⚪"}</div>
<div style="font-size:12px;font-weight:700;color:#0f172a;word-break:break-word;">{_rak_firma}</div>
<div style="font-size:10px;color:#94a3b8;margin-top:2px;">Rakip</div></div>
<div style="padding:14px 8px;text-align:center;border-right:1px solid #f1f5f9;">
<div style="font-size:28px;margin-bottom:6px;">{"🔴" if _v("engel") != "—" else "🟢"}</div>
<div style="font-size:12px;font-weight:700;color:#0f172a;">{_v("engel")}</div>
<div style="font-size:10px;color:#94a3b8;margin-top:2px;">Engel</div></div>
<div style="padding:14px 8px;text-align:center;">
<div style="font-size:28px;margin-bottom:6px;">⏰</div>
<div style="font-size:12px;font-weight:700;color:#dc2626;">{fmt_tarih(_v("takip_tar"))}</div>
<div style="font-size:10px;color:#94a3b8;margin-top:2px;">Takip</div></div>
</div></div>""", unsafe_allow_html=True)

                _d1, _d2, _d3 = st.columns(3)
                with _d1:
                    st.markdown(f"""<div style="background:white;border-radius:10px;border:0.5px solid #e2e8f0;padding:14px;">
{_kt("👤","Müşteri Bilgisi")}
{_satir("Yetkili", _v("yetkili"))}
{_satir("İletişim", _v("iletisim"))}
{_satir("Sektör", _v("sektor"))}
{_satir("Kaynak", _pills("kaynak"))}
{_satir("Müşteri durumu", _pills("mdurum"))}
{_satir("Görüşme amacı", _pills("amac"))}
{_satir("Karar verici", _pills("karar"))}
{_satir("Karar süresi", _pills("sure"))}
</div>""", unsafe_allow_html=True)

                with _d2:
                    st.markdown(f"""<div style="background:white;border-radius:10px;border:0.5px solid #e2e8f0;padding:14px;">
{_kt("💰","Ciro & Rakip")}
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px;text-align:center;">
<div style="background:#f0fdf4;border-radius:7px;padding:10px 4px;"><div style="font-size:15px;font-weight:800;color:#16a34a;">{_bek_v:,.0f}₺</div><div style="font-size:9px;color:#64748b;">Hedef/ay</div></div>
<div style="background:#fffbeb;border-radius:7px;padding:10px 4px;"><div style="font-size:15px;font-weight:800;color:#d97706;">{_ger_v:,.0f}₺</div><div style="font-size:9px;color:#64748b;">Gerçek</div></div>
<div style="background:#eff6ff;border-radius:7px;padding:10px 4px;"><div style="font-size:15px;font-weight:800;color:#2563eb;">%{_doluluk}</div><div style="font-size:9px;color:#64748b;">Doluluk</div></div>
</div>
{_satir("Rakip firma", _rak_firma)}
{_satir("Rakip fiyatı", _rak_fiyat)}
{_satir("Beklenti", _pills("beklenti"))}
{_satir("Engel", _pills("engel"))}
{_satir("Fiyat beklentisi", _v("fiyat_bek"))}
{_satir("Özel istek", _v("ozel_istek"))}
</div>""", unsafe_allow_html=True)

                with _d3:
                    _not_txt = _v("not_alan")
                    st.markdown(f"""<div style="background:white;border-radius:10px;border:0.5px solid #e2e8f0;padding:14px;">
{_kt("✅","Sonuç & Notlar")}
{_satir("Sonuç", _v("sonuc").title())}
{_satir("Sonraki adım", _pills("sonraki_adim"))}
{_satir("Takip tarihi", fmt_tarih(_v("takip_tar")))}
{_satir("Potansiyel", _v("potansiyel").title())}
<div style="margin-top:10px;">
<div style="font-size:10px;color:#94a3b8;margin-bottom:6px;">📝 GÖRÜŞME NOTU</div>
<div style="background:#f8fafc;border-left:3px solid #2563eb;padding:10px 12px;border-radius:0 8px 8px 0;font-size:13px;color:#374151;line-height:1.8;min-height:60px;">
{"<span style='color:#94a3b8'>Henüz not girilmedi</span>" if _not_txt == "—" else _not_txt}
</div></div></div>""", unsafe_allow_html=True)

                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
                _kb1,_kb2,_kb3,_kb4,_kb5,_kb6 = st.columns(6)
                if _kb1.button("✏️ Düzenle", key="an_det_duz", use_container_width=True, type="primary"):
                    st.session_state["an_duzenle_firma"] = _detay_firma
                    st.session_state.pop("an_detay_firma", None)
                    for _kk in [f"an_init_{_detay_firma}","an_fiyat_rows","an_bolge_rows","an_rakip_rows","an_grp"]:
                        st.session_state.pop(_kk, None)
                    st.rerun()
                if _tel2 and "@" not in _tel2:
                    _kb2.markdown(f"<button style='width:100%;padding:8px;font-size:12px;background:#9ca3af;color:white;border:none;border-radius:7px;cursor:not-allowed;font-weight:500' disabled title='Geçici devre dışı'>💬 WA</button>", unsafe_allow_html=True)
                if _kb3.button("📄 Spot Teklif", key="an_det_spot", use_container_width=True):
                    st.session_state["aktif_tab"]="teklif"; st.session_state["teklif_musteri_onsel"]=_detay_firma; st.rerun()
                if _kb4.button("⭐ Özel Teklif", key="an_det_ozel", use_container_width=True):
                    st.session_state["aktif_tab"]="ozel_teklif"; st.session_state["teklif_musteri_onsel"]=_detay_firma; st.rerun()
                _pdf_bytes = _analiz_pdf(pd.Series(_da))
                if _pdf_bytes:
                    _kb5.download_button("⬇️ PDF", data=_pdf_bytes,
                        file_name=f"analiz_{_detay_firma[:20].replace(' ','_')}.pdf",
                        mime="application/pdf", key="an_det_pdf", use_container_width=True)
                if _kb6.button("🗑 Sil", key="an_det_sil", use_container_width=True):
                    if _an_sil(_detay_firma):
                        st.session_state.pop("an_detay_firma",None); st.rerun()
            else:
                st.error("Analiz bulunamadı")
                if st.button("← Geri"): st.session_state.pop("an_detay_firma",None); st.rerun()
            st.stop()

        _df_tum = _an_liste()
        _dff = pd.DataFrame()  # her zaman tanımlı olsun

        if _df_tum.empty:
            st.info("Henüz analiz kaydı yok. '✏️ Yeni / Düzenle' sekmesinden ekleyin.")
        else:
            # Filtreler
            _f1,_f2,_f3 = st.columns(3)
            _ff = _f1.text_input("Firma ara", key="an_ff", placeholder="firma adı...")
            _fs = _f2.selectbox("Sonuç", ["Tümü","takip edilecek","teklif verildi","anlaşma yapıldı","beklemede","ilgisiz"], key="an_fs")
            _fp = _f3.selectbox("Potansiyel", ["Tümü","çok yüksek","yüksek","orta","düşük","çok düşük"], key="an_fp")
            _dff = _df_tum.copy()
            if _ff: _dff = _dff[_dff["firma"].str.contains(_ff, case=False, na=False)]
            if _fs != "Tümü": _dff = _dff[_dff["sonuc"] == _fs]
            if _fp != "Tümü": _dff = _dff[_dff["potansiyel"] == _fp]

            # Metrik özet
            _sc1,_sc2,_sc3,_sc4,_sc5 = st.columns(5)
            _sc1.metric("Toplam", len(_df_tum))
            _sc2.metric("Yüksek Pot.", len(_df_tum[_df_tum["potansiyel"].isin(["yüksek","çok yüksek"])]))
            _sc3.metric("Takip Bekleyen", len(_df_tum[_df_tum["sonuc"]=="takip edilecek"]))
            _sc4.metric("Anlaşma", len(_df_tum[_df_tum["sonuc"]=="anlaşma yapıldı"]))
            try:
                _df_tum["bek_ciro"] = pd.to_numeric(_df_tum["bek_ciro"], errors="coerce").fillna(0)
                _sc5.metric("Beklenen Ciro", f"{_df_tum['bek_ciro'].sum():,.0f} ₺")
            except: pass

            st.caption(f"{len(_dff)} analiz")

            _pic_map = {"çok yüksek":"🟢","yüksek":"🟢","orta":"🟡","düşük":"🟠","çok düşük":"🔴"}
        # ── PDF ÜRETICI FONKSİYONU ───────────────────────────────────────────
        # ── KART GÖRÜNÜMÜ ─────────────────────────────────────────────────────
        _pot_renk = {"çok yüksek":"#22c55e","yüksek":"#22c55e","orta":"#f59e0b","düşük":"#ef4444","çok düşük":"#ef4444"}

        # ── ANALİZ LİSTESİ — MODEL 1: Renkli Şerit + Kompakt Satır ──────────────
        st.markdown("""<style>
.an-m1-card{display:flex;align-items:stretch;background:white;border:0.5px solid #e2e8f0;border-radius:10px;margin-bottom:6px;overflow:hidden;transition:box-shadow .15s;}
.an-m1-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06);}
.an-m1-strip{width:5px;flex-shrink:0;}
.an-m1-body{flex:1;padding:11px 14px;}
.an-m1-name{font-size:13px;font-weight:600;color:#0f172a;margin-bottom:4px;}
.an-m1-meta{font-size:11px;color:#64748b;display:flex;flex-wrap:wrap;gap:9px;align-items:center;}
.an-m1-pot{font-size:10px;padding:2px 8px;border-radius:20px;font-weight:500;white-space:nowrap;}
.an-m1-ciro{font-size:12px;font-weight:600;color:#16a34a;white-space:nowrap;}
div[data-testid="stHorizontalBlock"]:has(.an-m1-marker) { gap: 6px !important; align-items: stretch !important; margin-bottom: 6px !important; }
div[data-testid="stHorizontalBlock"]:has(.an-m1-marker) button {
    height: 100% !important; min-height: 56px !important;
    border-radius: 8px !important; font-size: 13px !important;
}
</style>""", unsafe_allow_html=True)

        _pot_renkler_m1 = {
            "çok yüksek": ("#dcfce7","#166534","🟢 Çok Yüksek"),
            "yüksek":     ("#dcfce7","#166534","🟢 Yüksek"),
            "orta":       ("#fef9c3","#854d0e","🟡 Orta"),
            "düşük":      ("#ffedd5","#9a3412","🟠 Düşük"),
            "çok düşük":  ("#fee2e2","#991b1b","🔴 Çok Düşük"),
        }
        _strip_renkler_m1 = {
            "çok yüksek": "#16a34a", "yüksek": "#16a34a", "orta": "#eab308",
            "düşük": "#f97316", "çok düşük": "#ef4444",
        }
        _sonuc_ikon_m1 = {"anlaşma yapıldı":"✅","teklif verildi":"📄","takip edilecek":"⏰","beklemede":"⏳","ilgisiz":"❌"}

        for _ai, (_, _ar) in enumerate(_dff.iterrows()):
            _ar_firma   = str(_ar.get("firma","") or "?")
            _ar_pot     = str(_ar.get("potansiyel","") or "")
            _ar_sonuc   = str(_ar.get("sonuc","") or "")
            _ar_tarih   = fmt_tarih(_ar.get("tarih",""))
            _ar_yetkili = str(_ar.get("yetkili","") or "")
            _ar_sektor  = str(_ar.get("sektor","") or "")
            _ar_bek     = float(_ar.get("bek_ciro",0) or 0)

            _strip = _strip_renkler_m1.get(_ar_pot, "#94a3b8")
            _pbg, _ptc, _plbl = _pot_renkler_m1.get(_ar_pot, ("#f1f5f9","#475569","⚪ —"))
            _sonuc_ic = _sonuc_ikon_m1.get(_ar_sonuc, "·")

            _meta_parts = [f"{_sonuc_ic} {_ar_sonuc.title() if _ar_sonuc else '—'}", f"📅 {_ar_tarih}"]
            if _ar_yetkili and _ar_yetkili not in ["nan","None","—",""]:
                _meta_parts.append(f"👤 {_ar_yetkili}")
            if _ar_sektor and _ar_sektor not in ["nan","None","—",""]:
                _meta_parts.append(f"🏭 {_ar_sektor}")
            _meta_html = " <span style='color:#cbd5e1'>·</span> ".join(_meta_parts)
            _ciro_html = f"<span class='an-m1-ciro'>💰 {_ar_bek:,.0f}₺</span>" if _ar_bek > 0 else ""

            _ac1, _ac2, _ac3 = st.columns([1, 8, 2])

            with _ac1:
                _sil_key = f"an_sil_onay_{_ai}"
                if st.session_state.get(_sil_key):
                    if st.button("✓", key=f"an_sil_evet_{_ai}", use_container_width=True, help="Evet, sil"):
                        if _an_sil(_ar_firma):
                            st.session_state.pop(_sil_key, None); st.rerun()
                    if st.button("✗", key=f"an_sil_hayir_{_ai}", use_container_width=True, help="İptal"):
                        st.session_state.pop(_sil_key, None); st.rerun()
                else:
                    if st.button("🗑", key=f"an_sil2_{_ai}", use_container_width=True, help="Sil"):
                        st.session_state[_sil_key] = True; st.rerun()

            with _ac2:
                _kart_html = (
                    f'<div class="an-m1-card">'
                    f'<div class="an-m1-strip" style="background:{_strip};"></div>'
                    f'<div class="an-m1-body">'
                    f'<div class="an-m1-name">{_ar_firma}</div>'
                    f'<div class="an-m1-meta">'
                    f'<span class="an-m1-pot" style="background:{_pbg};color:{_ptc};">{_plbl}</span>'
                    f'<span>{_meta_html}</span>'
                    f'{_ciro_html}'
                    f'</div></div></div>'
                )
                st.markdown(_kart_html, unsafe_allow_html=True)

            with _ac3:
                st.markdown('<div class="an-m1-marker" style="height:1px"></div>', unsafe_allow_html=True)
                if st.button("Detayı Aç →", key=f"an_ac_{_ai}", use_container_width=True):
                    st.session_state["an_detay_firma"] = _ar_firma
                    st.rerun()

        st.divider()

    # ── TAB 2: FORM ───────────────────────────────────────────────────────────
    with _an_tab2:
        st.markdown("### ✏️ Analiz Formu")
        _df_cari = get_cari_listesi()
        _col1, _col2 = st.columns([3,1])
        _opts = ["-- Seçin --"] + [f"[{int(r['id'])}] {r['firma']}" for _,r in _df_cari.iterrows()]
        _sec = _col1.selectbox("Müşteri seç", _opts, key="an_cari_sec")
        _yaz = _col2.text_input("veya firma adı", key="an_firma_yaz", placeholder="Manuel...",
        value=st.session_state.pop("an_duzenle_firma",""))

        _firma = ""
        _cari_row = None
        if _sec != "-- Seçin --" and "[" in _sec:
            _cid = int(_sec.split("]")[0].replace("[","").strip())
            _cr = _df_cari[_df_cari["id"]==_cid]
            if not _cr.empty:
                _cari_row = _cr.iloc[0]
                _firma = str(_cari_row.get("firma",""))
        elif _yaz.strip():
            _firma = _yaz.strip()

        if not _firma:
            st.warning("⚠️ Müşteri seçin veya firma adı yazın.")
        else:
            _mv_data = _an_getir(_firma)
            _duzenle = _mv_data is not None
            _ik = f"an_init_{_firma}"

            # Başlık
            _hc1, _hc2 = st.columns([4,1])
            with _hc1:
                if _duzenle:
                    st.success(f"✅ **{_firma}** — kayıtlı analiz düzenleniyor")
                else:
                    st.info(f"🆕 **{_firma}** — yeni analiz")
            with _hc2:
                if _duzenle:
                    if st.button("🗑 Sil", use_container_width=True, key="an_sil_hdr"):
                        if _an_sil(_firma):
                            st.success("Silindi!"); st.rerun()

            def _mv(k, d=""):  return (_mv_data or {}).get(k) or d
            def _mvl(k):
                v = _mv(k, "")
                return [x.strip() for x in v.split(",") if x.strip()] if v else []
            def _mvj(k):
                try: return _aj.loads(_mv(k, "[]") or "[]")
                except: return []
            def _gs2(k): return ", ".join(st.session_state.get(k, []))

            # ── 4 SÜTUN MODEL ─────────────────────────────────────────────────
            _c1, _c2, _c3, _c4 = st.columns(4)

            # ── SÜTUN 1: KİM? ─────────────────────────────────────────────────
            with _c1:
                st.markdown("#### 👤 Kim?")
                # Cari listeden otomatik doldur — analiz kaydı yoksa cari bilgileri kullan
                _oto_yetkili  = str(_cari_row.get("yetkili","") or "") if _cari_row is not None else ""
                _oto_iletisim = str(_cari_row.get("gsm","") or _cari_row.get("email","") or "") if _cari_row is not None else ""
                _oto_sektor   = str(_cari_row.get("segment","") or "") if _cari_row is not None else ""
                _an_yetkili   = st.text_input("Yetkili", value=_mv("yetkili", _oto_yetkili), key="an_yetkili", placeholder="Adı soyadı...")
                _an_iletisim  = st.text_input("İletişim", value=_mv("iletisim", _oto_iletisim), key="an_iletisim", placeholder="Telefon / email...")
                _an_sektor    = st.text_input("Sektör", value=_mv("sektor", _oto_sektor), key="an_sektor", placeholder="Sektör...")
                st.markdown("**Müşteri Durumu**")
                _mdurum_opts = ["yeni","mevcut","eski","rakip firmanın müşterisi"]
                _mdurum_def  = _mvl("mdurum") if _duzenle else []
                _mdurum_sec  = []
                for _md in _mdurum_opts:
                    _cur = _md in _mdurum_def
                    if st.checkbox(_md, value=_cur, key=f"an_md_{_md}"):
                        _mdurum_sec.append(_md)
                st.session_state["an_t_mdurum"] = _mdurum_sec

                st.markdown("**Potansiyel**")
                _pot_opts = ["çok düşük","düşük","orta","yüksek","çok yüksek"]
                _pot_def  = (_mvl("potansiyel") or [""])[0] if _duzenle else ""
                _pot_idx  = _pot_opts.index(_pot_def) if _pot_def in _pot_opts else 2
                _pot_sel  = st.radio("", _pot_opts, index=_pot_idx, key="an_t_pot_r", horizontal=False, label_visibility="collapsed")
                st.session_state["an_t_pot"] = [_pot_sel]

            # ── SÜTUN 2: NE KONUŞTUK? ─────────────────────────────────────────
            with _c2:
                st.markdown("#### 🎯 Ne Konuştuk?")
                st.markdown("**Görüşme Amacı**")
                _amac_opts = ["yeni müşteri kazanım","zam görüşmesi","nezaket ziyareti",
                              "erken potansiyel","kayıp müşteri geri kazanım",
                              "mevcut müşteri analizi","rakip takibi","pazar araştırması"]
                _amac_def  = _mvl("amac") if _duzenle else []
                _amac_sec  = []
                for _ao in _amac_opts:
                    if st.checkbox(_ao, value=_ao in _amac_def, key=f"an_amac_{_ao}"):
                        _amac_sec.append(_ao)
                st.session_state["an_t_amac"] = _amac_sec

                st.markdown("**Müşteri Beklentisi**")
                _bek_opts = ["fiyat indirimi","daha iyi hizmet","hızlı teslimat",
                             "özel çözüm","daha iyi iletişim","teknik destek"]
                _bek_def  = _mvl("beklenti") if _duzenle else []
                _bek_sec  = []
                for _bo in _bek_opts:
                    if st.checkbox(_bo, value=_bo in _bek_def, key=f"an_bek_{_bo}"):
                        _bek_sec.append(_bo)
                st.session_state["an_t_beklenti"] = _bek_sec

                _an_bek = st.text_input("Hedef Ciro (₺/ay)", value=str(_mv("bek_ciro","") or ""), key="an_bek", placeholder="₺/ay")
                _an_ger = st.text_input("Gerçekleşen (₺/ay)", value=str(_mv("ger_ciro","") or ""), key="an_ger", placeholder="₺/ay")

            # ── SÜTUN 3: RAKİP ────────────────────────────────────────────────
            with _c3:
                st.markdown("#### ⚔️ Rakip")
                st.markdown("**Engeller**")
                _engel_opts = ["fiyat yüksek","marka bilinirliği","uzun sözleşme",
                               "mevcut tedarikçi memnun","teknik uyumsuzluk"]
                _engel_def  = _mvl("engel") if _duzenle else []
                _engel_sec  = []
                for _eo in _engel_opts:
                    if st.checkbox(_eo, value=_eo in _engel_def, key=f"an_eng_{_eo}"):
                        _engel_sec.append(_eo)
                st.session_state["an_t_engel"] = _engel_sec

                st.markdown("**Rakip Firmaları**")
                if "an_rakip_rows" not in st.session_state:
                    _rr = _mvj("rakip")
                    st.session_state["an_rakip_rows"] = _rr if isinstance(_rr, list) and _rr else [{"firma":"","fiyat":""}]
                _rak_rows = st.session_state["an_rakip_rows"]
                _rak_new = []
                for _ri, _rr in enumerate(_rak_rows):
                    _ra1, _ra2 = st.columns(2)
                    _rn = _ra1.text_input("Rakip", value=_rr.get("firma",""), key=f"an_rak_f_{_ri}", label_visibility="collapsed", placeholder="Rakip adı")
                    _rp = _ra2.text_input("Fiyat", value=_rr.get("fiyat",""), key=f"an_rak_p_{_ri}", label_visibility="collapsed", placeholder="₺/kg")
                    _rak_new.append({"firma":_rn,"fiyat":_rp})
                st.session_state["an_rakip_rows"] = _rak_new
                if st.button("+ Rakip ekle", key="an_rak_ekle"):
                    st.session_state["an_rakip_rows"].append({"firma":"","fiyat":""}); st.rerun()

                _an_fbek  = st.text_input("Fiyat Beklentisi", value=_mv("fiyat_bek",""), key="an_fbek", placeholder="Müşterinin fiyat beklentisi...")
                _an_ozel  = st.text_input("Özel İstek", value=_mv("ozel_istek",""), key="an_ozel", placeholder="Özel istek / talep...")
                _an_karar_opts = ["yetkili kendisi","üst yönetim","komite","bilinmiyor"]
                _an_karar_def = (_mvl("karar") or ["bilinmiyor"])[0]
                _an_karar_idx = _an_karar_opts.index(_an_karar_def) if _an_karar_def in _an_karar_opts else 3
                _an_karar = st.radio("Karar Verici", _an_karar_opts, index=_an_karar_idx, key="an_karar_r", horizontal=False)
                st.session_state["an_t_karar"] = [_an_karar]

            # ── SÜTUN 4: SONUÇ ────────────────────────────────────────────────
            with _c4:
                st.markdown("#### ✅ Sonuç")
                _sonuc_opts = ["teklif verildi","randevu alındı","takip edilecek",
                               "beklemede","ilgisiz","anlaşma yapıldı"]
                _sonuc_def  = (_mvl("sonuc") or ["takip edilecek"])[0]
                _sonuc_idx  = _sonuc_opts.index(_sonuc_def) if _sonuc_def in _sonuc_opts else 2
                _sonuc_sel  = st.radio("Sonuç", _sonuc_opts, index=_sonuc_idx, key="an_t_sonuc_r", horizontal=False)
                st.session_state["an_t_sonuc"] = [_sonuc_sel]

                _sonraki_opts = ["fiyat teklifi gönder","tekrar ara","randevu al",
                                 "numune gönder","sözleşme hazırla","demo yap"]
                _sonraki_def  = _mvl("sonraki_adim") if _duzenle else []
                _sonraki_sec  = []
                st.markdown("**Sonraki Adım**")
                for _so in _sonraki_opts:
                    if st.checkbox(_so, value=_so in _sonraki_def, key=f"an_son_{_so}"):
                        _sonraki_sec.append(_so)
                st.session_state["an_t_sonraki"] = _sonraki_sec

                _an_takip   = st.date_input("Takip Tarihi", key="an_takip")
                _an_not     = st.text_area("Notlar", value=_mv("not_alan",""), key="an_not",
                                           placeholder="Görüşme notları...", height=100)
                _an_sonraki_txt = st.text_input("Sonraki adım notu", value=_mv("sonraki_adim",""),
                                                key="an_sonraki", placeholder="isteğe bağlı...")

                # Kaydet
                if st.button(f"💾 {'Güncelle' if _duzenle else 'Kaydet'}", type="primary",
                             use_container_width=True, key="an_kaydet_main"):
                    st.session_state["an_kaydet_trigger"] = True; st.rerun()

                st.markdown("---")
                _ab1, _ab2 = st.columns(2)
                if _ab1.button("📄 Spot Teklif", use_container_width=True, key="an_spot"):
                    st.session_state["aktif_tab"] = "teklif"
                    st.session_state["teklif_musteri_onsel"] = _firma; st.rerun()
                if _ab2.button("⭐ Özel Teklif", use_container_width=True, key="an_ozel_t"):
                    st.session_state["aktif_tab"] = "ozel_teklif"
                    st.session_state["teklif_musteri_onsel"] = _firma; st.rerun()

            # ── KAYDET ────────────────────────────────────────────────────────
            _pot_val   = (st.session_state.get("an_t_pot") or ["orta"])[0]
            _sonuc_val = (st.session_state.get("an_t_sonuc") or ["takip edilecek"])[0]
            try: _bv = float((_an_bek or "0").replace(".","").replace(",","."))
            except: _bv = 0
            try: _gv = float((_an_ger or "0").replace(".","").replace(",","."))
            except: _gv = 0

            if st.session_state.get("an_kaydet_trigger"):
                st.session_state.pop("an_kaydet_trigger", None)
                _veri = {
                    "yetkili":_an_yetkili,"iletisim":_an_iletisim,"sektor":_an_sektor,
                    "amac":_gs2("an_t_amac"),"mdurum":_gs2("an_t_mdurum"),
                    "bek_ciro":_bv,"ger_ciro":_gv,
                    "beklenti":_gs2("an_t_beklenti"),"engel":_gs2("an_t_engel"),
                    "sonuc":_sonuc_val,
                    "sonraki_adim":_gs2("an_t_sonraki") or _an_sonraki_txt,
                    "potansiyel":_pot_val,"not_alan":_an_not,
                    "takip_tar":str(_an_takip),
                    "fiyat_bek":_an_fbek,"ozel_istek":_an_ozel,
                    "karar":_gs2("an_t_karar"),
                    "rakip":_aj.dumps(st.session_state.get("an_rakip_rows",[]),ensure_ascii=False),
                    "olusturan":st.session_state.get("kullanici",""),
                }
                _GECERLI = {"yetkili","iletisim","sektor","amac","mdurum","bek_ciro","ger_ciro",
                    "beklenti","engel","sonuc","sonraki_adim","sik","potansiyel","not_alan",
                    "takip_tar","fiyat_bek","ozel_istek","karar","sure","bolge","rakip","olusturan","firma","tarih"}
                _veri_temiz = {k:v for k,v in _veri.items() if k in _GECERLI}
                _ok, _err = _an_kaydet(_firma, _veri_temiz)
                if _ok:
                    st.success(f"✅ **{_firma}** analizi {'güncellendi' if _duzenle else 'kaydedildi'}!")
                    st.balloons()
                    if _ik in st.session_state: del st.session_state[_ik]
                    try: db_read.clear()
                    except: pass
                    st.rerun()
                else:
                    st.error(f"❌ Kayıt hatası: {_err}")

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

# ── TELEFON KİŞİLER ──────────────────────────────────────────────────────────
elif aktif == "kisiler":
    sayfa_log("kisiler")

    # PIN koruması — sadece PIN bilen girebilir
    _KIS_PIN = "255266"
    if st.session_state.get("_kisiler_pin_ok") != True:
        st.markdown("## 🔐 Telefon Kişiler")
        st.markdown("Bu sayfa PIN korumalıdır.")
        _pin_gir = st.text_input("PIN girin:", type="password", key="kisiler_pin_input", max_chars=10)
        if st.button("Giriş", key="kisiler_pin_btn", type="primary"):
            if _pin_gir == _KIS_PIN:
                st.session_state["_kisiler_pin_ok"] = True
                st.rerun()
            else:
                st.error("❌ Yanlış PIN!")
        st.stop()

    # Yetki kontrolü — sadece admin görebilir
    if st.session_state.get("rol", "") != "admin":
        st.warning("⛔ Bu sayfaya erişim yetkiniz yok.")
        st.stop()

    import re as _re_kis
    st.markdown("## 📞 Telefon Kişiler & Rehber")

    ben = st.session_state.get("kullanici","")

    tab_rehber1, tab_rehber2, tab_rehber3, tab_rehber4, tab_rehber5, tab_rehber6 = st.tabs([
        "📋 Kişi Listesi", "➕ Kişi Ekle", "📥 Toplu İçe Aktar",
        "📝 Kayıtlı Şablonlar", "📊 Mesaj Raporu", "👤 Satış Temsilcileri"
    ])

    # Şablonları yükle (tüm tablar için)
    try:
        df_sab_all = db_read("sablon_mesajlar", extra_sql="WHERE aktif=1 ORDER BY ad")
        sablon_adlari = df_sab_all["ad"].tolist() if not df_sab_all.empty else []
    except:
        df_sab_all = pd.DataFrame()
        sablon_adlari = []

    # ── KİŞİ LİSTESİ ──────────────────────────────────────────────────────────
    with tab_rehber1:
        df_kis = db_read("kisiler", extra_sql="ORDER BY firma, ad")
        ara_kis = st.text_input("🔍 Ara:", key="kisiler_ara", placeholder="Ad, firma, tel, bölge...")
        if ara_kis:
            df_kis = df_kis[df_kis.apply(lambda r: ara_kis.lower() in str(r).lower(), axis=1)]
        st.caption(f"{len(df_kis)} kişi")

        if df_kis.empty:
            st.info("Kişi bulunamadı.")
        else:
            h1,h2,h3,h4,h5,h6,h7 = st.columns([2,1.5,1.3,1.5,2,0.8,0.8])
            for hdr,txt in zip([h1,h2,h3,h4,h5,h6,h7],["Ad","Firma","Tel","Mesaj","Şablon","📱","⚙️"]):
                hdr.caption(f"**{txt}**")

            # Mesaj loglarını tek seferde çek
            try:
                df_ml_all = db_read("kisiler_mesaj_log", extra_sql="ORDER BY tarih DESC")
            except:
                df_ml_all = pd.DataFrame()

            for _, kisi in df_kis.iterrows():
                # Tel: ham veriyi düzgün formatla
                tel_raw = str(kisi.get("telefon","") or "")
                tel = fmt_tel(tel_raw)
                # fmt_tel bazen boş dönebilir, ham veriyi de dene
                if not tel and tel_raw.strip():
                    tel = _re_kis.sub(r"[^\d]","",tel_raw.strip())

                isim = f"{kisi.get('ad','')} {kisi.get('soyad','')}".strip()
                _kisi_id = int(kisi.get("id",0) or 0)

                # Mesaj geçmişi bellekten filtrele
                if not df_ml_all.empty and "kisi_id" in df_ml_all.columns:
                    df_ml = df_ml_all[df_ml_all["kisi_id"]==_kisi_id]
                else:
                    df_ml = pd.DataFrame()

                # WA numarası hazırla
                t_wa = ""
                if tel:
                    t_wa = _re_kis.sub(r"[^\d]","",tel)
                    if t_wa.startswith("0") and len(t_wa)==11: t_wa = "90"+t_wa[1:]
                    elif len(t_wa)==10: t_wa = "90"+t_wa

                c1,c2,c3,c4,c5,c6,c7 = st.columns([2,1.5,1.4,1.5,2.2,0.8,0.8])
                c1.caption(f"**{isim}**")
                c2.caption(str(kisi.get("firma","") or "—")[:16])
                # Tel: göster
                c3.caption(tel if tel else f"_{tel_raw[:10]}_" if tel_raw else "—")

                # Mesaj geçmişi butonu
                if not df_ml.empty:
                    son = df_ml.iloc[0]
                    if c4.button(f"📨{len(df_ml)}", key=f"msg_btn_{_kisi_id}", use_container_width=True):
                        st.session_state[f"show_msg_{_kisi_id}"] = not st.session_state.get(f"show_msg_{_kisi_id}", False)
                else:
                    c4.caption("—")

                # Şablon seç
                sec_opts = ["—"] + sablon_adlari + ["✏️"]
                sec = c5.selectbox("", sec_opts, key=f"ks_{_kisi_id}", label_visibility="collapsed")

                # WA butonu — şablon seçilince hemen aktif
                if t_wa and len(t_wa) >= 10:
                    firma_h = str(kisi.get("firma","") or "").strip()
                    gorev_h = str(kisi.get("gorev","") or "").strip()

                    if sec == "✏️":
                        # Manuel mesaj
                        mesaj_key = f"km_{_kisi_id}"
                        if mesaj_key not in st.session_state:
                            st.session_state[mesaj_key] = ""
                        mesaj_txt = st.text_area("", height=60, key=mesaj_key, label_visibility="collapsed",
                            placeholder=f"Merhaba {isim}...")
                    elif sec != "—" and not df_sab_all.empty:
                        # Şablondan doldur
                        sab_row = df_sab_all[df_sab_all["ad"]==sec]
                        if not sab_row.empty:
                            sablon_txt = str(sab_row.iloc[0]["metin"]) if not sab_row.empty else ""
                            if firma_h:
                                header = f"*{firma_h}*" + (f" | {gorev_h}" if gorev_h else "") + "\n\n"
                                sablon_txt = header + sablon_txt
                            sablon_txt = sablon_txt.replace("{ad}", str(kisi.get("ad","") or ""))
                            sablon_txt = sablon_txt.replace("{firma}", firma_h)
                            sablon_txt = sablon_txt.replace("{yetkili}", gorev_h)
                        else:
                            sablon_txt = ""
                        mesaj_txt = sablon_txt
                    else:
                        mesaj_txt = ""

                    # WA linki — GEÇİCİ DEVRE DIŞI
                    if mesaj_txt and mesaj_txt.strip():
                        c6.button("📱", use_container_width=True, type="primary", disabled=True, help="Geçici olarak devre dışı", key=f"wa_btn_kisi_{_kisi_id}")
                        # Log
                        lk = f"logged_{_kisi_id}_{abs(hash(mesaj_txt[:30]))}"
                        if not st.session_state.get(lk) and _kisi_id > 0:
                            st.session_state[lk] = True
                            try:
                                sb_log = get_sb_client()
                                if sb_log:
                                    sb_log.table("kisiler_mesaj_log").insert({
                                        "kisi_id":_kisi_id,"kisi_adi":isim,"telefon":tel,
                                        "sablon_adi": sec if sec not in ["—","✏️"] else "Manuel",
                                        "mesaj":mesaj_txt[:500],"gonderen":ben
                                    }).execute()
                                    # Aynı zamanda islem_kaydi'ye de yaz — WA raporunda görünsün
                                    sb_log.table("islem_kaydi").insert({
                                        "musteri_id": 0,
                                        "musteri_adi": isim,
                                        "islem_turu": "📱 WA Kişi — " + (sec if sec not in ["—","✏️"] else "Manuel"),
                                        "icerik": mesaj_txt[:300],
                                        "gonderim_bilgisi": t_wa,
                                        "olusturan": ben
                                    }).execute()
                                    try: db_read.clear()
                                    except: pass
                            except: pass
                    else:
                        c6.caption("📱")
                else:
                    c5.caption("Tel yok")
                    c6.caption("—")

                if c7.button("✏️", key=f"kis_menu_{_kisi_id}", use_container_width=True):
                    st.session_state[f"kis_edit_{_kisi_id}"] = not st.session_state.get(f"kis_edit_{_kisi_id}", False)

                # Mesaj geçmişi göster
                if st.session_state.get(f"show_msg_{_kisi_id}") and not df_ml.empty:
                    with st.expander(f"📨 {isim} — {len(df_ml)} mesaj", expanded=True):
                        for _, mlog in df_ml.iterrows():
                            m1,m2,m3 = st.columns([2,5,1])
                            m1.caption(f"🕐 {str(mlog.get('tarih',''))[:16]}\n**{mlog.get('sablon_adi','')}**")
                            m2.info(str(mlog.get('mesaj','')))
                            if m3.button("🗑️", key=f"msg_sil_{mlog.get('id','')}_{_kisi_id}"):
                                try:
                                    sb_ms = get_sb_client()
                                    if sb_ms:
                                        sb_ms.table("kisiler_mesaj_log").delete().eq("id", int(mlog.get("id",0))).execute()
                                    try: db_read.clear()
                                    except: pass
                                except: pass
                                st.rerun()

                # Düzenle formu
                if st.session_state.get(f"kis_edit_{_kisi_id}"):
                    with st.form(f"kis_duzenle_{_kisi_id}"):
                        ed1,ed2,ed3 = st.columns(3)
                        e_ad    = ed1.text_input("Ad:", value=str(kisi.get("ad","")))
                        e_soyad = ed1.text_input("Soyad:", value=str(kisi.get("soyad","")))
                        e_tel   = ed2.text_input("Tel:", value=tel)
                        e_firma = ed2.text_input("Firma:", value=str(kisi.get("firma","")))
                        e_bolge = ed3.text_input("Bölge:", value=str(kisi.get("bolge","")))
                        e_email = ed3.text_input("Email:", value=str(kisi.get("email","")))
                        b1,b2,b3 = st.columns(3)
                        if b1.form_submit_button("💾 Kaydet", use_container_width=True, type="primary"):
                            db_update("kisiler",{"ad":e_ad,"soyad":e_soyad,"telefon":e_tel,
                                "firma":e_firma,"bolge":e_bolge,"email":e_email},"id",_kisi_id)
                            try: db_read.clear()
                            except: pass
                            st.success("✅ Kaydedildi!")
                            st.session_state.pop(f"kis_edit_{_kisi_id}",None); st.rerun()
                        if b2.form_submit_button("🗑️ Sil", use_container_width=True):
                            sb_ks = get_sb_client()
                            if sb_ks: sb_ks.table("kisiler").delete().eq("id",_kisi_id).execute()
                            try: db_read.clear()
                            except: pass
                            st.success("✅ Silindi!")
                            st.session_state.pop(f"kis_edit_{_kisi_id}",None); st.rerun()
                        if b3.form_submit_button("İptal", use_container_width=True):
                            st.session_state.pop(f"kis_edit_{_kisi_id}",None); st.rerun()

    # ── KİŞİ EKLE ─────────────────────────────────────────────────────────────
    with tab_rehber2:
        with st.form("kisi_ekle_form"):
            ke1, ke2, ke3 = st.columns(3)
            k_ad      = ke1.text_input("Ad*")
            k_soyad   = ke1.text_input("Soyad")
            k_tel     = ke2.text_input("Telefon*", placeholder="05xxxxxxxxx")
            k_email   = ke2.text_input("Email")
            k_firma   = ke3.text_input("Firma")
            k_gorev   = ke3.text_input("Görev/Ünvan")
            k_bolge   = ke1.text_input("Bölge")
            df_tem2 = db_read("temsilciler", extra_sql="WHERE aktif=1 ORDER BY ad")
            tem_opts = ["—"] + [f"{r['ad']} {r['soyad']}" for _, r in df_tem2.iterrows()] if not df_tem2.empty else ["—"]
            k_temsilci = ke2.selectbox("Sorumlu Temsilci", tem_opts)
            k_notlar  = ke3.text_area("Notlar", height=80)
            k_kaynak  = ke1.selectbox("Kaynak", ["Manuel","Sistem Müşterisi","Referans","Soğuk Arama","Diğer"])
            if st.form_submit_button("💾 Kişiyi Kaydet", use_container_width=True, type="primary"):
                if k_ad and k_tel:
                    kullanici_log_kaydet("KİŞİ_EKLE", "kisiler", f"Kişi: {k_ad}, Firma: {k_firma}")
                    db_insert("kisiler", {
                        "ad":k_ad,"soyad":k_soyad,"telefon":k_tel,"email":k_email,
                        "firma":k_firma,"gorev":k_gorev,"bolge":k_bolge,
                        "temsilci":k_temsilci if k_temsilci!="—" else "",
                        "notlar":k_notlar,"kaynak":k_kaynak
                    })
                    try: db_read.clear()
                    except: pass
                    st.success(f"✅ {k_ad} eklendi!"); st.rerun()
                else:
                    st.warning("Ad ve telefon zorunlu!")

    # ── TOPLU İÇE AKTAR ───────────────────────────────────────────────────────
    with tab_rehber3:
        st.info("Excel şablonunu indirin, doldurun, yükleyin.")
        sablon_kis = pd.DataFrame([{
            "firma":"ABC Ltd.","ad":"Ahmet","soyad":"Yılmaz",
            "telefon":"05001234567","email":"ahmet@firma.com",
            "gorev":"Satın Alma Müdürü","bolge":"İstanbul","notlar":""
        }])
        sbuf = io.BytesIO(); sablon_kis.to_excel(sbuf, index=False); sbuf.seek(0)
        st.download_button("📥 Şablon İndir", data=sbuf, file_name="kisiler_sablonu.xlsx", use_container_width=True)
        yukle_kis = st.file_uploader("Excel Yükle:", type=["xlsx","xls"], key="kisiler_yukle")
        if yukle_kis:
            df_yukle_kis = pd.read_excel(yukle_kis).fillna("").astype(str)
            df_yukle_kis = df_yukle_kis.replace("nan","").replace("None","")
            st.caption(f"{len(df_yukle_kis)} satır — önizleme:")
            st.dataframe(df_yukle_kis.head(5), use_container_width=True, hide_index=True)
            if st.button("🚀 İçe Aktar", use_container_width=True, type="primary"):
                pb = st.progress(0, text="Aktarılıyor...")
                batch = []; hatali = 0
                for _, row in df_yukle_kis.iterrows():
                    firma_v = str(row.get("firma","")).strip()
                    ad_v = str(row.get("ad","")).strip()
                    if not firma_v and not ad_v: hatali += 1; continue
                    batch.append({"firma":firma_v,"ad":ad_v,
                        "soyad":str(row.get("soyad","")).strip(),
                        "telefon":fmt_tel(str(row.get("telefon",""))),
                        "email":str(row.get("email","")).strip(),
                        "gorev":str(row.get("gorev","")).strip(),
                        "bolge":str(row.get("bolge","")).strip(),
                        "notlar":str(row.get("notlar","")).strip(),"kaynak":"Excel"})
                basarili = 0; sb_b = get_sb_client()
                for start in range(0, len(batch), 50):
                    chunk = batch[start:start+50]
                    try:
                        if sb_b: sb_b.table("kisiler").insert(chunk).execute(); basarili += len(chunk)
                        else:
                            for item in chunk:
                                db_insert("kisiler", item); basarili += 1
                    except:
                        for item in chunk:
                            try: db_insert("kisiler", item); basarili += 1
                            except: hatali += 1
                    pb.progress(min((start+50)/len(batch),1.0), text=f"{basarili} eklendi...")
                pb.empty()
                try: db_read.clear()
                except: pass
                st.success(f"✅ {basarili} kişi eklendi! {hatali} atlandı."); st.rerun()

    # ── KAYITLI ŞABLONLAR ─────────────────────────────────────────────────────
    with tab_rehber4:
        st.markdown("#### 📝 Kayıtlı Şablonlar")
        st.caption("💡 `{ad}` → kişi adı  `{firma}` → firma  `{yetkili}` → görevi")
        with st.form("sablon_kaydet_form"):
            s1, s2 = st.columns([2,5])
            sab_isim = s1.text_input("Şablon Adı*:", placeholder="Örn: Tanışma")
            sab_metin = s2.text_area("Mesaj Metni*:", height=100, placeholder="Merhaba {ad} Bey/Hanım,")
            if st.form_submit_button("💾 Kaydet", use_container_width=True, type="primary"):
                if sab_isim and sab_isim.strip() and sab_metin and sab_metin.strip():
                    db_insert("sablon_mesajlar", {"ad":sab_isim.strip(),"metin":sab_metin.strip(),"olusturan":ben,"aktif":1})
                    try: db_read.clear()
                    except: pass
                    st.success("✅ Kaydedildi!"); st.rerun()
                else:
                    st.error("Şablon adı ve mesaj metni dolu olmalı!")
        try:
            df_sab_list = db_read("sablon_mesajlar", extra_sql="WHERE aktif=1 ORDER BY ad")
        except:
            df_sab_list = pd.DataFrame()
        if not df_sab_list.empty:
            st.divider()
            st.markdown(f"**{len(df_sab_list)} şablon**")
            for _, sab in df_sab_list.iterrows():
                sa1,sa2,sa3,sa4 = st.columns([2,5,1,1])
                sa1.markdown(f"**{sab['ad']}**")
                sa2.caption(str(sab['metin'])[:100])
                if sa3.button("✏️", key=f"sab_edit_{sab['id']}"):
                    st.session_state[f"edit_sab_{sab['id']}"] = not st.session_state.get(f"edit_sab_{sab['id']}", False)
                can_del = st.session_state.get("rol")=="admin" or str(sab.get("olusturan",""))==ben
                if can_del and sa4.button("🗑️", key=f"sab_sil_{sab['id']}"):
                    sb_d = get_sb_client()
                    if sb_d: sb_d.table("sablon_mesajlar").delete().eq("id", int(sab["id"])).execute()
                    try: db_read.clear()
                    except: pass
                    st.rerun()
                if st.session_state.get(f"edit_sab_{sab['id']}"):
                    with st.form(f"sab_duzenle_{sab['id']}"):
                        yeni_ad = st.text_input("Ad:", value=sab["ad"])
                        yeni_mt = st.text_area("Metin:", value=sab["metin"], height=100)
                        c1,c2 = st.columns(2)
                        if c1.form_submit_button("💾 Güncelle", use_container_width=True, type="primary"):
                            db_update("sablon_mesajlar",{"ad":yeni_ad,"metin":yeni_mt},"id",int(sab["id"]))
                            try: db_read.clear()
                            except: pass
                            st.session_state.pop(f"edit_sab_{sab['id']}", None); st.rerun()
                        if c2.form_submit_button("İptal", use_container_width=True):
                            st.session_state.pop(f"edit_sab_{sab['id']}", None); st.rerun()
        else:
            st.info("Henüz şablon yok. Yukarıdan ekleyin.")

    # ── MESAJ RAPORU ──────────────────────────────────────────────────────────
    with tab_rehber5:
        st.markdown("#### 📊 Mesaj Raporu")
        try:
            df_mlog_all = db_read("kisiler_mesaj_log", extra_sql="ORDER BY tarih DESC")
        except:
            df_mlog_all = pd.DataFrame()
        if df_mlog_all.empty:
            st.info("Henüz mesaj kaydı yok.")
        else:
            mr1,mr2,mr3 = st.columns(3)
            mr1.metric("Toplam Gönderim", len(df_mlog_all))
            mr2.metric("Farklı Kişi", df_mlog_all["kisi_id"].nunique() if "kisi_id" in df_mlog_all.columns else 0)
            mr3.metric("Farklı Şablon", df_mlog_all["sablon_adi"].nunique() if "sablon_adi" in df_mlog_all.columns else 0)
            st.divider()
            if "tarih" in df_mlog_all.columns:
                df_mlog_all["gun"] = pd.to_datetime(df_mlog_all["tarih"], errors="coerce").dt.strftime("%Y-%m-%d")
                gun_oz = df_mlog_all.groupby("gun").agg(
                    Gonderim=("id","count"),Kisi=("kisi_adi","nunique"),
                    Sablon=("sablon_adi", lambda x:", ".join(x.unique()[:3]))
                ).reset_index().sort_values("gun",ascending=False)
                gun_oz.columns=["Tarih","Gönderim","Kişi","Şablonlar"]
                st.markdown("**📅 Gün Gün:**")
                st.dataframe(gun_oz, use_container_width=True, hide_index=True)
            if "sablon_adi" in df_mlog_all.columns:
                sab_oz = df_mlog_all.groupby("sablon_adi").agg(
                    Kullanim=("id","count"),Kisi=("kisi_adi","nunique"),Son=("tarih","max")
                ).reset_index().sort_values("Kullanim",ascending=False)
                sab_oz["Son"] = sab_oz["Son"].astype(str).str[:16]
                st.markdown("**📝 Şablon Bazlı:**")
                st.dataframe(sab_oz, use_container_width=True, hide_index=True)
            with st.expander("📋 Tüm Gönderimler"):
                st.dataframe(df_mlog_all[[c for c in ["tarih","kisi_adi","sablon_adi","mesaj","gonderen"] if c in df_mlog_all.columns]], use_container_width=True, hide_index=True)
            buf_ml = io.BytesIO(); df_mlog_all.to_excel(buf_ml, index=False); buf_ml.seek(0)
            st.download_button("📥 İndir", data=buf_ml, file_name="mesaj_raporu.xlsx", use_container_width=True)

    with tab_rehber6:
        st.markdown("#### 👤 Satış Temsilcisi Kartları")
        df_tem = db_read("temsilciler", extra_sql="WHERE aktif=1 ORDER BY ad")
        if not df_tem.empty:
            st.dataframe(df_tem[["id","ad","soyad","telefon","email","bolge","unvan"]], use_container_width=True, hide_index=True)
        st.divider()
        st.markdown("#### ➕ Yeni Temsilci Ekle")
        with st.form("temsilci_form"):
            tc1, tc2, tc3 = st.columns(3)
            t_ad    = tc1.text_input("Ad*")
            t_soyad = tc1.text_input("Soyad")
            t_tel   = tc2.text_input("Telefon*", placeholder="05xxxxxxxxx")
            t_email = tc2.text_input("Email")
            t_bolge = tc3.text_input("Bölge")
            t_unvan = tc3.text_input("Ünvan", placeholder="Satış Temsilcisi")
            if st.form_submit_button("💾 Kaydet", use_container_width=True):
                if t_ad and t_tel:
                    db_insert("temsilciler", {"ad":t_ad,"soyad":t_soyad,"telefon":t_tel,"email":t_email,"bolge":t_bolge,"unvan":t_unvan,"aktif":1})
                    try: db_read.clear()
                    except: pass
                    st.success(f"✅ {t_ad} eklendi!"); st.rerun()
                else:
                    st.warning("Ad ve telefon zorunlu!")


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

            # Sıralama hafızası
            if "rand_sort_col" not in st.session_state:
                st.session_state["rand_sort_col"] = "Tarih"
                st.session_state["rand_sort_asc"] = True
            _rs1,_rs2 = st.columns([2,1])
            _sort_col = _rs1.selectbox("Sırala:", ["ID","Tarih","Saat","Müşteri","İl","Bölge","Görev","Sonuç","Temsilci"],
                index=["ID","Tarih","Saat","Müşteri","İl","Bölge","Görev","Sonuç","Temsilci"].index(st.session_state.get("rand_sort_col","Tarih")) if st.session_state.get("rand_sort_col","Tarih") in ["ID","Tarih","Saat","Müşteri","İl","Bölge","Görev","Sonuç","Temsilci"] else 1,
                key="rand_sort_sel",
                help="ID hiçbir zaman değişmez — her randevu ilk oluşturulduğu numarayı korur. Listeyi farklı sütuna göre sıralamak sadece görüntü sırasını değiştirir, ID'leri değiştirmez.")
            _sort_asc = _rs2.checkbox("Artan", value=st.session_state.get("rand_sort_asc",True), key="rand_sort_asc_cb")
            # Hafızaya kaydet
            st.session_state["rand_sort_col"] = _sort_col
            st.session_state["rand_sort_asc"] = _sort_asc
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
            } for _,r in df_rand.iterrows()])

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
                    _rmn_r = _sb_rmn.table("cari_aciklamalar").select("aciklama,created_at").eq("cari_id", int(_rmid)).order("id", desc=True).limit(1).execute()
                    if _rmn_r.data:
                        _rm_son_not = str(_rmn_r.data[0].get("aciklama","") or "")
                        _rm_not_tarih = str(_rmn_r.data[0].get("created_at","") or "")[:10]
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
            st.markdown(f"""<div style="
                position:relative; margin-top:-38px; pointer-events:none;
                font-size:13px; color:#0f172a; padding:9px 14px;
                background:transparent; text-align:left;
            ">📅 {_tarih_okunur}</div>""", unsafe_allow_html=True)
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
                            _rn_veri = {"cari_id": int(musteri_id), "aciklama": _not_metni, "olusturan": _yazar_rn, "cari_adi": str(musteri_adi)}
                            if _sb_rn:
                                try:
                                    _sb_rn.table("cari_aciklamalar").insert(_rn_veri).execute()
                                except Exception:
                                    _rn_veri2 = {"cari_id": int(musteri_id), "aciklama": _not_metni, "olusturan": _yazar_rn}
                                    _sb_rn.table("cari_aciklamalar").insert(_rn_veri2).execute()
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
        if not _df_as.empty and "islem_asamasi" in _df_as.columns:
            for _da in _df_as["islem_asamasi"].dropna().unique():
                if str(_da).strip() and str(_da) not in ["nan",""] and _da not in _tum_asama_r:
                    _tum_asama_r.append(str(_da))

        _col_config_r = {
            "Seç":           st.column_config.CheckboxColumn("Seç", default=False),
            "id":            st.column_config.NumberColumn("ID", disabled=True, width=_w("id")),
            "tarih":         None, "olusturan": None, "silindi": None,
            "beklenen_ciro": st.column_config.NumberColumn("Hedef ₺", format="%,.0f ₺", width=_w("beklenen_ciro")),
            "gerceklesen_ciro": st.column_config.NumberColumn("Gerçek ₺", format="%,.0f ₺", width=_w("gerceklesen_ciro")),
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
        _col_order_r = ["Seç","id","firma","yetkili","gsm","sabit","email","adres","il","ilce","durum","temsilci","islem_asamasi","aciklama","beklenen_ciro","gerceklesen_ciro","📅 Son Randevu","📨 Notlar"]
        _kol_gizli_map_r = {"firma":"firma","yetkili":"yetkili","gsm":"gsm","sabit":"sabit","email":"email","adres":"adres","il":"il","ilce":"ilce","durum":"durum","temsilci":"temsilci","islem_asamasi":"islem_asamasi","aciklama":"aciklama",
                            "📅 Son Randevu":"📅 Son Randevu","📨 Notlar":"📨 Notlar","id":"id",
                            "beklenen_ciro":"beklenen_ciro","gerceklesen_ciro":"gerceklesen_ciro"}
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
            _varsayilan = ["Aktif","Hedef","Pasif"]
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
                    _rn = sb_liste.table("cari_aciklamalar").select("cari_id, cari_adi").execute()
                    if _rn.data:
                        import collections as _col
                        _sayac = _col.Counter([(r["cari_id"], r["cari_adi"]) for r in _rn.data])
                        _df_notlu = pd.DataFrame([
                            {"cari_id": k[0], "firma": k[1], "not_sayi": v}
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
                except:
                    _df_notlar = pd.DataFrame()

                st.markdown(f"**{_sec_firma} — {len(_df_notlar)} not:**")

                if not _df_notlar.empty:
                    for _, _nr in _df_notlar.iterrows():
                        _nid   = _nr.get("id", 0)
                        _ntarih = fmt_tarih(_nr.get("tarih",""))
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
        "📞 Kişiler":         "kisiler",
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



elif aktif == "patron":
    sayfa_log("patron")
    import json as _pj
    from datetime import datetime as _pdt, timedelta as _ptd
    import streamlit.components.v1 as _pc

    # Müşteri Atama hızlı erişim
    _pat_c1, _pat_c2 = st.columns([1,4])
    if _pat_c1.button("🎯 Müşteri Atama", use_container_width=True, type="primary"):
        st.session_state["aktif_tab"] = "musteri_atama"
        st.rerun()
    st.divider()

    _bugun = _pdt.now().date()

    # Veri çek
    _p_cari = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")
    _p_rand = db_read("randevular", extra_sql="ORDER BY randevu_tarihi DESC")
    _p_tek  = db_read("teklifler", order_col="tarih")
    _p_an   = db_read("musteri_analiz")
    try:
        _sb_pat = get_sb_client()
        if _sb_pat:
            _p_notlar_raw = _sb_pat.table("cari_aciklamalar").select("cari_id,created_at,tarih").execute().data or []
        else:
            _p_notlar_raw = []
    except:
        try:
            _sb_pat = get_sb_client()
            _p_notlar_raw = _sb_pat.table("cari_aciklamalar").select("*").execute().data or [] if _sb_pat else []
        except: _p_notlar_raw = []

    # Tarih normalize — created_at veya tarih kolonundan al
    _p_notlar = []
    for _nn in _p_notlar_raw:
        _nt = str(_nn.get("created_at","") or _nn.get("tarih","") or "")[:10]
        if _nt:
            _p_notlar.append({"cari_id": _nn.get("cari_id",""), "tarih": _nt})

    # Periyot seçimi
    _periyot = st.session_state.get("patron_periyot", "ay")
    _pc1,_pc2,_pc3 = st.columns(3)
    if _pc1.button("Bugün", key="pp1", use_container_width=True, type="primary" if _periyot=="bugun" else "secondary"):
        st.session_state["patron_periyot"]="bugun"; st.rerun()
    if _pc2.button("Bu Hafta", key="pp2", use_container_width=True, type="primary" if _periyot=="hafta" else "secondary"):
        st.session_state["patron_periyot"]="hafta"; st.rerun()
    if _pc3.button("Bu Ay", key="pp3", use_container_width=True, type="primary" if _periyot=="ay" else "secondary"):
        st.session_state["patron_periyot"]="ay"; st.rerun()

    # Tarih aralığı
    if _periyot == "bugun":
        _bas = str(_bugun); _bit = str(_bugun)
        _per_lbl = f"Bugün — {_bugun.strftime('%d %B %Y')}"
    elif _periyot == "hafta":
        _bas = str(_bugun - _ptd(days=_bugun.weekday())); _bit = str(_bugun)
        _per_lbl = f"Bu Hafta — {(_bugun - _ptd(days=_bugun.weekday())).strftime('%d')}–{_bugun.strftime('%d %B %Y')}"
    else:
        _bas = str(_bugun.replace(day=1)); _bit = str(_bugun)
        _per_lbl = f"Bu Ay — {_bugun.strftime('%B %Y')}"

    # Tarih filtresi
    def _tfil(df, kolon):
        if df.empty or kolon not in df.columns: return pd.DataFrame()
        return df[(df[kolon].astype(str)>=_bas)&(df[kolon].astype(str)<=_bit)]

    _p_rand_p = _tfil(_p_rand, "randevu_tarihi")
    _p_tek_p  = _tfil(_p_tek, "tarih")
    _p_an_p   = _tfil(_p_an, "tarih") if not _p_an.empty and "tarih" in _p_an.columns else _p_an

    # Not sayıları — dönem filtreli
    _not_sayi = sum(1 for n in _p_notlar if n["tarih"] >= _bas and n["tarih"] <= _bit)

    # KPI
    _kpi_rnd = len(_p_rand_p)
    _kpi_anl = len(_p_an_p) if not _p_an_p.empty else 0
    _kpi_not = _not_sayi
    _kpi_tkl = len(_p_tek_p) if not _p_tek_p.empty else 0
    _kpi_arm = len(_p_rand_p[_p_rand_p["gorev"]=="Arama"]) if not _p_rand_p.empty and "gorev" in _p_rand_p.columns else 0

    # Gün gün satırlar — cari kartlara join
    _cari_map = {}
    if not _p_cari.empty:
        for _, _cr in _p_cari.iterrows():
            _cari_map[str(_cr.get("firma",""))] = {
                "yetkili": str(_cr.get("yetkili","") or "—"),
                "gsm": str(_cr.get("gsm","") or "—"),
                "il": str(_cr.get("il","") or ""),
                "ilce": str(_cr.get("ilce","") or ""),
            }

    # Tarih bazlı gruplama
    _gun_data = {}

    # Randevular
    if not _p_rand_p.empty:
        for _, _rr in _p_rand_p.iterrows():
            _rt = str(_rr.get("randevu_tarihi",""))[:10]
            if not _rt or _rt < _bas: continue
            _fm = str(_rr.get("musteri","") or "")
            _cr = _cari_map.get(_fm, {"yetkili":"—","gsm":"—","il":"","ilce":""})
            _gorev = str(_rr.get("gorev","") or "")
            _saat = str(_rr.get("randevu_saati","") or "")
            _sonuc = str(_rr.get("sonuc","") or "")
            if _rt not in _gun_data: _gun_data[_rt] = {}
            _key = _fm + "_" + _rt
            if _key not in _gun_data[_rt]:
                _gun_data[_rt][_key] = {"f":_fm,"alt":_gorev,"y":_cr["yetkili"],"tel":_cr["gsm"],"adr":(_cr["il"]+("/"+_cr["ilce"] if _cr["ilce"] else "")),"r":0,"a":0,"n":0,"k":0,"m":0,"z":_saat}
            if _gorev == "Ziyaret": _gun_data[_rt][_key]["r"] += 1
            elif _gorev == "Arama": _gun_data[_rt][_key]["m"] += 1
            else: _gun_data[_rt][_key]["r"] += 1

    # Analizler
    if not _p_an_p.empty:
        for _, _ar in _p_an_p.iterrows():
            _at = str(_ar.get("tarih",""))[:10]
            if not _at or _at < _bas: continue
            _fm = str(_ar.get("firma","") or "")
            _cr = _cari_map.get(_fm, {"yetkili":"—","gsm":"—","il":"","ilce":""})
            if _at not in _gun_data: _gun_data[_at] = {}
            _key = _fm + "_" + _at
            if _key not in _gun_data[_at]:
                _gun_data[_at][_key] = {"f":_fm,"alt":"Analiz yapıldı","y":_cr["yetkili"],"tel":_cr["gsm"],"adr":(_cr["il"]+("/"+_cr["ilce"] if _cr["ilce"] else "")),"r":0,"a":0,"n":0,"k":0,"m":0,"z":""}
            _gun_data[_at][_key]["a"] += 1

    # Teklifler
    if not _p_tek_p.empty:
        for _, _tr in _p_tek_p.iterrows():
            _tt = str(_tr.get("tarih",""))[:10]
            if not _tt or _tt < _bas: continue
            _fm = str(_tr.get("musteri","") or _tr.get("firma","") or "")
            _cr = _cari_map.get(_fm, {"yetkili":"—","gsm":"—","il":"","ilce":""})
            if _tt not in _gun_data: _gun_data[_tt] = {}
            _key = _fm + "_" + _tt
            if _key not in _gun_data[_tt]:
                _gun_data[_tt][_key] = {"f":_fm,"alt":"Teklif hazırlandı","y":_cr["yetkili"],"tel":_cr["gsm"],"adr":(_cr["il"]+("/"+_cr["ilce"] if _cr["ilce"] else "")),"r":0,"a":0,"n":0,"k":0,"m":0,"z":""}
            _gun_data[_tt][_key]["k"] += 1

    # Notlar - cari_id → firma adı map
    _cari_id_map = {}
    if not _p_cari.empty and "id" in _p_cari.columns:
        for _, _cr2 in _p_cari.iterrows():
            _cari_id_map[str(int(_cr2["id"]))] = str(_cr2.get("firma","") or "")

    for _nn in _p_notlar:
        _nt = _nn["tarih"]
        if not _nt or _nt < _bas or _nt > _bit: continue
        _ncid = str(_nn.get("cari_id","") or "")
        _nm = _cari_id_map.get(_ncid, "")
        if not _nm: continue
        _cr = _cari_map.get(_nm, {"yetkili":"—","gsm":"—","il":"","ilce":""})
        if _nt not in _gun_data: _gun_data[_nt] = {}
        _key = _nm + "_" + _nt
        if _key not in _gun_data[_nt]:
            _gun_data[_nt][_key] = {"f":_nm,"alt":"Not eklendi","y":_cr["yetkili"],"tel":_cr["gsm"],"adr":(_cr["il"]+("/"+_cr["ilce"] if _cr["ilce"] else "")),"r":0,"a":0,"n":0,"k":0,"m":0,"z":""}
        _gun_data[_nt][_key]["n"] += 1

    # JSON hazırla
    _rows_json = []
    for _tarih in sorted(_gun_data.keys(), reverse=True):
        for _key, _val in _gun_data[_tarih].items():
            _rows_json.append({
                "t": _tarih,
                "z": _val["z"],
                "f": _val["f"][:40],
                "alt": _val["alt"],
                "y": _val["y"][:25],
                "tel": _val["tel"],
                "adr": _val["adr"],
                "r": _val["r"],
                "a": _val["a"],
                "n": _val["n"],
                "k": _val["k"],
                "m": _val["m"],
            })

    _data_json = _pj.dumps({
        "kpi": {"rnd":_kpi_rnd,"anl":_kpi_anl,"not":_kpi_not,"tkl":_kpi_tkl,"arm":_kpi_arm},
        "rows": _rows_json,
        "label": _per_lbl,
        "periyot": _periyot,
    }, ensure_ascii=False)

    _patron_html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.44.0/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;}
body{padding:8px;color:#1e293b;background:transparent;}
.kpi-row{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:14px;}
.kpi{background:#f8fafc;border:0.5px solid #e2e8f0;border-radius:10px;padding:12px;display:flex;align-items:center;gap:10px;}
.kpi-icon{width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:18px;}
.kpi-v{font-size:20px;font-weight:600;}
.kpi-l{font-size:11px;color:#64748b;margin-top:1px;}
.tbl{background:white;border:0.5px solid #e2e8f0;border-radius:10px;overflow:hidden;}
.thdr{display:grid;grid-template-columns:100px 1fr 1fr 85px 55px 55px 55px 55px 55px;padding:8px 12px;background:#f8fafc;border-bottom:0.5px solid #e2e8f0;font-size:10px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;gap:4px;}
.trow{display:grid;grid-template-columns:100px 1fr 1fr 85px 55px 55px 55px 55px 55px;padding:9px 12px;border-bottom:0.5px solid #f1f5f9;align-items:center;gap:4px;cursor:default;transition:background .1s;}
.trow:last-child{border-bottom:none;}
.trow:hover{background:#f8fafc;}
.tarih-sep{padding:5px 12px;background:#f1f5f9;border-bottom:0.5px solid #e2e8f0;font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.5px;display:flex;align-items:center;justify-content:space-between;}
.z{font-size:11px;color:#94a3b8;}
.zb{font-weight:600;color:#374151;}
.f .fn{font-size:13px;font-weight:600;color:#0f172a;}
.f .fa{font-size:11px;color:#94a3b8;margin-top:1px;}
.con .cy{font-size:12px;color:#374151;}
.con .ct{font-size:11px;color:#3266ad;margin-top:1px;}
.con .ca{font-size:10px;color:#94a3b8;margin-top:1px;}
.cn{text-align:center;}
.b{display:inline-flex;align-items:center;justify-content:center;border-radius:6px;font-size:12px;font-weight:600;min-width:28px;padding:3px 6px;}
.d{color:#e2e8f0;}
.chip{display:inline-block;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:500;}
.foot{display:flex;justify-content:space-between;align-items:center;padding:9px 12px;background:#f8fafc;border-top:0.5px solid #e2e8f0;font-size:12px;color:#64748b;}
</style></head><body>
<div id="root"></div>
<script>
var DATA=""" + _data_json + """;
var CFG=[
  {k:'rnd',l:'Randevu',c:'#3266ad',bg:'#eff6ff',ic:'ti-calendar'},
  {k:'anl',l:'Analiz',c:'#7c3aed',bg:'#fdf4ff',ic:'ti-chart-bar'},
  {k:'not',l:'Not',c:'#0369a1',bg:'#f0f9ff',ic:'ti-notes'},
  {k:'tkl',l:'Teklif',c:'#b45309',bg:'#fff7ed',ic:'ti-file-text'},
  {k:'arm',l:'Arama',c:'#16a34a',bg:'#f0fdf4',ic:'ti-phone'},
];
var KM={rnd:'r',anl:'a',not:'n',tkl:'k',arm:'m'};
function bc(v,c,bg){
  if(!v) return '<div class="cn"><span class="d">—</span></div>';
  return '<div class="cn"><span class="b" style="background:'+bg+';color:'+c+'">'+v+'</span></div>';
}
function render(){
  var root=document.getElementById('root');
  var d=DATA;
  // KPI
  var kh='<div class="kpi-row">';
  CFG.forEach(function(c){
    kh+='<div class="kpi"><div class="kpi-icon" style="background:'+c.bg+'"><i class="ti '+c.ic+'" style="color:'+c.c+'"></i></div><div><div class="kpi-v" style="color:'+c.c+'">'+d.kpi[c.k]+'</div><div class="kpi-l">'+c.l+'</div></div></div>';
  });
  kh+='</div>';
  // Tablo
  var th='<div class="tbl"><div class="thdr"><div>Tarih/Saat</div><div>Müşteri</div><div>Yetkili & İletişim</div><div>Toplam</div><div style="text-align:center;color:#3266ad">Rnd</div><div style="text-align:center;color:#7c3aed">Anl</div><div style="text-align:center;color:#0369a1">Not</div><div style="text-align:center;color:#b45309">Tkl</div><div style="text-align:center;color:#16a34a">Arm</div></div>';
  // Tarih grupla
  var tarihler=[],tm={};
  d.rows.forEach(function(r){if(!tm[r.t]){tarihler.push(r.t);tm[r.t]=[];}tm[r.t].push(r);});
  var showGrup=d.periyot==='ay';
  tarihler.forEach(function(tarih){
    var rows=tm[tarih];
    var gt=0;rows.forEach(function(r){gt+=r.r+r.a+r.n+r.k+r.m;});
    if(showGrup){
      var d2=new Date(tarih);
      var ay=['Oca','Şub','Mar','Nis','May','Haz','Tem','Ağu','Eyl','Eki','Kas','Ara'];
      th+='<div class="tarih-sep"><span>'+d2.getDate()+' '+ay[d2.getMonth()]+'</span><span style="background:white;border:0.5px solid #e2e8f0;padding:2px 8px;border-radius:6px;font-size:10px">'+rows.length+' müşteri · '+gt+' işlem</span></div>';
    }
    rows.forEach(function(row,ri){
      var t=row.r+row.a+row.n+row.k+row.m;
      var tc=t>=6?'#dc2626':t>=3?'#b45309':'#374151';
      var tbg=t>=6?'#fee2e2':t>=3?'#fff7ed':'#f1f5f9';
      var zc=showGrup?(ri===0&&row.z?'<div class="z">'+row.z+'</div>':'<div class="z"></div>')
        :'<div class="z"><span class="zb">'+tarih.slice(5).replace('-',' ')+'</span>'+(row.z?'<br>'+row.z:'')+'</div>';
      th+='<div class="trow">'+zc
        +'<div class="f"><div class="fn">'+row.f+'</div><div class="fa">'+row.alt+'</div></div>'
        +'<div class="con"><div class="cy">'+row.y+'</div><div class="ct"><i class="ti ti-phone" style="font-size:10px"></i> '+row.tel+'</div><div class="ca"><i class="ti ti-map-pin" style="font-size:10px"></i> '+row.adr+'</div></div>'
        +'<div><span class="chip" style="background:'+tbg+';color:'+tc+'">'+t+' işlem</span></div>'
        +bc(row.r,'#1d4ed8','#eff6ff')+bc(row.a,'#7c3aed','#fdf4ff')+bc(row.n,'#0369a1','#f0f9ff')+bc(row.k,'#c2410c','#fff7ed')+bc(row.m,'#15803d','#f0fdf4')
        +'</div>';
    });
  });
  var tot={r:0,a:0,n:0,k:0,m:0};
  d.rows.forEach(function(r){tot.r+=r.r;tot.a+=r.a;tot.n+=r.n;tot.k+=r.k;tot.m+=r.m;});
  var grand=tot.r+tot.a+tot.n+tot.k+tot.m;
  th+='<div class="foot"><span style="font-weight:600;color:#0f172a">'+d.label+' · '+grand+' toplam işlem</span>'
    +'<div style="display:flex;gap:12px">'
    +'<span><span style="color:#3266ad;font-weight:600">'+tot.r+'</span> randevu</span>'
    +'<span><span style="color:#7c3aed;font-weight:600">'+tot.a+'</span> analiz</span>'
    +'<span><span style="color:#0369a1;font-weight:600">'+tot.n+'</span> not</span>'
    +'<span><span style="color:#b45309;font-weight:600">'+tot.k+'</span> teklif</span>'
    +'<span><span style="color:#16a34a;font-weight:600">'+tot.m+'</span> arama</span>'
    +'</div></div></div>';
  root.innerHTML=kh+th;
}
render();
</script></body></html>"""

    _pc.html(_patron_html, height=700, scrolling=True)



elif aktif == "musteri_atama":
    sayfa_log("musteri_atama")

    if st.session_state.get("rol") != "admin":
        st.error("❌ Bu sayfaya erişim yetkiniz yok.")
        st.stop()

    st.markdown("## 🎯 Müşteri Atama")
    st.caption("Checkbox ile seç, kullanıcı belirle, tek butonla kaydet.")

    _sb_ma = get_sb_client()

    # Kullanıcıları yükle
    try:
        _kul_res = _sb_ma.table("kullanicilar").select("kullanici_adi,rol").execute()
        _kul_listesi = [r["kullanici_adi"] for r in _kul_res.data if r.get("kullanici_adi")] if _kul_res.data else []
    except:
        _kul_listesi = []

    # Müşterileri yükle — hedef, durum, il, ilçe ile
    try:
        _ma_res = _sb_ma.table("cari_kartlar").select("id,firma,durum,il,ilce,beklenen_ciro,atanan_kullanici").neq("silindi",1).order("firma").execute()
        _df_ma = pd.DataFrame(_ma_res.data) if _ma_res.data else pd.DataFrame()
    except:
        _df_ma = pd.DataFrame()

    if _df_ma.empty:
        st.info("Müşteri bulunamadı.")
        st.stop()

    # İstatistik
    _atanmis = len(_df_ma[_df_ma["atanan_kullanici"].notna() & (_df_ma["atanan_kullanici"] != "")])
    _atanmamis = len(_df_ma) - _atanmis
    _sc1, _sc2, _sc3 = st.columns(3)
    _sc1.metric("Toplam Müşteri", len(_df_ma))
    _sc2.metric("Atanmış", _atanmis)
    _sc3.metric("Atanmamış", _atanmamis)

    st.divider()

    # ── FİLTRELER ─────────────────────────────────────────────────────────────
    _maf1, _maf2 = st.columns(2)
    _ma_ara = _maf1.text_input("🔍 Firma Ara", placeholder="firma adı...", key="ma_ara")
    _ma_kul_fil = _maf2.selectbox("Kullanıcıya Göre", ["Tümü", "Atanmamış"] + _kul_listesi, key="ma_kul_fil")

    # Filtre uygula
    _df_goster = _df_ma.copy()
    if _ma_ara:
        _df_goster = _df_goster[_df_goster["firma"].astype(str).str.contains(_ma_ara, case=False, na=False)]
    if _ma_kul_fil == "Atanmamış":
        _df_goster = _df_goster[_df_goster["atanan_kullanici"].isna() | (_df_goster["atanan_kullanici"] == "")]
    elif _ma_kul_fil != "Tümü":
        _df_goster = _df_goster[_df_goster["atanan_kullanici"] == _ma_kul_fil]

    _df_goster = _df_goster.reset_index(drop=True)
    st.caption(f"{len(_df_goster)} müşteri gösteriliyor")

    # ── TOPLU ATAMA BARI ──────────────────────────────────────────────────────
    _opts_kul = ["— Kullanıcı Seç —"] + _kul_listesi
    _tab1, _tab2 = st.columns([3,1])
    _ma_toplu_kul = _tab1.selectbox("Seçilenleri şu kullanıcıya ata:", _opts_kul, key="ma_toplu_kul", label_visibility="collapsed")

    # Seçili ID'leri session'dan al
    if "ma_secili_ids" not in st.session_state:
        st.session_state["ma_secili_ids"] = set()
    _secili_ids = st.session_state["ma_secili_ids"]

    # Tümünü seç/kaldır
    _tumu_sec = _tab2.checkbox(f"Tümünü Seç ({len(_df_goster)})", key="ma_tumunu_sec_v2")
    if _tumu_sec:
        _secili_ids = set(_df_goster["id"].tolist())
        st.session_state["ma_secili_ids"] = _secili_ids
    elif not _tumu_sec and st.session_state.get("ma_tumunu_sec_v2_onceki", False):
        _secili_ids = set()
        st.session_state["ma_secili_ids"] = _secili_ids
    st.session_state["ma_tumunu_sec_v2_onceki"] = _tumu_sec

    # Tümünü seç/kaldır

    # ── SIRALAMA ──────────────────────────────────────────────────────────────
    if "ma_sort_col" not in st.session_state:
        st.session_state["ma_sort_col"] = "firma"
        st.session_state["ma_sort_asc"] = True

    _sort_map = {"firma":"firma","durum":"durum","il":"il","ilce":"ilce","hedef":"beklenen_ciro","atanan":"atanan_kullanici"}
    _sort_col_key = st.session_state["ma_sort_col"]
    _sort_asc_val = st.session_state["ma_sort_asc"]
    if _sort_col_key in _df_goster.columns:
        _df_goster = _df_goster.sort_values(_sort_col_key, ascending=_sort_asc_val, na_position="last").reset_index(drop=True)

    def _ma_sort_btn(col_key, label):
        _cur = st.session_state.get("ma_sort_col","firma")
        _asc = st.session_state.get("ma_sort_asc", True)
        _ikon = (" ↑" if _asc else " ↓") if _cur == col_key else ""
        return f"{label}{_ikon}"

    # Toplu ata butonu
    if _secili_ids and _ma_toplu_kul != "— Kullanıcı Seç —":
        if st.button(f"✅ Seçili {len(_secili_ids)} müşteriyi **{_ma_toplu_kul}**'a ata", type="primary", use_container_width=True, key="ma_toplu_btn"):
            try:
                _basarili = 0
                for _tid in _secili_ids:
                    _sb_ma.table("cari_kartlar").update({"atanan_kullanici": _ma_toplu_kul}).eq("id", int(_tid)).execute()
                    _basarili += 1
                st.session_state["ma_secili_ids"] = set()
                st.toast(f"✅ {_basarili} müşteri {_ma_toplu_kul}'a atandı!", icon="✅")
                st.rerun()
            except Exception as _mae:
                st.error(f"❌ Hata: {_mae}")

    st.divider()

    # ── LİSTE BAŞLIĞI ─────────────────────────────────────────────────────────
    # ── LİSTE BAŞLIĞI — tıklanabilir sıralama ────────────────────────────────
    st.markdown("""<style>
.ma-satir-wrap{background:white;border:0.5px solid #e2e8f0;border-radius:10px;margin-bottom:5px;padding:8px 4px;}
.ma-firma{font-weight:600;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;padding-top:6px;}
.ma-durum{font-size:10px;padding:3px 8px;border-radius:20px;background:#eff6ff;color:#1d4ed8;white-space:nowrap;display:inline-block;margin-top:4px;}
.ma-hedef{font-size:12px;font-weight:600;color:#16a34a;text-align:right;padding-top:6px;}
.ma-il{font-size:11px;color:#475569;padding-top:6px;}
/* Başlık butonları */
div[data-testid="stHorizontalBlock"]:has(.ma-hdr-marker) button {
    background:none !important; border:none !important;
    font-size:10px !important; font-weight:600 !important;
    color:#64748b !important; padding:4px 0 !important;
    text-transform:uppercase !important; letter-spacing:.3px !important;
    border-radius:0 !important; border-bottom:1.5px solid transparent !important;
}
div[data-testid="stHorizontalBlock"]:has(.ma-hdr-marker) button:hover {
    color:#0f172a !important; border-bottom-color:#2563eb !important;
}
</style>""", unsafe_allow_html=True)

    st.markdown('<span class="ma-hdr-marker" style="display:none"></span>', unsafe_allow_html=True)
    _hc0, _hc1, _hc2, _hc3, _hc4, _hc5, _hc6, _hc7 = st.columns([1, 6, 2, 2, 2, 2, 4, 1])
    _hc0.markdown("")
    if _hc1.button(_ma_sort_btn("firma","FİRMA"), key="ma_hdr_firma", use_container_width=True):
        if st.session_state["ma_sort_col"] == "firma": st.session_state["ma_sort_asc"] = not _sort_asc_val
        else: st.session_state["ma_sort_col"] = "firma"; st.session_state["ma_sort_asc"] = True
        st.rerun()
    if _hc2.button(_ma_sort_btn("durum","DURUM"), key="ma_hdr_durum", use_container_width=True):
        if st.session_state["ma_sort_col"] == "durum": st.session_state["ma_sort_asc"] = not _sort_asc_val
        else: st.session_state["ma_sort_col"] = "durum"; st.session_state["ma_sort_asc"] = True
        st.rerun()
    if _hc3.button(_ma_sort_btn("il","İL"), key="ma_hdr_il", use_container_width=True):
        if st.session_state["ma_sort_col"] == "il": st.session_state["ma_sort_asc"] = not _sort_asc_val
        else: st.session_state["ma_sort_col"] = "il"; st.session_state["ma_sort_asc"] = True
        st.rerun()
    if _hc4.button(_ma_sort_btn("ilce","İLÇE"), key="ma_hdr_ilce", use_container_width=True):
        if st.session_state["ma_sort_col"] == "ilce": st.session_state["ma_sort_asc"] = not _sort_asc_val
        else: st.session_state["ma_sort_col"] = "ilce"; st.session_state["ma_sort_asc"] = True
        st.rerun()
    if _hc5.button(_ma_sort_btn("beklenen_ciro","HEDEF ₺"), key="ma_hdr_hedef", use_container_width=True):
        if st.session_state["ma_sort_col"] == "beklenen_ciro": st.session_state["ma_sort_asc"] = not _sort_asc_val
        else: st.session_state["ma_sort_col"] = "beklenen_ciro"; st.session_state["ma_sort_asc"] = False
        st.rerun()
    if _hc6.button(_ma_sort_btn("atanan_kullanici","ATANAN"), key="ma_hdr_atanan", use_container_width=True):
        if st.session_state["ma_sort_col"] == "atanan_kullanici": st.session_state["ma_sort_asc"] = not _sort_asc_val
        else: st.session_state["ma_sort_col"] = "atanan_kullanici"; st.session_state["ma_sort_asc"] = True
        st.rerun()
    _hc7.markdown("")
    st.markdown("<hr style='margin:4px 0 8px;border-color:#e2e8f0'>", unsafe_allow_html=True)

    # ── SATIRLAR ──────────────────────────────────────────────────────────────
    _opts_atama = ["— Atanmamış —"] + _kul_listesi
    for _idx, _mrow in _df_goster.iterrows():
        _mid     = int(_mrow.get("id",0))
        _mfirma  = str(_mrow.get("firma","") or "")
        _mdurum  = str(_mrow.get("durum","") or "")
        _mil     = str(_mrow.get("il","") or "")
        _milce   = str(_mrow.get("ilce","") or "")
        _mhedef  = float(_mrow.get("beklenen_ciro",0) or 0)
        _matanan = str(_mrow.get("atanan_kullanici","") or "")

        _col_chk, _col_firma, _col_dur, _col_il, _col_ilce, _col_hedef, _col_ata, _col_btn = st.columns([1, 6, 2, 2, 2, 2, 4, 1])

        st.markdown('<span class="ma-chk-marker" style="display:none"></span>', unsafe_allow_html=True)
        _checked = _col_chk.checkbox("", value=_mid in _secili_ids, key=f"ma_chk_{_mid}", label_visibility="collapsed")
        if _checked and _mid not in _secili_ids:
            st.session_state["ma_secili_ids"].add(_mid)
            st.rerun()
        elif not _checked and _mid in _secili_ids:
            st.session_state["ma_secili_ids"].discard(_mid)
            st.rerun()

        _col_firma.markdown(f"<div class='ma-firma' title='{_mfirma}'>{_mfirma}</div>", unsafe_allow_html=True)
        _col_dur.markdown(f"<span class='ma-durum'>{_mdurum}</span>", unsafe_allow_html=True)
        _col_il.markdown(f"<div class='ma-il'>{_mil}</div>", unsafe_allow_html=True)
        _col_ilce.markdown(f"<div class='ma-il'>{_milce}</div>", unsafe_allow_html=True)
        _col_hedef.markdown(f"<div class='ma-hedef'>{int(_mhedef):,}₺</div>" if _mhedef > 0 else "<div class='ma-hedef' style='color:#cbd5e1'>—</div>", unsafe_allow_html=True)

        _secim_idx = 0
        if _matanan and _matanan in _kul_listesi:
            _secim_idx = _kul_listesi.index(_matanan) + 1
        _yeni_atama = _col_ata.selectbox("Kullanıcı", options=_opts_atama, index=_secim_idx, key=f"ma_sec_{_mid}", label_visibility="collapsed")

        if _col_btn.button("💾", key=f"ma_kaydet_{_mid}", help="Kaydet"):
            try:
                _atama_deger = _yeni_atama if _yeni_atama != "— Atanmamış —" else None
                _sb_ma.table("cari_kartlar").update({"atanan_kullanici": _atama_deger}).eq("id", _mid).execute()
                st.toast(f"✅ {_mfirma[:30]} → {_yeni_atama}", icon="✅")
                st.rerun()
            except Exception as _mae2:
                st.error(f"❌ {_mae2}")



# ─────────────────────────────────────────────────────────────────────────────
elif aktif == "rota_analiz":
    sayfa_log("rota_analiz")
    st.markdown("### 🚚 Rota Analiz")

    _RA_ILLER = ["Adana","Adıyaman","Afyonkarahisar","Ağrı","Amasya","Ankara","Antalya","Artvin","Aydın","Balıkesir","Bilecik","Bingöl","Bitlis","Bolu","Burdur","Bursa","Çanakkale","Çankırı","Çorum","Denizli","Diyarbakır","Edirne","Elazığ","Erzincan","Erzurum","Eskişehir","Gaziantep","Giresun","Gümüşhane","Hakkari","Hatay","Isparta","Mersin","İstanbul","İzmir","Kars","Kastamonu","Kayseri","Kırklareli","Kırşehir","Kocaeli","Konya","Kütahya","Malatya","Manisa","Kahramanmaraş","Mardin","Muğla","Muş","Nevşehir","Niğde","Ordu","Rize","Sakarya","Samsun","Siirt","Sinop","Sivas","Tekirdağ","Tokat","Trabzon","Tunceli","Şanlıurfa","Uşak","Van","Yozgat","Zonguldak","Aksaray","Bayburt","Karaman","Kırıkkale","Batman","Şırnak","Bartın","Ardahan","Iğdır","Yalova","Karabük","Kilis","Osmaniye","Düzce"]
    _RA_GENISLIK = [0.5, 2, 1.5, 1.2, 1.2, 1.2, 1.2, 0.8, 0.8, 1, 1.5, 0.5]
    _RA_BASLIKLAR = ["ID","Firma","Yetkili","Tel","Bölge","Çıkış","Varış","Koli","Palet","Toplam ₺","Açıklama",""]

    @st.cache_data(ttl=30)
    def get_rota_analiz():
        sb = get_sb_client()
        if sb:
            try:
                res = sb.table("rota_analiz").select("*").order("id").execute()
                return pd.DataFrame(res.data) if res.data else pd.DataFrame()
            except: pass
        return pd.DataFrame()

    _ra_cariler = _atama_filtresi_uygula(get_cari_listesi())

    with st.expander("➕ Sisteme kayıtlı müşteriyi ekle"):
        if not _ra_cariler.empty:
            _ra_firma_sec = st.selectbox("Müşteri seç", ["-- Seçin --"] + _ra_cariler["firma"].dropna().tolist(), key="ra_firma_sec")
            _ra_aciklama_yeni = st.text_input("Açıklama", key="ra_aciklama_yeni")
            if st.button("Ekle", key="ra_ekle_btn") and _ra_firma_sec != "-- Seçin --":
                _ra_secilen = _ra_cariler[_ra_cariler["firma"] == _ra_firma_sec].iloc[0]
                try:
                    _sb_ra2 = get_sb_client()
                    if _sb_ra2:
                        _sb_ra2.table("rota_analiz").insert({
                            "cari_id": int(_ra_secilen.get("id", 0)),
                            "firma": str(_ra_secilen.get("firma", "")),
                            "yetkili": str(_ra_secilen.get("yetkili", _ra_secilen.get("temsilci", ""))),
                            "tel": str(_ra_secilen.get("gsm", "")),
                            "bolge": str(_ra_secilen.get("il", "")) + (" - " + str(_ra_secilen.get("ilce", "")) if _ra_secilen.get("ilce") else ""),
                            "aciklama": _ra_aciklama_yeni,
                        }).execute()
                        get_rota_analiz.clear()
                        st.success("Eklendi!")
                        st.rerun()
                except Exception as _e_ra:
                    st.error(f"Hata: {_e_ra}")

    _ra_df = get_rota_analiz()
    # Atama filtresi — admin hepsini görür, kullanıcı sadece kendine atananları
    if not _ra_df.empty:
        _ra_atama = _atama_filtresi_uygula(get_cari_listesi())
        if not _ra_atama.empty and "id" in _ra_atama.columns:
            _ra_izinli_ids = set(_ra_atama["id"].astype(int).tolist())
            _ra_df = _ra_df[_ra_df["cari_id"].astype(int).isin(_ra_izinli_ids)]
    if _ra_df.empty:
        st.info("Henüz müşteri eklenmedi. Yukarıdan ekleyin.")
    else:
        _hdr_cols = st.columns(_RA_GENISLIK)
        for _hi, _hl in enumerate(_RA_BASLIKLAR):
            _hdr_cols[_hi].markdown(f"<span style='font-size:11px;color:var(--text-muted);font-weight:500'>{_hl}</span>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:4px 0;border-color:var(--border)'>", unsafe_allow_html=True)

        for _, _mrow in _ra_df.iterrows():
            _ra_id    = int(_mrow.get("id", 0))
            _cari_id  = int(_mrow.get("cari_id", 0))
            _firma    = str(_mrow.get("firma", ""))
            _yetkili  = str(_mrow.get("yetkili", ""))
            _tel      = str(_mrow.get("tel", ""))
            _bolge    = str(_mrow.get("bolge", ""))
            _aciklama = str(_mrow.get("aciklama", ""))

            try:
                _sb_ra3 = get_sb_client()
                _rotalar = []
                if _sb_ra3:
                    _rr = _sb_ra3.table("rota_analiz_detay").select("*").eq("rota_analiz_id", _ra_id).execute()
                    _rotalar = _rr.data if _rr.data else []
            except:
                _rotalar = []

            _toplam = sum(r.get("toplam", 0) or 0 for r in _rotalar)

            for _ri, _r in enumerate(_rotalar):
                _rc = st.columns(_RA_GENISLIK)
                if _ri == 0:
                    _rc[0].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_cari_id}</span>", unsafe_allow_html=True)
                    _rc[1].markdown(f"<span style='font-size:12px;font-weight:500'>{_firma}</span>", unsafe_allow_html=True)
                    _rc[2].markdown(f"<span style='font-size:12px'>{_yetkili}</span>", unsafe_allow_html=True)
                    _rc[3].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_tel}</span>", unsafe_allow_html=True)
                    _rc[4].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_bolge}</span>", unsafe_allow_html=True)
                    _rc[10].markdown(f"<span style='font-size:11px;font-style:italic;color:var(--text-muted)'>{_aciklama}</span>", unsafe_allow_html=True)
                _rc[5].markdown(f"<span style='font-size:12px'>{_r.get('cikis_il','')}</span>", unsafe_allow_html=True)
                _rc[6].markdown(f"<span style='font-size:12px'>{_r.get('varis_il','')}</span>", unsafe_allow_html=True)
                _rc[7].markdown(f"<span style='font-size:12px'>{_r.get('koli','')}</span>", unsafe_allow_html=True)
                _rc[8].markdown(f"<span style='font-size:12px'>{_r.get('palet','')}</span>", unsafe_allow_html=True)
                _rc[9].markdown(f"<span style='font-size:12px;font-weight:500'>{int(_r.get('toplam',0)):,}</span>", unsafe_allow_html=True)
                if _rc[11].button("🗑", key=f"ra_sil_r_{_r.get('id',_ri)}"):
                    try:
                        _sb_ra3.table("rota_analiz_detay").delete().eq("id", int(_r["id"])).execute()
                        get_rota_analiz.clear()
                        st.rerun()
                    except: pass

            # Ekleme satırı
            _add = st.columns(_RA_GENISLIK)
            if len(_rotalar) == 0:
                _add[0].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_cari_id}</span>", unsafe_allow_html=True)
                _add[1].markdown(f"<span style='font-size:12px;font-weight:500'>{_firma}</span>", unsafe_allow_html=True)
                _add[2].markdown(f"<span style='font-size:12px'>{_yetkili}</span>", unsafe_allow_html=True)
                _add[3].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_tel}</span>", unsafe_allow_html=True)
                _add[4].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_bolge}</span>", unsafe_allow_html=True)
                _add[10].markdown(f"<span style='font-size:11px;font-style:italic;color:var(--text-muted)'>{_aciklama}</span>", unsafe_allow_html=True)
            _cikis_il  = _add[5].selectbox("", _RA_ILLER, key=f"ra_cikis_{_ra_id}", label_visibility="collapsed")
            _varis_il  = _add[6].selectbox("", _RA_ILLER, key=f"ra_varis_{_ra_id}", label_visibility="collapsed")
            _koli_v    = _add[7].number_input("", min_value=0, step=1, key=f"ra_koli_{_ra_id}", label_visibility="collapsed")
            _palet_v   = _add[8].number_input("", min_value=0, step=1, key=f"ra_palet_{_ra_id}", label_visibility="collapsed")
            _rtoplam_v = int(_koli_v) + int(_palet_v)
            _add[9].markdown(f"<span style='font-size:12px;font-weight:500;color:var(--text-accent)'>{_rtoplam_v:,}</span>", unsafe_allow_html=True)
            _racik_v   = _add[10].text_input("", key=f"ra_racik_{_ra_id}", label_visibility="collapsed", placeholder="Açıklama")
            if _add[11].button("✅", key=f"ra_ekle_r_{_ra_id}"):
                try:
                    _sb_ra4 = get_sb_client()
                    if _sb_ra4:
                        _sb_ra4.table("rota_analiz_detay").insert({
                            "rota_analiz_id": _ra_id,
                            "cikis_il": _cikis_il,
                            "varis_il": _varis_il,
                            "koli": int(_koli_v),
                            "palet": int(_palet_v),
                            "toplam": _rtoplam_v,
                            "aciklama": _racik_v,
                        }).execute()
                        get_rota_analiz.clear()
                        st.rerun()
                except Exception as _e_ra2:
                    st.error(f"Hata: {_e_ra2}")

            if _rotalar:
                _tot = st.columns(_RA_GENISLIK)
                _tot[9].markdown(f"<span style='font-size:13px;font-weight:500;color:var(--text-accent)'>{int(_toplam):,} ₺</span>", unsafe_allow_html=True)

            st.markdown("<hr style='margin:4px 0;border-color:var(--border)'>", unsafe_allow_html=True)





# ─────────────────────────────────────────────────────────────────────────────
elif aktif == "operasyon":
    sayfa_log("operasyon")

    _op_kul = st.session_state.get("kullanici", "")
    _op_rol = st.session_state.get("rol", "")
    _op_admin = (_op_rol == "admin")

    st.markdown("### 🚛 Operasyon")

    # ── SUPABASE TABLO KONTROL ─────────────────────────────────────────────
    _sb_op = get_sb_client()
    if _sb_op:
        try:
            _sb_op.table("operasyon_ihbar").select("id").limit(1).execute()
        except:
            pass

    # ── VERİ YÜKLEME ──────────────────────────────────────────────────────
    @st.cache_data(ttl=20)
    def get_op_ihbar():
        sb = get_sb_client()
        if sb:
            try:
                res = sb.table("operasyon_ihbar").select("*").neq("arsiv", 1).order("tarih", desc=True).execute()
                return pd.DataFrame(res.data) if res.data else pd.DataFrame()
            except: pass
        return pd.DataFrame()

    _op_cariler = _atama_filtresi_uygula(get_cari_listesi())
    _op_df = get_op_ihbar()

    # Yetki filtresi — admin hepsini, kullanıcı sadece kendinin veya kendine atanmışları görür
    if not _op_df.empty and not _op_admin:
        _op_df = _op_df[
            (_op_df["personel"].astype(str) == _op_kul) |
            (_op_df["gonderen_musteri"].astype(str).isin(
                _op_cariler["firma"].dropna().tolist() if not _op_cariler.empty else []
            ))
        ]

    # ── KARGO TÜRLERİ ─────────────────────────────────────────────────────
    KARGO_TURLERI = ["Koli", "Palet", "Sandık", "Top", "Çuval", "Kasa", "Taban yük", "Üst yük", "Diğer"]

    # ── BAŞLIK ──────────────────────────────────────────────────────────────
    _hdr1, _hdr2 = st.columns([1, 1])
    _hdr1.markdown(
        f"**Alım İhbar Kaydı** — {datetime.now().strftime('%d.%m.%Y')}"
        + (f" — **{len(_op_df)} kayıt**" if not _op_df.empty else "")
    )
    if _op_admin and _hdr2.button("📦 Günü Kapat / Arşivle", key="op_arsiv"):
        try:
            _sb_op2 = get_sb_client()
            if _sb_op2:
                _sb_op2.table("operasyon_ihbar").update({"arsiv": 1}).neq("arsiv", 1).execute()
                get_op_ihbar.clear()
                st.success("✅ Günün tüm kayıtları arşivlendi!")
                st.rerun()
        except Exception as _e: st.error(f"Hata: {_e}")

    st.markdown("---")

    # ── YEŞİL EKLEME SATIRI (EN ÜSTTE HER ZAMAN) ─────────────────────────
    with st.container():
        st.markdown(
            "<div style='background:var(--bg-success);border:1px solid var(--border-success);"
            "border-radius:8px;padding:8px 12px;margin-bottom:8px;'>",
            unsafe_allow_html=True
        )
        _ac1, _ac2, _ac3, _ac4, _ac5, _ac6, _ac7, _ac8, _ac9 = st.columns([1.2,1.2,1,1,1,1.4,1.6,1.2,0.4])

        _op_gonderen_firmalar = ["-- Seçin --"] + (_op_cariler["firma"].dropna().tolist() if not _op_cariler.empty else [])
        _op_alici_firmalar = get_cari_listesi()
        _op_alici_firmalar = _op_alici_firmalar["firma"].dropna().tolist() if not _op_alici_firmalar.empty else []

        _ac1.markdown(f"<span style='font-size:11px;color:var(--text-muted)'>👤 {_op_kul}</span>", unsafe_allow_html=True)
        _ac2.markdown(f"<span style='font-size:11px;color:var(--text-muted)'>🕐 {datetime.now().strftime('%d.%m %H:%M')}</span>", unsafe_allow_html=True)

        _gon_sec = _ac3.selectbox("Gönderen", _op_gonderen_firmalar, key="op_gon_sec", label_visibility="collapsed")
        _gon_sube = _ac4.text_input("G.Şube", key="op_gon_sube", label_visibility="collapsed", placeholder="Gönderen şube")
        _ali_sec = _ac5.selectbox("Alıcı", ["-- Seçin --"] + _op_alici_firmalar, key="op_ali_sec", label_visibility="collapsed")
        _ali_sube = _ac6.text_input("A.Şube", key="op_ali_sube", label_visibility="collapsed", placeholder="Alıcı şube")

        with _ac7:
            _kt1, _kt2, _kt3 = st.columns([1.2, 0.7, 0.7])
            _kargo_tur = _kt1.selectbox("Tür", KARGO_TURLERI, key="op_kargo_tur", label_visibility="collapsed")
            _kargo_adet = _kt2.number_input("Adet", min_value=0, step=1, key="op_kargo_adet", label_visibility="collapsed")
            _kargo_fiyat = _kt3.number_input("₺", min_value=0, step=1, key="op_kargo_fiyat", label_visibility="collapsed")

        _arac_bilgi = _ac8.text_input("Araç/Sürücü/Plaka", key="op_arac", label_visibility="collapsed", placeholder="Plaka · Sürücü · Tel")

        if _ac9.button("✅", key="op_ekle_btn"):
            if _gon_sec == "-- Seçin --" or _ali_sec == "-- Seçin --":
                st.warning("Gönderen ve alıcı seçin!")
            else:
                try:
                    _sb_op3 = get_sb_client()
                    if _sb_op3:
                        _sb_op3.table("operasyon_ihbar").insert({
                            "personel": _op_kul,
                            "tarih": datetime.now().isoformat(),
                            "gonderen_musteri": _gon_sec,
                            "gonderen_sube": _gon_sube,
                            "alici_musteri": _ali_sec,
                            "alici_sube": _ali_sube,
                            "kargo_tur": _kargo_tur,
                            "kargo_adet": int(_kargo_adet),
                            "kargo_fiyat": int(_kargo_fiyat),
                            "arac_bilgi": _arac_bilgi,
                            "arsiv": 0,
                        }).execute()
                        get_op_ihbar.clear()
                        st.success("✅ Kaydedildi!")
                        st.rerun()
                except Exception as _e: st.error(f"Hata: {_e}")

        st.markdown("</div>", unsafe_allow_html=True)

    # ── KAYIT LİSTESİ ─────────────────────────────────────────────────────
    if _op_df.empty:
        st.info("Bugün henüz ihbar kaydı yok.")
    else:
        # Başlıklar
        _bh = st.columns([0.8,0.8,1.5,0.9,1.5,0.9,1.5,1.6,1,0.4])
        for _col, _lbl in zip(_bh, ["Personel","Tarih/Saat","Gönderen","G.Şube","Alıcı","A.Şube","Kargo","Araç/Sürücü","Açıklama",""]):
            _col.markdown(f"<span style='font-size:11px;font-weight:500;color:var(--text-muted)'>{_lbl}</span>", unsafe_allow_html=True)
        st.markdown("<hr style='margin:3px 0 4px;border-color:var(--border)'>", unsafe_allow_html=True)

        _op_toplam = 0
        for _, _row in _op_df.iterrows():
            _rid = int(_row.get("id", 0))
            _rpers = str(_row.get("personel", ""))
            _rtarih = str(_row.get("tarih", ""))[:16].replace("T"," ")
            _rgon = str(_row.get("gonderen_musteri", ""))
            _rgsube = str(_row.get("gonderen_sube", ""))
            _rali = str(_row.get("alici_musteri", ""))
            _rasube = str(_row.get("alici_sube", ""))
            _rtur = str(_row.get("kargo_tur", ""))
            _radet = int(_row.get("kargo_adet", 0) or 0)
            _rfiyat = int(_row.get("kargo_fiyat", 0) or 0)
            _rarac = str(_row.get("arac_bilgi", ""))
            _racik = str(_row.get("aciklama", ""))
            _op_toplam += _rfiyat

            _rc = st.columns([0.8,0.8,1.5,0.9,1.5,0.9,1.5,1.6,1,0.4])
            _rc[0].markdown(f"<span style='font-size:11px'>{_rpers}</span>", unsafe_allow_html=True)
            _rc[1].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_rtarih}</span>", unsafe_allow_html=True)
            _rc[2].markdown(f"<span style='font-size:11px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block'>{_rgon}</span>", unsafe_allow_html=True)
            _rc[3].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_rgsube}</span>", unsafe_allow_html=True)
            _rc[4].markdown(f"<span style='font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block'>{_rali}</span>", unsafe_allow_html=True)
            _rc[5].markdown(f"<span style='font-size:11px;color:var(--text-muted)'>{_rasube}</span>", unsafe_allow_html=True)
            _rc[6].markdown(
                f"<span style='font-size:11px;background:var(--bg-accent);color:var(--text-accent);"
                f"padding:1px 6px;border-radius:4px;'>{_rtur} ×{_radet} — {_rfiyat:,}₺</span>",
                unsafe_allow_html=True
            )
            _rc[7].markdown(f"<span style='font-size:11px;color:var(--text-secondary)'>{_rarac}</span>", unsafe_allow_html=True)
            _rc[8].markdown(f"<span style='font-size:11px;color:var(--text-muted);font-style:italic'>{_racik}</span>", unsafe_allow_html=True)

            # Sil/düzenle sadece kendi kaydı veya admin
            if _op_admin or _rpers == _op_kul:
                if _rc[9].button("🗑", key=f"op_sil_{_rid}"):
                    try:
                        _sb_op4 = get_sb_client()
                        if _sb_op4:
                            _sb_op4.table("operasyon_ihbar").update({"arsiv": 1}).eq("id", _rid).execute()
                            get_op_ihbar.clear()
                            st.rerun()
                    except: pass

            st.markdown("<hr style='margin:2px 0;border-color:var(--border)'>", unsafe_allow_html=True)

        # Toplam
        _tot_cols = st.columns([0.8,0.8,1.5,0.9,1.5,0.9,1.5,1.6,1,0.4])
        _tot_cols[6].markdown(
            f"<span style='font-size:13px;font-weight:500;color:var(--text-accent)'>{_op_toplam:,} ₺</span>",
            unsafe_allow_html=True
        )

    # ── TIR DOLULUK (sadece admin görür) ──────────────────────────────────
    if _op_admin and not _op_df.empty:
        st.markdown("---")
        st.markdown("**🚛 TIR Doluluk Durumu**")

        # Rota bazlı grupla: gonderen_sube → alici_sube
        _rotalar = {}
        for _, _rw in _op_df.iterrows():
            _gs = str(_rw.get("gonderen_sube","")).strip()
            _as = str(_rw.get("alici_sube","")).strip()
            if not _gs or _gs in ["nan","None",""]: _gs = "?"
            if not _as or _as in ["nan","None",""]: _as = "?"
            _rk = f"{_gs}→{_as}"
            if _rk not in _rotalar:
                _rotalar[_rk] = {"palet":0,"koli":0,"taban":False,"label":f"{_gs} → {_as}"}
            _tur = str(_rw.get("kargo_tur",""))
            _adet = int(_rw.get("kargo_adet",0) or 0)
            if _tur=="Palet": _rotalar[_rk]["palet"] += _adet
            elif _tur=="Koli": _rotalar[_rk]["koli"] += _adet
            elif _tur=="Taban yük": _rotalar[_rk]["taban"] = True
            elif _tur in ["Sandık","Top","Çuval","Kasa"]: _rotalar[_rk]["koli"] += _adet

        def _tir_svg_kart(palet, koli, taban, label):
            P = min(palet, 11)
            K = min(koli, 22)
            pp = min(int(palet/33*100),100)
            pk = min(int(koli/500*100),100)
            badge_p = f'<span style="background:#1050a8;color:#d0e0ff;padding:1px 7px;border-radius:3px;font-size:10px;font-family:sans-serif;">{palet}/33 palet</span>'
            badge_k = f'<span style="background:#7a3808;color:#ffe0c0;padding:1px 7px;border-radius:3px;font-size:10px;font-family:sans-serif;">{koli}/500 koli</span>'
            badge_t = '<span style="background:#2a3848;color:#b0c8e0;padding:1px 7px;border-radius:3px;font-size:10px;font-family:sans-serif;">Taban</span>' if taban else ""

            # TABAN YUK
            tb = '<rect x="73" y="58" width="216" height="5" fill="#2a3848"/>' if taban else ""

            # PALETLER — y=49..63, 11 slot, pitch=20
            ps = ""
            for i in range(11):
                x = 73 + i*20
                if i < P:
                    ps += f'<rect x="{x}" y="49" width="18" height="14" fill="#c8a028"/><rect x="{x}" y="49" width="18" height="3" fill="#f0d050"/><rect x="{x}" y="60" width="18" height="3" fill="#f0d050"/><rect x="{x+3}" y="52" width="3" height="7" fill="#7a5810"/><rect x="{x+8}" y="52" width="3" height="7" fill="#7a5810"/><rect x="{x+13}" y="52" width="3" height="7" fill="#7a5810"/>'
                else:
                    ps += f'<rect x="{x}" y="49" width="18" height="14" fill="none" stroke="#a8a49c" stroke-width="0.6" stroke-dasharray="3,2"/>'

            # KOLİLER — y=37..49, palet basina 2 koli, pitch=10
            ks = ""
            ki = 0
            for i in range(11):
                x = 73 + i*20
                for j in range(2):
                    kx = x + j*10
                    if ki < K:
                        ks += f'<rect x="{kx}" y="37" width="9" height="12" fill="#d09848"/><rect x="{kx}" y="37" width="9" height="2" fill="#f0c060"/>'
                    ki += 1

            return f"""<div style="flex:1;min-width:200px;max-width:320px;border:0.5px solid var(--border);border-radius:10px;padding:8px;background:var(--surface-1);">
<div style="font-size:11px;font-weight:500;color:var(--text-primary);margin-bottom:5px;font-family:sans-serif;">🚛 {label}</div>
<svg viewBox="0 0 300 95" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block;">
<rect x="0" y="0" width="300" height="72" fill="#a8c8e8"/>
<ellipse cx="255" cy="10" rx="18" ry="6" fill="white" opacity="0.6"/>
<ellipse cx="38" cy="15" rx="13" ry="5" fill="white" opacity="0.55"/>
<rect x="0" y="72" width="300" height="23" fill="#383634"/>
<rect x="0" y="72" width="300" height="2" fill="#4c4a48"/>
<rect x="8" y="78" width="16" height="2" rx="1" fill="#c8b820" opacity="0.7"/>
<rect x="50" y="78" width="16" height="2" rx="1" fill="#c8b820" opacity="0.7"/>
<rect x="92" y="78" width="16" height="2" rx="1" fill="#c8b820" opacity="0.7"/>
<rect x="134" y="78" width="16" height="2" rx="1" fill="#c8b820" opacity="0.7"/>
<rect x="176" y="78" width="16" height="2" rx="1" fill="#c8b820" opacity="0.7"/>
<rect x="218" y="78" width="16" height="2" rx="1" fill="#c8b820" opacity="0.7"/>
<rect x="260" y="78" width="16" height="2" rx="1" fill="#c8b820" opacity="0.7"/>
<ellipse cx="165" cy="74" rx="138" ry="3" fill="rgba(0,0,0,0.1)"/>
<rect x="2" y="16" width="2.5" height="14" rx="1" fill="#585858"/>
<path d="M9,26 Q13,9 19,7 L50,7 Q53,7 53,11 L53,26 Z" fill="#183878" stroke="#0c1838" stroke-width="0.8"/>
<rect x="9" y="26" width="44" height="37" rx="2" fill="#183878" stroke="#0c1838" stroke-width="1"/>
<rect x="10" y="28" width="40" height="18" rx="1" fill="#5080b8" stroke="#0c1838" stroke-width="0.8"/>
<rect x="11" y="29" width="38" height="16" rx="1" fill="#6090c8"/>
<line x1="13" y1="30" x2="15" y2="45" stroke="#a0c8e8" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
<line x1="34" y1="44" x2="47" y2="36" stroke="#081020" stroke-width="1" stroke-linecap="round"/>
<rect x="9" y="46" width="44" height="15" fill="#112868"/>
<rect x="10" y="48" width="18" height="7" rx="1" fill="#040810"/>
<rect x="30" y="48" width="20" height="7" rx="2" fill="#a88018"/>
<text x="40" y="54" font-size="4" font-weight="bold" fill="#100800" text-anchor="middle" font-family="sans-serif">MW</text>
<rect x="9" y="60" width="44" height="3" rx="1" fill="#060808"/>
<rect x="3" y="43" width="4" height="7" rx="1" fill="#f0f0c0"/>
<rect x="3" y="50" width="4" height="3" rx="1" fill="#f08080"/>
<rect x="3" y="34" width="3" height="6" rx="1" fill="#181818"/>
<rect x="62" y="59" width="8" height="3" rx="1" fill="#282828"/>
<circle cx="17" cy="76" r="8" fill="#111" stroke="#2a2a2a" stroke-width="1"/><circle cx="17" cy="76" r="5" fill="#0e0e0e"/><circle cx="17" cy="76" r="2.5" fill="#505050"/><circle cx="17" cy="76" r="1" fill="#888"/><circle cx="17" cy="76" r="7.5" fill="none" stroke="#080808" stroke-width="2" stroke-dasharray="3.5,3"/><line x1="17" y1="68" x2="17" y2="84" stroke="#333" stroke-width="1"/><line x1="9" y1="76" x2="25" y2="76" stroke="#333" stroke-width="1"/>
<circle cx="38" cy="76" r="8" fill="#111" stroke="#2a2a2a" stroke-width="1"/><circle cx="38" cy="76" r="5" fill="#0e0e0e"/><circle cx="38" cy="76" r="2.5" fill="#505050"/><circle cx="38" cy="76" r="1" fill="#888"/><circle cx="38" cy="76" r="7.5" fill="none" stroke="#080808" stroke-width="2" stroke-dasharray="3.5,3"/><line x1="38" y1="68" x2="38" y2="84" stroke="#333" stroke-width="1"/><line x1="30" y1="76" x2="46" y2="76" stroke="#333" stroke-width="1"/>
<circle cx="48" cy="76" r="8" fill="#090909" stroke="#181818" stroke-width="0.7"/><circle cx="48" cy="76" r="5" fill="#0c0c0c"/><circle cx="48" cy="76" r="2.5" fill="#404040"/>
<rect x="70" y="62" width="226" height="5" rx="1" fill="#101010"/>
<rect x="70" y="18" width="226" height="3" rx="1" fill="#888480"/>
<rect x="70" y="21" width="226" height="5" rx="1" fill="#989490"/>
<rect x="71" y="26" width="221" height="37" rx="2" fill="#ccc8c0"/>
{tb}
{ps}
{ks}
<rect x="71" y="26" width="221" height="37" rx="2" fill="none" stroke="#787470" stroke-width="1.2"/>
<rect x="71" y="26" width="221" height="4" fill="#b0aca4"/>
<rect x="71" y="62" width="221" height="3" fill="#b08820"/>
<rect x="289" y="26" width="5" height="37" fill="#686460"/>
<line x1="291" y1="26" x2="291" y2="63" stroke="#484440" stroke-width="1" stroke-dasharray="4,3"/>
<line x1="73" y1="47" x2="289" y2="47" stroke="#a8a49c" stroke-width="0.4" stroke-dasharray="4,4"/>
<circle cx="115" cy="76" r="8" fill="#111" stroke="#2a2a2a" stroke-width="1"/><circle cx="115" cy="76" r="5" fill="#0e0e0e"/><circle cx="115" cy="76" r="2.5" fill="#505050"/><circle cx="115" cy="76" r="1" fill="#888"/><circle cx="115" cy="76" r="7.5" fill="none" stroke="#080808" stroke-width="2" stroke-dasharray="3.5,3"/><line x1="115" y1="68" x2="115" y2="84" stroke="#333" stroke-width="1"/><line x1="107" y1="76" x2="123" y2="76" stroke="#333" stroke-width="1"/>
<circle cx="124" cy="76" r="8" fill="#090909" stroke="#181818" stroke-width="0.7"/><circle cx="124" cy="76" r="5" fill="#0c0c0c"/><circle cx="124" cy="76" r="2.5" fill="#404040"/>
<circle cx="185" cy="76" r="8" fill="#111" stroke="#2a2a2a" stroke-width="1"/><circle cx="185" cy="76" r="5" fill="#0e0e0e"/><circle cx="185" cy="76" r="2.5" fill="#505050"/><circle cx="185" cy="76" r="1" fill="#888"/><circle cx="185" cy="76" r="7.5" fill="none" stroke="#080808" stroke-width="2" stroke-dasharray="3.5,3"/><line x1="185" y1="68" x2="185" y2="84" stroke="#333" stroke-width="1"/><line x1="177" y1="76" x2="193" y2="76" stroke="#333" stroke-width="1"/>
<circle cx="194" cy="76" r="8" fill="#090909" stroke="#181818" stroke-width="0.7"/><circle cx="194" cy="76" r="5" fill="#0c0c0c"/><circle cx="194" cy="76" r="2.5" fill="#404040"/>
<circle cx="250" cy="76" r="8" fill="#111" stroke="#2a2a2a" stroke-width="1"/><circle cx="250" cy="76" r="5" fill="#0e0e0e"/><circle cx="250" cy="76" r="2.5" fill="#505050"/><circle cx="250" cy="76" r="1" fill="#888"/><circle cx="250" cy="76" r="7.5" fill="none" stroke="#080808" stroke-width="2" stroke-dasharray="3.5,3"/><line x1="250" y1="68" x2="250" y2="84" stroke="#333" stroke-width="1"/><line x1="242" y1="76" x2="258" y2="76" stroke="#333" stroke-width="1"/>
<circle cx="259" cy="76" r="8" fill="#090909" stroke="#181818" stroke-width="0.7"/><circle cx="259" cy="76" r="5" fill="#0c0c0c"/><circle cx="259" cy="76" r="2.5" fill="#404040"/>
</svg>
<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:5px;">{badge_p} {badge_k} {badge_t}</div>
<div style="margin-top:4px;">
<div style="height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin-bottom:3px;"><div style="height:100%;width:{pp}%;background:#1050a8;border-radius:2px;"></div></div>
<div style="height:3px;background:var(--border);border-radius:2px;overflow:hidden;"><div style="height:100%;width:{pk}%;background:#7a3808;border-radius:2px;"></div></div>
</div>
</div>"""

        if _rotalar:
            _html_parts = []
            for _rk, _rd in _rotalar.items():
                _html_parts.append(_tir_svg_kart(_rd["palet"], _rd["koli"], _rd["taban"], _rd["label"]))
            st.markdown(
                '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start;">' + "".join(_html_parts) + '</div>',
                unsafe_allow_html=True
            )

    # ── SUPABASE SQL ───────────────────────────────────────────────────────




# ── İŞLEM TAKİP ───────────────────────────────────────────────────────────────
elif aktif == "islem_takip":
    sayfa_log("islem_takip")
    # Cache temizle — her açılışta taze veri
    if not st.session_state.get("_it_cache_cleared"):
        st.cache_data.clear()
        st.session_state["_it_cache_cleared"] = True

    _it_kul   = st.session_state.get("kullanici","")
    _it_rol   = st.session_state.get("rol","")
    _it_admin = (_it_rol == "admin")

    st.markdown("## 📋 İşlem Takip")

    _sb_it = get_sb_client()

    # ── VERİ ÇEK ─────────────────────────────────────────────────────────────
    try:
        _r1 = _sb_it.table("cari_aciklamalar").select("*").order("tarih", desc=False).execute()
        _df_acik = pd.DataFrame(_r1.data) if _r1.data else pd.DataFrame()
    except: _df_acik = pd.DataFrame()

    try:
        _r2 = _sb_it.table("randevular").select("*").order("randevu_tarihi", desc=False).execute()
        _df_rdv = pd.DataFrame(_r2.data) if _r2.data else pd.DataFrame()
    except: _df_rdv = pd.DataFrame()

    try:
        _r3 = _sb_it.table("teklifler").select("*").order("tarih", desc=False).execute()
        _df_tek3 = pd.DataFrame(_r3.data) if _r3.data else pd.DataFrame()
    except: _df_tek3 = pd.DataFrame()

    _it_cariler = get_cari_listesi()
    _it_cari_map = {}
    if not _it_cariler.empty:
        for _, _cr in _it_cariler.iterrows():
            _info = {
                "firma":    str(_cr.get("firma","") or ""),
                "yetkili":  str(_cr.get("yetkili","") or ""),
                "gsm":      str(_cr.get("gsm","") or ""),
                "il":       str(_cr.get("il","") or ""),
                "ilce":     str(_cr.get("ilce","") or ""),
                "durum":    str(_cr.get("durum","") or ""),
                "asama":    str(_cr.get("islem_asamasi","") or ""),
                "beklenen": _cr.get("beklenen_ciro", 0) or 0,
            }
            _it_cari_map[str(_cr.get("id",""))] = _info
            _it_cari_map[str(_cr.get("firma",""))] = _info

    # ── İŞLEMLERİ TOPLA ──────────────────────────────────────────────────────
    _it_islemler = []

    def _it_firma_bul(row, id_col, ad_col):
        _cid = str(row.get(id_col,"") or "")
        _ad  = str(row.get(ad_col,"") or "")
        if _ad and _ad not in ["nan","None",""]: return _ad, _cid
        if _cid and _cid in _it_cari_map: return _it_cari_map[_cid]["firma"], _cid
        return "", _cid

    # Notlar
    if not _df_acik.empty:
        for _, _r in _df_acik.iterrows():
            _kul = str(_r.get("olusturan","") or "")
            if not _it_admin and _kul != _it_kul: continue
            _firma, _cid = _it_firma_bul(_r, "cari_id", "cari_adi")
            _tarih = str(_r.get("tarih","") or "")[:10]
            _acik  = str(_r.get("aciklama","") or "")[:120]
            _a = _acik.lower()
            if "arama" in _a or "arandı" in _a: _tur = "Arama"
            elif "mesaj" in _a or "whatsapp" in _a: _tur = "Mesaj"
            elif "teklif" in _a: _tur = "Teklif"
            elif "randevu" in _a: _tur = "Randevu"
            else: _tur = "Not"
            if _firma and _tarih and _tarih not in ["","nan","None"]:
                _it_islemler.append({"id":str(_r.get("id","")), "firma":_firma,"cid":_cid,"tarih":_tarih,"tur":_tur,"aciklama":_acik,"kul":_kul,"kaynak":"not"})

    # Randevular
    if not _df_rdv.empty:
        for _, _r in _df_rdv.iterrows():
            _kul = str(_r.get("olusturan","") or _r.get("temsilci","") or "")
            if not _it_admin and _kul != _it_kul: continue
            _firma, _cid = _it_firma_bul(_r, "musteri_id", "musteri_adi")
            _tarih = str(_r.get("tarih","") or "")[:10]
            _rdv_t = str(_r.get("randevu_tarihi","") or "")[:10]
            if _firma and _tarih and _tarih not in ["","nan","None"]:
                _it_islemler.append({"id":str(_r.get("id","")), "firma":_firma,"cid":_cid,"tarih":_tarih,"tur":"Randevu","aciklama":f"Randevu: {_rdv_t}","kul":_kul,"kaynak":"randevu"})

    # Teklifler — mükerrer önle
    _not_firma_tarih = {(_i["firma"],_i["tarih"]) for _i in _it_islemler if _i["tur"]=="Teklif"}
    if not _df_tek3.empty:
        for _, _r in _df_tek3.iterrows():
            _kul = str(_r.get("olusturan","") or "")
            if not _it_admin and _kul != _it_kul: continue
            _firma, _cid = _it_firma_bul(_r, "musteri_id", "musteri_adi")
            _tarih = str(_r.get("tarih","") or "")[:10]
            if _firma and _tarih and (_firma,_tarih) not in _not_firma_tarih and _tarih not in ["","nan","None"]:
                _it_islemler.append({"id":str(_r.get("id","")), "firma":_firma,"cid":_cid,"tarih":_tarih,"tur":"Teklif","aciklama":"Teklif oluşturuldu","kul":_kul,"kaynak":"teklif"})

    if not _it_islemler:
        st.info("Henüz kayıtlı işlem bulunamadı.")
        st.stop()

    # ── MÜŞTERİ BAZINDA GRUPLA ────────────────────────────────────────────────
    _it_gruplu = {}
    for _ism in _it_islemler:
        _f = _ism["firma"]
        if not _f or _f in ["","nan","None"]: continue
        if _f not in _it_gruplu: _it_gruplu[_f] = []
        _it_gruplu[_f].append(_ism)

    for _f in _it_gruplu:
        # Mükerrer kaldır — aynı tarih+tur+aciklama
        _seen = set()
        _uniq = []
        for _ism in _it_gruplu[_f]:
            _key = (_ism["tarih"], _ism["tur"], _ism["aciklama"][:50])
            if _key not in _seen:
                _seen.add(_key)
                _uniq.append(_ism)
        _it_gruplu[_f] = sorted(_uniq, key=lambda x: x["tarih"])

    # En çok işlem yapılan üstte
    _it_sirali = sorted(_it_gruplu.items(), key=lambda x: len(x[1]), reverse=True)

    # ── YARDIMCILAR ──────────────────────────────────────────────────────────
    def _it_ikon(tur):
        t = str(tur).lower()
        if "arama" in t: return "📞"
        if "mesaj" in t or "whatsapp" in t: return "💬"
        if "teklif" in t: return "📄"
        if "randevu" in t: return "📅"
        if "analiz" in t: return "🔍"
        if "email" in t: return "✉️"
        return "📝"

    def _it_asama(firma):
        _ci = _it_cari_map.get(firma, {})
        if not isinstance(_ci, dict): return ""
        _as = _ci.get("asama","") or _ci.get("durum","")
        return str(_as) if _as and str(_as) not in ["","nan","None"] else ""

    def _it_badge(firma):
        _ci = _it_cari_map.get(firma, {})
        if not isinstance(_ci, dict): return ""
        _d = str(_ci.get("durum","")).lower()
        if "özel" in _d or "ozel" in _d: return "<span style='font-size:9px;padding:1px 6px;border-radius:8px;background:#ede9fe;color:#6d28d9;'>Özel Müşteri</span>"
        if "portf" in _d: return "<span style='font-size:9px;padding:1px 6px;border-radius:8px;background:#dbeafe;color:#1d4ed8;'>Portföy</span>"
        if "teklif" in _d: return "<span style='font-size:9px;padding:1px 6px;border-radius:8px;background:#fef3c7;color:#92400e;'>Teklif</span>"
        if "kazan" in _d: return "<span style='font-size:9px;padding:1px 6px;border-radius:8px;background:#dcfce7;color:#166534;'>Kazanıldı</span>"
        if "negatif" in _d: return "<span style='font-size:9px;padding:1px 6px;border-radius:8px;background:#fee2e2;color:#991b1b;'>Negatif</span>"
        return ""

    # ── FİLTRE ───────────────────────────────────────────────────────────────
    _it_ara = st.text_input("", placeholder="🔍 Firma ara...", key="it_ara", label_visibility="collapsed")
    if _it_ara:
        _it_sirali = [(f,i) for f,i in _it_sirali if _it_ara.lower() in f.lower()]
    st.caption(f"{len(_it_sirali)} müşteri · toplam {sum(len(i) for _,i in _it_sirali)} işlem")

    # ── EXCEL İNDİR ─────────────────────────────────────────────────────────
    try:
        import io as _io2
        _xl_rows = []
        for _fxl, _ixl in _it_sirali:
            for _ism in _ixl:
                _ci2 = _it_cari_map.get(_fxl, {})
                _xl_rows.append({
                    "Firma": _fxl,
                    "Yetkili": _ci2.get("yetkili","") if isinstance(_ci2,dict) else "",
                    "İl": _ci2.get("il","") if isinstance(_ci2,dict) else "",
                    "Beklenen ₺": _ci2.get("beklenen",0) if isinstance(_ci2,dict) else 0,
                    "Aşama": _it_asama(_fxl),
                    "Tarih": _ism["tarih"],
                    "İşlem Türü": _ism["tur"],
                    "Açıklama": _ism["aciklama"],
                    "Kullanıcı": _ism.get("kul",""),
                })
        _xl_df2 = pd.DataFrame(_xl_rows)
        _xl_buf2 = _io2.BytesIO()
        _xl_df2.to_excel(_xl_buf2, index=False, engine="openpyxl")
        _xl_buf2.seek(0)
        st.download_button("📥 Excel İndir", _xl_buf2, "islem_takip.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="it_excel_indir")
    except: pass

    # ── LİSTE RENDER ─────────────────────────────────────────────────────────
    _sb_islem = get_sb_client()
    for _firma, _islemler in _it_sirali:
        _ci = _it_cari_map.get(_firma, {})
        _yt  = _ci.get("yetkili","") if isinstance(_ci,dict) else ""
        _il  = _ci.get("il","") if isinstance(_ci,dict) else ""
        _ilc = _ci.get("ilce","") if isinstance(_ci,dict) else ""
        _bk  = _ci.get("beklenen",0) if isinstance(_ci,dict) else 0
        try: _bk_f = f"{int(float(_bk)):,}".replace(",",".") + " ₺" if float(_bk)>0 else ""
        except: _bk_f = ""
        _as  = _it_asama(_firma)
        _bdg = _it_badge(_firma)
        _loc = " · ".join(x for x in [_yt,_il,_ilc] if x and x not in ["nan","None",""])

        # Mükerrer tespit
        _muk_sayac = {}
        for _ism in _islemler:
            _mk = (_ism["tarih"], _ism["tur"])
            _muk_sayac[_mk] = _muk_sayac.get(_mk, 0) + 1

        # Firma başlığı
        _hdr_html = f"""<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;
            padding:9px 14px;background:#f8fafc;border:0.5px solid #e2e8f0;
            border-radius:10px 10px 0 0;margin-top:12px;">
            <span style="font-size:13px;font-weight:600;color:#0f172a;">{_firma}</span>
            <span style="font-size:9px;padding:2px 8px;border-radius:10px;background:#dbeafe;color:#1d4ed8;">{len(_islemler)} işlem</span>
            {"<span style='font-size:11px;font-weight:500;color:#16a34a;'>"+_bk_f+"</span>" if _bk_f else ""}
            {_bdg}
            {"<span style='font-size:10px;color:#94a3b8;'>"+_loc+"</span>" if _loc else ""}
            {"<span style='margin-left:auto;font-size:11px;font-weight:500;color:#334155;'>"+_as+"</span>" if _as else ""}
        </div>
        <div style="border:0.5px solid #e2e8f0;border-top:none;border-radius:0 0 10px 10px;margin-bottom:0;">"""
        st.markdown(_hdr_html, unsafe_allow_html=True)

        # İşlem satırları
        for _ism in _islemler:
            _ikon = _it_ikon(_ism["tur"])
            _acik = _ism["aciklama"][:150] + ("..." if len(_ism["aciklama"])>150 else "")
            _arsiv = str(_ism.get("arsiv","")).lower() in ["1","true","yes"]
            _nid = str(_ism.get("id",""))
            _kaynak = _ism.get("kaynak","not")
            _is_muk = _muk_sayac.get((_ism["tarih"], _ism["tur"]),0) > 1
            _row_bg = "background:rgba(251,191,36,0.07);" if _is_muk else ""
            _opacity = "opacity:0.4;" if _arsiv else ""

            if _nid and _nid not in ["","None","nan"]:
                _c1,_c2,_c3,_c4,_c5 = st.columns([1.1,1,5.5,0.6,0.6])
            else:
                _c1,_c2,_c3 = st.columns([1.1,1,7.1])
                _c4=_c5=None

            _c1.markdown(f"<div style='font-size:10px;color:#94a3b8;padding:4px 0;{_opacity}{_row_bg}'>{_ism['tarih']}</div>", unsafe_allow_html=True)
            _muk_tag = " <span style='font-size:8px;padding:1px 4px;background:#fef3c7;color:#92400e;border-radius:3px;'>mükerrer</span>" if _is_muk else ""
            _c2.markdown(f"<div style='font-size:10px;font-weight:500;color:#1e293b;padding:4px 0;{_opacity}'>{_ikon} {_ism['tur']}{_muk_tag}</div>", unsafe_allow_html=True)
            _c3.markdown(f"<div style='font-size:11px;color:#475569;padding:4px 0;line-height:1.5;{_opacity}'>{_acik}</div>", unsafe_allow_html=True)

            if _c4 and _c5:
                if not _arsiv and _kaynak == "not":
                    if _c4.button("📦", key=f"it_arsiv_{_kaynak}_{_nid}_{_firma[:6]}", help="Arşivle"):
                        try:
                            if _sb_islem:
                                _sb_islem.table("cari_aciklamalar").update({"arsiv": True}).eq("id", int(_nid)).execute()
                                st.cache_data.clear(); st.rerun()
                        except: pass
                if _c5.button("🗑", key=f"it_sil_{_kaynak}_{_nid}_{_firma[:6]}", help="Sil"):
                    try:
                        if _sb_islem:
                            _tbl = {"randevu":"randevular","teklif":"teklifler"}.get(_kaynak,"cari_aciklamalar")
                            _sb_islem.table(_tbl).delete().eq("id", int(_nid)).execute()
                            st.cache_data.clear(); st.rerun()
                    except: pass

        # Not ekle butonu
        _cid_f = _islemler[0].get("cid","") if _islemler else ""
        _nk = f"it_not_ac_{_firma[:20]}"
        _na1, _na2 = st.columns([8,2])
        if _na2.button("✏️ not ekle", key=f"it_not_btn_{_firma[:20]}"):
            st.session_state[_nk] = not st.session_state.get(_nk, False)
        if st.session_state.get(_nk, False):
            _yeni = st.text_area("", key=f"it_not_txt_{_firma[:20]}", placeholder="Not yaz...", height=60, label_visibility="collapsed")
            if st.button("Kaydet", key=f"it_not_sv_{_firma[:20]}", type="primary"):
                if _yeni and _yeni.strip():
                    try:
                        if _sb_islem:
                            _sb_islem.table("cari_aciklamalar").insert({
                                "cari_id": int(_cid_f) if str(_cid_f).isdigit() else 0,
                                "cari_adi": _firma,
                                "aciklama": _yeni.strip(),
                                "olusturan": st.session_state.get("kullanici",""),
                            }).execute()
                            st.success("✅ Eklendi!")
                            st.session_state[_nk] = False
                            st.cache_data.clear(); st.rerun()
                    except Exception as _ne: st.error(f"Hata: {_ne}")
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)



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
        _hc1,_hc2,_hc3 = st.columns(3)
        _h_durum = _hc1.multiselect("Durum filtrele", sorted(_hdf["durum"].dropna().unique().tolist()) if "durum" in _hdf.columns else [], key="h_durum")
        _h_seg   = _hc2.multiselect("Segment", sorted(_hdf["segment"].dropna().unique().tolist()) if "segment" in _hdf.columns else [], key="h_seg")
        _h_tem   = _hc3.multiselect("Temsilci", sorted(_hdf["temsilci"].dropna().unique().tolist()) if "temsilci" in _hdf.columns else [], key="h_tem")
        _hdf_f = _hdf.copy()
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
            "Aktif":"#15803d","Negatif Portföy":"#dc2626","Kazanıldı":"#16a34a",
        }
        def _tr_lower(s):
            """Türkçe karakterleri doğru küçült"""
            return (s.replace("İ","i").replace("I","ı").replace("Ş","ş")
                     .replace("Ğ","ğ").replace("Ü","ü").replace("Ö","ö")
                     .replace("Ç","ç").lower().strip())

        _gorulen_firmalar = set()
        _pins = []
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
            _adrs = str(_hr.get("adres","") or "—").replace("'","&#39;").replace('"','&quot;')
            _lat, _lng = None, None
            # Önce ilçe — tam eşleşme
            if _ilce:
                if _ilce in _ILCE_KOOR:
                    _lat, _lng = _ILCE_KOOR[_ilce]
                else:
                    for _k in _ILCE_KOOR:
                        if _tr_lower(_k) == _ilce:
                            _lat, _lng = _ILCE_KOOR[_k]; break
            # Sonra il — tam eşleşme
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
                "adres":_adrs,"rand":_rand_etiketi})

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
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap',maxZoom:18}).addTo(map);
var cl = L.markerClusterGroup({maxClusterRadius:50,spiderfyOnMaxZoom:true,showCoverageOnHover:false});
var rnk={};
pins.forEach(function(p){
  rnk[p.durum]=p.renk;
  var svg='<svg xmlns="http://www.w3.org/2000/svg" width="24" height="32" viewBox="0 0 24 32">'
    +'<path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 20 12 20s12-11 12-20C24 5.4 18.6 0 12 0z" fill="'+p.renk+'" stroke="white" stroke-width="1.5"/>'
    +'<circle cx="12" cy="12" r="5" fill="white" opacity="0.9"/></svg>';
  var ic=L.divIcon({html:svg,className:'',iconSize:[24,32],iconAnchor:[12,32],popupAnchor:[0,-30]});
  var pop='<div class="pp"><h4>'+p.firma+(p.rand?' <span style="font-size:11px;color:#dc2626">'+p.rand+'</span>':'')+'</h4><table>'
    +'<tr><td>İl/İlçe</td><td>'+p.il+(p.ilce?' / '+p.ilce:'')+'</td></tr>'
    +'<tr><td>Adres</td><td>'+p.adres+'</td></tr>'
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
            st.markdown("**📊 İl / İlçe Bazlı Özet**")
            _grp_cols = [c for c in [_il_col, "ilce"] if c in _hdf_f.columns]
            _il_g = (_hdf_f.groupby(_grp_cols).size()
                     .reset_index(name="Müşteri Sayısı")
                     .sort_values(["Müşteri Sayısı"] + _grp_cols[:1], ascending=[False, True])
                     .head(50))
            st.dataframe(_il_g, use_container_width=True, hide_index=True)

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