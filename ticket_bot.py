import logging
import asyncio
import nest_asyncio
import sqlite3
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import qrcode
import random
import string
from datetime import datetime

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)

# Conversation steps
ASK_NAME, ASK_CATEGORY, ASK_EVENT_OR_MATCH, ASK_TYPE = range(4)

# Ticket types
ticket_types = {
    "VIP": 30,
    "Regular": 15,
    "Online": 8
}

# Events and Matches
events = [
    "🎤 Night Beats Concert - Aug 5",
    "💡 Future of AI Seminar - Aug 15"
]

matches = [
    "🏆 Algeria vs Egypt - Aug 12",
    "⚽ Morocco vs Tunisia - Aug 20"
]

# Payment Address (TRC20 USDT)
BINANCE_USDT_ADDRESS = "TM6Qf5CZCdh9BG6SodA1VRfL395apHQojQ"
DB_PATH = "bookings.db"
ADMIN_CHAT_ID = 6614307731  # Change to your admin Telegram user ID

# Initialize database
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id TEXT,
            name TEXT,
            category TEXT,
            selection TEXT,
            ticket_type TEXT,
            price INTEGER,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_booking_to_db(booking_id, name, category, selection, ticket_type, price):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO bookings (booking_id, name, category, selection, ticket_type, price, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (booking_id, name, category, selection, ticket_type, price, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# Start conversation
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! What is your full name?\nBonjour ! Quel est votre nom complet ?"
    )
    return ASK_NAME

# Ask category (Event or Match)
async def ask_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    keyboard = [["🎫 Event", "🏟️ Match"]]
    await update.message.reply_text(
        "📌 Do you want to book an Event or a Match?\nSouhaitez-vous réserver un événement ou un match ?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_CATEGORY

# Ask specific event or match
async def ask_event_or_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text
    context.user_data["category"] = category

    if "Event" in category:
        keyboard = [[e] for e in events]
        await update.message.reply_text(
            "🎤 Please choose the event:\nVeuillez choisir l'événement :",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
    else:
        keyboard = [[m] for m in matches]
        await update.message.reply_text(
            "⚽ Please choose the match:\nVeuillez choisir le match :",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
    return ASK_EVENT_OR_MATCH

# Ask ticket type
async def ask_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["selection"] = update.message.text
    keyboard = [["VIP"], ["Regular"], ["Online"]]
    await update.message.reply_text(
        "🎟️ Choose the ticket type:\nChoisissez le type de billet :",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_TYPE

# Confirm booking, generate PDF
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_type = update.message.text
    name = context.user_data["name"]
    category = context.user_data["category"]
    selection = context.user_data["selection"]
    price = ticket_types.get(ticket_type, 0)

    booking_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    # Generate QR code
    qr = qrcode.make(BINANCE_USDT_ADDRESS)
    qr_buffer = BytesIO()
    qr.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    qr_img = ImageReader(qr_buffer)

    # Create PDF ticket
    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    c.setFont("Helvetica", 14)

    lines = [
        "✅ Booking Confirmation / Confirmation de réservation",
        "",
        f"Booking ID / ID de réservation: {booking_id}",
        f"Name / Nom: {name}",
        f"Category / Catégorie: {category}",
        f"Details / Détails: {selection}",
        f"Ticket Type / Type de billet: {ticket_type}",
        f"Price / Prix: {price} USDT",
        "",
        "📌 Payment address (Binance USDT TRC20):",
        BINANCE_USDT_ADDRESS,
        "",
        "📸 After payment, send a screenshot to confirm your booking.\n"
        "Après le paiement, envoyez une capture d'écran pour confirmer votre réservation."
    ]

    y = 780
    for line in lines:
        c.drawString(50, y, line)
        y -= 25

    c.drawImage(qr_img, 50, y - 150, width=150, height=150)
    c.save()
    pdf_buffer.seek(0)

    # Save to DB
    save_booking_to_db(booking_id, name, category, selection, ticket_type, price)

    # Notify admin
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            f"📥 New Booking:\n"
            f"ID: {booking_id}\n"
            f"Name: {name}\n"
            f"Category: {category}\n"
            f"Details: {selection}\n"
            f"Type: {ticket_type}\n"
            f"Price: {price} USDT"
        )
    )

    # Send PDF to user
    await update.message.reply_document(
        document=pdf_buffer,
        filename=f"ticket_{booking_id}.pdf",
        caption=f"📄 Your booking is confirmed!\nVotre réservation est confirmée !"
    )

    return ConversationHandler.END

# Cancel handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Booking cancelled.\nRéservation annulée.")
    return ConversationHandler.END

# Booking statistics
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(price) FROM bookings")
    count, total = c.fetchone()
    conn.close()
    await update.message.reply_text(
        f"📊 Total bookings: {count or 0}\n💰 Total amount: {total or 0} USDT\n"
        f"Réservations totales : {count or 0}\nMontant total : {total or 0} USDT"
    )

# Main app
async def main():
    init_db()
    app = ApplicationBuilder().token("8057304466:AAHe_hFHNntom5B3n7V2wrmEUdxDQmqF82U").build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_category)],
            ASK_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_event_or_match)],
            ASK_EVENT_OR_MATCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_type)],
            ASK_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("stats", stats))

    print("✅ Bot is running... Start it via Telegram /start")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
