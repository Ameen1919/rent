# مشروع نظام إدارة الإيجارات - ملاحظات المشروع

## نظرة عامة
تطبيق Streamlit لإدارة عقود إيجار ودفعات وسندات قبض، يستخدم:
- **قاعدة البيانات**: Turso (libsql) - cloud - عبر HTTP Pipeline API (بدون WebSocket)
- **المرفقات**: تيليجرام (file_id في قاعدة البيانات)
- **النسخ الاحتياطي**: JSON + gzip على تيليجرام + تحميل يدوي
- **الاستضافة**: Streamlit Community Cloud
- **GitHub**: https://github.com/Ameen1919/rent
- **رابط التطبيق**: https://rentameen.streamlit.app
- **Turso Database**: backup2026-09-19 (ameen1920, rentals-group)
- **Telegram Bot**: @rentsolimanbot
- **Telegram Group**: Ameen and inventory backup (chat_id: -10024445645793)

## البنية التقنية
- **الملف الرئيسي**: app.py
- **المكتبات**: streamlit, pandas, requests, hijri-converter, reportlab, arabic-reshaper, python-bidi
- **Secrets**: TURSO_URL, TURSO_TOKEN + [telegram] (bot_token, chat_id)

## التحديات التقنية التي تم حلها
1. **libsql-client لا يعمل على Streamlit Cloud** (WSServerHandshakeError)
   → تم الحل بالاتصال المباشر عبر HTTP Pipeline API بدون مكتبة libsql
2. **بطء الاتصال بسبب WebSocket**
   → تم استخدام requests.Session مع Connection Pooling
3. **كل INSERT يحتاج استعلام إضافي لـ last_insert_rowid**
   → استخدام RETURNING id
4. **التقارير بطيئة بسبب استعلامات متعددة**
   → Batch Requests في طلب HTTP واحد
5. **المرفقات تُفقد على Cloud**
   → تُرفع على تيليجرام ويُخزن file_id
6. **التواريخ الهجرية** تُحسب في التقويم الميلادي
   → استخدام add_hijri_months للدفعات الهجرية

## الميزات الحالية
- تسجيل دخول بأدوار (مدير/محاسب/مشاهد) + صلاحيات دقيقة
- إدارة مستأجرين، عقود، عقارات
- دعم عقود ميلادية + هجرية مع تحويل تلقائي
- دفعات مقدمة (is_advance)
- رصيد سابق مُرحّل عند إنشاء عقد جديد
- منع تداخل العقود النشطة لنفس المستأجر
- سندات القبض (إنشاء/تعديل/حذف كامل)
- كشف حساب مستأجر (يشمل كل العقود)
- تقارير: دفعات/إيرادات/ضرائب/مستحقات
- عقود منتهية + دفعات مؤقتة
- نسخ احتياطي JSON مضغوط على تيليجرام
- تصدير Excel + PDF (RTL عربي)

## بنية قاعدة البيانات (Turso)
- settings, users
- tenants, properties, contracts
- payments, receipts
- alerts, contract_pricing_tiers
- additional_fees, contract_discounts

## قواعد مهمة
- **ممنوع استخدام libsql-client** (لا يعمل على Streamlit Cloud)
- استخدم `_clean_turso_url()` لتحويل libsql:// → https://
- **لا تغلق الاتصال** — محفوظ في st.session_state.db_conn
- **استخدم `RETURNING id`** في INSERT لجلب الـ id
- **استخدم `conn.execute_batch()`** في التقارير
- المرفقات: file_id يبدأ بـ AgAC/BQAC/BAAC
- التواريخ في DB: نص ISO (YYYY-MM-DD)
- التواريخ الهجرية للإدخال: dd-mm-yyyy

## التحسينات المطبقة للأداء
1. **Connection Pooling**: requests.Session مع HTTPAdapter
2. **RETURNING id**: بدل last_insert_rowid المنفصل
3. **Batch Requests**: تنفيذ عدة SELECT في طلب واحد
4. **Caching**: st.cache_data(ttl=30-120)

## الأفكار المستقبلية
- [ ] تقارير رسومية (Charts)
- [ ] تنبيهات تلقائية على تيليجرام عند انتهاء العقود
- [ ] صلاحيات دقيقة لكل مستخدم
- [ ] سجل تدقيق (Audit Log)
- [ ] الباركود / QR للمستأجرين
- [ ] دفع عبر الإنترنت
- [ ] نسخ احتياطي تلقائي يومي
