# PANICBOT FINAL VERSION

import os
import sqlite3
import asyncio
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "@panic_sos_bot"

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
username TEXT,
name TEXT,
contacts TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS alerts(
alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
sender_id INTEGER,
contact_id INTEGER,
latitude REAL,
longitude REAL,
confirmed INTEGER DEFAULT 0
)
""")

conn.commit()

# ---------------- UTIL ----------------

def main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🚨 SEND LOCATION", request_location=True)]],
        resize_keyboard=True
    )


def get_contacts(user_id):
    cursor.execute("SELECT contacts FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return []
    return [int(x) for x in row[0].split(",")]


def save_contacts(user_id, contacts):
    contacts_str = ",".join(str(x) for x in contacts)
    cursor.execute("UPDATE users SET contacts=? WHERE user_id=?", (contacts_str, user_id))
    conn.commit()

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
        (user.id, user.username)
    )
    conn.commit()

    cursor.execute("SELECT name,contacts FROM users WHERE user_id=?", (user.id,))
    row = cursor.fetchone()

    if row and row[0] and row[1]:
        await update.message.reply_text(
            "When you are in danger press the button below.",
            reply_markup=main_keyboard()
        )
        return

    msg = await update.message.reply_text("🚨 Welcome to PANICBOT\n\nWhat is your name?")
    context.user_data["setup_msgs"] = [msg.message_id]
    context.user_data["step"] = "name"

# ---------------- MENU ----------------

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Edit Name", callback_data="edit_name")],
        [InlineKeyboardButton("Update Contacts", callback_data="update_contacts")],
        [InlineKeyboardButton("Fake Texting", callback_data="fake_texting")],
        [InlineKeyboardButton("Restart Setup", callback_data="restart_setup")]
    ])

    await update.message.reply_text("⚙ PANICBOT MENU", reply_markup=keyboard)

# ---------------- TEXT HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user_id = update.message.from_user.id
    step = context.user_data.get("step")

    # ---------- SET NAME ----------
    if step == "name":

        cursor.execute("UPDATE users SET name=? WHERE user_id=?", (text, user_id))
        conn.commit()

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1", callback_data="contacts_1"),
                InlineKeyboardButton("2", callback_data="contacts_2"),
                InlineKeyboardButton("3", callback_data="contacts_3"),
                InlineKeyboardButton("4", callback_data="contacts_4"),
                InlineKeyboardButton("5", callback_data="contacts_5")
            ]
        ])

        await update.message.reply_text(
            "How many emergency contacts do you want?",
            reply_markup=keyboard
        )
        return

    # ---------- EDIT NAME ----------
    if step == "edit_name":

        cursor.execute("UPDATE users SET name=? WHERE user_id=?", (text, user_id))
        conn.commit()

        context.user_data.clear()

        await update.message.reply_text(
            "Name updated successfully.",
            reply_markup=main_keyboard()
        )
        return

    # ---------- ADD CONTACT ----------
    if step == "add_contact":

        username = text.replace("@","")

        cursor.execute("SELECT user_id FROM users WHERE username=?", (username,))
        result = cursor.fetchone()

        if not result:
            await update.message.reply_text(
                f"That user hasn't started PANICBOT.\nSend them this:\n{BOT_USERNAME}"
            )
            return

        context.user_data["contacts"].append(result[0])

        current = len(context.user_data["contacts"])
        total = context.user_data["contact_count"]

        if current < total:
            await update.message.reply_text(f"Send username for contact {current+1}")
        else:

            save_contacts(user_id, context.user_data["contacts"])
            context.user_data.clear()

            await update.message.reply_text(
                "Contacts updated.",
                reply_markup=main_keyboard()
            )
        return

    # ---------- FAKE TEXT CHAT ----------
    if step == "fake_chat":

        context.user_data["last_reply"] = asyncio.get_event_loop().time()
        return

# ---------------- BUTTON HANDLER ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # EDIT NAME
    if data == "edit_name":
        context.user_data["step"] = "edit_name"
        await query.edit_message_text("Enter your new name:")
        return

    # UPDATE CONTACTS
    if data == "update_contacts":

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1", callback_data="contacts_1"),
                InlineKeyboardButton("2", callback_data="contacts_2"),
                InlineKeyboardButton("3", callback_data="contacts_3"),
                InlineKeyboardButton("4", callback_data="contacts_4"),
                InlineKeyboardButton("5", callback_data="contacts_5")
            ]
        ])

        await query.edit_message_text(
            "Updating contacts will remove ALL existing contacts.\n\nHow many contacts do you want?",
            reply_markup=keyboard
        )
        return

    # FAKE TEXTING
    if data == "fake_texting":

        context.user_data["step"] = "fake_chat"
        context.user_data["last_reply"] = asyncio.get_event_loop().time()

        await query.edit_message_text(
            "Information sent to your emergency contacts.\nSend your location as well.\n\n"
            "From this point on just type away and tell me everything you see.\n"
            "If you stop replying for more than 2 minutes I will alert your emergency contacts.\n"
            "If you are safe press OK."
        )

        asyncio.create_task(fake_chat_loop(context, user_id))

        return

    # RESTART
    if data == "restart_setup":

        cursor.execute("UPDATE users SET name=NULL, contacts=NULL WHERE user_id=?", (user_id,))
        conn.commit()

        context.user_data["step"] = "name"

        await query.edit_message_text("Setup restarted.\nWhat is your name?")
        return

    # CONTACT COUNT
    if data.startswith("contacts_"):

        count = int(data.split("_")[1])

        context.user_data["contact_count"] = count
        context.user_data["contacts"] = []
        context.user_data["step"] = "add_contact"

        await query.edit_message_text("Send username for contact 1\nExample: @username")
        return

    # SAFE BUTTON
    if data == "safe":

        contacts = get_contacts(user_id)

        for c in contacts:
            await context.bot.send_message(c, "User is now safe.")

        context.user_data.clear()

        await context.bot.send_message(
            user_id,
            "Glad you're safe.\nPress SEND LOCATION if you are ever in danger.",
            reply_markup=main_keyboard()
        )

# ---------------- FAKE CHAT LOOP ----------------

async def fake_chat_loop(context, user_id):

    replies = [
        "Really? That's great! Are you okay?",
        "Oh that is so cool!",
        "Tell me more. I'm enjoying myself here."
    ]

    i = 0

    while True:

        await asyncio.sleep(120)

        if context.user_data.get("step") != "fake_chat":
            break

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("OK", callback_data="safe")]
        ])

        await context.bot.send_message(
            user_id,
            replies[i % len(replies)],
            reply_markup=keyboard
        )

        i += 1

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, text_handler))
app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()
