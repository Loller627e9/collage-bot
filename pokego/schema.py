"""Account investigation data model.

Every value carries an evidence status so the classifier and the report can tell
"the screenshot showed zero" apart from "the screenshot did not show this".

This distinction is the whole point of the module. The investigation spec says
"do not assume missing information means zero", which means a plain ``0`` is not
enough: we need ``None`` (not visible) versus ``0`` (visible and empty).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class Evidence(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    NOT_VISIBLE = "NOT_VISIBLE"

    @classmethod
    def coerce(cls, value: Any) -> "Evidence":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.NOT_VISIBLE
        token = str(value).strip().upper().replace(" ", "_").replace("-", "_")
        return {
            "VERIFIED": cls.VERIFIED,
            "CLEAR": cls.VERIFIED,
            "PARTIALLY_VERIFIED": cls.PARTIALLY_VERIFIED,
            "PARTIAL": cls.PARTIALLY_VERIFIED,
            "UNVERIFIED": cls.UNVERIFIED,
            "NOT_VISIBLE": cls.NOT_VISIBLE,
            "UNKNOWN": cls.NOT_VISIBLE,
        }.get(token, cls.NOT_VISIBLE)


class AccountClass(str, Enum):
    MINI = "MINI"
    MID = "MID"
    STACKED = "STACKED"

    @property
    def rank(self) -> int:
        return _CLASS_RANK[self]


_CLASS_RANK = {AccountClass.MINI: 0, AccountClass.MID: 1, AccountClass.STACKED: 2}


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def rank(self) -> int:
        return _CONF_RANK[self]


_CONF_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


class RarityLabel(str, Enum):
    COMMON = "Common"
    UNCOMMON = "Uncommon"
    RARE = "Rare"
    VERY_RARE = "Very Rare"
    EXTREMELY_RARE = "Extremely Rare"

    @property
    def rank(self) -> int:
        return _RARITY_RANK[self]


_RARITY_RANK = {
    RarityLabel.COMMON: 0,
    RarityLabel.UNCOMMON: 1,
    RarityLabel.RARE: 2,
    RarityLabel.VERY_RARE: 3,
    RarityLabel.EXTREMELY_RARE: 4,
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def _int(value: Any) -> int | None:
    """Parse an integer that may arrive as '12,345' or '1 234' or a float."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    cleaned = str(value).strip().replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "yes", "y", "1", "visible", "present"}


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in out:
            out.append(text)
    return out


@dataclass
class PokemonEntry:
    """One identified Pokémon. ``None`` = not visible; ``False`` = visible and absent."""

    species: str
    cp: int | None = None
    iv_percent: float | None = None
    shiny: bool = False
    lucky: bool = False
    shadow: bool = False
    purified: bool = False
    costume: str | None = None
    background: str | None = None
    legacy_move: str | None = None
    dynamax: bool = False
    gigantamax: bool = False
    mega: bool = False
    legendary: bool | None = None
    mythical: bool | None = None
    ultra_beast: bool | None = None
    regional: bool | None = None
    xxl: bool = False
    xxs: bool = False
    form: str | None = None
    notes: str | None = None
    evidence: Evidence = Evidence.PARTIALLY_VERIFIED

    def __post_init__(self) -> None:
        self.species = (_text(self.species) or "").strip()
        self.cp = _int(self.cp)
        if self.iv_percent is not None:
            try:
                iv = float(str(self.iv_percent).replace("%", "").strip())
                self.iv_percent = round(iv, 1) if 0 <= iv <= 100 else None
            except ValueError:
                self.iv_percent = None
        self.costume = _text(self.costume)
        self.background = _text(self.background)
        self.legacy_move = _text(self.legacy_move)
        self.form = _text(self.form)
        self.notes = _text(self.notes)
        for attr in ("shiny", "lucky", "shadow", "purified", "dynamax",
                     "gigantamax", "mega", "xxl", "xxs"):
            setattr(self, attr, _bool(getattr(self, attr)))
        self.evidence = Evidence.coerce(self.evidence)

    @property
    def species_key(self) -> str:
        return " ".join(self.species.lower().split())

    @property
    def is_hundo(self) -> bool:
        return self.iv_percent is not None and self.iv_percent >= 100.0

    @property
    def is_nundo(self) -> bool:
        return self.iv_percent is not None and self.iv_percent <= 0.0

    @property
    def is_shundo(self) -> bool:
        """Shiny hundo - the 'shundo' collectors chase."""
        return self.is_hundo and self.shiny

    def dedupe_key(self) -> tuple:
        return (
            self.species_key, self.cp, self.iv_percent, self.shiny, self.lucky,
            self.shadow, self.purified, (self.costume or "").lower(),
            (self.background or "").lower(), (self.form or "").lower(),
        )

    def merge_missing_from(self, other: "PokemonEntry") -> None:
        for attr in ("cp", "iv_percent", "costume", "background", "legacy_move",
                     "form", "notes"):
            if getattr(self, attr) in (None, "") and getattr(other, attr) not in (None, ""):
                setattr(self, attr, getattr(other, attr))
        for attr in ("shiny", "lucky", "shadow", "purified", "dynamax",
                     "gigantamax", "mega", "xxl", "xxs"):
            if not getattr(self, attr) and getattr(other, attr):
                setattr(self, attr, True)
        for attr in ("legendary", "mythical", "ultra_beast", "regional"):
            if getattr(self, attr) is None and getattr(other, attr) is not None:
                setattr(self, attr, getattr(other, attr))
        if self.evidence is not Evidence.VERIFIED and other.evidence is Evidence.VERIFIED:
            self.evidence = Evidence.VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "species": self.species, "cp": self.cp, "iv_percent": self.iv_percent,
            "shiny": self.shiny, "lucky": self.lucky, "shadow": self.shadow,
            "purified": self.purified, "costume": self.costume,
            "background": self.background, "legacy_move": self.legacy_move,
            "dynamax": self.dynamax, "gigantamax": self.gigantamax, "mega": self.mega,
            "legendary": self.legendary, "mythical": self.mythical,
            "ultra_beast": self.ultra_beast, "regional": self.regional,
            "xxl": self.xxl, "xxs": self.xxs, "form": self.form,
            "notes": self.notes, "evidence": self.evidence.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PokemonEntry":
        if not isinstance(data, dict):
            raise ValueError("pokemon entry must be an object")
        return cls(
            species=data.get("species") or data.get("name") or "",
            cp=data.get("cp"), iv_percent=data.get("iv_percent", data.get("iv")),
            shiny=data.get("shiny"), lucky=data.get("lucky"),
            shadow=data.get("shadow"), purified=data.get("purified"),
            costume=data.get("costume"), background=data.get("background"),
            legacy_move=data.get("legacy_move"), dynamax=data.get("dynamax"),
            gigantamax=data.get("gigantamax"), mega=data.get("mega"),
            legendary=data.get("legendary"), mythical=data.get("mythical"),
            ultra_beast=data.get("ultra_beast"), regional=data.get("regional"),
            xxl=data.get("xxl"), xxs=data.get("xxs"), form=data.get("form"),
            notes=data.get("notes"),
            evidence=data.get("evidence", Evidence.PARTIALLY_VERIFIED),
        )


@dataclass
class AccountFacts:
    """Everything the scanner could read. Nothing here is a judgement."""

    # Identity / progression
    trainer_name: str | None = None
    level: int | None = None
    xp: int | None = None
    team: str | None = None
    total_caught: int | None = None
    pokedex_caught: int | None = None
    pokedex_seen: int | None = None
    account_age_note: str | None = None

    # Resources
    stardust: int | None = None
    pokecoins: int | None = None
    candy_notes: str | None = None
    xl_candy_notes: str | None = None
    rare_candy: int | None = None
    rare_candy_xl: int | None = None
    pokemon_storage: int | None = None
    pokemon_storage_used: int | None = None
    item_storage: int | None = None
    item_storage_used: int | None = None
    item_inventory_notes: str | None = None

    # Achievements
    medals: list[str] = field(default_factory=list)
    raid_history_notes: str | None = None
    pvp_notes: str | None = None
    special_research_notes: str | None = None

    evidence: Evidence = Evidence.PARTIALLY_VERIFIED

    def __post_init__(self) -> None:
        for attr in ("level", "xp", "total_caught", "pokedex_caught", "pokedex_seen",
                     "stardust", "pokecoins", "rare_candy", "rare_candy_xl",
                     "pokemon_storage", "pokemon_storage_used", "item_storage",
                     "item_storage_used"):
            setattr(self, attr, _int(getattr(self, attr)))
        for attr in ("trainer_name", "team", "account_age_note", "candy_notes",
                     "xl_candy_notes", "item_inventory_notes", "raid_history_notes",
                     "pvp_notes", "special_research_notes"):
            setattr(self, attr, _text(getattr(self, attr)))
        self.medals = _text_list(self.medals)
        self.evidence = Evidence.coerce(self.evidence)

    def merge_missing_from(self, other: "AccountFacts") -> None:
        for attr in ("trainer_name", "level", "xp", "team", "total_caught",
                     "pokedex_caught", "pokedex_seen", "account_age_note",
                     "stardust", "pokecoins", "candy_notes", "xl_candy_notes",
                     "rare_candy", "rare_candy_xl", "pokemon_storage",
                     "pokemon_storage_used", "item_storage", "item_storage_used",
                     "item_inventory_notes", "raid_history_notes", "pvp_notes",
                     "special_research_notes"):
            if getattr(self, attr) in (None, "") and getattr(other, attr) not in (None, ""):
                setattr(self, attr, getattr(other, attr))
        for medal in other.medals:
            if medal not in self.medals:
                self.medals.append(medal)
        if self.evidence is not Evidence.VERIFIED and other.evidence is Evidence.VERIFIED:
            self.evidence = Evidence.VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "trainer_name": self.trainer_name, "level": self.level, "xp": self.xp,
            "team": self.team, "total_caught": self.total_caught,
            "pokedex_caught": self.pokedex_caught, "pokedex_seen": self.pokedex_seen,
            "account_age_note": self.account_age_note, "stardust": self.stardust,
            "pokecoins": self.pokecoins, "candy_notes": self.candy_notes,
            "xl_candy_notes": self.xl_candy_notes, "rare_candy": self.rare_candy,
            "rare_candy_xl": self.rare_candy_xl,
            "pokemon_storage": self.pokemon_storage,
            "pokemon_storage_used": self.pokemon_storage_used,
            "item_storage": self.item_storage,
            "item_storage_used": self.item_storage_used,
            "item_inventory_notes": self.item_inventory_notes,
            "medals": list(self.medals),
            "raid_history_notes": self.raid_history_notes,
            "pvp_notes": self.pvp_notes,
            "special_research_notes": self.special_research_notes,
            "evidence": self.evidence.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountFacts":
        data = data or {}
        return cls(
            trainer_name=data.get("trainer_name"), level=data.get("level"),
            xp=data.get("xp"), team=data.get("team"),
            total_caught=data.get("total_caught"),
            pokedex_caught=data.get("pokedex_caught"),
            pokedex_seen=data.get("pokedex_seen"),
            account_age_note=data.get("account_age_note"),
            stardust=data.get("stardust"), pokecoins=data.get("pokecoins"),
            candy_notes=data.get("candy_notes"), xl_candy_notes=data.get("xl_candy_notes"),
            rare_candy=data.get("rare_candy"), rare_candy_xl=data.get("rare_candy_xl"),
            pokemon_storage=data.get("pokemon_storage"),
            pokemon_storage_used=data.get("pokemon_storage_used"),
            item_storage=data.get("item_storage"),
            item_storage_used=data.get("item_storage_used"),
            item_inventory_notes=data.get("item_inventory_notes"),
            medals=list(data.get("medals") or []),
            raid_history_notes=data.get("raid_history_notes"),
            pvp_notes=data.get("pvp_notes"),
            special_research_notes=data.get("special_research_notes"),
            evidence=data.get("evidence", Evidence.PARTIALLY_VERIFIED),
        )


@dataclass
class AccountScan:
    """Scanner output: facts plus the collection, no judgements."""

    facts: AccountFacts = field(default_factory=AccountFacts)
    pokemon: list[PokemonEntry] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    screen_types: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_pokemon(self, entry: PokemonEntry) -> bool:
        """Add a Pokémon, merging an identical one instead of double counting."""
        if not entry.species:
            return False
        key = entry.dedupe_key()
        for existing in self.pokemon:
            if existing.dedupe_key() == key:
                existing.merge_missing_from(entry)
                return False
        if entry.cp is not None:
            for existing in self.pokemon:
                if (existing.species_key, existing.cp) == (entry.species_key, entry.cp):
                    existing.merge_missing_from(entry)
                    return False
        self.pokemon.append(entry)
        return True

    def merge(self, other: "AccountScan") -> None:
        self.facts.merge_missing_from(other.facts)
        for entry in other.pokemon:
            self.add_pokemon(entry)
        for name in other.screenshots:
            if name not in self.screenshots:
                self.screenshots.append(name)
        for kind in other.screen_types:
            if kind not in self.screen_types:
                self.screen_types.append(kind)
        for warning in other.warnings:
            if warning not in self.warnings:
                self.warnings.append(warning)

    def counts(self) -> dict[str, int]:
        pokemon = self.pokemon
        return {
            "total_identified": len(pokemon),
            "shiny": sum(1 for p in pokemon if p.shiny),
            "legendary": sum(1 for p in pokemon if p.legendary),
            "mythical": sum(1 for p in pokemon if p.mythical),
            "ultra_beast": sum(1 for p in pokemon if p.ultra_beast),
            "regional": sum(1 for p in pokemon if p.regional),
            "costume": sum(1 for p in pokemon if p.costume),
            "background": sum(1 for p in pokemon if p.background),
            "hundo": sum(1 for p in pokemon if p.is_hundo),
            "shundo": sum(1 for p in pokemon if p.is_shundo),
            "legacy_move": sum(1 for p in pokemon if p.legacy_move),
            "lucky": sum(1 for p in pokemon if p.lucky),
            "shadow": sum(1 for p in pokemon if p.shadow),
            "purified": sum(1 for p in pokemon if p.purified),
            "dynamax": sum(1 for p in pokemon if p.dynamax),
            "gigantamax": sum(1 for p in pokemon if p.gigantamax),
            "mega": sum(1 for p in pokemon if p.mega),
            "xxl": sum(1 for p in pokemon if p.xxl),
            "xxs": sum(1 for p in pokemon if p.xxs),
            "shiny_legendary": sum(1 for p in pokemon if p.shiny and p.legendary),
            "shiny_mythical": sum(1 for p in pokemon if p.shiny and p.mythical),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": self.facts.to_dict(),
            "pokemon": [p.to_dict() for p in self.pokemon],
            "counts": self.counts(),
            "screenshots": list(self.screenshots),
            "screen_types": list(self.screen_types),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountScan":
        data = data or {}
        scan = cls(
            facts=AccountFacts.from_dict(data.get("facts") or data.get("trainer") or {}),
            screenshots=list(data.get("screenshots") or []),
            screen_types=list(data.get("screen_types") or []),
            warnings=list(data.get("warnings") or []),
        )
        for raw in data.get("pokemon") or []:
            try:
                scan.add_pokemon(PokemonEntry.from_dict(raw))
            except ValueError:
                continue
        return scan


def merge_scans(scans: Iterable[AccountScan]) -> AccountScan:
    merged = AccountScan()
    for scan in scans:
        merged.merge(scan)
    return merged
