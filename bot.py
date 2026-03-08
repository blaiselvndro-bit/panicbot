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
contact1 INTEGER,
contact2 INTEGER
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


# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
        (user.id, user.username)
    )

    conn.commit()

    await update.message.reply_text(
        "🚨 Welcome to PANICBOT\n\nWhat is your name?"
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
            "Send the username of your FIRST emergency contact.\nExample: @username"
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
                "⚠️ That user hasn't started PANICBOT yet."
            )
            return

        context.user_data["contact1"] = result[0]

        keyboard = [[KeyboardButton("SKIP")]]

        await update.message.reply_text(
            "Send the username of your SECOND emergency contact or press SKIP.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )

        context.user_data["step"] = "contact2"
        return


    # ---------- CONTACT 2 ----------
    if step == "contact2":

        if text == "SKIP":
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
            "✅ Setup complete.\n\nPress the button below when you need to send your location.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

        context.user_data["step"] = None


# ---------------- LOCATION HANDLER ----------------

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    sender_id = update.message.from_user.id
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    cursor.execute(
        "SELECT name,contact1,contact2 FROM users WHERE user_id=?",
        (sender_id,)
    )

    name, contact1, contact2 = cursor.fetchone()

    for contact in [contact1, contact2]:

        if not contact:
            continue

        cursor.execute(
            "INSERT INTO alerts (sender_id,contact_id,latitude,longitude) VALUES (?,?,?,?)",
            (sender_id,contact,lat,lon)
        )

        alert_id = cursor.lastrowid
        conn.commit()

        await send_alert(context, alert_id, name, contact, lat, lon)

        # schedule reminder
        context.job_queue.run_repeating(
            reminder_job,
            interval=300,
            first=300,
            data={"alert_id": alert_id}
        )

    await update.message.reply_text("🚨 Emergency alert sent.")


# ---------------- SEND ALERT ----------------

async def send_alert(context, alert_id, name, contact, lat, lon):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("CONFIRM", callback_data=f"confirm_{alert_id}")]
    ])

    message = (
        f"🚨 EMERGENCY ALERT\n\n"
        f"{name} may be in danger.\n\n"
        f"Location:\nhttps://maps.google.com/?q={lat},{lon}"
    )

    await context.bot.send_message(
        chat_id=contact,
        text=message,
        reply_markup=keyboard
    )

    await context.bot.send_location(contact, lat, lon)


# ---------------- REMINDER JOB ----------------

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):

    alert_id = context.job.data["alert_id"]

    cursor.execute(
        "SELECT sender_id,contact_id,latitude,longitude,confirmed FROM alerts WHERE alert_id=?",
        (alert_id,)
    )

    row = cursor.fetchone()

    if not row:
        return

    sender_id, contact, lat, lon, confirmed = row

    if confirmed:
        context.job.schedule_removal()
        return

    cursor.execute(
        "SELECT name FROM users WHERE user_id=?",
        (sender_id,)
    )

    name = cursor.fetchone()[0]

    await send_alert(context, alert_id, name, contact, lat, lon)


# ---------------- CONFIRM BUTTON ----------------

async def confirm_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

    sender_id = cursor.fetchone()[0]

    confirmer = query.from_user.username

    await query.edit_message_text(
        "✅ Emergency alert confirmed."
    )

    await context.bot.send_message(
        sender_id,
        f"✅ Your emergency contact @{confirmer} confirmed receiving your alert."
    )


# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(CallbackQueryHandler(confirm_alert, pattern="confirm_"))

app.run_polling()
