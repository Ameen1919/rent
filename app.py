import sqlite3
from datetime import datetime
import pandas as pd
from dateutil.relativedelta import relativedelta
import streamlit as st

# إعداد الصفحة
st.set_page_config(
    page_title="نظام إدارة العقارات والمستأجرين", page_icon="🏢", layout="wide"
)


# دالة الاتصال بقاعدة البيانات مع تحسينات الأداء (WAL Mode)
def get_conn():
  conn = sqlite3.connect("rentals.db", timeout=10)
  conn.execute("PRAGMA journal_mode=WAL;")
  conn.execute("PRAGMA synchronous=NORMAL;")
  return conn


# إنشاء الجداول والفهارس (تنفذ مرة واحدة بكفاءة عالية)
@st.cache_resource
def init_db():
  conn = get_conn()
  cursor = conn.cursor()

  # جدول المستأجرين
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            unit_no TEXT
        )
    """)

  # جدول العقود
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            amount REAL,
            start_date TEXT,
            end_date TEXT,
            status TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id)
        )
    """)

  # جدول المدفوعات
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER,
            paid_amount REAL,
            payment_date TEXT,
            FOREIGN KEY (contract_id) REFERENCES contracts (id)
        )
    """)

  # إنشاء فهارس (Indexes) لتسريع البحث بشكل كبير جداً وتخفيف ضغط المعالج
  cursor.execute(
      "CREATE INDEX IF NOT EXISTS idx_contracts_tenant ON contracts"
      " (tenant_id);"
  )
  cursor.execute(
      "CREATE INDEX IF NOT EXISTS idx_payments_contract ON payments"
      " (contract_id);"
  )

  conn.commit()
  conn.close()


# تشغيل تهيئة القاعدة عند بدء التطبيق
init_db()


# دوال جلب البيانات مع التخزين المؤقت (Caching) لتوفير موارد الـ CPU
@st.cache_data(ttl=300)
def load_tenants():
  conn = get_conn()
  df = pd.read_sql_query("SELECT * FROM tenants", conn)
  conn.close()
  return df


@st.cache_data(ttl=300)
def load_contracts():
  conn = get_conn()
  query = """
        SELECT c.id, t.name as tenant_name, c.amount, c.start_date, c.end_date, c.status
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
    """
  df = pd.read_sql_query(query, conn)
  conn.close()
  return df


@st.cache_data(ttl=300)
def load_payments():
  conn = get_conn()
  query = """
        SELECT p.id, t.name as tenant_name, p.paid_amount, p.payment_date
        FROM payments p
        JOIN contracts c ON p.contract_id = c.id
        JOIN tenants t ON c.tenant_id = t.id
    """
  df = pd.read_sql_query(query, conn)
  conn.close()
  return df


# 🎨 واجهة المستخدم
st.title("🏢 النظام المحسّن لإدارة العقارات والمستأجرين")

menu = ["لوحة التحكم", "المستأجرين", "العقود", "المدفوعات", "النسخ الاحتياطي"]
choice = st.sidebar.selectbox("القائمة الرئيسية", menu)

if choice == "لوحة التحكم":
  st.subheader("📊 ملخص النظام العام")
  col1, col2, col3 = st.columns(3)

  df_tenants = load_tenants()
  df_contracts = load_contracts()

  with col1:
    st.metric("إجمالي المستأجرين", len(df_tenants))
  with col2:
    active_contracts = (
        len(df_contracts[df_contracts["status"] == "نشط"])
        if not df_contracts.empty
        else 0
    )
    st.metric("العقود النشطة", active_contracts)
  with col3:
    total_rev = df_contracts["amount"].sum() if not df_contracts.empty else 0
    st.metric("إجمالي قيمة العقود", f"{total_rev:,.2f} ر.س")

elif choice == "المستأجرين":
  st.subheader("👥 إدارة المستأجرين")

  with st.form("add_tenant_form", clear_on_submit=True):
    name = st.text_input("اسم المستأجر")
    phone = st.text_input("رقم الهاتف")
    unit_no = st.text_input("رقم الوحدة / الغرفة")
    submit = st.form_submit_button("إضافة مستأجر جديد")

    if submit:
      if name.strip():
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tenants (name, phone, unit_no) VALUES (?, ?, ?)",
            (name, phone, unit_no),
        )
        conn.commit()
        conn.close()
        st.cache_data.clear()  # تفريغ الكاش لتحديث البيانات فوراً
        st.success("تم إضافة المستأجر بنجاح!")
        st.rerun()  # إعادة تشغيل آمنة وموجهة بعد الإضافة فقط
      else:
        st.warning("يرجى إدخال اسم المستأجر على الأقل.")

  st.markdown("---")
  st.dataframe(load_tenants(), use_container_width=True)

elif choice == "العقود":
  st.subheader("📄 إدارة العقود")
  df_tenants = load_tenants()

  if df_tenants.empty:
    st.warning("⚠️ يجب إضافة مستأجرين أولاً قبل إنشاء العقود.")
  else:
    with st.form("add_contract_form", clear_on_submit=True):
      tenant_dict = dict(zip(df_tenants["name"], df_tenants["id"]))
      selected_tenant = st.selectbox(
          "اختر المستأجر", list(tenant_dict.keys())
      )
      amount = st.number_input(
          "قيمة العقد الإجمالية", min_value=0.0, step=100.0, format="%.2f"
      )
      start_date = st.date_input("تاريخ بداية العقد")
      duration_months = st.number_input(
          "مدة العقد (بالشهور)", min_value=1, value=12
      )
      submit_contract = st.form_submit_button("حفظ وحساب العقد")

      if submit_contract:
        end_date = start_date + relativedelta(months=int(duration_months))
        tenant_id = tenant_dict[selected_tenant]

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
                    INSERT INTO contracts (tenant_id, amount, start_date, end_date, status)
                    VALUES (?, ?, ?, ?, ?)
                """,
            (tenant_id, amount, str(start_date), str(end_date), "نشط"),
        )
        conn.commit()
        conn.close()
        st.cache_data.clear()
        st.success("تم حفظ العقد بنجاح!")
        st.rerun()

  st.markdown("---")
  st.dataframe(load_contracts(), use_container_width=True)

elif choice == "المدفوعات":
  st.subheader("💰 تسجيل المدفوعات والتحصيلات")
  df_contracts = load_contracts()

  if df_contracts.empty:
    st.warning("⚠️ لا توجد عقود مسجلة لتسجيل دفعات لها.")
  else:
    with st.form("add_payment_form", clear_on_submit=True):
      contract_ids = df_contracts["id"].tolist()
      selected_cid = st.selectbox("رقم العقد / المستأجر", contract_ids)
      paid_amount = st.number_input(
          "المبلغ المسدد", min_value=0.0, step=50.0, format="%.2f"
      )
      payment_date = st.date_input("تاريخ السداد")
      submit_payment = st.form_submit_button("تسجيل دفعة السداد")

      if submit_payment:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
                    INSERT INTO payments (contract_id, paid_amount, payment_date)
                    VALUES (?, ?, ?)
                """,
            (selected_cid, paid_amount, str(payment_date)),
        )
        conn.commit()
        conn.close()
        st.cache_data.clear()
        st.success("تم تسجيل الدفعة بنجاح!")
        st.rerun()

  st.markdown("---")
  st.dataframe(load_payments(), use_container_width=True)

elif choice == "النسخ الاحتياطي":
  st.subheader("💾 النسخ الاحتياطي للبيانات")
  st.info(
      "يمكنك تحميل نسخة من قاعدة البيانات وحفظها لديك كنسخة احتياطية آمنة في"
      " أي وقت."
  )
  if st.button("توليد رابط التحميل للنسخة الاحتياطية"):
    with open("rentals.db", "rb") as f:
      st.download_button(
          label="⬇️ اضغط هنا لتحميل ملف قاعدة البيانات (rentals.db)",
          data=f,
          file_name=f"rentals_backup_{datetime.now().strftime('%Y-%m-%d')}.db",
          mime="application/octet-stream",
      )