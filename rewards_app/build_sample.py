"""Build the app's bundled 100,000-customer sample.

    python -m rewards_app.build_sample

Generates the reward_stress profile at 100,000 customers (default seed) into
generator/out/reward_stress_100k unless it is already there, builds the
account frame from the engine's ledger, and writes it to
samples/reward_stress_100k_accounts.parquet. The raw tables are far too large
for the repo (generator/out/ is git-ignored); the account frame is all the
app needs. Takes several minutes.
"""
from __future__ import annotations
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.rewards import data as D  # noqa: E402

N = 100_000
SEED = 20260921
OUT = ROOT / "generator" / "out" / "reward_stress_100k"
SAMPLE = ROOT / "samples" / "reward_stress_100k_accounts.parquet"


def generate(out: Path, n: int = N, seed: int = SEED) -> None:
    subprocess.run([sys.executable, "-W", "ignore", "-m", "generator.run", "--profile", "reward_stress",
                    "--n", str(n), "--seed", str(seed), "--out", str(out)], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)


def build(data_dir: Path, path: Path, n: int = N, seed: int = SEED) -> dict:
    t, meta = D.account_frame(data_dir)
    manifest = data_dir / "build_manifest.json"
    meta.update({"data_dir": data_dir.relative_to(ROOT).as_posix() if data_dir.is_relative_to(ROOT) else str(data_dir),
                 "profile": "reward_stress", "customers": n, "seed": seed,
                 "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else None})
    D.save_account_frame(t, meta, path)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--sample", type=Path, default=SAMPLE)
    ap.add_argument("--regenerate", action="store_true", help="regenerate even if --out already has a build")
    a = ap.parse_args()
    if a.regenerate or not (a.out / "build_manifest.json").exists():
        print(f"Generating reward_stress, {N:,} customers -> {a.out}", flush=True)
        generate(a.out)
    meta = build(a.out, a.sample)
    print(f"Wrote {a.sample} - {meta['accounts']:,} card accounts, {meta['first']} to {meta['last']}, "
          f"{a.sample.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
