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

@st.cache_data(ttl=0)
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

st.markdown("""
<style>
@media (max-width: 768px) {
    .block-container { padding: 0.5rem !important; }
    div[data-testid="column"] { min-width: 100% !important; }
    .stButton>button { width: 100% !important; font-size: 13px !important; }
    h1 { font-size: 1.3rem !important; }
    h2 { font-size: 1.1rem !important; }
}
.stButton>button { border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)

if "giris" not in st.session_state:
    st.session_state["giris"] = False
if "kullanici" not in st.session_state:
    st.session_state["kullanici"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = ""
if "aktif_tab" not in st.session_state:
    st.session_state["aktif_tab"] = "liste"
if "kayit_mesaj" not in st.session_state:
    st.session_state["kayit_mesaj"] = ""

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



_TAB_LISTESI_DEFAULT = ["yeni", "liste", "randevu", "teklif", "kisiler", "rapor", "excel", "arsiv", "mesajlar", "kullanici", "admin_rapor"]
_TAB_ETIKETLER = {
    "yeni": "➕ Yeni Kart Ekle",
    "liste": "📋 Cari Liste / Düzenle",
    "arsiv": "🗃️ Arşiv (Silinenler)",
    "rapor": "📊 Raporlar",
    "teklif": "📄 Teklif Oluştur",
    "excel": "📥 Excel Aktar",
    "kisiler": "📞 Telefon Kişiler",
    "randevu": "📅 Randevular",
    "kullanici": "👥 Kullanıcı Yönetimi",
    "koddepo": "💾 Kod Deposu",
    "mesajlar": "💬 Mesajlar",
    "admin_rapor": "📊 Rapor Tasarla",
}

def get_menu_tercihi(kullanici):
    def _temizle(liste):
        """Duplicate'leri temizle, sıralamasını koru"""
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
                kayitli = _menu_json.loads(res.data[0]["deger"])
                tam_liste = _TAB_LISTESI_DEFAULT.copy()
                if st.session_state.get("rol") == "admin":
                    tam_liste += ["kullanici","koddepo","admin_rapor"]
                tam_liste = _temizle(tam_liste)
                for t in tam_liste:
                    if t not in kayitli:
                        kayitli.append(t)
                kayitli = [t for t in kayitli if t in tam_liste]
                return _temizle(kayitli)
        else:
            conn = get_conn()
            conn.execute("CREATE TABLE IF NOT EXISTS kullanici_tercih (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, anahtar TEXT, deger TEXT, UNIQUE(kullanici, anahtar))")
            conn.commit()
            row = conn.execute("SELECT deger FROM kullanici_tercih WHERE kullanici=? AND anahtar='menu_sirasi'", (kullanici,)).fetchone()
            conn.close()
            if row:
                kayitli = _menu_json.loads(row[0])
                tam_liste = _TAB_LISTESI_DEFAULT.copy()
                if st.session_state.get("rol") == "admin":
                    tam_liste += ["kullanici","koddepo","admin_rapor"]
                tam_liste = _temizle(tam_liste)
                for t in tam_liste:
                    if t not in kayitli:
                        kayitli.append(t)
                kayitli = [t for t in kayitli if t in tam_liste]
                return _temizle(kayitli)
    except: pass
    tam_liste = _TAB_LISTESI_DEFAULT.copy()
    if st.session_state.get("rol") == "admin":
        tam_liste += ["kullanici","koddepo","admin_rapor"]
    return _temizle(tam_liste)

def save_menu_tercihi(kullanici, sira):
    try:
        sb_m = get_sb_client()
        if sb_m:
            sb_m.table("kullanici_tercih").upsert({
                "kullanici": kullanici,
                "anahtar": "menu_sirasi",
                "deger": _menu_json.dumps(sira)
            }, on_conflict="kullanici,anahtar").execute()
        else:
            conn = get_conn()
            conn.execute("CREATE TABLE IF NOT EXISTS kullanici_tercih (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, anahtar TEXT, deger TEXT, UNIQUE(kullanici, anahtar))")
            conn.execute("INSERT OR REPLACE INTO kullanici_tercih (kullanici, anahtar, deger) VALUES (?,?,?)",
                (kullanici, "menu_sirasi", _menu_json.dumps(sira)))
            conn.commit(); conn.close()
    except: pass

# ── SIDEBAR ───────────────────────────────────────────────────────────────────

# ── VERSİYON KONTROL SİSTEMİ ─────────────────────────────────────────────────
GUNCEL_SURUM = "v6.3"  # Bu kodun versiyonu — her güncellemede artır

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
                # Sadece "guncelleniyor" değilse kontrol et — kullanıcı her zaman çalışır
                if _stable != "guncelleniyor" and _stable != GUNCEL_SURUM:
                    pass  # Eski sürümde çalışmaya devam et — sorun yok
    except:
        pass  # Hata olursa engelleme yapma

with st.sidebar:
    st.markdown("## 🏢 MWCRMPRO")
    st.caption(f"👤 {st.session_state.get('kullanici','')} | {st.session_state.get('rol','')}")
    if st.button("🚪 Çıkış", use_container_width=True, key="sidebar_cikis"):
        cikis()

    st.divider()
    st.divider()

    # ── MENÜ LİSTESİ ──────────────────────────────────────────────────────────
    _sb_liste = get_menu_tercihi(st.session_state["kullanici"])
    if st.session_state.get("rol") == "admin":
        for _t in ["kullanici","koddepo","admin_rapor"]:
            if _t not in _sb_liste:
                _sb_liste.append(_t)
    # Yetki filtresi
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

    # Duplicate key'leri temizle
    _sb_liste_temiz = []
    for _t in _sb_liste:
        if _t not in _sb_liste_temiz:
            _sb_liste_temiz.append(_t)
    _sb_liste = _sb_liste_temiz

    for _tab_key in _sb_liste:
        _etiket = _TAB_ETIKETLER.get(_tab_key, _tab_key)
        _aktif_mi = st.session_state["aktif_tab"] == _tab_key
        if st.button(_etiket, use_container_width=True,
                     type="primary" if _aktif_mi else "secondary",
                     key=f"sb_{_tab_key}"):
            st.session_state["aktif_tab"] = _tab_key
            st.rerun()

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
            # Duplicate temizle
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
                save_menu_tercihi(st.session_state["kullanici"], _TAB_LISTESI_DEFAULT.copy() + ["kullanici","koddepo","admin_rapor"])
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
            # Mevcut duyuruları göster
            try:
                _sb_dy = get_sb_client()
                if _sb_dy:
                    _dy_res = _sb_dy.table("duyurular").select("*").eq("aktif",1).order("tarih",desc=True).execute()
                    _df_dy = pd.DataFrame(_dy_res.data) if _dy_res.data else pd.DataFrame()
                else:
                    _df_dy = db_read("duyurular", extra_sql="WHERE aktif=1 ORDER BY tarih DESC")
                if not _df_dy.empty:
                    st.markdown("**Aktif Duyurular:**")
                    for _, _dy in _df_dy.iterrows():
                        _tip = _dy.get("tip","bilgi")
                        _renk = "#1f6feb" if _tip=="bilgi" else "#ff9800" if _tip=="uyari" else "#f44336"
                        st.markdown(
                            f"<div style='border-left:4px solid {_renk};padding:6px 10px;margin:4px 0;background:#f8f9fa;border-radius:4px'>"
                            f"<b>{_dy.get('baslik','')}</b> <small style='color:#888'>— {_tip}</small><br>"
                            f"{_dy.get('icerik','')}</div>",
                            unsafe_allow_html=True
                        )
                        if st.button("🗑️ Kaldır", key=f"dy_sil_{_dy.get('id',0)}"):
                            if _sb_dy:
                                _sb_dy.table("duyurular").update({"aktif":0}).eq("id",int(_dy.get("id",0))).execute()
                            st.rerun()
            except: pass

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
        _asama_base = ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]
        try:
            _df_as2 = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi IS NULL")
            if not _df_as2.empty and "islem_asamasi" in _df_as2.columns:
                _asama_base = sorted(set(_asama_base + [str(a) for a in _df_as2["islem_asamasi"].dropna().unique() if str(a).strip() and str(a)!="nan"]))
        except: pass
        if "ekstra_asamalar" in st.session_state:
            for _ea in st.session_state["ekstra_asamalar"]:
                if _ea not in _asama_base: _asama_base.append(_ea)
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

    # ── ASAMA LİSTESİ ───────────────────────────────────────────────────────────
    _ASAMA_VARSAYILAN = ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]
    if not df.empty and "islem_asamasi" in df.columns:
        _asama_ek = [str(a) for a in df["islem_asamasi"].dropna().unique()
                     if str(a).strip() and str(a) not in ["nan",""]]
        tum_asama_opts = sorted(set(_ASAMA_VARSAYILAN + _asama_ek))
    else:
        tum_asama_opts = _ASAMA_VARSAYILAN.copy()
    # Kalıcı ekstra aşamaları session_state'te tut
    if "ekstra_asamalar" not in st.session_state:
        st.session_state["ekstra_asamalar"] = []
    for _ea in st.session_state["ekstra_asamalar"]:
        if _ea not in tum_asama_opts:
            tum_asama_opts.append(_ea)

    # ── ÜST METRİKLER ───────────────────────────────────────────────────────────
    # ── ÜST METRİKLER ────────────────────────────────────────────────────────
    # Durum satırı — sabit 5 kolon, boşluk sağda
    if "durum" in df.columns:
        _tum_d = ["Aktif","Hedef","Pasif"] + [
            d for d in df["durum"].dropna().unique()
            if str(d).strip() and str(d) != "nan" and d not in ["Aktif","Hedef","Pasif"]
        ]
        _d_veri = [("Toplam", len(df))] + [(d, len(df[df["durum"]==d])) for d in _tum_d if len(df[df["durum"]==d]) > 0]
    else:
        _d_veri = [("Toplam", len(df))]

    _c = st.columns(5)
    for i in range(5):
        if i < len(_d_veri):
            _c[i].metric(_d_veri[i][0], _d_veri[i][1])

    # Aşama satırı — sabit 5 kolon, boşluk sağda
    if "islem_asamasi" in df.columns:
        _a_veri = [
            (a, int(n)) for a, n in
            df[df["islem_asamasi"].notna() & (df["islem_asamasi"].astype(str).str.strip() != "") & (df["islem_asamasi"].astype(str) != "nan")]
            ["islem_asamasi"].value_counts().items()
        ]
        if _a_veri:
            _ca = st.columns(5)
            for i in range(5):
                if i < len(_a_veri):
                    _ca[i].metric(_a_veri[i][0], _a_veri[i][1])

    # ── FİLTRE ──────────────────────────────────────────────────────────────────
    f1,f2,f3 = st.columns(3)
    filtre_asama = f1.selectbox("Aşama:", ["Tümü"]+tum_asama_opts, key="fil_asama")
    filtre_durum = f2.selectbox("Durum:", ["Tümü","Aktif","Hedef","Pasif"], key="fil_durum")
    ara_txt      = f3.text_input("🔍 Ara:", placeholder="Firma, yetkili, il...", key="ara_liste")

    df_f = df.copy()
    if filtre_asama != "Tümü": df_f = df_f[df_f["islem_asamasi"]==filtre_asama]
    if filtre_durum  != "Tümü": df_f = df_f[df_f["durum"]==filtre_durum]
    if ara_txt: df_f = df_f[df_f.apply(lambda r: ara_txt.lower() in str(r).lower(), axis=1)]
    df_f = df_f.reset_index(drop=True)

    # ── MÜŞTERİ KARTI ───────────────────────────────────────────────────────────
    kart_opts = ["-- Müşteri Seçin --"] + [
        f"[{int(r['id'])}] {r['firma']} | {r.get('il','')} | {r.get('islem_asamasi','')}"
        for _, r in df_f.iterrows()
    ]
    secili_kart = st.selectbox("🔍 Müşteri Kartı Seç:", kart_opts, key="kart_sec")
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
            ab1,ab2,ab3,ab4 = st.columns(4)
            if ab1.button("✏️ Düzenle", key=f"kd_{kart_id}", use_container_width=True):
                d2 = {str(k):(None if str(v) in ["nan","None","NaT"] else v) for k,v in kart_row.items()}
                for _k in ["firma","yetkili","gsm","sabit","email","adres","il","ilce","durum","temsilci","islem_asamasi","aciklama"]:
                    if _k in d2: d2[_k] = "" if d2[_k] is None else str(d2[_k])
                st.session_state["duzenle_musteri"] = d2
                st.session_state["aktif_tab"] = "yeni"; st.rerun()
            if ab2.button("📄 Teklif", key=f"kt_{kart_id}", use_container_width=True, type="primary"):
                st.session_state["aktif_tab"] = "teklif"
                st.session_state["hedef_mus"] = str(kart_row.get("firma",""))
                st.session_state["son_secili_id"] = None; st.rerun()
            if ab3.button("📅 Randevu", key=f"kr_{kart_id}", use_container_width=True, type="primary"):
                st.session_state["aktif_tab"] = "randevu"
                st.session_state["rand_musteri_onsel"] = kart_id; st.rerun()
            if ab4.button("🗑️ Arşive", key=f"ka_{kart_id}", use_container_width=True):
                if sb_liste: sb_liste.table("cari_kartlar").update({"silindi":1}).eq("id",kart_id).execute()
                else: db_update("cari_kartlar",{"silindi":1},"id",kart_id)
                try: db_read.clear()
                except: pass
                st.success("Arşive gönderildi!"); st.rerun()

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
    st.caption(f"**{len(df_f)} kayıt**")

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
        "durum":         st.column_config.SelectboxColumn("Durum", options=_tum_durumlar),
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

    # KEY YAKLAŞIMI: her render'da edited_df'i yakala, session_state'e yaz
    # Böylece buton basılınca kaybolmaz
    edited_df = st.data_editor(
        df_edit,
        use_container_width=True,
        num_rows="fixed",
        column_config=col_config,
        column_order=col_order,
        key="cari_editor"
    )
    # HER render'da tüm tabloyu session_state'e kaydet
    import json as _json_ls
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

    # ── KAYDET BUTONU ─────────────────────────────────────────────────────────
    btn_k, btn_a, btn_s = st.columns(3)
    with btn_k:
        if st.button("💾 Değişiklikleri Kaydet", use_container_width=True, type="primary", key="liste_kaydet"):
            # session_state'teki son tabloyu al
            _tablo_json = st.session_state.get("_ls_tablo")
            if not _tablo_json:
                st.warning("Önce bir hücreye tıklayıp değişiklik yapın.")
            else:
                try:
                    _rows = _json_ls.loads(_tablo_json)
                except:
                    _rows = []
                kayit_sayi = 0
                hata_list  = []
                for row in _rows:
                    rid = row.get("id")
                    if not rid or str(rid) in ["nan","None",""]: continue
                    try:
                        rid = int(float(str(rid)))
                        guncelle = {
                            "firma":         str(row.get("firma","") or ""),
                            "yetkili":       str(row.get("yetkili","") or ""),
                            "gsm":           str(row.get("gsm","") or ""),
                            "sabit":         str(row.get("sabit","") or ""),
                            "email":         str(row.get("email","") or ""),
                            "il":            str(row.get("il","") or ""),
                            "ilce":          str(row.get("ilce","") or ""),
                            "durum":         str(row.get("durum","") or ""),
                            "temsilci":      str(row.get("temsilci","") or ""),
                            "islem_asamasi": str(row.get("islem_asamasi","") or ""),
                            "aciklama":      str(row.get("aciklama","") or ""),
                        }
                        # notlar olmayan Supabase için 2 deneme
                        ok = False
                        if sb_liste:
                            try:
                                sb_liste.table("cari_kartlar").update(guncelle).eq("id", rid).execute()
                                ok = True
                            except Exception as e1:
                                # notlar kolonu yoksa onsuz dene
                                g2 = {k:v for k,v in guncelle.items() if k != "aciklama"}
                                try:
                                    sb_liste.table("cari_kartlar").update(g2).eq("id", rid).execute()
                                    ok = True
                                except Exception as e2:
                                    hata_list.append(f"ID{rid}: {e2}")
                        else:
                            conn_u = get_conn()
                            try:
                                sets = ", ".join([f"{k}=?" for k in guncelle])
                                conn_u.execute(f"UPDATE cari_kartlar SET {sets} WHERE id=?",
                                    list(guncelle.values()) + [rid])
                                conn_u.commit(); ok = True
                            except:
                                g2 = {k:v for k,v in guncelle.items() if k != "aciklama"}
                                sets = ", ".join([f"{k}=?" for k in g2])
                                conn_u.execute(f"UPDATE cari_kartlar SET {sets} WHERE id=?",
                                    list(g2.values()) + [rid])
                                conn_u.commit()
                                ok = True
                            conn_u.close()
                        if ok: kayit_sayi += 1
                    except Exception as e_row:
                        hata_list.append(f"ID{rid}: {e_row}")

                try: db_read.clear()
                except: pass
                st.session_state.pop("_ls_tablo", None)

                # Açıklama hücresi doluysa cari_aciklamalar'a arşivle + hücreyi temizle
                _arsiv_sayi = 0
                for row in _rows:
                    rid = row.get("id")
                    _ac_yeni = str(row.get("aciklama","") or "").strip()
                    if not rid or not _ac_yeni or _ac_yeni == "nan": continue
                    try:
                        rid = int(float(str(rid)))
                        # cari_aciklamalar'a ekle
                        _ac_veri = {
                            "cari_id":   rid,
                            "cari_adi":  str(row.get("firma","")),
                            "aciklama":  _ac_yeni,
                            "olusturan": st.session_state.get("kullanici",""),
                        }
                        if sb_liste:
                            sb_liste.table("cari_aciklamalar").insert(_ac_veri).execute()
                            # Hücreyi temizle
                            sb_liste.table("cari_kartlar").update({"aciklama":""}).eq("id",rid).execute()
                        else:
                            _cx = get_conn()
                            _cx.execute("INSERT INTO cari_aciklamalar (cari_id,cari_adi,aciklama,olusturan) VALUES (?,?,?,?)",
                                (rid, str(row.get("firma","")), _ac_yeni, st.session_state.get("kullanici","")))
                            _cx.execute("UPDATE cari_kartlar SET aciklama='' WHERE id=?", (rid,))
                            _cx.commit(); _cx.close()
                        _arsiv_sayi += 1
                    except: pass

                if kayit_sayi > 0:
                    st.success(f"✅ {kayit_sayi} satır kaydedildi!" + (f" · {_arsiv_sayi} açıklama 📨 arşivlendi!" if _arsiv_sayi > 0 else ""))
                else:
                    st.warning("Hiç kayıt yapılamadı.")
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

    # ── AŞAMA & DURUM YÖNETİMİ — Supabase'e kayıtlı ─────────────────────────
    with st.expander("⚙️ Aşama & Durum Yönetimi"):
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

            _kayitli_asamalar = _sb_tercih_yukle("ekstra_asamalar")
            _varsayilan_asamalar = ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]
            _tum_asamalar_yon = _varsayilan_asamalar.copy()
            for _a in _kayitli_asamalar:
                if _a not in _tum_asamalar_yon:
                    _tum_asamalar_yon.append(_a)

            # Yeni aşama ekle
            _ya1, _ya2 = st.columns([3,1])
            _yeni_a = _ya1.text_input("Yeni aşama:", key="yeni_asama_ekle", placeholder="Demo, Numune, Görüşme...", label_visibility="collapsed")
            if _ya2.button("➕ Ekle", key="asama_ekle_sb", use_container_width=True):
                if _yeni_a and _yeni_a.strip() and _yeni_a.strip() not in _tum_asamalar_yon:
                    _kayitli_asamalar.append(_yeni_a.strip())
                    _sb_tercih_kaydet("ekstra_asamalar", _kayitli_asamalar)
                    st.success(f"✅ '{_yeni_a}' eklendi!")
                    st.rerun()
                elif _yeni_a.strip() in _tum_asamalar_yon:
                    st.warning("Bu aşama zaten var!")

            st.caption("Tüm aşamalar:")
            for _a in _tum_asamalar_yon:
                _adet = len(df[df["islem_asamasi"]==_a]) if not df.empty and "islem_asamasi" in df.columns else 0
                _ac1, _ac2, _ac3 = st.columns([3,1,1])
                _ac1.caption(f"{'🔹' if _adet>0 else '⬜'} **{_a}** ({_adet})")

                # Düzenle
                if _a in _kayitli_asamalar:
                    if _ac2.button("✏️", key=f"asm_duz_{_a}", help="Düzenle"):
                        st.session_state[f"asm_edit_{_a}"] = True
                    # Sil — veri yoksa
                    if _adet == 0:
                        if _ac3.button("🗑️", key=f"asm_sil_{_a}", help="Sil"):
                            _kayitli_asamalar.remove(_a)
                            _sb_tercih_kaydet("ekstra_asamalar", _kayitli_asamalar)
                            st.rerun()
                    else:
                        _ac3.caption("—")
                else:
                    _ac2.caption("—")
                    _ac3.caption("—")

                # Düzenleme formu
                if st.session_state.get(f"asm_edit_{_a}"):
                    with st.form(f"asm_form_{_a}"):
                        _yeni_asm = st.text_input("Yeni ad:", value=_a, key=f"asm_inp_{_a}")
                        _f1, _f2 = st.columns(2)
                        if _f1.form_submit_button("💾 Kaydet"):
                            if _yeni_asm and _yeni_asm.strip() != _a:
                                idx = _kayitli_asamalar.index(_a)
                                _kayitli_asamalar[idx] = _yeni_asm.strip()
                                _sb_tercih_kaydet("ekstra_asamalar", _kayitli_asamalar)
                                # Supabase'de bu aşamadaki kartları da güncelle
                                _sb2 = get_sb_client()
                                if _sb2:
                                    try:
                                        _sb2.table("cari_kartlar").update(
                                            {"islem_asamasi":_yeni_asm.strip()}
                                        ).eq("islem_asamasi",_a).execute()
                                    except: pass
                                st.session_state.pop(f"asm_edit_{_a}", None)
                                st.success(f"✅ '{_a}' → '{_yeni_asm}' güncellendi!")
                                st.rerun()
                        if _f2.form_submit_button("İptal"):
                            st.session_state.pop(f"asm_edit_{_a}", None)
                            st.rerun()

        # ── DURUM YÖNETİMİ ────────────────────────────────────────────────────
        with yc2:
            st.markdown("**📊 Durum Yönetimi**")

            _kayitli_durumlar = _sb_tercih_yukle("ekstra_durumlar")
            _varsayilan_durumlar = ["Aktif","Hedef","Pasif"]
            _tum_durumlar_yon = _varsayilan_durumlar.copy()
            for _d in _kayitli_durumlar:
                if _d not in _tum_durumlar_yon:
                    _tum_durumlar_yon.append(_d)

            # Yeni durum ekle
            _yd1, _yd2 = st.columns([3,1])
            _yeni_d = _yd1.text_input("Yeni durum:", key="yeni_durum_ekle", placeholder="VIP, Potansiyel...", label_visibility="collapsed")
            if _yd2.button("➕ Ekle", key="durum_ekle_sb", use_container_width=True):
                if _yeni_d and _yeni_d.strip() and _yeni_d.strip() not in _tum_durumlar_yon:
                    _kayitli_durumlar.append(_yeni_d.strip())
                    _sb_tercih_kaydet("ekstra_durumlar", _kayitli_durumlar)
                    st.success(f"✅ '{_yeni_d}' eklendi!")
                    st.rerun()
                elif _yeni_d.strip() in _tum_durumlar_yon:
                    st.warning("Bu durum zaten var!")

            st.caption("Tüm durumlar:")
            for _d in _tum_durumlar_yon:
                _dadet = len(df[df["durum"]==_d]) if not df.empty and "durum" in df.columns else 0
                _dc1, _dc2, _dc3 = st.columns([3,1,1])
                _dc1.caption(f"{'🔹' if _dadet>0 else '⬜'} **{_d}** ({_dadet})")

                if _d in _kayitli_durumlar:
                    if _dc2.button("✏️", key=f"dur_duz_{_d}", help="Düzenle"):
                        st.session_state[f"dur_edit_{_d}"] = True
                    if _dadet == 0:
                        if _dc3.button("🗑️", key=f"dur_sil_{_d}", help="Sil"):
                            _kayitli_durumlar.remove(_d)
                            _sb_tercih_kaydet("ekstra_durumlar", _kayitli_durumlar)
                            st.rerun()
                    else:
                        _dc3.caption("—")
                else:
                    _dc2.caption("—")
                    _dc3.caption("—")

                # Düzenleme formu
                if st.session_state.get(f"dur_edit_{_d}"):
                    with st.form(f"dur_form_{_d}"):
                        _yeni_dur = st.text_input("Yeni ad:", value=_d, key=f"dur_inp_{_d}")
                        _f1, _f2 = st.columns(2)
                        if _f1.form_submit_button("💾 Kaydet"):
                            if _yeni_dur and _yeni_dur.strip() != _d:
                                idx = _kayitli_durumlar.index(_d)
                                _kayitli_durumlar[idx] = _yeni_dur.strip()
                                _sb_tercih_kaydet("ekstra_durumlar", _kayitli_durumlar)
                                _sb3 = get_sb_client()
                                if _sb3:
                                    try:
                                        _sb3.table("cari_kartlar").update(
                                            {"durum":_yeni_dur.strip()}
                                        ).eq("durum",_d).execute()
                                    except: pass
                                st.session_state.pop(f"dur_edit_{_d}", None)
                                st.success(f"✅ '{_d}' → '{_yeni_dur}' güncellendi!")
                                st.rerun()
                        if _f2.form_submit_button("İptal"):
                            st.session_state.pop(f"dur_edit_{_d}", None)
                            st.rerun()



    # ── AŞAMA BAZLI SAYFALAR ─────────────────────────────────────────────────
    st.markdown("### 📂 Aşama Sayfaları")
    secili_asama_sayfa = st.selectbox("Aşama Seç:", tum_asama_opts, key="asama_sayfa_sec")
    df_asama = df[df["islem_asamasi"]==secili_asama_sayfa].copy() if not df.empty else pd.DataFrame()
    df_asama = df_asama.reset_index(drop=True)
    st.markdown(f"**{secili_asama_sayfa} — {len(df_asama)} kayıt**")

    if df_asama.empty:
        st.info(f"Bu aşamada kayıt yok.")
        if st.button("➕ Bu Aşamaya Kart Ekle", use_container_width=True, type="primary", key="asama_yeni_btn"):
            st.session_state["aktif_tab"] = "yeni"
            st.session_state["varsayilan_asama"] = secili_asama_sayfa; st.rerun()
    else:
        df_asama_edit = df_asama.copy()
        df_asama_edit.insert(0, "Seç", False)
        _asama_key = f"aed_{secili_asama_sayfa[:10].replace(' ','_')}"

        edited_asama = st.data_editor(
            df_asama_edit,
            use_container_width=True,
            num_rows="fixed",
            column_config=col_config,
            column_order=col_order,
            key=_asama_key
        )
        # Her render'da kaydet
        try:
            st.session_state[f"_as_tablo_{_asama_key}"] = edited_asama[col_order[1:]].to_json(orient="records", force_ascii=False)
        except: pass

        secili_asama_df = edited_asama[edited_asama["Seç"]==True]
        secili_asama_idler = secili_asama_df["id"].tolist() if not secili_asama_df.empty else []

        aa1,aa2,aa3 = st.columns(3)
        with aa1:
            if st.button("💾 Kaydet", key=f"asv_{_asama_key}", use_container_width=True, type="primary"):
                _tj = st.session_state.get(f"_as_tablo_{_asama_key}")
                ks = 0
                if _tj:
                    _arows = _json_ls.loads(_tj)
                    for row in _arows:
                        rid = row.get("id")
                        if not rid or str(rid) in ["nan","None",""]: continue
                        try:
                            rid = int(float(str(rid)))
                            gd = {
                                "firma":str(row.get("firma","") or ""),
                                "yetkili":str(row.get("yetkili","") or ""),
                                "gsm":str(row.get("gsm","") or ""),
                                "sabit":str(row.get("sabit","") or ""),
                                "email":str(row.get("email","") or ""),
                                "il":str(row.get("il","") or ""),
                                "ilce":str(row.get("ilce","") or ""),
                                "durum":str(row.get("durum","") or ""),
                                "temsilci":str(row.get("temsilci","") or ""),
                                "islem_asamasi":str(row.get("islem_asamasi","") or ""),
                                "aciklama":str(row.get("aciklama","") or ""),
                            }
                            if sb_liste:
                                try: sb_liste.table("cari_kartlar").update(gd).eq("id",rid).execute()
                                except:
                                    g2={k:v for k,v in gd.items() if k!="aciklama"}
                                    sb_liste.table("cari_kartlar").update(g2).eq("id",rid).execute()
                            else:
                                conn_a=get_conn()
                                sets=", ".join([f"{k}=?" for k in gd])
                                conn_a.execute(f"UPDATE cari_kartlar SET {sets} WHERE id=?",list(gd.values())+[rid])
                                conn_a.commit(); conn_a.close()
                            ks += 1
                        except: pass
                try: db_read.clear()
                except: pass
                st.session_state.pop(f"_as_tablo_{_asama_key}", None)
                st.success(f"✅ {ks} kaydedildi!"); st.rerun()

        with aa2:
            hedef_asama = st.selectbox("→ Taşı:", tum_asama_opts, key=f"tasi_{_asama_key}")
            if st.button("🔄 Seçilileri Taşı", key=f"tasibtn_{_asama_key}", use_container_width=True):
                if secili_asama_idler:
                    for rid in secili_asama_idler:
                        try:
                            if sb_liste: sb_liste.table("cari_kartlar").update({"islem_asamasi":hedef_asama}).eq("id",int(rid)).execute()
                            else: db_update("cari_kartlar",{"islem_asamasi":hedef_asama},"id",int(rid))
                        except: pass
                    try: db_read.clear()
                    except: pass
                    st.success(f"✅ {len(secili_asama_idler)} → {hedef_asama}"); st.rerun()
                else:
                    st.warning("Önce Seç kolonunu işaretleyin!")

        with aa3:
            if st.button("➕ Bu Aşamaya Ekle", key=f"aaekle_{_asama_key}", use_container_width=True):
                st.session_state["aktif_tab"] = "yeni"
                st.session_state["varsayilan_asama"] = secili_asama_sayfa; st.rerun()

    st.divider()

    # ── SAYFA RAPORU ─────────────────────────────────────────────────────────
    with st.expander("📊 Rapor & Durum Yönetimi", expanded=True):

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


# ── ARŞİV ─────────────────────────────────────────────────────────────────────
elif aktif == "arsiv":
    sayfa_log("arsiv")
    df_arsiv = db_read("cari_kartlar", filters={"silindi": 1}, order_col="tarih")

    st.markdown(f"**Arşivde {len(df_arsiv)} kayıt**")

    if df_arsiv.empty:
        st.info("Arşiv boş.")
    else:
        edited_arsiv = st.data_editor(
            df_arsiv,
            use_container_width=True,
            column_config={
                "id":            st.column_config.NumberColumn("ID", disabled=True),
                "tarih":         st.column_config.TextColumn("Tarih", disabled=True),
                "olusturan":     st.column_config.TextColumn("Oluşturan", disabled=True),
                "silindi":       st.column_config.NumberColumn("Silindi", disabled=True),
                "durum":         st.column_config.SelectboxColumn("Durum", options=["Aktif","Hedef","Pasif"]),
                "islem_asamasi": st.column_config.SelectboxColumn("İşlem Aşaması", options=["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]),
            },
            key="arsiv_editor"
        )

        col_geri, col_guncelle = st.columns(2)
        with col_geri:
            with st.expander("♻️ Arşivden Geri Al"):
                restore_id = st.number_input("Geri getirilecek ID:", min_value=1, step=1, key="restore_id")
                if st.button("Geri Al", use_container_width=True):
                    db_update("cari_kartlar", {"silindi": 0}, "id", restore_id)
                    try: db_read.clear()
                    except: pass
                    st.success(f"✅ ID {restore_id} geri alındı.")
                    st.rerun()

        with col_guncelle:
            if st.button("💾 Arşiv Değişikliklerini Kaydet", use_container_width=True):
                for _, row in edited_arsiv.iterrows():
                    if row.get("id"):
                        db_update("cari_kartlar", {
                            "firma": row.get("firma"), "yetkili": row.get("yetkili"),
                            "gsm": row.get("gsm"), "sabit": row.get("sabit"),
                            "email": row.get("email"), "adres": row.get("adres"),
                            "ilce": row.get("ilce"), "il": row.get("il"),
                            "durum": row.get("durum"), "temsilci": row.get("temsilci"),
                            "islem_asamasi": row.get("islem_asamasi")
                        }, "id", row.get("id"))
                st.success("✅ Arşiv güncellendi!")
                st.rerun()

# ── KULLANICI YÖNETİMİ ───────────────────────────────────────────────────────
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
        "excel":"📥 Excel","arsiv":"🗃️ Arşiv","mesajlar":"💬 Mesajlar",
        "admin_rapor":"📊 Rapor Tasarla","kullanici_log":"📊 Kullanıcı Log",
        "surum_yonetimi":"🚀 Sürüm Yönetimi"
    }

    # Sürüm Yönetimi sekmesi: sadece admin VEYA yetkisi olan kullanıcı
    _surum_yetkisi = (
        st.session_state.get("rol") == "admin" or
        "surum_yonetimi" in str(st.session_state.get("_yetki_listesi",""))
    )

    if st.session_state.get("rol") == "admin":
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5 = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi"])
    elif _surum_yetkisi:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4, kul_tab5 = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log","🚀 Sürüm Yönetimi"])
    else:
        kul_tab1, kul_tab2, kul_tab3, kul_tab4 = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle","📊 Kullanıcı Log"])
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
                mv_liste = _kj2.loads(mv) if mv!="tam" else list(TUM_MENULER.keys())
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
                ystr = "tam" if tam2_cb else _kj2.dumps(yeni_liste)
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

    st.markdown("## 📊 Raporlar")
    st.caption("Başlığa tıklayarak raporu açın")

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

        # Üst metrikler
        m1,m2,m3,m4,m5,m6 = st.columns(6)
        m1.metric("Toplam", toplam)
        m2.metric("Aktif", len(df_rapor[df_rapor["durum"]=="Aktif"]))
        m3.metric("Hedef", len(df_rapor[df_rapor["durum"]=="Hedef"]))
        m4.metric("Pasif", len(df_rapor[df_rapor["durum"]=="Pasif"]))
        m5.metric("Beklenen", fmt_para(toplam_beklenen))
        m6.metric("Gerçekleşen", fmt_para(toplam_gercek))
    else:
        st.info("Henüz müşteri kaydı yok.")

    st.divider()
    st.markdown("### 📅 Randevu Raporları")

    if not df_rand_r.empty and "adet" in df_rand_r.columns:
        df_rand_r["adet"] = pd.to_numeric(df_rand_r["adet"], errors="coerce").fillna(0)
        rm1,rm2,rm3,rm4 = st.columns(4)
        rm1.metric("Toplam Randevu", len(df_rand_r))
        rm2.metric("✅ Bitti", len(df_rand_r[df_rand_r["sonuc"]=="Bitti"]) if "sonuc" in df_rand_r.columns else 0)
        rm3.metric("🔄 Devam", len(df_rand_r[df_rand_r["sonuc"]=="Devam Ediyor"]) if "sonuc" in df_rand_r.columns else 0)
        rm4.metric("❌ Gidilmedi", len(df_rand_r[df_rand_r["sonuc"]=="Gidilmedi"]) if "sonuc" in df_rand_r.columns else 0)

    with st.expander("📊 Genel Özet — Tarih & Temsilci"):
        if df_rand_r.empty:
            st.info("Randevu yok.")
        else:
            if "randevu_tarihi" in df_rand_r.columns:
                t_oz = df_rand_r.groupby("randevu_tarihi").agg(
                    Musteri=("musteri_adi","nunique"), Randevu=("id","count")
                ).reset_index().sort_values("randevu_tarihi", ascending=False)
                t_oz.columns = ["Tarih","Müşteri","Randevu"]
                st.dataframe(t_oz, use_container_width=True, hide_index=True)
            if "temsilci" in df_rand_r.columns:
                tem_oz = df_rand_r.groupby("temsilci").agg(
                    Toplam=("id","count"),
                    Bitti=("sonuc", lambda x: (x=="Bitti").sum()),
                    Devam=("sonuc", lambda x: (x=="Devam Ediyor").sum()),
                ).reset_index().sort_values("Toplam", ascending=False)
                st.dataframe(tem_oz, use_container_width=True, hide_index=True)

    with st.expander("🗺️ Bölge Raporu"):
        if df_rand_r.empty:
            st.info("Randevu yok.")
        elif "bolge" in df_rand_r.columns:
            b_oz = df_rand_r.groupby("bolge").agg(
                Randevu=("id","count"), Musteri=("musteri_adi","nunique"),
                Bitti=("sonuc", lambda x: (x=="Bitti").sum())
            ).reset_index().sort_values("Randevu", ascending=False)
            b_oz.columns = ["Bölge","Randevu","Müşteri","Bitti"]
            st.dataframe(b_oz, use_container_width=True, hide_index=True)
            buf_b = _rio2.BytesIO(); b_oz.to_excel(buf_b, index=False); buf_b.seek(0)
            st.download_button("📥 İndir", data=buf_b, file_name="bolge.xlsx", use_container_width=True)

    with st.expander("🎯 Görev Raporu"):
        if df_rand_r.empty:
            st.info("Randevu yok.")
        elif "gorev" in df_rand_r.columns:
            g_oz = df_rand_r.groupby("gorev").agg(
                Adet=("id","count"),
                Bitti=("sonuc", lambda x: (x=="Bitti").sum()),
                Devam=("sonuc", lambda x: (x=="Devam Ediyor").sum()),
                Gidilmedi=("sonuc", lambda x: (x=="Gidilmedi").sum()),
            ).reset_index().sort_values("Adet", ascending=False)
            g_oz["Başarı%"] = (g_oz["Bitti"]/g_oz["Adet"]*100).round(1).astype(str)+"%"
            st.dataframe(g_oz, use_container_width=True, hide_index=True)
            if "temsilci" in df_rand_r.columns:
                st.markdown("**Temsilci × Görev:**")
                st.dataframe(pd.crosstab(df_rand_r["temsilci"], df_rand_r["gorev"]), use_container_width=True)

    with st.expander("📋 Takip & Sonuç Raporu"):
        if df_rand_r.empty:
            st.info("Randevu yok.")
        else:
            if "takip" in df_rand_r.columns:
                st.markdown("**Takip:**")
                st.dataframe(df_rand_r.groupby("takip").size().reset_index(name="Adet"), use_container_width=True, hide_index=True)
            if "sonuc" in df_rand_r.columns:
                st.markdown("**Sonuç:**")
                st.dataframe(df_rand_r.groupby("sonuc").agg(Adet=("id","count"),Musteri=("musteri_adi","nunique")).reset_index(), use_container_width=True, hide_index=True)
            acik = df_rand_r[~df_rand_r.get("sonuc",pd.Series()).isin(["Bitti","İptal","Gidilmedi"])] if "sonuc" in df_rand_r.columns else pd.DataFrame()
            if not acik.empty:
                st.warning(f"⚠️ {len(acik)} açık randevu!")
                st.dataframe(acik[[c for c in ["randevu_tarihi","musteri_adi","bolge","gorev","temsilci","sonuc"] if c in acik.columns]], use_container_width=True, hide_index=True)
            else:
                st.success("✅ Tüm sonuçlar girilmiş.")
            buf_rs = _rio2.BytesIO(); df_rand_r.to_excel(buf_rs, index=False); buf_rs.seek(0)
            st.download_button("📥 Randevu Raporu", data=buf_rs, file_name="randevu_raporu.xlsx", use_container_width=True)

    st.divider()
    st.markdown("### 🏢 Cari Raporlar")

    with st.expander("📊 Durum Dağılımı"):
        if df_rapor.empty: st.info("Veri yok.")
        else:
            d_oz = df_rapor.groupby("durum").agg(Adet=("firma","count"),Beklenen=("beklenen_ciro","sum"),Gerceklesen=("gerceklesen_ciro","sum")).reset_index()
            d_oz["Beklenen"] = d_oz["Beklenen"].apply(fmt_para)
            d_oz["Gerceklesen"] = d_oz["Gerceklesen"].apply(fmt_para)
            st.dataframe(d_oz, use_container_width=True, hide_index=True)

    with st.expander("🔄 Aşama Bazlı Detay Raporu — Patron Görünümü", expanded=False):
        if df_rapor.empty: st.info("Veri yok.")
        else:
            # Tüm aşamaları bul
            tum_asama_r = sorted(df_rapor["islem_asamasi"].dropna().unique().tolist())
            
            # Özet tablo
            a_oz = df_rapor.groupby("islem_asamasi").agg(
                Adet=("firma","count"),
                Beklenen=("beklenen_ciro","sum"),
                Gerceklesen=("gerceklesen_ciro","sum")
            ).reset_index().sort_values("Adet",ascending=False)
            a_oz["Başarı%"] = a_oz.apply(lambda r: f"{r['Gerceklesen']/r['Beklenen']*100:.1f}%" if r["Beklenen"]>0 else "—", axis=1)
            a_oz["Beklenen"] = a_oz["Beklenen"].apply(fmt_para)
            a_oz["Gerceklesen"] = a_oz["Gerceklesen"].apply(fmt_para)
            a_oz.columns = ["Aşama","Müşteri Sayısı","Beklenen Ciro","Gerçekleşen","Başarı%"]
            st.markdown("**📊 Aşama Özeti:**")
            st.dataframe(a_oz, use_container_width=True, hide_index=True)
            
            st.divider()
            # Her aşama için detay tab
            if tum_asama_r:
                asama_tabs = st.tabs([f"🔹 {a}" for a in tum_asama_r])
                for tab_i, asama_adi in enumerate(tum_asama_r):
                    with asama_tabs[tab_i]:
                        df_asama_r = df_rapor[df_rapor["islem_asamasi"]==asama_adi]
                        st.markdown(f"**{asama_adi} — {len(df_asama_r)} firma**")
                        
                        # Metrikler
                        rm1,rm2,rm3,rm4 = st.columns(4)
                        rm1.metric("Firma", len(df_asama_r))
                        rm2.metric("Aktif", len(df_asama_r[df_asama_r["durum"]=="Aktif"]) if "durum" in df_asama_r.columns else 0)
                        rm3.metric("Beklenen", fmt_para(df_asama_r["beklenen_ciro"].sum()))
                        rm4.metric("Gerçekleşen", fmt_para(df_asama_r["gerceklesen_ciro"].sum()))
                        
                        # Liste
                        goster_cols = [c for c in ["id","firma","yetkili","gsm","il","durum","temsilci","aciklama","beklenen_ciro","gerceklesen_ciro"] if c in df_asama_r.columns]
                        df_show = df_asama_r[goster_cols].copy()
                        if "beklenen_ciro" in df_show.columns:
                            df_show["beklenen_ciro"] = df_show["beklenen_ciro"].apply(fmt_para)
                        if "gerceklesen_ciro" in df_show.columns:
                            df_show["gerceklesen_ciro"] = df_show["gerceklesen_ciro"].apply(fmt_para)
                        st.dataframe(df_show, use_container_width=True, hide_index=True)
                        
                        buf_ar = _rio2.BytesIO(); df_asama_r.to_excel(buf_ar, index=False); buf_ar.seek(0)
                        st.download_button(f"📥 {asama_adi} Excel", data=buf_ar, file_name=f"asama_{asama_adi}.xlsx", use_container_width=True, key=f"dl_asama_{asama_adi}")

    with st.expander("👤 Temsilci Bazlı Rapor"):
        if df_rapor.empty: st.info("Veri yok.")
        else:
            t_oz3 = df_rapor.groupby("temsilci").agg(
                Musteri=("firma","count"), Beklenen=("beklenen_ciro","sum"),
                Gerceklesen=("gerceklesen_ciro","sum"), Fark=("fark","sum")
            ).reset_index().sort_values("Gerceklesen",ascending=False)
            t_oz3["Başarı%"] = t_oz3.apply(lambda r: f"{r['Gerceklesen']/r['Beklenen']*100:.1f}%" if r["Beklenen"]>0 else "0%", axis=1)
            t_oz3["Beklenen"] = t_oz3["Beklenen"].apply(fmt_para)
            t_oz3["Gerceklesen"] = t_oz3["Gerceklesen"].apply(fmt_para)
            t_oz3["Fark"] = t_oz3["Fark"].apply(fmt_para)
            st.dataframe(t_oz3, use_container_width=True, hide_index=True)

    with st.expander("🗺️ İl Bazlı Rapor (Top 15)"):
        if df_rapor.empty: st.info("Veri yok.")
        else:
            il_oz = df_rapor.groupby("il").agg(Musteri=("firma","count"),Beklenen=("beklenen_ciro","sum"),Gerceklesen=("gerceklesen_ciro","sum")).reset_index().sort_values("Musteri",ascending=False).head(15)
            il_oz["Beklenen"] = il_oz["Beklenen"].apply(fmt_para)
            il_oz["Gerceklesen"] = il_oz["Gerceklesen"].apply(fmt_para)
            st.dataframe(il_oz, use_container_width=True, hide_index=True)

    with st.expander("💰 Müşteri Bazlı Ciro Detayı (Top 20)"):
        if df_rapor.empty: st.info("Veri yok.")
        else:
            top20 = df_rapor.sort_values("beklenen_ciro",ascending=False).head(20)
            show_cols = [c for c in ["firma","temsilci","il","durum","islem_asamasi","beklenen_ciro","gerceklesen_ciro","yuzde"] if c in top20.columns]
            df_top = top20[show_cols].copy()
            df_top["beklenen_ciro"] = df_top["beklenen_ciro"].apply(fmt_para)
            df_top["gerceklesen_ciro"] = df_top["gerceklesen_ciro"].apply(fmt_para)
            df_top["yuzde"] = df_top["yuzde"].apply(lambda x: f"{x:.1f}%")
            st.dataframe(df_top, use_container_width=True, hide_index=True)
            buf_c = _rio2.BytesIO(); df_top.to_excel(buf_c, index=False); buf_c.seek(0)
            st.download_button("📥 İndir", data=buf_c, file_name="ciro_top20.xlsx", use_container_width=True)

    with st.expander("🔍 Arama / Filtreleme Raporu"):
        if df_rapor.empty: st.info("Veri yok.")
        else:
            fa1,fa2,fa3 = st.columns(3)
            ara_r = fa1.text_input("Ara:", key="rp_ara")
            fil_d = fa2.selectbox("Durum:", ["Tümü","Aktif","Hedef","Pasif"], key="rp_durum")
            fil_a = fa3.selectbox("Aşama:", ["Tümü","İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"], key="rp_asama")
            df_f = df_rapor.copy()
            if ara_r: df_f = df_f[df_f.apply(lambda r: ara_r.lower() in str(r).lower(), axis=1)]
            if fil_d != "Tümü": df_f = df_f[df_f["durum"]==fil_d]
            if fil_a != "Tümü": df_f = df_f[df_f["islem_asamasi"]==fil_a]
            st.caption(f"{len(df_f)} kayıt")
            st.dataframe(df_f[[c for c in ["id","firma","yetkili","gsm","email","durum","islem_asamasi","temsilci","il"] if c in df_f.columns]], use_container_width=True, hide_index=True)
            buf_f = _rio2.BytesIO(); df_f.to_excel(buf_f, index=False); buf_f.seek(0)
            st.download_button("📥 İndir", data=buf_f, file_name="filtre_raporu.xlsx", use_container_width=True)

    with st.expander("📱 WhatsApp & Email Gönderim Raporu"):
        try:
            df_wa = db_read("islem_kaydi", order_col="tarih", limit=500)
            if df_wa.empty:
                st.info("Kayıt yok.")
            else:
                st.caption(f"{len(df_wa)} kayıt")
                st.dataframe(df_wa, use_container_width=True, hide_index=True)
                buf_wa = _rio2.BytesIO(); df_wa.to_excel(buf_wa, index=False); buf_wa.seek(0)
                st.download_button("📥 İndir", data=buf_wa, file_name="wa_email.xlsx", use_container_width=True)
        except Exception as e:
            st.error(f"Hata: {e}")

    st.divider()
    st.markdown("### 📄 Teklif Raporları")

    if not df_tek_r.empty and "toplam_tutar" in df_tek_r.columns:
        df_tek_r["toplam_tutar"] = pd.to_numeric(df_tek_r["toplam_tutar"], errors="coerce").fillna(0)
        tk1,tk2,tk3 = st.columns(3)
        tk1.metric("Toplam Teklif", len(df_tek_r))
        tk2.metric("Toplam Tutar", fmt_para(df_tek_r["toplam_tutar"].sum()))
        tk3.metric("Ort. Teklif", fmt_para(df_tek_r["toplam_tutar"].mean()))

    with st.expander("📄 Verilen Teklifler Raporu"):
        if df_tek_r.empty:
            st.info("Teklif yok.")
        else:
            goster = [c for c in ["id","tarih","musteri_adi","toplam_tutar","olusturan","notlar"] if c in df_tek_r.columns]
            df_gs = df_tek_r[goster].copy()
            df_gs["toplam_tutar"] = df_gs["toplam_tutar"].apply(fmt_para)
            st.dataframe(df_gs, use_container_width=True, hide_index=True)
            sec_t = st.selectbox("Detay gör:", ["-- Seçin --"]+[f"[{int(r['id'])}] {r.get('musteri_adi','')} | {fmt_para(r.get('toplam_tutar',0))}" for _,r in df_tek_r.iterrows()], key="rp_tek_sec")
            if sec_t != "-- Seçin --" and "[" in sec_t:
                tid = int(sec_t.split("]")[0].replace("[",""))
                trow = df_tek_r[df_tek_r["id"]==tid].iloc[0]
                try:
                    d = json.loads(trow.get("satirlar","{}"))
                    if "teklif" in d: st.dataframe(pd.DataFrame(d["teklif"]), use_container_width=True, hide_index=True)
                    if "hesap" in d: st.dataframe(pd.DataFrame(d["hesap"]), use_container_width=True, hide_index=True)
                except: pass
            buf_t = _rio2.BytesIO(); df_tek_r.to_excel(buf_t, index=False); buf_t.seek(0)
            st.download_button("📥 İndir", data=buf_t, file_name="teklifler.xlsx", use_container_width=True)

    with st.expander("🗺️ İl & Ürün Türü Raporu"):
        if df_tek_r.empty:
            st.info("Teklif yok.")
        else:
            il_tur_detay = []
            for _,row_t in df_tek_r.iterrows():
                try:
                    d = json.loads(row_t.get("satirlar","{}"))
                    for s in d.get("teklif",[]):
                        il_tur_detay.append({
                            "Müşteri": row_t.get("musteri_adi",""),
                            "Çıkış İli": s.get("cikis_il",""), "Varış İli": s.get("varis_il",""),
                            "Tür": s.get("tur",""), "KG": float(s.get("kg",0) or 0),
                            "Desi": float(s.get("bit_desi",0) or 0), "Tutar": float(s.get("tutar",0) or 0),
                        })
                except: pass
            if il_tur_detay:
                df_it = pd.DataFrame(il_tur_detay)
                st.markdown("**İl Analizi:**")
                il_oz2 = df_it.groupby(["Çıkış İli","Varış İli"]).agg(Adet=("KG","count"),Toplam=("Tutar","sum")).reset_index().sort_values("Toplam",ascending=False)
                il_oz2["Toplam"] = il_oz2["Toplam"].apply(fmt_para)
                st.dataframe(il_oz2, use_container_width=True, hide_index=True)
                st.markdown("**Ürün Türü:**")
                tur_oz = df_it.groupby("Tür").agg(Adet=("KG","count"),Toplam=("Tutar","sum")).reset_index().sort_values("Toplam",ascending=False)
                tur_oz["Toplam"] = tur_oz["Toplam"].apply(fmt_para)
                st.dataframe(tur_oz, use_container_width=True, hide_index=True)
                buf_it = _rio2.BytesIO(); df_it.to_excel(buf_it, index=False); buf_it.seek(0)
                st.download_button("📥 İndir", data=buf_it, file_name="il_tur.xlsx", use_container_width=True)
            else:
                st.info("İl/tür verisi yok.")

elif aktif == "teklif":
    sayfa_log("teklif")
    import json, re, io

    st.markdown("## Teklif Olustur")

    IL_KM = {
        ("Istanbul","Ankara"):454,("Ankara","Istanbul"):454,
        ("Istanbul","Izmir"):479,("Izmir","Istanbul"):479,
        ("Istanbul","Bursa"):154,("Bursa","Istanbul"):154,
        ("Istanbul","Antalya"):725,("Antalya","Istanbul"):725,
        ("Istanbul","Konya"):664,("Konya","Istanbul"):664,
        ("Istanbul","Adana"):939,("Adana","Istanbul"):939,
        ("Istanbul","Gaziantep"):1130,("Gaziantep","Istanbul"):1130,
        ("Istanbul","Kayseri"):770,("Kayseri","Istanbul"):770,
        ("Istanbul","Mersin"):930,("Mersin","Istanbul"):930,
        ("Istanbul","Diyarbakir"):1360,("Diyarbakir","Istanbul"):1360,
        ("Istanbul","Samsun"):730,("Samsun","Istanbul"):730,
        ("Istanbul","Trabzon"):1100,("Trabzon","Istanbul"):1100,
        ("Istanbul","Erzurum"):1270,("Erzurum","Istanbul"):1270,
        ("Ankara","Izmir"):590,("Izmir","Ankara"):590,
        ("Ankara","Antalya"):480,("Antalya","Ankara"):480,
        ("Ankara","Konya"):260,("Konya","Ankara"):260,
        ("Ankara","Adana"):490,("Adana","Ankara"):490,
        ("Ankara","Samsun"):420,("Samsun","Ankara"):420,
        ("Ankara","Trabzon"):790,("Trabzon","Ankara"):790,
        ("Izmir","Antalya"):490,("Antalya","Izmir"):490,
        ("Izmir","Bursa"):330,("Bursa","Izmir"):330,
        ("Bursa","Ankara"):390,("Ankara","Bursa"):390,
        ("Konya","Antalya"):220,("Antalya","Konya"):220,
        ("Konya","Adana"):330,("Adana","Konya"):330,
        ("Adana","Gaziantep"):220,("Gaziantep","Adana"):220,
        ("Adana","Mersin"):70,("Mersin","Adana"):70,
        ("Gaziantep","Diyarbakir"):300,("Diyarbakir","Gaziantep"):300,
        ("Samsun","Trabzon"):355,("Trabzon","Samsun"):355,
        ("Trabzon","Erzurum"):215,("Erzurum","Trabzon"):215,
        ("Kayseri","Adana"):340,("Adana","Kayseri"):340,
        ("Kayseri","Konya"):260,("Konya","Kayseri"):260,
        ("Kayseri","Ankara"):320,("Ankara","Kayseri"):320,
        ("Eskisehir","Istanbul"):330,("Istanbul","Eskisehir"):330,
        ("Eskisehir","Ankara"):235,("Ankara","Eskisehir"):235,
        ("Manisa","Izmir"):40,("Izmir","Manisa"):40,
        ("Denizli","Izmir"):250,("Izmir","Denizli"):250,
        ("Balikesir","Istanbul"):310,("Istanbul","Balikesir"):310,
        ("Tekirdag","Istanbul"):135,("Istanbul","Tekirdag"):135,
        ("Edirne","Istanbul"):230,("Istanbul","Edirne"):230,
        ("Kocaeli","Istanbul"):100,("Istanbul","Kocaeli"):100,
        ("Sakarya","Istanbul"):160,("Istanbul","Sakarya"):160,
        ("Hatay","Adana"):195,("Adana","Hatay"):195,
        ("Kahramanmaras","Adana"):175,("Adana","Kahramanmaras"):175,
        ("Malatya","Elazig"):100,("Elazig","Malatya"):100,
        ("Elazig","Diyarbakir"):155,("Diyarbakir","Elazig"):155,
        ("Mardin","Diyarbakir"):95,("Diyarbakir","Mardin"):95,
        ("Ordu","Samsun"):115,("Samsun","Ordu"):115,
        ("Giresun","Trabzon"):170,("Trabzon","Giresun"):170,
        ("Rize","Trabzon"):75,("Trabzon","Rize"):75,
        ("Isparta","Antalya"):135,("Antalya","Isparta"):135,
        ("Aydin","Izmir"):100,("Izmir","Aydin"):100,
        ("Canakkale","Istanbul"):325,("Istanbul","Canakkale"):325,
        ("Yalova","Istanbul"):80,("Istanbul","Yalova"):80,
        ("Sinop","Samsun"):170,("Samsun","Sinop"):170,
        ("Duzce","Istanbul"):200,("Istanbul","Duzce"):200,
    }

    def get_km(cikis, varis):
        if not cikis or not varis or cikis == varis:
            return ""
        key = (cikis.strip(), varis.strip())
        if key in IL_KM: return str(IL_KM[key])
        key2 = (varis.strip(), cikis.strip())
        if key2 in IL_KM: return str(IL_KM[key2])
        return "?"

    URUN_TIPLERI = ["Koli","Sandık","Top","Çuval","Kasa","Palet","Diğer","Manuel"]
    IL_LISTESI = ["","İstanbul","Ankara","İzmir","Bursa","Antalya","Adana","Konya",
        "Gaziantep","Mersin","Kayseri","Eskişehir","Diyarbakır","Samsun","Trabzon",
        "Erzurum","Şanlıurfa","Manisa","Balıkesir","Tekirdağ","Kocaeli","Sakarya",
        "Denizli","Muğla","Hatay","Malatya","Kahramanmaraş","Van","Elazığ","Aydın",
        "Edirne","Çanakkale","Afyonkarahisar","Isparta","Kütahya","Uşak","Nevşehir",
        "Niğde","Aksaray","Yozgat","Sivas","Erzincan","Ordu","Amasya","Tokat","Çorum",
        "Sinop","Kastamonu","Karabük","Zonguldak","Bolu","Düzce","Yalova","Bilecik",
        "Kırklareli","Kırıkkale","Çankırı","Karaman","Osmaniye","Kilis","Adıyaman",
        "Burdur","Rize","Giresun","Artvin","Mardin","Şırnak","Batman","Bitlis",
        "Muş","Bingöl","Tunceli","Siirt","Hakkari","Ağrı","Iğdır","Kars","Ardahan"]

    # IL_KM anahtarlarını da Türkçe'ye çevir
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
        ("İstanbul","Diyarbakır"):1360,("Diyarbakır","İstanbul"):1360,
        ("İstanbul","Samsun"):730,("Samsun","İstanbul"):730,
        ("İstanbul","Trabzon"):1100,("Trabzon","İstanbul"):1100,
        ("İstanbul","Erzurum"):1270,("Erzurum","İstanbul"):1270,
        ("İstanbul","Eskişehir"):330,("Eskişehir","İstanbul"):330,
        ("İstanbul","Balıkesir"):310,("Balıkesir","İstanbul"):310,
        ("İstanbul","Tekirdağ"):135,("Tekirdağ","İstanbul"):135,
        ("İstanbul","Edirne"):230,("Edirne","İstanbul"):230,
        ("İstanbul","Kocaeli"):100,("Kocaeli","İstanbul"):100,
        ("İstanbul","Sakarya"):160,("Sakarya","İstanbul"):160,
        ("İstanbul","Düzce"):200,("Düzce","İstanbul"):200,
        ("İstanbul","Yalova"):80,("Yalova","İstanbul"):80,
        ("İstanbul","Çanakkale"):325,("Çanakkale","İstanbul"):325,
        ("Ankara","İzmir"):590,("İzmir","Ankara"):590,
        ("Ankara","Antalya"):480,("Antalya","Ankara"):480,
        ("Ankara","Konya"):260,("Konya","Ankara"):260,
        ("Ankara","Adana"):490,("Adana","Ankara"):490,
        ("Ankara","Samsun"):420,("Samsun","Ankara"):420,
        ("Ankara","Trabzon"):790,("Trabzon","Ankara"):790,
        ("Ankara","Bursa"):390,("Bursa","Ankara"):390,
        ("Ankara","Eskişehir"):235,("Eskişehir","Ankara"):235,
        ("Ankara","Kayseri"):320,("Kayseri","Ankara"):320,
        ("İzmir","Antalya"):490,("Antalya","İzmir"):490,
        ("İzmir","Bursa"):330,("Bursa","İzmir"):330,
        ("İzmir","Manisa"):40,("Manisa","İzmir"):40,
        ("İzmir","Denizli"):250,("Denizli","İzmir"):250,
        ("İzmir","Aydın"):100,("Aydın","İzmir"):100,
        ("Konya","Antalya"):220,("Antalya","Konya"):220,
        ("Konya","Adana"):330,("Adana","Konya"):330,
        ("Konya","Kayseri"):260,("Kayseri","Konya"):260,
        ("Adana","Gaziantep"):220,("Gaziantep","Adana"):220,
        ("Adana","Mersin"):70,("Mersin","Adana"):70,
        ("Adana","Hatay"):195,("Hatay","Adana"):195,
        ("Adana","Kahramanmaraş"):175,("Kahramanmaraş","Adana"):175,
        ("Adana","Kayseri"):340,("Kayseri","Adana"):340,
        ("Gaziantep","Diyarbakır"):300,("Diyarbakır","Gaziantep"):300,
        ("Samsun","Trabzon"):355,("Trabzon","Samsun"):355,
        ("Samsun","Ordu"):115,("Ordu","Samsun"):115,
        ("Samsun","Sinop"):170,("Sinop","Samsun"):170,
        ("Trabzon","Erzurum"):215,("Erzurum","Trabzon"):215,
        ("Trabzon","Giresun"):170,("Giresun","Trabzon"):170,
        ("Trabzon","Rize"):75,("Rize","Trabzon"):75,
        ("Elazığ","Diyarbakır"):155,("Diyarbakır","Elazığ"):155,
        ("Elazığ","Malatya"):100,("Malatya","Elazığ"):100,
        ("Diyarbakır","Mardin"):95,("Mardin","Diyarbakır"):95,
        ("Antalya","Isparta"):135,("Isparta","Antalya"):135,
    }

    def get_km(cikis, varis):
        if not cikis or not varis or cikis == varis: return ""
        key = (cikis.strip(), varis.strip())
        if key in IL_KM_TR: return str(IL_KM_TR[key])
        if key in IL_KM: return str(IL_KM[key])
        return "?"

    # Musteri listesi - TUM musteriler (durum filtresi dropdown ile)
    df_m = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")

    fil_col, _ = st.columns([2,4])
    df_fil = fil_col.selectbox("Filtre:", ["Tumu","Aktif","Hedef","Pasif"], key="teklif_fil")
    musteriler_f = df_m if df_fil == "Tumu" else df_m[df_m["durum"] == df_fil]

    # Musteri secim listesi: ID + firma + durum hepsi gorunsun
    musteri_opts = ["-- Musteri Secin --"] + [
        f"[{int(r['id'])}] {str(r['firma'])} ({str(r['durum'])})"
        for _, r in musteriler_f.iterrows()]

    secim = st.selectbox("Teklif Verilecek Firma (ID + Ad + Durum):", musteri_opts, key="teklif_musteri")

    secili_musteri = None
    gsm_kayitli = ""; email_kayitli = ""

    if secim != "-- Musteri Secin --" and secim.startswith("["):
        try:
            mid = int(secim.split("]")[0].replace("[","").strip())
            rows = df_m[df_m["id"] == mid]
            if len(rows) > 0:
                secili_musteri = rows.iloc[0]
                gsm_kayitli = str(secili_musteri["gsm"] or "")
                email_kayitli = str(secili_musteri["email"] or "")
                c1, c2, c3 = st.columns(3)
                c1.info(f"Email: {email_kayitli or 'Yok'}")
                c2.info(f"GSM: {gsm_kayitli or 'Yok'}")
                c3.info(f"Il: {secili_musteri['il'] or ''} | {secili_musteri['durum'] or ''}")
        except Exception as e:
            st.error(f"Secim hatasi: {e}")

    # Ust bilgiler
    st.markdown("### Teklif Bilgileri")
    ub1, ub2, ub3 = st.columns(3)
    firma_default = str(secili_musteri["firma"]) if secili_musteri is not None else ""
    # Müşteri seçilince key'i güncelle
    if "hedef_mus" not in st.session_state or (secili_musteri is not None and st.session_state.get("son_secili_id") != secim):
        st.session_state["hedef_mus"] = firma_default
        st.session_state["son_secili_id"] = secim
    hedef_musteri = ub1.text_input("Hedef Musteri", key="hedef_mus")
    vade = ub2.text_input("Vade", placeholder="30 gun, pesin...", key="vade")
    gorus = ub3.text_area("Gorus", placeholder="Gorusme notu...", key="gorus", height=80)
    musteri_talep = ub1.text_area("Musteri Talep", key="musteri_talep", height=80)

    # Manuel iletisim
    st.markdown("#### Iletisim (Kayitli yoksa manuel girin)")
    mc1, mc2 = st.columns(2)
    gsm_manuel = mc1.text_input("WhatsApp No", value=gsm_kayitli, placeholder="05xxxxxxxxx", key="gsm_manuel")
    email_manuel = mc2.text_input("Email", value=email_kayitli, placeholder="ornek@firma.com", key="email_manuel")

    # WA isleme
    gsm_temiz2 = re.sub(r"[\s\-\(\)]", "", gsm_manuel)
    if gsm_temiz2.startswith("0") and len(gsm_temiz2) == 11:
        gsm_wa_final = "90" + gsm_temiz2[1:]
    elif gsm_temiz2.startswith("+9"):
        gsm_wa_final = gsm_temiz2.replace("+","")
    elif len(gsm_temiz2) == 10:
        gsm_wa_final = "90" + gsm_temiz2
    elif len(gsm_temiz2) == 12 and gsm_temiz2.startswith("90"):
        gsm_wa_final = gsm_temiz2
    else:
        gsm_wa_final = gsm_temiz2
    wa_final_gecerli = len(gsm_wa_final) == 12 and gsm_wa_final.isdigit()
    if gsm_manuel:
        if wa_final_gecerli:
            st.success(f"WhatsApp: {gsm_wa_final}")
        else:
            st.error("Gecersiz numara! 05xxxxxxxxx formatinda girin.")

    st.divider()

    # Satir sayisi
    if "teklif_satir_n" not in st.session_state:
        st.session_state["teklif_satir_n"] = 1

    col_ekle, col_sil, col_sort = st.columns([1,1,2])
    with col_ekle:
        if st.button("+ Satır Ekle", use_container_width=True, type="primary"):
            st.session_state["teklif_satir_n"] += 1
            st.rerun()
    with col_sil:
        if st.button("- Son Satırı Sil", use_container_width=True) and st.session_state["teklif_satir_n"] > 1:
            st.session_state["teklif_satir_n"] -= 1
            st.rerun()
    with col_sort:
        sort_yonu = st.selectbox("Desi/KG Sırala:", ["—","Büyükten Küçüğe","Küçükten Büyüğe"], key="sort_yonu")

    n = st.session_state["teklif_satir_n"]

    # ONCE hesaplama degerlerini oku (session_state uzerinden)
    # Sonra teklif satirlarinda bu degerleri kullan
    hesap_desi = []
    hesap_bf   = []
    hesap_urun = []

    for i in range(n):
        en_key  = f"h_en_{i}"
        boy_key = f"h_boy_{i}"
        yuk_key = f"h_yuk_{i}"
        bf_key  = f"h_bf_{i}"
        tip_key = f"h_tip_{i}"

        en_v   = float(st.session_state.get(en_key, 0) or 0)
        boy_v  = float(st.session_state.get(boy_key, 0) or 0)
        yuk_v  = float(st.session_state.get(yuk_key, 0) or 0)
        bf_v   = float(st.session_state.get(bf_key, 0) or 0)
        tip_v  = st.session_state.get(tip_key, URUN_TIPLERI[0])

        desi_v = round((en_v * boy_v * yuk_v) / 3000, 2) if (en_v and boy_v and yuk_v) else 0.0
        hesap_desi.append(desi_v)
        hesap_bf.append(bf_v)
        hesap_urun.append(tip_v)

        # Teklif tarafina otomatik yaz (key henuz yoksa)
        bit_key = f"t_bit_{i}"
        tur_key = f"t_tur_{i}"
        if bit_key not in st.session_state:
            st.session_state[bit_key] = desi_v
        else:
            # Her hesaplamada guncelle
            st.session_state[bit_key] = desi_v
        if tur_key not in st.session_state:
            st.session_state[tur_key] = tip_v

    hesap_sonuclar = []
    teklif_sonuclar = []
    toplam_tutar = 0.0

    left, right = st.columns(2)

    with left:
        st.markdown("#### HESAPLAMA")
        hh = st.columns([1.5, 0.7, 0.7, 0.7, 0.8, 1.2])
        for txt, col in zip(["Ürün","En","Boy","Yük","Desi","Birim Fiyat"], hh):
            col.markdown(f"**{txt}**")
        for i in range(n):
            hc = st.columns([1.5, 0.7, 0.7, 0.7, 0.8, 1.2])
            urun_tip = hc[0].selectbox("", URUN_TIPLERI, key=f"h_tip_{i}", label_visibility="collapsed")
            en  = hc[1].number_input("", min_value=0.0, step=1.0, key=f"h_en_{i}", label_visibility="collapsed", format="%.0f")
            boy = hc[2].number_input("", min_value=0.0, step=1.0, key=f"h_boy_{i}", label_visibility="collapsed", format="%.0f")
            yuk = hc[3].number_input("", min_value=0.0, step=1.0, key=f"h_yuk_{i}", label_visibility="collapsed", format="%.0f")
            desi = round((en * boy * yuk) / 3000, 2) if (en and boy and yuk) else 0.0
            hc[4].markdown(f"**{desi}**")
            birim_fiyat = hc[5].number_input("", min_value=0.0, step=0.5, key=f"h_bf_{i}", label_visibility="collapsed")
            urun_adi = urun_tip
            if urun_tip == "Manuel":
                urun_adi = st.text_input(f"Ürün adı {i+1}:", key=f"h_adi_{i}", placeholder="Ürün adı")
            hesap_sonuclar.append({"urun": urun_adi, "en": en, "boy": boy, "yuk": yuk,
                                   "desi": desi, "birim_fiyat": birim_fiyat})
            hesap_desi[i] = desi
            hesap_bf[i]   = birim_fiyat
            hesap_urun[i] = urun_tip

    with right:
        st.markdown("#### TEKLİFİMİZ")
        th = st.columns([1.2,1.2,0.7,0.9,0.8,0.8,0.7,1.0])
        for txt, col in zip(["Çıkış İli","Varış İli","KM","Tür","Baş Desi","Bit Desi","KG","Tutar"], th):
            col.markdown(f"**{txt}**")
        for i in range(n):
            h_desi = hesap_desi[i]
            h_bf   = hesap_bf[i]
            h_urun = hesap_urun[i]
            tur_key = f"t_tur_{i}"
            if h_urun in URUN_TIPLERI:
                st.session_state[tur_key] = h_urun
            with right:
                tc = st.columns([1.2,1.2,0.7,0.9,0.8,0.8,0.7,1.0])
                cikis_il = tc[0].selectbox("", IL_LISTESI, key=f"t_cil_{i}", label_visibility="collapsed")
                varis_il = tc[1].selectbox("", IL_LISTESI, key=f"t_vil_{i}", label_visibility="collapsed")
                auto_km  = get_km(cikis_il, varis_il)
                tc[2].markdown(f"**{auto_km if auto_km else '-'}**")
                tur = tc[3].selectbox("", URUN_TIPLERI, key=tur_key, label_visibility="collapsed")
                bas_desi = tc[4].number_input("", min_value=0.0, step=0.5, key=f"t_bas_{i}", label_visibility="collapsed")
                tc[5].markdown(f"**{h_desi}**")
                bit_desi = h_desi
                kg = tc[6].number_input("", min_value=0.0, step=0.5, key=f"t_kg_{i}", label_visibility="collapsed")
                buyuk = max(kg, bit_desi)
                tutar = round(buyuk * h_bf, 2)
                tc[7].markdown(f"**{fmt_para(tutar)}**")
            toplam_tutar += tutar
            teklif_sonuclar.append({
                "cikis_il": cikis_il, "varis_il": varis_il, "km": auto_km,
                "tur": tur, "bas_desi": bas_desi, "bit_desi": bit_desi,
                "kg": kg, "buyuk": buyuk, "birim_fiyat": h_bf, "tutar": tutar
            })

    if toplam_tutar > 0:
        st.success(f"**Genel Toplam: {fmt_para(toplam_tutar)}**")

    if st.button("Teklifi Kaydet", use_container_width=True, type="primary"):
        if not hedef_musteri:
            st.warning("Musteri adi bos olamaz!")
        else:
            kullanici_log_kaydet("TEKLİF_KAYDET", "teklif", f"Müşteri: {hedef_musteri}, Tutar: {fmt_para(toplam_tutar)}")
            db_insert("teklifler", {
                "musteri_id": int(secili_musteri["id"]) if secili_musteri is not None else 0,
                "musteri_adi": hedef_musteri,
                "satirlar": json.dumps({"hesap": hesap_sonuclar, "teklif": teklif_sonuclar}, ensure_ascii=False),
                "toplam_tutar": toplam_tutar,
                "olusturan": st.session_state["kullanici"],
                "notlar": f"Vade:{vade} | Gorus:{gorus} | Talep:{musteri_talep}"
            })
            st.success("Teklif kaydedildi!")

    st.divider()
    st.markdown("### Mesaj Olustur ve Gonder")

    teklif_ozet_str = "\n".join([
        f"- {t['cikis_il']} > {t['varis_il']} ({t['km']} km): {t['tur']} | {t['bas_desi']}-{t['bit_desi']} desi | {t['buyuk']} kg | {t['birim_fiyat']} TL/kg | Tutar: {t['tutar']:,.2f} TL"
        for t in teklif_sonuclar if t["birim_fiyat"] > 0])
    musteri_ili = str(secili_musteri["il"]) if secili_musteri is not None else ""

    def sablon_wa(firma, ozet, vade_, talep_, il_):
        msg = f"Sayin {firma} yetkilisi,\n\n"
        msg += "Size ozel kargo teklifimiz asagidadir.\n\n"
        msg += f"TEKLIF:\n{ozet}\n"
        if vade_: msg += f"\nVade: {vade_}"
        if il_: msg += f"\n{il_} bolgesine hizmet veriyoruz."
        if talep_: msg += f"\nNot: {talep_}"
        msg += "\n\n7/24 ulasabilirsiniz."
        return msg

    def sablon_email(firma, ozet, vade_, talep_):
        msg = f"Konu: {firma} - Ozel Kargo Fiyat Teklifi\n\n"
        msg += f"Sayin {firma} Yetkilisi,\n\nTEKLIF DETAYLARI:\n{ozet}\n"
        if vade_: msg += f"\nVADE: {vade_}"
        if talep_: msg += f"\nNOTLAR: {talep_}"
        msg += "\n\nSaygilarimizla"
        return msg

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("Sablon Mesaj Olustur", use_container_width=True):
            st.session_state["ai_whatsapp"] = sablon_wa(hedef_musteri, teklif_ozet_str, vade, musteri_talep, musteri_ili)
            st.session_state["ai_email"]    = sablon_email(hedef_musteri, teklif_ozet_str, vade, musteri_talep)
            st.rerun()
    with col_s2:
        api_key = ""
        try: api_key = st.secrets.get("ANTHROPIC_API_KEY","")
        except: pass
        ai_aktif = bool(api_key)
        if st.button("AI ile Ikna Edici Mesaj" if ai_aktif else "AI (API Key Gerekli)",
                     use_container_width=True, type="primary", disabled=not ai_aktif):
            with st.spinner("AI yazıyor..."):
                try:
                    import requests as req
                    prompt = (f"Sen kargo sirketi satis temsilcisisin.\nMusteri: {hedef_musteri} ({musteri_ili})\n"
                              f"Teklif:\n{teklif_ozet_str}\nVade: {vade}\nMusteri talebi: {musteri_talep}\n\n"
                              f"Once WhatsApp (3 paragraf, samimi, ikna edici).\n"
                              f"Sonra ---AYIRAC--- yaz.\nSonra email (Konu: ile basla).")
                    resp = req.post("https://api.anthropic.com/v1/messages",
                        headers={"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"},
                        json={"model":"claude-sonnet-4-20250514","max_tokens":1200,
                              "messages":[{"role":"user","content":prompt}]}, timeout=30)
                    ai_yanit = resp.json()["content"][0]["text"]
                    parcalar = ai_yanit.split("---AYIRAC---")
                    st.session_state["ai_whatsapp"] = parcalar[0].strip()
                    st.session_state["ai_email"]    = parcalar[1].strip() if len(parcalar)>1 else ai_yanit
                    st.rerun()
                except Exception as e:
                    st.error(f"AI hatasi: {e}")
                    st.session_state["ai_whatsapp"] = sablon_wa(hedef_musteri, teklif_ozet_str, vade, musteri_talep, musteri_ili)
                    st.session_state["ai_email"]    = sablon_email(hedef_musteri, teklif_ozet_str, vade, musteri_talep)
                    st.rerun()

    if not ai_aktif:
        st.info("AI icin secrets.toml dosyasina ANTHROPIC_API_KEY ekleyin.")

    if st.session_state.get("ai_whatsapp"):
        st.markdown("#### WhatsApp Mesaji")
        wa_mesaj = st.text_area("", value=st.session_state["ai_whatsapp"], height=180, key="wa_metin")
        st.markdown("#### Email Mesaji")
        email_mesaj = st.text_area("", value=st.session_state["ai_email"], height=200, key="email_metin")

        col_wa, col_em = st.columns(2)
        with col_wa:
            if wa_final_gecerli:
                wa_url = "https://wa.me/" + gsm_wa_final + "?text=" + wa_mesaj.replace(" ","%20").replace("\n","%0A")
                st.link_button("WhatsApp'ta Ac", wa_url, use_container_width=True)
                if st.button("WA Gonderildi Kaydet", use_container_width=True):
                    db_insert("islem_kaydi", {
                        "musteri_id": int(secili_musteri["id"]) if secili_musteri is not None else 0,
                        "musteri_adi": hedef_musteri,
                        "islem_turu": "WhatsApp Teklif",
                        "icerik": wa_mesaj,
                        "gonderim_bilgisi": gsm_wa_final,
                        "olusturan": st.session_state["kullanici"]
                    })
                    st.success("WA gonderimi kaydedildi!")
            else:
                st.warning("Gecerli WA numarasi yok. Yukaridaki alana girin.")
        with col_em:
            email_gonder = email_manuel.strip()
            if email_gonder:
                email_satirlar = email_mesaj.split("\n")
                konu = email_satirlar[0].replace("Konu:","").strip() if email_satirlar else "Teklif"
                govde = "\n".join(email_satirlar[1:]).strip()
                mailto = "mailto:" + email_gonder + "?subject=" + konu + "&body=" + govde.replace(" ","%20").replace("\n","%0A")
                st.link_button("Email'i Ac", mailto, use_container_width=True)
                if st.button("Email Gonderildi Kaydet", use_container_width=True):
                    db_insert("islem_kaydi", {
                        "musteri_id": int(secili_musteri["id"]) if secili_musteri is not None else 0,
                        "musteri_adi": hedef_musteri,
                        "islem_turu": "Email Teklif",
                        "icerik": email_mesaj,
                        "gonderim_bilgisi": email_gonder,
                        "olusturan": st.session_state["kullanici"]
                    })
                    st.success("Email gonderimi kaydedildi!")
            else:
                st.warning("Email yok. Yukaridaki alana girin.")

    st.divider()
    st.markdown("### 📋 Kayıtlı Teklifler")
    try:
        df_tek = db_read("teklifler", order_col="tarih")
        if df_tek.empty:
            st.info("Henüz kayıtlı teklif yok.")
        else:
            # Seçim dropdown
            tek_opts = ["-- Teklif Seçin --"] + [
                f"[{int(r['id'])}] {r.get('musteri_adi','')} | {str(r.get('tarih',''))[:10]} | {fmt_para(float(r.get('toplam_tutar',0) or 0))}"
                for _, r in df_tek.iterrows()
            ]
            sec_tek = st.selectbox("Teklif Seç:", tek_opts, key="tek_sec")

            if sec_tek != "-- Teklif Seçin --" and "[" in sec_tek:
                tek_id = int(sec_tek.split("]")[0].replace("[","").strip())
                tek_row = df_tek[df_tek["id"]==tek_id].iloc[0]

                # Başlık
                st.markdown(f"## 📄 {tek_row.get('musteri_adi','')} — {fmt_para(float(tek_row.get('toplam_tutar',0) or 0))}")
                st.caption(f"📅 {str(tek_row.get('tarih',''))[:16]} | 👤 {tek_row.get('olusturan','')}")
                if tek_row.get('notlar'):
                    st.info(f"📝 {tek_row.get('notlar','')}")

                # Satırlar
                try:
                    data = json.loads(tek_row.get('satirlar','{}'))
                    if "teklif" in data and data["teklif"]:
                        st.markdown("**Teklif Satırları:**")
                        df_t = pd.DataFrame(data["teklif"])
                        if "tutar" in df_t.columns:
                            df_t["tutar"] = df_t["tutar"].apply(lambda x: fmt_para(float(x or 0)))
                        if "birim_fiyat" in df_t.columns:
                            df_t["birim_fiyat"] = df_t["birim_fiyat"].apply(lambda x: fmt_para(float(x or 0)))
                        st.dataframe(df_t, use_container_width=True, hide_index=True)
                    if "hesap" in data and data["hesap"]:
                        st.markdown("**Hesaplama Satırları:**")
                        st.dataframe(pd.DataFrame(data["hesap"]), use_container_width=True, hide_index=True)
                except:
                    st.text(str(tek_row.get('satirlar','')))

                # Aksiyonlar
                st.divider()
                ak1, ak2, ak3 = st.columns(3)

                # Not güncelle
                with ak1.expander("✏️ Notu Güncelle"):
                    yeni_not = st.text_area("Not:", value=str(tek_row.get('notlar','')), height=80, key=f"tek_not_{tek_id}")
                    if st.button("💾 Kaydet", key=f"tek_not_btn_{tek_id}", use_container_width=True):
                        db_update("teklifler", {"notlar": yeni_not}, "id", tek_id)
                        st.success("✅ Not güncellendi!")
                        st.rerun()

                # Arşivle
                if ak2.button("🗃️ Arşivle", key=f"tek_arsiv_{tek_id}", use_container_width=True):
                    db_update("teklifler", {"arsivlendi": 1}, "id", tek_id)
                    st.success("✅ Arşivlendi!")
                    st.rerun()

                # Sil
                if ak3.button("🗑️ Sil", key=f"tek_sil_{tek_id}", use_container_width=True, type="primary"):
                    sb_d = get_sb_client()
                    if sb_d:
                        sb_d.table("teklifler").delete().eq("id", tek_id).execute()
                    st.success("🗑️ Teklif silindi!")
                    st.rerun()

            # Özet tablo
            st.divider()
            goster_cols = [c for c in ["id","tarih","musteri_adi","toplam_tutar","olusturan"] if c in df_tek.columns]
            df_ozet = df_tek[goster_cols].copy()
            if "toplam_tutar" in df_ozet.columns:
                df_ozet["toplam_tutar"] = df_ozet["toplam_tutar"].apply(lambda x: fmt_para(float(x or 0)))
            st.dataframe(df_ozet, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Hata: {e}")

    st.markdown("### Islem Kayitlari")
    try:
        df_islem = db_read("islem_kaydi", order_col="tarih", limit=30)
        if not df_islem.empty:
            goster = [c for c in ["tarih","musteri_adi","islem_turu","gonderim_bilgisi","olusturan"] if c in df_islem.columns]
            st.dataframe(df_islem[goster], use_container_width=True, hide_index=True)
        else:
            st.info("Henuz islem kaydi yok.")
    except Exception as e:
        st.error(f"Islem kaydi hatasi: {e}")

# ── EXCEL AKTAR ──────────────────────────────────────────────────────────────
elif aktif == "excel":
    sayfa_log("excel")
    import io

    st.markdown("## 📥 Excel ile Toplu Veri Aktarımı")

    # ── ŞABLON İNDİR ──────────────────────────────────────────────────────────
    st.markdown("### 1️⃣ Şablonu İndir")
    st.info("Önce şablonu indirin, doldurun, sonra yükleyin. Başlıkları değiştirmeyin.")

    sablon_kolonlar = [
        "firma", "yetkili", "gsm", "sabit", "email",
        "adres", "ilce", "il", "durum", "temsilci",
        "islem_asamasi", "beklenen_ciro", "gerceklesen_ciro"
    ]
    sablon_aciklama = {
        "firma": "Zorunlu - Firma adı",
        "yetkili": "Yetkili kişi adı",
        "gsm": "GSM no (05xxxxxxxxx)",
        "sabit": "Sabit telefon",
        "email": "Email adresi",
        "adres": "Açık adres",
        "ilce": "İlçe adı",
        "il": "İl adı (İstanbul, Ankara...)",
        "durum": "Aktif / Hedef / Pasif",
        "temsilci": "Satış temsilcisi adı",
        "islem_asamasi": "İlk Temas / Teklif / Sözleşme / Kazanıldı / Kaybedildi",
        "beklenen_ciro": "Sayı (örn: 50000)",
        "gerceklesen_ciro": "Sayı (örn: 35000)"
    }

    # Örnek veri ile şablon oluştur
    sablon_veri = [{
        "firma": "Örnek Firma A.Ş.",
        "yetkili": "Ahmet Yılmaz",
        "gsm": "05001234567",
        "sabit": "02121234567",
        "email": "ahmet@ornekfirma.com",
        "adres": "Atatürk Cad. No:1",
        "ilce": "Kadıköy",
        "il": "İstanbul",
        "durum": "Aktif",
        "temsilci": "Satış Temsilcisi",
        "islem_asamasi": "İlk Temas",
        "beklenen_ciro": 100000,
        "gerceklesen_ciro": 0
    }, {
        "firma": "Demo Lojistik Ltd.",
        "yetkili": "Ayşe Kaya",
        "gsm": "05329876543",
        "sabit": "",
        "email": "ayse@demolojistik.com",
        "adres": "Sanayi Sok. No:5",
        "ilce": "Çerkezköy",
        "il": "Tekirdağ",
        "durum": "Hedef",
        "temsilci": "Satış Temsilcisi",
        "islem_asamasi": "Teklif",
        "beklenen_ciro": 250000,
        "gerceklesen_ciro": 0
    }]

    df_sablon = pd.DataFrame(sablon_veri, columns=sablon_kolonlar)

    # Açıklama satırı ekle
    df_aciklama = pd.DataFrame([sablon_aciklama], columns=sablon_kolonlar)

    sablon_buf = io.BytesIO()
    with pd.ExcelWriter(sablon_buf, engine="openpyxl") as writer:
        df_sablon.to_excel(writer, sheet_name="Cari_Listesi", index=False)
        df_aciklama.to_excel(writer, sheet_name="Aciklama", index=False)
    sablon_buf.seek(0)

    st.download_button(
        "📥 Excel Şablonunu İndir",
        data=sablon_buf,
        file_name="cari_liste_sablonu.xlsx",
        mime="application/vnd.ms-excel",
        use_container_width=True,
        type="primary"
    )

    st.divider()

    # ── EXCEL YÜKLE ───────────────────────────────────────────────────────────
    st.markdown("### 2️⃣ Doldurulmuş Dosyayı Yükle")
    yuklenen = st.file_uploader(
        "Excel dosyası seçin (.xlsx veya .xls)",
        type=["xlsx","xls"],
        key="excel_yukle"
    )

    if yuklenen is not None:
        try:
            df_yukle = pd.read_excel(yuklenen, sheet_name=0)
            st.success(f"✅ Dosya okundu: {len(df_yukle)} satır, {len(df_yukle.columns)} sütun")

            # Kolon eşleştirme
            st.markdown("#### Kolon Eşleştirme")
            eksik = [k for k in sablon_kolonlar if k not in df_yukle.columns]
            if eksik:
                st.warning(f"Şu kolonlar eksik/farklı: {', '.join(eksik)}")
                st.markdown("**Kolon eşleştirmesi yapın:**")
                eslesme = {}
                dosya_kolonlari = list(df_yukle.columns)
                for sb_kol in sablon_kolonlar:
                    if sb_kol in dosya_kolonlari:
                        eslesme[sb_kol] = sb_kol
                    else:
                        secim_kol = st.selectbox(
                            f"'{sb_kol}' kolonu için:",
                            ["-- Boş bırak --"] + dosya_kolonlari,
                            key=f"esles_{sb_kol}"
                        )
                        eslesme[sb_kol] = None if secim_kol == "-- Boş bırak --" else secim_kol
                # Yeniden adlandır
                rename_map = {v: k for k, v in eslesme.items() if v and v != k}
                if rename_map:
                    df_yukle = df_yukle.rename(columns=rename_map)
            else:
                st.success("✅ Tüm kolonlar eşleşti!")
                eslesme = {k: k for k in sablon_kolonlar}

            # Önizleme
            st.markdown("#### Önizleme (ilk 10 satır)")
            preview_cols = [k for k in sablon_kolonlar if k in df_yukle.columns]
            st.dataframe(df_yukle[preview_cols].head(10), use_container_width=True, hide_index=True)

            # Doğrulama
            st.markdown("#### Doğrulama")
            hatalar = []
            uyarilar = []

            if "firma" not in df_yukle.columns:
                hatalar.append("'firma' kolonu zorunlu!")
            else:
                bos_firma = df_yukle["firma"].isna().sum() + (df_yukle["firma"] == "").sum()
                if bos_firma > 0:
                    hatalar.append(f"{bos_firma} satırda firma adı boş!")

            if "durum" in df_yukle.columns:
                gecersiz_durum = df_yukle[~df_yukle["durum"].isin(["Aktif","Hedef","Pasif",""])]["firma"].count()
                if gecersiz_durum > 0:
                    uyarilar.append(f"{gecersiz_durum} satırda durum geçersiz (Aktif/Hedef/Pasif olmalı) → 'Hedef' yapılacak")

            if "islem_asamasi" in df_yukle.columns:
                gecerli_asama = ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi",""]
                gecersiz_asama = df_yukle[~df_yukle["islem_asamasi"].isin(gecerli_asama)]["firma"].count()
                if gecersiz_asama > 0:
                    uyarilar.append(f"{gecersiz_asama} satırda işlem aşaması geçersiz → 'İlk Temas' yapılacak")

            if hatalar:
                for h in hatalar:
                    st.error(f"❌ {h}")
            if uyarilar:
                for u in uyarilar:
                    st.warning(f"⚠️ {u}")

            if not hatalar:
                st.success(f"✅ {len(df_yukle)} satır yüklenmeye hazır")

                # Mükerrer kontrol
                _df_mevcut = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL)")
                mevcut_firmalar = set(_df_mevcut["firma"].dropna().str.strip().tolist()) if not _df_mevcut.empty else set()

                mukerrer = df_yukle[df_yukle["firma"].astype(str).str.strip().isin(mevcut_firmalar)]
                if len(mukerrer) > 0:
                    st.warning(f"⚠️ {len(mukerrer)} firma zaten sistemde kayıtlı:")
                    st.dataframe(mukerrer[["firma"]].head(10), use_container_width=True, hide_index=True)
                    mukerrer_sec = st.radio(
                        "Mükerrer kayıtlar için:",
                        ["Atla (kaydetme)", "Üzerine yaz (güncelle)", "Yine de ekle (kopya oluşur)"],
                        key="mukerrer_sec"
                    )
                else:
                    mukerrer_sec = "Atla (kaydetme)"

                col_yukle_btn, _ = st.columns([2,4])
                with col_yukle_btn:
                    if st.button("🚀 Sisteme Aktar", use_container_width=True, type="primary"):
                        basarili = 0
                        atlanan = 0
                        guncellenen = 0
                        hatali = 0

                        for _, row in df_yukle.iterrows():
                            try:
                                firma_adi = str(row.get("firma","") or "").strip()
                                if not firma_adi or firma_adi.lower() == "nan":
                                    hatali += 1
                                    continue

                                def temiz(val):
                                    """NaN ve None değerleri temizle"""
                                    import math
                                    if val is None: return ""
                                    try:
                                        if math.isnan(float(val)): return ""
                                    except: pass
                                    s = str(val).strip()
                                    return "" if s.lower() == "nan" else s

                                def temiz_sayi(val):
                                    try:
                                        import math
                                        f = float(val)
                                        if math.isnan(f): return 0.0
                                        return f
                                    except: return 0.0

                                yetkili_v  = temiz(row.get("yetkili",""))
                                gsm_v      = fmt_tel(temiz(row.get("gsm","")))
                                sabit_v    = fmt_tel(temiz(row.get("sabit","")))
                                email_v    = temiz(row.get("email",""))
                                adres_v    = temiz(row.get("adres",""))
                                ilce_v     = temiz(row.get("ilce",""))
                                il_v       = temiz(row.get("il",""))
                                durum_v    = temiz(row.get("durum",""))
                                temsilci_v = temiz(row.get("temsilci",""))
                                asama_v    = temiz(row.get("islem_asamasi",""))
                                bek_ciro   = temiz_sayi(row.get("beklenen_ciro",0))
                                ger_ciro   = temiz_sayi(row.get("gerceklesen_ciro",0))

                                # Durum düzelt
                                if durum_v not in ["Aktif","Hedef","Pasif"]:
                                    durum_v = "Hedef"
                                # Aşama düzelt
                                if asama_v not in ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]:
                                    asama_v = "İlk Temas"

                                firma_mevcut = firma_adi.strip() in mevcut_firmalar

                                if firma_mevcut and mukerrer_sec == "Atla (kaydetme)":
                                    atlanan += 1
                                    continue
                                elif firma_mevcut and mukerrer_sec == "Üzerine yaz (güncelle)":
                                    db_update("cari_kartlar", {
                                        "yetkili": yetkili_v, "gsm": gsm_v, "sabit": sabit_v,
                                        "email": email_v, "adres": adres_v, "ilce": ilce_v, "il": il_v,
                                        "durum": durum_v, "temsilci": temsilci_v, "islem_asamasi": asama_v,
                                        "beklenen_ciro": bek_ciro, "gerceklesen_ciro": ger_ciro
                                    }, "firma", firma_adi)
                                    guncellenen += 1
                                else:
                                    db_insert("cari_kartlar", {
                                        "tarih": datetime.now().isoformat(),
                                        "firma": firma_adi, "yetkili": yetkili_v, "gsm": gsm_v,
                                        "sabit": sabit_v, "email": email_v, "adres": adres_v,
                                        "ilce": ilce_v, "il": il_v, "durum": durum_v,
                                        "temsilci": temsilci_v, "islem_asamasi": asama_v,
                                        "silindi": 0, "olusturan": f"Excel:{st.session_state['kullanici']}",
                                        "beklenen_ciro": bek_ciro, "gerceklesen_ciro": ger_ciro
                                    })
                                    basarili += 1

                            except Exception as row_e:
                                hatali += 1

                        st.markdown("---")
                        r1, r2, r3, r4 = st.columns(4)
                        r1.metric("✅ Eklendi", basarili)
                        r2.metric("🔄 Güncellendi", guncellenen)
                        r3.metric("⏭️ Atlandı", atlanan)
                        r4.metric("❌ Hatalı", hatali)
                        if basarili + guncellenen > 0:
                            st.success(f"Aktarım tamamlandı! {basarili} yeni kayıt eklendi, {guncellenen} güncellendi.")
                        if hatali > 0:
                            st.warning(f"{hatali} satır hata nedeniyle atlandı.")

        except Exception as e:
            st.error(f"Dosya okuma hatası: {e}")
            st.info("Lütfen geçerli bir .xlsx dosyası yükleyin ve şablon formatına uyun.")

    st.divider()

    # ── MEVCUT VERİLERİ DIŞA AKTAR ────────────────────────────────────────────
    st.markdown("### 3️⃣ Mevcut Verileri Excel'e Aktar")
    df_disari = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")

    st.markdown(f"Sistemde **{len(df_disari)}** aktif kayıt var.")

    disari_buf = io.BytesIO()
    df_disari.to_excel(disari_buf, index=False)
    disari_buf.seek(0)
    st.download_button(
        "📤 Tüm Carileri Excel'e Aktar",
        data=disari_buf,
        file_name=f"cari_listesi_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.ms-excel",
        use_container_width=True
    )

# ── MUSTERİ ANALİZ ────────────────────────────────────────────────────────────
elif aktif == "analiz":

    st.markdown("## 🧠 Müşteri Analiz")

    api_key = ""
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY","")
    except:
        pass

    if not api_key:
        st.warning("AI analiz için `.streamlit/secrets.toml` dosyasına `ANTHROPIC_API_KEY` ekleyin.")

    # ── FİRMA GİRİŞİ ──
    st.markdown("### 1️⃣ Firma Bilgisi")
    gir1, gir2 = st.columns([2,1])
    firma_manuel = gir1.text_input("Firma Adı (manuel yazın veya sistemden seçin):",
        placeholder="Örn: Oncu Kargo A.Ş.", key="analiz_firma_manuel")

    df_an = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")

    an_opts = ["-- Sistemden Seçin (opsiyonel) --"] + [f"[{int(r['id'])}] {r['firma']} ({r['durum']})" for _, r in df_an.iterrows()]
    an_secim = gir2.selectbox("Sistemdeki Müşteri:", an_opts, key="analiz_musteri")

    an_musteri = None
    if an_secim != "-- Sistemden Seçin (opsiyonel) --" and "[" in an_secim:
        an_mid = int(an_secim.split("]")[0].replace("[","").strip())
        an_rows = df_an[df_an["id"] == an_mid]
        if len(an_rows) > 0:
            an_musteri = an_rows.iloc[0]
            if not firma_manuel.strip():
                firma_manuel = str(an_musteri["firma"])

    ek_soru = st.text_area("Sormak istediğiniz soru / ek bilgi:",
        placeholder="Örn: Bu firma hangi sektörde? Rakipleri kimler? Bizimle çalışmasının faydaları neler?",
        height=80, key="analiz_soru")

    st.divider()

    col_an1, col_an2 = st.columns(2)
    with col_an1:
        sistem_analiz_btn = st.button("📊 Sistem Analizi (kayıtlı veriler)", use_container_width=True,
            disabled=(an_musteri is None))
    with col_an2:
        internet_analiz_btn = st.button(
            "🌐 İnternet + AI Araştırması" if api_key else "🌐 AI Araştırma (API Key Gerekli)",
            use_container_width=True, type="primary", disabled=not bool(api_key or False))

    # ── SİSTEM ANALİZİ ──
    if sistem_analiz_btn and an_musteri is not None:
        st.divider()
        st.markdown(f"### 📋 Sistem Analizi: **{an_musteri['firma']}**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Durum", str(an_musteri['durum']))
        m2.metric("Aşama", str(an_musteri['islem_asamasi']))
        bek = float(an_musteri['beklenen_ciro'] or 0)
        ger = float(an_musteri['gerceklesen_ciro'] or 0)
        m3.metric("Beklenen Ciro", fmt_para(bek))
        m4.metric("Gerçekleşen", fmt_para(ger), delta=fmt_para(ger-bek))

        try:
            df_islem_an = db_read("islem_kaydi", filters={"musteri_id": int(an_musteri["id"])}, order_col="tarih")
            df_tek_an = db_read("teklifler", filters={"musteri_id": int(an_musteri["id"])}, order_col="tarih")
        except:
            df_islem_an = pd.DataFrame()
            df_tek_an = pd.DataFrame()

        col_ia, col_ta = st.columns(2)
        with col_ia:
            st.markdown("**İletişim Geçmişi**")
            if not df_islem_an.empty:
                st.dataframe(df_islem_an, use_container_width=True, hide_index=True)
            else:
                st.info("İletişim kaydı yok.")
        with col_ta:
            st.markdown("**Teklif Geçmişi**")
            if not df_tek_an.empty:
                df_tek_an["toplam_tutar"] = df_tek_an["toplam_tutar"].apply(lambda x: fmt_para(float(x)))
                st.dataframe(df_tek_an, use_container_width=True, hide_index=True)
            else:
                st.info("Teklif kaydı yok.")

    # ── İNTERNET + AI ANALİZİ ──
    if internet_analiz_btn:
        if not firma_manuel.strip():
            st.warning("Lütfen firma adı girin!")
        elif not api_key:
            st.warning("API Key gerekli!")
        else:
            firma_adi = firma_manuel.strip()
            sistem_bilgi = ""
            if an_musteri is not None:
                bek = float(an_musteri['beklenen_ciro'] or 0)
                ger = float(an_musteri['gerceklesen_ciro'] or 0)
                sistem_bilgi = (
                    f"\nSistemdeki kayıt bilgileri:\n"
                    f"- İl: {an_musteri['il']}\n"
                    f"- Durum: {an_musteri['durum']}\n"
                    f"- Aşama: {an_musteri['islem_asamasi']}\n"
                    f"- Beklenen Ciro: ₺{bek:,.0f}\n"
                    f"- Gerçekleşen Ciro: ₺{ger:,.0f}\n"
                )

            with st.spinner(f"'{firma_adi}' internette araştırılıyor..."):
                try:
                    import requests as _req
                    prompt = (
                        f"Türkiye'de faaliyet gösteren '{firma_adi}' firmasını araştır.\n"
                        f"{sistem_bilgi}"
                        f"{f'Ek soru: {ek_soru}' if ek_soru else ''}\n\n"
                        f"Şunları bul ve raporla:\n"
                        f"1. Firma hakkında genel bilgi (sektör, kuruluş, faaliyet alanı)\n"
                        f"2. Web sitesi ve iletişim bilgileri (varsa)\n"
                        f"3. Kargo/lojistik ihtiyaçları olabilir mi? Hangi ürünleri taşıyabilirler?\n"
                        f"4. Bizim için satış fırsatı var mı? Neden?\n"
                        f"5. Rakip kargo firmaları kullanıyor mu?\n"
                        f"6. Önerilen yaklaşım ve strateji\n"
                        f"7. Önerilen cari kart bilgileri: il, ilçe, durum, islem_asamasi, tahmini beklenen_ciro\n\n"
                        f"Son olarak JSON formatında cari kart önerisi ver:\n"
                        f"```json\n"
                        f"{{\"firma\": \"...\", \"il\": \"...\", \"ilce\": \"...\", \"durum\": \"Hedef\", \"islem_asamasi\": \"İlk Temas\", \"beklenen_ciro\": 0, \"yetkili\": \"\", \"gsm\": \"\", \"email\": \"\", \"adres\": \"\"}}\n"
                        f"```\n"
                        f"Türkçe yaz."
                    )

                    resp = _req.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"Content-Type":"application/json",
                                 "x-api-key":api_key,
                                 "anthropic-version":"2023-06-01"},
                        json={
                            "model":"claude-sonnet-4-20250514",
                            "max_tokens":2000,
                            "tools":[{"type":"web_search_20250305","name":"web_search"}],
                            "messages":[{"role":"user","content":prompt}]
                        },
                        timeout=90
                    )
                    data = resp.json()
                    ai_text = " ".join([b["text"] for b in data.get("content",[]) if b.get("type")=="text"])

                    st.session_state["analiz_sonuc"] = ai_text
                    st.session_state["analiz_firma"] = firma_adi

                    # JSON önerisi parse et
                    json_match = _re.search(r'```json\s*(\{.*?\})\s*```', ai_text, _re.DOTALL)
                    if json_match:
                        try:
                            oneri = _aj.loads(json_match.group(1))
                            st.session_state["analiz_oneri"] = oneri
                        except:
                            st.session_state["analiz_oneri"] = None
                    else:
                        st.session_state["analiz_oneri"] = None

                except Exception as e:
                    st.error(f"AI araştırma hatası: {e}")

    # ── SONUÇ GÖSTER ──
    if st.session_state.get("analiz_sonuc"):
        st.divider()
        st.markdown(f"### 🌐 AI Araştırma Sonucu: **{st.session_state.get('analiz_firma','')}**")
        st.markdown(st.session_state["analiz_sonuc"])

        # Cari listeye ekleme
        oneri = st.session_state.get("analiz_oneri")
        if oneri:
            st.divider()
            st.markdown("### ➕ Cari Listeye Ekle")
            st.info("AI'nın önerdiği bilgiler aşağıya dolduruldu. Düzenleyip kaydedebilirsiniz.")

            ek1, ek2, ek3 = st.columns(3)
            ek_firma    = ek1.text_input("Firma Adı*", value=oneri.get("firma", firma_manuel), key="ek_firma")
            ek_yetkili  = ek1.text_input("Yetkili", value=oneri.get("yetkili",""), key="ek_yetkili")
            ek_gsm      = ek2.text_input("GSM", value=oneri.get("gsm",""), key="ek_gsm")
            ek_email    = ek2.text_input("Email", value=oneri.get("email",""), key="ek_email")
            ek_il       = ek3.text_input("İl", value=oneri.get("il",""), key="ek_il")
            ek_ilce     = ek3.text_input("İlçe", value=oneri.get("ilce",""), key="ek_ilce")
            ek_adres    = ek1.text_input("Adres", value=oneri.get("adres",""), key="ek_adres")

            durum_opts  = ["Aktif","Hedef","Pasif"]
            durum_def   = oneri.get("durum","Hedef")
            durum_idx   = durum_opts.index(durum_def) if durum_def in durum_opts else 1
            ek_durum    = ek2.selectbox("Durum", durum_opts, index=durum_idx, key="ek_durum")

            asama_opts  = ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]
            asama_def   = oneri.get("islem_asamasi","İlk Temas")
            asama_idx   = asama_opts.index(asama_def) if asama_def in asama_opts else 0
            ek_asama    = ek3.selectbox("Aşama", asama_opts, index=asama_idx, key="ek_asama")

            ek_ciro     = ek1.number_input("Beklenen Ciro (₺)", min_value=0.0, step=1000.0,
                value=float(oneri.get("beklenen_ciro",0) or 0), key="ek_ciro")
            ek_temsilci = ek2.text_input("Temsilci", value=st.session_state.get("kullanici",""), key="ek_temsilci")

            if st.button("✅ Cari Listeye Ekle (Hedef)", use_container_width=True, type="primary"):
                if not ek_firma.strip():
                    st.warning("Firma adı boş olamaz!")
                else:
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO cari_kartlar (tarih,firma,yetkili,gsm,sabit,email,adres,ilce,il,durum,temsilci,islem_asamasi,silindi,olusturan,beklenen_ciro,gerceklesen_ciro) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         ek_firma, ek_yetkili, ek_gsm, "", ek_email, ek_adres, ek_ilce, ek_il,
                         ek_durum, ek_temsilci, ek_asama, 0,
                         f"AI-Analiz:{st.session_state['kullanici']}", ek_ciro, 0.0))
                    conn.commit(); conn.close()
                    st.success(f"✅ '{ek_firma}' cari listeye eklendi!")
                    st.session_state["analiz_sonuc"] = None
                    st.session_state["analiz_oneri"] = None
                    st.session_state["aktif_tab"] = "liste"
                    st.rerun()

        if st.button("🗑️ Sonucu Temizle", key="analiz_temizle"):
            st.session_state["analiz_sonuc"] = None
            st.session_state["analiz_oneri"] = None
            st.rerun()

# ── KOD DEPOSU (sadece admin) ─────────────────────────────────────────────────
elif aktif == "koddepo":
    sayfa_log("koddepo")
    if st.session_state.get("rol") != "admin":
        st.error("Bu sayfa sadece adminlere özeldir.")
        st.stop()

    st.markdown("## 💾 Kod Deposu & Sürüm Arşivi")
    st.info("Bu bölüm sadece admin kullanıcılara görünür. Sistemin güncel kodunu ve notlarını buraya kaydedin.")

    # Kod deposu tablosu
    conn = get_conn()
    conn.execute('''CREATE TABLE IF NOT EXISTS kod_deposu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        surum TEXT, aciklama TEXT, kod TEXT, olusturan TEXT)''')
    conn.commit()
    conn.close()

    # Yeni sürüm ekle
    with st.expander("➕ Yeni Sürüm Kaydet", expanded=False):
        kd1, kd2 = st.columns(2)
        surum_no = kd1.text_input("Sürüm No:", placeholder="v2.1, v2.2...", key="kd_surum")
        kd_aciklama = kd2.text_area("Açıklama (ne değişti?):", height=80, key="kd_aciklama",
            placeholder="Örn: Teklif modülüne WhatsApp entegrasyonu eklendi, Excel aktarım düzeltildi...")
        kd_kod = st.text_area("Kod (main.py içeriği):", height=300, key="kd_kod",
            placeholder="main.py dosyasının içeriğini buraya yapıştırın...")

        if st.button("💾 Sürümü Kaydet", use_container_width=True, type="primary"):
            if not surum_no or not kd_aciklama:
                st.warning("Sürüm no ve açıklama zorunlu!")
            else:
                db_insert("kod_deposu", {"surum": surum_no, "aciklama": kd_aciklama, "kod": kd_kod, "olusturan": st.session_state["kullanici"]})
                st.success(f"✅ {surum_no} sürümü kaydedildi!")
                st.rerun()

    # Mevcut koddan otomatik kaydet
    with st.expander("⚡ Mevcut main.py'yi Otomatik Kaydet"):
        auto_surum = st.text_input("Sürüm No:", key="auto_surum", placeholder="v2.3")
        auto_aciklama = st.text_area("Bu sürümde neler var?", height=100, key="auto_aciklama",
            value="Yeni Kart düzenleme, Teklif modülü, Excel aktarım, Raporlama, Müşteri Analiz, Kod Deposu, Sidebar destek paneli, Footer, WhatsApp/Email entegrasyonu")
        if st.button("⚡ main.py'yi Oku ve Kaydet", use_container_width=True):
            if not auto_surum:
                st.warning("Sürüm no girin!")
            else:
                try:
                    with open("main.py", "r", encoding="utf-8") as mf:
                        mevcut_kod = mf.read()
                    db_insert("kod_deposu", {"surum": auto_surum, "aciklama": auto_aciklama, "kod": mevcut_kod, "olusturan": st.session_state["kullanici"]})
                    st.success(f"✅ {auto_surum} — {len(mevcut_kod):,} karakter kaydedildi!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Hata: {e}")

    st.divider()

    # Sürüm listesi
    try:
        df_depo = db_read("kod_deposu", extra_sql="ORDER BY tarih DESC")
        if not df_depo.empty:
            st.markdown(f"### 📦 Kayıtlı Sürümler ({len(df_depo)} adet)")
            df_depo_goster = df_depo[["id","tarih","surum","aciklama","olusturan"]].copy()
            df_depo_goster.columns = ["ID","Tarih","Sürüm","Açıklama","Kaydeden"]
            st.dataframe(df_depo_goster, use_container_width=True, hide_index=True)

            # Sürüm indir
            st.markdown("#### 📥 Sürüm İndir")
            indir_id = st.number_input("İndirilecek Sürüm ID:", min_value=1, step=1, key="indir_surum_id")
            if st.button("Kodu İndir", use_container_width=True):
                conn2 = get_conn()
                row = conn2.execute("SELECT surum, kod, aciklama, tarih FROM kod_deposu WHERE id=?", (indir_id,)).fetchone()
                conn2.close()
                if row and row[1]:
                    st.download_button(
                        f"⬇️ {row[0]} — main.py İndir",
                        data=row[1].encode("utf-8"),
                        file_name=f"main_{row[0].replace('.','_')}.py",
                        mime="text/plain",
                        use_container_width=True
                    )
                    st.markdown(f"**Açıklama:** {row[2]}")
                    st.markdown(f"**Tarih:** {row[3]}")
                    st.code(row[1][:2000] + ("..." if len(row[1])>2000 else ""), language="python")
                else:
                    st.error("Bu ID bulunamadı veya kod boş.")

            # Sürüm sil
            with st.expander("🗑️ Sürüm Sil"):
                sil_id = st.number_input("Silinecek ID:", min_value=1, step=1, key="sil_surum_id")
                if st.button("Sil", type="primary"):
                    conn3 = get_conn()
                    conn3.execute("DELETE FROM kod_deposu WHERE id=?", (sil_id,))
                    conn3.commit(); conn3.close()
                    st.success(f"ID {sil_id} silindi.")
                    st.rerun()
        else:
            st.info("Henüz kayıtlı sürüm yok. Yukarıdan ilk sürümü kaydedin.")
    except Exception as e:
        st.error(f"Kod deposu hatası: {e}")

# ── WHATSAPP ──────────────────────────────────────────────────────────────────
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

    with st.expander("👤 Satış Temsilcisi Kartları", expanded=False):
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

    st.divider()
    ben = st.session_state.get("kullanici","")

    tab_rehber1, tab_rehber2, tab_rehber3, tab_rehber4, tab_rehber5 = st.tabs([
        "📋 Kişi Listesi", "➕ Kişi Ekle", "📥 Toplu İçe Aktar",
        "📝 Kayıtlı Şablonlar", "📊 Mesaj Raporu"
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


elif aktif == "randevu":
    sayfa_log("randevu")
    import io as _rio
    st.markdown("## 📅 Randevular & Ziyaret Planı")

    # ── HATIRLATMALAR (sayfa açılınca otomatik göster) ────────────────────────
    df_rand_all = db_read("randevular", extra_sql="ORDER BY randevu_tarihi ASC, randevu_saati ASC")

    if not df_rand_all.empty and "randevu_tarihi" in df_rand_all.columns:
        bugun_str = datetime.now().strftime("%Y-%m-%d")

        # Yaklaşan (bugün ve sonraki 3 gün, sonucu bitmemiş)
        yaklasan = df_rand_all[
            (df_rand_all["randevu_tarihi"] >= bugun_str) &
            (df_rand_all["randevu_tarihi"] <= datetime.now().strftime("%Y-%m-") + str(datetime.now().day + 3).zfill(2)) &
            (~df_rand_all["sonuc"].isin(["Bitti","İptal"]))
        ] if "sonuc" in df_rand_all.columns else pd.DataFrame()

        # Geçmiş açık (tarihi geçmiş ama sonuç girilmemiş)
        gecmis_acik = df_rand_all[
            (df_rand_all["randevu_tarihi"] < bugun_str) &
            (~df_rand_all["sonuc"].isin(["Bitti","İptal","Gidilmedi"]))
        ] if "sonuc" in df_rand_all.columns else pd.DataFrame()

        if len(yaklasan) > 0 or len(gecmis_acik) > 0:
            with st.expander(f"⚠️ Hatırlatmalar ({len(yaklasan)} yaklaşan, {len(gecmis_acik)} açık)", expanded=True):
                if len(yaklasan) > 0:
                    st.markdown("**🔔 Yaklaşan Randevular:**")
                    for _, row in yaklasan.iterrows():
                        hc1, hc2, hc3, hc4 = st.columns([2,2,2,1])
                        hc1.markdown(f"📅 **{row.get('randevu_tarihi','')} {row.get('randevu_saati','')}**")
                        hc2.markdown(f"🏢 {row.get('musteri_adi','')}")
                        hc3.markdown(f"👤 {row.get('temsilci','')} — {row.get('bolge','')}")
                        # WA hatırlatma
                        tem_tel_h = str(row.get("temsilci_tel","") or "")
                        if tem_tel_h:
                            ht = re.sub(r"[\s\-\(\)+]","", tem_tel_h)
                            if ht.startswith("0"): ht = "90" + ht[1:]
                            msg_h = f"⏰ RANDEVU HATIRLATMA\nMüşteri: {row.get('musteri_adi','')}\nTarih: {row.get('randevu_tarihi','')} {row.get('randevu_saati','')}\nBölge: {row.get('bolge','')}"
                            hc4.link_button("📱 WA", f"https://wa.me/{ht}?text={msg_h.replace(' ','%20').replace(chr(10),'%0A')}", use_container_width=True)

                if len(gecmis_acik) > 0:
                    st.markdown("**⚠️ Sonuç Girilmemiş Geçmiş Randevular:**")
                    for _, row in gecmis_acik.iterrows():
                        gc1, gc2, gc3 = st.columns([2,2,2])
                        gc1.markdown(f"📅 {row.get('randevu_tarihi','')} — _{row.get('gorev','')}_")
                        gc2.markdown(f"🏢 {row.get('musteri_adi','')}")
                        gc3.warning(f"Sonuç bekleniyor! ID: {row.get('id','')}")

    r_tab1, r_tab2, r_tab3, r_tab4 = st.tabs(["📋 Randevu Listesi", "➕ Yeni Randevu", "✏️ Düzenle / Sil", "📊 Özet Rapor"])

    with r_tab1:
        rf1, rf2, rf3 = st.columns(3)
        filtre_tem_r = rf1.text_input("Temsilci filtrele:", key="rand_filtre_tem")
        filtre_sonuc = rf2.selectbox("Sonuç:", ["Tümü","Bitti","Devam Ediyor","Gidilmedi","İptal","—"], key="rand_sonuc")
        filtre_tarih = rf3.date_input("Başlangıç tarihi:", value=datetime.now().date(), key="rand_bas")

        df_rand = df_rand_all.copy() if not df_rand_all.empty else pd.DataFrame()

        if not df_rand.empty:
            if filtre_tem_r:
                df_rand = df_rand[df_rand["temsilci"].str.contains(filtre_tem_r, case=False, na=False)]
            if filtre_sonuc != "Tümü":
                df_rand = df_rand[df_rand["sonuc"] == filtre_sonuc]

        if df_rand.empty:
            st.info("Randevu bulunamadı.")
        else:
            rm1, rm2, rm3, rm4 = st.columns(4)
            rm1.metric("Toplam", len(df_rand))
            rm2.metric("✅ Bitti", len(df_rand[df_rand["sonuc"]=="Bitti"]) if "sonuc" in df_rand.columns else 0)
            rm3.metric("🔄 Devam", len(df_rand[df_rand["sonuc"]=="Devam Ediyor"]) if "sonuc" in df_rand.columns else 0)
            rm4.metric("❌ Gidilmedi", len(df_rand[df_rand["sonuc"]=="Gidilmedi"]) if "sonuc" in df_rand.columns else 0)

            g_cols = [c for c in ["id","randevu_tarihi","randevu_saati","musteri_adi","bolge","gorev","takip","adet","sonuc","temsilci","aciklama"] if c in df_rand.columns]
            st.dataframe(df_rand[g_cols], use_container_width=True, hide_index=True)

            # WA uyarı linkleri + yaklaşan otomatik hazır
            st.markdown("#### 📱 WhatsApp Uyarı Gönder")

            # Yaklaşan randevuları vurgula
            bugun_str = datetime.now().strftime("%Y-%m-%d")
            yarin_str = (datetime.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

            for _, row in df_rand.head(20).iterrows():
                musteri_r  = str(row.get("musteri_adi",""))
                tarih_r    = str(row.get("randevu_tarihi",""))
                saat_r     = str(row.get("randevu_saati",""))
                bolge_r    = str(row.get("bolge",""))
                gorev_r    = str(row.get("gorev",""))
                temsilci_r = str(row.get("temsilci",""))
                tem_tel_r  = fmt_tel(str(row.get("temsilci_tel","") or ""))

                # Yaklaşan uyarısı
                yaklasan = tarih_r in [bugun_str, yarin_str]
                etiket = f"{'🔴 BUGÜN' if tarih_r==bugun_str else '🟡 YARIN' if tarih_r==yarin_str else tarih_r} — {musteri_r} | {temsilci_r}"

                with st.container():
                    wc1, wc2, wc3, wc4 = st.columns([3, 1.5, 1.5, 1])
                    wc1.markdown(f"{'**' if yaklasan else ''}{etiket}{'**' if yaklasan else ''}")
                    wc2.caption(f"📍 {bolge_r} | {gorev_r}")

                    # Telefon var mı kontrol
                    if tem_tel_r:
                        t_wa = re.sub(r'[^\d]','',tem_tel_r)
                        if t_wa.startswith('0') and len(t_wa)==11: t_wa = '90'+t_wa[1:]
                        elif len(t_wa)==10: t_wa = '90'+t_wa
                        msg_wa = f"📅 RANDEVU HATIRLATMA\nMüşteri: {musteri_r}\nTarih: {tarih_r} {saat_r}\nBölge: {bolge_r}\nGörev: {gorev_r}\nİyi çalışmalar!"
                        wa_link = f"https://wa.me/{t_wa}?text={msg_wa.replace(' ','%20').replace(chr(10),'%0A')}"
                        wc3.link_button("📱 WA Gönder", wa_link, use_container_width=True, type="primary" if yaklasan else "secondary")
                    else:
                        # Manuel tel girişi
                        manuel_t = wc3.text_input("Tel:", placeholder="05xx", key=f"wa_tel_{row.get('id','')}", label_visibility="collapsed")
                        if manuel_t and wc4.button("📱", key=f"wa_gnd_{row.get('id','')}"):
                            t_m = re.sub(r'[^\d]','',manuel_t)
                            if t_m.startswith('0') and len(t_m)==11: t_m = '90'+t_m[1:]
                            elif len(t_m)==10: t_m = '90'+t_m
                            msg_m = f"📅 RANDEVU\nMüşteri: {musteri_r}\nTarih: {tarih_r} {saat_r}\nGörev: {gorev_r}"
                            st.markdown(f"[📱 WA Aç](https://wa.me/{t_m}?text={msg_m.replace(' ','%20').replace(chr(10),'%0A')})")
                        elif not manuel_t:
                            wc3.caption("📞 Tel yok")

            buf_r = _rio.BytesIO()
            df_rand.to_excel(buf_r, index=False)
            buf_r.seek(0)
            st.download_button("📥 Excel İndir", data=buf_r,
                file_name=f"randevular_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel", use_container_width=True)

    with r_tab2:
        df_mrand = db_read("cari_kartlar", extra_sql="WHERE (silindi=0 OR silindi='0' OR silindi IS NULL) ORDER BY firma")
        musteri_rand_opts = ["-- Müşteri Seçin --"] + [f"[{int(r['id'])}] {r['firma']} ({r['durum']})" for _, r in df_mrand.iterrows()]

        # Cari listeden geldiyse otomatik seç
        _onsel_id = st.session_state.pop("rand_musteri_onsel", None)
        _onsel_idx = 0
        if _onsel_id:
            for i, opt in enumerate(musteri_rand_opts):
                if f"[{_onsel_id}]" in opt:
                    _onsel_idx = i
                    break

        with st.form("randevu_form"):
            rand_musteri = st.selectbox("Müşteri*:", musteri_rand_opts, index=_onsel_idx, key="rand_musteri")
            rc1, rc2, rc3 = st.columns(3)
            rand_tarih = rc1.date_input("Tarih*:", value=datetime.now().date(), key="rand_tarih")
            rand_saat  = rc2.time_input("Saat*:", key="rand_saat")
            rand_bolge = rc3.text_input("Bölge:", placeholder="İstanbul Beykoz")

            rc4, rc5, rc6 = st.columns(3)
            rand_gorev = rc4.selectbox("Görev*:", ["Ziyaret","Arama","Değerlendirme","Kazanıldı","Kaybedildi","Devam Ediyor","Whatsapp Mesaj","E-mail","Yeni Tarihe Ertele"])
            rand_takip = rc5.selectbox("Takip:", ["Gidildi","Gidilmedi","Devam Ediyor","Ertelendi"])
            rand_adet  = rc6.number_input("Adet:", min_value=0, step=1, key="rand_adet")

            rand_temsilci = st.text_input("Satış Temsilcisi*:", placeholder="Temsilci adı yazın", key="rand_tem")
            rand_tem_tel  = st.text_input("Temsilci WhatsApp No:", placeholder="05xxxxxxxxx", key="rand_tem_tel")
            rand_aciklama = st.text_area("Açıklama / Not:", height=80, key="rand_aciklama")
            rand_sonuc    = st.selectbox("Sonuç:", ["—","Bitti","Devam Ediyor","Gidilmedi","İptal"])

            if st.form_submit_button("💾 Randevu Kaydet", use_container_width=True, type="primary"):
                if rand_musteri == "-- Müşteri Seçin --":
                    st.warning("Müşteri seçin!")
                else:
                    musteri_id = 0; musteri_adi = rand_musteri
                    if "[" in rand_musteri:
                        try:
                            musteri_id = int(rand_musteri.split("]")[0].replace("[","").strip())
                            musteri_adi = rand_musteri.split("] ")[1].split(" (")[0]
                        except: pass

                    # Mükerrer randevu kontrolü
                    if musteri_id > 0:
                        df_muk = db_read("randevular", filters={"musteri_id": musteri_id})
                        if not df_muk.empty and "sonuc" in df_muk.columns:
                            aktif_muk = df_muk[~df_muk["sonuc"].isin(["Bitti","İptal","Gidilmedi"])]
                            if not aktif_muk.empty:
                                st.error(f"⚠️ Bu müşterinin zaten aktif bir randevusu var! "
                                        f"({aktif_muk.iloc[0].get('randevu_tarihi','')} — {aktif_muk.iloc[0].get('gorev','')}). "
                                        f"Önce mevcut randevuyu tamamlayın veya iptal edin.")
                                st.stop()

                    kullanici_log_kaydet("RANDEVU_EKLE", "randevu", f"Müşteri: {musteri_adi}, Tarih: {rand_tarih}")
                    db_insert("randevular", {
                        "randevu_tarihi": str(rand_tarih),
                        "randevu_saati": str(rand_saat),
                        "musteri_id": musteri_id, "musteri_adi": musteri_adi,
                        "bolge": rand_bolge, "gorev": rand_gorev, "takip": rand_takip,
                        "adet": int(rand_adet), "aciklama": rand_aciklama,
                        "sonuc": rand_sonuc if rand_sonuc != "—" else "",
                        "temsilci": rand_temsilci,
                        "olusturan": st.session_state["kullanici"]
                    })
                    try: db_read.clear()
                    except: pass
                    st.success("✅ Randevu kaydedildi!")

                    if rand_tem_tel.strip():
                        twt2 = re.sub(r"[\s\-\(\)+]","", rand_tem_tel.strip())
                        if twt2.startswith("0"): twt2 = "90" + twt2[1:]
                        elif len(twt2)==10: twt2 = "90" + twt2
                        msg2 = f"🗓️ YENİ RANDEVU\nMüşteri: {musteri_adi}\nTarih: {rand_tarih} {rand_saat}\nBölge: {rand_bolge}\nGörev: {rand_gorev}\nİyi çalışmalar!"
                        wa2 = f"https://wa.me/{twt2}?text={msg2.replace(' ','%20').replace(chr(10),'%0A')}"
                        st.link_button("📱 Temsilciye WA Uyarısı Gönder", wa2, use_container_width=True, type="primary")
                    st.rerun()

    with r_tab3:
        st.markdown("### ✏️ Randevu Düzenle / Sil")
        if df_rand_all.empty:
            st.info("Randevu yok.")
        else:
            duzenle_id = st.number_input("Düzenlenecek Randevu ID:", min_value=1, step=1, key="rand_duzenle_id")
            df_sec = df_rand_all[df_rand_all["id"] == duzenle_id] if duzenle_id else pd.DataFrame()

            if st.button("🔍 Getir", key="rand_getir") and not df_sec.empty:
                st.session_state["rand_duzenle_row"] = df_sec.iloc[0].to_dict()

            if st.session_state.get("rand_duzenle_row"):
                row_d = st.session_state["rand_duzenle_row"]
                st.success(f"ID {row_d.get('id')} — {row_d.get('musteri_adi')} — {row_d.get('randevu_tarihi')}")

                with st.form("rand_duzenle_form"):
                    dd1, dd2, dd3 = st.columns(3)
                    d_tarih    = dd1.text_input("Tarih:", value=str(row_d.get("randevu_tarihi","")))
                    d_saat     = dd2.text_input("Saat:", value=str(row_d.get("randevu_saati","")))
                    d_bolge    = dd3.text_input("Bölge:", value=str(row_d.get("bolge","")))
                    dd4, dd5, dd6 = st.columns(3)
                    d_gorev    = dd4.text_input("Görev:", value=str(row_d.get("gorev","")))
                    d_takip    = dd5.text_input("Takip:", value=str(row_d.get("takip","")))
                    d_adet     = dd6.number_input("Adet:", min_value=0, value=int(row_d.get("adet",0) or 0))
                    d_temsilci = dd1.text_input("Temsilci:", value=str(row_d.get("temsilci","")))
                    d_sonuc_opts = ["—","Bitti","Devam Ediyor","Gidilmedi","İptal"]
                    d_sonuc_idx  = d_sonuc_opts.index(row_d.get("sonuc","—")) if row_d.get("sonuc") in d_sonuc_opts else 0
                    d_sonuc    = dd2.selectbox("Sonuç:", d_sonuc_opts, index=d_sonuc_idx)
                    d_aciklama = st.text_area("Açıklama:", value=str(row_d.get("aciklama","")), height=80)

                    col_gunc, col_sil = st.columns(2)
                    gunc_btn = col_gunc.form_submit_button("💾 Güncelle", use_container_width=True, type="primary")
                    sil_btn  = col_sil.form_submit_button("🗑️ Sil", use_container_width=True)

                    if gunc_btn:
                        db_update("randevular", {
                            "randevu_tarihi": d_tarih, "randevu_saati": d_saat,
                            "bolge": d_bolge, "gorev": d_gorev, "takip": d_takip,
                            "adet": d_adet, "temsilci": d_temsilci,
                            "sonuc": d_sonuc if d_sonuc != "—" else "", "aciklama": d_aciklama
                        }, "id", int(row_d["id"]))
                        try: db_read.clear()
                        except: pass
                        st.success("✅ Randevu güncellendi!")
                        st.session_state.pop("rand_duzenle_row", None)
                        st.rerun()

                    if sil_btn:
                        sb = get_sb_client()
                        if sb:
                            sb.table("randevular").delete().eq("id", int(row_d["id"])).execute()
                        st.success("🗑️ Silindi!")
                        st.session_state.pop("rand_duzenle_row", None)
                        st.rerun()

    with r_tab4:
        if df_rand_all.empty:
            st.info("Randevu yok.")
        else:
            st.markdown("#### 👤 Temsilci Bazlı")
            if "temsilci" in df_rand_all.columns:
                t_oz = df_rand_all.groupby("temsilci").agg(
                    Toplam=("id","count"),
                    Bitti=("sonuc", lambda x: (x=="Bitti").sum()),
                    Devam=("sonuc", lambda x: (x=="Devam Ediyor").sum()),
                    Gidilmedi=("sonuc", lambda x: (x=="Gidilmedi").sum()),
                ).reset_index()
                st.dataframe(t_oz, use_container_width=True, hide_index=True)

            st.markdown("#### 📋 Görev Dağılımı")
            if "gorev" in df_rand_all.columns:
                g_oz = df_rand_all.groupby("gorev").agg(Adet=("id","count")).reset_index().sort_values("Adet",ascending=False)
                st.dataframe(g_oz, use_container_width=True, hide_index=True)

            st.markdown("#### 📅 Bu Hafta")
            bugun2 = datetime.now().strftime("%Y-%m-%d")
            bu_hafta = df_rand_all[df_rand_all["randevu_tarihi"] >= bugun2] if "randevu_tarihi" in df_rand_all.columns else pd.DataFrame()
            if not bu_hafta.empty:
                bh_cols = [c for c in ["randevu_tarihi","randevu_saati","musteri_adi","bolge","gorev","temsilci","sonuc"] if c in bu_hafta.columns]
                st.dataframe(bu_hafta[bh_cols], use_container_width=True, hide_index=True)
            else:
                st.info("Bu hafta randevu yok.")

# ── SİSTEM MESAJLAŞMA ────────────────────────────────────────────────────────
elif aktif == "mesajlar":
    sayfa_log("mesajlar")
    st.markdown("## 💬 Sistem İçi Mesajlaşma")

    ben = st.session_state.get("kullanici","")

    # Tüm kullanıcı listesi
    try:
        df_kullar = db_read("kullanicilar", extra_sql="")
        kullar_liste = [r["kullanici_adi"] for _, r in df_kullar.iterrows() if r["kullanici_adi"] != ben]
    except:
        kullar_liste = []

    # Aktif kullanıcılar
    try:
        df_aktif2 = db_read("aktif_kullanicilar", extra_sql="")
        if not df_aktif2.empty and "son_gorulme" in df_aktif2.columns:
            df_aktif2["son_gorulme"] = pd.to_datetime(df_aktif2["son_gorulme"], errors="coerce")
            aktif_isimler = set(df_aktif2[
                df_aktif2["son_gorulme"] > pd.Timestamp.now() - pd.Timedelta(minutes=5)
            ]["kullanici"].tolist())
        else:
            aktif_isimler = set()
    except:
        aktif_isimler = set()

    msg_col1, msg_col2 = st.columns([1, 2])

    with msg_col1:
        st.markdown("### 👥 Kullanıcılar")
        if not kullar_liste:
            st.info("Başka kullanıcı yok.")
        for kul in kullar_liste:
            # Okunmamış sayısı
            try:
                df_ok = db_read("mesajlar", extra_sql=f"WHERE alici='{ben}' AND gonderen='{kul}' AND okundu=0")
                ok_say = len(df_ok)
            except:
                ok_say = 0

            aktif_dot = "🟢" if kul in aktif_isimler else "⚫"
            etiket = f"{aktif_dot} {kul}"
            if ok_say > 0:
                etiket += f" 🔴{ok_say}"

            if st.button(etiket, key=f"msg_kul_{kul}", use_container_width=True):
                st.session_state["msg_alici"] = kul
                # Okundu olarak işaretle
                try:
                    sb_m = get_sb_client()
                    if sb_m:
                        sb_m.table("mesajlar").update({"okundu": 1}).eq("alici", ben).eq("gonderen", kul).execute()
                except: pass
                st.rerun()

    with msg_col2:
        alici = st.session_state.get("msg_alici", "")
        if not alici:
            st.info("Sol taraftan bir kullanıcı seçin.")
        else:
            aktif_dot2 = "🟢 Çevrimiçi" if alici in aktif_isimler else "⚫ Çevrimdışı"
            st.markdown(f"### 💬 {alici} — {aktif_dot2}")

            # Mesaj geçmişi
            try:
                df_mesajlar = db_read("mesajlar", extra_sql=f"WHERE (gonderen='{ben}' AND alici='{alici}') OR (gonderen='{alici}' AND alici='{ben}') ORDER BY tarih ASC")
            except:
                df_mesajlar = pd.DataFrame()

            # Mesaj baloncukları
            mesaj_html = "<div style='height:350px;overflow-y:auto;border:1px solid #eee;border-radius:8px;padding:10px;background:#fafafa;'>"
            if df_mesajlar.empty:
                mesaj_html += "<p style='color:#aaa;text-align:center;margin-top:50px'>Henüz mesaj yok</p>"
            else:
                for _, msg in df_mesajlar.iterrows():
                    gond = str(msg.get("gonderen",""))
                    metin = str(msg.get("mesaj",""))
                    zaman = str(msg.get("tarih",""))[:16]
                    if gond == ben:
                        mesaj_html += f"<div style='text-align:right;margin:5px 0'><span style='background:#1f6feb;color:white;padding:8px 12px;border-radius:16px 16px 4px 16px;display:inline-block;max-width:80%'>{metin}</span><br><small style='color:#aaa'>{zaman}</small></div>"
                    else:
                        mesaj_html += f"<div style='text-align:left;margin:5px 0'><span style='background:#e9ecef;color:#333;padding:8px 12px;border-radius:16px 16px 16px 4px;display:inline-block;max-width:80%'>{metin}</span><br><small style='color:#aaa'>{zaman}</small></div>"
            mesaj_html += "</div>"
            st.markdown(mesaj_html, unsafe_allow_html=True)

            # Mesaj gönder
            with st.form("mesaj_gonder_form", clear_on_submit=True):
                yeni_mesaj = st.text_input("Mesajınız:", placeholder="Mesaj yazın...", key="yeni_mesaj_input")
                gc1, gc2 = st.columns([4,1])
                if gc2.form_submit_button("📤 Gönder", use_container_width=True, type="primary"):
                    if yeni_mesaj.strip():
                        db_insert("mesajlar", {
                            "gonderen": ben,
                            "alici": alici,
                            "mesaj": yeni_mesaj.strip(),
                            "okundu": 0
                        })
                        st.rerun()

            if st.button("🔄 Yenile", use_container_width=True):
                st.rerun()

# ── ADMİN RAPOR TASARIM ──────────────────────────────────────────────────────
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
    "MWCRMPRO v6.3 &nbsp;|&nbsp; "
    "<a href='tel:05400344228' style='color:#888;text-decoration:none;'>📞 5400344228</a>"
    " &nbsp;|&nbsp; "
    "<a href='mailto:osnenufu@gmail.com' style='color:#888;text-decoration:none;'>✉️ osnenufu@gmail.com</a>"
    " &nbsp;|&nbsp; "
    "<a href='https://wa.me/905400344228' target='_blank' style='color:#25D366;text-decoration:none;'>💬 WhatsApp</a>"
    "</div>",
    unsafe_allow_html=True
)