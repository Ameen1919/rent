import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, timedelta
from io import BytesIO
import base64

# ---------- إعداد الصفحة ----------
st.set_page_config(page_title="نظام إدارة الإيجارات", page_icon="🏢", layout="wide")
st.title("🏢 نظام إدارة الإيجارات")

# ---------- الاتصال بقاعدة البيانات ----------
@st.cache_resource
def init_db():
    conn = sqlite3.connect('rentals.db', check_same_thread=False)
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
            notes TEXT,
            contract_file BLOB,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            address TEXT,
            region TEXT,
            area TEXT,
            notes TEXT
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
            payment_frequency TEXT,
            deposit_amount REAL,
            contract_file BLOB,
            notes TEXT,
            status TEXT DEFAULT 'نشط',
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
            priority TEXT,
            is_alert INTEGER,
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
    conn.commit()
    return conn

conn = init_db()
cur = conn.cursor()

# ---------- دوال مساعدة ----------
def generate_receipt_number():
    import time
    return f"RCP-{int(time.time())}"

def create_payment_schedule(contract_id, tenant_id, start_date, end_date, rent_amount, frequency):
    from datetime import datetime, timedelta
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    freq_days = {'شهري': 30, 'ربع سنوي': 90, 'نصف سنوي': 180, 'سنوي': 365}
    interval = freq_days.get(frequency, 30)
    current = start
    while current <= end:
        cur.execute('''
            INSERT INTO payments (contract_id, tenant_id, due_date, amount)
            VALUES (?, ?, ?, ?)
        ''', (contract_id, tenant_id, current.isoformat(), rent_amount))
        current += timedelta(days=interval)
    conn.commit()

def add_note(tenant_id, note_text, priority, is_alert):
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

def get_unread_alerts(tenant_id=None):
    if tenant_id:
        cur.execute('''
            SELECT alert_text, alert_date FROM alerts WHERE tenant_id = ? AND is_read = 0
            ORDER BY alert_date DESC
        ''', (tenant_id,))
    else:
        cur.execute('''
            SELECT a.alert_text, a.alert_date, t.name
            FROM alerts a JOIN tenants t ON a.tenant_id = t.id
            WHERE a.is_read = 0 ORDER BY a.alert_date DESC
        ''')
    return cur.fetchall()

def mark_alerts_read(tenant_id):
    cur.execute('UPDATE alerts SET is_read = 1 WHERE tenant_id = ? AND is_read = 0', (tenant_id,))
    conn.commit()

# ---------- القائمة الجانبية ----------
menu = st.sidebar.radio("القائمة الرئيسية", ["لوحة التحكم", "المستأجرين", "العقارات", "العقود", "الدفعات", "التقارير"])

# ================== لوحة التحكم ==================
if menu == "لوحة التحكم":
    st.subheader("📊 لوحة التحكم")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        cur.execute("SELECT COUNT(*) FROM tenants")
        tenants_count = cur.fetchone()[0]
        st.metric("عدد المستأجرين", tenants_count)
    with col2:
        cur.execute("SELECT COUNT(*) FROM contracts WHERE status = 'نشط'")
        active_contracts = cur.fetchone()[0]
        st.metric("العقود النشطة", active_contracts)
    with col3:
        cur.execute("SELECT COUNT(*) FROM payments WHERE status IN ('مستحق','متأخر','جزئي')")
        due_payments = cur.fetchone()[0]
        st.metric("دفعات مستحقة", due_payments)
    with col4:
        cur.execute("SELECT COALESCE(SUM(paid_amount),0) FROM payments")
        total_paid = cur.fetchone()[0]
        st.metric("إجمالي المحصل", f"{total_paid:,.2f}")
    st.markdown("---")
    st.subheader("⚠️ تنبيهات غير مقروءة")
    alerts = get_unread_alerts()
    if alerts:
        for alert in alerts:
            st.warning(f"**{alert[2]}** - {alert[0]} (تاريخ: {alert[1]})")
    else:
        st.info("لا توجد تنبيهات.")
    st.subheader("📅 الدفعات القادمة (30 يوم)")
    today = date.today()
    end_date = today + timedelta(days=30)
    cur.execute('''
        SELECT t.name, p.name, pay.due_date, pay.amount, pay.paid_amount, pay.status
        FROM payments pay
        JOIN tenants t ON pay.tenant_id = t.id
        JOIN contracts c ON pay.contract_id = c.id
        JOIN properties p ON c.property_id = p.id
        WHERE pay.due_date BETWEEN ? AND ? AND pay.status IN ('مستحق','جزئي')
        ORDER BY pay.due_date
    ''', (today.isoformat(), end_date.isoformat()))
    upcoming = cur.fetchall()
    if upcoming:
        df = pd.DataFrame(upcoming, columns=["المستأجر", "العقار", "تاريخ الاستحقاق", "المبلغ", "المدفوع", "الحالة"])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("لا توجد دفعات مستحقة خلال 30 يوم.")

# ================== المستأجرين ==================
elif menu == "المستأجرين":
    st.subheader("👥 إدارة المستأجرين")
    tab1, tab2 = st.tabs(["عرض الكل", "إضافة مستأجر"])
    with tab1:
        cur.execute("SELECT id, name, phone, national_id, address, region FROM tenants")
        tenants = cur.fetchall()
        if tenants:
            df = pd.DataFrame(tenants, columns=["ID", "الاسم", "الهاتف", "الرقم القومي", "العنوان", "المنطقة"])
            st.dataframe(df, use_container_width=True)
            selected_id = st.selectbox("اختر مستأجر لعرض التفاصيل", [t[0] for t in tenants], format_func=lambda x: next(t[1] for t in tenants if t[0]==x))
            if selected_id:
                cur.execute("SELECT * FROM tenants WHERE id = ?", (selected_id,))
                tenant = cur.fetchone()
                st.markdown("### تفاصيل المستأجر")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**الاسم:** {tenant[1]}")
                    st.write(f"**الهاتف:** {tenant[2] or 'غير محدد'}")
                    st.write(f"**الرقم القومي:** {tenant[3] or 'غير محدد'}")
                    st.write(f"**العنوان:** {tenant[4] or 'غير محدد'}")
                    st.write(f"**المنطقة:** {tenant[5] or 'غير محدد'}")
                # عرض ملف العقد إذا وجد
                if tenant[7]:
                    st.download_button("تحميل ملف العقد", data=tenant[7], file_name=f"contract_{tenant[1]}.pdf")
                # تنبيهات
                alerts = get_unread_alerts(tenant[0])
                if alerts:
                    st.warning("⚠️ تنبيهات:")
                    for a in alerts:
                        st.write(f"- {a[0]} (تاريخ: {a[1]})")
                    if st.button("تحديد كمقروء"):
                        mark_alerts_read(tenant[0])
                        st.rerun()
                # الملاحظات
                st.markdown("**الملاحظات:**")
                cur.execute("SELECT note_date, note_text, priority, is_alert FROM notes WHERE tenant_id = ? ORDER BY note_date DESC", (tenant[0],))
                notes = cur.fetchall()
                if notes:
                    for n in notes:
                        st.write(f"- [{n[0]}] ({n[2]}) {n[1]}{' ⚠️' if n[3] else ''}")
                else:
                    st.write("لا توجد ملاحظات.")
                # إضافة ملاحظة
                with st.form("add_note_form"):
                    note_text = st.text_area("ملاحظة جديدة")
                    priority = st.selectbox("الأهمية", ["عادية", "متوسطة", "عالية"])
                    is_alert = st.checkbox("تنبيه")
                    if st.form_submit_button("إضافة ملاحظة"):
                        if note_text.strip():
                            add_note(tenant[0], note_text.strip(), priority, 1 if is_alert else 0)
                            st.success("تمت إضافة الملاحظة")
                            st.rerun()
        else:
            st.info("لا يوجد مستأجرين.")
    with tab2:
        with st.form("add_tenant"):
            name = st.text_input("الاسم *")
            phone = st.text_input("الهاتف")
            national_id = st.text_input("الرقم القومي")
            address = st.text_input("العنوان")
            region = st.text_input("المنطقة")
            notes = st.text_area("ملاحظات")
            contract_file = st.file_uploader("ملف العقد (PDF/صورة)", type=["pdf", "png", "jpg", "jpeg"])
            submit = st.form_submit_button("حفظ")
            if submit:
                if not name.strip():
                    st.error("الاسم مطلوب")
                else:
                    file_bytes = None
                    if contract_file:
                        file_bytes = contract_file.read()
                    cur.execute('''
                        INSERT INTO tenants (name, phone, national_id, address, region, notes, contract_file)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (name, phone, national_id, address, region, notes, file_bytes))
                    conn.commit()
                    st.success("تمت إضافة المستأجر")
                    st.rerun()

# ================== العقارات ==================
elif menu == "العقارات":
    st.subheader("🏬 إدارة العقارات")
    tab1, tab2 = st.tabs(["عرض الكل", "إضافة عقار"])
    with tab1:
        cur.execute("SELECT id, name, description, address, region, area FROM properties")
        props = cur.fetchall()
        if props:
            df = pd.DataFrame(props, columns=["ID", "الاسم", "الوصف", "العنوان", "المنطقة", "المساحة"])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("لا توجد عقارات.")
    with tab2:
        with st.form("add_property"):
            name = st.text_input("اسم العقار *")
            description = st.text_area("الوصف")
            address = st.text_input("العنوان")
            region = st.text_input("المنطقة")
            area = st.text_input("المساحة")
            notes = st.text_area("ملاحظات")
            submit = st.form_submit_button("حفظ")
            if submit:
                if not name.strip():
                    st.error("الاسم مطلوب")
                else:
                    cur.execute('''
                        INSERT INTO properties (name, description, address, region, area, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (name, description, address, region, area, notes))
                    conn.commit()
                    st.success("تمت الإضافة")
                    st.rerun()

# ================== العقود ==================
elif menu == "العقود":
    st.subheader("📄 إدارة العقود")
    tab1, tab2 = st.tabs(["عرض الكل", "إضافة عقد"])
    with tab1:
        cur.execute('''
            SELECT c.id, c.contract_number, t.name, p.name, c.start_date, c.end_date,
                   c.rent_amount, c.payment_frequency, c.status
            FROM contracts c
            JOIN tenants t ON c.tenant_id = t.id
            JOIN properties p ON c.property_id = p.id
        ''')
        contracts = cur.fetchall()
        if contracts:
            df = pd.DataFrame(contracts, columns=["ID", "رقم العقد", "المستأجر", "العقار", "تاريخ البداية", "تاريخ النهاية", "الإيجار", "الدورية", "الحالة"])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("لا توجد عقود.")
    with tab2:
        with st.form("add_contract"):
            cur.execute("SELECT id, name FROM tenants")
            tenants = cur.fetchall()
            cur.execute("SELECT id, name FROM properties")
            properties = cur.fetchall()
            if not tenants or not properties:
                st.warning("يجب إضافة مستأجر وعقار أولاً.")
            else:
                tenant_id = st.selectbox("المستأجر", [t[0] for t in tenants], format_func=lambda x: next(t[1] for t in tenants if t[0]==x))
                property_id = st.selectbox("العقار", [p[0] for p in properties], format_func=lambda x: next(p[1] for p in properties if p[0]==x))
                contract_number = st.text_input("رقم العقد")
                start_date = st.date_input("تاريخ البداية")
                end_date = st.date_input("تاريخ النهاية", value=start_date + timedelta(days=365))
                rent_amount = st.number_input("قيمة الإيجار", min_value=0.0, step=100.0)
                payment_frequency = st.selectbox("دورية السداد", ["شهري", "ربع سنوي", "نصف سنوي", "سنوي"])
                deposit_amount = st.number_input("التأمين", min_value=0.0, step=100.0)
                contract_file = st.file_uploader("ملف العقد", type=["pdf", "png", "jpg", "jpeg"])
                notes = st.text_area("ملاحظات")
                submit = st.form_submit_button("حفظ العقد")
                if submit:
                    file_bytes = None
                    if contract_file:
                        file_bytes = contract_file.read()
                    cur.execute('''
                        INSERT INTO contracts (tenant_id, property_id, contract_number, start_date, end_date,
                                               rent_amount, payment_frequency, deposit_amount, contract_file, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (tenant_id, property_id, contract_number, start_date.isoformat(), end_date.isoformat(),
                          rent_amount, payment_frequency, deposit_amount, file_bytes, notes))
                    contract_id = cur.lastrowid
                    create_payment_schedule(contract_id, tenant_id, start_date.isoformat(), end_date.isoformat(), rent_amount, payment_frequency)
                    conn.commit()
                    st.success("تم إنشاء العقد وجدولة الدفعات")
                    st.rerun()

# ================== الدفعات ==================
elif menu == "الدفعات":
    st.subheader("💰 متابعة الدفعات")
    tab1, tab2 = st.tabs(["الدفعات المستحقة", "تسجيل دفعة"])
    with tab1:
        filter_status = st.selectbox("فلتر الحالة", ["الكل", "مستحق", "مدفوع", "متأخر", "جزئي"])
        query = '''
            SELECT pay.id, t.name, p.name, pay.due_date, pay.amount, pay.paid_amount,
                   (pay.amount - pay.paid_amount), pay.status
            FROM payments pay
            JOIN tenants t ON pay.tenant_id = t.id
            JOIN contracts c ON pay.contract_id = c.id
            JOIN properties p ON c.property_id = p.id
        '''
        if filter_status != "الكل":
            query += " WHERE pay.status = ?"
            cur.execute(query, (filter_status,))
        else:
            cur.execute(query)
        payments = cur.fetchall()
        if payments:
            df = pd.DataFrame(payments, columns=["ID", "المستأجر", "العقار", "تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة"])
            st.dataframe(df, use_container_width=True)
            # تسجيل دفعة لدفعة محددة
            payment_id = st.selectbox("اختر دفعة لتسجيل سداد", [p[0] for p in payments], format_func=lambda x: f"ID {x}")
            if payment_id:
                cur.execute("SELECT amount, paid_amount, tenant_id, contract_id FROM payments WHERE id = ?", (payment_id,))
                pay = cur.fetchone()
                remaining = pay[0] - pay[1]
                with st.form("pay_form"):
                    amount_to_pay = st.number_input("المبلغ المدفوع", min_value=0.0, max_value=remaining, step=100.0)
                    payment_date = st.date_input("تاريخ السداد")
                    method = st.selectbox("طريقة السداد", ["نقدي", "تحويل بنكي", "شيك"])
                    notes = st.text_input("ملاحظات")
                    if st.form_submit_button("تسجيل"):
                        new_paid = pay[1] + amount_to_pay
                        status = "مدفوع" if new_paid >= pay[0] else "جزئي" if new_paid > 0 else "مستحق"
                        cur.execute('''
                            UPDATE payments SET paid_amount = ?, paid_date = ?, status = ? WHERE id = ?
                        ''', (new_paid, payment_date.isoformat(), status, payment_id))
                        receipt_number = generate_receipt_number()
                        cur.execute('''
                            INSERT INTO receipts (receipt_number, tenant_id, contract_id, payment_id, amount, receipt_date, payment_method, notes)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (receipt_number, pay[2], pay[3], payment_id, amount_to_pay, payment_date.isoformat(), method, notes))
                        conn.commit()
                        st.success("تم تسجيل السداد")
                        st.rerun()
    with tab2:
        st.info("استخدم تبويب 'الدفعات المستحقة' لاختيار دفعة وتسجيل سداد.")

# ================== التقارير ==================
elif menu == "التقارير":
    st.subheader("📈 التقارير")
    report_type = st.radio("اختر التقرير", ["كشف حساب مستأجر", "الدفعات المستحقة لتاريخ محدد", "تقرير المناطق", "تقرير الإيرادات"])
    if report_type == "كشف حساب مستأجر":
        cur.execute("SELECT id, name FROM tenants")
        tenants = cur.fetchall()
        if tenants:
            tenant_id = st.selectbox("اختر المستأجر", [t[0] for t in tenants], format_func=lambda x: next(t[1] for t in tenants if t[0]==x))
            cur.execute("SELECT name, phone, address, region FROM tenants WHERE id = ?", (tenant_id,))
            tenant_info = cur.fetchone()
            st.markdown(f"### كشف حساب: {tenant_info[0]}")
            cur.execute('''
                SELECT due_date, amount, paid_amount, (amount - paid_amount) as remaining, status, paid_date
                FROM payments WHERE tenant_id = ? ORDER BY due_date
            ''', (tenant_id,))
            payments = cur.fetchall()
            if payments:
                df = pd.DataFrame(payments, columns=["تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة", "تاريخ السداد"])
                st.dataframe(df, use_container_width=True)
                total_amount = sum(p[1] for p in payments)
                total_paid = sum(p[2] for p in payments)
                st.write(f"**إجمالي المستحق:** {total_amount:,.2f}")
                st.write(f"**إجمالي المدفوع:** {total_paid:,.2f}")
                st.write(f"**المتبقي:** {total_amount - total_paid:,.2f}")
            else:
                st.info("لا توجد دفعات.")
            # سندات القبض
            st.markdown("### سندات القبض")
            cur.execute('''
                SELECT receipt_number, amount, receipt_date, payment_method FROM receipts WHERE tenant_id = ?
                ORDER BY receipt_date DESC
            ''', (tenant_id,))
            receipts = cur.fetchall()
            if receipts:
                df_receipts = pd.DataFrame(receipts, columns=["رقم السند", "المبلغ", "التاريخ", "الطريقة"])
                st.dataframe(df_receipts, use_container_width=True)
            # زر تصدير
            if payments:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, sheet_name='الدفعات', index=False)
                    if receipts:
                        df_receipts.to_excel(writer, sheet_name='سندات القبض', index=False)
                st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"كشف_حساب_{tenant_info[0]}.xlsx")
        else:
            st.info("لا يوجد مستأجرين.")
    elif report_type == "الدفعات المستحقة لتاريخ محدد":
        target_date = st.date_input("تاريخ الاستحقاق")
        cur.execute('''
            SELECT t.name, p.name, pay.due_date, pay.amount, pay.paid_amount,
                   (pay.amount - pay.paid_amount), pay.status, t.phone
            FROM payments pay
            JOIN tenants t ON pay.tenant_id = t.id
            JOIN contracts c ON pay.contract_id = c.id
            JOIN properties p ON c.property_id = p.id
            WHERE pay.due_date <= ? AND pay.status IN ('مستحق','متأخر','جزئي')
            ORDER BY pay.due_date
        ''', (target_date.isoformat(),))
        due_payments = cur.fetchall()
        if due_payments:
            df = pd.DataFrame(due_payments, columns=["المستأجر", "العقار", "تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة", "الهاتف"])
            st.dataframe(df, use_container_width=True)
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='الدفعات المستحقة', index=False)
            st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"مستحقات_{target_date}.xlsx")
        else:
            st.info("لا توجد دفعات مستحقة حتى هذا التاريخ.")
    elif report_type == "تقرير المناطق":
        st.markdown("### تقرير حسب المناطق")
        from_date = st.date_input("من تاريخ", value=date.today().replace(day=1))
        to_date = st.date_input("إلى تاريخ", value=date.today())
        region_filter = st.text_input("فلتر منطقة (اتركه فارغ للكل)")
        query = '''
            SELECT COALESCE(t.region, p.region, 'غير محدد') as region,
                   COUNT(DISTINCT t.id) as tenants_count,
                   COUNT(DISTINCT c.id) as contracts_count,
                   COALESCE(SUM(pay.amount),0) as total_amount,
                   COALESCE(SUM(pay.paid_amount),0) as total_paid,
                   COALESCE(SUM(pay.amount - pay.paid_amount),0) as remaining
            FROM tenants t
            LEFT JOIN contracts c ON t.id = c.tenant_id
            LEFT JOIN properties p ON c.property_id = p.id
            LEFT JOIN payments pay ON c.id = pay.contract_id
            WHERE 1=1
        '''
        params = []
        if region_filter:
            query += " AND (t.region = ? OR p.region = ?)"
            params.extend([region_filter, region_filter])
        if from_date and to_date:
            query += " AND (pay.due_date BETWEEN ? AND ? OR pay.due_date IS NULL)"
            params.extend([from_date.isoformat(), to_date.isoformat()])
        query += " GROUP BY COALESCE(t.region, p.region, 'غير محدد') ORDER BY region"
        cur.execute(query, params)
        results = cur.fetchall()
        if results:
            df = pd.DataFrame(results, columns=["المنطقة", "عدد العملاء", "عدد العقود", "إجمالي المستحق", "إجمالي المدفوع", "المتبقي"])
            df["نسبة التحصيل"] = df["إجمالي المدفوع"] / df["إجمالي المستحق"] * 100
            df["نسبة التحصيل"] = df["نسبة التحصيل"].fillna(0).round(1).astype(str) + "%"
            st.dataframe(df, use_container_width=True)
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='تقرير المناطق', index=False)
            st.download_button("تحميل Excel", data=output.getvalue(), file_name="تقرير_المناطق.xlsx")
        else:
            st.info("لا توجد بيانات.")
    elif report_type == "تقرير الإيرادات":
        st.markdown("### تقرير الإيرادات")
        from_date = st.date_input("من تاريخ", value=date.today().replace(day=1))
        to_date = st.date_input("إلى تاريخ", value=date.today())
        cur.execute('''
            SELECT r.receipt_date, t.name, r.receipt_number, r.amount, r.payment_method
            FROM receipts r JOIN tenants t ON r.tenant_id = t.id
            WHERE r.receipt_date BETWEEN ? AND ? ORDER BY r.receipt_date
        ''', (from_date.isoformat(), to_date.isoformat()))
        receipts = cur.fetchall()
        if receipts:
            df = pd.DataFrame(receipts, columns=["التاريخ", "المستأجر", "رقم السند", "المبلغ", "طريقة السداد"])
            st.dataframe(df, use_container_width=True)
            total = sum(r[3] for r in receipts)
            st.write(f"**إجمالي الإيرادات:** {total:,.2f}")
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='الإيرادات', index=False)
            st.download_button("تحميل Excel", data=output.getvalue(), file_name="تقرير_الإيرادات.xlsx")
        else:
            st.info("لا توجد إيرادات في هذه الفترة.")

# ---------- إغلاق قاعدة البيانات ----------
# لا نغلقها لأننا نستخدمها في كل تشغيل