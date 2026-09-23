import html
import json
import os
import re
from datetime import date
from urllib.parse import quote

import requests


ORCID_ID = "0000-0001-8345-2640"
OUTPUT_DIR = "_publications"

ORCID_API = "https://pub.orcid.org/v3.0"
DOI_API = "https://doi.org"
CROSSREF_API = "https://api.crossref.org/works"

USER_AGENT = (
    "academic.lifequality.org.in publication synchronisation "
    "(mailto:sarwalr@gmail.com)"
)

ORCID_HEADERS = {
    "Accept": "application/json",
    "User-Agent": USER_AGENT,
}

DOI_HEADERS = {
    "Accept": "application/vnd.citationstyles.csl+json",
    "User-Agent": USER_AGENT,
}

CROSSREF_HEADERS = {
    "Accept": "application/json",
    "User-Agent": USER_AGENT,
}


def fetch_json(url, headers):
    """Fetch JSON from an HTTP endpoint."""
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_orcid_publications(orcid_id):
    """Fetch works registered in the ORCID record."""
    url = f"{ORCID_API}/{orcid_id}/works"
    return fetch_json(url, ORCID_HEADERS)


def fetch_work_details(orcid_id, put_code):
    """Fetch detailed metadata for one ORCID work."""
    url = f"{ORCID_API}/{orcid_id}/work/{put_code}"
    return fetch_json(url, ORCID_HEADERS)


def normalise_doi(value):
    """Convert a DOI or DOI URL to a plain DOI."""
    if not value:
        return ""

    doi = str(value).strip()

    doi = re.sub(
        r"^https?://(dx\.)?doi\.org/",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    doi = doi.strip()
    doi = doi.rstrip(" .,;")

    return doi


def get_orcid_doi(external_ids):
    """Extract a DOI from ORCID external identifiers."""
    if not external_ids:
        return ""

    for external_id in external_ids.get("external-id", []):
        identifier_type = (
            external_id.get("external-id-type", "").strip().lower()
        )

        if identifier_type == "doi":
            return normalise_doi(
                external_id.get("external-id-value", "")
            )

    return ""


def get_publication_date(publication_date):
    """Convert an ORCID date object to YYYY-MM-DD."""
    if not publication_date:
        return "1900-01-01"

    year = publication_date.get("year", {}).get("value")
    month = publication_date.get("month", {}).get("value", "01")
    day = publication_date.get("day", {}).get("value", "01")

    year = str(year or "1900")
    month = str(month or "01").zfill(2)
    day = str(day or "01").zfill(2)

    try:
        date(int(year), int(month), int(day))
        return f"{year}-{month}-{day}"
    except ValueError:
        return f"{year}-01-01"


def get_date_from_parts(date_parts):
    """Convert CSL JSON date-parts to YYYY-MM-DD."""
    if not date_parts:
        return ""

    try:
        year = int(date_parts[0])
        month = int(date_parts[1]) if len(date_parts) > 1 else 1
        day = int(date_parts[2]) if len(date_parts) > 2 else 1

        date(year, month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except (TypeError, ValueError, IndexError):
        return ""


def clean_text(value):
    """Clean HTML and excess whitespace from a metadata value."""
    if not value:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def yaml_string(value):
    """Quote a value safely for YAML."""
    return json.dumps(
        str(value or "").strip(),
        ensure_ascii=False,
    )


def sanitize_filename(title):
    """Convert a publication title to a safe filename slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)

    return slug[:80].strip("-") or "untitled"


def initials_from_given_names(given_names):
    """Convert given names to initials."""
    words = re.findall(
        r"[A-Za-zÀ-ÖØ-öø-ÿ]+",
        given_names or "",
    )

    return " ".join(f"{word[0].upper()}." for word in words)


def format_author_name(name):
    """
    Convert a name to APA-like format.

    Examples:
      Rakesh Sarwal       -> Sarwal, R.
      Nitish Kumar       -> Kumar, N.
      Rakesh Kumar Sarwal -> Sarwal, R. K.
    """
    name = clean_text(name)

    if not name:
        return ""

    if "," in name:
        family_name, given_names = [
            part.strip()
            for part in name.split(",", 1)
        ]

        initials = initials_from_given_names(given_names)
        return f"{family_name}, {initials}".strip(", ")

    parts = name.split()

    if len(parts) == 1:
        return parts[0]

    family_name = parts[-1]
    given_names = " ".join(parts[:-1])
    initials = initials_from_given_names(given_names)

    return f"{family_name}, {initials}".strip(", ")


def format_csl_author(author):
    """Format one author from CSL JSON metadata."""
    literal = clean_text(author.get("literal", ""))

    if literal:
        return literal

    family_name = clean_text(author.get("family", ""))
    given_names = clean_text(author.get("given", ""))

    if family_name:
        initials = initials_from_given_names(given_names)
        return f"{family_name}, {initials}".strip(", ")

    return format_author_name(given_names)


def deduplicate_authors(authors):
    """Remove duplicate authors while preserving order."""
    result = []
    seen = set()

    for author in authors:
        normalised = re.sub(r"\s+", " ", author).strip()
        key = normalised.casefold()

        if normalised and key not in seen:
            result.append(normalised)
            seen.add(key)

    return result


def fetch_doi_metadata(doi):
    """
    Fetch raw DOI metadata using DOI content negotiation.

    DOI content negotiation commonly returns CSL JSON containing:
    title, author, issued, container-title, DOI, and URL.
    """
    if not doi:
        return {}

    encoded_doi = quote(doi, safe="")
    url = f"{DOI_API}/{encoded_doi}"

    try:
        metadata = fetch_json(url, DOI_HEADERS)
        print(f"   DOI metadata retrieved: {doi}")
        return metadata

    except requests.RequestException as error:
        print(f"⚠️  DOI metadata lookup failed for {doi}: {error}")
        return {}


def fetch_crossref_metadata(doi):
    """Fallback: fetch metadata directly from Crossref."""
    if not doi:
        return {}

    encoded_doi = quote(doi, safe="")
    url = f"{CROSSREF_API}/{encoded_doi}"

    try:
        data = fetch_json(url, CROSSREF_HEADERS)
        return data.get("message", {})

    except requests.RequestException as error:
        print(f"⚠️  Crossref lookup failed for {doi}: {error}")
        return {}


def get_doi_authors(doi_metadata):
    """Extract authors from DOI content-negotiation metadata."""
    authors = []

    for author in doi_metadata.get("author", []):
        formatted = format_csl_author(author)

        if formatted:
            authors.append(formatted)

    return deduplicate_authors(authors)


def get_crossref_authors(crossref_metadata):
    """Extract authors from Crossref metadata."""
    authors = []

    for author in crossref_metadata.get("author", []):
        literal = clean_text(author.get("name", ""))

        if literal:
            formatted = literal
        else:
            family_name = clean_text(author.get("family", ""))
            given_names = clean_text(author.get("given", ""))

            if family_name:
                initials = initials_from_given_names(given_names)
                formatted = f"{family_name}, {initials}".strip(", ")
            else:
                formatted = format_author_name(given_names)

        if formatted:
            authors.append(formatted)

    return deduplicate_authors(authors)


def get_orcid_authors(work):
    """Extract authors from ORCID contributor metadata."""
    authors = []

    contributors = (
        work.get("contributors", {})
        .get("contributor", [])
    )

    if isinstance(contributors, dict):
        contributors = [contributors]

    for contributor in contributors:
        credit_name = contributor.get("credit-name", {})
        name = clean_text(credit_name.get("value", ""))

        if name:
            authors.append(format_author_name(name))
            continue

        given_names = clean_text(
            contributor.get("given-names", {}).get("value", "")
        )
        family_name = clean_text(
            contributor.get("family-name", {}).get("value", "")
        )

        if given_names or family_name:
            authors.append(
                format_author_name(
                    f"{given_names} {family_name}".strip()
                )
            )

    return deduplicate_authors(authors)


def get_title_from_orcid(work):
    """Extract a title from ORCID metadata."""
    title = (
        work.get("title", {})
        .get("title", {})
        .get("value", "")
    )

    return clean_text(title) or "Untitled"


def get_venue_from_orcid(work):
    """Extract the venue from ORCID metadata."""
    venue = work.get("journal-title", {}).get("value", "")
    return clean_text(venue)


def get_description_from_orcid(work):
    """Extract the ORCID short description."""
    return clean_text(work.get("short-description", ""))


def get_authors(work, doi_metadata, crossref_metadata):
    """
    Select the best available author list.

    Priority:
      1. DOI metadata
      2. Crossref metadata
      3. ORCID contributors
      4. Dr. Sarwal fallback
    """
    doi_authors = get_doi_authors(doi_metadata)

    if doi_authors:
        return doi_authors

    crossref_authors = get_crossref_authors(crossref_metadata)

    if crossref_authors:
        return crossref_authors

    orcid_authors = get_orcid_authors(work)

    if orcid_authors:
        return orcid_authors

    return ["Sarwal, R."]


def format_authors_apa(authors):
    """Format authors as a compact APA-style string."""
    if not authors:
        return "Sarwal, R."

    if len(authors) == 1:
        return authors[0]

    if len(authors) == 2:
        return f"{authors[0]}, & {authors[1]}"

    if len(authors) <= 20:
        return ", ".join(authors[:-1]) + f", & {authors[-1]}"

    return ", ".join(authors[:19]) + ", ... " + authors[-1]


def get_doi_title(doi_metadata, crossref_metadata):
    """Get a title from DOI metadata or Crossref."""
    titles = doi_metadata.get("title", [])

    if titles:
        return clean_text(titles[0])

    titles = crossref_metadata.get("title", [])

    if titles:
        return clean_text(titles[0])

    return ""


def get_doi_venue(doi_metadata, crossref_metadata):
    """Get the journal or repository name from DOI metadata."""
    venue = doi_metadata.get("container-title", "")

    if isinstance(venue, list):
        venue = venue[0] if venue else ""

    if venue:
        return clean_text(venue)

    venue = crossref_metadata.get("container-title", [])

    if isinstance(venue, list):
        venue = venue[0] if venue else ""

    return clean_text(venue)


def get_doi_date(doi_metadata, crossref_metadata):
    """Get publication date from DOI metadata or Crossref."""
    issued = doi_metadata.get("issued", {})
    publication_date = get_date_from_parts(
        issued.get("date-parts", [[]])[0]
    )

    if publication_date:
        return publication_date

    for field in ("published-print", "published-online", "issued"):
        issued = crossref_metadata.get(field, {})
        publication_date = get_date_from_parts(
            issued.get("date-parts", [[]])[0]
        )

        if publication_date:
            return publication_date

    return ""


def create_markdown(work, output_dir):
    """Create one Jekyll publication file."""
    orcid_title = get_title_from_orcid(work)
    doi = get_orcid_doi(work.get("external-ids"))

    doi_metadata = fetch_doi_metadata(doi)
    crossref_metadata = {}

    if doi and not doi_metadata:
        crossref_metadata = fetch_crossref_metadata(doi)

    if doi_metadata and doi:
        crossref_metadata = fetch_crossref_metadata(doi)

    title = (
        get_doi_title(doi_metadata, crossref_metadata)
        or orcid_title
    )

    publication_date = (
        get_doi_date(doi_metadata, crossref_metadata)
        or get_publication_date(work.get("publication-date"))
    )

    venue = (
        get_doi_venue(doi_metadata, crossref_metadata)
        or get_venue_from_orcid(work)
    )

    authors = get_authors(
        work,
        doi_metadata,
        crossref_metadata,
    )

    description = get_description_from_orcid(work)
    authors_apa = format_authors_apa(authors)

    citation = f"{authors_apa} ({publication_date[:4]}). {title}."

    if venue:
        citation += f" {venue}."

    if doi:
        citation += f" https://doi.org/{doi}"

    slug = sanitize_filename(title)
    filename = f"{publication_date}-{slug}.md"
    filepath = os.path.join(output_dir, filename)

    authors_yaml = "\n".join(
        f"  - {yaml_string(author)}"
        for author in authors
    )

    paper_url = f"https://doi.org/{doi}" if doi else ""

    content = f"""---
title: {yaml_string(title)}
collection: publications
permalink: /publication/{publication_date}-{slug}
date: {publication_date}
venue: {yaml_string(venue)}
authors:
{authors_yaml}
doi: {yaml_string(doi)}
paperurl: {yaml_string(paper_url)}
citation: {yaml_string(citation)}
---

{description}
"""

    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)

    print(f"✅ Created: {filename}")
    print(f"   DOI: {doi or 'none'}")
    print(f"   Authors: {'; '.join(authors)}")

    return filename


def main():
    print(f"🔍 Fetching publications for ORCID: {ORCID_ID}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # This deletes every Markdown file in _publications.
    # Use this only when the directory contains ORCID-synchronised files.
    for filename in os.listdir(OUTPUT_DIR):
        filepath = os.path.join(OUTPUT_DIR, filename)

        if filename.endswith(".md") and os.path.isfile(filepath):
            os.remove(filepath)
            print(f"🗑️  Removed old file: {filename}")

    data = fetch_orcid_publications(ORCID_ID)
    works_group = data.get("group", [])

    print(f"📚 Found {len(works_group)} ORCID publication groups\n")

    created = []

    for group in works_group:
        work_summaries = group.get("work-summary", [])

        if not work_summaries:
            continue

        summary = work_summaries[0]
        put_code = summary.get("put-code")

        if not put_code:
            print("⚠️  Skipped work without a put-code")
            continue

        try:
            work = fetch_work_details(ORCID_ID, put_code)
            filename = create_markdown(work, OUTPUT_DIR)
            created.append(filename)

        except requests.RequestException as error:
            print(
                f"⚠️  Request failed for ORCID put-code "
                f"{put_code}: {error}"
            )

        except Exception as error:
            print(f"⚠️  Skipped ORCID work {put_code}: {error}")

    print(f"\n🎉 Done! Created {len(created)} publication files.")


if __name__ == "__main__":
    main()
