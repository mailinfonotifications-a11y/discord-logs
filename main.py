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
# 4. 1分ごとの自動見回りタスク (重複完全ブロック版)
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

    # 1. 現在スプレッドシートにある全データを取得して「すでに存在するログのセット」を作る
    all_rows = worksheet.get_all_values()
    existing_logs = set()
    
    # 2行目以降のデータを合体させて一意のキーにする
    for row in all_rows[1:]:
        if len(row) >= 5:
            # サーバー名_チャンネル名_ユーザー名_内容_時間
            log_key = f"{row[0]}_{row[1]}_{row[2]}_{row[3]}_{row[4]}"
            existing_logs.add(log_key)

    for channel_id in list(registered_channels):
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        
        try:
            new_rows = []
            # 直近50件のメッセージを確認
            async for message in channel.history(limit=50):
                if message.author.bot:
                    continue
                
                formatted_time = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                
                # これから追加しようとしているメッセージのキーを作成
                current_key = f"{channel.guild.name}_{channel.name}_{message.author.name}_{message.content}_{formatted_time}"
                
                # ❌ すでにスプレッドシートに存在する、または今回の一括処理内で重複している場合は【絶対に無視】する
                if current_key in existing_logs:
                    continue
                
                row = [
                    channel.guild.name,
                    channel.name,
                    message.author.name,
                    message.content,
                    formatted_time
                ]
                new_rows.append(row)
                existing_logs.add(current_key) # 今回追加する分もセットに記録しておく
            
            # 本当に新しいログだけをまとめて追加
            if new_rows:
                # 送信日時が古い順にスプレッドシートの下に追加されるように逆順にする
                new_rows.reverse()
                worksheet.append_rows(new_rows)
                print(f"  └ [#{channel.name}] 新着ログ {len(new_rows)} 件を安全に追加しました。")
                
        except Exception as e:
            print(f"チャンネル {channel_id} のログ取得中にエラー: {e}")

# ==========================================
# 5. 起動
# ==========================================
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))
