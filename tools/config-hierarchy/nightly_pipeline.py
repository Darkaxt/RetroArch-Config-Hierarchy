#!/usr/bin/env python3
"""Pure policy helpers for the RetroArch Android nightly monitor."""

from dataclasses import dataclass
import re
from urllib.parse import urljoin


class ProvenanceError(ValueError):
    pass


@dataclass(frozen=True)
class NightlyPair:
    date: str
    normal_url: str
    aarch64_url: str


_APK_PATTERN = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})-RetroArch(?P<aarch64>_aarch64)?\.apk"
)


def discover_pairs(index_html, base_url):
    discovered = {}
    for match in _APK_PATTERN.finditer(index_html):
        date = match.group("date")
        variant = "aarch64" if match.group("aarch64") else "normal"
        filename = match.group(0)
        discovered.setdefault(date, {})[variant] = urljoin(base_url, filename)

    return [
        NightlyPair(date, variants["normal"], variants["aarch64"])
        for date, variants in sorted(discovered.items())
        if set(variants) == {"normal", "aarch64"}
    ]


def select_next_pair(pairs, last_released_date):
    for pair in sorted(pairs, key=lambda item: item.date):
        if not last_released_date or pair.date > last_released_date:
            return pair
    return None


def resolve_pair_revision(normal_revision, aarch64_revision, resolver):
    if normal_revision != aarch64_revision:
        raise ProvenanceError(
            "Upstream APKs contain divergent RetroArch revisions: "
            f"{normal_revision} != {aarch64_revision}"
        )
    full_revision = resolver(normal_revision)
    if not full_revision or not re.fullmatch(r"[0-9a-fA-F]{40}", full_revision):
        raise ProvenanceError(
            f"Embedded upstream revision does not resolve to one full commit: {normal_revision}"
        )
    return full_revision.lower()


def ensure_forward_revision(previous_revision, new_revision, is_ancestor):
    if previous_revision and not is_ancestor(previous_revision, new_revision):
        raise ProvenanceError(
            f"Upstream revision rollback rejected: {new_revision} does not descend from {previous_revision}"
        )


def check_processed_pair(date, apk_hashes, state):
    if not state or date != state.get("date"):
        return
    if apk_hashes != state.get("upstream_apk_sha256"):
        raise ProvenanceError(
            f"Upstream replaced already processed nightly {date}; manual review is required"
        )
