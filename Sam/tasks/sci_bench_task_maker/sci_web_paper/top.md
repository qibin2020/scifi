---
Rank: 1
Timeout: 600
NoMemory: on
---

# Fetch arXiv abstract metadata

## Context

Fetch the abstract page of arXiv paper `2307.02405` (the nu2flows paper),
extract the title, the first author, and the first sentence of the abstract,
and write the result to `paper.json`.

You can use any of: `curl`, `wget`, the `web_fetch` tool if available, or a
Python script with `urllib`. Network is available inside the container.

## Todo

1. Fetch `https://arxiv.org/abs/2307.02405` (the HTML page)
2. Parse out:
   - The paper title (from the `<meta name="citation_title">` or the `<h1 class="title">` tag)
   - The first author (from `<meta name="citation_author">` — pick the first one)
   - The first sentence of the abstract (from `<blockquote class="abstract">`, take everything up to the first period)
3. Write `paper.json` with keys `arxiv_id`, `title`, `first_author`, `abstract_first_sentence`

## Expect

- `paper.json` exists, valid JSON
- Has all four keys: `arxiv_id`, `title`, `first_author`, `abstract_first_sentence`
- `arxiv_id` equals `"2307.02405"`
- `title` is non-empty
