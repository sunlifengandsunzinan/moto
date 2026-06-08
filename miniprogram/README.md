# Moto Mini Program

This directory contains a WeChat Mini Program frontend for the three primary tabs:

- routes
- spots
- me

The Mini Program reads data from the Flask backend JSON APIs:

- `GET /api/moto/routes`
- `GET /api/moto/spots`
- `GET /api/moto/me`

Default local endpoints and request paths are centralized in `utils/backend-config.js`:

- devtools simulator web base URL: `http://127.0.0.1:6001`
- phone preview / real device web base URL: `https://517f3375.r8.vip.cpolar.cn`
- API base URL follows the selected web base URL with `/api`
- unified API paths: `routes`, `spots`, `me`
- unified Mini Program routes: tab pages, route detail, and webview URLs
- backend route and spot payloads now expose structured `mini_program_action` / `mini_program` fields so the frontend can avoid parsing raw href strings

## Run locally

1. Start Flask:

```bash
source .venv/bin/activate
python app.py
```

2. Open the `miniprogram/` directory in WeChat DevTools.
3. If needed, change the single phone-side LAN address in `utils/backend-config.js`, or override `apiBaseUrl` / `webBaseUrl` in storage.

## Notes

- `pages/webview/index` is used to open existing Flask HTML pages for detail and tool pages.
- The simulator and phone now intentionally use different default hosts: `127.0.0.1` for devtools, LAN IP for preview and real-device debugging.
- Backend base URL storage now lives under the single key `backendConfig`; legacy `backendConfig.v2`, `backendConfig.v3`, `backendConfig.v4`, `apiBaseUrl`, and `webBaseUrl` are migrated and cleared automatically.
- If the Mac changes networks, update `DEFAULT_DEVICE_WEB_BASE_URL` in `utils/backend-config.js`.
- On a real device outside the local network, replace the LAN IP with a domain allowed by Mini Program request and web-view settings.