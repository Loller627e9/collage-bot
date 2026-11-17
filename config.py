"""
config.py - optional settings for TTC Collage Bot. Keep it in the same folder as bot.py.

Priority: environment variable  >  this file  >  built-in default.
(So on Render you can use either Render's Environment tab or fill this in. If both are set,
the Render env var wins.) Blank values are ignored.

SECURITY: do NOT commit a real BOT_TOKEN in a PUBLIC repository - anyone could take over
your bot. Use a private repo, or leave BOT_TOKEN blank here and set it on Render instead.

How to find a numeric Telegram ID: message @userinfobot, or send /id to this bot, or read
it from the "This bot is private" reply a new person receives.
"""

# --- required --------------------------------------------------------------------------
BOT_TOKEN = ""            # from @BotFather, e.g. "123456789:AAH..."
WEBHOOK_SECRET = ""       # Render only. Letters, digits, _ and - only, e.g. "k3J9_x-Q..."

# --- who may use the bot (fill at least one admin or allowed entry) ----------------------
# Admins can use /admin, /allow, /ban, /broadcast, ... IDs are safer than usernames.
ADMIN_IDS = []            # e.g. [123456789]
ADMIN_USERNAMES = []      # e.g. ["yourname"]   (no @)

# Normal users (collage only).
ALLOWED_IDS = []          # e.g. [111111111, 222222222]
ALLOWED_USERNAMES = []    # e.g. ["friend1", "friend2"]

# --- optional --------------------------------------------------------------------------
WATERMARK_TEXT = "TTC"    # basic Latin letters/digits/punctuation only

# --- account investigation (/analyze, /desc) --------------------------------------------
# Optional. Without a key the collage bot works normally and /analyze reports that
# investigation is unavailable. Get a key at https://aistudio.google.com/apikey
GEMINI_API_KEY = ""       # e.g. "AIza..." - keep this out of a PUBLIC repository
# Leave blank to try the current models in order; set one to pin it.
GEMINI_MODEL = ""         # e.g. "gemini-3.8-flash"
# Leave blank for Google's endpoint; set a proxy URL if you use one.
GEMINI_BASE_URL = ""
# auto | interactions | generatecontent
GEMINI_TRANSPORT = "auto"
# Default description style for /desc: "eldorado" or "auction".
DEFAULT_DESCRIPTION = "eldorado"
