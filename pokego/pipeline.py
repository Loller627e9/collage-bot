"""End-to-end account investigation: screenshots in, report + descriptions out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .classification import ClassificationResult, classify
from .descriptions import Description, build_description
from .gemini import GeminiError, GeminiResponse, GeminiClient, ImagePart
from .prompts import (
    SCANNER_SYSTEM_PROMPT,
    SCANNER_JSON_SCHEMA,
    build_scanner_prompt,
    build_report_prompt,
    build_description_prompt,
    dumps,
)
from .rarity import RarityAssessment, assess_collection, enrich_missing_flags, top_highlights
from .report import ReportBundle, build_report
from .schema import AccountScan


@dataclass
class InvestigationResult:
    scan: AccountScan
    assessments: list[RarityAssessment]
    classification: ClassificationResult
    report: ReportBundle
    descriptions: dict[str, Description] = field(default_factory=dict)
    scanner_model: str = "offline"
    scanner_transport: str = "offline"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan": self.scan.to_dict(),
            "rarity": [a.to_dict() for a in self.assessments],
            "classification": self.classification.to_dict(),
            "report": self.report.to_dict(),
            "descriptions": {k: v.to_dict() for k, v in self.descriptions.items()},
            "highlights": [a.to_dict() for a in top_highlights(self.assessments)],
            "meta": {
                "scanner_model": self.scanner_model,
                "scanner_transport": self.scanner_transport,
                "warnings": list(self.warnings),
            },
        }


def scan_only(
    images: Sequence[ImagePart], client: GeminiClient, *, extra_instructions: str | None = None
) -> AccountScan:
    """Run the Account Scanner and return the raw scan. Raises GeminiError."""
    response = client.generate(
        build_scanner_prompt(extra_instructions),
        system_instruction=SCANNER_SYSTEM_PROMPT,
        images=images,
        json_schema=SCANNER_JSON_SCHEMA,
        temperature=0.1,
    )
    scan = AccountScan.from_dict(response.json())
    enrich_missing_flags(scan.pokemon)
    return scan


def investigate(
    images: Sequence[ImagePart],
    client: GeminiClient | None = None,
    *,
    extra_instructions: str | None = None,
    use_narrative: bool = True,
    description_types: Sequence[str] = ("eldorado", "auction"),
    image_names: Sequence[str] | None = None,
) -> InvestigationResult:
    """Run scanner -> classification -> rarity -> report -> descriptions."""
    warnings: list[str] = []
    scan = AccountScan()
    scanner_response: GeminiResponse | None = None

    if images and client is not None:
        try:
            scanner_response = client.generate(
                build_scanner_prompt(extra_instructions),
                system_instruction=SCANNER_SYSTEM_PROMPT,
                images=images,
                json_schema=SCANNER_JSON_SCHEMA,
                temperature=0.1,
            )
            scan = AccountScan.from_dict(scanner_response.json())
        except GeminiError as exc:
            warnings.append(f"Scanner failed: {exc}")
    elif not images:
        warnings.append("No screenshots were supplied.")

    if image_names:
        scan.screenshots = list(image_names)
    scan.warnings.extend(w for w in warnings if w not in scan.warnings)

    enrich_missing_flags(scan.pokemon)
    assessments = assess_collection(scan.pokemon)
    classification = classify(scan)

    narrative: str | None = None
    if use_narrative and scanner_response is not None:
        try:
            prompt = build_report_prompt(
                dumps(scan.to_dict()),
                dumps(classification.to_dict()),
                dumps([a.to_dict() for a in assessments]),
            )
            response = client.generate(prompt, system_instruction=None, temperature=0.4)
            if response.text.strip():
                narrative = response.text
        except GeminiError as exc:
            warnings.append(f"Narrative skipped: {exc}")

    report = build_report(scan, assessments, classification, narrative=narrative)
    for warning in warnings:
        if warning not in report.warnings:
            report.warnings.append(warning)

    descriptions: dict[str, Description] = {}
    for kind in description_types:
        desc_narrative: str | None = None
        if use_narrative and scanner_response is not None:
            try:
                prompt = build_description_prompt(
                    kind,
                    dumps(scan.to_dict()),
                    dumps(classification.to_dict()),
                    dumps([a.to_dict() for a in assessments]),
                )
                response = client.generate(prompt, temperature=0.5)
                desc_narrative = response.text.strip() or None
            except GeminiError as exc:
                warnings.append(f"{kind} description narrative skipped: {exc}")
        try:
            descriptions[kind] = build_description(
                kind, scan, assessments, classification, narrative=desc_narrative
            )
        except ValueError as exc:
            warnings.append(str(exc))

    return InvestigationResult(
        scan=scan,
        assessments=assessments,
        classification=classification,
        report=report,
        descriptions=descriptions,
        scanner_model=scanner_response.model if scanner_response else "offline",
        scanner_transport=scanner_response.transport if scanner_response else "offline",
        warnings=report.warnings,
    )
