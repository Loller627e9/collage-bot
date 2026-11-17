"""Deterministic report assembly.

The report tables are built here, from the scan and the rules engines, so their
numbers can never drift from the evidence. The model only supplies prose for the
narrative sections, and a numeric guard flags any number in that prose the scan
cannot support.

Section structure follows the investigation spec exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .classification import ClassificationResult
from .rarity import RarityAssessment, top_highlights
from .schema import AccountScan, Confidence

NOT_VISIBLE = "Not visible"

SECTION_ORDER = (
    "ACCOUNT OVERVIEW",
    "COLLECTION ANALYSIS",
    "RESOURCE ANALYSIS",
    "RARE ASSETS",
    "ACCOUNT STRENGTHS",
    "ACCOUNT WEAKNESSES",
    "FINAL DESCRIPTION",
    "CONFIDENCE",
)


@dataclass
class ReportBundle:
    classification: str
    markdown: str
    sections: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    narrative_source: str = "deterministic"
    confidence: Confidence = Confidence.LOW

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "markdown": self.markdown,
            "sections": dict(self.sections),
            "warnings": list(self.warnings),
            "missing_information": list(self.missing_information),
            "narrative_source": self.narrative_source,
            "confidence": self.confidence.value,
        }


def _fmt(value: object) -> str:
    if value is None or value == "":
        return NOT_VISIBLE
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _overview(scan: AccountScan) -> str:
    f = scan.facts
    lines = [
        f"- Trainer Level: {_fmt(f.level)}",
        f"- XP: {_fmt(f.xp)}",
        f"- Pokémon caught: {_fmt(f.total_caught)}",
        "- Pokédex progress: "
        + (
            f"caught {_fmt(f.pokedex_caught)}, seen {_fmt(f.pokedex_seen)}"
            if f.pokedex_caught is not None or f.pokedex_seen is not None
            else NOT_VISIBLE
        ),
        f"- Stardust: {_fmt(f.stardust)}",
        f"- Account progression: {_progression_line(scan)}",
    ]
    if f.team:
        lines.append(f"- Team: {f.team}")
    if f.trainer_name:
        lines.append(f"- Trainer: {f.trainer_name}")
    return "\n".join(lines)


def _progression_line(scan: AccountScan) -> str:
    f = scan.facts
    if f.level is None and f.pokedex_caught is None and f.xp is None:
        return NOT_VISIBLE
    bits: list[str] = []
    if f.level is not None:
        bits.append(f"level {f.level}")
    if f.pokedex_caught is not None:
        bits.append(f"{f.pokedex_caught} Pokédex entries")
    if len(f.medals) >= 20:
        bits.append(f"{len(f.medals)} medals")
    return ", ".join(bits) if bits else NOT_VISIBLE


def _collection(scan: AccountScan) -> str:
    c = scan.counts()
    return "\n".join([
        f"- Shiny count: {c['shiny']} identified",
        f"- Legendary count: {c['legendary']} identified",
        f"- Mythical count: {c['mythical']} identified",
        f"- Hundo count: {c['hundo']} identified",
        f"- Shundo count: {c['shundo']} identified",
        f"- Regional collection: {c['regional']} identified",
        f"- Costume collection: {c['costume']} identified",
        f"- Background collection: {c['background']} identified",
        f"- Legacy moves: {c['legacy_move']} identified",
        f"- PvP collection: {_pvp_line(scan)}",
        f"- Ultra Beasts: {c['ultra_beast']} identified",
        f"- XXL/XXS: {c['xxl'] + c['xxs']} identified",
    ])


def _pvp_line(scan: AccountScan) -> str:
    if scan.facts.pvp_notes:
        return scan.facts.pvp_notes
    return NOT_VISIBLE


def _resources(scan: AccountScan) -> str:
    f = scan.facts
    return "\n".join([
        f"- Stardust: {_fmt(f.stardust)}",
        f"- Candy: {f.candy_notes or NOT_VISIBLE}",
        f"- XL Candy: {f.xl_candy_notes or NOT_VISIBLE}",
        f"- Rare Candy: {_fmt(f.rare_candy)}",
        f"- Rare Candy XL: {_fmt(f.rare_candy_xl)}",
        f"- Pokécoins: {_fmt(f.pokecoins)}",
        "- Pokémon storage: "
        + (f"{f.pokemon_storage_used:,} / {f.pokemon_storage:,}"
           if f.pokemon_storage is not None and f.pokemon_storage_used is not None
           else _fmt(f.pokemon_storage or f.pokemon_storage_used)),
    ])


def _rare_assets(scan: AccountScan, assessments: list[RarityAssessment], limit: int = 15) -> str:
    if not scan.pokemon:
        return ("- No individual Pokémon were identified with enough evidence to "
                "single any out.")
    highlights = top_highlights(assessments, limit=limit)
    lines: list[str] = []
    for assessment in highlights:
        entry = assessment.entry
        bits = [f"Rarity: {assessment.label.value}"]
        if assessment.reasons:
            bits.append("; ".join(assessment.reasons))
        line = f"- **{entry.species}** — " + ". ".join(bits) + "."
        if entry.cp is not None:
            line += f" CP {entry.cp:,}."
        if entry.iv_percent is not None:
            line += f" IV {entry.iv_percent:g}%."
        lines.append(line)
    if not lines:
        lines.append("- Nothing identified reached the Rare tier; the identified "
                     "collection matches commonly available Pokémon.")
    backgrounds = [p for p in scan.pokemon if p.background]
    moves = [p for p in scan.pokemon if p.legacy_move]
    costumes = [p for p in scan.pokemon if p.costume]
    if backgrounds:
        lines.append("")
        lines.append("Special backgrounds: " + ", ".join(
            f"{p.species} ({p.background})" for p in backgrounds[:10]))
    if moves:
        lines.append("Legacy moves: " + ", ".join(
            f"{p.species} ({p.legacy_move})" for p in moves[:10]))
    if costumes:
        lines.append("Costumes: " + ", ".join(
            f"{p.species} ({p.costume})" for p in costumes[:10]))
    return "\n".join(lines)


def _strengths(scan: AccountScan, classification: ClassificationResult) -> str:
    strong = sorted(
        (s for s in classification.observed_signals() if s.ratio and s.ratio >= 0.4),
        key=lambda s: s.weight * s.ratio, reverse=True,
    )
    if not strong:
        return ("- No area was visible strongly enough to call out as a clear "
                "strength. Additional screenshots may reveal one.")
    return "\n".join(f"- {s.name}: {s.detail}" for s in strong[:8])


def _weaknesses(scan: AccountScan, classification: ClassificationResult) -> list[str]:
    weak: list[str] = []
    for s in classification.observed_signals():
        if s.ratio is not None and s.ratio < 0.2 and s.weight >= 1.5:
            weak.append(f"Limited {s.name.lower()} ({s.detail}).")
    for name in classification.to_dict()["missing_signals"]:
        weak.append(f"{name}: not visible in the supplied screenshots.")
    if scan.warnings:
        weak.append("Screenshot issues: " + "; ".join(scan.warnings[:3]))
    if not weak:
        weak.append("No significant gaps identified from the supplied evidence.")
    return weak


def _final_description(
    scan: AccountScan, classification: ClassificationResult, narrative: str | None
) -> str:
    if narrative:
        return narrative.strip()
    f, c = scan.facts, scan.counts()
    level = f"level {f.level}" if f.level is not None else "an unknown trainer level"
    parts = [
        f"This is a {classification.account_class.value} account at {level}.",
        f"The supplied evidence identifies {c['total_identified']} Pokémon, including "
        f"{c['shiny']} shiny, {c['legendary']} legendary, {c['mythical']} mythical, "
        f"{c['hundo']} hundo and {c['shundo']} shundo.",
    ]
    if c["total_identified"] == 0:
        parts.append("No Pokémon could be identified, so the collection cannot yet "
                     "be described.")
    return " ".join(parts)


def _confidence_line(classification: ClassificationResult, confidence: Confidence) -> str:
    return (
        f"CONFIDENCE: {confidence.value}\n\n"
        f"Classification score {classification.score:.2f} against the observed "
        f"maximum, with {classification.coverage:.2f} of all signals visible. "
        + " ".join(classification.reasons)
    )


_NUMBER_RE = re.compile(r"\b\d[\d,]{0,9}\b")


def numeric_claims_not_in_scan(narrative: str, scan: AccountScan) -> list[str]:
    """Flag integers in model prose the scan cannot support."""
    if not narrative:
        return []
    allowed: set[int] = set()
    f = scan.facts
    for value in (f.level, f.xp, f.total_caught, f.pokedex_caught, f.pokedex_seen,
                  f.stardust, f.pokecoins, f.rare_candy, f.rare_candy_xl,
                  f.pokemon_storage, f.item_storage, f.pokemon_storage_used,
                  f.item_storage_used):
        if value is not None:
            allowed.add(int(value))
    allowed.update(int(v) for v in scan.counts().values())
    allowed.update(int(p.cp) for p in scan.pokemon if p.cp is not None)
    # IV percentages are real scan facts ("100% IV"), so they are supported too.
    allowed.update(int(p.iv_percent) for p in scan.pokemon if p.iv_percent is not None)

    flags: list[str] = []
    for match in _NUMBER_RE.finditer(narrative):
        token = match.group(0).replace(",", "")
        try:
            number = int(token)
        except ValueError:
            continue
        if number <= 12:
            continue
        if number in allowed:
            continue
        flags.append(token)
    seen: set[str] = set()
    out: list[str] = []
    for token in flags:
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _parse_sections(text: str) -> dict[str, str]:
    """Split model prose into the spec's sections by heading."""
    sections: dict[str, str] = {}
    if not text:
        return sections
    current: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        upper = stripped.lstrip("#").strip().upper()
        matched = next((s for s in SECTION_ORDER if upper.startswith(s)), None)
        if matched or upper.startswith("ACCOUNT CLASSIFICATION"):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = matched
            buffer = []
            continue
        if current:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    return sections


def build_report(
    scan: AccountScan,
    assessments: list[RarityAssessment],
    classification: ClassificationResult,
    *,
    narrative: str | None = None,
) -> ReportBundle:
    warnings = list(scan.warnings)
    narrative_sections: dict[str, str] = {}
    if narrative:
        narrative_sections = _parse_sections(narrative)
        unsupported = numeric_claims_not_in_scan(narrative, scan)
        if unsupported:
            warnings.append(
                "AI narrative contained numbers not supported by the scan and they "
                "were not used in the report tables: " + ", ".join(unsupported)
            )

    sections: dict[str, str] = {}
    sections["ACCOUNT OVERVIEW"] = _overview(scan)
    sections["COLLECTION ANALYSIS"] = _collection(scan)
    sections["RESOURCE ANALYSIS"] = _resources(scan)
    sections["RARE ASSETS"] = (
        narrative_sections.get("RARE ASSETS") or _rare_assets(scan, assessments)
    )
    sections["ACCOUNT STRENGTHS"] = (
        narrative_sections.get("ACCOUNT STRENGTHS") or _strengths(scan, classification)
    )
    weaknesses = _weaknesses(scan, classification)
    sections["ACCOUNT WEAKNESSES"] = (
        narrative_sections.get("ACCOUNT WEAKNESSES")
        or "\n".join(f"- {w}" for w in weaknesses)
    )
    sections["FINAL DESCRIPTION"] = _final_description(
        scan, classification, narrative_sections.get("FINAL DESCRIPTION")
    )
    confidence = classification.confidence
    sections["CONFIDENCE"] = (
        narrative_sections.get("CONFIDENCE") or _confidence_line(classification, confidence)
    )

    markdown = _render(sections, classification)
    return ReportBundle(
        classification=classification.account_class.value,
        markdown=markdown,
        sections=sections,
        warnings=warnings,
        missing_information=weaknesses,
        narrative_source="gemini" if narrative_sections else "deterministic",
        confidence=confidence,
    )


def _render(sections: dict[str, str], classification: ClassificationResult) -> str:
    parts = [
        f"ACCOUNT CLASSIFICATION: {classification.account_class.value}",
        "",
    ]
    for name in SECTION_ORDER:
        body = sections.get(name, "").strip()
        parts.append(name)
        parts.append("")
        parts.append(body if body else NOT_VISIBLE)
        parts.append("")
    return "\n".join(parts).strip() + "\n"
