import asyncio
import re
from telegram import (
    Update,
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

from bot.config import TELEGRAM_BOT_TOKEN
from bot.utils import extract_video_id, check_link_validity
from bot.transcript_service import get_transcript
from bot.summary_service import (
    generate_summary,
    generate_answer,
    generate_deepdive,
    generate_action_points
)

# Store transcript + conversation state per user
user_sessions = {}

# -------------------------------
# HELPERS
# -------------------------------

def get_language_keyboard():
    """Returns a keyboard for initial language selection."""
    langs = [
        ("English", "lang_English"), ("Hindi", "lang_Hindi"),
        ("Malayalam", "lang_Malayalam"), ("Tamil", "lang_Tamil"),
        ("Telugu", "lang_Telugu"), ("Spanish", "lang_Spanish"),
        ("French", "lang_French"), ("German", "lang_German")
    ]
    keyboard = []
    # 2 buttons per row
    for i in range(0, len(langs), 2):
        row = [
            InlineKeyboardButton(langs[i][0], callback_data=langs[i][1]),
            InlineKeyboardButton(langs[i+1][0], callback_data=langs[i+1][1])
        ]
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def get_switch_keyboard(current_lang):
    """Returns a 'Switch to English' button if current language is not English."""
    if current_lang == "English":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Settings / Change Language", callback_data="show_languages")
        ]])
    
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Switch to English", callback_data="lang_English")
    ]])

async def stream_to_message(update: Update, generator, language="English"):
    """
    Polls an async generator and sends the final message with a language toggle button.
    """
    # Defensive check: if it's a callback update, use the existing message
    if update.callback_query:
        msg = await update.callback_query.edit_message_text("Processing...")
    else:
        msg = await update.message.reply_text("Processing...")
        
    full_text = ""
    try:
        async for chunk in generator:
            full_text += chunk
        
        if full_text:
            await msg.edit_text(
                full_text,
                reply_markup=get_switch_keyboard(language)
            )
        else:
            await msg.edit_text("Error: Empty response from model.")
        return True, full_text
    except Exception as e:
        await msg.edit_text(f"Error during generation: {str(e)}")
        return False, str(e)

# -------------------------------
# COMMANDS & CALLBACKS
# -------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send me a YouTube link and I’ll summarize it for you.\n\n"
        "I support multiple languages and contextual Q&A."
    )

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await query.edit_message_text("Please send a YouTube link first.")
        return

    data = query.data
    session = user_sessions[user_id]
    
    # 1. Show language list
    if data == "show_languages":
        await query.edit_message_text(
            "Select your preferred language:",
            reply_markup=get_language_keyboard()
        )
        return

    # 2. Handle specific language selection
    if data.startswith("lang_"):
        new_lang = data.replace("lang_", "")
        session["preferred_language"] = new_lang
        
        # If we have a transcript but haven't summarized yet, do it now
        if session["transcript"]:
            await stream_to_message(update, generate_summary(session["transcript"], language=new_lang), language=new_lang)
        else:
            await query.edit_message_text(f"Language set to {new_lang}. Send a link to start!")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("Please send a YouTube link first.")
        return
    session = user_sessions[user_id]
    lang = session.get("preferred_language", "English")
    await stream_to_message(update, generate_summary(session["transcript"], language=lang), language=lang)

async def deepdive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("Please send a YouTube link first.")
        return
    session = user_sessions[user_id]
    lang = session.get("preferred_language", "English")
    await stream_to_message(update, generate_deepdive(session["transcript"], language=lang), language=lang)

async def actionpoints_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("Please send a YouTube link first.")
        return
    session = user_sessions[user_id]
    lang = session.get("preferred_language", "English")
    await stream_to_message(update, generate_action_points(session["transcript"], language=lang), language=lang)

# -------------------------------
# MESSAGE HANDLER
# -------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    youtube_pattern = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
    user_id = update.effective_user.id

    # NOT a YouTube link -> Q&A or Commands
    if not re.search(youtube_pattern, user_text):
        if user_id not in user_sessions:
            await update.message.reply_text("Please send a YouTube link first.")
            return

        session = user_sessions[user_id]
        
        # Commands
        if user_text.lower() in ["close", "end", "stop"]:
            session["history"] = []
            session["active_question"] = False
            await update.message.reply_text("Question closed. You can ask a new one.")
            return

        if user_text.lower() in ["yes", "continue"]:
            await update.message.reply_text("Please ask your follow-up question.")
            return

        # Q&A FLOW
        if not session["active_question"]:
            session["history"] = []
            session["active_question"] = True

        lang = session.get("preferred_language", "English")
        success, full_answer = await stream_to_message(
            update, 
            generate_answer(session["transcript"], user_text, session["history"], language=lang),
            language=lang
        )

        if success:
            session["history"].append({"role": "user", "content": user_text})
            session["history"].append({"role": "assistant", "content": full_answer})
            session["history"] = session["history"][-2:]
            await update.message.reply_text("Continue? (yes / close)")
        return

    # YouTube link received
    video_id = extract_video_id(user_text)
    if not video_id:
        await update.message.reply_text("Could not extract a valid YouTube video ID.")
        return

    status_msg = await update.message.reply_text("Analyzing link...")
    is_valid = await asyncio.to_thread(check_link_validity, user_text if user_text.startswith("http") else f"https://www.youtube.com/watch?{video_id}")
    
    if not is_valid:
        await status_msg.edit_text("Video link is broken or unavailable.")
        return

    await status_msg.edit_text("Fetching transcript...")
    success, result = await asyncio.to_thread(get_transcript, video_id)

    if not success:
        await status_msg.edit_text(result)
        return

    # Store state but don't summarize yet
    user_sessions[user_id] = {
        "transcript": result,
        "history": [],
        "active_question": False,
        "preferred_language": "English" # Default
    }

    await status_msg.edit_text(
        "Transcript found! What language should I respond in?",
        reply_markup=get_language_keyboard()
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("deepdive", deepdive_command))
    app.add_handler(CommandHandler("actionpoints", actionpoints_command))
    app.add_handler(CallbackQueryHandler(language_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
