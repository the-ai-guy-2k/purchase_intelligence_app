"""Start an explicitly labelled, isolated synthetic operator preview."""

import argparse
import os
from pathlib import Path

import uvicorn

from app.config import load_settings
from app.demo import build_demo_app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Regenerate owned demo storage only.")
    args = parser.parse_args()
    os.chdir(Path(__file__).resolve().parent)
    app = build_demo_app(load_settings(), reset=args.reset)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))