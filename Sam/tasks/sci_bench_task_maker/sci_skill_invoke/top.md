---
Rank: 1
Timeout: 300
Skills: text_stats
NoMemory: on
---

# Invoke the text_stats skill

## Context

Demonstrate that the agent can use a declared skill (`text_stats`). The seed
file `small_corpus.txt` is provided in the task directory. Invoke the
`text_stats` skill on it and write the returned statistics to `stats.json`.

## Todo

1. The task directory contains `small_corpus.txt`
2. Invoke the `text_stats` skill via your tool interface, passing `small_corpus.txt` as the `path` argument
3. Capture the skill's return value as JSON and save it to `stats.json`

## Expect

- `stats.json` exists, valid JSON
- Contains numeric counts for words / lines / chars
