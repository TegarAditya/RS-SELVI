from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from pymongo import MongoClient, DESCENDING, ASCENDING
from bson.objectid import ObjectId
from functools import wraps
from datetime import datetime
import pandas
from xhtml2pdf import pisa
import os
import locale
import logging
import bcrypt
import re
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

app = Flask(__name__)
app.secret_key = 'VPgjvL6yVtLE7Ev0JiDyAAuMV2asjuY3'

client = MongoClient('mongodb://selvi:selvi@ac-ou90izj-shard-00-00.37a1b2k.mongodb.net:27017,ac-ou90izj-shard-00-01.37a1b2k.mongodb.net:27017,ac-ou90izj-shard-00-02.37a1b2k.mongodb.net:27017/?ssl=true&replicaSet=atlas-4a46gy-shard-0&authSource=admin&retryWrites=true&w=majority&appName=Cluster0')
db = client['inventory_app']
users_collection = db['users']
roles_collection = db['roles']
categories_collection = db['categories']
items_collection = db['items']
incoming_transactions_collection = db['incoming_transactions']
outgoing_transactions_collection = db['outgoing_transactions']

client2 = MongoClient('mongodb://xyla:xyla@ac-8gpxh2x-shard-00-00.fvn8oip.mongodb.net:27017,ac-8gpxh2x-shard-00-01.fvn8oip.mongodb.net:27017,ac-8gpxh2x-shard-00-02.fvn8oip.mongodb.net:27017/?ssl=true&replicaSet=atlas-wrnuk2-shard-0&authSource=admin&retryWrites=true&w=majority&appName=Cluster0/RSUD_DR_Darsono')
db2 = client2['RSUD_DR_Darsono']

@app.template_filter('clean')
def clean_string(s):
    return s.replace(' ', '').lower()

def format_rupiah(value):
    try:
        value = int(value)
        return f"Rp {value:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

# Month name conversion function
def bulan_indo(bulan_int):
    bulan_dict = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
        5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }
    return bulan_dict.get(int(bulan_int), 'Invalid month')


app.jinja_env.filters['rupiah'] = format_rupiah
app.jinja_env.filters['bulan_indo'] = bulan_indo

def login_required(roles=None):
    if roles is None:
        roles = []
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                return redirect(url_for('login'))
            user = db.users.find_one({'username': session['username']})
            if user is None or user['role'] not in roles:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/api/items_below_minimum', methods=['GET'])
@login_required(roles=['adminbarang', 'adminsistem'])  
def get_items_below_minimum():
    items_below_minimum = db.items.count_documents({'$expr': {'$lte': ['$stock_tersedia', '$stock_minimum']}})
    return jsonify({'items_below_minimum': items_below_minimum})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = db.users.find_one({'username': username, 'password_not_hash': password})
        if user:
            if user['status'] == 'Aktif':
                session['username'] = username
                session['role'] = user['role']
                return redirect('/')
            else:
                return render_template('login.html', message='Akun Anda dinonaktifkan. Silahkan hubungi admin!')
        else:
            return render_template('login.html', message='Username atau password salah')
    else:
        return render_template('login.html')
    
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/login')

@app.route('/')
@login_required(roles=['adminsistem','adminbarang','kepalagudang'])
def dashboard():
    if 'username' in session:
        username = session['username']
        user = db.users.find_one({'username': username})
        role = user['role']
        
        if role == 'adminbarang':
            return redirect('/adminbarang')
        elif role == 'adminsistem':
            return redirect('/adminsistem')
        elif role == 'kepalagudang':
            return redirect('/kepalagudang')
        else:
            return render_template('login.html', message='Role not recognized')
    else:
        return redirect('/login')

@app.route('/adminsistem', methods=['GET'])
@login_required(roles=['adminsistem'])
def adminsistem():
    total_roles = db.roles.count_documents({})
    total_users = db.users.count_documents({})
    total_active_users = db.users.count_documents({'status': 'Aktif'})
    total_nonactive_users = db.users.count_documents({'status': 'Nonaktif'})

    user_list = list(db.users.find().limit(10))

    return render_template('adminsistem_dashboard.html',  
                           total_roles=total_roles,
                           total_users=total_users,
                           total_active_users=total_active_users,
                           total_nonactive_users=total_nonactive_users,
                           user_list=user_list)

@app.route('/role', methods=['GET'])
@login_required(roles=['adminsistem'])
def role():
    roles = list(db.roles.find())
    return render_template('adminsistem_role.html', roles=roles)

# Route CRUD untuk role
@app.route('/role/add', methods=['POST'])
@login_required(roles=['adminsistem'])
def add_role():
    data = request.get_json()
    role_name = data.get('roleName')

    # Validasi nama role
    if not role_name:
        return jsonify({'message': 'Nama Role harus diisi.'}), 400

    # Memastikan nama role hanya huruf kecil tanpa spasi
    if not re.match(r'^[a-z]+$', role_name):
        return jsonify({'message': 'Nama Role hanya boleh huruf kecil tanpa spasi.'}), 400

    existing_role = db.roles.find_one({'name': role_name})
    if existing_role:
        return jsonify({'message': 'Role sudah terdapat, gunakan nama lain'}), 400
    
    db.roles.insert_one({'name': role_name})
    return jsonify({'message': 'Role added successfully!'}), 201

@app.route('/role/edit/<id>', methods=['POST'])
@login_required(roles=['adminsistem'])
def edit_role(id):
    data = request.get_json()
    role_name = data.get('roleName')
    if role_name:
        db.roles.update_one({'_id': ObjectId(id)}, {'$set': {'name': role_name}})
        return jsonify({'message': 'Role updated successfully!'}), 200
    return jsonify({'message': 'Role name is required!'}), 400

@app.route('/role/delete/<id>', methods=['DELETE'])
@login_required(roles=['adminsistem'])
def delete_role(id):
    db.roles.delete_one({'_id': ObjectId(id)})
    return jsonify({'message': 'Role deleted successfully!'}), 200    

# Route CRUD untuk user
@app.route('/user', methods=['GET'])
@login_required(roles=['adminsistem'])
def user():
    users = list(db.users.find())
    return render_template('adminsistem_user.html', users=users)

@app.route('/user/add', methods=['POST'])
@login_required(roles=['adminsistem'])
def add_user():
    import re
    data = request.get_json()
    name = data.get('name')
    username = data.get('username').lower().replace(" ", "")  # Ensure username is lowercase without spaces
    password = data.get('password')
    role = data.get('role')

    if not all([name, username, password, role]):
        return jsonify({'message': 'All fields are required!'}), 400

    # Password validation
    password_pattern = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$')
    if not password_pattern.match(password):
        return jsonify({'message': 'Password harus minimal 8 karakter dan mengandung huruf besar, huruf kecil, angka, dan simbol.'}), 400

    existing_user = db.users.find_one({'username': username})
    if existing_user:
        return jsonify({'message': 'Username sudah digunakan, gunakan username lain'}), 400

    # Hash the password with bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    db.users.insert_one({
        'name': name,
        'username': username,
        'password': hashed_password.decode('utf-8'),
        'password_not_hash': password,
        'role': role,
        'status': 'Aktif'
    })
    return jsonify({'message': 'User added successfully!'}), 201

@app.route('/user/status/<id>', methods=['POST'])
@login_required(roles=['adminsistem'])
def change_status_user(id):
    user = db.users.find_one({'_id': ObjectId(id)})
    new_status = 'Nonaktif' if user['status'] == 'Aktif' else 'Aktif'
    db.users.update_one({'_id': ObjectId(id)}, {'$set': {'status': new_status}})
    return jsonify({'message': 'User status updated successfully!'}), 200

@app.route('/user/delete/<id>', methods=['DELETE'])
@login_required(roles=['adminsistem'])
def delete_user(id):
    db.users.delete_one({'_id': ObjectId(id)})
    return jsonify({'message': 'User deleted successfully!'}), 200    

@app.route('/tambahuser', methods=['GET'])
@login_required(roles=['adminsistem'])
def tambahuser():
    roles = list(db.roles.find())
    return render_template('adminsistem_tambahuser.html', roles=roles)        

@app.route("/user/detail/<id>", methods=["GET"])
@login_required(roles=['adminsistem'])
def get_user_details(id):
    user = users_collection.find_one({"_id": ObjectId(id)})
    if not user:
        return jsonify({"message": "User not found"}), 404

    return render_template('adminsistem_detailuser.html', user=user)

@app.route('/adminbarang', methods=['GET', 'POST'])
@login_required(roles=['adminbarang'])
def adminbarang():
    try:
        total_in_items = db.incoming_transactions.count_documents({})
        total_out_items = db.outgoing_transactions.count_documents({})
        total_categories = db.categories.count_documents({})
        total_items = db.items.count_documents({})

        recaps = list(db.monthly_recaps.find())

        for recap in recaps:
            bulan = recap['bulan']
            tahun = recap['tahun']
            saldo_awal = recap.get('saldo_awal', 0)

            start_date = datetime(int(tahun), int(bulan), 1)
            if int(bulan) == 12:
                end_date = datetime(int(tahun) + 1, 1, 1)
            else:
                end_date = datetime(int(tahun), int(bulan) + 1, 1)

            incoming_transactions = db.incoming_transactions.find({
                'tanggal_masuk': {'$gte': start_date, '$lt': end_date}  # Menggunakan $lt untuk membatasi sampai sebelum bulan berikutnya
            })

            pengeluaran = sum(transaction['harga_barang'] for transaction in incoming_transactions)
            saldo_akhir = saldo_awal - pengeluaran

            recap['pengeluaran'] = pengeluaran
            recap['saldo_akhir'] = saldo_akhir

        if request.method == 'POST':
            bulan = request.form.get('bulan')
            saldo_awal = request.form.get('saldo_awal')

            if bulan:
                year, month = bulan.split('-')
            else:
                return redirect(url_for('adminbarang'))

            cek = db.monthly_recaps.find_one({'bulan': int(month), 'tahun': int(year)})

            if cek is None:
                db.monthly_recaps.insert_one({'bulan': int(month), 'tahun': int(year), 'saldo_awal': int(saldo_awal)})
            else:
                db.monthly_recaps.update_one({'bulan': int(month), 'tahun': int(year)}, {'$set': {'saldo_awal': int(saldo_awal)}})

            return redirect(url_for('adminbarang'))

        return render_template('adminbarang_dashboard.html',  
                               total_in_items=total_in_items,
                               total_out_items=total_out_items,
                               total_categories=total_categories,
                               total_items=total_items,
                               recaps=recaps)
    
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return render_template('error.html', message='Terjadi kesalahan dalam memproses data. Silakan coba lagi nanti.')


# Route CRUD untuk kategori
@app.route('/kategori', methods=['GET'])
@login_required(roles=['adminbarang'])
def kategori():
    categories = list(db.categories.find())
    return render_template('adminbarang_kategori.html', categories=categories)

@app.route('/kategori/add', methods=['POST'])
@login_required(roles=['adminbarang'])
def add_category():
    data = request.get_json()
    category = data.get('category')
    
    existing_category = db.categories.find_one({'nama_kategori': category})
    if existing_category:
        return jsonify({'message': 'Kategori sudah digunakan, gunakan nama lain'}), 400
    
    db.categories.insert_one({'nama_kategori': category})
    return jsonify({'message': 'Category added successfully!'}), 201

@app.route('/kategori/edit/<id>', methods=['POST'])
@login_required(roles=['adminbarang'])
def edit_category(id):
    data = request.get_json()
    category = data.get('category')
    if category:
        db.categories.update_one({'_id': ObjectId(id)}, {'$set': {'nama_kategori': category}})
        return jsonify({'message': 'Category updated successfully!'}), 200
    return jsonify({'message': 'Category name is required!'}), 400

@app.route('/kategori/delete/<id>', methods=['DELETE'])
@login_required(roles=['adminbarang'])
def delete_category(id):
    db.categories.delete_one({'_id': ObjectId(id)})
    return jsonify({'message': 'Category deleted successfully!'}), 200    

# Route CRUD untuk satuan
@app.route('/satuan', methods=['GET'])
@login_required(roles=['adminbarang'])
def satuan():
    units = list(db.satuan.find())
    return render_template('adminbarang_satuan.html', units=units)

@app.route('/satuan/add', methods=['POST'])
@login_required(roles=['adminbarang'])
def add_unit():
    data = request.get_json()
    unit = data.get('unit')
    
    existing_unit = db.satuan.find_one({'nama_satuan': unit})
    if existing_unit:
        return jsonify({'message': 'Satuan sudah digunakan, gunakan nama lain'}), 400
    
    db.satuan.insert_one({'nama_satuan': unit})
    return jsonify({'message': 'Unit added successfully!'}), 201

@app.route('/satuan/edit/<id>', methods=['POST'])
@login_required(roles=['adminbarang'])
def edit_unit(id):
    data = request.get_json()
    unit = data.get('unit')
    if unit:
        db.satuan.update_one({'_id': ObjectId(id)}, {'$set': {'nama_satuan': unit}})
        return jsonify({'message': 'Unit updated successfully!'}), 200
    return jsonify({'message': 'Unit name is required!'}), 400

@app.route('/satuan/delete/<id>', methods=['DELETE'])
@login_required(roles=['adminbarang'])
def delete_unit(id):
    db.satuan.delete_one({'_id': ObjectId(id)})
    return jsonify({'message': 'Unit deleted successfully!'}), 200

# Route CRUD untuk barang
@app.route('/barang', methods=['GET'])
@login_required(roles=['adminbarang'])
def barang():
    items = list(db.items.find())
    categories = list(db.categories.find())
    satuans = list(db.satuan.find())
    for item in items:
        category = db.categories.find_one({'_id': item['kategori_id']})
        item['nama_kategori'] = category['nama_kategori'] if category else 'Unknown'
        satuan = db.satuan.find_one({'_id': item['satuan_id']})
        item['nama_satuan'] = satuan['nama_satuan'] if satuan else 'Unknown'
    return render_template('adminbarang_barang.html', items=items, categories=categories, satuans=satuans)

@app.route('/barang/add', methods=['POST'])
@login_required(roles=['adminbarang'])
def add_barang():
    data = request.get_json()
    kategori_id = data.get('kategori_id')
    nama_barang = data.get('nama_barang')
    satuan_id = data.get('satuan_id')
    stock_awal = data.get('stock_awal')
    stock_minimum = data.get('stock_minimum')

    if data:
        existing_item = db.items.find_one({'nama_barang': nama_barang})
        if existing_item:
            return jsonify({'message': 'Barang sudah digunakan, gunakan nama lain'}), 400
        
        db.items.insert_one({
            'kategori_id': ObjectId(kategori_id),
            'nama_barang': nama_barang,
            'satuan_id': ObjectId(satuan_id),
            'stock_awal': int(stock_awal),
            'stock_minimum': int(stock_minimum),
            'stock_tersedia': int(stock_awal)
        })
        return jsonify({'message': 'Item added successfully!'}), 201
    
    return jsonify({'message': 'Item name is required!'}), 400

@app.route('/barang/edit/<id>', methods=['POST'])
@login_required(roles=['adminbarang'])
def edit_barang(id):
    data = request.get_json()
    kategori_id = data.get('kategori_id')
    nama_barang = data.get('nama_barang')
    satuan_id = data.get('satuan_id')
    stock_awal = data.get('stock_awal')
    stock_minimum = data.get('stock_minimum')
    if data:
        db.items.update_one({'_id': ObjectId(id)}, {'$set': {
            'kategori_id': ObjectId(kategori_id),
            'nama_barang': nama_barang,
            'satuan_id': ObjectId(satuan_id),
            'stock_awal': int(stock_awal),
            'stock_minimum': int(stock_minimum),
            'stock_tersedia': int(stock_awal)
        }})
        return jsonify({'message': 'Item updated successfully!'}), 200
    return jsonify({'message': 'Item name is required!'}), 400

@app.route('/barang/delete/<id>', methods=['DELETE'])
@login_required(roles=['adminbarang'])
def delete_barang(id):
    db.items.delete_one({'_id': ObjectId(id)})
    return jsonify({'message': 'Item deleted successfully!'}), 200

# Route CRUD untuk Barang Masuk
@app.route('/barangmasuk', methods=['GET'])
@login_required(roles=['adminbarang'])
def barangmasuk():
    today = datetime.today().strftime('%Y-%m-%d')

    incoming_transactions = list(db.incoming_transactions.find().sort('tanggal_masuk', DESCENDING))

    # Menyimpan semua barang yang ditemukan untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    satuan_cache = {}  # Cache satuan data

    # Dictionary untuk menyimpan stok barang
    stock_cache = {}

    items = list(db.items.find())
    for item in items:
        items_cache[str(item['_id'])] = item

    for transaction in incoming_transactions:
        # Mencari barang berdasarkan barang_id
        barang_id = str(transaction['barang_id'])
        
        if barang_id in items_cache:
            item = items_cache[barang_id]
            # Menambahkan nama barang ke transaksi
            transaction['nama_barang'] = item.get('nama_barang', 'Unknown')
            transaction['nama_satuan'] = item.get('nama_satuan', 'Unknown')

            # Mencari kategori berdasarkan kategori_id dalam item
            kategori_id = str(item['kategori_id'])
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category

            # Menambahkan nama kategori ke transaksi
            transaction['nama_kategori'] = categories_cache.get(kategori_id, {}).get('nama_kategori', 'Unknown')

            satuan_id = items_cache[barang_id]['satuan_id']
            if satuan_id not in satuan_cache:
                satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                if satuan:
                    satuan_cache[satuan_id] = satuan

            transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'


            # Menghitung stok barang
            if barang_id not in stock_cache:
                # Mengambil stok awal dari master barang
                stock_cache[barang_id] = item.get('stock_awal', 0)

            # Tambahkan jumlah barang masuk ke stok
            stock_cache[barang_id] += transaction['jumlah_barang']
            transaction['stock'] = stock_cache[barang_id]
        else:
            transaction['nama_barang'] = 'Unknown'
            transaction['nama_satuan'] = 'Unknown'
            transaction['nama_kategori'] = 'Unknown'
            transaction['stock'] = 0

        print(transaction)

    return render_template('adminbarang_barangmasuk.html', items=items, incoming_transactions=incoming_transactions, today=today)

@app.route('/barangmasuk/add', methods=['POST'])
@login_required(roles=['adminbarang'])
def add_barangmasuk():
    data = request.get_json()
    barang_id = data.get('barang_id')
    tanggal_masuk = data.get('tanggal_masuk')
    harga_barang = data.get('harga_barang')
    jumlah_barang = data.get('jumlah_barang')
    keterangan = data.get('keterangan')

    # Get current logged-in user's username
    added_by = session.get('username')

    # Validasi data yang masuk
    if not all([barang_id, tanggal_masuk, harga_barang, jumlah_barang]):
        return jsonify({'message': 'Data tidak lengkap!'}), 400

    item = db.items.find_one({'_id': ObjectId(barang_id)})

    # Insert data ke collection incoming_transactions
    db.incoming_transactions.insert_one({
        'barang_id': ObjectId(barang_id),
        'tanggal_masuk': datetime.strptime(tanggal_masuk, '%Y-%m-%d'),
        'harga_barang': int(harga_barang),
        'jumlah_barang': int(jumlah_barang),
        'stock_tersedia': int(jumlah_barang) + int(item['stock_tersedia']),
        'keterangan': keterangan,
        'added_by': added_by  # Store username of the user who added the item
    })

    if item:
        db.items.update_one({'_id': ObjectId(barang_id)}, {'$set': {
            'stock_tersedia': int(item['stock_tersedia']) + int(jumlah_barang)
        }})
    
    return jsonify({'message': 'Incoming item added successfully!'}), 201

@app.route('/barangmasuk/edit/<id>', methods=['POST'])
@login_required(roles=['adminbarang'])
def edit_barangmasuk(id):
    data = request.get_json()
    barang_id = data.get('barang_id')
    tanggal_masuk = data.get('tanggal_masuk')
    harga_barang = data.get('harga_barang')
    jumlah_barang = data.get('jumlah_barang')
    old_jumlah_barang = data.get('old_jumlah_barang')

    # Get current logged-in user's username
    last_edited_by = session.get('username')

    # Fetch the original transaction data
    transaction = db.incoming_transactions.find_one({'_id': ObjectId(id)})

    if not transaction:
        return jsonify({'message': 'Transaksi tidak ditemukan!'}), 404

    # Check if the current user is the one who added the item
    if transaction['added_by'] != last_edited_by:
        return jsonify({'message': 'Tidak dapat diedit! Anda bukan pengguna yang menambahkan barang ini.'}), 403

    # Lanjutkan proses edit jika user yang menambahkan barang
    if data:
        item = db.items.find_one({'_id': ObjectId(barang_id)})
        db.items.update_one({'_id': ObjectId(barang_id)}, {'$set': {
            'stock_tersedia': int(item['stock_tersedia']) - int(old_jumlah_barang)
        }})

        item2 = db.items.find_one({'_id': ObjectId(barang_id)})

        if item2:
            db.items.update_one({'_id': ObjectId(barang_id)}, {'$set': {
                'stock_tersedia': int(item2['stock_tersedia']) + int(jumlah_barang)
            }})
        
        db.incoming_transactions.update_one({'_id': ObjectId(id)}, {'$set': {
            'barang_id': ObjectId(barang_id),
            'tanggal_masuk': datetime.strptime(tanggal_masuk, '%Y-%m-%d'),
            'harga_barang': int(harga_barang),
            'jumlah_barang': int(jumlah_barang),
            'stock_tersedia': int(item2['stock_tersedia']) + int(jumlah_barang),
            'last_edited_by': last_edited_by  # Store username of the user who edited the item
        }})

        return jsonify({'message': 'Incoming item updated successfully!'}), 200
    return jsonify({'message': 'Incoming item name is required!'}), 400

@app.route('/barangmasuk/delete/<id>', methods=['DELETE'])
@login_required(roles=['adminbarang'])
def delete_barangmasuk(id):
    incoming = db.incoming_transactions.find_one({'_id': ObjectId(id)})

    if incoming:
        item = db.items.find_one({'_id': ObjectId(incoming['barang_id'])})

        if item:
            db.items.update_one({'_id': ObjectId(incoming['barang_id'])}, {'$set': {
                'stock_tersedia': item['stock_tersedia'] - int(incoming['jumlah_barang'])
            }})
        
        db.incoming_transactions.delete_one({'_id': ObjectId(id)})
        return jsonify({'message': 'Incoming item deleted successfully!'}), 200
    
    return jsonify({'message': 'Data tidak ditemukan!'}), 400

# CRUD barang keluar
@app.route('/barangkeluar', methods=['GET'])
@login_required(roles=['adminbarang'])
def barangkeluar():
    ########### NEW ################ 
    fw_filter = {"is_verif": True, "status": "Process"}
    barang_keluar_col = db2['staff_gudang']
    barang_keluar_tbl = list(barang_keluar_col.find(fw_filter).sort('tanggal_penerimaan', DESCENDING))
    items2 = list(db.items.find())
    categories2 = list(db.categories.find())
    satuan2 = list(db.satuan.find())  # Fetch satuan data
    
    categories_dict = {category['_id']: category for category in categories2}
    satuans_dict = {satuan['_id']: satuan['nama_satuan'] for satuan in satuan2}  # Map satuan 
    for item in items2:
        kategori_id = item.get('kategori_id')
        if kategori_id in categories_dict:
            item['kategori'] = categories_dict[kategori_id]
        else:
            item['kategori'] = "Kebersihan"

        satuan_id = item.get('satuan_id')
        if satuan_id in satuans_dict:
            item['satuan'] = satuans_dict[satuan_id]
        else:
            item['satuan'] = "Box"

    # items_dict = {item['nama_barang']: item['satuan'] for item in items2}
    satuan_dict = {item['nama_barang']: item['satuan'] for item in items2}
    kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}

    for item in barang_keluar_tbl:
        nama_barang = item.get('nama_barang')

        if nama_barang in kategori_dict:
            item['kategori'] = kategori_dict[nama_barang]
        else:
            item['kategori'] = "Kebersihan"

        if nama_barang in satuan_dict:
            item['satuan'] = satuan_dict[nama_barang]
        else:
            item['satuan'] = 'Box'



    # print(barang_keluar_tbl)
    # print(items2)
    # print(categories2)
    ########### END ################ 

    today = datetime.today().strftime('%Y-%m-%d')
    outgoing_transactions = list(db.outgoing_transactions.find().sort('tanggal_keluar', DESCENDING))

    # Menyimpan semua barang yang ditemukan untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    satuan_cache = {}  # Cache satuan data

    # Dictionary untuk menyimpan stok barang
    stock_cache = {}

    items = list(db.items.find())
    for transaction in outgoing_transactions:
        # Mencari barang berdasarkan barang_id
        barang_id = transaction['barang_id']
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item
        
        # Menambahkan nama barang ke transaksi
        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        transaction['satuan'] = items_cache[barang_id]['satuan'] if barang_id in items_cache else 'Unknown'
        
        # Mencari kategori berdasarkan kategori_id dalam item
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            # Menambahkan nama kategori ke transaksi
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

            satuan_id = items_cache[barang_id]['satuan_id']
            if satuan_id not in satuan_cache:
                satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                if satuan:
                    satuan_cache[satuan_id] = satuan

            transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'

        # Menghitung stok barang
        # if barang_id not in stock_cache:
        #     # Mengambil stok awal dari master barang
        #     stock_cache[barang_id] = items_cache[barang_id]['stock_awal']
        
        # # Tambahkan jumlah barang masuk ke stok
        # stock_cache[barang_id] += transaction['jumlah_barang']
        # transaction['stock'] = stock_cache[barang_id]
    
    return render_template('adminbarang_barangkeluar.html', items=items, outgoing_transactions=outgoing_transactions, today=today, barang_keluar_tbl=barang_keluar_tbl)

@app.route('/barangkeluar/add', methods=['POST'])
@login_required(roles=['adminbarang'])
def add_barangkeluar():
    data = request.get_json()
    barang_id = data.get('barang_id')
    tanggal_keluar = data.get('tanggal_keluar')
    jumlah_barang = data.get('jumlah_barang')
    keterangan = data.get('keterangan')

    added_by = session.get('username')

    # Validasi data yang masuk
    if not all([barang_id, tanggal_keluar, keterangan, jumlah_barang]):
        return jsonify({'message': 'Data tidak lengkap!'}), 400

    item = db.items.find_one({'_id': ObjectId(barang_id)})

    # Insert data ke collection incoming_transactions
    db.outgoing_transactions.insert_one({
        'barang_id': ObjectId(barang_id),
        'tanggal_keluar': datetime.strptime(tanggal_keluar, '%Y-%m-%d'),
        'jumlah_barang': int(jumlah_barang),
        'stock_tersedia': int(item['stock_tersedia']) - int(jumlah_barang),
        'keterangan': keterangan,
        'added_by': added_by  # Store username of the user who added the item
    })

    if item:
        db.items.update_one({'_id': ObjectId(barang_id)}, {'$set': {
            'stock_tersedia': item['stock_tersedia'] - int(jumlah_barang)
        }})
    
    return jsonify({'message': 'Outgoing item added successfully!'}), 201

@app.route('/barangkeluar/edit/<id>', methods=['POST'])
@login_required(roles=['adminbarang'])
def edit_barangkeluar(id):
    data = request.get_json()
    barang_id = data.get('barang_id')
    tanggal_keluar = data.get('tanggal_keluar')
    keterangan = data.get('keterangan')
    jumlah_barang = data.get('jumlah_barang')
    old_jumlah_barang = data.get('old_jumlah_barang')

    last_edited_by = session.get('username')

    if data:
        item = db.items.find_one({'_id': ObjectId(barang_id)})
        db.items.update_one({'_id': ObjectId(barang_id)}, {'$set': {
            'stock_tersedia': item['stock_tersedia'] + int(old_jumlah_barang)
        }})

        item2 = db.items.find_one({'_id': ObjectId(barang_id)})

        if item2:
            db.items.update_one({'_id': ObjectId(barang_id)}, {'$set': {
                'stock_tersedia': item2['stock_tersedia'] - int(jumlah_barang)
            }})
        
        db.outgoing_transactions.update_one({'_id': ObjectId(id)}, {'$set': {
            'barang_id': ObjectId(barang_id),
            'tanggal_keluar': datetime.strptime(tanggal_keluar, '%Y-%m-%d'),
            'keterangan': keterangan,
            'jumlah_barang': int(jumlah_barang),
            'stock_tersedia': item2['stock_tersedia'] - int(jumlah_barang),
            'last_edited_by': last_edited_by  # Store username of the user who edited the item
        }})

        return jsonify({'message': 'Outgoing item updated successfully!'}), 200
    return jsonify({'message': 'Outgoing item name is required!'}), 400

@app.route('/barangkeluar/delete/<id>', methods=['DELETE'])
@login_required(roles=['adminbarang'])
def delete_barangkeluar(id):
    outgoing = db.outgoing_transactions.find_one({'_id': ObjectId(id)})

    if outgoing:
        item = db.items.find_one({'_id': ObjectId(outgoing['barang_id'])})

        if item:
            db.items.update_one({'_id': ObjectId(outgoing['barang_id'])}, {'$set': {
                'stock_tersedia': item['stock_tersedia'] + int(outgoing['jumlah_barang'])
            }})
        
        db.outgoing_transactions.delete_one({'_id': ObjectId(id)})
        return jsonify({'message': 'Outgoing item deleted successfully!'}), 200
    
    return jsonify({'message': 'Data tidak ditemukan!'}), 400

# Filter Kartu Stock
@app.route('/kartustock', methods=['GET'])
@login_required(roles=['adminbarang'])
def kartustock():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    barang_id = request.args.get('barang_id')

    incoming_filter_conditions = {}
    outgoing_filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            incoming_filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
            outgoing_filter_conditions['$expr'] = {
                '$gte': [
                    {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                    start_date
                ]
            }
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400

    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in incoming_filter_conditions:
                incoming_filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                incoming_filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                incoming_filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
            
            if '$expr' in outgoing_filter_conditions:
                outgoing_filter_conditions['$expr'] = {
                    '$and': [
                        outgoing_filter_conditions['$expr'],
                        {'$lte': [
                            {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                            end_date
                        ]}
                    ]
                }
            else:
                outgoing_filter_conditions['$expr'] = {
                    '$lte': [
                        {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                        end_date
                    ]
                }
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

    selected_item = None
    nama_barang = None

    if barang_id:
        try:
            barang_id = ObjectId(barang_id)
            incoming_filter_conditions['barang_id'] = barang_id
            selected_item = db.items.find_one({'_id': barang_id})
            if selected_item:
                nama_barang = selected_item.get('nama_barang')
        except Exception as e:
            return jsonify({'message': 'Barang ID tidak valid!'}), 400

    # Ambil data dari incoming_transactions
    incoming_transactions = list(db.incoming_transactions.find(incoming_filter_conditions))

    # Ambil data dari staff_gudang dengan filter tanggal_penerimaan dan nama_barang
    barang_keluar_col = db2['staff_gudang']

    statuses_to_filter = ["Process", "Success"]
    outgoing_filter_conditions['is_verif'] = True
    outgoing_filter_conditions['status'] = {'$in': statuses_to_filter}

    if nama_barang:
        outgoing_filter_conditions['nama_barang'] = nama_barang

    # Ambil data dari barang_keluar_col dengan filter outgoing_filter_conditions
    outgoing_transactions = list(barang_keluar_col.find(outgoing_filter_conditions))

    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
    
    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['keterangan'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
    
    # Sortir data berdasarkan tanggal
    # all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    
    for transaction in incoming_transactions:
        barang_id = transaction.get('barang_id')
        
        if barang_id:
            try:
                barang_id = ObjectId(barang_id)
            except Exception as e:
                transaction['nama_barang'] = 'Unknown'
                transaction['nama_kategori'] = 'Unknown'
                continue
            
            if barang_id not in items_cache:
                item = db.items.find_one({'_id': barang_id})
                if item:
                    items_cache[barang_id] = item
            
            transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
            
            if barang_id in items_cache:
                kategori_id = items_cache[barang_id]['kategori_id']
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'

    # Process outgoing_transactions (which have nama_barang)
    for transaction in outgoing_transactions:
        nama_barang = transaction.get('nama_barang')
        
        if nama_barang:
            if nama_barang not in items_cache:
                item = db.items.find_one({'nama_barang': nama_barang})
                if item:
                    items_cache[nama_barang] = item
            
            if nama_barang in items_cache:
                barang_id = items_cache[nama_barang]['_id']
                kategori_id = items_cache[nama_barang]['kategori_id']
                transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
        else:
            transaction['nama_kategori'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Gabungkan data
    # Sort transactions by date
    incoming_transactions.sort(key=lambda x: x['date'])
    outgoing_transactions.sort(key=lambda x: x['date'])

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']

    # Combine transactions for output
    all_transactions = incoming_transactions + outgoing_transactions

    # all_transactions = incoming_transactions + outgoing_transactions
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))

    items = list(db.items.find())
    return render_template('adminbarang_kartustock.html', transactions=all_transactions, items=items, barang_id=barang_id, start_date=start_date, end_date=end_date, selected_item=selected_item)

@app.route('/kartustock/export/pdf', methods=['GET'])
@login_required(roles=['adminbarang'])
def kartustock_export_pdf():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    barang_id = request.args.get('barang_id')

    incoming_filter_conditions = {}
    outgoing_filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            incoming_filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
            outgoing_filter_conditions['$expr'] = {
                '$gte': [
                    {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                    start_date
                ]
            }
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400

    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in incoming_filter_conditions:
                incoming_filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                incoming_filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                incoming_filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
            
            if '$expr' in outgoing_filter_conditions:
                outgoing_filter_conditions['$expr'] = {
                    '$and': [
                        outgoing_filter_conditions['$expr'],
                        {'$lte': [
                            {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                            end_date
                        ]}
                    ]
                }
            else:
                outgoing_filter_conditions['$expr'] = {
                    '$lte': [
                        {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                        end_date
                    ]
                }
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

    selected_item = None
    nama_barang = None

    if barang_id:
        try:
            barang_id = ObjectId(barang_id)
            incoming_filter_conditions['barang_id'] = barang_id
            selected_item = db.items.find_one({'_id': barang_id})
            if selected_item:
                nama_barang = selected_item.get('nama_barang')
        except Exception as e:
            return jsonify({'message': 'Barang ID tidak valid!'}), 400

    # Ambil data dari incoming_transactions
    incoming_transactions = list(db.incoming_transactions.find(incoming_filter_conditions))

    # Ambil data dari staff_gudang dengan filter tanggal_penerimaan dan nama_barang
    barang_keluar_col = db2['staff_gudang']

    statuses_to_filter = ["Process", "Success"]
    outgoing_filter_conditions['is_verif'] = True
    outgoing_filter_conditions['status'] = {'$in': statuses_to_filter}

    if nama_barang:
        outgoing_filter_conditions['nama_barang'] = nama_barang

    # Ambil data dari barang_keluar_col dengan filter outgoing_filter_conditions
    outgoing_transactions = list(barang_keluar_col.find(outgoing_filter_conditions))

    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
    
    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['keterangan'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
        transaction['jumlah_barang'] = transaction['jumlah_diterima']
    
    # Sortir data berdasarkan tanggal
    # all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    
    for transaction in incoming_transactions:
        barang_id = transaction.get('barang_id')
        
        if barang_id:
            try:
                barang_id = ObjectId(barang_id)
            except Exception as e:
                transaction['nama_barang'] = 'Unknown'
                transaction['nama_kategori'] = 'Unknown'
                continue
            
            if barang_id not in items_cache:
                item = db.items.find_one({'_id': barang_id})
                if item:
                    items_cache[barang_id] = item
            
            transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
            
            if barang_id in items_cache:
                kategori_id = items_cache[barang_id]['kategori_id']
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'

    # Process outgoing_transactions (which have nama_barang)
    for transaction in outgoing_transactions:
        nama_barang = transaction.get('nama_barang')
        
        if nama_barang:
            if nama_barang not in items_cache:
                item = db.items.find_one({'nama_barang': nama_barang})
                if item:
                    items_cache[nama_barang] = item
            
            if nama_barang in items_cache:
                barang_id = items_cache[nama_barang]['_id']
                kategori_id = items_cache[nama_barang]['kategori_id']
                transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
        else:
            transaction['nama_kategori'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Gabungkan data
    # Sort transactions by date
    incoming_transactions.sort(key=lambda x: x['date'])
    outgoing_transactions.sort(key=lambda x: x['date'])

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']

    # Combine transactions for output
    all_transactions = incoming_transactions + outgoing_transactions

    # all_transactions = incoming_transactions + outgoing_transactions
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))

    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}

    for transaction in all_transactions:
        barang_id = transaction['barang_id']

        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'

        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category

            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

    # Prepare the heading
    heading = "Kartu Stock Semua Barang"
    if start_date or end_date or selected_item:
        heading = "Kartu Stock "
        if selected_item:
            heading += selected_item['nama_barang'] + " "
        heading += "Periode "
        heading += start_date.strftime('%d-%m-%Y') if start_date else "-"
        heading += " sampai "
        heading += end_date.strftime('%d-%m-%Y') if end_date else "-"

    # Render template HTML
    rendered_template = render_template('export_kartustock.html', transactions=all_transactions, heading=heading)

    # Buat file PDF
    pdf_file_path = 'kartustock.pdf'
    with open(pdf_file_path, 'wb') as file:
        pisa.CreatePDF(rendered_template, dest=file)

    # Mengirim file PDF sebagai respons
    return send_file(pdf_file_path, as_attachment=True)

@app.route('/kartustock/export/xsl', methods=['GET'])
@login_required(roles=['adminbarang'])
def kartustock_export_excel():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    barang_id = request.args.get('barang_id')

    incoming_filter_conditions = {}
    outgoing_filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            incoming_filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
            outgoing_filter_conditions['$expr'] = {
                '$gte': [
                    {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                    start_date
                ]
            }
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400

    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in incoming_filter_conditions:
                incoming_filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                incoming_filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                incoming_filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
            
            if '$expr' in outgoing_filter_conditions:
                outgoing_filter_conditions['$expr'] = {
                    '$and': [
                        outgoing_filter_conditions['$expr'],
                        {'$lte': [
                            {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                            end_date
                        ]}
                    ]
                }
            else:
                outgoing_filter_conditions['$expr'] = {
                    '$lte': [
                        {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                        end_date
                    ]
                }
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

    selected_item = None
    nama_barang = None

    if barang_id:
        try:
            barang_id = ObjectId(barang_id)
            incoming_filter_conditions['barang_id'] = barang_id
            selected_item = db.items.find_one({'_id': barang_id})
            if selected_item:
                nama_barang = selected_item.get('nama_barang')
        except Exception as e:
            return jsonify({'message': 'Barang ID tidak valid!'}), 400

    # Ambil data dari incoming_transactions
    incoming_transactions = list(db.incoming_transactions.find(incoming_filter_conditions))

    # Ambil data dari staff_gudang dengan filter tanggal_penerimaan dan nama_barang
    barang_keluar_col = db2['staff_gudang']

    statuses_to_filter = ["Process", "Success"]
    outgoing_filter_conditions['is_verif'] = True
    outgoing_filter_conditions['status'] = {'$in': statuses_to_filter}

    if nama_barang:
        outgoing_filter_conditions['nama_barang'] = nama_barang

    # Ambil data dari barang_keluar_col dengan filter outgoing_filter_conditions
    outgoing_transactions = list(barang_keluar_col.find(outgoing_filter_conditions))

    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
    
    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['keterangan'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
        transaction['jumlah_barang'] = transaction['jumlah_diterima']
    
    # Sortir data berdasarkan tanggal
    # all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    
    for transaction in incoming_transactions:
        barang_id = transaction.get('barang_id')
        
        if barang_id:
            try:
                barang_id = ObjectId(barang_id)
            except Exception as e:
                transaction['nama_barang'] = 'Unknown'
                transaction['nama_kategori'] = 'Unknown'
                continue
            
            if barang_id not in items_cache:
                item = db.items.find_one({'_id': barang_id})
                if item:
                    items_cache[barang_id] = item
            
            transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
            
            if barang_id in items_cache:
                kategori_id = items_cache[barang_id]['kategori_id']
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'

    # Process outgoing_transactions (which have nama_barang)
    for transaction in outgoing_transactions:
        nama_barang = transaction.get('nama_barang')
        
        if nama_barang:
            if nama_barang not in items_cache:
                item = db.items.find_one({'nama_barang': nama_barang})
                if item:
                    items_cache[nama_barang] = item
            
            if nama_barang in items_cache:
                barang_id = items_cache[nama_barang]['_id']
                kategori_id = items_cache[nama_barang]['kategori_id']
                transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
        else:
            transaction['nama_kategori'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Gabungkan data
    # Sort transactions by date
    incoming_transactions.sort(key=lambda x: x['date'])
    outgoing_transactions.sort(key=lambda x: x['date'])

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']

    # Combine transactions for output
    all_transactions = incoming_transactions + outgoing_transactions

    # all_transactions = incoming_transactions + outgoing_transactions
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    
    for transaction in all_transactions:
        barang_id = transaction['barang_id']
        
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'


    selected_columns = ['tanggal_masuk', 'tanggal_keluar', 'nama_barang', 'jumlah_barang', 'stock_tersedia', 'keterangan']

    # Konversi data ke DataFrame
    df = pandas.DataFrame(all_transactions, columns=selected_columns)

    # Buat file Excel
    excel_file_path = 'export_kartustock.xlsx'
    df.to_excel(excel_file_path, index=False)

    # Mengirim file Excel sebagai respons
    return send_file(excel_file_path, as_attachment=True)

@app.route('/laporan-barang-per-bulan', methods=['GET'])
@login_required(roles=['adminbarang'])
def laporanbarangperbulan():
    bulan = request.args.get('bulan')
    param_bulan = request.args.get('bulan')
    barang_id = request.args.get('barang_id')

    filter_conditions = {}
    outgoing_conditions = {
        'is_verif': True,
        'status': 'Process'
    }
    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    ori_bulan = bulan

    if bulan:
        try:
            tahun, bulan = bulan.split('-')
            start_date = datetime(int(tahun), int(bulan), 1)
            if int(bulan) == 12:
                end_date = datetime(int(tahun) + 1, 1, 1)
            else:
                end_date = datetime(int(tahun), int(bulan) + 1, 1)
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date, '$lte': end_date}},
                {'tanggal_keluar': {'$gte': start_date, '$lte': end_date}}
            ]

        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400

        try:
            _tahun, _bulan = ori_bulan.split('-')
            _start_date = f"{_tahun}-{_bulan}-01"
            if int(_bulan) == 12:
                _end_date = f"{int(_tahun) + 1}-01-01"
            else:
                _end_date = f"{_tahun}-{int(_bulan) + 1:02d}-01"

            outgoing_conditions['$or'] = [
                {'tanggal_pengajuan': {'$gte': _start_date, '$lt': _end_date}},
                {'tanggal_penerimaan': {'$gte': _start_date, '$lt': _end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400

    selected_item = None
    nama_barang = None

    if barang_id:
        try:
            barang_id = ObjectId(barang_id)
            filter_conditions['barang_id'] = barang_id
            selected_item = db.items.find_one({'_id': barang_id})
            if selected_item:
                nama_barang = selected_item.get('nama_barang')
        except Exception as e:
            return jsonify({'message': 'Barang ID tidak valid!'}), 400

    if nama_barang:
        outgoing_conditions['nama_barang'] = nama_barang
        
    incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    barang_keluar_col = db2['staff_gudang']
    barang_keluar_tbl = list(barang_keluar_col.find(outgoing_conditions).sort('tanggal_penerimaan', 1))
    
    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None

    items2 = list(db.items.find())
    categories2 = list(db.categories.find())
    satuan2 = list(db.satuan.find())
    
    categories_dict = {category['_id']: category for category in categories2}
    satuans_dict = {satuan['_id']: satuan['nama_satuan'] for satuan in satuan2}
    for item in items2:
        kategori_id = item.get('kategori_id')
        if kategori_id in categories_dict:
            item['kategori'] = categories_dict[kategori_id]
        else:
            item['kategori'] = "Kebersihan"

        satuan_id = item.get('satuan_id')
        if satuan_id in satuans_dict:
            item['satuan'] = satuans_dict[satuan_id]
        else:
            item['satuan'] = "Box"

    satuan_dict = {item['nama_barang']: item['satuan'] for item in items2}
    kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}

    for item in barang_keluar_tbl:
        nama_barang = item.get('nama_barang')
        if nama_barang in satuan_dict:
            item['satuan'] = satuan_dict[nama_barang]
        else:
            item['satuan'] = 'Box'

        if nama_barang in kategori_dict:
            item['kategori'] = kategori_dict[nama_barang]
        else:
            item['kategori'] = "Kebersihan"
            
    outgoing_transactions = barang_keluar_tbl
    
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['keterangan'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
    
    items_cache = {}
    categories_cache = {}
    satuan_cache = {}
    
    for transaction in incoming_transactions:
        barang_id = transaction.get('barang_id')
        
        if barang_id:
            try:
                barang_id = ObjectId(barang_id)
            except Exception as e:
                transaction['nama_barang'] = 'Unknown'
                transaction['nama_kategori'] = 'Unknown'
                continue
            
            if barang_id not in items_cache:
                item = db.items.find_one({'_id': barang_id})
                if item:
                    items_cache[barang_id] = item
            
            transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
            
            if barang_id in items_cache:
                kategori_id = items_cache[barang_id]['kategori_id']
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

                satuan_id = items_cache[barang_id]['satuan_id']
                if satuan_id not in satuan_cache:
                    satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                    if satuan:
                        satuan_cache[satuan_id] = satuan

                transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'

    for transaction in outgoing_transactions:
        nama_barang = transaction.get('nama_barang')
        
        if nama_barang:
            if nama_barang not in items_cache:
                item = db.items.find_one({'nama_barang': nama_barang})
                if item:
                    items_cache[nama_barang] = item
            
            if nama_barang in items_cache:
                barang_id = items_cache[nama_barang]['_id']
                kategori_id = items_cache[nama_barang]['kategori_id']
                transaction['barang_id'] = str(barang_id)
                
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

                satuan_id = items_cache[nama_barang]['satuan_id']
                if satuan_id not in satuan_cache:
                    satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                    if satuan:
                        satuan_cache[satuan_id] = satuan

                transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
        else:
            transaction['nama_kategori'] = 'Unknown'

    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    all_transactions = incoming_transactions + outgoing_transactions
    all_transactions.sort(key=lambda x: x['date'])

    total_masuk_dict = {}
    total_keluar_dict = {}

    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        total_masuk_dict[nama_barang] = total_masuk_dict.get(nama_barang, 0) + trans['jumlah_barang']

    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        total_keluar_dict[nama_barang] = total_keluar_dict.get(nama_barang, 0) + trans['jumlah_diterima']

    indonesian_date = ""
    if param_bulan:
        date_obj = datetime.strptime(param_bulan, "%Y-%m")
        formatted_date = date_obj.strftime("%B %Y")
        months_translation = {
            "January": "Januari",
            "February": "Februari",
            "March": "Maret",
            "April": "April",
            "May": "Mei",
            "June": "Juni",
            "July": "Juli",
            "August": "Agustus",
            "September": "September",
            "October": "Oktober",
            "November": "November",
            "December": "Desember"
        }
        indonesian_date = months_translation[formatted_date.split()[0]] + " " + formatted_date.split()[1]

    # Ambil nama barang dari all_transactions
    nama_barang_set = {t['nama_barang'] for t in all_transactions}
    
    # Filter items untuk hanya menampilkan barang yang ada dalam nama_barang_set
    items = list(db.items.find({'nama_barang': {'$in': list(nama_barang_set)}}))

    return render_template('adminbarang_laporanbarangperbulan.html', indonesian_date=indonesian_date, bulan=bulan, param_bulan=param_bulan, total_masuk_dict=total_masuk_dict, total_keluar_dict=total_keluar_dict, transactions=all_transactions, items=items, barang_id=barang_id, start_date=start_date, end_date=end_date, selected_item=selected_item)


@app.route('/laporan-barang-per-bulan/export/pdf', methods=['GET'])
@login_required(roles=['adminbarang'])
def laporanbarangperbulan_export_pdf():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    barang_id = request.args.get('barang_id')

    incoming_filter_conditions = {}
    outgoing_filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            incoming_filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
            outgoing_filter_conditions['$expr'] = {
                '$gte': [
                    {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                    start_date
                ]
            }
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400

    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in incoming_filter_conditions:
                incoming_filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                incoming_filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                incoming_filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
            
            if '$expr' in outgoing_filter_conditions:
                outgoing_filter_conditions['$expr'] = {
                    '$and': [
                        outgoing_filter_conditions['$expr'],
                        {'$lte': [
                            {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                            end_date
                        ]}
                    ]
                }
            else:
                outgoing_filter_conditions['$expr'] = {
                    '$lte': [
                        {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                        end_date
                    ]
                }
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

    selected_item = None
    nama_barang = None

    if barang_id:
        try:
            barang_id = ObjectId(barang_id)
            incoming_filter_conditions['barang_id'] = barang_id
            selected_item = db.items.find_one({'_id': barang_id})
            if selected_item:
                nama_barang = selected_item.get('nama_barang')
        except Exception as e:
            return jsonify({'message': 'Barang ID tidak valid!'}), 400

    # Ambil data dari incoming_transactions
    incoming_transactions = list(db.incoming_transactions.find(incoming_filter_conditions))

    # Ambil data dari staff_gudang dengan filter tanggal_penerimaan dan nama_barang
    barang_keluar_col = db2['staff_gudang']

    statuses_to_filter = ["Process", "Success"]
    outgoing_filter_conditions['is_verif'] = True
    outgoing_filter_conditions['status'] = {'$in': statuses_to_filter}

    if nama_barang:
        outgoing_filter_conditions['nama_barang'] = nama_barang

    # Ambil data dari barang_keluar_col dengan filter outgoing_filter_conditions
    outgoing_transactions = list(barang_keluar_col.find(outgoing_filter_conditions))

    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
    
    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['keterangan'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
        transaction['jumlah_barang'] = transaction['jumlah_diterima']
    
    # Sortir data berdasarkan tanggal
    # all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    
    for transaction in incoming_transactions:
        barang_id = transaction.get('barang_id')
        
        if barang_id:
            try:
                barang_id = ObjectId(barang_id)
            except Exception as e:
                transaction['nama_barang'] = 'Unknown'
                transaction['nama_kategori'] = 'Unknown'
                continue
            
            if barang_id not in items_cache:
                item = db.items.find_one({'_id': barang_id})
                if item:
                    items_cache[barang_id] = item
            
            transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
            
            if barang_id in items_cache:
                kategori_id = items_cache[barang_id]['kategori_id']
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'

    # Process outgoing_transactions (which have nama_barang)
    for transaction in outgoing_transactions:
        nama_barang = transaction.get('nama_barang')
        
        if nama_barang:
            if nama_barang not in items_cache:
                item = db.items.find_one({'nama_barang': nama_barang})
                if item:
                    items_cache[nama_barang] = item
            
            if nama_barang in items_cache:
                barang_id = items_cache[nama_barang]['_id']
                kategori_id = items_cache[nama_barang]['kategori_id']
                transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
        else:
            transaction['nama_kategori'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Gabungkan data
    # Sort transactions by date
    incoming_transactions.sort(key=lambda x: x['date'])
    outgoing_transactions.sort(key=lambda x: x['date'])

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']

    # Combine transactions for output
    all_transactions = incoming_transactions + outgoing_transactions

    # all_transactions = incoming_transactions + outgoing_transactions
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))

    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}

    for transaction in all_transactions:
        barang_id = transaction['barang_id']

        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'

        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category

            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

    # Prepare the heading
    heading = "Kartu Stock Semua Barang"
    if start_date or end_date or selected_item:
        heading = "Kartu Stock "
        if selected_item:
            heading += selected_item['nama_barang'] + " "
        heading += "Periode "
        heading += start_date.strftime('%d-%m-%Y') if start_date else "-"
        heading += " sampai "
        heading += end_date.strftime('%d-%m-%Y') if end_date else "-"

    # Render template HTML
    rendered_template = render_template('export_kartustock.html', transactions=all_transactions, heading=heading)

    # Buat file PDF
    pdf_file_path = 'kartustock.pdf'
    with open(pdf_file_path, 'wb') as file:
        pisa.CreatePDF(rendered_template, dest=file)

    # Mengirim file PDF sebagai respons
    return send_file(pdf_file_path, as_attachment=True)

@app.route('/laporan-barang-per-bulan/export/xsl', methods=['GET'])
@login_required(roles=['adminbarang'])
def laporanbarangperbulan_export_excel():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    barang_id = request.args.get('barang_id')

    incoming_filter_conditions = {}
    outgoing_filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            incoming_filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
            outgoing_filter_conditions['$expr'] = {
                '$gte': [
                    {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                    start_date
                ]
            }
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400

    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in incoming_filter_conditions:
                incoming_filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                incoming_filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                incoming_filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
            
            if '$expr' in outgoing_filter_conditions:
                outgoing_filter_conditions['$expr'] = {
                    '$and': [
                        outgoing_filter_conditions['$expr'],
                        {'$lte': [
                            {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                            end_date
                        ]}
                    ]
                }
            else:
                outgoing_filter_conditions['$expr'] = {
                    '$lte': [
                        {'$dateFromString': {'dateString': '$tanggal_penerimaan', 'format': '%Y-%m-%d'}},
                        end_date
                    ]
                }
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

    selected_item = None
    nama_barang = None

    if barang_id:
        try:
            barang_id = ObjectId(barang_id)
            incoming_filter_conditions['barang_id'] = barang_id
            selected_item = db.items.find_one({'_id': barang_id})
            if selected_item:
                nama_barang = selected_item.get('nama_barang')
        except Exception as e:
            return jsonify({'message': 'Barang ID tidak valid!'}), 400

    # Ambil data dari incoming_transactions
    incoming_transactions = list(db.incoming_transactions.find(incoming_filter_conditions))

    # Ambil data dari staff_gudang dengan filter tanggal_penerimaan dan nama_barang
    barang_keluar_col = db2['staff_gudang']

    statuses_to_filter = ["Process", "Success"]
    outgoing_filter_conditions['is_verif'] = True
    outgoing_filter_conditions['status'] = {'$in': statuses_to_filter}

    if nama_barang:
        outgoing_filter_conditions['nama_barang'] = nama_barang

    # Ambil data dari barang_keluar_col dengan filter outgoing_filter_conditions
    outgoing_transactions = list(barang_keluar_col.find(outgoing_filter_conditions))

    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
    
    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['keterangan'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
        transaction['jumlah_barang'] = transaction['jumlah_diterima']
    
    # Sortir data berdasarkan tanggal
    # all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    
    for transaction in incoming_transactions:
        barang_id = transaction.get('barang_id')
        
        if barang_id:
            try:
                barang_id = ObjectId(barang_id)
            except Exception as e:
                transaction['nama_barang'] = 'Unknown'
                transaction['nama_kategori'] = 'Unknown'
                continue
            
            if barang_id not in items_cache:
                item = db.items.find_one({'_id': barang_id})
                if item:
                    items_cache[barang_id] = item
            
            transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
            
            if barang_id in items_cache:
                kategori_id = items_cache[barang_id]['kategori_id']
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'

    # Process outgoing_transactions (which have nama_barang)
    for transaction in outgoing_transactions:
        nama_barang = transaction.get('nama_barang')
        
        if nama_barang:
            if nama_barang not in items_cache:
                item = db.items.find_one({'nama_barang': nama_barang})
                if item:
                    items_cache[nama_barang] = item
            
            if nama_barang in items_cache:
                barang_id = items_cache[nama_barang]['_id']
                kategori_id = items_cache[nama_barang]['kategori_id']
                transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
        else:
            transaction['nama_kategori'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Gabungkan data
    # Sort transactions by date
    incoming_transactions.sort(key=lambda x: x['date'])
    outgoing_transactions.sort(key=lambda x: x['date'])

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']

    # Combine transactions for output
    all_transactions = incoming_transactions + outgoing_transactions

    # all_transactions = incoming_transactions + outgoing_transactions
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    
    for transaction in all_transactions:
        barang_id = transaction['barang_id']
        
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'


    selected_columns = ['tanggal_masuk', 'tanggal_keluar', 'nama_barang', 'jumlah_barang', 'stock_tersedia', 'keterangan']

    # Konversi data ke DataFrame
    df = pandas.DataFrame(all_transactions, columns=selected_columns)

    # Buat file Excel
    excel_file_path = 'export_kartustock.xlsx'
    df.to_excel(excel_file_path, index=False)

    # Mengirim file Excel sebagai respons
    return send_file(excel_file_path, as_attachment=True)

@app.route('/stocktersedia', methods=['GET'])
@login_required(roles=['adminbarang'])
def stock_tersedia():
    items = list(db.items.find())
    categories = list(db.categories.find())
    satuans = list(db.satuan.find())

    # Create dictionaries to map IDs to names
    categories_dict = {str(category['_id']): category['nama_kategori'] for category in categories}
    satuans_dict = {str(satuan['_id']): satuan['nama_satuan'] for satuan in satuans}

    # Add 'nama_kategori' and 'nama_satuan' to each item
    for item in items:
        item['nama_kategori'] = categories_dict.get(str(item['kategori_id']), 'Unknown')
        item['nama_satuan'] = satuans_dict.get(str(item['satuan_id']), 'Unknown')

    return render_template('adminbarang_stocktersedia.html', items=items)

@app.route('/stockminimum', methods=['GET'])
@login_required(roles=['adminbarang'])
def stockminimum():
    items = list(db.items.find({'$expr': {'$lte': ['$stock_tersedia', '$stock_minimum']}}))
    
    categories = list(db.categories.find())
    satuans = list(db.satuan.find())

    # Create dictionaries to map IDs to names
    categories_dict = {str(category['_id']): category['nama_kategori'] for category in categories}
    satuans_dict = {str(satuan['_id']): satuan['nama_satuan'] for satuan in satuans}

    for item in items:
        item['nama_kategori'] = categories_dict.get(str(item['kategori_id']), 'Unknown')
        item['nama_satuan'] = satuans_dict.get(str(item['satuan_id']), 'Unknown')

    return render_template('adminbarang_stockminimum.html', items=items)

@app.route('/laporan-barang', methods=['GET'])
@login_required(roles=['adminbarang'])
def adbarlaporanbarang():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    jenis_laporan = request.args.get('jenis_laporan')

    # Buat filter untuk MongoDB
    filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in filter_conditions:
                filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400
        
    if jenis_laporan == 'out':
        filter_conditions = {
            'is_verif': True,
            'status': 'Process'
        }

        if start_date:
            try:
                start_date_dt = start_date
                start_date_str = start_date_dt.strftime('%Y-%m-%d')
            except ValueError:
                return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400

        if end_date:
            try:
                end_date_dt = end_date
                end_date_str = end_date_dt.strftime('%Y-%m-%d')
            except ValueError:
                return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

        pipeline = [
            {'$match': filter_conditions},
            {
                '$addFields': {
                    'tanggal_penerimaan_date': {
                        '$dateFromString': {
                            'dateString': '$tanggal_penerimaan',
                            'format': '%Y-%m-%d'
                        }
                    }
                }
            }
        ]

        if start_date:
            pipeline.append({'$match': {'tanggal_penerimaan_date': {'$gte': start_date_dt}}})

        if end_date:
            pipeline.append({'$match': {'tanggal_penerimaan_date': {'$lte': end_date_dt}}})

        pipeline.append({'$sort': {'tanggal_penerimaan_date': 1}})

        barang_keluar_col = db2['staff_gudang']
        barang_keluar_tbl = list(barang_keluar_col.aggregate(pipeline))

        items2 = list(db.items.find())
        categories2 = list(db.categories.find())
        satuans2 = list(db.satuan.find())  # Fetch satuan data

        categories_dict = {category['_id']: category for category in categories2}
        satuans_dict = {satuan['_id']: satuan['nama_satuan'] for satuan in satuans2}  # Map satuan data
        for item in items2:
            kategori_id = item.get('kategori_id')
            if kategori_id in categories_dict:
                item['kategori'] = categories_dict[kategori_id]
            else:
                item['kategori'] = "Kebersihan"

            satuan_id = item.get('satuan_id')
            if satuan_id in satuans_dict:
                item['satuan'] = satuans_dict[satuan_id]
            else:
                item['satuan'] = "Box"

        # items_dict = {item['nama_barang']: item['satuan'] for item in items2}
        satuan_dict = {item['nama_barang']: item['satuan'] for item in items2}
        kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}

        for item in barang_keluar_tbl:
            item['keterangan'] = 'Ruangan ' + item['ruangan']
            item['jumlah_barang'] = item['jumlah_diterima']
            item['tanggal_keluar'] = datetime.strptime(item['tanggal_penerimaan'], '%Y-%m-%d')
            nama_barang = item.get('nama_barang')
            # if nama_barang in items_dict:
            #     item['satuan'] = items_dict[nama_barang]
            # else:
            #     item['satuan'] = 'pcs'

            if nama_barang in kategori_dict:
                item['kategori'] = kategori_dict[nama_barang]['nama_kategori']
                item['nama_kategori'] = kategori_dict[nama_barang]['nama_kategori']
            else:
                item['kategori'] = "-"
                item['nama_kategori'] = "-"

            # Add satuan information
            if nama_barang in satuan_dict:
                item['satuan'] = satuan_dict[nama_barang]
            else:
                item['satuan'] = 'Box'

        transactions = barang_keluar_tbl
        transactions.sort(key=lambda x: x.get('tanggal_penerimaan'))
    else:
        transactions = list(db.incoming_transactions.find(filter_conditions))
        transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))

        items_cache = {}
        categories_cache = {}
        satuan_cache = {}  # Cache satuan data

        for transaction in transactions:
            barang_id = transaction['barang_id']

            if barang_id not in items_cache:
                item = db.items.find_one({'_id': ObjectId(barang_id)})
                if item:
                    items_cache[barang_id] = item

            transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'

            if barang_id in items_cache:
                kategori_id = items_cache[barang_id]['kategori_id']
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category

                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

                # Add satuan information
                satuan_id = items_cache[barang_id]['satuan_id']
                if satuan_id not in satuan_cache:
                    satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                    if satuan:
                        satuan_cache[satuan_id] = satuan

                transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'

    return render_template('adminbarang_laporanbarang.html', 
                           transactions=transactions,
                           jenis_laporan=jenis_laporan, 
                           start_date=start_date, 
                           end_date=end_date)

@app.route('/laporan-barang/export/pdf', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanbarang_export_pdf():
    # Ambil data transaksi
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    jenis_laporan = request.args.get('jenis_laporan')

    # Buat filter untuk MongoDB
    filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in filter_conditions:
                filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

    if jenis_laporan == 'out':
        filter_conditions = {
            'is_verif': True,
            'status': 'Process'
        }

        pipeline = [
            {'$match': filter_conditions},
            {
                '$addFields': {
                    'tanggal_penerimaan_date': {
                        '$dateFromString': {
                            'dateString': '$tanggal_penerimaan',
                            'format': '%Y-%m-%d'
                        }
                    }
                }
            }
        ]

        if start_date:
            pipeline.append({'$match': {'tanggal_penerimaan_date': {'$gte': start_date}}})

        if end_date:
            pipeline.append({'$match': {'tanggal_penerimaan_date': {'$lte': end_date}}})

        pipeline.append({'$sort': {'tanggal_penerimaan_date': 1}})

        barang_keluar_col = db2['staff_gudang']
        barang_keluar_tbl = list(barang_keluar_col.aggregate(pipeline))

        items2 = list(db.items.find())
        categories2 = list(db.categories.find())

        categories_dict = {category['_id']: category for category in categories2}
        for item in items2:
            kategori_id = item.get('kategori_id')
            if kategori_id in categories_dict:
                item['kategori'] = categories_dict[kategori_id]
            else:
                item['kategori'] = "Kebersihan"

        items_dict = {item['nama_barang']: item.get('satuan', 'Unknown') for item in items2}
        kategori_dict = {item['nama_barang']: item.get('kategori', {'nama_kategori': '-'}) for item in items2}

        for item in barang_keluar_tbl:
            item['keterangan'] = 'Ruangan '+item.get('ruangan', 'Unknown')
            item['jumlah_barang'] = item.get('jumlah_diterima', 0)
            item['tanggal_keluar'] = datetime.strptime(item.get('tanggal_penerimaan', '1970-01-01'), '%Y-%m-%d')
            nama_barang = item.get('nama_barang', 'Unknown')
            item['satuan'] = items_dict.get(nama_barang, 'pcs')

            kategori = kategori_dict.get(nama_barang, {'nama_kategori': '-'})
            item['kategori'] = kategori['nama_kategori']
            item['nama_kategori'] = kategori['nama_kategori']

        transactions = barang_keluar_tbl
        transactions.sort(key=lambda x: x.get('tanggal_penerimaan'))
    else:
        transactions = list(db.incoming_transactions.find(filter_conditions))
        
        transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
        
        items_cache = {}
        categories_cache = {}
        
        for transaction in transactions:
            barang_id = transaction['barang_id']
            
            if barang_id not in items_cache:
                item = db.items.find_one({'_id': ObjectId(barang_id)})
                if item:
                    items_cache[barang_id] = item

            transaction['nama_barang'] = items_cache.get(barang_id, {}).get('nama_barang', 'Unknown')
            transaction['satuan'] = items_cache.get(barang_id, {}).get('satuan', 'Unknown')
            
            if barang_id in items_cache:
                kategori_id = items_cache[barang_id].get('kategori_id')
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category
                
                transaction['nama_kategori'] = categories_cache.get(kategori_id, {}).get('nama_kategori', 'Unknown')

    # Render template HTML
    rendered_template = render_template(
        'export_laporan_barang.html', 
        transactions=transactions, 
        jenis_laporan=jenis_laporan,
        start_date=start_date,
        end_date=end_date
    )

    # Buat file PDF
    pdf_file_path = 'export_laporan_barang.pdf'
    with open(pdf_file_path, 'wb') as file:
        pisa.CreatePDF(rendered_template, dest=file)

    # Mengirim file PDF sebagai respons
    return send_file(pdf_file_path, as_attachment=True)


@app.route('/laporan-barang/export/xsl', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanbarang_export_excel():
    # Ambil data transaksi
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    jenis_laporan = request.args.get('jenis_laporan')

    # Buat filter untuk MongoDB
    filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in filter_conditions:
                filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

    if jenis_laporan == 'out':
        filter_conditions = {
            'is_verif': True,
            'status': 'Process'
        }

        pipeline = [
            {'$match': filter_conditions},
            {
                '$addFields': {
                    'tanggal_penerimaan_date': {
                        '$dateFromString': {
                            'dateString': '$tanggal_penerimaan',
                            'format': '%Y-%m-%d'
                        }
                    }
                }
            }
        ]

        if start_date:
            pipeline.append({'$match': {'tanggal_penerimaan_date': {'$gte': start_date}}})

        if end_date:
            pipeline.append({'$match': {'tanggal_penerimaan_date': {'$lte': end_date}}})

        pipeline.append({'$sort': {'tanggal_penerimaan_date': 1}})

        barang_keluar_col = db2['staff_gudang']
        barang_keluar_tbl = list(barang_keluar_col.aggregate(pipeline))

        items2 = list(db.items.find())
        categories2 = list(db.categories.find())

        categories_dict = {category['_id']: category for category in categories2}
        for item in items2:
            kategori_id = item.get('kategori_id')
            if kategori_id in categories_dict:
                item['kategori'] = categories_dict[kategori_id]
            else:
                item['kategori'] = "Kebersihan"

        items_dict = {item['nama_barang']: item['nama_barang'] for item in items2}
        kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}

        for item in barang_keluar_tbl:
            item['keterangan'] = 'Ruangan ' + item.get('ruangan', 'Unknown')
            item['jumlah_barang'] = item.get('jumlah_diterima', 0)
            item['tanggal_keluar'] = datetime.strptime(item.get('tanggal_penerimaan', '1900-01-01'), '%Y-%m-%d')
            nama_barang = item.get('nama_barang', 'Unknown')
            item['satuan'] = items_dict.get(nama_barang, 'pcs')

            kategori = kategori_dict.get(nama_barang, {'nama_kategori': '-'})
            item['kategori'] = kategori['nama_kategori']
            item['nama_kategori'] = kategori['nama_kategori']

        transactions = barang_keluar_tbl
        transactions.sort(key=lambda x: x.get('tanggal_penerimaan', datetime.min))
    else:
        transactions = list(db.incoming_transactions.find(filter_conditions))
        transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar', datetime.min)))
        
        items_cache = {}
        categories_cache = {}

        for transaction in transactions:
            barang_id = transaction.get('barang_id')
            
            if barang_id not in items_cache:
                item = db.items.find_one({'_id': ObjectId(barang_id)})
                if item:
                    items_cache[barang_id] = item

            item = items_cache.get(barang_id, {})
            transaction['nama_barang'] = item.get('nama_barang', 'Unknown')
            transaction['satuan'] = item.get('satuan', 'Unknown')
            
            kategori_id = item.get('kategori_id')
            if kategori_id and kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            category = categories_cache.get(kategori_id, {})
            transaction['nama_kategori'] = category.get('nama_kategori', 'Unknown')

    # Konversi data ke DataFrame
    if jenis_laporan == 'out':
        selected_columns = ['tanggal_keluar', 'nama_kategori', 'nama_barang', 'jumlah_barang', 'harga_barang', 'keterangan']
    else:
        selected_columns = ['tanggal_masuk', 'nama_kategori', 'nama_barang', 'jumlah_barang', 'harga_barang', 'keterangan']

    df = pandas.DataFrame(transactions, columns=selected_columns)

    # Buat file Excel
    excel_file_path = 'export_laporan_barang.xlsx'
    df.to_excel(excel_file_path, index=False)

    # Mengirim file Excel sebagai respons
    return send_file(excel_file_path, as_attachment=True)

@app.route('/laporan-stock', methods=['GET'])
@login_required(roles=['adminbarang'])
def adbarlaporanstock():
    jenis_laporan = request.args.get('jenis_laporan')

    if jenis_laporan == 'minimum':
        items = list(db.items.find({'$expr': {'$lte': ['$stock_tersedia', '$stock_minimum']}}))
    else:
        items = list(db.items.find())

    for item in items:
        category = db.categories.find_one({'_id': item['kategori_id']})
        item['nama_kategori'] = category['nama_kategori'] if category else 'Unknown'

    for item in items:
        satuan = db.satuan.find_one({'_id': item['satuan_id']})
        item['nama_satuan'] = satuan['nama_satuan'] if satuan else 'Unknown'

    return render_template('adminbarang_laporanstock.html', items=items, jenis_laporan=jenis_laporan)

@app.route('/laporan-stock/export/pdf', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanstock_export_pdf():
    # Ambil data item
    jenis_laporan = request.args.get('jenis_laporan')

    if jenis_laporan == 'minimum':
        items = list(db.items.find({'$expr': {'$lte': ['$stock_tersedia', '$stock_minimum']}}))
    else:
        items = list(db.items.find())

    for item in items:
        category = db.categories.find_one({'_id': item['kategori_id']})
        item['nama_kategori'] = category['nama_kategori'] if category else 'Unknown'

        satuan = db.satuan.find_one({'_id': item['satuan_id']})
        item['nama_satuan'] = satuan['nama_satuan'] if satuan else 'Unknown'

    # Render template HTML
    rendered_template = render_template('export_laporan_stock.html', items=items, jenis_laporan=jenis_laporan)

    # Buat file PDF
    pdf_file_path = 'export_laporan_stock.pdf'
    with open(pdf_file_path, 'wb') as file:
        pisa.CreatePDF(rendered_template, dest=file)

    # Mengirim file PDF sebagai respons
    return send_file(pdf_file_path, as_attachment=True)

@app.route('/laporan-stock/export/xsl', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanstock_export_excel():
    # Ambil data item
    jenis_laporan = request.args.get('jenis_laporan')

    if jenis_laporan == 'minimum':
        items = list(db.items.find({'$expr': {'$lte': ['$stock_tersedia', '$stock_minimum']}}))
    else:
        items = list(db.items.find())

    for item in items:
        category = db.categories.find_one({'_id': item['kategori_id']})
        item['nama_kategori'] = category['nama_kategori'] if category else 'Unknown'

        satuan = db.satuan.find_one({'_id': item['satuan_id']})
        item['nama_satuan'] = satuan['nama_satuan'] if satuan else 'Unknown'

    selected_columns = ['nama_kategori', 'nama_barang', 'nama_satuan', 'stock_tersedia']
    
    # Konversi data ke DataFrame
    df = pandas.DataFrame(items, columns=selected_columns)

    # Buat file Excel
    excel_file_path = 'export_laporan_stock.xlsx'
    df.to_excel(excel_file_path, index=False)

    # Mengirim file Excel sebagai respons
    return send_file(excel_file_path, as_attachment=True)

@app.route('/laporan-persediaan', methods=['GET'])
@login_required(roles=['adminbarang'])
def adbarlaporanpersediaan():
    # Ambil filter bulan dari request
    bulan = request.args.get('bulan')
    param_bulan = request.args.get('bulan')

    # Buat filter untuk MongoDB
    filter_conditions = {}
    outgoing_conditions = {
        'is_verif': True,
        'status': 'Process'
    }
    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    ori_bulan = bulan

    if bulan:
        try:
            # Split bulan menjadi tahun dan bulan
            tahun, bulan = bulan.split('-')
            # Ambil tanggal awal dan akhir bulan
            start_date = datetime(int(tahun), int(bulan), 1)
            if int(bulan) == 12:
                end_date = datetime(int(tahun) + 1, 1, 1)
            else:
                end_date = datetime(int(tahun), int(bulan) + 1, 1)
            # Masukkan filter ke dalam kondisi
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date, '$lte': end_date}},
                {'tanggal_keluar': {'$gte': start_date, '$lte': end_date}}
            ]

        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400

        try:
            _tahun, _bulan = ori_bulan.split('-')
            _start_date = f"{_tahun}-{_bulan}-01"
            if int(_bulan) == 12:
                _end_date = f"{int(_tahun) + 1}-01-01"
            else:
                _end_date = f"{_tahun}-{int(_bulan) + 1:02d}-01"

            outgoing_conditions['$or'] = [
                {'tanggal_pengajuan': {'$gte': _start_date, '$lt': _end_date}},
                {'tanggal_penerimaan': {'$gte': _start_date, '$lt': _end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400
        
    # Ambil data dari incoming_transactions dan outgoing_transactions
    incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    barang_keluar_col = db2['staff_gudang']
    barang_keluar_tbl = list(barang_keluar_col.find(outgoing_conditions).sort('tanggal_penerimaan', 1))
    
    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None

    items2 = list(db.items.find())
    categories2 = list(db.categories.find())
    satuan2 = list(db.satuan.find())  # Fetch satuan data
    
    categories_dict = {category['_id']: category for category in categories2}
    satuans_dict = {satuan['_id']: satuan['nama_satuan'] for satuan in satuan2}  # Map satuan data
    for item in items2:
        kategori_id = item.get('kategori_id')
        if kategori_id in categories_dict:
            item['kategori'] = categories_dict[kategori_id]
        else:
            item['kategori'] = "Kebersihan"

        satuan_id = item.get('satuan_id')
        if satuan_id in satuans_dict:
            item['satuan'] = satuans_dict[satuan_id]
        else:
            item['satuan'] = "Kebersihan"

    kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}
    satuan_dict = {item['nama_barang']: item['satuan'] for item in items2}

    for item in barang_keluar_tbl:
        nama_barang = item.get('nama_barang')

        if nama_barang in kategori_dict:
            item['kategori'] = kategori_dict[nama_barang]
        else:
            item['kategori'] = "Kebersihan"

        if nama_barang in satuan_dict:
            item['satuan'] = satuan_dict[nama_barang]
        else:
            item['satuan'] = 'Box'
            
    selected_item = None
    nama_barang = None

    outgoing_transactions = barang_keluar_tbl

    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
        transaction['jumlah_barang'] = transaction['jumlah_diterima']
  
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    satuan_cache = {}  # Cache satuan data
    monthly_recaps_cache = {}

    # Mengambil saldo_awal dari monthly_recaps
    if f"{start_date.year}-{start_date.month}" not in monthly_recaps_cache:
        recap = db.monthly_recaps.find_one({'bulan': start_date.month, 'tahun': start_date.year})
        if recap:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = recap['saldo_awal']
        else:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = 0
    
    saldo_awal = monthly_recaps_cache[f"{start_date.year}-{start_date.month}"]
    current_saldo_akhir = saldo_awal
    
    for transaction in incoming_transactions:
        barang_id = transaction['barang_id']
        
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

            # Add satuan information
            satuan_id = items_cache[barang_id]['satuan_id']
            if satuan_id not in satuan_cache:
                satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                if satuan:
                    satuan_cache[satuan_id] = satuan

            transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'

        # Calculate saldo_awal, pengeluaran, and saldo_akhir
        if transaction['jenis_transaksi'] == 'Masuk':
            pengeluaran = transaction['harga_barang']
            current_saldo_akhir -= pengeluaran
            
            transaction['saldo_awal'] = saldo_awal
            transaction['pengeluaran'] = pengeluaran
            transaction['saldo_akhir'] = current_saldo_akhir

        for transaction in outgoing_transactions:
            nama_barang = transaction.get('nama_barang')
            
            if nama_barang:
                if nama_barang not in items_cache:
                    item = db.items.find_one({'nama_barang': nama_barang})
                    if item:
                        items_cache[nama_barang] = item
                
                if nama_barang in items_cache:
                    barang_id = items_cache[nama_barang]['_id']
                    kategori_id = items_cache[nama_barang]['kategori_id']
                    satuan_id = items_cache[nama_barang]['satuan_id']
                    transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                    
                    if kategori_id not in categories_cache:
                        category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                        if category:
                            categories_cache[kategori_id] = category
                    
                    transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
                    
                    if satuan_id not in satuan_cache:
                        satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                        if satuan:
                            satuan_cache[satuan_id] = satuan

                    transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'
                else:
                    transaction['nama_kategori'] = 'Unknown'
                    transaction['nama_satuan'] = 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
                transaction['nama_satuan'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']
    
    # Gabungkan data
    all_transactions = incoming_transactions + outgoing_transactions
    
    # Sortir data berdasarkan tanggal
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))

    indonesian_date = ""
    if param_bulan:
        # Parse the date
        date_obj = datetime.strptime(param_bulan, "%Y-%m")

        # Format the date to "Juli 2024"
        formatted_date = date_obj.strftime("%B %Y")

        # Translate the month to Indonesian
        months_translation = {
            "January": "Januari",
            "February": "Februari",
            "March": "Maret",
            "April": "April",
            "May": "Mei",
            "June": "Juni",
            "July": "Juli",
            "August": "Agustus",
            "September": "September",
            "October": "Oktober",
            "November": "November",
            "December": "Desember"
        }

        indonesian_date = months_translation[formatted_date.split()[0]] + " " + formatted_date.split()[1]

    return render_template('adminbarang_laporanpersediaan.html', indonesian_date=indonesian_date, param_bulan=param_bulan, transactions=all_transactions)

@app.route('/laporan-persediaan/export/pdf', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanpersediaan_export_pdf():
    # Ambil filter bulan dari request
    bulan = request.args.get('bulan')
    param_bulan = request.args.get('bulan')

    # Buat filter untuk MongoDB
    filter_conditions = {}
    outgoing_conditions = {
        'is_verif': True,
        'status': 'Process'
    }
    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    ori_bulan = bulan

    if bulan:
        try:
            # Split bulan menjadi tahun dan bulan
            tahun, bulan = bulan.split('-')
            # Ambil tanggal awal dan akhir bulan
            start_date = datetime(int(tahun), int(bulan), 1)
            if int(bulan) == 12:
                end_date = datetime(int(tahun) + 1, 1, 1)
            else:
                end_date = datetime(int(tahun), int(bulan) + 1, 1)
            # Masukkan filter ke dalam kondisi
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date, '$lte': end_date}},
                {'tanggal_keluar': {'$gte': start_date, '$lte': end_date}}
            ]

        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400

        try:
            _tahun, _bulan = ori_bulan.split('-')
            _start_date = f"{_tahun}-{_bulan}-01"
            if int(_bulan) == 12:
                _end_date = f"{int(_tahun) + 1}-01-01"
            else:
                _end_date = f"{_tahun}-{int(_bulan) + 1:02d}-01"

            outgoing_conditions['$or'] = [
                {'tanggal_pengajuan': {'$gte': _start_date, '$lt': _end_date}},
                {'tanggal_penerimaan': {'$gte': _start_date, '$lt': _end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400
        
    # Ambil data dari incoming_transactions dan outgoing_transactions
    incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    barang_keluar_col = db2['staff_gudang']
    barang_keluar_tbl = list(barang_keluar_col.find(outgoing_conditions).sort('tanggal_penerimaan', 1))
    
    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None

    items2 = list(db.items.find())
    categories2 = list(db.categories.find())
    satuan2 = list(db.satuan.find())  # Fetch satuan data
    
    categories_dict = {category['_id']: category for category in categories2}
    satuans_dict = {satuan['_id']: satuan['nama_satuan'] for satuan in satuan2}  # Map satuan data
    for item in items2:
        kategori_id = item.get('kategori_id')
        if kategori_id in categories_dict:
            item['kategori'] = categories_dict[kategori_id]
        else:
            item['kategori'] = "Kebersihan"

        satuan_id = item.get('satuan_id')
        if satuan_id in satuans_dict:
            item['satuan'] = satuans_dict[satuan_id]
        else:
            item['satuan'] = "Kebersihan"

    kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}
    satuan_dict = {item['nama_barang']: item['satuan'] for item in items2}

    for item in barang_keluar_tbl:
        nama_barang = item.get('nama_barang')

        if nama_barang in kategori_dict:
            item['kategori'] = kategori_dict[nama_barang]
        else:
            item['kategori'] = "Kebersihan"

        if nama_barang in satuan_dict:
            item['satuan'] = satuan_dict[nama_barang]
        else:
            item['satuan'] = 'Box'
            
    selected_item = None
    nama_barang = None

    outgoing_transactions = barang_keluar_tbl

    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
        transaction['jumlah_barang'] = transaction['jumlah_diterima']
  
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    satuan_cache = {}  # Cache satuan data
    monthly_recaps_cache = {}

    # Mengambil saldo_awal dari monthly_recaps
    if f"{start_date.year}-{start_date.month}" not in monthly_recaps_cache:
        recap = db.monthly_recaps.find_one({'bulan': start_date.month, 'tahun': start_date.year})
        if recap:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = recap['saldo_awal']
        else:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = 0
    
    saldo_awal = monthly_recaps_cache[f"{start_date.year}-{start_date.month}"]
    current_saldo_akhir = saldo_awal
    
    for transaction in incoming_transactions:
        barang_id = transaction['barang_id']
        
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

            # Add satuan information
            satuan_id = items_cache[barang_id]['satuan_id']
            if satuan_id not in satuan_cache:
                satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                if satuan:
                    satuan_cache[satuan_id] = satuan

            transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'

        # Calculate saldo_awal, pengeluaran, and saldo_akhir
        if transaction['jenis_transaksi'] == 'Masuk':
            pengeluaran = transaction['harga_barang']
            current_saldo_akhir -= pengeluaran
            
            transaction['saldo_awal'] = saldo_awal
            transaction['pengeluaran'] = pengeluaran
            transaction['saldo_akhir'] = current_saldo_akhir

        for transaction in outgoing_transactions:
            nama_barang = transaction.get('nama_barang')
            
            if nama_barang:
                if nama_barang not in items_cache:
                    item = db.items.find_one({'nama_barang': nama_barang})
                    if item:
                        items_cache[nama_barang] = item
                
                if nama_barang in items_cache:
                    barang_id = items_cache[nama_barang]['_id']
                    kategori_id = items_cache[nama_barang]['kategori_id']
                    satuan_id = items_cache[nama_barang]['satuan_id']
                    transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                    
                    if kategori_id not in categories_cache:
                        category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                        if category:
                            categories_cache[kategori_id] = category
                    
                    transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
                    
                    if satuan_id not in satuan_cache:
                        satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                        if satuan:
                            satuan_cache[satuan_id] = satuan

                    transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'
                else:
                    transaction['nama_kategori'] = 'Unknown'
                    transaction['nama_satuan'] = 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
                transaction['nama_satuan'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']
    
    # Gabungkan data
    all_transactions = incoming_transactions + outgoing_transactions
    
    # Sortir data berdasarkan tanggal
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))

    indonesian_date = ""
    if param_bulan:
        # Parse the date
        date_obj = datetime.strptime(param_bulan, "%Y-%m")

        # Format the date to "Juli 2024"
        formatted_date = date_obj.strftime("%B %Y")

        # Translate the month to Indonesian
        months_translation = {
            "January": "Januari",
            "February": "Februari",
            "March": "Maret",
            "April": "April",
            "May": "Mei",
            "June": "Juni",
            "July": "Juli",
            "August": "Agustus",
            "September": "September",
            "October": "Oktober",
            "November": "November",
            "December": "Desember"
        }

        indonesian_date = months_translation[formatted_date.split()[0]] + " " + formatted_date.split()[1]

    # Render template HTML
    rendered_template = render_template('export_laporan_persediaan.html', param_bulan=param_bulan, indonesian_date=indonesian_date, transactions=all_transactions, bulan=bulan)

    # Buat file PDF
    pdf_file_path = 'export_laporan_persediaan.pdf'
    with open(pdf_file_path, 'wb') as file:
        pisa.CreatePDF(rendered_template, dest=file)

    # Mengirim file PDF sebagai respons
    return send_file(pdf_file_path, as_attachment=True)

@app.route('/laporan-persediaan/export/xsl', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanpersediaan_export_excel():
    # Ambil filter bulan dari request
    bulan = request.args.get('bulan')

    # Buat filter untuk MongoDB
    filter_conditions = {}
    outgoing_conditions = {
        'is_verif': True,
        'status': 'Process'
    }
    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    ori_bulan = bulan

    if bulan:
        try:
            # Split bulan menjadi tahun dan bulan
            tahun, bulan = bulan.split('-')
            # Ambil tanggal awal dan akhir bulan
            start_date = datetime(int(tahun), int(bulan), 1)
            if int(bulan) == 12:
                end_date = datetime(int(tahun) + 1, 1, 1)
            else:
                end_date = datetime(int(tahun), int(bulan) + 1, 1)
            # Masukkan filter ke dalam kondisi
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date, '$lte': end_date}},
                {'tanggal_keluar': {'$gte': start_date, '$lte': end_date}}
            ]

        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400

        try:
            _tahun, _bulan = ori_bulan.split('-')
            _start_date = f"{_tahun}-{_bulan}-01"
            if int(_bulan) == 12:
                _end_date = f"{int(_tahun) + 1}-01-01"
            else:
                _end_date = f"{_tahun}-{int(_bulan) + 1:02d}-01"

            outgoing_conditions['$or'] = [
                {'tanggal_pengajuan': {'$gte': _start_date, '$lt': _end_date}},
                {'tanggal_penerimaan': {'$gte': _start_date, '$lt': _end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400
        
    # Ambil data dari incoming_transactions dan outgoing_transactions
    incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    barang_keluar_col = db2['staff_gudang']
    barang_keluar_tbl = list(barang_keluar_col.find(outgoing_conditions).sort('tanggal_penerimaan', 1))
    
    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None

    items2 = list(db.items.find())
    categories2 = list(db.categories.find())
    satuan2 = list(db.satuan.find())  # Fetch satuan data
    
    categories_dict = {category['_id']: category for category in categories2}
    satuans_dict = {satuan['_id']: satuan['nama_satuan'] for satuan in satuan2}  # Map satuan data
    for item in items2:
        kategori_id = item.get('kategori_id')
        if kategori_id in categories_dict:
            item['kategori'] = categories_dict[kategori_id]
        else:
            item['kategori'] = "Kebersihan"

        satuan_id = item.get('satuan_id')
        if satuan_id in satuans_dict:
            item['satuan'] = satuans_dict[satuan_id]
        else:
            item['satuan'] = "Kebersihan"

    kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}
    satuan_dict = {item['nama_barang']: item['satuan'] for item in items2}

    for item in barang_keluar_tbl:
        nama_barang = item.get('nama_barang')

        if nama_barang in kategori_dict:
            item['kategori'] = kategori_dict[nama_barang]
        else:
            item['kategori'] = "Kebersihan"

        if nama_barang in satuan_dict:
            item['satuan'] = satuan_dict[nama_barang]
        else:
            item['satuan'] = 'Box'
            
    selected_item = None
    nama_barang = None

    outgoing_transactions = barang_keluar_tbl

    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
        transaction['jumlah_barang'] = transaction['jumlah_diterima']
  
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    satuan_cache = {}  # Cache satuan data
    monthly_recaps_cache = {}

    # Mengambil saldo_awal dari monthly_recaps
    if f"{start_date.year}-{start_date.month}" not in monthly_recaps_cache:
        recap = db.monthly_recaps.find_one({'bulan': start_date.month, 'tahun': start_date.year})
        if recap:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = recap['saldo_awal']
        else:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = 0
    
    saldo_awal = monthly_recaps_cache[f"{start_date.year}-{start_date.month}"]
    current_saldo_akhir = saldo_awal
    
    for transaction in incoming_transactions:
        barang_id = transaction['barang_id']
        
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

            # Add satuan information
            satuan_id = items_cache[barang_id]['satuan_id']
            if satuan_id not in satuan_cache:
                satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                if satuan:
                    satuan_cache[satuan_id] = satuan

            transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'

        # Calculate saldo_awal, pengeluaran, and saldo_akhir
        if transaction['jenis_transaksi'] == 'Masuk':
            pengeluaran = transaction['harga_barang']
            current_saldo_akhir -= pengeluaran
            
            transaction['saldo_awal'] = saldo_awal
            transaction['pengeluaran'] = pengeluaran
            transaction['saldo_akhir'] = current_saldo_akhir

        for transaction in outgoing_transactions:
            nama_barang = transaction.get('nama_barang')
            
            if nama_barang:
                if nama_barang not in items_cache:
                    item = db.items.find_one({'nama_barang': nama_barang})
                    if item:
                        items_cache[nama_barang] = item
                
                if nama_barang in items_cache:
                    barang_id = items_cache[nama_barang]['_id']
                    kategori_id = items_cache[nama_barang]['kategori_id']
                    satuan_id = items_cache[nama_barang]['satuan_id']
                    transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                    
                    if kategori_id not in categories_cache:
                        category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                        if category:
                            categories_cache[kategori_id] = category
                    
                    transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
                    
                    if satuan_id not in satuan_cache:
                        satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                        if satuan:
                            satuan_cache[satuan_id] = satuan

                    transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'
                else:
                    transaction['nama_kategori'] = 'Unknown'
                    transaction['nama_satuan'] = 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
                transaction['nama_satuan'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']
    
    # Gabungkan data
    all_transactions = incoming_transactions + outgoing_transactions
    
    # Sortir data berdasarkan tanggal
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    selected_columns = ['tanggal_masuk', 'tanggal_keluar', 'nama_kategori', 'nama_barang', 'nama_satuan', 'jenis_transaksi', 'jumlah_barang', 'stock_tersedia', 'saldo_awal', 'pengeluaran', 'saldo_akhir']

    # Konversi data ke DataFrame
    df = pandas.DataFrame(all_transactions, columns=selected_columns)

    # Buat workbook dan worksheet dengan openpyxl
    wb = Workbook()
    ws = wb.active
    ws.title = "Laporan Persediaan"

    # Menambahkan keterangan
    ws.append(["Laporan Persediaan Barang Periode Bulan: " + ori_bulan])
    ws.append([""])
    
    # Menambahkan header DataFrame ke worksheet
    for row in dataframe_to_rows(df, index=False, header=True):
        ws.append(row)

    # Buat file Excel
    excel_file_path = 'export_laporan_persediaan.xlsx'
    wb.save(excel_file_path)

    # Mengirim file Excel sebagai respons
    return send_file(excel_file_path, as_attachment=True)


@app.route('/laporan-barang-masuk/export/pdf', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanbarangmasuk_export_pdf():
    bulan = request.args.get('bulan')
    param_bulan = request.args.get('bulan')

    filter_conditions = {}
    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    if bulan:
        try:
            tahun, bulan = bulan.split('-')
            start_date = datetime(int(tahun), int(bulan), 1)
            if int(bulan) == 12:
                end_date = datetime(int(tahun) + 1, 1, 1)
            else:
                end_date = datetime(int(tahun), int(bulan) + 1, 1)
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date, '$lte': end_date}},
                {'tanggal_keluar': {'$gte': start_date, '$lte': end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400
        
    incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
    
    all_transactions = incoming_transactions
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    items_cache = {}
    categories_cache = {}
    monthly_recaps_cache = {}

    if f"{start_date.year}-{start_date.month}" not in monthly_recaps_cache:
        recap = db.monthly_recaps.find_one({'bulan': start_date.month, 'tahun': start_date.year})
        if recap:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = recap['saldo_awal']
        else:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = 0
    
    saldo_awal = monthly_recaps_cache[f"{start_date.year}-{start_date.month}"]
    current_saldo_akhir = saldo_awal
    
    for transaction in all_transactions:
        barang_id = transaction['barang_id']
        
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        transaction['satuan'] = items_cache[barang_id]['satuan'] if barang_id in items_cache else 'Unknown'
        
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

        if transaction['jenis_transaksi'] == 'Masuk':
            pengeluaran = transaction['harga_barang']
            current_saldo_akhir -= pengeluaran
            
            transaction['saldo_awal'] = saldo_awal
            transaction['pengeluaran'] = pengeluaran
            transaction['saldo_akhir'] = current_saldo_akhir

    rendered_template = render_template('export_laporan_barang_masuk.html', transactions=all_transactions, bulan=bulan)
    pdf_file_path = 'export_laporan_barang_masuk.pdf'
    with open(pdf_file_path, 'wb') as file:
        pisa.CreatePDF(rendered_template, dest=file)

    return send_file(pdf_file_path, as_attachment=True)

@app.route('/laporan-barang-masuk/export/xsl', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanbarangmasuk_export_excel():
    bulan = request.args.get('bulan')
    param_bulan = request.args.get('bulan')

    filter_conditions = {}
    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    if bulan:
        try:
            tahun, bulan = bulan.split('-')
            start_date = datetime(int(tahun), int(bulan), 1)
            if int(bulan) == 12:
                end_date = datetime(int(tahun) + 1, 1, 1)
            else:
                end_date = datetime(int(tahun), int(bulan) + 1, 1)
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date, '$lte': end_date}},
                {'tanggal_keluar': {'$gte': start_date, '$lte': end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400
        
    incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
    
    all_transactions = incoming_transactions
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))
    
    items_cache = {}
    categories_cache = {}
    monthly_recaps_cache = {}

    if f"{start_date.year}-{start_date.month}" not in monthly_recaps_cache:
        recap = db.monthly_recaps.find_one({'bulan': start_date.month, 'tahun': start_date.year})
        if recap:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = recap['saldo_awal']
        else:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = 0
    
    saldo_awal = monthly_recaps_cache[f"{start_date.year}-{start_date.month}"]
    current_saldo_akhir = saldo_awal
    
    for transaction in all_transactions:
        barang_id = transaction['barang_id']
        
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        transaction['satuan'] = items_cache[barang_id]['satuan'] if barang_id in items_cache else 'Unknown'
        
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

        if transaction['jenis_transaksi'] == 'Masuk':
            pengeluaran = transaction['harga_barang']
            current_saldo_akhir -= pengeluaran
            
            transaction['saldo_awal'] = saldo_awal
            transaction['pengeluaran'] = pengeluaran
            transaction['saldo_akhir'] = current_saldo_akhir


    selected_columns = ['tanggal_masuk', 'nama_kategori', 'nama_barang', 'satuan', 'jumlah_barang']

    # Konversi data ke DataFrame
    df = pandas.DataFrame(all_transactions, columns=selected_columns)

    # Buat file Excel
    excel_file_path = 'export_laporan_barang_masuk.xlsx'
    df.to_excel(excel_file_path, index=False)

    # Mengirim file Excel sebagai respons
    return send_file(excel_file_path, as_attachment=True)

@app.route('/laporan-barang-keluar/export/pdf', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanbarangkeluar_export_pdf():
    bulan = request.args.get('bulan')
    param_bulan = request.args.get('bulan')

    filter_conditions = {
        'is_verif': True,
        'status': 'Process'
    }

    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    if bulan:
        try:
            tahun, bulan = bulan.split('-')
            start_date = f"{tahun}-{bulan}-01"
            if int(bulan) == 12:
                end_date = f"{int(tahun) + 1}-01-01"
            else:
                end_date = f"{tahun}-{int(bulan) + 1:02d}-01"

            filter_conditions['$or'] = [
                {'tanggal_pengajuan': {'$gte': start_date, '$lt': end_date}},
                {'tanggal_penerimaan': {'$gte': start_date, '$lt': end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400

    barang_keluar_col = db2['staff_gudang']
    barang_keluar_tbl = list(barang_keluar_col.find(filter_conditions).sort('tanggal_penerimaan', 1))
    
    items2 = list(db.items.find())
    categories2 = list(db.categories.find())
    
    categories_dict = {category['_id']: category for category in categories2}
    for item in items2:
        kategori_id = item.get('kategori_id')
        if kategori_id in categories_dict:
            item['kategori'] = categories_dict[kategori_id]
        else:
            item['kategori'] = "Kebersihan"

    items_dict = {item['nama_barang']: item['satuan'] for item in items2}
    kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}

    for item in barang_keluar_tbl:
        nama_barang = item.get('nama_barang')
        if nama_barang in items_dict:
            item['satuan'] = items_dict[nama_barang]
        else:
            item['satuan'] = 'pcs'

        if nama_barang in kategori_dict:
            item['kategori'] = kategori_dict[nama_barang]
        else:
            item['kategori'] = "Kebersihan"

    incoming_transactions = barang_keluar_tbl
    # incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    
    all_transactions = incoming_transactions

    rendered_template = render_template('export_laporan_barang_keluar.html', transactions=all_transactions, bulan=bulan)
    pdf_file_path = 'export_laporan_barang_keluar.pdf'
    with open(pdf_file_path, 'wb') as file:
        pisa.CreatePDF(rendered_template, dest=file)

    return send_file(pdf_file_path, as_attachment=True)

@app.route('/laporan-barang-keluar/export/xsl', methods=['GET'])
@login_required(roles=['adminbarang', 'kepalagudang'])
def laporanbarangkeluar_export_excel():
    bulan = request.args.get('bulan')
    param_bulan = request.args.get('bulan')

    filter_conditions = {
        'is_verif': True,
        'status': 'Process'
    }

    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    if bulan:
        try:
            tahun, bulan = bulan.split('-')
            start_date = f"{tahun}-{bulan}-01"
            if int(bulan) == 12:
                end_date = f"{int(tahun) + 1}-01-01"
            else:
                end_date = f"{tahun}-{int(bulan) + 1:02d}-01"

            filter_conditions['$or'] = [
                {'tanggal_pengajuan': {'$gte': start_date, '$lt': end_date}},
                {'tanggal_penerimaan': {'$gte': start_date, '$lt': end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400

    barang_keluar_col = db2['staff_gudang']
    barang_keluar_tbl = list(barang_keluar_col.find(filter_conditions).sort('tanggal_penerimaan', 1))
    
    items2 = list(db.items.find())
    categories2 = list(db.categories.find())
    
    categories_dict = {category['_id']: category for category in categories2}
    for item in items2:
        kategori_id = item.get('kategori_id')
        if kategori_id in categories_dict:
            item['kategori'] = categories_dict[kategori_id]
        else:
            item['kategori'] = "Kebersihan"

    items_dict = {item['nama_barang']: item['satuan'] for item in items2}
    kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}

    for item in barang_keluar_tbl:
        nama_barang = item.get('nama_barang')
        if nama_barang in items_dict:
            item['satuan'] = items_dict[nama_barang]
        else:
            item['satuan'] = 'pcs'

        if nama_barang in kategori_dict:
            item['kategori'] = kategori_dict[nama_barang]['nama_kategori']
        else:
            item['kategori'] = "-"

    incoming_transactions = barang_keluar_tbl
    # incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    
    all_transactions = incoming_transactions

    selected_columns = ['tanggal_penerimaan', 'tanggal_pengajuan', 'kategori', 'nama_barang', 'satuan', 'jumlah_diterima']

    # Konversi data ke DataFrame
    df = pandas.DataFrame(all_transactions, columns=selected_columns)

    # Buat file Excel
    excel_file_path = 'export_laporan_barang_keluar.xlsx'
    df.to_excel(excel_file_path, index=False)

    # Mengirim file Excel sebagai respons
    return send_file(excel_file_path, as_attachment=True)

@app.route('/kepalagudang', methods=['GET'])
@login_required(roles=['kepalagudang'])
def kepalagudang():
    return render_template('kepalagudang_dashboard.html')  

@app.route('/kg-stocktersedia', methods=['GET'])
@login_required(roles=['kepalagudang'])
def kgstocktersedia():
    items = list(db.items.find())
    categories = list(db.categories.find())
    satuans = list(db.satuan.find())

    # Create dictionaries to map IDs to names
    categories_dict = {str(category['_id']): category['nama_kategori'] for category in categories}
    satuans_dict = {str(satuan['_id']): satuan['nama_satuan'] for satuan in satuans}

    # Add 'nama_kategori' and 'nama_satuan' to each item
    for item in items:
        item['nama_kategori'] = categories_dict.get(str(item['kategori_id']), 'Unknown')
        item['nama_satuan'] = satuans_dict.get(str(item['satuan_id']), 'Unknown')

    return render_template('kepalagudang_stocktersedia.html', items=items)

@app.route('/kg-laporan-barang', methods=['GET'])
@login_required(roles=['kepalagudang'])
def kglaporanbarang():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    jenis_laporan = request.args.get('jenis_laporan')

    # Buat filter untuk MongoDB
    filter_conditions = {}

    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date}},
                {'tanggal_keluar': {'$gte': start_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            if '$or' in filter_conditions:
                filter_conditions['$or'][0]['tanggal_masuk']['$lte'] = end_date
                filter_conditions['$or'][1]['tanggal_keluar']['$lte'] = end_date
            else:
                filter_conditions['$or'] = [
                    {'tanggal_masuk': {'$lte': end_date}},
                    {'tanggal_keluar': {'$lte': end_date}}
                ]
        except ValueError:
            return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400
        
    if jenis_laporan == 'out':
        filter_conditions = {
            'is_verif': True,
            'status': 'Process'
        }

        if start_date:
            try:
                start_date_dt = start_date
                start_date_str = start_date_dt.strftime('%Y-%m-%d')
            except ValueError:
                return jsonify({'message': 'Format tanggal mulai tidak valid!'}), 400

        if end_date:
            try:
                end_date_dt = end_date
                end_date_str = end_date_dt.strftime('%Y-%m-%d')
            except ValueError:
                return jsonify({'message': 'Format tanggal selesai tidak valid!'}), 400

        pipeline = [
            {'$match': filter_conditions},
            {
                '$addFields': {
                    'tanggal_penerimaan_date': {
                        '$dateFromString': {
                            'dateString': '$tanggal_penerimaan',
                            'format': '%Y-%m-%d'
                        }
                    }
                }
            }
        ]

        if start_date:
            pipeline.append({'$match': {'tanggal_penerimaan_date': {'$gte': start_date_dt}}})

        if end_date:
            pipeline.append({'$match': {'tanggal_penerimaan_date': {'$lte': end_date_dt}}})

        pipeline.append({'$sort': {'tanggal_penerimaan_date': 1}})

        barang_keluar_col = db2['staff_gudang']
        barang_keluar_tbl = list(barang_keluar_col.aggregate(pipeline))

        items2 = list(db.items.find())
        categories2 = list(db.categories.find())
        satuans2 = list(db.satuan.find())  # Fetch satuan data

        categories_dict = {category['_id']: category for category in categories2}
        satuans_dict = {satuan['_id']: satuan['nama_satuan'] for satuan in satuans2}  # Map satuan data
        for item in items2:
            kategori_id = item.get('kategori_id')
            if kategori_id in categories_dict:
                item['kategori'] = categories_dict[kategori_id]
            else:
                item['kategori'] = "Kebersihan"

            satuan_id = item.get('satuan_id')
            if satuan_id in satuans_dict:
                item['satuan'] = satuans_dict[satuan_id]
            else:
                item['satuan'] = "Box"

        # items_dict = {item['nama_barang']: item['satuan'] for item in items2}
        satuan_dict = {item['nama_barang']: item['satuan'] for item in items2}
        kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}

        for item in barang_keluar_tbl:
            item['keterangan'] = 'Ruangan ' + item['ruangan']
            item['jumlah_barang'] = item['jumlah_diterima']
            item['tanggal_keluar'] = datetime.strptime(item['tanggal_penerimaan'], '%Y-%m-%d')
            nama_barang = item.get('nama_barang')
            # if nama_barang in items_dict:
            #     item['satuan'] = items_dict[nama_barang]
            # else:
            #     item['satuan'] = 'pcs'

            if nama_barang in kategori_dict:
                item['kategori'] = kategori_dict[nama_barang]['nama_kategori']
                item['nama_kategori'] = kategori_dict[nama_barang]['nama_kategori']
            else:
                item['kategori'] = "-"
                item['nama_kategori'] = "-"

            # Add satuan information
            if nama_barang in satuan_dict:
                item['satuan'] = satuan_dict[nama_barang]
            else:
                item['satuan'] = 'Box'

        transactions = barang_keluar_tbl
        transactions.sort(key=lambda x: x.get('tanggal_penerimaan'))
    else:
        transactions = list(db.incoming_transactions.find(filter_conditions))
        transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))

        items_cache = {}
        categories_cache = {}
        satuan_cache = {}  # Cache satuan data

        for transaction in transactions:
            barang_id = transaction['barang_id']

            if barang_id not in items_cache:
                item = db.items.find_one({'_id': ObjectId(barang_id)})
                if item:
                    items_cache[barang_id] = item

            transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'

            if barang_id in items_cache:
                kategori_id = items_cache[barang_id]['kategori_id']
                if kategori_id not in categories_cache:
                    category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                    if category:
                        categories_cache[kategori_id] = category

                transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

                # Add satuan information
                satuan_id = items_cache[barang_id]['satuan_id']
                if satuan_id not in satuan_cache:
                    satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                    if satuan:
                        satuan_cache[satuan_id] = satuan

                transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'

    return render_template('kepalagudang_laporanbarang.html', 
                           transactions=transactions,
                           jenis_laporan=jenis_laporan, 
                           start_date=start_date, 
                           end_date=end_date)

@app.route('/kg-laporan-stock', methods=['GET'])
@login_required(roles=['kepalagudang'])
def kglaporanstock():
    jenis_laporan = request.args.get('jenis_laporan')

    if jenis_laporan == 'minimum':
        items = list(db.items.find({'$expr': {'$lte': ['$stock_tersedia', '$stock_minimum']}}))
    else:
        items = list(db.items.find())

    for item in items:
        category = db.categories.find_one({'_id': item['kategori_id']})
        item['nama_kategori'] = category['nama_kategori'] if category else 'Unknown'

    for item in items:
        satuan = db.satuan.find_one({'_id': item['satuan_id']})
        item['nama_satuan'] = satuan['nama_satuan'] if satuan else 'Unknown'

    return render_template('kepalagudang_laporanstock.html', items=items, jenis_laporan=jenis_laporan)

@app.route('/kg-laporan-persediaan', methods=['GET'])
@login_required(roles=['kepalagudang'])
def kglaporanpersediaan():
    # Ambil filter bulan dari request
    bulan = request.args.get('bulan')
    param_bulan = request.args.get('bulan')

    # Buat filter untuk MongoDB
    filter_conditions = {}
    outgoing_conditions = {
        'is_verif': True,
        'status': 'Process'
    }
    if not bulan:
        bulan = datetime.now().strftime('%Y-%m')

    ori_bulan = bulan

    if bulan:
        try:
            # Split bulan menjadi tahun dan bulan
            tahun, bulan = bulan.split('-')
            # Ambil tanggal awal dan akhir bulan
            start_date = datetime(int(tahun), int(bulan), 1)
            if int(bulan) == 12:
                end_date = datetime(int(tahun) + 1, 1, 1)
            else:
                end_date = datetime(int(tahun), int(bulan) + 1, 1)
            # Masukkan filter ke dalam kondisi
            filter_conditions['$or'] = [
                {'tanggal_masuk': {'$gte': start_date, '$lte': end_date}},
                {'tanggal_keluar': {'$gte': start_date, '$lte': end_date}}
            ]

        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400

        try:
            _tahun, _bulan = ori_bulan.split('-')
            _start_date = f"{_tahun}-{_bulan}-01"
            if int(_bulan) == 12:
                _end_date = f"{int(_tahun) + 1}-01-01"
            else:
                _end_date = f"{_tahun}-{int(_bulan) + 1:02d}-01"

            outgoing_conditions['$or'] = [
                {'tanggal_pengajuan': {'$gte': _start_date, '$lt': _end_date}},
                {'tanggal_penerimaan': {'$gte': _start_date, '$lt': _end_date}}
            ]
        except ValueError:
            return jsonify({'message': 'Format bulan tidak valid!'}), 400
        
    # Ambil data dari incoming_transactions dan outgoing_transactions
    incoming_transactions = list(db.incoming_transactions.find(filter_conditions))
    barang_keluar_col = db2['staff_gudang']
    barang_keluar_tbl = list(barang_keluar_col.find(outgoing_conditions).sort('tanggal_penerimaan', 1))
    
    def convert_to_date(date_str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None

    items2 = list(db.items.find())
    categories2 = list(db.categories.find())
    satuan2 = list(db.satuan.find())  # Fetch satuan data
    
    categories_dict = {category['_id']: category for category in categories2}
    satuans_dict = {satuan['_id']: satuan['nama_satuan'] for satuan in satuan2}  # Map satuan data
    for item in items2:
        kategori_id = item.get('kategori_id')
        if kategori_id in categories_dict:
            item['kategori'] = categories_dict[kategori_id]
        else:
            item['kategori'] = "Kebersihan"

        satuan_id = item.get('satuan_id')
        if satuan_id in satuans_dict:
            item['satuan'] = satuans_dict[satuan_id]
        else:
            item['satuan'] = "Kebersihan"

    kategori_dict = {item['nama_barang']: item['kategori'] for item in items2}
    satuan_dict = {item['nama_barang']: item['satuan'] for item in items2}

    for item in barang_keluar_tbl:
        nama_barang = item.get('nama_barang')

        if nama_barang in kategori_dict:
            item['kategori'] = kategori_dict[nama_barang]
        else:
            item['kategori'] = "Kebersihan"

        if nama_barang in satuan_dict:
            item['satuan'] = satuan_dict[nama_barang]
        else:
            item['satuan'] = 'Box'
            
    selected_item = None
    nama_barang = None

    outgoing_transactions = barang_keluar_tbl

    # Menambahkan jenis transaksi untuk membedakan barang masuk dan keluar
    for transaction in incoming_transactions:
        transaction['jenis_transaksi'] = 'Masuk'
        transaction['date'] = transaction['tanggal_masuk']
    
    for transaction in outgoing_transactions:
        transaction['stock_tersedia'] = 0
        transaction['jenis_transaksi'] = 'Keluar'
        transaction['keterangan'] = 'Ruangan '+transaction['ruangan']
        transaction['tanggal_keluar'] = convert_to_date(transaction['tanggal_penerimaan']) 
        transaction['date'] = convert_to_date(transaction['tanggal_penerimaan'])
        transaction['jumlah_barang'] = transaction['jumlah_diterima']
  
    # Menyimpan semua barang dan kategori untuk menghindari pencarian berulang
    items_cache = {}
    categories_cache = {}
    satuan_cache = {}  # Cache satuan data
    monthly_recaps_cache = {}

    # Mengambil saldo_awal dari monthly_recaps
    if f"{start_date.year}-{start_date.month}" not in monthly_recaps_cache:
        recap = db.monthly_recaps.find_one({'bulan': start_date.month, 'tahun': start_date.year})
        if recap:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = recap['saldo_awal']
        else:
            monthly_recaps_cache[f"{start_date.year}-{start_date.month}"] = 0
    
    saldo_awal = monthly_recaps_cache[f"{start_date.year}-{start_date.month}"]
    current_saldo_akhir = saldo_awal
    
    for transaction in incoming_transactions:
        barang_id = transaction['barang_id']
        
        if barang_id not in items_cache:
            item = db.items.find_one({'_id': ObjectId(barang_id)})
            if item:
                items_cache[barang_id] = item

        transaction['nama_barang'] = items_cache[barang_id]['nama_barang'] if barang_id in items_cache else 'Unknown'
        
        if barang_id in items_cache:
            kategori_id = items_cache[barang_id]['kategori_id']
            if kategori_id not in categories_cache:
                category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                if category:
                    categories_cache[kategori_id] = category
            
            transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'

            # Add satuan information
            satuan_id = items_cache[barang_id]['satuan_id']
            if satuan_id not in satuan_cache:
                satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                if satuan:
                    satuan_cache[satuan_id] = satuan

            transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'

        # Calculate saldo_awal, pengeluaran, and saldo_akhir
        if transaction['jenis_transaksi'] == 'Masuk':
            pengeluaran = transaction['harga_barang']
            current_saldo_akhir -= pengeluaran
            
            transaction['saldo_awal'] = saldo_awal
            transaction['pengeluaran'] = pengeluaran
            transaction['saldo_akhir'] = current_saldo_akhir

        for transaction in outgoing_transactions:
            nama_barang = transaction.get('nama_barang')
            
            if nama_barang:
                if nama_barang not in items_cache:
                    item = db.items.find_one({'nama_barang': nama_barang})
                    if item:
                        items_cache[nama_barang] = item
                
                if nama_barang in items_cache:
                    barang_id = items_cache[nama_barang]['_id']
                    kategori_id = items_cache[nama_barang]['kategori_id']
                    satuan_id = items_cache[nama_barang]['satuan_id']
                    transaction['barang_id'] = str(barang_id)  # Add barang_id to the transaction
                    
                    if kategori_id not in categories_cache:
                        category = db.categories.find_one({'_id': ObjectId(kategori_id)})
                        if category:
                            categories_cache[kategori_id] = category
                    
                    transaction['nama_kategori'] = categories_cache[kategori_id]['nama_kategori'] if kategori_id in categories_cache else 'Unknown'
                    
                    if satuan_id not in satuan_cache:
                        satuan = db.satuan.find_one({'_id': ObjectId(satuan_id)})
                        if satuan:
                            satuan_cache[satuan_id] = satuan

                    transaction['nama_satuan'] = satuan_cache[satuan_id]['nama_satuan'] if satuan_id in satuan_cache else 'Unknown'
                else:
                    transaction['nama_kategori'] = 'Unknown'
                    transaction['nama_satuan'] = 'Unknown'
            else:
                transaction['nama_kategori'] = 'Unknown'
                transaction['nama_satuan'] = 'Unknown'

    # Get all nama_barang in incoming_transactions
    incoming_nama_barang = {trans['nama_barang'] for trans in incoming_transactions}

    # Filter outgoing_transactions
    filtered_outgoing_transactions = [
        trans for trans in outgoing_transactions
        if trans['nama_barang'] in incoming_nama_barang
    ]

    outgoing_transactions = filtered_outgoing_transactions

    # Create a dictionary to track the latest stock availability for each nama_barang
    stock_dict = {}
    out_stock_dict = {}
    for trans in incoming_transactions:
        nama_barang = trans['nama_barang']
        stock_dict[nama_barang] = {
            'stock_tersedia': trans['stock_tersedia'],
            'date': trans['date']
        }

    # Update outgoing transactions with stock_tersedia
    already_added = {}
    for trans in outgoing_transactions:
        nama_barang = trans['nama_barang']
        if nama_barang in stock_dict:
            # Find the latest incoming transaction before the outgoing transaction date
            for in_trans in reversed(incoming_transactions):
                if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                    stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                    break

            for out_trans in reversed(outgoing_transactions):
                if out_trans['nama_barang'] == nama_barang and out_trans['date'] <= trans['date'] and out_trans['stock_tersedia']:
                    stock_dict[nama_barang]['stock_tersedia'] = out_trans['stock_tersedia']
                    break

            # Decrement the stock based on the outgoing transaction quantity
            stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
            trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']
            
            if trans['stock_tersedia'] < 0:
                for in_trans in reversed(incoming_transactions):
                    if in_trans['nama_barang'] == nama_barang and in_trans['date'] <= trans['date']:
                        stock_dict[nama_barang]['stock_tersedia'] = in_trans['stock_tersedia']
                        break

                stock_dict[nama_barang]['stock_tersedia'] -= trans['jumlah_diterima']
                trans['stock_tersedia'] = stock_dict[nama_barang]['stock_tersedia']

            # Update the date in the stock_dict to reflect this outgoing transaction
            stock_dict[nama_barang]['date'] = trans['date']
    
    # Gabungkan data
    all_transactions = incoming_transactions + outgoing_transactions
    
    # Sortir data berdasarkan tanggal
    all_transactions.sort(key=lambda x: x.get('tanggal_masuk', x.get('tanggal_keluar')))

    indonesian_date = ""
    if param_bulan:
        # Parse the date
        date_obj = datetime.strptime(param_bulan, "%Y-%m")

        # Format the date to "Juli 2024"
        formatted_date = date_obj.strftime("%B %Y")

        # Translate the month to Indonesian
        months_translation = {
            "January": "Januari",
            "February": "Februari",
            "March": "Maret",
            "April": "April",
            "May": "Mei",
            "June": "Juni",
            "July": "Juli",
            "August": "Agustus",
            "September": "September",
            "October": "Oktober",
            "November": "November",
            "December": "Desember"
        }

        indonesian_date = months_translation[formatted_date.split()[0]] + " " + formatted_date.split()[1]

    return render_template('kepalagudang_laporanpersediaan.html', indonesian_date=indonesian_date, param_bulan=param_bulan, transactions=all_transactions)

if __name__ == '__main__':
    app.run('0.0.0.0', port=5001, debug=True)
