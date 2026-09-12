elif menu == "نسخ احتياطي":
    st.subheader("💾 النسخ الاحتياطي")
    if not has_permission(current_user_id, "نسخ احتياطي"): st.error("لا تملك صلاحية")
    else:
        # ====== معلومات الحدود ======
        st.info("""
        ℹ️ **حدود Telegram Bot API:**
        - الرفع المباشر: حتى **50 ميجابايت**
        - التحميل: حتى **20 ميجابايت**
        
        ✅ النظام يقوم **بضغط قاعدة البيانات تلقائياً** قبل الرفع (عادة يقل الحجم بنسبة 80-90%).
        إذا استمر الحجم أكبر من 50 ميجا، سيتم **تقسيم الملف تلقائياً** إلى أجزاء.
        """)

        st.markdown("---")
        c1, c2 = st.columns(2)

        # ====== تنزيل نسخة احتياطية (محلية) ======
        with c1:
            st.markdown("### 📥 تنزيل نسخة محلية")
            try:
                compressed_data, orig_size, comp_size = create_compressed_backup()
                if compressed_data:
                    orig_mb = orig_size / (1024 * 1024)
                    comp_mb = comp_size / (1024 * 1024)
                    ratio = (1 - comp_size / orig_size) * 100 if orig_size > 0 else 0
                    st.write(f"📊 **حجم قاعدة البيانات الأصلي:** {orig_mb:.2f} MB")
                    st.write(f"📦 **الحجم بعد الضغط:** {comp_mb:.2f} MB (توفير {ratio:.1f}%)")
                    st.download_button(
                        "⬇️ تحميل النسخة المضغوطة (.gz)",
                        data=compressed_data,
                        file_name=f"backup_{date.today()}.db.gz",
                        mime="application/gzip",
                        key="dl_backup_gz"
                    )
                    # زر إضافي للنسخة غير المضغوطة
                    with open("rentals.db", "rb") as f:
                        raw_data = f.read()
                    st.download_button(
                        "⬇️ تحميل النسخة الأصلية (غير مضغوطة)",
                        data=raw_data,
                        file_name=f"backup_{date.today()}.db",
                        mime="application/octet-stream",
                        key="dl_backup_raw"
                    )
                else:
                    st.error("فشل إنشاء النسخة")
            except FileNotFoundError:
                st.warning("لا توجد قاعدة بيانات بعد")

        # ====== استعادة نسخة (محلية) ======
        with c2:
            st.markdown("### 📤 استعادة نسخة محلية")
            st.caption("اختر ملف .db عادي أو .db.gz مضغوط")
            uf = st.file_uploader("اختر ملف النسخة", type=["db", "sqlite", "gz"], key="restore_up")
            if uf:
                file_bytes = uf.read()
                file_name = uf.name.lower()
                is_gz = file_name.endswith(".gz") or (len(file_bytes) > 2 and file_bytes[:2] == b'\x1f\x8b')
                if is_gz:
                    try:
                        decompressed = gzip.decompress(file_bytes)
                        st.success(f"✅ الملف مضغوط - الحجم بعد فك الضغط: {len(decompressed)/(1024*1024):.2f} MB")
                        if st.button("🔄 استعادة الملف المضغوط", key="btn_restore_gz"):
                            with open("rentals.db", "wb") as f:
                                f.write(decompressed)
                            st.cache_data.clear()
                            st.toast("تمت الاستعادة بنجاح", icon="✅")
                            time.sleep(1)
                            st.rerun()
                    except Exception as e:
                        st.error(f"فشل فك الضغط: {e}")
                else:
                    if st.button("🔄 استعادة النسخة", key="btn_restore_raw"):
                        with open("rentals.db", "wb") as f:
                            f.write(file_bytes)
                        st.cache_data.clear()
                        st.toast("تمت الاستعادة بنجاح", icon="✅")
                        time.sleep(1)
                        st.rerun()

        st.markdown("---")

        # ====== النسخ عبر تيليجرام ======
        st.subheader("📱 النسخ الاحتياطي عبر تيليجرام")

        if not telegram_bot_token or not telegram_chat_id:
            st.warning("⚠️ أدخل بيانات تيليجرام (Bot Token + Chat ID) في صفحة الإعدادات أولاً")
        else:
            # عرض حجم النسخة المضغوطة قبل الرفع
            compressed_data, orig_size, comp_size = create_compressed_backup()
            if compressed_data:
                comp_mb = comp_size / (1024 * 1024)
                orig_mb = orig_size / (1024 * 1024)
                st.markdown(f"**حجم قاعدة البيانات الحالي:** {orig_mb:.2f} MB")
                st.markdown(f"**الحجم المضغوط المتوقع:** {comp_mb:.2f} MB")

                # تحذير حسب الحجم
                if comp_mb <= 20:
                    st.success(f"✅ الحجم أقل من 20 ميجا - الرفع والاستعادة سيعملان بسلاسة")
                    st.info(f"📌 سيتم رفع ملف واحد بحجم {comp_mb:.2f} ميجا")
                    needs_chunks = False
                    chunk_size = None
                elif comp_mb <= 50:
                    st.warning(f"⚠️ الحجم بين 20 و 50 ميجا - الرفع سيعمل لكن الاستعادة ستفشل بـ getFile")
                    st.info(f"📌 سيتم تقسيم الملف إلى أجزاء بحجم 15 ميجا (لضمان الاستعادة)")
                    needs_chunks = True
                    chunk_size = 15 * 1024 * 1024
                else:
                    st.warning(f"⚠️ الحجم أكبر من 50 ميجا - سيتم تقسيم الملف تلقائياً")
                    st.info(f"📌 سيتم تقسيم الملف إلى أجزاء بحجم 15 ميجا")
                    needs_chunks = True
                    chunk_size = 15 * 1024 * 1024

            col_up, col_down = st.columns(2)

            # ====== رفع إلى تيليجرام ======
            with col_up:
                st.markdown("### ⬆️ رفع النسخة إلى تيليجرام")
                if st.button("🚀 رفع النسخة المضغوطة", key="btn_tg_up", use_container_width=True):
                    with st.spinner("جاري إعداد النسخة والرفع..."):
                        try:
                            data, _, csize = create_compressed_backup()
                            if not data:
                                st.error("فشل إنشاء النسخة")
                            else:
                                session_id = int(time.time())
                                if csize <= 50 * 1024 * 1024:
                                    # ملف واحد
                                    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendDocument"
                                    files = {'document': (f"backup_{session_id}.db.gz", data, 'application/gzip')}
                                    d = {
                                        'chat_id': telegram_chat_id,
                                        'caption': f"نسخة احتياطية {datetime.now():%Y-%m-%d %H:%M} - حجم {csize/(1024*1024):.2f} MB"
                                    }
                                    resp = requests.post(url, files=files, data=d, timeout=300)
                                    if resp.status_code == 200:
                                        fid = resp.json().get('result', {}).get('document', {}).get('file_id')
                                        if fid:
                                            save_setting('telegram_file_id', fid)
                                            save_setting('telegram_session_id', str(session_id))
                                            save_setting('telegram_chunks', "1")
                                            st.success(f"✅ تم الرفع بنجاح ({csize/(1024*1024):.2f} MB)")
                                            st.code(f"File ID: {fid}", language=None)
                                        else:
                                            st.error("فشل استخراج File ID")
                                    else:
                                        st.error(f"فشل الرفع: {resp.text[:200]}")
                                else:
                                    # تقسيم إلى أجزاء
                                    chunks = split_into_chunks(data, chunk_size)
                                    st.info(f"📦 تم تقسيم الملف إلى {len(chunks)} أجزاء")
                                    progress = st.progress(0)
                                    status_txt = st.empty()
                                    file_ids = []
                                    for idx, chunk in enumerate(chunks, 1):
                                        status_txt.text(f"رفع الجزء {idx}/{len(chunks)}...")
                                        filename = f"backup_{session_id}_part{idx}of{len(chunks)}.bin.gz"
                                        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendDocument"
                                        files = {'document': (filename, chunk, 'application/gzip')}
                                        d = {'chat_id': telegram_chat_id, 'caption': f"الجزء {idx}/{len(chunks)}"}
                                        r = requests.post(url, files=files, data=d, timeout=300)
                                        if r.status_code == 200:
                                            fid = r.json().get('result', {}).get('document', {}).get('file_id')
                                            if fid: file_ids.append(fid)
                                        progress.progress(idx / len(chunks))
                                    if len(file_ids) == len(chunks):
                                        save_setting('telegram_file_id', ",".join(file_ids))
                                        save_setting('telegram_session_id', str(session_id))
                                        save_setting('telegram_chunks', str(len(chunks)))
                                        st.success(f"✅ تم رفع {len(chunks)} أجزاء بنجاح")
                                        with st.expander("عرض معرفات الأجزاء"):
                                            for i, fid in enumerate(file_ids, 1):
                                                st.code(f"جزء {i}: {fid}", language=None)
                                    else:
                                        st.error(f"تم رفع {len(file_ids)} من {len(chunks)} أجزاء")
                        except Exception as e:
                            st.error(f"حدث خطأ: {str(e)}")

            # ====== استعادة من تيليجرام ======
            with col_down:
                st.markdown("### ⬇️ استعادة النسخة من تيليجرام")
                st.caption("سيتم استخدام File ID المحفوظ تلقائياً")

                # عرض معرّف الملف الحالي
                saved_fid = settings.get('telegram_file_id', '')
                saved_chunks = settings.get('telegram_chunks', '1')
                if saved_fid:
                    with st.expander("معرّف الملف المحفوظ"):
                        st.code(saved_fid, language=None)
                        st.text(f"عدد الأجزاء: {saved_chunks}")

                if st.button("🔄 استعادة النسخة", key="btn_tg_down", use_container_width=True):
                    if not saved_fid:
                        st.error("لا يوجد File ID محفوظ. قم برفع نسخة أولاً أو أدخل المعرّف يدوياً في الإعدادات.")
                    else:
                        with st.spinner("جاري التحميل والاستعادة..."):
                            try:
                                file_ids = saved_fid.split(",")
                                num_chunks = len(file_ids)
                                if num_chunks == 1:
                                    st.text("تحميل الملف...")
                                    data = download_file_from_telegram(telegram_bot_token, file_ids[0].strip())
                                    st.text(f"تم التحميل ({len(data)/(1024*1024):.2f} MB) - جاري فك الضغط...")
                                    restore_from_compressed(data)
                                    st.success("✅ تمت الاستعادة بنجاح")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.text(f"تحميل {num_chunks} أجزاء...")
                                    progress = st.progress(0)
                                    all_data = b""
                                    for i, fid in enumerate(file_ids, 1):
                                        st.text(f"تحميل الجزء {i}/{num_chunks}...")
                                        chunk = download_file_from_telegram(telegram_bot_token, fid.strip())
                                        all_data += chunk
                                        progress.progress(i / num_chunks)
                                    st.text(f"إجمالي الحجم: {len(all_data)/(1024*1024):.2f} MB - جاري فك الضغط...")
                                    restore_from_compressed(all_data)
                                    st.success("✅ تمت الاستعادة بنجاح")
                                    time.sleep(1)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"فشل الاستعادة: {str(e)}")