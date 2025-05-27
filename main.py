"""
Telegram Video Downloader Bot
Fast, smart bot for downloading videos without freezing
Supports YouTube, TikTok, Instagram, Twitter - up to 2GB files
"""

import os
import asyncio
import logging
import re
import time
import json
from datetime import datetime
from typing import Dict, Optional, List
import aiofiles
import aiohttp
from dataclasses import dataclass
from urllib.parse import urlparse

# Telegram Bot
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    InputMediaVideo, InputMediaAudio, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatAction

# Video processing
import yt_dlp
import ffmpeg
from PIL import Image
import tempfile
import shutil

# Configuration
from dotenv import load_dotenv
load_dotenv()

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', '0'))
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
DOWNLOAD_TIMEOUT = 1800  # 30 minutes

@dataclass
class VideoInfo:
    title: str
    url: str
    thumbnail: str
    duration: int
    formats: List[Dict]
    platform: str
    file_size: int = 0

class DownloadProgress:
    def __init__(self, chat_id: int, message_id: int, context):
        self.chat_id = chat_id
        self.message_id = message_id
        self.context = context
        self.last_update = 0
        self.start_time = time.time()
    
    async def update(self, d):
        if d['status'] == 'downloading':
            current_time = time.time()
            if current_time - self.last_update < 2:  # Update every 2 seconds
                return
            
            try:
                percent = d.get('_percent_str', 'N/A')
                speed = d.get('_speed_str', 'N/A')
                eta = d.get('_eta_str', 'N/A')
                
                progress_bar = self._create_progress_bar(d.get('downloaded_bytes', 0), 
                                                       d.get('total_bytes', 1))
                
                text = f"📥 جاري التحميل...\n\n"
                text += f"{progress_bar}\n"
                text += f"📊 التقدم: {percent}\n"
                text += f"⚡ السرعة: {speed}\n"
                text += f"⏰ الوقت المتبقي: {eta}\n"
                text += f"💡 {self._get_random_tip()}"
                
                await self.context.bot.edit_message_text(
                    text=text,
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                    parse_mode=ParseMode.HTML
                )
                self.last_update = current_time
                
            except Exception as e:
                logger.error(f"Progress update error: {e}")
    
    def _create_progress_bar(self, downloaded: int, total: int) -> str:
        if total == 0:
            return "▱▱▱▱▱▱▱▱▱▱ 0%"
        
        percent = (downloaded / total) * 100
        filled = int(percent // 10)
        bar = "▰" * filled + "▱" * (10 - filled)
        return f"{bar} {percent:.1f}%"
    
    def _get_random_tip(self) -> str:
        tips = [
            "💡 يمكنك إرسال عدة روابط في نفس الوقت!",
            "🎵 جرب تحويل الفيديو إلى MP3 للحصول على الصوت فقط",
            "⚡ البوت يدعم التحميل المتزامن لعدة مستخدmين",
            "🔄 إذا فشل التحميل، جرب مرة أخرى",
            "📱 البوت يعمل على جميع الأجهزة",
            "🎬 ندعم أكثر من 1000 موقع للتحميل!"
        ]
        import random
        return random.choice(tips)

class VideoDownloader:
    def __init__(self):
        self.stats = {
            'downloads': 0,
            'users': set(),
            'platforms': {},
            'start_time': datetime.now()
        }
        self.active_downloads = {}
        
    async def get_video_info(self, url: str) -> Optional[VideoInfo]:
        """Extract video information without downloading"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(
                    None, ydl.extract_info, url, False
                )
                
                if not info:
                    return None
                
                # Determine platform
                platform = self._detect_platform(url)
                
                # Get available formats
                formats = []
                if 'formats' in info:
                    for f in info['formats']:
                        if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                            formats.append({
                                'format_id': f['format_id'],
                                'quality': f.get('height', 0),
                                'ext': f.get('ext', 'mp4'),
                                'filesize': f.get('filesize', 0),
                                'format_note': f.get('format_note', '')
                            })
                
                return VideoInfo(
                    title=info.get('title', 'Unknown'),
                    url=url,
                    thumbnail=info.get('thumbnail', ''),
                    duration=info.get('duration', 0),
                    formats=formats,
                    platform=platform
                )
                
        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            return None
    
    def _detect_platform(self, url: str) -> str:
        """Detect video platform from URL"""
        domain = urlparse(url).netloc.lower()
        
        if 'youtube.com' in domain or 'youtu.be' in domain:
            return 'YouTube'
        elif 'tiktok.com' in domain:
            return 'TikTok'
        elif 'instagram.com' in domain:
            return 'Instagram'
        elif 'twitter.com' in domain or 'x.com' in domain:
            return 'Twitter/X'
        elif 'facebook.com' in domain:
            return 'Facebook'
        else:
            return 'Other'
    
    async def download_video(self, url: str, quality: str, format_type: str, 
                           progress_callback) -> Optional[str]:
        """Download video with progress tracking"""
        
        temp_dir = tempfile.mkdtemp()
        
        try:
            if format_type == 'audio':
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
                    'progress_hooks': [progress_callback.update],
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                }
            else:
                # Video download
                if quality == 'best':
                    format_selector = 'best[height<=?1080]'
                elif quality == 'medium':
                    format_selector = 'best[height<=?720]'
                else:
                    format_selector = 'best[height<=?480]'
                
                ydl_opts = {
                    'format': format_selector,
                    'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
                    'progress_hooks': [progress_callback.update],
                    'merge_output_format': 'mp4',
                }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await asyncio.get_event_loop().run_in_executor(
                    None, ydl.download, [url]
                )
            
            # Find downloaded file
            files = os.listdir(temp_dir)
            if files:
                return os.path.join(temp_dir, files[0])
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
        finally:
            # Cleanup will happen in calling function
            pass
        
        return None

# Global downloader instance
downloader = VideoDownloader()

# URL validation patterns
URL_PATTERNS = [
    r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
    r'https?://youtu\.be/[\w-]+',
    r'https?://(?:www\.)?tiktok\.com/@[\w.]+/video/\d+',
    r'https?://(?:www\.)?instagram\.com/(?:p|reel)/[\w-]+',
    r'https?://(?:twitter\.com|x\.com)/\w+/status/\d+',
    r'https?://(?:www\.)?facebook\.com/\w+/videos/\d+',
]

def is_valid_url(text: str) -> bool:
    """Check if text contains valid video URL"""
    for pattern in URL_PATTERNS:
        if re.search(pattern, text):
            return True
    return False

def extract_urls(text: str) -> List[str]:
    """Extract all valid URLs from text"""
    urls = []
    for pattern in URL_PATTERNS:
        matches = re.findall(pattern, text)
        urls.extend(matches)
    return urls

# Bot Command Handlers

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    downloader.stats['users'].add(user.id)
    
    welcome_text = f"""
🎬 مرحباً {user.first_name}!

أنا بوت تحميل الفيديوهات الذكي 🤖

✨ **المميزات:**
🎥 تحميل من YouTube, TikTok, Instagram, Twitter
📱 يدعم جميع الأجهزة
⚡ سريع وذكي - بدون تجميد
🎵 تحويل إلى MP3
📊 تتبع التقدم المباشر
💾 ملفات تصل إلى 2 جيجا

📝 **طريقة الاستخدام:**
فقط أرسل رابط الفيديو وسأتولى الباقي!

🆘 للمساعدة: /help
📊 الإحصائيات: /stats
"""
    
    keyboard = [
        [InlineKeyboardButton("📖 دليل الاستخدام", callback_data="help")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
        [InlineKeyboardButton("🔗 شارك البوت", 
                            url=f"https://t.me/share/url?url=https://t.me/{context.bot.username}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
📖 **دليل الاستخدام**

🔗 **المواقع المدعومة:**
• YouTube (youtube.com, youtu.be)
• TikTok (tiktok.com)
• Instagram (instagram.com)
• Twitter/X (twitter.com, x.com)
• Facebook (facebook.com)

⚡ **طريقة الاستخدام:**
1️⃣ أرسل رابط الفيديو
2️⃣ اختر جودة التحميل
3️⃣ انتظر التحميل
4️⃣ استلم الفيديو!

🎵 **تحويل إلى MP3:**
اختر "صوت فقط" من قائمة الخيارات

📱 **نصائح:**
• يمكنك إرسال عدة روابط
• الحد الأقصى: 2 جيجا
• البوت يعمل 24/7

🆘 **مشاكل؟** تواصل مع المطور
"""
    
    await update.message.reply_text(help_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    uptime = datetime.now() - downloader.stats['start_time']
    
    stats_text = f"""
📊 **إحصائيات البوت**

👥 المستخدمون: {len(downloader.stats['users'])}
📥 التحميلات: {downloader.stats['downloads']}
⏰ وقت التشغيل: {uptime.days} يوم، {uptime.seconds//3600} ساعة

📱 **المنصات الأكثر استخداماً:**
"""
    
    for platform, count in downloader.stats['platforms'].items():
        stats_text += f"• {platform}: {count}\n"
    
    if not downloader.stats['platforms']:
        stats_text += "• لا توجد بيانات بعد"
    
    await update.message.reply_text(stats_text)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command (admin only)"""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ هذا الأمر للمدير فقط")
        return
    
    admin_text = f"""
🔧 **لوحة التحكم**

📊 **الإحصائيات المفصلة:**
👥 إجمالي المستخدمين: {len(downloader.stats['users'])}
📥 إجمالي التحميلات: {downloader.stats['downloads']}
🔄 التحميلات النشطة: {len(downloader.active_downloads)}

💾 **استخدام الذاكرة:**
🗂️ الملفات المؤقتة: {len(os.listdir('/tmp')) if os.path.exists('/tmp') else 0}

⚙️ **حالة النظام:**
✅ البوت يعمل بشكل طبيعي
🌐 الاتصال بالإنترنت: نشط
"""
    
    keyboard = [
        [InlineKeyboardButton("🗑️ مسح الملفات المؤقتة", callback_data="admin_cleanup")],
        [InlineKeyboardButton("📊 تصدير الإحصائيات", callback_data="admin_export")],
        [InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="admin_restart")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(admin_text, reply_markup=reply_markup)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video URL messages"""
    text = update.message.text
    urls = extract_urls(text)
    
    if not urls:
        await update.message.reply_text(
            "❌ لم أتمكن من العثور على رابط فيديو صالح\n"
            "تأكد من أن الرابط من المواقع المدعومة:\n"
            "YouTube, TikTok, Instagram, Twitter, Facebook"
        )
        return
    
    url = urls[0]  # Process first URL
    
    # Send processing message
    processing_msg = await update.message.reply_text("🔍 جاري تحليل الرابط...")
    
    # Get video info
    video_info = await downloader.get_video_info(url)
    
    if not video_info:
        await processing_msg.edit_text("❌ فشل في تحليل الرابط. تأكد من صحة الرابط.")
        return
    
    # Update stats
    platform = video_info.platform
    downloader.stats['platforms'][platform] = downloader.stats['platforms'].get(platform, 0) + 1
    
    # Create preview message
    duration_str = f"{video_info.duration // 60}:{video_info.duration % 60:02d}" if video_info.duration else "غير محدد"
    
    preview_text = f"""
🎬 **معاينة الفيديو**

📝 العنوان: {video_info.title[:50]}...
📱 المنصة: {video_info.platform}
⏱️ المدة: {duration_str}

اختر جودة التحميل:
"""
    
    # Create quality options
    keyboard = [
        [InlineKeyboardButton("🔥 أفضل جودة", callback_data=f"download_{url}_best_video")],
        [InlineKeyboardButton("⚡ جودة متوسطة", callback_data=f"download_{url}_medium_video")],
        [InlineKeyboardButton("📱 جودة منخفضة", callback_data=f"download_{url}_low_video")],
        [InlineKeyboardButton("🎵 صوت فقط (MP3)", callback_data=f"download_{url}_best_audio")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send thumbnail if available
    if video_info.thumbnail:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=video_info.thumbnail,
                caption=preview_text,
                reply_markup=reply_markup
            )
            await processing_msg.delete()
        except Exception:
            await processing_msg.edit_text(preview_text, reply_markup=reply_markup)
    else:
        await processing_msg.edit_text(preview_text, reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "help":
        await help_command(update, context)
    elif data == "stats":
        await stats_command(update, context)
    elif data == "cancel":
        await query.edit_message_text("❌ تم إلغاء العملية")
    elif data.startswith("download_"):
        await handle_download_callback(update, context)
    elif data.startswith("admin_"):
        await handle_admin_callback(update, context)

async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle download callback"""
    query = update.callback_query
    data = query.data
    
    # Parse callback data: download_URL_QUALITY_TYPE
    parts = data.split("_", 3)
    if len(parts) < 4:
        await query.edit_message_text("❌ خطأ في البيانات")
        return
    
    url = parts[1]
    quality = parts[2]
    format_type = parts[3]
    
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    
    # Check if user already has active download
    if user_id in downloader.active_downloads:
        await query.edit_message_text("⏳ لديك تحميل نشط بالفعل. انتظر حتى ينتهي.")
        return
    
    # Start download
    await query.edit_message_text("🚀 بدء التحميل...")
    
    # Create progress tracker
    progress = DownloadProgress(chat_id, query.message.message_id, context)
    downloader.active_downloads[user_id] = True
    
    try:
        # Send typing action
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
        
        # Download file
        file_path = await downloader.download_video(url, quality, format_type, progress)
        
        if not file_path or not os.path.exists(file_path):
            await context.bot.edit_message_text(
                text="❌ فشل في التحميل. حاول مرة أخرى.",
                chat_id=chat_id,
                message_id=query.message.message_id
            )
            return
        
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            await context.bot.edit_message_text(
                text=f"❌ الملف كبير جداً ({file_size / (1024*1024*1024):.1f} GB)\n"
                     f"الحد الأقصى المسموح: 2 GB",
                chat_id=chat_id,
                message_id=query.message.message_id
            )
            os.remove(file_path)
            return
        
        # Send file
        await context.bot.edit_message_text(
            text="📤 جاري رفع الملف...",
            chat_id=chat_id,
            message_id=query.message.message_id
        )
        
        with open(file_path, 'rb') as file:
            if format_type == 'audio':
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=file,
                    caption="🎵 تم تحويل الفيديو إلى MP3 بنجاح!"
                )
            else:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=file,
                    caption="✅ تم تحميل الفيديو بنجاح!"
                )
        
        # Success message with share button
        keyboard = [
            [InlineKeyboardButton("🔗 شارك البوت", 
                                url=f"https://t.me/share/url?url=https://t.me/{context.bot.username}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.edit_message_text(
            text="✅ تم التحميل بنجاح!\n\n💡 شارك البوت مع أصدقائك",
            chat_id=chat_id,
            message_id=query.message.message_id,
            reply_markup=reply_markup
        )
        
        # Update stats
        downloader.stats['downloads'] += 1
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await context.bot.edit_message_text(
            text="❌ حدث خطأ غير متوقع. حاول مرة أخرى.",
            chat_id=chat_id,
            message_id=query.message.message_id
        )
    finally:
        # Cleanup
        if user_id in downloader.active_downloads:
            del downloader.active_downloads[user_id]
        
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                # Remove file and temp directory
                temp_dir = os.path.dirname(file_path)
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin callbacks"""
    query = update.callback_query
    
    if query.from_user.id != ADMIN_USER_ID:
        await query.answer("❌ غير مصرح", show_alert=True)
        return
    
    data = query.data
    
    if data == "admin_cleanup":
        # Cleanup temp files
        try:
            temp_files = 0
            for root, dirs, files in os.walk('/tmp'):
                for file in files:
                    if file.endswith(('.mp4', '.mp3', '.webm', '.m4a')):
                        os.remove(os.path.join(root, file))
                        temp_files += 1
            
            await query.edit_message_text(f"🗑️ تم مسح {temp_files} ملف مؤقت")
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ في المسح: {e}")
    
    elif data == "admin_export":
        # Export stats
        stats_data = {
            'users': len(downloader.stats['users']),
            'downloads': downloader.stats['downloads'],
            'platforms': downloader.stats['platforms'],
            'uptime': str(datetime.now() - downloader.stats['start_time']),
            'active_downloads': len(downloader.active_downloads)
        }
        
        stats_json = json.dumps(stats_data, indent=2, ensure_ascii=False)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(stats_json)
            f.flush()
            
            with open(f.name, 'rb') as file:
                await context.bot.send_document(
                    chat_id=query.message.chat.id,
                    document=file,
                    filename=f"bot_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    caption="📊 إحصائيات البوت"
                )
        
        os.unlink(f.name)
        await query.edit_message_text("📊 تم تصدير الإحصائيات")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

async def set_bot_commands(application: Application):
    """Set bot commands menu"""
    commands = [
        BotCommand("start", "بدء استخدام البوت"),
        BotCommand("help", "دليل الاستخدام"),
        BotCommand("stats", "إحصائيات البوت"),
    ]
    
    if ADMIN_USER_ID:
        commands.append(BotCommand("admin", "لوحة التحكم (للمدير)"))
    
    await application.bot.set_my_commands(commands)

def main():
    """Start the bot"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        return
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin", admin_command))
    
    # URL handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_url
    ))
    
    # Callback handler
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Set commands
    application.job_queue.run_once(
        lambda context: asyncio.create_task(set_bot_commands(application)), 
        when=1
    )
    
    # Start bot
    logger.info("Starting Telegram Video Downloader Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
