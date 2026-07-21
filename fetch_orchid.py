import requests
import os
import re

ORCID_ID = "0000-0001-8345-2640"
OUTPUT_DIR = "_publications"

def fetch_orcid_publications(orcid_id):
    """Fetch publications from ORCID public API"""
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def fetch_work_details(orcid_id, put_code):
    """Fetch detailed info for a single work"""
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/work/{put_code}"
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def sanitize_filename(title):
    """Convert title to a safe filename"""
    title = title.lower()
    title = re.sub(r'[^a-z0-9\s-]', '', title)
    title = re.sub(r'\s+', '-', title.strip())
    return title[:60]

def get_doi(external_ids):
    """Extract DOI from external IDs"""
    if not external_ids:
        return None
    for ext_id in external_ids.get("external-id", []):
        if ext_id.get("external-id-type") == "doi":
            return ext_id.get("external-id-value")
    return None

def get_year(pub_date):
    """Extract year from publication date"""
    if pub_date and pub_date.get("year"):
        return pub_date["year"].get("value", "2000")
    return "2000"

def create_markdown(work, output_dir):
    """Create a markdown file for a publication"""
    # Get basic details
    title = "Untitled"
    if work.get("title") and work["title"].get("title"):
        title = work["title"]["title"].get("value", "Untitled")

    year = get_year(work.get("publication-date"))
    
    # Get journal/venue
    venue = ""
    if work.get("journal-title") and work["journal-title"].get("value"):
        venue = work["journal-title"]["value"]

    # Get DOI
    doi = get_doi(work.get("external-ids"))
    paper_url = f"https://doi.org/{doi}" if doi else ""

    # Get contributors/citation
    citation = f"Sarwal, R. ({year}). {title}."
    if venue:
        citation += f" {venue}."
    if doi:
        citation += f" https://doi.org/{doi}"

    # Get abstract/description
    description = ""
    if work.get("short-description"):
        description = work["short-description"]

    # Create filename
    filename = f"{year}-{sanitize_filename(title)}.md"
    filepath = os.path.join(output_dir, filename)

    # Write markdown file
    content = f"""---
title: "{title.replace('"', "'")}"
collection: publications
permalink: /publication/{year}-{sanitize_filename(title)}
date: {year}-01-01
venue: "{venue.replace('"', "'")}"
paperurl: "{paper_url}"
citation: "{citation.replace('"', "'")}"
---
{description}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Created: {filename}")
    return filename

def main():
    print(f"🔍 Fetching publications for ORCID: {ORCID_ID}")
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Clear existing auto-generated publications
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".md"):
            os.remove(os.path.join(OUTPUT_DIR, f))
            print(f"🗑️  Removed old file: {f}")

    # Fetch all works
    data = fetch_orcid_publications(ORCID_ID)
    works_group = data.get("group", [])
    
    print(f"📚 Found {len(works_group)} publications\n")

    created = []
    for group in works_group:
        work_summaries = group.get("work-summary", [])
        if not work_summaries:
            continue
        
        # Get the most recent version of the work
        summary = work_summaries[0]
        put_code = summary.get("put-code")

        try:
            # Fetch full details
            work = fetch_work_details(ORCID_ID, put_code)
            filename = create_markdown(work, OUTPUT_DIR)
            created.append(filename)
        except Exception as e:
            print(f"⚠️  Skipped a work due to error: {e}")

    print(f"\n🎉 Done! Created {len(created)} publication files.")

if __name__ == "__main__":
    main()
