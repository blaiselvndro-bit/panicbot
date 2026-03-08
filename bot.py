import sqlite3
from telegram import *
from telegram.ext import *

TOKEN = "YOUR_BOT_TOKEN"

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
name TEXT,
contact1 TEXT,
contact2 TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sos(
session_id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
latitude REAL,
longitude REAL,
confirmed INTEGER DEFAULT 0
)
""")

conn.commit()

app = ApplicationBuilder().token(TOKEN).build()
