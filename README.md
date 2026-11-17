# TTC Collage Bot + Pokémon GO Account Investigator

A private Telegram bot that turns Pokémon GO screenshots into a shareable collage,
and — optionally — into an evidence-based account investigation with a
MINI / MID / STACKED classification and a written description.

Two features, one bot:

1. **Collage** — send screenshots, get one clean collage. Every image keeps its own
   aspect ratio, nothing is cropped or stretched.
2. **Account investigation** — send account screenshots, send `/analyze`, and get a
   classification, an evidence-labelled report, and a description in one of two
   styles: **Eldorado** (marketplace listing with a keyword title) or
   **Auction** (itemised lot notes).

---

## Why the investigation is built as two functions

The obvious approach — one AI prompt that looks at screenshots and writes a
description — hallucinates. It invents shiny counts, guesses at rarity, and calls
every shiny "extremely rare".

This project separates the job:

| Stage | Responsibility | Can it invent numbers? |
|---|---|---|
| **Account Scanner** (Gemini) | Read screenshots, emit structured JSON facts only | No — it is told to use `null` when something is not visible |
| **Rules engines** (pure Python) | MINI/MID/STACKED classification, rarity labels, report tables | No — deterministic weights and thresholds |
| **Writer** (Gemini) | Narrative prose over the JSON and the rules output | Checked — numbers in prose the scan cannot support are flagged |

The AI reads pixels and writes words. It never decides how good an account is, and
it never sees the screenshots when it writes the prose, so it cannot invent from
them. Classification and rarity are reproducible and auditable.

---

## Quick start

```bash
pip install -r requirements.txt
```

Set at least one admin or allowed entry (environment variable or `config.py`), then:

```bash
BOT_TOKEN=... ADMIN_IDS=123456789 GEMINI_API_KEY=... python bot.py
```

On Render, set the same names in the Environment tab. `RENDER_EXTERNAL_URL` switches
the bot to webhook mode automatically; locally it polls.

Without `GEMINI_API_KEY` the collage features work normally and `/analyze` replies
that investigation needs a key — it never invents an account profile.

---

## Using it

Send up to 20 images. The collage builds after 10 seconds of quiet, or on `/done`.

| Command | What it does |
|---|---|
| `/done` | Build the collage now |
| `/layout` | Choose grid style (Auto, or 1–8 per row) |
| `/watermark` | Add or remove the watermark |
| `/quality` | Set JPEG quality (1–95) |
| `/analyze` | Classify the account and write the report |
| `/desc` | Choose Eldorado, Auction, or both |
| `/status` | Current settings |
| `/clear` | Reset the queue |
| `/id` | Show your Telegram ID |
| `/admin` | Admin panel (admins only) |

**Investigation flow:** send the account screenshots (trainer profile, Pokémon
storage, Pokédex, medals), pick a style with `/desc`, then `/analyze`. `/analyze`
remembers your last batch, so it still works after the collage has auto-built.

---

## The report

The report uses the required structure:

```
ACCOUNT CLASSIFICATION: MINI / MID / STACKED

ACCOUNT OVERVIEW
COLLECTION ANALYSIS
RESOURCE ANALYSIS
RARE ASSETS
ACCOUNT STRENGTHS
ACCOUNT WEAKNESSES
FINAL DESCRIPTION
CONFIDENCE
```

The overview, collection and resource tables are assembled from the scan, so their
numbers always match the evidence. Anything not visible is written as
**"Not visible"** — never as `0`.

---

## Classification rules

The spec sets two rules, and both are enforced structurally in
`pokego/classification.py`:

- **Never classify on Trainer Level alone.** A single observation can never lift an
  account above MINI, so a screenshot showing only a level returns MINI with LOW
  confidence.
- **Never treat missing information as zero.** A value that was never visible is
  excluded from both the numerator and the denominator. Absent evidence neither
  helps nor hurts the score; a separate coverage figure records how much was
  actually seen.

The score blends **progression** (level, Pokédex, caught, stardust, XP, candy,
medals) with **collection quality**, which is scored per Pokémon — a shiny
legendary, a shundo or a legacy move carries weight even in a small sample. A
STACKED verdict additionally requires that the collection was actually seen,
matching the spec's own definition.

---

## Descriptions

Two styles, both generated from the same verified facts:

- **Eldorado** — marketplace listing copy in the house style of that marketplace.
  It leads with a keyword listing title (`👑 STACKED | LEVEL 62 | MYSTIC |
  28M DUST | SHUNDO MEWTWO | 1 SHINY LEG | 2 LEG`), then a flat inventory of
  what the account holds, then the named headline pieces, then resources. A weak
  account is described honestly rather than oversold.
- **Auction** — itemised lot notes: `LOT HIGHLIGHTS`, `PROGRESSION`, `RESOURCES`,
  `COLLECTION TOTALS`, `EVIDENCE`.

The listing title is built from the verified facts, not written by the model, so
it cannot gain a number the screenshots do not support. Every segment is dropped
when its fact is not visible, so a sparse scan yields a shorter title rather than
a padded one.

Both carry the same notice: no price is estimated, the description reflects the
supplied screenshots only, and account trading is restricted by the game's terms.

---

## Layout

```
bot.py                 the bot (collage + investigation wiring)
config.py              optional settings; env vars win
pokego/
  schema.py            data model, evidence status, de-duplication
  classification.py    deterministic MINI / MID / STACKED
  rarity.py            curated species data + rarity rules
  report.py            report tables + numeric guard
  descriptions.py      Eldorado and Auction listings
  titles.py            deterministic listing titles
  gemini.py            API client (interactions + generateContent, fallback)
  prompts.py           Scanner and Writer prompts
  pipeline.py          orchestration
tests/                 171 tests, no network or API key required
```

---

## Configuration

Every setting can come from an environment variable or `config.py`. Environment
variables win, and blank values are ignored.

| Setting | Meaning |
|---|---|
| `BOT_TOKEN` | from @BotFather (required) |
| `WEBHOOK_SECRET` | Render only; letters, digits, `_` and `-` |
| `ADMIN_IDS` / `ADMIN_USERNAMES` | who can use `/admin` |
| `ALLOWED_IDS` / `ALLOWED_USERNAMES` | who can use the bot |
| `GEMINI_API_KEY` | enables `/analyze` and `/desc` |
| `GEMINI_MODEL` | pin a model; otherwise current models are tried in order |
| `GEMINI_BASE_URL` | override for a proxy |
| `GEMINI_TRANSPORT` | `auto`, `interactions`, or `generatecontent` |
| `DEFAULT_DESCRIPTION` | `eldorado` or `auction` |
| `WATERMARK_TEXT` | watermark text (basic Latin only) |
| `PROTECT_CONTENT` | stop recipients forwarding the collage |

---

## Tests

```bash
python -m pytest
```

171 tests cover de-duplication, the classification rules (including the
level-only and missing-is-not-zero guards), rarity, report structure, the numeric
guard, both description types, both Gemini transports against a mock server, the
pipeline end to end, and the bot wiring. No network or API key is needed.

---

## Privacy and scope

- Images are never written to disk. Each is downloaded into RAM and discarded.
- Settings, bans and allowlist additions live in RAM and reset when the service
  restarts.
- The investigator reports only what the screenshots show. It does not assign
  monetary value, does not invent prices, and does not facilitate account theft,
  credential extraction, or unauthorised access.
- Account trading is restricted by the Pokémon GO terms of service.

---

## Notes

The Gemini client uses the standard library (`urllib`), matching the bot's
dependency style — no SDK required. Both the `interactions` and `generateContent`
endpoints are supported with automatic fallback, because Google is mid-migration
between them. `gemini-2.5-flash` is deprecated for new API users, so the fallback
list starts at `gemini-3.8-flash`.

The rarity dataset in `pokego/rarity.py` is a curated snapshot of documented
species classes, not a live database. It is plain data: correct or extend it
without touching logic.
