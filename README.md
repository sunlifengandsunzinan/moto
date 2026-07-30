# Personal

Minimal Flask project with a standard Flask application package layout.

## Project Features

This project has evolved from a minimal Flask scaffold into a Liaoning motorcycle travel planning and spot-collection system.

Current capabilities include:

- route planning for Liaoning motorcycle trips, with route templates, trip preferences, must-visit spots, and custom planning entrypoints
- a Liaoning spot library covering scenic checkpoints, motorcycle stations, supply stops, and support nodes
- a WeChat Mini Program frontend scaffold for the three main tabs: routes, spots, and me
- structured spot detail pages with generated image galleries, route-fit recommendations, and source metadata display
- a schema-driven spot collection page for manual entry, candidate review, and approval into the formal library
- a pending-review workflow that separates raw collection results from approved public data
- automation support for raw candidate ingestion, normalization, reviewed approval output, and third-party collector adaptation
- OpenClaw-oriented collection support for Liaoning-only discovery from Douyin and Xiaohongshu, feeding the existing pending-review queue

The app is organized around three linked flows:

1. user-facing planning: home page, planner, route detail, and spot detail pages
2. data building: structured collection form, candidate review, approval, and spot library publishing
3. automation: raw collector output, normalization scripts, OpenClaw adapter flow, and review-queue ingestion

## Structure

- `app.py`: local development entrypoint
- `app/__init__.py`: app factory with instance config loading
- `app/config.py`: base config classes and environment overrides
- `app/routes.py`: route registration
- `app/templates/`: HTML templates
- `app/static/`: static assets
- `instance/config.py`: deployment-specific local overrides

## Environment Config

The project uses a three-step config chain:

- `app/config.py`: checked-in defaults for development and production
- `instance/config.py`: instance-local overrides in the Flask `instance/` folder
- `.env`: environment-variable overrides without requiring `python-dotenv`

- `APP_ENV=development`: enables development defaults
- `APP_ENV=production`: switches to production defaults
- `HOST`, `PORT`, `DEBUG`, `SECRET_KEY`: override runtime settings

## Run

```bash
source .venv/bin/activate
python app.py
```

The app listens on `http://127.0.0.1:5000`.

Port `6000` is intentionally avoided because Chromium-based browsers block it as an unsafe port (`ERR_UNSAFE_PORT`).

Useful endpoints during development:

- `GET /`: landing page
- `GET /status`: runtime status page
- `GET /api/status`: runtime status JSON
- `GET /api/moto/routes`: route-list payload for the Mini Program routes tab
- `GET /api/moto/spots`: spot-list payload for the Mini Program spots tab
- `GET /api/moto/me`: workspace payload for the Mini Program me tab

## WeChat Mini Program

The repository now includes a real Mini Program frontend under `miniprogram/`.

- app root: `miniprogram/`
- tabs: `pages/routes/index`, `pages/spots/index`, `pages/me/index`
- detail bridge: `pages/webview/index`

Default backend addresses in the Mini Program are selected at runtime:

- WeChat DevTools simulator: `http://127.0.0.1:5000` and `http://127.0.0.1:5000/api`
- phone preview / real-device debugging: `https://www.xingtu.ltd` and `https://www.xingtu.ltd/api`

Recommended local flow:

1. start Flask with `python app.py`
2. open `miniprogram/` in WeChat DevTools, or open the repository root now that `project.config.json` points `miniprogramRoot` to `miniprogram/`
3. keep the backend running while the Mini Program requests `/api/moto/*`

If WeChat DevTools reports `app.json not found in root directory`, that means the wrong folder was imported. Use one of these two import roots:

- `miniprogram/`
- the repository root, which now contains `project.config.json` and redirects DevTools to `miniprogram/`

The project now routes by runtime environment: devtools uses `127.0.0.1`, while phone preview and real-device debugging use the device-side domain configured in `miniprogram/utils/backend-config.js`.

The production domain `https://www.xingtu.ltd` is served by Aliyun Nginx over HTTPS and reverse-proxied to the Flask process on `127.0.0.1:6001`.

For a real device build, ensure the Mini Program request domain and web-view business domain both include `https://www.xingtu.ltd`.

## Page Entry Overview

The main page and feature entrypoints are:

- `GET /`: basic Flask landing page used for runtime verification
- `GET /moto`: redirects to `/moto/routes` for the tab-first Moto entry
- `GET /moto/planner`: interactive route planner with route template, must-visit spot, trip-day, distance, and riding-preference inputs
- `POST /moto/planner/result`: planner result page for the submitted trip conditions
- `GET /moto/routes`: route template index for browsing preset Liaoning ride plans
- `GET /moto/routes/<slug>`: route detail page for one preset route template
- `GET /moto/spots`: Liaoning spot library, with filtering by region and support role
- `GET /moto/spots/liaoning/<slug>`: structured spot detail page with metadata, image gallery, source cards, and recommended route templates
- `GET /moto/spots/collect`: schema-driven spot collection and candidate review page
- `POST /moto/spots/review/<slug>/<decision>`: approval or rejection entrypoint for normalized candidate spots
- `GET /moto/custom`: custom motorcycle-trip requirement form

If you are exploring the product manually, the usual order is `/moto` -> `/moto/planner` or `/moto/spots` -> `/moto/spots/collect`.

## Route Navigation Waypoints

Route templates now support a dedicated navigation config layer for Amap export and direct navigation.

The canonical route data source now lives in [app/services/route_templates.json](app/services/route_templates.json). The Python module [app/services/route_templates_config.py](app/services/route_templates_config.py) is only a thin JSON loader.

Recommended route-level field:

```json
"navigation": {
	"provider": "amap",
	"waypoints": [
		{"name": "杭州", "lng": 120.1551, "lat": 30.2741},
		{"name": "莫干山", "lng": 119.8795, "lat": 30.6140},
		{"name": "安吉", "lng": 119.6803, "lat": 30.6380}
	]
}
```

Legacy `navigation_waypoints` is still accepted for backward compatibility, but new route data should prefer `navigation.waypoints`.

You can also put waypoints on each day item if a route needs day-scoped control:

```json
"days_plan": [
	{
		"day": 1,
		"title": "杭州 -> 莫干山 -> 安吉",
		"waypoints": [
			{"name": "杭州", "lng": 120.1551, "lat": 30.2741},
			{"name": "莫干山", "lng": 119.8795, "lat": 30.6140},
			{"name": "安吉", "lng": 119.6803, "lat": 30.6380}
		]
	}
]
```

Supported waypoint input keys are:

- `name`: required, used for display and fallback navigation text
- `lat` / `lng`: preferred coordinate keys
- `latitude` / `longitude`: accepted aliases
- `coordinates.lat` / `coordinates.lng`: accepted nested form

Recommended template split:

- `days_plan`: user-facing ride story, daily distance, highlights, notes
- `navigation.waypoints`: navigation-only ordered waypoint chain for direct Amap export

This keeps display copy and navigation maintenance separate. If the displayed day title changes, you do not need to rebuild the Amap chain by parsing text.

The route export payload at `/api/moto/routes` now includes:

- `navigation_waypoints`: normalized waypoint list on each route card
- `amap_export.waypoints`: the same normalized waypoint list for frontend navigation use
- `amap_export.navigation_mode`: `none`, `names`, `mixed`, or `coordinates`
- `amap_export.status_text`: human-readable navigation readiness text such as `5/5 个点已带坐标，可直接高德逐点导航`
- `amap_export.supports_coordinate_navigation`: whether any waypoint already has coordinates
- `amap_export.coordinate_waypoint_count`: number of waypoints that already have coordinates

The JSON source now keeps only retained real routes and collected route records.

Behavior:

- if no coordinates are present, Amap export falls back to name-based navigation
- if some coordinates are present, export uses mixed mode and keeps the rest as names
- if all waypoints have coordinates, the direct-navigation link is emitted with coordinate-aware Amap parameters, including middle waypoints

## Route Waypoint Collection Entry

Reserved collection entrypoints for future route-coordinate and waypoint gathering:

- `GET /moto/routes/collect`: web collection entry for choosing a route and seeing the current waypoint seed
- `GET /api/moto/routes/collect/schema`: JSON schema and selected route seed payload for future Mini Program or tooling integration

Current storage-related anchors:

- canonical route source: `app/services/route_templates.json`
- collection example seed: `data/raw/route_waypoint_collection.example.json`
- standalone validation command: `python scripts/validate_route_templates.py`

## Data Directory Overview

The `data/` directory is split by collection stage so raw automation output does not directly overwrite approved public spot data.

- `data/raw/`: raw collection and adapter-stage files
- `data/normalized/`: normalized pending-review queue used by the collection/review page
- `data/reviewed/`: reviewed outputs separated into approved and rejected records

Current important files are:

- `data/raw/map_candidates.json`: raw candidate spots collected from map-oriented sources
- `data/raw/map_seed_queries.json`: seed queries for map-based collection
- `data/raw/openclaw_export.example.json`: reference wrapped export shape for OpenClaw input
- `data/raw/openclaw_export.json`: actual third-party export drop location before adaptation
- `data/raw/openclaw_candidates.json`: adapted OpenClaw output in the repo's raw-candidate shape
- `data/normalized/candidate_spots.json`: pending-review queue consumed by `/moto/spots/collect`
- `data/reviewed/approved_spots.json`: approved candidates that can be merged into the formal spot library
- `data/reviewed/rejected_spots.json`: rejected review records kept for traceability

The normal data flow is:

1. collector output lands in `data/raw/`
2. adapter and normalization scripts produce `data/normalized/candidate_spots.json`
3. manual review in `/moto/spots/collect` moves records into `data/reviewed/approved_spots.json` or `data/reviewed/rejected_spots.json`
4. approved spots are reused by the spot library, planner weighting, and spot detail pages

## Moto Spot Collection Schema

Motorcycle checkpoints, stations, and support nodes should follow one fixed collection schema in [app/services/liaoning_spots.py](/Users/Lifeng.Sun/workspace/Personal/app/services/liaoning_spots.py).

Use these exported helpers as the canonical source of truth:

- `get_moto_spot_collection_schema()`: field definitions with required flag, type, group, and example
- `get_empty_moto_spot_record()`: blank record template for manual collection or future admin forms

The schema is grouped into:

- `identity`: point identity and classification
- `identity`: point identity, main type, and fixed markers such as `checkin-point`, `fuel-station`, `moto-station`, `coffee-stop`
- `location`: coordinates, access, parking
- `travel`: season, riding level, stay duration, road/risk info
- `content`: summary, photo focus, image key
- `content`: summary, photo focus, collected image URLs, image key
- `planning`: route tags and nearby spot relations
- `support`: fuel, repair, lodging, food, station features
- `quality`: confidence score, sources, last verification time

For `sources`, prefer one line per source using this format:

- `来源类型 | 来源名称 | 来源地址 | 作者 | 是否核验 | 备注`

For an implementation-oriented automation plan built around this schema, see [AUTOMATION_COLLECTION_ARCHITECTURE.md](/Users/Lifeng.Sun/workspace/Personal/AUTOMATION_COLLECTION_ARCHITECTURE.md).

## Third-Party Collector Adapter

The repository now supports a thin adapter layer for third-party collectors such as OpenClaw.

- Put third-party export payloads into `data/raw/openclaw_export.json`. The reference shape is shown in [data/raw/openclaw_export.example.json](/Users/Lifeng.Sun/workspace/Personal/data/raw/openclaw_export.example.json).
- Run `python scripts/run_candidate_pipeline.py` for the shortest end-to-end path.
- Or run `python scripts/adapt_openclaw_candidates.py` and then `python scripts/normalize_candidate_spots.py` manually.

The OpenClaw adapter accepts both flat arrays and wrapped exports such as `{ "items": [...] }`, and tolerates common alias fields like `name/title`, `link/url/sourceUrl`, `creator/author/owner`, `location.latitude/geo.lat`, and `type/category/poiType`.

This keeps external collection output separate from the app-facing candidate schema while reusing the existing manual review flow.

## OpenClaw Liaoning Social Collection

The repo now includes an OpenClaw task script for Liaoning-only social collection from Douyin and Xiaohongshu:

- task script: `/Users/Lifeng.Sun/workspace/Personal/openclaw/liaoning_social_task.js`
- export target: `data/raw/openclaw_export.json`
- pipeline to review queue: `python scripts/run_candidate_pipeline.py`

Recommended flow:

1. Import and run `/Users/Lifeng.Sun/workspace/Personal/openclaw/liaoning_social_task.js` in OpenClaw.
2. Make sure the task writes `data/raw/openclaw_export.json` in the wrapped shape shown in [data/raw/openclaw_export.example.json](/Users/Lifeng.Sun/workspace/Personal/data/raw/openclaw_export.example.json).
3. Run `python scripts/run_candidate_pipeline.py`.
4. Open `/moto/spots/collect` to review the normalized candidates.

The task now applies hard filters before export:

- source URL must belong to Douyin or Xiaohongshu
- candidate must include real image URLs from the source payload
- AI-generated markers and `data:image/...` payloads are dropped

The task is scoped to Liaoning and seeded with city/route terms for:

- 沈阳骑士驿站 / 集合点
- 本溪本桓公路
- 桓仁补给与夜宿
- 丹东绿江村 / 鸭绿江
- 宽甸青山沟
- 大连滨海路 / 旅顺沿海
- 盘锦红海滩
- 兴城海滨

To run with production-style settings:

```bash
source .venv/bin/activate
APP_ENV=production DEBUG=false python app.py
```

To run tests:

```bash
source .venv/bin/activate
pytest
```

## Notes

The project uses its own `.venv`. In this environment, Flask was bootstrapped offline
from packages already present on the machine because direct package downloads are blocked.