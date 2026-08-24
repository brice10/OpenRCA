"""Build a `record_detailed.csv` per dataset: each ground-truth failure enriched
with the log/metric/trace rows sampled in a custom time window around it."""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, project_root)

DATASETS = ["Telecom", "Bank", "Market/cloudbed-1", "Market/cloudbed-2"]
DATA_TYPES = ["log", "metric", "trace"]
TIME_COLUMNS = ["timestamp", "startTime"]
# Any epoch value above this bound is expressed in milliseconds.
MILLISECOND_BOUND = 1e11


def normalize_timestamps(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where(values < MILLISECOND_BOUND, values // 1000)


def find_time_column(columns) -> str | None:
    for name in TIME_COLUMNS:
        if name in columns:
            return name
    return None


def record_days(record_datetime: str, before: int, after: int) -> list[str]:
    """Day folders a window may span, since it can cross midnight."""
    center = datetime.strptime(record_datetime, "%Y-%m-%d %H:%M:%S")
    days = {
        (center - timedelta(seconds=before)).strftime("%Y_%m_%d"),
        center.strftime("%Y_%m_%d"),
        (center + timedelta(seconds=after)).strftime("%Y_%m_%d"),
    }
    return sorted(days)


def render(collected: dict[str, list[str]], schemas: dict[str, str], truncated: set[str]) -> str:
    if not collected:
        return ""
    blocks = []
    for fname in sorted(collected):
        rows = collected[fname]
        block = f"#### {fname} Schema: {schemas[fname]}\n" + "\n".join(rows)
        if fname in truncated:
            block += "\n... [truncated]"
        blocks.append(block)
    return "\n\n".join(blocks)


def scan_file(path: str, windows: list[tuple[int, int, int]], max_rows: int, chunk_size: int,
              component: dict[int, str] | None, results: dict, fname: str) -> None:
    """Stream one telemetry file and dispatch matching rows to every window it covers."""
    earliest = min(start for _, start, _ in windows)
    latest = max(end for _, _, end in windows)

    for chunk in pd.read_csv(path, chunksize=chunk_size, dtype=str, low_memory=False):
        time_col = find_time_column(chunk.columns)
        if time_col is None:
            logger.warning(f"no timestamp column in {path}, skipping")
            return

        stamps = normalize_timestamps(chunk[time_col])
        chunk = chunk[stamps.between(earliest, latest)]
        if chunk.empty:
            continue
        stamps = stamps.loc[chunk.index]

        for idx, start, end in windows:
            bucket = results[idx]
            if len(bucket["rows"].get(fname, [])) >= max_rows:
                continue

            selected = chunk[stamps.between(start, end)]
            if component is not None and "cmdb_id" in selected.columns:
                target = component[idx]
                selected = selected[selected["cmdb_id"].fillna("").str.contains(target, regex=False)]
            if selected.empty:
                continue

            bucket["schemas"][fname] = ",".join(selected.columns)
            bucket["counts"][fname] = bucket["counts"].get(fname, 0) + len(selected)
            stored = bucket["rows"].setdefault(fname, [])
            room = max_rows - len(stored)
            if len(selected) > room:
                bucket["truncated"].add(fname)
                selected = selected.head(room)
            stored.extend(selected.astype(str).agg(",".join, axis=1).tolist())


def process_dataset(dataset: str, args) -> None:
    record_path = f"dataset/{dataset}/record.csv"
    if not os.path.exists(record_path):
        logger.error(f"{record_path} not found, skipping {dataset}")
        return

    records = pd.read_csv(record_path)
    records["timestamp"] = records["timestamp"].astype(float).astype(int)
    logger.info(f"[{dataset}] {len(records)} failure records")

    day_to_records = defaultdict(list)
    for idx, row in records.iterrows():
        for day in record_days(row["datetime"], args.before, args.after):
            day_to_records[day].append(idx)

    results = {
        idx: {
            data_type: {"rows": {}, "schemas": {}, "counts": {}, "truncated": set()}
            for data_type in DATA_TYPES
        }
        for idx in records.index
    }
    components = dict(records["component"]) if args.component_only else None

    telemetry_root = f"dataset/{dataset}/telemetry"
    for day in sorted(day_to_records):
        day_path = f"{telemetry_root}/{day}"
        if not os.path.isdir(day_path):
            continue

        windows = [
            (idx, records.at[idx, "timestamp"] - args.before, records.at[idx, "timestamp"] + args.after)
            for idx in day_to_records[day]
        ]

        for data_type in DATA_TYPES:
            type_path = f"{day_path}/{data_type}"
            if not os.path.isdir(type_path):
                continue
            for fname in sorted(os.listdir(type_path)):
                if not fname.endswith(".csv"):
                    continue
                logger.info(f"[{dataset}] scanning {day}/{data_type}/{fname}")
                scan_file(
                    path=f"{type_path}/{fname}",
                    windows=windows,
                    max_rows=args.max_rows,
                    chunk_size=args.chunk_size,
                    component=components,
                    results={idx: results[idx][data_type] for idx, _, _ in windows},
                    fname=fname,
                )

    for data_type in DATA_TYPES:
        records[data_type] = [
            render(results[idx][data_type]["rows"], results[idx][data_type]["schemas"],
                   results[idx][data_type]["truncated"])
            for idx in records.index
        ]
        records[f"{data_type}_count"] = [
            sum(results[idx][data_type]["counts"].values()) for idx in records.index
        ]

    records["window_start"] = records["timestamp"] - args.before
    records["window_end"] = records["timestamp"] + args.after

    output_path = args.output or f"dataset/{dataset}/record_detailed.csv"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    records.to_csv(output_path, index=False)
    logger.info(f"[{dataset}] saved {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", nargs="+", default=DATASETS, help="datasets to process")
    parser.add_argument("--before", type=int, default=300, help="seconds kept before the failure")
    parser.add_argument("--after", type=int, default=300, help="seconds kept after the failure")
    parser.add_argument("--max-rows", type=int, default=50, help="row cap per telemetry file per record")
    parser.add_argument("--chunk-size", type=int, default=500_000, help="rows per read_csv chunk")
    parser.add_argument("--component-only", action="store_true",
                        help="keep only rows whose cmdb_id matches the root cause component")
    parser.add_argument("--output", type=str, default=None,
                        help="output path (only valid with a single --dataset)")
    args = parser.parse_args()

    if args.output and len(args.dataset) > 1:
        parser.error("--output can only be used with a single --dataset")

    for dataset in args.dataset:
        process_dataset(dataset, args)
