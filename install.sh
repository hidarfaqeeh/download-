#!/bin/bash

echo "🚀 تثبيت بوت تحميل الفيديوهات..."

# تحديث النظام
echo "📦 تحديث النظام..."
sudo apt update

# تثب��ت Python و pip
echo "🐍 تثبيت Python..."
sudo apt install -y python3 python3-pip python3-venv

# تثبيت ffmpeg
echo "🎬 تثبيت FFmpeg..."
sudo apt install -y ffmpeg

# إنشاء بيئة افتراضية
echo "🔧 إنشاء بيئة افتراضية..."
python3 -m venv venv
source venv/bin/activate

# تثبيت المتطلبات
echo "📚 تثبيت المتطلبات..."
pip install --upgrade pip
pip install -r requirements.txt

# تحديث yt-dlp لآخر إصدار
echo "⬆️ تحديث yt-dlp..."
pip install --upgrade yt-dlp

echo "✅ تم التثبيت بنجاح!"
echo ""
echo "🔑 الآن أضف توكن البوت:"
echo "export BOT_TOKEN='your_bot_token_here'"
echo ""
echo "🚀 لتشغيل البوت:"
echo "python main.py"
