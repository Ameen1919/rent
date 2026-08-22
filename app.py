import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta  # لمعالجة دقيقة لأشهر وسنوات العقود

st.set_page_config(page_title="نظام الإيجارات", layout="wide")
st.title("🏢 نظام إدارة الإيجارات")

# ---------- إعداد قاعدة البيانات ----------
def get_db_connection():
    conn = sqlite3.connect('rentals.db', check_same_thread=False)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            region TEXT,
            notes TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            region TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            property_id INTEGER,
            start_date TEXT,
            end_date TEXT,
            rent_amount REAL,
            payment_frequency TEXT
        )
    ''')
    # تصحيح: إضافة paid_date إلى الجدول
    cur.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER,
            tenant_id INTEGER,
            due_date TEXT,
            amount REAL,
            paid_amount REAL DEFAULT 0,
            paid_date TEXT,
            status TEXT DEFAULT 'مستحق'
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            amount REAL,
            receipt_date TEXT,
            payment_method TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            note_text TEXT,
            note_date TEXT,
            priority TEXT,
            is_alert INTEGER
        )
    ''')
    conn.commit()
    conn.close()

# تهيئة قاعدة البيانات
init_db()

conn = get_db_connection()
cur = conn.cursor()

# ---------- القائمة الجانبية ----------
menu = st.sidebar.radio("القائمة", ["لوحة التحكم", "المستأجرين", "العقارات", "العقود", "الدفعات", "التقارير", "نسخ احتياطي"])

# ---------- لوحة التحكم ----------
if menu == "لوحة التحكم":
    st.subheader("📊 لوحة التحكم")
    col1, col2, col3 = st.columns(3)
    with col1:
        cur.execute("SELECT COUNT(*) FROM tenants")
        st.metric("المستأجرين", cur.fetchone()[0])
    with col2:
        cur.execute("SELECT COUNT(*) FROM contracts")
        st.metric("العقود", cur.fetchone()[0])
    with col3:
        cur.execute("SELECT COALESCE(SUM(paid_amount),0) FROM payments")
        st.metric("المحصل", f"{cur.fetchone()[0]:,.2f}")
    st.markdown("---")
    
    cur.execute("SELECT COUNT(*) FROM notes WHERE is_alert = 1")
    alerts_count = cur.fetchone()[0]
    if alerts_count > 0:
        st.warning(f"لديك {alerts_count} تنبيهات غير مقروءة")
    else:
        st.success("لا توجد تنبيهات")

# ---------- المستأجرين ----------
elif menu == "المستأجرين":
    st.subheader("👥 المستأجرين")
    tab1, tab2 = st.tabs(["عرض", "إضافة"])
    with tab1:
        cur.execute("SELECT id, name, phone, region FROM tenants")
        tenants = cur.fetchall()
        if tenants:
            df = pd.DataFrame(tenants, columns=["ID", "الاسم", "الهاتف", "المنطقة"])
            st.dataframe(df, use_container_width=True)
            
            tenant_ids = [t[0] for t in tenants]
            selected_id = st.selectbox("اختر مستأجر", tenant_ids, format_func=lambda x: next(t[1] for t in tenants if t[0]==x))
            if selected_id:
                cur.execute("SELECT * FROM tenants WHERE id = ?", (selected_id,))
                tenant = cur.fetchone()
                st.markdown(f"**الاسم:** {tenant[1]}")
                st.markdown(f"**الهاتف:** {tenant[2] or 'غير محدد'}")
                st.markdown(f"**المنطقة:** {tenant[3] or 'غير محدد'}")
                
                cur.execute("SELECT note_text, priority, is_alert FROM notes WHERE tenant_id = ?", (selected_id,))
                notes = cur.fetchall()
                if notes:
                    st.markdown("**الملاحظات:**")
                    for n in notes:
                        icon = "⚠️" if n[2] else ""
                        st.write(f"- ({n[1]}) {n[0]} {icon}")
        else:
            st.info("لا يوجد مستأجرين بعد")
    with tab2:
        with st.form("add_tenant"):
            name = st.text_input("الاسم *")
            phone = st.text_input("الهاتف")
            region = st.text_input("المنطقة")
            notes = st.text_area("ملاحظات")
            submit = st.form_submit_button("حفظ")
            if submit:
                if name:
                    cur.execute("INSERT INTO tenants (name, phone, region, notes) VALUES (?,?,?,?)", (name, phone, region, notes))
                    conn.commit()
                    st.success("تمت الإضافة")
                    st.rerun()
                else:
                    st.error("الاسم مطلوب")

# ---------- العقارات ----------
elif menu == "العقارات":
    st.subheader("🏬 العقارات")
    tab1, tab2 = st.tabs(["عرض", "إضافة"])
    with tab1:
        cur.execute("SELECT id, name, region FROM properties")
        props = cur.fetchall()
        if props:
            df = pd.DataFrame(props, columns=["ID", "الاسم", "المنطقة"])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("لا توجد عقارات")
    with tab2:
        with st.form("add_property"):
            name = st.text_input("اسم العقار *")
            region = st.text_input("المنطقة")
            submit = st.form_submit_button("حفظ")
            if submit:
                if name:
                    cur.execute("INSERT INTO properties (name, region) VALUES (?,?)", (name, region))
                    conn.commit()
                    st.success("تمت الإضافة")
                    st.rerun()

# ---------- العقود ----------
elif menu == "العقود":
    st.subheader("📄 العقود")
    tab1, tab2 = st.tabs(["عرض", "إضافة"])
    with tab1:
        cur.execute('''
            SELECT c.id, t.name, p.name, c.start_date, c.end_date, c.rent_amount, c.payment_frequency
            FROM contracts c
            JOIN tenants t ON c.tenant_id = t.id
            JOIN properties p ON c.property_id = p.id
        ''')
        contracts = cur.fetchall()
        if contracts:
            df = pd.DataFrame(contracts, columns=["ID", "المستأجر", "العقار", "من", "إلى", "الإيجار", "الدورية"])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("لا توجد عقود")
    with tab2:
        cur.execute("SELECT id, name FROM tenants")
        tenants = cur.fetchall()
        cur.execute("SELECT id, name FROM properties")
        properties = cur.fetchall()
        if not tenants or not properties:
            st.warning("يجب إضافة مستأجر وعقار أولاً")
        else:
            with st.form("add_contract"):
                tenant_id = st.selectbox("المستأجر", [t[0] for t in tenants], format_func=lambda x: next(t[1] for t in tenants if t[0]==x))
                property_id = st.selectbox("العقار", [p[0] for p in properties], format_func=lambda x: next(p[1] for p in properties if p[0]==x))
                start_date = st.date_input("تاريخ البداية")
                end_date = st.date_input("تاريخ النهاية", value=start_date + timedelta(days=365))
                rent_amount = st.number_input("قيمة الإيجار", min_value=0.0)
                payment_frequency = st.selectbox("دورية السداد", ["شهري", "ربع سنوي", "نصف سنوي", "سنوي"])
                submit = st.form_submit_button("حفظ")
                if submit:
                    cur.execute('''
                        INSERT INTO contracts (tenant_id, property_id, start_date, end_date, rent_amount, payment_frequency)
                        VALUES (?,?,?,?,?,?)
                    ''', (tenant_id, property_id, start_date.isoformat(), end_date.isoformat(), rent_amount, payment_frequency))
                    contract_id = cur.lastrowid
                    
                    # تحسين جدولة الدفعات باستخدام relativedelta
                    freq_delta = {
                        'شهري': relativedelta(months=1),
                        'ربع سنوي': relativedelta(months=3),
                        'نصف سنوي': relativedelta(months=6),
                        'سنوي': relativedelta(years=1)
                    }
                    step = freq_delta[payment_frequency]
                    current = start_date
                    while current <= end_date:
                        cur.execute('''
                            INSERT INTO payments (contract_id, tenant_id, due_date, amount)
                            VALUES (?,?,?,?)
                        ''', (contract_id, tenant_id, current.isoformat(), rent_amount))
                        current += step
                    
                    conn.commit()
                    st.success("تم إنشاء العقد والدفعات")
                    st.rerun()

# ---------- الدفعات ----------
elif menu == "الدفعات":
    st.subheader("💰 الدفعات")
    status_filter = st.selectbox("فلتر الحالة", ["الكل", "مستحق", "مدفوع", "جزئي"])
    query = '''
        SELECT pay.id, t.name, p.name, pay.due_date, pay.amount, pay.paid_amount, (pay.amount - pay.paid_amount), pay.status
        FROM payments pay
        JOIN tenants t ON pay.tenant_id = t.id
        JOIN contracts c ON pay.contract_id = c.id
        JOIN properties p ON c.property_id = p.id
    '''
    if status_filter != "الكل":
        query += " WHERE pay.status = ?"
        cur.execute(query, (status_filter,))
    else:
        cur.execute(query)
    payments = cur.fetchall()
    if payments:
        df = pd.DataFrame(payments, columns=["ID", "المستأجر", "العقار", "الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة"])
        st.dataframe(df, use_container_width=True)
        
        payment_id = st.selectbox("اختر دفعة لتسجيل سداد", [p[0] for p in payments])
        if payment_id:
            cur.execute("SELECT amount, paid_amount, tenant_id, contract_id FROM payments WHERE id = ?", (payment_id,))
            pay = cur.fetchone()
            remaining = pay[0] - pay[1]
            with st.form("pay_form"):
                amount_paid = st.number_input("المبلغ المدفوع", min_value=0.0, max_value=remaining)
                pay_date = st.date_input("تاريخ السداد")
                method = st.selectbox("طريقة السداد", ["نقدي", "تحويل بنكي", "شيك"])
                if st.form_submit_button("تسجيل"):
                    new_paid = pay[1] + amount_paid
                    status = "مدفوع" if new_paid >= pay[0] else "جزئي" if new_paid > 0 else "مستحق"
                    cur.execute("UPDATE payments SET paid_amount = ?, paid_date = ?, status = ? WHERE id = ?", (new_paid, pay_date.isoformat(), status, payment_id))
                    cur.execute("INSERT INTO receipts (tenant_id, amount, receipt_date, payment_method) VALUES (?,?,?,?)", (pay[2], amount_paid, pay_date.isoformat(), method))
                    conn.commit()
                    st.success("تم التسجيل")
                    st.rerun()
    else:
        st.info("لا توجد دفعات")

# ---------- التقارير ----------
elif menu == "التقارير":
    st.subheader("📈 التقارير")
    report = st.radio("اختر التقرير", ["كشف حساب مستأجر", "الدفعات المستحقة", "تقرير المناطق", "الإيرادات"])
    if report == "كشف حساب مستأجر":
        cur.execute("SELECT id, name FROM tenants")
        tenants = cur.fetchall()
        if tenants:
            tenant_id = st.selectbox("اختر المستأجر", [t[0] for t in tenants], format_func=lambda x: next(t[1] for t in tenants if t[0]==x))
            cur.execute("SELECT name FROM tenants WHERE id = ?", (tenant_id,))
            tenant_name = cur.fetchone()[0]
            st.markdown(f"### كشف حساب: {tenant_name}")
            cur.execute("SELECT due_date, amount, paid_amount, (amount - paid_amount), status FROM payments WHERE tenant_id = ? ORDER BY due_date", (tenant_id,))
            pays = cur.fetchall()
            if pays:
                df = pd.DataFrame(pays, columns=["تاريخ الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة"])
                st.dataframe(df, use_container_width=True)
                total_amount = sum(p[1] for p in pays)
                total_paid = sum(p[2] for p in pays)
                st.write(f"**إجمالي المستحق:** {total_amount:,.2f}")
                st.write(f"**إجمالي المدفوع:** {total_paid:,.2f}")
                st.write(f"**المتبقي:** {total_amount - total_paid:,.2f}")
                
                # تصدير Excel مصحح بحزمة io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("تحميل Excel", data=output.getvalue(), file_name=f"كشف_حساب_{tenant_name}.xlsx", mime="application/vnd.ms-excel")
            else:
                st.info("لا توجد دفعات")
    elif report == "الدفعات المستحقة":
        target = st.date_input("تاريخ الاستحقاق")
        cur.execute('''
            SELECT t.name, p.name, pay.due_date, pay.amount, pay.paid_amount, (pay.amount - pay.paid_amount), pay.status
            FROM payments pay
            JOIN tenants t ON pay.tenant_id = t.id
            JOIN contracts c ON pay.contract_id = c.id
            JOIN properties p ON c.property_id = p.id
            WHERE pay.due_date <= ? AND pay.status != 'مدفوع'
        ''', (target.isoformat(),))
        dues = cur.fetchall()
        if dues:
            df = pd.DataFrame(dues, columns=["المستأجر", "العقار", "الاستحقاق", "المبلغ", "المدفوع", "المتبقي", "الحالة"])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("لا توجد مستحقات")
    elif report == "تقرير المناطق":
        cur.execute('''
            SELECT COALESCE(t.region, 'غير محدد') as region, COUNT(t.id)
            FROM tenants t
            GROUP BY region
        ''')
        regions = cur.fetchall()
        if regions:
            df = pd.DataFrame(regions, columns=["المنطقة", "عدد المستأجرين"])
            st.dataframe(df, use_container_width=True)
    elif report == "الإيرادات":
        from_date = st.date_input("من", value=date.today().replace(day=1))
        to_date = st.date_input("إلى", value=date.today())
        cur.execute("SELECT receipt_date, tenant_id, amount, payment_method FROM receipts WHERE receipt_date BETWEEN ? AND ?", (from_date.isoformat(), to_date.isoformat()))
        recs = cur.fetchall()
        if recs:
            df = pd.DataFrame(recs, columns=["التاريخ", "المستأجر ID", "المبلغ", "الطريقة"])
            st.dataframe(df, use_container_width=True)
            total = sum(r[2] for r in recs)
            st.write(f"**الإجمالي:** {total:,.2f}")
        else:
            st.info("لا توجد إيرادات")

# ---------- النسخ الاحتياطي ----------
elif menu == "نسخ احتياطي":
    st.subheader("💾 نسخ احتياطي يدوي")
    with open('rentals.db', 'rb') as f:
        db_bytes = f.read()
    st.download_button("تحميل قاعدة البيانات", data=db_bytes, file_name=f"rentals_backup_{date.today()}.db")
    
    uploaded = st.file_uploader("استعادة نسخة", type=['db'])
    if uploaded:
        if st.button("استعادة"):
            with open('rentals.db', 'wb') as f:
                f.write(uploaded.read())
            st.success("تمت الاستعادة بنجاح")
            st.rerun()