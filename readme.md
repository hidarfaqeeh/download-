# 🤖 Telegram Video Downloader Bot - Setup Guide

## 📁 Project Structure
```
telegram_video_bot/
├── main.py                 # Main bot code
├── requirements.txt        # Python dependencies
├── .env                   # Environment variables
├── docker-compose.yml     # Docker deployment
├── Dockerfile            # Docker image
└── README.md             # This file
```

## 📋 Requirements.txt
```txt
python-telegram-bot==20.7
yt-dlp==2023.12.30
python-dotenv==1.0.0
aiofiles==23.2.1
aiohttp==3.9.1
ffmpeg-python==0.2.0
Pillow==10.1.0
```

## 🔧 Environment Variables (.env)
```env
# Telegram Bot Configuration
BOT_TOKEN=your_bot_token_here
ADMIN_USER_ID=your_telegram_user_id

# Optional: Advanced Configuration
MAX_CONCURRENT_DOWNLOADS=5
DOWNLOAD_TIMEOUT=1800
TEMP_DIR=/tmp/telegram_bot
LOG_LEVEL=INFO
```

## 🐳 Dockerfile
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY .env .

# Create temp directory
RUN mkdir -p /tmp/telegram_bot

# Run the bot
CMD ["python", "main.py"]
```

## 🐙 Docker Compose (docker-compose.yml)
```yaml
version: '3.8'

services:
  telegram-bot:
    build: .
    container_name: video_downloader_bot
    restart: unless-stopped
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - ADMIN_USER_ID=${ADMIN_USER_ID}
    volumes:
      - ./downloads:/tmp/telegram_bot
      - ./logs:/app/logs
    mem_limit: 2g
    cpus: 1.0
    networks:
      - bot_network

networks:
  bot_network:
    driver: bridge
```

## 🚀 Quick Setup Instructions

### Step 1: Create Telegram Bot
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`
3. Choose a name and username for your bot
4. Copy the **Bot Token**

### Step 2: Get Your User ID
1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy your **User ID** (for admin access)

### Step 3: Install Dependencies
```bash
# Clone or create project directory
mkdir telegram_video_bot
cd telegram_video_bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Install ffmpeg (if not using Docker)
# Ubuntu/Debian: sudo apt install ffmpeg
# macOS: brew install ffmpeg
# Windows: Download from https://ffmpeg.org
```

### Step 4: Configure Environment
Create `.env` file with your tokens:
```env
BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ
ADMIN_USER_ID=123456789
```

### Step 5: Run the Bot

#### Option A: Direct Python
```bash
python main.py
```

#### Option B: Docker
```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## 🎯 Bot Features

### ✅ What Works
- **Multi-platform support**: YouTube, TikTok, Instagram, Twitter, Facebook
- **Smart downloads**: No bot freezing with async processing
- **Progress tracking**: Real-time download percentage
- **Multiple formats**: Video qualities + MP3 audio extraction
- **File size handling**: Up to 2GB files
- **Admin panel**: Statistics and management
- **Arabic interface**: Fully localized
- **Concurrent downloads**: Multiple users simultaneously

### 🔧 Advanced Features
- **Auto-cleanup**: Temporary files management
- **Error recovery**: Robust error handling
- **Statistics tracking**: Usage analytics
- **Progress animations**: Engaging user experience
- **Smart tips**: Random helpful messages during downloads

### 📱 Supported Platforms
| Platform | URL Format | Status |
|----------|------------|--------|
| YouTube | youtube.com, youtu.be | ✅ |
| TikTok | tiktok.com | ✅ |
| Instagram | instagram.com/p/, /reel/ | ✅ |
| Twitter/X | twitter.com, x.com | ✅ |
| Facebook | facebook.com/videos/ | ✅ |

## 🛠️ Commands

### User Commands
- `/start` - Welcome message and bot introduction
- `/help` - Usage guide and supported platforms
- `/stats` - Bot statistics and uptime

### Admin Commands (Admin only)
- `/admin` - Admin control panel
- Cleanup temp files
- Export statistics
- System monitoring

## 🔧 Customization

### Adding New Platforms
```python
# In URL_PATTERNS list, add new regex:
r'https?://(?:www\.)?newsite\.com/video/[\w-]+',

# In _detect_platform method:
elif 'newsite.com' in domain:
    return 'NewSite'
```

### Changing Language
Replace Arabic text with your preferred language in:
- Command responses
- Button labels
- Progress messages
- Error messages

### Adjusting Limits
```python
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # Change size limit
DOWNLOAD_TIMEOUT = 1800  # Change timeout (seconds)
```

## 🐛 Troubleshooting

### Common Issues

#### "Bot Token Invalid"
- Check your `.env` file
- Ensure BOT_TOKEN is correct from @BotFather

#### "FFmpeg not found"
```bash
# Install FFmpeg
sudo apt install ffmpeg  # Ubuntu/Debian
brew install ffmpeg      # macOS
```

#### "Download fails"
- Check internet connection
- Some platforms may have restrictions
- Try different video URLs

#### "File too large"
- Bot has 2GB Telegram limit
- Choose lower quality
- Use audio-only for music

### Performance Tips
1. **Use Docker** for better resource management
2. **Monitor disk space** - temp files can accumulate
3. **Regular cleanup** via admin panel
4. **Limit concurrent users** if needed

## 📈 Monitoring

### Log Files
```bash
# View real-time logs
tail -f logs/bot.log

# Docker logs
docker-compose logs -f telegram-bot
```

### Health Checks
- Bot responds to `/start`
- Admin panel accessible
- Download completion rates
- Server resource usage

## 🔒 Security

### Best Practices
- Keep bot token secure
- Set admin user ID correctly
- Regular updates of dependencies
- Monitor for abuse
- Implement rate limiting if needed

### File Security
- Automatic temp file cleanup
- No permanent storage of user content
- Secure file handling

## 🚀 Deployment Options

### 1. VPS/Server
- Ubuntu 20.04+ recommended
- 2GB RAM minimum
- 50GB+ storage
- Good internet connection

### 2. Cloud Platforms
- **Heroku**: Easy deployment, limited file storage
- **DigitalOcean**: Full control, affordable
- **AWS EC2**: Scalable, pay-as-you-go
- **Google Cloud**: Credit available for new users

### 3. Raspberry Pi
- Pi 4 with 4GB+ RAM
- External storage recommended
- Good for personal use

## 📞 Support

### Getting Help
1. Check logs for error messages
2. Verify all dependencies installed
3. Test with simple YouTube URLs first
4. Check internet connectivity

### Common Commands for Debugging
```bash
# Check Python version
python --version

# Test imports
python -c "import yt_dlp; print('yt-dlp OK')"
python -c "import telegram; print('telegram OK')"

# Check ffmpeg
ffmpeg -version
```

---

## 🎉 You're Ready!

Your Telegram video downloader bot is now ready to use! Send a video URL to test it out.

**Pro Tips:**
- Start with YouTube URLs for testing
- Monitor the first few downloads
- Use the admin panel to track usage
- Share with friends once stable

**Need help?** Check the logs and error messages - they usually point to the exact issue!
