import os
import asyncio
import math
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import yt_dlp
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class LargeFileHandler:
    def __init__(self, max_size_mb=2000):  # 2 جيجا
        self.max_size_mb = max_size_mb
        self.telegram_limit_mb = 50  # حد تلقرام للبوتات
        self.chunk_size_mb = 45  # حجم كل جزء للتقسيم
        
    async def check_file_size(self, url):
        """فحص حجم الملف قبل التحميل"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # البحث عن أفضل جودة متاحة
                formats = info.get('formats', [])
                best_format = None
                file_size = 0
                
                for fmt in formats:
                    if fmt.get('filesize'):
                        if not best_format or fmt.get('height', 0) > best_format.get('height', 0):
                            best_format = fmt
                            file_size = fmt['filesize']
                
                return {
                    'size_bytes': file_size,
                    'size_mb': file_size / (1024 * 1024) if file_size else 0,
                    'format': best_format,
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0)
                }
        except Exception as e:
            logger.error(f"خطأ في فحص حجم الملف: {e}")
            return None

    async def handle_large_file(self, update_or_query, context: ContextTypes.DEFAULT_TYPE, url, video_info):
        """معالجة الملفات الكبيرة - إصلاح المشكلة"""
        # التحقق من نوع الكائن
        if hasattr(update_or_query, 'callback_query'):
            # إذا كان query
            query = update_or_query
            user_id = query.from_user.id
        elif hasattr(update_or_query, 'effective_user'):
            # إذا كان update
            update = update_or_query
            user_id = update.effective_user.id
        else:
            # إذا كان query مباشرة
            query = update_or_query
            user_id = query.from_user.id
        
        file_info = await self.check_file_size(url)
        
        if not file_info:
            await self.download_with_monitoring(update_or_query, url, video_info)
            return
        
        size_mb = file_info['size_mb']
        
        if size_mb == 0:
            await self.download_with_monitoring(update_or_query, url, video_info)
            return
        
        if size_mb > self.max_size_mb:
            await self.handle_oversized_file(update_or_query, file_info, url, context)
        elif size_mb > self.telegram_limit_mb:
            await self.handle_large_download(update_or_query, file_info, url, video_info, context)
        else:
            await self.download_with_monitoring(update_or_query, url, video_info)

    async def handle_oversized_file(self, update_or_query, file_info, url, context):
        """معالجة الملفات الأكبر من 2 جيجا"""
        size_gb = file_info['size_mb'] / 1024
        
        # التحقق من نوع الكائن
        if hasattr(update_or_query, 'callback_query'):
            query = update_or_query
            user_id = query.from_user.id
            send_method = query.edit_message_text
        elif hasattr(update_or_query, 'effective_user'):
            update = update_or_query
            user_id = update.effective_user.id
            send_method = update.message.reply_text
        else:
            query = update_or_query
            user_id = query.from_user.id
            send_method = query.edit_message_text
        
        message = f"""
🚫 **الملف كبير جداً!**

📁 **الحجم:** {size_gb:.1f} جيجابايت
⚠️ **الحد الأقصى:** 2 جيجابايت

🔧 **الحلول المتاحة:**
        """
        
        keyboard = [
            [InlineKeyboardButton("📱 جودة متوسطة (720p)", callback_data=f"compress_720_{user_id}")],
            [InlineKeyboardButton("📺 جودة منخفضة (480p)", callback_data=f"compress_480_{user_id}")],
            [InlineKeyboardButton("🎵 صوت فقط (MP3)", callback_data=f"audio_only_{user_id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # حفظ معلومات الملف
        context.user_data[f'oversized_file_{user_id}'] = {
            'url': url,
            'file_info': file_info
        }
        
        await send_method(message, reply_markup=reply_markup)

    async def handle_large_download(self, update_or_query, file_info, url, video_info, context):
        """معالجة التحميلات الكبيرة (50MB - 2GB)"""
        size_mb = file_info['size_mb']
        estimated_time = size_mb / 10  # تقدير 10 ميجا/ثانية
        
        # التحقق من نوع الكائن
        if hasattr(update_or_query, 'callback_query'):
            query = update_or_query
            user_id = query.from_user.id
            send_method = query.edit_message_text
        elif hasattr(update_or_query, 'effective_user'):
            update = update_or_query
            user_id = update.effective_user.id
            send_method = update.message.reply_text
        else:
            query = update_or_query
            user_id = query.from_user.id
            send_method = query.edit_message_text
        
        warning_message = f"""
⚠️ **ملف كبير الحجم!**

📁 **الحجم:** {size_mb:.0f} ميجابايت ({size_mb/1024:.1f} جيجا)
⏱️ **الوقت المتوقع:** {estimated_time/60:.1f} دقيقة
💾 **مساحة مطلوبة:** {size_mb*1.5:.0f} ميجا (مؤقتاً)

🔧 **خيارات التحميل:**
        """
        
        keyboard = [
            [InlineKeyboardButton("📤 تقسيم وإرسال", callback_data=f"split_send_{user_id}")],
            [InlineKeyboardButton("🗜️ ضغط وإرسال", callback_data=f"compress_send_{user_id}")],
            [InlineKeyboardButton("📱 جودة أقل", callback_data=f"lower_quality_{user_id}")],
            [InlineKeyboardButton("🎵 صوت فقط", callback_data=f"audio_only_{user_id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # حفظ معلومات الملف
        context.user_data[f'large_file_{user_id}'] = {
            'url': url,
            'info': video_info,
            'file_info': file_info
        }
        
        await send_method(warning_message, reply_markup=reply_markup)

    async def download_with_monitoring(self, update_or_query, url, video_info):
        """تحميل مع مراقبة التقدم والحجم"""
        # التحقق من نوع الكائن
        if hasattr(update_or_query, 'callback_query'):
            query = update_or_query
            user_id = query.from_user.id
            progress_msg = await query.edit_message_text("🚀 بدء التحميل...")
            message_obj = query.message
        elif hasattr(update_or_query, 'effective_user'):
            update = update_or_query
            user_id = update.effective_user.id
            progress_msg = await update.message.reply_text("🚀 بدء التحميل...")
            message_obj = update.message
        else:
            query = update_or_query
            user_id = query.from_user.id
            progress_msg = await query.edit_message_text("🚀 بدء التحميل...")
            message_obj = query.message
        
        timestamp = int(datetime.now().timestamp())
        filename = f'downloads/large_video_{user_id}_{timestamp}.%(ext)s'
        
        # إعدادات خاصة للملفات الكبيرة
        ydl_opts = {
            'outtmpl': filename,
            'format': 'best[filesize<2000M]/best',  # تفضيل الملفات أقل من 2 جيجا
            'merge_output_format': 'mp4',
            'socket_timeout': 60,
            'retries': 3,
            'fragment_retries': 5,
            'progress_hooks': [lambda d: asyncio.create_task(self.enhanced_progress_hook(d, progress_msg))],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            # البحث عن الملف المحمل
            download_dir = 'downloads'
            files = [f for f in os.listdir(download_dir) if f.startswith(f'large_video_{user_id}_{timestamp}')]
            
            if files:
                file_path = os.path.join(download_dir, files[0])
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                
                if file_size_mb > self.telegram_limit_mb:
                    await progress_msg.edit_text("📤 الملف كبير، جاري التحضير للإرسال...")
                    await self.handle_large_file_send(message_obj, file_path, video_info, progress_msg)
                else:
                    await self.send_normal_file(message_obj, file_path, video_info, progress_msg)
                
                # تنظيف
                try:
                    os.remove(file_path)
                except:
                    pass
                
        except Exception as e:
            await progress_msg.edit_text(f"❌ فشل التحميل: {str(e)[:100]}...")

    async def enhanced_progress_hook(self, d, progress_msg):
        """شريط تقدم محسن للملفات الكبيرة"""
        if d['status'] == 'downloading':
            try:
                percent = d.get('_percent_str', '0%').strip()
                speed = d.get('_speed_str', 'غير معروف')
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes', 0)
                
                if total > 0:
                    downloaded_mb = downloaded / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    
                    # تقدير الوقت المتبقي
                    if 'speed' in d and d['speed']:
                        remaining_bytes = total - downloaded
                        eta_seconds = remaining_bytes / d['speed']
                        eta_minutes = eta_seconds / 60
                        eta_text = f"⏱️ متبقي: {eta_minutes:.1f} دقيقة"
                    else:
                        eta_text = ""
                    
                    # شريط تقدم بصري
                    progress_bar = self.create_progress_bar(downloaded / total)
                    
                    progress_text = f"""
📥 **تحميل ملف كبير...**

{progress_bar} {percent}

📁 **الحجم:** {downloaded_mb:.0f}/{total_mb:.0f} ميجا
⚡ **السرعة:** {speed}
{eta_text}

💡 **نصيحة:** لا تغلق التطبيق أثناء التحميل
                    """
                else:
                    progress_text = f"📥 جاري التحميل... {percent}\n⚡ السرعة: {speed}"
                
                await progress_msg.edit_text(progress_text)
                
            except Exception:
                pass  # تجاهل أخطاء التحديث

    def create_progress_bar(self, progress, length=20):
        """إنشاء شريط تقدم بصري"""
        filled = int(progress * length)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}]"

    async def handle_large_file_send(self, message_obj, file_path, video_info, progress_msg):
        """معالجة إرسال الملفات الكبيرة"""
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size_mb > 2000:  # أكبر من 2 جيجا
            await progress_msg.edit_text("⚠️ الملف كبير جداً! جاري الضغط...")
            compressed_path = await self.compress_video(file_path)
            if compressed_path and compressed_path != file_path:
                os.remove(file_path)  # حذف الملف الأصلي
                file_path = compressed_path
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size_mb > self.telegram_limit_mb:
            # تقسيم الملف
            await progress_msg.edit_text("✂️ جاري تقسيم الملف...")
            await self.split_and_send_file(message_obj, file_path, video_info, progress_msg)
        else:
            await self.send_normal_file(message_obj, file_path, video_info, progress_msg)

    async def compress_video(self, input_path, target_size_mb=1800):
        """ضغط الفيديو لتقليل الحجم"""
        output_path = input_path.replace('.', '_compressed.')
        
        try:
            # حساب bitrate المطلوب
            probe_cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', input_path
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            duration = float(result.stdout.strip())
            
            # حساب bitrate (بالكيلوبت/ثانية)
            target_bitrate = int((target_size_mb * 8 * 1024) / duration * 0.9)  # 90% للأمان
            
            cmd = [
                'ffmpeg', '-i', input_path,
                '-c:v', 'libx264',
                '-b:v', f'{target_bitrate}k',
                '-maxrate', f'{target_bitrate * 1.2}k',
                '-bufsize', f'{target_bitrate * 2}k',
                '-preset', 'medium',
                '-c:a', 'aac',
                '-b:a', '128k',
                output_path,
                '-y'
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            return output_path
            
        except Exception as e:
            logger.error(f"خطأ في الضغط: {e}")
            return input_path  # إرجاع الملف الأصلي في حالة فشل الضغط

    async def split_and_send_file(self, message_obj, file_path, video_info, progress_msg):
        """تقسيم وإرسال الملف"""
        file_size = os.path.getsize(file_path)
        chunk_size = self.chunk_size_mb * 1024 * 1024  # تحويل إلى بايت
        total_chunks = math.ceil(file_size / chunk_size)
        
        await progress_msg.edit_text(f"📤 جاري إرسال {total_chunks} أجزاء...")
        
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        try:
            with open(file_path, 'rb') as f:
                for i in range(total_chunks):
                    chunk_data = f.read(chunk_size)
                    chunk_filename = f"{base_name}_part{i+1}of{total_chunks}.bin"
                    chunk_path = os.path.join('downloads', chunk_filename)
                    
                    with open(chunk_path, 'wb') as chunk_file:
                        chunk_file.write(chunk_data)
                    
                    # إرسال الجزء
                    caption = f"""
📦 **جزء {i+1} من {total_chunks}**

🎬 **العنوان:** {video_info['title']}
📁 **حجم الجزء:** {len(chunk_data)/(1024*1024):.1f} ميجا

💡 **لدمج الأجزاء:** استخدم أي برنامج دمج ملفات
                    """
                    
                    with open(chunk_path, 'rb') as chunk_file:
                        await message_obj.reply_document(
                            document=chunk_file,
                            filename=chunk_filename,
                            caption=caption
                        )
                    
                    # حذف الجزء المؤقت
                    os.remove(chunk_path)
                    
                    # تحديث التقدم
                    await progress_msg.edit_text(f"📤 تم إرسال {i+1}/{total_chunks} أجزاء...")
            
            # رسالة الانتهاء
            final_message = f"""
✅ **تم إرسال جميع الأجزاء!**

📦 **العدد:** {total_chunks} جزء
🎬 **العنوان:** {video_info['title']}
📁 **الحجم الإجمالي:** {file_size/(1024*1024):.0f} ميجا

🔧 **لدمج الأجزاء:**
1. حمل جميع الأجزاء
2. استخدم برنامج مثل HJSplit أو 7-Zip
3. اختر الجزء الأول وادمج

🤖 شكراً لاستخدام البوت!
            """
            
            await progress_msg.edit_text(final_message)
            
        except Exception as e:
            await progress_msg.edit_text(f"❌ فشل في تقسيم الملف: {str(e)[:100]}...")

    async def send_normal_file(self, message_obj, file_path, video_info, progress_msg):
        """إرسال الملف العادي"""
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        await progress_msg.edit_text(f"📤 جاري الإرسال... ({file_size:.0f} ميجا)")
        
        caption = f"""
✅ **تم التحميل بنجاح!**

🎬 **العنوان:** {video_info['title']}
📁 **الحجم:** {file_size:.0f} ميجابايت
⏱️ **المدة:** {self.format_duration(video_info.get('duration', 0))}

🤖 شكراً لاستخدام البوت!
        """
        
        try:
            if file_path.endswith('.mp3'):
                with open(file_path, 'rb') as audio_file:
                    await message_obj.reply_audio(
                        audio=audio_file,
                        caption=caption,
                        title=video_info['title']
                    )
            else:
                with open(file_path, 'rb') as video_file:
                    await message_obj.reply_video(
                        video=video_file,
                        caption=caption,
                        supports_streaming=True
                    )
            
            await progress_msg.edit_text("✅ تم الإرسال بنجاح!")
            
        except Exception as e:
            if "too large" in str(e).lower():
                await progress_msg.edit_text("❌ الملف كبير جداً! جاري التقسيم...")
                await self.split_and_send_file(message_obj, file_path, video_info, progress_msg)
            else:
                await progress_msg.edit_text(f"❌ فشل الإرسال: {str(e)[:100]}...")

    def format_duration(self, seconds):
        """تنسيق مدة الفيديو"""
        if not seconds:
            return "غير معروف"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    async def handle_compression_callback(self, query, context, quality):
        """معالجة طلبات الضغط"""
        user_id = query.from_user.id
        file_data = context.user_data.get(f'oversized_file_{user_id}') or context.user_data.get(f'large_file_{user_id}')
        
        if not file_data:
            await query.edit_message_text("❌ انتهت صلاحية الجلسة!")
            return
        
        url = file_data['url']
        
        progress_msg = await query.edit_message_text(f"🚀 بدء التحميل بجودة {quality}...")
        
        # إعدادات الجودة
        if quality == "720":
            format_selector = 'best[height<=720]/best'
        elif quality == "480":
            format_selector = 'best[height<=480]/best'
        else:
            format_selector = 'best'
        
        timestamp = int(datetime.now().timestamp())
        filename = f'downloads/compressed_{quality}_{user_id}_{timestamp}.%(ext)s'
        
        ydl_opts = {
            'outtmpl': filename,
            'format': format_selector,
            'merge_output_format': 'mp4',
            'progress_hooks': [lambda d: asyncio.create_task(self.enhanced_progress_hook(d, progress_msg))],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # البحث عن الملف
            download_dir = 'downloads'
            files = [f for f in os.listdir(download_dir) if f.startswith(f'compressed_{quality}_{user_id}_{timestamp}')]
            
            if files:
                file_path = os.path.join(download_dir, files[0])
                video_info = file_data.get('info', {'title': 'فيديو مضغوط', 'duration': 0})
                
                await self.handle_large_file_send(query.message, file_path, video_info, progress_msg)
                
                try:
                    os.remove(file_path)
                except:
                    pass
            else:
                await progress_msg.edit_text("❌ فشل في العثور على الملف المحمل!")
                
        except Exception as e:
            await progress_msg.edit_text(f"❌ فشل التحميل: {str(e)[:100]}...")
