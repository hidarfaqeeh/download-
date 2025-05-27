import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

class AdminPanel:
    def __init__(self, admin_ids):
        self.admin_ids = admin_ids
        
    def is_admin(self, user_id):
        """التحقق من صلاحيات المشرف"""
        return user_id in self.admin_ids
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لوحة تحكم المشرف"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ ليس لديك صلاحية للوصول!")
            return
        
        admin_text = """
🔧 **لوحة تحكم المشرف**

اختر العملية المطلوبة:
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 إحصائيات مفصلة", callback_data="admin_detailed_stats")],
            [InlineKeyboardButton("👥 قائمة المستخدمين", callback_data="admin_users_list")],
            [InlineKeyboardButton("📝 سجل التحميلات", callback_data="admin_download_logs")],
            [InlineKeyboardButton("📢 إرسال إشعار", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔄 إعادة تشغيل", callback_data="admin_restart")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(admin_text, reply_markup=reply_markup)
    
    async def detailed_stats(self, query):
        """إحصائيات مفصلة للمشرف"""
        try:
            with open('stats.json', 'r', encoding='utf-8') as f:
                stats = json.load(f)
            
            # حساب إحصائيات إضافية
            total_users = len(stats.get('users', []))
            total_downloads = stats.get('total_downloads', 0)
            
            # إحصائيات اليوم
            today = datetime.now().date()
            daily_downloads = 0  # يمكن تحسينها بحفظ تواريخ التحميل
            
            stats_text = f"""
📊 **إحصائيات مفصلة**

👥 **المستخدمين:**
• إجمالي المستخدمين: {total_users:,}
• مستخدمين جدد اليوم: {daily_downloads}

📥 **التحميلات:**
• إجمالي التحميلات: {total_downloads:,}
• تحميلات اليوم: {daily_downloads}
• متوسط التحميل لكل مستخدم: {total_downloads/max(total_users,1):.1f}

🌐 **المنصات الأكثر استخداماً:**
• يوتيوب: {stats['platforms'].get('youtube', 0):,}
• تويتر: {stats['platforms'].get('twitter', 0):,}
• تيك توك: {stats['platforms'].get('tiktok', 0):,}
• إنستقرام: {stats['platforms'].get('instagram', 0):,}

📅 **معلومات النظام:**
• تاريخ البداية: {stats.get('start_date', 'غير معروف')[:10]}
• وقت آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M')}
            """
            
            keyboard = [[InlineKeyboardButton("🔙 العودة", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(stats_text, reply_markup=reply_markup)
            
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ في تحميل الإحصائيات: {e}")
    
    async def broadcast_message(self, context, message, users_list):
        """إرسال رسالة جماعية"""
        sent_count = 0
        failed_count = 0
        
        for user_id in users_list:
            try:
                await context.bot.send_message(chat_id=user_id, text=message)
                sent_count += 1
                await asyncio.sleep(0.1)  # تجنب حدود التلقرام
            except Exception:
                failed_count += 1
        
        return sent_count, failed_count
