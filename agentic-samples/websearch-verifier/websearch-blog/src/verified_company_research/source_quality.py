from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from .contracts import FieldName, FieldSubmission


class SourceClass(StrEnum):
    COMPANY_OWNED = "company_owned"
    REGISTRY = "registry"
    INDEPENDENT_EDITORIAL = "independent_editorial"
    DISCOVERY_ONLY = "discovery_only"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceQualityPolicy:
    domain_classes: dict[SourceClass, tuple[str, ...]]
    field_requirements: dict[FieldName, tuple[frozenset[SourceClass], ...]]
    suitability_rules: dict[FieldName, str]
    official_source_classes: frozenset[SourceClass]

    @classmethod
    def from_dict(cls, value: dict) -> "SourceQualityPolicy":
        domain_classes = {
            SourceClass(name): tuple(domain.lower() for domain in domains)
            for name, domains in value["domain_classes"].items()
        }
        requirements = {
            FieldName(field): tuple(
                frozenset(SourceClass(name) for name in group)
                for group in groups
            )
            for field, groups in value["field_requirements"].items()
        }
        suitability = {
            FieldName(field): rule
            for field, rule in value["suitability_rules"].items()
        }
        official = frozenset(
            SourceClass(name)
            for name in value.get(
                "official_source_classes",
                ["company_owned", "registry"],
            )
        )
        return cls(domain_classes, requirements, suitability, official)

    def classify(self, url: str) -> SourceClass:
        hostname = (urlparse(url).hostname or "").lower()
        matches: list[tuple[int, SourceClass]] = []
        for source_class, domains in self.domain_classes.items():
            matches.extend(
                (len(domain), source_class)
                for domain in domains
                if hostname == domain or hostname.endswith(f".{domain}")
            )
        if not matches:
            return SourceClass.UNKNOWN
        return max(matches, key=lambda item: item[0])[1]

    def assess(self, field: FieldSubmission) -> dict:
        eligible_classes = frozenset().union(
            *self.field_requirements[field.field]
        )
        sources = [
            {
                "url": item.url,
                "source_class": self.classify(item.url).value,
                "official": (
                    self.classify(item.url) in self.official_source_classes
                ),
                "eligible_for_field": (
                    self.classify(item.url) in eligible_classes
                ),
            }
            for item in field.evidence
        ]
        present = {SourceClass(item["source_class"]) for item in sources}
        missing = [
            sorted(source_class.value for source_class in group)
            for group in self.field_requirements[field.field]
            if not present.intersection(group)
        ]
        inadmissible = [
            item.url
            for item in field.evidence
            if self.classify(item.url) not in eligible_classes
        ]
        return {
            "sources": sources,
            "required_source_groups": [
                sorted(source_class.value for source_class in group)
                for group in self.field_requirements[field.field]
            ],
            "official_source_classes": sorted(
                source_class.value
                for source_class in self.official_source_classes
            ),
            "missing_source_groups": missing,
            "inadmissible_evidence_urls": inadmissible,
            "semantic_suitability_rule": self.suitability_rules[field.field],
            "mechanically_admissible": not missing,
        }

    def prompt_text(self) -> str:
        lines = [
            "Official sources are "
            + ", ".join(
                sorted(item.value for item in self.official_source_classes)
            )
            + ". Official status alone is not enough: the passage must be "
            "suitable for the field and support the complete claim.",
            "Discovery-only and unknown sources may guide search but can never "
            "support acceptance.",
            "Only source classes listed for a field may support that field; "
            "other sources remain discovery context.",
        ]
        for field in FieldName:
            groups = self.field_requirements[field]
            required = " AND ".join(
                "(" + " OR ".join(sorted(item.value for item in group)) + ")"
                for group in groups
            )
            lines.append(
                f"- {field.value}: requires {required}. "
                f"{self.suitability_rules[field]}"
            )
        return "\n".join(lines)
