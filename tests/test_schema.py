"""Schema, evidence status, de-duplication and merge behaviour."""

from __future__ import annotations

from pokego.schema import (
    AccountFacts,
    AccountScan,
    Evidence,
    PokemonEntry,
    RarityLabel,
    merge_scans,
)


class TestEvidence:
    def test_none_is_not_visible(self):
        assert Evidence.coerce(None) is Evidence.NOT_VISIBLE

    def test_normalises_spacing_and_case(self):
        assert Evidence.coerce("partially verified") is Evidence.PARTIALLY_VERIFIED
        assert Evidence.coerce("VERIFIED") is Evidence.VERIFIED

    def test_unknown_token_is_not_visible(self):
        assert Evidence.coerce("something else") is Evidence.NOT_VISIBLE


class TestFacts:
    def test_missing_and_zero_are_different(self):
        facts = AccountFacts(stardust=None, pokecoins=0)
        assert facts.stardust is None
        assert facts.pokecoins == 0

    def test_parses_formatted_numbers(self):
        facts = AccountFacts(xp="1,234,567", stardust="2 500")
        assert facts.xp == 1_234_567
        assert facts.stardust == 2500

    def test_merge_fills_only_gaps(self):
        base = AccountFacts(level=40, stardust=0)
        other = AccountFacts(level=99, stardust=5000, team="Mystic")
        base.merge_missing_from(other)
        assert base.level == 40          # already known, not overwritten
        assert base.stardust == 0        # zero is a real value, not a gap
        assert base.team == "Mystic"     # gap filled

    def test_medals_merge_without_duplicates(self):
        base = AccountFacts(medals=["Gold Fisherman"])
        base.merge_missing_from(AccountFacts(medals=["Gold Fisherman", "Gold Backpacker"]))
        assert base.medals == ["Gold Fisherman", "Gold Backpacker"]


class TestPokemonEntry:
    def test_iv_parsing_and_bounds(self):
        assert PokemonEntry("Mewtwo", iv_percent="100%").iv_percent == 100.0
        assert PokemonEntry("Mewtwo", iv_percent=87.5).iv_percent == 87.5
        assert PokemonEntry("Mewtwo", iv_percent=150).iv_percent is None

    def test_hundo_shundo_nundo(self):
        assert PokemonEntry("A", iv_percent=100).is_hundo
        assert PokemonEntry("A", iv_percent=100, shiny=True).is_shundo
        assert PokemonEntry("A", iv_percent=0).is_nundo
        assert not PokemonEntry("A", iv_percent=98).is_hundo

    def test_legacy_move_is_a_string_not_a_moveset(self):
        entry = PokemonEntry("Rayquaza", legacy_move="Dragon Ascent")
        assert entry.legacy_move == "Dragon Ascent"

    def test_merge_missing_from_fills_attributes(self):
        a = PokemonEntry("Mewtwo", cp=4000)
        b = PokemonEntry("Mewtwo", cp=4000, shiny=True, iv_percent=100,
                         background="Special")
        a.merge_missing_from(b)
        assert a.shiny is True
        assert a.iv_percent == 100
        assert a.background == "Special"

    def test_roundtrip_dict(self):
        entry = PokemonEntry("Mew", cp=1800, shiny=True, mythical=True,
                             evidence=Evidence.VERIFIED)
        restored = PokemonEntry.from_dict(entry.to_dict())
        assert restored.species == "Mew"
        assert restored.shiny is True
        assert restored.mythical is True
        assert restored.evidence is Evidence.VERIFIED


class TestScanDedupe:
    def test_identical_pokemon_are_not_double_counted(self):
        scan = AccountScan()
        assert scan.add_pokemon(PokemonEntry("Mewtwo", cp=4000)) is True
        assert scan.add_pokemon(PokemonEntry("Mewtwo", cp=4000)) is False
        assert scan.counts()["total_identified"] == 1

    def test_same_species_same_cp_merges_and_keeps_new_attribute(self):
        scan = AccountScan()
        scan.add_pokemon(PokemonEntry("Mewtwo", cp=4000))
        scan.add_pokemon(PokemonEntry("Mewtwo", cp=4000, shiny=True))
        assert scan.counts()["total_identified"] == 1
        assert scan.counts()["shiny"] == 1

    def test_different_cp_counts_separately(self):
        scan = AccountScan()
        scan.add_pokemon(PokemonEntry("Mewtwo", cp=4000))
        scan.add_pokemon(PokemonEntry("Mewtwo", cp=3000))
        assert scan.counts()["total_identified"] == 2

    def test_empty_species_is_rejected(self):
        scan = AccountScan()
        assert scan.add_pokemon(PokemonEntry("  ")) is False
        assert scan.counts()["total_identified"] == 0


class TestCounts:
    def test_counts_shiny_legendary_and_shundo(self):
        scan = AccountScan()
        scan.add_pokemon(PokemonEntry("Mewtwo", cp=4000, shiny=True, legendary=True))
        scan.add_pokemon(PokemonEntry("Rayquaza", cp=4100, shiny=True, legendary=True,
                                      iv_percent=100))
        scan.add_pokemon(PokemonEntry("Pidgey", cp=300))
        counts = scan.counts()
        assert counts["total_identified"] == 3
        assert counts["shiny"] == 2
        assert counts["legendary"] == 2
        assert counts["hundo"] == 1
        assert counts["shundo"] == 1
        assert counts["shiny_legendary"] == 2


class TestMergeScans:
    def test_merge_combines_facts_and_pokemon(self):
        a = AccountScan(facts=AccountFacts(level=40))
        a.add_pokemon(PokemonEntry("Mewtwo", cp=4000))
        b = AccountScan(facts=AccountFacts(stardust=5000))
        b.add_pokemon(PokemonEntry("Pidgey", cp=300))
        merged = merge_scans([a, b])
        assert merged.facts.level == 40
        assert merged.facts.stardust == 5000
        assert merged.counts()["total_identified"] == 2

    def test_merge_does_not_double_count_the_same_pokemon(self):
        a = AccountScan()
        a.add_pokemon(PokemonEntry("Mewtwo", cp=4000))
        b = AccountScan()
        b.add_pokemon(PokemonEntry("Mewtwo", cp=4000))
        assert merge_scans([a, b]).counts()["total_identified"] == 1


class TestRarityLabel:
    def test_ordering(self):
        assert RarityLabel.COMMON.rank < RarityLabel.RARE.rank
        assert RarityLabel.RARE.rank < RarityLabel.EXTREMELY_RARE.rank


class TestScanRoundtrip:
    def test_scan_from_dict_accepts_scanner_shape(self):
        scan = AccountScan.from_dict({
            "facts": {"level": 50, "stardust": 1000, "evidence": "VERIFIED"},
            "pokemon": [{"species": "Mewtwo", "cp": 4000, "shiny": True}],
        })
        assert scan.facts.level == 50
        assert scan.counts()["shiny"] == 1
        assert scan.facts.evidence is Evidence.VERIFIED

    def test_scan_from_dict_tolerates_bad_entries(self):
        scan = AccountScan.from_dict({"pokemon": [{"cp": 4000}, "nonsense"]})
        assert scan.counts()["total_identified"] == 0

    def test_missing_pokemon_list_is_not_an_error(self):
        scan = AccountScan.from_dict({})
        assert scan.counts()["total_identified"] == 0
