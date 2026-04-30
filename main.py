import os
import json
import logging
import uuid
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

with open("quran.json", "r", encoding="utf-8") as f:
    QURAN_DATA = json.load(f)

BISMILLAH = QURAN_DATA["bismillah"]
MALAYALAM = {}
SURAH_NAMES = {}
for surah in QURAN_DATA["surahs"]:
    num = surah["number"]
    SURAH_NAMES[num] = surah["name"]
    MALAYALAM[num] = {}
    for verse in surah["verses"]:
        MALAYALAM[num][verse["number"]] = verse["text"]

USER_PREFS = {}


def get_pref(user_id: int) -> str:
    return USER_PREFS.get(user_id, "malayalam")


def parse_query(text: str):
    text = text.strip().replace(" ", "")
    if ":" not in text:
        return None, None
    parts = text.split(":")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def format_verse(surah_num: int, verse_num: int) -> str:
    surah_name = SURAH_NAMES.get(surah_num)
    if not surah_name:
        return "❌ സൂറ കണ്ടെത്തിയില്ല. Surah not found."
    ml_text = MALAYALAM.get(surah_num, {}).get(verse_num)
    if not ml_text:
        return "❌ ആയത്ത് കണ്ടെത്തിയില്ല. Verse not found."
    return f"📖 *{surah_name}* — {surah_num}:{verse_num}\n\n{ml_text}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"അസ്സലാമു അലൈക്കും {name}! 🌙\n\n"
        "ഖുർആൻ ആയത്തുകൾ മലയാളത്തിൽ വായിക്കാൻ:\n\n"
        "സൂറ നമ്പർ:ആയത്ത് നമ്പർ എന്ന് അയക്കൂ\n"
        "ഉദാഹരണം: 1:1 അല്ലെങ്കിൽ 2:255\n\n"
        "Commands:\n"
        "/start — ആരംഭം\n"
        "/help — സഹായം\n"
        "/settings — ഭാഷ തിരഞ്ഞെടുക്കുക",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *ഖുർആൻ ബോട്ട് — സഹായം*\n\n"
        "ആയത്ത് തിരയാൻ:\n"
        "സൂറ:ആയത്ത് — ഉദാ: 1:1 അല്ലെങ്കിൽ 2:255\n\n"
        "Inline mode:\n"
        "@BotUsername എന്നിട്ട് ആയത്ത് നമ്പർ ടൈപ്പ് ചെയ്യൂ\n"
        "ഉദാ: @BotUsername 2:255",
        parse_mode="Markdown",
    )


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = get_pref(user_id)
    keyboard = [
        [InlineKeyboardButton(
            "മലയാളം മാത്രം" + (" ✅" if current == "malayalam" else ""),
            callback_data="pref_malayalam",
        )],
        [InlineKeyboardButton(
            "അറബിക് മാത്രം" + (" ✅" if current == "arabic" else ""),
            callback_data="pref_arabic",
        )],
        [InlineKeyboardButton(
            "രണ്ടും / Both" + (" ✅" if current == "both" else ""),
            callback_data="pref_both",
        )],
    ]
    await update.message.reply_text(
        "ഭാഷ തിരഞ്ഞെടുക്കുക / Choose Language:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pref_map = {
        "pref_malayalam": "malayalam",
        "pref_arabic": "arabic",
        "pref_both": "both",
    }
    label_map = {
        "malayalam": "മലയാളം മാത്രം",
        "arabic": "അറബിക് മാത്രം",
        "both": "രണ്ടും / Both",
    }
    chosen = pref_map.get(query.data, "malayalam")
    USER_PREFS[query.from_user.id] = chosen
    await query.edit_message_text(
        f"തിരഞ്ഞെടുത്തു: {label_map[chosen]}\n\n"
        "ഇനി ആയത്ത് നമ്പർ അയക്കൂ. ഉദാ: 2:255"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    surah, verse = parse_query(update.message.text)
    if surah is None:
        await update.message.reply_text(
            "ദയവായി ശരിയായ ഫോർമാറ്റ് ഉപയോഗിക്കൂ.\n"
            "ഉദാഹരണം: 1:1 അല്ലെങ്കിൽ 2:255"
        )
        return
    await update.message.reply_text(
        format_verse(surah, verse), parse_mode="Markdown"
    )


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.strip()
    results = []
    if query_text:
        surah, verse = parse_query(query_text)
        if surah is not None:
            response = format_verse(surah, verse)
            surah_name = SURAH_NAMES.get(surah, f"Surah {surah}")
            ml_text = MALAYALAM.get(surah, {}).get(verse, "")
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title=f"{surah_name} — {surah}:{verse}",
                    description=ml_text[:80],
                    input_message_content=InputTextMessageContent(
                        response, parse_mode="Markdown"
                    ),
                )
            )
    await update.inline_query.answer(results, cache_time=30)


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN environment variable is not set!")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^pref_"))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
