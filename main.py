import os
import json
import threading
from datetime import datetime
from flask import Flask
import discord
from discord.ext import commands, tasks
from discord import app_commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. Flask Webサーバーの設定
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Discord Bot is running!"

def run_flask():
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
SPREADSHEET_ID = "1xT829FaaYVMcm3VnFwywoF021s2hTFkisq04uaS5xbA"  # ★ここにIDを貼り付け
sheet = client.open_by_key(SPREADSHEET_ID)

# ==========================================
# 3. Discord Bot & スラッシュコマンドの設定
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 自動見回り対象のチャンネルIDを保持するリスト (簡易的にメモリ保存)
# ※Botが再起動するとリセットされるため、本格運用時はこれも別シートに保存するのが理想です
registered_channels = set()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    # スラッシュコマンドをDiscordに同期
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    # 1分ごとの定期タスクを開始
    if not auto_log_loop.is_running():
        auto_log_loop.start()

# ---- スラッシュコマンド：登録 ----
@bot.tree.command(name="log_register", description="このチャンネルを1分ごとの自動ログ収集対象に登録します")
async def log_register(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    if channel_id in registered_channels:
        await interaction.response.send_message(f"すでにこのチャンネル(#{interaction.channel.name})は登録されています。", ephemeral=True)
    else:
        registered_channels.add(channel_id)
        await interaction.response.send_message(f"成功: #{interaction.channel.name} を自動ログ収集に登録しました！(1分ごとに見回ります)", ephemeral=True)

# ---- スラッシュコマンド：解除 ----
@bot.tree.command(name="log_unregister", description="このチャンネルの自動ログ収集を解除します")
async def log_unregister(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    if channel_id in registered_channels:
        registered_channels.remove(channel_id)
        await interaction.response.send_message(f"解除しました: #{interaction.channel.name} の自動見回りを停止しました。", ephemeral=True)
    else:
        await interaction.response.send_message(f"このチャンネルは登録されていません。", ephemeral=True)

# ==========================================
# 4. 1分ごとの自動見回りタスク (重複防止版)
# ==========================================
@tasks.loop(minutes=1.0)
async def auto_log_loop():
    if not registered_channels:
        return
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 自動見回り中... 対象チャンネル数: {len(registered_channels)}")

    try:
        worksheet = sheet.worksheet("AllLogs")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title="AllLogs", rows="100", cols="5")
        worksheet.append_row(["ServerName", "ChannelName", "UserName", "Content", "Timestamp"])

    # スプレッドシートの全データを一度に取得して、各チャンネルの「最後の時間」を調べる
    all_rows = worksheet.get_all_values()
    
    for channel_id in list(registered_channels):
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        
        # スプレッドシートから、このチャンネルの最新のタイムスタンプ（最後の時間）を探す
        last_timestamp = None
        # 下から上に向かって検索（最新のものが下にあるため）
        for row in reversed(all_rows):
            if len(row) >= 5 and row[0] == channel.guild.name and row[1] == channel.name:
                try:
                    # 文字列をdatetimeオブジェクトに変換
                    last_timestamp = datetime.strptime(row[4], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
                break # 一番最初に見つかった（＝最新の）ログで終了

        try:
            # 新しいログを一時的に貯めるリスト
            new_rows = []
            
            # 過去のメッセージを取得（afterを指定すると、その時間以降のものだけを取得できる）
            # discord.py の history(after=...) は古い順にメッセージが取得されます
            async for message in channel.history(limit=50, after=last_timestamp):
                if message.author.bot:
                    continue
                
                # discord.py の after は「その時間ぴったり」も含まれることがあるため、秒単位で完全一致はスキップ
                formatted_time = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if last_timestamp and formatted_time == last_timestamp.strftime("%Y-%m-%d %H:%M:%S"):
                    continue
                
                row = [
                    channel.guild.name,
                    channel.name,
                    message.author.name,
                    message.content,
                    formatted_time
                ]
                new_rows.append(row)
            
            # 新しいログがあれば、まとめてスプレッドシートの末尾に追加
            if new_rows:
                worksheet.append_rows(new_rows)
                print(f"  └ [#{channel.name}] {len(new_rows)}件の新着ログを追加しました。")
                
        except Exception as e:
            print(f"チャンネル {channel_id} のログ取得中にエラー: {e}")

# ==========================================
# 5. 起動
# ==========================================
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))
