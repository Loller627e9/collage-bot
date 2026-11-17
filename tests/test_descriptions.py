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

from .conftest import make_scan


def _build(kind, scan, narrative=None):
    return build_description(kind, scan, assess_collection(scan.pokemon),
                             classify(scan), narrative=narrative)


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
    def test_leads_with_classification_and_headline_asset(self, stacked_scan):
        body = _build(ELDORADO, stacked_scan).body
        assert "STACKED" in body
        assert "Headline asset" in body

    def test_uses_vivid_but_honest_language(self, stacked_scan):
        assert "Eldorado" in _build(ELDORADO, stacked_scan).title

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
        assert set(data) == {"kind", "title", "body", "source"}


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

    def test_eldorado_evidence_is_one_bullet_per_reason(self, stacked_scan):
        body = _build(ELDORADO, stacked_scan).body
        section = body.split("Classification evidence:")[1].split("\n\n")[0]
        bullets = [line for line in section.splitlines() if line.startswith("- ")]
        assert len(bullets) >= 2
