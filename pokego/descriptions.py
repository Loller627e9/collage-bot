"""The two description types: Eldorado (marketplace listing) and Auction (lot notes).

Both are generated from the same verified facts and the same deterministic
classification, so neither can describe an account as better than the evidence
supports. A deterministic fallback is always available, so the bot still works
with no API key.

The Eldorado text follows the house format of that marketplace: a keyword title,
then a flat inventory of what the account holds. The Auction text is an
auctioneer's itemised lot sheet. Neither is an audit - the evidence tables live
in the report, so the listing stays readable.

Hard rules encoded here, matching the investigation spec:
  * no invented numbers
  * no prices, no currency estimates
  * account trading is restricted by the game's terms
"""

from __future__ import annotations

from dataclasses import dataclass

from .classification import ClassificationResult
from .rarity import RarityAssessment, top_highlights
from .schema import AccountScan
from .titles import listing_title

ELDORADO = "eldorado"
AUCTION = "auction"

DESCRIPTION_TYPES = (ELDORADO, AUCTION)

# Shown on every description so a reader cannot mistake these for a valuation.
VALUATION_NOTICE = (
    "No price is estimated. This description reflects the supplied screenshots "
    "only. Account trading is restricted by the Pokémon GO terms of service."
)


@dataclass
class Description:
    kind: str
    title: str
    body: str
    source: str = "deterministic"
    listing_title: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title, "body": self.body,
                "source": self.source, "listing_title": self.listing_title}


def _num(value) -> str:
    """Format an optional integer, or 'not visible' when it was never seen."""
    if value is None:
        return "not visible"
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value)


def _descriptor(entry) -> str:
    """Short seller-style tag for one Pokémon: SHUNDO / HUNDO / SHINY / ... ."""
    if entry.is_shundo:
        return "SHUNDO"
    if entry.is_hundo:
        return "HUNDO"
    if entry.shiny and entry.legendary:
        return "SHINY LEGENDARY"
    if entry.shiny:
        return "SHINY"
    if entry.legendary:
        return "LEGENDARY"
    if entry.mythical:
        return "MYTHICAL"
    if entry.shadow:
        return "SHADOW"
    return ""


def _attribute_suffix(assessment: RarityAssessment) -> str:
    entry = assessment.entry
    bits: list[str] = []
    if entry.cp is not None:
        bits.append(f"CP {entry.cp:,}")
    if entry.iv_percent is not None:
        bits.append(f"{entry.iv_percent:g}% IV")
    if entry.costume:
        bits.append(entry.costume)
    if entry.background:
        bits.append(f"{entry.background} background")
    if entry.legacy_move:
        bits.append(f"legacy {entry.legacy_move}")
    if entry.gigantamax:
        bits.append("Gigantamax")
    elif entry.dynamax:
        bits.append("Dynamax")
    elif entry.mega:
        bits.append("Mega")
    if entry.lucky:
        bits.append("lucky")
    return ", ".join(bits)


def _standout_lines(assessments: list[RarityAssessment], limit: int = 12) -> list[str]:
    """Collapse the strongest pieces into '3× Shiny Zacian ✨' style lines."""
    grouped: dict[tuple, int] = {}
    for assessment in top_highlights(assessments, limit=limit):
        entry = assessment.entry
        key = (entry.species, _descriptor(entry), entry.costume or "",
               entry.background or "", entry.legacy_move or "")
        grouped[key] = grouped.get(key, 0) + 1

    lines: list[str] = []
    for (species, descriptor, costume, background, move), count in grouped.items():
        parts: list[str] = []
        if count > 1:
            parts.append(f"{count}×")
        if descriptor:
            parts.append(descriptor.title())
        if costume:
            parts.append(costume)
        parts.append(species)
        line = " ".join(parts)
        extras: list[str] = []
        if background:
            extras.append(f"{background} BG")
        if move:
            extras.append(f"legacy {move}")
        if extras:
            line += " — " + " · ".join(extras)
        lines.append(line + " ✨")
    return lines


def _inventory_lines(scan: AccountScan) -> list[str]:
    """Flat count lines, in the order a buyer scans for. Zero counts are omitted."""
    counts = scan.counts()
    lines: list[str] = []
    for count, noun in (
        (counts["legendary"], "Legendary Pokémon"),
        (counts["shiny"], "Shiny Pokémon"),
        (counts["shiny_legendary"], "Shiny Legendary Pokémon"),
        (counts["mythical"], "Mythical Pokémon"),
        (counts["ultra_beast"], "Ultra Beast Pokémon"),
        (counts["shundo"], "Shundo (Shiny 100% IV)"),
        (counts["hundo"], "Perfect IV (100% IV)"),
        (counts["background"], "Special Background Pokémon"),
        (counts["costume"], "Costume Pokémon"),
        (counts["legacy_move"], "Legacy Move Pokémon"),
        (counts["regional"], "Regional Pokémon"),
        (counts["lucky"], "Lucky Pokémon"),
        (counts["shadow"], "Shadow Pokémon"),
        (counts["dynamax"], "Dynamax Pokémon"),
        (counts["gigantamax"], "Gigantamax Pokémon"),
        (counts["mega"], "Mega Evolutions"),
        (counts["xxl"], "XXL Pokémon"),
    ):
        if count:
            lines.append(f"{count} {noun}")
    return lines


def _account_lines(scan: AccountScan) -> list[str]:
    facts = scan.facts
    lines: list[str] = []
    if facts.level is not None:
        lines.append(f"LEVEL {facts.level}")
    if facts.xp is not None:
        lines.append(f"{facts.xp:,} XP")
    if facts.team:
        lines.append(f"{facts.team} team")
    if facts.total_caught is not None:
        lines.append(f"{facts.total_caught:,} Pokémon caught")
    if facts.pokedex_caught is not None:
        seen = f" / {facts.pokedex_seen} seen" if facts.pokedex_seen is not None else ""
        lines.append(f"Pokédex {facts.pokedex_caught} caught{seen}")
    if facts.medals:
        count = len(facts.medals)
        lines.append(f"{count} medal" if count == 1 else f"{count} medals")
    return lines


def _resource_lines(scan: AccountScan) -> list[str]:
    facts = scan.facts
    lines: list[str] = []
    if facts.stardust is not None:
        lines.append(f"{facts.stardust:,} Stardust 🌠")
    if facts.pokecoins is not None:
        lines.append(f"{facts.pokecoins:,} PokéCoins")
    if facts.rare_candy is not None:
        lines.append(f"{facts.rare_candy:,} Rare Candy")
    if facts.rare_candy_xl is not None:
        lines.append(f"{facts.rare_candy_xl:,} Rare Candy XL")
    if facts.pokemon_storage is not None:
        lines.append(f"Pokémon Storage: {facts.pokemon_storage:,}")
    if facts.item_storage is not None:
        lines.append(f"Item Storage: {facts.item_storage:,}")
    return lines


def eldorado_description(
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
    *,
    narrative: str | None = None,
) -> Description:
    """Marketplace listing copy in the Eldorado house style."""
    title = listing_title(scan, assessments, classification)

    if narrative and narrative.strip():
        return Description(
            ELDORADO, "Eldorado Listing", narrative.strip() + "\n\n" + VALUATION_NOTICE,
            "gemini", listing_title=title,
        )

    facts = scan.facts
    lines = ["Pokémon GO Account", ""]

    header = f"{classification.account_class.value} account"
    if facts.team:
        header += f" · {facts.team} team"
    lines.append(header + ".")

    account = _account_lines(scan)
    if account:
        lines.append("")
        lines.extend(account)

    inventory = _inventory_lines(scan)
    if inventory:
        lines.append("")
        lines.extend(inventory)

    standouts = _standout_lines(assessments)
    if standouts:
        lines.append("")
        lines.extend(standouts)

    resources = _resource_lines(scan)
    if resources:
        lines.append("")
        lines.extend(resources)

    if not inventory and not standouts:
        lines.append("")
        if scan.pokemon:
            lines.append("No rare pieces were visible in the supplied screenshots.")
        else:
            lines.append("Collection details were not visible in the supplied screenshots.")

    lines.append("")
    lines.append(VALUATION_NOTICE)
    return Description(ELDORADO, "Eldorado Listing", "\n".join(lines), listing_title=title)


def auction_description(
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
    *,
    narrative: str | None = None,
) -> Description:
    """Auctioneer's lot sheet: itemised and factual."""
    title = listing_title(scan, assessments, classification)

    if narrative and narrative.strip():
        return Description(
            AUCTION, "Auction Lot Notes", narrative.strip() + "\n\n" + VALUATION_NOTICE,
            "gemini", listing_title=title,
        )

    facts = scan.facts
    counts = scan.counts()
    lines = [
        f"LOT: Pokémon GO account — {classification.account_class.value}",
        "",
        "LOT HIGHLIGHTS",
    ]
    highlights = top_highlights(assessments, limit=8)
    if highlights:
        for assessment in highlights:
            suffix = _attribute_suffix(assessment)
            line = f"- {assessment.entry.species}"
            if suffix:
                line += f" — {suffix}"
            line += f" [{assessment.label.value}]"
            lines.append(line)
    else:
        lines.append("- No standout items identified from the supplied evidence.")

    lines.append("")
    lines.append("PROGRESSION")
    lines.append(f"- Trainer level: {_num(facts.level)}")
    lines.append(f"- Pokédex caught: {_num(facts.pokedex_caught)}")
    lines.append(f"- Pokémon caught: {_num(facts.total_caught)}")
    lines.append("")
    lines.append("RESOURCES")
    lines.append(f"- Stardust: {_num(facts.stardust)}")
    lines.append(f"- PokéCoins: {_num(facts.pokecoins)}")
    lines.append(f"- Rare Candy: {_num(facts.rare_candy)}")
    lines.append(f"- Rare Candy XL: {_num(facts.rare_candy_xl)}")
    lines.append("")
    lines.append("COLLECTION TOTALS (identified)")
    lines.append(f"- Shiny {counts['shiny']} · Legendary {counts['legendary']} · "
                 f"Mythical {counts['mythical']} · Hundo {counts['hundo']} · "
                 f"Shundo {counts['shundo']}")
    lines.append(f"- Costume {counts['costume']} · Background {counts['background']} · "
                 f"Legacy moves {counts['legacy_move']}")
    lines.append("")
    lines.append("EVIDENCE")
    lines.append(f"- Facts evidence status: {facts.evidence.value}")
    lines.append(f"- Screenshots supplied: {len(scan.screenshots)}")
    if scan.warnings:
        lines.append("- Unreadable or unclear: " + "; ".join(scan.warnings[:3]))
    lines.append(f"- Signals not visible: "
                 f"{', '.join(classification.to_dict()['missing_signals']) or 'none'}")
    lines.append("")
    lines.append(VALUATION_NOTICE)
    return Description(AUCTION, "Auction Lot Notes", "\n".join(lines), listing_title=title)


def build_description(
    kind: str,
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
    *,
    narrative: str | None = None,
) -> Description:
    kind = (kind or "").strip().lower()
    if kind == ELDORADO:
        return eldorado_description(scan, assessments, classification, narrative=narrative)
    if kind == AUCTION:
        return auction_description(scan, assessments, classification, narrative=narrative)
    raise ValueError(f"unknown description type: {kind!r} (expected one of {DESCRIPTION_TYPES})")
