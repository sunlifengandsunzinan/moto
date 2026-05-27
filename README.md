# Personal

Minimal Flask project with a standard Flask application package layout.

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

The app listens on `http://127.0.0.1:6001`.

Port `6000` is intentionally avoided because Chromium-based browsers block it as an unsafe port (`ERR_UNSAFE_PORT`).

Useful endpoints during development:

- `GET /`: landing page
- `GET /status`: runtime status page
- `GET /api/status`: runtime status JSON

## Moto Spot Collection Schema

Motorcycle checkpoints, stations, and support nodes should follow one fixed collection schema in [app/services/liaoning_spots.py](/Users/Lifeng.Sun/workspace/Personal/app/services/liaoning_spots.py).

Use these exported helpers as the canonical source of truth:

- `get_moto_spot_collection_schema()`: field definitions with required flag, type, group, and example
- `get_empty_moto_spot_record()`: blank record template for manual collection or future admin forms

The schema is grouped into:

- `identity`: point identity and classification
- `location`: coordinates, access, parking
- `travel`: season, riding level, stay duration, road/risk info
- `content`: summary, photo focus, image key
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