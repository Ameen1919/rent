import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
import time
from hijri_converter import convert
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import requests
import os
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import base64
import hashlib
import json

# ---------- إعداد الصفحة ----------
st.set_page_config(page_title="نظام إدارة الإيجارات", page_icon="🏢", layout="wide")

# ---------- دوال دعم العربية في PDF ----------
def download_arabic_font():
    font_path = "Amiri-Regular.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/aliftype/amiri/raw/main/fonts/Amiri-Regular.ttf"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(font_path, "wb") as f:
                    f.write(r.content)
            else:
                return None
        except:
            return None
    return font_path

def setup_arabic_font():
    font_path = download_arabic_font()
    if font_path and os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('Amiri', font_path))
        return 'Amiri'
    else:
        return 'Helvetica'

def reshape_arabic_text(text):
    reshaped = arabic_reshaper.reshape(str(text))
    bidi_text = get_display(reshaped)
    return bidi_text

def parse_currency(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.replace(',', '').strip())
    return 0.0

def parse_date_safe(value, default=None):
    if not value:
        return default or date.today()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except:
        try:
            return datetime.fromisoformat(str(value)).date()
        except:
            return default or date.today()

def format_currency(value):
    # Handle None or non-numeric gracefully
    try:
        val = float(value)
        return f"{val:,.2f}"
    except (TypeError, ValueError):
        return "0.00"

def split_header_text(col):
    if col == 'المبلغ شامل الضريبة':
        return ['المبلغ', 'شامل الضريبة']
    elif col == 'المبلغ غير شامل الضريبة':
        return ['المبلغ', 'غير شامل الضريبة']
    elif col == 'نسبة الضريبة':
        return ['نسبة', 'الضريبة']
    elif col == 'بداية الفترة':
        return ['بداية', 'الفترة']
    elif col == 'نهاية الفترة':
        return ['نهاية', 'الفترة']
    else:
        return [col]

def draw_centered_multiline(c, text_lines, x_center, y, font_name, font_size):
    line_height = font_size + 2
    total_height = len(text_lines) * line_height
    start_y = y + (total_height / 2) - (line_height / 2)
    for i, line in enumerate(text_lines):
        c.drawCentredString(x_center, start_y - i * line_height, reshape_arabic_text(line))

def export_df_to_pdf(df, title, file_name, columns_order=None, extra_info=None):
    if columns_order:
        df = df[columns_order]
    else:
        df = df.copy()
    df_numeric = df.copy()
    for col in df_numeric.columns:
        try:
            df_numeric[col] = df_numeric[col].apply(parse_currency)
        except:
            pass
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = setup_arabic_font()
    c.setFont(font_name, 10)
    c.setFillColor(colors.HexColor("#4A90E2"))
    c.rect(0, height-30, width, 30, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_name, 16)
    c.drawCentredString(width/2, height-20, reshape_arabic_text(title))
    y_extra = height - 50
    if extra_info:
        c.setFillColor(colors.black)
        c.setFont(font_name, 12)
        c.drawCentredString(width/2, y_extra, reshape_arabic_text(extra_info))
        y_extra -= 20
    actual_columns = list(df.columns)
    headers = ["م"] + actual_columns
    col_widths = []
    for col in headers:
        if col == "م":
            col_widths.append(30)
        else:
            if col in ['المبلغ', 'المدفوع', 'المتبقي', 'المبلغ شامل الضريبة', 'مبلغ الضريبة', 'المبلغ غير شامل الضريبة']:
                col_widths.append(80)
            elif col in ['تاريخ الاستحقاق', 'تاريخ السداد', 'بداية الفترة', 'نهاية الفترة']:
                col_widths.append(100)
            else:
                width_est = max(len(reshape_arabic_text(col)) * 4, 80)
                col_widths.append(width_est)
    total_width = sum(col_widths)
    x_start = (width - total_width) / 2
    if x_start < 30:
        x_start = 30
    y = y_extra - 20 if extra_info else height - 60
    c.setFont(font_name, 8)
    c.setFillColor(colors.HexColor("#f0f0f0"))
    c.rect(x_start, y-12, total_width, 20, fill=1, stroke=0)
    c.setFillColor(colors.black)
    x_cursor = x_start + total_width
    for i, header in enumerate(headers):
        col_w = col_widths[i]
        x_right = x_cursor
        x_left = x_cursor - col_w
        c.drawCentredString((x_left + x_right) / 2, y, reshape_arabic_text(header))
        x_cursor -= col_w
    y -= 25
    c.setFillColor(colors.white)
    serial = 1
    for _, row in df.iterrows():
        if y < 50:
            c.showPage()
            c.setFont(font_name, 8)
            y = height - 50
            c.setFillColor(colors.HexColor("#f0f0f0"))
            c.rect(x_start, y-12, total_width, 20, fill=1, stroke=0)
            c.setFillColor(colors.black)
            x_cursor = x_start + total_width
            for i, header in enumerate(headers):
                col_w = col_widths[i]
                x_right = x_cursor
                x_left = x_cursor - col_w
                c.drawCentredString((x_left + x_right) / 2, y, reshape_arabic_text(header))
                x_cursor -= col_w
            y -= 25
        c.setFillColor(colors.white)
        c.rect(x_start, y-5, total_width, 15, fill=1, stroke=0)
        c.setFillColor(colors.black)
        col_w = col_widths[0]
        x_right = x_start + total_width
        x_left = x_right - col_w
        c.drawCentredString((x_left + x_right) / 2, y, str(serial))
        serial += 1
        x_cursor = x_right - col_w
        for i, col in enumerate(actual_columns, start=1):
            col_w = col_widths[i]
            x_right = x_cursor
            x_left = x_cursor - col_w
            value = row[col]
            if isinstance(value, (int, float)):
                value_str = format_currency(value)
            else:
                value_str = str(value)
            c.drawRightString(x_right - 5, y, reshape_arabic_text(value_str))
            x_cursor -= col_w
        c.setStrokeColor(colors.grey)
        c.setLineWidth(0.5)
        c.line(x_start, y+10, x_start+total_width, y+10)
        c.line(x_start, y-5, x_start+total_width, y-5)
        x_cursor = x_start + total_width
        for i in range(len(headers)):
            c.line(x_cursor, y+10, x_cursor, y-5)
            x_cursor -= col_widths[i]
        c.line(x_start, y+10, x_start, y-5)
        y -= 15
    c.line(x_start, y+5, x_start+total_width, y+5)
    y -= 5
    c.setFillColor(colors.HexColor("#e8f0fe"))
    c.rect(x_start, y-5, total_width, 15, fill=1, stroke=0)
    c.setFillColor(colors.black)
    col_w = col_widths[0]
    x_right = x_start + total_width
    x_left = x_right - col_w
    c.drawCentredString((x_left + x_right) / 2, y, reshape_arabic_text("الإجمالي"))
    x_cursor = x_right - col_w
    for i, col in enumerate(actual_columns, start=1):
        col_w = col_widths[i]
        x_right = x_cursor
        x_left = x_cursor - col_w
        try:
            total_val = df_numeric[col].sum()
            c.drawRightString(x_right - 5, y, format_currency(total_val))
        except:
            pass
        x_cursor -= col_w
    c.save()
    buffer.seek(0)
    st.download_button("تحميل PDF", data=buffer, file_name=file_name, mime="application/pdf")

def export_tax_pdf(df, title, file_name, columns_order=None):
    if columns_order:
        df = df[columns_order]
    else:
        df = df.copy()
    df_numeric = df.copy()
    for col in ['المبلغ شامل الضريبة', 'مبلغ الضريبة', 'المبلغ غير شامل الضريبة']:
        if col in df_numeric.columns:
            df_numeric[col] = df_numeric[col].apply(parse_currency)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    font_name = setup_arabic_font()
    c.setFont(font_name, 10)
    c.setFillColor(colors.HexColor("#4A90E2"))
    c.rect(0, height-30, width, 30, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_name, 16)
    c.drawCentredString(width/2, height-20, reshape_arabic_text(title))
    actual_columns = list(df.columns)
    headers = ["م"] + actual_columns
    col_widths = []
    for col in headers:
        if col == "م":
            col_widths.append(25)
        elif col in ['المبلغ شامل الضريبة', 'مبلغ الضريبة', 'المبلغ غير شامل الضريبة']:
            col_widths.append(75)
        elif col == 'نسبة الضريبة':
            col_widths.append(50)
        elif col in ['بداية الفترة', 'نهاية الفترة']:
            col_widths.append(85)
        elif col == 'اسم المستأجر':
            col_widths.append(100)
        elif col == 'رقم العقد':
            col_widths.append(80)
        elif col == 'طريقة الدفع':
            col_widths.append(70)
        else:
            width_est = max(len(reshape_arabic_text(col)) * 3.5, 70)
            col_widths.append(width_est)
    total_width = sum(col_widths)
    x_start = (width - total_width) / 2
    if x_start < 20:
        x_start = 20
    y = height - 60
    c.setFont(font_name, 7)
    c.setFillColor(colors.HexColor("#f0f0f0"))
    c.rect(x_start, y-18, total_width, 28, fill=1, stroke=0)
    c.setFillColor(colors.black)
    x_cursor = x_start + total_width
    for i, header in enumerate(headers):
        col_w = col_widths[i]
        x_right = x_cursor
        x_left = x_cursor - col_w
        x_center = (x_left + x_right) / 2
        if header == "م":
            c.drawCentredString(x_center, y-2, "م")
        else:
            text_lines = split_header_text(header)
            if len(text_lines) == 1:
                c.drawCentredString(x_center, y-2, reshape_arabic_text(text_lines[0]))
            else:
                draw_centered_multiline(c, text_lines, x_center, y-8, font_name, 7)
        x_cursor -= col_w
    y -= 30
    c.setFont(font_name, 8)
    serial = 1
    for _, row in df.iterrows():
        if y < 50:
            c.showPage()
            c.setFont(font_name, 8)
            y = height - 50
            c.setFont(font_name, 7)
            c.setFillColor(colors.HexColor("#f0f0f0"))
            c.rect(x_start, y-18, total_width, 28, fill=1, stroke=0)
            c.setFillColor(colors.black)
            x_cursor = x_start + total_width
            for i, header in enumerate(headers):
                col_w = col_widths[i]
                x_right = x_cursor
                x_left = x_cursor - col_w
                x_center = (x_left + x_right) / 2
                if header == "م":
                    c.drawCentredString(x_center, y-2, "م")
                else:
                    text_lines = split_header_text(header)
                    if len(text_lines) == 1:
                        c.drawCentredString(x_center, y-2, reshape_arabic_text(text_lines[0]))
                    else:
                        draw_centered_multiline(c, text_lines, x_center, y-8, font_name, 7)
                x_cursor -= col_w
            y -= 30
            c.setFont(font_name, 8)
        c.setFillColor(colors.white)
        c.rect(x_start, y-5, total_width, 18, fill=1, stroke=0)
        c.setFillColor(colors.black)
        col_w = col_widths[0]
        x_right = x_start + total_width
        x_left = x_right - col_w
        c.drawCentredString((x_left + x_right) / 2, y, str(serial))
        serial += 1
        x_cursor = x_right - col_w
        for i, col in enumerate(actual_columns, start=1):
            col_w = col_widths[i]
            x_right = x_cursor
            x_left = x_cursor - col_w
            value = row[col]
            if isinstance(value, (int, float)):
                value_str = format_currency(value)
            else:
                value_str = str(value)
            c.drawRightString(x_right - 5, y, reshape_arabic_text(value_str))
            x_cursor -= col_w
        c.setStrokeColor(colors.grey)
        c.setLineWidth(0.5)
        c.line(x_start, y+12, x_start+total_width, y+12)
        c.line(x_start, y-5, x_start+total_width, y-5)
        x_cursor = x_start + total_width
        for i in range(len(headers)):
            c.line(x_cursor, y+12, x_cursor, y-5)
            x_cursor -= col_widths[i]
        c.line(x_start, y+12, x_start, y-5)
        y -= 18
    c.line(x_start, y+5, x_start+total_width, y+5)
    y -= 5
    c.setFillColor(colors.HexColor("#e8f0fe"))
    c.rect(x_start, y-5, total_width, 18, fill=1, stroke=0)
    c.setFillColor(colors.black)
    col_w = col_widths[0]
    x_right = x_start + total_width
    x_left = x_right - col_w
    c.drawCentredString((x_left + x_right) / 2, y, reshape_arabic_text("الإجمالي"))
    x_cursor = x_right - col_w
    for i, col in enumerate(actual_columns, start=1):
        col_w = col_widths[i]
        x_right = x_cursor
        x_left = x_cursor - col_w
        if col in ['المبلغ شامل الضريبة', 'مبلغ الضريبة', 'المبلغ غير شامل الضريبة']:
            total_val = df_numeric[col].sum()
            c.drawRightString(x_right - 5, y, format_currency(total_val))
        x_cursor -= col_w
    c.save()
    buffer.seek(0)
    st.download_button("تحميل PDF", data=buffer, file_name=file_name, mime="application/pdf")

def print_receipt(receipt_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''SELECT r.receipt_number, t.name, r.amount, r.receipt_date, r.payment_method, r.notes FROM receipts r JOIN tenants t ON r.tenant_id = t.id WHERE r.id = ?''', (receipt_id,))
    receipt = cur.fetchone()
    conn.close()
    if not receipt:
        st.error("السند غير موجود")
        return None
    receipt_no, tenant_name, amount, r_date, method, notes = receipt
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = setup_arabic_font()
    c.setFont(font_name, 12)
    c.setFillColor(colors.HexColor("#4A90E2"))
    c.rect(0, height-40, width, 40, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_name, 18)
    c.drawCentredString(width/2, height-25, reshape_arabic_text("سند قبض"))
    c.setFont(font_name, 12)
    c.setFillColor(colors.black)
    y = height - 80
    fields = [
        ("رقم السند:", receipt_no),
        ("اسم المستأجر:", tenant_name),
        ("المبلغ:", format_currency(amount)),
        ("تاريخ السداد:", r_date),
        ("طريقة الدفع:", method),
        ("ملاحظات:", notes or "لا يوجد")
    ]
    for label, value in fields:
        c.drawRightString(width - 100, y, reshape_arabic_text(f"{label} {value}"))
        y -= 25
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

# ---------- إدارة قاعدة البيانات ----------
def get_conn():
    conn = sqlite3.connect("rentals.db", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def ensure_columns(cur, table_name, required_columns):
    cur.execute(f"PRAGMA table_info({table_name})")
    existing_columns = [col[1] for col in cur.fetchall()]
    for col_name in required_columns:
        if col_name not in existing_columns:
            if col_name in ('interval_months', 'tax_included'):
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} INTEGER DEFAULT 0")
            elif col_name == 'tax_rate':
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} REAL DEFAULT 0.15")
            elif col_name in ('attachment', 'contract_file', 'permissions'):
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} TEXT")
            else:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} TEXT")

@st.cache_resource
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT, role TEXT DEFAULT 'مشاهد', permissions TEXT DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    ensure_columns(cur, 'users', ['permissions'])
    cur.execute('''CREATE TABLE IF NOT EXISTS tenants (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT, national_id TEXT, address TEXT, region TEXT, notes TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS properties (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, address TEXT, region TEXT, area TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS contracts (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, property_id INTEGER, contract_number TEXT UNIQUE, start_date TEXT, end_date TEXT, rent_amount REAL, interval_months INTEGER DEFAULT 1, deposit_amount REAL, notes TEXT, status TEXT DEFAULT 'نشط', tax_included INTEGER DEFAULT 0, tax_rate REAL DEFAULT 0.15, contract_file BLOB)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER, tenant_id INTEGER, due_date TEXT, amount REAL, paid_amount REAL DEFAULT 0, paid_date TEXT, status TEXT DEFAULT 'مستحق', notes TEXT, attachment BLOB)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS receipts (id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_number TEXT, tenant_id INTEGER, contract_id INTEGER, payment_id INTEGER, amount REAL, receipt_date TEXT, payment_method TEXT, notes TEXT, attachment BLOB)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, note_text TEXT, note_date TEXT, priority TEXT DEFAULT 'عادية', is_alert INTEGER DEFAULT 0)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, alert_text TEXT, alert_date TEXT, is_read INTEGER DEFAULT 0)''')
    ensure_columns(cur, 'payments', ['due_date', 'paid_date', 'attachment'])
    ensure_columns(cur, 'contracts', ['interval_months', 'tax_included', 'tax_rate', 'contract_file'])
    ensure_columns(cur, 'receipts', ['attachment'])
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments(due_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contracts_tenant ON contracts(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(receipt_date)")
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (username, password_hash, role, permissions) VALUES (?, ?, ?, ?)",
                    ('admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'مدير', json.dumps({})))
    else:
        cur.execute("SELECT password_hash FROM users WHERE username = 'admin'")
        admin_hash = cur.fetchone()
        if admin_hash and admin_hash[0] != hashlib.sha256('admin123'.encode()).hexdigest():
            cur.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'",
                        (hashlib.sha256('admin123'.encode()).hexdigest(),))
    conn.commit()
    conn.close()

init_db()

# ---------- دوال الصلاحيات ----------
PAGE_KEYS = [
    "لوحة التحكم",
    "إدارة البيانات",
    "الدفعات",
    "سندات القبض",
    "التقارير",
    "المستخدمون",
    "الإعدادات",
    "نسخ احتياطي"
]

def get_default_permissions(role):
    if role == 'مدير':
        return {page: True for page in PAGE_KEYS}
    elif role == 'محاسب':
        return {
            "لوحة التحكم": True,
            "إدارة البيانات": True,
            "الدفعات": True,
            "سندات القبض": True,
            "التقارير": True,
            "المستخدمون": False,
            "الإعدادات": False,
            "نسخ احتياطي": False
        }
    else:
        return {page: False for page in PAGE_KEYS}

def load_permissions(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in cur.fetchall()]
    if 'permissions' not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT '{}'")
        conn.commit()
    cur.execute("SELECT role, permissions FROM users WHERE id = ?", (user_id,))
    result = cur.fetchone()
    conn.close()
    if not result:
        return {}
    role, permissions_json = result
    permissions = {}
    try:
        permissions = json.loads(permissions_json or '{}')
    except:
        permissions = {}
    default_perms = get_default_permissions(role)
    for key in PAGE_KEYS:
        if key not in permissions:
            permissions[key] = default_perms.get(key, False)
    return permissions

def save_permissions(user_id, permissions):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in cur.fetchall()]
    if 'permissions' not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT '{}'")
    cur.execute("UPDATE users SET permissions = ? WHERE id = ?", (json.dumps(permissions), user_id))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def has_permission(user_id, page):
    if not user_id:
        return False
    permissions = load_permissions(user_id)
    return permissions.get(page, False)

def check_login(username, password):
    conn = get_conn()
    cur = conn.cursor()
    password_hash = hashlib.sha256(password.strip().encode()).hexdigest()
    cur.execute("SELECT id, username, role FROM users WHERE username = ? COLLATE NOCASE AND password_hash = ?", (username.strip(), password_hash))
    user = cur.fetchone()
    conn.close()
    if user:
        return {'id': user[0], 'username': user[1], 'role': user[2]}
    return None

# ---------- دوال الإعدادات ----------
def load_settings():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    conn.close()
    settings = {}
    for row in rows:
        try:
            if row[0] == 'font_size':
                settings[row[0]] = int(row[1])
            else:
                settings[row[0]] = row[1]
        except:
            settings[row[0]] = row[1]
    defaults = {
        'font_size': 18,
        'primary_color': '#4A90E2',
        'secondary_color': '#F5A623',
        'background_color': '#F8F9FA',
        'logo': None,
        'company_name': 'نظام إدارة الإيجارات',
        'telegram_bot_token': '',
        'telegram_chat_id': '',
        'telegram_file_id': ''
    }
    for key, value in defaults.items():
        if key not in settings:
            settings[key] = value
    return settings

def save_setting(key, value):
    conn = get_conn()
    cur = conn.cursor()
    if value is None:
        value_str = ''
    elif isinstance(value, bytes):
        value_str = base64.b64encode(value).decode('utf-8')
    else:
        value_str = str(value)
    cur.execute('''INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value''', (key, value_str))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def load_logo_data():
    settings = load_settings()
    logo_b64 = settings.get('logo', None)
    if logo_b64:
        return base64.b64decode(logo_b64)
    return None

settings = load_settings()
font_size = settings['font_size']
primary_color = settings['primary_color']
secondary_color = settings['secondary_color']
background_color = settings['background_color']
logo_data = load_logo_data()
telegram_bot_token = settings.get('telegram_bot_token', '')
telegram_chat_id = settings.get('telegram_chat_id', '')
telegram_file_id = settings.get('telegram_file_id', '')

# ---------- تسجيل الدخول ----------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_info = None

if not st.session_state.logged_in:
    st.markdown(f"""<style>.login-box{{max-width:400px;margin:auto;padding:40px;background:white;border-radius:10px;box-shadow:0 0 20px rgba(0,0,0,0.1);text-align:center;}}.login-box h2{{color:{primary_color};margin-bottom:20px;}}.login-box input{{width:100%;padding:10px;margin:10px 0;border:1px solid #ddd;border-radius:5px;text-align:right;}}.login-btn{{width:100%;padding:10px;background-color:{secondary_color};color:white;border:none;border-radius:5px;font-size:16px;cursor:pointer;}}</style><div class="login-box"><h2>تسجيل الدخول</h2>""", unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("اسم المستخدم").strip()
        password = st.text_input("كلمة المرور", type="password").strip()
        submitted = st.form_submit_button("دخول")
        if submitted:
            user = check_login(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_info = user
                st.rerun()
            else:
                st.error("اسم المستخدم أو كلمة المرور غير صحيحة")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ---------- بعد تسجيل الدخول ----------
user_info = st.session_state.user_info
current_user_id = user_info['id']
current_role = user_info['role']
user_permissions = load_permissions(current_user_id)

st.markdown(f"""<style>html,body,[class*="css"]{{direction:rtl;text-align:right;font-size:{font_size}px;}}.stApp{{background-color:{background_color};}}.stSidebar{{background-color:{primary_color};color:white;}}.stSidebar [data-testid="stMarkdown"]{{color:white;}}.stSidebar .stRadio label,.stSidebar .stSelectbox label{{color:white!important;}}.stButton>button{{background-color:{secondary_color};color:white;border-radius:8px;border:none;padding:8px 16px;font-weight:bold;}}.stButton>button:hover{{background-color:{primary_color};color:white;}}h1,h2,h3,h4{{color:{primary_color};}}.stMetric{{background-color:white;padding:15px;border-radius:10px;box-shadow:0 2px 5px rgba(0,0,0,0.1);text-align:center;}}.stDataFrame,.stTable{{background-color:white;border-radius:10px;padding:10px;box-shadow:0 2px 5px rgba(0,0,0,0.1);}}.stApp header{{background-color:{primary_color};color:white;}}</style>""", unsafe_allow_html=True)

if logo_data:
    st.sidebar.image(logo_data, width=150)
else:
    st.sidebar.markdown("🏢 **نظام الإدارة**")

st.sidebar.markdown(f"**المستخدم:** {user_info['username']}")
st.sidebar.markdown(f"**الدور:** {current_role}")
st.sidebar.markdown("---")

if st.sidebar.button("تسجيل الخروج"):
    st.session_state.logged_in = False
    st.session_state.user_info = None
    st.rerun()

st.sidebar.markdown("---")

col_up, col_down = st.sidebar.columns(2)
with col_up:
    if st.button('➕ تكبير الخط', use_container_width=True):
        save_setting('font_size', min(24, font_size + 1))
        st.rerun()
with col_down:
    if st.button('➖ تصغير الخط', use_container_width=True):
        save_setting('font_size', max(10, font_size - 1))
        st.rerun()

st.sidebar.markdown("---")

menu = st.sidebar.radio("القائمة الرئيسية", PAGE_KEYS)

# ---------- دوال مساعدة ----------
def add_note(tenant_id, note_text, priority='عادية', is_alert=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''INSERT INTO notes (tenant_id, note_text, note_date, priority, is_alert) VALUES (?, ?, ?, ?, ?)''', (tenant_id, note_text, date.today().isoformat(), priority, is_alert))
    if is_alert:
        cur.execute('''INSERT INTO alerts (tenant_id, alert_text, alert_date) VALUES (?, ?, ?)''', (tenant_id, note_text, date.today().isoformat()))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def generate_receipt_number():
    return f"RCP-{int(time.time())}"

def generate_contract_number():
    conn = get_conn()
    cur = conn.cursor()
    today_str = date.today().strftime("%Y%m%d")
    while True:
        num = f"CTR-{today_str}-{int(time.time() * 1000) % 100000:05d}"
        existing = cur.execute("SELECT id FROM contracts WHERE contract_number = ?", (num,)).fetchone()
        if not existing:
            break
    conn.close()
    return num

def create_payment_schedule(contract_id, tenant_id, start_date, end_date, rent_amount, interval_months):
    step = relativedelta(months=interval_months)
    current = start_date
    conn = get_conn()
    cur = conn.cursor()
    payment_amount = rent_amount * interval_months / 12.0
    count = 0
    while current <= end_date:
        cur.execute('''INSERT INTO payments (contract_id, tenant_id, due_date, amount) VALUES (?, ?, ?, ?)''', (contract_id, tenant_id, current.isoformat(), payment_amount))
        current += step
        count += 1
    conn.commit()
    conn.close()
    return count

def get_unread_alerts(tenant_id=None):
    conn = get_conn()
    cur = conn.cursor()
    if tenant_id:
        cur.execute('''SELECT alert_text, alert_date FROM alerts WHERE tenant_id = ? AND is_read = 0 ORDER BY alert_date DESC''', (tenant_id,))
    else:
        cur.execute('''SELECT a.alert_text, a.alert_date, t.name FROM alerts a JOIN tenants t ON a.tenant_id = t.id WHERE a.is_read = 0 ORDER BY a.alert_date DESC''')
    alerts = cur.fetchall()
    conn.close()
    return alerts

def mark_alerts_read(tenant_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('UPDATE alerts SET is_read = 1 WHERE tenant_id = ? AND is_read = 0', (tenant_id,))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def gregorian_to_hijri(greg_date):
    hijri = convert.Gregorian(greg_date.year, greg_date.month, greg_date.day).to_hijri()
    return f"{hijri.day:02d}-{hijri.month:02d}-{hijri.year}"

def hijri_to_gregorian(hijri_str):
    day, month, year = map(int, hijri_str.split('-'))
    greg = convert.Hijri(year, month, day).to_gregorian()
    return date(greg.year, greg.month, greg.day)

def display_dataframe_with_reorder(df, key_prefix):
    columns = list(df.columns)
    default = st.session_state.get(f"{key_prefix}_order", columns)
    selected_cols = st.multiselect("اختر الأعمدة وترتيبها", options=columns, default=default, key=f"{key_prefix}_cols")
    if selected_cols:
        df = df[selected_cols]
        st.session_state[f"{key_prefix}_order"] = selected_cols
    st.dataframe(df, use_container_width=True)
    return df, selected_cols

# ---------- دوال قراءة البيانات ----------
@st.cache_data(ttl=60)
def load_tenants():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT t.id as "الرقم", t.name as "الاسم", t.phone as "الهاتف", 
               t.national_id as "رقم الهوية / الإقامة", t.address as "العنوان", t.region as "المنطقة",
               COALESCE(c.contract_number, 'لا يوجد عقد') as "رقم العقد",
               CASE 
                   WHEN c.id IS NULL THEN 'بدون عقد'
                   WHEN c.end_date < date('now') THEN 'منتهي'
                   ELSE 'ساري'
               END as "حالة العقد"
        FROM tenants t
        LEFT JOIN contracts c ON c.tenant_id = t.id AND c.status = 'نشط'
        ORDER BY t.name
    """, conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_properties():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT id as "الرقم", name as "الاسم", description as "الوصف", 
               address as "العنوان", region as "المنطقة", area as "المساحة"
        FROM properties
    """, conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_contracts():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(contracts)")
    columns = [col[1] for col in cur.fetchall()]
    select_cols = []
    aliases = {
        'id': 'الرقم',
        'contract_number': 'رقم العقد',
        'start_date': 'تاريخ البداية',
        'end_date': 'تاريخ النهاية',
        'rent_amount': 'قيمة الإيجار السنوي',
        'interval_months': 'دورية السداد (شهور)',
        'deposit_amount': 'التأمين',
        'status': 'الحالة',
        'tax_included': 'شامل الضريبة',
        'tax_rate': 'نسبة الضريبة',
        'contract_file': 'ملف العقد'
    }
    for col in ['id', 'contract_number', 'start_date', 'end_date', 'rent_amount', 'interval_months', 'deposit_amount', 'status', 'tax_included', 'tax_rate', 'contract_file']:
        if col in columns:
            select_cols.append(f"c.{col} as '{aliases[col]}'")
        else:
            if col == 'interval_months':
                select_cols.append("1 as 'دورية السداد (شهور)'")
            elif col == 'tax_included':
                select_cols.append("0 as 'شامل الضريبة'")
            elif col == 'tax_rate':
                select_cols.append("0.15 as 'نسبة الضريبة'")
            elif col == 'contract_file':
                select_cols.append("NULL as 'ملف العقد'")
            else:
                select_cols.append(f"NULL as '{aliases[col]}'")
    query = f"""
        SELECT {', '.join(select_cols)},
               t.name as 'اسم المستأجر', p.name as 'اسم العقار'
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN properties p ON c.property_id = p.id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_payments(status_filter='الكل'):
    conn = get_conn()
    query = '''SELECT pay.id as 'الرقم', t.name as 'المستأجر', p.name as 'العقار', pay.due_date as 'تاريخ الاستحقاق', pay.amount as 'المبلغ', pay.paid_amount as 'المدفوع', (pay.amount - pay.paid_amount) as 'المتبقي', pay.status as 'الحالة', pay.paid_date as 'تاريخ السداد', pay.attachment as 'المرفق' FROM payments pay JOIN tenants t ON pay.tenant_id = t.id JOIN contracts c ON pay.contract_id = c.id JOIN properties p ON c.property_id = p.id'''
    if status_filter != 'الكل':
        query += " WHERE pay.status = ?"
        params = (status_filter,)
    else:
        params = ()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_receipts():
    conn = get_conn()
    query = '''SELECT r.id as 'الرقم', r.receipt_number as 'رقم السند', t.name as 'المستأجر', r.amount as 'المبلغ', r.receipt_date as 'التاريخ', r.payment_method as 'طريقة الدفع', r.notes as 'ملاحظات', r.attachment as 'المرفق' FROM receipts r JOIN tenants t ON r.tenant_id = t.id ORDER BY r.receipt_date DESC'''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def import_tenants_from_excel(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file)
        if "الاسم" not in df.columns:
            st.error("يجب أن يحتوي الملف على عمود 'الاسم'")
            return
        conn = get_conn()
        cur = conn.cursor()
        existing_names = {row[0] for row in cur.execute("SELECT name FROM tenants").fetchall()}
        added = 0
        skipped = 0
        for _, row in df.iterrows():
            name = str(row.get("الاسم", "")).strip()
            if not name:
                continue
            if name in existing_names:
                skipped += 1
                continue
            phone = str(row.get("الهاتف", "")).strip() if "الهاتف" in df.columns else ""
            national_id = str(row.get("رقم الهوية / الإقامة", "")).strip() if "رقم الهوية / الإقامة" in df.columns else ""
            address = str(row.get("العنوان", "")).strip() if "العنوان" in df.columns else ""
            region = str(row.get("المنطقة", "")).strip() if "المنطقة" in df.columns else ""
            notes = str(row.get("ملاحظات", "")).strip() if "ملاحظات" in df.columns else ""
            cur.execute('''INSERT INTO tenants (name, phone, national_id, address, region, notes) VALUES (?, ?, ?, ?, ?, ?)''', (name, phone, national_id, address, region, notes))
            added += 1
        conn.commit()
        conn.close()
        st.cache_data.clear()
        msg = f"تم استيراد {added} مستأجر جديد"
        if skipped > 0:
            msg += f"، وتم تجاهل {skipped} اسم مكرر"
        st.success(msg)
    except Exception as e:
        st.error(f"حدث خطأ أثناء الاستيراد: {str(e)}")

def import_contracts_from_excel(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file)
        required_cols = ["اسم المستأجر", "اسم العقار", "تاريخ البداية", "تاريخ النهاية"]
        for col in required_cols:
            if col not in df.columns:
                st.error(f"يجب أن يحتوي الملف على عمود '{col}'")
                return

        conn = get_conn()
        cur = conn.cursor()
        tenants_dict = {row[1]: row[0] for row in cur.execute("SELECT id, name FROM tenants").fetchall()}
        properties_dict = {row[1]: row[0] for row in cur.execute("SELECT id, name FROM properties").fetchall()}
        existing_contract_numbers = {row[0] for row in cur.execute("SELECT contract_number FROM contracts WHERE contract_number IS NOT NULL").fetchall()}

        imported = 0
        skipped = 0
        errors = []
        for idx, row in df.iterrows():
            try:
                tenant_name = str(row["اسم المستأجر"]).strip()
                property_name = str(row["اسم العقار"]).strip()
                if tenant_name not in tenants_dict:
                    errors.append(f"صف {idx+2}: المستأجر '{tenant_name}' غير موجود")
                    continue
                if property_name not in properties_dict:
                    errors.append(f"صف {idx+2}: العقار '{property_name}' غير موجود")
                    continue

                tenant_id = tenants_dict[tenant_name]
                property_id = properties_dict[property_name]

                contract_number = str(row.get("رقم العقد", "")).strip() if "رقم العقد" in df.columns else ""
                if not contract_number:
                    contract_number = generate_contract_number()
                elif contract_number in existing_contract_numbers:
                    skipped += 1
                    continue

                start_date = pd.to_datetime(row["تاريخ البداية"]).date()
                end_date = pd.to_datetime(row["تاريخ النهاية"]).date()
                rent_amount = float(row.get("قيمة الإيجار السنوي", 0.0)) if "قيمة الإيجار السنوي" in df.columns else 0.0
                interval_months = int(row.get("دورية السداد (شهور)", 1)) if "دورية السداد (شهور)" in df.columns else 1
                deposit_amount = float(row.get("التأمين", 0.0)) if "التأمين" in df.columns else 0.0
                tax_included = 1 if row.get("شامل الضريبة", False) else 0
                tax_rate = float(row.get("نسبة الضريبة", 0.15)) if "نسبة الضريبة" in df.columns else 0.15
                notes = str(row.get("ملاحظات", "")).strip() if "ملاحظات" in df.columns else ""

                if start_date >= end_date:
                    errors.append(f"صف {idx+2}: تاريخ البداية بعد تاريخ النهاية")
                    continue

                cur.execute('''INSERT INTO contracts (tenant_id, property_id, contract_number, start_date, end_date, rent_amount, interval_months, deposit_amount, notes, tax_included, tax_rate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (tenant_id, property_id, contract_number, start_date.isoformat(), end_date.isoformat(), rent_amount, interval_months, deposit_amount, notes, tax_included, tax_rate))
                contract_id = cur.lastrowid
                count = create_payment_schedule(contract_id, tenant_id, start_date, end_date, rent_amount, interval_months)
                imported += 1
                existing_contract_numbers.add(contract_number)
            except Exception as e:
                errors.append(f"صف {idx+2}: {str(e)}")

        conn.commit()
        conn.close()
        st.cache_data.clear()
        msg = f"تم استيراد {imported} عقد جديد"
        if skipped > 0:
            msg += f"، وتم تجاهل {skipped} عقد مكرر"
        if imported > 0:
            st.success(msg)
        if errors:
            st.warning("بعض الأخطاء: " + "; ".join(errors[:10]))
    except Exception as e:
        st.error(f"حدث خطأ أثناء الاستيراد: {str(e)}")

def import_properties_from_excel(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file)
        required_cols = ["الاسم"]
        for col in required_cols:
            if col not in df.columns:
                st.error(f"يجب أن يحتوي الملف على عمود '{col}'")
                return

        conn = get_conn()
        cur = conn.cursor()
        existing_names = {row[0] for row in cur.execute("SELECT name FROM properties").fetchall()}
        added = 0
        skipped = 0
        for _, row in df.iterrows():
            name = str(row["الاسم"]).strip()
            if not name:
                continue
            if name in existing_names:
                skipped += 1
                continue
            description = str(row.get("الوصف", "")).strip() if "الوصف" in df.columns else ""
            address = str(row.get("العنوان", "")).strip() if "العنوان" in df.columns else ""
            region = str(row.get("المنطقة", "")).strip() if "المنطقة" in df.columns else ""
            area = str(row.get("المساحة", "")).strip() if "المساحة" in df.columns else ""
            cur.execute('''INSERT INTO properties (name, description, address, region, area) VALUES (?, ?, ?, ?, ?)''', (name, description, address, region, area))
            added += 1
        conn.commit()
        conn.close()
        st.cache_data.clear()
        msg = f"تم استيراد {added} عقار جديد"
        if skipped > 0:
            msg += f"، وتم تجاهل {skipped} اسم مكرر"
        st.success(msg)
    except Exception as e:
        st.error(f"حدث خطأ أثناء الاستيراد: {str(e)}")

def add_user(username, password, role):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),))
    if cur.fetchone()[0] > 0:
        conn.close()
        return False, "اسم المستخدم موجود مسبقاً"
    password_hash = hashlib.sha256(password.strip().encode()).hexdigest()
    default_perms = get_default_permissions(role)
    cur.execute('''INSERT INTO users (username, password_hash, role, permissions) VALUES (?, ?, ?, ?)''', (username.strip(), password_hash, role, json.dumps(default_perms)))
    conn.commit()
    conn.close()
    return True, "تم إضافة المستخدم بنجاح"

def update_user_role(user_id, new_role):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    old_role = cur.fetchone()[0]
    if old_role != new_role:
        default_perms = get_default_permissions(new_role)
        cur.execute("UPDATE users SET role = ?, permissions = ? WHERE id = ?", (new_role, json.dumps(default_perms), user_id))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def delete_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def load_users():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id as 'الرقم', username as 'اسم المستخدم', role as 'الدور' FROM users", conn)
    conn.close()
    return df

def delete_contract(contract_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM receipts WHERE contract_id = ?", (contract_id,))
    cur.execute("DELETE FROM payments WHERE contract_id = ?", (contract_id,))
    cur.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def update_payment(payment_id, due_date, amount, status, notes):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''UPDATE payments SET due_date=?, amount=?, status=?, notes=? WHERE id=?''', (due_date, amount, status, notes, payment_id))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def update_receipt_amount(receipt_id, new_amount):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT payment_id, amount FROM receipts WHERE id = ?", (receipt_id,))
    receipt_data = cur.fetchone()
    if not receipt_data:
        conn.close()
        return False, "السند غير موجود"
    payment_id, old_amount = receipt_data
    cur.execute("UPDATE receipts SET amount = ? WHERE id = ?", (new_amount, receipt_id))
    if payment_id:
        cur.execute("SELECT amount, paid_amount FROM payments WHERE id = ?", (payment_id,))
        pay_data = cur.fetchone()
        if pay_data:
            new_paid = pay_data[1] - old_amount + new_amount
            if new_paid < 0:
                new_paid = 0
            status = "مدفوع" if new_paid >= pay_data[0] else "جزئي" if new_paid > 0 else "مستحق"
            cur.execute("UPDATE payments SET paid_amount = ?, status = ? WHERE id = ?", (new_paid, status, payment_id))
    conn.commit()
    conn.close()
    st.cache_data.clear()
    return True, "تم تعديل السند بنجاح"

# ================== دوال القوالب (Templates) ==================
def download_tenants_template():
    df = pd.DataFrame(columns=[
        "الاسم", "الهاتف", "رقم الهوية / الإقامة", "العنوان", "المنطقة", "ملاحظات"
    ])
    df.loc[0] = ["مثال: أحمد محمد", "0501234567", "1234567890", "شارع الملك فهد", "الرياض", "مثال"]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='المستأجرين')
    output.seek(0)
    st.download_button(
        label="تحميل قالب استيراد المستأجرين",
        data=output.getvalue(),
        file_name="نموذج_استيراد_المستأجرين.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def download_contracts_template():
    df = pd.DataFrame(columns=[
        "اسم المستأجر", "اسم العقار", "تاريخ البداية", "تاريخ النهاية",
        "قيمة الإيجار السنوي", "دورية السداد (شهور)", "التأمين",
        "شامل الضريبة", "نسبة الضريبة", "ملاحظات"
    ])
    df.loc[0] = ["أحمد محمد", "عمارة النخبة", "2025-01-01", "2025-12-31", 60000, 6, 5000, 0, 0.15, "مثال"]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='العقود')
    output.seek(0)
    st.download_button(
        label="تحميل قالب استيراد العقود",
        data=output.getvalue(),
        file_name="نموذج_استيراد_العقود.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def download_properties_template():
    df = pd.DataFrame(columns=[
        "الاسم", "الوصف", "العنوان", "المنطقة", "المساحة"
    ])
    df.loc[0] = ["عمارة النخبة", "عمارة سكنية 4 شقق", "حي الروضة", "جدة", "500 م²"]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='العقارات')
    output.seek(0)
    st.download_button(
        label="تحميل قالب استيراد العقارات",
        data=output.getvalue(),
        file_name="نموذج_استيراد_العقارات.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ================== لوحة التحكم ==================
if menu == "لوحة التحكم" and has_permission(current_user_id, "لوحة التحكم"):
    st.subheader("📊 لوحة التحكم")
    df_tenants = load_tenants()
    df_contracts = load_contracts()
    df_payments = load_payments()
    today = date.today()
    soon_limit = today + timedelta(days=60)
    df_contracts['end_date_dt'] = pd.to_datetime(df_contracts['تاريخ النهاية'])
    expiring_soon = df_contracts[(df_contracts['الحالة'] == 'نشط') & (df_contracts['end_date_dt'] >= pd.Timestamp(today)) & (df_contracts['end_date_dt'] <= pd.Timestamp(soon_limit))]
    expired = df_contracts[(df_contracts['الحالة'] == 'نشط') & (df_contracts['end_date_dt'] < pd.Timestamp(today))]
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("إجمالي المستأجرين", len(df_tenants))
    with col2:
        active_contracts = len(df_contracts[df_contracts["الحالة"] == "نشط"])
        st.metric("العقود النشطة", active_contracts)
    with col3:
        due_payments = len(df_payments[df_payments["الحالة"].isin(["مستحق", "متأخر", "جزئي"])])
        st.metric("دفعات مستحقة", due_payments)
    with col4:
        total_collected = df_payments["المدفوع"].sum()
        st.metric("إجمالي المحصل", format_currency(total_collected))
    col5, col6 = st.columns(2)
    with col5:
        st.metric("عقود تنتهي خلال شهرين", len(expiring_soon))
    with col6:
        st.metric("عقود منتهية", len(expired))
    st.markdown("---")
    st.subheader("⚠️ تنبيهات غير مقروءة")
    alerts = get_unread_alerts()
    if alerts:
        for alert in alerts:
            st.warning(f"**{alert[2]}** - {alert[0]} (تاريخ: {alert[1]})")
    else:
        st.info("لا توجد تنبيهات.")
    st.markdown("---")
    st.subheader("📅 الدفعات القادمة خلال 30 يوم")
    upcoming = df_payments[
        (df_payments["تاريخ الاستحقاق"] >= today.isoformat()) &
        (df_payments["تاريخ الاستحقاق"] <= (today + timedelta(days=30)).isoformat()) &
        (df_payments["الحالة"].isin(["مستحق", "جزئي"]))
    ]
    if not upcoming.empty:
        upcoming_display = upcoming[["المستأجر", "العقار", "تاريخ الاستحقاق", "المبلغ", "المدفوع", "الحالة"]]
        display_dataframe_with_reorder(upcoming_display, "upcoming")
    else:
        st.info("لا توجد دفعات مستحقة خلال 30 يوم.")

# ================== إدارة البيانات ==================
elif menu == "إدارة البيانات":
    if not has_permission(current_user_id, "إدارة البيانات"):
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        st.subheader("📂 إدارة البيانات")
        data_tab1, data_tab2, data_tab3 = st.tabs(["المستأجرين", "العقارات", "العقود"])

        # ----- تبويب المستأجرين -----
        with data_tab1:
            st.subheader("👥 المستأجرين")
            col_import1, col_import2 = st.columns(2)
            with col_import1:
                download_tenants_template()
            with col_import2:
                uploaded_tenants = st.file_uploader("استيراد من Excel", type=["xlsx", "xls"], key="import_tenants")
                if uploaded_tenants is not None:
                    if st.button("تنفيذ الاستيراد", key="btn_import_tenants"):
                        import_tenants_from_excel(uploaded_tenants)
                        st.rerun()
            st.markdown("---")

            df_tenants = load_tenants()
            if not df_tenants.empty:
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    region_filter = st.selectbox("المنطقة", ["الكل"] + df_tenants["المنطقة"].dropna().unique().tolist(), key="tenant_region_filter")
                with col_f2:
                    search_term = st.text_input("بحث بالاسم أو الهاتف", key="tenant_search")
                filtered = df_tenants.copy()
                if region_filter != "الكل":
                    filtered = filtered[filtered["المنطقة"] == region_filter]
                if search_term:
                    mask = filtered.apply(lambda row: search_term.lower() in str(row.values).lower(), axis=1)
                    filtered = filtered[mask]
                if not filtered.empty:
                    st.dataframe(filtered, use_container_width=True)
                    tenant_id = st.selectbox("اختر مستأجر", filtered["الرقم"], format_func=lambda x: filtered[filtered["الرقم"]==x]["الاسم"].iloc[0])
                    if tenant_id:
                        conn = get_conn()
                        cur = conn.cursor()
                        tenant_info = cur.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
                        st.markdown(f"**الاسم:** {tenant_info['name']} | **الهاتف:** {tenant_info['phone'] or 'غير محدد'} | **المنطقة:** {tenant_info['region'] or 'غير محدد'}")
                        contracts = cur.execute("""
                            SELECT c.contract_number, p.name, c.start_date, c.end_date, c.status, c.rent_amount, c.interval_months
                            FROM contracts c JOIN properties p ON c.property_id=p.id WHERE c.tenant_id=?
                        """, (tenant_id,)).fetchall()
                        conn.close()
                        if contracts:
                            st.markdown("**العقود المرتبطة:**")
                            df_contracts_tenant = pd.DataFrame(contracts, columns=["رقم العقد", "العقار", "بداية", "نهاية", "الحالة", "إيجار سنوي", "دورية"])
                            st.dataframe(df_contracts_tenant, use_container_width=True)
                        else:
                            st.info("لا توجد عقود لهذا المستأجر")
                        if current_role == 'مدير':
                            c1, c2 = st.columns(2)
                            with c1:
                                if st.button("تعديل المستأجر", key="edit_tenant_btn"):
                                    st.session_state['edit_tenant_id'] = tenant_id
                                    st.rerun()
                            with c2:
                                if st.button("حذف المستأجر", key="del_tenant_btn"):
                                    conn = get_conn()
                                    cur = conn.cursor()
                                    has_contracts = cur.execute("SELECT COUNT(*) FROM contracts WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
                                    if has_contracts > 0:
                                        st.error("لا يمكن حذف مستأجر لديه عقود")
                                    else:
                                        cur.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
                                        conn.commit()
                                        st.success("تم الحذف")
                                        st.rerun()
                                    conn.close()
                        if 'edit_tenant_id' in st.session_state and st.session_state['edit_tenant_id'] == tenant_id:
                            conn = get_conn()
                            cur = conn.cursor()
                            tdata = cur.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
                            conn.close()
                            with st.form("edit_tenant_form"):
                                name = st.text_input("الاسم", value=tdata['name'])
                                phone = st.text_input("الهاتف", value=tdata['phone'] or "")
                                national_id = st.text_input("رقم الهوية", value=tdata['national_id'] or "")
                                address = st.text_input("العنوان", value=tdata['address'] or "")
                                region = st.text_input("المنطقة", value=tdata['region'] or "")
                                notes = st.text_area("ملاحظات", value=tdata['notes'] or "")
                                if st.form_submit_button("حفظ التعديلات"):
                                    conn = get_conn()
                                    cur = conn.cursor()
                                    cur.execute("UPDATE tenants SET name=?, phone=?, national_id=?, address=?, region=?, notes=? WHERE id=?", (name, phone, national_id, address, region, notes, tenant_id))
                                    conn.commit()
                                    conn.close()
                                    st.cache_data.clear()
                                    st.success("تم التحديث")
                                    st.session_state['edit_tenant_id'] = None
                                    st.rerun()
                else:
                    st.info("لا توجد نتائج")
            else:
                st.info("لا يوجد مستأجرين")

        # ----- تبويب العقارات -----
        with data_tab2:
            st.subheader("🏬 العقارات")
            col_import1, col_import2 = st.columns(2)
            with col_import1:
                download_properties_template()
            with col_import2:
                uploaded_properties = st.file_uploader("استيراد من Excel", type=["xlsx", "xls"], key="import_properties")
                if uploaded_properties is not None:
                    if st.button("تنفيذ الاستيراد", key="btn_import_properties"):
                        import_properties_from_excel(uploaded_properties)
                        st.rerun()
            st.markdown("---")

            df_props = load_properties()
            if not df_props.empty:
                search_prop = st.text_input("بحث", key="prop_search")
                if search_prop:
                    mask = df_props.apply(lambda row: search_prop.lower() in str(row.values).lower(), axis=1)
                    filtered_props = df_props[mask]
                else:
                    filtered_props = df_props
                if not filtered_props.empty:
                    st.dataframe(filtered_props, use_container_width=True)
                    prop_id = st.selectbox("اختر عقار", filtered_props["الرقم"], format_func=lambda x: filtered_props[filtered_props["الرقم"]==x]["الاسم"].iloc[0])
                    if prop_id:
                        conn = get_conn()
                        cur = conn.cursor()
                        prop_info = cur.execute("SELECT * FROM properties WHERE id=?", (prop_id,)).fetchone()
                        st.markdown(f"**الاسم:** {prop_info['name']} | **المنطقة:** {prop_info['region'] or 'غير محدد'} | **العنوان:** {prop_info['address'] or 'غير محدد'}")
                        contracts = cur.execute("""
                            SELECT c.contract_number, t.name, c.start_date, c.end_date, c.status
                            FROM contracts c JOIN tenants t ON c.tenant_id=t.id WHERE c.property_id=?
                        """, (prop_id,)).fetchall()
                        conn.close()
                        if contracts:
                            st.markdown("**العقود المرتبطة:**")
                            df_contracts_prop = pd.DataFrame(contracts, columns=["رقم العقد", "المستأجر", "بداية", "نهاية", "الحالة"])
                            st.dataframe(df_contracts_prop, use_container_width=True)
                        else:
                            st.info("لا توجد عقود لهذا العقار")
                        if current_role == 'مدير':
                            c1, c2 = st.columns(2)
                            with c1:
                                if st.button("تعديل العقار", key="edit_prop_btn"):
                                    st.session_state['edit_property_id'] = prop_id
                                    st.rerun()
                            with c2:
                                if st.button("حذف العقار", key="del_prop_btn"):
                                    conn = get_conn()
                                    cur = conn.cursor()
                                    has_contracts = cur.execute("SELECT COUNT(*) FROM contracts WHERE property_id=?", (prop_id,)).fetchone()[0]
                                    if has_contracts > 0:
                                        st.error("لا يمكن حذف عقار لديه عقود")
                                    else:
                                        cur.execute("DELETE FROM properties WHERE id=?", (prop_id,))
                                        conn.commit()
                                        st.success("تم الحذف")
                                        st.rerun()
                                    conn.close()
                        if 'edit_property_id' in st.session_state and st.session_state['edit_property_id'] == prop_id:
                            conn = get_conn()
                            cur = conn.cursor()
                            pdata = cur.execute("SELECT * FROM properties WHERE id=?", (prop_id,)).fetchone()
                            conn.close()
                            with st.form("edit_property_form"):
                                name = st.text_input("الاسم", value=pdata['name'])
                                description = st.text_area("الوصف", value=pdata['description'] or "")
                                address = st.text_input("العنوان", value=pdata['address'] or "")
                                region = st.text_input("المنطقة", value=pdata['region'] or "")
                                area = st.text_input("المساحة", value=pdata['area'] or "")
                                if st.form_submit_button("حفظ التعديلات"):
                                    conn = get_conn()
                                    cur = conn.cursor()
                                    cur.execute("UPDATE properties SET name=?, description=?, address=?, region=?, area=? WHERE id=?", (name, description, address, region, area, prop_id))
                                    conn.commit()
                                    conn.close()
                                    st.cache_data.clear()
                                    st.success("تم التحديث")
                                    st.session_state['edit_property_id'] = None
                                    st.rerun()
                else:
                    st.info("لا توجد نتائج")
            else:
                st.info("لا توجد عقارات")

        # ----- تبويب العقود -----
        with data_tab3:
            st.subheader("📄 العقود")
            col_import1, col_import2 = st.columns(2)
            with col_import1:
                download_contracts_template()
            with col_import2:
                uploaded_contracts = st.file_uploader("استيراد من Excel", type=["xlsx", "xls"], key="import_contracts")
                if uploaded_contracts is not None:
                    if st.button("تنفيذ الاستيراد", key="btn_import_contracts"):
                        import_contracts_from_excel(uploaded_contracts)
                        st.rerun()
            st.markdown("---")

            df_contracts = load_contracts()
            if not df_contracts.empty:
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    region_filter_c = st.selectbox("المنطقة", ["الكل"] + load_tenants()["المنطقة"].dropna().unique().tolist(), key="contract_region_filter")
                with col_c2:
                    tenant_filter_c = st.selectbox("المستأجر", ["الكل"] + df_contracts["اسم المستأجر"].unique().tolist(), key="contract_tenant_filter")
                filtered_c = df_contracts.copy()
                if region_filter_c != "الكل":
                    tenants_in_region = load_tenants()[load_tenants()["المنطقة"] == region_filter_c]["الاسم"].tolist()
                    filtered_c = filtered_c[filtered_c["اسم المستأجر"].isin(tenants_in_region)]
                if tenant_filter_c != "الكل":
                    filtered_c = filtered_c[filtered_c["اسم المستأجر"] == tenant_filter_c]
                if not filtered_c.empty:
                    st.dataframe(filtered_c, use_container_width=True)
                    contract_id = st.selectbox("اختر عقد", filtered_c["الرقم"], format_func=lambda x: filtered_c[filtered_c["الرقم"]==x]["رقم العقد"].iloc[0])
                    if contract_id:
                        conn = get_conn()
                        cur = conn.cursor()
                        cinfo = cur.execute("""
                            SELECT c.*, t.name as tenant_name, t.phone as tenant_phone, t.region as tenant_region,
                                   p.name as prop_name, p.address as prop_address, p.region as prop_region
                            FROM contracts c
                            JOIN tenants t ON c.tenant_id=t.id
                            JOIN properties p ON c.property_id=p.id
                            WHERE c.id=?
                        """, (contract_id,)).fetchone()
                        conn.close()
                        st.markdown("### تفاصيل العقد")
                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            st.write(f"**رقم العقد:** {cinfo['contract_number']}")
                            st.write(f"**المستأجر:** {cinfo['tenant_name']}")
                            st.write(f"**هاتف المستأجر:** {cinfo['tenant_phone'] or 'غير محدد'}")
                            st.write(f"**منطقة المستأجر:** {cinfo['tenant_region'] or 'غير محدد'}")
                        with col_d2:
                            st.write(f"**العقار:** {cinfo['prop_name']}")
                            st.write(f"**عنوان العقار:** {cinfo['prop_address'] or 'غير محدد'}")
                            st.write(f"**منطقة العقار:** {cinfo['prop_region'] or 'غير محدد'}")
                        st.divider()
                        st.write(f"**بداية العقد:** {cinfo['start_date']}")
                        st.write(f"**نهاية العقد:** {cinfo['end_date']}")
                        st.write(f"**الإيجار السنوي:** {format_currency(cinfo['rent_amount'])}")
                        st.write(f"**دورية السداد:** كل {cinfo['interval_months']} شهر")
                        st.write(f"**التأمين:** {format_currency(cinfo['deposit_amount'])}")
                        st.write(f"**الحالة:** {cinfo['status']}")
                        st.write(f"**شامل الضريبة:** {'نعم' if cinfo['tax_included'] else 'لا'}")
                        st.write(f"**نسبة الضريبة:** {cinfo['tax_rate']*100:.1f}%")
                        st.write(f"**ملاحظات:** {cinfo['notes'] or 'لا يوجد'}")

                        if cinfo['contract_file']:
                            st.download_button("📥 تحميل ملف العقد", data=cinfo['contract_file'], file_name=f"contract_{contract_id}.pdf", mime="application/pdf")
                        else:
                            st.info("لا يوجد ملف عقد مرفق")

                        if current_role == 'مدير':
                            c1, c2 = st.columns(2)
                            with c1:
                                if st.button("تعديل العقد", key="edit_contract_btn"):
                                    st.session_state['edit_contract_id'] = contract_id
                                    st.rerun()
                            with c2:
                                if st.button("حذف العقد", key="del_contract_btn"):
                                    delete_contract(contract_id)
                                    st.success("تم الحذف")
                                    st.rerun()

                        if 'edit_contract_id' in st.session_state and st.session_state['edit_contract_id'] == contract_id:
                            conn = get_conn()
                            cur = conn.cursor()
                            cdata = cur.execute("SELECT * FROM contracts WHERE id=?", (contract_id,)).fetchone()
                            conn.close()
                            df_tenants_all = load_tenants()
                            df_props_all = load_properties()
                            with st.form("edit_contract_form"):
                                tenant_id = st.selectbox("المستأجر", df_tenants_all["الرقم"], index=df_tenants_all.index[df_tenants_all["الرقم"]==cdata['tenant_id']][0], format_func=lambda x: df_tenants_all[df_tenants_all["الرقم"]==x]["الاسم"].iloc[0])
                                property_id = st.selectbox("العقار", df_props_all["الرقم"], index=df_props_all.index[df_props_all["الرقم"]==cdata['property_id']][0], format_func=lambda x: df_props_all[df_props_all["الرقم"]==x]["الاسم"].iloc[0])
                                contract_number = st.text_input("رقم العقد", value=cdata['contract_number'])
                                start_date = st.date_input("تاريخ البداية", value=parse_date_safe(cdata['start_date']))
                                end_date = st.date_input("تاريخ النهاية", value=parse_date_safe(cdata['end_date']))
                                rent_amount = st.number_input("قيمة الإيجار السنوي", min_value=0.0, step=100.0, value=float(cdata['rent_amount']))
                                interval_months = st.number_input("دورية السداد (شهور)", min_value=1, value=int(cdata['interval_months']))
                                deposit_amount = st.number_input("التأمين", min_value=0.0, step=100.0, value=float(cdata['deposit_amount']))
                                tax_included = st.checkbox("المبلغ شامل الضريبة", value=bool(cdata['tax_included']))
                                tax_rate = st.number_input("نسبة الضريبة (%)", min_value=0.0, value=float(cdata['tax_rate'])*100, step=1.0) / 100
                                notes = st.text_area("ملاحظات", value=cdata['notes'] or "")
                                new_contract_file = st.file_uploader("استبدال ملف العقد (PDF)", type=["pdf"])
                                if st.form_submit_button("حفظ التعديلات"):
                                    if start_date >= end_date:
                                        st.error("تاريخ النهاية يجب أن يكون بعد البداية")
                                    else:
                                        if contract_number != cdata['contract_number']:
                                            existing = get_conn().execute("SELECT id FROM contracts WHERE contract_number=? AND id!=?", (contract_number, contract_id)).fetchone()
                                            if existing:
                                                st.error("رقم العقد موجود بالفعل")
                                                st.stop()
                                        file_bytes = cdata['contract_file']
                                        if new_contract_file is not None:
                                            file_bytes = new_contract_file.read()
                                        conn = get_conn()
                                        cur = conn.cursor()
                                        cur.execute("""
                                            UPDATE contracts SET tenant_id=?, property_id=?, contract_number=?, start_date=?, end_date=?, rent_amount=?, interval_months=?, deposit_amount=?, tax_included=?, tax_rate=?, notes=?, contract_file=?
                                            WHERE id=?
                                        """, (tenant_id, property_id, contract_number, start_date.isoformat(), end_date.isoformat(), rent_amount, interval_months, deposit_amount, 1 if tax_included else 0, tax_rate, notes, file_bytes, contract_id))
                                        conn.commit()
                                        conn.close()
                                        conn = get_conn()
                                        cur = conn.cursor()
                                        cur.execute("DELETE FROM payments WHERE contract_id=?", (contract_id,))
                                        conn.commit()
                                        conn.close()
                                        count = create_payment_schedule(contract_id, tenant_id, start_date, end_date, rent_amount, interval_months)
                                        st.cache_data.clear()
                                        st.success(f"تم تحديث العقد وإعادة جدولة الدفعات ({count} دفعة)")
                                        st.session_state['edit_contract_id'] = None
                                        st.rerun()
                else:
                    st.info("لا توجد عقود مطابقة")
            else:
                st.info("لا توجد عقود")

# ================== الدفعات ==================
elif menu == "الدفعات":
    st.subheader("💰 متابعة الدفعات")
    if not has_permission(current_user_id, "الدفعات"):
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        tab1, tab2 = st.tabs(["عرض الدفعات", "تعديل دفعة"])
        with tab1:
            status_filter = st.selectbox("فلتر الحالة", ["الكل", "مستحق", "مدفوع", "متأخر", "جزئي"])
            df_payments = load_payments(status_filter)
            if not df_payments.empty:
                search_payment = st.text_input("بحث باسم المستأجر", key="search_payment")
                if search_payment:
                    mask = df_payments["المستأجر"].str.contains(search_payment, case=False, na=False)
                    filtered_payments = df_payments[mask]
                else:
                    filtered_payments = df_payments
                if not filtered_payments.empty:
                    display_dataframe_with_reorder(filtered_payments.drop(columns=["المرفق"]), "payments_filtered")
                    col_exp1, col_exp2 = st.columns(2)
                    with col_exp1:
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            filtered_payments.drop(columns=["المرفق"]).to_excel(writer, index=False)
                        st.download_button("تحميل Excel", data=output.getvalue(), file_name="الدفعات_المفلترة.xlsx")
                    with col_exp2:
                        export_df_to_pdf(filtered_payments.drop(columns=["المرفق"]), "بيان الدفعات", "الدفعات_المفلترة.pdf")
                else:
                    st.info("لا توجد نتائج")
            else:
                st.info("لا توجد دفعات")
        with tab2:
            if current_role == 'مدير':
                df_payments = load_payments()
                if not df_payments.empty:
                    payment_id = st.selectbox("اختر دفعة للتعديل", df_payments["الرقم"].tolist())
                    if payment_id:
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute("SELECT due_date, amount, status, notes FROM payments WHERE id = ?", (payment_id,))
                        pay_data = cur.fetchone()
                        conn.close()
                        with st.form("edit_payment_form"):
                            due_date = st.date_input("تاريخ الاستحقاق", value=parse_date_safe(pay_data[0]))
                            amount = st.number_input("المبلغ", min_value=0.0, step=100.0, value=float(pay_data[1]))
                            status = st.selectbox("الحالة", ["مستحق", "مدفوع", "جزئي", "متأخر"], index=["مستحق", "مدفوع", "جزئي", "متأخر"].index(pay_data[2]))
                            notes = st.text_area("ملاحظات", value=pay_data[3] or "")
                            if st.form_submit_button("حفظ"):
                                update_payment(payment_id, due_date.isoformat(), amount, status, notes)
                                st.success("تم تعديل الدفعة")
                                st.rerun()
                else:
                    st.info("لا توجد دفعات")
            else:
                st.warning("لا تملك صلاحية تعديل الدفعات")

# ================== سندات القبض ==================
elif menu == "سندات القبض":
    st.subheader("🧾 سندات القبض")
    if not has_permission(current_user_id, "سندات القبض"):
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        tab1, tab2 = st.tabs(["تسجيل سداد", "سجل سندات القبض"])
        with tab1:
            if current_role == 'مدير' or current_role == 'محاسب':
                df_tenants = load_tenants()
                if df_tenants.empty:
                    st.warning("لا يوجد مستأجرين")
                else:
                    tenant_id = st.selectbox("اختر المستأجر", df_tenants["الرقم"], format_func=lambda x: df_tenants[df_tenants["الرقم"]==x]["الاسم"].iloc[0])
                    today = date.today()
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute('''SELECT id, due_date, amount, paid_amount, (amount - paid_amount) as remaining FROM payments WHERE tenant_id = ? AND status != 'مدفوع' AND due_date <= ? ORDER BY due_date''', (tenant_id, today.isoformat()))
                    dues = cur.fetchall()
                    conn.close()
                    if not dues:
                        st.info("لا توجد دفعات مستحقة")
                    else:
                        df_dues = pd.DataFrame(dues, columns=["رقم الدفعة", "تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي"])
                        df_dues["المبلغ"] = df_dues["المبلغ"].apply(format_currency)
                        df_dues["المدفوع"] = df_dues["المدفوع"].apply(format_currency)
                        df_dues["المتبقي"] = df_dues["المتبقي"].apply(format_currency)
                        st.dataframe(df_dues, use_container_width=True)
                        payment_ids = df_dues["رقم الدفعة"].tolist()
                        payment_id = st.selectbox("اختر الدفعة", payment_ids, format_func=lambda x: f"دفعة رقم {x}")
                        if payment_id:
                            remaining_amount = float(df_dues[df_dues["رقم الدفعة"] == payment_id]["المتبقي"].iloc[0].replace(",", ""))
                            payment_date = st.date_input("تاريخ السداد", value=today)
                            amount = st.number_input("المبلغ", min_value=0.0, max_value=remaining_amount, value=remaining_amount, step=100.0)
                            method = st.selectbox("طريقة الدفع", ["نقدي", "تحويل بنكي", "شيك", "دفع في المنصة"])
                            attachment = st.file_uploader("مرفق دليل الدفع", type=["pdf", "png", "jpg", "jpeg"])
                            if st.button("تسجيل السداد"):
                                if amount <= 0:
                                    st.error("المبلغ يجب أن يكون أكبر من صفر")
                                else:
                                    file_bytes = None
                                    if attachment is not None:
                                        file_bytes = attachment.read()
                                    conn = get_conn()
                                    cur = conn.cursor()
                                    cur.execute("SELECT amount, paid_amount, contract_id FROM payments WHERE id = ?", (payment_id,))
                                    pay_data = cur.fetchone()
                                    new_paid = pay_data[1] + amount
                                    status = "مدفوع" if new_paid >= pay_data[0] else "جزئي"
                                    cur.execute('''UPDATE payments SET paid_amount = ?, paid_date = ?, status = ?, attachment = ? WHERE id = ?''', (new_paid, payment_date.isoformat(), status, file_bytes, payment_id))
                                    receipt_number = generate_receipt_number()
                                    cur.execute('''INSERT INTO receipts (receipt_number, tenant_id, contract_id, payment_id, amount, receipt_date, payment_method, attachment) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (receipt_number, tenant_id, pay_data[2], payment_id, amount, payment_date.isoformat(), method, file_bytes))
                                    conn.commit()
                                    conn.close()
                                    st.cache_data.clear()
                                    st.success(f"تم تسجيل سداد بمبلغ {format_currency(amount)}")
                                    st.rerun()
            else:
                st.warning("لا تملك صلاحية تسجيل السداد")
        with tab2:
            df_receipts = load_receipts()
            if not df_receipts.empty:
                display_dataframe_with_reorder(df_receipts.drop(columns=["المرفق"]), "receipts")
                receipt_id = st.selectbox("اختر سند", df_receipts["الرقم"], format_func=lambda x: f"{df_receipts[df_receipts['الرقم']==x]['رقم السند'].iloc[0]}")
                if receipt_id:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        pdf_data = print_receipt(receipt_id)
                        if pdf_data:
                            st.download_button("طباعة السند", data=pdf_data, file_name=f"receipt_{receipt_id}.pdf", mime="application/pdf")
                    with col2:
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute("SELECT attachment FROM receipts WHERE id = ?", (receipt_id,))
                        att = cur.fetchone()
                        conn.close()
                        if att and att[0]:
                            st.download_button("تحميل المرفق", data=att[0], file_name=f"receipt_{receipt_id}_attachment.pdf", mime="application/octet-stream")
                    with col3:
                        if current_role == 'مدير':
                            if st.button("تعديل المبلغ"):
                                st.session_state['edit_receipt_id'] = receipt_id
                                st.rerun()
                    if 'edit_receipt_id' in st.session_state and st.session_state['edit_receipt_id'] == receipt_id and current_role == 'مدير':
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute("SELECT amount FROM receipts WHERE id = ?", (receipt_id,))
                        current_amount = cur.fetchone()[0]
                        conn.close()
                        with st.form("edit_receipt_form"):
                            new_amount = st.number_input("المبلغ الجديد", min_value=0.0, step=100.0, value=float(current_amount))
                            if st.form_submit_button("حفظ التعديل"):
                                success, message = update_receipt_amount(receipt_id, new_amount)
                                if success:
                                    st.success(message)
                                    st.session_state['edit_receipt_id'] = None
                                    st.rerun()
                                else:
                                    st.error(message)
            else:
                st.info("لا توجد سندات قبض")

# ================== التقارير ==================
elif menu == "التقارير":
    st.subheader("📈 التقارير")
    if not has_permission(current_user_id, "التقارير"):
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        report_type = st.radio("اختر التقرير", [
            "كشف حساب مستأجر",
            "الدفعات المستحقة بين تاريخين",
            "تقرير الإيرادات",
            "تقرير الضرائب"
        ])
        cal_choice = st.radio("نوع التاريخ", ["ميلادي", "هجري"], horizontal=True)

        if report_type == "كشف حساب مستأجر":
            df_tenants = load_tenants()
            if df_tenants.empty:
                st.info("لا يوجد مستأجرين")
            else:
                regions = df_tenants["المنطقة"].dropna().unique().tolist()
                region_filter = st.selectbox("المنطقة", ["الكل"] + regions)
                if region_filter != "الكل":
                    filtered_tenants = df_tenants[df_tenants["المنطقة"] == region_filter]
                else:
                    filtered_tenants = df_tenants
                if filtered_tenants.empty:
                    st.warning("لا يوجد مستأجرين في هذه المنطقة")
                else:
                    tenant_id = st.selectbox("اختر المستأجر", filtered_tenants["الرقم"], format_func=lambda x: filtered_tenants[filtered_tenants["الرقم"]==x]["الاسم"].iloc[0])
                    col_from, col_to = st.columns(2)
                    with col_from:
                        if cal_choice == "هجري":
                            hijri_from = st.text_input("من تاريخ هجري (يوم-شهر-سنة)", "01-01-1445")
                            try:
                                from_date = hijri_to_gregorian(hijri_from)
                            except:
                                st.error("صيغة التاريخ الهجري غير صحيحة")
                                st.stop()
                        else:
                            from_date = st.date_input("من تاريخ", value=date.today().replace(day=1))
                    with col_to:
                        if cal_choice == "هجري":
                            hijri_to = st.text_input("إلى تاريخ هجري (يوم-شهر-سنة)", "30-12-1445")
                            try:
                                to_date = hijri_to_gregorian(hijri_to)
                            except:
                                st.error("صيغة التاريخ الهجري غير صحيحة")
                                st.stop()
                        else:
                            to_date = st.date_input("إلى تاريخ", value=date.today())
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute("SELECT name, region FROM tenants WHERE id = ?", (tenant_id,))
                    tenant_name, tenant_region = cur.fetchone()
                    cur.execute('''SELECT c.contract_number FROM contracts c WHERE c.tenant_id = ? AND c.status='نشط' LIMIT 1''', (tenant_id,))
                    contract_row = cur.fetchone()
                    contract_no = contract_row[0] if contract_row else "لا يوجد"
                    cur.execute('''SELECT id, due_date, amount, paid_amount, (amount - paid_amount) as remaining, status, paid_date, attachment FROM payments WHERE tenant_id = ? AND due_date BETWEEN ? AND ? ORDER BY due_date''', (tenant_id, from_date.isoformat(), to_date.isoformat()))
                    payments = cur.fetchall()
                    cur.execute('''SELECT receipt_number, amount, receipt_date, payment_method, attachment FROM receipts WHERE tenant_id = ? AND receipt_date BETWEEN ? AND ? ORDER BY receipt_date DESC''', (tenant_id, from_date.isoformat(), to_date.isoformat()))
                    receipts = cur.fetchall()
                    conn.close()

                    st.markdown(f"### كشف حساب: {tenant_name}")
                    st.write(f"**المنطقة:** {tenant_region or 'غير محدد'} | **رقم العقد:** {contract_no}")
                    if cal_choice == "هجري":
                        st.write(f"**الفترة:** من {from_date} إلى {to_date} هـ")
                    else:
                        st.write(f"**الفترة:** من {from_date} إلى {to_date} م")

                    if payments:
                        for pay in payments:
                            pay_id, due, amount, paid, remaining, status, paid_date, attachment = pay
                            with st.expander(f"📅 تاريخ الاستحقاق: {due} | المبلغ: {format_currency(amount)} | المدفوع: {format_currency(paid)} | المتبقي: {format_currency(remaining)} | الحالة: {status}"):
                                if paid > 0 and attachment is not None:
                                    st.download_button(label="تحميل مرفق السداد", data=attachment, file_name=f"payment_{pay_id}_attachment.pdf", mime="application/octet-stream")
                                else:
                                    st.write("لا يوجد مرفق لهذه الدفعة.")
                        total_amount = sum(p[2] for p in payments)
                        total_paid = sum(p[3] for p in payments)
                        st.write(f"**إجمالي المستحق:** {format_currency(total_amount)}")
                        st.write(f"**إجمالي المدفوع:** {format_currency(total_paid)}")
                        st.write(f"**المتبقي:** {format_currency(total_amount - total_paid)}")
                    else:
                        st.info("لا توجد دفعات في هذه الفترة")

                    st.markdown("### سندات القبض")
                    if receipts:
                        for rec in receipts:
                            receipt_no, amount, rec_date, method, attachment = rec
                            with st.expander(f"🧾 سند: {receipt_no} | المبلغ: {format_currency(amount)} | التاريخ: {rec_date} | الطريقة: {method}"):
                                if attachment is not None:
                                    st.download_button(label="تحميل المرفق", data=attachment, file_name=f"receipt_{receipt_no}_attachment.pdf", mime="application/octet-stream")
                                else:
                                    st.write("لا يوجد مرفق.")
                    else:
                        st.info("لا توجد سندات في هذه الفترة")

                    if payments:
                        df_payments_export = pd.DataFrame([(p[1], p[2], p[3], p[2]-p[3], p[5], p[6]) for p in payments], columns=["تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة", "تاريخ السداد"])
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            df_payments_export.to_excel(writer, sheet_name='الدفعات', index=False)
                            if receipts:
                                df_receipts_export = pd.DataFrame([(r[0], r[1], r[2], r[3]) for r in receipts], columns=["رقم السند", "المبلغ", "التاريخ", "الطريقة"])
                                df_receipts_export.to_excel(writer, sheet_name='سندات', index=False)
                        st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"كشف_حساب_{tenant_name}_{from_date}_to_{to_date}.xlsx")
                        extra_info = f"المنطقة: {tenant_region or 'غير محدد'} - رقم العقد: {contract_no}"
                        pdf_title = f"كشف حساب {tenant_name} من {from_date} إلى {to_date}"
                        export_df_to_pdf(df_payments_export, pdf_title, f"كشف_حساب_{tenant_name}_{from_date}_to_{to_date}.pdf", extra_info=extra_info)

        elif report_type == "الدفعات المستحقة بين تاريخين":
            st.markdown("### تقرير الدفعات المستحقة بين تاريخين")
            if cal_choice == "هجري":
                col1, col2 = st.columns(2)
                with col1:
                    hijri_from = st.text_input("من تاريخ هجري (يوم-شهر-سنة)", "01-01-1445")
                with col2:
                    hijri_to = st.text_input("إلى تاريخ هجري (يوم-شهر-سنة)", "30-12-1445")
                try:
                    from_date = hijri_to_gregorian(hijri_from)
                    to_date = hijri_to_gregorian(hijri_to)
                except:
                    st.error("صيغة التاريخ الهجري غير صحيحة")
                    st.stop()
            else:
                col1, col2 = st.columns(2)
                with col1:
                    from_date = st.date_input("من تاريخ", value=date.today().replace(day=1))
                with col2:
                    to_date = st.date_input("إلى تاريخ", value=date.today())
            tenant_filter = st.selectbox("اختر مستأجر (اختياري)", ["الكل"] + load_tenants()["الاسم"].tolist())
            region_filter = st.selectbox("المنطقة", ["الكل"] + load_tenants()["المنطقة"].dropna().unique().tolist())

            conn = get_conn()
            cur = conn.cursor()
            query = '''SELECT t.name as 'المستأجر', p.name as 'العقار', pay.due_date as 'تاريخ الاستحقاق', pay.amount as 'المبلغ', pay.paid_amount as 'المدفوع', (pay.amount - pay.paid_amount) as 'المتبقي', pay.status as 'الحالة', t.region as 'المنطقة' FROM payments pay JOIN tenants t ON pay.tenant_id = t.id JOIN contracts c ON pay.contract_id = c.id JOIN properties p ON c.property_id = p.id WHERE pay.due_date BETWEEN ? AND ?'''
            params = [from_date.isoformat(), to_date.isoformat()]
            if tenant_filter != "الكل":
                query += " AND t.name = ?"
                params.append(tenant_filter)
            if region_filter != "الكل":
                query += " AND t.region = ?"
                params.append(region_filter)
            query += " ORDER BY pay.due_date"
            cur.execute(query, params)
            dues = cur.fetchall()
            conn.close()

            if dues:
                df = pd.DataFrame(dues, columns=["المستأجر", "العقار", "تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة", "المنطقة"])
                display_dataframe_with_reorder(df.copy(), "report_due")
                total_amount = sum(d[3] for d in dues)
                total_paid = sum(d[4] for d in dues)
                st.write(f"**إجمالي المستحق:** {format_currency(total_amount)}")
                st.write(f"**إجمالي المدفوع:** {format_currency(total_paid)}")
                st.write(f"**إجمالي المتبقي:** {format_currency(total_amount - total_paid)}")
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"مستحقات_{from_date}_to_{to_date}.xlsx")
                export_df_to_pdf(df, f"مستحقات {from_date} إلى {to_date}", f"مستحقات_{from_date}_to_{to_date}.pdf")
            else:
                st.info("لا توجد مستحقات في هذه الفترة")

        elif report_type == "تقرير الإيرادات":
            st.markdown("### تقرير الإيرادات")
            if cal_choice == "هجري":
                col1, col2 = st.columns(2)
                with col1:
                    hijri_from = st.text_input("من تاريخ هجري (يوم-شهر-سنة)", "01-01-1445")
                with col2:
                    hijri_to = st.text_input("إلى تاريخ هجري (يوم-شهر-سنة)", "30-12-1445")
                try:
                    from_date = hijri_to_gregorian(hijri_from)
                    to_date = hijri_to_gregorian(hijri_to)
                except:
                    st.error("صيغة التاريخ الهجري غير صحيحة")
                    st.stop()
            else:
                col1, col2 = st.columns(2)
                with col1:
                    from_date = st.date_input("من تاريخ", value=date.today().replace(day=1))
                with col2:
                    to_date = st.date_input("إلى تاريخ", value=date.today())
            conn = get_conn()
            query = '''SELECT r.receipt_date as 'التاريخ', t.name as 'المستأجر', r.receipt_number as 'رقم السند', r.amount as 'المبلغ', r.payment_method as 'طريقة السداد' FROM receipts r JOIN tenants t ON r.tenant_id = t.id WHERE r.receipt_date BETWEEN ? AND ? ORDER BY r.receipt_date'''
            df = pd.read_sql_query(query, conn, params=(from_date.isoformat(), to_date.isoformat()))
            conn.close()
            if not df.empty:
                display_dataframe_with_reorder(df.copy(), "report_revenue")
                total = df["المبلغ"].sum()
                st.write(f"**إجمالي الإيرادات:** {format_currency(total)}")
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"إيرادات_{from_date}_to_{to_date}.xlsx")
                export_df_to_pdf(df, "تقرير الإيرادات", f"إيرادات_{from_date}_to_{to_date}.pdf")
            else:
                st.info("لا توجد إيرادات في هذه الفترة")

        elif report_type == "تقرير الضرائب":
            st.markdown("### تقرير الضرائب")
            if cal_choice == "هجري":
                col1, col2 = st.columns(2)
                with col1:
                    hijri_from = st.text_input("من تاريخ هجري (يوم-شهر-سنة)", "01-01-1445")
                with col2:
                    hijri_to = st.text_input("إلى تاريخ هجري (يوم-شهر-سنة)", "30-12-1445")
                try:
                    from_date = hijri_to_gregorian(hijri_from)
                    to_date = hijri_to_gregorian(hijri_to)
                except:
                    st.error("صيغة التاريخ الهجري غير صحيحة")
                    st.stop()
            else:
                col1, col2 = st.columns(2)
                with col1:
                    from_date = st.date_input("من تاريخ", value=date.today().replace(day=1))
                with col2:
                    to_date = st.date_input("إلى تاريخ", value=date.today())
            conn = get_conn()
            query = '''SELECT t.name as 'اسم المستأجر', c.contract_number as 'رقم العقد', c.start_date as 'بداية الفترة', c.end_date as 'نهاية الفترة', pay.amount as 'المبلغ شامل الضريبة', c.tax_included as 'شامل الضريبة', c.tax_rate as 'نسبة الضريبة', r.payment_method as 'طريقة الدفع' FROM payments pay JOIN tenants t ON pay.tenant_id = t.id JOIN contracts c ON pay.contract_id = c.id LEFT JOIN receipts r ON r.payment_id = pay.id WHERE pay.status = 'مدفوع' AND pay.paid_date BETWEEN ? AND ? ORDER BY pay.paid_date'''
            df = pd.read_sql_query(query, conn, params=(from_date.isoformat(), to_date.isoformat()))
            conn.close()
            if not df.empty:
                tax_values = []
                for _, row in df.iterrows():
                    amount = float(row['المبلغ شامل الضريبة'])
                    tax_included = int(row['شامل الضريبة'])
                    tax_rate = float(row['نسبة الضريبة'])
                    if tax_included == 1:
                        if tax_rate > 0:
                            tax = amount * (tax_rate / (1 + tax_rate))
                        else:
                            tax = 0
                    else:
                        tax = amount * tax_rate
                    tax_values.append(tax)
                df['مبلغ الضريبة'] = tax_values
                df['المبلغ غير شامل الضريبة'] = df['المبلغ شامل الضريبة'] - df['مبلغ الضريبة']
                df = df[['اسم المستأجر', 'رقم العقد', 'بداية الفترة', 'نهاية الفترة', 'المبلغ شامل الضريبة', 'نسبة الضريبة', 'مبلغ الضريبة', 'المبلغ غير شامل الضريبة', 'طريقة الدفع']]
                df_display, selected_cols = display_dataframe_with_reorder(df.copy(), "report_tax")
                total_amount = df['المبلغ شامل الضريبة'].sum()
                total_tax = df['مبلغ الضريبة'].sum()
                total_net = df['المبلغ غير شامل الضريبة'].sum()
                st.write(f"**إجمالي المبلغ شامل الضريبة:** {format_currency(total_amount)}")
                st.write(f"**إجمالي مبلغ الضريبة:** {format_currency(total_tax)}")
                st.write(f"**إجمالي المبلغ غير شامل الضريبة:** {format_currency(total_net)}")
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_display.to_excel(writer, index=False)
                st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"ضرائب_{from_date}_to_{to_date}.xlsx")
                export_tax_pdf(df_display, "تقرير الضرائب", f"ضرائب_{from_date}_to_{to_date}.pdf", columns_order=selected_cols)
            else:
                st.info("لا توجد دفعات مدفوعة بالكامل في هذه الفترة")

# ================== المستخدمون ==================
elif menu == "المستخدمون":
    st.subheader("👤 إدارة المستخدمين والصلاحيات")
    if not has_permission(current_user_id, "المستخدمون"):
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        tab1, tab2 = st.tabs(["عرض المستخدمين", "إضافة مستخدم"])
        with tab1:
            df_users = load_users()
            if not df_users.empty:
                st.dataframe(df_users, use_container_width=True)
                user_id = st.selectbox("اختر مستخدم لتعديل صلاحياته", df_users["الرقم"], format_func=lambda x: df_users[df_users["الرقم"]==x]["اسم المستخدم"].iloc[0])
                if user_id:
                    user_perms = load_permissions(user_id)
                    st.markdown("### الصلاحيات")
                    new_perms = {}
                    for page in PAGE_KEYS:
                        new_perms[page] = st.checkbox(page, value=user_perms.get(page, False), key=f"perm_{user_id}_{page}")
                    if st.button("حفظ الصلاحيات"):
                        save_permissions(user_id, new_perms)
                        st.success("تم حفظ الصلاحيات")
                        st.rerun()
                    if st.button("حذف المستخدم"):
                        delete_user(user_id)
                        st.success("تم حذف المستخدم")
                        st.rerun()
                    if current_role == 'مدير':
                        with st.expander("تغيير كلمة المرور"):
                            new_password = st.text_input("كلمة المرور الجديدة", type="password", key=f"new_pass_{user_id}")
                            if st.button("تعيين كلمة المرور", key=f"set_pass_{user_id}"):
                                if new_password.strip():
                                    conn = get_conn()
                                    cur = conn.cursor()
                                    new_hash = hashlib.sha256(new_password.strip().encode()).hexdigest()
                                    cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
                                    conn.commit()
                                    conn.close()
                                    st.success("تم تحديث كلمة المرور")
                                    st.rerun()
                                else:
                                    st.error("كلمة المرور لا يمكن أن تكون فارغة")
            else:
                st.info("لا يوجد مستخدمين")
        with tab2:
            with st.form("add_user_form"):
                username = st.text_input("اسم المستخدم *")
                password = st.text_input("كلمة المرور *", type="password")
                role = st.selectbox("الدور الافتراضي", ["مدير", "محاسب", "مشاهد"])
                submit = st.form_submit_button("إضافة مستخدم")
                if submit:
                    if username.strip() and password.strip():
                        success, message = add_user(username, password, role)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                    else:
                        st.error("يجب إدخال اسم المستخدم وكلمة المرور")

# ================== الإعدادات ==================
elif menu == "الإعدادات":
    st.subheader("⚙️ الإعدادات")
    if not has_permission(current_user_id, "الإعدادات"):
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        with st.form("settings_form"):
            company_name = st.text_input("اسم الشركة / النظام", settings.get('company_name', 'نظام إدارة الإيجارات'))
            primary_color = st.color_picker("اللون الأساسي", settings['primary_color'])
            secondary_color = st.color_picker("اللون الثانوي", settings['secondary_color'])
            background_color = st.color_picker("لون الخلفية", settings['background_color'])
            font_size = st.slider("حجم الخط", min_value=14, max_value=28, value=settings['font_size'])
            logo_file = st.file_uploader("شعار الشركة (PNG/JPEG)", type=["png", "jpg", "jpeg"])
            submit_settings = st.form_submit_button("حفظ الإعدادات")
            if submit_settings:
                save_setting('company_name', company_name)
                save_setting('primary_color', primary_color)
                save_setting('secondary_color', secondary_color)
                save_setting('background_color', background_color)
                save_setting('font_size', font_size)
                if logo_file is not None:
                    logo_bytes = logo_file.read()
                    save_setting('logo', logo_bytes)
                st.success("تم حفظ الإعدادات بنجاح")
                st.rerun()

        st.markdown("---")
        st.subheader("📱 إعداد تيليجرام للنسخ الاحتياطي")
        with st.form("telegram_settings_form"):
            token_input = st.text_input("Bot Token", value=telegram_bot_token, type="password")
            chat_input = st.text_input("Chat ID", value=telegram_chat_id)
            file_id_input = st.text_input("File ID (اختياري، يُحفظ للاستعادة الدائمة)", value=telegram_file_id)
            submit_telegram = st.form_submit_button("حفظ بيانات تيليجرام")
            if submit_telegram:
                save_setting('telegram_bot_token', token_input)
                save_setting('telegram_chat_id', chat_input)
                save_setting('telegram_file_id', file_id_input)
                st.success("تم حفظ بيانات تيليجرام")
                st.rerun()

        st.markdown("---")
        st.subheader("معاينة الألوان")
        st.markdown(f"""
            <div style="background-color:{primary_color}; color:white; padding:20px; border-radius:10px; text-align:center; margin-bottom:10px;">
                اللون الأساسي
            </div>
            <div style="background-color:{secondary_color}; color:white; padding:20px; border-radius:10px; text-align:center; margin-bottom:10px;">
                اللون الثانوي
            </div>
            <div style="background-color:{background_color}; padding:20px; border-radius:10px; text-align:center; border:1px solid #ccc;">
                لون الخلفية
            </div>
        """, unsafe_allow_html=True)

# ================== النسخ الاحتياطي ==================
elif menu == "نسخ احتياطي":
    st.subheader("💾 النسخ الاحتياطي اليدوي")
    if not has_permission(current_user_id, "نسخ احتياطي"):
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### تنزيل نسخة احتياطية")
            try:
                with open("rentals.db", "rb") as f:
                    db_bytes = f.read()
                st.download_button(
                    label="تحميل قاعدة البيانات",
                    data=db_bytes,
                    file_name=f"rentals_backup_{date.today().isoformat()}.db",
                    mime="application/octet-stream"
                )
            except FileNotFoundError:
                st.warning("لا توجد قاعدة بيانات بعد.")
        with col2:
            st.markdown("### استعادة نسخة احتياطية")
            uploaded_file = st.file_uploader("اختر ملف قاعدة البيانات", type=["db", "sqlite"])
            if uploaded_file is not None:
                if st.button("استعادة النسخة المرفوعة"):
                    with open("rentals.db", "wb") as f:
                        f.write(uploaded_file.read())
                    st.cache_data.clear()
                    st.success("تم استعادة النسخة الاحتياطية بنجاح")
                    st.rerun()

        st.markdown("---")
        st.subheader("📱 النسخ الاحتياطي عبر تيليجرام")

        if not telegram_bot_token or not telegram_chat_id:
            st.warning("يرجى إدخال بيانات تيليجرام في صفحة الإعدادات أولاً")
        else:
            if st.button("⬆️ رفع قاعدة البيانات إلى تيليجرام"):
                url = f"https://api.telegram.org/bot{telegram_bot_token}/sendDocument"
                try:
                    with open("rentals.db", "rb") as f:
                        resp = requests.post(url, files={'document': f}, data={'chat_id': telegram_chat_id, 'caption': f"نسخة احتياطية {datetime.now().strftime('%Y-%m-%d %H:%M')}"})
                    if resp.status_code == 200:
                        file_id = resp.json().get('result', {}).get('document', {}).get('file_id')
                        if file_id:
                            save_setting('telegram_file_id', file_id)
                            st.success("تم رفع قاعدة البيانات إلى تيليجرام بنجاح")
                            st.info(f"📎 معرّف الملف (File ID) الحالي: `{file_id}`")
                        else:
                            st.error("فشل استخراج معرّف الملف من الاستجابة")
                    else:
                        st.error(f"فشل الرفع: {resp.text}")
                except Exception as e:
                    st.error(f"حدث خطأ: {str(e)}")

            if st.button("⬇️ استعادة قاعدة البيانات من تيليجرام"):
                if not telegram_file_id:
                    st.error("لا يوجد معرّف ملف محفوظ. يرجى رفع نسخة أولاً أو إدخال المعرّف يدويًا في الإعدادات.")
                else:
                    try:
                        info_url = f"https://api.telegram.org/bot{telegram_bot_token}/getFile?file_id={telegram_file_id}"
                        resp = requests.get(info_url).json()
                        if not resp.get('ok'):
                            st.error("فشل جلب معلومات الملف من تيليجرام")
                        else:
                            file_path = resp['result']['file_path']
                            download_url = f"https://api.telegram.org/file/bot{telegram_bot_token}/{file_path}"
                            db_resp = requests.get(download_url)
                            if db_resp.status_code == 200:
                                with open("rentals.db", "wb") as f:
                                    f.write(db_resp.content)
                                st.cache_data.clear()
                                st.success("تم استعادة قاعدة البيانات من تيليجرام بنجاح")
                                st.rerun()
                            else:
                                st.error("فشل تنزيل الملف")
                    except Exception as e:
                        st.error(f"حدث خطأ: {str(e)}")