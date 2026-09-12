import streamlit as st
import pandas as pd
import sqlite3
import io
import gzip
import shutil
import tempfile
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
import numpy as np

st.set_page_config(page_title="نظام إدارة الإيجارات", page_icon="🏢", layout="wide")

st.markdown("""
<style>
    html, body, [class*="css"] { direction: rtl !important; text-align: right !important; }
    .stApp { direction: rtl !important; }
    .stSidebar { direction: rtl !important; text-align: right !important; }
    .stButton, .stSelectbox, .stTextInput, .stNumberInput, .stDateInput, .stRadio, .stCheckbox {
        direction: rtl !important; text-align: right !important;
    }
    h1, h2, h3, h4, h5, h6 { direction: rtl !important; text-align: right !important; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl !important; }
    input, textarea { direction: rtl !important; text-align: right !important; }
    .stDownloadButton button { direction: rtl !important; }
    .streamlit-expanderHeader { direction: rtl !important; text-align: right !important; }
    .stAlert { direction: rtl !important; text-align: right !important; }
    [data-testid="stMetric"] { direction: rtl !important; text-align: right !important; }
    [data-testid="stDataFrame"] { direction: ltr !important; }
    [data-testid="stDataFrame"] [role="columnheader"] { text-align: center !important; }
</style>
""", unsafe_allow_html=True)

def safe_float(value, default=0.0):
    try:
        if value is None or pd.isna(value): return default
        return float(value)
    except (TypeError, ValueError): return default

def format_currency(value):
    val = safe_float(value, 0.0)
    if val == int(val): return f"{int(val):,}"
    return f"{val:,.2f}"

def rtl_dataframe(df, key=None, **kwargs):
    df_display = df.copy()
    numeric_cols = df_display.select_dtypes(include=[np.number]).columns.tolist()
    date_cols = [c for c in df_display.columns if 'تاريخ' in c or 'date' in c.lower() or 'بداية' in c or 'نهاية' in c or 'استحقاق' in c]
    number_like = [c for c in df_display.columns if any(kw in c for kw in ['المبلغ','المدفوع','المتبقي','الضريبة','إيجار','التأمين','الرقم','نسبة'])]
    ltr_cols = list(set(numeric_cols + date_cols + number_like))
    rtl_cols = [c for c in df_display.columns if c not in ltr_cols]
    styled = df_display.style
    if ltr_cols: styled = styled.set_properties(subset=ltr_cols, **{'text-align':'left','direction':'ltr'})
    if rtl_cols: styled = styled.set_properties(subset=rtl_cols, **{'text-align':'right','direction':'rtl'})
    st.dataframe(styled, use_container_width=True, key=key, **kwargs)

def display_dataframe_with_reorder(df, key_prefix):
    columns = list(df.columns)
    default = st.session_state.get(f"{key_prefix}_order", columns)
    selected = st.multiselect("اختر الأعمدة وترتيبها", options=columns, default=default, key=f"{key_prefix}_cols")
    if selected:
        df = df[selected]
        st.session_state[f"{key_prefix}_order"] = selected
    rtl_dataframe(df, key=f"{key_prefix}_rtl")
    return df, selected

def download_arabic_font():
    fp = "Amiri-Regular.ttf"
    if not os.path.exists(fp):
        try:
            r = requests.get("https://github.com/aliftype/amiri/raw/main/fonts/Amiri-Regular.ttf", timeout=10)
            if r.status_code == 200:
                with open(fp, "wb") as f: f.write(r.content)
            else: return None
        except: return None
    return fp

def setup_arabic_font():
    fp = download_arabic_font()
    if fp and os.path.exists(fp):
        pdfmetrics.registerFont(TTFont('Amiri', fp))
        return 'Amiri'
    return 'Helvetica'

def reshape_arabic_text(text):
    return get_display(arabic_reshaper.reshape(str(text)))

def parse_currency(v): return safe_float(v, 0.0)

def parse_date_safe(v, default=None):
    if not v: return default or date.today()
    if isinstance(v, date): return v
    try: return datetime.strptime(str(v), '%Y-%m-%d').date()
    except:
        try: return datetime.fromisoformat(str(v)).date()
        except: return default or date.today()

def wrap_text_for_pdf(text, max_chars_per_line):
    s = str(text)
    if len(s) <= max_chars_per_line: return [s]
    lines = []
    remaining = s
    while len(remaining) > max_chars_per_line:
        chunk = remaining[:max_chars_per_line]
        space_idx = chunk.rfind(' ')
        if space_idx > max_chars_per_line // 3:
            lines.append(remaining[:space_idx].strip())
            remaining = remaining[space_idx:].strip()
        else:
            lines.append(chunk)
            remaining = remaining[max_chars_per_line:]
    if remaining: lines.append(remaining)
    return lines

def export_df_to_pdf(df, title, file_name, columns_order=None, extra_info=None, landscape_mode=False):
    if columns_order: df = df[columns_order]
    else: df = df.copy()
    df_num = df.copy()
    for c in df_num.columns:
        try: df_num[c] = df_num[c].apply(parse_currency)
        except: pass
    buf = io.BytesIO()
    pagesize = landscape(A4) if landscape_mode else A4
    c = canvas.Canvas(buf, pagesize=pagesize)
    w, h = pagesize
    fn = setup_arabic_font()
    c.setFont(fn, 10)
    c.setFillColor(colors.HexColor("#4A90E2"))
    c.rect(0, h-30, w, 30, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont(fn, 16)
    c.drawCentredString(w/2, h-20, reshape_arabic_text(title))
    y_extra = h - 50
    if extra_info:
        c.setFillColor(colors.black); c.setFont(fn, 12)
        c.drawCentredString(w/2, y_extra, reshape_arabic_text(extra_info))
        y_extra -= 20
    cols = list(df.columns); headers = ["م"] + cols
    widths = []
    for idx, col in enumerate(headers):
        if col == "م": widths.append(30); continue
        max_len = len(reshape_arabic_text(str(col)))
        for v in df[col].tolist():
            s = format_currency(v) if isinstance(v, (int, float)) and not pd.isna(v) else (str(v) if not pd.isna(v) else "")
            max_len = max(max_len, len(reshape_arabic_text(s)))
        if col in ['المبلغ','المدفوع','المتبقي','المبلغ شامل الضريبة','مبلغ الضريبة','المبلغ غير شامل الضريبة','الإيجار السنوي']: widths.append(85)
        elif col in ['تاريخ الاستحقاق','تاريخ السداد','بداية الفترة','نهاية الفترة']: widths.append(95)
        elif col in ['المستأجر','اسم المستأجر']: widths.append(140)
        elif col in ['العقار','اسم العقار']: widths.append(120)
        elif col in ['المنطقة']: widths.append(80)
        elif col in ['الحالة']: widths.append(65)
        elif col in ['رقم السند','رقم العقد']: widths.append(90)
        elif col in ['طريقة الدفع','طريقة السداد']: widths.append(85)
        else: widths.append(min(max(max_len * 6 + 15, 65), 130))
    tw = sum(widths); max_w = w - 40
    if tw > max_w:
        sf = max_w / tw; widths = [x * sf for x in widths]; tw = max_w
    xs = (w - tw) / 2
    if xs < 20: xs = 20
    y = y_extra - 20 if extra_info else h - 60
    c.setFont(fn, 8); c.setFillColor(colors.HexColor("#f0f0f0"))
    c.rect(xs, y-15, tw, 25, fill=1, stroke=0)
    c.setFillColor(colors.black)
    xc = xs + tw
    for i, hd in enumerate(headers):
        cw = widths[i]; xr = xc; xl = xc - cw
        c.drawCentredString((xl+xr)/2, y-3, reshape_arabic_text(hd)); xc -= cw
    y -= 30; sn = 1; line_height = 11
    for _, row in df.iterrows():
        row_lines = []
        for col in cols:
            v = row[col]
            vs = format_currency(v) if isinstance(v, (int, float)) and not pd.isna(v) else (str(v) if not pd.isna(v) else "")
            col_idx = cols.index(col) + 1
            cw = widths[col_idx]
            if col in ['تاريخ الاستحقاق','تاريخ السداد','بداية الفترة','نهاية الفترة']:
                max_chars = 20
            else:
                max_chars = max(int(cw / 7), 5)
            lines = wrap_text_for_pdf(vs, max_chars)
            row_lines.append(lines)
        max_lines = max((len(lines) for lines in row_lines), default=1)
        row_height = max_lines * line_height + 6
        if y - row_height < 40:
            c.showPage(); c.setFont(fn, 8); y = h - 50
            c.setFillColor(colors.HexColor("#f0f0f0")); c.rect(xs, y-15, tw, 25, fill=1, stroke=0)
            c.setFillColor(colors.black); xc = xs + tw
            for i, hd in enumerate(headers):
                cw = widths[i]; xr = xc; xl = xc - cw
                c.drawCentredString((xl+xr)/2, y-3, reshape_arabic_text(hd)); xc -= cw
            y -= 30
        c.setFillColor(colors.white); c.rect(xs, y - row_height + 5, tw, row_height, fill=1, stroke=0)
        c.setFillColor(colors.black)
        cw = widths[0]; xr = xs + tw; xl = xr - cw
        center_y = y - (row_height / 2) + 3
        c.drawCentredString((xl+xr)/2, center_y, str(sn)); sn += 1; xc = xr - cw
        for i, col in enumerate(cols, 1):
            cw = widths[i]; xr = xc; xl = xc - cw
            lines = row_lines[i-1]; start_y = y - 3
            for li, line in enumerate(lines):
                c.drawRightString(xr - 5, start_y - li * line_height, reshape_arabic_text(line))
            xc -= cw
        c.setStrokeColor(colors.grey); c.setLineWidth(0.5)
        c.line(xs, y+5, xs+tw, y+5); c.line(xs, y - row_height + 5, xs+tw, y - row_height + 5)
        xc = xs + tw
        for i in range(len(headers)): c.line(xc, y+5, xc, y - row_height + 5); xc -= widths[i]
        c.line(xs, y+5, xs, y - row_height + 5)
        y -= row_height
    c.line(xs, y+5, xs+tw, y+5); y -= 5
    c.setFillColor(colors.HexColor("#e8f0fe")); c.rect(xs, y-15, tw, 22, fill=1, stroke=0); c.setFillColor(colors.black)
    cw = widths[0]; xr = xs + tw; xl = xr - cw
    c.drawCentredString((xl+xr)/2, y-7, reshape_arabic_text("الإجمالي")); xc = xr - cw
    for i, col in enumerate(cols, 1):
        cw = widths[i]; xr = xc; xl = xc - cw
        try:
            total_val = df_num[col].sum()
            c.drawRightString(xr-5, y-7, format_currency(total_val))
        except: pass
        xc -= cw
    c.save(); buf.seek(0)
    orientation_label = "أفقي" if landscape_mode else "عمودي"
    st.download_button(f"تحميل PDF ({orientation_label})", data=buf, file_name=file_name, mime="application/pdf")

def export_tax_pdf(df, title, file_name, columns_order=None, landscape_mode=True):
    if columns_order: df = df[columns_order]
    else: df = df.copy()
    df_num = df.copy()
    for c in ['المبلغ شامل الضريبة','مبلغ الضريبة','المبلغ غير شامل الضريبة']:
        if c in df_num.columns: df_num[c] = df_num[c].apply(parse_currency)
    buf = io.BytesIO()
    pagesize = landscape(A4) if landscape_mode else A4
    c = canvas.Canvas(buf, pagesize=pagesize)
    w, h = pagesize
    fn = setup_arabic_font()
    c.setFont(fn, 10); c.setFillColor(colors.HexColor("#4A90E2"))
    c.rect(0, h-30, w, 30, fill=1, stroke=0); c.setFillColor(colors.white)
    c.setFont(fn, 16); c.drawCentredString(w/2, h-20, reshape_arabic_text(title))
    cols = list(df.columns); headers = ["م"] + cols
    widths = []
    for col in headers:
        if col == "م": widths.append(25)
        elif col in ['المبلغ شامل الضريبة','مبلغ الضريبة','المبلغ غير شامل الضريبة']: widths.append(90)
        elif col == 'نسبة الضريبة': widths.append(60)
        elif col in ['بداية الفترة','نهاية الفترة']: widths.append(95)
        elif col in ['اسم المستأجر','المستأجر']: widths.append(140)
        elif col in ['رقم العقد']: widths.append(90)
        elif col == 'طريقة الدفع': widths.append(85)
        else: widths.append(max(len(reshape_arabic_text(col))*5, 75))
    tw = sum(widths); max_w = w - 40
    if tw > max_w:
        sf = max_w / tw; widths = [x*sf for x in widths]; tw = max_w
    xs = (w - tw) / 2
    if xs < 20: xs = 20
    y = h - 60
    c.setFont(fn, 7); c.setFillColor(colors.HexColor("#f0f0f0"))
    c.rect(xs, y-18, tw, 28, fill=1, stroke=0); c.setFillColor(colors.black)
    xc = xs + tw
    for i, hd in enumerate(headers):
        cw = widths[i]; xr = xc; xl = xc - cw; xm = (xl+xr)/2
        c.drawCentredString(xm, y-3, reshape_arabic_text(hd)); xc -= cw
    y -= 30; c.setFont(fn, 8); sn = 1; line_height = 10
    for _, row in df.iterrows():
        row_lines = []
        for col in cols:
            v = row[col]
            vs = format_currency(v) if isinstance(v, (int, float)) and not pd.isna(v) else (str(v) if not pd.isna(v) else "")
            col_idx = cols.index(col) + 1
            cw = widths[col_idx]
            if col in ['بداية الفترة','نهاية الفترة']: max_chars = 20
            else: max_chars = max(int(cw / 6.5), 5)
            row_lines.append(wrap_text_for_pdf(vs, max_chars))
        max_lines = max((len(l) for l in row_lines), default=1)
        row_height = max_lines * line_height + 5
        if y - row_height < 40:
            c.showPage(); c.setFont(fn, 7); y = h - 50
            c.setFillColor(colors.HexColor("#f0f0f0")); c.rect(xs, y-18, tw, 28, fill=1, stroke=0)
            c.setFillColor(colors.black); xc = xs + tw
            for i, hd in enumerate(headers):
                cw = widths[i]; xr = xc; xl = xc - cw; xm = (xl+xr)/2
                c.drawCentredString(xm, y-3, reshape_arabic_text(hd)); xc -= cw
            y -= 30; c.setFont(fn, 8)
        c.setFillColor(colors.white); c.rect(xs, y - row_height + 5, tw, row_height, fill=1, stroke=0); c.setFillColor(colors.black)
        cw = widths[0]; xr = xs + tw; xl = xr - cw
        c.drawCentredString((xl+xr)/2, y - row_height/2 + 2, str(sn)); sn += 1; xc = xr - cw
        for i, col in enumerate(cols, 1):
            cw = widths[i]; xr = xc; xl = xc - cw
            for li, line in enumerate(row_lines[i-1]):
                c.drawRightString(xr-4, y - 3 - li*line_height, reshape_arabic_text(line))
            xc -= cw
        c.setStrokeColor(colors.grey); c.setLineWidth(0.5)
        c.line(xs, y+5, xs+tw, y+5); c.line(xs, y-row_height+5, xs+tw, y-row_height+5)
        xc = xs + tw
        for i in range(len(headers)): c.line(xc, y+5, xc, y-row_height+5); xc -= widths[i]
        c.line(xs, y+5, xs, y-row_height+5)
        y -= row_height
    c.save(); buf.seek(0)
    orientation_label = "أفقي" if landscape_mode else "عمودي"
    st.download_button(f"تحميل PDF ({orientation_label})", data=buf, file_name=file_name, mime="application/pdf")

def print_receipt(receipt_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute('''SELECT r.receipt_number, t.name, r.amount, r.receipt_date, r.payment_method, r.notes
                   FROM receipts r JOIN tenants t ON r.tenant_id = t.id WHERE r.id = ?''', (receipt_id,))
    r = cur.fetchone(); conn.close()
    if not r: return None
    rn, tn, amt, rd, mt, nt = r
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4; fn = setup_arabic_font()
    c.setFont(fn, 12); c.setFillColor(colors.HexColor("#4A90E2"))
    c.rect(0, h-40, w, 40, fill=1, stroke=0); c.setFillColor(colors.white)
    c.setFont(fn, 18); c.drawCentredString(w/2, h-25, reshape_arabic_text("سند قبض"))
    c.setFont(fn, 12); c.setFillColor(colors.black); y = h - 80
    for lbl, val in [("رقم السند:", rn),("اسم المستأجر:", tn),("المبلغ:", format_currency(amt)),
                     ("تاريخ السداد:", rd),("طريقة الدفع:", mt),("ملاحظات:", nt or "لا يوجد")]:
        c.drawRightString(w-100, y, reshape_arabic_text(f"{lbl} {val}")); y -= 25
    c.save(); buf.seek(0)
    return buf.getvalue()

def get_conn():
    conn = sqlite3.connect("rentals.db", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;"); conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def ensure_columns(cur, table, cols):
    cur.execute(f"PRAGMA table_info({table})")
    ex = [c[1] for c in cur.fetchall()]
    for cn in cols:
        if cn not in ex:
            if cn in ('interval_months','tax_included','is_temporary'):
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {cn} INTEGER DEFAULT 0")
            elif cn == 'tax_rate':
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {cn} REAL DEFAULT 0.15")
            elif cn in ('attachment','contract_file','permissions','temporary_note'):
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {cn} TEXT")
            else:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {cn} TEXT")

@st.cache_resource
def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cur.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
                   password_hash TEXT, role TEXT DEFAULT 'مشاهد', permissions TEXT DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    ensure_columns(cur, 'users', ['permissions'])
    cur.execute('''CREATE TABLE IF NOT EXISTS tenants (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                   phone TEXT, national_id TEXT, address TEXT, region TEXT, notes TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS properties (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                   description TEXT, address TEXT, region TEXT, area TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS contracts (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, property_id INTEGER,
                   contract_number TEXT UNIQUE, start_date TEXT, end_date TEXT, rent_amount REAL, interval_months INTEGER DEFAULT 1,
                   deposit_amount REAL, notes TEXT, status TEXT DEFAULT 'نشط', tax_included INTEGER DEFAULT 0, tax_rate REAL DEFAULT 0.15, contract_file BLOB)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER, tenant_id INTEGER,
                   due_date TEXT, amount REAL, paid_amount REAL DEFAULT 0, paid_date TEXT, status TEXT DEFAULT 'مستحق', notes TEXT, attachment BLOB)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS receipts (id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_number TEXT, tenant_id INTEGER,
                   contract_id INTEGER, payment_id INTEGER, amount REAL, receipt_date TEXT, payment_method TEXT, notes TEXT, attachment BLOB)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, alert_text TEXT,
                   alert_date TEXT, is_read INTEGER DEFAULT 0)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS contract_pricing_tiers (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER,
                   start_date TEXT, end_date TEXT, annual_rent REAL, notes TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS additional_fees (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER, fee_name TEXT, amount REAL,
                   frequency TEXT DEFAULT 'مرة واحدة', tax_included INTEGER DEFAULT 0, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS contract_discounts (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER, discount_type TEXT DEFAULT 'نسبة',
                   discount_value REAL, start_date TEXT, end_date TEXT, reason TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    ensure_columns(cur, 'payments', ['due_date','paid_date','attachment','is_temporary','temporary_note'])
    ensure_columns(cur, 'contracts', ['interval_months','tax_included','tax_rate','contract_file','is_temporary'])
    ensure_columns(cur, 'receipts', ['attachment'])
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (username, password_hash, role, permissions) VALUES (?, 