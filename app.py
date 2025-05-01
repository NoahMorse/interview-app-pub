from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import html
import random
import requests
from functools import wraps

app = Flask(__name__)
app.secret_key = "dev_key_1234"

def init_db():
    conn = sqlite3.connect('store.db')
    c = conn.cursor()
    
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )
    ''')
    
    c.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT,
        description TEXT,
        price REAL,
        stock INTEGER
    )
    ''')
    
    c.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        product_id INTEGER,
        quantity INTEGER,
        total_price REAL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (product_id) REFERENCES products (id)
    )
    ''')
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
                  ('admin', 'admin123', 1))
        c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
                  ('user', 'password123', 0))
    
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        products = [
            ('Laptop', 'High-performance laptop', 999.99, 10),
            ('Smartphone', 'Latest model smartphone', 699.99, 15),
            ('Headphones', 'Noise-cancelling headphones', 149.99, 20),
            ('Tablet', '10-inch tablet', 349.99, 8),
            ('Smartwatch', 'Fitness tracking smartwatch', 199.99, 12)
        ]
        c.executemany("INSERT INTO products (name, description, price, stock) VALUES (?, ?, ?, ?)", products)
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('store.db')
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'is_admin' not in session or session['is_admin'] != 1:
            flash('Admin access required')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    conn = get_db()
    products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    return render_template('index.html', products=products)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
        user = conn.execute(query).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            return redirect(url_for('index'))
        else:
            error = 'Invalid credentials'
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
    
        
        conn = get_db()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                        (username, password))
            conn.commit()
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()
    
    if product:
        return render_template('product_detail.html', product=product)
    
    flash('Product not found')
    return redirect(url_for('index'))

@app.route('/checkout/<int:product_id>', methods=['GET', 'POST'])
@login_required
def checkout(product_id):
    conn = get_db()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    
    if not product:
        conn.close()
        flash('Product not found')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        quantity = int(request.form['quantity'])
        
        if quantity > product['stock']:
            flash('Not enough items in stock')
            conn.close()
            return redirect(url_for('product_detail', product_id=product_id))
        
        total_price = product['price'] * quantity
        
        conn.execute('UPDATE products SET stock = stock - ? WHERE id = ?', 
                    (quantity, product_id))
        
        conn.execute('''
        INSERT INTO orders (user_id, product_id, quantity, total_price) 
        VALUES (?, ?, ?, ?)
        ''', (session['user_id'], product_id, quantity, total_price))
        
        conn.commit()
        conn.close()
        
        flash('Order placed successfully!')
        return redirect(url_for('orders'))
    
    conn.close()
    return render_template('checkout.html', product=product)

@app.route('/orders')
@login_required
def orders():
    conn = get_db()

    orders = conn.execute('''
    SELECT orders.*, products.name, products.price 
    FROM orders 
    JOIN products ON orders.product_id = products.id
    WHERE orders.user_id = ?
    ''', (session['user_id'],)).fetchall()
    conn.close()
    
    return render_template('orders.html', orders=orders)

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    conn = get_db()
    users = conn.execute('SELECT * FROM users').fetchall()
    products = conn.execute('SELECT * FROM products').fetchall()
    orders = conn.execute('''
    SELECT orders.*, users.username, products.name 
    FROM orders 
    JOIN users ON orders.user_id = users.id 
    JOIN products ON orders.product_id = products.id
    ''').fetchall()
    conn.close()
    
    return render_template('admin.html', users=users, products=products, orders=orders)

@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        
        conn = get_db()
        conn.execute('''
        INSERT INTO products (name, description, price, stock) 
        VALUES (?, ?, ?, ?)
        ''', (name, description, price, stock))
        conn.commit()
        conn.close()
        
        flash('Product added successfully')
        return redirect(url_for('admin_panel'))
    
    return render_template('add_product.html')

@app.route('/download_receipt/<int:order_id>')
@login_required
def download_receipt(order_id):
    conn = get_db()
    order = conn.execute('''
    SELECT orders.*, products.name
    FROM orders 
    JOIN products ON orders.product_id = products.id
    WHERE orders.id = ?
    ''', (order_id,)).fetchone()
    conn.close()
    
    if not order:
        flash('Order not found')
        return redirect(url_for('orders'))
    
    receipt = f"Receipt for Order #{order_id}\n"
    receipt += f"Product: {order['name']}\n"
    receipt += f"Quantity: {order['quantity']}\n"
    receipt += f"Total: ${order['total_price']:.2f}\n"
    
    return receipt

@app.route('/search')
def search():
    query = request.args.get('q', '')
    
    conn = get_db()
    products = conn.execute(f"SELECT * FROM products WHERE name LIKE '%{query}%'").fetchall()
    conn.close()
    
    return render_template('search_results.html', products=products, query=query)

@app.route('/update_profile', methods=['GET', 'POST'])
@login_required
def update_profile():
    if request.method == 'POST':
        new_password = request.form['password']
        
        conn = get_db()
        conn.execute('UPDATE users SET password = ? WHERE id = ?', 
                    (new_password, session['user_id']))
        conn.commit()
        conn.close()
        
        flash('Profile updated successfully')
    
    return render_template('update_profile.html')

@app.route('/fetch_external')
@login_required
@admin_required
def fetch_external():    
    url = request.args.get('url', '')
    if url:
        try:
            response = requests.get(url)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"
    
    return render_template('fetch_external.html')

@app.route('/api/products', methods=['GET'])
def api_products():
    conn = get_db()
    products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    
    product_list = []
    for product in products:
        product_list.append({
            'id': product['id'],
            'name': product['name'],
            'description': product['description'],
            'price': product['price'],
            'stock': product['stock']
        })
    
    return jsonify(product_list)

if __name__ == '__main__':
    app.run(debug=True)