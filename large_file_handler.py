import os
import asyncio
import math
from telegram import Update
from telegram.ext import ContextTypes
import yt_dlp

class LargeFileHandler:
    def __init__(self, max_size_mb=2000):  # 2 جيجا
        self.max_size_mb = max_size_mb
        self.chunk_size_mb = 500  # تقسيم إلى أجزاء 500 ميجا
        
    async def check_file_size(self, url):
        """فحص حجم الملف قبل التحميل"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
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
                    'title': info.get('title', 'Unknown')
                }
        except Exception as e:
            return None

    async def handle_large_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url, video_info):
        """معالجة الملفات الكبيرة"""
        file_info = await self.check_file_size(url)
        
        if not file_info:
            await update.message.reply_text("❌ لا يمكن تحديد حجم الملف!")
            return
        
        size_mb = file_info['size_mb']
        
        if size_mb == 0:
            await update.message.reply_text("⚠️ حجم الملف غير معروف، سأحاول التحميل...")
            return await self.download_with_monitoring(update, url, video_info)
        
        if size_mb > self.max_size_mb:
            return await self.handle_oversized_file(update, file_info, url)
        elif size_mb > 1000:  # أكبر من 1 جيجا
            return await self.handle_large_download(update, file_info, url, video_info)
        else:
            return await self.download_with_monitoring(update, url, video_info)

    async def handle_oversized_file(self, update, file_info, url):
        """معالجة الملفات الأكبر من 2 جيجا"""
        size_gb = file_info['size_mb'] / 1024
        
        message = f"""
🚫 **الملف كبير جداً!**

📁 **الحجم:** {size_gb:.1f} جيجابايت
⚠️ **الحد الأقصى:** 2 جيجابايت

🔧 **الحلول المتاحة:**
        """
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [InlineKeyboardButton("📱 جودة متوسطة (720p)", callback_data=f"compress_720_{update.effective_user.id}")],
            [InlineKeyboardButton("📺 جودة منخفضة (480p)", callback_data=f"compress_480_{update.effective_user.id}")],
            [InlineKeyboardButton("🎵 صوت فقط (MP3)", callback_data=f"audio_only_{update.effective_user.id}")],
            [InlineKeyboardButton("✂️ تقسيم إلى أجزاء", callback_data=f"split_file_{update.effective_user.id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup)

    async def handle_large_download(self, update, file_info, url, video_info):
        """معالجة التحميلات الكبيرة (1-2 جيجا)"""
        size_mb = file_info['size_mb']
        estimated_time = size_mb / 10  # تقدير 10 ميجا/ثانية
        
        warning_message = f"""
⚠️ **ملف كبير الحجم!**

📁 **الحجم:** {size_mb:.0f} ميجابايت
⏱️ **الوقت المتوقع:** {estimated_time/60:.1f} دقيقة
💾 **مساحة مطلوبة:** {size_mb*1.5:.0f} ميجا (مؤقتاً)

🤔 **هل تريد المتابعة؟**
        """
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [InlineKeyboardButton("✅ نعم، حمل الملف", callback_data=f"proceed_large_{update.effective_user.id}")],
            [InlineKeyboardButton("📱 جودة أقل", callback_data=f"lower_quality_{update.effective_user.id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # حفظ معلومات الملف
        context.user_data[f'large_file_{update.effective_user.id}'] = {
            'url': url,
            'info': video_info,
            'file_info': file_info
        }
        
        await update.message.reply_text(warning_message, reply_markup=reply_markup)

    async def download_with_monitoring(self, update, url, video_info):
        """تحميل مع مراقبة التقدم والحجم"""
        progress_msg = await update.message.reply_text("🚀 بدء التحميل الكبير...")
        
        # إعدادات خاصة للملفات الكبيرة
        ydl_opts = {
            'outtmpl': f'downloads/large_video_{update.effective_user.id}_{int(asyncio.get_event_loop().time())}.%(ext)s',
            'format': 'best[filesize<2000M]/best',  # تفضيل الملفات أقل من 2 جيجا
            'progress_hooks': [lambda d: asyncio.create_task(self.enhanced_progress_hook(d, progress_msg))],
            'socket_timeout': 60,
            'retries': 3,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            # البحث عن الملف المحمل
            download_dir = 'downloads'
            files = [f for f in os.listdir(download_dir) if f.startswith(f'large_video_{update.effective_user.id}')]
            
            if files:
                file_path = os.path.join(download_dir, files[0])
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # بالميجا
                
                if file_size > 2000:  # أكبر من 2 جيجا
                    await progress_msg.edit_text("⚠️ الملف كبير جداً! جاري الضغط...")
                    compressed_path = await self.compress_video(file_path)
                    os.remove(file_path)  # حذف الملف الأصلي
                    file_path = compressed_path
                
                await self.send_large_file(update, file_path, video_info, progress_msg)
                os.remove(file_path)  # تنظيف
                
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
                    
                    progress_text = f"""
📥 **تحميل ملف كبير...**

📊 **التقدم:** {percent}
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

    async def compress_video(self, input_path):
        """ضغط الفيديو لتقليل الحجم"""
        output_path = input_path.replace('.', '_compressed.')
        
        # استخدام ffmpeg للضغط
        import subprocess
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-c:v', 'libx264',
            '-crf', '28',  # جودة متوسطة
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '128k',
            output_path,
            '-y'  # استبدال الملف إذا كان موجوداً
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return output_path
        except subprocess.CalledProcessError:
            return input_path  # إرجاع الملف الأصلي في حالة فشل الضغط

    async def send_large_file(self, update, file_path, video_info, progress_msg):
        """إرسال الملفات الكبيرة مع معلومات إضافية"""
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
                await update.message.reply_audio(
                    audio=open(file_path, 'rb'),
                    caption=caption,
                    title=video_info['title']
                )
            else:
                await update.message.reply_video(
                    video=open(file_path, 'rb'),
                    caption=caption,
                    supports_streaming=True  # دعم التشغيل أثناء التحميل
                )
            
            await progress_msg.edit_text("✅ تم الإرسال بنجاح!")
            
        except Exception as e:
            if "too large" in str(e).lower():
                await progress_msg.edit_text("❌ الملف كبير جداً للإرسال! جرب جودة أقل.")
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
