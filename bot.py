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

    await update.message.reply_text(
        "🚨 Welcome to PANICBOT\n\nWhat is your name?"
    )

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

    # SAFE COMMAND
    if text.lower().strip() == "iam safe":

        contacts = get_contacts(user_id)

        for c in contacts:
            await context.bot.send_message(c, f"✅ @{update.message.from_user.username} is SAFE.")

        context.user_data.clear()

        await update.message.reply_text("Glad you're safe.", reply_markup=main_keyboard())
        return


    # RESPONSE DURING MONITORING
    if step in ["fake_chat", "sos_monitor"]:
        context.user_data["responded"] = True

        if step == "fake_chat":
            if "clues" not in context.user_data:
                context.user_data["clues"] = []
            context.user_data["clues"].append(text)

        return


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


    if step == "edit_name":

        cursor.execute("UPDATE users SET name=? WHERE user_id=?", (text, user_id))
        conn.commit()

        context.user_data.clear()

        await update.message.reply_text(
            "Name updated.",
            reply_markup=main_keyboard()
        )
        return


    if step == "add_contact":

        username = text.replace("@","")

        cursor.execute("SELECT user_id FROM users WHERE username=?", (username,))
        result = cursor.fetchone()

        if not result:
            await update.message.reply_text(
                f"That user hasn't started PANICBOT.\n\nSend them this:\n{BOT_USERNAME}"
            )
            return

        context.user_data["contacts"].append(result[0])

        current = len(context.user_data["contacts"])
        total = context.user_data["contact_count"]

        if current < total:
            await update.message.reply_text(f"Send username for contact {current+1}")

        else:

            save_contacts(user_id, context.user_data["contacts"])

            await update.message.reply_text(
                "Setup Complete.\nWhen you are in danger press the button below.",
                reply_markup=main_keyboard()
            )

            context.user_data.clear()

        return


# ---------- Fake texting questions ----------

    if step == "fake_q1":
        context.user_data["fake_q1"] = text
        context.user_data["step"] = "fake_q2"
        await update.message.reply_text("Where are you?")
        return

    if step == "fake_q2":
        context.user_data["fake_q2"] = text
        context.user_data["step"] = "fake_q3"
        await update.message.reply_text("Any landmarks you can see?")
        return

    if step == "fake_q3":
        context.user_data["fake_q3"] = text
        context.user_data["step"] = "fake_q4"
        await update.message.reply_text("Are you in a car? If yes give plate number.")
        return

    if step == "fake_q4":

        context.user_data["fake_q4"] = text
        context.user_data["clues"] = []
        context.user_data["missed_checks"] = 0

        username = update.message.from_user.username
        contacts = get_contacts(user_id)

        message = (
            f"@{username} may be in danger.\n\n"
            f"People I'm with: {context.user_data['fake_q1']}\n"
            f"Location: {context.user_data['fake_q2']}\n"
            f"Landmarks: {context.user_data['fake_q3']}\n"
            f"Car plate: {context.user_data['fake_q4']}"
        )

        for c in contacts:
            await context.bot.send_message(c, message)

        context.user_data["step"] = "fake_chat"
        context.user_data["username"] = username

        await update.message.reply_text(
            "Information sent to emergency contacts.\n\n"
            "You can type clues anytime.\n"
            "Type 'Iam Safe' when safe."
        )

        asyncio.create_task(fake_chat_loop(context, user_id))


# ---------------- FAKE CHAT LOOP ----------------

async def fake_chat_loop(context, user_id):

    while True:

        await asyncio.sleep(30)

        if context.user_data.get("step") != "fake_chat":
            break

        context.user_data["responded"] = False

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Still Here", callback_data="still_here")]
        ])

        await context.bot.send_message(
            user_id,
            "Let me know if you're fine right now.",
            reply_markup=keyboard
        )

        await asyncio.sleep(10)

        if not context.user_data.get("responded"):

            context.user_data["missed_checks"] += 1
            username = context.user_data.get("username")
            contacts = get_contacts(user_id)

            for c in contacts:
                await context.bot.send_message(
                    c,
                    f"@{username} stopped responding during fake texting."
                )


# ---------------- SOS MONITOR ----------------

async def sos_monitor_loop(context, user_id):

    username = context.user_data.get("username")

    while True:

        await asyncio.sleep(30)

        if context.user_data.get("step") != "sos_monitor":
            break

        context.user_data["responded"] = False

        await context.bot.send_message(
            user_id,
            "Checking on you. Let me know you're okay."
        )

        await asyncio.sleep(10)

        if not context.user_data.get("responded"):

            contacts = get_contacts(user_id)

            for c in contacts:
                await context.bot.send_message(
                    c,
                    f"⚠️ @{username} is not responding after sending an SOS.\nPlease check their location and confirm their safety."
                )


# ---------------- BUTTON HANDLER ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data == "still_here":

        context.user_data["responded"] = True

        await query.edit_message_reply_markup(reply_markup=None)

        await context.bot.send_message(
            user_id,
            "That is great to hear. Let me know once you're safe."
        )
        return


    if data == "cancel_sos":
        context.user_data["cancelled"] = True
        return

    if data == "send_now":
        context.user_data["force_send"] = True
        return


    if data == "fake_texting":
        context.user_data["step"] = "fake_q1"
        await query.edit_message_text("Who are you with?")
        return


# ---------------- LOCATION HANDLER ----------------

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    lat = update.message.location.latitude
    lon = update.message.location.longitude

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Send Now", callback_data="send_now"),
            InlineKeyboardButton("Cancel", callback_data="cancel_sos")
        ]
    ])

    msg = await update.message.reply_text("SOS will send in 10 seconds.", reply_markup=keyboard)

    for i in range(10):

        await asyncio.sleep(1)

        if context.user_data.get("cancelled"):
            context.user_data["cancelled"] = False
            return

        if context.user_data.get("force_send"):
            context.user_data["force_send"] = False
            break

    await msg.edit_text(
        "SOS sent to your emergency contacts. Please wait for confirmation.\n\n"
        "I will check on you every 30 seconds.\n"
        "If you are safe type: Iam Safe"
    )

    user = update.effective_user
    context.user_data["step"] = "sos_monitor"
    context.user_data["username"] = user.username

    asyncio.create_task(sos_monitor_loop(context, user.id))
