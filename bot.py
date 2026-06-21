import os
import re
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# 指定讀取名為 token.env 的檔案
load_dotenv(dotenv_path="token.env")

# 從環境變數中取得 Token
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ 錯誤：在 token.env 中找不到 TELEGRAM_BOT_TOKEN，請檢查檔案內容！")

# 複製開源項目的精準比對正則表達式 (X/Twitter, Threads, Instagram, TikTok)
TWITTER_REGEX = r'(https?://(?:www\.)?(?:twitter\.com|x\.com)/[a-zA-Z0-9_]+/status/\d+)'
THREADS_REGEX = r'(https?://(?:www\.)?threads\.net/(?:@[a-zA-Z0-9_\.]+)/post/[a-zA-Z0-9_\-]+)'
INSTAGRAM_REGEX = r'(https?://(?:www\.)?instagram\.com/(?:p|reel)/[a-zA-Z0-9_\-]+)'
TIKTOK_REGEX = r'(https?://(?:www\.)?(?:vt\.tiktok\.com|tiktok\.com)/[a-zA-Z0-9_/]+)'

async def fix_social_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_message = update.message.text
    
    # 用來存放轉換後的網址清單
    fixed_urls = []

    # 1. 處理 Twitter / X 網址
    twitter_matches = re.findall(TWITTER_REGEX, user_message)
    for match in twitter_matches:
        # 將 x.com 或 twitter.com 替換成 fxtwitter.com
        fixed = re.sub(r'https?://(?:www\.)?(?:twitter\.com|x\.com)', 'https://fxtwitter.com', match)
        fixed_urls.append(f"🐦 <b>Twitter / X 預覽：</b>\n{fixed}")

    # 2. 處理 Threads 脆 網址
    threads_matches = re.findall(THREADS_REGEX, user_message)
    for match in threads_matches:
        # 將 threads.net 替換成 fxthreads.com
        fixed = re.sub(r'https?://(?:www\.)?threads\.net', 'https://fxthreads.com', match)
        fixed_urls.append(f"🧵 <b>Threads 脆 預覽：</b>\n{fixed}")

    # 3. 處理 Instagram 網址 (開源項目內建使用 ddinstagram)
    instagram_matches = re.findall(INSTAGRAM_REGEX, user_message)
    for match in instagram_matches:
        fixed = re.sub(r'https?://(?:www\.)?instagram\.com', 'https://ddinstagram.com', match)
        fixed_urls.append(f"📸 <b>Instagram 預覽：</b>\n{fixed}")

    # 4. 處理 TikTok 抖音網址 (開源項目額外支援的 vxtiktok)
    tiktok_matches = re.findall(TIKTOK_REGEX, user_message)
    for match in tiktok_matches:
        fixed = re.sub(r'https?://(?:www\.)?(?:vt\.tiktok\.com|tiktok\.com)', 'https://vxtiktok.com', match)
        fixed_urls.append(f"🎵 <b>TikTok 預覽：</b>\n{fixed}")

    # 如果訊息中包含任何需要轉換的社群網址
    if fixed_urls:
        # 串接所有轉換完成的網址，用兩個換行隔開
        response_text = "\n\n".join(fixed_urls)
        
        # 發送回覆
        await update.message.reply_text(
            text=response_text,
            parse_mode="HTML"
        )

def main():
    # 初始化機器人
    application = Application.builder().token(BOT_TOKEN).build()

    # 監聽群組與私訊內的所有文字訊息
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fix_social_links))

    print("====================================================")
    print(" 🚀【FixTweet 開源移植整合版】機器人已成功啟動！")
    print(" 目前支援自動轉換優化：X(Twitter)、Threads、IG、TikTok")
    print("====================================================")
    application.run_polling()

if __name__ == "__main__":
    main()