# Motorcycle Spot Automation Architecture

This document describes a practical automation pipeline for collecting motorcycle checkpoints, rider stations, support nodes, and related spot metadata for this project.

The goal is not full automatic ingestion into the formal spot library. The goal is a controlled pipeline:

1. discover candidate spots automatically
2. normalize them into the existing collection schema
3. score and deduplicate them
4. send them into a review flow
5. promote approved records into the formal library

## Design Principles

- Keep the formal spot library clean.
- Treat automation output as candidate data, not trusted data.
- Reuse the existing schema in `app/services/liaoning_spots.py`.
- Let scripts do bulk discovery and normalization.
- Let humans approve records before formal inclusion.

## Recommended Directory Layout

```text
data/
  raw/
    map_candidates.json
    content_candidates.json
  normalized/
    candidate_spots.json
  reviewed/
    approved_spots.json
    rejected_spots.json

scripts/
  collect_map_candidates.py
  collect_content_candidates.py
  normalize_candidate_spots.py
  dedupe_candidate_spots.py
  score_candidate_spots.py
  export_review_queue.py
```

## Data Flow

### 1. Raw Candidate Discovery

Sources should stay separated at this stage.

- map search results
- article extraction
- short-video text extraction
- rider community recommendations

Each source should produce minimal raw records with source metadata intact.

Example raw map candidate:

```json
{
  "source_type": "map",
  "source_name": "osm",
  "raw_name": "骑士驿站咖啡",
  "city": "沈阳",
  "lat": 41.8057,
  "lng": 123.4315,
  "category": "cafe",
  "raw_tags": ["parking", "coffee", "rider"],
  "captured_at": "2026-05-27"
}
```

### 2. Schema Normalization

Every candidate should be mapped into the project schema exposed by:

- `get_moto_spot_collection_schema()`
- `get_empty_moto_spot_record()`

Target normalized candidate format:

```json
{
  "slug": "shenyang-rider-station",
  "name": "沈阳骑士驿站",
  "spot_type": "moto-station",
  "city": "沈阳",
  "region": "辽中",
  "route_type": "supply-stop",
  "coordinates": {"lat": 41.8057, "lng": 123.4315},
  "access_level": "easy",
  "parking_friendly": true,
  "best_seasons": [],
  "best_time_of_day": [],
  "ride_level": "beginner",
  "recommended_stay": "半天 / 过夜",
  "road_features": [],
  "risk_notes": [],
  "summary": "适合出发前集合、补给和过夜。",
  "photo_focus": ["机车合影", "出发集结"],
  "image_urls": ["https://cdn.example.com/shenyang-rider-station-cover.jpg"],
  "image_key": "candidate-shenyang-rider-station",
  "route_tags": ["辽中", "fuel-friendly", "overnight-friendly"],
  "nearby_spot_slugs": [],
  "fuel_support": "nearby",
  "repair_support": "limited",
  "lodging_support": "available",
  "food_support": "available",
  "support_role": ["fuel", "lodging"],
  "moto_station_features": ["可停车", "骑友集合"],
  "confidence_score": "B",
  "sources": [
    {
      "type": "map",
      "name": "osm",
      "verified": false,
      "note": "map candidate"
    }
  ],
  "last_verified_at": ""
}
```

### 3. Deduplication and Merge

Deduplication should happen before human review.

Recommended matching keys:

- exact slug match
- same city + similar name
- distance within a small coordinate threshold
- same support pattern + same nearby route context

Recommended outputs:

- merged candidate
- duplicate references list
- conflict notes for manual review

### 4. Confidence Scoring

Confidence should be used to rank the review queue.

Suggested scoring signals:

- has coordinates
- has 2 or more independent sources
- source data agrees on name and city
- has functional support information
- has clear motorcycle relevance
- was mentioned recently

Suggested grades:

- `A`: recently verified by human or multiple strong sources
- `B`: multiple sources but not yet manually confirmed
- `C`: weak or single-source candidate

### 5. Review Queue

The current collection page at `/moto/spots/collect` should be the manual review surface.

Recommended next implementation step:

- feed normalized candidates into the collection page as prefilled records
- let reviewer edit, preview image cards, and approve
- store approval result into `data/reviewed/approved_spots.json`

## Script Responsibilities

### `scripts/collect_map_candidates.py`

Purpose:

- query map sources
- collect structural POI candidates
- save raw results only

Best targets:

- gas stations
- repair shops
- hotels and inns
- campsites
- cafes likely used as rider meet points
- viewpoints and parking bays

### `scripts/collect_content_candidates.py`

Purpose:

- parse route articles, notes, transcripts, or copied text
- extract candidate names, route hints, and support clues

Best extracted fields:

- summary
- photo_focus
- risk_notes
- moto_station_features
- route_tags

### `scripts/normalize_candidate_spots.py`

Purpose:

- map raw candidates into the formal schema
- fill defaults with `get_empty_moto_spot_record()`
- normalize lists, booleans, and source metadata
- merge multiple raw candidate sources from `data/raw/*_candidates.json`

### `scripts/adapt_openclaw_candidates.py`

Purpose:

- convert OpenClaw or similar third-party collector output into the repo's raw candidate shape
- preserve source URL and author before schema normalization
- keep external payload structure isolated from app-facing review data

Suggested interface:

- input: `data/raw/openclaw_export.json`
- output: `data/raw/openclaw_candidates.json`
- next step: run `scripts/normalize_candidate_spots.py`

Recommended compatibility targets for the adapter:

- wrapped exports like `{ "items": [...] }`, `{ "results": [...] }`, or `{ "data": [...] }`
- field aliases such as `name/title`, `creator/author/owner`, `link/url/sourceUrl`
- nested coordinates under `location`, `coordinates`, or `geo`
- content hints under `summary`, `excerpt`, `description`, or `snippet`

For day-to-day usage, a thin orchestration entrypoint can run:

1. `scripts/adapt_openclaw_candidates.py`
2. `scripts/normalize_candidate_spots.py`

The repo now includes `scripts/run_candidate_pipeline.py` for that shortest path.

### OpenClaw Social Collection Package

For Liaoning-only social discovery on Douyin and Xiaohongshu, this repo also includes a task-side script:

- `openclaw/liaoning_social_task.js`

Task intent:

- search only Liaoning-related motorcycle travel content
- focus on checkpoints, rider stations, support nodes, and scenic stopovers
- normalize raw post-like results into the wrapped export shape used by `adapt_openclaw_candidates.py`
- hand off to `scripts/run_candidate_pipeline.py` so results land in `data/normalized/candidate_spots.json`

This keeps the OpenClaw runtime responsible for platform-side discovery while the repo remains responsible for schema normalization and approval flow.

### `scripts/dedupe_candidate_spots.py`

Purpose:

- merge duplicates
- keep original source references
- generate conflict flags

### `scripts/score_candidate_spots.py`

Purpose:

- assign confidence grade
- rank review priority
- identify top candidates for human verification

### `scripts/export_review_queue.py`

Purpose:

- export a clean candidate list for manual review
- optionally generate prefilled URLs or JSON payloads for the Flask review page

## Integration With Current App

Current project assets already suitable for integration:

- schema definition in `app/services/liaoning_spots.py`
- collection page at `/moto/spots/collect`
- spot library page at `/moto/spots`
- detail page and image preview flow at `/moto/spots/liaoning/<slug>`

Recommended next code integration sequence:

1. add `data/` and `scripts/` directories
2. create a small candidate JSON example file
3. add one loader that reads candidate records
4. support prefilled collection-page review from candidate data
5. add an approval action that writes reviewed records to a file

## Review Model

Keep automation and formal records separated.

Suggested states:

- `raw`: source-specific untrusted data
- `normalized`: schema-shaped candidate
- `review-ready`: deduped and scored candidate
- `approved`: human-reviewed and ready for formal library
- `published`: added to formal spot library

## Practical MVP

The shortest useful automation MVP for this repo is:

1. collect map-based candidates into `data/raw/map_candidates.json`
2. normalize them into `data/normalized/candidate_spots.json`
3. manually review them through the existing collection page
4. move approved records into `data/reviewed/approved_spots.json`

That gives you automation without polluting the main spot dataset.