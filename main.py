import streamlit as st
import sqlite3
import pandas as pd
import shutil
import os
import io
import re
import json
from datetime import datetime

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
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL","")
        key = st.secrets.get("SUPABASE_KEY","")
        if url and key:
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
        if s.endswith(".0"):
            s = s[:-2]
        return s
    return seri.apply(_tek)

@st.cache_data(ttl=60)
def get_cari_listesi():
    """60 sn cache'li cari listesi"""
    sb = get_sb_client()
    if sb:
        try:
            res = sb.table("cari_kartlar").select("*").neq("silindi",1).order("firma").execute()
            _df_g = pd.DataFrame(res.data) if res.data else pd.DataFrame()
            if not _df_g.empty:
                for _tk in ["gsm","sabit"]:
                    if _tk in _df_g.columns:
                        _df_g[_tk] = _telefon_temizle(_df_g[_tk])
            return _df_g
        except: pass
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
            pass  # SQLite fallback
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
    """Insert — Supabase önce, SQLite fallback"""
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


def _tanimlar_yukle(tip):
    """sistem_tanimlar tablosundan aşama/durum listesi çek
    + cari_kartlar'daki eksik değerleri otomatik ekle"""
    _sb = get_sb_client()
    _liste = []
    try:
        if _sb:
            _r = _sb.table("sistem_tanimlar").select("deger").eq("tip", tip).order("sira").execute()
            if _r.data:
                _liste = [d["deger"] for d in _r.data]
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
        return _liste

    # Fallback
    if tip == "asama":
        return ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]
    return ["Aktif","Hedef","Pasif"]

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
    st.markdown("<h1 style='text-align:center;color:#1f6feb;'>🏢 MWCRMPRO</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align:center;color:#888;'>Cari Yönetim Sistemi</h4><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("giris_form"):
            st.subheader("Giriş Yap")
            kullanici = st.text_input("Kullanıcı Adı")
            sifre = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap", use_container_width=True):
                row = None

                # 1. Supabase ile dene
                try:
                    from supabase import create_client
                    url = st.secrets.get("SUPABASE_URL","")
                    key = st.secrets.get("SUPABASE_KEY","")
                    if url and key:
                        sb = create_client(url, key)
                        res = sb.table("kullanicilar").select("*").eq("kullanici_adi", kullanici).eq("sifre", sifre).execute()
                        if res.data:
                            row = res.data[0]
                except Exception as e:
                    pass

                # 2. SQLite fallback
                if row is None:
                    try:
                        conn = get_conn()
                        r = conn.execute(
                            "SELECT * FROM kullanicilar WHERE kullanici_adi=? AND sifre=?",
                            (kullanici, sifre)).fetchone()
                        conn.close()
                        if r:
                            row = {"kullanici_adi": r[1], "sifre": r[2], "rol": r[3]}
                    except:
                        pass

                # 3. Hardcoded admin (son çare)
                if row is None and kullanici == "admin" and sifre == "admin123":
                    row = {"kullanici_adi": "admin", "sifre": "admin123", "rol": "admin"}

                if row:
                    st.session_state["giris"] = True
                    st.session_state["kullanici"] = kullanici
                    # Rol belirle
                    if isinstance(row, dict):
                        rol_val = str(row.get("rol") or "")
                    else:
                        rol_val = ""
                    if not rol_val or rol_val == "None":
                        rol_val = "admin" if kullanici == "admin" else "kullanici"
                    st.session_state["rol"] = rol_val
                    st.session_state["aktif_tab"] = "liste"
                    # Yetki listesini yükle
                    try:
                        import json as _yjson
                        _yetki_val = str(row.get("yetkiler","tam") or "tam")
                        if _yetki_val == "tam":
                            st.session_state["_yetki_listesi"] = "tam"
                        else:
                            st.session_state["_yetki_listesi"] = _yjson.loads(_yetki_val)
                    except:
                        st.session_state["_yetki_listesi"] = "tam"
                    # Giriş logla
                    try:
                        _sb_logi = get_sb_client()
                        if _sb_logi:
                            _sb_logi.table("kullanici_log").insert({
                                "kullanici": kullanici,
                                "rol": rol_val,
                                "sayfa": "giris",
                                "islem": "GİRİŞ_YAPILDI",
                                "detay": f"{kullanici} sisteme giriş yaptı",
                            }).execute()
                    except: pass
                    st.rerun()
                else:
                    st.error("Kullanıcı adı veya şifre hatalı!")

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
    st.rerun()

# ── SESSION STATE ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="MWCRMPRO", layout="wide", initial_sidebar_state="expanded")
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
/* Mobil uyumluluk */
@media (max-width: 768px) {
    .block-container { padding: 0.5rem !important; }
    div[data-testid="column"] { min-width: 100% !important; }
    .stButton>button { width: 100% !important; font-size: 13px !important; }
    .stDataFrame { font-size: 11px !important; }
    h1 { font-size: 1.3rem !important; }
    h2 { font-size: 1.1rem !important; }
    h3 { font-size: 1rem !important; }
}
/* Genel buton iyileştirme */
.stButton>button { border-radius: 8px !important; }
</style>
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
        if s.endswith(".0"): s = s[:-2]
        # Sadece rakam bırak
        s = _re_tel.sub(r"[^0-9]", "", s)
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
        # 2026-06-22 veya 2026-06-22T... → 22.06.2026
        if len(s) >= 10 and s[4] == "-":
            return f"{s[8:10]}.{s[5:7]}.{s[:4]}"
        # Zaten 22.06.2026 formatındaysa
        if len(s) >= 10 and s[2] == "." and s[5] == ".":
            return s[:10]
    except:
        pass
    return s[:10]



_TAB_LISTESI_DEFAULT = ["yeni", "liste", "detay_cari", "analiz", "randevu", "teklif", "ozel_teklif", "kisiler", "rapor", "excel", "kullanici", "admin_rapor"]
_TAB_ETIKETLER = {
    "yeni": "➕ Yeni Kart Ekle",
    "liste": "📋 Cari Liste / Düzenle",
    "rapor": "📊 Raporlar",
    "teklif": "📄 Spot Teklif",
    "ozel_teklif": "⭐ Özel Teklif",
    "excel": "📥 Excel Aktar",
    "kisiler": "📞 Telefon Kişiler",
    "analiz": "🔍 Müşteri Analizi",
    "detay_cari": "📊 Detay Cari Liste",
    "randevu": "📅 Randevular",
    "kullanici": "👥 Kullanıcı Yönetimi",
    "mesajlar": "💬 Mesajlar",
    "admin_rapor": "📊 Rapor Tasarla",
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
section[data-testid="stSidebar"] { padding-top: 0.5rem !important; transform: translateX(0px) !important; }
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
        "<div style='font-size:15px;font-weight:700;color:#1f6feb;"
        "padding:14px 10px 14px;letter-spacing:0.8px;border-bottom:2px solid #1f6feb;margin-bottom:10px;'>"
        "🏢 MWCRMPRO</div>",
        unsafe_allow_html=True
    )

    # ── MENÜ LİSTESİ ──────────────────────────────────────────────────────────
    _sb_liste = get_menu_tercihi(st.session_state["kullanici"])
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

    for _tab_key in _sb_liste:
        _etiket = _TAB_ETIKETLER.get(_tab_key, _tab_key)
        _aktif_mi = st.session_state["aktif_tab"] == _tab_key
        _renk = _TAB_RENKLER.get(_tab_key, "#374151")
        if not _aktif_mi:
            st.markdown(f"<style>section[data-testid='stSidebar'] div[data-testid='stVerticalBlock'] > div:last-child .stButton>button p {{ color: {_renk} !important; }}</style>", unsafe_allow_html=True)
        if st.button(_etiket, use_container_width=True,
                     type="primary" if _aktif_mi else "secondary",
                     key=f"sb_{_tab_key}"):
            st.session_state["aktif_tab"] = _tab_key
            st.rerun()

    # ── ALT BÖLÜM ─────────────────────────────────────────────────────────────
    st.divider()

    with st.expander("❓ Yardım"):
        st.markdown("📞 [5400344228](tel:05400344228)")
        st.link_button("📱 WhatsApp", "https://wa.me/905400344228", use_container_width=True)
        talep = st.text_area("Talep:", height=60, key="sidebar_talep")
        if st.button("📨 Gönder", key="sidebar_wa_btn"):
            if talep.strip():
                st.markdown(f"[👉 Gönder](https://wa.me/905400344228?text={talep.replace(' ','%20')})")

    if st.session_state.get("rol") == "admin":
        with st.expander("🎛️ Menü Sırası"):
            mevcut_sira_m = get_menu_tercihi(st.session_state["kullanici"])
            _goster = []
            for _t in mevcut_sira_m:
                if _t not in _goster:
                    _goster.append(_t)
            mevcut_sira_m = _goster
            for idx_m, tab_key in enumerate(mevcut_sira_m):
                c1, c2, c3 = st.columns([4,1,1])
                c1.caption(_TAB_ETIKETLER.get(tab_key, tab_key))
                if idx_m > 0 and c2.button("▲", key=f"up_{tab_key}"):
                    yeni_s = mevcut_sira_m.copy()
                    yeni_s[idx_m], yeni_s[idx_m-1] = yeni_s[idx_m-1], yeni_s[idx_m]
                    save_menu_tercihi(st.session_state["kullanici"], yeni_s)
                    st.rerun()
                if idx_m < len(mevcut_sira_m)-1 and c3.button("▼", key=f"dn_{tab_key}"):
                    yeni_s = mevcut_sira_m.copy()
                    yeni_s[idx_m], yeni_s[idx_m+1] = yeni_s[idx_m+1], yeni_s[idx_m]
                    save_menu_tercihi(st.session_state["kullanici"], yeni_s)
                    st.rerun()
            if st.button("↺ Sıfırla", use_container_width=True, key="menu_sifirla"):
                save_menu_tercihi(st.session_state["kullanici"], _TAB_LISTESI_DEFAULT.copy() + ["kullanici","admin_rapor"])
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
aktif = st.session_state["aktif_tab"]
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

    st.divider()
    if duzenle:
        st.markdown(f"### ✏️ Düzenleniyor: **{duzenle.get('firma')}** (ID: {duzenle.get('id')})")
    else:
        st.markdown("### ➕ Yeni Cari Kart")

    il_listesi = sorted(ILLER_ILCELER.keys())
    mevcut_il   = duzenle.get("il","") if duzenle and duzenle.get("il","") in il_listesi else il_listesi[0]
    # Eski session key'lerini temizle
    for _dk in ["yeni_il_sec","yeni_ilce_sec","yeni_il_form","yeni_ilce_form"]:
        if _dk in st.session_state and not duzenle:
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
                    "beklenen_ciro": beklenen_ciro, "gerceklesen_ciro": gerceklesen_ciro
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
    if st.session_state.get("kayit_mesaj"):
        st.success(st.session_state["kayit_mesaj"])
        st.session_state["kayit_mesaj"] = ""

    # ── VERİ YÜKLE ──────────────────────────────────────────────────────────────
    sb_liste = get_sb_client()
    try:
        if sb_liste:
            res_l = sb_liste.table("cari_kartlar").select("*").neq("silindi",1).order("tarih",desc=True).execute()
            df = pd.DataFrame(res_l.data) if res_l.data else pd.DataFrame()
        else:
            raise Exception()
    except:
        df = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi='0' OR silindi IS NULL ORDER BY tarih DESC")

    if not df.empty:
        for _tk in ["gsm","sabit"]:
            if _tk in df.columns:
                df[_tk] = _telefon_temizle(df[_tk])

    with st.expander("🔍 Mükerrer (Aynı İsimli) Müşterileri Bul ve Birleştir"):
        _firma_gruplari = df.groupby(df["firma"].str.strip().str.upper())["id"].apply(list)
        _mukerrerler = {k: v for k, v in _firma_gruplari.items() if len(v) > 1}

        if not _mukerrerler:
            st.caption("Mükerrer müşteri bulunamadı.")
        else:
            st.warning(f"{len(_mukerrerler)} mükerrer firma adı bulundu.")

            _mr_tab1, _mr_tab2 = st.tabs(["📋 Toplu Karşılaştırma (hepsi)", "🔎 Tek Seçerek Karşılaştır"])

            with _mr_tab1:
                @st.cache_data(ttl=60)
                def _dc_tum_not_analiz_sayilari():
                    """Tek seferde tüm notları ve analizleri çek — N+1 sorgu sorununu önler"""
                    _not_say = {}
                    _analiz_say = {}
                    try:
                        sb_mt = get_sb_service() or get_sb_client()
                        if sb_mt:
                            _rn = sb_mt.table("cari_aciklamalar").select("cari_id").execute()
                            if _rn.data:
                                for _row in _rn.data:
                                    _cid_n = _row.get("cari_id")
                                    _not_say[_cid_n] = _not_say.get(_cid_n, 0) + 1
                            _ra = sb_mt.table("musteri_analiz").select("firma").execute()
                            if _ra.data:
                                for _row in _ra.data:
                                    _fad_n = _row.get("firma")
                                    _analiz_say[_fad_n] = _analiz_say.get(_fad_n, 0) + 1
                    except: pass
                    return _not_say, _analiz_say

                _not_say_tum, _analiz_say_tum = _dc_tum_not_analiz_sayilari()

                _toplu_satirlar = []
                for _fadi_t, _idler_t in _mukerrerler.items():
                    _grup_t = df[df["id"].isin(_idler_t)]
                    for _, _gt in _grup_t.iterrows():
                        _gcid_t = int(_gt["id"])
                        _toplu_satirlar.append({
                            "Sil": False,
                            "Firma Grubu": _fadi_t,
                            "ID": _gcid_t,
                            "Kayıt Tarihi": fmt_tarih(_gt.get("tarih","")),
                            "Yetkili": _gt.get("yetkili","") or "—",
                            "GSM": _gt.get("gsm","") or "—",
                            "İl/İlçe": f"{_gt.get('il','') or ''} / {_gt.get('ilce','') or ''}",
                            "Segment": _gt.get("segment","") or "—",
                            "Durum/Aşama": f"{_gt.get('durum','') or ''} / {_gt.get('islem_asamasi','') or ''}",
                            "Not Sayısı": _not_say_tum.get(_gcid_t, 0),
                            "Analiz Sayısı": _analiz_say_tum.get(str(_gt.get("firma","")), 0),
                        })
                _df_toplu = pd.DataFrame(_toplu_satirlar)
                _edited_toplu = st.data_editor(
                    _df_toplu,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="fixed",
                    height=min(600, 60+len(_df_toplu)*38),
                    disabled=["Firma Grubu","ID","Kayıt Tarihi","Yetkili","GSM","İl/İlçe","Segment","Durum/Aşama","Not Sayısı","Analiz Sayısı"],
                    column_config={"Sil": st.column_config.CheckboxColumn(width="small", help="İşaretleyip aşağıdaki butona basın")},
                    key="dc_mukerrer_toplu_editor"
                )

                _isaretli_toplu = _edited_toplu[_edited_toplu["Sil"] == True]
                if st.button(f"🗑 İşaretlenen {len(_isaretli_toplu)} Kaydı Sil", type="primary", use_container_width=True, key="dc_mukerrer_toplu_sil_btn", disabled=len(_isaretli_toplu)==0):
                    _silinen_t = 0
                    _hata_t = 0
                    sb_toplu_sil = get_sb_service() or get_sb_client()
                    for _, _isr in _isaretli_toplu.iterrows():
                        _sid_t = int(_isr["ID"])
                        try:
                            sb_toplu_sil.table("musteri_calisma_tablosu").delete().eq("cari_id", _sid_t).execute()
                            sb_toplu_sil.table("cari_kartlar").update({"silindi": 1}).eq("id", _sid_t).execute()
                            _silinen_t += 1
                        except Exception as _et:
                            _hata_t += 1
                    try: get_cari_listesi.clear()
                    except: pass
                    if _silinen_t:
                        st.success(f"✅ {_silinen_t} kayıt silindi! (Notlar taşınmadı — tek tek silmek isterseniz 'Tek Seçerek Karşılaştır' sekmesini kullanın)")
                    if _hata_t:
                        st.error(f"❌ {_hata_t} kayıt silinemedi.")
                    st.rerun()

                st.divider()
                st.caption("Birleştirmek (not taşıyarak) istediğiniz grubu seçin, direkt karşılaştırma paneli açılır:")
                _mukerrer_opts_t1 = [f"{k} ({len(v)} kayıt)" for k, v in _mukerrerler.items()]
                _secilen_grup_t1 = st.selectbox("Grup seç", ["-- Seçin --"] + _mukerrer_opts_t1, key="dc_mukerrer_grup_sec_t1")
                if _secilen_grup_t1 != "-- Seçin --":
                    st.session_state["dc_mukerrer_grup_sec"] = _secilen_grup_t1
                    st.info("👉 'Tek Seçerek Karşılaştır' sekmesine geçin, grup otomatik seçili gelecek.")

            with _mr_tab2:
                _mukerrer_opts = [f"{k} ({len(v)} kayıt)" for k, v in _mukerrerler.items()]
                _secilen_grup = st.selectbox("İncelenecek grup", ["-- Seçin --"] + _mukerrer_opts, key="dc_mukerrer_grup_sec")

                if _secilen_grup != "-- Seçin --":
                    _grup_adi = list(_mukerrerler.keys())[_mukerrer_opts.index(_secilen_grup)]
                    _grup_idler = _mukerrerler[_grup_adi]
                    _grup_satirlar = df[df["id"].isin(_grup_idler)]

                    @st.cache_data(ttl=30)
                    def _dc_kayit_sayilari(cid, firma_adi):
                        try:
                            sb_m = get_sb_service() or get_sb_client()
                            if sb_m:
                                _n1 = len(sb_m.table("cari_aciklamalar").select("id").eq("cari_id", cid).execute().data or [])
                                _n2 = len(sb_m.table("musteri_analiz").select("id").eq("firma", firma_adi).execute().data or [])
                                return _n1, _n2
                        except: pass
                        return 0, 0

                    st.markdown(f"#### {_grup_adi} — karşılaştırma")
                    _kart_cols = st.columns(len(_grup_satirlar))
                    _id_listesi = list(_grup_satirlar["id"])
                    for _ci, (_, _gr) in enumerate(_grup_satirlar.iterrows()):
                        _gcid = int(_gr["id"])
                        _nnot, _nanaliz = _dc_kayit_sayilari(_gcid, str(_gr.get("firma","")))
                        with _kart_cols[_ci]:
                            st.markdown(f"**ID [{_gcid}]**")
                            st.caption(f"📅 Kayıt: {fmt_tarih(_gr.get('tarih',''))}")
                            _m_yetkili = st.text_input("Yetkili", value=_gr.get("yetkili","") or "", key=f"dc_mk_yetkili_{_gcid}")
                            _m_gsm = st.text_input("GSM", value=_gr.get("gsm","") or "", key=f"dc_mk_gsm_{_gcid}")
                            _m_il = st.text_input("İl", value=_gr.get("il","") or "", key=f"dc_mk_il_{_gcid}")
                            _m_ilce = st.text_input("İlçe", value=_gr.get("ilce","") or "", key=f"dc_mk_ilce_{_gcid}")
                            _m_segment = st.text_input("Segment", value=_gr.get("segment","") or "", key=f"dc_mk_segment_{_gcid}")
                            _m_durum = st.text_input("Durum", value=_gr.get("durum","") or "", key=f"dc_mk_durum_{_gcid}")
                            _m_asama = st.text_input("Aşama", value=_gr.get("islem_asamasi","") or "", key=f"dc_mk_asama_{_gcid}")
                            st.caption(f"💰 Hedef: {_gr.get('beklenen_ciro',0) or 0} ₺")
                            st.caption(f"📝 Not sayısı: **{_nnot}**")
                            st.caption(f"🔍 Analiz sayısı: **{_nanaliz}**")

                            if st.button("💾 Bu Kartı Güncelle", key=f"dc_mukerrer_guncelle_{_gcid}", use_container_width=True):
                                try:
                                    sb_guncelle = get_sb_service() or get_sb_client()
                                    sb_guncelle.table("cari_kartlar").update({
                                        "yetkili": _m_yetkili, "gsm": _m_gsm, "il": _m_il, "ilce": _m_ilce,
                                        "segment": _m_segment, "durum": _m_durum, "islem_asamasi": _m_asama,
                                    }).eq("id", _gcid).execute()
                                    try: get_cari_listesi.clear()
                                    except: pass
                                    st.success(f"✅ [{_gcid}] güncellendi!")
                                    st.rerun()
                                except Exception as _eguncelle:
                                    st.error(f"Güncelleme hatası: {_eguncelle}")

                            if st.button(f"🗑 Bunu Sil", key=f"dc_mukerrer_sil_{_gcid}", use_container_width=True):
                                _kalacak_id = [i for i in _id_listesi if i != _gcid][0] if len(_id_listesi) == 2 else None
                                try:
                                    sb_birlestir = get_sb_service() or get_sb_client()
                                    _tasinan = 0
                                    if _kalacak_id:
                                        # notları kalan kayda taşı
                                        _r_not = sb_birlestir.table("cari_aciklamalar").select("id").eq("cari_id", _gcid).execute()
                                        if _r_not.data:
                                            sb_birlestir.table("cari_aciklamalar").update({"cari_id": _kalacak_id}).eq("cari_id", _gcid).execute()
                                            _tasinan = len(_r_not.data)
                                    # çalışma tablosu kaydını sil (varsa)
                                    sb_birlestir.table("musteri_calisma_tablosu").delete().eq("cari_id", _gcid).execute()
                                    # cari kartı soft-delete yap
                                    sb_birlestir.table("cari_kartlar").update({"silindi": 1}).eq("id", _gcid).execute()
                                    try: get_cari_listesi.clear()
                                    except: pass
                                    if _tasinan:
                                        st.success(f"✅ [{_gcid}] silindi! {_tasinan} not [{_kalacak_id}]'e taşındı.")
                                    else:
                                        st.success(f"✅ [{_gcid}] silindi!")
                                    st.rerun()
                                except Exception as _esil:
                                    st.error(f"Silme hatası: {_esil}")

                    if len(_id_listesi) > 2:
                        st.caption("💡 3+ kayıt olduğu için, sildikten sonra kalan kayıtlar arasında tekrar seçim yapabilirsiniz. Notlar otomatik taşınmaz, manuel kontrol edin.")

                st.divider()
                st.caption("Tüm mükerrer gruplar:")
                for _fadi, _idler in _mukerrerler.items():
                    _satirlar = df[df["id"].isin(_idler)]
                    st.markdown(f"**{_fadi}**")
                    for _, _sr in _satirlar.iterrows():
                        st.caption(f"[{int(_sr['id'])}] {_sr['firma']} — {_sr.get('il','') or ''} {_sr.get('ilce','') or ''} — {_sr.get('gsm','') or ''} — kayıt: {str(_sr.get('tarih','') or '')[:10]}")


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

    # df'de olan ama tabloda olmayan aşama/durumları da ekle
    if not df.empty:
        if "islem_asamasi" in df.columns:
            for _da in df["islem_asamasi"].dropna().unique():
                if str(_da).strip() and str(_da) not in ["nan",""] and _da not in tum_asama_opts:
                    tum_asama_opts.append(str(_da))
        if "durum" in df.columns:
            for _dd in df["durum"].dropna().unique():
                if str(_dd).strip() and str(_dd) not in ["nan",""] and _dd not in tum_durum_opts:
                    tum_durum_opts.append(str(_dd))

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

    # Durum satırı
    _d_veri = [("Toplam", len(df))]
    for _dn in tum_durum_opts:
        _dc = len(df[df["durum"]==_dn]) if "durum" in df.columns else 0
        _d_veri.append((_dn, _dc))

    _d_cols = st.columns(len(_d_veri))
    for i, (_ad, _sayi) in enumerate(_d_veri):
        _em = _DURUM_EMOJI.get(_ad, "🔹")
        if _d_cols[i].button(f"{_em} {_ad}\n{_sayi}", key=f"dur_btn_{i}", use_container_width=True):
            if _ad == "Toplam":
                st.session_state["_cl_fil_durum_multi"] = []
            else:
                st.session_state["_cl_fil_durum_multi"] = [_ad]
            st.rerun()

    # Aşama satırı
    if tum_asama_opts:
        _a_veri = [(a, len(df[df["islem_asamasi"]==a]) if "islem_asamasi" in df.columns else 0) for a in tum_asama_opts]
        _a_cols = st.columns(len(_a_veri))
        for i, (_an, _ac) in enumerate(_a_veri):
            _em2 = _ASAMA_EMOJI.get(_an, "🔸")
            if _a_cols[i].button(f"{_em2} {_an}\n{_ac}", key=f"asm_btn_{i}", use_container_width=True):
                st.session_state["_cl_fil_asama_multi"] = [_an]
                st.rerun()

    # ── GELİŞMİŞ FİLTRE PANEL ────────────────────────────────────────────────
    with st.expander("🔍 Filtreler & Arama", expanded=st.session_state.get("_cl_fil_acik", True)):
        st.session_state["_cl_fil_acik"] = True  # expander açık kalsın
        _frow1 = st.columns([2,1,1,1,1,1,1])
        ara_txt = _frow1[0].text_input("", placeholder="🔍 Firma, yetkili, il, gsm...", key="ara_liste", label_visibility="collapsed")

        # Asama multiselect
        _asama_sec = _frow1[1].multiselect(
            "Aşama", tum_asama_opts,
            default=st.session_state.get("_cl_fil_asama_multi", []),
            key="_cl_fil_asama_multi", placeholder="Aşama seç..."
        )
        # Durum multiselect
        _durum_sec = _frow1[2].multiselect(
            "Durum", tum_durum_opts,
            default=st.session_state.get("_cl_fil_durum_multi", []),
            key="_cl_fil_durum_multi", placeholder="Durum seç..."
        )
        # Segment
        filtre_seg = _frow1[3].selectbox(
            "Segment", ["Tümü","👑 A+","⭐ A","🔵 B","⚪ C","Segmentsiz"],
            key="fil_seg", label_visibility="visible"
        )
        # İl multiselect
        _il_opts = sorted(df["il"].dropna().astype(str).unique().tolist()) if "il" in df.columns else []
        _il_sec = _frow1[4].multiselect(
            "İl", _il_opts,
            default=st.session_state.get("_cl_fil_il_multi", []),
            key="_cl_fil_il_multi", placeholder="İl seç..."
        )
        # İlçe multiselect — seçili ile göre dinamik filtrele
        if _il_sec:
            _ilce_opts = sorted(df[df["il"].astype(str).isin(_il_sec)]["ilce"].dropna().astype(str).unique().tolist()) if "ilce" in df.columns else []
        else:
            _ilce_opts = sorted(df["ilce"].dropna().astype(str).unique().tolist()) if "ilce" in df.columns else []
        _ilce_opts = [x for x in _ilce_opts if x and x not in ["nan","None",""]]
        _ilce_sec = _frow1[5].multiselect(
            "İlçe", _ilce_opts,
            default=[x for x in st.session_state.get("_cl_fil_ilce_multi", []) if x in _ilce_opts],
            key="_cl_fil_ilce_multi", placeholder="İlçe seç..."
        )
        # Temsilci multiselect
        _tem_opts = sorted(df["temsilci"].dropna().astype(str).unique().tolist()) if "temsilci" in df.columns else []
        _tem_sec = _frow1[6].multiselect(
            "Temsilci", _tem_opts,
            default=st.session_state.get("_cl_fil_temsilci_multi", []),
            key="_cl_fil_temsilci_multi", placeholder="Temsilci seç..."
        )

        _frow2 = st.columns([2,1,1])
        siralama_kol = _frow2[0].selectbox(
            "Sıralama", ["Tarih↓","Firma A-Z","Firma Z-A","İl A-Z","Temsilci A-Z"],
            key="siralama_kol", label_visibility="visible"
        )
        if _frow2[1].button("🗑️ Filtreleri Temizle", use_container_width=True, key="cl_fil_temizle"):
            for _fk in ["_cl_fil_asama_multi","_cl_fil_durum_multi","_cl_fil_il_multi","_cl_fil_ilce_multi","_cl_fil_temsilci_multi","fil_seg","ara_liste"]:
                st.session_state.pop(_fk, None)
            st.rerun()

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

    # Segment hesapla ve sırala
    df_f["_seg_goster"] = df_f.apply(lambda r: hesapla_segment(r.get("segment",""), r.get("gerceklesen_ciro",0)), axis=1)
    _seg_sira = {"👑 A+":0,"⭐ A":1,"🔵 B":2,"⚪ C":3,"":4}
    df_f["_seg_sira"] = df_f["_seg_goster"].map(lambda s: _seg_sira.get(s,4))
    df_f = df_f.sort_values(["_seg_sira","firma"], ascending=[True,True]).reset_index(drop=True)
    if siralama_kol == "Firma A-Z":      df_f = df_f.sort_values("firma", ascending=True)
    elif siralama_kol == "Firma Z-A":    df_f = df_f.sort_values("firma", ascending=False)
    elif siralama_kol == "İl A-Z" and "il" in df_f.columns:       df_f = df_f.sort_values("il", ascending=True)
    elif siralama_kol == "Temsilci A-Z" and "temsilci" in df_f.columns: df_f = df_f.sort_values("temsilci", ascending=True)
    df_f = df_f.reset_index(drop=True)

    # Müşteri seçici + aktif filtre özeti
    _fc_row = st.columns([3,1,0.6])
    kart_opts = ["-- Müşteri Seçin --"] + [
        f"[{int(r['id'])}] {r['_seg_goster']+' ' if r['_seg_goster'] else ''}{r['firma']} | {r.get('il','')} | {r.get('islem_asamasi','')}"
        for _, r in df_f.iterrows()
    ]
    if st.session_state.get("kart_sec_reset"):
        st.session_state.pop("kart_sec_reset", None)
        st.session_state.pop("kart_sec", None)
    secili_kart = _fc_row[0].selectbox("", kart_opts, key="kart_sec", label_visibility="collapsed")
    if secili_kart != "-- Müşteri Seçin --":
        if _fc_row[1].button("❌ Temizle", key="kart_sec_temizle", use_container_width=True):
            st.session_state["kart_sec_reset"] = True
            st.rerun()
    _aktif_fil_sayisi = sum([
        bool(ara_txt), bool(_asama_sec), bool(_durum_sec),
        filtre_seg != "Tümü", bool(_il_sec), bool(_ilce_sec), bool(_tem_sec)
    ])
    _fil_badge = f" 🔵 {_aktif_fil_sayisi} filtre aktif" if _aktif_fil_sayisi else ""
    _fc_row[2].markdown(f"<small style='color:gray'>{len(df_f)} kayıt{_fil_badge}</small>", unsafe_allow_html=True)
    if secili_kart != "-- Müşteri Seçin --" and "[" in secili_kart:
        try:
            kart_id = int(secili_kart.split("]")[0].replace("[","").strip())
            kart_row = df_f[df_f["id"]==kart_id].iloc[0]
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
                st.markdown(f"<a href='https://wa.me/{_gsm_raw}' target='_blank'>WhatsApp aç</a>", unsafe_allow_html=True)
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

            # Supabase'den çek
            _df_ac = pd.DataFrame()
            if sb_liste:
                try:
                    _r = sb_liste.table("cari_aciklamalar").select("*").eq("cari_id", kart_id).order("tarih", desc=True).execute()
                    _df_ac = pd.DataFrame(_r.data) if _r.data else pd.DataFrame()
                except:
                    _df_ac = pd.DataFrame()

            # YENİ AÇIKLAMA FORMU
            with st.form(f"acform_{kart_id}", clear_on_submit=True):
                _yaz = st.text_area("Yeni Açıklama:", height=80, placeholder="Açıklamanızı yazın...")
                if st.form_submit_button("💾 Kaydet", type="primary", use_container_width=True):
                    if _yaz and _yaz.strip():
                        try:
                            sb_liste.table("cari_aciklamalar").insert({
                                "cari_id": kart_id,
                                "cari_adi": str(kart_row.get("firma","")),
                                "aciklama": _yaz.strip(),
                                "olusturan": st.session_state.get("kullanici","")
                            }).execute()
                            st.success("✅ Kaydedildi!")
                            st.rerun()
                        except Exception as _ex:
                            st.error(f"Hata: {_ex}")
                    else:
                        st.warning("Boş olamaz!")

            # ESKİ AÇIKLAMALAR
            if not _df_ac.empty:
                st.markdown(f"**{len(_df_ac)} kayıt — tıkla aç:**")
                for _, _row in _df_ac.iterrows():
                    _rid   = _row.get("id", 0)
                    _tarih = fmt_tarih(_row.get("tarih",""))
                    _kim   = str(_row.get("olusturan",""))
                    _txt   = str(_row.get("aciklama",""))
                    with st.expander(f"📅 {_tarih}  👤 {_kim}  · {_txt[:50]}{'...' if len(_txt)>50 else ''}"):
                        st.write(_txt)
                        if st.button("🗑️ Sil", key=f"sil_{_rid}_{kart_id}"):
                            try:
                                sb_liste.table("cari_aciklamalar").delete().eq("id", int(_rid)).execute()
                                st.rerun()
                            except: pass

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
    col_config = {
        "Seç":           st.column_config.CheckboxColumn("Seç", default=False),
        "id":            st.column_config.NumberColumn("ID", disabled=True),
        "tarih":         None, "olusturan": None, "silindi": None,
        "beklenen_ciro": None, "gerceklesen_ciro": None,
        "adres":         None, "aciklama":   None,
        "firma":         st.column_config.TextColumn("Firma"),
        "yetkili":       st.column_config.TextColumn("Yetkili"),
        "gsm":           st.column_config.TextColumn("GSM"),
        "sabit":         st.column_config.TextColumn("S. Tel"),
        "email":         st.column_config.TextColumn("Email"),
        "il":            st.column_config.TextColumn("İl"),
        "ilce":          st.column_config.TextColumn("İlçe"),
        "durum":         st.column_config.SelectboxColumn("Durum", options=tum_durum_opts),
        "temsilci":      st.column_config.TextColumn("Temsilci"),
        "islem_asamasi": st.column_config.SelectboxColumn("Aşama", options=tum_asama_opts),
        "aciklama":      st.column_config.TextColumn("Açıklama — yaz kaydet → arşivlenir", width="large"),
        "📨 Notlar":     st.column_config.TextColumn("📨 Notlar", disabled=True, width="small"),
    }
    col_order = ["Seç","id","firma","yetkili","gsm","sabit","email","il","ilce","durum","temsilci","islem_asamasi","aciklama","📨 Notlar"]

    # ── DATA EDITOR ─────────────────────────────────────────────────────────────
    df_edit = df_f.copy()
    # aciklama kolonu kesinlikle olsun
    if "aciklama" not in df_edit.columns:
        df_edit["aciklama"] = ""
    df_edit["aciklama"] = df_edit["aciklama"].fillna("").astype(str).replace("nan","")

    # Her firma için not sayısı + içerik (hover için)
    _not_detay = {}  # {cari_id: [{tarih, olusturan, aciklama}, ...]}
    if sb_liste:
        try:
            _res_notlar = sb_liste.table("cari_aciklamalar").select("cari_id,tarih,olusturan,aciklama").execute()
            if _res_notlar.data:
                import collections
                _not_sayac = collections.Counter([str(r["cari_id"]) for r in _res_notlar.data])
                for _nr in _res_notlar.data:
                    _ncid = str(_nr.get("cari_id",""))
                    if _ncid not in _not_detay:
                        _not_detay[_ncid] = []
                    _not_detay[_ncid].append({
                        "tarih": fmt_tarih(_nr.get("tarih","")),
                        "kim": str(_nr.get("olusturan","") or ""),
                        "metin": str(_nr.get("aciklama","") or ""),
                    })
                df_edit["📨 Notlar"] = df_edit["id"].apply(lambda x: f"📨 {_not_sayac.get(str(int(x)),0)}" if _not_sayac.get(str(int(x)),0) > 0 else "")
            else:
                df_edit["📨 Notlar"] = ""
        except:
            df_edit["📨 Notlar"] = ""
    else:
        df_edit["📨 Notlar"] = ""

    df_edit.insert(0, "Seç", False)

    import json as _json_ls

    # ── TÜMÜ GÖSTER — tablo sol, not paneli sağ ──────────────────────────────
    _kayitli_sira = st.session_state.get("_cl_kolon_sira", [])
    _aktif_col_order = _kayitli_sira if _kayitli_sira else col_order

    # Sağda not paneli açık mı?
    _not_panel_id = st.session_state.get("_cl_not_panel_id")

    if _not_panel_id:
        _tbl_col, _not_col = st.columns([3, 1])
    else:
        _tbl_col = st.container()
        _not_col = None

    with _tbl_col:
        edited_df = st.data_editor(
            df_edit,
            use_container_width=True,
            num_rows="fixed",
            column_config=col_config,
            column_order=_aktif_col_order,
            key="cari_editor"
        )

    if _not_panel_id and _not_col:
        with _not_col:
            _panel_notlar = _not_detay.get(str(_not_panel_id), [])
            _panel_firma = ""
            _panel_rows = df_edit[df_edit["id"] == int(_not_panel_id)]
            if not _panel_rows.empty:
                _panel_firma = str(_panel_rows.iloc[0].get("firma",""))
            st.markdown(
                f"<div style='border:1.5px solid #3b82f6;border-radius:10px;padding:12px 14px;background:white'>"
                f"<div style='font-size:12px;font-weight:600;color:#1e40af;margin-bottom:8px'>📋 {_panel_firma[:22]}<br>"
                f"<span style='font-weight:400;color:#64748b'>{len(_panel_notlar)} not</span></div>"
                + "".join([
                    f"<div style='border-left:3px solid #3b82f6;padding:7px 10px;margin:5px 0;"
                    f"border-radius:0 6px 6px 0;background:#f8fafc'>"
                    f"<div style='font-size:11px;color:#94a3b8;margin-bottom:2px'>📅 {_nn.get('tarih','')} · 👤 {_nn.get('kim','')}</div>"
                    f"<div style='color:#1e293b;font-size:12px'>{str(_nn.get('metin','')).replace('<','&lt;').replace('>','&gt;')}</div>"
                    f"</div>"
                    for _nn in _panel_notlar
                ])
                + "<div style='font-size:11px;color:#94a3b8;margin-top:8px'>Satırı tekrar seç → kapanır</div>"
                + "</div>",
                unsafe_allow_html=True
            )

    # Kolon sırası değiştiyse session_state'e kaydet
    try:
        _editor_meta = st.session_state.get("cari_editor", {})
        _col_order_now = _editor_meta.get("column_order", [])
        if _col_order_now:
            st.session_state["_cl_kolon_sira"] = _col_order_now
    except:
        pass

    # Her render'da tüm tabloyu session_state'e kaydet
    try:
        _kv = edited_df.copy()
        if "aciklama" not in _kv.columns:
            _kv["aciklama"] = ""
        _kv["aciklama"] = _kv["aciklama"].fillna("").astype(str).replace("nan","")
        _kayit_kolonlar = ["id","firma","yetkili","gsm","sabit","email","il","ilce","durum","temsilci","islem_asamasi","aciklama"]
        _mevcut = [c for c in _kayit_kolonlar if c in _kv.columns]
        st.session_state["_ls_tablo"] = _kv[_mevcut].to_json(orient="records", force_ascii=False)
    except:
        pass

    secili_df = edited_df[edited_df["Seç"] == True]
    secili_sayi = len(secili_df)
    secili_idler = secili_df["id"].tolist() if not secili_df.empty else []

    secili_df = edited_df[edited_df["Seç"] == True]
    secili_sayi = len(secili_df)
    secili_idler = secili_df["id"].tolist() if not secili_df.empty else []

    # Tek satır seçilince — notu varsa sağ paneli aç
    if secili_sayi == 1:
        _sel_id = int(secili_idler[0])
        if _not_detay.get(str(_sel_id)):
            if st.session_state.get("_cl_not_panel_id") != _sel_id:
                st.session_state["_cl_not_panel_id"] = _sel_id
                st.rerun()
    elif secili_sayi == 0 and st.session_state.get("_cl_not_panel_id"):
        # Seçim kalkarsa paneli kapat
        st.session_state.pop("_cl_not_panel_id", None)
        st.rerun()


    # ── BUTONLAR ──────────────────────────────────────────────────────────────
    # Kaydet flag'i — ilk tıkta set et, ikinci render'da çalıştır
    if st.session_state.get("_kaydet_flag"):
        st.session_state.pop("_kaydet_flag")
        _editor_state = st.session_state.get("cari_editor", {})
        _edited_rows  = _editor_state.get("edited_rows", {})
        _tablo_json   = st.session_state.get("_ls_tablo")
        _do_kaydet = True
    else:
        _do_kaydet = False

    btn_k, btn_a, btn_s, btn_kolon = st.columns(4)
    with btn_kolon:
        if st.button("🔄 Kolon Sırasını Sıfırla", use_container_width=True, key="cl_kolon_sifirla"):
            st.session_state.pop("_cl_kolon_sira", None)
            st.rerun()
    with btn_k:
        if st.button("💾 Değişiklikleri Kaydet", use_container_width=True, type="primary", key="liste_kaydet"):
            st.session_state["_kaydet_flag"] = True
            st.rerun()
        if _do_kaydet:
            _editor_state = st.session_state.get("cari_editor", {})
            _edited_rows  = _editor_state.get("edited_rows", {})
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
                        guncelle = {k: str(v) if v is not None else ""
                                   for k, v in degisiklikler.items() if k != "Seç"}
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
                    st.success(f"✅ {kayit_sayi} satır kaydedildi!" + (f" · {_arsiv_sayi} not 📨 arşivlendi!" if _arsiv_sayi > 0 else ""))
                elif _arsiv_sayi > 0:
                    st.success(f"✅ {_arsiv_sayi} not 📨 arşivlendi!")
                else:
                    st.info("Değişiklik kaydedildi.")
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

    # ── FİLTRELENMİŞ FİRMALARA TOPLU NOT / ÇALIŞMA ───────────────────────────
    if len(df_f) > 0:
        with st.expander(f"📝 Filtrelenmiş {len(df_f)} Firmaya Toplu Not / Çalışma Ekle", expanded=False):
            st.caption(f"Şu an filtrede görünen **{len(df_f)} firma**ya aynı notu/çalışmayı ekleyebilirsiniz.")
            _toplu_not_col1, _toplu_not_col2 = st.columns([3,1])
            _toplu_not_metni = _toplu_not_col1.text_area(
                "Not metni:", height=80,
                placeholder="Örn: 'Mayıs kampanyası bilgilendirmesi yapıldı'",
                key="toplu_not_metni"
            )
            _toplu_not_kim = st.session_state.get("kullanici", "")
            if _toplu_not_col2.button(f"💾 {len(df_f)} Firmaya Ekle", use_container_width=True, key="toplu_not_kaydet", type="primary"):
                if _toplu_not_metni and _toplu_not_metni.strip():
                    _toplu_eklenen = 0
                    _toplu_hata = 0
                    for _, _tf in df_f.iterrows():
                        try:
                            _tcid = int(_tf["id"])
                            if sb_liste:
                                sb_liste.table("cari_aciklamalar").insert({
                                    "cari_id": _tcid,
                                    "cari_adi": str(_tf.get("firma","")),
                                    "aciklama": _toplu_not_metni.strip(),
                                    "olusturan": _toplu_not_kim,
                                }).execute()
                            _toplu_eklenen += 1
                        except:
                            _toplu_hata += 1
                    if _toplu_eklenen:
                        st.success(f"✅ {_toplu_eklenen} firmaya not eklendi!" + (f" (Hata: {_toplu_hata})" if _toplu_hata else ""))
                        st.rerun()
                    else:
                        st.error("Not eklenemedi.")
                else:
                    st.warning("Not metni boş olamaz!")

    st.divider()
elif aktif == "kullanici":
    sayfa_log("kullanici")
    st.markdown("## 👥 Kullanıcı Yönetimi")

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
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5, kul_tab5_ekran, kul_tab_tanim = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi","🎨 Ekran Ayarları","⚙️ Tanımlar"])
    elif _surum_yetkisi:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5, kul_tab5_ekran, kul_tab_tanim = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi","🎨 Ekran Ayarları","⚙️ Tanımlar"])
    else:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5_ekran, kul_tab_tanim = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🎨 Ekran Ayarları","⚙️ Tanımlar"])
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
            if st.button("🔑 Şifreyi Güncelle",use_container_width=True):
                if s1 and s1==s2:
                    ok_s = db_update("kullanicilar",{"sifre":s1},"id",int(s_sec.split("]")[0].replace("[","")))
                    try: db_read.clear()
                    except: pass
                    st.success("✅ Şifre güncellendi!")
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
                    yetki = "tam" if tam else _kj.dumps(secili_m)
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
                            try:
                                # Sadece temel kolonlarla dene
                                sb_k.table("kullanicilar").insert(veri).execute()
                                st.success(f"✅ '{yk_kadi}' eklendi! (Ek bilgiler için Supabase'e kolon ekleyin)")
                                st.rerun()
                            except Exception as e2:
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
            k3_row  = df_kul3[df_kul3["id"]==k3_id].iloc[0]

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

    # ── ⚙️ TANIMLAR TABÜ — AŞAMA & DURUM YÖNETİMİ ───────────────────────────
    with kul_tab_tanim:
        st.markdown("### ⚙️ Aşama & Durum Tanımları")
        _sb_tan = get_sb_client()

        def _tan_liste(tip):
            try:
                if _sb_tan:
                    r = _sb_tan.table("sistem_tanimlar").select("deger").eq("tip",tip).order("sira").execute()
                    return [d["deger"] for d in r.data] if r.data else []
            except: return []

        def _tan_ekle(tip, deger):
            try:
                if _sb_tan:
                    mevcut = _sb_tan.table("sistem_tanimlar").select("sira").eq("tip",tip).order("sira",desc=True).limit(1).execute()
                    sira = (mevcut.data[0]["sira"] + 1) if mevcut.data else 1
                    _sb_tan.table("sistem_tanimlar").insert({"tip":tip,"deger":deger,"sira":sira}).execute()
                    return True
            except: return False

        def _tan_sil(tip, deger):
            try:
                if _sb_tan:
                    _sb_tan.table("sistem_tanimlar").delete().eq("tip",tip).eq("deger",deger).execute()
                    return True
            except: return False

        _ta1, _ta2 = st.columns(2)

        # AŞAMA
        with _ta1:
            st.markdown("**🔄 Aşama Yönetimi**")
            _asama_listesi = _tan_liste("asama")
            _ea1, _ea2 = st.columns([3,1])
            _yeni_asama = _ea1.text_input("", placeholder="Yeni aşama adı...", key="kul_yeni_asama", label_visibility="collapsed")
            if _ea2.button("➕ Ekle", key="kul_asama_ekle", use_container_width=True):
                if _yeni_asama.strip():
                    if _yeni_asama.strip() in _asama_listesi:
                        st.warning("Bu aşama zaten var!")
                    elif _tan_ekle("asama", _yeni_asama.strip()):
                        st.success(f"✅ '{_yeni_asama}' eklendi!"); st.rerun()
            st.caption(f"{len(_asama_listesi)} aşama")
            for _a in _asama_listesi:
                _ac1, _ac2 = st.columns([4,1])
                _ac1.markdown(f"🔸 **{_a}**")
                if _ac2.button("🗑", key=f"asil_{_a}", use_container_width=True, help="Sil"):
                    if _tan_sil("asama", _a):
                        st.success(f"'{_a}' silindi!"); st.rerun()

        # DURUM
        with _ta2:
            st.markdown("**📊 Durum Yönetimi**")
            _durum_listesi = _tan_liste("durum")
            _ed1, _ed2 = st.columns([3,1])
            _yeni_durum = _ed1.text_input("", placeholder="Yeni durum adı...", key="kul_yeni_durum", label_visibility="collapsed")
            if _ed2.button("➕ Ekle", key="kul_durum_ekle", use_container_width=True):
                if _yeni_durum.strip():
                    if _yeni_durum.strip() in _durum_listesi:
                        st.warning("Bu durum zaten var!")
                    elif _tan_ekle("durum", _yeni_durum.strip()):
                        st.success(f"✅ '{_yeni_durum}' eklendi!"); st.rerun()
            st.caption(f"{len(_durum_listesi)} durum")
            for _d in _durum_listesi:
                _dc1, _dc2 = st.columns([4,1])
                _dc1.markdown(f"🔹 **{_d}**")
                if _dc2.button("🗑", key=f"dsil2_{_d}", use_container_width=True, help="Sil"):
                    if _tan_sil("durum", _d):
                        st.success(f"'{_d}' silindi!"); st.rerun()

elif aktif == "rapor":
    sayfa_log("rapor")
    import io as _rio2

    # Veri yükle
    df_rapor = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi=\'0\' OR silindi IS NULL)")
    df_rand_r = db_read("randevular", extra_sql="ORDER BY randevu_tarihi DESC")
    df_tek_r  = db_read("teklifler", order_col="tarih")

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
    _t_fil = _tr[0].selectbox("", ["Tümü","Aktif","Hedef","Pasif"], key="teklif_fil", label_visibility="collapsed")
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
                st.link_button("📱 WhatsApp'ta Aç",f"https://wa.me/{gsm_wa_final}?text={_tq(_wa_txt,safe='')}",use_container_width=True,type="primary")
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
                    _tek_row = df_tek[df_tek["id"]==_tek_id].iloc[0]
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
    _oz_fil = _ozr[0].selectbox("", ["Tümü","Aktif","Hedef","Pasif"], key="oz2_fil", label_visibility="collapsed")
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
            st.link_button("📱 WhatsApp'ta Aç", f"https://wa.me/{_wno}?text={_ozq(_wtxt,safe='')}", use_container_width=True, type="primary")
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
                    _oz_trow = _oz_df_tek2[_oz_df_tek2["id"]==_oz_tid].iloc[0]
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
                    return df[df["firma"].notna() & (df["firma"] != "")]
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

    # ── TÜM ANALİZLER LİSTESİ ────────────────────────────────────────────────
    st.markdown("## 🔍 Müşteri Görüşme Analizi")
    _df_tum = _an_liste()

    if not _df_tum.empty:
        st.markdown("### 📋 Tüm Analizler")
        _f1,_f2,_f3 = st.columns(3)
        _ff = _f1.text_input("Firma ara", key="an_ff", placeholder="firma adı...")
        _fs = _f2.selectbox("Sonuç", ["Tümü","takip edilecek","teklif verildi","anlaşma yapıldı","beklemede","ilgisiz"], key="an_fs")
        _fp = _f3.selectbox("Potansiyel", ["Tümü","çok yüksek","yüksek","orta","düşük","çok düşük"], key="an_fp")
        _dff = _df_tum.copy()
        if _ff: _dff = _dff[_dff["firma"].str.contains(_ff, case=False, na=False)]
        if _fs != "Tümü": _dff = _dff[_dff["sonuc"] == _fs]
        if _fp != "Tümü": _dff = _dff[_dff["potansiyel"] == _fp]
        st.caption(f"{len(_dff)} analiz")

        _pic_map = {"çok yüksek":"🟢","yüksek":"🟢","orta":"🟡","düşük":"🟠","çok düşük":"🔴"}
        # ── PDF ÜRETICI FONKSİYONU ───────────────────────────────────────────
        def _analiz_pdf(_ar):
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.units import cm
                from reportlab.lib.styles import ParagraphStyle
                from reportlab.lib import colors
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
                from reportlab.lib.enums import TA_LEFT, TA_CENTER
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
                def _clean(v): return "—" if str(v or "").strip() in ["","nan","None","—"] else str(v)
                def _pills(txt): return " · ".join([x.strip() for x in str(txt or "").split(",") if x.strip()]) or "—"

                ST_TITLE  = _s("t", fontSize=18, fontName="Helvetica-Bold", leading=22, textColor=colors.HexColor("#0f172a"))
                ST_SECTION= _s("sec", fontSize=11, fontName="Helvetica-Bold", textColor=colors.HexColor("#1d4ed8"), leading=16)
                ST_KEY    = _s("key", fontSize=9,  textColor=colors.HexColor("#64748b"), leading=12)
                ST_VAL    = _s("val", fontSize=10, textColor=colors.HexColor("#1e293b"), leading=14)
                ST_NOTE   = _s("note",fontSize=10, textColor=colors.HexColor("#374151"), leading=16)
                ST_SMALL  = _s("sm",  fontSize=8,  textColor=colors.HexColor("#94a3b8"), leading=11)

                _firma_pdf   = _clean(_ar.get("firma",""))
                _tarih_pdf   = fmt_tarih(_ar.get("tarih",""))
                _pot_pdf     = _clean(_ar.get("potansiyel",""))
                _sonuc_pdf   = _clean(_ar.get("sonuc",""))
                _bek_pdf     = f"{float(_ar.get('bek_ciro',0) or 0):,.0f} TL"
                _ger_pdf     = f"{float(_ar.get('ger_ciro',0) or 0):,.0f} TL"

                # Başlık
                story.append(_p(f"{_firma_pdf}", ST_TITLE))
                story.append(Spacer(1, 4))
                story.append(_p(f"Analiz Tarihi: {_tarih_pdf}  |  Potansiyel: {_pot_pdf}  |  Sonuç: {_sonuc_pdf}", ST_SMALL))
                story.append(HRFlowable(width=W, thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=10, spaceBefore=6))

                # Metrikler
                _met_data = [["Beklenen Ciro","Gerçekleşen","Potansiyel","Sonuç"],
                             [_bek_pdf, _ger_pdf, _pot_pdf, _sonuc_pdf]]
                _met_tbl = Table(_met_data, colWidths=[W/4]*4)
                _met_tbl.setStyle(TableStyle([
                    ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f8fafc")),
                    ("FONTNAME",(0,0),(-1,0),"Helvetica"),
                    ("FONTSIZE",(0,0),(-1,0),8),
                    ("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#64748b")),
                    ("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),
                    ("FONTSIZE",(0,1),(-1,1),11),
                    ("TEXTCOLOR",(0,1),(-1,1),colors.HexColor("#0f172a")),
                    ("ALIGN",(0,0),(-1,-1),"CENTER"),
                    ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ("PADDING",(0,0),(-1,-1),8),
                    ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e2e8f0")),
                    ("ROUNDEDCORNERS",[4,4,4,4]),
                ]))
                story.append(_met_tbl)
                story.append(Spacer(1, 10))

                def _bolum(baslik, satirlar):
                    story.append(_p(baslik, ST_SECTION))
                    story.append(Spacer(1,3))
                    tdata = [[_p(k, ST_KEY), _p(v, ST_VAL)] for k,v in satirlar]
                    t = Table(tdata, colWidths=[3.5*cm, W-3.5*cm])
                    t.setStyle(TableStyle([
                        ("VALIGN",(0,0),(-1,-1),"TOP"),
                        ("LINEBELOW",(0,0),(-1,-1),0.3,colors.HexColor("#f1f5f9")),
                        ("LEFTPADDING",(0,0),(-1,-1),4),
                        ("RIGHTPADDING",(0,0),(-1,-1),4),
                        ("TOPPADDING",(0,0),(-1,-1),5),
                        ("BOTTOMPADDING",(0,0),(-1,-1),5),
                    ]))
                    story.append(t)
                    story.append(Spacer(1,8))

                # 1. Analiz amacı
                _bolge_raw2 = {}
                try:
                    _br2 = _ar.get("bolge","")
                    if _br2: _bolge_raw2 = _pj.loads(_br2) if isinstance(_br2,str) else _br2
                except: pass
                _urun_pdf = _bolge_raw2.get("urun","") if isinstance(_bolge_raw2,dict) else ""

                _bolum("1 — ANALİZ AMACI",[
                    ("Görüşme amacı", _pills(_ar.get("amac",""))),
                    ("Müşteri durumu", _clean(_ar.get("mdurum",""))),
                ])

                # 2. Kaynak & müşteri
                _bolum("2 — KAYNAK & MÜŞTERİ",[
                    ("Firma", _clean(_ar.get("firma",""))),
                    ("Yetkili", _clean(_ar.get("yetkili",""))),
                    ("İletişim", _clean(_ar.get("iletisim",""))),
                    ("Sektör", _clean(_ar.get("sektor",""))),
                    ("Kaynak", _clean(_ar.get("kaynak",""))),
                    ("Gönderi türü", _urun_pdf or _pills(_ar.get("urun",""))),
                ])

                # 3. Bölge tablosu
                story.append(_p("3 — ÜRÜN, HACİM & CİRO", ST_SECTION))
                story.append(Spacer(1,3))
                _bolge_rows2 = []
                if isinstance(_bolge_raw2, dict):
                    _bolge_rows2 = _bolge_raw2.get("satirlar",[])
                elif isinstance(_bolge_raw2, list):
                    _bolge_rows2 = _bolge_raw2
                if _bolge_rows2:
                    _tbl_data = [["Güzergah & Desi","Tip","Adet","Fiyat (TL)","Periyot"]]
                    for _br in _bolge_rows2:
                        _tbl_data.append([
                            str(_br.get("il","") or "—"),
                            str(_br.get("urun","") or "—"),
                            str(_br.get("adet","") or "—"),
                            str(_br.get("ciro","") or "—"),
                            str(_br.get("siklik","") or "—"),
                        ])
                    _bt = Table(_tbl_data, colWidths=[W*0.45,W*0.1,W*0.1,W*0.15,W*0.2])
                    _bt.setStyle(TableStyle([
                        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f8fafc")),
                        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                        ("FONTSIZE",(0,0),(-1,-1),9),
                        ("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#64748b")),
                        ("TEXTCOLOR",(0,1),(-1,-1),colors.HexColor("#1e293b")),
                        ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#e2e8f0")),
                        ("PADDING",(0,0),(-1,-1),6),
                        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ]))
                    story.append(_bt)
                else:
                    story.append(_p("— veri girilmedi", ST_VAL))
                story.append(Spacer(1,8))

                # 4. Beklenti & sonuç
                _bolum("4 — BEKLENTİ & SONUÇ",[
                    ("Beklenti", _pills(_ar.get("beklenti",""))),
                    ("Engel",    _pills(_ar.get("engel",""))),
                    ("Sonuç",    _clean(_ar.get("sonuc",""))),
                    ("Sonraki adım", _pills(_ar.get("sonraki_adim",""))),
                ])

                # 5. Rakip
                _rakip_pdf = []
                try:
                    _rp = _ar.get("rakip","")
                    if _rp: _rakip_pdf = _pj.loads(_rp) if isinstance(_rp,str) else _rp
                except: pass
                story.append(_p("5 — RAKİP", ST_SECTION))
                story.append(Spacer(1,3))
                if _rakip_pdf:
                    _rt = Table([["Rakip Firma","₺/Desi","Güç","Sebep"]] +
                        [[str(r.get("firma","—")),str(r.get("fiyat","—")),str(r.get("durum","—")),str(r.get("sebep","—"))] for r in _rakip_pdf],
                        colWidths=[W*0.3,W*0.15,W*0.15,W*0.4])
                    _rt.setStyle(TableStyle([
                        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f8fafc")),
                        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                        ("FONTSIZE",(0,0),(-1,-1),9),
                        ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#e2e8f0")),
                        ("PADDING",(0,0),(-1,-1),6),
                    ]))
                    story.append(_rt)
                else:
                    story.append(_p("— henüz girilmedi", ST_VAL))
                story.append(Spacer(1,8))

                # 6. Not & özet
                _bolum("6 — NOT & ÖZET",[
                    ("Görüşme notu", _clean(_ar.get("not_alan",""))),
                    ("Takip tarihi", fmt_tarih(_ar.get("takip_tar",""))),
                    ("Olusturan",    _clean(_ar.get("olusturan",""))),
                ])

                doc.build(story)
                buf.seek(0)
                return buf.read()
            except Exception as _pe:
                return None

        # ── KART GÖRÜNÜMÜ ─────────────────────────────────────────────────────
        def _pill_html2(txt, renk="gray"):
            _renkler = {"blue":"#e6f1fb;color:#185fa5","green":"#eaf3de;color:#3b6d11",
                        "red":"#fcebeb;color:#a32d2d","amber":"#faeeda;color:#854f0b",
                        "gray":"#f1f5f9;color:#64748b"}
            _stl = _renkler.get(renk, _renkler["gray"])
            pills = [x.strip() for x in str(txt or "").split(",") if x.strip() and x.strip() not in ["nan","None"]]
            if not pills: return "<span style='color:#94a3b8;font-style:italic'>— henüz girilmedi</span>"
            return "".join([f"<span style='display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;background:{_stl.split(';')[0].replace('background:','')};color:{_stl.split('color:')[1]};margin:2px'>{p}</span>" for p in pills])

        def _val_html(v):
            s = str(v or "").strip()
            if s in ["","nan","None","—"]: return "<span style='color:#94a3b8;font-style:italic'>— henüz girilmedi</span>"
            return f"<span style='color:var(--color-text-primary,#1e293b)'>{s}</span>"

        _pot_renk = {"çok yüksek":"#22c55e","yüksek":"#22c55e","orta":"#f59e0b","düşük":"#ef4444","çok düşük":"#ef4444"}

        for _ai, (_, _ar) in enumerate(_dff.iterrows()):
            _ar_firma   = str(_ar.get("firma","") or "?")
            _ar_pot     = str(_ar.get("potansiyel","") or "")
            _ar_sonuc   = str(_ar.get("sonuc","") or "")
            _ar_tarih   = fmt_tarih(_ar.get("tarih",""))
            _dot_clr    = _pot_renk.get(_ar_pot,"#94a3b8")
            _bek_v      = float(_ar.get("bek_ciro",0) or 0)
            _ger_v      = float(_ar.get("ger_ciro",0) or 0)

            # Bölge JSON parse
            try:
                _br_raw = _ar.get("bolge","")
                _br_obj = __import__("json").loads(_br_raw) if isinstance(_br_raw,str) and _br_raw else _br_raw
            except: _br_obj = {}
            _br_rows = _br_obj.get("satirlar",[]) if isinstance(_br_obj,dict) else (_br_obj if isinstance(_br_obj,list) else [])
            _urun_v  = _br_obj.get("urun","") if isinstance(_br_obj,dict) else ""

            # Bölge tablosu HTML
            _tbl_rows_html = ""
            for _brow in _br_rows:
                _brow_il   = str(_brow.get("il","") or "—")
                _brow_urun = str(_brow.get("urun","") or "—")
                _brow_adet = str(_brow.get("adet","") or "—")
                _brow_ciro = str(_brow.get("ciro","") or "—")
                _brow_sik  = str(_brow.get("siklik","") or "—")
                _pu = "green" if _brow_urun=="palet" else "amber" if _brow_urun in ["dorse","TIR/komple"] else "blue"
                _tbl_rows_html += f"""<tr>
                  <td style='padding:8px 16px;border-bottom:0.5px solid #f1f5f9;font-size:12px;color:#1e293b'>{_brow_il}</td>
                  <td style='padding:8px 16px;border-bottom:0.5px solid #f1f5f9'>{_pill_html2(_brow_urun,_pu)}</td>
                  <td style='padding:8px 16px;border-bottom:0.5px solid #f1f5f9;font-size:12px;color:#1e293b;text-align:center'>{_brow_adet}</td>
                  <td style='padding:8px 16px;border-bottom:0.5px solid #f1f5f9;font-size:12px;color:#1e293b;text-align:right'>{_brow_ciro}</td>
                  <td style='padding:8px 16px;border-bottom:0.5px solid #f1f5f9;font-size:12px;color:#64748b'>{_brow_sik}</td>
                </tr>"""

            _rakip_rows_html = ""
            try:
                _rp_raw = _ar.get("rakip","")
                _rp_lst = __import__("json").loads(_rp_raw) if isinstance(_rp_raw,str) and _rp_raw else []
                for _rr in _rp_lst:
                    _rg = "red" if _rr.get("durum","")=="güçlü" else "amber" if _rr.get("durum","")=="orta" else "green"
                    _rakip_rows_html += f"<tr><td style='padding:7px 16px;font-size:12px;border-bottom:0.5px solid #f1f5f9'>{_rr.get('firma','—')}</td><td style='padding:7px 16px;font-size:12px;border-bottom:0.5px solid #f1f5f9;text-align:right'>{_rr.get('fiyat','—')}</td><td style='padding:7px 16px;border-bottom:0.5px solid #f1f5f9'>{_pill_html2(_rr.get('durum',''),_rg)}</td><td style='padding:7px 16px;font-size:12px;border-bottom:0.5px solid #f1f5f9;color:#64748b'>{_rr.get('sebep','—')}</td></tr>"
            except: pass

            _ar_sonraki_txt = _pills(_ar.get("sonraki_adim",""))
            _ar_takip_txt   = fmt_tarih(_ar.get("takip_tar",""))
            if _ar.get("sonraki_adim","") or _ar.get("takip_tar",""):
                _sonraki_blok = f"<div style='display:flex;align-items:center;gap:8px;padding:10px 18px;font-size:13px;color:#64748b;border-bottom:0.5px solid #f1f5f9'>📅 Sonraki adım: <strong style='color:#0f172a'>{_ar_sonraki_txt}</strong> → <strong style='color:#0f172a'>{_ar_takip_txt}</strong></div>"
            else:
                _sonraki_blok = ""

            _kart_html = f"""
<div style='background:white;border:0.5px solid #e2e8f0;border-radius:12px;overflow:hidden;margin-bottom:14px;font-family:-apple-system,sans-serif'>

  <div style='display:flex;align-items:center;justify-content:space-between;padding:14px 18px;gap:12px;flex-wrap:wrap'>
    <div style='display:flex;align-items:center;gap:10px'>
      <span style='width:10px;height:10px;border-radius:50%;background:{_dot_clr};display:inline-block;flex-shrink:0'></span>
      <span style='font-size:15px;font-weight:500;color:#0f172a'>{_ar_firma}</span>
      <span style='font-size:12px;color:#94a3b8'>{_ar_tarih}</span>
    </div>
    <div style='display:flex;gap:6px;flex-wrap:wrap'>
      <span style='font-size:11px;padding:3px 10px;border-radius:20px;font-weight:500;background:#eaf3de;color:#3b6d11'>{_ar_pot} potansiyel</span>
      <span style='font-size:11px;padding:3px 10px;border-radius:20px;font-weight:500;background:#e6f1fb;color:#185fa5'>{_ar_sonuc}</span>
    </div>
  </div>

  <div style='display:grid;grid-template-columns:repeat(4,1fr);border-top:0.5px solid #e2e8f0'>
    <div style='padding:12px 16px;border-right:0.5px solid #e2e8f0'><div style='font-size:11px;color:#64748b;margin-bottom:4px'>Potansiyel</div><div style='font-size:17px;font-weight:500;color:#0f172a'>{_ar_pot.title() if _ar_pot else "—"}</div></div>
    <div style='padding:12px 16px;border-right:0.5px solid #e2e8f0'><div style='font-size:11px;color:#64748b;margin-bottom:4px'>Beklenen ciro</div><div style='font-size:17px;font-weight:500;color:#0f172a'>{_bek_v:,.0f} ₺</div></div>
    <div style='padding:12px 16px;border-right:0.5px solid #e2e8f0'><div style='font-size:11px;color:#64748b;margin-bottom:4px'>Gerçekleşen</div><div style='font-size:17px;font-weight:500;color:#0f172a'>{_ger_v:,.0f} ₺</div></div>
    <div style='padding:12px 16px'><div style='font-size:11px;color:#64748b;margin-bottom:4px'>Sonuç</div><div style='font-size:14px;font-weight:500;color:#0f172a'>{_ar_sonuc.title() if _ar_sonuc else "—"}</div></div>
  </div>

  <div style='border-top:0.5px solid #e2e8f0'>
    <div style='padding:9px 18px;background:#f8fafc;font-size:11px;font-weight:500;color:#64748b;border-bottom:0.5px solid #e2e8f0'>① ANALİZ AMACI</div>
    <div style='display:flex;padding:9px 18px;border-bottom:0.5px solid #f1f5f9'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Analiz amacı</div><div style='flex:1'>{_pill_html2(_ar.get("amac",""),"blue")}</div></div>
    <div style='display:flex;padding:9px 18px'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Müşteri durumu</div><div style='flex:1'>{_pill_html2(_ar.get("mdurum",""),"gray")}</div></div>
  </div>

  <div style='border-top:0.5px solid #e2e8f0'>
    <div style='padding:9px 18px;background:#f8fafc;font-size:11px;font-weight:500;color:#64748b;border-bottom:0.5px solid #e2e8f0'>② KAYNAK & MÜŞTERİ</div>
    <div style='display:flex;padding:9px 18px;border-bottom:0.5px solid #f1f5f9'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Firma</div><div style='flex:1;font-size:13px;color:#1e293b'>{_ar_firma}</div></div>
    <div style='display:flex;padding:9px 18px;border-bottom:0.5px solid #f1f5f9'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Yetkili</div><div style='flex:1;font-size:13px'>{_val_html(_ar.get("yetkili",""))}</div></div>
    <div style='display:flex;padding:9px 18px;border-bottom:0.5px solid #f1f5f9'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Sektör</div><div style='flex:1;font-size:13px'>{_val_html(_ar.get("sektor",""))}</div></div>
    <div style='display:flex;padding:9px 18px;border-bottom:0.5px solid #f1f5f9'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Kaynak</div><div style='flex:1'>{_pill_html2(_ar.get("kaynak",""),"gray")}</div></div>
    <div style='display:flex;padding:9px 18px'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Gönderi türü</div><div style='flex:1'>{_pill_html2(_urun_v or _ar.get("urun",""),"green")}</div></div>
  </div>

  <div style='border-top:0.5px solid #e2e8f0'>
    <div style='padding:9px 18px;background:#f8fafc;font-size:11px;font-weight:500;color:#64748b;border-bottom:0.5px solid #e2e8f0'>③ ÜRÜN, HACİM & CİRO</div>
    {'<table style="width:100%;border-collapse:collapse"><thead><tr><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;text-align:left;border-bottom:0.5px solid #e2e8f0">Güzergah & Desi</th><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;text-align:left;border-bottom:0.5px solid #e2e8f0">Tip</th><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;text-align:center;border-bottom:0.5px solid #e2e8f0">Adet</th><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;text-align:right;border-bottom:0.5px solid #e2e8f0">Fiyat (₺)</th><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;border-bottom:0.5px solid #e2e8f0">Periyot</th></tr></thead><tbody>' + _tbl_rows_html + '</tbody></table>' if _tbl_rows_html else '<div style="padding:12px 18px;font-size:12px;color:#94a3b8;font-style:italic">— henüz girilmedi</div>'}
  </div>

  <div style='border-top:0.5px solid #e2e8f0'>
    <div style='padding:9px 18px;background:#f8fafc;font-size:11px;font-weight:500;color:#64748b;border-bottom:0.5px solid #e2e8f0'>④ BEKLENTİ & SONUÇ</div>
    <div style='display:flex;padding:9px 18px;border-bottom:0.5px solid #f1f5f9'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Beklenti</div><div style='flex:1'>{_pill_html2(_ar.get("beklenti",""),"blue")}</div></div>
    <div style='display:flex;padding:9px 18px;border-bottom:0.5px solid #f1f5f9'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Engel</div><div style='flex:1'>{_pill_html2(_ar.get("engel",""),"red")}</div></div>
    <div style='display:flex;padding:9px 18px'><div style='width:140px;flex-shrink:0;font-size:12px;color:#64748b'>Sonuç</div><div style='flex:1'>{_pill_html2(_ar.get("sonuc",""),"blue")}</div></div>
  </div>

  <div style='border-top:0.5px solid #e2e8f0'>
    <div style='padding:9px 18px;background:#f8fafc;font-size:11px;font-weight:500;color:#64748b;border-bottom:0.5px solid #e2e8f0'>⑤ RAKİP</div>
    {'<table style="width:100%;border-collapse:collapse"><thead><tr><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;border-bottom:0.5px solid #e2e8f0">Mevcut Taşıyıcı</th><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;border-bottom:0.5px solid #e2e8f0;text-align:right">Fiyat</th><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;border-bottom:0.5px solid #e2e8f0">Güç</th><th style="padding:7px 16px;background:#f8fafc;font-size:11px;color:#64748b;font-weight:500;border-bottom:0.5px solid #e2e8f0">Sebep</th></tr></thead><tbody>' + _rakip_rows_html + '</tbody></table>' if _rakip_rows_html else '<div style="padding:12px 18px;font-size:12px;color:#94a3b8;font-style:italic">— henüz girilmedi</div>'}
  </div>

  <div style='border-top:0.5px solid #e2e8f0'>
    <div style='padding:9px 18px;background:#f8fafc;font-size:11px;font-weight:500;color:#64748b;border-bottom:0.5px solid #e2e8f0'>⑥ NOT & ÖZET</div>
    {f"<div style='padding:12px 18px;font-size:13px;color:#374151;line-height:1.6;border-bottom:0.5px solid #f1f5f9'>{_val_html(_ar.get('not_alan',''))}</div>"}
    {_sonraki_blok}
  </div>

</div>"""

            st.markdown(_kart_html, unsafe_allow_html=True)

            # Aksiyon butonları
            _kb1,_kb2,_kb3,_kb4,_kb5,_kb6 = st.columns(6)
            if _kb1.button("✏️ Düzenle", key=f"duz_{_ai}", use_container_width=True):
                st.session_state["an_duzenle_firma"] = _ar_firma
                _ik2 = f"an_init_{_ar_firma}"
                for _kk in [_ik2,"an_fiyat_rows","an_bolge_rows","an_avm_rows","an_rakip_rows"]:
                    if _kk in st.session_state: del st.session_state[_kk]
                for _pk in list(st.session_state.keys()):
                    if _pk.endswith("_custom"): del st.session_state[_pk]
                st.rerun()
            _tel2 = str(_ar.get("iletisim","") or "").replace(" ","").replace("-","")
            if _tel2 and "@" not in _tel2:
                if _tel2.startswith("0"): _tel2 = "90"+_tel2[1:]
                _kb2.markdown(f"<a href='https://wa.me/{_tel2}' target='_blank'><button style='width:100%;padding:6px;font-size:11px;background:#25d366;color:white;border:none;border-radius:6px;cursor:pointer'>💬 WA</button></a>", unsafe_allow_html=True)
            if _kb3.button("📄 Spot", key=f"tek_{_ai}", use_container_width=True):
                st.session_state["aktif_tab"] = "teklif"
                st.session_state["teklif_musteri_onsel"] = _ar_firma
                st.rerun()
            if _kb4.button("⭐ Özel", key=f"oztk_{_ai}", use_container_width=True):
                st.session_state["aktif_tab"] = "ozel_teklif"
                st.session_state["teklif_musteri_onsel"] = _ar_firma
                st.rerun()
            # PDF indir
            _pdf_bytes = _analiz_pdf(_ar)
            if _pdf_bytes:
                _kb5.download_button("⬇️ PDF", data=_pdf_bytes,
                    file_name=f"analiz_{_ar_firma[:20].replace(' ','_')}.pdf",
                    mime="application/pdf", key=f"pdf_{_ai}", use_container_width=True)
            if _kb6.button("🗑 Sil", key=f"sil_{_ai}", use_container_width=True):
                if _an_sil(_ar_firma): st.success("Silindi!"); st.rerun()
            st.markdown("---")

        st.divider()
        _sc1,_sc2,_sc3,_sc4,_sc5 = st.columns(5)
        _sc1.metric("Toplam", len(_df_tum))
        _sc2.metric("Yüksek Pot.", len(_df_tum[_df_tum["potansiyel"].isin(["yüksek","çok yüksek"])]))
        _sc3.metric("Takip Bekleyen", len(_df_tum[_df_tum["sonuc"]=="takip edilecek"]))
        _sc4.metric("Anlaşma", len(_df_tum[_df_tum["sonuc"]=="anlaşma yapıldı"]))
        try: _sc5.metric("Beklenen Ciro", f"{_df_tum['bek_ciro'].sum():,.0f} ₺")
        except: pass
        st.divider()

    # ── YENİ / DÜZENLE FORMU ─────────────────────────────────────────────────
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

        # Başlık + düzenle/sil
        _hc1, _hc2 = st.columns([4,1])
        with _hc1:
            if _duzenle:
                st.success(f"✅ **{_firma}** — kayıtlı analiz düzenleniyor")
            else:
                st.info(f"🆕 **{_firma}** — yeni analiz")
        with _hc2:
            if _duzenle:
                if st.button("🗑 Analizi Sil", use_container_width=True, key="an_sil_hdr"):
                    if _an_sil(_firma):
                        for _kk in [_ik,"an_fiyat_rows","an_bolge_rows","an_avm_rows","an_rakip_rows"]:
                            if _kk in st.session_state: del st.session_state[_kk]
                        st.success("Silindi!"); st.rerun()

        # Session init
        if _ik not in st.session_state:
            _bolge_raw = _mvj("bolge")
            if isinstance(_bolge_raw, dict):
                _bolge_init     = _bolge_raw.get("satirlar", [])
                _yetkili_ek_init= _bolge_raw.get("yetkili_ek", [])
                _urun_init      = [x.strip() for x in _bolge_raw.get("urun","").split(",") if x.strip()]
                _kargo_init     = [x.strip() for x in _bolge_raw.get("kargo","").split(",") if x.strip()]
                _fiyattur_init  = [x.strip() for x in _bolge_raw.get("fiyattur","").split(",") if x.strip()]
                _odeme_init     = [x.strip() for x in _bolge_raw.get("odeme","").split(",") if x.strip()]
            else:
                _bolge_init     = _bolge_raw if isinstance(_bolge_raw, list) else []
                _yetkili_ek_init= []
                _urun_init      = _mvl("urun") or ["koli"]
                _kargo_init     = _mvl("kargo")
                _fiyattur_init  = _mvl("teklif_tur")
                _odeme_init     = _mvl("odeme")

            for _k,_d in [
                ("an_t_amac",     _mvl("amac")),
                ("an_t_mdurum",   _mvl("mdurum") or ["yeni"]),
                ("an_t_kaynak",   _mvl("kaynak")),
                ("an_t_urun",     _urun_init),
                ("an_t_kargo",    _kargo_init),
                ("an_t_fiyattur", _fiyattur_init),
                ("an_t_odeme",    _odeme_init),
                ("an_t_beklenti", _mvl("beklenti")),
                ("an_t_engel",    _mvl("engel")),
                ("an_t_sonuc",    _mvl("sonuc") or ["takip edilecek"]),
                ("an_t_sonraki",  _mvl("sonraki_adim")),
                ("an_t_sik",      _mvl("sik")),
                ("an_t_karar",    _mvl("karar") or ["yetkili kendisi"]),
                ("an_t_sure",     _mvl("sure") or ["belirsiz"]),
                ("an_t_pot",      _mvl("potansiyel") or ["orta"]),
            ]:
                st.session_state[_k] = _d
            st.session_state["an_bolge_rows"]   = _bolge_init or [{"il":"","urun":"koli","adet":"","ciro":"","siklik":"haftalık"}]
            st.session_state["an_rakip_rows"]   = _mvj("rakip") or [{"firma":"","fiyat":"","durum":"orta","sebep":""}]
            st.session_state["an_fiyat_rows"]   = []
            st.session_state["an_yetkili_rows"] = _yetkili_ek_init
            st.session_state[_ik] = True

        # ── WIZARD FORM ───────────────────────────────────────────────────────
        _STEPS = ["🎯 Analiz Amacı","🔍 Kaynak & Müşteri","📦 Ürün & Ciro","💬 Beklenti & Sonuç","⚔️ Rakip","💡 Not & Özet"]
        _step = st.session_state.get("an_wizard_step", 0)

        # İlerleme çubuğu
        _prog_cols = st.columns(len(_STEPS))
        for _pi, _pn in enumerate(_STEPS):
            _done = _pi < _step
            _active = _pi == _step
            _clr = "#16a34a" if _done else ("#1d4ed8" if _active else "#e2e8f0")
            _tc  = "white" if (_done or _active) else "#94a3b8"
            _prog_cols[_pi].markdown(
                f"<div style='text-align:center;padding:6px 4px;border-radius:8px;"
                f"background:{_clr};color:{_tc};font-size:11px;font-weight:500'>"
                f"{'✓' if _done else str(_pi+1)}  {_pn.split(' ',1)[1] if ' ' in _pn else _pn}</div>",
                unsafe_allow_html=True)
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        def _btn_an(key, opts, tek=False, label=""):
            if label: st.caption(label)
            sel = list(st.session_state.get(key, []))
            customs = st.session_state.get(f"{key}_custom", [])
            all_opts = list(opts) + [c for c in customs if c not in opts]
            cols = st.columns(len(all_opts) + 1)
            changed = False
            for i, o in enumerate(all_opts):
                is_on = o in sel
                if cols[i].button(o, key=f"{key}_{i}", type="primary" if is_on else "secondary", use_container_width=True):
                    if tek: sel = [o]
                    elif is_on: sel.remove(o)
                    else: sel.append(o)
                    st.session_state[key] = sel; changed = True
            if cols[-1].button("＋", key=f"{key}_plus", use_container_width=True):
                st.session_state[f"{key}_add_open"] = True
            if st.session_state.get(f"{key}_add_open"):
                _ac1,_ac2,_ac3 = st.columns([3,1,1])
                _nv = _ac1.text_input("",placeholder="Yeni seçenek...",key=f"{key}_add_inp",label_visibility="collapsed")
                if _ac2.button("Ekle",key=f"{key}_add_ok",use_container_width=True):
                    if _nv.strip():
                        _cl = st.session_state.get(f"{key}_custom",[])
                        if _nv.strip() not in _cl: _cl.append(_nv.strip())
                        st.session_state[f"{key}_custom"] = _cl
                        sel.append(_nv.strip()); st.session_state[key] = sel
                    st.session_state.pop(f"{key}_add_open",None); st.rerun()
                if _ac3.button("İptal",key=f"{key}_add_no",use_container_width=True):
                    st.session_state.pop(f"{key}_add_open",None); st.rerun()
            if changed: st.rerun()

        # ── ADIM 0 ───────────────────────────────────────────────────────────
        if _step == 0:
            st.markdown("#### 🎯 Analiz Amacı")
            _btn_an("an_t_amac",["yeni müşteri kazanım","zam görüşmesi","nezaket ziyareti","erken potansiyel","kayıp müşteri geri kazanım","mevcut müşteri analizi","rakip takibi","pazar araştırması"],label="Görüşme sebebi")
            _btn_an("an_t_mdurum",["yeni","mevcut","eski","rakip firmanın müşterisi"],tek=True,label="Müşteri durumu")
            _xc1,_xc2,_xc3 = st.columns(3)
            _an_bek = _xc1.text_input("Beklenen ciro (₺/ay)",key="an_bek_ciro",value=str(int(float(_mv("bek_ciro",0) or 0))) if _mv("bek_ciro",0) else "",placeholder="₺/ay")
            _an_ger = _xc2.text_input("Gerçekleşen ciro (₺/ay)",key="an_ger_ciro",value=str(int(float(_mv("ger_ciro",0) or 0))) if _mv("ger_ciro",0) else "",placeholder="₺/ay")
            try:
                _bv2=float((_an_bek or "0").replace(".","").replace(",",".")); _gv2=float((_an_ger or "0").replace(".","").replace(",","."))
                _fv2=f"{'+'if _gv2>=_bv2 else ''}{_gv2-_bv2:,.0f} ₺" if _bv2>0 and _gv2>0 else ""
            except: _fv2=""
            _xc3.text_input("Fark",value=_fv2,disabled=True,key="an_fark")
        else:
            _an_bek = str(int(float(_mv("bek_ciro",0) or 0))) if _mv("bek_ciro",0) else ""
            _an_ger = str(int(float(_mv("ger_ciro",0) or 0))) if _mv("ger_ciro",0) else ""

        # ── ADIM 1 ───────────────────────────────────────────────────────────
        if _step == 1:
            st.markdown("#### 🔍 Kaynak & Müşteri")
            _k1,_k2,_k3 = st.columns(3)
            _an_tarih    = _k1.date_input("Görüşme tarihi",key="an_tarih")
            _an_saat     = _k2.time_input("Saat",key="an_saat")
            _an_temsilci = _k3.text_input("Temsilci",value=_mv("olusturan",st.session_state.get("kullanici","")),key="an_temsilci")
            _btn_an("an_t_kaynak",["soğuk arama","referans","linkedin","internet/forum","ziyaret","fuar","sosyal medya","eski müşteri"],label="Nereden bulundu?")
            _k6,_k7,_k8 = st.columns(3)
            _auto_tel2 = str(_cari_row.get("gsm","") or "") if _cari_row is not None else ""
            _an_yetkili  = _k6.text_input("Yetkili / Ünvan",value=_mv("yetkili",""),key="an_yetkili",placeholder="Ad Soyad")
            _an_iletisim = _k7.text_input("Tel / E-posta",value=_mv("iletisim",_auto_tel2),key="an_iletisim",placeholder="05xx / mail@...")
            _sl = ["--","Tekstil","Gıda","Otomotiv","Elektronik","İnşaat","E-ticaret","AVM/Perakende","Kimya","Mobilya","Medikal","Kozmetik","Tarım","Diğer"]
            _an_sektor = _k8.selectbox("Sektör",_sl,index=_sl.index(_mv("sektor","--")) if _mv("sektor","--") in _sl else 0,key="an_sektor")

            # ── Ek yetkili satırları (+ ile eklenebilir) ──────────────────
            st.caption("Ek Yetkili / Kişi")
            _yk_rows = st.session_state.get("an_yetkili_rows", [])
            _sl2 = ["--","Tekstil","Gıda","Otomotiv","Elektronik","İnşaat","E-ticaret","AVM/Perakende","Kimya","Mobilya","Medikal","Kozmetik","Tarım","Diğer"]
            for _yi in range(len(_yk_rows)):
                _yr = _yk_rows[_yi]
                _yc = st.columns([2,2,2,0.3])
                _yk_rows[_yi]["yetkili"]  = _yc[0].text_input("",value=_yr.get("yetkili",""),key=f"yk_y_{_yi}",placeholder="Ad Soyad · Ünvan",label_visibility="collapsed")
                _yk_rows[_yi]["iletisim"] = _yc[1].text_input("",value=_yr.get("iletisim",""),key=f"yk_i_{_yi}",placeholder="Tel / E-posta",label_visibility="collapsed")
                _yk_rows[_yi]["sektor"]   = _yc[2].selectbox("",_sl2,index=_sl2.index(_yr.get("sektor","--")) if _yr.get("sektor","--") in _sl2 else 0,key=f"yk_s_{_yi}",label_visibility="collapsed")
                if _yc[3].button("✕",key=f"yk_del_{_yi}"):
                    _yk_rows.pop(_yi); st.session_state["an_yetkili_rows"]=_yk_rows; st.rerun()
            st.session_state["an_yetkili_rows"] = _yk_rows
            if st.button("＋ Yetkili / Kişi Ekle", key="yk_ekle"):
                st.session_state["an_yetkili_rows"].append({"yetkili":"","iletisim":"","sektor":"--"}); st.rerun()
        else:
            _an_tarih=date.today(); _an_saat=None; _an_temsilci=_mv("olusturan","")
            _auto_tel2 = str(_cari_row.get("gsm","") or "") if _cari_row is not None else ""
            _an_yetkili=_mv("yetkili",""); _an_iletisim=_mv("iletisim",_auto_tel2); _an_sektor=_mv("sektor","--")

        # ── ADIM 2 ───────────────────────────────────────────────────────────
        if _step == 2:
            st.markdown("#### 📦 Ürün, Hacim & Ciro")
            _btn_an("an_t_urun",["koli","palet","parsiyel","TIR/komple","soğuk zincir","ADR/tehlikeli","ambar kargo","dış nakliye"],label="Gönderi türü")
            st.caption("İl bazlı hacim & ciro")
            _bolge_rows = st.session_state.get("an_bolge_rows",[{"il":"","urun":"koli","adet":"","ciro":"","siklik":"haftalık"}])
            _urun_opts_t=["koli","palet","dorse","ambar","AVM"]; _sikl_opts_t=["haftalık","günlük","aylık","düzensiz"]
            for _bi in range(len(_bolge_rows)):
                _br=_bolge_rows[_bi]; _bc=st.columns([2,1,1,1,1,0.3])
                _bolge_rows[_bi]["il"]     = _bc[0].text_input("",value=_br.get("il",""),key=f"bil_{_bi}",placeholder="İl",label_visibility="collapsed")
                _bolge_rows[_bi]["urun"]   = _bc[1].selectbox("",_urun_opts_t,index=_urun_opts_t.index(_br.get("urun","koli")) if _br.get("urun","koli") in _urun_opts_t else 0,key=f"bur_{_bi}",label_visibility="collapsed")
                _bolge_rows[_bi]["adet"]   = _bc[2].text_input("",value=_br.get("adet",""),key=f"bad_{_bi}",placeholder="adet/ay",label_visibility="collapsed")
                _bolge_rows[_bi]["ciro"]   = _bc[3].text_input("",value=_br.get("ciro",""),key=f"bci_{_bi}",placeholder="₺",label_visibility="collapsed")
                _bolge_rows[_bi]["siklik"] = _bc[4].selectbox("",_sikl_opts_t,index=_sikl_opts_t.index(_br.get("siklik","haftalık")) if _br.get("siklik","haftalık") in _sikl_opts_t else 0,key=f"bsk_{_bi}",label_visibility="collapsed")
                if _bc[5].button("✕",key=f"bdel_{_bi}") and len(_bolge_rows)>1:
                    _bolge_rows.pop(_bi); st.session_state["an_bolge_rows"]=_bolge_rows; st.rerun()
            st.session_state["an_bolge_rows"]=_bolge_rows
            if st.button("+ Satır ekle",key="bolge_ekle"):
                st.session_state["an_bolge_rows"].append({"il":"","urun":"koli","adet":"","ciro":"","siklik":"haftalık"}); st.rerun()
            _btn_an("an_t_fiyattur",["spot","anlaşmalı","ihale","paket fiyat","yıllık kontrat"],label="Fiyat teklif türü")
            _btn_an("an_t_odeme",["nakit","çek","havale","vadeli","kredi kartı"],label="Ödeme türü")

        # ── ADIM 3 ───────────────────────────────────────────────────────────
        if _step == 3:
            st.markdown("#### 💬 Beklenti, Engel & Sonuç")
            _btn_an("an_t_beklenti",["düşük fiyat","uzun vade","spot fiyat","hız/dakiklik","hizmet kalitesi","alım saati","bölge kapsamı","takip sistemi","sigorta","AVM girişi"],label="Müşteri beklentisi")
            _btn_an("an_t_engel",["fiyat","vade","rakip teklifi","karar verici","bölge eksikliği","güven","alışkanlık"],label="Engel")
            _btn_an("an_t_sonuc",["takip edilecek","teklif verildi","beklemede","ilgisiz","randevu verildi","anlaşma yapıldı"],tek=True,label="Sonuç")
            _btn_an("an_t_sonraki",["fiyat teklifi gönder","tekrar ara","randevu al","numune gönder","sözleşme hazırla","demo yap"],label="Sonraki adım")
            _be1,_be2=st.columns(2)
            _an_fbek=_be1.text_input("Fiyat beklentisi",value=_mv("fiyat_bek",""),key="an_fiyat_bek",placeholder="₺/desi")
            _an_ozel=_be2.text_input("Özel istek",value=_mv("ozel_istek",""),key="an_ozel",placeholder="varsa yaz...")
        else:
            _an_fbek=_mv("fiyat_bek",""); _an_ozel=_mv("ozel_istek","")

        # ── ADIM 4 ───────────────────────────────────────────────────────────
        if _step == 4:
            st.markdown("#### ⚔️ Rakip & Sorunlar")
            st.caption("Rakip Firma | ₺/desi | Güç | Sebep")
            _rakip_rows=st.session_state.get("an_rakip_rows",[{"firma":"","fiyat":"","durum":"orta","sebep":""}])
            _rd=["güçlü","orta","zayıf"]
            for _ri in range(len(_rakip_rows)):
                _rs=_rakip_rows[_ri]; _rc=st.columns([2,1,1,2,0.3])
                _rakip_rows[_ri]["firma"]=_rc[0].text_input("",value=_rs.get("firma",""),key=f"rfirma_{_ri}",placeholder="rakip",label_visibility="collapsed")
                _rakip_rows[_ri]["fiyat"]=_rc[1].text_input("",value=_rs.get("fiyat",""),key=f"rfiyat_{_ri}",placeholder="₺/desi",label_visibility="collapsed")
                _rakip_rows[_ri]["durum"]=_rc[2].selectbox("",_rd,index=_rd.index(_rs.get("durum","orta")) if _rs.get("durum","orta") in _rd else 1,key=f"rdurum_{_ri}",label_visibility="collapsed")
                _rakip_rows[_ri]["sebep"]=_rc[3].text_input("",value=_rs.get("sebep",""),key=f"rsebep_{_ri}",placeholder="sebep",label_visibility="collapsed")
                if _rc[4].button("✕",key=f"rdel_{_ri}") and len(_rakip_rows)>1:
                    _rakip_rows.pop(_ri); st.session_state["an_rakip_rows"]=_rakip_rows; st.rerun()
            st.session_state["an_rakip_rows"]=_rakip_rows
            if st.button("+ Rakip ekle",key="rakip_ekle"):
                st.session_state["an_rakip_rows"].append({"firma":"","fiyat":"","durum":"orta","sebep":""}); st.rerun()
            _btn_an("an_t_sik",["hasar","geç teslimat","fiyat yüksek","iletişim zayıf","takip yok","kayıp kargo","AVM girişi yok"],label="Müşteri şikayetleri")

        # ── ADIM 5 ───────────────────────────────────────────────────────────
        if _step == 5:
            st.markdown("#### 💡 Not & Değerlendirme")
            _btn_an("an_t_pot",["çok düşük","düşük","orta","yüksek","çok yüksek"],tek=True,label="Potansiyel")
            _btn_an("an_t_karar",["yetkili kendisi","üst yönetim","komite","bilinmiyor"],tek=True,label="Karar verici")
            _btn_an("an_t_sure",["acil (bu hafta)","kısa (1 ay)","uzun (3+ ay)","belirsiz"],tek=True,label="Karar süresi")
            _an_not=st.text_area("Görüşme notu",value=_mv("not_alan",""),key="an_not",placeholder="Görüşme detaylarını yaz...",height=90)
            _nc1,_nc2=st.columns(2)
            _an_takip  =_nc1.date_input("Takip tarihi",key="an_takip")
            _an_sonraki=_nc2.text_input("Sonraki adım notu",value=_mv("sonraki_adim",""),key="an_sonraki",placeholder="isteğe bağlı...")
            st.divider()
            st.markdown("**📋 Özet**")
            _oz1,_oz2,_oz3=st.columns(3)
            _oz1.metric("Potansiyel",(st.session_state.get("an_t_pot") or ["—"])[0])
            _oz2.metric("Sonuç",(st.session_state.get("an_t_sonuc") or ["—"])[0])
            _oz3.metric("Amaç",(st.session_state.get("an_t_amac") or ["—"])[0])
        else:
            _an_not=_mv("not_alan",""); _an_takip=date.today(); _an_sonraki=_mv("sonraki_adim","")

        # ── NAVİGASYON ────────────────────────────────────────────────────────
        st.markdown("<div style='height:16px'></div>",unsafe_allow_html=True)
        _nav1,_nav2,_nav3=st.columns([1,3,1])
        if _step > 0:
            if _nav1.button("← Geri",use_container_width=True,key="an_geri"):
                st.session_state["an_wizard_step"]=_step-1; st.rerun()
        _nav2.markdown(f"<div style='text-align:center;font-size:12px;color:#94a3b8;padding:8px'>Adım {_step+1} / {len(_STEPS)}</div>",unsafe_allow_html=True)
        if _step < len(_STEPS)-1:
            if _nav3.button("İleri →",type="primary",use_container_width=True,key="an_ileri"):
                st.session_state["an_wizard_step"]=_step+1; st.rerun()
        else:
            if _nav3.button(f"💾 {'Güncelle' if _duzenle else 'Kaydet'}",type="primary",use_container_width=True,key="an_kaydet_main"):
                st.session_state["an_kaydet_trigger"]=True; st.rerun()

        _ab1,_ab2,_ab3=st.columns(3)
        if _ab1.button("📄 Spot Teklif",use_container_width=True,key="an_spot"):
            st.session_state["aktif_tab"] = "teklif"
            st.session_state["teklif_musteri_onsel"] = _firma
            st.rerun()
        if _ab2.button("⭐ Özel Teklif",use_container_width=True,key="an_ozel_t"):
            st.session_state["aktif_tab"] = "ozel_teklif"
            st.session_state["teklif_musteri_onsel"] = _firma
            st.rerun()
        if _duzenle and _ab3.button("🗑 Sil",use_container_width=True,key="an_sil_btn"):
            if _an_sil(_firma):
                if _ik in st.session_state: del st.session_state[_ik]
                st.success("Silindi!"); st.rerun()

        # ── KAYDET ────────────────────────────────────────────────────────────
        _gs2=lambda k: ", ".join(st.session_state.get(k,[]))
        _pot_val  =(st.session_state.get("an_t_pot") or ["orta"])[0]
        _sonuc_val=(st.session_state.get("an_t_sonuc") or ["takip edilecek"])[0]
        try: _bv=float((_an_bek or "0").replace(".","").replace(",","."))
        except: _bv=0
        try: _gv=float((_an_ger or "0").replace(".","").replace(",","."))
        except: _gv=0
        if st.session_state.get("an_kaydet_trigger"):
            st.session_state.pop("an_kaydet_trigger",None)
            # urun, kargo, fiyattur, odeme, yetkili_ek → bolge JSON'una dahil et
            _bolge_data = {
                "satirlar":  st.session_state.get("an_bolge_rows",[]),
                "urun":      _gs2("an_t_urun"),
                "kargo":     _gs2("an_t_kargo"),
                "fiyattur":  _gs2("an_t_fiyattur"),
                "odeme":     _gs2("an_t_odeme"),
                "yetkili_ek": st.session_state.get("an_yetkili_rows",[]),
            }
            _veri={
                "yetkili":_an_yetkili,"iletisim":_an_iletisim,"sektor":_an_sektor,
                "amac":_gs2("an_t_amac"),"mdurum":_gs2("an_t_mdurum"),"bek_ciro":_bv,"ger_ciro":_gv,
                "kaynak":_gs2("an_t_kaynak"),
                "beklenti":_gs2("an_t_beklenti"),"engel":_gs2("an_t_engel"),"sonuc":_sonuc_val,
                "sonraki_adim":_gs2("an_t_sonraki") or _an_sonraki,"sik":_gs2("an_t_sik"),
                "potansiyel":_pot_val,"not_alan":_an_not,"takip_tar":str(_an_takip),
                "fiyat_bek":_an_fbek,"ozel_istek":_an_ozel,
                "karar":_gs2("an_t_karar"),"sure":_gs2("an_t_sure"),
                "bolge":_aj.dumps(_bolge_data,ensure_ascii=False),
                "rakip":_aj.dumps(st.session_state.get("an_rakip_rows",[]),ensure_ascii=False),
                "olusturan":st.session_state.get("kullanici",""),
            }
            # Sadece DB'de var olan kolonları gönder
            _GECERLI_KOLONLAR = {"yetkili","iletisim","sektor","amac","mdurum","bek_ciro","ger_ciro",
                "kaynak","beklenti","engel","sonuc","sonraki_adim","sik","potansiyel","not_alan",
                "takip_tar","fiyat_bek","ozel_istek","karar","sure","bolge","rakip","olusturan","firma","tarih"}
            _veri_temiz = {k:v for k,v in _veri.items() if k in _GECERLI_KOLONLAR}
            _ok,_err=_an_kaydet(_firma,_veri_temiz)
            if _ok:
                st.success(f"✅ **{_firma}** analizi {'güncellendi' if _duzenle else 'kaydedildi'}!")
                st.balloons()
                st.session_state.pop("an_wizard_step",None)
                if _ik in st.session_state: del st.session_state[_ik]
                try: db_read.clear()
                except: pass
                st.rerun()
            else:
                st.error(f"❌ Kayıt hatası: {_err}")

    # DB FONKSIYONLARI
    def _sb():
        return get_sb_service() or get_sb_client()

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
                    return df[df["firma"].notna() & (df["firma"] != "")]
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

elif aktif == "detay_cari":
    sayfa_log("detay_cari")
    import json as _dcj

    st.markdown("## 📊 Detay Cari Liste — Çalışma Tablosu")
    st.markdown("<small style='color:#64748b;'>Hücrelere tıklayıp direkt yazabilirsiniz. Çoklu değer için virgülle ayırın (örn: İstanbul, Ankara, Bursa).</small>", unsafe_allow_html=True)

    def _dc_sb():
        return get_sb_service() or get_sb_client()

    @st.cache_data(ttl=60)
    def _dc_getir_tum():
        try:
            sb = get_sb_service() or get_sb_client()
            if sb:
                r = sb.table("musteri_calisma_tablosu").select("*").execute()
                return {row["cari_id"]: row for row in r.data} if r.data else {}
        except Exception as e:
            st.error(f"Veri çekme hatası: {e}")
        return {}

    @st.cache_data(ttl=60)
    def _dc_notlar_getir_tum():
        try:
            sb = get_sb_service() or get_sb_client()
            if sb:
                r = sb.table("cari_aciklamalar").select("*").order("tarih", desc=True).execute()
                if r.data:
                    _gruplu = {}
                    for row in r.data:
                        cid = row.get("cari_id")
                        _gruplu.setdefault(cid, []).append(row)
                    return _gruplu
        except: pass
        return {}

    def _dc_not_ekle(cari_id, firma, metin):
        try:
            sb = _dc_sb()
            if sb:
                sb.table("cari_aciklamalar").insert({
                    "cari_id": cari_id, "cari_adi": firma, "aciklama": metin,
                    "olusturan": st.session_state.get("kullanici","")
                }).execute()
                try: _dc_notlar_getir_tum.clear()
                except: pass
                return True
        except Exception as e:
            st.error(f"Not ekleme hatası: {e}")
        return False

    def _dc_kaydet_satir(cari_id, veri):
        try:
            sb = _dc_sb()
            if sb:
                ex = sb.table("musteri_calisma_tablosu").select("id").eq("cari_id", cari_id).execute()
                if ex.data:
                    sb.table("musteri_calisma_tablosu").update(veri).eq("cari_id", cari_id).execute()
                else:
                    veri["cari_id"] = cari_id
                    sb.table("musteri_calisma_tablosu").insert(veri).execute()
                try: _dc_getir_tum.clear()
                except: pass
                return True
        except Exception as e:
            st.error(f"Kayıt hatası ({veri.get('firma','?')}): {e}")
            return False
        return False

    def _dc_satir_sil(cari_id):
        try:
            sb = _dc_sb()
            if sb:
                sb.table("musteri_calisma_tablosu").delete().eq("cari_id", cari_id).execute()
                try: _dc_getir_tum.clear()
                except: pass
                return True
        except Exception as e:
            st.error(f"Silme hatası: {e}")
        return False

    # VERİ YÜKLE
    _df_cari_dc = get_cari_listesi()
    _dc_kayitlar = _dc_getir_tum()
    _dc_notlar_tum = _dc_notlar_getir_tum()

    if _df_cari_dc.empty:
        st.info("Henüz cari kayıt yok.")
        st.stop()

    # SADECE musteri_calisma_tablosu'na kaydı olan müşteriler
    _dc_kayitli_idler = set(_dc_kayitlar.keys())
    _df_goster = _df_cari_dc[_df_cari_dc["id"].isin(_dc_kayitli_idler)].copy()

    # YENİ MÜŞTERİ EKLE
    with st.expander("➕ Cari Listeden Yeni Müşteri Ekle", expanded=_df_goster.empty):
        _df_henuz_yok = _df_cari_dc[~_df_cari_dc["id"].isin(_dc_kayitli_idler)]
        if _df_henuz_yok.empty:
            st.caption("Tüm cari müşteriler zaten bu listede.")
        else:
            _yeni_opts_cok = [f"[{int(r['id'])}] {r['firma']}" for _,r in _df_henuz_yok.iterrows()]
            _yeni_sec_cok = st.multiselect("Müşteri seç (birden fazla seçebilirsiniz)", _yeni_opts_cok, key="dc_yeni_musteri_sec_cok")

            _ek1, _ek2 = st.columns(2)
            if _ek1.button(f"Seçilenleri Ekle ({len(_yeni_sec_cok)})", key="dc_yeni_musteri_ekle_btn", disabled=len(_yeni_sec_cok)==0):
                _eklenen_say = 0
                for _ys in _yeni_sec_cok:
                    _yeni_cid = int(_ys.split("]")[0].replace("[","").strip())
                    _yeni_firma_adi = str(_df_henuz_yok[_df_henuz_yok["id"]==_yeni_cid].iloc[0]["firma"])
                    if _dc_kaydet_satir(_yeni_cid, {"firma": _yeni_firma_adi, "guncelleyen": st.session_state.get("kullanici","")}):
                        _eklenen_say += 1
                st.success(f"✅ {_eklenen_say} müşteri eklendi!")
                st.rerun()
            if _ek2.button(f"🔁 Tüm Cari Listeyi Ekle ({len(_df_henuz_yok)})", key="dc_tum_ekle_btn"):
                _eklenen_say2 = 0
                for _, _hr in _df_henuz_yok.iterrows():
                    if _dc_kaydet_satir(int(_hr["id"]), {"firma": str(_hr["firma"]), "guncelleyen": st.session_state.get("kullanici","")}):
                        _eklenen_say2 += 1
                st.success(f"✅ {_eklenen_say2} müşteri eklendi!")
                st.rerun()

    # MÜKERRER MÜŞTERİ TESPİTİ
    if _df_goster.empty:
        st.info("Henüz bu çalışma tablosunda müşteri yok. Yukarıdan ekleyin.")
        st.stop()

    _dc_ara = st.text_input("Firma ara", key="dc_ara", placeholder="firma adı ile filtrele...")
    if _dc_ara:
        _df_goster = _df_goster[_df_goster["firma"].str.contains(_dc_ara, case=False, na=False)]

    st.caption(f"{len(_df_goster)} müşteri")

    # TABLO VERİSİ — tek tablo, direkt düzenlenebilir + Sil kolonu
    _tablo_satirlar = []
    for _idx, (___, _cr) in enumerate(_df_goster.iterrows(), start=1):
        _cid = int(_cr["id"])
        _kayit = _dc_kayitlar.get(_cid, {})
        _notlar_bu = _dc_notlar_tum.get(_cid, [])
        _eski_notlar = " | ".join([f"{str(n.get('tarih',''))[:10]}: {n.get('aciklama','')}" for n in _notlar_bu]) if _notlar_bu else ""

        _hedef_oto = str(int(_cr.get("beklenen_ciro",0))) if _cr.get("beklenen_ciro",0) else ""
        _gercek_oto = str(int(_cr.get("gerceklesen_ciro",0))) if _cr.get("gerceklesen_ciro",0) else ""

        _tablo_satirlar.append({
            "Sil": False,
            "Sıra": _idx,
            "Kayıt Tarihi": fmt_tarih(_cr.get("tarih","")),
            "ID": _cid,
            "Firma": str(_cr.get("firma","")),
            "Yetkili": str(_cr.get("yetkili","") or ""),
            "GSM": str(_cr.get("gsm","") or ""),
            "İl": str(_cr.get("il","") or ""),
            "İlçe": str(_cr.get("ilce","") or ""),
            "Çıkış İl": _kayit.get("cikis_il","") or "",
            "Varış İl": _kayit.get("varis_il","") or "",
            "Ciro": _kayit.get("ciro","") or "",
            "Tür": _kayit.get("tur","") or "",
            "Desi-Kg": _kayit.get("desi_kg","") or "",
            "Fiyat": _kayit.get("fiyat","") or "",
            "Durum": (_kayit.get("durum","") or "") if (_kayit.get("durum","") or "") not in ["","--"] else str(_cr.get("durum","") or ""),
            "Aşama": (_kayit.get("asama","") or "") if (_kayit.get("asama","") or "") not in ["","--"] else str(_cr.get("islem_asamasi","") or ""),
            "Segment": str(_cr.get("segment","") or ""),
            "Hedef Ciro": _kayit.get("hedef_ciro","") or _hedef_oto,
            "Gerçekleşen": _kayit.get("gerceklesen","") or _gercek_oto,
            "fark": _kayit.get("fark","") or "",
            "Başarı yuzdesi": _kayit.get("basari","") or "",
            "Açıklama Yaz": "",
            "Eski Açıklama Notu": _eski_notlar,
            "Randevu İşlem Tarih": _kayit.get("randevu_tar","") or "",
        })

    _df_tablo = pd.DataFrame(_tablo_satirlar)

    # ── DETAY CARİ NOT PANELİ ────────────────────────────────────────────────
    _dc_not_panel_id = st.session_state.get("_dc_not_panel_id")

    if _dc_not_panel_id:
        _dc_tbl_col, _dc_not_col = st.columns([3, 1])
    else:
        _dc_tbl_col = st.container()
        _dc_not_col = None

    with _dc_tbl_col:
        _edited = st.data_editor(
            _df_tablo,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            height=min(700, 90 + len(_df_tablo)*40),
            disabled=["Sıra","Kayıt Tarihi","ID","Firma","Yetkili","GSM","İl","İlçe","Segment","Eski Açıklama Notu"],
            column_config={
                "Sil": st.column_config.CheckboxColumn(width="small", help="İşaretleyip aşağıdaki 'Seçilenleri Sil' butonuna basın"),
                "Sıra": st.column_config.NumberColumn(width="small"),
                "Kayıt Tarihi": st.column_config.TextColumn(width="small"),
                "ID": st.column_config.NumberColumn(width="small"),
                "Çıkış İl": st.column_config.TextColumn(width="medium", help="virgülle ayırın"),
                "Varış İl": st.column_config.TextColumn(width="medium", help="virgülle ayırın"),
                "Ciro": st.column_config.TextColumn(width="medium", help="virgülle ayırın"),
                "Tür": st.column_config.TextColumn(width="medium"),
                "Desi-Kg": st.column_config.TextColumn(width="medium"),
                "Fiyat": st.column_config.TextColumn(width="small"),
                "Durum": st.column_config.TextColumn(width="small"),
                "Aşama": st.column_config.TextColumn(width="small"),
                "Hedef Ciro": st.column_config.TextColumn(width="small"),
                "Gerçekleşen": st.column_config.TextColumn(width="small"),
                "fark": st.column_config.TextColumn(width="small"),
                "Başarı yuzdesi": st.column_config.TextColumn(width="small"),
                "Açıklama Yaz": st.column_config.TextColumn(width="medium"),
                "Eski Açıklama Notu": st.column_config.TextColumn(width="large"),
                "Randevu İşlem Tarih": st.column_config.TextColumn(width="medium"),
            },
            key="dc_data_editor"
        )

    # Detay cari — seçili satır not paneli
    _dc_secili = _edited[_edited.get("Sil", False) == True] if "Sil" in _edited.columns else pd.DataFrame()
    # Tek satır seçili + notu var → paneli aç
    if len(_dc_secili) == 1:
        _dc_sel_id = int(_dc_secili.iloc[0]["ID"])
        _dc_sel_notlar = _dc_notlar_tum.get(_dc_sel_id, [])
        if _dc_sel_notlar and st.session_state.get("_dc_not_panel_id") != _dc_sel_id:
            st.session_state["_dc_not_panel_id"] = _dc_sel_id
            st.rerun()
        elif not _dc_sel_notlar:
            st.session_state.pop("_dc_not_panel_id", None)
    elif len(_dc_secili) == 0 and st.session_state.get("_dc_not_panel_id"):
        st.session_state.pop("_dc_not_panel_id", None)
        st.rerun()

    if _dc_not_panel_id and _dc_not_col:
        with _dc_not_col:
            _dc_pnotlar = _dc_notlar_tum.get(int(_dc_not_panel_id), [])
            _dc_pfirma = ""
            _dc_prows = _df_tablo[_df_tablo["ID"] == int(_dc_not_panel_id)]
            if not _dc_prows.empty:
                _dc_pfirma = str(_dc_prows.iloc[0].get("Firma",""))
            st.markdown(
                f"<div style='border:1.5px solid #3b82f6;border-radius:10px;padding:12px 14px;background:white'>"
                f"<div style='font-size:12px;font-weight:600;color:#1e40af;margin-bottom:8px'>📋 {_dc_pfirma[:22]}<br>"
                f"<span style='font-weight:400;color:#64748b'>{len(_dc_pnotlar)} not</span></div>"
                + "".join([
                    f"<div style='border-left:3px solid #3b82f6;padding:7px 10px;margin:5px 0;"
                    f"border-radius:0 6px 6px 0;background:#f8fafc'>"
                    f"<div style='font-size:11px;color:#94a3b8;margin-bottom:2px'>📅 {fmt_tarih(_dn.get('tarih',''))} · 👤 {_dn.get('olusturan','')}</div>"
                    f"<div style='color:#1e293b;font-size:12px'>{str(_dn.get('aciklama','')).replace('<','&lt;').replace('>','&gt;')}</div>"
                    f"</div>"
                    for _dn in _dc_pnotlar
                ])
                + "<div style='font-size:11px;color:#94a3b8;margin-top:8px'>Satırı tekrar seç → kapanır</div>"
                + "</div>",
                unsafe_allow_html=True
            )

    _bk1, _bk2 = st.columns(2)

    if _bk1.button("💾 Tüm Değişiklikleri Kaydet", type="primary", use_container_width=True, key="dc_kaydet_tum"):
        _basarili = 0
        _hatali = 0
        for _i, _row in _edited.iterrows():
            _cid_e = int(_row["ID"])
            _eski_satir = _df_tablo.iloc[_i]

            _degisti = any(str(_row[_c]) != str(_eski_satir[_c]) for _c in [
                "Çıkış İl","Varış İl","Ciro","Tür","Desi-Kg","Fiyat","Durum","Aşama",
                "Hedef Ciro","Gerçekleşen","fark","Başarı yuzdesi","Açıklama Yaz","Randevu İşlem Tarih"
            ])
            if not _degisti:
                continue

            _yeni_not = str(_row.get("Açıklama Yaz","") or "").strip()
            if _yeni_not:
                _dc_not_ekle(_cid_e, str(_row["Firma"]), _yeni_not)

            _veri_kayit = {
                "firma": str(_row["Firma"]),
                "cikis_il": str(_row.get("Çıkış İl","") or ""),
                "varis_il": str(_row.get("Varış İl","") or ""),
                "ciro": str(_row.get("Ciro","") or ""),
                "tur": str(_row.get("Tür","") or ""),
                "desi_kg": str(_row.get("Desi-Kg","") or ""),
                "fiyat": str(_row.get("Fiyat","") or ""),
                "durum": str(_row.get("Durum","") or ""),
                "asama": str(_row.get("Aşama","") or ""),
                "hedef_ciro": str(_row.get("Hedef Ciro","") or ""),
                "gerceklesen": str(_row.get("Gerçekleşen","") or ""),
                "fark": str(_row.get("fark","") or ""),
                "basari": str(_row.get("Başarı yuzdesi","") or ""),
                "randevu_tar": str(_row.get("Randevu İşlem Tarih","") or ""),
                "guncelleyen": st.session_state.get("kullanici",""),
            }
            if _dc_kaydet_satir(_cid_e, _veri_kayit):
                _basarili += 1
            else:
                _hatali += 1

        if _basarili:
            st.success(f"✅ {_basarili} müşteri kaydedildi!")
        if _hatali:
            st.error(f"❌ {_hatali} müşteride hata oluştu.")
        if _basarili or _hatali:
            if "dc_data_editor" in st.session_state:
                del st.session_state["dc_data_editor"]
            st.rerun()
        else:
            st.info("Değişiklik bulunamadı.")

    if _bk2.button("🗑 İşaretli Müşterileri Listeden Çıkar", use_container_width=True, key="dc_sil_btn"):
        _silinecekler = _edited[_edited["Sil"] == True]
        if _silinecekler.empty:
            st.warning("Silmek için en az bir satırın 'Sil' kutusunu işaretleyin.")
        else:
            _silinen_sayisi = 0
            for _, _srow in _silinecekler.iterrows():
                if _dc_satir_sil(int(_srow["ID"])):
                    _silinen_sayisi += 1
            st.success(f"✅ {_silinen_sayisi} müşteri listeden çıkarıldı!")
            st.rerun()


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
                wa_row = df_wa[df_wa["id"] == wa_mid].iloc[0]
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
                wa_url_link = f"https://wa.me/{wa_no_link}?text={wa_mesaj.replace(' ','%20').replace(chr(10),'%0A')}"
                st.link_button("🔗 WhatsApp Web'de Aç", wa_url_link, use_container_width=True)

    # ── TOPLU GÖNDER ──────────────────────────────────────────────────────────
    with wa_tab2:
        st.markdown("### 👥 Toplu Mesaj Gönder")
        st.warning("⚠️ Spam yapmayın — WhatsApp toplu mesaj için kısıtlama uygulayabilir.")

        filtre_durum_wa = st.selectbox("Müşteri Filtresi:", ["Tümü","Aktif","Hedef","Pasif"], key="toplu_filtre")
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
                            sablon_txt = str(sab_row.iloc[0]["metin"])
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

                    # WA linki — şablon seçilince hemen göster
                    if mesaj_txt and mesaj_txt.strip():
                        from urllib.parse import quote
                        wa_url = f"https://wa.me/{t_wa}?text={quote(mesaj_txt, safe='')}"
                        c6.link_button("📱", wa_url, use_container_width=True, type="primary")
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
    bugun_str = datetime.now().strftime("%Y-%m-%d")

    # ── iki sekme ─────────────────────────────────────────────────────────────
    r_tab1, r_tab2, r_tab3, r_tab4 = st.tabs(["📋 Liste & Düzenle", "➕ Yeni Randevu", "📂 Aşama Sayfaları", "⚙️ Yönetim"])

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

            _df_goster = pd.DataFrame([{
                "ID":       int(r.get("id",0) or 0),
                "Tarih":    fmt_tarih(r.get("randevu_tarihi","")),
                "Saat":     str(r.get("randevu_saati","") or "09:00")[:5],
                "Müşteri":  str(r.get("musteri_adi","") or ""),
                "Bölge":    str(r.get("bolge","") or ""),
                "Görev":    str(r.get("gorev","") or ""),
                "Sonuç":    str(r.get("sonuc","") or "—"),
                "Açıklama": str(r.get("aciklama","") or ""),
                "Temsilci": str(r.get("temsilci","") or ""),
                "Hedef ₺":  float(_ciro_map.get(str(r.get("musteri_adi","")),{"hedef":0})["hedef"]),
                "Gerçek ₺": float(_ciro_map.get(str(r.get("musteri_adi","")),{"gercek":0})["gercek"]),
                "Fark ₺":   float(_ciro_map.get(str(r.get("musteri_adi","")),{"gercek":0})["gercek"]) - float(_ciro_map.get(str(r.get("musteri_adi","")),{"hedef":0})["hedef"]),
            } for _,r in df_rand.iterrows()])

            # id→index map (kaydetmek için)
            _rand_id_list = [int(r.get("id",0)) for _,r in df_rand.iterrows()]

            _edited_rand = st.data_editor(
                _df_goster,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config={
                    "ID":       st.column_config.NumberColumn("ID", width="small", disabled=True),
                    "Tarih":    st.column_config.TextColumn("Tarih", width="small", help="GG.AA.YYYY"),
                    "Saat":     st.column_config.SelectboxColumn("Saat", options=_saat_opts, width="small"),
                    "Müşteri":  st.column_config.TextColumn("Müşteri", width="large"),
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
                            # GG.AA.YYYY → YYYY-MM-DD (DB formatı)
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

        with st.form("randevu_form"):
            rand_musteri = st.selectbox("Müşteri:", musteri_rand_opts,
                index=musteri_rand_opts.index(_rand_mus_sec) if _rand_mus_sec in musteri_rand_opts else 0,
                key="rand_musteri")
            rc1,rc2,rc3 = st.columns(3)
            rand_tarih    = rc1.date_input("Tarih*:", value=datetime.now().date(), key="rand_tarih")
            _rand_saat_opts = [f"{h:02d}:{m:02d}" for h in range(9,21) for m in (0,15,30,45)]
            rand_saat     = rc2.selectbox("Saat*:", _rand_saat_opts, index=4, key="rand_saat")  # default 10:00
            rand_bolge    = rc3.text_input("Bölge:", placeholder="İstanbul Beykoz")
            rc4,rc5,rc6 = st.columns(3)
            rand_gorev    = rc4.selectbox("Görev*:", ["Ziyaret","Arama","Değerlendirme","Kazanıldı","Kaybedildi","Devam Ediyor","Whatsapp Mesaj","E-mail","Yeni Tarihe Ertele"])
            rand_takip    = rc5.selectbox("Takip:", ["Gidildi","Gidilmedi","Devam Ediyor","Ertelendi"])
            rand_adet     = rc6.number_input("Adet:", min_value=0, step=1, key="rand_adet")
            rand_temsilci = st.text_input("Satış Temsilcisi*:", key="rand_tem")
            rand_tem_tel  = st.text_input("Temsilci WA No:", placeholder="05xxxxxxxxx", key="rand_tem_tel")
            rand_aciklama = st.text_area("Açıklama:", height=70, key="rand_aciklama")
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

                    # Mükerrer kontrolü
                    if musteri_id > 0:
                        _df_muk = db_read("randevular", filters={"musteri_id":musteri_id})
                        if not _df_muk.empty and "sonuc" in _df_muk.columns:
                            _aktif = _df_muk[~_df_muk["sonuc"].isin(["Bitti","İptal","Gidilmedi"])]
                            if not _aktif.empty:
                                st.error(f"⚠️ Bu müşterinin aktif randevusu var! ({_aktif.iloc[0].get('randevu_tarihi','')} — {_aktif.iloc[0].get('gorev','')})")
                                st.stop()

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

                    if rand_tem_tel.strip():
                        import re as _re_r3
                        _tw3 = _re_r3.sub(r"[\s\-\(\)+]","",rand_tem_tel.strip())
                        if _tw3.startswith("0"): _tw3 = "90"+_tw3[1:]
                        elif len(_tw3)==10: _tw3 = "90"+_tw3
                        _msg3 = f"🗓️ YENİ RANDEVU\nMüşteri: {musteri_adi}\nTarih: {rand_tarih} {rand_saat}\nBölge: {rand_bolge}\nGörev: {rand_gorev}\nİyi çalışmalar!"
                        st.link_button("📱 Temsilciye WA Gönder",
                            f"https://wa.me/{_tw3}?text={_msg3.replace(' ','%20').replace(chr(10),'%0A')}",
                            use_container_width=True, type="primary")
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
            "id":            st.column_config.NumberColumn("ID", disabled=True),
            "tarih":         None, "olusturan": None, "silindi": None,
            "beklenen_ciro": None, "gerceklesen_ciro": None,
            "adres":         None, "aciklama":   None,
            "firma":         st.column_config.TextColumn("Firma"),
            "yetkili":       st.column_config.TextColumn("Yetkili"),
            "gsm":           st.column_config.TextColumn("GSM"),
            "sabit":         st.column_config.TextColumn("S. Tel"),
            "email":         st.column_config.TextColumn("Email"),
            "il":            st.column_config.TextColumn("İl"),
            "ilce":          st.column_config.TextColumn("İlçe"),
            "durum":         st.column_config.SelectboxColumn("Durum", options=_tum_durum_r),
            "temsilci":      st.column_config.TextColumn("Temsilci"),
            "islem_asamasi": st.column_config.SelectboxColumn("Aşama", options=_tum_asama_r),
        }
        _col_order_r = ["Seç","id","firma","yetkili","gsm","sabit","email","il","ilce","durum","temsilci","islem_asamasi"]

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
                            if _lc2.button("🗑️", key=f"dsil_{_d}", help="Sil (önce veri silinmeli)"):
                                st.warning(f"'{_d}' durumunda {_adet} firma var, önce firmalar başka duruma taşınmalı!")
                        else:
                            _lc2.caption("—")
                    # VERİ OLMAYANLAR — ekstra ise silinebilir
                    elif _d in _ekstra_durumlar:
                        _lc1, _lc2 = st.columns([4,1])
                        _lc1.caption(f"⬜ {_d} — 0 firma")
                        if _lc2.button("🗑️", key=f"dsil_{_d}"):
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
                    _rnotlar = sb_liste.table("cari_aciklamalar").select("*").eq("cari_id", _sec_cari_id).order("tarih", desc=True).execute()
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




# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='position:fixed;bottom:0;left:0;right:0;background:#f0f2f6;padding:6px;text-align:center;font-size:11px;color:#888;z-index:999;'>"
    "MWCRMPRO v6.7 &nbsp;|&nbsp; "
    "<a href='tel:05400344228' style='color:#888;text-decoration:none;'>📞 5400344228</a>"
    " &nbsp;|&nbsp; "
    "<a href='mailto:osnenufu@gmail.com' style='color:#888;text-decoration:none;'>✉️ osnenufu@gmail.com</a>"
    " &nbsp;|&nbsp; "
    "<a href='https://wa.me/905400344228' target='_blank' style='color:#25D366;text-decoration:none;'>💬 WhatsApp</a>"
    "</div>",
    unsafe_allow_html=True
)