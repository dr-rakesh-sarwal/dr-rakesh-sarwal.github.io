import os
import re
import requests

ORCID_ID = "0000-0001-8345-2640"
OUTPUT_DIR = "_publications"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "academic.lifequality.org.in/1.0 (mailto:equal.society@gmail.com)"
}


# ---------- ORCID ----------

def fetch_orcid_publications(orcid_id):
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_work_details(orcid_id, put_code):
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/work/{put_code}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------- Crossref ----------

def fetch_crossref_metadata(doi):
    if not doi:
        return {}

    url = f"https://api.crossref.org/works/{doi}"

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            params={"mailto": "equal.society@gmail.com"},
            timeout=30
        )
        r.raise_for_status()
        return r.json().get("message", {})
    except Exception:
        return {}


# ---------- Helpers ----------

def sanitize_filename(title):
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s-]", "", title)
    title = re.sub(r"\s+", "-", title.strip())
    return title[:60]


def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_doi(external_ids):
    if not external_ids:
        return None

    for ext in external_ids.get("external-id", []):
        if ext.get("external-id-type") == "doi":
            return ext.get("external-id-value")

    return None


def get_orcid_date(pub_date):
    """YYYY-MM-DD from ORCID"""
    if not pub_date:
        return "2000-01-01"

    year = pub_date.get("year", {}).get("value", "2000")
    month = pub_date.get("month", {}).get("value", "01")
    day = pub_date.get("day", {}).get("value", "01")

    return f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"


def get_best_date(orcid_date, crossref):
    """
    Prefer Crossref date.
    Fallback to ORCID.
    """

    for field in (
        "published",
        "published-print",
        "published-online",
        "issued",
        "created",
    ):
        if field in crossref:
            parts = crossref[field]["date-parts"][0]

            year = parts[0]
            month = parts[1] if len(parts) > 1 else 1
            day = parts[2] if len(parts) > 2 else 1

            return f"{year}-{month:02d}-{day:02d}"

    return orcid_date


# ---------- Generator ----------

def create_markdown(work, output_dir):

    title = work.get("title", {}).get("title", {}).get("value", "Untitled")

    put_code = work.get("put-code")

    orcid_date = get_orcid_date(work.get("publication-date"))

    year = orcid_date[:4]

    venue = work.get("journal-title", {}).get("value", "")

    doi = get_doi(work.get("external-ids"))

    paper_url = f"https://doi.org/{doi}" if doi else ""

    crossref = fetch_crossref_metadata(doi)

    date = get_best_date(orcid_date, crossref)

    container = crossref.get("container-title")

    if not venue and isinstance(container, list) and container:
        venue = container[0]

    publisher = crossref.get("publisher", "")

    if not venue:
        venue = publisher

    description = clean_text(
        work.get("short-description")
        or crossref.get("abstract", "")
    )

    citation = f"Sarwal, R. ({year}). {title}."

    if venue:
        citation += f" {venue}."

    if doi:
        citation += f" https://doi.org/{doi}"

    filename = f"{year}-{sanitize_filename(title)}.md"

    filepath = os.path.join(output_dir, filename)

    content = f"""---
title: "{title.replace('"', "'")}"
collection: publications
put_code: "{put_code}"
permalink: /publication/{year}-{sanitize_filename(title)}
date: {date}
venue: "{venue.replace('"', "'")}"
publisher: "{publisher.replace('"', "'")}"
doi: "{doi or ''}"
paperurl: "{paper_url}"
excerpt: "{description.replace('"', "'")[:500]}"
citation: "{citation.replace('"', "'")}"
---

{description}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filename


# ---------- Main ----------

def main():

    print(f"Fetching ORCID works for {ORCID_ID}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    data = fetch_orcid_publications(ORCID_ID)

    groups = data.get("group", [])

    created = 0
    updated = 0

    for group in groups:

        summaries = group.get("work-summary", [])

        if not summaries:
            continue

        put_code = summaries[0].get("put-code")

        try:

            work = fetch_work_details(ORCID_ID, put_code)

            title = work.get("title", {}).get("title", {}).get("value", "Untitled")

            year = get_orcid_date(work.get("publication-date"))[:4]

            filename = f"{year}-{sanitize_filename(title)}.md"

            existed = os.path.exists(os.path.join(OUTPUT_DIR, filename))

            create_markdown(work, OUTPUT_DIR)

            if existed:
                updated += 1
            else:
                created += 1

        except Exception as e:
            print(f"Skipped {put_code}: {e}")

    print(f"Created: {created}")
    print(f"Updated: {updated}")


if __name__ == "__main__":
    main()
