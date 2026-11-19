import json
import os
import re
from datetime import date
from urllib.parse import quote

import requests


ORCID_ID = "0000-0001-8345-2640"
OUTPUT_DIR = "_publications"
ORCID_API = "https://pub.orcid.org/v3.0"
CROSSREF_API = "https://api.crossref.org/works"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "academic.lifequality.org.in/1.0 (mailto:equal.society@gmail.com)",
}


def fetch_json(url, params=None):
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def normalize_doi(value):
    """Normalize DOI URLs, prefixes, whitespace, and case for comparison."""
    if not value:
        return ""

    doi = str(value).strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi.strip().strip("\"'").rstrip(" .,;").casefold()


def normalize_title(value):
    """Normalize punctuation, spacing, and case for title comparisons."""
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def quote_yaml(value):
    return json.dumps(str(value or "").strip(), ensure_ascii=False)


def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", value).strip()


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80].rstrip("-") or "untitled"


def get_title(work):
    title_data = work.get("title") or {}
    title = (title_data.get("title") or {}).get("value")
    return clean_text(title) or "Untitled"


def get_doi(work):
    external_ids = work.get("external-ids") or {}
    identifiers = external_ids.get("external-id") or []

    if isinstance(identifiers, dict):
        identifiers = [identifiers]

    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue

        identifier_type = str(
            identifier.get("external-id-type") or ""
        ).casefold()

        if identifier_type == "doi":
            return normalize_doi(identifier.get("external-id-value"))

    return ""


def date_from_orcid(publication_date):
    if not publication_date:
        return ""

    year = (publication_date.get("year") or {}).get("value")
    month = (publication_date.get("month") or {}).get("value") or 1
    day = (publication_date.get("day") or {}).get("value") or 1

    try:
        return date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        try:
            return date(int(year), 1, 1).isoformat()
        except (TypeError, ValueError):
            return ""


def fetch_crossref(doi):
    if not doi:
        return {}

    try:
        result = fetch_json(
            f"{CROSSREF_API}/{quote(doi, safe='')}",
            params={"mailto": "equal.society@gmail.com"},
        )
        return result.get("message", {})
    except requests.RequestException as error:
        print(f"Crossref lookup unavailable for {doi}: {error}")
        return {}


def crossref_date(metadata):
    for key in ("published", "published-print", "published-online", "issued"):
        parts = (metadata.get(key) or {}).get("date-parts") or []
        if not parts or not parts[0]:
            continue

        try:
            values = parts[0]
            return date(
                int(values[0]),
                int(values[1]) if len(values) > 1 else 1,
                int(values[2]) if len(values) > 2 else 1,
            ).isoformat()
        except (TypeError, ValueError):
            continue

    return ""


def get_authors(work, crossref):
    names = []
    contributors = (work.get("contributors") or {}).get("contributor", [])

    if isinstance(contributors, dict):
        contributors = [contributors]

    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue

        credit = clean_text(
            (contributor.get("credit-name") or {}).get("value")
        )

        if not credit:
            given = clean_text(
                (contributor.get("given-names") or {}).get("value")
            )
            family = clean_text(
                (contributor.get("family-name") or {}).get("value")
            )
            credit = " ".join(part for part in (given, family) if part)

        if credit and credit.casefold() not in {
            name.casefold() for name in names
        }:
            names.append(credit)

    if not names:
        for author in crossref.get("author", []) or []:
            if not isinstance(author, dict):
                continue

            name = clean_text(author.get("name")) or " ".join(
                part
                for part in (
                    clean_text(author.get("given")),
                    clean_text(author.get("family")),
                )
                if part
            )

            if name:
                names.append(name)

    return names or ["Rakesh Sarwal"]


def read_front_matter_value(metadata, field):
    """Read a scalar front-matter value, including quoted strings."""
    match = re.search(
        rf"(?m)^{re.escape(field)}:\s*(.*?)\s*$",
        metadata,
    )
    if not match:
        return ""

    value = match.group(1).strip()
    if not value:
        return ""

    if value.startswith('"'):
        try:
            return str(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            return value.strip('"')

    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")

    return value


def read_publication_metadata(filepath):
    """Return parsed scalar metadata for a publication Markdown file."""
    with open(filepath, encoding="utf-8") as source:
        parts = source.read().split("---", 2)

    if len(parts) < 3:
        return {}

    metadata = parts[1]
    return {
        "doi": read_front_matter_value(metadata, "doi"),
        "put_code": read_front_matter_value(metadata, "put_code").strip(),
        "title": read_front_matter_value(metadata, "title"),
        "excerpt": read
