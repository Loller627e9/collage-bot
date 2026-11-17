"""Pokémon GO account investigation and classification.

Two functions, deliberately separated so the model cannot invent account facts:

* Account Scanner - reads screenshots, returns structured facts only.
* Deterministic rules engines - classification (MINI/MID/STACKED) and rarity
  labels come from these, never from the model.
* Writer - turns the facts and the deterministic tables into the report and the
  two description types (Eldorado, Auction).
"""

from .schema import (
    AccountClass,
    AccountFacts,
    AccountScan,
    Confidence,
    Evidence,
    PokemonEntry,
    RarityLabel,
    merge_scans,
)
from .classification import ClassificationResult, classify
from .rarity import RarityAssessment, assess, assess_collection
from .report import ReportBundle, build_report
from .descriptions import (
    AUCTION,
    ELDORADO,
    DESCRIPTION_TYPES,
    Description,
    build_description,
)
from .pipeline import InvestigationResult, investigate

__all__ = [
    "AccountClass",
    "AccountFacts",
    "AccountScan",
    "Confidence",
    "Evidence",
    "PokemonEntry",
    "RarityLabel",
    "merge_scans",
    "ClassificationResult",
    "classify",
    "RarityAssessment",
    "assess",
    "assess_collection",
    "ReportBundle",
    "build_report",
    "AUCTION",
    "ELDORADO",
    "DESCRIPTION_TYPES",
    "Description",
    "build_description",
    "InvestigationResult",
    "investigate",
]

__version__ = "0.1.0"
