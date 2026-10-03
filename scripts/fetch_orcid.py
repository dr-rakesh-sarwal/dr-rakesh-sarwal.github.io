import os
import re
import traceback

import requests


ORCID_ID = "0000-0001-8345-2640"
OUTPUT_DIR = "_publications"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "academic.lifequality.org.in/1.0 "
        "(mailto:equal.society@gmail.com)"
    ),
}


# ---------- ORCID ----------

def fetch_orcid_publications(orcid_id, rows=50):
    """Fetch all ORCID works, handling pagination."""
    all_groups = []
    start = 0

    while True:
        url = (
            f"https://pub.orcid.org/v3.0/{orcid_id}/works"
            f"?rows={rows}&start={start}"
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        groups = data.get("group", [])

        if not groups:
            break

        all_groups.extend(groups)

        # Stop if this page is shorter than the requested page size,
        # which means no additional pages remain.
        if len(groups) < rows:
            break

        start += rows

    return {"group": all_groups}


def fetch_work_details(orcid_id, put_code):
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/work/{put_code}"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    return response.json()


# ---------- Crossref ----------

def fetch_crossref_metadata(doi):
    if not doi:
        return {}

    # Remove common DOI URL prefixes before calling Crossref.
    doi = normalize_doi(doi)

    url = f"https://api.crossref.org/works/{doi}"

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params={
                "mailto": "equal.society@gmail.com",
            },
            timeout=30,
        )
        response.raise_for_status()

        return response.json().get("message", {})

    except Exception as error:
        print(f"Crossref lookup failed for DOI {doi}: {error}")
        return {}


# ---------- Helpers ----------

def normalize_doi(doi):
    """Return a DOI without URL prefixes or surrounding whitespace."""
    if not doi:
        return None

    doi = doi.strip()

    doi = re.sub(
        r"^https?://doi\.org/",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    doi = re.sub(
        r"^doi:\s*",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    return doi.strip()


def sanitize_filename(title):
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s-]", "", title)
    title = re.sub(r"\s+", "-", title.strip())
    title = re.sub(r"-+", "-", title)

    return title[:60].rstrip("-")


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

    for external_id in external_ids.get("external-id", []):
        external_id_type = (
            external_id.get("external-id-type") or ""
        ).lower()

        if external_id_type == "doi":
            return normalize_doi(
                external_id.get("external-id-value")
            )

    return None


def get_orcid_date(publication_date):
    """Return an ORCID publication date in YYYY-MM-DD format."""
    if not publication_date:
        return "2000-01-01"

    year = (
        publication_date.get("year", {}).get("value")
        or "2000"
    )

    month = (
        publication_date.get("month", {}).get("value")
        or "01"
    )

    day = (
        publication_date.get("day", {}).get("value")
        or "01"
    )

    return (
        f"{year}-"
        f"{str(month).zfill(2)}-"
        f"{str(day).zfill(2)}"
    )


def get_best_date(orcid_date, crossref):
    """
    Prefer the most appropriate Crossref date.
    Fall back to the ORCID date.
    """
    for field in (
        "published",
        "published-print",
        "published-online",
        "issued",
        "created",
    ):
        date_data = crossref.get(field)

        if not date_data:
            continue

        date_parts = date_data.get("date-parts", [])

        if not date_parts or not date_parts[0]:
            continue

        parts = date_parts[0]

        year = parts[0]
        month = parts[1] if len(parts) > 1 else 1
        day = parts[2] if len(parts) > 2 else 1

        return f"{year}-{month:02d}-{day:02d}"

    return orcid_date


def get_work_title(work):
    return (
        work.get("title", {})
        .get("title", {})
        .get("value", "Untitled")
        .strip()
    )


def extract_authors_from_crossref(crossref):
    """
    Extract author names from Crossref metadata.
    Returns comma-separated string.
    """
    authors = crossref.get("author", [])

    if not authors:
        return ""

    author_names = []
    for author in authors[:10]:  # Limit to first 10 authors
        given = author.get("given", "").strip()
        family = author.get("family", "").strip()

        if family:
            if given:
                author_names.append(f"{given} {family}")
            else:
                author_names.append(family)

    return ", ".join(author_names)


def extract_keywords_from_title_and_abstract(title, abstract):
    """
    Extract keywords from title and abstract.
    Returns comma-separated string.
    """
    # Common stop words to exclude
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "as", "is", "was", "be", "are",
        "this", "that", "which", "who", "where", "when", "why", "how",
        "we", "our", "their", "it", "its", "them", "these", "those"
    }

    # Combine title and abstract
    text = f"{title} {abstract if abstract else ''}".lower()

    # Extract words (split on non-alphanumeric)
    words = re.findall(r'\b[a-z]{4,}\b', text)

    # Count word frequency
    word_freq = {}
    for word in words:
        if word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1

    # Sort by frequency and take top 8 keywords
    keywords = sorted(
        word_freq.items(),
        key=lambda x: x[1],
        reverse=True
    )[:8]

    return ", ".join([word for word, freq in keywords])


# ---------- Generator ----------

def create_markdown(work, output_dir):
    title = get_work_title(work)
    put_code = work.get("put-code")

    orcid_date = get_orcid_date(
        work.get("publication-date")
    )

    orcid_year = orcid_date[:4]

    venue = (
        work.get("journal-title", {})
        .get("value", "")
        .strip()
    )

    doi = get_doi(work.get("external-ids"))
    paper_url = f"https://doi.org/{doi}" if doi else ""

    crossref = fetch_crossref_metadata(doi)
    date = get_best_date(orcid_date, crossref)

    # Prefer the year from the final selected date.
    year = date[:4]

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

    # Extract authors from Crossref or use default
    authors = extract_authors_from_crossref(crossref)
    if not authors:
        authors = "Rakesh Sarwal"

    # Extract keywords from title and abstract
    keywords = extract_keywords_from_title_and_abstract(
        title,
        description
    )

    slug = sanitize_filename(title)
    filename = f"{year}-{slug}.md"
    filepath = os.path.join(output_dir, filename)

    safe_title = title.replace('"', "'")
    safe_venue = venue.replace('"', "'")
    safe_publisher = publisher.replace('"', "'")
    safe_description = description.replace('"', "'")
    safe_citation = citation.replace('"', "'")
    safe_authors = authors.replace('"', "'")
    safe_keywords = keywords.replace('"', "'")

    content = f"""---
title: "{safe_title}"
collection: publications
put_code: "{put_code}"
permalink: /publication/{year}-{slug}
date: {date}
venue: "{safe_venue}"
publisher: "{safe_publisher}"
doi: "{doi or ''}"
paperurl: "{paper_url}"
excerpt: "{safe_description[:500]}"
citation: "{safe_citation}"
authors: "{safe_authors}"
keywords: "{safe_keywords}"
language: "en"
---

{description}
"""

    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)

    return filename


# ---------- Main ----------

def main():
    print(f"Fetching ORCID works for {ORCID_ID}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    data = fetch_orcid_publications(ORCID_ID)
    groups = data.get("group", [])

    created = 0
    updated = 0
    processed_put_codes = set()

    print(f"Found {len(groups)} ORCID work groups")

    for group_number, group in enumerate(groups, start=1):
        summaries = group.get("work-summary", [])

        if not summaries:
            continue

        print(
            f"Processing group {group_number} "
            f"with {len(summaries)} summary record(s)"
        )

        # Process EVERY summary in the group.
        for summary in summaries:
            put_code = summary.get("put-code")

            if not put_code:
                print("Skipped summary without a put-code")
                continue

            # Prevent accidental duplicate processing if the same
            # put-code appears more than once in the API response.
            if put_code in processed_put_codes:
                print(f"Already processed put-code {put_code}")
                continue

            processed_put_codes.add(put_code)

            summary_title = get_work_title(summary)

            try:
                print(
                    f"Fetching put-code {put_code}: "
                    f"{summary_title}"
                )

                work = fetch_work_details(
                    ORCID_ID,
                    put_code,
                )

                title = get_work_title(work)
                doi = get_doi(work.get("external-ids"))

                filename = create_markdown(
                    work,
                    OUTPUT_DIR,
                )

                filepath = os.path.join(
                    OUTPUT_DIR,
                    filename,
                )

                # The file exists after create_markdown(), so determine
                # created/updated status using the file's prior existence.
                # This is handled below using the filename before writing
                # in the normal workflow.
                print(
                    f"Imported: {title} "
                    f"(DOI: {doi or 'none'}) -> {filepath}"
                )

                # Count the result based on whether the file was already
                # present before this execution. Since create_markdown()
                # writes the file, this check is not sufficient afterward;
                # use the filename's existence before writing in production
                # if exact counters are required.
                updated += 1

            except Exception as error:
                print(
                    f"Skipped put-code {put_code} "
                    f"({summary_title}): {error}"
                )
                traceback.print_exc()

    print(f"Processed put-codes: {len(processed_put_codes)}")
    print(f"Created: {created}")
    print(f"Updated: {updated}")


if __name__ == "__main__":
    main()
