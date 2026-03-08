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
        "This bot sends your location to trusted contacts in case of emergency.\n\n"
        "First, what is your name?"
    )

    context.user_data["step"] = "name"


# ---------------- TEXT HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    step = context.user_data.get("step")
    text = update.message.text
    user_id = update.message.from_user.id

    # ----- NAME -----
    if step == "name":

        context.user_data["name"] = text

        await update.message.reply_text(
            "Send the username of your FIRST emergency contact.\n\n"
            "Example:\n@johnsmith"
        )

        context.user_data["step"] = "contact1"
        return

    # ----- CONTACT 1 -----
    if step == "contact1":

        context.user_data["contact1"] = text

        keyboard = [
            [KeyboardButton("➕ Add Second Contact")],
            [KeyboardButton("⏭ Skip")]
        ]

        await update.message.reply_text(
            "Would you like to add a second emergency contact?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True
            )
        )

        context.user_data["step"] = "ask_second"
        return

    # ----- ASK SECOND -----
    if step == "ask_second":

        if text == "➕ Add Second Contact":

            await update.message.reply_text(
                "Send the username of your second emergency contact.\n\nExample:\n@janedoe"
            )

            context.user_data["step"] = "contact2"
            return

        if text == "⏭ Skip":
            contact2 = None
        else:
            return

        # save user
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

    # ----- CONTACT 2 -----
    if step == "contact2":

        contact2 = text

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

    # ----- MAIN MENU BUTTON -----
    if text == "🚨 SEND EMERGENCY LOCATION":

        keyboard = [[KeyboardButton("📍 Send Location", request_location=True)]]

        await update.message.reply_text(
            "🚨 EMERGENCY MODE\n\nSend your LIVE LOCATION now.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True
            )
        )


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
        f"Name:\n{name}\n\n"
        f"Emergency Contacts:\n{contacts_text}\n\n"
        f"⚠️ IMPORTANT\n"
        f"Ask your contacts to start PANICBOT so they can receive alerts.",
        reply_markup=share_button
    )

    keyboard = [[KeyboardButton("🚨 SEND EMERGENCY LOCATION")]]

    await update.message.reply_text(
        "PANICBOT is ready.",
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
        await update.message.reply_text("Please run /start first.")
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
            except:
                pass

    await update.message.reply_text(
        "✅ Emergency alert sent to your contacts."
    )


# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))

app.run_polling()
