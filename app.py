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

# ---------- إعداد الصفحة ----------
st.set_page_config(page_title="نظام إدارة الإيجارات", page_icon="🏢", layout="wide")
st.title("🏢 نظام إدارة الإيجارات")

# ---------- إدارة قاعدة البيانات ----------
def get_conn():
    """فتح اتصال جديد بقاعدة البيانات"""
    conn = sqlite3.connect("rentals.db", timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def ensure_columns(cur, table_name, required_columns):
    """
    فحص الأعمدة المفقودة في جدول وإضافتها تلقائيًا.
    required_columns: قائمة من الأعمدة المطلوبة (اسم العمود فقط).
    """
    cur.execute(f"PRAGMA table_info({table_name})")
    existing_columns = [col[1] for col in cur.fetchall()]
    for col_name in required_columns:
        if col_name not in existing_columns:
            # تحديد نوع البيانات بناءً على اسم العمود
            if col_name in ('interval_months', 'tax_included'):
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} INTEGER DEFAULT 0")
            elif col_name == 'tax_rate':
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} REAL DEFAULT 0.15")
            else:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} TEXT")

@st.cache_resource
def init_db():
    """إنشاء الجداول والفهارس مع ترحيل آمن للأعمدة الناقصة"""
    conn = get_conn()
    cur = conn.cursor()

    # إنشاء الجداول
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

    # ✅ ترحيل: إضافة الأعمدة المفقودة في جدول payments
    ensure_columns(cur, 'payments', ['due_date', 'paid_date'])

    # ✅ ترحيل: إضافة الأعمدة المفقودة في جدول contracts
    ensure_columns(cur, 'contracts', ['interval_months', 'tax_included', 'tax_rate'])

    # إنشاء الفهارس
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_due_date ON payments(due_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contracts_tenant ON contracts(tenant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(receipt_date)")

    conn.commit()
    conn.close()

# استدعاء التهيئة
init_db()

# ---------- دوال مساعدة ----------
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

def export_df_to_pdf(df, title, file_name):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, title)
    c.setFont("Helvetica", 10)
    y = height - 80
    for i, row in df.iterrows():
        text = " | ".join(str(x) for x in row.values)
        c.drawString(50, y, text[:100])
        y -= 20
        if y < 50:
            c.showPage()
            y = height - 50
    c.save()
    buffer.seek(0)
    st.download_button("تحميل PDF", data=buffer, file_name=file_name, mime="application/pdf")

def gregorian_to_hijri(greg_date):
    hijri = convert.Gregorian(greg_date.year, greg_date.month, greg_date.day).to_hijri()
    return f"{hijri.day:02d}-{hijri.month:02d}-{hijri.year}"

def hijri_to_gregorian(hijri_str):
    day, month, year = map(int, hijri_str.split('-'))
    greg = convert.Hijri(year, month, day).to_gregorian()
    return date(greg.year, greg.month, greg.day)

# ---------- دوال قراءة البيانات مع الكاش ----------
@st.cache_data(ttl=60)
def load_tenants():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, name, phone, national_id, address, region FROM tenants", conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_properties():
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, name, description, address, region, area FROM properties", conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_contracts():
    conn = get_conn()
    # الحصول على أسماء الأعمدة الفعلية في جدول contracts
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(contracts)")
    columns = [col[1] for col in cur.fetchall()]
    # بناء قائمة الأعمدة المطلوبة مع القيم الافتراضية إذا كانت مفقودة
    select_cols = []
    for col in ['id', 'contract_number', 'start_date', 'end_date', 'rent_amount', 'interval_months', 'deposit_amount', 'status', 'tax_included', 'tax_rate']:
        if col in columns:
            select_cols.append(f"c.{col}")
        else:
            # استخدام قيمة افتراضية بناءً على نوع العمود
            if col == 'interval_months':
                select_cols.append("1 AS interval_months")
            elif col == 'tax_included':
                select_cols.append("0 AS tax_included")
            elif col == 'tax_rate':
                select_cols.append("0.15 AS tax_rate")
            else:
                select_cols.append(f"NULL AS {col}")
    # إضافة أسماء المستأجر والعقار
    query = f"""
        SELECT {', '.join(select_cols)},
               t.name as tenant, p.name as property
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
    query = '''
        SELECT pay.id, t.name as tenant, p.name as property, pay.due_date,
               pay.amount, pay.paid_amount, (pay.amount - pay.paid_amount) as remaining,
               pay.status, pay.paid_date
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
        SELECT r.receipt_number, t.name as tenant, r.amount, r.receipt_date, r.payment_method
        FROM receipts r
        JOIN tenants t ON r.tenant_id = t.id
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# ---------- القائمة الجانبية ----------
menu = st.sidebar.radio(
    "القائمة الرئيسية",
    ["لوحة التحكم", "المستأجرين", "العقارات", "العقود", "الدفعات", "صفحة السداد", "التقارير", "نسخ احتياطي"]
)

# ================== لوحة التحكم ==================
if menu == "لوحة التحكم":
    st.subheader("📊 لوحة التحكم")

    df_tenants = load_tenants()
    df_contracts = load_contracts()
    df_payments = load_payments()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("إجمالي المستأجرين", len(df_tenants))
    with col2:
        active_contracts = len(df_contracts[df_contracts["status"] == "نشط"])
        st.metric("العقود النشطة", active_contracts)
    with col3:
        due_payments = len(df_payments[df_payments["status"].isin(["مستحق", "متأخر", "جزئي"])])
        st.metric("دفعات مستحقة", due_payments)
    with col4:
        total_collected = df_payments["paid_amount"].sum()
        st.metric("إجمالي المحصل", f"{total_collected:,.2f}")

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
    today = date.today()
    end_date = today + timedelta(days=30)
    upcoming = df_payments[
        (df_payments["due_date"] >= today.isoformat()) &
        (df_payments["due_date"] <= end_date.isoformat()) &
        (df_payments["status"].isin(["مستحق", "جزئي"]))
    ]
    if not upcoming.empty:
        st.dataframe(upcoming[["tenant", "property", "due_date", "amount", "paid_amount", "status"]], use_container_width=True)
    else:
        st.info("لا توجد دفعات مستحقة خلال 30 يوم.")

# ================== المستأجرين ==================
elif menu == "المستأجرين":
    st.subheader("👥 إدارة المستأجرين")
    tab1, tab2 = st.tabs(["عرض الكل", "إضافة مستأجر"])

    with tab1:
        df_tenants = load_tenants()
        if not df_tenants.empty:
            st.dataframe(df_tenants, use_container_width=True)
            tenant_dict = dict(zip(df_tenants["name"], df_tenants["id"]))
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
                st.write(f"**الرقم القومي:** {tenant[3] or 'غير محدد'}")
                st.write(f"**العنوان:** {tenant[4] or 'غير محدد'}")
                st.write(f"**المنطقة:** {tenant[5] or 'غير محدد'}")
            with col2:
                st.write(f"**ملاحظات:** {tenant[6] or 'لا يوجد'}")

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
            st.info("لا يوجد مستأجرين بعد")

    with tab2:
        with st.form("add_tenant_form", clear_on_submit=True):
            name = st.text_input("الاسم *")
            phone = st.text_input("الهاتف")
            national_id = st.text_input("الرقم القومي")
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

# ================== العقارات ==================
elif menu == "العقارات":
    st.subheader("🏬 إدارة العقارات")
    tab1, tab2 = st.tabs(["عرض الكل", "إضافة عقار"])

    with tab1:
        df_props = load_properties()
        if not df_props.empty:
            st.dataframe(df_props, use_container_width=True)
        else:
            st.info("لا توجد عقارات")

    with tab2:
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
    tab1, tab2 = st.tabs(["عرض الكل", "إنشاء عقد"])

    with tab1:
        df_contracts = load_contracts()
        if not df_contracts.empty:
            st.dataframe(df_contracts, use_container_width=True)
        else:
            st.info("لا توجد عقود")

    with tab2:
        df_tenants = load_tenants()
        df_props = load_properties()
        if df_tenants.empty or df_props.empty:
            st.warning("يجب إضافة مستأجر وعقار أولاً")
        else:
            with st.form("add_contract_form", clear_on_submit=True):
                tenant_id = st.selectbox("المستأجر", df_tenants["id"], format_func=lambda x: df_tenants[df_tenants["id"]==x]["name"].iloc[0])
                property_id = st.selectbox("العقار", df_props["id"], format_func=lambda x: df_props[df_props["id"]==x]["name"].iloc[0])
                contract_number = st.text_input("رقم العقد")
                start_date = st.date_input("تاريخ البداية")
                end_date = st.date_input("تاريخ النهاية", value=start_date + relativedelta(years=1))
                rent_amount = st.number_input("قيمة الإيجار", min_value=0.0, step=100.0)
                interval_months = st.number_input("دورية السداد (عدد الشهور)", min_value=1, value=1)
                deposit_amount = st.number_input("التأمين", min_value=0.0, step=100.0)
                tax_included = st.checkbox("المبلغ شامل الضريبة")
                tax_rate = st.number_input("نسبة الضريبة (%)", min_value=0.0, value=15.0, step=1.0) / 100
                notes = st.text_area("ملاحظات")
                submit = st.form_submit_button("حفظ وإنشاء الدفعات")

                if submit:
                    if start_date >= end_date:
                        st.error("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
                    else:
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute('''
                            INSERT INTO contracts (tenant_id, property_id, contract_number, start_date, end_date,
                                                   rent_amount, interval_months, deposit_amount, notes,
                                                   tax_included, tax_rate)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (tenant_id, property_id, contract_number, start_date.isoformat(), end_date.isoformat(),
                              rent_amount, interval_months, deposit_amount, notes,
                              1 if tax_included else 0, tax_rate))
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
            st.dataframe(df_payments, use_container_width=True)
            payment_id = st.selectbox("اختر دفعة لتسجيل سداد", df_payments["id"].tolist())
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
                    if st.form_submit_button("تسجيل"):
                        new_paid = pay[1] + amount_paid
                        status = "مدفوع" if new_paid >= pay[0] else "جزئي" if new_paid > 0 else "مستحق"
                        cur.execute(
                            "UPDATE payments SET paid_amount = ?, paid_date = ?, status = ? WHERE id = ?",
                            (new_paid, pay_date.isoformat(), status, payment_id)
                        )
                        receipt_number = generate_receipt_number()
                        cur.execute('''
                            INSERT INTO receipts (receipt_number, tenant_id, contract_id, payment_id, amount, receipt_date, payment_method)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (receipt_number, pay[2], pay[3], payment_id, amount_paid, pay_date.isoformat(), method))
                        conn.commit()
                        conn.close()
                        st.cache_data.clear()
                        st.success("تم تسجيل السداد")
                        st.rerun()
        else:
            st.info("لا توجد دفعات مطابقة")

    with tab2:
        st.info("استخدم تبويب 'الدفعات المستحقة' لاختيار دفعة وتسجيل سداد.")

# ================== صفحة السداد ==================
elif menu == "صفحة السداد":
    st.subheader("💳 صفحة السداد السريع")
    df_tenants = load_tenants()
    if df_tenants.empty:
        st.warning("لا يوجد مستأجرين")
    else:
        with st.form("quick_payment_form"):
            tenant_id = st.selectbox("اختر المستأجر", df_tenants["id"], format_func=lambda x: df_tenants[df_tenants["id"]==x]["name"].iloc[0])
            payment_amount = st.number_input("المبلغ الكلي للسداد", min_value=0.0, step=100.0)
            payment_date = st.date_input("تاريخ السداد")
            method = st.selectbox("طريقة السداد", ["نقدي", "تحويل بنكي", "شيك"])
            submit = st.form_submit_button("تسجيل السداد")

            if submit and payment_amount > 0:
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
                    INSERT INTO receipts (receipt_number, tenant_id, amount, receipt_date, payment_method)
                    VALUES (?, ?, ?, ?, ?)
                ''', (receipt_number, tenant_id, payment_amount, receipt_date, method))
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
                        UPDATE payments SET paid_amount = ?, paid_date = ?, status = ?
                        WHERE id = ?
                    ''', (new_paid, receipt_date, status, pay_id))
                    remaining_amount -= pay_amount_to_apply
                conn.commit()
                conn.close()
                st.cache_data.clear()
                st.success(f"تم تسجيل سداد بمبلغ {payment_amount:,.2f} للمستأجر")
                st.rerun()

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
            tenant_id = st.selectbox("اختر المستأجر", df_tenants["id"], format_func=lambda x: df_tenants[df_tenants["id"]==x]["name"].iloc[0])
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT name FROM tenants WHERE id = ?", (tenant_id,))
            tenant_name = cur.fetchone()[0]
            cur.execute('''
                SELECT due_date, amount, paid_amount, (amount - paid_amount) as remaining, status, paid_date
                FROM payments WHERE tenant_id = ? ORDER BY due_date
            ''', (tenant_id,))
            payments = cur.fetchall()
            cur.execute('''
                SELECT receipt_number, amount, receipt_date, payment_method
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
                df = pd.DataFrame(payments, columns=["تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة", "تاريخ السداد"])
                st.dataframe(df, use_container_width=True)
                total_amount = sum(p[1] for p in payments)
                total_paid = sum(p[2] for p in payments)
                st.write(f"**إجمالي المستحق:** {total_amount:,.2f}")
                st.write(f"**إجمالي المدفوع:** {total_paid:,.2f}")
                st.write(f"**المتبقي:** {total_amount - total_paid:,.2f}")
            else:
                st.info("لا توجد دفعات")

            st.markdown("### سندات القبض")
            if receipts:
                df_receipts = pd.DataFrame(receipts, columns=["رقم السند", "المبلغ", "التاريخ", "الطريقة"])
                st.dataframe(df_receipts, use_container_width=True)
            else:
                st.info("لا توجد سندات")

            if payments:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    pd.DataFrame(payments, columns=["تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة", "تاريخ السداد"]).to_excel(writer, sheet_name='الدفعات', index=False)
                    if receipts:
                        pd.DataFrame(receipts, columns=["رقم السند", "المبلغ", "التاريخ", "الطريقة"]).to_excel(writer, sheet_name='سندات', index=False)
                st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"كشف_حساب_{tenant_name}.xlsx")
                df_pdf = pd.DataFrame(payments, columns=["تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة", "تاريخ السداد"])
                export_df_to_pdf(df_pdf, f"كشف حساب {tenant_name}", f"كشف_حساب_{tenant_name}.pdf")

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
        tenant_filter = st.selectbox("اختر مستأجر (اختياري)", ["الكل"] + load_tenants()["name"].tolist())

        conn = get_conn()
        cur = conn.cursor()
        query = '''
            SELECT t.name, p.name, pay.due_date, pay.amount, pay.paid_amount,
                   (pay.amount - pay.paid_amount) as remaining, pay.status
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
            st.dataframe(df, use_container_width=True)
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
            SELECT COALESCE(t.region, 'غير محدد') as region,
                   COUNT(DISTINCT t.id) as tenants_count,
                   COUNT(DISTINCT c.id) as contracts_count,
                   COALESCE(SUM(pay.amount), 0) as total_amount,
                   COALESCE(SUM(pay.paid_amount), 0) as total_paid,
                   COALESCE(SUM(pay.amount - pay.paid_amount), 0) as remaining
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
        query += " GROUP BY COALESCE(t.region, 'غير محدد') ORDER BY region"
        conn = get_conn()
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        if not df.empty:
            df["نسبة التحصيل"] = (df["total_paid"] / df["total_amount"] * 100).fillna(0).round(1).astype(str) + "%"
            st.dataframe(df, use_container_width=True)
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
            SELECT r.receipt_date, t.name, r.receipt_number, r.amount, r.payment_method
            FROM receipts r
            JOIN tenants t ON r.tenant_id = t.id
            WHERE r.receipt_date BETWEEN ? AND ?
            ORDER BY r.receipt_date
        '''
        df = pd.read_sql_query(query, conn, params=(from_date.isoformat(), to_date.isoformat()))
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            total = df["amount"].sum()
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
            SELECT r.receipt_date, t.name as tenant, r.receipt_number, r.amount,
                   c.tax_included, c.tax_rate
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
                if row['tax_included'] == 1:
                    tax = row['amount'] * (row['tax_rate'] / (1 + row['tax_rate']))
                else:
                    tax = row['amount'] * row['tax_rate']
                tax_values.append(tax)
            df['الضريبة'] = tax_values
            df['صافي المبلغ'] = df['amount'] - df['الضريبة']
            st.dataframe(df, use_container_width=True)
            total_tax = df['الضريبة'].sum()
            st.write(f"**إجمالي الضريبة:** {total_tax:,.2f}")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"ضرائب_{from_date}_to_{to_date}.xlsx")
            export_df_to_pdf(df, "تقرير الضرائب", f"ضرائب_{from_date}_to_{to_date}.pdf")
        else:
            st.info("لا توجد سندات في هذه الفترة")

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