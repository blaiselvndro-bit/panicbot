import os
import sqlite3
import asyncio
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove
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

def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📍 Send Location"],
            ["⚙️ Menu"]
        ],
        resize_keyboard=True
    )

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
            "When you are in danger press the button to send your location.",
            reply_markup=main_keyboard()
        )
        return

    await update.message.reply_text(
        "🚨 Welcome to PANICBOT\n\nWhat is your name?"
    )

    context.user_data["step"] = "name"


# ---------------- TEXT HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user_id = update.message.from_user.id
    step = context.user_data.get("step")

    # ---------- MENU ----------
    if text == "⚙️ Menu":

        keyboard = ReplyKeyboardMarkup(
            [
                ["Change Name"],
                ["Edit Emergency Contacts"],
                ["⬅ Back"]
            ],
            resize_keyboard=True
        )

        await update.message.reply_text("Menu:", reply_markup=keyboard)
        return


    if text == "⬅ Back":

        await update.message.reply_text(
            "When you are in danger press the button to send your location.",
            reply_markup=main_keyboard()
        )
        return


    if text == "Change Name":

        await update.message.reply_text("Enter new name:")
        context.user_data["step"] = "name"
        return


    if text == "Edit Emergency Contacts":

        keyboard = ReplyKeyboardMarkup(
            [["1","2","3","4","5"]],
            resize_keyboard=True
        )

        await update.message.reply_text(
            "How many emergency contacts do you want? (1-5)",
            reply_markup=keyboard
        )

        context.user_data["step"] = "choose_contacts"
        return


    # ---------- NAME ----------
    if step == "name":

        cursor.execute(
            "UPDATE users SET name=? WHERE user_id=?",
            (text, user_id)
        )

        conn.commit()

        keyboard = ReplyKeyboardMarkup(
            [["1","2","3","4","5"]],
            resize_keyboard=True
        )

        await update.message.reply_text(
            "How many emergency contacts do you want? (1-5)",
            reply_markup=keyboard
        )

        context.user_data["step"] = "choose_contacts"
        return


    # ---------- CHOOSE CONTACT COUNT ----------
    if step == "choose_contacts":

        count = int(text)

        context.user_data["contact_count"] = count
        context.user_data["contacts"] = []
        context.user_data["step"] = "add_contact"

        await update.message.reply_text(
            f"Send username for contact 1\nExample: @username",
            reply_markup=ReplyKeyboardRemove()
        )

        return


    # ---------- ADD CONTACT ----------
    if step == "add_contact":

        username = text.replace("@","")

        cursor.execute(
            "SELECT user_id FROM users WHERE username=?",
            (username,)
        )

        result = cursor.fetchone()

        if not result:
            await update.message.reply_text("User hasn't started PANICBOT yet.")
            return

        context.user_data["contacts"].append(result[0])

        current = len(context.user_data["contacts"])
        total = context.user_data["contact_count"]

        if current < total:

            await update.message.reply_text(
                f"Send username for contact {current+1}"
            )

        else:

            save_contacts(user_id, context.user_data["contacts"])

            await update.message.reply_text(
                "Setup Complete. When you are in danger press the button below to send your location.",
                reply_markup=main_keyboard()
            )

            context.user_data.clear()

        return


    # ---------- SEND LOCATION ----------
    if text == "📍 Send Location":

        keyboard = [[KeyboardButton("Send Location", request_location=True)]]

        await update.message.reply_text(
            "Press to send your location.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )


# ---------------- LOCATION HANDLER ----------------

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    context.user_data["pending_location"] = (lat, lon)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Cancel SOS", callback_data="cancel_sos")]]
    )

    msg = await update.message.reply_text(
        "SOS will send in 10 seconds.\nPress cancel to stop.",
        reply_markup=keyboard
    )

    context.user_data["countdown_message"] = msg.message_id

    await asyncio.sleep(10)

    if context.user_data.get("cancelled"):
        context.user_data["cancelled"] = False
        return

    await context.bot.delete_message(update.effective_chat.id, msg.message_id)

    await trigger_alert(update, context, lat, lon)


# ---------------- CANCEL SOS ----------------

async def cancel_sos(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    context.user_data["cancelled"] = True

    await query.edit_message_text("SOS cancelled.")


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

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("CONFIRM", callback_data=f"confirm_{alert_id}")]]
        )

        message = f"🚨 EMERGENCY ALERT\n{name} may be in danger."

        await context.bot.send_message(contact, message, reply_markup=keyboard)
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

    cursor.execute("SELECT name FROM users WHERE user_id=?", (sender,))
    name = cursor.fetchone()[0]

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("CONFIRM", callback_data=f"confirm_{alert_id}")]]
    )

    await context.bot.send_message(
        contact,
        f"🚨 REMINDER\n{name} may be in danger.",
        reply_markup=keyboard
    )

    await context.bot.send_location(contact, lat, lon)


# ---------------- CONFIRM ----------------

async def confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    alert_id = int(query.data.split("_")[1])

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
        "When you are in danger press the button to send your location.",
        reply_markup=main_keyboard()
    )


# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(CallbackQueryHandler(cancel_sos, pattern="cancel_sos"))
app.add_handler(CallbackQueryHandler(confirm_handler, pattern="confirm_"))

app.run_polling()
