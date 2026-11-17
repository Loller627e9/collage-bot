"""Deterministic listing titles in the Eldorado house style.

Marketplace titles are a keyword format, not prose: a leading emoji, the
trainer level, the headline counts, the named standouts, then delivery words.
Sellers pack as much searchable detail as the character limit allows.

Titles are built here from the verified scan rather than written by the model,
for the same reason the report tables are: a title is the most-read line of the
listing and it must not gain a single number that the screenshots do not
support. Every segment is dropped when its fact is not visible, so a sparse
scan yields a shorter title, never a padded one.
"""

from __future__ import annotations

from .classification import ClassificationResult
from .rarity import RarityAssessment, top_highlights
from .schema import AccountScan

# Marketplaces truncate titles; keep the whole line comfortably inside that.
TITLE_LIMIT = 120

_SEP = " | "


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _short_number(value: int) -> str:
    """Compact marketplace number: 2_900_000 -> '2.9M', 375_000 -> '375K'."""
    if value >= 1_000_000:
        millions = value / 1_000_000
        text = f"{millions:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if value >= 1_000:
        return f"{value // 1_000}K"
    return str(value)


def _headline_pokemon(assessments: list[RarityAssessment], limit: int = 3) -> list[str]:
    """Names of the strongest pieces, with the marker a buyer scans for."""
    names: list[str] = []
    for assessment in top_highlights(assessments, limit=limit):
        entry = assessment.entry
        marker = "SHUNDO" if entry.is_shundo else ("HUNDO" if entry.is_hundo else "")
        if entry.shiny and not marker:
            marker = "SHINY"
        if entry.legendary and not marker:
            marker = "LEGENDARY"
        if entry.mythical and not marker:
            marker = "MYTHICAL"
        name = entry.species.upper()
        label = f"{marker} {name}".strip()
        if label and label not in names:
            names.append(label)
    return names


def _segments(
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
) -> list[str]:
    counts = scan.counts()
    facts = scan.facts
    segments: list[str] = []

    segments.append(classification.account_class.value)

    if facts.level is not None:
        segments.append(f"LEVEL {facts.level}")

    if facts.team:
        segments.append(facts.team.upper())

    # Stardust ranks above the named pieces: it is a headline search term.
    if facts.stardust:
        segments.append(f"{_short_number(facts.stardust)} DUST")

    segments.extend(_headline_pokemon(assessments))

    if counts["shiny_legendary"]:
        segments.append(f"{counts['shiny_legendary']} SHINY LEG")
    elif counts["shiny"]:
        segments.append(f"{counts['shiny']} SHINY")
    if counts["legendary"]:
        segments.append(f"{counts['legendary']} LEG")
    if counts["mythical"]:
        segments.append(f"{counts['mythical']} MYTHICAL")
    if counts["shundo"]:
        segments.append(_plural(counts["shundo"], "SHUNDO"))
    elif counts["hundo"]:
        segments.append(_plural(counts["hundo"], "HUNDO"))
    if counts["background"]:
        segments.append(f"{counts['background']} BG")
    if counts["costume"]:
        segments.append(_plural(counts["costume"], "COSTUME"))
    if facts.pokedex_caught:
        segments.append(f"POKEDEX {facts.pokedex_caught}")
    return segments


def _emoji(
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
) -> str:
    counts = scan.counts()
    if classification.account_class.value == "STACKED":
        return "👑"
    if counts["shundo"] or counts["shiny_legendary"]:
        return "💎"
    if counts["shiny"] or counts["legendary"]:
        return "✨"
    if classification.account_class.value == "MINI":
        return "🎮"
    return "🔥"


def listing_title(
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
    *,
    limit: int = TITLE_LIMIT,
) -> str:
    """A keyword-packed, honest listing title. Never adds an unseen fact."""
    segments = _segments(scan, assessments, classification)

    # Fill to the limit, dropping the lowest-value segments first when needed.
    while segments:
        title = _emoji(scan, assessments, classification) + " " + _SEP.join(segments)
        if len(title) <= limit:
            return title
        segments.pop()
    return _emoji(scan, assessments, classification) + " Pokémon GO Account"
