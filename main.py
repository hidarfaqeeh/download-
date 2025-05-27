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
import subprocess
import sys

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
        
        # تحديث yt-dlp عند البداية
        self.update_ytdlp()
        
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

    def safe_format_number(self, number):
        """تنسيق آمن للأرقام"""
        if number is None:
            return "0"
        try:
            return f"{int(number):,}"
        except (ValueError, TypeError):
            return "غير معروف"

    def update_ytdlp(self):
        """تحديث yt-dlp لآخر إصدار"""
        try:
            logger.info("🔄 تحديث yt-dlp...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"], 
                         capture_output=True, check=True)
            logger.info("✅ تم تحديث yt-dlp بنجاح")
        except Exception as e:
            logger.warning(f"⚠️ فشل تحديث yt-dlp: {e}")

    def load_stats(self):
        """تحميل الإحصائيات من الملف"""
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                stats = json.load(f)
                # تحويل قائمة المستخدمين إلى set
                if isinstance(stats.get('users'), list):
                    stats['users'] = set(stats['users'])
                return stats
        except FileNotFoundError:
            return {
                "total_downloads": 0,
                "users": set(),
                "platforms": {"youtube": 0, "twitter": 0, "tiktok": 0, "instagram": 0, "facebook": 0, "other": 0},
                "start_date": datetime.now().isoformat()
            }

    def save_stats(self):
        """حفظ الإحصائيات"""
        stats_to_save = self.stats.copy()
        stats_to_save["users"] = list(self.stats["users"])
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats_to_save, f, ensure_ascii=False, indent=2)

    def detect_platform(self, url):
        """تحديد نوع المنصة من الرابط - محسن"""
        url_lower = url.lower()
        domain = urlparse(url).netloc.lower()
        
        # يوتيوب
        if any(x in domain for x in ['youtube.com', 'youtu.be', 'm.youtube.com']):
            return 'youtube'
        
        # تويتر/X
        elif any(x in domain for x in ['twitter.com', 'x.com', 't.co', 'mobile.twitter.com']):
            return 'twitter'
        
        # تيك توك
        elif any(x in domain for x in ['tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com']):
            return 'tiktok'
        
        # إنستقرام
        elif any(x in domain for x in ['instagram.com', 'instagr.am']):
            return 'instagram'
        
        # فيسبوك
        elif any(x in domain for x in ['facebook.com', 'fb.watch', 'm.facebook.com']):
            return 'facebook'
        
        # منصات أخرى مدعومة
        elif any(x in domain for x in ['dailymotion.com', 'vimeo.com', 'twitch.tv', 'reddit.com']):
            return 'other'
        
        else:
            return 'unknown'

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر البداية"""
        user = update.effective_user
        self.stats["users"].add(user.id)
        
        welcome_text = f"""
🎬 مرحباً {user.first_name}! 

أنا بوت تحميل الفيديوهات السريع والذكي! 🚀

✨ **المنصات المدعومة:**
• يوتيوب 📺 (جميع الأنواع)
• تويتر/X 🐦 (فيديوهات وGIFs)
• تيك توك 🎵 (بدون علامة مائية)
• إنستقرام 📸 (منشورات وستوريز)
• فيسبوك 👥 (فيديوهات عامة)
• منصات أخرى 🌐 (Vimeo, Dailymotion...)

📋 **كيفية الاستخدام:**
فقط أرسل لي رابط الفيديو وسأتولى الباقي!

🎯 **مميزات خاصة:**
• تحميل سريع بدون تجميد
• جودات متعددة (4K, HD, SD)
• تحويل إلى MP3 عالي الجودة
• إزالة العلامات المائية
• دعم الروابط المختصرة
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
            [InlineKeyboardButton("ℹ️ المساعدة", callback_data="help"),
             InlineKeyboardButton("🔗 شارك البوت", callback_data="share")],
            [InlineKeyboardButton("🧪 اختبار الروابط", callback_data="test_links")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def get_video_info(self, url):
        """الحصول على معلومات الفيديو - محسن"""
        # إعدادات محسنة لـ yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'referer': 'https://www.google.com/',
            'headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        }
        
        # إعدادات خاصة حسب المنصة
        platform = self.detect_platform(url)
        
        if platform == 'tiktok':
            ydl_opts.update({
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
            })
        elif platform == 'instagram':
            ydl_opts.update({
                'http_headers': {
                    'User-Agent': 'Instagram 76.0.0.15.395 Android (24/7.0; 640dpi; 1440x2560; samsung; SM-G930F; herolte; samsungexynos8890; en_US; 138226743)'
                }
            })
        elif platform == 'twitter':
            ydl_opts.update({
                'http_headers': {
                    'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
                    'User-Agent': 'TwitterAndroid/9.95.0-release.0 (29950000-r-0) ONEPLUS+A6000/9 (OnePlus;ONEPLUS+A6000;OnePlus;OnePlus6;0;;1;2016)'
                }
            })
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"🔍 محاولة استخراج معلومات من: {url}")
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    logger.error("❌ لم يتم العثور على معلومات")
                    return None
                
                logger.info(f"✅ تم استخراج المعلومات: {info.get('title', 'بدون عنوان')}")
                
                return {
                    'title': info.get('title', 'غير معروف'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'uploader': info.get('uploader', 'غير معروف'),
                    'view_count': info.get('view_count', 0),
                    'formats': info.get('formats', []),
                    'webpage_url': info.get('webpage_url', url),
                    'description': info.get('description', '')[:200] + '...' if info.get('description') else ''
                }
        except Exception as e:
            logger.error(f"❌ خطأ في استخراج المعلومات: {e}")
            # محاولة ثانية مع إعدادات مبسطة
            try:
                simple_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'skip_download': True
                }
                with yt_dlp.YoutubeDL(simple_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info:
                        return {
                            'title': info.get('title', 'فيديو'),
                            'duration': 0,
                            'thumbnail': None,
                            'uploader': info.get('uploader', 'غير معروف'),
                            'view_count': 0,
                            'formats': [],
                            'webpage_url': url,
                            'description': ''
                        }
            except:
                pass
            return None

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الروابط المرسلة - محسن"""
        url = update.message.text.strip()
        user_id = update.effective_user.id
        
        # تنظيف الرابط
        url = self.clean_url(url)
        
        # التحقق من صحة الرابط
        if not self.is_valid_url(url):
            await update.message.reply_text(
                "❌ الرابط غير صحيح!\n\n"
                "💡 **أمثلة على روابط صحيحة:**\n"
                "• https://youtube.com/watch?v=...\n"
                "• https://twitter.com/user/status/...\n"
                "• https://tiktok.com/@user/video/...\n"
                "• https://instagram.com/p/..."
            )
            return
        
        platform = self.detect_platform(url)
        if platform == 'unknown':
            await update.message.reply_text(
                "❌ المنصة غير مدعومة حالياً!\n\n"
                "🌐 **المنصات المدعومة:**\n"
                "• YouTube\n• Twitter/X\n• TikTok\n• Instagram\n• Facebook\n• Vimeo\n• Dailymotion"
            )
            return
        
        # رسالة انتظار مرحة
        waiting_msg = await update.message.reply_text(
            f"🔍 جاري تحليل الرابط من {platform.title()}...\n"
            "⏳ قد يستغرق هذا بضع ثوانٍ..."
        )
        
        # الحصول على معلومات الفيديو
        try:
            video_info = await self.get_video_info(url)
            
            if not video_info:
                await waiting_msg.edit_text(
                    "❌ فشل في تحليل الرابط!\n\n"
                    "🔧 **حلول مقترحة:**\n"
                    "• تأكد من أن الرابط يعمل في المتصفح\n"
                    "• جرب نسخ الرابط مرة أخرى\n"
                    "• تأكد من أن الفيديو عام وليس خاص\n"
                    "• جرب رابط مختلف من نفس المنصة"
                )
                return
            
            # عرض معاينة الفيديو
            preview_text = f"""
🎬 **{video_info['title']}**

📺 **القناة:** {video_info['uploader']}
⏱️ **المدة:** {self.format_duration(video_info['duration'])}
👀 **المشاهدات:** {video_info.get('view_count', 0) or 0:,}
🌐 **المنصة:** {platform.title()}

📝 **الوصف:** {video_info['description'][:100]}...
            """
            
            # أزرار الخيارات
            keyboard = [
                [InlineKeyboardButton("🎬 فيديو عالي الجودة", callback_data=f"download_video_high_{user_id}")],
                [InlineKeyboardButton("📱 فيديو جودة متوسطة", callback_data=f"download_video_medium_{user_id}")],
                [InlineKeyboardButton("🎵 صوت MP3", callback_data=f"download_audio_{user_id}")],
                [InlineKeyboardButton("ℹ️ معلومات تفصيلية", callback_data=f"info_{user_id}"),
                 InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # حفظ معلومات الفيديو في السياق
            context.user_data[f'video_info_{user_id}'] = {
                'url': url,
                'info': video_info,
                'platform': platform
            }
            
            await waiting_msg.edit_text(preview_text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الرابط: {e}")
            await waiting_msg.edit_text(
                f"❌ حدث خطأ أثناء معالجة الرابط!\n\n"
                f"🔍 **تفاصيل الخطأ:** {str(e)[:100]}...\n\n"
                "🔄 جرب مرة أخرى أو استخدم رابط مختلف"
            )

    def clean_url(self, url):
        """تنظيف الرابط من المعاملات غير الضرورية"""
        # إزالة المسافات
        url = url.strip()
        
        # إزالة معاملات التتبع الشائعة
        tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'fbclid', 'gclid']
        
        for param in tracking_params:
            if param in url:
                url = re.sub(f'[?&]{param}=[^&]*', '', url)
        
        # تنظيف روابط تيك توك المختصرة
        if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
            # هذه الروابط تحتاج إعادة توجيه
            pass
        
        return url

    def is_valid_url(self, url):
        """التحقق من صحة الرابط - محسن"""
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
        """معالجة أزرار التحميل - محسن"""
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
        
        if data == "test_links":
            await self.show_test_links(query)
            return
        
        if data == "back_to_main":
            await self.show_main_menu(query)
            return
        
        if data.startswith("info_"):
            await self.show_detailed_info(query, context, user_id)
            return
        
        # معالجة التحميل
        if data.startswith("download_"):
            await self.process_download(query, context, data, user_id)

    async def show_test_links(self, query):
        """عرض روابط اختبار للمنصات المختلفة"""
        test_text = """
🧪 **روابط اختبار للمنصات المختلفة:**

📺 **يوتيوب:**
https://www.youtube.com/watch?v=dQw4w9WgXcQ

🐦 **تويتر:**
https://twitter.com/Twitter/status/1234567890

🎵 **تيك توك:**
https://www.tiktok.com/@tiktok/video/1234567890

📸 **إنستقرام:**
https://www.instagram.com/p/ABC123/

💡 **نصيحة:** انسخ أي رابط وأرسله لي لاختبار البوت!
        """
        
        keyboard = [[InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(test_text, reply_markup=reply_markup)

    async def show_main_menu(self, query):
        """عرض القائمة الرئيسية"""
        welcome_text = """
🎬 **بوت تحميل الفيديوهات**

أرسل لي رابط فيديو من أي منصة مدعومة وسأقوم بتحميله لك!

✨ **المنصات المدعومة:**
• يوتيوب 📺
• تويتر/X 🐦
• تيك توك 🎵
• إنستقرام 📸
• فيسبوك 👥
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
            [InlineKeyboardButton("ℹ️ المساعدة", callback_data="help"),
             InlineKeyboardButton("🔗 شارك البوت", callback_data="share")],
            [InlineKeyboardButton("🧪 اختبار الروابط", callback_data="test_links")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(welcome_text, reply_markup=reply_markup)

    async def show_detailed_info(self, query, context, user_id):
        """عرض معلومات تفصيلية عن الفيديو"""
        video_data = context.user_data.get(f'video_info_{user_id}')
        
        if not video_data:
            await query.edit_message_text("❌ انتهت صلاحية الجلسة!")
            return
        
        info = video_data['info']
        platform = video_data['platform']
        
        detailed_text = f"""
📋 **معلومات تفصيلية**

🎬 **العنوان:** {info['title']}
📺 **القناة:** {info['uploader']}
⏱️ **المدة:** {self.format_duration(info['duration'])}
👀 **المشاهدات:** {info.get('view_count', 0):,}
🌐 **المنصة:** {platform.title()}
🔗 **الرابط:** {info['webpage_url']}

📝 **الوصف:**
{info['description'][:300]}...

🎥 **الجودات المتاحة:**
        """
        
        # عرض الجودات المتاحة
        formats = info.get('formats', [])
        if formats:
            qualities = set()
            for fmt in formats:
                if fmt.get('height'):
                    qualities.add(f"{fmt['height']}p")
            
            if qualities:
                detailed_text += "\n• " + "\n• ".join(sorted(qualities, reverse=True))
        
        keyboard = [
            [InlineKeyboardButton("📥 تحميل", callback_data=f"download_video_medium_{user_id}")],
            [InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(detailed_text, reply_markup=reply_markup)

    async def process_download(self, query, context, data, user_id):
        """معالجة عملية التحميل - محسن"""
        video_data = context.user_data.get(f'video_info_{user_id}')
        
        if not video_data:
            await query.edit_message_text("❌ انتهت صلاحية الجلسة! أرسل الرابط مرة أخرى.")
            return
        
        url = video_data['url']
        video_info = video_data['info']
        platform = video_data['platform']
        
        # تحديث الإحصائيات
        self.stats["total_downloads"] += 1
        if platform in self.stats["platforms"]:
            self.stats["platforms"][platform] += 1
        else:
            self.stats["platforms"]["other"] += 1
        self.save_stats()
        
        # رسالة التحميل
        progress_msg = await query.edit_message_text(
            f"🚀 بدء التحميل من {platform.title()}...\n"
            "⏳ قد يستغرق هذا بضع دقائق..."
        )
        
        try:
            if "audio" in data:
                file_path = await self.download_audio(url, video_info, progress_msg, platform)
            else:
                quality = "high" if "high" in data else "medium"
                file_path = await self.download_video(url, video_info, quality, progress_msg, platform)
            
            if file_path and os.path.exists(file_path):
                await self.send_file(query, file_path, video_info)
                # حذف الملف بعد الإرسال
                try:
                    os.remove(file_path)
                except:
                    pass
            else:
                await progress_msg.edit_text(
                    "❌ فشل في التحميل!\n\n"
                    "🔧 **حلول مقترحة:**\n"
                    "• جرب جودة أقل\n"
                    "• تأكد من أن الفيديو متاح\n"
                    "• جرب رابط مختلف"
                )
                
        except Exception as e:
            logger.error(f"خطأ في التحميل: {e}")
            await progress_msg.edit_text(
                f"❌ حدث خطأ أثناء التحميل!\n\n"
                f"🔍 **تفاصيل:** {str(e)[:100]}...\n"
                "🔄 جرب مرة أخرى"
            )

    async def download_video(self, url, video_info, progress_msg, quality="medium", platform="unknown"):
        """تحميل الفيديو - محسن"""
        timestamp = int(datetime.now().timestamp())
        filename = f"{self.downloads_dir}/video_{platform}_{timestamp}.%(ext)s"
        
        # إعدادات محسنة حسب الجودة والمنصة
        if quality == "high":
            format_selector = 'best[height<=1080]/best'
        else:
            format_selector = 'best[height<=720]/best'
        
        ydl_opts = {
            'outtmpl': filename,
            'format': format_selector,
            'merge_output_format': 'mp4',
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,
            'no_warnings': True,
            'extractaudio': False,
            'audioformat': 'mp3',
            'embed_subs': False,
            'writeinfojson': False,
            'writethumbnail': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'referer': 'https://www.google.com/',
            'socket_timeout': 60,
            'retries': 3,
            'progress_hooks': [lambda d: asyncio.create_task(self.progress_hook(d, progress_msg))],
        }
        
        # إعدادات خاصة لكل منصة
        if platform == 'tiktok':
            ydl_opts.update({
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
                }
            })
        elif platform == 'instagram':
            ydl_opts.update({
                'http_headers': {
                    'User-Agent': 'Instagram 76.0.0.15.395 Android'
                }
            })
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # البحث عن الملف المحمل
            download_files = [f for f in os.listdir(self.downloads_dir) 
                            if f.startswith(f'video_{platform}_{timestamp}')]
            
            if download_files:
                return os.path.join(self.downloads_dir, download_files[0])
            else:
                return None
                
        except Exception as e:
            logger.error(f"خطأ في تحميل الفيديو: {e}")
            return None

    async def download_audio(self, url, video_info, progress_msg, platform="unknown"):
        """تحميل الصوت - محسن"""
        timestamp = int(datetime.now().timestamp())
        filename = f"{self.downloads_dir}/audio_{platform}_{timestamp}.%(ext)s"
        
        ydl_opts = {
            'outtmpl': filename,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'ignoreerrors': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'socket_timeout': 60,
            'retries': 3,
            'progress_hooks': [lambda d: asyncio.create_task(self.progress_hook(d, progress_msg))],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # البحث عن الملف المحمل
            download_files = [f for f in os.listdir(self.downloads_dir) 
                            if f.startswith(f'audio_{platform}_{timestamp}')]
            
            if download_files:
                return os.path.join(self.downloads_dir, download_files[0])
            else:
                return None
                
        except Exception as e:
            logger.error(f"خطأ في تحميل الصوت: {e}")
            return None

    async def progress_hook(self, d, progress_msg):
        """تحديث شريط التقدم - محسن"""
        if d['status'] == 'downloading':
            try:
                percent = d.get('_percent_str', '0%').strip()
                speed = d.get('_speed_str', 'غير معروف')
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes', 0)
                
                if total > 0:
                    downloaded_mb = downloaded / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    progress_text = f"""
📥 **جاري التحميل...**

📊 **التقدم:** {percent}
📁 **الحجم:** {downloaded_mb:.1f}/{total_mb:.1f} ميجا
⚡ **السرعة:** {speed}

⏳ يرجى الانتظار...
                    """
                else:
                    progress_text = f"📥 جاري التحميل... {percent}\n⚡ السرعة: {speed}"
                
                await progress_msg.edit_text(progress_text)
                
            except Exception:
                pass  # تجاهل أخطاء التحديث

    async def send_file(self, query, file_path, video_info):
        """إرسال الملف للمستخدم - محسن"""
        try:
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # بالميجا
            
            caption = f"""
✅ **تم التحميل بنجاح!**

🎬 **العنوان:** {video_info['title']}
📁 **الحجم:** {file_size:.1f} ميجابايت
⏱️ **المدة:** {self.format_duration(video_info.get('duration', 0))}

🤖 شكراً لاستخدام البوت!
            """
            
            if file_path.endswith('.mp3'):
                with open(file_path, 'rb') as audio_file:
                    await query.message.reply_audio(
                        audio=audio_file,
                        caption=caption,
                        title=video_info['title'],
                        performer=video_info.get('uploader', 'Unknown')
                    )
            else:
                with open(file_path, 'rb') as video_file:
                    await query.message.reply_video(
                        video=video_file,
                        caption=caption,
                        supports_streaming=True
                    )
            
            # زر مشاركة البوت
            keyboard = [[InlineKeyboardButton("🔗 شارك البوت", callback_data="share")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("✅ تم الإرسال بنجاح!", reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"خطأ في إرسال الملف: {e}")
            if "too large" in str(e).lower():
                await query.edit_message_text(
                    "❌ الملف كبير جداً للإرسال!\n\n"
                    "💡 **حلول:**\n"
                    "• جرب جودة أقل\n"
                    "• حول إلى MP3 بدلاً من الفيديو"
                )
            else:
                await query.edit_message_text(f"❌ فشل في إرسال الملف: {str(e)[:100]}...")

    async def show_stats(self, query):
        """عرض الإحصائيات - محسن"""
        total_users = len(self.stats['users'])
        total_downloads = self.stats['total_downloads']
        
        stats_text = f"""
📊 **إحصائيات البوت**

👥 **المستخدمون:** {total_users}
📥 **إجمالي التحميلات:** {total_downloads}

🌐 **التحميلات حسب المنصة:**
📺 يوتيوب: {self.stats['platforms'].get('youtube', 0)}
🐦 تويتر: {self.stats['platforms'].get('twitter', 0)}
🎵 تيك توك: {self.stats['platforms'].get('tiktok', 0)}
📸 إنستقرام: {self.stats['platforms'].get('instagram', 0)}
👥 فيسبوك: {self.stats['platforms'].get('facebook', 0)}
🌐 أخرى: {self.stats['platforms'].get('other', 0)}

📅 **تاريخ البداية:** {self.stats['start_date'][:10]}
⚡ **متوسط التحميل:** {total_downloads/max(total_users,1):.1f} لكل مستخدم
        """
        
        keyboard = [[InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_text, reply_markup=reply_markup)

    async def show_help(self, query):
        """عرض المساعدة - محسن"""
        help_text = """
ℹ️ **دليل الاستخدام الشامل**

🚀 **كيفية الاستخدام:**
1️⃣ انسخ رابط الفيديو من أي منصة
2️⃣ أرسل الرابط للبوت
3️⃣ اختر جودة التحميل
4️⃣ انتظر واستلم ملفك!

🌐 **المنصات المدعومة:**
• YouTube (جميع الأنواع)
• Twitter/X (فيديوهات وGIFs)
• TikTok (بدون علامة مائية)
• Instagram (منشورات وستوريز)
• Facebook (فيديوهات عامة)
• Vimeo, Dailymotion وأخرى

🎯 **أنواع التحميل:**
• **فيديو HD:** جودة عالية (1080p)
• **فيديو SD:** جودة متوسطة (720p)
• **صوت MP3:** صوت فقط (192kbps)

💡 **نصائح مهمة:**
• استخدم روابط مباشرة للفيديوهات
• تأكد من أن الفيديو عام وليس خاص
• الجودة العالية تحتاج وقت أكثر
• MP3 أسرع وأصغر حجماً

❓ **حل المشاكل:**
• إذا فشل التحميل، جرب جودة أقل
• تأكد من صحة الرابط
• بعض الفيديوهات قد تكون محمية
• جرب نسخ الرابط مرة أخرى

🔧 **مشاكل شائعة:**
• "المنصة غير مدعومة" → تأكد من الرابط
• "فشل التحليل" → جرب رابط آخر
• "الملف كبير" → اختر جودة أقل
        """
        
        keyboard = [[InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup)

    async def show_share(self, query):
        """عرض رسالة المشاركة - محسن"""
        share_text = """
🔗 **شارك البوت مع أصدقائك!**

📱 **انسخ الرسالة التالية وأرسلها:**

---
🎬 **اكتشفت بوت رائع لتحميل الفيديوهات!**

✨ **يحمل من جميع المنصات:**
• يوتيوب 📺 (جميع الجودات)
• تويتر/X 🐦 (فيديوهات وGIFs)
• تيك توك 🎵 (بدون علامة مائية)
• إنستقرام 📸 (منشورات وستوريز)
• فيسبوك 👥 (فيديوهات عامة)

🚀 **مميزات رائعة:**
• سريع وذكي ومجاني 100%
• جودات متعددة (4K, HD, SD)
• تحويل إلى MP3 عالي الجودة
• واجهة عربية سهلة الاستخدام

🔗 **جربه الآن:** @YourBotUsername
---

❤️ **شكراً لك على المشاركة!**
كلما زاد عدد المستخدمين، كلما تحسن البوت أكثر!
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
        logger.info("🚀 بدء تشغيل البوت المحسن...")
        self.app.run_polling()

# تشغيل البوت
if __name__ == "__main__":
    BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ يرجى تعيين BOT_TOKEN في متغيرات البيئة!")
        print("💡 مثال: export BOT_TOKEN='1234567890:ABCdefGHIjklMNOpqrsTUVwxyz'")
        exit(1)
    
    bot = VideoDownloaderBot(BOT_TOKEN)
    bot.run()
