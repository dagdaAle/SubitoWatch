"""Write backend/openapi.json, the API contract checked by the snapshot test: uv run python -m app.export_openapi"""
import json
from pathlib import Path

from app.main import app

PATH = Path(__file__).resolve().parents[1] / 'openapi.json'


def render() -> str:
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True) + '\n'


if __name__ == '__main__':
    PATH.write_text(render())
    print(f'scritto {PATH}')
