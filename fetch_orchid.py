import json
import os
import re
from datetime import date

import requests


ORCID_ID = "0000-0001-8345-2640"
OUTPUT_DIR = "_publications"
ORCID_API = "https://pub.orcid.org/v3.0"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "academic.lifequality.org.in ORCID publication synchronisation",
}


def fetch_json(url):
    """Fetch JSON from the ORCID public API."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_orcid_publications(orcid_id):
    """Fetch the works summary for an ORCID record."""
    url = f"{ORCID_API}/{orcid_id}/works"
    return fetch_json(url)


def fetch_work_details(orcid_id, put_code):
    """Fetch detailed information for one ORCID work."""
    url = f"{ORCID_API}/{orcid_id}/work/{put_code}"
    return fetch_json(url)


def yaml_string(value):
    """Represent a string safely in YAML using JSON quoting."""
    return json.dumps(str(value or "").strip(), ensure_ascii=False)


def sanitize_filename(title):
    """Convert a publication title to a safe filename slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-") or "untitled"


def get_doi(external_ids):
    """Extract the DOI from ORCID external identifiers."""
    if not external_ids:
        return ""

    for external_id in external_ids.get("external-id", []):
        if external_id.get("external-id-type", "").lower() == "doi":
            value = external_id.get("external-id-value", "")
            return value.strip()

    return ""


def get_publication_date(publication_date):
    """Return the best available publication date as YYYY-MM-DD."""
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


def initials_from_given_names(given_names):
    """Convert given names to initials."""
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", given_names or "")
    return " ".join(f"{word[0].upper()}." for word in words if word)


def format_author_name(name):
    """
    Convert an ORCID contributor name to an APA-like format.

    Handles:
    - 'Rakesh Sarwal'       -> 'Sarwal, R.'
    - 'Sarwal, Rakesh'      -> 'Sarwal, R.'
    - 'Rakesh Kumar Sarwal' -> 'Sarwal, R. K.'
    """
    name = re.sub(r"\s+", " ", (name or "").strip())

    if not name:
        return ""

    if "," in name:
        family_name, given_names = [part.strip() for part in name.split(",", 1)]
        initials = initials_from_given_names(given_names)
        return f"{family_name}, {initials}".strip(", ")

    parts = name.split()

    if len(parts) == 1:
        return parts[0]

    family_name = parts[-1]
    given_names = " ".join(parts[:-1])
    initials = initials_from_given_names(given_names)

    return f"{family_name}, {initials}".strip(", ")


def get_authors(work):
    """
    Extract authors from the ORCID work contributors.

    ORCID normally provides contributor names under:
    contributors -> contributor -> credit-name -> value
    """
    authors = []
    contributors = work.get("contributors", {}).get("contributor", [])

    for contributor in contributors:
        credit_name = contributor.get("credit-name", {})
        name = credit_name.get("value", "").strip()

        if not name:
            continue

        author = format_author_name(name)

        if author and author not in authors:
            authors.append(author)

    # Ensure the ORCID record owner appears if ORCID has no contributor data.
    sarwal_names = {
        "Sarwal, R.",
        "Rakesh Sarwal",
        "Sarwal, Rakesh",
    }

    if not any(author in sarwal_names for author in authors):
        authors.insert(0, "Sarwal, R.")

    return authors


def format_authors_apa(authors):
    """Format an author list in a compact APA-style form."""
    if not authors:
        return "Sarwal, R."

    if len(authors) == 1:
        return authors[0]

    if len(authors) == 2:
        return f"{authors[0]}, & {authors[1]}"

    if len(authors) <= 20:
        return ", ".join(authors[:-1]) + f", & {authors[-1]}"

    return ", ".join(authors[:19]) + ", ... " + authors[-1]


def get_title(work):
    """Extract the publication title."""
    title_data = work.get("title", {}).get("title", {})
    return title_data.get("value", "Untitled").strip() or "Untitled"


def get_venue(work):
    """Extract the journal or publication venue."""
    journal_title = work.get("journal-title", {})
    return journal_title.get("value", "").strip()


def get_description(work):
    """Extract the ORCID short description or return an empty string."""
    return (work.get("short-description") or "").strip()


def create_markdown(work, output_dir):
    """Create one Jekyll publication file from an ORCID work."""
    title = get_title(work)
    publication_date = get_publication_date(work.get("publication-date"))
    publication_year = publication_date[:4]
    venue = get_venue(work)
    description = get_description(work)

    doi = get_doi(work.get("external-ids"))
    paper_url = f"https://doi.org/{doi}" if doi else ""

    authors = get_authors(work)
    authors_apa = format_authors_apa(authors)

    citation = f"{authors_apa} ({publication_year}). {title}."

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

    content = f"""---
title: {yaml_string(title)}
collection: publications
permalink: /publication/{publication_date}-{slug}
date: {publication_date}
venue: {yaml_string(venue)}
authors:
{authors_yaml}
paperurl: {yaml_string(paper_url)}
citation: {yaml_string(citation)}
---

{description}
"""

    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)

    print(f"✅ Created: {filename}")
    print(f"   Authors: {', '.join(authors)}")

    return filename


def main():
    print(f"🔍 Fetching publications for ORCID: {ORCID_ID}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # This removes all existing Markdown files in _publications.
    # Keep this only if _publications contains exclusively ORCID-generated files.
    for filename in os.listdir(OUTPUT_DIR):
        filepath = os.path.join(OUTPUT_DIR, filename)

        if filename.endswith(".md") and os.path.isfile(filepath):
            os.remove(filepath)
            print(f"🗑️  Removed old file: {filename}")

    data = fetch_orcid_publications(ORCID_ID)
    works_group = data.get("group", [])

    print(f"📚 Found {len(works_group)} publication groups\n")

    created = []

    for group in works_group:
        work_summaries = group.get("work-summary", [])

        if not work_summaries:
            continue

        # Select the first/latest summary returned by ORCID.
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
            print(f"⚠️  ORCID request failed for put-code {put_code}: {error}")

        except Exception as error:
            print(f"⚠️  Skipped work {put_code}: {error}")

    print(f"\n🎉 Done! Created {len(created)} publication files.")


if __name__ == "__main__":
    main()
