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
        [
            [KeyboardButton("🚨 SEND SOS", request_location=True)]
        ],
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
        "🚨 Hi I'm PANICKA\n\nWhat is your name?"
    )

    context.user_data["step"] = "name"

# ---------------- COMMANDS ----------------

async def sos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Press the SOS button below to send your location.",
        reply_markup=main_keyboard()
    )


async def stealth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["step"] = "fake_q1"
    await update.message.reply_text("Who are you with?")


async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
        "Updating contacts will remove ALL existing contacts.\n\nHow many contacts do you want?",
        reply_markup=keyboard
    )


async def name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["step"] = "edit_name"
    await update.message.reply_text("Enter your new name:")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "PANICKA\n\n"
        "Your personal safety assistant.\n\n"
        "If you feel unsafe, PANICKA can immediately alert your trusted contacts and share your location.\n\n"
        "Features:\n"
        "• One-tap SOS location alert\n"
        "• Stealth texting mode\n"
        "• Activity safety checks\n\n"
        "© CLG"
    )

async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💛 Donate to PANICKA", url="https://paymongo.page/l/panicka")]
    ])

    await update.message.reply_text(
        "💛 Support PANICKA\n\n"
        "If you think this bot can help you feel safer, you can support its development here.\n\n"
        "Your support helps keep PANICKA running and improving for everyone.",
        reply_markup=keyboard
    )

# ---------------- MENU ----------------

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Edit Name", callback_data="edit_name")],
        [InlineKeyboardButton("Update Contacts", callback_data="update_contacts")],
        [InlineKeyboardButton("Stealth Texting", callback_data="fake_texting")],
        [InlineKeyboardButton("Restart Setup", callback_data="restart_setup")]
    ])

    await update.message.reply_text("⚙ PANICKA MENU", reply_markup=keyboard)


# ---------------- TEXT HANDLER ----------------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user_id = update.message.from_user.id
    step = context.user_data.get("step")

    lower = text.lower().strip()
# ---------------- MENU BUTTONS ----------------

    if text == "✏️ EDIT NAME":
        context.user_data["step"] = "edit_name"
        await update.message.reply_text("Enter your new name:")
        return


    if text == "📇 UPDATE CONTACTS":

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
            "Updating contacts will remove ALL existing contacts.\n\nHow many contacts do you want?",
            reply_markup=keyboard
        )
        return


    if text == "🕶 STEALTH TEXTING":
        context.user_data["step"] = "fake_q1"
        await update.message.reply_text("Who are you with?")
        return


    if text == "ℹ️ ABOUT":
        await update.message.reply_text(
            "PANICKA\n\n"
            "Your personal safety assistant.\n\n"
            "If you feel unsafe, PANICKA can immediately alert your trusted contacts and share your location.\n\n"
            "Features:\n"
            "• One-tap SOS location alert\n"
            "• Stealth texting mode\n"
            "• Activity safety checks\n\n"
            "© CLG"
        )
        return
    
    # GLOBAL SAFE COMMAND
    if lower in ["i am safe", "i'm safe", "safe"]:

        contacts = get_contacts(user_id)
        username = update.message.from_user.username

        for c in contacts:
            await context.bot.send_message(
                c,
                f"✅ @{username} confirmed they are SAFE."
            )

        context.user_data["sos_active"] = False
        context.user_data["step"] = None

        await update.message.reply_text(
            "Glad you are safe!",
            reply_markup=main_keyboard()
        )
        return

    # STOP FAKE TEXTING
    if step == "fake_chat" and text.lower().strip() == "iam safe":

        contacts = get_contacts(user_id)

        for c in contacts:
            await context.bot.send_message(c, f"✅ @{update.message.from_user.username} is SAFE.")

        context.user_data.clear()

        await update.message.reply_text("Glad you're safe.", reply_markup=main_keyboard())
        return


    # SAVE CLUES DURING FAKE CHAT
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
                f"That user hasn't started PANICKA.\n\nSend them this:\n{BOT_USERNAME}"
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
            "You can type clues or details anytime.\n"
            "I will check on you every 30 seconds.\n"
            "Please press “Still Here” to confirm that you are responsive.\n\n"
            "If you do not respond, I will notify your emergency contacts immediately.\n\n"
            "Once you are safe, type “Safe” to stop the safety checks."
        )

        asyncio.create_task(fake_chat_loop(context, user_id))


# ---------------- FAKE CHAT LOOP ----------------

async def fake_chat_loop(context, user_id):

    while True:

        await asyncio.sleep(30)

        if context.user_data.get("step") != "fake_chat":
            break

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Still Here", callback_data="still_here")]
        ])

        await context.bot.send_message(
            user_id,
            "Let me know if you're fine right now.",
            reply_markup=keyboard
        )

        context.user_data["ok_pressed"] = False

        await asyncio.sleep(10)

        if not context.user_data.get("ok_pressed"):

            context.user_data["missed_checks"] += 1

            username = context.user_data.get("username")
            contacts = get_contacts(user_id)

            for c in contacts:
                await context.bot.send_message(
                    c,
                    f"@{username} stopped responding during fake texting."
                )
                await context.bot.send_message(
    user_id,
    "I couldn't confirm your activity. I've sent a message to your emergency contacts."
)

            if context.user_data["missed_checks"] >= 5:

                clues = "\n".join(context.user_data.get("clues", []))

                report = (
                    f"FULL FAKE TEXTING REPORT\n\n"
                    f"People: {context.user_data.get('fake_q1')}\n"
                    f"Location: {context.user_data.get('fake_q2')}\n"
                    f"Landmarks: {context.user_data.get('fake_q3')}\n"
                    f"Vehicle: {context.user_data.get('fake_q4')}\n\n"
                    f"Clues:\n{clues}"
                )

                for c in contacts:
                    await context.bot.send_message(c, report)

                break


# ---------------- SOS CHECK LOOP ----------------

async def sos_check_loop(context, user_id):

    while context.user_data.get("sos_active"):

        await asyncio.sleep(30)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Still Here", callback_data="sos_still_here")]
        ])

        await context.bot.send_message(
            user_id,
            "Let me know if you are fine.",
            reply_markup=keyboard
        )

        context.user_data["sos_ok_pressed"] = False

        await asyncio.sleep(10)

        if not context.user_data.get("sos_ok_pressed"):

            context.user_data["sos_missed"] += 1

            username = context.user_data.get("username")
            contacts = get_contacts(user_id)
            lat = context.user_data.get("last_lat")
            lon = context.user_data.get("last_lon")

            for c in contacts:
                await context.bot.send_message(
                    c,
                    f"⚠ @{username} is not responding. Follow-up #{context.user_data['sos_missed']}."
                )
                
                if lat and lon:
                    await context.bot.send_location(c, lat, lon)
                
            await context.bot.send_message(
                user_id,
                "I couldn't confirm your activity. I've sent a message to your emergency contacts."
            )

            if context.user_data["sos_missed"] >= 10:

                for c in contacts:
                    await context.bot.send_message(
                        c,
                        f"🚨 FINAL ALERT\n\n@{username} has stopped responding after 10 safety checks.\nThis was their last known location."
                    )
                    if lat and lon:
                        await context.bot.send_location(c, lat, lon)

                break


# ---------------- PHOTO HANDLER ----------------

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.message.from_user.id
    username = update.message.from_user.username
    contacts = get_contacts(user_id)

    if not contacts:
        return

    photo = update.message.photo[-1].file_id

    for c in contacts:

        await context.bot.send_message(
            c,
            f"📷 Photo sent by @{username}"
        )

        await context.bot.send_photo(c, photo)


# ---------------- BUTTON HANDLER ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data == "sos_still_here":

        context.user_data["sos_ok_pressed"] = True

        await query.edit_message_reply_markup(reply_markup=None)

        await context.bot.send_message(
            user_id,
            "That is great to hear. Let me know once you're safe."
        )
        return

    if data == "still_here":

        context.user_data["ok_pressed"] = True

        await query.edit_message_reply_markup(reply_markup=None)

        await context.bot.send_message(
            user_id,
            "That is great to hear. Let me know once you're safe."
        )
        return



    if data.startswith("confirm_"):

        alert_id = int(data.split("_")[1])

        cursor.execute("UPDATE alerts SET confirmed=1 WHERE alert_id=?", (alert_id,))
        conn.commit()

        cursor.execute("SELECT sender_id FROM alerts WHERE alert_id=?", (alert_id,))
        sender = cursor.fetchone()[0]

        await query.edit_message_text("Alert confirmed. Thank you.")

        await context.bot.send_message(
            sender,
            f"✅ @{query.from_user.username} confirmed they received your emergency alert."
        )
        return

    if data == "edit_name":
        context.user_data["step"] = "edit_name"
        await query.edit_message_text("Enter your new name:")
        return

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

    if data == "fake_texting":
        context.user_data["step"] = "fake_q1"
        await query.edit_message_text("Who are you with?")
        return

    if data == "restart_setup":

        cursor.execute("UPDATE users SET name=NULL, contacts=NULL WHERE user_id=?", (user_id,))
        conn.commit()

        context.user_data["step"] = "name"

        await query.edit_message_text("Setup restarted.\nWhat is your name?")
        return

    if data.startswith("contacts_"):

        count = int(data.split("_")[1])

        context.user_data["contact_count"] = count
        context.user_data["contacts"] = []
        context.user_data["step"] = "add_contact"

        await query.edit_message_text("Send username for contact 1\nExample: @username")
        return


# ---------------- LOCATION HANDLER ----------------

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    lat = update.message.location.latitude
    lon = update.message.location.longitude
    context.user_data["last_lat"] = lat
    context.user_data["last_lon"] = lon

    

    msg = await update.message.reply_text("Sending SOS...")

    await msg.edit_text(
        "SOS sent to your emergency contacts. Please wait for confirmation.\n\n"
        "I will check on you every 30 seconds.\n"
        "Please press “Still Here” to confirm that you are responsive.\n\n"
        "If you do not respond, I will notify your emergency contacts immediately.\n\n"
        "Once you are safe, type “Safe” to stop the safety checks."
    )

    user_id = update.effective_user.id
    context.user_data["username"] = update.effective_user.username
    context.user_data["sos_active"] = True
    context.user_data["sos_missed"] = 0

    asyncio.create_task(sos_check_loop(context, user_id))

    await trigger_alert(update, context, lat, lon)


# ---------------- ALERT ----------------

async def trigger_alert(update, context, lat, lon):

    user = update.effective_user
    user_id = user.id
    username = user.username

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

        await context.bot.send_message(
            contact,
            f"🚨 EMERGENCY ALERT\n\n@{username} may be in danger.\nName: {name}",
            reply_markup=keyboard
        )

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

    cursor.execute("SELECT username FROM users WHERE user_id=?", (sender,))
    sender_username = cursor.fetchone()[0]

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("CONFIRM", callback_data=f"confirm_{alert_id}")]
    ])

    await context.bot.send_message(
        contact,
        f"🚨 EMERGENCY REMINDER\n\nHave you received the emergency alert from @{sender_username}?",
        reply_markup=keyboard
    )

    await context.bot.send_location(contact, lat, lon)


# ---------------- APP ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(CommandHandler("sos", sos_command))
app.add_handler(CommandHandler("stealth", stealth_command))
app.add_handler(CommandHandler("contacts", contacts_command))
app.add_handler(CommandHandler("name", name_command))
app.add_handler(CommandHandler("about", about_command))
app.add_handler(CommandHandler("donate", donate_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()
