import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import time
from hijri_converter import convert
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import requests
import os
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import base64
import hashlib

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

def export_df_to_pdf(df, title, file_name, columns_order=None):
    if columns_order:
        df = df[columns_order]
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = setup_arabic_font()
    c.setFont(font_name, 10)
    c.setFont(font_name, 16)
    c.drawRightString(width - 50, height - 50, reshape_arabic_text(title))
    c.setFont(font_name, 8)
    x_start = width - 50
    y = height - 80
    col_widths = [max(len(reshape_arabic_text(col)) * 4, 80) for col in df.columns]
    total_width = sum(col_widths)
    c.line(x_start - total_width, y, x_start, y)
    y -= 15
    for i, col in enumerate(df.columns):
        x = x_start - sum(col_widths[:i+1])
        c.drawRightString(x, y, reshape_arabic_text(col))
    y -= 15
    for _, row in df.iterrows():
        if y < 50:
            c.showPage()
            c.setFont(font_name, 8)
            y = height - 50
        for i, value in enumerate(row):
            x = x_start - sum(col_widths[:i+1])
            c.drawRightString(x, y, reshape_arabic_text(value))
        y -= 15
    c.save()
    buffer.seek(0)
    st.download_button("تحميل PDF", data=buffer, file_name=file_name, mime="application/pdf")

# ---------- إدارة قاعدة البيانات ----------
def get_conn():
    conn = sqlite3.connect("rentals.db", timeout=10)
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
            elif col_name in ('attachment', 'contract_file'):
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} BLOB")
            else:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} TEXT")

@st.cache_resource
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # جدول الإعدادات
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # جدول المستخدمين
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            role TEXT DEFAULT 'مشاهد',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            national_id TEXT,
            address TEXT,
            region TEXT,
            notes TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            address TEXT,
            region TEXT,
            area TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            property_id INTEGER,
            contract_number TEXT,
            start_date TEXT,
            end_date TEXT,
            rent_amount REAL,
            interval_months INTEGER DEFAULT 1,
            deposit_amount REAL,
            notes TEXT,
            status TEXT DEFAULT 'نشط',
            tax_included INTEGER DEFAULT 0,
            tax_rate REAL DEFAULT 0.15,
            contract_file BLOB,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (property_id) REFERENCES properties(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER,
            tenant_id INTEGER,
            due_date TEXT,
            amount REAL,
            paid_amount REAL DEFAULT 0,
            paid_date TEXT,
            status TEXT DEFAULT 'مستحق',
            notes TEXT,
            attachment BLOB,
            FOREIGN KEY (contract_id) REFERENCES contracts(id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_number TEXT,
            tenant_id INTEGER,
            contract_id INTEGER,
            payment_id INTEGER,
            amount REAL,
            receipt_date TEXT,
            payment_method TEXT,
            notes TEXT,
            attachment BLOB,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (contract_id) REFERENCES contracts(id),
            FOREIGN KEY (payment_id) REFERENCES payments(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            note_text TEXT,
            note_date TEXT,
            priority TEXT DEFAULT 'عادية',
            is_alert INTEGER DEFAULT 0,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            alert_text TEXT,
            alert_date TEXT,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
    ''')

    ensure_columns(cur, 'payments', ['due_date', 'paid_date', 'attachment'])
    ensure_columns(cur, 'contracts', ['interval_months', 'tax_included', 'tax_rate', 'contract_file'])
    ensure_columns(cur, 'receipts', ['attachment'])

    # إنشاء فهارس
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments(due_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contracts_tenant ON contracts(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(receipt_date)")

    # إضافة مستخدم افتراضي إذا لم يوجد أي مستخدم
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ('admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'مدير'))

    conn.commit()
    conn.close()

init_db()

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
        'font_size': 16,
        'primary_color': '#1e3a8a',
        'secondary_color': '#f97316',
        'background_color': '#f8fafc',
        'logo': None,
        'company_name': 'نظام إدارة الإيجارات'
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
    cur.execute('''
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    ''', (key, value_str))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def load_logo_data():
    settings = load_settings()
    logo_b64 = settings.get('logo', None)
    if logo_b64:
        return base64.b64decode(logo_b64)
    return None

# ---------- تحميل الإعدادات ----------
settings = load_settings()
font_size = settings['font_size']
primary_color = settings['primary_color']
secondary_color = settings['secondary_color']
background_color = settings['background_color']
logo_data = load_logo_data()

# ---------- تطبيق CSS مخصص ----------
st.markdown(f"""
<style>
    html, body, [class*="css"] {{
        direction: RTL;
        text-align: right;
        font-size: {font_size}px;
    }}
    .stApp {{
        background-color: {background_color};
    }}
    .stSidebar {{
        background-color: {primary_color};
        color: white;
    }}
    .stSidebar [data-testid="stMarkdown"] {{
        color: white;
    }}
    .stSidebar .stRadio label, .stSidebar .stSelectbox label {{
        color: white !important;
    }}
    .stButton>button {{
        background-color: {secondary_color};
        color: white;
        border-radius: 8px;
        border: none;
        padding: 8px 16px;
        font-weight: bold;
    }}
    .stButton>button:hover {{
        background-color: {primary_color};
        color: white;
    }}
    h1, h2, h3, h4 {{
        color: {primary_color};
    }}
    .stMetric {{
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        text-align: center;
    }}
    .stDataFrame, .stTable {{
        background-color: white;
        border-radius: 10px;
        padding: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }}
    .stApp header {{
        background-color: {primary_color};
        color: white;
    }}
</style>
""", unsafe_allow_html=True)

# ---------- عرض الشعار والتحكم في الخط ----------
if logo_data:
    st.sidebar.image(logo_data, width=150)
else:
    st.sidebar.markdown("🏢 **نظام الإدارة**")

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

# ---------- إدارة تسجيل الدخول والمستخدمين ----------
# الحصول على قائمة المستخدمين
conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT id, username, role FROM users")
users = cur.fetchall()
conn.close()

if users:
    user_options = {u[1]: u[0] for u in users}
    selected_user = st.sidebar.selectbox("المستخدم الحالي", list(user_options.keys()))
    current_user_id = user_options[selected_user]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = ?", (current_user_id,))
    current_role = cur.fetchone()[0]
    conn.close()
    st.sidebar.markdown(f"**الدور:** {current_role}")
else:
    current_role = "مدير"  # افتراضي
    current_user_id = None

# القائمة الرئيسية
menu = st.sidebar.radio(
    "القائمة الرئيسية",
    ["لوحة التحكم", "المستأجرين", "العقارات", "العقود", "الدفعات", "صفحة السداد", "التقارير", "المستخدمون", "الإعدادات", "نسخ احتياطي"]
)

# ---------- دوال مساعدة عامة ----------
def add_note(tenant_id, note_text, priority='عادية', is_alert=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO notes (tenant_id, note_text, note_date, priority, is_alert)
        VALUES (?, ?, ?, ?, ?)
    ''', (tenant_id, note_text, date.today().isoformat(), priority, is_alert))
    if is_alert:
        cur.execute('''
            INSERT INTO alerts (tenant_id, alert_text, alert_date)
            VALUES (?, ?, ?)
        ''', (tenant_id, note_text, date.today().isoformat()))
    conn.commit()
    conn.close()
    st.cache_data.clear()

def generate_receipt_number():
    return f"RCP-{int(time.time())}"

def create_payment_schedule(contract_id, tenant_id, start_date, end_date, rent_amount, interval_months):
    step = relativedelta(months=interval_months)
    current = start_date
    conn = get_conn()
    cur = conn.cursor()
    while current <= end_date:
        cur.execute('''
            INSERT INTO payments (contract_id, tenant_id, due_date, amount)
            VALUES (?, ?, ?, ?)
        ''', (contract_id, tenant_id, current.isoformat(), rent_amount))
        current += step
    conn.commit()
    conn.close()

def get_unread_alerts(tenant_id=None):
    conn = get_conn()
    cur = conn.cursor()
    if tenant_id:
        cur.execute('''
            SELECT alert_text, alert_date FROM alerts
            WHERE tenant_id = ? AND is_read = 0
            ORDER BY alert_date DESC
        ''', (tenant_id,))
    else:
        cur.execute('''
            SELECT a.alert_text, a.alert_date, t.name
            FROM alerts a JOIN tenants t ON a.tenant_id = t.id
            WHERE a.is_read = 0 ORDER BY a.alert_date DESC
        ''')
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
    selected_cols = st.multiselect(
        "اختر الأعمدة وترتيبها",
        options=columns,
        default=default,
        key=f"{key_prefix}_cols"
    )
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
               CASE WHEN EXISTS (
                   SELECT 1 FROM contracts c 
                   WHERE c.tenant_id = t.id AND c.status='نشط' AND c.end_date >= date('now')
               ) THEN 'ساري' ELSE 'غير ساري' END as "حالة العقد"
        FROM tenants t
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
        'rent_amount': 'قيمة الإيجار',
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
    # تحويل عمود 'ملف العقد' إلى حالة وجود ملف (نعم/لا)
    if 'ملف العقد' in df.columns:
        df['ملف العقد'] = df['ملف العقد'].apply(lambda x: 'نعم' if x is not None and len(x) > 0 else 'لا')
    else:
        df['ملف العقد'] = 'لا'
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_payments(status_filter='الكل'):
    conn = get_conn()
    query = '''
        SELECT pay.id as 'الرقم', t.name as 'المستأجر', p.name as 'العقار', 
               pay.due_date as 'تاريخ الاستحقاق', pay.amount as 'المبلغ',
               pay.paid_amount as 'المدفوع', (pay.amount - pay.paid_amount) as 'المتبقي',
               pay.status as 'الحالة', pay.paid_date as 'تاريخ السداد', pay.attachment as 'المرفق'
        FROM payments pay
        JOIN tenants t ON pay.tenant_id = t.id
        JOIN contracts c ON pay.contract_id = c.id
        JOIN properties p ON c.property_id = p.id
    '''
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
    query = '''
        SELECT r.receipt_number as 'رقم السند', t.name as 'المستأجر', r.amount as 'المبلغ',
               r.receipt_date as 'التاريخ', r.payment_method as 'طريقة السداد'
        FROM receipts r
        JOIN tenants t ON r.tenant_id = t.id
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# ---------- وظيفة استيراد Excel للمستأجرين ----------
def import_tenants_from_excel(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file)
        if "الاسم" not in df.columns:
            st.error("يجب أن يحتوي الملف على عمود 'الاسم'")
            return
        conn = get_conn()
        cur = conn.cursor()
        for _, row in df.iterrows():
            name = str(row.get("الاسم", "")).strip()
            if not name:
                continue
            phone = str(row.get("الهاتف", "")).strip() if "الهاتف" in df.columns else ""
            national_id = str(row.get("رقم الهوية / الإقامة", "")).strip() if "رقم الهوية / الإقامة" in df.columns else ""
            address = str(row.get("العنوان", "")).strip() if "العنوان" in df.columns else ""
            region = str(row.get("المنطقة", "")).strip() if "المنطقة" in df.columns else ""
            notes = str(row.get("ملاحظات", "")).strip() if "ملاحظات" in df.columns else ""
            cur.execute('''
                INSERT INTO tenants (name, phone, national_id, address, region, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, phone, national_id, address, region, notes))
        conn.commit()
        conn.close()
        st.cache_data.clear()
        st.success(f"تم استيراد {len(df)} مستأجر بنجاح")
    except Exception as e:
        st.error(f"حدث خطأ أثناء الاستيراد: {str(e)}")

# ---------- إدارة المستخدمين ----------
def add_user(username, password, role):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
    if cur.fetchone()[0] > 0:
        conn.close()
        return False, "اسم المستخدم موجود مسبقاً"
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    cur.execute('''
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
    ''', (username, password_hash, role))
    conn.commit()
    conn.close()
    return True, "تم إضافة المستخدم بنجاح"

def update_user_role(user_id, new_role):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
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

# ================== لوحة التحكم ==================
if menu == "لوحة التحكم":
    st.subheader("📊 لوحة التحكم")

    df_tenants = load_tenants()
    df_contracts = load_contracts()
    df_payments = load_payments()

    # إضافة مقاييس العقود المنتهية والقريبة من الانتهاء
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
        st.metric("إجمالي المحصل", f"{total_collected:,.2f}")

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

# ================== المستأجرين ==================
elif menu == "المستأجرين":
    st.subheader("👥 إدارة المستأجرين")
    tab1, tab2, tab3 = st.tabs(["عرض الكل", "إضافة / تعديل مستأجر", "استيراد من Excel"])

    with tab1:
        df_tenants = load_tenants()
        if not df_tenants.empty:
            # إضافة خانة بحث
            search_term = st.text_input("بحث في المستأجرين (الاسم، الهاتف، رقم الهوية)", key="search_tenants")
            if search_term:
                mask = df_tenants.apply(lambda row: search_term.lower() in str(row["الاسم"]).lower() or
                                       search_term.lower() in str(row["الهاتف"]).lower() or
                                       search_term.lower() in str(row["رقم الهوية / الإقامة"]).lower(), axis=1)
                filtered_tenants = df_tenants[mask]
            else:
                filtered_tenants = df_tenants
            
            if not filtered_tenants.empty:
                display_dataframe_with_reorder(filtered_tenants, "tenants_filtered")
                tenant_dict = dict(zip(filtered_tenants["الاسم"], filtered_tenants["الرقم"]))
                selected_name = st.selectbox("اختر مستأجر لعرض التفاصيل", list(tenant_dict.keys()))
                tenant_id = tenant_dict[selected_name]

                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
                tenant = cur.fetchone()

                st.markdown("### بيانات المستأجر")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**الاسم:** {tenant[1]}")
                    st.write(f"**الهاتف:** {tenant[2] or 'غير محدد'}")
                    st.write(f"**رقم الهوية / الإقامة:** {tenant[3] or 'غير محدد'}")
                    st.write(f"**العنوان:** {tenant[4] or 'غير محدد'}")
                    st.write(f"**المنطقة:** {tenant[5] or 'غير محدد'}")
                with col2:
                    st.write(f"**ملاحظات:** {tenant[6] or 'لا يوجد'}")
                    # حالة العقد من الجدول
                    tenant_status = df_tenants[df_tenants['الرقم']==tenant_id]['حالة العقد'].iloc[0] if tenant_id in df_tenants['الرقم'].values else 'غير متاح'
                    st.write(f"**حالة العقد:** {tenant_status}")

                # عرض عقود المستأجر
                st.markdown("### عقود المستأجر")
                cur.execute('''
                    SELECT c.id, c.contract_number, p.name, c.start_date, c.end_date, c.status
                    FROM contracts c
                    JOIN properties p ON c.property_id = p.id
                    WHERE c.tenant_id = ?
                    ORDER BY c.start_date DESC
                ''', (tenant_id,))
                tenant_contracts = cur.fetchall()
                if tenant_contracts:
                    df_tenant_contracts = pd.DataFrame(tenant_contracts, columns=["رقم العقد", "اسم العقار", "تاريخ البداية", "تاريخ النهاية", "الحالة"])
                    st.dataframe(df_tenant_contracts, use_container_width=True)
                else:
                    st.info("لا توجد عقود لهذا المستأجر")

                # أزرار تعديل وحذف حسب الدور
                if current_role == "مدير":
                    col_edit, col_del = st.columns(2)
                    with col_edit:
                        if st.button("تعديل بيانات المستأجر", key="edit_tenant_btn"):
                            st.session_state['edit_tenant_id'] = tenant_id
                            st.rerun()
                    with col_del:
                        if st.button("حذف المستأجر", key="delete_tenant_btn"):
                            if st.session_state.get('confirm_delete_tenant') == tenant_id:
                                conn = get_conn()
                                cur = conn.cursor()
                                cur.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
                                conn.commit()
                                conn.close()
                                st.cache_data.clear()
                                st.success("تم حذف المستأجر")
                                st.session_state['confirm_delete_tenant'] = None
                                st.rerun()
                            else:
                                st.session_state['confirm_delete_tenant'] = tenant_id
                                st.warning("اضغط مرة أخرى لتأكيد الحذف")
                elif current_role == "محاسب":
                    col_edit, _ = st.columns(2)
                    with col_edit:
                        if st.button("تعديل بيانات المستأجر", key="edit_tenant_btn"):
                            st.session_state['edit_tenant_id'] = tenant_id
                            st.rerun()
                    st.info("لا تملك صلاحية الحذف")
                else:  # مشاهد
                    st.info("صلاحيتك للعرض فقط")

                # تنبيهات
                alerts = get_unread_alerts(tenant_id)
                if alerts:
                    st.warning("⚠️ تنبيهات غير مقروءة:")
                    for a in alerts:
                        st.write(f"- {a[0]} (تاريخ: {a[1]})")
                    if st.button("تحديد كمقروء"):
                        mark_alerts_read(tenant_id)
                        st.rerun()

                # ملاحظات
                st.markdown("**الملاحظات:**")
                cur.execute("SELECT note_date, note_text, priority, is_alert FROM notes WHERE tenant_id = ? ORDER BY note_date DESC", (tenant_id,))
                notes = cur.fetchall()
                if notes:
                    for n in notes:
                        icon = "⚠️" if n[3] else ""
                        st.write(f"- [{n[0]}] ({n[2]}) {n[1]} {icon}")
                else:
                    st.write("لا توجد ملاحظات.")

                # إضافة ملاحظة
                if current_role in ["مدير", "محاسب"]:
                    with st.form("add_note_form"):
                        note_text = st.text_area("ملاحظة جديدة")
                        priority = st.selectbox("الأهمية", ["عادية", "متوسطة", "عالية"])
                        is_alert = st.checkbox("تنبيه")
                        if st.form_submit_button("إضافة ملاحظة"):
                            if note_text.strip():
                                add_note(tenant_id, note_text.strip(), priority, 1 if is_alert else 0)
                                st.success("تمت إضافة الملاحظة")
                                st.rerun()
                conn.close()
            else:
                st.info("لا توجد نتائج مطابقة للبحث")
        else:
            st.info("لا يوجد مستأجرين بعد")

    with tab2:
        if current_role == "مشاهد":
            st.warning("لا تملك صلاحية الإضافة أو التعديل")
        else:
            if 'edit_tenant_id' in st.session_state and st.session_state['edit_tenant_id']:
                tenant_id = st.session_state['edit_tenant_id']
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT name, phone, national_id, address, region, notes FROM tenants WHERE id = ?", (tenant_id,))
                tenant_data = cur.fetchone()
                conn.close()
                st.markdown("### تعديل بيانات المستأجر")
                with st.form("edit_tenant_form", clear_on_submit=True):
                    name = st.text_input("الاسم *", value=tenant_data[0])
                    phone = st.text_input("الهاتف", value=tenant_data[1])
                    national_id = st.text_input("رقم الهوية / الإقامة", value=tenant_data[2])
                    address = st.text_input("العنوان", value=tenant_data[3])
                    region = st.text_input("المنطقة", value=tenant_data[4])
                    notes = st.text_area("ملاحظات", value=tenant_data[5])
                    submit = st.form_submit_button("حفظ التعديلات")
                    if submit:
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute('''
                            UPDATE tenants SET name=?, phone=?, national_id=?, address=?, region=?, notes=?
                            WHERE id=?
                        ''', (name, phone, national_id, address, region, notes, tenant_id))
                        conn.commit()
                        conn.close()
                        st.cache_data.clear()
                        st.success("تم تحديث بيانات المستأجر")
                        st.session_state['edit_tenant_id'] = None
                        st.rerun()
            else:
                with st.form("add_tenant_form", clear_on_submit=True):
                    name = st.text_input("الاسم *")
                    phone = st.text_input("الهاتف")
                    national_id = st.text_input("رقم الهوية / الإقامة")
                    address = st.text_input("العنوان")
                    region = st.text_input("المنطقة")
                    notes = st.text_area("ملاحظات")
                    submit = st.form_submit_button("حفظ")
                    if submit:
                        if name.strip():
                            conn = get_conn()
                            cur = conn.cursor()
                            cur.execute('''
                                INSERT INTO tenants (name, phone, national_id, address, region, notes)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (name, phone, national_id, address, region, notes))
                            conn.commit()
                            conn.close()
                            st.cache_data.clear()
                            st.success("تمت إضافة المستأجر")
                            st.rerun()
                        else:
                            st.error("الاسم مطلوب")

    with tab3:
        if current_role == "مشاهد":
            st.warning("لا تملك صلاحية الاستيراد")
        else:
            st.markdown("### استيراد المستأجرين من ملف Excel")
            st.info("يجب أن يحتوي الملف على الأعمدة التالية: الاسم (إجباري)، الهاتف، رقم الهوية / الإقامة، العنوان، المنطقة، ملاحظات")
            uploaded_file = st.file_uploader("اختر ملف Excel", type=["xlsx", "xls"])
            if uploaded_file is not None:
                if st.button("بدء الاستيراد"):
                    import_tenants_from_excel(uploaded_file)

# ================== العقارات ==================
elif menu == "العقارات":
    st.subheader("🏬 إدارة العقارات")
    tab1, tab2 = st.tabs(["عرض الكل", "إضافة عقار"])

    with tab1:
        df_props = load_properties()
        if not df_props.empty:
            search_prop = st.text_input("بحث في العقارات (الاسم، المنطقة)", key="search_props")
            if search_prop:
                mask = df_props.apply(lambda row: search_prop.lower() in str(row["الاسم"]).lower() or
                                     search_prop.lower() in str(row["المنطقة"]).lower(), axis=1)
                filtered_props = df_props[mask]
            else:
                filtered_props = df_props
            if not filtered_props.empty:
                display_dataframe_with_reorder(filtered_props, "properties_filtered")
                if current_role == "مدير":
                    prop_id = st.selectbox("اختر عقار", filtered_props["الرقم"], format_func=lambda x: filtered_props[filtered_props["الرقم"]==x]["الاسم"].iloc[0])
                    col_edit, col_del = st.columns(2)
                    with col_edit:
                        if st.button("تعديل العقار", key="edit_prop_btn"):
                            st.session_state['edit_property_id'] = prop_id
                            st.rerun()
                    with col_del:
                        if st.button("حذف العقار", key="delete_prop_btn"):
                            if st.session_state.get('confirm_delete_property') == prop_id:
                                conn = get_conn()
                                cur = conn.cursor()
                                cur.execute("DELETE FROM properties WHERE id = ?", (prop_id,))
                                conn.commit()
                                conn.close()
                                st.cache_data.clear()
                                st.success("تم حذف العقار")
                                st.session_state['confirm_delete_property'] = None
                                st.rerun()
                            else:
                                st.session_state['confirm_delete_property'] = prop_id
                                st.warning("اضغط مرة أخرى لتأكيد الحذف")
                elif current_role == "محاسب":
                    prop_id = st.selectbox("اختر عقار للتعديل", filtered_props["الرقم"], format_func=lambda x: filtered_props[filtered_props["الرقم"]==x]["الاسم"].iloc[0])
                    if st.button("تعديل العقار", key="edit_prop_btn"):
                        st.session_state['edit_property_id'] = prop_id
                        st.rerun()
                else:
                    st.info("صلاحيتك للعرض فقط")
            else:
                st.info("لا توجد نتائج مطابقة للبحث")
        else:
            st.info("لا توجد عقارات")

    with tab2:
        if current_role == "مشاهد":
            st.warning("لا تملك صلاحية الإضافة أو التعديل")
        else:
            if 'edit_property_id' in st.session_state and st.session_state['edit_property_id']:
                prop_id = st.session_state['edit_property_id']
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT name, description, address, region, area FROM properties WHERE id = ?", (prop_id,))
                prop_data = cur.fetchone()
                conn.close()
                st.markdown("### تعديل عقار")
                with st.form("edit_property_form", clear_on_submit=True):
                    name = st.text_input("اسم العقار *", value=prop_data[0])
                    description = st.text_area("الوصف", value=prop_data[1])
                    address = st.text_input("العنوان", value=prop_data[2])
                    region = st.text_input("المنطقة", value=prop_data[3])
                    area = st.text_input("المساحة", value=prop_data[4])
                    submit = st.form_submit_button("حفظ التعديلات")
                    if submit:
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute('''
                            UPDATE properties SET name=?, description=?, address=?, region=?, area=?
                            WHERE id=?
                        ''', (name, description, address, region, area, prop_id))
                        conn.commit()
                        conn.close()
                        st.cache_data.clear()
                        st.success("تم تحديث العقار")
                        st.session_state['edit_property_id'] = None
                        st.rerun()
            else:
                with st.form("add_property_form", clear_on_submit=True):
                    name = st.text_input("اسم العقار *")
                    description = st.text_area("الوصف")
                    address = st.text_input("العنوان")
                    region = st.text_input("المنطقة")
                    area = st.text_input("المساحة")
                    submit = st.form_submit_button("حفظ")
                    if submit:
                        if name.strip():
                            conn = get_conn()
                            cur = conn.cursor()
                            cur.execute('''
                                INSERT INTO properties (name, description, address, region, area)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (name, description, address, region, area))
                            conn.commit()
                            conn.close()
                            st.cache_data.clear()
                            st.success("تمت إضافة العقار")
                            st.rerun()
                        else:
                            st.error("الاسم مطلوب")

# ================== العقود ==================
elif menu == "العقود":
    st.subheader("📄 إدارة العقود")
    tab1, tab2 = st.tabs(["عرض الكل", "إنشاء / تعديل عقد"])

    with tab1:
        df_contracts = load_contracts()
        if not df_contracts.empty:
            search_contract = st.text_input("بحث في العقود (رقم العقد، المستأجر، العقار)", key="search_contracts")
            if search_contract:
                mask = df_contracts.apply(lambda row: search_contract.lower() in str(row["رقم العقد"]).lower() or
                                         search_contract.lower() in str(row["اسم المستأجر"]).lower() or
                                         search_contract.lower() in str(row["اسم العقار"]).lower(), axis=1)
                filtered_contracts = df_contracts[mask]
            else:
                filtered_contracts = df_contracts
            if not filtered_contracts.empty:
                display_dataframe_with_reorder(filtered_contracts, "contracts_filtered")
                if current_role == "مدير":
                    contract_id = st.selectbox("اختر عقد", filtered_contracts["الرقم"], format_func=lambda x: f"عقد رقم {x}")
                    col_edit, col_del = st.columns(2)
                    with col_edit:
                        if st.button("تعديل العقد", key="edit_contract_btn"):
                            st.session_state['edit_contract_id'] = contract_id
                            st.rerun()
                    with col_del:
                        if st.button("حذف العقد", key="delete_contract_btn"):
                            if st.session_state.get('confirm_delete_contract') == contract_id:
                                conn = get_conn()
                                cur = conn.cursor()
                                cur.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
                                conn.commit()
                                conn.close()
                                st.cache_data.clear()
                                st.success("تم حذف العقد")
                                st.session_state['confirm_delete_contract'] = None
                                st.rerun()
                            else:
                                st.session_state['confirm_delete_contract'] = contract_id
                                st.warning("اضغط مرة أخرى لتأكيد الحذف")
                    # عرض زر تحميل الملف إذا وجد
                    cur = get_conn().cursor()
                    cur.execute("SELECT contract_file FROM contracts WHERE id = ?", (contract_id,))
                    file_data = cur.fetchone()
                    if file_data and file_data[0]:
                        if st.download_button("تحميل ملف العقد", data=file_data[0], file_name=f"contract_{contract_id}.pdf", mime="application/octet-stream"):
                            pass
                elif current_role == "محاسب":
                    contract_id = st.selectbox("اختر عقد للتعديل", filtered_contracts["الرقم"], format_func=lambda x: f"عقد رقم {x}")
                    if st.button("تعديل العقد", key="edit_contract_btn"):
                        st.session_state['edit_contract_id'] = contract_id
                        st.rerun()
                    # عرض زر تحميل الملف
                    cur = get_conn().cursor()
                    cur.execute("SELECT contract_file FROM contracts WHERE id = ?", (contract_id,))
                    file_data = cur.fetchone()
                    if file_data and file_data[0]:
                        st.download_button("تحميل ملف العقد", data=file_data[0], file_name=f"contract_{contract_id}.pdf", mime="application/octet-stream")
                else:
                    st.info("صلاحيتك للعرض فقط")
            else:
                st.info("لا توجد نتائج مطابقة للبحث")
        else:
            st.info("لا توجد عقود")

    with tab2:
        if current_role == "مشاهد":
            st.warning("لا تملك صلاحية الإضافة أو التعديل")
        else:
            df_tenants = load_tenants()
            df_props = load_properties()
            if df_tenants.empty or df_props.empty:
                st.warning("يجب إضافة مستأجر وعقار أولاً")
            else:
                if 'edit_contract_id' in st.session_state and st.session_state['edit_contract_id']:
                    contract_id = st.session_state['edit_contract_id']
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute('''
                        SELECT tenant_id, property_id, contract_number, start_date, end_date,
                               rent_amount, interval_months, deposit_amount, tax_included, tax_rate, notes
                        FROM contracts WHERE id = ?
                    ''', (contract_id,))
                    contract_data = cur.fetchone()
                    conn.close()
                    st.markdown("### تعديل العقد")
                    with st.form("edit_contract_form", clear_on_submit=True):
                        tenant_id = st.selectbox("المستأجر", df_tenants["الرقم"],
                                                 index=df_tenants.index[df_tenants["الرقم"] == contract_data[0]][0],
                                                 format_func=lambda x: df_tenants[df_tenants["الرقم"]==x]["الاسم"].iloc[0])
                        property_id = st.selectbox("العقار", df_props["الرقم"],
                                                   index=df_props.index[df_props["الرقم"] == contract_data[1]][0],
                                                   format_func=lambda x: df_props[df_props["الرقم"]==x]["الاسم"].iloc[0])
                        contract_number = st.text_input("رقم العقد", value=contract_data[2])
                        start_date = st.date_input("تاريخ البداية", value=date.fromisoformat(contract_data[3]))
                        end_date = st.date_input("تاريخ النهاية", value=date.fromisoformat(contract_data[4]))
                        rent_amount = st.number_input("قيمة الإيجار", min_value=0.0, step=100.0, value=float(contract_data[5]))
                        interval_months = st.number_input("دورية السداد (عدد الشهور)", min_value=1, value=int(contract_data[6]))
                        deposit_amount = st.number_input("التأمين", min_value=0.0, step=100.0, value=float(contract_data[7]))
                        tax_included = st.checkbox("المبلغ شامل الضريبة", value=bool(contract_data[8]))
                        tax_rate = st.number_input("نسبة الضريبة (%)", min_value=0.0, value=float(contract_data[9])*100, step=1.0) / 100
                        notes = st.text_area("ملاحظات", value=contract_data[10])
                        submit = st.form_submit_button("حفظ التعديلات")
                        if submit:
                            conn = get_conn()
                            cur = conn.cursor()
                            cur.execute('''
                                UPDATE contracts SET tenant_id=?, property_id=?, contract_number=?, start_date=?, end_date=?,
                                       rent_amount=?, interval_months=?, deposit_amount=?, tax_included=?, tax_rate=?, notes=?
                                WHERE id=?
                            ''', (tenant_id, property_id, contract_number, start_date.isoformat(), end_date.isoformat(),
                                  rent_amount, interval_months, deposit_amount, 1 if tax_included else 0, tax_rate, notes, contract_id))
                            conn.commit()
                            conn.close()
                            st.cache_data.clear()
                            st.success("تم تحديث العقد")
                            st.session_state['edit_contract_id'] = None
                            st.rerun()
                else:
                    with st.form("add_contract_form", clear_on_submit=True):
                        tenant_id = st.selectbox("المستأجر", df_tenants["الرقم"], format_func=lambda x: df_tenants[df_tenants["الرقم"]==x]["الاسم"].iloc[0])
                        property_id = st.selectbox("العقار", df_props["الرقم"], format_func=lambda x: df_props[df_props["الرقم"]==x]["الاسم"].iloc[0])
                        contract_number = st.text_input("رقم العقد")
                        start_date = st.date_input("تاريخ البداية")
                        end_date = st.date_input("تاريخ النهاية", value=start_date + relativedelta(years=1))
                        rent_amount = st.number_input("قيمة الإيجار", min_value=0.0, step=100.0)
                        interval_months = st.number_input("دورية السداد (عدد الشهور)", min_value=1, value=1)
                        deposit_amount = st.number_input("التأمين", min_value=0.0, step=100.0)
                        tax_included = st.checkbox("المبلغ شامل الضريبة")
                        tax_rate = st.number_input("نسبة الضريبة (%)", min_value=0.0, value=15.0, step=1.0) / 100
                        notes = st.text_area("ملاحظات")
                        contract_file = st.file_uploader("مرفق العقد (PDF/صورة)", type=["pdf", "png", "jpg", "jpeg"])
                        submit = st.form_submit_button("حفظ وإنشاء الدفعات")
                        if submit:
                            if start_date >= end_date:
                                st.error("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
                            else:
                                file_bytes = None
                                if contract_file is not None:
                                    file_bytes = contract_file.read()
                                conn = get_conn()
                                cur = conn.cursor()
                                cur.execute('''
                                    INSERT INTO contracts (tenant_id, property_id, contract_number, start_date, end_date,
                                                           rent_amount, interval_months, deposit_amount, notes,
                                                           tax_included, tax_rate, contract_file)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (tenant_id, property_id, contract_number, start_date.isoformat(), end_date.isoformat(),
                                      rent_amount, interval_months, deposit_amount, notes,
                                      1 if tax_included else 0, tax_rate, file_bytes))
                                contract_id = cur.lastrowid
                                conn.commit()
                                conn.close()
                                create_payment_schedule(contract_id, tenant_id, start_date, end_date, rent_amount, interval_months)
                                st.cache_data.clear()
                                st.success("تم إنشاء العقد وجدولة الدفعات")
                                st.rerun()

# ================== الدفعات ==================
elif menu == "الدفعات":
    st.subheader("💰 متابعة الدفعات")
    tab1, tab2 = st.tabs(["الدفعات المستحقة", "تسجيل دفعة"])

    with tab1:
        status_filter = st.selectbox("فلتر الحالة", ["الكل", "مستحق", "مدفوع", "متأخر", "جزئي"])
        df_payments = load_payments(status_filter)
        if not df_payments.empty:
            display_dataframe_with_reorder(df_payments.drop(columns=["المرفق"]), "payments")
            if current_role in ["مدير", "محاسب"]:
                payment_id = st.selectbox("اختر دفعة لتسجيل سداد", df_payments["الرقم"].tolist())
                if payment_id:
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute("SELECT amount, paid_amount, tenant_id, contract_id FROM payments WHERE id = ?", (payment_id,))
                    pay = cur.fetchone()
                    remaining = pay[0] - pay[1]
                    with st.form("pay_form"):
                        amount_paid = st.number_input("المبلغ المدفوع", min_value=0.0, max_value=remaining, step=100.0)
                        pay_date = st.date_input("تاريخ السداد")
                        method = st.selectbox("طريقة السداد", ["نقدي", "تحويل بنكي", "شيك"])
                        attachment = st.file_uploader("مرفق السداد (PDF/صورة)", type=["pdf", "png", "jpg", "jpeg"])
                        if st.form_submit_button("تسجيل"):
                            new_paid = pay[1] + amount_paid
                            status = "مدفوع" if new_paid >= pay[0] else "جزئي" if new_paid > 0 else "مستحق"
                            file_bytes = None
                            if attachment is not None:
                                file_bytes = attachment.read()
                            cur.execute(
                                "UPDATE payments SET paid_amount = ?, paid_date = ?, status = ?, attachment = ? WHERE id = ?",
                                (new_paid, pay_date.isoformat(), status, file_bytes, payment_id)
                            )
                            receipt_number = generate_receipt_number()
                            cur.execute('''
                                INSERT INTO receipts (receipt_number, tenant_id, contract_id, payment_id, amount, receipt_date, payment_method, attachment)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (receipt_number, pay[2], pay[3], payment_id, amount_paid, pay_date.isoformat(), method, file_bytes))
                            conn.commit()
                            conn.close()
                            st.cache_data.clear()
                            st.success("تم تسجيل السداد")
                            st.rerun()
            else:
                st.info("صلاحيتك للعرض فقط")
        else:
            st.info("لا توجد دفعات مطابقة")

    with tab2:
        if current_role in ["مدير", "محاسب"]:
            st.info("استخدم تبويب 'الدفعات المستحقة' لاختيار دفعة وتسجيل سداد.")
        else:
            st.info("لا تملك صلاحية تسجيل الدفعات")

# ================== صفحة السداد ==================
elif menu == "صفحة السداد":
    st.subheader("💳 صفحة السداد السريع")
    if current_role in ["مدير", "محاسب"]:
        df_tenants = load_tenants()
        if df_tenants.empty:
            st.warning("لا يوجد مستأجرين")
        else:
            with st.form("quick_payment_form"):
                tenant_id = st.selectbox("اختر المستأجر", df_tenants["الرقم"], format_func=lambda x: df_tenants[df_tenants["الرقم"]==x]["الاسم"].iloc[0])
                payment_amount = st.number_input("المبلغ الكلي للسداد", min_value=0.0, step=100.0)
                payment_date = st.date_input("تاريخ السداد")
                method = st.selectbox("طريقة السداد", ["نقدي", "تحويل بنكي", "شيك"])
                attachment = st.file_uploader("مرفق السداد (PDF/صورة)", type=["pdf", "png", "jpg", "jpeg"])
                submit = st.form_submit_button("تسجيل السداد")

                if submit and payment_amount > 0:
                    file_bytes = None
                    if attachment is not None:
                        file_bytes = attachment.read()
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute('''
                        SELECT id, amount, paid_amount, contract_id
                        FROM payments
                        WHERE tenant_id = ? AND status != 'مدفوع'
                        ORDER BY due_date ASC
                    ''', (tenant_id,))
                    unpaid_payments = cur.fetchall()
                    remaining_amount = payment_amount
                    receipt_date = payment_date.isoformat()
                    receipt_number = generate_receipt_number()
                    cur.execute('''
                        INSERT INTO receipts (receipt_number, tenant_id, amount, receipt_date, payment_method, attachment)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (receipt_number, tenant_id, payment_amount, receipt_date, method, file_bytes))
                    for pay in unpaid_payments:
                        if remaining_amount <= 0:
                            break
                        pay_id, pay_amount, pay_paid, contract_id = pay
                        due = pay_amount - pay_paid
                        if due <= 0:
                            continue
                        pay_amount_to_apply = min(due, remaining_amount)
                        new_paid = pay_paid + pay_amount_to_apply
                        status = "مدفوع" if new_paid >= pay_amount else "جزئي"
                        cur.execute('''
                            UPDATE payments SET paid_amount = ?, paid_date = ?, status = ?, attachment = ?
                            WHERE id = ?
                        ''', (new_paid, receipt_date, status, file_bytes, pay_id))
                        remaining_amount -= pay_amount_to_apply
                    conn.commit()
                    conn.close()
                    st.cache_data.clear()
                    st.success(f"تم تسجيل سداد بمبلغ {payment_amount:,.2f} للمستأجر")
                    st.rerun()
    else:
        st.warning("لا تملك صلاحية تسجيل السداد")

# ================== التقارير ==================
elif menu == "التقارير":
    st.subheader("📈 التقارير")
    report_type = st.radio("اختر التقرير", [
        "كشف حساب مستأجر",
        "الدفعات المستحقة بين تاريخين",
        "تقرير المناطق",
        "تقرير الإيرادات",
        "تقرير الضرائب"
    ])
    cal_choice = st.radio("نوع التاريخ", ["ميلادي", "هجري"], horizontal=True)

    if report_type == "كشف حساب مستأجر":
        df_tenants = load_tenants()
        if df_tenants.empty:
            st.info("لا يوجد مستأجرين")
        else:
            tenant_id = st.selectbox("اختر المستأجر", df_tenants["الرقم"], format_func=lambda x: df_tenants[df_tenants["الرقم"]==x]["الاسم"].iloc[0])
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT name FROM tenants WHERE id = ?", (tenant_id,))
            tenant_name = cur.fetchone()[0]
            cur.execute('''
                SELECT id, due_date, amount, paid_amount, (amount - paid_amount) as remaining, status, paid_date, attachment
                FROM payments WHERE tenant_id = ? ORDER BY due_date
            ''', (tenant_id,))
            payments = cur.fetchall()
            cur.execute('''
                SELECT receipt_number, amount, receipt_date, payment_method, attachment
                FROM receipts WHERE tenant_id = ? ORDER BY receipt_date DESC
            ''', (tenant_id,))
            receipts = cur.fetchall()
            conn.close()

            st.markdown(f"### كشف حساب: {tenant_name}")
            if cal_choice == "هجري":
                st.write(f"التاريخ: {gregorian_to_hijri(date.today())} هـ")
            else:
                st.write(f"التاريخ: {date.today().isoformat()} م")

            if payments:
                for pay in payments:
                    pay_id, due, amount, paid, remaining, status, paid_date, attachment = pay
                    with st.expander(f"📅 تاريخ الاستحقاق: {due} | المبلغ: {amount:,.2f} | المدفوع: {paid:,.2f} | المتبقي: {remaining:,.2f} | الحالة: {status}"):
                        if paid > 0 and attachment is not None:
                            st.download_button(
                                label="تحميل مرفق السداد",
                                data=attachment,
                                file_name=f"payment_{pay_id}_attachment.pdf",
                                mime="application/octet-stream"
                            )
                        else:
                            st.write("لا يوجد مرفق لهذه الدفعة.")
                total_amount = sum(p[2] for p in payments)
                total_paid = sum(p[3] for p in payments)
                st.write(f"**إجمالي المستحق:** {total_amount:,.2f}")
                st.write(f"**إجمالي المدفوع:** {total_paid:,.2f}")
                st.write(f"**المتبقي:** {total_amount - total_paid:,.2f}")
            else:
                st.info("لا توجد دفعات")

            st.markdown("### سندات القبض")
            if receipts:
                for rec in receipts:
                    receipt_no, amount, rec_date, method, attachment = rec
                    with st.expander(f"🧾 سند: {receipt_no} | المبلغ: {amount:,.2f} | التاريخ: {rec_date} | الطريقة: {method}"):
                        if attachment is not None:
                            st.download_button(
                                label="تحميل المرفق",
                                data=attachment,
                                file_name=f"receipt_{receipt_no}_attachment.pdf",
                                mime="application/octet-stream"
                            )
                        else:
                            st.write("لا يوجد مرفق.")
            else:
                st.info("لا توجد سندات")

            # تصدير Excel و PDF
            if payments:
                df_payments = pd.DataFrame([(p[1], p[2], p[3], p[2]-p[3], p[5], p[6]) for p in payments],
                                           columns=["تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة", "تاريخ السداد"])
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_payments.to_excel(writer, sheet_name='الدفعات', index=False)
                    if receipts:
                        df_receipts = pd.DataFrame([(r[0], r[1], r[2], r[3]) for r in receipts],
                                                   columns=["رقم السند", "المبلغ", "التاريخ", "الطريقة"])
                        df_receipts.to_excel(writer, sheet_name='سندات', index=False)
                st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"كشف_حساب_{tenant_name}.xlsx")
                export_df_to_pdf(df_payments, f"كشف حساب {tenant_name}", f"كشف_حساب_{tenant_name}.pdf")

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

        conn = get_conn()
        cur = conn.cursor()
        query = '''
            SELECT t.name as 'المستأجر', p.name as 'العقار', pay.due_date as 'تاريخ الاستحقاق', 
                   pay.amount as 'المبلغ', pay.paid_amount as 'المدفوع',
                   (pay.amount - pay.paid_amount) as 'المتبقي', pay.status as 'الحالة'
            FROM payments pay
            JOIN tenants t ON pay.tenant_id = t.id
            JOIN contracts c ON pay.contract_id = c.id
            JOIN properties p ON c.property_id = p.id
            WHERE pay.due_date BETWEEN ? AND ?
        '''
        params = [from_date.isoformat(), to_date.isoformat()]
        if tenant_filter != "الكل":
            query += " AND t.name = ?"
            params.append(tenant_filter)
        query += " ORDER BY pay.due_date"
        cur.execute(query, params)
        dues = cur.fetchall()
        conn.close()

        if dues:
            df = pd.DataFrame(dues, columns=["المستأجر", "العقار", "تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة"])
            display_dataframe_with_reorder(df, "report_due")
            total_amount = sum(d[3] for d in dues)
            total_paid = sum(d[4] for d in dues)
            st.write(f"**إجمالي المستحق:** {total_amount:,.2f}")
            st.write(f"**إجمالي المدفوع:** {total_paid:,.2f}")
            st.write(f"**إجمالي المتبقي:** {total_amount - total_paid:,.2f}")

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"مستحقات_{from_date}_to_{to_date}.xlsx")
            export_df_to_pdf(df, f"مستحقات {from_date} إلى {to_date}", f"مستحقات_{from_date}_to_{to_date}.pdf")
        else:
            st.info("لا توجد مستحقات في هذه الفترة")

    elif report_type == "تقرير المناطق":
        st.markdown("### تقرير حسب المناطق")
        region_filter = st.text_input("فلتر منطقة (اتركه فارغ للكل)")
        query = '''
            SELECT COALESCE(t.region, 'غير محدد') as 'المنطقة',
                   COUNT(DISTINCT t.id) as 'عدد المستأجرين',
                   COUNT(DISTINCT c.id) as 'عدد العقود',
                   COALESCE(SUM(pay.amount), 0) as 'إجمالي المستحق',
                   COALESCE(SUM(pay.paid_amount), 0) as 'إجمالي المدفوع',
                   COALESCE(SUM(pay.amount - pay.paid_amount), 0) as 'المتبقي'
            FROM tenants t
            LEFT JOIN contracts c ON t.id = c.tenant_id
            LEFT JOIN properties p ON c.property_id = p.id
            LEFT JOIN payments pay ON c.id = pay.contract_id
        '''
        if region_filter:
            query += " WHERE t.region = ?"
            params = (region_filter,)
        else:
            params = ()
        query += " GROUP BY COALESCE(t.region, 'غير محدد') ORDER BY 'المنطقة'"
        conn = get_conn()
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        if not df.empty:
            df["نسبة التحصيل"] = (df["إجمالي المدفوع"] / df["إجمالي المستحق"] * 100).fillna(0).round(1).astype(str) + "%"
            display_dataframe_with_reorder(df, "report_regions")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("تحميل Excel", data=output.getvalue(), file_name="تقرير_المناطق.xlsx")
            export_df_to_pdf(df, "تقرير المناطق", "تقرير_المناطق.pdf")
        else:
            st.info("لا توجد بيانات")

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
        query = '''
            SELECT r.receipt_date as 'التاريخ', t.name as 'المستأجر', r.receipt_number as 'رقم السند',
                   r.amount as 'المبلغ', r.payment_method as 'طريقة السداد'
            FROM receipts r
            JOIN tenants t ON r.tenant_id = t.id
            WHERE r.receipt_date BETWEEN ? AND ?
            ORDER BY r.receipt_date
        '''
        df = pd.read_sql_query(query, conn, params=(from_date.isoformat(), to_date.isoformat()))
        conn.close()
        if not df.empty:
            display_dataframe_with_reorder(df, "report_revenue")
            total = df["المبلغ"].sum()
            st.write(f"**إجمالي الإيرادات:** {total:,.2f}")
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
        query = '''
            SELECT r.receipt_date as 'التاريخ', t.name as 'المستأجر', r.receipt_number as 'رقم السند',
                   r.amount as 'المبلغ', c.tax_included as 'شامل الضريبة', c.tax_rate as 'نسبة الضريبة'
            FROM receipts r
            JOIN tenants t ON r.tenant_id = t.id
            LEFT JOIN contracts c ON r.contract_id = c.id
            WHERE r.receipt_date BETWEEN ? AND ?
            ORDER BY r.receipt_date
        '''
        df = pd.read_sql_query(query, conn, params=(from_date.isoformat(), to_date.isoformat()))
        conn.close()
        if not df.empty:
            tax_values = []
            for _, row in df.iterrows():
                try:
                    amount_val = float(row['المبلغ'] or 0)
                    tax_included_val = int(row['شامل الضريبة'] or 0)
                    tax_rate_val = float(row['نسبة الضريبة'] or 0)
                except (ValueError, TypeError):
                    tax_values.append(0)
                    continue
                if tax_included_val == 1:
                    if tax_rate_val > 0:
                        tax = amount_val * (tax_rate_val / (1 + tax_rate_val))
                    else:
                        tax = 0
                else:
                    tax = amount_val * tax_rate_val
                tax_values.append(tax)
            df['الضريبة'] = tax_values
            df['صافي المبلغ'] = df['المبلغ'] - df['الضريبة']
            display_dataframe_with_reorder(df, "report_tax")
            total_tax = df['الضريبة'].sum()
            st.write(f"**إجمالي الضريبة:** {total_tax:,.2f}")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"ضرائب_{from_date}_to_{to_date}.xlsx")
            export_df_to_pdf(df, "تقرير الضرائب", f"ضرائب_{from_date}_to_{to_date}.pdf")
        else:
            st.info("لا توجد سندات في هذه الفترة")

# ================== المستخدمون ==================
elif menu == "المستخدمون":
    st.subheader("👤 إدارة المستخدمين والصلاحيات")
    if current_role != "مدير":
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        tab1, tab2 = st.tabs(["عرض المستخدمين", "إضافة مستخدم"])

        with tab1:
            df_users = load_users()
            if not df_users.empty:
                st.dataframe(df_users, use_container_width=True)
                user_id = st.selectbox("اختر مستخدم لتعديل دوره", df_users["الرقم"], format_func=lambda x: df_users[df_users["الرقم"]==x]["اسم المستخدم"].iloc[0])
                if user_id:
                    current_role_user = df_users[df_users["الرقم"]==user_id]["الدور"].iloc[0]
                    new_role = st.selectbox("الدور الجديد", ["مدير", "محاسب", "مشاهد"], index=["مدير", "محاسب", "مشاهد"].index(current_role_user))
                    if st.button("تحديث الدور"):
                        update_user_role(user_id, new_role)
                        st.success("تم تحديث الدور بنجاح")
                        st.rerun()
                    # حذف مستخدم (لا يمكن حذف آخر مدير)
                    if current_role_user == "مدير" and len(df_users[df_users["الدور"]=="مدير"]) <= 1:
                        st.warning("لا يمكن حذف آخر مدير")
                    else:
                        if st.button("حذف المستخدم"):
                            delete_user(user_id)
                            st.success("تم حذف المستخدم")
                            st.rerun()
            else:
                st.info("لا يوجد مستخدمين")

        with tab2:
            with st.form("add_user_form"):
                username = st.text_input("اسم المستخدم *")
                password = st.text_input("كلمة المرور *", type="password")
                role = st.selectbox("الدور", ["مدير", "محاسب", "مشاهد"])
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
    if current_role != "مدير":
        st.error("لا تملك صلاحية الوصول لهذه الصفحة")
    else:
        with st.form("settings_form"):
            company_name = st.text_input("اسم الشركة / النظام", settings.get('company_name', 'نظام إدارة الإيجارات'))
            primary_color = st.color_picker("اللون الأساسي", settings['primary_color'])
            secondary_color = st.color_picker("اللون الثانوي", settings['secondary_color'])
            background_color = st.color_picker("لون الخلفية", settings['background_color'])
            font_size = st.slider("حجم الخط", min_value=10, max_value=24, value=settings['font_size'])
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