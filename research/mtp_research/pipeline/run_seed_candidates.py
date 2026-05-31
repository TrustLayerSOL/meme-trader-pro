"""CLI for seeding local launch candidates."""

from __future__ import annotations

import argparse

from research.mtp_research.pipeline.candidate_seed_loader import (
    seed_registry_from_file,
    write_example_seed_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed local candidate registry.")
    parser.add_argument("--seed-path", default="data/seeds/candidate_seeds.jsonl")
    parser.add_argument("--registry-path")
    parser.add_argument("--write-example", action="store_true")
    args = parser.parse_args()

    if args.write_example:
        output_path = write_example_seed_file(args.seed_path)
        print(f"example_seed_path={output_path}")
        print("network_calls=0")
        return 0

    counts = seed_registry_from_file(args.seed_path, registry_path=args.registry_path)
    print(f"inserted={counts['inserted']}")
    print(f"updated={counts['updated']}")
    print(f"skipped={counts['skipped']}")
    print(f"seed_path={args.seed_path}")
    print(f"registry_path={args.registry_path or 'data/normalized/candidate_registry.jsonl'}")
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
