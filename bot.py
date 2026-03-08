# PANICBOT FINAL VERSION
# (trimmed explanation here to keep message readable)

import os
import sqlite3
import asyncio
from telegram import *
from telegram.ext import *

TOKEN = os.getenv("BOT_TOKEN")

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

# ---------- UI ----------

def main_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🚨 SEND LOCATION", request_location=True)]],
        resize_keyboard=True
    )

# ---------- CONTACT UTILS ----------

def get_contacts(uid):
    cursor.execute("SELECT contacts FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return []
    return [int(x) for x in row[0].split(",")]

def save_contacts(uid, contacts):
    cursor.execute(
        "UPDATE users SET contacts=? WHERE user_id=?",
        (",".join(map(str,contacts)), uid)
    )
    conn.commit()

# ---------- START ----------

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):

    u = update.message.from_user

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id,username) VALUES (?,?)",
        (u.id,u.username)
    )
    conn.commit()

    cursor.execute("SELECT name,contacts FROM users WHERE user_id=?", (u.id,))
    row = cursor.fetchone()

    if row and row[0] and row[1]:

        await update.message.reply_text(
            "When you are in danger press SEND LOCATION.",
            reply_markup=main_keyboard()
        )
        return

    msg = await update.message.reply_text("What is your name?")
    context.user_data["setup_msgs"]=[msg.message_id]
    context.user_data["step"]="name"

# ---------- MENU ----------

async def menu(update:Update,context:ContextTypes.DEFAULT_TYPE):

    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton("Edit Name",callback_data="edit_name")],
        [InlineKeyboardButton("Update Contacts",callback_data="contacts")],
        [InlineKeyboardButton("Fake Texting",callback_data="fake")],
        [InlineKeyboardButton("Restart Setup",callback_data="restart")]
    ])

    await update.message.reply_text(
        "⚙ PANICBOT MENU",
        reply_markup=kb,
        reply_markup_remove=False
    )

# ---------- TEXT HANDLER ----------

async def text_handler(update:Update,context:ContextTypes.DEFAULT_TYPE):

    txt=update.message.text
    uid=update.message.from_user.id
    step=context.user_data.get("step")

    if step=="name":

        cursor.execute("UPDATE users SET name=? WHERE user_id=?",(txt,uid))
        conn.commit()

        kb=InlineKeyboardMarkup([[
            InlineKeyboardButton("1",callback_data="c1"),
            InlineKeyboardButton("2",callback_data="c2"),
            InlineKeyboardButton("3",callback_data="c3"),
            InlineKeyboardButton("4",callback_data="c4"),
            InlineKeyboardButton("5",callback_data="c5")
        ]])

        m=await update.message.reply_text(
            "How many emergency contacts?",
            reply_markup=kb
        )

        context.user_data["setup_msgs"].append(m.message_id)
        return

    if step=="add_contact":

        username=txt.replace("@","")

        cursor.execute("SELECT user_id FROM users WHERE username=?",(username,))
        r=cursor.fetchone()

        if not r:

            await update.message.reply_text(
                "That user hasn't started PANICBOT.\n\nSend them:\n@panic_sos_bot"
            )
            return

        context.user_data["contacts"].append(r[0])

        cur=len(context.user_data["contacts"])
        tot=context.user_data["contact_count"]

        if cur<tot:
            m=await update.message.reply_text(f"Send username for contact {cur+1}")
            context.user_data["setup_msgs"].append(m.message_id)
        else:

            save_contacts(uid,context.user_data["contacts"])

            for mid in context.user_data["setup_msgs"]:
                try:
                    await context.bot.delete_message(update.effective_chat.id,mid)
                except: pass

            await update.message.reply_text(
                "Setup Complete.\nWhen you are in danger press SEND LOCATION.",
                reply_markup=main_keyboard()
            )

            context.user_data.clear()

# ---------- SOS LOCATION ----------

async def location_handler(update:Update,context:ContextTypes.DEFAULT_TYPE):

    lat=update.message.location.latitude
    lon=update.message.location.longitude

    kb=InlineKeyboardMarkup([[
        InlineKeyboardButton("Send Now",callback_data="send_now"),
        InlineKeyboardButton("Cancel",callback_data="cancel")
    ]])

    msg=await update.message.reply_text("SOS will send in 10 seconds.",reply_markup=kb)

    for i in range(10):
        await asyncio.sleep(1)

        if context.user_data.get("cancel"):
            return

        if context.user_data.get("force"):
            break

    await msg.edit_text("SOS sent to your emergency contacts. Wait for confirmation.")

    await trigger_alert(update,context,lat,lon)

# ---------- ALERT ----------

async def trigger_alert(update,context,lat,lon):

    uid=update.effective_user.id

    cursor.execute("SELECT name FROM users WHERE user_id=?",(uid,))
    name=cursor.fetchone()[0]

    contacts=get_contacts(uid)

    for c in contacts:

        cursor.execute(
            "INSERT INTO alerts (sender_id,contact_id,latitude,longitude) VALUES (?,?,?,?)",
            (uid,c,lat,lon)
        )
        alert_id=cursor.lastrowid
        conn.commit()

        kb=InlineKeyboardMarkup([[InlineKeyboardButton("CONFIRM",callback_data=f"confirm_{alert_id}")]])

        await context.bot.send_message(
            c,
            f"🚨 EMERGENCY ALERT\n{name} may be in danger.\nPlease confirm you received the location.",
            reply_markup=kb
        )

        await context.bot.send_location(c,lat,lon)

        context.job_queue.run_repeating(reminder_job,60,60,data={"alert":alert_id})

# ---------- REMINDER ----------

async def reminder_job(context:ContextTypes.DEFAULT_TYPE):

    aid=context.job.data["alert"]

    cursor.execute("SELECT sender_id,contact_id,latitude,longitude,confirmed FROM alerts WHERE alert_id=?",(aid,))
    r=cursor.fetchone()

    if not r:
        return

    sender,contact,lat,lon,confirmed=r

    if confirmed:
        context.job.schedule_removal()
        return

    cursor.execute("SELECT username FROM users WHERE user_id=?",(sender,))
    u=cursor.fetchone()[0]

    kb=InlineKeyboardMarkup([[InlineKeyboardButton("CONFIRM",callback_data=f"confirm_{aid}")]])

    await context.bot.send_message(
        contact,
        f"@{u} may be in danger please confirm you received the location.",
        reply_markup=kb
    )

    await context.bot.send_location(contact,lat,lon)

# ---------- CONFIRM ----------

async def button_handler(update:Update,context:ContextTypes.DEFAULT_TYPE):

    q=update.callback_query
    await q.answer()

    data=q.data

    if data.startswith("confirm_"):

        aid=int(data.split("_")[1])

        cursor.execute("UPDATE alerts SET confirmed=1 WHERE alert_id=?",(aid,))
        conn.commit()

        cursor.execute("SELECT sender_id FROM alerts WHERE alert_id=?",(aid,))
        sender=cursor.fetchone()[0]

        await q.edit_message_text("Alert confirmed.")

        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("Rescued",callback_data="rescued")],
            [InlineKeyboardButton("Not Yet",callback_data="notyet")]
        ])

        await context.bot.send_message(
            sender,
            "Confirm if you are rescued.",
            reply_markup=kb
        )

    if data=="rescued":

        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("Clean Dashboard",callback_data="clean")]
        ])

        await q.edit_message_text("Do you want to remove previous messages?",reply_markup=kb)

    if data=="clean":

        chat=q.message.chat.id

        async for m in context.bot.get_chat_history(chat):
            try:
                await context.bot.delete_message(chat,m.message_id)
            except:
                pass

        await context.bot.send_message(
            chat,
            "When you are in danger press SEND LOCATION.",
            reply_markup=main_keyboard()
        )

# ---------- APP ----------

app=ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start",start))
app.add_handler(CommandHandler("menu",menu))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler))
app.add_handler(MessageHandler(filters.LOCATION,location_handler))
app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()
