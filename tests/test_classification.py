"""Deterministic classification: MINI / MID / STACKED.

These tests pin the two rules the spec insists on:
  * level alone must never decide the class
  * missing information must never be treated as zero
"""

from __future__ import annotations

from pokego.classification import classify, collection_quality, desirability
from pokego.schema import AccountClass, Confidence, Evidence, PokemonEntry

from .conftest import make_scan


class TestArchetypes:
    def test_strong_account_is_stacked(self, stacked_scan):
        assert classify(stacked_scan).account_class is AccountClass.STACKED

    def test_new_player_is_mini(self, mini_scan):
        assert classify(mini_scan).account_class is AccountClass.MINI

    def test_established_account_is_mid(self):
        scan = make_scan(
            [
                PokemonEntry("Groudon", cp=3800, legendary=True),
                PokemonEntry("Pikachu", cp=800, shiny=True),
                PokemonEntry("Machop", cp=1200, shadow=True),
                PokemonEntry("Snorlax", cp=2900, iv_percent=96),
            ],
            level=44, total_caught=45_000, pokedex_caught=560, stardust=4_500_000,
            rare_candy_xl=140, medals=["Gold Fisherman"] * 14,
            evidence=Evidence.VERIFIED,
        )
        assert classify(scan).account_class is AccountClass.MID


class TestLevelIsNotDecisive:
    def test_high_level_alone_is_not_mid(self):
        """A single observation must never lift an account above MINI."""
        result = classify(make_scan([], level=70, evidence=Evidence.PARTIALLY_VERIFIED))
        assert result.account_class is AccountClass.MINI
        assert result.confidence is Confidence.LOW

    def test_low_level_strong_collection_is_not_forced_mini(self):
        """A great collection matters even at a modest level."""
        scan = make_scan(
            [
                PokemonEntry("Mewtwo", cp=4000, shiny=True, legendary=True,
                             iv_percent=100),
                PokemonEntry("Rayquaza", cp=3900, shiny=True, legendary=True),
                PokemonEntry("Mew", cp=1700, mythical=True, shiny=True),
                PokemonEntry("Pikachu", cp=800, shiny=True, costume="Party Hat"),
                PokemonEntry("Nihilego", cp=3700, ultra_beast=True),
                PokemonEntry("Zacian", cp=4000, legendary=True),
            ],
            level=30, pokedex_caught=400, stardust=6_000_000,
            evidence=Evidence.VERIFIED,
        )
        assert classify(scan).account_class in (AccountClass.MID, AccountClass.STACKED)


class TestMissingIsNotZero:
    def test_no_collection_screenshots_excludes_collection_signals(self):
        scan = make_scan([], level=70, pokedex_caught=700, stardust=15_000_000,
                         evidence=Evidence.VERIFIED)
        result = classify(scan)
        missing = result.to_dict()["missing_signals"]
        assert "Collection quality" in missing
        # A STACKED verdict needs collection evidence, per the spec's definition.
        assert result.account_class is not AccountClass.STACKED

    def test_observed_zero_pokemon_differs_from_no_pokemon(self):
        empty = make_scan([], level=40, evidence=Evidence.VERIFIED)
        assert collection_quality(empty.pokemon) is None

    def test_thin_evidence_lowers_coverage_and_confidence(self):
        thin = classify(make_scan([], level=45, evidence=Evidence.PARTIALLY_VERIFIED))
        rich = classify(make_scan(
            [PokemonEntry("Mewtwo", cp=4000, legendary=True)],
            level=45, stardust=1_000_000, pokedex_caught=300,
            evidence=Evidence.VERIFIED,
        ))
        assert thin.coverage < rich.coverage
        assert thin.confidence.rank <= rich.confidence.rank


class TestDesirability:
    def test_shiny_legendary_beats_plain_common(self):
        shiny_legend = PokemonEntry("Mewtwo", legendary=True, shiny=True)
        common = PokemonEntry("Pidgey")
        assert desirability(shiny_legend) > desirability(common)

    def test_shundo_beats_plain_shiny(self):
        shundo = PokemonEntry("Rayquaza", shiny=True, iv_percent=100, legendary=True)
        shiny = PokemonEntry("Rayquaza", shiny=True, legendary=True)
        assert desirability(shundo) > desirability(shiny)

    def test_common_pokemon_has_low_desirability(self):
        assert desirability(PokemonEntry("Pidgey")) < 0.1

    def test_desirability_is_bounded(self):
        loaded = PokemonEntry("Mewtwo", shiny=True, legendary=True, iv_percent=100,
                              background="Special", costume="Armored",
                              legacy_move="Psystrike", gigantamax=True, regional=True)
        assert 0.0 <= desirability(loaded) <= 1.0


class TestCollectionQuality:
    def test_quality_is_none_for_empty_collection(self):
        assert collection_quality([]) is None

    def test_quality_rewards_a_strong_top_few(self):
        ordinary = [PokemonEntry(f"Pidgey{i}", cp=300) for i in range(10)]
        strong = [
            PokemonEntry("Mewtwo", shiny=True, legendary=True, iv_percent=100),
            PokemonEntry("Mew", shiny=True, mythical=True),
            PokemonEntry("Rayquaza", shiny=True, legendary=True),
        ] + ordinary
        assert collection_quality(strong) > collection_quality(ordinary)


class TestResultShape:
    def test_result_reports_score_and_coverage_in_range(self, stacked_scan):
        result = classify(stacked_scan)
        assert 0.0 <= result.score <= 1.0
        assert 0.0 <= result.coverage <= 1.0

    def test_reasons_explain_the_classification(self, stacked_scan):
        result = classify(stacked_scan)
        assert result.reasons
        assert any("observed maximum" in r for r in result.reasons)

    def test_to_dict_is_json_friendly(self, stacked_scan):
        import json
        json.dumps(classify(stacked_scan).to_dict())

    def test_signals_cover_the_spec_categories(self, stacked_scan):
        names = {s.name for s in classify(stacked_scan).signals}
        for expected in ("Trainer level", "Pokédex completion", "Stardust",
                         "Collection quality", "Medals", "Rare Candy XL"):
            assert expected in names
