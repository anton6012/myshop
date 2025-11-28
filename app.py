import os
import uuid
import hashlib
import urllib.parse
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from database import get_db
from config import SECRET_KEY, UPLOAD_FOLDER, ALLOWED_EXTENSIONS

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Helper functions
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def require_login(required_role=None):
    """Decorator untuk memerlukan login dan role tertentu"""
    def decorator(f):
        def decorated_function(*args, **kwargs):
            if not session.get("admin"):
                flash("Anda harus login terlebih dahulu!", "error")
                return redirect(url_for("login"))
            
            if required_role and session.get("admin_role") != required_role:
                if required_role == "superadmin" and session.get("admin_role") not in ["superadmin"]:
                    flash("Akses ditolak! Hanya Super Admin yang dapat mengakses halaman ini.", "error")
                    return redirect(url_for("admin_dashboard"))
                elif required_role == "admin" and session.get("admin_role") not in ["superadmin", "admin"]:
                    flash("Akses ditolak! Anda tidak memiliki izin untuk mengakses halaman ini.", "error")
                    return redirect(url_for("admin_dashboard"))
            
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

# ==============================
# FILTER RUPIAH - DIPERBAIKI
# ==============================
@app.template_filter('rupiah')
def rupiah_format(value):
    try:
        value = int(value)
        return f"Rp {value:,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

# TAMBAHKAN FILTER format_rupiah (alias untuk rupiah)
@app.template_filter('format_rupiah')
def format_rupiah(value):
    try:
        value = int(value)
        return f"Rp {value:,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

# ==============================
# HALAMAN CUSTOMER
# ==============================
@app.route("/")
def home():
    conn = get_db()
    produk = conn.execute("SELECT * FROM produk WHERE stok > 0 ORDER BY id DESC").fetchall()
    return render_template("index.html", produk=produk)

@app.route("/produk/<int:pid>")
def produk_detail(pid):
    conn = get_db()
    p = conn.execute("SELECT * FROM produk WHERE id=?", (pid,)).fetchone()
    if not p:
        return "Produk tidak ditemukan", 404
    return render_template("produk_detail.html", p=p)

# ==============================
# KERANJANG BELANJA
# ==============================
@app.route("/add/<int:id>")
def add_to_cart(id):
    conn = get_db()
    produk = conn.execute("SELECT * FROM produk WHERE id=?", (id,)).fetchone()
    
    if not produk:
        flash("Produk tidak ditemukan!", "error")
        return redirect(request.referrer or url_for("home"))
    
    # Validasi stok
    cart = session.get("cart", {})
    current_qty = cart.get(str(id), 0)
    
    if produk["stok"] <= 0:
        flash(f"Maaf, {produk['nama']} sedang habis!", "error")
        return redirect(request.referrer or url_for("home"))
    
    if current_qty >= produk["stok"]:
        flash(f"Maaf, stok {produk['nama']} tidak mencukupi! Stok tersedia: {produk['stok']}", "error")
        return redirect(request.referrer or url_for("home"))
    
    cart[str(id)] = current_qty + 1
    session["cart"] = cart
    flash(f"{produk['nama']} berhasil ditambahkan ke keranjang!", "success")
    return redirect(request.referrer or url_for("home"))

@app.route("/api/add_to_cart/<int:id>", methods=["POST"])
def api_add_to_cart(id):
    conn = get_db()
    produk = conn.execute("SELECT * FROM produk WHERE id=?", (id,)).fetchone()
    
    if not produk:
        return jsonify({"status": "error", "message": "Produk tidak ditemukan"})
    
    # Validasi stok
    cart = session.get("cart", {})
    current_qty = cart.get(str(id), 0)
    
    if produk["stok"] <= 0:
        return jsonify({"status": "error", "message": f"Maaf, {produk['nama']} sedang habis!"})
    
    if current_qty >= produk["stok"]:
        return jsonify({"status": "error", "message": f"Stok {produk['nama']} tidak mencukupi! Stok tersedia: {produk['stok']}"})
    
    cart[str(id)] = current_qty + 1
    session["cart"] = cart
    
    return jsonify({
        "status": "success", 
        "total_qty": sum(cart.values()),
        "message": f"{produk['nama']} berhasil ditambahkan!"
    })

@app.route("/cart")
def cart():
    cart = session.get("cart", {})
    items = []
    total = 0

    conn = get_db()

    for pid, qty in cart.items():
        p = conn.execute("SELECT * FROM produk WHERE id=?", (pid,)).fetchone()
        if p:
            # Validasi stok - jika stok berkurang, sesuaikan quantity
            if qty > p["stok"]:
                if p["stok"] <= 0:
                    # Hapus item jika stok habis
                    del cart[pid]
                    flash(f"{p['nama']} dihapus dari keranjang karena stok habis", "warning")
                    continue
                else:
                    # Sesuaikan quantity dengan stok tersedia
                    cart[pid] = p["stok"]
                    qty = p["stok"]
                    flash(f"Quantity {p['nama']} disesuaikan dengan stok tersedia: {p['stok']}", "warning")
            
            subtotal = p["harga"] * qty
            total += subtotal
            items.append({
                "id": p["id"],
                "nama": p["nama"],
                "harga": p["harga"],
                "qty": qty,
                "subtotal": subtotal,
                "foto": p["foto"],
                "stok": p["stok"]
            })

    session["cart"] = cart
    return render_template("cart.html", items=items, total=total)

@app.route("/hapus_item/<int:id>")
def hapus_item(id):
    cart = session.get("cart", {})
    pid = str(id)
    if pid in cart:
        del cart[pid]
        flash("Item berhasil dihapus dari keranjang!", "success")
    session["cart"] = cart
    return redirect(url_for("cart"))

@app.route("/tambah_qty/<int:id>")
def tambah_qty(id):
    conn = get_db()
    produk = conn.execute("SELECT * FROM produk WHERE id=?", (id,)).fetchone()
    
    cart = session.get("cart", {})
    pid = str(id)
    
    if pid in cart:
        # Validasi stok sebelum menambah quantity
        if cart[pid] >= produk["stok"]:
            flash(f"Maaf, stok {produk['nama']} tidak mencukupi! Stok tersedia: {produk['stok']}", "error")
        else:
            cart[pid] += 1
            flash(f"Quantity {produk['nama']} berhasil ditambah!", "success")
    
    session["cart"] = cart
    return redirect(url_for("cart"))

@app.route("/kurangi_qty/<int:id>")
def kurangi_qty(id):
    cart = session.get("cart", {})
    pid = str(id)
    if pid in cart:
        cart[pid] -= 1
        if cart[pid] <= 0:
            del cart[pid]
            flash("Item berhasil dihapus dari keranjang!", "success")
        else:
            flash("Quantity berhasil dikurangi!", "success")
    session["cart"] = cart
    return redirect(url_for("cart"))

@app.route("/clear_cart")
def clear_cart():
    session["cart"] = {}
    flash("Keranjang berhasil dikosongkan!", "success")
    return redirect(url_for("cart"))

# ==============================
# CHECKOUT & WHATSAPP - DIPERBAIKI
# ==============================
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Keranjang belanja kosong!", "error")
        return redirect(url_for("cart"))
    
    conn = get_db()
    
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        alamat = request.form.get("alamat", "").strip()
        no_hp = request.form.get("no_hp", "").strip()
        catatan = request.form.get("catatan", "").strip()
        
        if not nama or not alamat or not no_hp:
            flash("Nama, alamat, dan nomor HP wajib diisi!", "error")
            return render_template("checkout_form.html", 
                                 nama=nama, alamat=alamat, no_hp=no_hp, catatan=catatan)
        
        # Simpan data customer ke session
        session["customer_data"] = {
            "nama": nama,
            "alamat": alamat,
            "no_hp": no_hp,
            "catatan": catatan
        }
        
        # Redirect ke process-checkout
        return redirect(url_for('process_checkout'))
    
    # Tampilkan form checkout
    customer_data = session.get("customer_data", {})
    
    # PERBAIKAN: Hitung total langsung dari session cart
    cart_total = 0
    total_qty = 0
    cart_items = []
    
    for pid, qty in cart.items():
        p = conn.execute("SELECT * FROM produk WHERE id=?", (pid,)).fetchone()
        if p:
            subtotal = p["harga"] * qty
            cart_total += subtotal
            total_qty += qty
            cart_items.append({
                "id": p["id"],
                "nama": p["nama"],
                "harga": p["harga"],
                "qty": qty,
                "subtotal": subtotal
            })
    
    return render_template("checkout_form.html", 
                         nama=customer_data.get("nama", ""),
                         alamat=customer_data.get("alamat", ""),
                         no_hp=customer_data.get("no_hp", ""),
                         catatan=customer_data.get("catatan", ""),
                         cart_items=cart_items,
                         cart_total=cart_total,  # Kirim total yang sudah dihitung
                         total_qty=total_qty)    # Kirim total quantity

@app.route("/process-checkout")
def process_checkout():
    """Process checkout dan kosongkan keranjang"""
    cart = session.get("cart", {})
    customer_data = session.get("customer_data", {})
    
    if not cart:
        flash("Keranjang belanja kosong!", "error")
        return redirect(url_for("cart"))
    
    if not customer_data:
        flash("Silakan isi data pengiriman terlebih dahulu!", "error")
        return redirect(url_for("checkout"))
    
    conn = get_db()
    items = []
    total = 0
    item_details = []
    
    # VALIDASI STOK SEBELUM CHECKOUT
    for pid, qty in cart.items():
        p = conn.execute("SELECT * FROM produk WHERE id=?", (pid,)).fetchone()
        if p:
            if qty > p["stok"]:
                if p["stok"] <= 0:
                    flash(f"{p['nama']} stok habis, dihapus dari keranjang", "error")
                    del cart[pid]
                    continue
                else:
                    flash(f"Quantity {p['nama']} disesuaikan dengan stok tersedia: {p['stok']}", "warning")
                    cart[pid] = p["stok"]
                    qty = p["stok"]
            
            subtotal = p["harga"] * qty
            total += subtotal
            items.append({
                "id": p["id"],
                "nama": p["nama"],
                "harga": p["harga"],
                "qty": qty,
                "subtotal": subtotal
            })
            item_details.append(f"• {p['nama']} (Rp {p['harga']:,}) x{qty} = Rp {subtotal:,}")
    
    # Update cart setelah validasi stok
    session["cart"] = cart
    
    # Jika cart kosong setelah validasi stok
    if not cart:
        flash("Keranjang kosong setelah validasi stok!", "error")
        return redirect(url_for("cart"))
    
    # Hitung ongkir dan total akhir
    ongkir = 0 if total >= 500000 else 15000
    total_akhir = total + ongkir
    
    # Format pesan untuk WhatsApp
    message = f"""Halo! Saya ingin memesan:

📦 *DETAIL PESANAN:*
{chr(10).join(item_details)}

📊 *RINGKASAN:*
Subtotal: Rp {total:,}
Ongkos Kirim: {'GRATIS' if ongkir == 0 else f'Rp {ongkir:,}'}
*TOTAL: Rp {total_akhir:,}*

👤 *DATA PELANGGAN:*
Nama: {customer_data['nama']}
Alamat: {customer_data['alamat']}
No. HP: {customer_data['no_hp']}""" + (f"\nCatatan: {customer_data['catatan']}" if customer_data.get('catatan') else "") + """

Apakah pesanan ini ready dan bisa dikirim?"""
    
    encoded_message = urllib.parse.quote(message)
    whatsapp_number = "6285259805247"  # Ganti dengan nomor WhatsApp toko Anda
    wa_url = f"https://wa.me/{whatsapp_number}?text={encoded_message}"
    
    try:
        # UPDATE STOK DI DATABASE
        for pid, qty in cart.items():
            conn.execute("""
                UPDATE produk SET stok = stok - ? WHERE id = ?
            """, (qty, int(pid)))
        conn.commit()
        
        # KOSONGKAN KERANJANG SETELAH BERHASIL UPDATE STOK
        session["cart"] = {}
        
        # Simpan data untuk riwayat (opsional)
        session["last_order"] = {
            "customer_data": customer_data,
            "items": items,
            "total": total_akhir,
            "timestamp": datetime.now().isoformat()
        }
        
        # Hapus customer_data session agar tidak tersimpan untuk order berikutnya
        if "customer_data" in session:
            session.pop("customer_data")
            
        # Redirect ke halaman checkout.html (yang sudah Anda punya)
        return render_template("checkout.html", wa_url=wa_url)
        
    except Exception as e:
        conn.rollback()
        flash(f"Error saat memproses pesanan: {str(e)}", "error")
        return redirect(url_for("cart"))

# ==============================
# MULTI USER ADMIN SYSTEM
# ==============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_password = hash_password(password)

        conn = get_db()
        admin = conn.execute(
            "SELECT * FROM admin WHERE username=? AND password=? AND is_active=1",
            (username, hashed_password)
        ).fetchone()

        if admin:
            # Update last login
            conn.execute(
                "UPDATE admin SET last_login = CURRENT_TIMESTAMP WHERE id=?",
                (admin["id"],)
            )
            conn.commit()
            
            session["admin"] = True
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            session["admin_role"] = admin["role"]
            session["admin_email"] = admin["email"]
            
            flash(f"Login berhasil! Selamat datang {admin['username']} ({admin['role']})", "success")
            return redirect("/admin")
        else:
            return render_template("login.html", error="Username atau password salah!")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logout berhasil!", "info")
    return redirect("/login")

# ==============================
# ADMIN MANAGEMENT (Super Admin Only)
# ==============================
@app.route("/admin/kelola-admin")
@require_login("superadmin")
def kelola_admin():
    conn = get_db()
    admins = conn.execute("""
        SELECT id, username, email, role, is_active, created_at, last_login 
        FROM admin ORDER BY created_at DESC
    """).fetchall()
    
    return render_template("kelola_admin.html", admins=admins)

@app.route("/admin/tambah-admin", methods=["GET", "POST"])
@require_login("superadmin")
def tambah_admin():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]
        
        if not username or not email or not password:
            flash("Semua field wajib diisi!", "error")
            return render_template("tambah_admin.html")
        
        if len(password) < 6:
            flash("Password minimal 6 karakter!", "error")
            return render_template("tambah_admin.html")
        
        hashed_password = hash_password(password)
        
        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO admin (username, email, password, role) 
                VALUES (?, ?, ?, ?)
            """, (username, email, hashed_password, role))
            conn.commit()
            flash(f"Admin {username} berhasil ditambahkan!", "success")
            return redirect(url_for("kelola_admin"))
        except sqlite3.IntegrityError:
            flash("Username atau email sudah digunakan!", "error")
            return render_template("tambah_admin.html")
    
    return render_template("tambah_admin.html")

@app.route("/admin/edit-admin/<int:id>", methods=["GET", "POST"])
@require_login("superadmin")
def edit_admin(id):
    conn = get_db()
    admin = conn.execute("SELECT * FROM admin WHERE id=?", (id,)).fetchone()
    
    if not admin:
        flash("Admin tidak ditemukan!", "error")
        return redirect(url_for("kelola_admin"))
    
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        role = request.form["role"]
        is_active = request.form.get("is_active", 0)
        
        conn.execute("""
            UPDATE admin SET username=?, email=?, role=?, is_active=?
            WHERE id=?
        """, (username, email, role, is_active, id))
        conn.commit()
        
        flash(f"Admin {username} berhasil diupdate!", "success")
        return redirect(url_for("kelola_admin"))
    
    return render_template("edit_admin.html", admin=admin)

@app.route("/admin/reset-password/<int:id>", methods=["POST"])
@require_login("superadmin")
def reset_password_admin(id):
    new_password = request.form["new_password"]
    
    if len(new_password) < 6:
        flash("Password minimal 6 karakter!", "error")
        return redirect(url_for("kelola_admin"))
    
    hashed_password = hash_password(new_password)
    
    conn = get_db()
    conn.execute("UPDATE admin SET password=? WHERE id=?", (hashed_password, id))
    conn.commit()
    
    flash("Password berhasil direset!", "success")
    return redirect(url_for("kelola_admin"))

@app.route("/admin/hapus-admin/<int:id>")
@require_login("superadmin")
def hapus_admin(id):
    # Prevent self-deletion
    if id == session.get("admin_id"):
        flash("Tidak dapat menghapus akun sendiri!", "error")
        return redirect(url_for("kelola_admin"))
    
    conn = get_db()
    conn.execute("DELETE FROM admin WHERE id=?", (id,))
    conn.commit()
    
    flash("Admin berhasil dihapus!", "success")
    return redirect(url_for("kelola_admin"))

# ==============================
# ADMIN DASHBOARD & PRODUK (Role-based)
# ==============================
@app.route("/admin")
@require_login()
def admin_dashboard():
    conn = get_db()
    
    # Stats untuk dashboard
    total_produk = conn.execute("SELECT COUNT(*) as count FROM produk").fetchone()["count"]
    total_stok = conn.execute("SELECT SUM(stok) as total FROM produk").fetchone()["total"] or 0
    total_admin = conn.execute("SELECT COUNT(*) as count FROM admin WHERE is_active=1").fetchone()["count"]
    
    # Produk terbaru (max 5)
    produk = conn.execute("SELECT * FROM produk ORDER BY id DESC LIMIT 5").fetchall()
    
    return render_template("admin_dashboard.html", 
                         produk=produk,
                         total_produk=total_produk,
                         total_stok=total_stok,
                         total_admin=total_admin)

@app.route("/admin/produk")
@require_login()
def admin_produk():
    conn = get_db()
    
    # Staff hanya bisa lihat produk yang mereka buat
    if session.get("admin_role") == "staff":
        produk = conn.execute("""
            SELECT * FROM produk WHERE created_by = ? ORDER BY id DESC
        """, (session["admin_id"],)).fetchall()
    else:
        produk = conn.execute("SELECT * FROM produk ORDER BY id DESC").fetchall()
    
    return render_template("admin_produk.html", produk=produk)

@app.route("/admin/add", methods=["GET", "POST"])
@require_login()
def admin_add():
    if request.method == "POST":
        nama = request.form["nama"]
        harga = request.form["harga"]
        deskripsi = request.form["deskripsi"]
        kategori = request.form.get("kategori", "")
        stok = request.form.get("stok", 0)

        if not nama or not harga:
            return render_template("admin_add.html", error="Nama dan harga wajib diisi!")

        filename = ""
        foto = request.files["foto"]
        
        if foto and foto.filename != "":
            if allowed_file(foto.filename):
                ext = foto.filename.rsplit(".", 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                foto.save(filepath)
            else:
                return render_template("admin_add.html", error="Format file tidak diizinkan!")

        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO produk (nama, harga, deskripsi, foto, kategori, stok, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (nama, int(harga), deskripsi, filename, kategori, int(stok), session["admin_id"]))
            conn.commit()
            flash("Produk berhasil ditambahkan!", "success")
            return redirect("/admin")
        except Exception as e:
            return render_template("admin_add.html", error=f"Error: {str(e)}")

    return render_template("admin_add.html")

@app.route("/admin/produk/edit/<int:id>", methods=["GET", "POST"])
@require_login()
def admin_edit(id):
    conn = get_db()
    produk = conn.execute("SELECT * FROM produk WHERE id=?", (id,)).fetchone()

    if not produk:
        return "Produk tidak ditemukan", 404
    
    # Staff hanya bisa edit produk mereka sendiri
    if session.get("admin_role") == "staff" and produk["created_by"] != session["admin_id"]:
        flash("Anda hanya dapat mengedit produk yang Anda buat!", "error")
        return redirect("/admin")

    if request.method == "POST":
        nama = request.form["nama"]
        harga = request.form["harga"]
        deskripsi = request.form["deskripsi"]
        kategori = request.form.get("kategori", "")
        stok = request.form.get("stok", 0)

        filename = produk["foto"]
        foto = request.files["foto"]
        
        if foto and foto.filename != "":
            if allowed_file(foto.filename):
                ext = foto.filename.rsplit(".", 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                foto.save(filepath)

        conn.execute("""
            UPDATE produk SET nama=?, harga=?, deskripsi=?, kategori=?, foto=?, stok=?, updated_at=CURRENT_TIMESTAMP 
            WHERE id=?
        """, (nama, int(harga), deskripsi, kategori, filename, int(stok), id))

        conn.commit()
        flash("Produk berhasil diupdate!", "success")
        return redirect("/admin")

    return render_template("admin_edit.html", produk=produk)

@app.route("/admin/produk/delete/<int:id>")
@require_login()
def admin_delete(id):
    conn = get_db()
    produk = conn.execute("SELECT * FROM produk WHERE id=?", (id,)).fetchone()
    
    if not produk:
        flash("Produk tidak ditemukan!", "error")
        return redirect("/admin")
    
    # Staff hanya bisa hapus produk mereka sendiri
    if session.get("admin_role") == "staff" and produk["created_by"] != session["admin_id"]:
        flash("Anda hanya dapat menghapus produk yang Anda buat!", "error")
        return redirect("/admin")

    conn.execute("DELETE FROM produk WHERE id=?", (id,))
    conn.commit()

    flash("Produk berhasil dihapus!", "success")
    return redirect("/admin")

# ==============================
# GANTI PASSWORD (All Admin)
# ==============================
@app.route("/admin/ganti-password", methods=["GET", "POST"])
@require_login()
def admin_ganti_password():
    if request.method == "POST":
        password_lama = request.form["password_lama"]
        password_baru = request.form["password_baru"]
        konfirmasi_password = request.form["konfirmasi_password"]
        
        if not password_lama or not password_baru or not konfirmasi_password:
            flash("Semua field harus diisi!", "error")
            return render_template("admin_ganti_password.html")
        
        if password_baru != konfirmasi_password:
            flash("Password baru dan konfirmasi password tidak cocok!", "error")
            return render_template("admin_ganti_password.html")
        
        if len(password_baru) < 6:
            flash("Password baru minimal 6 karakter!", "error")
            return render_template("admin_ganti_password.html")
        
        conn = get_db()
        admin = conn.execute(
            "SELECT * FROM admin WHERE id=?", 
            (session["admin_id"],)
        ).fetchone()
        
        if admin["password"] != hash_password(password_lama):
            flash("Password lama salah!", "error")
            return render_template("admin_ganti_password.html")
        
        new_hashed_password = hash_password(password_baru)
        conn.execute(
            "UPDATE admin SET password=? WHERE id=?",
            (new_hashed_password, session["admin_id"])
        )
        conn.commit()
        
        flash("Password berhasil diubah!", "success")
        return redirect("/admin")
    
    return render_template("admin_ganti_password.html")

if __name__ == "__main__":
    app.run(debug=True)