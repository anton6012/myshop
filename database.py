import os
import sqlite3
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data","database.db")

print("Database location:", DB_PATH)

def get_db():
    conn = sqlite3.connect("DB_PATH")
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db()
    
    # Table admin dengan role-based
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'staff',  -- 'superadmin', 'admin', 'staff'
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)

    # Table produk
    conn.execute("""
        CREATE TABLE IF NOT EXISTS produk (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nama TEXT NOT NULL, 
            harga INTEGER NOT NULL, 
            foto TEXT, 
            deskripsi TEXT,
            kategori TEXT,
            stok INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES admin (id)
        )
    """)

    # Insert superadmin default
    hashed_password = hash_password("admin123")
    conn.execute("""
        INSERT OR IGNORE INTO admin (id, username, email, password, role) 
        VALUES (1, 'superadmin', 'superadmin@myshop.com', ?, 'superadmin')
    """, (hashed_password,))
    
    # Insert sample admin
    conn.execute("""
        INSERT OR IGNORE INTO admin (id, username, email, password, role) 
        VALUES (2, 'admin', 'admin@myshop.com', ?, 'admin')
    """, (hashed_password,))
    
    # Insert sample staff
    staff_password = hash_password("staff123")
    conn.execute("""
        INSERT OR IGNORE INTO admin (id, username, email, password, role) 
        VALUES (3, 'staff', 'staff@myshop.com', ?, 'staff')
    """, (staff_password,))

    # Insert sample products
    conn.execute("""
        INSERT OR IGNORE INTO produk (id, nama, harga, deskripsi, kategori, stok, foto, created_by)
        VALUES 
        (1, 'Laptop Gaming', 12000000, 'Laptop gaming dengan specs tinggi', 'Elektronik', 10, 'laptop.jpg', 1),
        (2, 'Smartphone', 5000000, 'Smartphone terbaru dengan kamera canggih', 'Elektronik', 15, 'phone.jpg', 1),
        (3, 'T-Shirt Casual', 150000, 'Kaos casual bahan cotton combed', 'Fashion', 50, 'tshirt.jpg', 2),
        (4, 'Sepatu Sneakers', 350000, 'Sepatu sneakers trendy dan nyaman', 'Fashion', 25, 'shoes.jpg', 2)
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database berhasil diinisialisasi!")