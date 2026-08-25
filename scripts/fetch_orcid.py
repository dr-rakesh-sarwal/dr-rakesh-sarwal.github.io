import os
import re
import requests

ORCID_ID = "0000-0001-8345-2640"
OUTPUT_DIR = "_publications"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "academic.lifequality.org.in/1.0 (mailto:sarwalr@gmail.com)"
}


def fetch_orcid_publications(orcid_id):
    """Fetch all works from ORCID."""
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_work_details(orcid_id, put_code):
    """Fetch detailed metadata for one ORCID work."""
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/work/{put_code}"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_crossref_metadata(doi):
    """Fetch metadata from Crossref using DOI."""
    if not doi:
        return {}

    url = f"https://api.crossref.org/works/{doi}"

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params={"mailto": "sarwalr@gmail.com"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("message", {})
    except Exception as e:
        print(f"Crossref lookup failed for {doi}: {e}")
        return {}


def clean_crossref_abstract(text):
    """Convert Crossref JATS abstract into plain text."""
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sanitize_filename(title):
    title = title.lower()
    title = re.sub(r"[^a-z0-9\\s-]", "", title)
    title = re.sub(r"\\s+", "-", title.strip())
    return title[:60]


def get_doi(external_ids):
    if not external_ids:
        return None

    for ext in external_ids.get("external-id", []):
        if ext.get("external-id-type") == "doi":
            return ext.get("external-id-value")

    return None


def get_year(pub_date):
    if pub_date and pub_date.get("year"):
        return pub_date["year"].get("value", "2000")
    return "2000"


def get_full_date(pub_date):
    """Return YYYY-MM-DD from ORCID."""
    year = pub_date.get("year", {}).get("value", "2000") if pub_date else "2000"
    month = pub_date.get("month", {}).get("value", "01") if pub_date else "01"
    day = pub_date.get("day", {}).get("value", "01") if pub_date else "01"

    month = str(month).zfill(2)
    day = str(day).zfill(2)

    return f"{year}-{month}-{day}"


def get_crossref_date(crossref):
    """Prefer Crossref's publication date if available."""
    for field in ("published-print", "published-online", "created"):
        if field in crossref:
            parts = crossref[field]["date-parts"][0]
            y = parts[0]
            m = parts[1] if len(parts) > 1 else 1
            d = parts[2] if len(parts) > 2 else 1
            return f"{y}-{m:02d}-{d:02d}"

    return None


def create_markdown(work, output_dir):
    """Create one publication markdown file."""

    title = "Untitled"

    if work.get("title") and work["title"].get("title"):
        title = work["title"]["title"].get("value", "Untitled")

    year = get_year(work.get("publication-date"))
    pub_date = get_full_date(work.get("publication-date"))

    venue = ""
    if work.get("journal-title") and work["journal-title"].get("value"):
        venue = work["journal-title"]["value"]

    doi = get_doi(work.get("external-ids"))
    paper_url = f"https://doi.org/{doi}" if doi else ""

    crossref = fetch_crossref_metadata(doi)

    if not venue and crossref.get("container-title"):
        venue = crossref["container-title"][0]

    publisher = crossref.get("publisher", "")

    crossref_date = get_crossref_date(crossref)
    if crossref_date:
        pub_date = crossref_date

    description = work.get("short-description") or clean_crossref_abstract(
        crossref.get("abstract", "")
    )

    citation = f"Sarwal, R. ({year}). {title}."

    if venue:
        citation += f" {venue}."

    if doi:
        citation += f" https://doi.org/{doi}"

    filename = f"{year}-{sanitize_filename(title)}.md"
    filepath = os.path.join(output_dir, filename)

    frontmatter = f"""---
title: "{title.replace('"', "'")}"
collection: publications
permalink: /publication/{year}-{sanitize_filename(title)}
date: {pub_date}
venue: "{venue.replace('"', "'")}"
publisher: "{publisher.replace('"', "'")}"
doi: "{doi or ''}"
paperurl: "{paper_url}"
excerpt: "{description.replace('"', "'")[:500]}"
citation: "{citation.replace('"', "'")}"
---
"""

    body = description if description else ""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter)
        f.write("\\n")
        f.write(body)
        f.write("\\n")

    print(f"Created: {filename}")


def main():
    print(f"Fetching ORCID works for {ORCID_ID}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".md"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    data = fetch_orcid_publications(ORCID_ID)

    groups = data.get("group", [])

    print(f"Found {len(groups)} works")

    created = 0

    for group in groups:
        summaries = group.get("work-summary", [])

        if not summaries:
            continue

        put_code = summaries[0].get("put-code")

        try:
            work = fetch_work_details(ORCID_ID, put_code)
            create_markdown(work, OUTPUT_DIR)
            created += 1
        except Exception as e:
            print(f"Skipped {put_code}: {e}")

    print(f"Done. Generated {created} publication files.")


if __name__ == "__main__":
    main()
