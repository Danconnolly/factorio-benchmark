"""Physical runtime assets shipped with the benchmark wheel."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeAssets:
    """Absolute filesystem locations of assets needed by a smelt session."""

    broker: Path
    scenario: Path
    baseline: Path


def runtime_assets() -> RuntimeAssets:
    """Return installed package paths, never paths inferred from a checkout."""
    root = Path(__file__).with_name("assets")
    assets = RuntimeAssets(
        broker=root / "scripts" / "factorio_constrained_broker.py",
        scenario=root / "scenarios" / "smelt-one-iron-plate.v2.json",
        baseline=root / "fixtures" / "smelt-one-iron-plate-baseline.v2.zip",
    )
    for path in (assets.broker, assets.scenario, assets.baseline):
        if not path.is_file():
            raise RuntimeError(f"installed benchmark asset is missing: {path}")
    return assets
