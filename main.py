import streamlit as st
import sqlite3
import pandas as pd
import shutil
import os
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

def get_sb():
    return get_sb_client()

def get_supabase():
    return get_sb_client()

@st.cache_data(ttl=60)
def get_cari_listesi():
    """60 sn cache'li cari listesi"""
    sb = get_sb()
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
    """Önbellekli okuma — 30 saniye cache"""
    sb = get_sb()
    if sb:
        try:
            q = sb.table(table).select("*")
            res = q.execute()
            return pd.DataFrame(res.data) if res.data else pd.DataFrame()
        except:
            pass
    try:
        conn = get_conn()
        sql = f"SELECT * FROM {table} {extra_sql}"
        df = pd.read_sql(sql, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

def db_read(table, filters=None, order_col="id", desc=True, limit=None, extra_sql=None):
    """Supabase veya SQLite'dan DataFrame döner"""
    sb = get_sb()
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
            return pd.DataFrame(res.data) if res.data else pd.DataFrame()
        except:
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
    """Insert — Supabase önce, SQLite fallback"""
    sb = get_sb()
    if sb:
        try:
            res = sb.table(table).insert(data).execute()
            if res.data:
                return True
            else:
                st.warning(f"Supabase insert boş döndü: {table}")
        except Exception as e:
            st.warning(f"Supabase insert hatası ({table}): {e}")
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
    sb = get_sb()
    if sb:
        try:
            sb.table(table).update(data).eq(where_col, where_val).execute()
            return True
        except:
            pass
    try:
        conn = get_conn()
        sets = ", ".join([f"{k}=?" for k in data.keys()])
        conn.execute(f"UPDATE {table} SET {sets} WHERE {where_col}=?",
                    list(data.values()) + [where_val])
        conn.commit()
        conn.close()
        return True
    except:
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
                import re
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
        for col in ["olusturan TEXT", "beklenen_ciro REAL DEFAULT 0", "gerceklesen_ciro REAL DEFAULT 0"]:
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
        bugun = datetime.now().strftime("%Y-%m-%d")
        yedek_klasor = "backups"
        os.makedirs(yedek_klasor, exist_ok=True)
        db_yedek = os.path.join(yedek_klasor, f"mw_crm_{bugun}.db")
        if not os.path.exists(db_yedek) and os.path.exists("mw_crm.db"):
            shutil.copy2("mw_crm.db", db_yedek)
        csv_yedek = os.path.join(yedek_klasor, f"cari_kartlar_{bugun}.csv")
        if not os.path.exists(csv_yedek):
            df_yedek = db_read("cari_kartlar", extra_sql="")
            df_yedek.to_csv(csv_yedek, index=False, encoding="utf-8-sig")
    except:
        pass

otomatik_yedek()


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
                    st.rerun()
                else:
                    st.error("Kullanıcı adı veya şifre hatalı!")

def cikis():
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
import json as _menu_json

_TAB_LISTESI_DEFAULT = ["yeni", "liste", "randevu", "teklif", "kisiler", "rapor", "excel", "arsiv", "mesajlar", "kullanici"]
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
    "mesajlar": "💬 Mesajlar"
}

def get_menu_tercihi(kullanici):
    try:
        # Supabase veya SQLite'dan oku
        sb_m = get_sb()
        if sb_m:
            res = sb_m.table("kullanici_tercih").select("deger").eq("kullanici", kullanici).eq("anahtar","menu_sirasi").execute()
            if res.data:
                kayitli = _menu_json.loads(res.data[0]["deger"])
                tam_liste = _TAB_LISTESI_DEFAULT.copy()
                if st.session_state.get("rol") == "admin":
                    tam_liste += ["kullanici","koddepo"]
                for t in tam_liste:
                    if t not in kayitli:
                        kayitli.append(t)
                kayitli = [t for t in kayitli if t in tam_liste]
                return kayitli
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
                    tam_liste += ["kullanici","koddepo"]
                for t in tam_liste:
                    if t not in kayitli:
                        kayitli.append(t)
                kayitli = [t for t in kayitli if t in tam_liste]
                return kayitli
    except: pass
    tam_liste = _TAB_LISTESI_DEFAULT.copy()
    if st.session_state.get("rol") == "admin":
        tam_liste += ["kullanici","koddepo"]
    return tam_liste

def save_menu_tercihi(kullanici, sira):
    try:
        sb_m = get_sb()
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
with st.sidebar:
    st.caption(f"👤 {st.session_state.get('kullanici','')} | {st.session_state.get('rol','')}")

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
            if st.button("↺ Sıfırla", use_container_width=True):
                save_menu_tercihi(st.session_state["kullanici"], _TAB_LISTESI_DEFAULT.copy() + ["kullanici","koddepo"])
                st.rerun()

        with st.expander("📢 Duyuru"):
            with st.form("duyuru_form"):
                d_b = st.text_input("Başlık:")
                d_i = st.text_area("İçerik:", height=50)
                d_t = st.selectbox("Tip:", ["bilgi","uyari","hata"])
                if st.form_submit_button("📢 Yayınla") and d_b:
                    db_insert("duyurular", {"baslik":d_b,"icerik":d_i,"tip":d_t,
                        "olusturan":st.session_state["kullanici"],"aktif":1})
                    st.success("Yayınlandı!")
                    st.rerun()
# ── ANA UYGULAMA ──────────────────────────────────────────────────────────────
col_bas, col_kul, col_cik = st.columns([6, 2, 1])
with col_bas:
    st.title("🏢 MWCRMPRO - Cari Yönetim Sistemi")
with col_kul:
    st.markdown(f"<br>👤 **{st.session_state['kullanici']}** ({st.session_state['rol']})", unsafe_allow_html=True)
with col_cik:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚪 Çıkış"):
        cikis()

st.divider()

# ── MANUEL TAB MENÜSÜ ─────────────────────────────────────────────────────────
tab_listesi = _TAB_LISTESI_DEFAULT.copy()
tab_etiketler = _TAB_ETIKETLER
if st.session_state["rol"] == "admin":
    tab_listesi.append("kullanici")
    tab_listesi.append("koddepo")

aktif_tab_listesi = get_menu_tercihi(st.session_state["kullanici"])

# Admin tabları her zaman listede olsun
if st.session_state["rol"] == "admin":
    for _t in ["kullanici","koddepo"]:
        if _t not in aktif_tab_listesi:
            aktif_tab_listesi.append(_t)

# Yetki filtresi (admin hepsini görür)
if st.session_state.get("rol") != "admin":
    try:
        import json as _yj
        df_kul_yetki = db_read("kullanicilar", extra_sql="")
        if not df_kul_yetki.empty and "yetkiler" in df_kul_yetki.columns:
            kul_row = df_kul_yetki[df_kul_yetki["kullanici_adi"] == st.session_state["kullanici"]]
            if not kul_row.empty:
                yetki_val = str(kul_row.iloc[0].get("yetkiler","tam") or "tam")
                if yetki_val != "tam":
                    izinli = _yj.loads(yetki_val)
                    aktif_tab_listesi = [t for t in aktif_tab_listesi if t in izinli]
    except: pass

cols = st.columns(len(aktif_tab_listesi))
for i, tab_key in enumerate(aktif_tab_listesi):
    with cols[i]:
        _is_aktif = st.session_state["aktif_tab"] == tab_key
        _etiket = _TAB_ETIKETLER.get(tab_key, tab_key)
        if st.button(
            _etiket,
            use_container_width=True,
            type="primary" if _is_aktif else "secondary",
            key=f"tab_btn_{tab_key}"
        ):
            st.session_state["aktif_tab"] = tab_key
            st.rerun()

st.divider()
aktif = st.session_state["aktif_tab"]

# ── YENİ KART EKLE / DÜZENLE ─────────────────────────────────────────────────
if aktif == "yeni":

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
                bulunan = row_s.iloc[0].to_dict()
                st.session_state["duzenle_musteri"] = bulunan
                st.success(f"✅ Bulundu: **{bulunan.get('firma')}** (ID: {bulunan.get('id')})")
            else:
                st.error("Müşteri bulunamadı.")
                st.session_state.pop("duzenle_musteri", None)
    elif not musteri_ara:
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
        gsm      = col2.text_input("GSM",        value=duzenle.get("gsm","") if duzenle else "")
        sabit    = col2.text_input("Sabit Tel",  value=duzenle.get("sabit","") if duzenle else "")
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

        asama_opts = ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]
        asama_idx  = asama_opts.index(duzenle.get("islem_asamasi")) if duzenle and duzenle.get("islem_asamasi") in asama_opts else 0
        asama      = col3.selectbox("İşlem Aşaması", asama_opts, index=asama_idx)
        adres      = st.text_area("Adres", value=duzenle.get("adres","") if duzenle else "")

        st.markdown("#### 💰 Ciro Bilgileri")
        ciro_col1, ciro_col2, ciro_col3, ciro_col4 = st.columns(4)
        beklenen_ciro = ciro_col1.number_input(
            "Beklenen Ciro (₺)", min_value=0.0, step=1000.0,
            value=float(duzenle.get("beklenen_ciro") or 0) if duzenle else 0.0)
        gerceklesen_ciro = ciro_col2.number_input(
            "Gerçekleşen Ciro (₺)", min_value=0.0, step=1000.0,
            value=float(duzenle.get("gerceklesen_ciro") or 0) if duzenle else 0.0)
        fark = gerceklesen_ciro - beklenen_ciro
        yuzde = (gerceklesen_ciro / beklenen_ciro * 100) if beklenen_ciro > 0 else 0
        ciro_col3.metric("Fark (₺)", f"₺{fark:,.0f}", delta=f"{fark:,.0f}")
        ciro_col4.metric("Gerçekleşme %", f"%{yuzde:.1f}")

        btn_label = "💾 Güncelle" if duzenle else "💾 Cari Kartı Kaydet"
        if st.form_submit_button(btn_label):
            if not firma:
                st.warning("Firma adı boş bırakılamaz!")
            elif duzenle:
                # Güncelle
                db_update("cari_kartlar", {
                    "firma": firma, "yetkili": yetkili, "gsm": gsm,
                    "sabit": sabit, "email": email, "adres": adres,
                    "ilce": ilce, "il": il, "durum": durum,
                    "temsilci": temsilci, "islem_asamasi": asama,
                    "beklenen_ciro": beklenen_ciro, "gerceklesen_ciro": gerceklesen_ciro
                }, "id", duzenle.get("id"))
                st.session_state.pop("duzenle_musteri", None)
                st.session_state["aktif_tab"] = "liste"
                st.session_state["kayit_mesaj"] = f"✅ '{firma}' güncellendi!"
                st.rerun()
            else:
                # Yeni kayıt
                db_insert("cari_kartlar", {
                    "tarih": datetime.now().isoformat(),
                    "firma": firma, "yetkili": yetkili, "gsm": gsm,
                    "sabit": sabit, "email": email, "adres": adres,
                    "ilce": ilce, "il": il, "durum": durum,
                    "temsilci": temsilci, "islem_asamasi": asama,
                    "silindi": 0, "olusturan": st.session_state["kullanici"],
                    "beklenen_ciro": beklenen_ciro, "gerceklesen_ciro": gerceklesen_ciro
                })
                st.session_state["aktif_tab"] = "liste"
                st.session_state["kayit_mesaj"] = f"✅ '{firma}' başarıyla kaydedildi!"
                st.rerun()

    if duzenle:
        if st.button("❌ Düzenlemeyi İptal Et", use_container_width=True):
            st.session_state.pop("duzenle_musteri", None)
            st.rerun()

# ── CARİ LİSTE ───────────────────────────────────────────────────────────────
elif aktif == "liste":
    if st.session_state.get("kayit_mesaj"):
        st.success(st.session_state["kayit_mesaj"])
        st.session_state["kayit_mesaj"] = ""

    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL","")
        key = st.secrets.get("SUPABASE_KEY","")
        if url and key:
            sb = create_client(url, key)
            res = sb.table("cari_kartlar").select("*").neq("silindi", 1).order("tarih", desc=True).execute()
            df = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=["id","tarih","firma","yetkili","gsm","sabit","email","adres","ilce","il","durum","temsilci","islem_asamasi","silindi","olusturan","beklenen_ciro","gerceklesen_ciro"])
        else:
            raise Exception("no supabase")
    except:
        try:
            df = db_read("cari_kartlar", extra_sql="WHERE silindi=0 OR silindi='0' OR silindi IS NULL ORDER BY tarih DESC")
        except:
            df = pd.DataFrame()

    st.markdown(f"**Toplam {len(df)} aktif kayıt**")

    ara = st.text_input("🔍 Firma, yetkili veya il ara...", key="ara")
    if ara:
        mask = df.apply(lambda r: ara.lower() in str(r).lower(), axis=1)
        df = df[mask]

    if df.empty:
        st.info("Kayıt bulunamadı.")
    else:
        # ── TABLO GÖRÜNÜMÜ ──
        df_goster = df.copy()
        df_goster.insert(0, "Seç", False)

        col_tumunu_sec, col_bos = st.columns([1, 5])
        with col_tumunu_sec:
            tumunu_sec = st.checkbox("✅ Tümünü Seç", key="tumunu_sec")
        if tumunu_sec:
            df_goster["Seç"] = True

        # Her satırın yanına 👁️ butonu için kompakt liste
        st.markdown("**Firma listesi — görmek istediğiniz satıra tıklayın:**")
        
        # Kompakt satır listesi
        for _, row in df.head(100).iterrows():
            cc1, cc2, cc3, cc4, cc5, cc6 = st.columns([3, 1.5, 1, 1, 1, 0.8])
            cc1.markdown(f"**{row.get('firma','')}**")
            cc2.caption(f"📍 {row.get('il','')} {row.get('ilce','')}")
            cc3.caption(f"{row.get('durum','')}")
            cc4.caption(f"📱 {str(row.get('gsm',''))[:11]}")
            cc5.caption(f"👤 {row.get('yetkili','')}")
            if cc6.button("👁️", key=f"kart_{int(row.get('id',0))}", use_container_width=True):
                st.session_state["detay_acik_id"] = int(row.get("id",0))
                st.rerun()

        # Seçili kart göster
        if st.session_state.get("detay_acik_id"):
            detay_id = st.session_state["detay_acik_id"]
            detay_rows = df[df["id"] == detay_id]
            if not detay_rows.empty:
                detay_row = detay_rows.iloc[0]
                st.divider()
                
                kart_col, kapat_col = st.columns([6, 1])
                kart_col.markdown(f"## 🏢 {detay_row.get('firma','')}")
                if kapat_col.button("✕ Kapat", key="kart_kapat"):
                    st.session_state.pop("detay_acik_id", None)
                    st.rerun()

                kc1, kc2, kc3 = st.columns(3)
                with kc1:
                    st.markdown("**📋 İletişim**")
                    st.write(f"👤 {detay_row.get('yetkili','-')}")
                    st.write(f"📱 {detay_row.get('gsm','-')}")
                    st.write(f"✉️ {detay_row.get('email','-')}")
                with kc2:
                    st.markdown("**📍 Konum & Durum**")
                    st.write(f"🏙️ {detay_row.get('il','-')} / {detay_row.get('ilce','-')}")
                    st.write(f"📊 {detay_row.get('durum','-')} — {detay_row.get('islem_asamasi','-')}")
                    st.write(f"👔 {detay_row.get('temsilci','-')}")
                with kc3:
                    bek = float(detay_row.get('beklenen_ciro',0) or 0)
                    ger = float(detay_row.get('gerceklesen_ciro',0) or 0)
                    st.metric("Beklenen", f"₺{bek:,.0f}")
                    st.metric("Gerçekleşen", f"₺{ger:,.0f}", delta=f"₺{ger-bek:,.0f}")

                # Aksiyon butonları
                ab1, ab2, ab3, ab4 = st.columns(4)
                if ab1.button("✏️ Düzenle", key="kab1", use_container_width=True):
                    # Tüm cari bilgileri session'a aktar
                    duzenle_dict = {}
                    for col in detay_row.index:
                        duzenle_dict[col] = detay_row[col]
                    st.session_state["duzenle_musteri"] = duzenle_dict
                    st.session_state["aktif_tab"] = "yeni"
                    st.session_state.pop("detay_acik_id", None)
                    st.rerun()
                if ab2.button("📄 Teklif Oluştur", key="kab2", use_container_width=True, type="primary"):
                    st.session_state["aktif_tab"] = "teklif"
                    st.session_state["hedef_mus"] = str(detay_row.get("firma",""))
                    st.session_state["son_secili_id"] = None
                    st.rerun()
                if ab3.button("📅 Randevu", key="kab3", use_container_width=True, type="primary"):
                    st.session_state["aktif_tab"] = "randevu"
                    st.session_state["rand_musteri_onsel"] = detay_id
                    st.rerun()

                # WhatsApp - numara kontrolü
                import re as _re_d
                gsm_raw = str(detay_row.get('gsm','') or '').strip()
                gsm_d = _re_d.sub(r'[\s\-\(\)+]','', gsm_raw)
                if gsm_d.startswith('0') and len(gsm_d)==11:
                    gsm_d = '90'+gsm_d[1:]
                elif len(gsm_d)==10:
                    gsm_d = '90'+gsm_d
                wa_gecerli = len(gsm_d)==12 and gsm_d.isdigit()

                with st.expander("📱 WhatsApp" + (" ✅" if wa_gecerli else " ⚠️ Numara Gerekli")):
                    if not wa_gecerli:
                        st.warning(f"Kayıtlı numara geçersiz: '{gsm_raw}'")
                        manuel_wa = st.text_input("Manuel numara girin:", placeholder="05xxxxxxxxx", key=f"wa_manuel_{detay_id}")
                        if manuel_wa:
                            m = _re_d.sub(r'[\s\-\(\)+]','', manuel_wa)
                            if m.startswith('0') and len(m)==11: m = '90'+m[1:]
                            elif len(m)==10: m = '90'+m
                            if len(m)==12 and m.isdigit():
                                gsm_d = m
                                wa_gecerli = True
                                st.success(f"✅ {gsm_d}")
                            else:
                                st.error("Geçersiz numara formatı")

                    if wa_gecerli:
                        wa_mesaj_d = st.text_area("Mesaj:", value=f"Merhaba {detay_row.get('yetkili','')} Bey/Hanım, MW Kargo olarak sizinle iletişime geçmek istiyoruz.", height=80, key=f"wa_msg_{detay_id}")
                        wa_url_d = f"https://wa.me/{gsm_d}?text={wa_mesaj_d.replace(' ','%20').replace(chr(10),'%0A')}"
                        st.link_button("📱 WhatsApp'ta Mesaj Gönder", wa_url_d, use_container_width=True)

                # Son teklif & randevu
                st.divider()
                tc1, tc2 = st.columns(2)
                with tc1:
                    st.markdown("**📄 Son Teklif**")
                    df_tek_d = db_read("teklifler", filters={"musteri_id": detay_id}, order_col="tarih")
                    if not df_tek_d.empty:
                        t = df_tek_d.iloc[0]
                        st.success(f"₺{float(t.get('toplam_tutar',0) or 0):,.2f} | {str(t.get('tarih',''))[:10]}")
                    else:
                        st.info("Teklif yok")
                with tc2:
                    st.markdown("**📅 Aktif Randevu**")
                    df_rand_d = db_read("randevular", filters={"musteri_id": detay_id}, order_col="randevu_tarihi", desc=True)
                    if not df_rand_d.empty:
                        aktif_r = df_rand_d[~df_rand_d["sonuc"].isin(["Bitti","İptal"])].head(1) if "sonuc" in df_rand_d.columns else df_rand_d.head(1)
                        if not aktif_r.empty:
                            r = aktif_r.iloc[0]
                            st.warning(f"🗓️ {r.get('randevu_tarihi','')} | {r.get('gorev','')} | {r.get('temsilci','')}")
                        else:
                            st.success(f"✅ {df_rand_d.iloc[0].get('sonuc','Tamamlandı')}")
                    else:
                        st.info("Randevu yok")

        st.divider()
        # Düzenleme için data editor (gizli ama kaydet için)
        df_edit = df.copy()
        df_edit.insert(0, "Seç", False)
        edited_df = st.data_editor(
            df_edit,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Seç": st.column_config.CheckboxColumn("Seç", default=False),
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "tarih": st.column_config.TextColumn("Tarih", disabled=True),
                "olusturan": st.column_config.TextColumn("Oluşturan", disabled=True),
                "silindi": None,
                "durum": st.column_config.SelectboxColumn("Durum", options=["Aktif","Hedef","Pasif"]),
                "islem_asamasi": st.column_config.SelectboxColumn("Aşama", options=["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]),
            },
            column_order=["Seç","id","firma","yetkili","gsm","email","il","ilce","durum","temsilci","islem_asamasi"],
            key="cari_editor"
        )

        secili_df = edited_df[edited_df["Seç"] == True]
        secili_sayi = len(secili_df)

        col_kaydet, col_arsiv = st.columns([2, 1])
        with col_kaydet:
            if st.button("💾 Tüm Değişiklikleri Kaydet", use_container_width=True):
                for _, row in edited_df.iterrows():
                    if row.get("id"):
                        db_update("cari_kartlar", {
                            "firma": row.get("firma"), "yetkili": row.get("yetkili"),
                            "gsm": row.get("gsm"), "sabit": row.get("sabit"),
                            "email": row.get("email"), "adres": row.get("adres"),
                            "ilce": row.get("ilce"), "il": row.get("il"),
                            "durum": row.get("durum"), "temsilci": row.get("temsilci"),
                            "islem_asamasi": row.get("islem_asamasi")
                        }, "id", row.get("id"))
                st.success("✅ Değişiklikler kaydedildi!")
                st.rerun()

        with col_arsiv:
            with st.expander("🗑️ Arşive Gönder"):
                # Seçili varsa tek tıkla arşive gönder
                if secili_sayi > 0:
                    st.info(f"{secili_sayi} kayıt seçili")
                    if st.button(f"🗑️ Seçili {secili_sayi} Kaydı Arşive Gönder", use_container_width=True, type="primary"):
                        for _, row in secili_df.iterrows():
                            if row.get("id") and str(row.get("id")) != "None":
                                db_update("cari_kartlar", {"silindi": 1}, "id", row.get("id"))
                        st.success(f"{secili_sayi} kayıt arşive gönderildi.")
                        st.rerun()
                else:
                    # ID veya firma adıyla arşive gönder
                    arsiv_yontemi = st.radio("Yöntem:", ["ID ile", "Firma Adı ile"], horizontal=True, key="arsiv_yontem")
                    if arsiv_yontemi == "ID ile":
                        target_id = st.number_input("ID:", min_value=1, step=1, key="arsiv_id")
                        if st.button("Arşive Gönder", use_container_width=True):
                            db_update("cari_kartlar", {"silindi": 1}, "id", target_id)
                            st.success(f"ID {target_id} arşive gönderildi.")
                            st.rerun()
                    else:
                        firma_listesi = df["firma"].dropna().tolist()
                        secili_firma = st.selectbox("Firma:", firma_listesi, key="arsiv_firma")
                        if st.button("Arşive Gönder", use_container_width=True, key="arsiv_firma_btn"):
                            db_update("cari_kartlar", {"silindi": 1}, "firma", secili_firma)
                            st.success(f"'{secili_firma}' arşive gönderildi.")
                            st.rerun()

    # ── MÜŞTERİ DETAY PANELİ ─────────────────────────────────────────────────
    st.divider()
    st.markdown("### 🔍 Müşteri Kartı — Teklif & Randevu")

    if not df.empty:
        # Arama ile hızlı müşteri bul
        ara_detay = st.text_input("🔍 Müşteri ara:", key="detay_ara", placeholder="Firma adı veya ID yaz...")
        df_detay_filtre = df.copy()
        if ara_detay:
            mask = df_detay_filtre.apply(lambda r: ara_detay.lower() in str(r).lower(), axis=1)
            df_detay_filtre = df_detay_filtre[mask]

        detay_opts = ["-- Seçin --"] + [
            f"[{int(r['id'])}] {r['firma']} — {r.get('il','')} {r.get('ilce','')} | {r.get('durum','')}"
            for _, r in df_detay_filtre.head(50).iterrows()
        ]
        secili_detay = st.selectbox("Müşteri:", detay_opts, key="detay_musteri_sec")

        if secili_detay != "-- Seçin --" and "[" in secili_detay:
            try:
                detay_id = int(secili_detay.split("]")[0].replace("[","").strip())
                detay_row = df[df["id"]==detay_id].iloc[0]

                # ── CARİ KART BİLGİLERİ ──
                st.markdown(f"## 🏢 {detay_row.get('firma','')}")

                kc1, kc2, kc3 = st.columns(3)
                with kc1:
                    st.markdown("**📋 Genel Bilgiler**")
                    st.write(f"👤 Yetkili: **{detay_row.get('yetkili','-')}**")
                    st.write(f"📱 GSM: **{detay_row.get('gsm','-')}**")
                    st.write(f"☎️ Sabit: **{detay_row.get('sabit','-')}**")
                    st.write(f"✉️ Email: **{detay_row.get('email','-')}**")

                with kc2:
                    st.markdown("**📍 Konum & Durum**")
                    st.write(f"🏙️ İl/İlçe: **{detay_row.get('il','-')} / {detay_row.get('ilce','-')}**")
                    st.write(f"📊 Durum: **{detay_row.get('durum','-')}**")
                    st.write(f"🔄 Aşama: **{detay_row.get('islem_asamasi','-')}**")
                    st.write(f"👔 Temsilci: **{detay_row.get('temsilci','-')}**")

                with kc3:
                    st.markdown("**💰 Ciro**")
                    bek = float(detay_row.get('beklenen_ciro',0) or 0)
                    ger = float(detay_row.get('gerceklesen_ciro',0) or 0)
                    st.metric("Beklenen", f"₺{bek:,.0f}")
                    st.metric("Gerçekleşen", f"₺{ger:,.0f}", delta=f"₺{ger-bek:,.0f}")

                if detay_row.get('adres'):
                    st.write(f"📮 Adres: {detay_row.get('adres','')}")

                st.divider()

                # ── AKSİYON BUTONLARI ──
                ab1, ab2, ab3, ab4 = st.columns(4)
                if ab1.button("✏️ Düzenle", key=f"duzenle_{detay_id}", use_container_width=True):
                    st.session_state["duzenle_musteri"] = detay_row.to_dict()
                    st.session_state["aktif_tab"] = "yeni"
                    st.rerun()

                if ab2.button("📄 Teklif Oluştur", key=f"teklif_{detay_id}", use_container_width=True, type="primary"):
                    st.session_state["aktif_tab"] = "teklif"
                    st.session_state["son_secili_id"] = None
                    st.session_state["hedef_mus"] = str(detay_row.get("firma",""))
                    st.rerun()

                if ab3.button("📅 Randevu Oluştur", key=f"randevu_{detay_id}", use_container_width=True, type="primary"):
                    st.session_state["aktif_tab"] = "randevu"
                    st.session_state["rand_musteri_onsel"] = detay_id
                    st.rerun()

                if ab4.button("📱 WA Gönder", key=f"wa_{detay_id}", use_container_width=True):
                    gsm_d = str(detay_row.get('gsm','') or '')
                    import re as _re_d
                    gsm_d = _re_d.sub(r'[\s\-\(\)]','',gsm_d)
                    if gsm_d.startswith('0'): gsm_d = '90'+gsm_d[1:]
                    elif len(gsm_d)==10: gsm_d = '90'+gsm_d
                    wa_d = f"https://wa.me/{gsm_d}"
                    st.markdown(f"[📱 WhatsApp'ta Aç]({wa_d})")

                st.divider()

                # ── SON TEKLİF & AKTİF RANDEVU ──
                col_tek, col_rand = st.columns(2)

                with col_tek:
                    st.markdown("#### 📄 Son Teklif")
                    df_tek_d = db_read("teklifler", filters={"musteri_id": detay_id}, order_col="tarih")
                    if not df_tek_d.empty:
                        son_tek = df_tek_d.iloc[0]
                        st.success(f"💰 **₺{float(son_tek.get('toplam_tutar',0) or 0):,.2f}**\n\n"
                                  f"📅 {str(son_tek.get('tarih',''))[:16]}\n\n"
                                  f"📝 {str(son_tek.get('notlar',''))[:80]}")
                        st.caption(f"Toplam {len(df_tek_d)} teklif verildi")
                    else:
                        st.info("Henüz teklif verilmemiş.")

                with col_rand:
                    st.markdown("#### 📅 Aktif Randevu")
                    df_rand_d = db_read("randevular", filters={"musteri_id": detay_id}, order_col="randevu_tarihi", desc=True)
                    if not df_rand_d.empty:
                        aktif_r = df_rand_d[~df_rand_d["sonuc"].isin(["Bitti","İptal"])].head(1) if "sonuc" in df_rand_d.columns else df_rand_d.head(1)
                        if not aktif_r.empty:
                            r = aktif_r.iloc[0]
                            st.warning(f"🗓️ **{r.get('randevu_tarihi','')} {r.get('randevu_saati','')}**\n\n"
                                      f"📍 {r.get('bolge','')}\n\n"
                                      f"🎯 {r.get('gorev','')}\n\n"
                                      f"👤 {r.get('temsilci','')}")
                            yeni_s = st.selectbox("Sonuç:", ["—","Bitti","Devam Ediyor","Gidilmedi","İptal"], key=f"rs_{detay_id}")
                            if yeni_s != "—" and st.button("💾 Güncelle", key=f"rg_{detay_id}", use_container_width=True):
                                db_update("randevular", {"sonuc": yeni_s}, "id", int(r["id"]))
                                st.success("✅ Güncellendi!")
                                st.rerun()
                        else:
                            son_r = df_rand_d.iloc[0]
                            st.success(f"✅ Tamamlandı: {son_r.get('randevu_tarihi','')} — {son_r.get('sonuc','')}")
                    else:
                        st.info("Henüz randevu yok.")

            except Exception as e:
                st.error(f"Detay hatası: {e}")

        if secili_detay != "-- Müşteri Seçin --":
            try:
                detay_id = int(secili_detay.split("]")[0].replace("[","").strip())
                detay_row = df[df["id"]==detay_id].iloc[0]

                # Müşteri bilgileri
                dc1, dc2, dc3, dc4 = st.columns(4)
                dc1.metric("Durum", str(detay_row.get("durum","")))
                dc2.metric("Aşama", str(detay_row.get("islem_asamasi","")))
                dc3.metric("Beklenen", f"₺{float(detay_row.get('beklenen_ciro',0) or 0):,.0f}")
                dc4.metric("Gerçekleşen", f"₺{float(detay_row.get('gerceklesen_ciro',0) or 0):,.0f}")

                col_tek, col_rand = st.columns(2)

                # Son teklif
                with col_tek:
                    st.markdown("#### 📄 Son Teklif")
                    df_tek_d = db_read("teklifler", filters={"musteri_id": detay_id}, order_col="tarih")
                    if not df_tek_d.empty:
                        son_tek = df_tek_d.iloc[0]
                        st.info(f"**{son_tek.get('musteri_adi','')}**\n\n"
                               f"💰 ₺{float(son_tek.get('toplam_tutar',0) or 0):,.2f}\n\n"
                               f"📅 {str(son_tek.get('tarih',''))[:16]}\n\n"
                               f"📝 {str(son_tek.get('notlar',''))[:100]}")
                        if st.button("📄 Teklif Detayı", key=f"tek_det_{detay_id}", use_container_width=True):
                            st.session_state["aktif_tab"] = "teklif"
                            st.session_state["teklif_hedef_musteri"] = str(detay_row.get("firma",""))
                            st.rerun()
                        if len(df_tek_d) > 1:
                            st.caption(f"Toplam {len(df_tek_d)} teklif var")
                    else:
                        st.info("Henüz teklif yok.")
                        if st.button("➕ Teklif Oluştur", key=f"tek_yeni_{detay_id}", use_container_width=True, type="primary"):
                            st.session_state["aktif_tab"] = "teklif"
                            st.session_state["teklif_hedef_musteri"] = str(detay_row.get("firma",""))
                            st.rerun()

                # Aktif randevu (tek randevu — mükerrer olmasın)
                with col_rand:
                    st.markdown("#### 📅 Aktif Randevu")
                    df_rand_d = db_read("randevular", filters={"musteri_id": detay_id}, order_col="randevu_tarihi", desc=True)

                    # Bitmemiş tek randevu göster
                    aktif_rand = pd.DataFrame()
                    if not df_rand_d.empty and "sonuc" in df_rand_d.columns:
                        aktif_rand = df_rand_d[~df_rand_d["sonuc"].isin(["Bitti","İptal"])].head(1)

                    if not aktif_rand.empty:
                        r = aktif_rand.iloc[0]
                        durum_renk = "🟡" if str(r.get("sonuc","")) == "Devam Ediyor" else "🔵"
                        st.info(f"{durum_renk} **{r.get('randevu_tarihi','')} {r.get('randevu_saati','')}**\n\n"
                               f"📍 {r.get('bolge','')}\n\n"
                               f"🎯 {r.get('gorev','')}\n\n"
                               f"👤 {r.get('temsilci','')}\n\n"
                               f"📋 {r.get('takip','')}")

                        # Sonuç güncelle
                        yeni_sonuc = st.selectbox("Sonuç Güncelle:",
                            ["—","Bitti","Devam Ediyor","Gidilmedi","İptal"],
                            key=f"rand_sonuc_{detay_id}")
                        if yeni_sonuc != "—":
                            if st.button("💾 Güncelle", key=f"rand_gunc_{detay_id}", use_container_width=True):
                                db_update("randevular", {"sonuc": yeni_sonuc}, "id", int(r["id"]))
                                st.success("✅ Güncellendi!")
                                st.rerun()

                        if st.button("📅 Randevu Detayı", key=f"rand_det_{detay_id}", use_container_width=True):
                            st.session_state["aktif_tab"] = "randevu"
                            st.rerun()
                    else:
                        if not df_rand_d.empty:
                            son_r = df_rand_d.iloc[0]
                            st.success(f"✅ Son randevu tamamlandı: {son_r.get('randevu_tarihi','')} — {son_r.get('sonuc','')}")
                        else:
                            st.info("Henüz randevu yok.")

                        if st.button("➕ Randevu Oluştur", key=f"rand_yeni_{detay_id}", use_container_width=True, type="primary"):
                            st.session_state["aktif_tab"] = "randevu"
                            st.session_state["rand_musteri_onsel"] = detay_id
                            st.rerun()

            except Exception as e:
                st.error(f"Detay hatası: {e}")

# ── ARŞİV ─────────────────────────────────────────────────────────────────────
elif aktif == "arsiv":
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
                    st.success(f"ID {restore_id} geri alındı.")
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
    st.markdown("## 👥 Kullanıcı Yönetimi")

    TUM_MENULER = {
        "yeni":"➕ Yeni Kart","liste":"📋 Cari Liste","randevu":"📅 Randevular",
        "teklif":"📄 Teklif","kisiler":"📞 Kişiler","rapor":"📊 Raporlar",
        "excel":"📥 Excel","arsiv":"🗃️ Arşiv","mesajlar":"💬 Mesajlar"
    }

    kul_tab1, kul_tab2, kul_tab3 = st.tabs(["📋 Kullanıcılar","➕ Yeni Kullanıcı","🔐 Yetki Düzenle"])

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
                    db_update("kullanicilar",{"sifre":s1},"id",int(s_sec.split("]")[0].replace("[","")))
                    st.success("✅ Güncellendi!")
                else:
                    st.error("Şifreler eşleşmiyor veya boş!")

            st.divider()
            st.markdown("#### 🗑️ Kullanıcı Sil")
            sil_opts = [f"[{int(r['id'])}] {r['kullanici_adi']}" for _,r in df_kul.iterrows() if r["kullanici_adi"]!="admin"]
            if sil_opts:
                sil_sec = st.selectbox("Silinecek:",sil_opts,key="sil_kul")
                if st.button("🗑️ Sil",type="primary"):
                    sil_id = int(sil_sec.split("]")[0].replace("[",""))
                    sb_s = get_sb()
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
                    import json as _kj
                    yetki = "tam" if tam else _kj.dumps(secili_m)
                    # Önce temel kolonlarla dene
                    veri = {"kullanici_adi": yk_kadi, "sifre": yk_sifre, "rol": yk_rol}
                    # Ek kolonları tek tek ekle
                    sb_k = get_sb()
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

            import json as _kj2
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
                st.success("✅ Güncellendi!"); st.rerun()

# ── RAPORLAR ─────────────────────────────────────────────────────────────────
elif aktif == "rapor":
    df_rapor = db_read("cari_kartlar", filters={"silindi": "neq_1"})

    if df_rapor.empty:
        st.info("Henüz kayıt yok. Önce müşteri ekleyin veya Excel'den aktar.")
        st.stop()

    for col in ["beklenen_ciro","gerceklesen_ciro","durum","islem_asamasi","temsilci","il","firma","yetkili","id"]:
        if col not in df_rapor.columns:
            df_rapor[col] = 0 if col in ["beklenen_ciro","gerceklesen_ciro","id"] else ""

    if "beklenen_ciro" not in df_rapor.columns:
        df_rapor["beklenen_ciro"] = 0
    if "gerceklesen_ciro" not in df_rapor.columns:
        df_rapor["gerceklesen_ciro"] = 0
    df_rapor["beklenen_ciro"]    = pd.to_numeric(df_rapor["beklenen_ciro"], errors="coerce").fillna(0)
    df_rapor["gerceklesen_ciro"] = pd.to_numeric(df_rapor["gerceklesen_ciro"], errors="coerce").fillna(0)
    df_rapor["fark"]  = df_rapor["gerceklesen_ciro"] - df_rapor["beklenen_ciro"]
    df_rapor["yuzde"] = df_rapor.apply(lambda r: (r["gerceklesen_ciro"] / r["beklenen_ciro"] * 100) if r["beklenen_ciro"] > 0 else 0, axis=1)

    st.markdown("## 📊 Genel Rapor")

    toplam         = len(df_rapor)
    aktif_say      = len(df_rapor[df_rapor["durum"] == "Aktif"])
    hedef_say      = len(df_rapor[df_rapor["durum"] == "Hedef"])
    pasif_say      = len(df_rapor[df_rapor["durum"] == "Pasif"])
    toplam_beklenen   = df_rapor["beklenen_ciro"].sum()
    toplam_gercek     = df_rapor["gerceklesen_ciro"].sum()
    toplam_fark       = toplam_gercek - toplam_beklenen
    genel_yuzde       = (toplam_gercek / toplam_beklenen * 100) if toplam_beklenen > 0 else 0
    kazanilan_ciro    = df_rapor[df_rapor["islem_asamasi"] == "Kazanıldı"]["gerceklesen_ciro"].sum()
    kaybedilen        = len(df_rapor[df_rapor["islem_asamasi"] == "Kaybedildi"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👥 Toplam Müşteri", toplam)
    c2.metric("✅ Aktif", aktif_say)
    c3.metric("🎯 Hedef", hedef_say)
    c4.metric("⏸️ Pasif", pasif_say)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("💰 Toplam Beklenen", f"₺{toplam_beklenen:,.0f}")
    c6.metric("✅ Toplam Gerçekleşen", f"₺{toplam_gercek:,.0f}", delta=f"₺{toplam_fark:,.0f}")
    c7.metric("📈 Gerçekleşme Oranı", f"%{genel_yuzde:.1f}")
    c8.metric("🏆 Kazanılan Ciro", f"₺{kazanilan_ciro:,.0f}")

    st.divider()
    col_r1, col_r2 = st.columns(2)

    with col_r1:
        st.markdown("### 📌 Durum Dağılımı")
        durum_df = df_rapor.groupby("durum").agg(
            Adet=("id","count"),
            Beklenen=("beklenen_ciro","sum"),
            Gerceklesen=("gerceklesen_ciro","sum")
        ).reset_index()
        durum_df["Fark"] = durum_df["Gerceklesen"] - durum_df["Beklenen"]
        durum_df["Oran%"] = durum_df.apply(lambda r: f"%{(r['Gerceklesen']/r['Beklenen']*100):.1f}" if r["Beklenen"] > 0 else "%0", axis=1)
        durum_df["Beklenen"]    = durum_df["Beklenen"].apply(lambda x: f"₺{x:,.0f}")
        durum_df["Gerceklesen"] = durum_df["Gerceklesen"].apply(lambda x: f"₺{x:,.0f}")
        durum_df["Fark"]        = durum_df["Fark"].apply(lambda x: f"₺{x:,.0f}")
        durum_df.columns = ["Durum","Müşteri","Beklenen Ciro","Gerçekleşen","Fark","Oran %"]
        st.dataframe(durum_df, use_container_width=True, hide_index=True)

    with col_r2:
        st.markdown("### 🔄 İşlem Aşaması")
        asama_df = df_rapor.groupby("islem_asamasi").agg(
            Adet=("id","count"),
            Beklenen=("beklenen_ciro","sum"),
            Gerceklesen=("gerceklesen_ciro","sum")
        ).reset_index()
        asama_df["Fark"] = asama_df["Gerceklesen"] - asama_df["Beklenen"]
        asama_df["Oran%"] = asama_df.apply(lambda r: f"%{(r['Gerceklesen']/r['Beklenen']*100):.1f}" if r["Beklenen"] > 0 else "%0", axis=1)
        asama_df["Beklenen"]    = asama_df["Beklenen"].apply(lambda x: f"₺{x:,.0f}")
        asama_df["Gerceklesen"] = asama_df["Gerceklesen"].apply(lambda x: f"₺{x:,.0f}")
        asama_df["Fark"]        = asama_df["Fark"].apply(lambda x: f"₺{x:,.0f}")
        asama_df.columns = ["Aşama","Müşteri","Beklenen Ciro","Gerçekleşen","Fark","Oran %"]
        st.dataframe(asama_df, use_container_width=True, hide_index=True)

    st.divider()
    col_r3, col_r4 = st.columns(2)

    with col_r3:
        st.markdown("### 👤 Temsilci Bazlı")
        t_df = df_rapor[df_rapor["temsilci"].notna() & (df_rapor["temsilci"] != "")].groupby("temsilci").agg(
            Adet=("id","count"),
            Beklenen=("beklenen_ciro","sum"),
            Gerceklesen=("gerceklesen_ciro","sum")
        ).reset_index().sort_values("Gerceklesen", ascending=False)
        t_df["Fark"]  = t_df["Gerceklesen"] - t_df["Beklenen"]
        t_df["Oran%"] = t_df.apply(lambda r: f"%{(r['Gerceklesen']/r['Beklenen']*100):.1f}" if r["Beklenen"] > 0 else "%0", axis=1)
        t_df["Beklenen"]    = t_df["Beklenen"].apply(lambda x: f"₺{x:,.0f}")
        t_df["Gerceklesen"] = t_df["Gerceklesen"].apply(lambda x: f"₺{x:,.0f}")
        t_df["Fark"]        = t_df["Fark"].apply(lambda x: f"₺{x:,.0f}")
        t_df.columns = ["Temsilci","Müşteri","Beklenen","Gerçekleşen","Fark","Oran %"]
        st.dataframe(t_df, use_container_width=True, hide_index=True)

    with col_r4:
        st.markdown("### 🗺️ İl Bazlı (Top 15)")
        il_df = df_rapor[df_rapor["il"].notna() & (df_rapor["il"] != "")].groupby("il").agg(
            Adet=("id","count"),
            Beklenen=("beklenen_ciro","sum"),
            Gerceklesen=("gerceklesen_ciro","sum")
        ).reset_index().sort_values("Adet", ascending=False).head(15)
        il_df["Fark"]  = il_df["Gerceklesen"] - il_df["Beklenen"]
        il_df["Oran%"] = il_df.apply(lambda r: f"%{(r['Gerceklesen']/r['Beklenen']*100):.1f}" if r["Beklenen"] > 0 else "%0", axis=1)
        il_df["Beklenen"]    = il_df["Beklenen"].apply(lambda x: f"₺{x:,.0f}")
        il_df["Gerceklesen"] = il_df["Gerceklesen"].apply(lambda x: f"₺{x:,.0f}")
        il_df["Fark"]        = il_df["Fark"].apply(lambda x: f"₺{x:,.0f}")
        il_df.columns = ["İl","Müşteri","Beklenen","Gerçekleşen","Fark","Oran %"]
        st.dataframe(il_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### 💰 Müşteri Bazlı Ciro Detayı (Top 20 Beklenen)")
    ciro_df = df_rapor[["firma","yetkili","durum","islem_asamasi","temsilci","beklenen_ciro","gerceklesen_ciro","fark","yuzde"]].sort_values("beklenen_ciro", ascending=False).head(20).copy()
    ciro_df["beklenen_ciro"]    = ciro_df["beklenen_ciro"].apply(lambda x: f"₺{x:,.0f}")
    ciro_df["gerceklesen_ciro"] = ciro_df["gerceklesen_ciro"].apply(lambda x: f"₺{x:,.0f}")
    ciro_df["fark"]             = ciro_df["fark"].apply(lambda x: f"₺{x:,.0f}")
    ciro_df["yuzde"]            = ciro_df["yuzde"].apply(lambda x: f"%{x:.1f}")
    ciro_df.columns = ["Firma","Yetkili","Durum","Aşama","Temsilci","Beklenen Ciro","Gerçekleşen Ciro","Fark","Gerçekleşme %"]
    st.dataframe(ciro_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### ⬇️ Raporu İndir")
    import io
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        csv_data = df_rapor.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("📥 CSV İndir", data=csv_data,
            file_name=f"rapor_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv", use_container_width=True)
    with col_d2:
        excel_buf = io.BytesIO()
        df_rapor.to_excel(excel_buf, index=False)
        excel_buf.seek(0)
        st.download_button("📥 Excel İndir", data=excel_buf,
            file_name=f"rapor_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.ms-excel", use_container_width=True)

    # ── ARAMA RAPORU ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("## 🔍 Arama / Filtreleme Raporu")
    ara_r1, ara_r2, ara_r3 = st.columns(3)
    arama_kelime = ara_r1.text_input("Kelime Ara (Firma/Yetkili/İl)", key="rapor_ara")
    filtre_durum = ara_r2.selectbox("Durum", ["Tümü","Aktif","Hedef","Pasif"], key="rapor_durum")
    filtre_asama = ara_r3.selectbox("Aşama", ["Tümü","İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"], key="rapor_asama")

    df_ara = df_rapor.copy()
    if arama_kelime:
        mask = df_ara.apply(lambda r: arama_kelime.lower() in str(r).lower(), axis=1)
        df_ara = df_ara[mask]
    if filtre_durum != "Tümü":
        df_ara = df_ara[df_ara["durum"] == filtre_durum]
    if filtre_asama != "Tümü":
        df_ara = df_ara[df_ara["islem_asamasi"] == filtre_asama]

    st.markdown(f"**{len(df_ara)} kayıt bulundu**")
    if not df_ara.empty:
        goster_cols = ["id","firma","yetkili","gsm","email","il","ilce","durum","islem_asamasi","temsilci","beklenen_ciro","gerceklesen_ciro"]
        goster_cols = [c for c in goster_cols if c in df_ara.columns]
        st.dataframe(df_ara[goster_cols], use_container_width=True, hide_index=True)
        ara_buf = io.BytesIO()
        df_ara[goster_cols].to_excel(ara_buf, index=False)
        ara_buf.seek(0)
        st.download_button("📥 Filtrelenmiş Excel İndir", data=ara_buf,
            file_name=f"filtrelenmis_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.ms-excel", use_container_width=True)

    # ── TEKLİF RAPORU ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("## 📄 Verilen Teklifler Raporu")
    try:
        df_tek_rapor = db_read("teklifler", order_col="tarih")

        if not df_tek_rapor.empty:
            t1, t2, t3, t4 = st.columns(4)
            t1.metric("Toplam Teklif", len(df_tek_rapor))
            t2.metric("Toplam Tutar", f"₺{df_tek_rapor['toplam_tutar'].sum():,.0f}")
            t3.metric("Ort. Teklif", f"₺{df_tek_rapor['toplam_tutar'].mean():,.0f}")
            t4.metric("Bu Ay", len(df_tek_rapor[df_tek_rapor["tarih"].str[:7] == datetime.now().strftime("%Y-%m")]) if "tarih" in df_tek_rapor.columns else 0)

            # Teklif listesi
            df_tek_goster = df_tek_rapor[["id","tarih","musteri_adi","toplam_tutar","olusturan","notlar"]].copy()
            df_tek_goster["toplam_tutar"] = df_tek_goster["toplam_tutar"].apply(lambda x: f"₺{float(x):,.2f}")
            df_tek_goster.columns = ["ID","Tarih","Müşteri","Tutar","Oluşturan","Notlar"]
            st.dataframe(df_tek_goster, use_container_width=True, hide_index=True)

            # Teklif detay tur analizi
            st.markdown("#### 📦 Teklif İçi Ürün/Tür Analizi")
            import json as _json
            tur_sayac = {}
            il_tur_sayac = {}
            for _, row in df_tek_rapor.iterrows():
                try:
                    data = _json.loads(row["satirlar"])
                    teklif_list = data.get("teklif", [])
                    for satir in teklif_list:
                        tur = satir.get("tur","Bilinmiyor")
                        cikis = satir.get("cikis_il","")
                        varis = satir.get("varis_il","")
                        tutar = float(satir.get("tutar",0))
                        tur_sayac[tur] = tur_sayac.get(tur, {"adet":0,"tutar":0.0})
                        tur_sayac[tur]["adet"] += 1
                        tur_sayac[tur]["tutar"] += tutar
                        if cikis:
                            il_key = f"{cikis} → {varis}"
                            il_tur_sayac[il_key] = il_tur_sayac.get(il_key, {"adet":0,"tutar":0.0})
                            il_tur_sayac[il_key]["adet"] += 1
                            il_tur_sayac[il_key]["tutar"] += tutar
                except:
                    pass

            ta1, ta2 = st.columns(2)
            with ta1:
                st.markdown("**Ürün/Tür Dağılımı**")
                if tur_sayac:
                    tur_df = pd.DataFrame([
                        {"Tür": k, "Teklif Adedi": v["adet"], "Toplam Tutar": f"₺{v['tutar']:,.2f}"}
                        for k, v in sorted(tur_sayac.items(), key=lambda x: x[1]["adet"], reverse=True)
                    ])
                    st.dataframe(tur_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Tür verisi yok.")

            with ta2:
                st.markdown("**Hat (Çıkış → Varış) Analizi**")
                if il_tur_sayac:
                    hat_df = pd.DataFrame([
                        {"Hat": k, "Teklif Adedi": v["adet"], "Toplam Tutar": f"₺{v['tutar']:,.2f}"}
                        for k, v in sorted(il_tur_sayac.items(), key=lambda x: x[1]["adet"], reverse=True)
                    ]).head(15)
                    st.dataframe(hat_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Hat verisi yok.")

            tek_buf = io.BytesIO()
            df_tek_rapor[["id","tarih","musteri_adi","toplam_tutar","olusturan","notlar"]].to_excel(tek_buf, index=False)
            tek_buf.seek(0)
            st.download_button("📥 Teklifler Excel İndir", data=tek_buf,
                file_name=f"teklifler_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel", use_container_width=True)
        else:
            conn.close()
            st.info("Henüz teklif kaydı yok.")
    except Exception as e:
        st.error(f"Teklif raporu hatası: {e}")

    # ── WHATSAPP / EMAIL RAPORU ────────────────────────────────────────────────
    st.divider()
    st.markdown("## 📱 WhatsApp & Email Gönderim Raporu")
    try:
        df_islem_rapor = db_read("islem_kaydi", order_col="tarih")

        if not df_islem_rapor.empty:
            wa_say  = len(df_islem_rapor[df_islem_rapor["islem_turu"].str.contains("WhatsApp", na=False)])
            em_say  = len(df_islem_rapor[df_islem_rapor["islem_turu"].str.contains("Email", na=False)])
            i1, i2, i3 = st.columns(3)
            i1.metric("Toplam Gönderim", len(df_islem_rapor))
            i2.metric("📱 WhatsApp", wa_say)
            i3.metric("📧 Email", em_say)

            # Filtre
            islem_filtre = st.selectbox("Filtrele:", ["Tümü","WhatsApp Teklif","Email Teklif"], key="islem_filtre")
            df_if = df_islem_rapor if islem_filtre == "Tümü" else df_islem_rapor[df_islem_rapor["islem_turu"] == islem_filtre]

            df_if_goster = df_if[["tarih","musteri_adi","islem_turu","gonderim_bilgisi","olusturan"]].copy()
            df_if_goster.columns = ["Tarih","Müşteri","İşlem","Gönderim Bilgisi","Kullanıcı"]
            st.dataframe(df_if_goster, use_container_width=True, hide_index=True)

            # Mesaj içeriği görüntüle
            with st.expander("📝 Gönderilen Mesaj İçeriklerini Gör"):
                df_ic = df_islem_rapor[["tarih","musteri_adi","islem_turu","icerik"]].copy()
                df_ic.columns = ["Tarih","Müşteri","Tür","İçerik"]
                st.dataframe(df_ic, use_container_width=True, hide_index=True)

            islem_buf = io.BytesIO()
            df_islem_rapor.to_excel(islem_buf, index=False)
            islem_buf.seek(0)
            st.download_button("📥 Gönderimler Excel İndir", data=islem_buf,
                file_name=f"gonderimler_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel", use_container_width=True)
        else:
            conn.close()
            st.info("Henüz gönderim kaydı yok.")
    except Exception as e:
        st.error(f"Gönderim raporu hatası: {e}")

    # ── İL / TÜR RAPORU ───────────────────────────────────────────────────────
    st.divider()
    st.markdown("## 🗺️ İl & Ürün Türü Raporu")
    try:
        df_tek2 = db_read("teklifler", extra_sql="")

        il_tur_detay = []
        import json as _json2
        for _, row in df_tek2.iterrows():
            try:
                data = _json2.loads(row["satirlar"])
                for satir in data.get("teklif", []):
                    il_tur_detay.append({
                        "Musteri": row["musteri_adi"],
                        "Cikis_Il": satir.get("cikis_il",""),
                        "Varis_Il": satir.get("varis_il",""),
                        "KM": satir.get("km",""),
                        "Tur": satir.get("tur",""),
                        "Bas_Desi": satir.get("bas_desi",0),
                        "Bit_Desi": satir.get("bit_desi",0),
                        "KG": satir.get("buyuk",0),
                        "Birim_Fiyat": satir.get("birim_fiyat",0),
                        "Tutar": satir.get("tutar",0),
                    })
            except:
                pass

        if il_tur_detay:
            df_ilt = pd.DataFrame(il_tur_detay)

            itr1, itr2 = st.columns(2)
            with itr1:
                st.markdown("#### 🏙️ Çıkış İline Göre Dağılım")
                cikis_df = df_ilt[df_ilt["Cikis_Il"] != ""].groupby("Cikis_Il").agg(
                    Adet=("Tur","count"),
                    Toplam_Tutar=("Tutar","sum")
                ).reset_index().sort_values("Adet", ascending=False)
                cikis_df["Toplam_Tutar"] = cikis_df["Toplam_Tutar"].apply(lambda x: f"₺{x:,.2f}")
                cikis_df.columns = ["Çıkış İli","Teklif Adedi","Toplam Tutar"]
                st.dataframe(cikis_df, use_container_width=True, hide_index=True)

            with itr2:
                st.markdown("#### 🎯 Varış İline Göre Dağılım")
                varis_df = df_ilt[df_ilt["Varis_Il"] != ""].groupby("Varis_Il").agg(
                    Adet=("Tur","count"),
                    Toplam_Tutar=("Tutar","sum")
                ).reset_index().sort_values("Adet", ascending=False)
                varis_df["Toplam_Tutar"] = varis_df["Toplam_Tutar"].apply(lambda x: f"₺{x:,.2f}")
                varis_df.columns = ["Varış İli","Teklif Adedi","Toplam Tutar"]
                st.dataframe(varis_df, use_container_width=True, hide_index=True)

            st.markdown("#### 📦 Ürün Türüne Göre İl Analizi")
            filtre_tur = st.selectbox("Ürün Türü Seç:",
                ["Tümü"] + sorted(df_ilt["Tur"].dropna().unique().tolist()),
                key="il_tur_filtre")
            df_ilt_f = df_ilt if filtre_tur == "Tümü" else df_ilt[df_ilt["Tur"] == filtre_tur]

            tur_il_df = df_ilt_f.groupby(["Tur","Cikis_Il","Varis_Il"]).agg(
                Adet=("KG","count"),
                Ort_KG=("KG","mean"),
                Toplam_Tutar=("Tutar","sum")
            ).reset_index().sort_values("Toplam_Tutar", ascending=False)
            tur_il_df["Ort_KG"] = tur_il_df["Ort_KG"].apply(lambda x: f"{x:.2f}")
            tur_il_df["Toplam_Tutar"] = tur_il_df["Toplam_Tutar"].apply(lambda x: f"₺{x:,.2f}")
            tur_il_df.columns = ["Tür","Çıkış","Varış","Adet","Ort.KG","Toplam Tutar"]
            st.dataframe(tur_il_df, use_container_width=True, hide_index=True)

            # Tüm detay indir
            ilt_buf = io.BytesIO()
            pd.DataFrame(il_tur_detay).to_excel(ilt_buf, index=False)
            ilt_buf.seek(0)
            st.download_button("📥 İl-Tür Detay Excel İndir", data=ilt_buf,
                file_name=f"il_tur_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel", use_container_width=True)
        else:
            st.info("Teklif içi il/tür verisi bulunamadı.")
    except Exception as e:
        st.error(f"İl/Tür raporu hatası: {e}")
# -- TEKLIF OLUSTUR --
elif aktif == "teklif":
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

    URUN_TIPLERI = ["Koli","Sandik","Top","Cuval","Kasa","Palet","Diger","Manuel"]
    IL_LISTESI = ["","Istanbul","Ankara","Izmir","Bursa","Antalya","Adana","Konya",
        "Gaziantep","Mersin","Kayseri","Eskisehir","Diyarbakir","Samsun","Trabzon",
        "Erzurum","Sanliurfa","Manisa","Balikesir","Tekirdag","Kocaeli","Sakarya",
        "Denizli","Mugla","Hatay","Malatya","Kahramanmaras","Van","Elazig","Aydin",
        "Edirne","Canakkale","Afyonkarahisar","Isparta","Kutahya","Usak","Nevsehir",
        "Nigde","Aksaray","Yozgat","Sivas","Erzincan","Ordu","Amasya","Tokat","Corum",
        "Sinop","Kastamonu","Karabuk","Zonguldak","Bolu","Duzce","Yalova","Bilecik",
        "Kirklareli","Kirikkale","Cankiri","Karaman","Osmaniye","Kilis","Adiyaman",
        "Burdur","Rize","Giresun","Artvin","Mardin","Sirnak","Batman","Bitlis",
        "Mus","Bingol","Tunceli","Siirt","Hakkari","Agri","Igdir","Kars","Ardahan"]

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

    col_ekle, col_sil = st.columns([1,1])
    with col_ekle:
        if st.button("+ Satir Ekle", use_container_width=True, type="primary"):
            st.session_state["teklif_satir_n"] += 1
            st.rerun()
    with col_sil:
        if st.button("- Son Satiri Sil", use_container_width=True) and st.session_state["teklif_satir_n"] > 1:
            st.session_state["teklif_satir_n"] -= 1
            st.rerun()

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
        for txt, col in zip(["Urun","En","Boy","Yuk","Desi","Birim Fiyat"], hh):
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
                urun_adi = st.text_input(f"Urun adi {i+1}:", key=f"h_adi_{i}", placeholder="Urun adi")
            hesap_sonuclar.append({"urun": urun_adi, "en": en, "boy": boy, "yuk": yuk,
                                   "desi": desi, "birim_fiyat": birim_fiyat})
            # Canli guncelle
            hesap_desi[i] = desi
            hesap_bf[i]   = birim_fiyat
            hesap_urun[i] = urun_tip

    with right:
        st.markdown("#### TEKLIFIMIZ")
        th = st.columns([1.2,1.2,0.7,0.9,0.8,0.8,0.7,1.0])
        for txt, col in zip(["Cikis Ili","Varis Ili","KM","Tur","Bas Desi","Bit Desi","KG","Tutar"], th):
            col.markdown(f"**{txt}**")

        for i in range(n):
            h_desi = hesap_desi[i]
            h_bf   = hesap_bf[i]
            h_urun = hesap_urun[i]

            # Tur: her render'da hesaplamadaki urunu session_state'e yaz
            tur_key = f"t_tur_{i}"
            if h_urun in URUN_TIPLERI:
                st.session_state[tur_key] = h_urun

            tc = st.columns([1.2,1.2,0.7,0.9,0.8,0.8,0.7,1.0])
            cikis_il = tc[0].selectbox("", IL_LISTESI, key=f"t_cil_{i}", label_visibility="collapsed")
            varis_il = tc[1].selectbox("", IL_LISTESI, key=f"t_vil_{i}", label_visibility="collapsed")
            auto_km  = get_km(cikis_il, varis_il)
            tc[2].markdown(f"**{auto_km if auto_km else '-'}**")

            tur = tc[3].selectbox("", URUN_TIPLERI, key=tur_key, label_visibility="collapsed")
            bas_desi = tc[4].number_input("", min_value=0.0, step=0.5, key=f"t_bas_{i}", label_visibility="collapsed")

            # Bit desi: hesaplama desisi direkt goster
            tc[5].markdown(f"**{h_desi}**")
            bit_desi = h_desi

            kg = tc[6].number_input("", min_value=0.0, step=0.5, key=f"t_kg_{i}", label_visibility="collapsed")
            buyuk = max(kg, bit_desi)
            tutar = round(buyuk * h_bf, 2)
            tc[7].markdown(f"**{tutar:,.2f}**")
            toplam_tutar += tutar
            teklif_sonuclar.append({
                "cikis_il": cikis_il, "varis_il": varis_il, "km": auto_km,
                "tur": tur, "bas_desi": bas_desi, "bit_desi": bit_desi,
                "kg": kg, "buyuk": buyuk, "birim_fiyat": h_bf, "tutar": tutar
            })

    st.markdown(f"### Genel Toplam: {toplam_tutar:,.2f} TL")
    st.divider()

    if st.button("Teklifi Kaydet", use_container_width=True, type="primary"):
        if not hedef_musteri:
            st.warning("Musteri adi bos olamaz!")
        else:
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
    st.markdown("### Kayitli Teklifler")
    try:
        df_tek = db_read("teklifler", order_col="tarih")
        if not df_tek.empty:
            goster_cols = [c for c in ["id","tarih","musteri_adi","toplam_tutar","olusturan","notlar"] if c in df_tek.columns]
            df_tek_goster = df_tek[goster_cols].copy()
            if "toplam_tutar" in df_tek_goster.columns:
                df_tek_goster["toplam_tutar"] = df_tek_goster["toplam_tutar"].apply(lambda x: f"{float(x):,.2f} TL" if x else "0 TL")
            st.dataframe(df_tek_goster, use_container_width=True, hide_index=True)
            with st.expander("Teklif Detayini Gor"):
                teklif_id = st.number_input("Teklif ID:", min_value=1, step=1, key="goster_id")
                if st.button("Detay Goster"):
                    df_det = db_read("teklifler", filters={"id": teklif_id})
                    if not df_det.empty:
                        row_det = df_det.iloc[0]
                        st.markdown(f"**Musteri:** {row_det['musteri_adi']} | **Tarih:** {row_det['tarih']} | **Tutar:** {float(row_det['toplam_tutar']):,.2f} TL")
                        try:
                            data = json.loads(row_det['satirlar'])
                            if "teklif" in data:
                                st.markdown("**Teklif Satirlari:**")
                                st.dataframe(pd.DataFrame(data["teklif"]), use_container_width=True)
                            if "hesap" in data:
                                st.markdown("**Hesaplama Satirlari:**")
                                st.dataframe(pd.DataFrame(data["hesap"]), use_container_width=True)
                        except:
                            st.text(str(row[0]))
                    else:
                        st.error("Bu ID bulunamadi.")
        else:
            st.info("Henuz kayitli teklif yok.")
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
    import io
    import re

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
                                gsm_v      = temiz(row.get("gsm",""))
                                sabit_v    = temiz(row.get("sabit",""))
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
    import json as _aj

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
        m3.metric("Beklenen Ciro", f"₺{bek:,.0f}")
        m4.metric("Gerçekleşen", f"₺{ger:,.0f}", delta=f"₺{ger-bek:,.0f}")

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
                df_tek_an["toplam_tutar"] = df_tek_an["toplam_tutar"].apply(lambda x: f"₺{float(x):,.2f}")
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
                    import re as _re
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
    import json as _wa_json

    st.markdown("## 💬 WhatsApp Entegrasyonu")

    # ── BAĞLANTI AYARLARI ──────────────────────────────────────────────────────
    with st.sidebar:
        st.divider()
        st.markdown("### 📡 Waha Bağlantısı")
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
        import re
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
    st.markdown("## 📞 Telefon Kişiler & Rehber")

    # Temsilci Kartları
    with st.expander("👤 Satış Temsilcisi Kartları", expanded=False):
        st.markdown("#### Kayıtlı Temsilciler")
        df_tem = db_read("temsilciler", extra_sql="WHERE aktif=1 ORDER BY ad")
        if not df_tem.empty:
            st.dataframe(df_tem[["id","ad","soyad","telefon","email","bolge","unvan"]], 
                        use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### ➕ Yeni Temsilci Ekle")
        with st.form("temsilci_form"):
            tc1, tc2, tc3 = st.columns(3)
            t_ad     = tc1.text_input("Ad*")
            t_soyad  = tc1.text_input("Soyad")
            t_tel    = tc2.text_input("Telefon*", placeholder="05xxxxxxxxx")
            t_email  = tc2.text_input("Email")
            t_bolge  = tc3.text_input("Bölge", placeholder="İstanbul, Ankara...")
            t_unvan  = tc3.text_input("Ünvan", placeholder="Satış Temsilcisi")
            if st.form_submit_button("💾 Temsilci Kaydet", use_container_width=True):
                if t_ad and t_tel:
                    db_insert("temsilciler", {
                        "ad": t_ad, "soyad": t_soyad, "telefon": t_tel,
                        "email": t_email, "bolge": t_bolge, "unvan": t_unvan, "aktif": 1
                    })
                    st.success(f"✅ {t_ad} {t_soyad} eklendi!")
                    st.rerun()
                else:
                    st.warning("Ad ve telefon zorunlu!")

    st.divider()

    # Kişi Ekleme
    tab_rehber1, tab_rehber2, tab_rehber3 = st.tabs(["📋 Kişi Listesi", "➕ Kişi Ekle", "📥 Toplu İçe Aktar"])

    with tab_rehber1:
        df_kis = db_read("kisiler", extra_sql="ORDER BY ad")
        
        ara_kis = st.text_input("🔍 Kişi ara (Ad, Firma, Bölge):", key="kisiler_ara")
        if ara_kis:
            mask = df_kis.apply(lambda r: ara_kis.lower() in str(r).lower(), axis=1)
            df_kis = df_kis[mask]

        st.markdown(f"**{len(df_kis)} kişi**")

        if not df_kis.empty:
            for _, kisi in df_kis.iterrows():
                with st.container():
                    kc1, kc2, kc3, kc4, kc5 = st.columns([2, 2, 2, 1, 1])
                    kc1.markdown(f"**{kisi.get('ad','')} {kisi.get('soyad','')}**")
                    kc2.markdown(f"🏢 {kisi.get('firma','')}")
                    kc3.markdown(f"📍 {kisi.get('bolge','')}")
                    
                    tel = str(kisi.get('telefon','') or '').strip()
                    if tel:
                        # Telefon formatla
                        import re as _re
                        tel_temiz = _re.sub(r"[\s\-\(\)]", "", tel)
                        if tel_temiz.startswith("0"):
                            wa_no = "90" + tel_temiz[1:]
                        elif tel_temiz.startswith("+"):
                            wa_no = tel_temiz.replace("+","")
                        else:
                            wa_no = "90" + tel_temiz if len(tel_temiz) == 10 else tel_temiz
                        
                        wa_url_kis = f"https://wa.me/{wa_no}?text=Merhaba%20{kisi.get('ad','')}%20Bey/Hanım,"
                        kc4.link_button("📱 WA", wa_url_kis, use_container_width=True)
                        kc5.markdown(f"`{tel}`")
                    else:
                        kc4.markdown("—")
                    st.divider()
        else:
            st.info("Kişi bulunamadı. 'Kişi Ekle' sekmesinden ekleyin.")

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

            # Temsilci listesi
            df_tem2 = db_read("temsilciler", extra_sql="WHERE aktif=1 ORDER BY ad")
            tem_opts = ["—"] + [f"{r['ad']} {r['soyad']}" for _, r in df_tem2.iterrows()] if not df_tem2.empty else ["—"]
            k_temsilci = ke2.selectbox("Sorumlu Temsilci", tem_opts)
            k_notlar  = ke3.text_area("Notlar", height=80)
            k_kaynak  = ke1.selectbox("Kaynak", ["Manuel", "Sistem Müşterisi", "Referans", "Soğuk Arama", "Diğer"])

            if st.form_submit_button("💾 Kişiyi Kaydet", use_container_width=True, type="primary"):
                if k_ad and k_tel:
                    db_insert("kisiler", {
                        "ad": k_ad, "soyad": k_soyad, "telefon": k_tel,
                        "email": k_email, "firma": k_firma, "gorev": k_gorev,
                        "bolge": k_bolge, "temsilci": k_temsilci if k_temsilci != "—" else "",
                        "notlar": k_notlar, "kaynak": k_kaynak
                    })
                    st.success(f"✅ {k_ad} {k_soyad} eklendi!")
                    st.rerun()
                else:
                    st.warning("Ad ve telefon zorunlu!")

    with tab_rehber3:
        st.info("Excel şablonunu indirin, doldurun, yükleyin.")
        import io as _kio

        sablon_kis = pd.DataFrame([{
            "ad": "Ahmet", "soyad": "Yılmaz", "telefon": "05001234567",
            "email": "ahmet@firma.com", "firma": "ABC Ltd.",
            "gorev": "Satın Alma Müdürü", "bolge": "İstanbul", "notlar": ""
        }])
        sbuf = _kio.BytesIO()
        sablon_kis.to_excel(sbuf, index=False)
        sbuf.seek(0)
        st.download_button("📥 Şablon İndir", data=sbuf, 
                          file_name="kisiler_sablonu.xlsx", use_container_width=True)

        yukle_kis = st.file_uploader("Excel Yükle:", type=["xlsx","xls"], key="kisiler_yukle")
        if yukle_kis:
            df_yukle_kis = pd.read_excel(yukle_kis)
            st.dataframe(df_yukle_kis.head(5), use_container_width=True, hide_index=True)
            if st.button("🚀 İçe Aktar", use_container_width=True, type="primary"):
                sayac = 0
                for _, row in df_yukle_kis.iterrows():
                    if str(row.get("ad","")).strip():
                        db_insert("kisiler", {
                            "ad": str(row.get("ad","")), "soyad": str(row.get("soyad","")),
                            "telefon": str(row.get("telefon","")), "email": str(row.get("email","")),
                            "firma": str(row.get("firma","")), "gorev": str(row.get("gorev","")),
                            "bolge": str(row.get("bolge","")), "notlar": str(row.get("notlar","")),
                            "kaynak": "Excel"
                        })
                        sayac += 1
                st.success(f"✅ {sayac} kişi eklendi!")
                st.rerun()

# ── RANDEVULAR ────────────────────────────────────────────────────────────────
elif aktif == "randevu":
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
                            import re as _reh
                            ht = _reh.sub(r"[\s\-\(\)+]","", tem_tel_h)
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

            # WA uyarı linkleri
            st.markdown("#### 📱 WhatsApp Uyarı Gönder")
            for _, row in df_rand.head(20).iterrows():
                tem_tel_r = str(row.get("temsilci_tel","") or "")
                musteri_r = row.get("musteri_adi","")
                tarih_r = f"{row.get('randevu_tarihi','')} {row.get('randevu_saati','')}"
                bolge_r = row.get("bolge","")
                gorev_r = row.get("gorev","")
                temsilci_r = row.get("temsilci","")

                wc1, wc2, wc3 = st.columns([3,2,1])
                wc1.markdown(f"**{musteri_r}** — {tarih_r} — {temsilci_r}")
                wc2.markdown(f"📍 {bolge_r} | {gorev_r}")
                if tem_tel_r:
                    import re as _rew
                    twt = _rew.sub(r"[\s\-\(\)+]","", tem_tel_r)
                    if twt.startswith("0"): twt = "90" + twt[1:]
                    msg_w = f"📅 RANDEVU: {musteri_r}\n{tarih_r}\nBölge: {bolge_r}\nGörev: {gorev_r}"
                    wc3.link_button("📱 WA", f"https://wa.me/{twt}?text={msg_w.replace(' ','%20').replace(chr(10),'%0A')}", use_container_width=True)
                else:
                    wc3.markdown("📞 Tel yok")

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
                    st.success("✅ Randevu kaydedildi!")

                    if rand_tem_tel.strip():
                        import re as _re3
                        twt2 = _re3.sub(r"[\s\-\(\)+]","", rand_tem_tel.strip())
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
                        st.success("✅ Güncellendi!")
                        st.session_state.pop("rand_duzenle_row", None)
                        st.rerun()

                    if sil_btn:
                        sb = get_sb()
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
                    sb_m = get_sb()
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

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='position:fixed;bottom:0;left:0;right:0;background:#f0f2f6;padding:6px;text-align:center;font-size:11px;color:#888;z-index:999;'>"
    "MWCRMPRO v2.0 &nbsp;|&nbsp; "
    "<a href='tel:05400344228' style='color:#888;text-decoration:none;'>📞 5400344228</a>"
    " &nbsp;|&nbsp; "
    "<a href='mailto:osnenufu@gmail.com' style='color:#888;text-decoration:none;'>✉️ osnenufu@gmail.com</a>"
    " &nbsp;|&nbsp; "
    "<a href='https://wa.me/905400344228' target='_blank' style='color:#25D366;text-decoration:none;'>💬 WhatsApp</a>"
    "</div>",
    unsafe_allow_html=True
)