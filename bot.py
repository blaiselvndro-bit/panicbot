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
BOT_USERNAME = "YOUR_BOT_USERNAME"

# ---------------- DATABASE ----------------

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
    cursor.execute(
        "UPDATE users SET contacts=? WHERE user_id=?",
        (contacts_str, user_id)
    )
    conn.commit()

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
        (user.id, user.username)
    )

    conn.commit()

    cursor.execute(
        "SELECT name,contacts FROM users WHERE user_id=?",
        (user.id,)
    )

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
        [InlineKeyboardButton("Change Name", callback_data="change_name")],
        [InlineKeyboardButton("Edit Emergency Contacts", callback_data="edit_contacts")]
    ])

    await update.message.reply_text(
        "PANICBOT Menu",
        reply_markup=keyboard
    )

# ---------------- TEXT HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user_id = update.message.from_user.id
    step = context.user_data.get("step")

    if step == "name":

        cursor.execute(
            "UPDATE users SET name=? WHERE user_id=?",
            (text, user_id)
        )

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

        context.user_data["step"] = "choose_contacts"

# ---------------- INLINE BUTTONS ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # choose number of contacts
    if data.startswith("contacts_"):

        count = int(data.split("_")[1])

        context.user_data["contact_count"] = count
        context.user_data["contacts"] = []
        context.user_data["step"] = "add_contact"

        await query.edit_message_text(
            "Send username for contact 1\nExample: @username"
        )
        return

    # cancel sos
    if data == "cancel_sos":

        context.user_data["cancelled"] = True
        await query.edit_message_text("SOS cancelled.")
        return

    # confirm sos
    if data.startswith("confirm_"):

        alert_id = int(data.split("_")[1])

        cursor.execute(
            "UPDATE alerts SET confirmed=1 WHERE alert_id=?",
            (alert_id,)
        )

        conn.commit()

        cursor.execute(
            "SELECT sender_id FROM alerts WHERE alert_id=?",
            (alert_id,)
        )

        sender = cursor.fetchone()[0]
        username = query.from_user.username

        await query.edit_message_text("Alert confirmed.")

        await context.bot.send_message(
            sender,
            f"@{username} confirmed your SOS."
        )

        await context.bot.send_message(
            sender,
            "When you are in danger press SEND LOCATION.",
            reply_markup=main_keyboard()
        )

# ---------------- LOCATION HANDLER ----------------

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    lat = update.message.location.latitude
    lon = update.message.location.longitude

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Cancel SOS", callback_data="cancel_sos")]
    ])

    msg = await update.message.reply_text(
        "SOS will send in 10 seconds.",
        reply_markup=keyboard
    )

    await asyncio.sleep(10)

    if context.user_data.get("cancelled"):
        context.user_data["cancelled"] = False
        return

    await trigger_alert(update, context, lat, lon)

# ---------------- ALERT ----------------

async def trigger_alert(update, context, lat, lon):

    user_id = update.effective_user.id

    cursor.execute(
        "SELECT name FROM users WHERE user_id=?",
        (user_id,)
    )

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

        await context.bot.send_message(
            contact,
            f"🚨 EMERGENCY ALERT\n{name} may be in danger.",
            reply_markup=keyboard
        )

        await context.bot.send_location(contact, lat, lon)

        context.job_queue.run_repeating(
            reminder_job,
            interval=120,
            first=120,
            data={"alert_id": alert_id}
        )

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

    await context.bot.send_message(
        contact,
        "🚨 REMINDER: Emergency alert not yet confirmed.",
        reply_markup=keyboard
    )

    await context.bot.send_location(contact, lat, lon)

# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()
