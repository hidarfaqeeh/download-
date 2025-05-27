# تحديث الملف الرئيسي لدعم الملفات الكبيرة
from main import VideoDownloaderBot
from large_file_handler import LargeFileHandler

class EnhancedVideoBot(VideoDownloaderBot):
    def __init__(self, bot_token):
        super().__init__(bot_token)
        self.large_file_handler = LargeFileHandler()
    
    async def process_download(self, query, context, data, user_id):
        """معالجة محسنة للتحميل"""
        video_data = context.user_data.get(f'video_info_{user_id}')
        
        if not video_data:
            await query.edit_message_text("❌ انتهت صلاحية الجلسة!")
            return
        
        url = video_data['url']
        video_info = video_data['info']
        
        # فحص حجم الملف أولاً
        file_info = await self.large_file_handler.check_file_size(url)
        
        if file_info and file_info['size_mb'] > 1000:  # أكبر من 1 جيجا
            await self.large_file_handler.handle_large_file(query, context, url, video_info)
        else:
            # التحميل العادي للملفات الصغيرة
            await super().process_download(query, context, data, user_id)

# استخدام البوت المحسن
if __name__ == "__main__":
    import os
    BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ يرجى تعيين BOT_TOKEN!")
        exit(1)
    
    bot = EnhancedVideoBot(BOT_TOKEN)
    bot.run()
