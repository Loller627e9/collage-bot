"""Report assembly: required sections, evidence labelling, numeric guard."""

from __future__ import annotations

from pokego.classification import classify
from pokego.rarity import assess_collection
from pokego.report import (
    SECTION_ORDER,
    build_report,
    numeric_claims_not_in_scan,
)
from pokego.schema import Evidence

from .conftest import make_scan


def _report(scan):
    return build_report(scan, assess_collection(scan.pokemon), classify(scan))


class TestRequiredSections:
    def test_every_required_heading_is_present(self, stacked_scan):
        md = _report(stacked_scan).markdown
        for heading in SECTION_ORDER:
            assert heading in md

    def test_classification_line_is_present_and_correct(self, stacked_scan):
        assert "ACCOUNT CLASSIFICATION: STACKED" in _report(stacked_scan).markdown

    def test_sections_dict_matches_order(self, stacked_scan):
        bundle = _report(stacked_scan)
        for heading in SECTION_ORDER:
            assert heading in bundle.sections


class TestNotVisible:
    def test_absent_values_render_as_not_visible(self):
        scan = make_scan([], evidence=Evidence.NOT_VISIBLE)
        md = _report(scan).markdown
        assert "Not visible" in md

    def test_zero_is_rendered_as_zero_not_not_visible(self):
        scan = make_scan([], level=0, stardust=0, evidence=Evidence.VERIFIED)
        overview = _report(scan).sections["ACCOUNT OVERVIEW"]
        assert "- Stardust: 0" in overview

    def test_unknown_values_are_not_rendered_as_zero(self):
        scan = make_scan([], evidence=Evidence.NOT_VISIBLE)
        overview = _report(scan).sections["ACCOUNT OVERVIEW"]
        assert "- Stardust: Not visible" in overview
        assert "- Stardust: 0" not in overview


class TestCollectionTables:
    def test_counts_come_from_the_scan(self, stacked_scan):
        sections = _report(stacked_scan).sections
        counts = stacked_scan.counts()
        assert f"- Shiny count: {counts['shiny']} identified" in sections["COLLECTION ANALYSIS"]
        assert f"- Shundo count: {counts['shundo']} identified" in sections["COLLECTION ANALYSIS"]

    def test_rare_assets_lists_notable_pokemon(self, stacked_scan):
        rare = _report(stacked_scan).sections["RARE ASSETS"]
        assert "Mewtwo" in rare
        assert "Extremely Rare" in rare


class TestNumericGuard:
    def test_flags_a_number_absent_from_the_scan(self, stacked_scan):
        flags = numeric_claims_not_in_scan("This account has 999 shinies.", stacked_scan)
        assert "999" in flags

    def test_accepts_numbers_the_scan_supports(self, stacked_scan):
        flags = numeric_claims_not_in_scan("Trainer level 62.", stacked_scan)
        assert flags == []

    def test_accepts_derived_counts(self, stacked_scan):
        shiny = stacked_scan.counts()["shiny"]
        assert numeric_claims_not_in_scan(f"{shiny} shiny identified.", stacked_scan) == []

    def test_ignores_small_numbers_like_level_caps(self, stacked_scan):
        assert numeric_claims_not_in_scan("Level 5 account, 3 medals.", stacked_scan) == []

    def test_empty_narrative_has_no_flags(self, stacked_scan):
        assert numeric_claims_not_in_scan("", stacked_scan) == []


class TestNarrativeHandling:
    def test_unsupported_numbers_in_prose_are_reported(self, stacked_scan):
        narrative = ("FINAL DESCRIPTION\nThis account holds 123456 shinies.")
        bundle = build_report(stacked_scan, assess_collection(stacked_scan.pokemon),
                              classify(stacked_scan), narrative=narrative)
        assert any("not supported by the scan" in w for w in bundle.warnings)

    def test_narrative_source_is_recorded(self, stacked_scan):
        narrative = "FINAL DESCRIPTION\nA fine account."
        bundle = build_report(stacked_scan, assess_collection(stacked_scan.pokemon),
                              classify(stacked_scan), narrative=narrative)
        assert bundle.narrative_source == "gemini"

    def test_deterministic_report_works_without_narrative(self, stacked_scan):
        bundle = _report(stacked_scan)
        assert bundle.narrative_source == "deterministic"
        assert bundle.sections["FINAL DESCRIPTION"]

    def test_tables_stay_deterministic_even_with_narrative(self, stacked_scan):
        """Model prose must never replace the computed collection numbers."""
        counts = stacked_scan.counts()
        narrative = "COLLECTION ANALYSIS\n- Shiny count: 9999 identified"
        bundle = build_report(stacked_scan, assess_collection(stacked_scan.pokemon),
                              classify(stacked_scan), narrative=narrative)
        assert f"- Shiny count: {counts['shiny']} identified" in bundle.markdown
        assert "9999" not in bundle.markdown


class TestMissingInformation:
    def test_weaknesses_list_absent_signals(self):
        scan = make_scan([], level=40, evidence=Evidence.PARTIALLY_VERIFIED)
        bundle = _report(scan)
        assert bundle.missing_information
        joined = " ".join(bundle.missing_information)
        assert "not visible" in joined.lower()

    def test_confidence_is_reported(self, stacked_scan):
        assert "CONFIDENCE" in _report(stacked_scan).markdown
