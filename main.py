import asyncio
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp
import aiohttp
import aiofiles
from urllib.parse import urlparse
import re
from datetime import datetime
import json

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VideoDownloaderBot:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.app = Application.builder().token(bot_token).build()
        self.downloads_dir = "downloads"
        self.sessions_dir = "sessions"
        self.stats_file = "stats.json"
        
        # إنشاء المجلدات المطلوبة
        os.makedirs(self.downloads_dir, exist_ok=True)
        os.makedirs(self.sessions_dir, exist_ok=True)
        
        # إحصائيات البوت
        self.stats = self.load_stats()
        
        # رسائل الانتظار المرحة
        self.waiting_messages = [
            "🎬 جاري تحضير الفيديو... اصبر شوية!",
            "⚡ البوت يعمل بسرعة البرق!",
            "🚀 تحميل سريع قادم...",
            "🎯 نحن نعمل على طلبك الآن!",
            "💫 سحر التكنولوجيا في العمل..."
        ]
        
        self.setup_handlers()

    def load_stats(self):
        """تحميل الإحصائيات من الملف"""
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "total_downloads": 0,
                "users": set(),
                "platforms": {"youtube": 0, "twitter": 0, "tiktok": 0, "instagram": 0},
                "start_date": datetime.now().isoformat()
            }

    def save_stats(self):
        """حفظ الإحصائيات"""
        stats_to_save = self.stats.copy()
        stats_to_save["users"] = list(self.stats["users"])
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats_to_save, f, ensure_ascii=False, indent=2)

    def detect_platform(self, url):
        """تحديد نوع المنصة من الرابط"""
        domain = urlparse(url).netloc.lower()
        
        if 'youtube.com' in domain or 'youtu.be' in domain:
            return 'youtube'
        elif 'twitter.com' in domain or 'x.com' in domain:
            return 'twitter'
        elif 'tiktok.com' in domain:
            return 'tiktok'
        elif 'instagram.com' in domain:
            return 'instagram'
        else:
            return 'unknown'

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر البداية"""
        user = update.effective_user
        self.stats["users"].add(user.id)
        
        welcome_text = f"""
🎬 مرحباً {user.first_name}! 

أنا بوت تحميل الفيديوهات السريع والذكي! 🚀

✨ **ما أستطيع فعله:**
• تحميل من يوتيوب 📺
• تحميل من تويتر/X 🐦
• تحميل من تيك توك 🎵
• تحميل من إنستقرام 📸
• تحويل إلى MP3 🎧

📋 **كيفية الاستخدام:**
فقط أرسل لي رابط الفيديو وسأتولى الباقي!

🎯 **مميزات خاصة:**
• تحميل سريع بدون تجميد
• جودات متعددة
• معاينة قبل التحميل
• إحصائيات مفصلة
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
            [InlineKeyboardButton("ℹ️ المساعدة", callback_data="help"),
             InlineKeyboardButton("🔗 شارك البوت", callback_data="share")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def get_video_info(self, url):
        """الحصول على معلومات الفيديو"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'غير معروف'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'uploader': info.get('uploader', 'غير معروف'),
                    'view_count': info.get('view_count', 0),
                    'formats': info.get('formats', [])
                }
        except Exception as e:
            logger.error(f"خطأ في الحصول على معلومات الفيديو: {e}")
            return None

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الروابط المرسلة"""
        url = update.message.text.strip()
        user_id = update.effective_user.id
        
        # التحقق من صحة الرابط
        if not self.is_valid_url(url):
            await update.message.reply_text("❌ الرابط غير صحيح! يرجى إرسال رابط صالح.")
            return
        
        platform = self.detect_platform(url)
        if platform == 'unknown':
            await update.message.reply_text("❌ المنصة غير مدعومة حالياً!")
            return
        
        # رسالة انتظار مرحة
        waiting_msg = await update.message.reply_text("🔍 جاري تحليل الرابط...")
        
        # الحصول على معلومات الفيديو
        video_info = await self.get_video_info(url)
        
        if not video_info:
            await waiting_msg.edit_text("❌ فشل في تحليل الرابط! تأكد من صحة الرابط.")
            return
        
        # عرض معاينة الفيديو
        preview_text = f"""
🎬 **{video_info['title']}**

📺 **القناة:** {video_info['uploader']}
⏱️ **المدة:** {self.format_duration(video_info['duration'])}
👀 **المشاهدات:** {video_info.get('view_count', 0):,}
🌐 **المنصة:** {platform.title()}
        """
        
        # أزرار الخيارات
        keyboard = [
            [InlineKeyboardButton("📹 فيديو عالي الجودة", callback_data=f"download_video_high_{user_id}")],
            [InlineKeyboardButton("📱 فيديو جودة متوسطة", callback_data=f"download_video_medium_{user_id}")],
            [InlineKeyboardButton("🎵 صوت MP3", callback_data=f"download_audio_{user_id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # حفظ معلومات الفيديو في السياق
        context.user_data[f'video_info_{user_id}'] = {
            'url': url,
            'info': video_info,
            'platform': platform
        }
        
        await waiting_msg.edit_text(preview_text, reply_markup=reply_markup)

    def is_valid_url(self, url):
        """التحقق من صحة الرابط"""
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None

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

    async def download_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أزرار التحميل"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = update.effective_user.id
        
        if data == "cancel":
            await query.edit_message_text("❌ تم إلغاء العملية.")
            return
        
        if data == "stats":
            await self.show_stats(query)
            return
        
        if data == "help":
            await self.show_help(query)
            return
        
        if data == "share":
            await self.show_share(query)
            return
        
        # معالجة التحميل
        if data.startswith("download_"):
            await self.process_download(query, context, data, user_id)

    async def process_download(self, query, context, data, user_id):
        """معالجة عملية التحميل"""
        video_data = context.user_data.get(f'video_info_{user_id}')
        
        if not video_data:
            await query.edit_message_text("❌ انتهت صلاحية الجلسة! أرسل الرابط مرة أخرى.")
            return
        
        url = video_data['url']
        video_info = video_data['info']
        platform = video_data['platform']
        
        # تحديث الإحصائيات
        self.stats["total_downloads"] += 1
        self.stats["platforms"][platform] += 1
        self.save_stats()
        
        # رسالة التحميل
        progress_msg = await query.edit_message_text("🚀 بدء التحميل... 0%")
        
        try:
            if "audio" in data:
                file_path = await self.download_audio(url, video_info, progress_msg)
            else:
                quality = "high" if "high" in data else "medium"
                file_path = await self.download_video(url, video_info, quality, progress_msg)
            
            if file_path and os.path.exists(file_path):
                await self.send_file(query, file_path, video_info)
                # حذف الملف بعد الإرسال
                os.remove(file_path)
            else:
                await progress_msg.edit_text("❌ فشل في التحميل! حاول مرة أخرى.")
                
        except Exception as e:
            logger.error(f"خطأ في التحميل: {e}")
            await progress_msg.edit_text("❌ حدث خطأ أثناء التحميل!")

    async def download_video(self, url, video_info, progress_msg, quality="medium"):
        """تحميل الفيديو"""
        filename = f"{self.downloads_dir}/video_{datetime.now().timestamp()}.mp4"
        
        ydl_opts = {
            'outtmpl': filename,
            'format': 'best[height<=720]' if quality == "medium" else 'best',
            'progress_hooks': [lambda d: asyncio.create_task(self.progress_hook(d, progress_msg))],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return filename
        except Exception as e:
            logger.error(f"خطأ في تحميل الفيديو: {e}")
            return None

    async def download_audio(self, url, video_info, progress_msg):
        """تحميل الصوت"""
        filename = f"{self.downloads_dir}/audio_{datetime.now().timestamp()}.mp3"
        
        ydl_opts = {
            'outtmpl': filename,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'progress_hooks': [lambda d: asyncio.create_task(self.progress_hook(d, progress_msg))],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return filename
        except Exception as e:
            logger.error(f"خطأ في تحميل الصوت: {e}")
            return None

    async def progress_hook(self, d, progress_msg):
        """تحديث شريط التقدم"""
        if d['status'] == 'downloading':
            try:
                percent = d.get('_percent_str', '0%').strip()
                speed = d.get('_speed_str', 'غير معروف')
                await progress_msg.edit_text(f"📥 جاري التحميل... {percent}\n⚡ السرعة: {speed}")
            except:
                pass

    async def send_file(self, query, file_path, video_info):
        """إرسال الملف للمستخدم"""
        try:
            caption = f"✅ **تم التحميل بنجاح!**\n\n🎬 {video_info['title']}\n\n🤖 @YourBotUsername"
            
            if file_path.endswith('.mp3'):
                await query.message.reply_audio(
                    audio=open(file_path, 'rb'),
                    caption=caption,
                    title=video_info['title']
                )
            else:
                await query.message.reply_video(
                    video=open(file_path, 'rb'),
                    caption=caption
                )
            
            # زر مشاركة البوت
            keyboard = [[InlineKeyboardButton("🔗 شارك البوت", callback_data="share")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("✅ تم الإرسال بنجاح!", reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"خطأ في إرسال الملف: {e}")
            await query.edit_message_text("❌ فشل في إرسال الملف!")

    async def show_stats(self, query):
        """عرض الإحصائيات"""
        stats_text = f"""
📊 **إحصائيات البوت**

👥 **عدد المستخدمين:** {len(self.stats['users'])}
📥 **إجمالي التحميلات:** {self.stats['total_downloads']}

🌐 **التحميلات حسب المنصة:**
📺 يوتيوب: {self.stats['platforms']['youtube']}
🐦 تويتر: {self.stats['platforms']['twitter']}
🎵 تيك توك: {self.stats['platforms']['tiktok']}
📸 إنستقرام: {self.stats['platforms']['instagram']}

📅 **تاريخ البداية:** {self.stats['start_date'][:10]}
        """
        
        keyboard = [[InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_text, reply_markup=reply_markup)

    async def show_help(self, query):
        """عرض المساعدة"""
        help_text = """
ℹ️ **كيفية استخدام البوت**

1️⃣ أرسل رابط الفيديو من أي منصة مدعومة
2️⃣ اختر جودة التحميل أو تحويل لـ MP3
3️⃣ انتظر قليلاً وستحصل على ملفك!

🌐 **المنصات المدعومة:**
• YouTube
• Twitter/X
• TikTok
• Instagram

💡 **نصائح:**
• استخدم روابط مباشرة للفيديوهات
• الجودة العالية تحتاج وقت أكثر
• MP3 أسرع في التحميل

❓ **مشاكل شائعة:**
• إذا فشل التحميل، جرب رابط آخر
• بعض الفيديوهات قد تكون محمية
• تأكد من أن الرابط يعمل في المتصفح
        """
        
        keyboard = [[InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup)

    async def show_share(self, query):
        """عرض رسالة المشاركة"""
        share_text = """
🔗 **شارك البوت مع أصدقائك!**

انسخ الرسالة التالية وأرسلها:

---
🎬 اكتشفت بوت رائع لتحميل الفيديوهات!

✨ يحمل من:
• يوتيوب 📺
• تويتر 🐦  
• تيك توك 🎵
• إنستقرام 📸

🚀 سريع وذكي ومجاني!
جربه الآن: @YourBotUsername
---

شكراً لك على المشاركة! ❤️
        """
        
        keyboard = [[InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(share_text, reply_markup=reply_markup)

    def setup_handlers(self):
        """إعداد معالجات الأوامر"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
        self.app.add_handler(CallbackQueryHandler(self.download_callback))

    def run(self):
        """تشغيل البوت"""
        logger.info("🚀 بدء تشغيل البوت...")
        self.app.run_polling()

# تشغيل البوت
if __name__ == "__main__":
    BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ يرجى تعيين BOT_TOKEN في متغيرات البيئة!")
        exit(1)
    
    bot = VideoDownloaderBot(BOT_TOKEN)
    bot.run()
