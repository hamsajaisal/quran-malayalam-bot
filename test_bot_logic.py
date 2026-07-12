import os
import unittest
import sqlite3
import shutil

# Set dummy environment variable before importing main
os.environ["BOT_TOKEN"] = "dummy_token"
os.environ["ADMIN_IDS"] = "123456,789012"

import main

class TestQuranBotLogic(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Backup existing database if it exists
        cls.db_backup = "bot_data.db.bak"
        if os.path.exists(main.DB_PATH):
            shutil.copy(main.DB_PATH, cls.db_backup)
            os.remove(main.DB_PATH)
        
        # Initialize test DB
        main.init_db()

    @classmethod
    def tearDownClass(cls):
        # Restore backup database if it existed
        if os.path.exists(main.DB_PATH):
            os.remove(main.DB_PATH)
        if os.path.exists(cls.db_backup):
            shutil.copy(cls.db_backup, main.DB_PATH)
            os.remove(cls.db_backup)

    def setUp(self):
        # Clear table before each test
        conn = sqlite3.connect(main.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users")
        conn.commit()
        conn.close()

    def test_database_helpers(self):
        # Register a user
        main.register_user(12345, "Test User", "test_uname")
        
        # Verify registered
        users = main.get_all_users()
        self.assertEqual(users, [12345])
        
        # Get default preference
        pref = main.get_pref(12345)
        self.assertEqual(pref, "both")
        
        # Set preference to arabic
        main.set_pref(12345, "arabic")
        pref = main.get_pref(12345)
        self.assertEqual(pref, "arabic")

        # Get default qari
        qari = main.get_qari(12345)
        self.assertEqual(qari, "Alafasy_128kbps")

        # Set qari to Sudais
        main.set_qari(12345, "Abdurrahmaan_As-Sudais_192kbps")
        qari = main.get_qari(12345)
        self.assertEqual(qari, "Abdurrahmaan_As-Sudais_192kbps")

        # Update user info (UPSERT check)
        main.register_user(12345, "Test User Updated", "test_uname_new")
        conn = sqlite3.connect(main.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT first_name, username FROM users WHERE user_id = ?", (12345,))
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row, ("Test User Updated", "test_uname_new"))

    def test_parse_query(self):
        # Single verse
        surah, verses = main.parse_query("2:255")
        self.assertEqual(surah, 2)
        self.assertEqual(verses, [255])

        # Dash range
        surah, verses = main.parse_query("2:22-26")
        self.assertEqual(surah, 2)
        self.assertEqual(verses, [22, 23, 24, 25, 26])

        # Comma list
        surah, verses = main.parse_query("23:24,25,26")
        self.assertEqual(surah, 23)
        self.assertEqual(verses, [24, 25, 26])

        # Non-contiguous list
        surah, verses = main.parse_query("23:26,35,43")
        self.assertEqual(surah, 23)
        self.assertEqual(verses, [26, 35, 43])

        # Mixed format
        surah, verses = main.parse_query("2:22-24,26,28-29")
        self.assertEqual(surah, 2)
        self.assertEqual(verses, [22, 23, 24, 26, 28, 29])

        # Swap start/end if start > end
        surah, verses = main.parse_query("2:26-24")
        self.assertEqual(surah, 2)
        self.assertEqual(verses, [24, 25, 26])

        # Limit enforcement (limit = 30)
        surah, verses = main.parse_query("2:1-40")
        self.assertEqual(surah, 2)
        self.assertEqual(len(verses), 30)
        self.assertEqual(verses[-1], 30)

        # Invalid formats
        self.assertTupleEqual(main.parse_query("invalid_query"), (None, None))
        self.assertTupleEqual(main.parse_query("2"), (None, None))
        self.assertTupleEqual(main.parse_query("2:"), (None, None))
        self.assertTupleEqual(main.parse_query(":255"), (None, None))
        self.assertTupleEqual(main.parse_query("115:1"), (None, None)) # Surah > 114
        self.assertTupleEqual(main.parse_query("0:1"), (None, None)) # Surah < 1
        self.assertTupleEqual(main.parse_query("2:abc"), (None, None))

    def test_format_verses(self):
        # Format single verse (both)
        messages = main.format_verses(1, [1], "both")
        self.assertEqual(len(messages), 1)
        self.assertIn("Fatihah", messages[0])
        self.assertIn("ബിസ്മി", messages[0]) # Arabic/Malayalam text in Al-Fatihah 1:1

        # Format invalid verse
        messages = main.format_verses(1, [99], "both") # Fatihah has only 7 verses
        self.assertIn("Verse not found", messages[0])

        # Format Malayalam only
        messages_ml = main.format_verses(1, [1], "malayalam")
        self.assertEqual(len(messages_ml), 1)
        self.assertIn("പരമകാരുണികനും", messages_ml[0])
        
        # Format Arabic only
        messages_ar = main.format_verses(1, [1], "arabic")
        self.assertEqual(len(messages_ar), 1)
        self.assertIn("بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ", messages_ar[0])

    def test_get_qiraat_page(self):
        # Check first page of Surah 1
        text, keyboard = main.get_qiraat_page(1, 1, "both")
        self.assertIn("Qira'at Mode", text)
        self.assertIn("Fatihah", text)
        self.assertIn("ആയത്തുകൾ: 1 - 5", text)
        
        # Verify keyboard buttons: Row 0 is Audio buttons, Row 1 is Navigation
        audio_buttons = keyboard.inline_keyboard[0]
        self.assertEqual(len(audio_buttons), 5)
        self.assertEqual(audio_buttons[0].text, "🔊 1")
        self.assertEqual(audio_buttons[0].callback_data, "qiraat_play_1_1")
        
        nav_buttons = keyboard.inline_keyboard[1]
        self.assertEqual(len(nav_buttons), 1)
        self.assertEqual(nav_buttons[0].text, "അടുത്തത് (Next) ➡️")
        self.assertEqual(nav_buttons[0].callback_data, "qiraat_page_1_6")

        # Check middle page of Surah 2 (total 286 verses, page starting at 6)
        text, keyboard = main.get_qiraat_page(2, 6, "both")
        audio_buttons = keyboard.inline_keyboard[0]
        self.assertEqual(len(audio_buttons), 5)
        self.assertEqual(audio_buttons[0].text, "🔊 6")
        
        nav_buttons = keyboard.inline_keyboard[1]
        # Should have Prev and Next
        self.assertEqual(len(nav_buttons), 2)
        self.assertEqual(nav_buttons[0].text, "⬅️ മുൻപത്തെ (Prev)")
        self.assertEqual(nav_buttons[0].callback_data, "qiraat_page_2_1")
        self.assertEqual(nav_buttons[1].text, "അടുത്തത് (Next) ➡️")
        self.assertEqual(nav_buttons[1].callback_data, "qiraat_page_2_11")

        # Check last page of Surah 1 (7 verses, starting at 6)
        text, keyboard = main.get_qiraat_page(1, 6, "both")
        audio_buttons = keyboard.inline_keyboard[0]
        self.assertEqual(len(audio_buttons), 2) # Only verses 6 and 7
        self.assertEqual(audio_buttons[0].text, "🔊 6")
        self.assertEqual(audio_buttons[1].text, "🔊 7")
        
        nav_buttons = keyboard.inline_keyboard[1]
        # Should only have Prev
        self.assertEqual(len(nav_buttons), 1)
        self.assertEqual(nav_buttons[0].text, "⬅️ മുൻപത്തെ (Prev)")
        self.assertEqual(nav_buttons[0].callback_data, "qiraat_page_1_1")

if __name__ == "__main__":
    unittest.main()
