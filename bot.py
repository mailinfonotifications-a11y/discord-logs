import os
import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 1. Google Sheets APIのセットアップ
# ※Renderの環境変数(Environment Variables)にJSONの内容を保存するか、
#   GitHub（非公開リポジトリ）にcredentials.jsonを配置してください。
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

# 事前に作成したスプレッドシートの名前、またはURL
SPREADSHEET_NAME = "Discord_Log_Database"
sheet = client.open(SPREADSHEET_NAME)

# 2. Discord Botのセットアップ
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_code="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

@bot.command(name="log")
async def save_log(ctx, *channels: discord.TextChannel):
    """
    使い方: !log #channel1 #channel2
    指定されたチャンネルの過去ログを取得し、スプレッドシートに保存・更新します。
    """
    if not channels:
        await ctx.send("チャンネルを1つ以上指定してください。(例: `!log #general`)")
        return

    await ctx.send("ログの取得およびスプレッドシートへの同期を開始します...")

    # 「Logs」という名前のシートに全データを蓄積する構成の例
    try:
        worksheet = sheet.worksheet("AllLogs")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title="AllLogs", rows="100", cols="5")
        worksheet.append_row(["ServerName", "ChannelName", "UserName", "Content", "Timestamp"])

    for channel in channels:
        # 既存の同一チャンネルのログを上書き(更新)したいため、一度古いデータを消すか、
        # ここではシンプルに最新100件を取得して追加するロジックにします
        async for message in channel.history(limit=100):
            # 既に同じメッセージIDがあるかチェックする処理などを入れるとより確実です
            if message.author.bot:
                continue # Botのメッセージは除外する場合
                
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

# Renderの環境変数からトークンを読み込む
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
