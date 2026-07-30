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

- devtools simulator web base URL: `http://127.0.0.1:5000`
- phone preview / real device web base URL: `https://www.xingtu.ltd`
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
3. If needed, change the single phone-side backend address in `utils/backend-config.js`, then restart the Mini Program so the refreshed default config is written back to storage.
4. To enable `vConsole` during remote debugging, install the Mini Program dependency and run WeChat DevTools `Tools -> Build NPM` after opening `miniprogram/`.

## Notes

- `pages/webview/index` is used to open existing Flask HTML pages for detail and tool pages.
- `vConsole` initialization is wired in `app.js` via `utils/debug-console.js`. If the dependency has not been built into the Mini Program yet, startup will skip it without crashing.
- The simulator and phone now intentionally use different default hosts: `127.0.0.1` for devtools, `https://www.xingtu.ltd` for preview and real-device debugging.
- Backend base URL storage now lives under the single key `backendConfig`; stale cached configs are invalidated automatically when the bundled backend-config version changes, and legacy `backendConfig.v2`, `backendConfig.v3`, `backendConfig.v4`, `apiBaseUrl`, and `webBaseUrl` are cleared automatically.
- The production HTTPS domain is expected to reverse-proxy to the backend listener on `127.0.0.1:6001`.
- On a real device, ensure the Mini Program request domain and web-view business domain both allow `https://www.xingtu.ltd`.