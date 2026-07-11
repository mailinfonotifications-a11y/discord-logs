import os
import json
import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 修正：環境変数からJSON文字列を読み込んで認証する
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_json_string = os.getenv("GOOGLE_CREDENTIALS_JSON")

if creds_json_string:
    creds_dict = json.loads(creds_json_string)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    raise ValueError("環境変数 GOOGLE_CREDENTIALS_JSON が設定されていません。")

client = gspread.authorize(creds)
# （以下、以前のコードと同じ）
