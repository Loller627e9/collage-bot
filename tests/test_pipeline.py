"""End-to-end pipeline: scanner -> classification -> report -> descriptions."""

from __future__ import annotations

import json

from pokego.descriptions import AUCTION, ELDORADO
from pokego.gemini import GeminiClient, ImagePart
from pokego.pipeline import investigate, scan_only
from pokego.schema import AccountClass, Evidence

SCAN_PAYLOAD = {
    "facts": {
        "trainer_name": "MockTrainer", "level": 58, "xp": 150_000_000,
        "team": "Instinct", "total_caught": 120_000, "pokedex_caught": 720,
        "pokedex_seen": 775, "stardust": 21_000_000, "pokecoins": 9000,
        "rare_candy": 700, "rare_candy_xl": 350, "pokemon_storage": 5500,
        "pokemon_storage_used": 5200,
        "medals": ["Gold Fisherman", "Gold Backpacker", "Gold Ace Trainer"],
        "pvp_notes": "Several Great League meta picks", "evidence": "VERIFIED",
    },
    "pokemon": [
        {"species": "Mewtwo", "cp": 4600, "iv_percent": 100, "shiny": True,
         "legendary": True, "background": "Special", "evidence": "VERIFIED"},
        {"species": "Rayquaza", "cp": 4200, "shiny": True, "legendary": True,
         "legacy_move": "Dragon Ascent", "evidence": "VERIFIED"},
        {"species": "Mew", "cp": 1700, "mythical": True, "shiny": True,
         "evidence": "VERIFIED"},
        {"species": "Pikachu", "cp": 850, "shiny": True, "costume": "Party Hat",
         "evidence": "VERIFIED"},
        {"species": "Nihilego", "cp": 3800, "ultra_beast": True, "evidence": "VERIFIED"},
        {"species": "Machop", "cp": 1300, "shadow": True, "evidence": "VERIFIED"},
    ],
    "screen_types": ["trainer_profile", "pokemon_storage"],
    "warnings": [],
}


def _client(server):
    return GeminiClient("test-key", base_url=server.base_url)


class TestFullRun:
    def test_pipeline_produces_scan_report_and_both_descriptions(self, mock_gemini):
        server = mock_gemini(SCAN_PAYLOAD)
        result = investigate([ImagePart.from_bytes(b"img")], _client(server))
        assert result.scan.counts()["total_identified"] == 6
        assert result.classification.account_class is AccountClass.STACKED
        assert set(result.descriptions) == {ELDORADO, AUCTION}
        assert "ACCOUNT CLASSIFICATION: STACKED" in result.report.markdown

    def test_scan_is_enriched_with_species_flags(self, mock_gemini):
        """A legendary the scanner left unflagged is filled from the dataset."""
        payload = dict(SCAN_PAYLOAD)
        payload["pokemon"] = [{"species": "Mewtwo", "cp": 4000, "evidence": "VERIFIED"}]
        server = mock_gemini(payload)
        result = investigate([ImagePart.from_bytes(b"img")], _client(server))
        assert result.scan.pokemon[0].legendary is True

    def test_images_are_not_sent_to_the_writer(self, mock_gemini):
        """The writer must never see pixels, so it cannot invent from them."""
        server = mock_gemini(SCAN_PAYLOAD)
        investigate([ImagePart.from_bytes(b"img")], _client(server))
        narrative_requests = [r for r in server.requests
                              if not any(p.get("type") == "image"
                                         for p in r["body"].get("input", []))]
        assert narrative_requests
        for request in narrative_requests:
            assert all(p.get("type") != "image" for p in request["body"]["input"])

    def test_writer_receives_the_deterministic_classification(self, mock_gemini):
        server = mock_gemini(SCAN_PAYLOAD)
        investigate([ImagePart.from_bytes(b"img")], _client(server))
        prompts = [p["text"] for r in server.requests for p in r["body"]["input"]
                   if p.get("type") == "text"]
        assert any("STACKED" in text for text in prompts)

    def test_no_narrative_keeps_deterministic_report(self, mock_gemini):
        server = mock_gemini(SCAN_PAYLOAD)
        result = investigate([ImagePart.from_bytes(b"img")], _client(server),
                             use_narrative=False)
        assert result.report.narrative_source == "deterministic"
        assert "ACCOUNT CLASSIFICATION: STACKED" in result.report.markdown

    def test_description_types_can_be_restricted(self, mock_gemini):
        server = mock_gemini(SCAN_PAYLOAD)
        result = investigate([ImagePart.from_bytes(b"img")], _client(server),
                             description_types=[ELDORADO])
        assert set(result.descriptions) == {ELDORADO}

    def test_to_dict_is_json_serialisable(self, mock_gemini):
        server = mock_gemini(SCAN_PAYLOAD)
        result = investigate([ImagePart.from_bytes(b"img")], _client(server))
        json.dumps(result.to_dict())


class TestNoImages:
    def test_no_images_yields_a_warning_and_offline_meta(self):
        result = investigate([], None)
        assert any("No screenshots" in w for w in result.warnings)
        assert result.scanner_model == "offline"
        assert result.classification.account_class is AccountClass.MINI

    def test_no_images_still_produces_a_report_and_descriptions(self):
        result = investigate([], None)
        assert "ACCOUNT CLASSIFICATION" in result.report.markdown
        assert set(result.descriptions) == {ELDORADO, AUCTION}

    def test_no_images_does_not_claim_zero_collection(self):
        result = investigate([], None)
        assert "Not visible" in result.report.markdown


class TestFailureHandling:
    def test_scanner_failure_is_reported_not_hidden(self):
        client = GeminiClient("test-key", base_url="http://127.0.0.1:9")
        result = investigate([ImagePart.from_bytes(b"img")], client)
        assert any("Scanner failed" in w for w in result.warnings)
        assert result.scanner_model == "offline"

    def test_scanner_failure_still_yields_deterministic_output(self):
        client = GeminiClient("test-key", base_url="http://127.0.0.1:9")
        result = investigate([ImagePart.from_bytes(b"img")], client)
        assert result.report.markdown
        assert result.descriptions


class TestScanOnly:
    def test_returns_a_scan_without_judgements(self, mock_gemini):
        server = mock_gemini(SCAN_PAYLOAD)
        scan = scan_only([ImagePart.from_bytes(b"img")], _client(server))
        assert scan.facts.level == 58
        assert scan.counts()["shiny"] == 4

    def test_dedupes_repeated_pokemon_across_screenshots(self, mock_gemini):
        payload = dict(SCAN_PAYLOAD)
        payload["pokemon"] = [
            {"species": "Mewtwo", "cp": 4600, "evidence": "VERIFIED"},
            {"species": "Mewtwo", "cp": 4600, "evidence": "VERIFIED"},
        ]
        server = mock_gemini(payload)
        scan = scan_only([ImagePart.from_bytes(b"img")], _client(server))
        assert scan.counts()["total_identified"] == 1


class TestEvidencePreserved:
    def test_evidence_status_survives_the_pipeline(self, mock_gemini):
        payload = dict(SCAN_PAYLOAD)
        payload["facts"] = dict(payload["facts"], evidence="PARTIALLY_VERIFIED")
        server = mock_gemini(payload)
        result = investigate([ImagePart.from_bytes(b"img")], _client(server))
        assert result.scan.facts.evidence is Evidence.PARTIALLY_VERIFIED
