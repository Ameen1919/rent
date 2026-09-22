مشروع نظام إدارة الإيجارات - ملاحظات المشروع
=============================================

## نظرة عامة
تطبيق Streamlit لإدارة عقود إيجار ودفعات وسندات قبض:
- قاعدة البيانات: Turso (libsql) - cloud - HTTP Pipeline API + retry
- المرفقات: تيليجرام (file_id في DB)
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

## requirements.txt
streamlit
pandas
requests
hijri-converter
reportlab
arabic-reshaper
python-bidi
xlsxwriter
numpy
python-dateutil
openpyxl

## التحديات التقنية التي تم حلها
1. libsql-client لا يعمل على Cloud → HTTP Pipeline API
2. بطء الاتصال → Connection Pooling (requests.Session + HTTPAdapter)
3. كل INSERT يستدعي استعلام إضافي → RETURNING id
4. التقارير بطيئة → execute_batch (طلبات مجمعة)
5. استيراد Excel بطيء → execute_write_batch (دفعات 50 صف)
6. المرفقات تُفقد → رفع على Telegram + file_id
7. التواريخ الهجرية → add_hijri_months
8. زر القفل الشمالي → CSS RTL
9. انقطاع الاتصال (ProtocolError) → _safe_post مع retry تلقائي 3 مرات
10. مكتبة openpyxl → مطلوبة في requirements لاستيراد Excel

## قواعد مهمة جداً
- ممنوع libsql-client
- استخدم _clean_turso_url() لتحويل libsql:// → https://
- لا تغلق الاتصال (st.session_state.db_conn)
- استخدم RETURNING id في INSERT
- استخدم execute_batch() و execute_write_batch()
- استخدم _safe_post() مع retry (موجودة في WrappedConnection)
- المرفقات: file_id يبدأ بـ AgAC / BQAC / BAAC
- التواريخ في DB: نص ISO (YYYY-MM-DD)
- الهجري للإدخال: dd-mm-yyyy
- RTL sidebar: CSS في أعلى app.py

## الميزات
- تسجيل دخول بأدوار + صلاحيات دقيقة
- إدارة مستأجرين / عقود / عقارات
- عقود ميلادية وهجرية
- دفعات مقدمة + رصيد سابق
- منع تداخل العقود
- سندات قبض (إضافة/تعديل/حذف)
- كشف حساب يجمع كل العقود
- تقارير: دفعات، إيرادات، ضرائب، مستحقات
- عقود منتهية + دفعات مؤقتة
- نسخ احتياطي على Telegram
- تصدير Excel + PDF RTL
- استيراد Excel بدفعات
- Sidebar بتصميم Wafeq

## بنية قاعدة البيانات
settings, users, tenants, properties
contracts (calendar_type, hijri_start_date, hijri_end_date)
payments (is_advance, is_temporary)
receipts, alerts
contract_pricing_tiers, additional_fees, contract_discounts

## الأفكار المستقبلية
- [ ] تقارير رسومية
- [ ] تنبيهات تلقائية على تيليجرام
- [ ] سجل تدقيق (Audit Log)
- [ ] QR / باركود
- [ ] نسخ احتياطي تلقائي يومي
