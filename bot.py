import os
import sqlite3
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")

# ---------------- DATABASE ----------------

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
username TEXT,
name TEXT,
contact1 INTEGER,
contact2 INTEGER
)
""")

conn.commit()

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user

    # Register user in database
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
        (user.id, user.username)
    )

    conn.commit()

    await update.message.reply_text(
        "🚨 Welcome to PANICBOT\n\n"
        "This bot will send your location to trusted contacts if you are in danger.\n\n"
        "First, what is your name?"
    )

    context.user_data["step"] = "name"


# ---------------- TEXT HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    step = context.user_data.get("step")
    text = update.message.text
    user_id = update.message.from_user.id

    # ---------- NAME ----------
    if step == "name":

        cursor.execute(
            "UPDATE users SET name=? WHERE user_id=?",
            (text, user_id)
        )

        conn.commit()

        await update.message.reply_text(
            "Send the username of your FIRST emergency contact.\n\nExample:\n@username"
        )

        context.user_data["step"] = "contact1"
        return


    # ---------- CONTACT 1 ----------
    if step == "contact1":

        username = text.replace("@","")

        cursor.execute(
            "SELECT user_id FROM users WHERE username=?",
            (username,)
        )

        result = cursor.fetchone()

        if not result:
            await update.message.reply_text(
                "⚠️ That user hasn't started PANICBOT yet.\n\n"
                "Ask them to start the bot first, then send their username again."
            )
            return

        context.user_data["contact1"] = result[0]

        await update.message.reply_text(
            "Send the username of your SECOND emergency contact or type SKIP."
        )

        context.user_data["step"] = "contact2"
        return


    # ---------- CONTACT 2 ----------
    if step == "contact2":

        if text.lower() == "skip":
            contact2 = None

        else:

            username = text.replace("@","")

            cursor.execute(
                "SELECT user_id FROM users WHERE username=?",
                (username,)
            )

            result = cursor.fetchone()

            if not result:
                await update.message.reply_text(
                    "⚠️ That user hasn't started PANICBOT yet."
                )
                return

            contact2 = result[0]

        contact1 = context.user_data["contact1"]

        cursor.execute(
            "UPDATE users SET contact1=?, contact2=? WHERE user_id=?",
            (contact1, contact2, user_id)
        )

        conn.commit()

        keyboard = [[KeyboardButton("📍 Send Location", request_location=True)]]

        await update.message.reply_text(
            "✅ Setup Complete.\n\n"
            "When you are in danger press the button below to send your location.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True
            )
        )

        context.user_data["step"] = None
        return


# ---------------- LOCATION HANDLER ----------------

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    cursor.execute(
        "SELECT name, contact1, contact2 FROM users WHERE user_id=?",
        (user_id,)
    )

    data = cursor.fetchone()

    if not data:
        await update.message.reply_text("Run /start first.")
        return

    name, contact1, contact2 = data

    message = (
        f"🚨 EMERGENCY ALERT\n\n"
        f"{name} may be in danger.\n\n"
        f"Location:\n"
        f"https://maps.google.com/?q={lat},{lon}"
    )

    for contact in [contact1, contact2]:

        if contact:

            try:
                await context.bot.send_message(contact, message)
                await context.bot.send_location(contact, lat, lon)

            except Exception as e:
                print(e)

    await update.message.reply_text(
        "🚨 Emergency alert sent to your contacts."
    )


# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))

app.run_polling()
