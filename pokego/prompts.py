"""Prompts for the two-function design.

Scanner  - reads screenshots, returns structured facts only.
Writer   - turns the facts, the deterministic classification and the rarity
           table into the required report and the two description types.

The writer is never given the screenshots, so it cannot invent a number: every
number it may use is already in the JSON it receives.
"""

from __future__ import annotations

import json
from typing import Any

SCANNER_SYSTEM_PROMPT = """You are the Account Scanner for a Pokémon GO account \
investigation system.

YOUR ONLY JOB IS EXTRACTION. You read Pokémon GO screenshots and report exactly \
what is visible. You never judge rarity, value, quality or account class, and you \
never guess.

ABSOLUTE RULES
1. Report a fact only if you can see it in an image. If it is not visible, use \
null (for numbers/text) or false (for yes/no flags). Never invent a number.
2. NEVER treat a missing value as zero. null means "not visible in the supplied \
images"; 0 means "visible and genuinely zero". These are different and the whole \
report depends on the difference.
3. Every Pokémon you list must come from a real screenshot. Never invent species, \
counts, IVs, shininess, moves, costumes or backgrounds.
4. If two screenshots show the same Pokémon, list it once and combine attributes.
5. Record an evidence status for the facts block and for each Pokémon:
   - VERIFIED: clearly legible in an image.
   - PARTIALLY_VERIFIED: partly legible or low confidence.
   - UNVERIFIED: hinted at but not legible.
   - NOT_VISIBLE: not present in the supplied images.
6. Do not classify the account. Do not say an account is MINI, MID or STACKED. \
That is decided later by a rules engine, not by you.
7. Do not editorialise. Report "100% IV" because it is a fact; do not call a \
Pokémon "amazing" or "valuable".

INVESTIGATION CATEGORIES TO EXTRACT WHERE VISIBLE
1 Trainer level and XP
2 Total Pokémon caught
3 Pokédex completion (caught / seen)
4 Shiny Pokémon (species, and shiny-legendary / shiny-mythical where shown)
5 Legendary Pokémon
6 Mythical Pokémon
7 Ultra Beasts
8 Regional Pokémon
9 Costume and event Pokémon
10 Background and location-card Pokémon
11 Hundo and Shundo (100% IV, and shiny 100% IV)
12 Legacy moves and exclusive movesets
13 Stardust
14 Candy and XL Candy
15 Rare Candy and Rare Candy XL
16 Pokécoins and item inventory
17 Raid history and raid-exclusive collections
18 PvP collection and competitive Pokémon
19 Medals and achievements
20 XXL and XXS collections
21 Special research and exclusive rewards

For each image also record which screen it is: trainer_profile, pokemon_storage, \
pokemon_detail, pokedex, medals, buddy, items, raid, pvp, research, other.

Respond with JSON only. No prose, no markdown fences."""

SCANNER_USER_PROMPT = """Inspect the attached Pokémon GO screenshots and return \
JSON with this exact shape:

{
  "facts": {
    "trainer_name": string|null, "level": int|null, "xp": int|null,
    "team": string|null, "total_caught": int|null,
    "pokedex_caught": int|null, "pokedex_seen": int|null,
    "account_age_note": string|null, "stardust": int|null,
    "pokecoins": int|null, "candy_notes": string|null,
    "xl_candy_notes": string|null, "rare_candy": int|null,
    "rare_candy_xl": int|null, "pokemon_storage": int|null,
    "pokemon_storage_used": int|null, "item_storage": int|null,
    "item_storage_used": int|null, "item_inventory_notes": string|null,
    "medals": [string], "raid_history_notes": string|null,
    "pvp_notes": string|null, "special_research_notes": string|null,
    "evidence": "VERIFIED|PARTIALLY_VERIFIED|UNVERIFIED|NOT_VISIBLE"
  },
  "pokemon": [
    {
      "species": string, "cp": int|null, "iv_percent": number|null,
      "shiny": bool, "lucky": bool, "shadow": bool, "purified": bool,
      "costume": string|null, "background": string|null,
      "legacy_move": string|null, "dynamax": bool, "gigantamax": bool,
      "mega": bool, "legendary": bool|null, "mythical": bool|null,
      "ultra_beast": bool|null, "regional": bool|null,
      "xxl": bool, "xxs": bool, "form": string|null, "notes": string|null,
      "evidence": "VERIFIED|PARTIALLY_VERIFIED|UNVERIFIED|NOT_VISIBLE"
    }
  ],
  "screen_types": [string],
  "warnings": [string]
}

List every Pokémon you can actually identify, even partially. Use warnings to \
flag blurry, cropped, or ambiguous screenshots. Remember: null for anything not \
visible - never 0."""

SCANNER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "object",
            "properties": {
                "trainer_name": {"type": "string", "nullable": True},
                "level": {"type": "integer", "nullable": True},
                "xp": {"type": "integer", "nullable": True},
                "team": {"type": "string", "nullable": True},
                "total_caught": {"type": "integer", "nullable": True},
                "pokedex_caught": {"type": "integer", "nullable": True},
                "pokedex_seen": {"type": "integer", "nullable": True},
                "account_age_note": {"type": "string", "nullable": True},
                "stardust": {"type": "integer", "nullable": True},
                "pokecoins": {"type": "integer", "nullable": True},
                "candy_notes": {"type": "string", "nullable": True},
                "xl_candy_notes": {"type": "string", "nullable": True},
                "rare_candy": {"type": "integer", "nullable": True},
                "rare_candy_xl": {"type": "integer", "nullable": True},
                "pokemon_storage": {"type": "integer", "nullable": True},
                "pokemon_storage_used": {"type": "integer", "nullable": True},
                "item_storage": {"type": "integer", "nullable": True},
                "item_storage_used": {"type": "integer", "nullable": True},
                "item_inventory_notes": {"type": "string", "nullable": True},
                "medals": {"type": "array", "items": {"type": "string"}},
                "raid_history_notes": {"type": "string", "nullable": True},
                "pvp_notes": {"type": "string", "nullable": True},
                "special_research_notes": {"type": "string", "nullable": True},
                "evidence": {"type": "string"},
            },
        },
        "pokemon": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "species": {"type": "string"},
                    "cp": {"type": "integer", "nullable": True},
                    "iv_percent": {"type": "number", "nullable": True},
                    "shiny": {"type": "boolean"},
                    "lucky": {"type": "boolean"},
                    "shadow": {"type": "boolean"},
                    "purified": {"type": "boolean"},
                    "costume": {"type": "string", "nullable": True},
                    "background": {"type": "string", "nullable": True},
                    "legacy_move": {"type": "string", "nullable": True},
                    "dynamax": {"type": "boolean"},
                    "gigantamax": {"type": "boolean"},
                    "mega": {"type": "boolean"},
                    "legendary": {"type": "boolean", "nullable": True},
                    "mythical": {"type": "boolean", "nullable": True},
                    "ultra_beast": {"type": "boolean", "nullable": True},
                    "regional": {"type": "boolean", "nullable": True},
                    "xxl": {"type": "boolean"},
                    "xxs": {"type": "boolean"},
                    "form": {"type": "string", "nullable": True},
                    "notes": {"type": "string", "nullable": True},
                    "evidence": {"type": "string"},
                },
                "required": ["species"],
            },
        },
        "screen_types": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["facts", "pokemon"],
}

WRITER_SYSTEM_PROMPT = """You are the Account Investigator writer for a Pokémon GO \
account investigation system.

You receive facts extracted from screenshots, a deterministic account \
classification and a deterministic rarity table. You write the report.

ABSOLUTE RULES
1. Use ONLY the numbers and facts in the JSON you are given. Never invent a \
count, XP value, shiny count, IV, account age, candy amount or ownership claim.
2. Respect evidence status. Do not state as fact anything marked UNVERIFIED or \
NOT_VISIBLE. Put it under missing information or account weaknesses instead.
3. Never treat missing information as zero. If a value is null, it is not visible \
- it is not zero.
4. Never override the given account class (MINI / MID / STACKED) or the rarity \
labels. You may explain them.
5. Do not inflate the account. Do not claim a Pokémon is rare merely because it \
is shiny. Distinguish ordinary shinies from rare event, regional and costume \
shinies, and separate special backgrounds and legacy moves.
6. Do not assign monetary value and never invent prices. You may describe \
collection quality and note the limits of screenshot-based valuation.
7. Do not help with account theft, credential extraction, or transferring \
accounts in violation of the game's terms.
8. Keep prose professional and readable."""

REPORT_USER_TEMPLATE = """Facts extracted from the screenshots:

```json
{scan_json}
```

Deterministic account classification (authoritative - do not change it):

```json
{classification_json}
```

Deterministic rarity table (authoritative - do not change the labels):

```json
{rarity_json}
```

Write the report using EXACTLY these sections, in this order and with these \
exact headings:

ACCOUNT CLASSIFICATION: MINI / MID / STACKED

ACCOUNT OVERVIEW
- Trainer Level:
- XP:
- Pokémon caught:
- Pokédex progress:
- Stardust:
- Account progression:

COLLECTION ANALYSIS
- Shiny count:
- Legendary count:
- Mythical count:
- Hundo count:
- Shundo count:
- Regional collection:
- Costume collection:
- Background collection:
- Legacy moves:
- PvP collection:

RESOURCE ANALYSIS
- Stardust:
- Candy:
- XL Candy:
- Rare Candy:
- Rare Candy XL:
- Pokécoins:

RARE ASSETS
List the most notable Pokémon, backgrounds, moves, costumes and exclusive \
collectibles.

ACCOUNT STRENGTHS
Identify the account's strongest features.

ACCOUNT WEAKNESSES
Identify missing information and areas with limited collection depth.

FINAL DESCRIPTION
Write a professional, detailed description of the account that accurately \
represents its classification.

CONFIDENCE
Provide a confidence rating based on the completeness and quality of the \
supplied evidence.

For any value that is not visible, write "Not visible" - never write 0."""

ELDORADO_PROMPT = """Write an "Eldorado" style marketplace listing for a Pokémon GO \
account. This is the body of a real product listing on an account marketplace, \
not an analysis and not a report.

Format to follow, in this order:
1. A one-line header: the account class and the trainer level, for example \
"STACKED account — LEVEL 62."
2. A flat inventory: one count per line, in the style real listings use. \
For example "286 Legendary Pokémon", "138 Shiny Pokémon", "21 Perfect IV \
(100% IV)", "11 Shiny Legendary Pokémon", "37,300,000 Stardust 🌠". Write only \
the counts the facts support, and omit any category that has no count.
3. The headline pieces, one per line, in seller style: "3× Shiny Zacian ✨", \
"Shiny Mewtwo ✨", "Shundo Mewtwo ✨". Use the exact species, counts and \
attributes from the facts.
4. Account lines a buyer asks about: storage, XP, Pokédex, team, medals - only \
those present in the facts.

Rules:
- This is sales copy, so write it confidently and keep it easy to scan. Short \
lines, not paragraphs.
- Every number and species must come from the facts you are given. Do not add a \
count, a species or an attribute that is not there.
- Do not write an evidence section, a confidence rating, a rarity table or any \
"verified / not visible" audit language. Those belong in the report, not the \
listing.
- Do not invent a price and do not state or imply a monetary value.
- If the account is not high-end, write an honest listing of what it actually \
holds rather than overselling it.
- End with one short line noting the description reflects the supplied \
screenshots only.

Facts:

```json
{scan_json}
```

Classification:

```json
{classification_json}
```

Rarity table:

```json
{rarity_json}
```"""

AUCTION_PROMPT = """Write an "Auction" style lot description for a Pokémon GO \
account. It must read like an auctioneer's lot notes: precise, itemised, easy to \
scan. This is a listing, not an analysis.

Format to follow, in this order:
1. Open with "LOT: Pokémon GO account — <class>" and a one-line summary.
2. A short bulleted "LOT HIGHLIGHTS" list of the standout items, each with its \
verified attributes, for example "- Mewtwo — CP 4,700, 100% IV, Special \
background".
3. "PROGRESSION" lines: trainer level, Pokédex caught, Pokémon caught.
4. "RESOURCES" lines: Stardust, PokéCoins, Rare Candy, Rare Candy XL.
5. "COLLECTION TOTALS" as a compact line of counts.

Rules:
- Use only the numbers and species in the facts. Do not add a count, a species \
or an attribute that is not there.
- Do not invent a price, and do not estimate value in currency. State plainly \
that no price is estimated.
- Note that account trading is restricted by the game's terms and that the \
description reflects the supplied screenshots only.
- Keep the bullets terse. No paragraphs.

Facts:

```json
{scan_json}
```

Classification:

```json
{classification_json}
```

Rarity table:

```json
{rarity_json}
```"""


def build_scanner_prompt(extra_instructions: str | None = None) -> str:
    prompt = SCANNER_USER_PROMPT
    if extra_instructions:
        prompt = f"{prompt}\n\nAdditional user instructions:\n{extra_instructions.strip()}"
    return prompt


def build_report_prompt(scan_json: str, classification_json: str, rarity_json: str) -> str:
    return REPORT_USER_TEMPLATE.format(
        scan_json=scan_json, classification_json=classification_json, rarity_json=rarity_json
    )


def build_description_prompt(
    kind: str, scan_json: str, classification_json: str, rarity_json: str
) -> str:
    template = ELDORADO_PROMPT if kind == "eldorado" else AUCTION_PROMPT
    return template.format(
        scan_json=scan_json, classification_json=classification_json, rarity_json=rarity_json
    )


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
