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

def get_supabase():
    return get_sb_client()

@st.cache_data(ttl=60)
def get_cari_listesi():
    """60 sn cache'li cari listesi"""
    sb = get_sb_client()
    if sb:
        try:
            res = sb.table("cari_kartlar").select("*").neq("silindi",1).order("firma").execute()
            return pd.DataFrame(res.data) if res.data else pd.DataFrame()
        except: pass
    try:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM cari_kartlar WHERE silindi=0 OR silindi='0' OR silindi IS NULL ORDER BY firma", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=120)
def get_kullanici_listesi():
    """2 dk cache'li kullanıcı listesi"""
    return db_read("kullanicilar", extra_sql="")

@st.cache_data(ttl=60)
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
    if sb:
        try:
            res = sb.table(table).insert(data).execute()
            if res.data:
                return True
        except Exception as e:
            pass  # SQLite fallback
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
    try:
        conn = get_conn()
        df = pd.read_sql(sql, conn, params=params)
        conn.close()
        return df
    except Exception as e:
        st.error(f"db_query hatası: {e}")
        return pd.DataFrame()

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
        conn = get_conn()
        sql = f"SELECT * FROM {table}"
        if filters:
            where = " AND ".join([f"{k}=?" for k in filters.keys()])
            sql += f" WHERE {where}"
            df = pd.read_sql(sql, conn, params=list(filters.values()))
        else:
            df = pd.read_sql(sql, conn)
        conn.close()
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
st.set_page_config(page_title="MWCRMPRO", layout="wide")

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



_TAB_LISTESI_DEFAULT = ["yeni", "liste", "analiz", "randevu", "teklif", "ozel_teklif", "kisiler", "rapor", "excel", "kullanici", "admin_rapor"]
_TAB_ETIKETLER = {
    "yeni": "➕ Yeni Kart Ekle",
    "liste": "📋 Cari Liste / Düzenle",
    "rapor": "📊 Raporlar",
    "teklif": "📄 Spot Teklif",
    "ozel_teklif": "⭐ Özel Teklif",
    "excel": "📥 Excel Aktar",
    "kisiler": "📞 Telefon Kişiler",
    "analiz": "🔍 Müşteri Analizi",
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
section[data-testid="stSidebar"] { padding-top: 0.5rem !important; }
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
                st.session_state["duzenle_musteri"] = bulunan
                st.success(f"✅ **{bulunan.get('firma')}** (ID: {bulunan.get('id')})")
            else:
                st.error("Müşteri bulunamadı.")
                st.session_state.pop("duzenle_musteri", None)

    duzenle = st.session_state.get("duzenle_musteri")

    st.divider()
    if duzenle:
        st.markdown(f"### ✏️ Düzenleniyor: **{duzenle.get('firma')}** (ID: {duzenle.get('id')})")
    else:
        st.markdown("### ➕ Yeni Cari Kart")

    il_listesi = sorted(ILLER_ILCELER.keys())
    mevcut_il = duzenle.get("il") if duzenle and duzenle.get("il") in il_listesi else il_listesi[0]
    mevcut_ilce_listesi = ILLER_ILCELER[mevcut_il]
    mevcut_ilce = duzenle.get("ilce") if duzenle and duzenle.get("ilce") in mevcut_ilce_listesi else mevcut_ilce_listesi[0]

    # İl/İlçe form dışında - dinamik güncelleme için
    il_col1, il_col2 = st.columns(2)
    il_idx = il_listesi.index(mevcut_il)
    secilen_il = il_col1.selectbox("İl", il_listesi, index=il_idx, key="yeni_il_sec")
    ilce_listesi_sec = ILLER_ILCELER[secilen_il]
    ilce_idx_sec = ilce_listesi_sec.index(mevcut_ilce) if mevcut_ilce in ilce_listesi_sec else 0
    secilen_ilce = il_col2.selectbox("İlçe", ilce_listesi_sec, index=ilce_idx_sec, key="yeni_ilce_sec")

    with st.form("yeni_kart_form"):
        col1, col2, col3 = st.columns(3)
        firma    = col1.text_input("Firma Adı",  value=duzenle.get("firma","") if duzenle else "")
        yetkili  = col1.text_input("Yetkili",    value=duzenle.get("yetkili","") if duzenle else "")
        gsm      = col2.text_input("GSM",        value=fmt_tel(duzenle.get("gsm","")) if duzenle else "")
        sabit    = col2.text_input("Sabit Tel",  value=fmt_tel(duzenle.get("sabit","")) if duzenle else "")
        email    = col3.text_input("E-Mail",     value=duzenle.get("email","") if duzenle else "")

        il_idx   = il_listesi.index(secilen_il)
        il       = col3.selectbox("İl", il_listesi, index=il_idx, key="yeni_il_form")
        ilce_listesi = ILLER_ILCELER[secilen_il]
        ilce_idx = ilce_listesi.index(secilen_ilce) if secilen_ilce in ilce_listesi else 0
        ilce     = col3.selectbox("İlçe", ilce_listesi, index=ilce_idx, key="yeni_ilce_form")

        durum_opts = ["Aktif","Hedef","Pasif"]
        durum_idx  = durum_opts.index(duzenle.get("durum")) if duzenle and duzenle.get("durum") in durum_opts else 0
        durum      = col1.selectbox("Durum", durum_opts, index=durum_idx)
        temsilci   = col2.text_input("Temsilci", value=duzenle.get("temsilci","") if duzenle else "")

        # Dinamik aşama listesi (sistemdeki tüm aşamalar + ekstralar)
        _asama_base = _tanimlar_yukle("asama")
        # df'de olan ama tabloda olmayan aşamaları da ekle
        try:
            _df_as2 = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi IS NULL")
            if not _df_as2.empty and "islem_asamasi" in _df_as2.columns:
                for _a in _df_as2["islem_asamasi"].dropna().unique():
                    if str(_a).strip() and str(_a) not in ["nan",""] and _a not in _asama_base:
                        _asama_base.append(str(_a))
        except: pass
        asama_opts = _asama_base
        _varsayilan_asama = st.session_state.pop("varsayilan_asama", None)
        _asama_default = duzenle.get("islem_asamasi") if duzenle else _varsayilan_asama
        asama_idx  = asama_opts.index(_asama_default) if _asama_default and _asama_default in asama_opts else 0
        asama      = col3.selectbox("İşlem Aşaması", asama_opts, index=asama_idx)
        adres      = st.text_area("Adres", value=duzenle.get("adres","") if duzenle else "")
        notlar_v   = st.text_area("📝 Açıklama", value=str(duzenle.get("aciklama","") or "") if duzenle else "", height=70, key="yeni_notlar")

        st.markdown("#### 💰 Ciro Bilgileri")
        ciro_col1, ciro_col2, ciro_col3, ciro_col4 = st.columns(4)
        bek_val = duzenle.get("beklenen_ciro", 0) if duzenle else 0
        ger_val = duzenle.get("gerceklesen_ciro", 0) if duzenle else 0

        bek_str = ciro_col1.text_input("Beklenen Ciro (₺)", value=fmt_para(bek_val).replace(" ₺",""), placeholder="Örn: 10.000", key="bek_ciro_str")
        ger_str = ciro_col2.text_input("Gerçekleşen Ciro (₺)", value=fmt_para(ger_val).replace(" ₺",""), placeholder="Örn: 8.500", key="ger_ciro_str")

        beklenen_ciro = parse_para(bek_str)
        gerceklesen_ciro = parse_para(ger_str)
        fark = gerceklesen_ciro - beklenen_ciro
        yuzde = (gerceklesen_ciro / beklenen_ciro * 100) if beklenen_ciro > 0 else 0
        ciro_col3.metric("Fark (₺)", fmt_para(fark))
        ciro_col4.metric("Gerçekleşme %", f"%{yuzde:.1f}".replace(".",","))

        btn_label = "💾 Güncelle" if duzenle else "💾 Cari Kartı Kaydet"
        if st.form_submit_button(btn_label):
            if not firma:
                st.warning("Firma adı boş bırakılamaz!")
            elif duzenle:
                ok = db_update("cari_kartlar", {
                    "firma": firma, "yetkili": yetkili, "gsm": gsm,
                    "sabit": sabit, "email": email, "adres": adres,
                    "ilce": ilce, "il": il, "durum": durum,
                    "temsilci": temsilci, "islem_asamasi": asama,
                    "aciklama": notlar_v,
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
                    "ilce": ilce, "il": il, "durum": durum,
                    "temsilci": temsilci, "islem_asamasi": asama,
                    "aciklama": notlar_v,
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
            st.session_state["pending_fil_durum"] = "Tümü" if _ad == "Toplam" else _ad
            st.rerun()

    # Aşama satırı
    if tum_asama_opts:
        _a_veri = [(a, len(df[df["islem_asamasi"]==a]) if "islem_asamasi" in df.columns else 0) for a in tum_asama_opts]
        _a_cols = st.columns(len(_a_veri))
        for i, (_an, _ac) in enumerate(_a_veri):
            _em2 = _ASAMA_EMOJI.get(_an, "🔸")
            if _a_cols[i].button(f"{_em2} {_an}\n{_ac}", key=f"asm_btn_{i}", use_container_width=True):
                st.session_state["pending_fil_asama"] = _an
                st.rerun()

    # ── FİLTRE TEK SATIR ─────────────────────────────────────────────────────
    _fc = st.columns([1.3, 1.3, 1.8, 1.8, 1.3, 0.4, 0.8])
    _p_asama = st.session_state.pop("pending_fil_asama", None)
    _asama_opts_full = ["Aşama: Tümü"]+tum_asama_opts
    _asama_idx = _asama_opts_full.index(_p_asama) if _p_asama and _p_asama in _asama_opts_full else 0
    filtre_asama = _fc[0].selectbox("", _asama_opts_full, index=_asama_idx, key="fil_asama", label_visibility="collapsed")
    _p_durum = st.session_state.pop("pending_fil_durum", None)
    _durum_opts_full = ["Durum: Tümü"]+tum_durum_opts
    _durum_idx = _durum_opts_full.index(_p_durum) if _p_durum and _p_durum in _durum_opts_full else 0
    filtre_durum = _fc[1].selectbox("", _durum_opts_full, index=_durum_idx, key="fil_durum", label_visibility="collapsed")

    df_f = df.copy()
    if filtre_asama != "Aşama: Tümü": df_f = df_f[df_f["islem_asamasi"]==filtre_asama]
    if filtre_durum  != "Durum: Tümü": df_f = df_f[df_f["durum"]==filtre_durum]

    kart_opts = ["-- Müşteri Seçin --"] + [
        f"[{int(r['id'])}] {r['firma']} | {r.get('il','')} | {r.get('islem_asamasi','')}"
        for _, r in df_f.iterrows()
    ]
    if st.session_state.get("kart_sec_reset"):
        st.session_state.pop("kart_sec_reset", None)
        st.session_state.pop("kart_sec", None)
    secili_kart = _fc[2].selectbox("", kart_opts, key="kart_sec", label_visibility="collapsed")
    ara_txt      = _fc[3].text_input("", placeholder="🔍 Firma, yetkili, il...", key="ara_liste", label_visibility="collapsed")
    siralama_kol = _fc[4].selectbox("", ["Tarih↓","Firma A-Z","Firma Z-A","İl A-Z","Temsilci A-Z"], key="siralama_kol", label_visibility="collapsed")

    if ara_txt: df_f = df_f[df_f.apply(lambda r: ara_txt.lower() in str(r).lower(), axis=1)]
    if siralama_kol == "Firma A-Z":      df_f = df_f.sort_values("firma", ascending=True)
    elif siralama_kol == "Firma Z-A":    df_f = df_f.sort_values("firma", ascending=False)
    elif siralama_kol == "İl A-Z" and "il" in df_f.columns:       df_f = df_f.sort_values("il", ascending=True)
    elif siralama_kol == "Temsilci A-Z" and "temsilci" in df_f.columns: df_f = df_f.sort_values("temsilci", ascending=True)
    df_f = df_f.reset_index(drop=True)

    if secili_kart != "-- Müşteri Seçin --":
        if _fc[5].button("❌", key="kart_sec_temizle", use_container_width=True, help="Temizle"):
            st.session_state["kart_sec_reset"] = True
            st.rerun()
    _fc[6].markdown(f"<small style='color:gray'>{len(df_f)} kayıt</small>", unsafe_allow_html=True)
    if secili_kart != "-- Müşteri Seçin --" and "[" in secili_kart:
        try:
            kart_id = int(secili_kart.split("]")[0].replace("[","").strip())
            kart_row = df_f[df_f["id"]==kart_id].iloc[0]
            st.markdown(f"---\n## 🏢 {kart_row.get('firma','')}")
            kc1,kc2,kc3 = st.columns(3)
            with kc1:
                st.markdown("**📋 İletişim**")
                st.write(f"👤 {kart_row.get('yetkili','-')}")
                st.write(f"📱 {fmt_tel(kart_row.get('gsm','')) or '-'}")
                st.write(f"☎️ {fmt_tel(kart_row.get('sabit','')) or '-'}")
                st.write(f"✉️ {kart_row.get('email','-')}")
            with kc2:
                st.markdown("**📍 Konum & Durum**")
                st.write(f"🏙️ {kart_row.get('il','-')} / {kart_row.get('ilce','-')}")
                st.write(f"📊 {kart_row.get('durum','-')}")
                st.write(f"🔄 {kart_row.get('islem_asamasi','-')}")
                st.write(f"👔 {kart_row.get('temsilci','-')}")
                _not = str(kart_row.get("aciklama","") or "")
                if _not and _not != "nan":
                    st.info(f"📝 {_not}")
            with kc3:
                bek = float(kart_row.get("beklenen_ciro",0) or 0)
                ger = float(kart_row.get("gerceklesen_ciro",0) or 0)
                st.metric("Beklenen",     fmt_para(bek))
                st.metric("Gerçekleşen",  fmt_para(ger), delta=fmt_para(ger-bek))
            # Analiz var mı kontrol et
            try:
                _an_check = None
                _sb_ck = get_sb_client()
                if _sb_ck:
                    _an_r2 = _sb_ck.table("musteri_analiz").select("sonuc,potansiyel,teklif_tur,bek_ciro").eq("firma", str(kart_row.get("firma",""))).execute()
                    if _an_r2.data: _an_check = _an_r2.data[0]
                else:
                    _cn2 = get_conn()
                    _an_rw = _cn2.execute("SELECT sonuc,potansiyel,teklif_tur,bek_ciro FROM musteri_analiz WHERE firma=?", (str(kart_row.get("firma","")),)).fetchone()
                    _cn2.close()
                    if _an_rw: _an_check = {"sonuc":_an_rw[0],"potansiyel":_an_rw[1],"teklif_tur":_an_rw[2],"bek_ciro":_an_rw[3]}
            except: _an_check = None
            if _an_check:
                _pot_ic2 = {"çok yüksek":"🟢","yüksek":"🟢","orta":"🟡","düşük":"🟠","çok düşük":"🔴"}.get(str(_an_check.get("potansiyel","")),"-")
                with st.expander(f"🔍 Analiz: {_pot_ic2} {_an_check.get('potansiyel','?')} potansiyel · {_an_check.get('sonuc','?')} · {_an_check.get('teklif_tur','?')}", expanded=False):
                    _pac1,_pac2,_pac3,_pac4 = st.columns(4)
                    _pac1.metric("Potansiyel", _an_check.get("potansiyel","—"))
                    _pac2.metric("Sonuç", _an_check.get("sonuc","—"))
                    _pac3.metric("Teklif Türü", _an_check.get("teklif_tur","—"))
                    _pac4.metric("Beklenen Ciro", f"{float(_an_check.get('bek_ciro',0) or 0):,.0f} ₺")
                    # Tam analiz detayı
                    try:
                        import json as _kj
                        _sb_full = get_sb_client()
                        if _sb_full:
                            _full = _sb_full.table("musteri_analiz").select("*").eq("firma", str(kart_row.get("firma",""))).execute()
                            _fd = _full.data[0] if _full.data else {}
                        else:
                            _cn_full = get_conn()
                            _fw = _cn_full.execute("SELECT * FROM musteri_analiz WHERE firma=?", (str(kart_row.get("firma","")),)).fetchone()
                            _cn_full.close()
                            if _fw:
                                _cols_f = [d[0] for d in get_conn().execute("PRAGMA table_info(musteri_analiz)").fetchall()]
                                _fd = dict(zip(_cols_f, _fw))
                            else: _fd = {}
                        if _fd:
                            st.markdown(f"""**Kargo:** {_fd.get('kargo','—')} · **Fatura:** {_fd.get('fatura','—')} · **Vade:** {_fd.get('odeme','—')}  
**Beklenti:** {_fd.get('beklenti','—')} · **Engel:** {_fd.get('engel','—')}  
**Sonraki Adım:** {_fd.get('sonraki_adim','—')} · **Takip:** {_fd.get('takip_tar','—')}""")
                            if _fd.get('not_alan'): st.info(f"📝 {_fd.get('not_alan')}")
                    except: pass
            # Verilen teklifler
            try:
                _df_tek_k = db_read("teklifler", extra_sql=f"WHERE musteri_adi='{str(kart_row.get('firma',''))}' ORDER BY tarih DESC LIMIT 10")
                if not _df_tek_k.empty:
                    with st.expander(f"📄 Verilen Teklifler ({len(_df_tek_k)})", expanded=False):
                        for _, _tr in _df_tek_k.iterrows():
                            try:
                                import json as _tj
                                _tdata = _tj.loads(_tr.get("satirlar","{}") or "{}")
                                _ttur = _tdata.get("teklif_turu","Spot")
                                _ttoplam = float(_tr.get("toplam_tutar",0) or 0)
                                _tnotlar = str(_tr.get("notlar","") or "")
                                _ttar = str(_tr.get("tarih",""))[:10]
                                _tgon = str(_tr.get("olusturan",""))
                                st.markdown(f"**{_ttar}** · {_ttur} · {_ttoplam:,.2f} ₺ · {_tgon}", unsafe_allow_html=True)
                                if _tnotlar: st.caption(_tnotlar)
                                st.divider()
                            except: pass
            except: pass
            ab1,ab2,ab3,ab4 = st.columns(4)
            if ab1.button("✏️ Düzenle", key=f"kd_{kart_id}", use_container_width=True):
                d2 = {str(k):(None if str(v) in ["nan","None","NaT"] else v) for k,v in kart_row.items()}
                for _k in ["firma","yetkili","gsm","sabit","email","adres","il","ilce","durum","temsilci","islem_asamasi","aciklama"]:
                    if _k in d2: d2[_k] = "" if d2[_k] is None else str(d2[_k])
                st.session_state["duzenle_musteri"] = d2
                st.session_state["aktif_tab"] = "yeni"; st.rerun()
            if ab2.button("📄 Teklif", key=f"kt_{kart_id}", use_container_width=True, type="primary"):
                st.session_state["aktif_tab"] = "teklif"
                st.session_state["pending_hedef_mus"] = str(kart_row.get("firma",""))
                st.session_state["son_secili_id"] = None; st.rerun()
            if ab3.button("📅 Randevu", key=f"kr_{kart_id}", use_container_width=True, type="primary"):
                st.session_state["aktif_tab"] = "randevu"
                st.session_state["rand_musteri_onsel"] = kart_id; st.rerun()
            if ab4.button("🔍 Analiz", key=f"kan_{kart_id}", use_container_width=True, help="Analizi görüntüle/düzenle"):
                st.session_state["aktif_tab"] = "analiz"
                st.session_state["an_firma_input"] = str(kart_row.get("firma",""))
                if "an_cari_sec" in st.session_state: del st.session_state["an_cari_sec"]
                st.rerun()

            # ── HIZLI KAYDET ─────────────────────────────────────────────────
            if st.button("💾 Değişiklikleri Kaydet", key=f"hiz_kyt_{kart_id}", use_container_width=True, type="primary"):
                _editor_state = st.session_state.get("cari_editor", {})
                _edited_rows  = _editor_state.get("edited_rows", {})
                _tablo_json   = st.session_state.get("_ls_tablo")
                _kayit_sayi   = 0
                if _edited_rows and _tablo_json:
                    import json as _hk_json
                    try:
                        _rows = _hk_json.loads(_tablo_json)
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
                                _kayit_sayi += 1
                            except: pass
                    except: pass
                if _kayit_sayi > 0:
                    try: db_read.clear()
                    except: pass
                    st.success(f"✅ {_kayit_sayi} satır kaydedildi!")
                else:
                    st.info("Tabloda değişiklik yok. Tabloda düzenleme yaptıktan sonra buradan kaydedebilirsiniz.")

            # ── HIZLI KAYDET BUTONU — ayrı satırda her zaman görünsün ────
            if st.button("💾 Bu Firmayı Kaydet", key=f"hiz_kyt2_{kart_id}", use_container_width=True, type="primary"):
                try:
                    _editor_state = st.session_state.get("cari_editor", {})
                    _edited_rows  = _editor_state.get("edited_rows", {})
                    _tablo_json   = st.session_state.get("_ls_tablo")
                    _kayit_sayi   = 0
                    if _edited_rows and _tablo_json:
                        import json as _hk_json
                        _rows = _hk_json.loads(_tablo_json)
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
                                _kayit_sayi += 1
                            except: pass
                    # Değişiklik yoksa mevcut satırı kaydet
                    if _kayit_sayi == 0:
                        _guncelle = {
                            "firma":        str(kart_row.get("firma","") or ""),
                            "yetkili":      str(kart_row.get("yetkili","") or ""),
                            "gsm":          str(kart_row.get("gsm","") or ""),
                            "sabit":        str(kart_row.get("sabit","") or ""),
                            "email":        str(kart_row.get("email","") or ""),
                            "il":           str(kart_row.get("il","") or ""),
                            "ilce":         str(kart_row.get("ilce","") or ""),
                            "durum":        str(kart_row.get("durum","") or ""),
                            "temsilci":     str(kart_row.get("temsilci","") or ""),
                            "islem_asamasi":str(kart_row.get("islem_asamasi","") or ""),
                        }
                        if sb_liste:
                            sb_liste.table("cari_kartlar").update(_guncelle).eq("id", kart_id).execute()
                        _kayit_sayi = 1
                    try: db_read.clear()
                    except: pass
                    st.success(f"✅ Kaydedildi!")
                except Exception as _hke:
                    st.error(f"Hata: {_hke}")

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
                    _tarih = str(_row.get("tarih",""))[:16]
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

    # Her firma için not sayısını göster
    if sb_liste:
        try:
            _res_notlar = sb_liste.table("cari_aciklamalar").select("cari_id").execute()
            if _res_notlar.data:
                import collections
                _not_sayac = collections.Counter([str(r["cari_id"]) for r in _res_notlar.data])
                df_edit["📨 Notlar"] = df_edit["id"].apply(lambda x: f"📨 {_not_sayac.get(str(int(x)),0)}" if _not_sayac.get(str(int(x)),0) > 0 else "")
            else:
                df_edit["📨 Notlar"] = ""
        except:
            df_edit["📨 Notlar"] = ""
    else:
        df_edit["📨 Notlar"] = ""

    df_edit.insert(0, "Seç", False)

    import json as _json_ls

    # ── TÜMÜ GÖSTER ──────────────────────────────────────────────────────────
    _df_sayfa = df_edit.copy()

    edited_df = st.data_editor(
        _df_sayfa,
        use_container_width=True,
        num_rows="fixed",
        column_config=col_config,
        column_order=col_order,
        key="cari_editor"
    )

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

    # ── BUTONLAR ──────────────────────────────────────────────────────────────
    btn_k, btn_a, btn_s = st.columns(3)
    with btn_k:
        if st.button("💾 Değişiklikleri Kaydet", use_container_width=True, type="primary", key="liste_kaydet"):
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
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5, kul_tab5_ekran = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi","🎨 Ekran Ayarları"])
    elif _surum_yetkisi:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5, kul_tab5_ekran = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi","🎨 Ekran Ayarları"])
    else:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5_ekran = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🎨 Ekran Ayarları"])
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

    # ── TEKLİF TÜRÜ ────────────────────────────────────────────────────────
    _ttur_col1, _ttur_col2 = st.columns([1,3])
    _teklif_turu = _ttur_col1.radio(
        "Teklif Türü:",
        ["🚀 Spot Teklif", "🤝 Özel Anlaşma"],
        horizontal=True,
        key="global_teklif_turu"
    )
    _is_ozel = "Özel" in _teklif_turu
    if _is_ozel:
        st.markdown("## 🤝 Özel Anlaşma Teklifi")
        _ttur_col2.info("💡 Özel anlaşma: sözleşmeli, vadeye özel, hacme göre kademeli fiyat.")
    else:
        st.markdown("## 🚀 Spot Teklif")
        _ttur_col2.info("⚡ Spot teklif: tek seferlik, anlık fiyat.")

    # ── TEK SATIR: FİLTRE + MÜŞTERİ + BİLGİLER ──────────────────────────────
    _df_cari_tek = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")

    if st.session_state.get("tek_mus_reset"):
        st.session_state.pop("tek_mus_reset", None)
        st.session_state.pop("teklif_musteri", None)
        st.session_state.pop("hedef_mus", None)

    _df_m  = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")

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
    _pending_hm = st.session_state.pop("pending_hedef_mus", None)
    if _pending_hm is not None:
        _firma_def = _pending_hm
    elif "hedef_mus" in st.session_state and st.session_state.get("son_secili_id") == _secim:
        _firma_def = st.session_state["hedef_mus"]
    st.session_state["son_secili_id"] = _secim

    hedef_musteri = _tr[3].text_input("", value=_firma_def, key="hedef_mus", placeholder="Müşteri Adı", label_visibility="collapsed")
    vade          = _tr[4].text_input("", placeholder="Vade...", key="vade", label_visibility="collapsed")
    gsm_manuel    = _tr[5].text_input("", value=gsm_kayitli, placeholder="05xxxxxxxxx", key="gsm_manuel", label_visibility="collapsed")
    email_manuel  = _tr[6].text_input("", value=email_kayitli, placeholder="Email", key="email_manuel", label_visibility="collapsed")

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
            _tt_kayit = "Özel Anlaşma" if st.session_state.get("global_teklif_turu","").startswith("🤝") else "Spot"
            db_insert("teklifler",{
                "musteri_id": int(secili_musteri["id"]) if secili_musteri is not None else 0,
                "musteri_adi": hedef_musteri,
                "satirlar": json.dumps({"hesap":hesap_sonuclar,"teklif":teklif_sonuclar,"teklif_turu":_tt_kayit},ensure_ascii=False),
                "toplam_tutar": toplam_tutar,
                "olusturan": st.session_state["kullanici"],
                "notlar": f"Teklif Türü: {_tt_kayit} | Vade:{vade}"
            })
            # Analiz kaydında da teklif_verildi güncelle
            try:
                _an_mevcut = None
                sb_tmp = get_sb_client()
                if sb_tmp:
                    _an_r = sb_tmp.table("musteri_analiz").select("id").eq("firma", hedef_musteri).execute()
                    if _an_r.data:
                        sb_tmp.table("musteri_analiz").update({"sonuc":"teklif verildi","teklif_tur":_tt_kayit}).eq("firma", hedef_musteri).execute()
                else:
                    conn_tmp = get_conn()
                    conn_tmp.execute("UPDATE musteri_analiz SET sonuc='teklif verildi', teklif_tur=? WHERE firma=?", (_tt_kayit, hedef_musteri))
                    conn_tmp.commit(); conn_tmp.close()
            except: pass
            st.success(f"✅ {_tt_kayit} teklifi kaydedildi!")

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
                    f"[{int(r['id'])}] {r.get('musteri_adi','')} | {str(r.get('tarih',''))[:10]}"
                    for _,r in df_tek.iterrows()]
                _sec_tek = st.selectbox("Teklif Seç:", _tek_opts, key="tek_sec")
                if _sec_tek != "-- Teklif Seçin --" and "[" in _sec_tek:
                    _tek_id = int(_sec_tek.split("]")[0].replace("[","").strip())
                    _tek_row = df_tek[df_tek["id"]==_tek_id].iloc[0]
                    st.caption(f"📅 {str(_tek_row.get('tarih',''))[:16]} · 👤 {_tek_row.get('olusturan','')} · 📝 {_tek_row.get('notlar','')}")
                    try:
                        _data = json.loads(_tek_row.get("satirlar","{}"))
                        if "teklif" in _data and _data["teklif"]:
                            _df_t = pd.DataFrame(_data["teklif"])
                            if "tutar" in _df_t.columns: _df_t["tutar"] = _df_t["tutar"].apply(lambda x: fmt_para(float(x or 0)))
                            if "birim_fiyat" in _df_t.columns: _df_t["birim_fiyat"] = _df_t["birim_fiyat"].apply(lambda x: fmt_para(float(x or 0)))
                            st.dataframe(_df_t, use_container_width=True, hide_index=True)
                    except: st.text(str(_tek_row.get("satirlar","")))
                    _ak1,_ak2,_ak3 = st.columns(3)
                    with _ak1.expander("✏️ Not Güncelle"):
                        _yn = st.text_area("Not:",value=str(_tek_row.get("notlar","")),height=70,key=f"tek_not_{_tek_id}")
                        if st.button("💾 Kaydet",key=f"tek_not_btn_{_tek_id}",use_container_width=True):
                            db_update("teklifler",{"notlar":_yn},"id",_tek_id); st.success("✅"); st.rerun()
                    if _ak2.button("🗃️ Arşivle",key=f"tek_arsiv_{_tek_id}",use_container_width=True):
                        db_update("teklifler",{"arsivlendi":1},"id",_tek_id); st.success("✅ Arşivlendi!"); st.rerun()
                    if _ak3.button("🗑️ Sil",key=f"tek_sil_{_tek_id}",use_container_width=True,type="primary"):
                        _sb_d=get_sb_client()
                        if _sb_d: _sb_d.table("teklifler").delete().eq("id",_tek_id).execute()
                        st.success("🗑️ Silindi!"); st.rerun()
        except Exception as _e:
            st.error(f"Hata: {_e}")


elif aktif == "ozel_teklif":
    sayfa_log("ozel_teklif")
    import json as _ozj, re as _ozre

    st.markdown("## ⭐ Özel Teklif")

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
    elif "oz2_hedef" in st.session_state and st.session_state.get("oz2_son_sec") == _oz_sec:
        _oz_fdef = st.session_state["oz2_hedef"]
    st.session_state["oz2_son_sec"] = _oz_sec

    _oz_hedef = _ozr[3].text_input("", value=_oz_fdef, key="oz2_hedef", placeholder="Hedef Müşteri", label_visibility="collapsed")
    _oz_vade  = _ozr[4].text_input("", placeholder="Vade...", key="oz2_vade", label_visibility="collapsed")
    _oz_not   = _ozr[5].text_input("", placeholder="Not...", key="oz2_not", label_visibility="collapsed")
    _oz_wa_no = _ozr[6].text_input("", value=_oz_gsm, placeholder="05xxxxxxxxx", key="oz2_wa", label_visibility="collapsed")
    _oz_email = _ozr[7].text_input("", value=_oz_eml, placeholder="Email", key="oz2_email", label_visibility="collapsed")

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
                if not _tt and not _ff: continue
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
                _oz_df_tek2 = _oz_df_tek[_oz_df_tek["satirlar"].str.contains('"tip": "ozel"', na=False) |
                                          _oz_df_tek["satirlar"].str.contains('"tip":"ozel"', na=False)]
            else:
                _oz_df_tek2 = pd.DataFrame()

            if _oz_df_tek2.empty:
                st.info("Henüz kayıtlı özel teklif yok.")
            else:
                _oz_tek_opts = ["-- Teklif Seçin --"] + [
                    f"[{int(r['id'])}] {r.get('musteri_adi','')} | {str(r.get('tarih',''))[:10]}"
                    for _,r in _oz_df_tek2.iterrows()]
                _oz_tek_sec = st.selectbox("Teklif Seç:", _oz_tek_opts, key="oz2_tek_sec")

                if _oz_tek_sec != "-- Teklif Seçin --" and "[" in _oz_tek_sec:
                    _oz_tid = int(_oz_tek_sec.split("]")[0].replace("[","").strip())
                    _oz_trow = _oz_df_tek2[_oz_df_tek2["id"]==_oz_tid].iloc[0]
                    st.caption(f"📅 {str(_oz_trow.get('tarih',''))[:16]} · 👤 {_oz_trow.get('olusturan','')} · 📝 {_oz_trow.get('notlar','')}")
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

                    _eak1,_eak2,_eak3 = st.columns(3)
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
                    with _eak2.expander("📝 Not Güncelle"):
                        _oz_yn = st.text_area("Not:",value=str(_oz_trow.get("notlar","")),height=70,key=f"oz2_not_up_{_oz_tid}")
                        if st.button("💾 Kaydet",key=f"oz2_not_btn_{_oz_tid}",use_container_width=True):
                            db_update("teklifler",{"notlar":_oz_yn},"id",_oz_tid)
                            st.success("✅"); st.rerun()
                    if _eak3.button("🗑️ Sil",key="oz2_tek_sil",use_container_width=True):
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
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    sablon_kolonlar = ["firma","yetkili","gsm","sabit","email","adres","ilce","il","durum","temsilci","islem_asamasi","beklenen_ciro","gerceklesen_ciro"]
    sablon_aciklama = {"firma":"Zorunlu - Firma adı","yetkili":"Yetkili kişi adı","gsm":"GSM no (05xxxxxxxxx)","sabit":"Sabit telefon","email":"Email adresi","adres":"Açık adres","ilce":"İlçe adı","il":"İl adı","durum":"Aktif / Hedef / Pasif","temsilci":"Satış temsilcisi","islem_asamasi":"İlk Temas / Teklif / Kazanıldı","beklenen_ciro":"Sayı (50000)","gerceklesen_ciro":"Sayı (35000)"}

    df_ck = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")
    _kayit_say = len(df_ck)

    _ek1, _ek2, _ek3 = st.columns(3)

    # ── KART 1 ────────────────────────────────────────────────────────────────
    with _ek1:
        st.markdown(f"""<div style='border:1.5px solid #bfdbfe;border-radius:10px;padding:16px 18px;background:#f0f6ff;min-height:160px;'>
<div style='display:flex;align-items:center;gap:10px;margin-bottom:10px;'>
  <div style='width:30px;height:30px;background:#1d4ed8;border-radius:7px;color:white;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;'>1</div>
  <span style='font-size:13px;font-weight:600;color:#1e293b;'>Şablon İndir</span>
</div>
<div style='font-size:11px;color:#475569;line-height:1.5;'>Hazır Excel şablonunu indir, doldur. Sütun başlıklarını değiştirme.</div>
</div>""", unsafe_allow_html=True)
        sablon_buf = io.BytesIO()
        pd.DataFrame(columns=sablon_kolonlar).to_excel(sablon_buf, index=False)
        sablon_buf.seek(0)
        st.download_button("📥 Şablonu İndir", data=sablon_buf, file_name="cari_sablon.xlsx", use_container_width=True, key="dl_sablon")

    # ── KART 2 ────────────────────────────────────────────────────────────────
    with _ek2:
        st.markdown("""<div style='border:1.5px solid #ede9fe;border-radius:10px;padding:16px 18px;background:#f5f3ff;min-height:160px;'>
<div style='display:flex;align-items:center;gap:10px;margin-bottom:10px;'>
  <div style='width:30px;height:30px;background:#7c3aed;border-radius:7px;color:white;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;'>2</div>
  <span style='font-size:13px;font-weight:600;color:#1e293b;'>Dosya Yükle</span>
</div>
<div style='font-size:11px;color:#475569;line-height:1.5;'>Doldurduğun Excel dosyasını yükle ve sisteme aktar.</div>
</div>""", unsafe_allow_html=True)
        yukl_dosya = st.file_uploader("", type=["xlsx","xls"], key="excel_yukle", label_visibility="collapsed")

    # ── KART 3 ────────────────────────────────────────────────────────────────
    with _ek3:
        st.markdown(f"""<div style='border:1.5px solid #bbf7d0;border-radius:10px;padding:16px 18px;background:#f0fdf4;min-height:160px;'>
<div style='display:flex;align-items:center;gap:10px;margin-bottom:10px;'>
  <div style='width:30px;height:30px;background:#16a34a;border-radius:7px;color:white;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;'>3</div>
  <span style='font-size:13px;font-weight:600;color:#1e293b;'>Veri Aktar</span>
</div>
<div style='font-size:11px;color:#475569;line-height:1.5;'>Sistemdeki <b>{_kayit_say} kayıt</b> Excel olarak dışa aktar.</div>
</div>""", unsafe_allow_html=True)
        if not df_ck.empty:
            aktar_buf = io.BytesIO()
            df_ck.to_excel(aktar_buf, index=False)
            aktar_buf.seek(0)
            st.download_button("📊 Tüm Carileri Aktar", data=aktar_buf, file_name="cari_listesi.xlsx", use_container_width=True, key="dl_cari")

    # ── YÜKLEME İŞLEMİ ────────────────────────────────────────────────────────
    if yukl_dosya:
        st.divider()
        try:
            df_yukl = pd.read_excel(yukl_dosya)
            df_yukl.columns = [str(c).strip().lower().replace(" ","_") for c in df_yukl.columns]
            if "firma" not in df_yukl.columns:
                st.error("❌ Zorunlu sütun eksik: firma")
            else:
                st.success(f"✅ {len(df_yukl)} satır okundu. Önizleme:")
                st.dataframe(df_yukl.head(10), use_container_width=True, hide_index=True)
                _ekl1, _ekl2 = st.columns(2)
                if _ekl1.button("✅ Sisteme Aktar", type="primary", use_container_width=True, key="excel_aktar_btn"):
                    _basarili=0; _hatali=0
                    for _,row in df_yukl.iterrows():
                        try:
                            _firma=str(row.get("firma","") or "").strip()
                            if not _firma: continue
                            db_insert("cari_kartlar",{"firma":_firma,"yetkili":str(row.get("yetkili","") or ""),"gsm":str(row.get("gsm","") or ""),"sabit":str(row.get("sabit","") or ""),"email":str(row.get("email","") or ""),"adres":str(row.get("adres","") or ""),"ilce":str(row.get("ilce","") or ""),"il":str(row.get("il","") or ""),"durum":str(row.get("durum","Hedef") or "Hedef"),"temsilci":str(row.get("temsilci","") or ""),"islem_asamasi":str(row.get("islem_asamasi","İlk Temas") or "İlk Temas"),"beklenen_ciro":float(row.get("beklenen_ciro",0) or 0),"gerceklesen_ciro":float(row.get("gerceklesen_ciro",0) or 0),"olusturan":st.session_state.get("kullanici",""),"silindi":0})
                            _basarili+=1
                        except: _hatali+=1
                    try: db_read.clear()
                    except: pass
                    if _basarili: st.success(f"✅ {_basarili} kayıt eklendi!")
                    if _hatali: st.warning(f"⚠️ {_hatali} kayıt eklenemedi.")
                    st.rerun()
                _ekl2.button("❌ İptal", use_container_width=True, key="excel_iptal_btn")
        except Exception as e:
            st.error(f"Dosya okunamadı: {e}")

elif aktif == "analiz":
    sayfa_log("analiz")
    import json as _aj

    st.markdown("## 🔍 Müşteri Görüşme Analizi")

    # ── ANA TABLAR ────────────────────────────────────────────────────────────
    _an_tab1, _an_tab2, _an_tab3 = st.tabs(["📋 Geçmiş Analizler", "✏️ Yeni / Düzenle", "📅 Takip Bekleyenler"])

    # ── DB FONKSİYONLARI ──────────────────────────────────────────────────────
    def _an_upsert(firma, veri):
        """Firma başına 1 analiz — varsa güncelle, yoksa ekle"""
        veri["firma"] = firma  # her zaman firma adını ekle
        try:
            sb = get_sb_client()
            if sb:
                _mevcut = sb.table("musteri_analiz").select("id").eq("firma", firma).execute()
                if _mevcut.data:
                    aid = _mevcut.data[0]["id"]
                    sb.table("musteri_analiz").update(veri).eq("id", aid).execute()
                    return True, aid
                else:
                    r = sb.table("musteri_analiz").insert(veri).execute()
                    return True, None
        except Exception as _sb_err:
            st.error(f"❌ Supabase kayıt hatası: {_sb_err}")
            return False, None
        try:
            conn = get_conn()
            conn.execute("""CREATE TABLE IF NOT EXISTS musteri_analiz (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                firma TEXT UNIQUE, yetkili TEXT, iletisim TEXT, sektor TEXT,
                amac TEXT, mdurum TEXT, bek_ciro REAL, ger_ciro REAL,
                kaynak TEXT, kargo TEXT, fatura TEXT, uapo TEXT, odeme TEXT,
                pazarlik TEXT, beklenti TEXT, teklif_tur TEXT, karar TEXT,
                sure TEXT, engel TEXT, sik TEXT, gecis TEXT, potansiyel TEXT,
                sonuc TEXT, not_alan TEXT, takip_tar TEXT, sonraki_adim TEXT,
                bolge TEXT, avm TEXT, fiyat_tablo TEXT, rakip TEXT,
                olusturan TEXT, tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            _mevcut = conn.execute("SELECT id FROM musteri_analiz WHERE firma=?", (firma,)).fetchone()
            if _mevcut:
                sets = ", ".join([f"{k}=?" for k in veri.keys()])
                conn.execute(f"UPDATE musteri_analiz SET {sets} WHERE firma=?", list(veri.values())+[firma])
            else:
                cols = ",".join(["firma"]+list(veri.keys()))
                vals = ",".join(["?"]+["?" for _ in veri])
                conn.execute(f"INSERT INTO musteri_analiz ({cols}) VALUES ({vals})", [firma]+list(veri.values()))
            conn.commit(); conn.close()
            return True, None
        except Exception as e:
            st.error(f"Kayıt hatası: {e}")
            return False, None

    def _an_getir_firma(firma):
        """Firma adına göre analizi getir"""
        try:
            sb = get_sb_client()
            if sb:
                r = sb.table("musteri_analiz").select("*").eq("firma", firma).execute()
                return r.data[0] if r.data else None
        except: pass
        try:
            conn = get_conn()
            row = conn.execute("SELECT * FROM musteri_analiz WHERE firma=?", (firma,)).fetchone()
            conn.close()
            if row:
                cols = [d[0] for d in conn.execute("PRAGMA table_info(musteri_analiz)").fetchall()]
                return dict(zip(cols, row))
        except: pass
        return None

    def _an_getir_tumü(limit=200):
        try:
            sb = get_sb_client()
            if sb:
                r = sb.table("musteri_analiz").select("*").order("tarih", desc=True).limit(limit).execute()
                return pd.DataFrame(r.data) if r.data else pd.DataFrame()
        except: pass
        try:
            conn = get_conn()
            conn.execute("""CREATE TABLE IF NOT EXISTS musteri_analiz (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                firma TEXT UNIQUE, yetkili TEXT, iletisim TEXT, sektor TEXT,
                amac TEXT, mdurum TEXT, bek_ciro REAL, ger_ciro REAL,
                kaynak TEXT, kargo TEXT, fatura TEXT, uapo TEXT, odeme TEXT,
                pazarlik TEXT, beklenti TEXT, teklif_tur TEXT, karar TEXT,
                sure TEXT, engel TEXT, sik TEXT, gecis TEXT, potansiyel TEXT,
                sonuc TEXT, not_alan TEXT, takip_tar TEXT, sonraki_adim TEXT,
                bolge TEXT, avm TEXT, fiyat_tablo TEXT, rakip TEXT,
                olusturan TEXT, tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            df = pd.read_sql_query(f"SELECT * FROM musteri_analiz ORDER BY tarih DESC LIMIT {limit}", conn)
            conn.close()
            return df
        except: return pd.DataFrame()

    def _an_sil(firma):
        try:
            sb = get_sb_client()
            if sb:
                sb.table("musteri_analiz").delete().eq("firma", firma).execute()
                return True
        except: pass
        try:
            conn = get_conn()
            conn.execute("DELETE FROM musteri_analiz WHERE firma=?", (firma,))
            conn.commit(); conn.close()
            return True
        except: return False

    with _an_tab1:
        # ── GEÇMİŞ ANALİZLER ─────────────────────────────────────────────────
        _df_tum_tab = _an_getir_tumü(limit=500)
        if _df_tum_tab.empty:
            st.info("📭 Henüz hiç analiz kaydedilmedi. 'Yeni / Düzenle' sekmesinden ilk analizinizi ekleyin.")
        else:
            # ── FİLTRELER ────────────────────────────────────────────────────
            _fa1,_fa2,_fa3,_fa4 = st.columns(4)
            _ff2 = _fa1.text_input("🔍 Firma ara", key="an_gecmis_ff", placeholder="firma adı...")
            _fs3 = _fa2.selectbox("Sonuç", ["Tümü","takip edilecek","teklif verildi","anlaşma yapıldı","beklemede","ilgisiz","randevu verildi"], key="an_gecmis_fs")
            _fp2 = _fa3.selectbox("Potansiyel", ["Tümü","çok yüksek","yüksek","orta","düşük","çok düşük"], key="an_gecmis_fp")
            _ft3 = _fa4.selectbox("Teklif Türü", ["Tümü","spot","özel anlaşma","sözleşme","dönemsel"], key="an_gecmis_ft")
            _df_f2 = _df_tum_tab.copy()
            if _ff2: _df_f2 = _df_f2[_df_f2["firma"].str.contains(_ff2, case=False, na=False)]
            if _fs3 != "Tümü": _df_f2 = _df_f2[_df_f2["sonuc"]==_fs3]
            if _fp2 != "Tümü": _df_f2 = _df_f2[_df_f2["potansiyel"]==_fp2]
            if _ft3 != "Tümü": _df_f2 = _df_f2[_df_f2["teklif_tur"].str.contains(_ft3, case=False, na=False)]
            st.caption(f"**{len(_df_f2)}** analiz")

            st.divider()

            for _ar_idx, _ar in _df_f2.reset_index(drop=True).iterrows():
                _pot_ic = {"çok yüksek":"🟢","yüksek":"🟢","orta":"🟡","düşük":"🟠","çok düşük":"🔴"}.get(str(_ar.get("potansiyel","")),"-")
                _tarih_val = _ar.get("tarih","")
                _tarih_str = str(_tarih_val)[:10] if _tarih_val and str(_tarih_val) not in ["None","nan",""] else ""
                _firma_goster = str(_ar.get("firma","") or "").strip() or "—"
                _bek = float(_ar.get('bek_ciro',0) or 0)
                _ger = float(_ar.get('ger_ciro',0) or 0)

                # ── KART (tümü açık, expander yok) ──────────────────────
                try:
                    _rak_list2 = _aj.loads(_ar.get("rakip","[]") or "[]")
                    _rak_str2 = ", ".join([f"{r.get('firma','')} ({r.get('fiyat','?')}₺)" for r in _rak_list2 if r.get('firma')]) or "—"
                except: _rak_str2 = "—"

                _not_html = f"<div style='background:#eff6ff;border-left:4px solid #3b82f6;padding:8px 12px;margin-top:8px;border-radius:4px;font-size:13px'>📝 <b>Not:</b> {_ar.get('not_alan','')}</div>" if _ar.get("not_alan") else ""

                st.markdown(f"""<div style='background:#ffffff;border:2px solid #e2e8f0;border-radius:12px;padding:20px;margin:10px 0'>
<div style='padding-bottom:12px;margin-bottom:14px;border-bottom:2px solid #f1f5f9'>
  <span style='font-size:20px;font-weight:800'>{_pot_ic} {_firma_goster}</span>&nbsp;&nbsp;
  <span style='background:#dbeafe;color:#1d4ed8;padding:2px 10px;border-radius:20px;font-size:12px'>📅 {_tarih_str or "—"}</span>&nbsp;
  <span style='background:#dcfce7;color:#166534;padding:2px 10px;border-radius:20px;font-size:12px'>📋 {_ar.get("sonuc","—") or "—"}</span>&nbsp;
  <span style='background:#fef9c3;color:#854d0e;padding:2px 10px;border-radius:20px;font-size:12px'>🎯 {_ar.get("potansiyel","—") or "—"}</span>&nbsp;
  <span style='background:#e0f2fe;color:#075985;padding:2px 10px;border-radius:20px;font-size:12px'>💰 Beklenen: <b>{_bek:,.0f} ₺</b></span>&nbsp;
  <span style='background:#f0fdf4;color:#14532d;padding:2px 10px;border-radius:20px;font-size:12px'>✅ Gerçekleşen: <b>{_ger:,.0f} ₺</b></span>
</div>
<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;font-size:13px'>
  <div>
    <p style='margin:5px 0'><b>👤 Yetkili:</b> {_ar.get("yetkili","—") or "—"}</p>
    <p style='margin:5px 0'><b>📞 İletişim:</b> {_ar.get("iletisim","—") or "—"}</p>
    <p style='margin:5px 0'><b>🏭 Sektör:</b> {_ar.get("sektor","—") or "—"}</p>
    <p style='margin:5px 0'><b>📌 Kaynak:</b> {_ar.get("kaynak","—") or "—"}</p>
    <p style='margin:5px 0'><b>🏆 Karar Verici:</b> {_ar.get("karar","—") or "—"} — Süre: {_ar.get("sure","—") or "—"}</p>
    <p style='margin:5px 0'><b>🕐 Takip Tarihi:</b> {_ar.get("takip_tar","—") or "—"}</p>
  </div>
  <div>
    <p style='margin:5px 0'><b>🎯 Analiz Amacı:</b> {_ar.get("amac","—") or "—"}</p>
    <p style='margin:5px 0'><b>👥 Müşteri Durumu:</b> {_ar.get("mdurum","—") or "—"}</p>
    <p style='margin:5px 0'><b>📦 Teklif Türü:</b> {_ar.get("teklif_tur","—") or "—"}</p>
    <p style='margin:5px 0'><b>🚚 Kullandığı Kargo:</b> {_ar.get("kargo","—") or "—"}</p>
    <p style='margin:5px 0'><b>🧾 Fatura:</b> {_ar.get("fatura","—") or "—"} / UA-PO: {_ar.get("uapo","—") or "—"}</p>
    <p style='margin:5px 0'><b>💳 Vade/Ödeme:</b> {_ar.get("odeme","—") or "—"} — Pazarlık: {_ar.get("pazarlik","—") or "—"}</p>
  </div>
  <div>
    <p style='margin:5px 0'><b>💬 Müşteri Beklentisi:</b> {_ar.get("beklenti","—") or "—"}</p>
    <p style='margin:5px 0'><b>🚧 Satışa Engel:</b> {_ar.get("engel","—") or "—"}</p>
    <p style='margin:5px 0'><b>😤 Şikayetleri:</b> {_ar.get("sik","—") or "—"}</p>
    <p style='margin:5px 0'><b>🔄 Geçiş Sebebi:</b> {_ar.get("gecis","—") or "—"}</p>
    <p style='margin:5px 0'><b>⚔️ Rakip Kargolar:</b> {_rak_str2}</p>
    <p style='margin:5px 0'><b>➡️ Sonraki Adım:</b> {_ar.get("sonraki_adim","—") or "—"}</p>
  </div>
</div>
{_not_html}
</div>""", unsafe_allow_html=True)

                # Tablolar
                try:
                    _ft2b = _aj.loads(_ar.get("fiyat_tablo","[]") or "[]")
                    if _ft2b and any(s.get("il") and s.get("il")!="--" for s in _ft2b):
                        st.markdown("**💰 Fiyat Tablosu:**")
                        st.dataframe(pd.DataFrame(_ft2b), use_container_width=True, hide_index=True)
                except: pass
                try:
                    _bt2b = _aj.loads(_ar.get("bolge","[]") or "[]")
                    if _bt2b and any(s.get("il") and s.get("il")!="--" for s in _bt2b):
                        st.markdown("**📍 Bölge Teslimat:**")
                        st.dataframe(pd.DataFrame(_bt2b), use_container_width=True, hide_index=True)
                except: pass
                try:
                    _at2b = _aj.loads(_ar.get("avm","[]") or "[]")
                    if _at2b and any(s.get("avm") for s in _at2b):
                        st.markdown("**🏬 AVM Teslimatları:**")
                        st.dataframe(pd.DataFrame(_at2b), use_container_width=True, hide_index=True)
                except: pass

                # AKSİYON BUTONLARI
                _wbg = st.columns(4)
                if _wbg[0].button("✏️ Düzenle", key=f"an_gduz_{_ar_idx}", use_container_width=True):
                    if "an_cari_sec" in st.session_state: del st.session_state["an_cari_sec"]
                    st.session_state["an_firma_input"] = str(_ar.get("firma",""))
                    for _k3 in ["an_fiyat_satirlar","an_bolge_satirlar","an_avm_satirlar","an_rakip_satirlar"]:
                        if _k3 in st.session_state: del st.session_state[_k3]
                    st.rerun()
                _tel3b = str(_ar.get("iletisim","") or "").replace(" ","").replace("-","")
                if _tel3b and "@" not in _tel3b:
                    if _tel3b.startswith("0"): _tel3b="90"+_tel3b[1:]
                    _wa3b = ("Merhaba " + str(_ar.get("firma","")) + ", gorusemiz icin tesekkurler.").replace(" ","%20")
                    _wbg[1].markdown(f"<a href='https://wa.me/{_tel3b}?text={_wa3b}' target='_blank'><button style='width:100%;padding:5px;font-size:11px;background:#25d366;color:white;border:none;border-radius:5px;cursor:pointer;'>💬 WA</button></a>", unsafe_allow_html=True)
                if _wbg[2].button("📄 Teklif", key=f"an_gtek_{_ar_idx}", use_container_width=True):
                    st.session_state["aktif_tab"] = "teklif"
                    st.session_state["pending_hedef_mus"] = str(_ar.get("firma",""))
                    _an_ttur_str2 = str(_ar.get("teklif_tur","") or "")
                    if "özel" in _an_ttur_str2.lower() or "sözleşme" in _an_ttur_str2.lower():
                        st.session_state["global_teklif_turu"] = "🤝 Özel Anlaşma"
                    else:
                        st.session_state["global_teklif_turu"] = "🚀 Spot Teklif"
                    st.rerun()
                if _wbg[3].button("🗑 Sil", key=f"an_gsil_{_ar_idx}", use_container_width=True):
                    if _an_sil(str(_ar.get("firma",""))):
                        st.success("Analiz silindi!")
                        st.rerun()

            # ── ÖZET METRİKLER ───────────────────────────────────────────
            st.divider()
            _ki1,_ki2,_ki3,_ki4,_ki5,_ki6 = st.columns(6)
            _bek_top = 0; _ger_top = 0
            try: _bek_top = float(_df_f2["bek_ciro"].sum())
            except: pass
            try: _ger_top = float(_df_f2["ger_ciro"].sum())
            except: pass
            _gerceklesme = round((_ger_top/_bek_top)*100,1) if _bek_top > 0 else 0
            _ki1.metric("📋 Toplam Analiz", len(_df_f2))
            _ki2.metric("🟢 Yüksek Potansiyel", len(_df_f2[_df_f2["potansiyel"].isin(["yüksek","çok yüksek"])]) if "potansiyel" in _df_f2.columns else 0)
            _ki3.metric("📄 Teklif Verildi", len(_df_f2[_df_f2["sonuc"]=="teklif verildi"]) if "sonuc" in _df_f2.columns else 0)
            _ki4.metric("🤝 Anlaşma", len(_df_f2[_df_f2["sonuc"]=="anlaşma yapıldı"]) if "sonuc" in _df_f2.columns else 0)
            _ki5.metric("💰 Beklenen Ciro", f"{_bek_top:,.0f} ₺")
            _ki6.metric("✅ Gerçekleşen", f"{_ger_top:,.0f} ₺", delta=f"%{_gerceklesme}")

            # (takip tablosu yukarıya taşındı)

            # ── Ciro Tablosu ─────────────────────────────────────────────────
            try:
                _ciro_df = _df_f2[["firma","bek_ciro","ger_ciro","potansiyel","sonuc"]].copy()
                _ciro_df["bek_ciro"] = pd.to_numeric(_ciro_df["bek_ciro"], errors="coerce").fillna(0)
                _ciro_df["ger_ciro"] = pd.to_numeric(_ciro_df["ger_ciro"], errors="coerce").fillna(0)
                _ciro_top = _ciro_df[_ciro_df["bek_ciro"]>0].sort_values("bek_ciro", ascending=False).head(10)
                if not _ciro_top.empty:
                    st.markdown("**💰 Beklenen Ciro (Top 10)**")
                    _ciro_top.columns = ["Firma","Beklenen ₺","Gerçekleşen ₺","Potansiyel","Sonuç"]
                    st.dataframe(_ciro_top, use_container_width=True, hide_index=True)
            except: pass

            # Excel dışa aktar
            try:
                _exp_buf = io.BytesIO()
                _df_f2.to_excel(_exp_buf, index=False); _exp_buf.seek(0)
                st.download_button("📥 Tüm Analizleri Excel'e Aktar", data=_exp_buf,
                    file_name=f"musteri_analizleri_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    use_container_width=True)
            except: pass

    with _an_tab3:
        # ── TAKİP BEKLEYENLERr ───────────────────────────────────────────────
        _df_tak_all = _an_getir_tumü(limit=500)
        if _df_tak_all.empty:
            st.info("Henüz analiz kaydı yok.")
        else:
            try:
                _tak_df3 = _df_tak_all[_df_tak_all["takip_tar"].notna() & (_df_tak_all["takip_tar"] != "") & (_df_tak_all["takip_tar"] != "None")].copy()
                if _tak_df3.empty:
                    st.info("Takip tarihi girilmiş analiz bulunamadı.")
                else:
                    _tak_df3["takip_tar"] = pd.to_datetime(_tak_df3["takip_tar"], errors="coerce")
                    _tak_df3 = _tak_df3.dropna(subset=["takip_tar"]).sort_values("takip_tar")
                    # None firma filtrele
                    _tak_df3 = _tak_df3[_tak_df3["firma"].notna() & (_tak_df3["firma"].astype(str) != "None") & (_tak_df3["firma"].astype(str) != "")]
                    _tak_df3["takip_tar"] = _tak_df3["takip_tar"].dt.normalize()
                    from datetime import date as _date
                    _bugun = pd.Timestamp(_date.today())
                    _gecmis     = _tak_df3[_tak_df3["takip_tar"] < _bugun]
                    _bugun_yarin= _tak_df3[(_tak_df3["takip_tar"] >= _bugun) & (_tak_df3["takip_tar"] <= _bugun + pd.Timedelta(days=2))]
                    _gelecek    = _tak_df3[_tak_df3["takip_tar"] > _bugun + pd.Timedelta(days=2)]

                    def _tak_goster(df, baslik):
                        if df.empty: return
                        st.markdown(f"#### {baslik}")
                        _s = df[["firma","takip_tar","sonuc","potansiyel","olusturan"]].copy()
                        _s["takip_tar"] = _s["takip_tar"].dt.strftime("%d.%m.%Y")
                        _s.columns = ["Firma","Takip Tarihi","Sonuç","Potansiyel","Temsilci"]
                        st.dataframe(_s, use_container_width=True, hide_index=True)

                    _tak_goster(_bugun_yarin, "🔴 Bugün / Yarın")
                    _tak_goster(_gecmis, "🟠 Geçmiş (Yapılmamış)")
                    _tak_goster(_gelecek, "🟢 Yaklaşan")
                    if _bugun_yarin.empty and _gecmis.empty and _gelecek.empty:
                        st.info("Firma adı girilmiş takip kaydı bulunamadı.")
            except Exception as _te:
                st.error(f"Hata: {_te}")

    with _an_tab2:
        # ── YENİ / DÜZENLE FORMU ─────────────────────────────────────────────
        # ── MÜŞTERI SEÇİMİ — cari listeden ya da manuel ───────────────────────────
        st.markdown("### Hangi müşteri için analiz?")
        _df_cari_an = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")
        _mac1, _mac2 = st.columns([3, 1])
        _cari_opts_an = ["-- Yeni / Manuel Yaz --"] + [f"[{int(r['id'])}] {r['firma']}" for _,r in _df_cari_an.iterrows()]
        _cari_sec_an = _mac1.selectbox("Cari listeden seç", _cari_opts_an, key="an_cari_sec")
        _an_firma_input = _mac2.text_input("veya firma adı yaz", key="an_firma_input", placeholder="Manuel yaz...")

        # Firmayı belirle
        _secili_firma = ""
        _secili_cari = None
        if _cari_sec_an != "-- Yeni / Manuel Yaz --" and "[" in _cari_sec_an:
            _cid = int(_cari_sec_an.split("]")[0].replace("[","").strip())
            _crow = _df_cari_an[_df_cari_an["id"]==_cid]
            if not _crow.empty:
                _secili_cari = _crow.iloc[0]
                _secili_firma = str(_secili_cari.get("firma",""))
        elif _an_firma_input.strip():
            _secili_firma = _an_firma_input.strip()

        if not _secili_firma:
            st.info("👆 Cari listeden müşteri seç **veya** sağdaki kutuya firma adı yaz.")
            st.stop()

        # Mevcut analizi yükle
        _mevcut_an = _an_getir_firma(_secili_firma)
        _duzenle_mod = _mevcut_an is not None

        # Manuel yazılan firma — cari listede yok ve yeni analiz — kart açmaya zorla
        _cari_var = not _df_cari_an[_df_cari_an["firma"].str.lower()==_secili_firma.lower()].empty
        if not _cari_var and not _duzenle_mod:
            st.warning(f"⚠️ **{_secili_firma}** cari listede yok. Analiz yapmadan önce kart açılmalı.")
            st.markdown("##### 🆕 Yeni Cari Kart Bilgileri")
            _kf1,_kf2,_kf3,_kf4 = st.columns(4)
            _kart_yetkili = _kf1.text_input("Yetkili / Ünvan", key="kart_yetkili", placeholder="Ad Soyad")
            _kart_gsm     = _kf2.text_input("GSM", key="kart_gsm", placeholder="05xx xxx xx xx")
            _kart_email   = _kf3.text_input("E-posta", key="kart_email", placeholder="mail@...")
            _kart_il      = _kf4.text_input("İl", key="kart_il", placeholder="İstanbul")
            _kf5,_kf6 = st.columns(2)
            _kart_asama = _kf5.selectbox("İşlem Aşaması", ["İlk Temas","Görüşme Yapıldı","Teklif Verildi","Müzakere","Kazanıldı","Kaybedildi"], key="kart_asama")
            _kart_durum = _kf6.selectbox("Durum", ["Hedef","Aktif","Pasif"], key="kart_durum")
            _kb1,_kb2 = st.columns(2)
            if _kb1.button("✅ Kartı Aç ve Analize Devam Et", type="primary", use_container_width=True, key="an_kart_ac"):
                db_insert("cari_kartlar",{
                    "firma":_secili_firma,"yetkili":_kart_yetkili or "","gsm":_kart_gsm or "",
                    "email":_kart_email or "","il":_kart_il or "","durum":_kart_durum,
                    "islem_asamasi":_kart_asama,"beklenen_ciro":0,
                    "olusturan":st.session_state.get("kullanici",""),"silindi":0
                })
                try: db_read.clear()
                except: pass
                st.success(f"✅ {_secili_firma} cari listeye eklendi!")
                st.rerun()
            if _kb2.button("❌ İptal", use_container_width=True, key="an_kart_iptal"):
                st.session_state.pop("an_firma_input", None)
                st.rerun()
            st.stop()

        if _duzenle_mod:
            st.success(f"✅ **{_secili_firma}** için kayıtlı analiz bulundu — düzenliyorsunuz")
        else:
            st.info(f"🆕 **{_secili_firma}** için yeni analiz oluşturuyorsunuz")

        def _mv(key, default=""):
            """Mevcut analiz verisini getir"""
            if _mevcut_an and _mevcut_an.get(key):
                return _mevcut_an[key]
            return default

        def _mv_list(key):
            val = _mv(key, "")
            if not val: return []
            return [x.strip() for x in str(val).split(",") if x.strip()]

        def _mv_json(key):
            val = _mv(key, "[]")
            try: return _aj.loads(val or "[]")
            except: return []

        # ── ANALİZ FORMU ──────────────────────────────────────────────────────────────

        # Kalıcı listeler - Supabase'den veya session'dan oku
        def _kalici_liste_oku(anahtar, varsayilan):
            try:
                sb = get_sb_client()
                if sb:
                    r = sb.table("kullanici_tercih").select("deger").eq("kullanici","__sistem__").eq("anahtar", anahtar).execute()
                    if r.data:
                        import json as _jk; return _jk.loads(r.data[0]["deger"])
            except: pass
            return st.session_state.get(f"_kal_{anahtar}", varsayilan)

        def _kalici_liste_kaydet(anahtar, liste):
            import json as _jk
            st.session_state[f"_kal_{anahtar}"] = liste
            try:
                sb = get_sb_client()
                if sb:
                    mevcut = sb.table("kullanici_tercih").select("id").eq("kullanici","__sistem__").eq("anahtar",anahtar).execute()
                    if mevcut.data:
                        sb.table("kullanici_tercih").update({"deger":_jk.dumps(liste,ensure_ascii=False)}).eq("kullanici","__sistem__").eq("anahtar",anahtar).execute()
                    else:
                        sb.table("kullanici_tercih").insert({"kullanici":"__sistem__","anahtar":anahtar,"deger":_jk.dumps(liste,ensure_ascii=False)}).execute()
            except: pass

        # Kalıcı listeler
        _kal_kaynak = _kalici_liste_oku("an_kaynak_liste", ["soğuk arama","referans","linkedin","internet","ziyaret","fuar","sosyal medya","eski müşteri"])
        _kal_sektor = _kalici_liste_oku("an_sektor_liste", ["Tekstil","Gıda","Otomotiv","Elektronik","E-ticaret","AVM/Perakende","Kimya","Mobilya","Medikal","Kozmetik"])
        _kal_kargo  = _kalici_liste_oku("an_kargo_liste",  ["Aras","Yurtiçi","MNG","Sürat","PTT","DHL","UPS","Horoz"])
        _kal_avm    = _kalici_liste_oku("an_avm_liste",    ["Cevahir AVM","Forum İstanbul","Metrocity","Kanyon","Ankamall","Optimum","Korupark","Hilltown","Agora","Özdilek","Piazza","TerraCity"])

        # Temsilciler - sistemdeki kullanıcılar
        try:
            _sb_tmp = get_sb_client()
            if _sb_tmp:
                _usr_r = _sb_tmp.table("kullanicilar").select("kullanici_adi").execute()
                _temsilci_liste = [r["kullanici_adi"] for r in _usr_r.data] if _usr_r.data else [st.session_state.get("kullanici","")]
            else:
                _cn_tmp = get_conn()
                _usr_rows = _cn_tmp.execute("SELECT kullanici_adi FROM kullanicilar").fetchall()
                _cn_tmp.close()
                _temsilci_liste = [r[0] for r in _usr_rows] if _usr_rows else [st.session_state.get("kullanici","")]
        except: _temsilci_liste = [st.session_state.get("kullanici","")]

        # Mesai saatleri 07:00-19:00
        import datetime as _dt
        _saat_secenekleri = [f"{h:02d}:{m:02d}" for h in range(7,20) for m in (0,30)]

        st.divider()

        # ── SATIR 1: Temel Bilgiler ────────────────────────────────────────────────
        st.markdown("##### 👤 Kişi & Görüşme Bilgileri")
        _r1c1,_r1c2,_r1c3,_r1c4,_r1c5,_r1c6 = st.columns(6)
        _an_yetkili    = _r1c1.text_input("Yetkili / Ünvan", value=_mv("yetkili",""), key="an_yetkili", placeholder="Ad Soyad — Ünvan")
        _an_iletisim   = _r1c2.text_input("Tel / E-posta", value=_mv("iletisim",""), key="an_iletisim", placeholder="05xx / mail@...")
        _an_tarih      = _r1c3.date_input("Görüşme tarihi", key="an_tarih")
        _saat_def      = _mv("saat","09:00"); _saat_def = _saat_def if _saat_def in _saat_secenekleri else "09:00"
        _an_saat       = _r1c4.selectbox("Saat", _saat_secenekleri, index=_saat_secenekleri.index(_saat_def), key="an_saat")
        _temsilci_def  = _mv("olusturan", st.session_state.get("kullanici",""))
        _temsilci_idx  = _temsilci_liste.index(_temsilci_def) if _temsilci_def in _temsilci_liste else 0
        _an_temsilci   = _r1c5.selectbox("Temsilci", _temsilci_liste, index=_temsilci_idx, key="an_temsilci")
        _an_mdurum     = _r1c6.selectbox("Müşteri Durumu", ["yeni","mevcut","eski","rakip müşterisi"], index=["yeni","mevcut","eski","rakip müşterisi"].index(_mv("mdurum","yeni")) if _mv("mdurum","yeni") in ["yeni","mevcut","eski","rakip müşterisi"] else 0, key="an_mdurum")

        # ── SATIR 2: Kaynak & Sektör (kalıcı, tekrar yok) ──────────────────────────
        st.markdown("##### 🔍 Kaynak & Sektör")
        _r2c1,_r2c2,_r2c3,_r2c4 = st.columns([2,1,2,1])
        _an_kaynak_sec = _r2c1.selectbox("Nereden Bulundu?", ["-- Seç --"] + _kal_kaynak + ["+ Yeni Ekle"], key="an_kaynak_sec")
        _an_kaynak_yeni = _r2c2.text_input("Yeni kaynak", key="an_kaynak_yeni", placeholder="yaz ve ekle", label_visibility="visible") if _an_kaynak_sec == "+ Yeni Ekle" else ""
        if _an_kaynak_yeni and _an_kaynak_yeni not in _kal_kaynak:
            _kal_kaynak.append(_an_kaynak_yeni); _kalici_liste_kaydet("an_kaynak_liste", _kal_kaynak); st.rerun()
        _an_kaynak_val = _an_kaynak_sec if _an_kaynak_sec not in ["-- Seç --","+ Yeni Ekle"] else _mv("kaynak","")

        _an_sektor_sec = _r2c3.selectbox("Sektör", ["-- Seç --"] + _kal_sektor + ["+ Yeni Ekle"], index=(["-- Seç --"]+_kal_sektor+["+ Yeni Ekle"]).index(_mv("sektor","-- Seç --")) if _mv("sektor","") in _kal_sektor else 0, key="an_sektor_sec")
        _an_sektor_yeni = _r2c4.text_input("Yeni sektör", key="an_sektor_yeni", placeholder="yaz ve ekle") if _an_sektor_sec == "+ Yeni Ekle" else ""
        if _an_sektor_yeni and _an_sektor_yeni not in _kal_sektor:
            _kal_sektor.append(_an_sektor_yeni); _kalici_liste_kaydet("an_sektor_liste", _kal_sektor); st.rerun()
        _an_sektor = _an_sektor_sec if _an_sektor_sec not in ["-- Seç --","+ Yeni Ekle"] else _mv("sektor","")

        # ── SATIR 3: Ciro & Potansiyel ─────────────────────────────────────────────
        st.markdown("##### 💰 Ciro & Değerlendirme")
        _r3c1,_r3c2,_r3c3,_r3c4,_r3c5,_r3c6 = st.columns(6)
        _an_bek_ciro = _r3c1.text_input("Beklenen Ciro (₺/ay)", value=str(int(_mv("bek_ciro",0) or 0)) if _mv("bek_ciro",0) else "", key="an_bek_ciro", placeholder="₺")
        _an_ger_ciro = _r3c2.text_input("Gerçekleşen Ciro (₺/ay)", value=str(int(_mv("ger_ciro",0) or 0)) if _mv("ger_ciro",0) else "", key="an_ger_ciro", placeholder="₺")
        _pot_list = ["çok düşük","düşük","orta","yüksek","çok yüksek"]
        _an_pot  = _r3c3.select_slider("Potansiyel", options=_pot_list, value=_mv("potansiyel","orta") if _mv("potansiyel","orta") in _pot_list else "orta", key="an_pot")
        _sonuc_list = ["takip edilecek","teklif verildi","beklemede","ilgisiz","randevu verildi","anlaşma yapıldı"]
        _an_sonuc = _r3c4.selectbox("Görüşme Sonucu", _sonuc_list, index=_sonuc_list.index(_mv("sonuc","takip edilecek")) if _mv("sonuc","takip edilecek") in _sonuc_list else 0, key="an_sonuc")
        _an_takip = _r3c5.date_input("Takip Tarihi", key="an_takip_tar")
        _karar_list = ["yetkili kendisi","üst yönetim","komite","bilinmiyor"]
        _an_karar = _r3c6.selectbox("Karar Verici", _karar_list, index=_karar_list.index(_mv("karar","yetkili kendisi")) if _mv("karar","yetkili kendisi") in _karar_list else 0, key="an_karar")

        # ── SATIR 4: Teklif Türü (sadece Spot veya Özel, zorunlu) ─────────────────
        st.markdown("##### 📄 Teklif Türü")
        _ttur_opts = ["🚀 Spot Teklif", "🤝 Özel Anlaşma"]
        _ttur_def  = "🤝 Özel Anlaşma" if "özel" in _mv("teklif_tur","").lower() else "🚀 Spot Teklif"
        _an_ttur_radio = st.radio("", _ttur_opts, index=_ttur_opts.index(_ttur_def), horizontal=True, key="an_ttur_radio", label_visibility="collapsed")
        _an_ttur_val   = "özel anlaşma" if "Özel" in _an_ttur_radio else "spot"
        if _an_ttur_val == "spot":
            st.info("⚡ **Spot Teklif** seçildi — bu müşteri Spot Teklif ekranında değerlendirilecek. Teklif verirken hatırlatılacak.")
        else:
            st.info("🤝 **Özel Anlaşma** seçildi — bu müşteri Özel Anlaşma ekranında değerlendirilecek. Teklif verirken hatırlatılacak.")

        # ── SATIR 5: Kargo (kalıcı, tekrar yok) ────────────────────────────────────
        st.markdown("##### 🚚 Kullandığı Kargo & Ödeme")
        _r5c1,_r5c2,_r5c3,_r5c4,_r5c5 = st.columns(5)
        _an_kargo_sec  = _r5c1.selectbox("Kullandığı Kargo", ["-- Seç --"] + _kal_kargo + ["+ Yeni Ekle"], key="an_kargo_sec")
        _an_kargo_yeni = _r5c2.text_input("Yeni kargo", key="an_kargo_yeni", placeholder="yaz ve ekle") if _an_kargo_sec == "+ Yeni Ekle" else ""
        if _an_kargo_yeni and _an_kargo_yeni not in _kal_kargo:
            _kal_kargo.append(_an_kargo_yeni); _kalici_liste_kaydet("an_kargo_liste", _kal_kargo); st.rerun()
        _an_kargo_val = _an_kargo_sec if _an_kargo_sec not in ["-- Seç --","+ Yeni Ekle"] else _mv("kargo","")
        _an_aylik_odeme = _r5c3.text_input("Aylık Kargo Ödemesi (₺)", value=str(int(_mv("aylik_odeme",0) or 0)) if _mv("aylik_odeme",0) else "", key="an_aylik_odeme", placeholder="₺/ay")
        _fatura_list = ["faturalı","faturasız","karma","bilinmiyor"]
        _an_fatura = _r5c4.selectbox("Faturalama", _fatura_list, index=_fatura_list.index(_mv("fatura","faturalı")) if _mv("fatura","faturalı") in _fatura_list else 0, key="an_fatura")
        _uapo_list = ["UA — gönderici öder","PO — alıcı öder","karma","bilinmiyor"]
        _an_uapo = _r5c5.selectbox("UA / PO", _uapo_list, index=_uapo_list.index(_mv("uapo","UA — gönderici öder")) if _mv("uapo","UA — gönderici öder") in _uapo_list else 0, key="an_uapo")

        # ── SATIR 6: Hacim & Teslimat ───────────────────────────────────────────────
        st.markdown("##### 📦 Hacim, Desi & Teslimat")
        _r6c1,_r6c2,_r6c3,_r6c4,_r6c5,_r6c6,_r6c7 = st.columns(7)
        _an_koli_adet = _r6c1.text_input("Aylık Koli Adedi", value=_mv("koli_adet",""), key="an_koli_adet", placeholder="adet")
        _an_koli_desi = _r6c2.text_input("Koli Desi (ort.)", value=_mv("kd_min",""), key="an_koli_desi", placeholder="desi")
        _an_koli_kg   = _r6c3.text_input("Koli Ağırlık (kg)", value=_mv("koli_kg",""), key="an_koli_kg", placeholder="kg")
        _an_pal_adet  = _r6c4.text_input("Aylık Palet Adedi", value=_mv("pal_adet",""), key="an_pal_adet", placeholder="adet")
        _an_pal_desi  = _r6c5.text_input("Palet Desi (ort.)", value=_mv("pd_min",""), key="an_pal_desi", placeholder="desi")
        _an_pal_kg    = _r6c6.text_input("Palet Ağırlık (kg)", value=_mv("pal_kg",""), key="an_pal_kg", placeholder="kg")
        _bsik_list = ["günlük","hf. 2–3","haftalık","aylık","düzensiz"]
        _bsik_def = _mv("sevk_siklik","haftalık"); _bsik_def = _bsik_def if _bsik_def in _bsik_list else "haftalık"
        _an_sevk_siklik = _r6c7.selectbox("Sevkiyat Sıklığı", _bsik_list, index=_bsik_list.index(_bsik_def), key="an_sevk_siklik")

        # ── SATIR 7: İl-Ürün-Fiyat Tablosu (Bölge + Fiyat birleşik) ───────────────
        st.markdown("##### 🗺️ Bölge & Fiyat Tablosu")
        st.caption("İl · Ürün · Min Desi · Max Desi · Aylık Adet · Müşteri Ödüyor ₺ · Bizim Teklifimiz ₺ · Sıklık · Not")
        _il_list  = ["--","İstanbul","Ankara","İzmir","Bursa","Manisa","Çorlu/Çerkezköy","Konya","Kocaeli","Adana","Tüm TR"]
        _ur_list  = ["koli","palet","parsiyel","TIR"]
        _def_fiyat = _mv_json("fiyat_tablo") or [{"il":"","urun":"koli","min":"","max":"","adet":"","musteri":"","biz":"","siklik":"haftalık","not":""}]
        if "an_fiyat_satirlar" not in st.session_state:
            st.session_state["an_fiyat_satirlar"] = _def_fiyat
        for _fi in range(len(st.session_state["an_fiyat_satirlar"])):
            _fs = st.session_state["an_fiyat_satirlar"][_fi]
            _fc = st.columns([1.2,0.7,0.5,0.5,0.6,0.8,0.8,0.7,1,0.25])
            st.session_state["an_fiyat_satirlar"][_fi]["il"]     = _fc[0].selectbox("", _il_list, index=_il_list.index(_fs.get("il","--")) if _fs.get("il","--") in _il_list else 0, key=f"an_fil_{_fi}", label_visibility="collapsed")
            st.session_state["an_fiyat_satirlar"][_fi]["urun"]   = _fc[1].selectbox("", _ur_list, index=_ur_list.index(_fs.get("urun","koli")) if _fs.get("urun","koli") in _ur_list else 0, key=f"an_furun_{_fi}", label_visibility="collapsed")
            st.session_state["an_fiyat_satirlar"][_fi]["min"]    = _fc[2].text_input("", value=_fs.get("min",""), key=f"an_fmin_{_fi}", placeholder="min", label_visibility="collapsed")
            st.session_state["an_fiyat_satirlar"][_fi]["max"]    = _fc[3].text_input("", value=_fs.get("max",""), key=f"an_fmax_{_fi}", placeholder="max", label_visibility="collapsed")
            st.session_state["an_fiyat_satirlar"][_fi]["adet"]   = _fc[4].text_input("", value=_fs.get("adet",""), key=f"an_fadet_{_fi}", placeholder="adet", label_visibility="collapsed")
            st.session_state["an_fiyat_satirlar"][_fi]["musteri"]= _fc[5].text_input("", value=_fs.get("musteri",""), key=f"an_fmus_{_fi}", placeholder="müşteri ₺", label_visibility="collapsed")
            st.session_state["an_fiyat_satirlar"][_fi]["biz"]    = _fc[6].text_input("", value=_fs.get("biz",""), key=f"an_fbiz_{_fi}", placeholder="bizim ₺", label_visibility="collapsed")
            st.session_state["an_fiyat_satirlar"][_fi]["siklik"] = _fc[7].selectbox("", _bsik_list, index=_bsik_list.index(_fs.get("siklik","haftalık")) if _fs.get("siklik","haftalık") in _bsik_list else 0, key=f"an_fsik_{_fi}", label_visibility="collapsed")
            st.session_state["an_fiyat_satirlar"][_fi]["not"]    = _fc[8].text_input("", value=_fs.get("not",""), key=f"an_fnot_{_fi}", placeholder="not / kısıt", label_visibility="collapsed")
            if _fc[9].button("×", key=f"an_fdel_{_fi}") and len(st.session_state["an_fiyat_satirlar"])>1:
                st.session_state["an_fiyat_satirlar"].pop(_fi); st.rerun()
        if st.button("+ Bölge/Fiyat Satırı Ekle", key="an_fiyat_ekle"):
            st.session_state["an_fiyat_satirlar"].append({"il":"","urun":"koli","min":"","max":"","adet":"","musteri":"","biz":"","siklik":"haftalık","not":""}); st.rerun()

        # ── SATIR 8: AVM Teslimatları (kalıcı AVM listesi) ─────────────────────────
        st.markdown("##### 🏬 AVM Teslimatları")
        _def_avm = _mv_json("avm") or []
        if "an_avm_satirlar" not in st.session_state:
            st.session_state["an_avm_satirlar"] = _def_avm
        _ash_list = ["--","İstanbul","Ankara","İzmir","Bursa","Manisa","Çorlu","Kocaeli","Konya","Diğer"]
        for _ai in range(len(st.session_state["an_avm_satirlar"])):
            _as2 = st.session_state["an_avm_satirlar"][_ai]
            _ac2 = st.columns([2.5,1,1.5,1.5,1.5,0.3])
            _avm_sec = _ac2[0].selectbox("", ["-- Seç --"]+_kal_avm+["+ Yeni AVM"], index=(["-- Seç --"]+_kal_avm+["+ Yeni AVM"]).index(_as2.get("avm","-- Seç --")) if _as2.get("avm") in _kal_avm else 0, key=f"an_aavm_{_ai}", label_visibility="collapsed")
            if _avm_sec == "+ Yeni AVM":
                _avm_yeni = _ac2[1].text_input("", key=f"an_avm_yeni_{_ai}", placeholder="AVM adı", label_visibility="collapsed")
                if _avm_yeni and _avm_yeni not in _kal_avm:
                    _kal_avm.append(_avm_yeni); _kalici_liste_kaydet("an_avm_liste", _kal_avm); st.rerun()
            else:
                st.session_state["an_avm_satirlar"][_ai]["avm"] = _avm_sec
                _ac2[1].empty()
            st.session_state["an_avm_satirlar"][_ai]["sehir"]= _ac2[2].selectbox("", _ash_list, index=_ash_list.index(_as2.get("sehir","--")) if _as2.get("sehir","--") in _ash_list else 0, key=f"an_asehir_{_ai}", label_visibility="collapsed")
            st.session_state["an_avm_satirlar"][_ai]["urun"] = _ac2[3].text_input("", value=_as2.get("urun",""), key=f"an_aurun_{_ai}", placeholder="koli/palet-adet", label_visibility="collapsed")
            st.session_state["an_avm_satirlar"][_ai]["saat"] = _ac2[4].text_input("", value=_as2.get("saat",""), key=f"an_asaat_{_ai}", placeholder="giriş saati kısıtı", label_visibility="collapsed")
            if _ac2[5].button("×", key=f"an_adel_{_ai}") and len(st.session_state["an_avm_satirlar"])>0:
                st.session_state["an_avm_satirlar"].pop(_ai); st.rerun()
        if st.button("+ AVM Ekle", key="an_avm_ekle"):
            st.session_state["an_avm_satirlar"].append({"avm":"","sehir":"--","urun":"","saat":""}); st.rerun()

        # ── SATIR 9: Rakip Analizi ──────────────────────────────────────────────────
        st.markdown("##### ⚔️ Rakip Analizi")
        st.caption("Rakip Firma · Durum · Fiyat Avantajı · Hız · Hasar Oranı · AVM Girişi · İlişki · Diğer Sebep")
        _def_rakip = _mv_json("rakip") or [{"firma":"","durum":"orta","fiyat_av":"","hiz":"","hasar":"","avm":"","iliski":"","sebep":""}]
        if "an_rakip_satirlar" not in st.session_state:
            st.session_state["an_rakip_satirlar"] = _def_rakip
        _rd_list = ["güçlü","orta","zayıf"]
        _yn_list = ["—","iyi","orta","kötü"]
        for _ri in range(len(st.session_state["an_rakip_satirlar"])):
            _rs = st.session_state["an_rakip_satirlar"][_ri]
            _rc = st.columns([1.5,0.7,0.7,0.7,0.7,0.7,0.7,1.5,0.25])
            st.session_state["an_rakip_satirlar"][_ri]["firma"]    = _rc[0].text_input("", value=_rs.get("firma",""), key=f"an_rfirma_{_ri}", placeholder="rakip firma", label_visibility="collapsed")
            st.session_state["an_rakip_satirlar"][_ri]["durum"]    = _rc[1].selectbox("", _rd_list, index=_rd_list.index(_rs.get("durum","orta")) if _rs.get("durum","orta") in _rd_list else 1, key=f"an_rdurum_{_ri}", label_visibility="collapsed")
            st.session_state["an_rakip_satirlar"][_ri]["fiyat_av"] = _rc[2].selectbox("", _yn_list, index=_yn_list.index(_rs.get("fiyat_av","—")) if _rs.get("fiyat_av","—") in _yn_list else 0, key=f"an_rfiyat_{_ri}", label_visibility="collapsed")
            st.session_state["an_rakip_satirlar"][_ri]["hiz"]      = _rc[3].selectbox("", _yn_list, index=_yn_list.index(_rs.get("hiz","—")) if _rs.get("hiz","—") in _yn_list else 0, key=f"an_rhiz_{_ri}", label_visibility="collapsed")
            st.session_state["an_rakip_satirlar"][_ri]["hasar"]    = _rc[4].selectbox("", _yn_list, index=_yn_list.index(_rs.get("hasar","—")) if _rs.get("hasar","—") in _yn_list else 0, key=f"an_rhasar_{_ri}", label_visibility="collapsed")
            st.session_state["an_rakip_satirlar"][_ri]["avm"]      = _rc[5].selectbox("", _yn_list, index=_yn_list.index(_rs.get("avm","—")) if _rs.get("avm","—") in _yn_list else 0, key=f"an_ravm_{_ri}", label_visibility="collapsed")
            st.session_state["an_rakip_satirlar"][_ri]["iliski"]   = _rc[6].selectbox("", _yn_list, index=_yn_list.index(_rs.get("iliski","—")) if _rs.get("iliski","—") in _yn_list else 0, key=f"an_riliski_{_ri}", label_visibility="collapsed")
            st.session_state["an_rakip_satirlar"][_ri]["sebep"]    = _rc[7].text_input("", value=_rs.get("sebep",""), key=f"an_rsebep_{_ri}", placeholder="diğer tercih sebebi", label_visibility="collapsed")
            if _rc[8].button("×", key=f"an_rdel_{_ri}") and len(st.session_state["an_rakip_satirlar"])>1:
                st.session_state["an_rakip_satirlar"].pop(_ri); st.rerun()
        if st.button("+ Rakip Ekle", key="an_rakip_ekle"):
            st.session_state["an_rakip_satirlar"].append({"firma":"","durum":"orta","fiyat_av":"—","hiz":"—","hasar":"—","avm":"—","iliski":"—","sebep":""}); st.rerun()

        # ── SATIR 10: Beklenti & Engel & Şikayet ───────────────────────────────────
        st.markdown("##### 💬 Beklenti, Engel & Şikayet")
        _r10c1,_r10c2,_r10c3 = st.columns(3)
        _an_beklenti = _r10c1.multiselect("Müşteri Beklentisi", ["düşük fiyat","uzun vade","hız/dakiklik","hizmet kalitesi","erken alım","bölge kapsamı","takip sistemi","sigorta","AVM girişi","özel araç"], default=_mv_list("beklenti"), key="an_beklenti")
        _an_engel    = _r10c2.multiselect("Anlaşma Engeli", ["fiyat","vade","rakip teklifi","karar verici","bölge eksikliği","güven","alışkanlık","teknik sorun"], default=_mv_list("engel"), key="an_engel")
        _an_sik      = _r10c3.multiselect("Şikayetleri", ["hasar","geç teslimat","fiyat yüksek","iletişim zayıf","takip yok","kayıp kargo","ambar bırakıyor","araç gelmiyor","AVM girişi yok"], default=_mv_list("sik"), key="an_sik")

        # ── SATIR 11: Geçiş & Ödeme & Karar ───────────────────────────────────────
        _r11c1,_r11c2,_r11c3,_r11c4 = st.columns(4)
        _an_gecis  = _r11c1.multiselect("Bize Geçiş Sebebi", ["fiyat avantajı","daha hızlı","kişisel ilişki","güven","takip sistemi","geniş bölge","erken alım","AVM çözümü"], default=_mv_list("gecis"), key="an_gecis")
        _an_odeme  = _r11c2.multiselect("Vade/Ödeme", ["nakit","havale","çek","30 gün","45 gün","60 gün","90 gün"], default=_mv_list("odeme"), key="an_odeme")
        _paz_list  = ["inebilir","zorlu","inmez","bilinmiyor"]
        _an_pazarlik = _r11c3.selectbox("Pazarlık", _paz_list, index=_paz_list.index(_mv("pazarlik","inebilir")) if _mv("pazarlik","inebilir") in _paz_list else 0, key="an_pazarlik")
        _sure_list = ["acil (bu hafta)","kısa (1 ay)","uzun (3+ ay)","belirsiz"]
        _an_sure   = _r11c4.selectbox("Karar Süresi", _sure_list, index=_sure_list.index(_mv("sure","belirsiz")) if _mv("sure","belirsiz") in _sure_list else 3, key="an_sure")

        # ── SATIR 12: Sonraki Adım & Not ────────────────────────────────────────────
        st.markdown("##### 📝 Sonraki Adım & Görüşme Notu")
        _an_sonraki_hint = "Spot teklif hazırla ve sun" if _an_ttur_val == "spot" else "Özel anlaşma şartlarını belirle ve sun"
        _an_sonraki = st.text_input("Bir Sonraki Adım", value=_mv("sonraki_adim",""), key="an_sonraki", placeholder=_an_sonraki_hint)
        _an_not = st.text_area("Görüşme Notu", value=_mv("not_alan",""), key="an_not", placeholder="Devrik de yaz, kısa da — karakter sınırı yok.", height=80)

        st.divider()

        # Veriyi kayıt için hazırla — sadece Supabase'de var olan kolonlar
        # Yeni alanları (koli_adet, saat vs.) not_alan içine göm, kolon hatası vermesin
        _ek_bilgi = {
            "saat": _an_saat or "",
            "koli_adet": _an_koli_adet or "",
            "koli_desi": _an_koli_desi or "",
            "koli_kg": _an_koli_kg or "",
            "pal_adet": _an_pal_adet or "",
            "pal_desi": _an_pal_desi or "",
            "pal_kg": _an_pal_kg or "",
            "sevk_siklik": _an_sevk_siklik or "",
            "aylik_odeme": str(_an_aylik_odeme or ""),
        }
        _ek_json = _aj.dumps(_ek_bilgi, ensure_ascii=False)

        _veri_an = {
            "yetkili":      _an_yetkili or "",
            "iletisim":     _an_iletisim or "",
            "sektor":       _an_sektor or "",
            "amac":         _an_kaynak_val or "",
            "mdurum":       _an_mdurum or "",
            "bek_ciro":     float((_an_bek_ciro or "0").replace(".","").replace(",",".")) if _an_bek_ciro else 0,
            "ger_ciro":     float((_an_ger_ciro or "0").replace(".","").replace(",",".")) if _an_ger_ciro else 0,
            "kaynak":       _an_kaynak_val or "",
            "kargo":        _an_kargo_val or "",
            "fatura":       _an_fatura or "",
            "uapo":         _an_uapo or "",
            "odeme":        ", ".join(_an_odeme) if _an_odeme else "",
            "pazarlik":     _an_pazarlik or "",
            "beklenti":     ", ".join(_an_beklenti) if _an_beklenti else "",
            "teklif_tur":   _an_ttur_val or "",
            "karar":        _an_karar or "",
            "sure":         _an_sure or "",
            "engel":        ", ".join(_an_engel) if _an_engel else "",
            "sik":          ", ".join(_an_sik) if _an_sik else "",
            "gecis":        ", ".join(_an_gecis) if _an_gecis else "",
            "potansiyel":   _an_pot or "",
            "sonuc":        _an_sonuc or "",
            "not_alan":     (_an_not or "") + (f"\n[EK:{_ek_json}]" if any(_ek_bilgi.values()) else ""),
            "takip_tar":    str(_an_takip) if _an_takip else "",
            "sonraki_adim": _an_sonraki or "",
            "olusturan":    _an_temsilci or st.session_state.get("kullanici",""),
            "fiyat_tablo":  _aj.dumps(st.session_state.get("an_fiyat_satirlar",[]), ensure_ascii=False),
            "avm":          _aj.dumps(st.session_state.get("an_avm_satirlar",[]), ensure_ascii=False),
            "rakip":        _aj.dumps(st.session_state.get("an_rakip_satirlar",[]), ensure_ascii=False),
            "bolge":        "[]",
        }

        # ── AKSİYON BUTONLARI ────────────────────────────────────────────────────────
        st.divider()
        _btn1, _btn2, _btn3 = st.columns(3)
        _kaydet_btn = _btn1.button("💾 " + ("Güncelle" if _duzenle_mod else "Kaydet"), type="primary", use_container_width=True, key="an_kaydet")
        _cari_btn   = _btn2.button("➕ Cari Listeye Ekle", use_container_width=True, key="an_cari")
        _teklif_btn = _btn3.button("📄 Teklif Oluştur", use_container_width=True, key="an_teklif")

        # Kaydet — direkt, önizleme yok
        if _kaydet_btn:
            if not _secili_firma:
                st.error("❌ Firma seçilmedi!")
            else:
                _ok, _ = _an_upsert(_secili_firma, _veri_an)
                if _ok:
                    _eylem = "güncellendi" if _duzenle_mod else "kaydedildi"
                    # Cari listede yoksa otomatik ekle
                    try:
                        _cari_chk = _df_cari_an[_df_cari_an["firma"].str.lower()==_secili_firma.lower()]
                        if _cari_chk.empty:
                            db_insert("cari_kartlar",{
                                "firma":_secili_firma,
                                "yetkili":_an_yetkili or "",
                                "gsm":_an_iletisim if "@" not in (_an_iletisim or "") else "",
                                "email":_an_iletisim if "@" in (_an_iletisim or "") else "",
                                "il":"","durum":"Hedef","islem_asamasi":"İlk Temas",
                                "beklenen_ciro":float((_an_bek_ciro or "0").replace(".","").replace(",",".")) if _an_bek_ciro else 0,
                                "olusturan":st.session_state.get("kullanici",""),"silindi":0
                            })
                            st.info(f"📋 {_secili_firma} cari listeye otomatik eklendi.")
                        else:
                            _cid2 = int(_cari_chk.iloc[0]["id"]); _upd2 = {}
                            if _an_bek_ciro:
                                try: _upd2["beklenen_ciro"]=float(_an_bek_ciro.replace(".","").replace(",","."))
                                except: pass
                            if _upd2: db_update("cari_kartlar",_upd2,"id",_cid2)
                    except: pass
                    st.success(f"✅ **{_secili_firma}** analizi başarıyla {_eylem}!")
                    st.balloons()
                    try: db_read.clear()
                    except: pass
                    st.rerun()


        if _cari_btn:
            _var_mi = not _df_cari_an[_df_cari_an["firma"].str.lower()==_secili_firma.lower()].empty
            if _var_mi:
                st.info(f"ℹ️ {_secili_firma} zaten cari listede!")
            else:
                db_insert("cari_kartlar", {
                    "firma": _secili_firma, "yetkili": _an_yetkili or "",
                    "gsm": _an_iletisim if "@" not in (_an_iletisim or "") else "",
                    "email": _an_iletisim if "@" in (_an_iletisim or "") else "",
                    "il":"","durum":"Hedef","islem_asamasi":"İlk Temas",
                    "beklenen_ciro": float((_an_bek_ciro or "0").replace(".","").replace(",",".")) if _an_bek_ciro else 0,
                    "olusturan": st.session_state.get("kullanici",""), "silindi": 0
                })
                try: db_read.clear()
                except: pass
                st.success(f"✅ {_secili_firma} cari listeye eklendi!")

        if _teklif_btn:
            st.session_state["aktif_tab"] = "teklif"
            st.rerun()


    # (eski liste ve istatistikler tab1'e taşındı)

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
    df_rand_all = db_read("randevular", extra_sql="ORDER BY randevu_tarihi DESC, randevu_saati ASC")
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

            # ── SATIR SATIR LİSTE — st.dataframe (sürüklenebilir) ───────────
            _df_goster = pd.DataFrame([{
                "ID": int(r.get("id",0) or 0),
                "Tarih": str(r.get("randevu_tarihi",""))[5:].replace("-","."),
                "Müşteri": str(r.get("musteri_adi","") or ""),
                "Bölge": str(r.get("bolge","") or ""),
                "Görev": str(r.get("gorev","") or ""),
                "Sonuç": str(r.get("sonuc","") or ""),
                "Hedef ₺": float(_ciro_map.get(str(r.get("musteri_adi","")),{"hedef":0})["hedef"]),
                "Gerçek ₺": float(_ciro_map.get(str(r.get("musteri_adi","")),{"gercek":0})["gercek"]),
                "Fark ₺": float(_ciro_map.get(str(r.get("musteri_adi","")),{"gercek":0})["gercek"]) - float(_ciro_map.get(str(r.get("musteri_adi","")),{"hedef":0})["hedef"]),
            } for _,r in df_rand.iterrows()])

            st.dataframe(
                _df_goster,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ID":       st.column_config.NumberColumn("ID", width="small"),
                    "Tarih":    st.column_config.TextColumn("Tarih", width="small"),
                    "Müşteri":  st.column_config.TextColumn("Müşteri", width="large"),
                    "Bölge":    st.column_config.TextColumn("Bölge"),
                    "Görev":    st.column_config.TextColumn("Görev", width="small"),
                    "Sonuç":    st.column_config.TextColumn("Sonuç", width="small"),
                    "Hedef ₺":  st.column_config.NumberColumn("Hedef ₺", format="%.0f ₺"),
                    "Gerçek ₺": st.column_config.NumberColumn("Gerçek ₺", format="%.0f ₺"),
                    "Fark ₺":   st.column_config.NumberColumn("Fark ₺", format="%.0f ₺"),
                },
                key="rand_df_goster"
            )

            # Düzenle — selectbox ile
            _edit_sec = st.selectbox("✏️ Düzenlenecek randevu seç:", ["—"] + [f"[{int(r['id'])}] {r['musteri_adi']} — {str(r.get('randevu_tarihi',''))[:10]}" for _,r in df_rand.iterrows()], key="rand_edit_sec", label_visibility="collapsed")
            if _edit_sec != "—":
                _edit_id = int(_edit_sec.split("]")[0].replace("[","").strip())
                _edit_row = df_rand[df_rand["id"]==_edit_id]
                if not _edit_row.empty:
                    st.session_state["rand_duz_row"] = _edit_row.iloc[0].to_dict()

            if False:  # eski döngü placeholder — form aşağıda
                _tablo_html = ""
            # Düzenleme formu
            if st.session_state.get("rand_duz_row"):
                _edit_id = st.session_state["rand_duz_row"].get("id")
                _rid = _edit_id
                row_d = st.session_state["rand_duz_row"]
                with st.form(f"rand_duz_form_{_rid}"):
                        dd1,dd2,dd3,dd4 = st.columns(4)
                        d_tarih    = dd1.text_input("Tarih:", value=str(row_d.get("randevu_tarihi","")))
                        d_saat     = dd2.text_input("Saat:", value=str(row_d.get("randevu_saati","")))
                        d_bolge    = dd3.text_input("Bölge:", value=str(row_d.get("bolge","")))
                        d_temsilci = dd4.text_input("Temsilci:", value=str(row_d.get("temsilci","")))
                        dd5,dd6 = st.columns(2)
                        d_gorev = dd5.text_input("Görev:", value=str(row_d.get("gorev","")))
                        d_sonuc_opts = ["—","Bitti","Devam Ediyor","Gidilmedi","İptal"]
                        d_sonuc_idx  = d_sonuc_opts.index(row_d.get("sonuc","—")) if row_d.get("sonuc") in d_sonuc_opts else 0
                        d_sonuc    = dd6.selectbox("Sonuç:", d_sonuc_opts, index=d_sonuc_idx)
                        d_aciklama = st.text_area("Açıklama:", value=str(row_d.get("aciklama","")), height=60)
                        _fb1,_fb2,_fb3 = st.columns(3)
                        if _fb1.form_submit_button("💾 Kaydet", use_container_width=True, type="primary"):
                            db_update("randevular",{"randevu_tarihi":d_tarih,"randevu_saati":d_saat,
                                "bolge":d_bolge,"gorev":d_gorev,"temsilci":d_temsilci,
                                "sonuc":d_sonuc if d_sonuc!="—" else "","aciklama":d_aciklama},
                                "id",_rid)
                            try: db_read.clear()
                            except: pass
                            st.session_state.pop("rand_duz_row",None)
                            st.success("✅ Güncellendi!"); st.rerun()
                        if _fb2.form_submit_button("🗑️ Sil", use_container_width=True):
                            _sb_rd = get_sb_client()
                            if _sb_rd: _sb_rd.table("randevular").delete().eq("id",_rid).execute()
                            st.session_state.pop("rand_duz_row",None)
                            st.success("🗑️ Silindi!"); st.rerun()
                        if _fb3.form_submit_button("İptal", use_container_width=True):
                            st.session_state.pop("rand_duz_row",None); st.rerun()

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
            rand_saat     = rc2.time_input("Saat*:", key="rand_saat")
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
                        _ntarih = str(_nr.get("tarih",""))[:16]
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