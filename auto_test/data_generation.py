import csv
import random
import os
import argparse
from typing import Optional

# ==========================================
# CONFIGURATION
# ==========================================
TOTAL_IDS = 1_000_000


def resolve_mix(sparsity: float, mix: Optional[tuple]):
    """Map the requested sparsity onto per-decile strategy counts.

    The four strategies partition the 10 id-deciles. NULLs in outer joins come
    from BROKEN (dangling dst) and PARTIAL (missing/skipped links) chains, so
    higher sparsity grows those at the expense of COMPLETE (fully-matching)
    chains. An explicit `mix=(broken,partial,complete,dup)` overrides sparsity.
    """
    if mix is not None:
        broken, partial, complete, dup = mix
        if min(mix) < 0 or sum(mix) != 10:
            raise ValueError(f"--mix must be four non-negative ints summing to 10, got {mix}")
        return broken, partial, complete, dup
    sparsity = max(0.0, min(1.0, sparsity))
    complete = max(0, round(3 * (1 - sparsity)))   # s=0→3 dense, s=0.8→1, s=1→0
    dup = 1
    rest = 10 - complete - dup
    broken = rest // 2
    partial = rest - broken
    return broken, partial, complete, dup


def generate_csvs(k: int, total_ids: int = TOTAL_IDS, output_dir: Optional[str] = None,
                  seed: Optional[int] = None, sparsity: float = 0.8,
                  mix: Optional[tuple] = None, partial_skip: Optional[float] = None):
    if k < 1:
        raise ValueError("k must be >= 1")

    if seed is not None:
        random.seed(seed)

    # Strategy mix (the sparsity "dimension"): cumulative decile cut points, plus
    # the intra-partial link-skip probability (more skips ⇒ more NULL padding).
    n_broken, n_partial, n_complete, n_dup = resolve_mix(sparsity, mix)
    t_broken = n_broken
    t_partial = n_broken + n_partial
    t_complete = n_broken + n_partial + n_complete
    if partial_skip is None:
        partial_skip = min(0.9, 0.15 + 0.6 * max(0.0, min(1.0, sparsity)))
    print(f"Strategy mix (deciles): broken={n_broken} partial={n_partial} "
          f"complete={n_complete} dup={n_dup}  partial_skip={partial_skip:.2f}")

    # Default output dir name: R1R{k}_data
    if output_dir is None:
        output_dir = f"R1R{k}_data"

    # 1. Setup Output Directory
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # 2. File Handles for R1..Rk
    tables = [f"R{i}" for i in range(1, k + 1)]
    files: dict[str, object] = {}
    writers: dict[str, csv.writer] = {}

    def chain_keys(i: int):
        """
        Create a deterministic chain of keys for R1..Rk.
        For a "perfect chain":
          Rj: (src=keys[j-1], dst=keys[j]) for j=1..k
        """
        base = i * 10
        keys = [base + j * 100 for j in range(k + 1)]  # length k+1
        return keys

    try:
        for t in tables:
            f = open(f"{output_dir}/{t}.csv", "w", newline="")
            files[t] = f
            w = csv.writer(f)
            writers[t] = w
            # w.writerow(["src", "dst"])

        print(f"Generating {total_ids} IDs for tables: {', '.join(tables)}")
        print("Patterns: broken chains, partial chains, complete chains, duplicate keys")

        for i in range(1, total_ids + 1):
            # Force first 30 IDs to cover all edge cases deterministically
            if i <= 30:
                signature = i % 16
            else:
                signature = random.randint(0, 15)

            keys = chain_keys(i)
            decile = i % 10

            # Strategy 1: BROKEN CHAINS — dst dangles, so outer joins NULL-extend
            if decile < t_broken:
                # Create edges, but break links by pointing to non-existent "next src"
                for j in range(1, k + 1):
                    if signature & (1 << ((j - 1) % 4)):  # repeat bitmask over k
                        src = keys[j - 1]
                        dst = keys[j] + 1_000_000_000 + j * 17  # unlikely to match any src
                        writers[f"R{j}"].writerow([src, dst])

                # Also add some isolated/orphan rows
                if signature & 8:
                    j = random.randint(1, k)
                    writers[f"R{j}"].writerow([keys[0] + 4_000_000_000, keys[0] + 5_000_000_000])

            # Strategy 2: PARTIAL CHAINS — truncated/holed chains force NULL padding
            elif decile < t_partial:
                # Create a chain but skip a random table/link to force NULL padding in outer joins
                break_at = random.randint(1, k)  # stop generating after this table
                for j in range(1, k + 1):
                    if j > break_at:
                        continue
                    # Randomly skip an intermediate link sometimes
                    if 1 < j < k and random.random() < partial_skip:
                        continue
                    writers[f"R{j}"].writerow([keys[j - 1], keys[j]])

            # Strategy 3: COMPLETE CHAINS — fully matching, no NULLs
            elif decile < t_complete:
                for j in range(1, k + 1):
                    writers[f"R{j}"].writerow([keys[j - 1], keys[j]])

            # Strategy 4: DUPLICATE KEYS — exercises multiset multiplicity
            else:
                bucket = (i // 100) * 100
                keys2 = chain_keys(bucket)

                # Pick a couple tables to duplicate rows in
                dup_tables = {random.randint(1, k)}
                if k >= 2 and random.random() < 0.5:
                    dup_tables.add(random.randint(1, k))

                for j in range(1, k + 1):
                    row = [keys2[j - 1], keys2[j]]
                    writers[f"R{j}"].writerow(row)
                    if j in dup_tables:
                        writers[f"R{j}"].writerow(row)  # duplicate

    finally:
        for f in files.values():
            f.close()

    print("\nData Generation Complete!")
    print(f"Files saved to '{output_dir}/' (tables R1..R{k})")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate join-stress CSVs for R1..Rk.")
    parser.add_argument(
        "--k",
        type=int,
        default=7,  # default number of tables
        help="Number of tables to generate (R1..Rk). Default: 4.",
    )
    parser.add_argument(
        "--total-ids",
        type=int,
        default=TOTAL_IDS,
        help=f"Number of IDs to generate. Default: {TOTAL_IDS}.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory. Default: R1R{k}_data (derived from --k).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility. Default: None (no fixed seed).",
    )
    parser.add_argument(
        "--sparsity",
        type=float,
        default=0.8,
        help="0=dense (more complete chains, fewer NULLs) .. 1=sparse "
             "(more broken/partial chains, more NULLs). Default: 0.8.",
    )
    parser.add_argument(
        "--mix",
        type=str,
        default=None,
        help="Explicit decile mix 'broken,partial,complete,dup' summing to 10 "
             "(overrides --sparsity). E.g. '5,4,0,1' for maximum NULLs.",
    )
    parser.add_argument(
        "--partial-skip",
        type=float,
        default=None,
        help="Prob. of skipping an intermediate link in a partial chain "
             "(more skips ⇒ more NULLs). Default: derived from --sparsity.",
    )
    args = parser.parse_args()

    mix = tuple(int(x) for x in args.mix.split(",")) if args.mix else None
    generate_csvs(k=args.k, total_ids=args.total_ids, output_dir=args.output_dir,
                  seed=args.seed, sparsity=args.sparsity, mix=mix,
                  partial_skip=args.partial_skip)
