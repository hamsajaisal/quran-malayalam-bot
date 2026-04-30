import os
import json
import logging
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import uuid

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Load Quran data ──────────────────────────────────────────────────────────
with open("quran.json", "r", encoding="utf-8") as f:
    QURAN_DATA = json.load(f)

BISMILLAH = QURAN_DATA["bismillah"]

# Build fast lookup: { surah_number: { verse_number: text } }
MALAYALAM = {}
SURAH_NAMES = {}
for surah in QURAN_DATA["surahs"]:
    num = surah["number"]
    SURAH_NAMES[num] = surah["name"]
    MALAYALAM[num] = {}
    for verse in surah["verses"]:
        MALAYALAM[num][verse["number"]] = verse["text"]

# ── User preferences (in-memory, resets on restart) ─────────────────────────
# When Arabic is added, preferences will matter more.
# For now everyone gets Malayalam. We store it ready for future use.
USER_PREFS = {}  # { user_id: "malayalam" | "arabic" | "both" }

DEFAULT_PREF = "malayalam"


def get_pref(user_id: int) -> str:
    return USER_PREFS.get(user_id, DEFAULT_PREF)


# ── Verse formatting ─────────────────────────────────────────────────────────
def format_verse(surah_num: int, verse_num: int, pref: str) -> str:
    """Return formatted verse text based on user preference."""
    surah_name = SURAH_NAMES.get(surah_num)
    if not surah_name:
        return "❌ സൂറ കണ്ടെത്തിയില്ല. / Surah not found."

    ml_verses = MALAYALAM.get(surah_num, {})
    ml_text = ml_verses.get(verse_num)
    if not ml_text:
        return "❌ ആയത്ത് കണ്ടെത്തിയില്ല. / Verse not found."

    header = f"📖 *{surah_name}* — {surah_num}:{verse_num}\n"

    # Arabic will be added here later when the file is available
    if pref == "arabic":
        return header + "_Arabic text coming soon._"
    elif pref == "both":
        return header + "_Arabic text coming soon._\n\n" + ml_text
    else:
        # malayalam only (default)
        return header + ml_text


def parse_query(text: str):
    """
    Parse user input like '1:1' or '2:255'.
    Returns (surah_num, verse_num) or (None, None) on failure.
    """
    text = text.strip().replace(" ", "")
    if ":" not in text:
        return None, None
    parts = text.split(":")
    if len(parts) != 2:
        return None, None
    try:
        surah = int(parts[0])
        verse = int(parts[1])
        return surah, verse
    except ValueError:
        return None, None


# ── Command handlers ─────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    text = (
        f"അസ്സലാമു അലൈക്കും {name}! 🌙\n\n"
        "ഖുർആൻ ആയത്തുകൾ മലയാളത്തിൽ വായിക്കാൻ:\n\n"
        "*സൂറ നമ്പർ:ആയത്ത് നമ്പർ* എന്ന് അയക്കൂ\n"
        "ഉദാഹരണം: *1:1* അല്ലെങ്കിൽ *2:255*\n\n"
        "📌 Commands:\n"
        "/start — ആരംഭം\n"
        "/help — സഹായം\n"
        "/settings — ഭാഷ തിരഞ്ഞെടുക്കുക\n\n"
        "Inline ആയി ഉപയോഗിക്കാം:\n"
        "ഏത് chat ലും @YourBotUsername 1:1 എന്ന് ടൈപ്പ് ചെയ്യൂ"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *ഖുർആൻ ബോട്ട് — സഹായം*\n\n"
        "*ആയത്ത് തിരയാൻ:*\n"
        "സൂറ:ആയത്ത് — ഉദാ: `1:1` അല്ലെങ്കിൽ `2:255`\n\n"
        "*ഭാഷ മാറ്റാൻ:*\n"
        "/settings ഉപയോഗിക്കൂ\n\n"
        "*Inline mode:*\n"
        "ഏത് chat ലും @BotUsername എന്നിട്ട് ആയത്ത് നമ്പർ ടൈപ്പ് ചെയ്യൂ\n"
        "ഉദാ: `@BotUsername 2:255`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = get_pref(user_id)

    keyboard = [
        [
            InlineKeyboardButton(
                "🇲🇾 മലയാളം മാത്രം" + (" ✅" if current == "malayalam" else ""),
                callback_data="pref_malayalam"
            )
        ],
        [
            InlineKeyboardButton(
                "🕌 അറബിക് മാത്രം" + (" ✅" if current == "arabic" else ""),
                callback_data="pref_arabic"
            )
        ],
        [
            InlineKeyboardButton(
                "📖 രണ്ടും / Both" + (" ✅" if current == "both" else ""),
                callback_data="pref_both"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚙️ *ഭാഷ തിരഞ്ഞെടുക്കുക / Choose Language:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data  # e.g. "pref_malayalam"

    pref_map = {
        "pref_malayalam": "malayalam",
        "pref_arabic": "arabic",
        "pref_both": "both",
    }
    chosen = pref_map.get(data, "malayalam")
    USER_PREFS[user_id] = chosen

    label_map = {
        "malayalam": "മലയാളം മാത്രം 🇲🇾",
        "arabic": "അറബിക് മാത്രം 🕌",
        "both": "രണ്ടും / Both 📖",
    }
    await query.edit_message_text(
        f"✅ തിരഞ്ഞെടുത്തു: *{label_map[chosen]}*\n\n"
        "ഇനി ആയത്ത് നമ്പർ അയക്കൂ. ഉദാ: `2:255`",
        parse_mode="Markdown"
    )


# ── Message handler ──────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    surah, verse = parse_query(text)
    if surah is None:
        await update.message.reply_text(
            "⚠️ ദയവായി ശരിയായ ഫോർമാറ്റ് ഉപയോഗിക്കൂ.\n"
            "ഉദാഹരണം: *1:1* അല്ലെങ്കിൽ *2:255*",
            parse_mode="Markdown"
        )
        return

    pref = get_pref(user_id)
    response = format_verse(surah, verse, pref)

    if pref == "both":
        # Send as two separate messages when both languages chosen
        lines = response.split("\n\n", 2)
        # For now Arabic is not available, send single message
        await update.message.reply_text(response, parse_mode="Markdown")
    else:
        await update.message.reply_text(response, parse_mode="Markdown")


# ── Inline query handler ─────────────────────────────────────────────────────
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.strip()
    user_id = update.inline_query.from_user.id
    results = []

    if not query_text:
        await update.inline_query.answer([], cache_time=0)
        return

    surah, verse = parse_query(query_text)
    if surah is not None:
        pref = get_pref(user_id)
        response = format_verse(surah, verse, pref)
        surah_name = SURAH_NAMES.get(surah, f"Surah {surah}")

        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=f"{surah_name} — {surah}:{verse}",
                description=MALAYALAM.get(surah, {}).get(verse, "")[:80],
                input_message_content=InputTextMessageContent(
                    response,
                    parse_mode="Markdown"
                ),
            )
        )

    await update.inline_query.answer(results, cache_time=30)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN environment variable is not set!")

    app = Application.builder().token(token).build()

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
