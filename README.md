مشروع نظام إدارة الإيجارات - ملاحظات المشروع
=============================================

## نظرة عامة
تطبيق Streamlit لإدارة عقود إيجار ودفعات وسندات قبض، يستخدم:
- قاعدة البيانات: Turso (libsql) - cloud - عبر HTTP Pipeline API
- المرفقات: تيليجرام (file_id مخزن في DB)
- النسخ الاحتياطي: JSON + gzip على تيليجرام
- الاستضافة: Streamlit Community Cloud
- GitHub: https://github.com/Ameen1919/rent
- رابط التطبيق: https://rentameen.streamlit.app

## بيانات مهمة
- Turso DB: backup2026-09-19
- Turso Account: ameen1920
- Turso Group: rentals-group
- Telegram Bot: @rentsolimanbot
- Chat ID: -10024445645793

## Secrets المطلوبة
TURSO_URL = "https://backup2026-09-19-ameen1920.turso.io"
TURSO_TOKEN = "eyJ..."
[telegram]
bot_token = "..."
chat_id = "-10024445645793"

## التحديات التقنية التي تم حلها
1. libsql-client لا يعمل على Streamlit Cloud (WSServerHandshakeError)
   → الحل: HTTP Pipeline API مباشرة
2. بطء الاتصال → Connection Pooling (requests.Session + HTTPAdapter)
3. كل INSERT يستدعي استعلام إضافي → RETURNING id
4. التقارير بطيئة → execute_batch (طلبات مجمعة)
5. استيراد Excel بطيء → execute_write_batch (دفعات 50 صف)
6. المرفقات تُفقد على Cloud → رفع على Telegram + file_id
7. التواريخ الهجرية تُحسب خطأ → add_hijri_months
8. زر القفل الجانبي في الشمال → CSS RTL مخصص

## الميزات
- تسجيل دخول بأدوار + صلاحيات دقيقة
- إدارة مستأجرين / عقود / عقارات
- عقود ميلادية وهجرية مع تحويل تلقائي
- دفعات مقدمة (is_advance)
- رصيد سابق مُرحّل
- منع تداخل العقود النشطة
- سندات قبض (إضافة/تعديل/حذف كامل)
- كشف حساب يجمع كل العقود
- تقارير: دفعات، إيرادات، ضرائب، مستحقات
- عقود منتهية + دفعات مؤقتة
- نسخ احتياطي JSON على تيليجرام
- تصدير Excel + PDF (RTL)
- استيراد Excel بدفعات (batch 50)
- sidebar على شكل Wafeq (RTL + زر اليمين)

## بنية قاعدة البيانات
- settings, users, tenants, properties
- contracts (مع calendar_type, hijri_*)
- payments (مع is_advance, is_temporary)
- receipts, alerts
- contract_pricing_tiers, additional_fees, contract_discounts

## قواعد مهمة جداً
- ممنوع libsql-client (لا يعمل على Cloud)
- استخدم _clean_turso_url() لتحويل libsql:// → https://
- لا تغلق الاتصال (st.session_state.db_conn)
- استخدم RETURNING id في INSERT لجلب id
- استخدم execute_batch() للـ SELECT المتعددة
- استخدم execute_write_batch() للـ INSERT/UPDATE/DELETE المتعددة
- المرفقات: file_id يبدأ بـ AgAC / BQAC / BAAC
- التواريخ في DB: نص ISO (YYYY-MM-DD)
- الهجري للإدخال: dd-mm-yyyy
- RTL sidebar: CSS في أعلى app.py

## الأفكار المستقبلية
- [ ] تقارير رسومية
- [ ] تنبيهات تلقائية على تيليجرام
- [ ] سجل تدقيق (Audit Log)
- [ ] QR / باركود
- [ ] نسخ احتياطي تلقائي يومي
