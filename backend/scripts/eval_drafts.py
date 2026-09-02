"""Live-model draft evaluation (manual, costs API credits).

Redrafts one asset under every preset and prints the measured metrics so
you can judge style separation and quality on real footage before
committing prompt changes:

    cd backend
    python scripts/eval_drafts.py <asset_id> [--brief "extra direction"]

Requires a reachable model endpoint (not DRY_RUN). Golden/CI replay of
*recorded* responses lives in tests/test_golden.py — this script is the
companion for real footage.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.repositories import assets as assets_repo
from app.services.providers.dry import get_provider
from app.styles import enforcement as enf
from app.styles import metrics
from app.styles.presets import list_presets, resolve_style


def evaluate(asset_id: str, brief: str) -> None:
    asset = assets_repo.get_asset(asset_id)
    if asset is None:
        sys.exit(f"asset {asset_id} not found")
    if not asset.frame_notes or asset.meta is None:
        sys.exit("asset has no cached analysis — run the pipeline first")

    provider = get_provider()
    duration = asset.meta.duration_s
    transcript = asset.transcript or None
    print(f"asset {asset_id} ({asset.filename}, {duration:.0f}s)\n")

    header = f"{'preset':<14} {'retention':>9} {'avg seg':>8} {'count':>6} {'ok':>3}"
    print(header)
    print("-" * len(header))
    for preset in list_presets():
        style = resolve_style(preset.preset_id, brief)
        try:
            raw = provider.select_segments(asset.frame_notes, duration, transcript, style=style)
        except Exception as exc:  # noqa: BLE001 — report per-preset failures
            print(f"{preset.preset_id:<14} failed: {exc}")
            continue
        final = enf.enforce_segments(raw, style, duration, transcript)
        bad = "Y" if enf.violates_hard_constraints(final, style) else ""
        print(
            f"{preset.preset_id:<14} "
            f"{metrics.retention(final, duration):>8.1%} "
            f"{metrics.avg_segment_s(final):>7.1f}s "
            f"{len(final):>6} {bad:>3}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_id")
    parser.add_argument("--brief", default="", help="extra natural-language direction")
    args = parser.parse_args()
    if config.DRY_RUN:
        print("NOTE: DRY_RUN=1 — numbers come from the heuristic stub, not a model.\n")
    evaluate(args.asset_id, args.brief)


if __name__ == "__main__":
    main()
