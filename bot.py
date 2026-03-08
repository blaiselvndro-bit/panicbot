import os
import sqlite3
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")

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

conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚨 Welcome to PANICBOT\n\nWhat is your name?"
    )
    context.user_data["step"] = "name"

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    step = context.user_data.get("step")

    if step == "name":
        context.user_data["name"] = update.message.text

        await update.message.reply_text(
            "Send the username of your first emergency contact.\nExample: @john"
        )

        context.user_data["step"] = "contact1"
        return

    if step == "contact1":
        context.user_data["contact1"] = update.message.text

        await update.message.reply_text(
            "Send second contact username or type SKIP"
        )

        context.user_data["step"] = "contact2"
        return

    if step == "contact2":

        contact2 = update.message.text
        if contact2.lower() == "skip":
            contact2 = None

        user_id = update.message.from_user.id

        cursor.execute(
            "INSERT OR REPLACE INTO users VALUES (?,?,?,?)",
            (
                user_id,
                context.user_data["name"],
                context.user_data["contact1"],
                contact2
            )
        )

        conn.commit()

        keyboard = [[KeyboardButton("🚨 SEND EMERGENCY LOCATION")]]

        await update.message.reply_text(
            "Setup complete.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

async def sos_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.text == "🚨 SEND EMERGENCY LOCATION":

        keyboard = [[KeyboardButton("📍 Send Location", request_location=True)]]

        await update.message.reply_text(
            "Send your live location now.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    lat = update.message.location.latitude
    lon = update.message.location.longitude

    user_id = update.message.from_user.id

    cursor.execute(
        "SELECT name,contact1,contact2 FROM users WHERE user_id=?",
        (user_id,)
    )

    data = cursor.fetchone()

    if not data:
        return

    name, c1, c2 = data

    message = f"""
🚨 EMERGENCY ALERT

{name} may be in danger.

Location:
https://maps.google.com/?q={lat},{lon}
"""

    if c1:
        try:
            await context.bot.send_message(c1, message)
        except:
            pass

    if c2:
        try:
            await context.bot.send_message(c2, message)
        except:
            pass

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.TEXT, sos_button))

app.run_polling()
