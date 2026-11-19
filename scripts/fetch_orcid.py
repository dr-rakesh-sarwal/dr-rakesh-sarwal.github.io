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
    """Normalize a title for duplicate checks when a DOI is unavailable."""
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
    return clean_text(
        work.get("title", {}).get("title", {}).get("value")
    ) or "Untitled"


def get_doi(work):
    external_ids = work.get("external-ids") or {}
    identifiers = external_ids.get("external-id") or []
    if isinstance(identifiers, dict):
        identifiers = [identifiers]

    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue
        if (identifier.get("external-id-type") or "").casefold() == "doi":
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
        credit = clean_text((contributor.get("credit-name") or {}).get("value"))
        if not credit:
            given = clean_text((contributor.get("given-names") or {}).get("value"))
            family = clean_text((contributor.get("family-name") or {}).get("value"))
            credit = " ".join(part for part in (given, family) if part)

        if credit and credit.casefold() not in {name.casefold() for name in names}:
            names.append(credit)

    if not names:
        for author in crossref.get("author", []):
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
    """Read a scalar front-matter value, including quoted YAML strings."""
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


def existing_file_for_work(doi, put_code, title):
    """
    Return a file already representing this DOI, put-code, or DOI-less title.

    A title match is only used when either the incoming record or existing file
    has no DOI, so publications with different DOIs are not merged by title.
    """
    if not os.path.isdir(OUTPUT_DIR):
        return None

    wanted_doi = normalize_doi(doi)
    wanted_put_code = str(put_code).strip() if put_code is not None else ""
    wanted_title = normalize_title(title)
    title_match_without_doi = None

    for filename in sorted(os.listdir(OUTPUT_DIR)):
        if not filename.lower().endswith(".md"):
            continue

        filepath = os.path.join(OUTPUT_DIR, filename)
        try:
            with open(filepath, encoding="utf-8") as source:
                parts = source.read().split("---", 2)

            if len(parts) < 3:
                continue

            metadata = parts[1]
            file_doi = normalize_doi(read_front_matter_value(metadata, "doi"))
            file_put_code = read_front_matter_value(metadata, "put_code").strip()
            file_title = normalize_title(read_front_matter_value(metadata, "title"))

            if wanted_doi and file_doi == wanted_doi:
                return filepath

            if wanted_put_code and file_put_code == wanted_put_code:
                return filepath

            if (
                wanted_title
                and file_title == wanted_title
                and (not wanted_doi or not file_doi)
                and title_match_without_doi is None
            ):
                title_match_without_doi = filepath

        except (OSError, UnicodeDecodeError) as error:
            print(f"Could not inspect {filepath}: {error}")

    return title_match_without_doi


def create_markdown(work, put_code):
    title = get_title(work)
    doi = get_doi(work)
    crossref = fetch_crossref(doi)

    publication_date = (
        date_from_orcid(work.get("publication-date"))
        or crossref_date(crossref)
        or "2000-01-01"
    )

    venue = clean_text((work.get("journal-title") or {}).get("value"))
    if not venue:
        container = crossref.get("container-title") or []
        venue = (
            clean_text(container[0])
            if container
            else clean_text(crossref.get("publisher"))
        )

    publisher = clean_text(crossref.get("publisher")) or venue
    description = (
        clean_text(work.get("short-description"))
        or clean_text(crossref.get("abstract"))
    )
    authors = get_authors(work, crossref)
    author_text = ", ".join(authors)
    year = publication_date[:4]

    citation = f"{author_text} ({year}). {title}."
    if venue:
        citation += f" {venue}."
    if doi:
        citation += f" https://doi.org/{doi}"

    paper_url = f"https://doi.org/{doi}" if doi else ""

    filepath = existing_file_for_work(doi, put_code, title)
    if not filepath:
        filename = f"{publication_date}-{slugify(title)}.md"
        filepath = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(filepath):
            filename = f"{publication_date}-{slugify(title)}-{put_code}.md"
            filepath = os.path.join(OUTPUT_DIR, filename)

    # Keep any existing hand-edited body while refreshing ORCID-sourced metadata.
    body = description
    if os.path.isfile(filepath):
        try:
            with open(filepath, encoding="utf-8") as source:
                parts = source.read().split("---", 2)
            if len(parts) == 3:
                body = parts[2].lstrip("\r\n")
        except (OSError, UnicodeDecodeError) as error:
            print(f"Could not preserve body from {filepath}: {error}")

    author_lines = "\n".join(
        f"  - {quote_yaml(author)}" for author in authors
    )
    content = f'''---
title: {quote_yaml(title)}
collection: publications
put_code: {quote_yaml(put_code)}
permalink: /publication/{publication_date}-{slugify(title)}
date: {publication_date}
venue: {quote_yaml(venue)}
publisher: {quote_yaml(publisher)}
doi: {quote_yaml(doi)}
paperurl: {quote_yaml(paper_url)}
excerpt: {quote_yaml(description[:500])}
citation: {quote_yaml(citation)}
authors:
{author_lines}
keywords: {quote_yaml("")}
language: "en"
---
{body.rstrip()}\n'''

    with open(filepath, "w", encoding="utf-8") as target:
        target.write(content)

    return filepath


def iter_work_summaries(data):
    """Yield each ORCID put-code once."""
    seen_put_codes = set()

    for group in data.get("group", []):
        summaries = group.get("work-summary", [])
        for summary in summaries:
            put_code = summary.get("put-code")
            if put_code is None:
                continue

            put_code_key = str(put_code).strip()
            if put_code_key in seen_put_codes:
                continue

            seen_put_codes.add(put_code_key)
            yield summary


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Fetching ORCID works for {ORCID_ID}")

    data = fetch_json(f"{ORCID_API}/{ORCID_ID}/works")
    summaries = list(iter_work_summaries(data))
    print(f"Found {len(summaries)} unique ORCID works")

    seen_dois = set()
    seen_titles_without_doi = set()
    created = updated = skipped = 0

    for summary in summaries:
        put_code = summary["put-code"]

        try:
            work = fetch_json(f"{ORCID_API}/{ORCID_ID}/work/{put_code}")
            external_ids = work.get("external-ids") or {}

            if external_ids.get("external-id") is None:
                print(
                    "ORCID work has no external identifiers: "
                    f"put-code {put_code}; title: {get_title(work)}"
                )

            doi = get_doi(work)
            title = get_title(work)
            title_key = normalize_title(title)

            if doi:
                if doi in seen_dois:
                    print(
                        f"Skipping duplicate ORCID work for DOI {doi} "
                        f"(put-code {put_code})"
                    )
                    continue
                seen_dois.add(doi)
            elif title_key:
                if title_key in seen_titles_without_doi:
                    print(
                        f"Skipping duplicate ORCID work without DOI: "
                        f"{title} (put-code {put_code})"
                    )
                    continue
                seen_titles_without_doi.add(title_key)

            existing_path = existing_file_for_work(doi, put_code, title)
            existed = existing_path is not None

            output_path = create_markdown(work, put_code)
            print(
                f"{'Updated' if existed else 'Created'}: "
                f"{os.path.basename(output_path)}"
            )

            if existed:
                updated += 1
            else:
                created += 1

        except (requests.RequestException, ValueError, KeyError) as error:
            skipped += 1
            print(f"Skipped ORCID put-code {put_code}: {error}")

    print(f"Finished: {created} created, {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    main()
