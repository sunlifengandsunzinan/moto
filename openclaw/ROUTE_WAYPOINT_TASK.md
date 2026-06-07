# OpenClaw Douyin Route Waypoint Task

This file documents the free scheduling logic and the runnable OpenClaw task for collecting route waypoints from Douyin videos.

## Task File

- runnable task: `openclaw/douyin_route_waypoint_task.js`
- output file: `data/raw/openclaw_route_waypoints.json`
- route seed source: `app/services/route_templates.json`

## What It Does

The task is scoped to existing routes in this repo.

For each non-demo route in `app/services/route_templates.json`, it:

1. builds Douyin search keywords from the route title and known waypoint hints
2. asks OpenClaw to search Douyin content for those route terms
3. reuses OpenClaw video analysis to read transcript, OCR, captions, and structured waypoints when available
4. falls back to free text extraction when no structured waypoint array is returned
5. merges repeated waypoint names across videos into one ordered waypoint chain per route
6. emits an Amap-compatible route link using names only or mixed coordinates when available

This keeps the whole flow free:

- no paid map search API
- no paid geocoding API
- no paid LLM dependency required by this repo layer

If OpenClaw can return structured `waypoints`, the task will use them. If not, it still produces a name-based Amap route that can open in Gaode.

## Output Shape

The output file is wrapped JSON:

```json
{
  "source": "openclaw-route-waypoints",
  "exported_at": "2026-05-31T00:00:00.000Z",
  "schedule": {
    "cron": "15 */6 * * *",
    "timezone": "Asia/Shanghai"
  },
  "items": [
    {
      "route_slug": "liaoning-benhuan-3-day",
      "route_title": "辽宁 3 天本溪到绿江边境风景线",
      "collection_status": "names",
      "source": {
        "channel": "openclaw-douyin-video-analysis",
        "reference_url": "https://www.douyin.com/video/...",
        "operator": "openclaw-scheduled-task"
      },
      "navigation": {
        "provider": "amap",
        "waypoints": [
          {"name": "杭州", "lng": null, "lat": null, "has_coordinates": false},
          {"name": "莫干山", "lng": null, "lat": null, "has_coordinates": false},
          {"name": "安吉", "lng": null, "lat": null, "has_coordinates": false}
        ]
      },
      "amap_export": {
        "href": "https://m.amap.com/navigation/carmap/...",
        "navigation_mode": "names"
      }
    }
  ]
}
```

The `navigation.waypoints` array is intentionally aligned with the route collection schema already used by this repo.

## Free Scheduling Logic

Recommended free cadence:

1. Incremental sweep every 6 hours
2. Full sweep once a day after midnight
3. Manual review after each daily full sweep

Suggested logic:

1. `07:15`, `13:15`, `19:15`: run the task against recent Douyin results and overwrite `data/raw/openclaw_route_waypoints.json`
2. `02:30`: run the same task as a full sweep, then manually compare new waypoint chains with current `route_templates.json`
3. only after review, copy accepted waypoint arrays into `app/services/route_templates.json`
4. validate with `python scripts/validate_route_templates.py`

Why this is still free:

- OpenClaw handles search and video analysis
- this task only merges local JSON and text extraction results
- Gaode route links are generated from waypoint names and optional coordinates already found in the video analysis

## OpenClaw Scheduler Example

If your OpenClaw instance supports cron-like task metadata, the task already exposes:

```js
schedule: {
  cron: "15 */6 * * *",
  timezone: "Asia/Shanghai"
}
```

If your OpenClaw UI needs a manual cron expression, use:

```text
15 */6 * * *
```

For the nightly full sweep, add a second scheduled job pointing to the same file with cron:

```text
30 2 * * *
```

## Environment Variables

Optional overrides:

- `OPENCLAW_PROJECT_ROOT`
- `OPENCLAW_ROUTE_TEMPLATE_PATH`
- `OPENCLAW_ROUTE_WAYPOINT_OUTPUT_PATH`
- `OPENCLAW_ROUTE_MAX_ITEMS_PER_KEYWORD`
- `OPENCLAW_ROUTE_MAX_KEYWORDS_PER_ROUTE`

## Recommended Review Flow

After the task runs:

1. open `data/raw/openclaw_route_waypoints.json`
2. compare `navigation.waypoints` with the current route record in `app/services/route_templates.json`
3. keep order first, then supplement coordinates later
4. run `python scripts/validate_route_templates.py`
5. use the generated `amap_export.href` to sanity-check whether the route opens correctly in Gaode