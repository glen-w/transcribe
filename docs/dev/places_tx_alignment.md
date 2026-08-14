# Places / NER map alignment (TranscriptX ↔ Transcribe)

Authority: developer note. Does not redefine runtime contracts. Source pins for
the NER module remain in [analysis_port_pins.md](analysis_port_pins.md).

## What TranscriptX does

| Concern | TX behaviour |
|---------|----------------|
| Place filter for maps | `GPE`, `LOC` only (`NERAnalysis._save_location_maps`) |
| Geocoder | `geopy.Nominatim(user_agent="transcriptx")` via `utils/location_cache.py` |
| Rate limit / cap | `sleep(1)` between live lookups; `max_locations=50`, frequency-ranked |
| Cache | `{DATA_DIR}/cache/location_cache.json` — hits as `{lat,lon}`, misses as `null` |
| Artifact | Always writes `ner-locations` JSON; Folium HTML/PNG soft-optional (`[maps]`) |
| UI | Speakers → Locations (Folium iframe); per-speaker + ALL maps |
| Privacy | `ner_include_geocoding` defaults **True** (no separate consent) |
| Provenance | `sentence`, `segment_index`, `start`, speaker |

Legacy duplicate: `core/geo_utils.py` (thinner; NER does **not** use it). Prefer the
`location_cache.py` patterns.

## What Transcribe does (aligned)

| Concern | Transcribe behaviour |
|---------|----------------------|
| Place filter | `GPE`\|`LOC` (TX parity) **+** `FAC` notebook adaptation |
| Geocoder | stdlib Nominatim HTTP (same OSM API; no geopy hard dep) |
| Rate limit / cap | ≥1.05s between live lookups; default cap **50**, frequency-ranked |
| Cache | `data/cache/geocode.json` — versioned schema, normalized keys, atomic writes; caches ok / not_found / error |
| Artifact | `analysis/ner/locations.json` (`transcribe.ner-locations`) when coords resolve |
| UI | View → Themes → People; primary nav → Places; Streamlit `st.map` |
| Privacy | **Opt-in** checkbox (intentional divergence — place names leave the machine only when enabled) |
| Provenance | `page_ids` + sample `sentence` from NER evidence quotes |

## Intentional divergences (keep)

1. **Opt-in geocoding** — local-first honesty; TX defaults on.
2. **No Folium / Playwright / geopy** — keep UI deps thin; `st.map` is enough for notebook pins.
3. **Maps outside the NER module** — Transcribe NER port explicitly removed speaker gates/maps/geocoding; places stay a services read-model over published NER.
4. **FAC included** — handwritten notebooks often name buildings/landmarks.
5. **No speaker-scoped maps** — page/notebook domain, not timed speakers.

## Do not

- Import TranscriptX at runtime.
- Port Folium map generation into the NER analysis module.
- Default network geocoding on without consent.
