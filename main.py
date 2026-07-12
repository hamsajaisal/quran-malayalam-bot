import os
import json
import logging
import uuid
import sqlite3
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
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

# Load Malayalam data
with open("quran.json", "r", encoding="utf-8") as f:
    QURAN_DATA = json.load(f)

MALAYALAM = {}
SURAH_NAMES = {}
for surah in QURAN_DATA["surahs"]:
    num = surah["number"]
    SURAH_NAMES[num] = surah["name"]
    MALAYALAM[num] = {}
    for verse in surah["verses"]:
        MALAYALAM[num][verse["number"]] = verse["text"]

# Load Arabic data
with open("arabic.json", "r", encoding="utf-8") as f:
    raw_arabic = json.load(f)

ARABIC = {}
for surah_key, verses in raw_arabic.items():
    ARABIC[int(surah_key)] = {int(v): t for v, t in verses.items()}

DB_PATH = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            preference TEXT DEFAULT 'both',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: add qari column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN qari TEXT DEFAULT 'Alafasy_128kbps'")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

# Run database initialization
init_db()

def register_user(user_id: int, first_name: str, username: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, first_name, username)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                username = excluded.username
        """, (user_id, first_name, username))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error registering user: {e}")

def get_pref(user_id: int) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT preference FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        logger.error(f"Error getting preference: {e}")
    return "both"

def set_pref(user_id: int, pref: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, preference)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET preference = excluded.preference
        """, (user_id, pref))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error setting preference: {e}")

def get_qari(user_id: int) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT qari FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.error(f"Error getting qari: {e}")
    return "Alafasy_128kbps"

def set_qari(user_id: int, qari: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, qari)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET qari = excluded.qari
        """, (user_id, qari))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error setting qari: {e}")

def get_all_users() -> list[int]:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

def register_interaction(update: Update):
    user = update.effective_user
    if user:
        register_user(user.id, user.first_name, user.username)

# Load Admin IDs from env
ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# Track Qira'at interactive state
USER_STATE = {}


def parse_query(text: str):
    text = text.strip().replace(" ", "")
    if ":" not in text:
        return None, None
    parts = text.split(":")
    if len(parts) != 2:
        return None, None
    try:
        surah_num = int(parts[0])
    except ValueError:
        return None, None

    if surah_num < 1 or surah_num > 114:
        return None, None

    verse_parts = parts[1].split(",")
    verses = []
    
    for part in verse_parts:
        if not part:
            continue
        if "-" in part:
            subparts = part.split("-")
            if len(subparts) != 2:
                return None, None
            try:
                start = int(subparts[0])
                end = int(subparts[1])
                if start <= 0 or end <= 0:
                    return None, None
                if start > end:
                    start, end = end, start
                verses.extend(range(start, end + 1))
            except ValueError:
                return None, None
        else:
            try:
                val = int(part)
                if val <= 0:
                    return None, None
                verses.append(val)
            except ValueError:
                return None, None

    if not verses:
        return None, None

    # Limit verses to a maximum of 30 to avoid message size limits
    MAX_VERSES_LIMIT = 30
    if len(verses) > MAX_VERSES_LIMIT:
        verses = verses[:MAX_VERSES_LIMIT]

    return surah_num, verses


def format_verses(surah_num: int, verse_nums: list[int], pref: str) -> list[str]:
    surah_name = SURAH_NAMES.get(surah_num)
    if not surah_name:
        return ["സൂറ കണ്ടെത്തിയില്ല. Surah not found."]

    messages = []
    current_message = f"*സൂറത്ത്: {surah_num}. {surah_name}*\n\n"
    
    for verse_num in verse_nums:
        ml_text = MALAYALAM.get(surah_num, {}).get(verse_num)
        ar_text = ARABIC.get(surah_num, {}).get(verse_num)

        if not ml_text and not ar_text:
            verse_str = f"*വചനം: {verse_num}*\nആയത്ത് കണ്ടെത്തിയില്ല. Verse not found.\n\n"
        else:
            verse_str = f"*വചനം: {verse_num}*\n"
            if pref == "arabic" and ar_text:
                verse_str += ar_text + "\n\n"
            elif pref == "malayalam" and ml_text:
                verse_str += ml_text + "\n\n"
            else:
                # both
                parts = []
                if ar_text:
                    parts.append(ar_text)
                if ml_text:
                    parts.append(ml_text)
                verse_str += "\n\n".join(parts) + "\n\n"
        
        # Split message if it exceeds 4000 characters
        if len(current_message) + len(verse_str) > 4000:
            messages.append(current_message.strip())
            current_message = f"*സൂറത്ത്: {surah_num}. {surah_name} (തുടർച്ച...)*\n\n" + verse_str
        else:
            current_message += verse_str
            
    messages.append(current_message.strip())
    return messages


def get_qiraat_page(surah_num: int, start_verse: int, pref: str) -> tuple[str, InlineKeyboardMarkup]:
    surah_name = SURAH_NAMES.get(surah_num, f"Surah {surah_num}")
    total_verses = len(MALAYALAM.get(surah_num, {}))
    if total_verses == 0:
        total_verses = len(ARABIC.get(surah_num, {}))
        
    end_verse = min(start_verse + 4, total_verses)
    verse_nums = list(range(start_verse, end_verse + 1))
    
    header = f"*📖 ഖിറാഅത്ത് മോഡ് (Qira'at Mode)*\n*സൂറത്ത്: {surah_num}. {surah_name}* (ആയത്തുകൾ: {start_verse} - {end_verse} / {total_verses})\n\n"
    
    parts = []
    for v in verse_nums:
        ml_text = MALAYALAM.get(surah_num, {}).get(v)
        ar_text = ARABIC.get(surah_num, {}).get(v)
        
        verse_str = f"*ആയത്ത്: {v}*\n"
        if pref == "arabic" and ar_text:
            verse_str += ar_text
        elif pref == "malayalam" and ml_text:
            verse_str += ml_text
        else:
            v_parts = []
            if ar_text:
                v_parts.append(ar_text)
            if ml_text:
                v_parts.append(ml_text)
            verse_str += "\n\n".join(v_parts)
        parts.append(verse_str)
        
    body = "\n\n---\n\n".join(parts)
    text = header + body
    
    if len(text) > 4000:
        text = text[:3900] + "\n\n...(Truncated due to length)"
        
    # Audio buttons row: 🔊 1 | 🔊 2 | ...
    audio_buttons = []
    for v in verse_nums:
        audio_buttons.append(InlineKeyboardButton(f"🔊 {v}", callback_data=f"qiraat_play_{surah_num}_{v}"))

    # Navigation buttons
    nav_buttons = []
    if start_verse > 1:
        prev_start = max(1, start_verse - 5)
        nav_buttons.append(InlineKeyboardButton("⬅️ മുൻപത്തെ (Prev)", callback_data=f"qiraat_page_{surah_num}_{prev_start}"))
    if end_verse < total_verses:
        next_start = end_verse + 1
        nav_buttons.append(InlineKeyboardButton("അടുത്തത് (Next) ➡️", callback_data=f"qiraat_page_{surah_num}_{next_start}"))
        
    keyboard = []
    if audio_buttons:
        keyboard.append(audio_buttons)
    if nav_buttons:
        keyboard.append(nav_buttons)

    return text, InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"അസ്സലാമു അലൈക്കും {name}!\n\n"
        "ഖുർആൻ ആയത്തുകൾ വായിക്കാൻ "
        "സൂറ നമ്പർ:ആയത്ത് നമ്പർ എന്ന് അയക്കൂ\n\n"
        "ഉദാഹരണം: 1:1 അല്ലെങ്കിൽ 2:255\n\n"
        "/help - സഹായം\n"
        "/settings - ഭാഷ തിരഞ്ഞെടുക്കുക\n"
        "/qiraat - ഖിറാഅത്ത് മോഡ് (തുടർച്ചയായ വായന)",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    await update.message.reply_text(
        "ആയത്ത് തിരയാൻ സൂറ:ആയത്ത് അയക്കൂ\n"
        "ഉദാ: 1:1 അല്ലെങ്കിൽ 2:255\n\n"
        "തുടർച്ചയായ വായനയ്ക്ക്:\n"
        "2:22-26 അല്ലെങ്കിൽ 23:24,25,26\n\n"
        "ഖിറാഅത്ത് മോഡ്: /qiraat\n\n"
        "Inline: @BotUsername 2:255"
    )


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    keyboard = [
        [InlineKeyboardButton("🌐 ഭാഷ തിരഞ്ഞെടുക്കുക (Choose Language)", callback_data="settings_lang")],
        [InlineKeyboardButton("🎙️ ഖാരിയെ തിരഞ്ഞെടുക്കുക (Choose Reciter)", callback_data="settings_qari")],
    ]
    await update.message.reply_text(
        "ക്രമീകരണങ്ങൾ തിരഞ്ഞെടുക്കുക / Settings:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def settings_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🌐 ഭാഷ തിരഞ്ഞെടുക്കുക (Choose Language)", callback_data="settings_lang")],
        [InlineKeyboardButton("🎙️ ഖാരിയെ തിരഞ്ഞെടുക്കുക (Choose Reciter)", callback_data="settings_qari")],
    ]
    await query.edit_message_text(
        "ക്രമീകരണങ്ങൾ തിരഞ്ഞെടുക്കുക / Settings:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def settings_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
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
        [InlineKeyboardButton("⬅️ ബാക്ക് (Back)", callback_data="settings_main")],
    ]
    await query.edit_message_text(
        "ഭാഷ തിരഞ്ഞെടുക്കുക / Choose Language:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
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
    chosen = pref_map.get(query.data, "both")
    set_pref(query.from_user.id, chosen)
    keyboard = [[InlineKeyboardButton("⬅️ ബാക്ക് (Back)", callback_data="settings_lang")]]
    await query.edit_message_text(
        f"തിരഞ്ഞെടുത്തു: {label_map[chosen]}\n\n"
        "ഇനി ആയത്ത് നമ്പർ അയക്കൂ. ഉദാ: 2:255",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def settings_qari_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    current = get_qari(user_id)
    
    qari_options = [
        ("Mishary Rashid Alafasy", "Alafasy_128kbps"),
        ("Abdurrahmaan As-Sudais", "Abdurrahmaan_As-Sudais_192kbps"),
        ("Saad Al-Ghamdi", "Ghamadi_40kbps"),
        ("Mahmoud Khalil Al-Husary", "Husary_128kbps"),
    ]
    
    keyboard = []
    for name, code in qari_options:
        tick = " ✅" if current == code else ""
        keyboard.append([InlineKeyboardButton(name + tick, callback_data=f"qari_{code}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ ബാക്ക് (Back)", callback_data="settings_main")])
    await query.edit_message_text(
        "ഖാരിയെ തിരഞ്ഞെടുക്കുക / Choose Reciter:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def qari_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    query = update.callback_query
    await query.answer()
    code = query.data.replace("qari_", "")
    set_qari(query.from_user.id, code)
    
    qari_names = {
        "Alafasy_128kbps": "Mishary Rashid Alafasy",
        "Abdurrahmaan_As-Sudais_192kbps": "Abdurrahmaan As-Sudais",
        "Ghamadi_40kbps": "Saad Al-Ghamdi",
        "Husary_128kbps": "Mahmoud Khalil Al-Husary",
    }
    
    name = qari_names.get(code, "Mishary Rashid Alafasy")
    keyboard = [[InlineKeyboardButton("⬅️ ബാക്ക് (Back)", callback_data="settings_qari")]]
    await query.edit_message_text(
        f"ഖാരിയെ തിരഞ്ഞെടുത്തു: {name}\n\n"
        "ഇനി ഖിറാഅത്ത് മോഡിൽ നിങ്ങൾക്ക് ഈ ഖാരിയുടെ ശബ്ദം കേൾക്കാം.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Intercept manual typed "/qira..." command
    if text.startswith("/qira"):
        await qiraat_command(update, context)
        return

    # Check if user is in a state (e.g. awaiting_surah)
    state_data = USER_STATE.get(user_id)
    if state_data and state_data.get("state") == "awaiting_surah":
        try:
            surah_num = int(text)
            if 1 <= surah_num <= 114:
                # Clear state
                USER_STATE.pop(user_id, None)
                pref = get_pref(user_id)
                text_content, reply_markup = get_qiraat_page(surah_num, 1, pref)
                await update.message.reply_text(
                    text=text_content,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
                return
            else:
                await update.message.reply_text(
                    "ദയവായി 1 നും 114 നും ഇടയിലുള്ള ഒരു നമ്പർ നൽകുക.\n"
                    "Please enter a number between 1 and 114."
                )
                return
        except ValueError:
            # If it contains ":", maybe they want to search instead.
            if ":" in text:
                USER_STATE.pop(user_id, None)
                # Fall through to parse query below
            else:
                await update.message.reply_text(
                    "ദയവായി ശരിയായ സൂറ നമ്പർ നൽകുക (1 - 114).\n"
                    "Please enter a valid Surah number (1 - 114)."
                )
                return

    surah, verses = parse_query(text)
    if surah is None:
        await update.message.reply_text(
            "ദയവായി ശരിയായ ഫോർമാറ്റ് ഉപയോഗിക്കൂ.\n"
            "ഉദാഹരണം: 1:1 അല്ലെങ്കിൽ 2:255\n"
            "തുടർച്ചയായ വായനയ്ക്ക്: 2:22-26 അല്ലെങ്കിൽ 23:24,25,26"
        )
        return
        
    pref = get_pref(user_id)
    formatted_messages = format_verses(surah, verses, pref)
    for msg in formatted_messages:
        await update.message.reply_text(msg, parse_mode="Markdown")


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    query_text = update.inline_query.query.strip()
    user_id = update.inline_query.from_user.id
    results = []
    if query_text:
        surah, verses = parse_query(query_text)
        if surah is not None:
            pref = get_pref(user_id)
            formatted_list = format_verses(surah, verses, pref)
            response = "\n\n".join(formatted_list)
            if len(response) > 4000:
                response = response[:3900] + "\n\n...(Truncated due to Telegram limit)"
            
            surah_name = SURAH_NAMES.get(surah, f"Surah {surah}")
            
            first_verse = verses[0]
            ml_text = MALAYALAM.get(surah, {}).get(first_verse, "")
            
            if len(verses) == 1:
                verses_title = f"{verses[0]}"
            else:
                is_contiguous = True
                for i in range(len(verses) - 1):
                    if verses[i+1] != verses[i] + 1:
                        is_contiguous = False
                        break
                if is_contiguous:
                    verses_title = f"{verses[0]}-{verses[-1]}"
                else:
                    verses_title = ",".join(map(str, verses))
            
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title=f"{surah_name} {surah}:{verses_title}",
                    description=ml_text[:80] if ml_text else "വചന പരിഭാഷ കാണുക",
                    input_message_content=InputTextMessageContent(
                        response, parse_mode="Markdown"
                    ),
                )
            )
    await update.inline_query.answer(results, cache_time=30)


async def qiraat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    user_id = update.effective_user.id
    USER_STATE[user_id] = {"state": "awaiting_surah"}
    await update.message.reply_text(
        "ദയവായി സൂറയുടെ നമ്പർ നൽകുക (1 - 114):\n"
        "Please enter the Surah number (1 - 114):"
    )


async def qiraat_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    if len(parts) != 4:
        return
    
    try:
        surah_num = int(parts[2])
        start_verse = int(parts[3])
    except ValueError:
        return
    
    user_id = query.from_user.id
    pref = get_pref(user_id)
    text_content, reply_markup = get_qiraat_page(surah_num, start_verse, pref)
    
    try:
        await query.edit_message_text(
            text=text_content,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")


async def qiraat_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("ഓഡിയോ ലോഡ് ചെയ്യുന്നു... Loading audio...")
    
    parts = query.data.split("_")
    if len(parts) != 4:
        return
    
    try:
        surah_num = int(parts[2])
        verse_num = int(parts[3])
    except ValueError:
        return
        
    user_id = query.from_user.id
    qari = get_qari(user_id)
    
    # Construct everyayah URL (3-digit zero padded format)
    audio_url = f"https://www.everyayah.com/data/{qari}/{surah_num:03d}{verse_num:03d}.mp3"
    
    surah_name = SURAH_NAMES.get(surah_num, f"Surah {surah_num}")
    
    qari_names = {
        "Alafasy_128kbps": "Mishary Rashid Alafasy",
        "Abdurrahmaan_As-Sudais_192kbps": "Abdurrahmaan As-Sudais",
        "Ghamadi_40kbps": "Saad Al-Ghamdi",
        "Husary_128kbps": "Mahmoud Khalil Al-Husary",
    }
    qari_name = qari_names.get(qari, "Mishary Rashid Alafasy")
    
    caption = f"📖 സൂറത്ത് {surah_name} ({surah_num}:{verse_num})\n🎙️ {qari_name}"
    
    try:
        await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=audio_url,
            caption=caption,
            title=f"Verse {surah_num}:{verse_num}",
            performer=surah_name
        )
    except Exception as e:
        logger.error(f"Error sending audio: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="ക്ഷമിക്കണം, ഈ ആയത്തിന്റെ ഓഡിയോ ലഭ്യമല്ല. Audio not available."
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("ഉങ്ങൾക്ക് ഈ കമാൻഡ് ഉപയോഗിക്കാൻ അനുമതിയില്ല. Access denied.")
        return

    users = get_all_users()
    await update.message.reply_text(
        f"📊 *Bot Statistics*\n\n"
        f"Total Registered Users: {len(users)}",
        parse_mode="Markdown"
    )


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("ഉങ്ങൾക്ക് ഈ കമാൻഡ് ഉപയോഗിക്കാൻ അനുമതിയില്ല. Access denied.")
        return

    if not os.path.exists(DB_PATH):
        await update.message.reply_text("ഡാറ്റാബേസ് ഫയൽ കണ്ടെത്തിയില്ല. Database file not found.")
        return

    try:
        with open(DB_PATH, "rb") as db_file:
            await update.message.reply_document(
                document=db_file,
                filename=DB_PATH,
                caption="Here is the backup of the bot database."
            )
    except Exception as e:
        logger.error(f"Error sending backup: {e}")
        await update.message.reply_text(f"Error backup: {str(e)}")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_interaction(update)
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("ഉങ്ങൾക്ക് ഈ കമാൻഡ് ഉപയോഗിക്കാൻ അനുമതിയില്ല. Access denied.")
        return

    text_to_send = ""
    if context.args:
        text_to_send = " ".join(context.args)
    
    if not text_to_send:
        await update.message.reply_text(
            "ദയവായി ബ്രോഡ്കാസ്റ്റ് ചെയ്യേണ്ട സന്ദേശം നൽകുക.\n"
            "Format: `/broadcast Your message here`",
            parse_mode="Markdown"
        )
        return

    users = get_all_users()
    if not users:
        await update.message.reply_text("അംഗങ്ങൾ ആരും തന്നെ ഇല്ല. No users registered.")
        return

    status_msg = await update.message.reply_text(f"Starting broadcast to {len(users)} users...")

    success = 0
    failed = 0
    for u_id in users:
        try:
            await context.bot.send_message(chat_id=u_id, text=text_to_send)
            success += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to {u_id}: {e}")
            failed += 1

    await status_msg.edit_text(
        f"📢 *Broadcast Completed*\n\n"
        f"Total Target Users: {len(users)}\n"
        f"Successfully Sent: {success}\n"
        f"Failed / Blocked: {failed}",
        parse_mode="Markdown"
    )


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN environment variable is not set!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("qiraat", qiraat_command))
    app.add_handler(CommandHandler("qira_at", qiraat_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^pref_"))
    app.add_handler(CallbackQueryHandler(settings_main_callback, pattern="^settings_main$"))
    app.add_handler(CallbackQueryHandler(settings_lang_callback, pattern="^settings_lang$"))
    app.add_handler(CallbackQueryHandler(settings_qari_callback, pattern="^settings_qari$"))
    app.add_handler(CallbackQueryHandler(qari_callback, pattern="^qari_"))
    app.add_handler(CallbackQueryHandler(qiraat_page_callback, pattern="^qiraat_page_"))
    app.add_handler(CallbackQueryHandler(qiraat_play_callback, pattern="^qiraat_play_"))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
