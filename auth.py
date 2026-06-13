import sqlite3
import hashlib

def check_login(username, password):
    # Şifreleri veritabanında olduğu gibi değil, hash (SHA-256) ile saklamak güvenlik içindir
    conn = sqlite3.connect("mw_crm_data.db")
    cursor = conn.cursor()
    
    # Şifreyi basitçe eşleştirme (Gerçek projede 'hashlib' ile şifreleme önerilir)
    cursor.execute("SELECT role FROM kullanicilar WHERE username=? AND password=?", (username, password))
    user = cursor.fetchone()
    conn.close()
    
    return user[0] if user else None

def add_user(username, password, role):
    conn = sqlite3.connect("mw_crm_data.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO kullanicilar (username, password, role) VALUES (?, ?, ?)", 
                       (username, password, role))
        conn.commit()
    except sqlite3.IntegrityError:
        print("Kullanıcı zaten mevcut!")
    conn.close()