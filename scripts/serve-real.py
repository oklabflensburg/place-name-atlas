"""Serve the published database without import/reset. Local ports: infra/local.json."""
import json
from pathlib import Path
import uvicorn

root = Path(__file__).resolve().parents[1]
config = json.loads((root / 'infra/local.json').read_text())
# Database settings come from .env / DATABASE_URL (default: system PostgreSQL, 5432).
uvicorn.run('atlas.main:app',host=config['host'],port=config['apiPort'],proxy_headers=False,
            access_log=False,h11_max_incomplete_event_size=65536)
