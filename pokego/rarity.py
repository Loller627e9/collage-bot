"""Deterministic rarity evaluation.

The Investigator model is *not* trusted to decide rarity from memory. Instead it
reports attributes, and this module applies explicit, auditable rules on top of
a curated species dataset. That keeps rarity labels reproducible and prevents
the classic failure mode of inflating every shiny into "extremely rare".

The dataset below is a curated snapshot of widely documented Pokémon GO facts
(which species are Legendary / Mythical / Ultra Beast / regional, and which
species received a Community Day). It is intentionally plain data so it can be
corrected or extended without touching logic. Availability changes over time, so
each assessment separates *historical* rarity from *current* availability.

Sources for the classification categories:
  - Niantic Pokémon GO help / support pages (Legendary & Mythical Pokémon)
  - Official Pokémon GO blog (Community Day announcements)
This file is a heuristic aid, not an authoritative reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import Evidence, PokemonEntry, RarityLabel

# --- Curated species data -------------------------------------------------

LEGENDARY_SPECIES: frozenset[str] = frozenset(
    s.lower()
    for s in [
        "Articuno", "Zapdos", "Moltres", "Mewtwo", "Raikou", "Entei", "Suicune",
        "Lugia", "Ho-Oh", "Regirock", "Regice", "Registeel", "Latias", "Latios",
        "Kyogre", "Groudon", "Rayquaza", "Uxie", "Mesprit", "Azelf", "Dialga",
        "Palkia", "Heatran", "Regigigas", "Giratina", "Cresselia", "Cobalion",
        "Terrakion", "Virizion", "Tornadus", "Thundurus", "Reshiram", "Zekrom",
        "Landorus", "Kyurem", "Xerneas", "Yveltal", "Zygarde", "Tapu Koko",
        "Tapu Lele", "Tapu Bulu", "Tapu Fini", "Cosmog", "Cosmoem", "Solgaleo",
        "Lunala", "Necrozma", "Zacian", "Zamazenta", "Eternatus", "Kubfu",
        "Urshifu", "Regieleki", "Regidrago", "Glastrier", "Spectrier", "Calyrex",
        "Enamorus", "Wo-Chien", "Chien-Pao", "Ting-Lu", "Chi-Yu", "Koraidon",
        "Miraidon", "Ogerpon", "Terapagos",
    ]
)

MYTHICAL_SPECIES: frozenset[str] = frozenset(
    s.lower()
    for s in [
        "Mew", "Celebi", "Jirachi", "Deoxys", "Phione", "Manaphy", "Darkrai",
        "Shaymin", "Arceus", "Victini", "Keldeo", "Meloetta", "Genesect", "Diancie",
        "Hoopa", "Volcanion", "Magearna", "Marshadow", "Zeraora", "Meltan",
        "Melmetal", "Zarude", "Pecharunt",
    ]
)

ULTRA_BEAST_SPECIES: frozenset[str] = frozenset(
    s.lower()
    for s in [
        "Nihilego", "Buzzwole", "Pheromosa", "Xurkitree", "Celesteela", "Kartana",
        "Guzzlord", "Poipole", "Naganadel", "Stakataka", "Blacephalon",
    ]
)

# Species that spawn commonly in the wild almost everywhere, so a non-shiny
# specimen is genuinely ordinary.
COMMON_SPECIES: frozenset[str] = frozenset(
    s.lower()
    for s in [
        "Pidgey", "Rattata", "Raticate", "Caterpie", "Weedle", "Spearow",
        "Pikachu", "Sandshrew", "Nidoran♀", "Nidoran♂", "Zubat", "Oddish",
        "Paras", "Venonat", "Diglett", "Meowth", "Psyduck", "Mankey", "Growlithe",
        "Poliwag", "Abra", "Machop", "Bellsprout", "Tentacool", "Geodude",
        "Ponyta", "Slowpoke", "Magnemite", "Doduo", "Seel", "Grimer", "Shellder",
        "Gastly", "Drowzee", "Krabby", "Voltorb", "Exeggcute", "Cubone",
        "Magikarp", "Sentret", "Hoothoot", "Ledyba", "Spinarak", "Chinchou",
        "Natu", "Mareep", "Hoppip", "Sunkern", "Wooper", "Snubbull", "Houndour",
        "Poochyena", "Zigzagoon", "Wurmple", "Lotad", "Seedot", "Taillow",
        "Wingull", "Ralts", "Surskit", "Shroomish", "Slakoth", "Whismur",
        "Makuhita", "Aron", "Meditite", "Electrike", "Gulpin", "Carvanha",
        "Numel", "Spoink", "Swablu", "Barboach", "Corphish", "Baltoy",
        "Lileep", "Anorith", "Starly", "Bidoof", "Kricketot", "Shinx", "Budew",
        "Burmy", "Combee", "Pachirisu", "Buizel", "Cherubi", "Shellos",
        "Drifloon", "Buneary", "Glameow", "Stunky", "Bronzor", "Chatot", "Spiritomb",
    ]
)

REGIONAL_SPECIES: frozenset[str] = frozenset(
    s.lower()
    for s in [
        "Farfetch'd", "Kangaskhan", "Mr. Mime", "Tauros", "Heracross", "Corsola",
        "Miltank", "Illumise", "Volbeat", "Torkoal", "Zangoose", "Seviper",
        "Lunatone", "Solrock", "Tropius", "Relicanth", "Pachirisu", "Chatot",
        "Carnivine", "Sawk", "Throh", "Maractus", "Bouffalant", "Klefki",
        "Comfey", "Hawlucha", "Oricorio", "Passimian", "Turtonator", "Kleavor",
        "Clauncher", "Skrelp",
    ]
)

# Species that received a Community Day (or Community Day Classic), which
# historically made their shiny form broadly available to active players.
COMMUNITY_DAY_SPECIES: frozenset[str] = frozenset(
    s.lower()
    for s in [
        "Pikachu", "Dratini", "Bulbasaur", "Mareep", "Charmander", "Larvitar",
        "Squirtle", "Eevee", "Chikorita", "Beldum", "Cyndaquil", "Totodile",
        "Bagon", "Swablu", "Mudkip", "Ralts", "Slakoth", "Turtwig", "Torchic",
        "Trapinch", "Treecko", "Chimchar", "Piplup", "Seedot", "Abra", "Rhyhorn",
        "Gastly", "Weedle", "Magikarp", "Porygon", "Swinub", "Snivy", "Tepig",
        "Oshawott", "Fletchling", "Roselia", "Gible", "Machop", "Duskull",
        "Shinx", "Timburr", "Deino", "Starly", "Litwick", "Chespin", "Fennekin",
        "Froakie", "Togetic", "Sandshrew", "Alolan Sandshrew", "Bagon",
        "Rowlet", "Litten", "Popplio", "Teddiursa", "Galarian Zigzagoon",
        "Hoppip", "Stufful", "Alolan Geodude", "Roggenrola", "Eevee",
        "Dratini", "Bounsweet", "Grubbin", "Larvitar", "Sableye", "Noibat",
        "Slowpoke", "Karrablast", "Shelmet", "Vulpix", "Alolan Vulpix", "Chansey",
        "Chikorita", "Cyndaquil", "Totodile", "Grookey", "Scorbunny", "Sobble",
        "Mankey", "Hatenna", "Poliwag", "Poochyena", "Goomy", "Sprigatito",
    ]
)

# Costume / event-form keywords. A shiny *and* costumed specimen is far scarcer
# than a plain shiny, because the costumed form is time-limited.
COSTUME_KEYWORDS: tuple[str, ...] = (
    "party hat", "santa", "witch hat", "witch", "halloween", "cake", "flower",
    "crown", "top hat", "bow", "ribbon", "sunglasses", "bandana", "gift",
    "christmas", "new year", "summer", "festival", "explorer", "detective",
    "avatar", "mimic", "clone", "armored", "team leader", "sunglass",
)

# Background keywords that are widely recognised as limited/event backgrounds.
RARE_BACKGROUND_KEYWORDS: tuple[str, ...] = (
    "special", "event", "location", "city", "region", "seasonal", "legendary",
    "raid", "safari", "go fest", "gofest", "taipei", "london", "osaka",
    "new york", "sendai", "madrid", "paris", "vegas", "limited", "research",
)


def species_flags(species: str) -> dict[str, bool | None]:
    """Look up what the curated dataset knows about a species.

    Returns ``None`` for a category when the dataset does not list the species
    at all, so callers can distinguish "known not legendary" from "unknown".
    """
    key = " ".join((species or "").lower().split())
    if not key:
        return {}
    known_species = key in (
        LEGENDARY_SPECIES
        | MYTHICAL_SPECIES
        | ULTRA_BEAST_SPECIES
        | COMMON_SPECIES
        | REGIONAL_SPECIES
    )
    return {
        "legendary": True if key in LEGENDARY_SPECIES else (False if known_species else None),
        "mythical": True if key in MYTHICAL_SPECIES else (False if known_species else None),
        "ultra_beast": True if key in ULTRA_BEAST_SPECIES else (False if known_species else None),
        "common": True if key in COMMON_SPECIES else (False if known_species else None),
        "regional": True if key in REGIONAL_SPECIES else (False if known_species else None),
        "community_day": key in COMMUNITY_DAY_SPECIES,
    }


@dataclass
class RarityAssessment:
    entry: PokemonEntry
    label: RarityLabel
    reasons: list[str] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)
    historic_note: str | None = None
    evidence: Evidence = Evidence.PARTIALLY_VERIFIED

    def to_dict(self) -> dict:
        return {
            "species": self.entry.species,
            "label": self.label.value,
            "rank": self.label.rank,
            "reasons": list(self.reasons),
            "flags": dict(self.flags),
            "historic_note": self.historic_note,
            "evidence": self.evidence.value,
        }


def _matches_any(text: str | None, keywords: tuple[str, ...]) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for keyword in keywords:
        if keyword in lowered:
            return keyword
    return None


def _bump(label: RarityLabel, steps: int) -> RarityLabel:
    order = [
        RarityLabel.COMMON,
        RarityLabel.UNCOMMON,
        RarityLabel.RARE,
        RarityLabel.VERY_RARE,
        RarityLabel.EXTREMELY_RARE,
    ]
    index = min(max(order.index(label) + steps, 0), len(order) - 1)
    return order[index]


def assess(entry: PokemonEntry) -> RarityAssessment:
    """Assign a rarity label to one Pokémon using explicit rules."""
    flags_lookup = species_flags(entry.species)
    reasons: list[str] = []
    historic_note: str | None = None

    legendary = entry.legendary if entry.legendary is not None else bool(flags_lookup.get("legendary"))
    mythical = entry.mythical if entry.mythical is not None else bool(flags_lookup.get("mythical"))
    ultra_beast = bool(flags_lookup.get("ultra_beast"))
    is_common = bool(flags_lookup.get("common"))
    community_day = bool(flags_lookup.get("community_day"))
    regional = bool(flags_lookup.get("regional"))

    # Base tier from species class alone.
    if mythical:
        label = RarityLabel.RARE
        reasons.append("Mythical species")
    elif legendary:
        label = RarityLabel.RARE
        reasons.append("Legendary species")
    elif ultra_beast:
        label = RarityLabel.RARE
        reasons.append("Ultra Beast species")
    elif regional:
        label = RarityLabel.UNCOMMON
        reasons.append("Regional species")
    elif is_common:
        label = RarityLabel.COMMON
        reasons.append("Commonly available species")
    else:
        label = RarityLabel.UNCOMMON
        reasons.append("Species not in the common-spawn list")

    if community_day:
        flags_lookup["community_day"] = True
        historic_note = (
            "This species had a Community Day, so its shiny form was widely "
            "obtainable by active players during that event."
        )

    # Attribute modifiers. Each is gated on evidence: a flag we never saw in a
    # screenshot cannot raise the tier.
    if entry.shiny:
        if legendary or mythical:
            label = _bump(label, 2)
            reasons.append("Shiny Legendary/Mythical")
        elif community_day and not (entry.costume or entry.background or entry.dynamax):
            # Community Day shinies are common among active players.
            reasons.append("Shiny from a Community Day species")
        else:
            label = _bump(label, 1)
            reasons.append("Shiny")

    if entry.costume:
        label = _bump(label, 1)
        reasons.append(f"Costume form ({entry.costume})")
        if entry.shiny:
            label = _bump(label, 1)
            reasons.append("Shiny costume (time-limited form)")

    background_keyword = _matches_any(entry.background, RARE_BACKGROUND_KEYWORDS)
    if entry.background:
        if background_keyword:
            label = _bump(label, 1)
            reasons.append(f"Special background ({entry.background})")
        else:
            reasons.append(f"Background recorded ({entry.background})")

    if entry.gigantamax:
        label = _bump(label, 1)
        reasons.append("Gigantamax capable")
    elif entry.dynamax:
        reasons.append("Dynamax capable")

    if entry.is_hundo:
        label = _bump(label, 1)
        reasons.append("Hundo (100% IV)")
        if entry.shiny:
            label = _bump(label, 1)
            reasons.append("Shundo (shiny 100% IV)")
    if entry.is_nundo:
        reasons.append("Nundo (0% IV)")

    if entry.legacy_move:
        label = _bump(label, 1)
        reasons.append(f"Legacy/exclusive move ({entry.legacy_move})")

    if entry.lucky:
        reasons.append("Lucky trade")
    if entry.purified:
        reasons.append("Purified (lower rarity than an un-purified shadow)")
    elif entry.shadow:
        label = _bump(label, 1)
        reasons.append("Shadow")

    if entry.mega:
        reasons.append("Mega Evolution recorded")

    # The dataset can only speak to species class; say so rather than implying
    # we verified event participation.
    evidence = entry.evidence
    if all(v is None for v in flags_lookup.values()):
        historic_note = historic_note or (
            "Species not in the curated dataset; rarity judged from reported "
            "attributes only."
        )

    return RarityAssessment(
        entry=entry,
        label=label,
        reasons=reasons,
        flags={k: bool(v) for k, v in flags_lookup.items() if v is not None},
        historic_note=historic_note,
        evidence=evidence,
    )


def assess_collection(pokemon: list[PokemonEntry]) -> list[RarityAssessment]:
    return [assess(entry) for entry in pokemon]


def enrich_missing_flags(pokemon: list[PokemonEntry]) -> None:
    """Fill Legendary/Mythical flags from the dataset *only when unknown*.

    A ``VERIFIED`` screenshot fact always wins; this only helps when the model
    did not report the class at all.
    """
    for entry in pokemon:
        flags = species_flags(entry.species)
        if entry.legendary is None and flags.get("legendary") is not None:
            entry.legendary = flags["legendary"]
        if entry.mythical is None and flags.get("mythical") is not None:
            entry.mythical = flags["mythical"]


def highlight_score(assessment: RarityAssessment) -> int:
    """Sort key for the showcase: rarer first, then more attributes."""
    score = assessment.label.rank * 100
    entry = assessment.entry
    for attr in (
        "shiny",
        "lucky",
        "shadow",
        "gigantamax",
        "dynamax",
        "mega",
    ):
        if getattr(entry, attr):
            score += 5
    if entry.costume:
        score += 4
    if entry.background:
        score += 3
    if entry.is_hundo:
        score += 6
    if entry.cp:
        score += min(entry.cp // 1000, 5)
    return score


def top_highlights(
    assessments: list[RarityAssessment], limit: int = 12
) -> list[RarityAssessment]:
    ranked = sorted(assessments, key=highlight_score, reverse=True)
    return [a for a in ranked if a.label.rank >= RarityLabel.RARE.rank][:limit]
