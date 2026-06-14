import streamlit as st
import sqlite3
import pandas as pd

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
    conn = get_conn()
    conn.execute('''CREATE TABLE IF NOT EXISTS kullanicilar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kullanici_adi TEXT UNIQUE NOT NULL,
        sifre TEXT NOT NULL,
        rol TEXT DEFAULT "kullanici")''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cari_kartlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        firma TEXT, yetkili TEXT, gsm TEXT, sabit TEXT, email TEXT,
        adres TEXT, ilce TEXT, il TEXT, durum TEXT, temsilci TEXT,
        islem_asamasi TEXT, silindi INTEGER DEFAULT 0,
        olusturan TEXT)''')
    try:
        conn.execute("ALTER TABLE cari_kartlar ADD COLUMN olusturan TEXT")
    except:
        pass
    try:
        conn.execute("INSERT INTO kullanicilar (kullanici_adi, sifre, rol) VALUES (?,?,?)",
                     ("admin", "admin123", "admin"))
    except:
        pass
    conn.commit()
    conn.close()

init_db()

# ── GİRİŞ ────────────────────────────────────────────────────────────────────
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
                conn = get_conn()
                row = conn.execute(
                    "SELECT * FROM kullanicilar WHERE kullanici_adi=? AND sifre=?",
                    (kullanici, sifre)).fetchone()
                conn.close()
                if row:
                    st.session_state["giris"] = True
                    st.session_state["kullanici"] = kullanici
                    st.session_state["rol"] = row[3]
                    st.session_state["aktif_tab"] = "liste"
                    st.rerun()
                else:
                    st.error("Kullanıcı adı veya şifre hatalı!")

def cikis():
    for k in ["giris","kullanici","rol","aktif_tab","kayit_mesaj"]:
        st.session_state.pop(k, None)
    st.rerun()

# ── SESSION STATE ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="MWCRMPRO", layout="wide")

if "giris" not in st.session_state:
    st.session_state["giris"] = False
if "kullanici" not in st.session_state:
    st.session_state["kullanici"] = ""
if "rol" not in st.session_state:
    st.session_state["rol"] = ""
if "aktif_tab" not in st.session_state:
    st.session_state["aktif_tab"] = "yeni"
if "kayit_mesaj" not in st.session_state:
    st.session_state["kayit_mesaj"] = ""

if not st.session_state["giris"]:
    giris_ekrani()
    st.stop()

# ── ÜSTBAR ────────────────────────────────────────────────────────────────────
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
tab_listesi = ["yeni", "liste", "arsiv"]
tab_etiketler = {"yeni": "➕ Yeni Kart Ekle", "liste": "📋 Cari Liste / Düzenle", "arsiv": "🗃️ Arşiv (Silinenler)"}
if st.session_state["rol"] == "admin":
    tab_listesi.append("kullanici")
    tab_etiketler["kullanici"] = "👥 Kullanıcı Yönetimi"

cols = st.columns(len(tab_listesi))
for i, tab_key in enumerate(tab_listesi):
    with cols[i]:
        aktif = st.session_state["aktif_tab"] == tab_key
        if st.button(
            tab_etiketler[tab_key],
            use_container_width=True,
            type="primary" if aktif else "secondary",
            key=f"tab_btn_{tab_key}"
        ):
            st.session_state["aktif_tab"] = tab_key
            st.rerun()

st.divider()
aktif = st.session_state["aktif_tab"]

# ── YENİ KART EKLE ───────────────────────────────────────────────────────────
if aktif == "yeni":
    with st.form("yeni_kart_form"):
        col1, col2, col3 = st.columns(3)
        firma    = col1.text_input("Firma Adı")
        yetkili  = col1.text_input("Yetkili")
        gsm      = col2.text_input("GSM")
        sabit    = col2.text_input("Sabit Tel")
        email    = col3.text_input("E-Mail")
        il_listesi = sorted(ILLER_ILCELER.keys())
        il   = col3.selectbox("İl", il_listesi)
        ilce = col3.selectbox("İlçe", ILLER_ILCELER[il])
        durum    = col1.selectbox("Durum", ["Aktif", "Hedef", "Pasif"])
        temsilci = col2.text_input("Temsilci")
        asama    = col3.selectbox("İşlem Aşaması", ["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"])
        adres    = st.text_area("Adres")

        if st.form_submit_button("💾 Cari Kartı Kaydet"):
            if not firma:
                st.warning("Firma adı boş bırakılamaz!")
            else:
                conn = get_conn()
                conn.execute(
                    "INSERT INTO cari_kartlar (firma,yetkili,gsm,sabit,email,adres,ilce,il,durum,temsilci,islem_asamasi,olusturan) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (firma, yetkili, gsm, sabit, email, adres, ilce, il, durum, temsilci, asama, st.session_state["kullanici"])
                )
                conn.commit(); conn.close()
                st.session_state["aktif_tab"] = "liste"
                st.session_state["kayit_mesaj"] = f"✅ '{firma}' başarıyla kaydedildi!"
                st.rerun()

# ── CARİ LİSTE ───────────────────────────────────────────────────────────────
elif aktif == "liste":
    if st.session_state.get("kayit_mesaj"):
        st.success(st.session_state["kayit_mesaj"])
        st.session_state["kayit_mesaj"] = ""

    conn = get_conn()
    df = pd.read_sql("SELECT * FROM cari_kartlar WHERE silindi=0 OR silindi='0' OR silindi IS NULL ORDER BY tarih DESC", conn)
    conn.close()

    st.markdown(f"**Toplam {len(df)} aktif kayıt**")

    ara = st.text_input("🔍 Firma, yetkili veya il ara...", key="ara")
    if ara:
        mask = df.apply(lambda r: ara.lower() in str(r).lower(), axis=1)
        df = df[mask]

    if df.empty:
        st.info("Kayıt bulunamadı.")
    else:
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "id":            st.column_config.NumberColumn("ID", disabled=True),
                "tarih":         st.column_config.TextColumn("Tarih", disabled=True),
                "olusturan":     st.column_config.TextColumn("Oluşturan", disabled=True),
                "silindi":       st.column_config.NumberColumn("Silindi", disabled=True),
                "durum":         st.column_config.SelectboxColumn("Durum", options=["Aktif","Hedef","Pasif"]),
                "islem_asamasi": st.column_config.SelectboxColumn("İşlem Aşaması", options=["İlk Temas","Teklif","Sözleşme","Kazanıldı","Kaybedildi"]),
            },
            key="cari_editor"
        )

        col_kaydet, col_arsiv = st.columns([2, 1])
        with col_kaydet:
            if st.button("💾 Tüm Değişiklikleri Kaydet", use_container_width=True):
                conn = get_conn()
                for _, row in edited_df.iterrows():
                    conn.execute("""UPDATE cari_kartlar SET
                        firma=?, yetkili=?, gsm=?, sabit=?, email=?,
                        adres=?, ilce=?, il=?, durum=?, temsilci=?, islem_asamasi=?
                        WHERE id=?""",
                        (row.get("firma"), row.get("yetkili"), row.get("gsm"),
                         row.get("sabit"), row.get("email"), row.get("adres"),
                         row.get("ilce"), row.get("il"), row.get("durum"),
                         row.get("temsilci"), row.get("islem_asamasi"), row.get("id")))
                conn.commit(); conn.close()
                st.success("✅ Değişiklikler kaydedildi!")
                st.rerun()

        with col_arsiv:
            with st.expander("🗑️ Arşive Gönder"):
                target_id = st.number_input("Arşive atılacak ID:", min_value=1, step=1, key="arsiv_id")
                if st.button("Arşive Gönder", use_container_width=True):
                    conn = get_conn()
                    conn.execute("UPDATE cari_kartlar SET silindi=1 WHERE id=?", (target_id,))
                    conn.commit(); conn.close()
                    st.success(f"ID {target_id} arşive gönderildi.")
                    st.rerun()

# ── ARŞİV ─────────────────────────────────────────────────────────────────────
elif aktif == "arsiv":
    conn = get_conn()
    df_arsiv = pd.read_sql("SELECT * FROM cari_kartlar WHERE silindi=1 OR silindi='1' ORDER BY tarih DESC", conn)
    conn.close()

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
                    conn = get_conn()
                    conn.execute("UPDATE cari_kartlar SET silindi=0 WHERE id=?", (restore_id,))
                    conn.commit(); conn.close()
                    st.success(f"ID {restore_id} geri alındı.")
                    st.rerun()

        with col_guncelle:
            if st.button("💾 Arşiv Değişikliklerini Kaydet", use_container_width=True):
                conn = get_conn()
                for _, row in edited_arsiv.iterrows():
                    conn.execute("""UPDATE cari_kartlar SET
                        firma=?, yetkili=?, gsm=?, sabit=?, email=?,
                        adres=?, ilce=?, il=?, durum=?, temsilci=?, islem_asamasi=?
                        WHERE id=?""",
                        (row.get("firma"), row.get("yetkili"), row.get("gsm"),
                         row.get("sabit"), row.get("email"), row.get("adres"),
                         row.get("ilce"), row.get("il"), row.get("durum"),
                         row.get("temsilci"), row.get("islem_asamasi"), row.get("id")))
                conn.commit(); conn.close()
                st.success("✅ Arşiv güncellendi!")
                st.rerun()

# ── KULLANICI YÖNETİMİ ───────────────────────────────────────────────────────
elif aktif == "kullanici" and st.session_state["rol"] == "admin":
    st.subheader("Kullanıcı Listesi")
    conn = get_conn()
    df_kul = pd.read_sql("SELECT id, kullanici_adi, rol FROM kullanicilar", conn)
    conn.close()

    edited_kul = st.data_editor(
        df_kul,
        use_container_width=True,
        column_config={
            "id":  st.column_config.NumberColumn("ID", disabled=True),
            "rol": st.column_config.SelectboxColumn("Rol", options=["admin","kullanici"]),
        },
        key="kul_editor"
    )

    if st.button("💾 Kullanıcı Değişikliklerini Kaydet"):
        conn = get_conn()
        for _, row in edited_kul.iterrows():
            conn.execute("UPDATE kullanicilar SET kullanici_adi=?, rol=? WHERE id=?",
                         (row["kullanici_adi"], row["rol"], row["id"]))
        conn.commit(); conn.close()
        st.success("Kullanıcılar güncellendi!")
        st.rerun()

    st.divider()
    st.subheader("Yeni Kullanıcı Ekle")
    with st.form("yeni_kullanici_form"):
        c1, c2, c3 = st.columns(3)
        yeni_kadi  = c1.text_input("Kullanıcı Adı")
        yeni_sifre = c2.text_input("Şifre")
        yeni_rol   = c3.selectbox("Rol", ["kullanici","admin"])
        if st.form_submit_button("➕ Kullanıcı Ekle"):
            if yeni_kadi and yeni_sifre:
                try:
                    conn = get_conn()
                    conn.execute("INSERT INTO kullanicilar (kullanici_adi,sifre,rol) VALUES (?,?,?)",
                                 (yeni_kadi, yeni_sifre, yeni_rol))
                    conn.commit(); conn.close()
                    st.success(f"'{yeni_kadi}' eklendi!")
                    st.rerun()
                except:
                    st.error("Bu kullanıcı adı zaten mevcut!")
            else:
                st.warning("Kullanıcı adı ve şifre boş olamaz!")
