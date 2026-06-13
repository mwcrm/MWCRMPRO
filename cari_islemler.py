import streamlit as st
import sqlite3
import pandas as pd

def cari_sayfasi():
    st.subheader("Cari Kart Yönetim Merkezi")
    
    tab1, tab2, tab3 = st.tabs(["Yeni Kart Ekle", "Cari Listesi / Düzenle", "Arşiv (Silinenler)"])

    # 1. SEKME: EKLEME
    with tab1:
        with st.form("yeni_kart"):
            c1, c2 = st.columns(2)
            firma = c1.text_input("Firma Adı")
            il = c1.selectbox("İl", ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Diğer"]) # Burayı genişletebilirsin
            ilce = c2.text_input("İlçe")
            gsm = c2.text_input("GSM")
            # ... diğer tüm alanları buraya ekleyebilirsin ...
            
            if st.form_submit_button("Cari Kartı Kaydet"):
                conn = sqlite3.connect("mw_crm_data.db")
                conn.execute("INSERT INTO cari_kartlar (firma, il, ilce, gsm) VALUES (?,?,?,?)", (firma, il, ilce, gsm))
                conn.commit(); conn.close()
                st.success("Kayıt Başarılı!")

    # 2. SEKME: LİSTELEME VE DÜZENLEME
    with tab2:
        conn = sqlite3.connect("mw_crm_data.db")
        df = pd.read_sql("SELECT * FROM cari_kartlar WHERE silindi=0", conn)
        conn.close()
        
        # Manuel düzenleme için 'data_editor' (Harika bir özellik!)
        edited_df = st.data_editor(df, num_rows="dynamic")
        
        if st.button("Değişiklikleri Kaydet"):
            conn = sqlite3.connect("mw_crm_data.db")
            edited_df.to_sql("cari_kartlar", conn, if_exists="replace", index=False)
            conn.commit(); conn.close()
            st.success("Tüm değişiklikler kaydedildi!")

        # Silme (Arşive atma)
        id_to_del = st.number_input("Arşive atılacak Cari ID:", step=1)
        if st.button("Seçili Kartı Arşive Gönder"):
            conn = sqlite3.connect("mw_crm_data.db")
            conn.execute("UPDATE cari_kartlar SET silindi=1 WHERE id=?", (id_to_del,))
            conn.commit(); conn.close()
            st.rerun()

    # 3. SEKME: ARŞİV
    with tab3:
        conn = sqlite3.connect("mw_crm_data.db")
        df_arsiv = pd.read_sql("SELECT * FROM cari_kartlar WHERE silindi=1", conn)
        conn.close()
        st.dataframe(df_arsiv)
        
        id_to_restore = st.number_input("Geri getirilecek Cari ID:", step=1)
        if st.button("Arşivden Geri Getir"):
            conn = sqlite3.connect("mw_crm_data.db")
            conn.execute("UPDATE cari_kartlar SET silindi=0 WHERE id=?", (id_to_restore,))
            conn.commit(); conn.close()
            st.rerun()