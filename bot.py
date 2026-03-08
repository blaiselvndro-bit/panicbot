import os
import sqlite3
import asyncio
import random
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

    # keyword safety stop
    if step == "fake_chat" and text.lower().strip() == "i am ok":

        contacts = get_contacts(user_id)

        for c in contacts:
            await context.bot.send_message(
                c,
                f"✅ @{update.message.from_user.username} is SAFE."
            )

        context.user_data.clear()

        await update.message.reply_text(
            "Glad you're safe.\nFake texting stopped.",
            reply_markup=main_keyboard()
        )
        return

    # ---------- NAME SETUP ----------
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

        msg = await update.message.reply_text(
            "How many emergency contacts do you want?",
            reply_markup=keyboard
        )

        context.user_data["setup_msgs"].append(msg.message_id)
        return

    # ---------- EDIT NAME ----------
    if step == "edit_name":

        cursor.execute("UPDATE users SET name=? WHERE user_id=?", (text, user_id))
        conn.commit()

        context.user_data.clear()

        await update.message.reply_text(
            "Name updated.",
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
                f"That user hasn't started PANICBOT.\n\nSend them this:\n{BOT_USERNAME}"
            )
            return

        context.user_data["contacts"].append(result[0])

        current = len(context.user_data["contacts"])
        total = context.user_data["contact_count"]

        if current < total:

            msg = await update.message.reply_text(f"Send username for contact {current+1}")
            context.user_data["setup_msgs"].append(msg.message_id)

        else:

            save_contacts(user_id, context.user_data["contacts"])

            for mid in context.user_data.get("setup_msgs", []):
                try:
                    await context.bot.delete_message(update.effective_chat.id, mid)
                except:
                    pass

            await update.message.reply_text(
                "Setup Complete.\nWhen you are in danger press the button below.",
                reply_markup=main_keyboard()
            )

            context.user_data.clear()

        return

    # ---------- FAKE TEXTING QUESTIONS ----------

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

        cursor.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
        username = cursor.fetchone()[0]

        message = (
            f"@{username} is in a emergency and needs your help.\n\n"
            f"Clues:\n"
            f"People I'm with: {context.user_data['fake_q1']}\n"
            f"Location: {context.user_data['fake_q2']}\n"
            f"Landmarks: {context.user_data['fake_q3']}\n"
            f"Car plate: {context.user_data['fake_q4']}"
        )

        contacts = get_contacts(user_id)

        for c in contacts:
            await context.bot.send_message(c, message)

        context.user_data["step"] = "fake_chat"

        await update.message.reply_text(
            "Information sent to your emergency contacts.\n"
            "Send your location as well.\n\n"
            "⚠️ IMPORTANT:\n"
            "Every 30 seconds I will send a message with an OK button.\n"
            "You must press OK within 10 seconds.\n"
            "If you don't, I will alert your emergency contacts.\n\n"
            "You can also type 'I am OK' to stop fake texting."
        )

        asyncio.create_task(fake_chat_loop(context, user_id))
        return

# ---------------- PHOTO HANDLER ----------------

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id
    contacts = get_contacts(user_id)

    photo = update.message.photo[-1].file_id

    for c in contacts:

        await context.bot.send_message(
            c,
            f"📷 Photo sent by @{update.message.from_user.username}"
        )

        await context.bot.send_photo(c, photo)

# ---------------- FAKE CHAT LOOP ----------------

async def fake_chat_loop(context, user_id):

    replies = [
        "Really? That's great! Are you okay?",
        "Oh that is so cool!",
        "Tell me more. I'm enjoying myself here."
    ]

    while True:

        await asyncio.sleep(30)

        if context.user_data.get("step") != "fake_chat":
            break

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("OK", callback_data="fake_safe")]
        ])

        await context.bot.send_message(
            user_id,
            random.choice(replies),
            reply_markup=keyboard
        )

        await asyncio.sleep(10)

        if context.user_data.get("step") == "fake_chat":

            contacts = get_contacts(user_id)

            for c in contacts:
                await context.bot.send_message(
                    c,
                    "⚠️ User stopped responding during fake texting."
                )

            break

# ---------------- BUTTON HANDLER ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "fake_safe":

        contacts = get_contacts(user_id)

        for c in contacts:
            await context.bot.send_message(c, "User is now safe.")

        context.user_data.clear()

        await query.edit_message_text("Glad you're safe.")

        await context.bot.send_message(
            user_id,
            "When you are in danger press the button below.",
            reply_markup=main_keyboard()
        )

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

    await msg.edit_text("SOS sent to your emergency contacts. Please wait for confirmation.")

    await trigger_alert(update, context, lat, lon)

# ---------------- ALERT ----------------

async def trigger_alert(update, context, lat, lon):

    user_id = update.effective_user.id

    cursor.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    name = cursor.fetchone()[0]

    contacts = get_contacts(user_id)

    for contact in contacts:

        cursor.execute(
            "INSERT INTO alerts (sender_id,contact_id,latitude,longitude) VALUES (?,?,?,?)",
            (user_id, contact, lat, lon)
        )

        alert_id = cursor.lastrowid
        conn.commit()

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("CONFIRM", callback_data=f"confirm_{alert_id}")]
        ])

        await context.bot.send_message(contact, f"🚨 EMERGENCY ALERT\n{name} may be in danger.", reply_markup=keyboard)

        await context.bot.send_location(contact, lat, lon)

        context.job_queue.run_repeating(reminder_job, interval=60, first=60, data={"alert_id": alert_id})

# ---------------- REMINDER ----------------

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):

    alert_id = context.job.data["alert_id"]

    cursor.execute(
        "SELECT sender_id,contact_id,latitude,longitude,confirmed FROM alerts WHERE alert_id=?",
        (alert_id,)
    )

    row = cursor.fetchone()

    if not row:
        return

    sender, contact, lat, lon, confirmed = row

    if confirmed:
        context.job.schedule_removal()
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("CONFIRM", callback_data=f"confirm_{alert_id}")]
    ])

    await context.bot.send_message(contact, "🚨 EMERGENCY ALERT\nReminder: alert not yet confirmed.", reply_markup=keyboard)
    await context.bot.send_location(contact, lat, lon)

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()
