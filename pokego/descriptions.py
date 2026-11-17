"""The two description types: Eldorado and Auction.

Both are generated from the same verified facts and the same deterministic
classification, so neither can describe an account as better than the evidence
supports. A deterministic fallback is always available, so the bot still works
with no API key.

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

    def to_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title, "body": self.body,
                "source": self.source}


def _best_asset(assessments: list[RarityAssessment]) -> RarityAssessment | None:
    highlights = top_highlights(assessments, limit=1)
    return highlights[0] if highlights else None


def _num(value) -> str:
    """Format an optional integer, or 'not visible' when it was never seen."""
    if value is None:
        return "not visible"
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value)


def _attribute_suffix(assessment: RarityAssessment) -> str:
    entry = assessment.entry
    bits: list[str] = []
    if entry.cp is not None:
        bits.append(f"CP {entry.cp:,}")
    if entry.iv_percent is not None:
        bits.append(f"{entry.iv_percent:g}% IV")
    if entry.shiny:
        bits.append("shiny")
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
    if entry.lucky:
        bits.append("lucky")
    return ", ".join(bits)


def eldorado_description(
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
    *,
    narrative: str | None = None,
) -> Description:
    """Showpiece listing copy. Vivid, but bounded by the facts."""
    if narrative and narrative.strip():
        return Description(ELDORADO, "Eldorado Description",
                           narrative.strip() + "\n\n" + VALUATION_NOTICE, "gemini")

    c = scan.counts()
    f = scan.facts
    best = _best_asset(assessments)
    level = f"Level {f.level}" if f.level is not None else "trainer level not visible"

    lines = [
        f"A {classification.account_class.value} Pokémon GO account — {level}.",
        "",
    ]
    if best is not None:
        suffix = _attribute_suffix(best)
        lead = f"Headline asset: {best.entry.species}"
        if suffix:
            lead += f" ({suffix})"
        lines.append(lead + f" — {best.label.value}.")
        lines.append("")

    standout: list[str] = []
    if c["shiny"]:
        standout.append(f"{c['shiny']} shiny identified")
    if c["legendary"]:
        standout.append(f"{c['legendary']} legendary")
    if c["mythical"]:
        standout.append(f"{c['mythical']} mythical")
    if c["shundo"]:
        standout.append(f"{c['shundo']} shundo")
    elif c["hundo"]:
        standout.append(f"{c['hundo']} hundo")
    if c["costume"]:
        standout.append(f"{c['costume']} costume")
    if c["background"]:
        standout.append(f"{c['background']} special background")
    if c["legacy_move"]:
        standout.append(f"{c['legacy_move']} legacy move")
    if standout:
        lines.append("Collection: " + ", ".join(standout) + ".")
    else:
        lines.append("No standout collection items were visible in the supplied "
                     "screenshots.")

    if f.stardust is not None or f.pokecoins is not None:
        res: list[str] = []
        if f.stardust is not None:
            res.append(f"{f.stardust:,} stardust")
        if f.pokecoins is not None:
            res.append(f"{f.pokecoins:,} PokéCoins")
        lines.append("Resources: " + ", ".join(res) + ".")

    lines.append("")
    lines.append("Classification evidence:")
    lines.extend(f"- {reason}" for reason in classification.reasons)
    lines.append("")
    lines.append(VALUATION_NOTICE)
    return Description(ELDORADO, "Eldorado Description", "\n".join(lines))


def auction_description(
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
    *,
    narrative: str | None = None,
) -> Description:
    """Auctioneer's lot notes: itemised and factual."""
    if narrative and narrative.strip():
        return Description(AUCTION, "Auction Description",
                           narrative.strip() + "\n\n" + VALUATION_NOTICE, "gemini")

    c = scan.counts()
    f = scan.facts
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
    lines.append(f"- Trainer level: {_num(f.level)}")
    lines.append(f"- Pokédex caught: {_num(f.pokedex_caught)}")
    lines.append(f"- Pokémon caught: {_num(f.total_caught)}")
    lines.append("")
    lines.append("RESOURCES")
    lines.append(f"- Stardust: {_num(f.stardust)}")
    lines.append(f"- PokéCoins: {_num(f.pokecoins)}")
    lines.append(f"- Rare Candy: {_num(f.rare_candy)}")
    lines.append(f"- Rare Candy XL: {_num(f.rare_candy_xl)}")
    lines.append("")
    lines.append("COLLECTION TOTALS (identified)")
    lines.append(f"- Shiny {c['shiny']} · Legendary {c['legendary']} · "
                 f"Mythical {c['mythical']} · Hundo {c['hundo']} · "
                 f"Shundo {c['shundo']}")
    lines.append(f"- Costume {c['costume']} · Background {c['background']} · "
                 f"Legacy moves {c['legacy_move']}")
    lines.append("")
    lines.append("EVIDENCE")
    lines.append(f"- Facts evidence status: {f.evidence.value}")
    lines.append(f"- Screenshots supplied: {len(scan.screenshots)}")
    if scan.warnings:
        lines.append("- Unreadable or unclear: " + "; ".join(scan.warnings[:3]))
    lines.append(f"- Signals not visible: "
                 f"{', '.join(classification.to_dict()['missing_signals']) or 'none'}")
    lines.append("")
    lines.append(VALUATION_NOTICE)
    return Description(AUCTION, "Auction Description", "\n".join(lines))


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
