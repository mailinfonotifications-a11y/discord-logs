import os
import json
import threading
from datetime import datetime
from flask import Flask
import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. Flask Webサーバーの設定 (Renderのエラー対策)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Discord Bot is running!"

def run_flask():
    # Renderは環境変数 PORT を指定してくるので、それを読み込んで起動します
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# 2. Google Sheets APIのセットアップ
# ==========================================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")

if json_creds:
    creds_dict = json.loads(json_creds)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)

client = gspread.authorize(creds)
SPREADSHEET_ID = "あなたのスプレッドシートID"  # ★ここにIDを貼り付け
sheet = client.open_by_key(SPREADSHEET_ID)

# ==========================================
# 3. Discord Botのセットアップ
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

@bot.command(name="log")
async def save_log(ctx, *channels: discord.TextChannel):
    if not channels:
        await ctx.send("チャンネルを1つ以上指定してください。(例: `!log #general`)")
        return

    await ctx.send("ログの取得およびスプレッドシートへの同期を開始します...")

    try:
        worksheet = sheet.worksheet("AllLogs")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title="AllLogs", rows="100", cols="5")
        worksheet.append_row(["ServerName", "ChannelName", "UserName", "Content", "Timestamp"])

    for channel in channels:
        async for message in channel.history(limit=100):
            if message.author.bot:
                continue
                
            formatted_time = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            row = [
                ctx.guild.name,
                channel.name,
                message.author.name,
                message.content,
                formatted_time
            ]
            worksheet.append_row(row)

    await ctx.send("データの更新が完了しました！")

# ==========================================
# 4. 同時起動の実行
# ==========================================
if __name__ == "__main__":
    # Flaskを別スレッドでバックグラウンド起動
    t = threading.Thread(target=run_flask)
    t.start()
    
    # Discord Botをメインスレッドで起動
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))
