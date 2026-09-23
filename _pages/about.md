---
layout: single
permalink: /
title: "Dr. Rakesh Sarwal"
redirect_from:
  - /about/
  - /about.html
author_profile: true
---
Public Health physician, Public Policy and Planning leader with over three decades of experience in governments in India. I combine academic rigour, insight of what works to analyze and develop solutions to problems. Driven by a passion for excellence, and a faith in the unity of existence, I see immense potential of people taking charge of their health through healthy Lifestyle, and a health system based on prevention.

Motivating and guiding lifestyle changes one person at a time, starting with the clinic, drawing policy lessons, and sharing them through policy briefs. 

Do visit **[EQUAL Society](https://lifequality.org.in)**, our not-for-profit organization working since 1997 to improve quality of life.

**My research interests** are in exploring the effectiveness of lifestyle therapies across a spectrum of chronic conditions.

## Recent lectures

{% assign recent_lectures = site.teaching | sort: "date" | reverse %}
{% for lecture in recent_lectures limit:3 %}
### [{{ lecture.title }}]({{ lecture.url | relative_url }})

{% if lecture.date %}<small>{{ lecture.date | date: "%-d %B %Y" }}{% endif %}{% if lecture.venue %} · {{ lecture.venue }}{% endif %}{% if lecture.location %}, {{ lecture.location }}{% endif %}</small>

{% endfor %}

[See all lectures →]({{ "/teaching/" | relative_url }})

## Recent talks

{% assign recent_talks = site.talks | sort: "date" | reverse %}
{% for talk in recent_talks limit:3 %}
### [{{ talk.title }}]({{ talk.url | relative_url }})

{% if talk.date %}<small>{{ talk.date | date: "%-d %B %Y" }}{% endif %}{% if talk.venue %} · {{ talk.venue }}{% endif %}{% if talk.location %}, {{ talk.location }}{% endif %}</small>

{% endfor %}

[See all talks →]({{ "/talks/" | relative_url }})

## Latest publications

{% assign recent_publications = site.publications | sort: "date" | reverse %}
{% for publication in recent_publications limit:3 %}
### [{{ publication.title }}]({{ publication.url | relative_url }})
<small>
  {{ publication.citation | remove: publication.paperurl | strip }}
</small>
{% endfor %}

[See all publications →]({{ "/publications/" | relative_url }})

[![Google Scholar](https://img.shields.io/badge/Google%20Scholar-Profile-blue?logo=googlescholar&logoColor=white)](https://scholar.google.com/citations?user=siSnZvMAAAAJ&hl=en)

<!-- Last updated: 2026-08-26 -->
