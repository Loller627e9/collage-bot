"""The two description types: Eldorado and Auction."""

from __future__ import annotations

import pytest

from pokego.classification import classify
from pokego.descriptions import (
    AUCTION,
    DESCRIPTION_TYPES,
    ELDORADO,
    VALUATION_NOTICE,
    build_description,
)
from pokego.rarity import assess_collection
from pokego.schema import Evidence
from pokego.titles import listing_title

from .conftest import make_scan


def _build(kind, scan, narrative=None):
    return build_description(kind, scan, assess_collection(scan.pokemon),
                             classify(scan), narrative=narrative)


def _title(scan) -> str:
    return listing_title(scan, assess_collection(scan.pokemon), classify(scan))


class TestTypes:
    def test_exactly_two_types_are_defined(self):
        assert set(DESCRIPTION_TYPES) == {ELDORADO, AUCTION}

    def test_unknown_type_raises(self, stacked_scan):
        with pytest.raises(ValueError):
            _build("bogus", stacked_scan)

    def test_both_types_generate(self, stacked_scan):
        for kind in DESCRIPTION_TYPES:
            assert _build(kind, stacked_scan).body.strip()


class TestEldorado:
    def test_reads_as_a_listing_not_an_audit(self, stacked_scan):
        body = _build(ELDORADO, stacked_scan).body
        assert "STACKED" in body
        assert "Pokémon GO Account" in body
        # Audit scaffolding belongs in the report, never in the listing.
        for audit in ("Classification evidence:", "EVIDENCE", "Confidence:"):
            assert audit not in body

    def test_uses_vivid_but_honest_language(self, stacked_scan):
        assert "Eldorado" in _build(ELDORADO, stacked_scan).title

    def test_carries_a_keyword_listing_title(self, stacked_scan):
        desc = _build(ELDORADO, stacked_scan)
        assert desc.listing_title
        assert "LEVEL 62" in desc.listing_title
        assert "STACKED" in desc.listing_title
        assert len(desc.listing_title) <= 120

    def test_flat_inventory_lines(self, stacked_scan):
        body = _build(ELDORADO, stacked_scan).body
        assert "3 Legendary Pokémon" in body
        assert "4 Shiny Pokémon" in body
        assert "1 Perfect IV (100% IV)" in body

    def test_headline_pieces_are_named(self, stacked_scan):
        body = _build(ELDORADO, stacked_scan).body
        assert "Shundo Mewtwo" in body
        assert "Shiny Mew" in body

    def test_weak_account_is_not_oversold(self, mini_scan):
        body = _build(ELDORADO, mini_scan).body
        assert "MINI" in body
        assert "Extremely Rare" not in body

    def test_no_price_assertion(self, stacked_scan):
        """No currency symbol and no price figure. The disclaimer may say 'no price'."""
        import re
        body = _build(ELDORADO, stacked_scan).body
        assert "$" not in body
        assert not re.search(r"\b\d[\d,]*\s*(usd|eur|gbp)\b", body, re.I)
        # The only mention of pricing is the disclaimer that none is given.
        assert body.count("price") == body.lower().count("no price")


class TestAuction:
    def test_has_itemised_lot_highlights(self, stacked_scan):
        body = _build(AUCTION, stacked_scan).body
        assert "LOT HIGHLIGHTS" in body
        assert "Mewtwo" in body

    def test_includes_progression_and_resources(self, stacked_scan):
        body = _build(AUCTION, stacked_scan).body
        assert "PROGRESSION" in body
        assert "RESOURCES" in body

    def test_includes_evidence_section(self, stacked_scan):
        body = _build(AUCTION, stacked_scan).body
        assert "EVIDENCE" in body
        assert "VERIFIED" in body

    def test_states_no_price_is_estimated(self, stacked_scan):
        body = _build(AUCTION, stacked_scan).body
        assert "No price is estimated" in body


class TestSharedGuarantees:
    def test_both_types_carry_the_valuation_notice(self, stacked_scan):
        for kind in DESCRIPTION_TYPES:
            assert VALUATION_NOTICE in _build(kind, stacked_scan).body

    def test_notice_mentions_the_terms_of_service(self, stacked_scan):
        for kind in DESCRIPTION_TYPES:
            assert "terms of service" in _build(kind, stacked_scan).body.lower()

    def test_missing_values_render_as_not_visible_not_zero(self):
        scan = make_scan([], evidence=Evidence.NOT_VISIBLE)
        body = _build(AUCTION, scan).body
        assert "not visible" in body.lower()
        assert "0" not in body.split("LOT HIGHLIGHTS")[1].split("PROGRESSION")[0]

    def test_narrative_is_used_and_labelled(self, stacked_scan):
        desc = _build(ELDORADO, stacked_scan, narrative="A pristine veteran account.")
        assert "pristine veteran account" in desc.body
        assert desc.source == "gemini"
        assert VALUATION_NOTICE in desc.body

    def test_deterministic_source_when_no_narrative(self, stacked_scan):
        assert _build(ELDORADO, stacked_scan).source == "deterministic"

    def test_never_invents_currency_amounts(self, stacked_scan):
        for kind in DESCRIPTION_TYPES:
            body = _build(kind, stacked_scan).body
            assert "$" not in body

    def test_to_dict_roundtrip(self, stacked_scan):
        data = _build(ELDORADO, stacked_scan).to_dict()
        assert set(data) == {"kind", "title", "body", "source", "listing_title"}


class TestNumberFormatting:
    def test_large_numbers_use_thousands_separators(self, stacked_scan):
        body = _build(AUCTION, stacked_scan).body
        assert "24,000,000" in body or "28,000,000" in body
        assert "180,000" in body or "150,000" in body

    def test_no_bare_seven_digit_numbers(self, stacked_scan):
        import re
        body = _build(AUCTION, stacked_scan).body
        assert not re.search(r"(?<![\d,])\d{7,}(?![\d,])", body)

    def test_not_visible_values_are_not_zero(self):
        scan = make_scan([], evidence=Evidence.NOT_VISIBLE)
        body = _build(AUCTION, scan).body
        assert "Stardust: not visible" in body


class TestListingTitles:
    """The title is the most-read line, so it is built from facts, not prose."""

    def test_title_only_uses_visible_facts(self):
        scan = make_scan([], evidence=Evidence.NOT_VISIBLE)
        title = _title(scan)
        assert "LEVEL" not in title
        assert "SHINY" not in title
        assert "DUST" not in title

    def test_title_omits_categories_with_no_evidence(self, mini_scan):
        title = _title(mini_scan)
        assert "SHINY" not in title
        assert "LEG" not in title

    def test_title_is_capped(self, stacked_scan):
        assert len(_title(stacked_scan)) <= 120

    def test_shiny_legendary_is_reported_separately(self, stacked_scan):
        title = _title(stacked_scan)
        assert "2 SHINY LEG" in title

    def test_dust_is_abbreviated(self, stacked_scan):
        assert "28M DUST" in _title(stacked_scan)

    def test_title_never_contains_a_price(self, stacked_scan):
        assert "$" not in _title(stacked_scan)

    def test_title_always_names_the_class(self, mini_scan):
        assert "MINI" in _title(mini_scan)

    def test_sparse_scan_still_gets_a_title(self):
        scan = make_scan([], evidence=Evidence.NOT_VISIBLE)
        assert _title(scan).strip()

    def test_title_has_no_duplicate_segments(self, stacked_scan):
        segments = [s.strip() for s in _title(stacked_scan).split("|")[1:]]
        assert len(segments) == len(set(segments))
