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
    if not value:
        return ""
    doi = str(value).strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi.rstrip(" .,;")


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
    identifiers = external_ids.get("external-id", [])
    if isinstance(identifiers, dict):
        identifiers = [identifiers]
    for identifier in identifiers:
        if (identifier.get("external-id-type") or "").lower() == "doi":
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
                part for part in (clean_text(author.get("given")), clean_text(author.get("family"))) if part
            )
            if name:
                names.append(name)
    return names or ["Rakesh Sarwal"]


def existing_file_for_work(doi, put_code):
    """Reuse a file already representing this DOI/ORCID put-code, preventing duplicates."""
    if not os.path.isdir(OUTPUT_DIR):
        return None
    for filename in os.listdir(OUTPUT_DIR):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(OUTPUT_DIR, filename)
        try:
            with open(filepath, encoding="utf-8") as source:
                front_matter = source.read().split("---", 2)
            if len(front_matter) < 3:
                continue
            metadata = front_matter[1]
            file_doi = re.search(r"(?m)^doi:\s*[\"']?([^\"'\n]+)", metadata)
            file_put_code = re.search(r"(?m)^put_code:\s*[\"']?([^\"'\n]+)", metadata)
            if doi and file_doi and normalize_doi(file_doi.group(1)) == doi:
                return filepath
            if put_code and file_put_code and file_put_code.group(1).strip() == str(put_code):
                return filepath
        except OSError as error:
            print(f"Could not inspect {filepath}: {error}")
    return None


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
        venue = clean_text(container[0]) if container else clean_text(crossref.get("publisher"))
    publisher = clean_text(crossref.get("publisher")) or venue
    description = clean_text(work.get("short-description")) or clean_text(crossref.get("abstract"))
    authors = get_authors(work, crossref)
    author_text = ", ".join(authors)
    year = publication_date[:4]
    citation = f"{author_text} ({year}). {title}."
    if venue:
        citation += f" {venue}."
    if doi:
        citation += f" https://doi.org/{doi}"
    paper_url = f"https://doi.org/{doi}" if doi else ""

    filepath = existing_file_for_work(doi, put_code)
    if not filepath:
        filename = f"{publication_date}-{slugify(title)}.md"
        filepath = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(filepath):
            filename = f"{publication_date}-{slugify(title)}-{put_code}.md"
            filepath = os.path.join(OUTPUT_DIR, filename)

    # Keep any existing hand-edited body while refreshing ORCID-sourced metadata.
    body = description
    if os.path.isfile(filepath):
        with open(filepath, encoding="utf-8") as source:
            parts = source.read().split("---", 2)
        if len(parts) == 3:
            body = parts[2].lstrip("\r\n")

    author_lines = "\n".join(f"  - {quote_yaml(author)}" for author in authors)
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
    seen = set()
    for group in data.get("group", []):
        summaries = group.get("work-summary", [])
        for summary in summaries:
            put_code = summary.get("put-code")
            if put_code is None or str(put_code) in seen:
                continue
            seen.add(str(put_code))
            yield summary


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Fetching ORCID works for {ORCID_ID}")
    data = fetch_json(f"{ORCID_API}/{ORCID_ID}/works")
    summaries = list(iter_work_summaries(data))
    print(f"Found {len(summaries)} unique ORCID works")
    seen_dois = set()
    created = updated = skipped = 0

    for summary in summaries:
        put_code = summary["put-code"]
        try:
            work = fetch_json(f"{ORCID_API}/{ORCID_ID}/work/{put_code}")
            doi = get_doi(work)
            if doi and doi in seen_dois:
                print(f"Skipping duplicate ORCID work for DOI {doi} (put-code {put_code})")
                continue
            if doi:
                seen_dois.add(doi)
            path = existing_file_for_work(doi, put_code)
            existed = path is not None
            output_path = create_markdown(work, put_code)
            print(f"{'Updated' if existed else 'Created'}: {os.path.basename(output_path)}")
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
