from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "replace_with_a_random_secret"   # change in production
DB_PATH = "crm.db"

# ---------- Database Helpers ----------
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE,
            name TEXT,
            description TEXT,
            price REAL,
            stock INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            address TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            address TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            supplier_id INTEGER,
            qty INTEGER,
            cost_per_item REAL,
            total_cost REAL,
            date TEXT,
            note TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            customer_id INTEGER,
            qty INTEGER,
            price_per_item REAL,
            total_price REAL,
            date TEXT,
            note TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ---------- CRUD Helpers ----------
def run_query(query, params=()):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    last = cur.lastrowid
    conn.close()
    return last

def fetch_df(query, params=()):
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

# ---------- Business Logic ----------
def add_product(sku, name, description, price, stock):
    run_query(
        "INSERT OR IGNORE INTO products (sku, name, description, price, stock) VALUES (?, ?, ?, ?, ?)",
        (sku, name, description, price, stock),
    )

def update_stock(product_id, delta):
    run_query("UPDATE products SET stock = stock + ? WHERE id = ?", (delta, product_id))

def add_customer(name, email, phone, address):
    return run_query(
        "INSERT INTO customers (name, email, phone, address) VALUES (?, ?, ?, ?)",
        (name, email, phone, address),
    )

def add_supplier(name, email, phone, address):
    return run_query(
        "INSERT INTO suppliers (name, email, phone, address) VALUES (?, ?, ?, ?)",
        (name, email, phone, address),
    )

def record_purchase(product_id, supplier_id, qty, cost_per_item, note):
    total = qty * cost_per_item
    date = datetime.now().isoformat()
    run_query(
        "INSERT INTO purchases (product_id, supplier_id, qty, cost_per_item, total_cost, date, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (product_id, supplier_id, qty, cost_per_item, total, date, note),
    )
    update_stock(product_id, qty)

def record_sale(product_id, customer_id, qty, price_per_item, note):
    total = qty * price_per_item
    date = datetime.now().isoformat()
    # reduce stock
    update_stock(product_id, -qty)
    run_query(
        "INSERT INTO sales (product_id, customer_id, qty, price_per_item, total_price, date, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (product_id, customer_id, qty, price_per_item, total, date, note),
    )

# ---------- Routes ----------
@app.route("/")
def index():
    products_df = fetch_df("SELECT * FROM products")
    sales_df = fetch_df("SELECT * FROM sales")
    purchases_df = fetch_df("SELECT * FROM purchases")
    low_stock = products_df[products_df["stock"] <= 5] if not products_df.empty else pd.DataFrame()
    return render_template("index.html",
                           total_products=len(products_df),
                           total_sales=len(sales_df),
                           total_purchases=len(purchases_df),
                           low_stock=low_stock.to_dict('records'))

@app.route("/products", methods=["GET", "POST"])
def products():
    if request.method == "POST":
        sku = request.form.get("sku", "").strip()
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = float(request.form.get("price") or 0)
        stock = int(request.form.get("stock") or 0)
        add_product(sku, name, description, price, stock)
        flash("Product added (or ignored if SKU existed)", "success")
        return redirect(url_for("products"))
    df = fetch_df("SELECT * FROM products")
    return render_template("products.html", products=df.to_dict("records"))

@app.route("/customers", methods=["GET", "POST"])
def customers():
    if request.method == "POST":
        add_customer(request.form.get("name"), request.form.get("email"),
                     request.form.get("phone"), request.form.get("address"))
        flash("Customer added", "success")
        return redirect(url_for("customers"))
    df = fetch_df("SELECT * FROM customers")
    return render_template("customers.html", customers=df.to_dict("records"))

@app.route("/suppliers", methods=["GET", "POST"])
def suppliers():
    if request.method == "POST":
        add_supplier(request.form.get("name"), request.form.get("email"),
                     request.form.get("phone"), request.form.get("address"))
        flash("Supplier added", "success")
        return redirect(url_for("suppliers"))
    df = fetch_df("SELECT * FROM suppliers")
    return render_template("suppliers.html", suppliers=df.to_dict("records"))

@app.route("/purchase", methods=["GET", "POST"])
def purchase():
    products = fetch_df("SELECT id, name, stock FROM products")
    suppliers = fetch_df("SELECT id, name FROM suppliers")
    if request.method == "POST":
        product_id = int(request.form.get("product_id"))
        supplier_id = int(request.form.get("supplier_id")) if request.form.get("supplier_id") else None
        qty = int(request.form.get("qty"))
        cost = float(request.form.get("cost") or 0)
        note = request.form.get("note")
        record_purchase(product_id, supplier_id, qty, cost, note)
        flash("Purchase recorded and stock updated", "success")
        return redirect(url_for("purchase"))
    df = fetch_df("SELECT * FROM purchases ORDER BY date DESC")
    return render_template("purchase.html", products=products.to_dict("records"),
                           suppliers=suppliers.to_dict("records"), purchases=df.to_dict("records"))

@app.route("/sale", methods=["GET", "POST"])
def sale():
    products = fetch_df("SELECT id, name, stock FROM products")
    customers = fetch_df("SELECT id, name FROM customers")
    if request.method == "POST":
        product_id = int(request.form.get("product_id"))
        customer_id = int(request.form.get("customer_id")) if request.form.get("customer_id") else None
        qty = int(request.form.get("qty"))
        price = float(request.form.get("price") or 0)
        # check stock
        stock_row = products[products["id"] == product_id]
        if stock_row.empty:
            flash("Product not found", "danger")
            return redirect(url_for("sale"))
        stock_val = int(stock_row.iloc[0]["stock"])
        if qty > stock_val:
            flash("Not enough stock!", "danger")
            return redirect(url_for("sale"))
        record_sale(product_id, customer_id, qty, price, request.form.get("note"))
        flash("Sale recorded and stock reduced", "success")
        return redirect(url_for("sale"))
    df = fetch_df("SELECT * FROM sales ORDER BY date DESC")
    return render_template("sale.html", products=products.to_dict("records"),
                           customers=customers.to_dict("records"), sales=df.to_dict("records"))

@app.route("/reports")
def reports():
    p_df = fetch_df("SELECT * FROM products")
    s_df = fetch_df("SELECT * FROM sales ORDER BY date DESC LIMIT 100")
    pur_df = fetch_df("SELECT * FROM purchases ORDER BY date DESC LIMIT 100")
    return render_template("reports.html",
                           products=p_df.to_dict("records"),
                           sales=s_df.to_dict("records"),
                           purchases=pur_df.to_dict("records"))

# ---------- Start ----------
if __name__ == "__main__":
    # ensure DB & tables exist
    init_db()
    # run app in debug for helpful errors (set False in production)
    app.run(debug=True)
