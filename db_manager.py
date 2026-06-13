import sqlite3
import shutil
import os
from datetime import datetime

DB_FILE = "mw_crm_data.db"
BACKUP_DIR = "yedekler"

def connect_db():
    # Yedekleme klasörü yoksa oluştur
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    # Her bağlantıda yedek al
    if os.path.exists(DB_FILE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(DB_FILE, os.path.join(BACKUP_DIR, f"backup_{timestamp}.db"))
        
    return sqlite3.connect(DB_FILE)

def init_tables():
    conn = connect_db()
    cursor = conn.cursor()
    # Müşteri tablosu
    cursor.execute('''CREATE TABLE IF NOT EXISTS musteriler (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tarih DATETIME DEFAULT CURRENT_TIMESTAMP,
                        ad_soyad TEXT,
                        telefon TEXT,
                        email TEXT,
                        durum TEXT,
                        aciklama TEXT,
                        is_active INTEGER DEFAULT 1,
                        is_deleted INTEGER DEFAULT 0)''')
    # Kullanıcı tablosu
    cursor.execute('''CREATE TABLE IF NOT EXISTS kullanicilar (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT,
                        role TEXT)''')
    conn.commit()
    conn.close()