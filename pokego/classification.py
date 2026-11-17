"""Deterministic MINI / MID / STACKED classification.

Two rules from the spec drive the design:

* "Do not classify accounts using Trainer Level alone." Level is one signal among
  many and is never decisive.
* "Do not assume missing information means zero." A value that was never visible
  is excluded from both the numerator and the denominator, so absent evidence
  neither helps nor hurts the score. The coverage figure records how much of the
  picture we actually saw.

The score blends two things:

* **Progression** - account-wide stats (level, Pokédex, caught, stardust, XP,
  candy, medals) when a profile screen was seen.
* **Collection quality** - a per-Pokémon desirability score, because collection
  value lives in the individual pieces (a shundo, a shiny mythical, a legacy
  move), not in how many categories happened to appear.

Averaging many categories punishes a small-but-excellent sample, so the
collection side is scored as the mean desirability of the identified Pokémon
plus a saturating bonus for the strength of the best few. The collection block is
excluded entirely when no Pokémon were identified, so a missing storage
screenshot cannot read as zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .schema import AccountClass, AccountScan, Confidence, Evidence, PokemonEntry

# Thresholds on the achieved share of the observed maximum.
STACKED_MIN = 0.62
MID_MIN = 0.26

# A class above MINI needs more than one independent observation, so the bot
# never classifies on Trainer Level alone.
MIN_SIGNALS_FOR_MID = 2

# Blend weights between the two halves.
W_PROGRESSION = 0.5
W_COLLECTION = 0.5


@dataclass
class Signal:
    """One weighted classification signal."""

    name: str
    weight: float
    ratio: float | None  # 0..1 achieved share, or None when not observed
    detail: str = ""

    @property
    def observed(self) -> bool:
        return self.ratio is not None


def _sat(count: int | float | None, scale: float) -> float | None:
    """Saturating 0..1 curve. ~0.63 at n == scale, ~0.95 at 3*scale."""
    if count is None:
        return None
    return 1.0 - math.exp(-max(0.0, float(count)) / scale)


def _share(value: int | float | None, full: float) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value) / full))


def _level_ratio(level: int | None) -> float | None:
    if level is None:
        return None
    return max(0.0, min(1.0, (level - 1) / 79.0))


def desirability(entry: PokemonEntry) -> float:
    """0..1 desirability of a single Pokémon, from its observed attributes.

    This is intentionally attribute-driven rather than a lookup on a species
    tier, so a shiny legendary, a shundo or a legacy move carries weight without
    needing an external price or tier list.
    """
    score = 0.0
    if entry.legendary or entry.mythical or entry.ultra_beast:
        score += 0.35
    if entry.shiny:
        score += 0.22
    if entry.is_shundo:
        score += 0.30
    elif entry.is_hundo:
        score += 0.14
    if entry.costume:
        score += 0.12
    if entry.background:
        score += 0.10
    if entry.legacy_move:
        score += 0.12
    if entry.gigantamax:
        score += 0.08
    elif entry.dynamax:
        score += 0.04
    if entry.shadow:
        score += 0.05
    if entry.xxl or entry.xxs:
        score += 0.03
    if entry.regional:
        score += 0.04
    return min(1.0, score)


def collection_quality(pokemon: list[PokemonEntry]) -> float | None:
    """0..1 quality of the identified collection, or None when nothing identified."""
    if not pokemon:
        return None
    scores = sorted((desirability(p) for p in pokemon), reverse=True)
    mean = sum(scores) / len(scores)
    # Strength of the top few: three great pieces should read as strong even if
    # the rest of the visible sample is ordinary.
    top = sum(scores[:5]) / min(len(scores), 5)
    return max(0.0, min(1.0, 0.5 * mean + 0.5 * top))


def compute_signals(scan: AccountScan) -> list[Signal]:
    """Build the signal list. Progression and collection are separate blocks."""
    f = scan.facts
    signals: list[Signal] = []

    signals.append(Signal("Trainer level", 1.5, _level_ratio(f.level),
                          f"level {f.level}" if f.level is not None else "not visible"))
    signals.append(Signal("Pokédex completion", 2.0, _share(f.pokedex_caught, 800),
                          f"{f.pokedex_caught} caught" if f.pokedex_caught is not None else "not visible"))
    signals.append(Signal("Pokémon caught", 1.0, _sat(f.total_caught, 50_000),
                          f"{f.total_caught:,} caught" if f.total_caught is not None else "not visible"))
    signals.append(Signal("Stardust", 2.0, _sat(f.stardust, 8_000_000),
                          f"{f.stardust:,} stardust" if f.stardust is not None else "not visible"))
    signals.append(Signal("XP", 1.0, _sat(f.xp, 100_000_000),
                          f"{f.xp:,} XP" if f.xp is not None else "not visible"))
    signals.append(Signal("Rare Candy XL", 1.5, _sat(f.rare_candy_xl, 300),
                          f"{f.rare_candy_xl:,} rare candy XL" if f.rare_candy_xl is not None else "not visible"))
    # An empty medals list is "not visible", not an observed zero: we cannot tell
    # a trainer with no medals from a screenshot that did not include them.
    signals.append(Signal("Medals", 1.0, _sat(len(f.medals), 20) if f.medals else None,
                          f"{len(f.medals)} medals" if f.medals else "not visible"))

    quality = collection_quality(scan.pokemon)
    signals.append(Signal(
        "Collection quality", 3.0, quality,
        f"mean desirability across {len(scan.pokemon)} identified Pokémon"
        if scan.pokemon else "no Pokémon identified",
    ))
    return signals


def _progression_ratio(scan: AccountScan) -> tuple[float, float, list[Signal]]:
    """(progression ratio, observed weight, signals) for the progression block."""
    progression = [s for s in compute_signals(scan) if s.name != "Collection quality"]
    observed = [s for s in progression if s.observed]
    if not observed:
        return 0.0, 0.0, progression
    weight = sum(s.weight for s in observed)
    achieved = sum(s.weight * s.ratio for s in observed)
    return achieved / weight, weight, progression


def classify(scan: AccountScan) -> "ClassificationResult":
    signals = compute_signals(scan)
    by_name = {s.name: s for s in signals}
    progression_ratio, _pw, _ps = _progression_ratio(scan)
    quality = by_name["Collection quality"].ratio

    # Blend only the halves that were actually observed.
    parts: list[tuple[float, float]] = []
    if _pw:
        parts.append((W_PROGRESSION, progression_ratio))
    if quality is not None:
        parts.append((W_COLLECTION, quality))
    total_w = sum(w for w, _ in parts)
    score = (sum(w * r for w, r in parts) / total_w) if total_w else 0.0

    observed = [s for s in signals if s.observed]
    observed_weight = sum(s.weight for s in observed)
    total_weight = sum(s.weight for s in signals)
    coverage = (observed_weight / total_weight) if total_weight else 0.0

    if score >= STACKED_MIN:
        account_class = AccountClass.STACKED
    elif score >= MID_MIN:
        account_class = AccountClass.MID
    else:
        account_class = AccountClass.MINI

    # The spec defines STACKED by collection depth as well as progression, so a
    # STACKED verdict requires that the collection was actually seen.
    if account_class is AccountClass.STACKED and quality is None:
        account_class = AccountClass.MID

    # Never classify above MINI on a single observation: that is exactly the
    # "Trainer Level alone" trap the spec warns about.
    if account_class is not AccountClass.MINI and len(observed) < MIN_SIGNALS_FOR_MID:
        account_class = AccountClass.MINI

    confidence = _confidence(coverage, observed, scan, quality is not None)
    return ClassificationResult(
        account_class=account_class,
        score=round(score, 3),
        coverage=round(coverage, 3),
        confidence=confidence,
        signals=signals,
        reasons=_reasons(scan, signals, score, coverage),
    )


def _confidence(
    coverage: float, observed: list[Signal], scan: AccountScan, saw_collection: bool
) -> Confidence:
    strong_evidence = scan.facts.evidence is Evidence.VERIFIED and len(scan.screenshots) >= 3
    if coverage >= 0.5 and len(observed) >= 6 and strong_evidence and saw_collection:
        return Confidence.HIGH
    if coverage >= 0.3 and len(observed) >= 3:
        return Confidence.MEDIUM
    return Confidence.LOW


def _reasons(
    scan: AccountScan, signals: list[Signal], score: float, coverage: float
) -> list[str]:
    reasons: list[str] = []
    observed = [s for s in signals if s.observed]
    strong = sorted(
        (s for s in observed if s.ratio is not None and s.ratio >= 0.5),
        key=lambda s: s.weight * s.ratio, reverse=True,
    )
    weak = sorted(
        (s for s in observed if s.ratio is not None and s.ratio < 0.2),
        key=lambda s: s.weight, reverse=True,
    )
    if strong:
        reasons.append("Strong areas: " + ", ".join(s.name for s in strong[:5]))
    if weak:
        reasons.append("Limited areas: " + ", ".join(s.name for s in weak[:5]))
    if scan.pokemon:
        best = max(scan.pokemon, key=desirability)
        reasons.append(
            f"Collection quality is driven by {len(scan.pokemon)} identified "
            f"Pokémon; the strongest is {best.species} "
            f"(desirability {desirability(best):.2f})."
        )
    reasons.append(
        f"Scored {score:.2f} against the observed maximum, with {coverage:.2f} of "
        "all signals visible in the evidence."
    )
    return reasons


@dataclass
class ClassificationResult:
    account_class: AccountClass
    score: float
    coverage: float
    confidence: Confidence
    signals: list[Signal] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def observed_signals(self) -> list[Signal]:
        return [s for s in self.signals if s.observed]

    def missing_signals(self) -> list[Signal]:
        return [s for s in self.signals if not s.observed]

    def to_dict(self) -> dict:
        return {
            "account_class": self.account_class.value,
            "score": self.score,
            "coverage": self.coverage,
            "confidence": self.confidence.value,
            "reasons": list(self.reasons),
            "signals": [
                {"name": s.name, "weight": s.weight, "ratio": s.ratio, "detail": s.detail}
                for s in self.signals
            ],
            "missing_signals": [s.name for s in self.missing_signals()],
        }


def confidence_from_evidence(scan: AccountScan) -> Confidence:
    """Evidence-quality confidence, independent of the classification score."""
    if scan.facts.evidence is Evidence.VERIFIED and len(scan.screenshots) >= 3:
        return Confidence.HIGH
    if scan.facts.evidence in (Evidence.VERIFIED, Evidence.PARTIALLY_VERIFIED):
        return Confidence.MEDIUM
    return Confidence.LOW
