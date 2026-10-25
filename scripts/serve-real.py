"""Serve the published database without import/reset; accept an explicit port profile."""
import json
import os
from pathlib import Path
import uvicorn

root = Path(__file__).resolve().parents[1]
config_path = Path(os.environ.get('ATLAS_LOCAL_CONFIG', root / 'infra/local.json'))
if not config_path.is_absolute():
    config_path = root / config_path
config = json.loads(config_path.read_text())
# Database settings come from .env / DATABASE_URL (default: system PostgreSQL, 5432).
uvicorn.run('atlas.main:app',host=config['host'],port=config['apiPort'],proxy_headers=False,
            access_log=False,h11_max_incomplete_event_size=65536)
