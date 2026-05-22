"""Load and merge config from YAML files and environment variables."""

import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

_DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_config(config_dir: str = None) -> dict:
    load_dotenv()
    base = Path(config_dir) if config_dir else _DEFAULT_CONFIG_DIR

    def _load(name):
        path = base / name
        return yaml.safe_load(path.read_text()) if path.exists() else {}

    instruments = _load("instruments.yaml")
    strategy = _load("strategy.yaml")
    risk = _load("risk.yaml")

    # Environment variable overrides
    if os.getenv("ACCOUNT_SIZE"):
        for key in ("fractional", "volatility_target"):
            if key in risk:
                risk[key]["account_size"] = float(os.getenv("ACCOUNT_SIZE"))

    return {
        **instruments,
        **strategy,
        "risk": risk,
    }
