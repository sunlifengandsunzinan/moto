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