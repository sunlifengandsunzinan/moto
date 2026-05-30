# Moto Mini Program

This directory contains a WeChat Mini Program frontend for the three primary tabs:

- routes
- spots
- me

The Mini Program reads data from the Flask backend JSON APIs:

- `GET /api/moto/routes`
- `GET /api/moto/spots`
- `GET /api/moto/me`

Default local endpoints are configured in `app.js` and `utils/request.js`:

- API base URL: `http://127.0.0.1:6001/api`
- web page base URL: `http://127.0.0.1:6001`

## Run locally

1. Start Flask:

```bash
source .venv/bin/activate
python app.py
```

2. Open the `miniprogram/` directory in WeChat DevTools.
3. If needed, change the base URLs in storage or code to your reachable backend domain.

## Notes

- `pages/webview/index` is used to open existing Flask HTML pages for detail and tool pages.
- On a real device, `127.0.0.1` will not be reachable; replace it with a domain allowed by Mini Program request and web-view settings.