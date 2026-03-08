import os
import sqlite3
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
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
name TEXT,
contact1 TEXT,
contact2 TEXT
)
""")

conn.commit()

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🚨 Welcome to PANICBOT\n\n"
        "This bot sends your location to trusted contacts if you are in danger.\n\n"
        "First, what is your name?"
    )

    context.user_data["step"] = "name"


# ---------------- TEXT HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    step = context.user_data.get("step")
    text = update.message.text
    user_id = update.message.from_user.id

    if step == "name":

        context.user_data["name"] = text

        await update.message.reply_text(
            "Send the username of your FIRST emergency contact.\n\nExample:\n@johnsmith"
        )

        context.user_data["step"] = "contact1"
        return


    if step == "contact1":

        context.user_data["contact1"] = text

        await update.message.reply_text(
            "Send the username of your SECOND emergency contact or type SKIP."
        )

        context.user_data["step"] = "contact2"
        return


    if step == "contact2":

        contact2 = text

        if contact2.lower() == "skip":
            contact2 = None

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

        await finish_setup(update, context)
        return


# ---------------- FINISH SETUP ----------------

async def finish_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):

    name = context.user_data["name"]
    c1 = context.user_data["contact1"]
    c2 = context.user_data.get("contact2")

    contacts_text = f"• {c1}"
    if c2:
        contacts_text += f"\n• {c2}"

    share_button = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📤 Share PANICBOT",
            url="https://t.me/YOUR_BOT_USERNAME"
        )]
    ])

    await update.message.reply_text(
        f"✅ Setup Complete\n\n"
        f"Name: {name}\n\n"
        f"Emergency Contacts:\n{contacts_text}\n\n"
        f"⚠️ IMPORTANT\n"
        f"Ask your contacts to START this bot so they can receive emergency alerts.",
        reply_markup=share_button
    )

    # Immediately request location

    keyboard = [[KeyboardButton("📍 Send Location", request_location=True)]]

    await update.message.reply_text(
        "When you are in danger, press the button below to send your location.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True
        )
    )

    context.user_data["step"] = None


# ---------------- LOCATION HANDLER ----------------

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    cursor.execute(
        "SELECT name,contact1,contact2 FROM users WHERE user_id=?",
        (user_id,)
    )

    data = cursor.fetchone()

    if not data:
        await update.message.reply_text("Run /start first.")
        return

    name, c1, c2 = data

    message = (
        f"🚨 EMERGENCY ALERT\n\n"
        f"{name} may be in danger.\n\n"
        f"Location:\n"
        f"https://maps.google.com/?q={lat},{lon}"
    )

    for contact in [c1, c2]:

        if contact:

            try:
                await context.bot.send_message(contact, message)
                await context.bot.send_location(contact, lat, lon)

            except Exception as e:
                print(e)

    await update.message.reply_text(
        "🚨 Emergency alert sent."
    )


# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))

app.run_polling()
