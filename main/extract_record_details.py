"""Build a `record_detailed.csv` per dataset: each ground-truth failure enriched
with the log/metric/trace rows sampled in a custom time window around it."""

import argparse
import heapq
import itertools
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, project_root)

DATASETS = ["Telecom", "Bank", "Market/cloudbed-1", "Market/cloudbed-2"]
DATA_TYPES = ["log", "metric", "trace"]
# Metrics are scanned first so the node/pod topology index is ready for logs and traces.
SCAN_ORDER = ["metric", "log", "trace"]
TIME_COLUMNS = ["timestamp", "startTime"]
# Any epoch value above this bound is expressed in milliseconds.
MILLISECOND_BOUND = 1e11
# Ranking weight that always puts failed spans above slow ones.
ERROR_WEIGHT = 1e12
# Returned by the scope resolver when the component cannot be mapped onto a file.
NO_MATCH = object()

row_counter = itertools.count()


def normalize_timestamps(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where(values < MILLISECOND_BOUND, values // 1000)


def service_of(component: str) -> str:
    """`shippingservice2-0` -> `shippingservice`, so failover pods map to their service."""
    return re.sub(r"\d+$", "", re.sub(r"-\d+$", "", component))


def join_patterns(patterns) -> str | None:
    return "|".join(patterns) if patterns else None


def match_any(frame: pd.DataFrame, columns: list[str], pattern: str) -> pd.Series:
    mask = pd.Series(False, index=frame.index)
    for column in columns:
        if column in frame.columns:
            mask |= frame[column].fillna("").astype(str).str.contains(
                pattern, case=False, regex=True, na=False)
    return mask


class Topology:
    """Node <-> pod placement learned from the container metric ids while scanning."""

    def __init__(self, config: dict):
        self.file = config["file"]
        self.column = config.get("id_column", "cmdb_id")
        self.pattern = re.compile(config["pattern"])
        self.node_to_pods = defaultdict(set)
        self.pod_to_node = {}

    def update(self, frame: pd.DataFrame, fname: str) -> None:
        if fname != self.file or self.column not in frame.columns:
            return
        for value in frame[self.column].dropna().unique():
            matched = self.pattern.match(str(value))
            if matched:
                node, pod = matched.group("node"), matched.group("pod")
                self.node_to_pods[node].add(pod)
                self.pod_to_node[pod] = node


class FilterSpec:
    def __init__(self, config: dict):
        self.schema = config.get("schema", {})
        self.scope = config.get("component_scope", {})
        self.reasons = config.get("reasons", {})
        self.default_reason = config.get("default_reason")
        self.topology_config = config.get("topology")
        self._warned = set()

    def file_rule(self, reason: str, data_type: str, fname: str) -> dict | None:
        block = self.reasons.get(reason)
        if block is None:
            if reason not in self._warned:
                self._warned.add(reason)
                logger.warning(f"reason '{reason}' is not in the filter file, using default_reason")
            block = self.default_reason or {}
        return (block.get(data_type) or {}).get(fname)

    def component_pattern(self, level: str, fname: str, component: str, topology: Topology | None):
        scope = self.scope.get(level) or self.scope.get("default") or {}
        template = scope[fname] if fname in scope else scope.get("default")
        if template is None:
            return None

        replacements = {"{component}": re.escape(component), "{service}": re.escape(service_of(component))}
        if "{node}" in template:
            node = topology.pod_to_node.get(component) if topology else None
            if not node:
                return NO_MATCH
            replacements["{node}"] = re.escape(node)
        if "{pods}" in template:
            pods = topology.node_to_pods.get(component) if topology else None
            if not pods:
                return NO_MATCH
            replacements["{pods}"] = "(?:" + "|".join(re.escape(pod) for pod in sorted(pods)) + ")"

        pattern = template
        for key, value in replacements.items():
            pattern = pattern.replace(key, value)
        return pattern


def load_filter(path: str, dataset: str) -> FilterSpec:
    if os.path.isdir(path):
        path = os.path.join(path, f"{dataset.split('/')[0]}.json")
    with open(path, encoding="utf-8") as handle:
        return FilterSpec(json.load(handle))


def select_component(selected: pd.DataFrame, spec: FilterSpec | None, meta_row: dict, fname: str,
                     file_schema: dict, topology: Topology | None, component_only: bool) -> pd.DataFrame:
    if spec is None:
        if component_only and "cmdb_id" in selected.columns:
            return selected[selected["cmdb_id"].fillna("").str.contains(meta_row["component"], regex=False)]
        return selected

    pattern = spec.component_pattern(meta_row["level"], fname, meta_row["component"], topology)
    if pattern is NO_MATCH:
        return selected.iloc[0:0]
    if pattern is None:
        return selected

    columns = file_schema.get("id_columns") or (
        [file_schema["id_column"]] if "id_column" in file_schema else [])
    columns = [column for column in columns if column in selected.columns]
    if not columns:
        return selected
    return selected[match_any(selected, columns, pattern)]


def apply_rule(selected: pd.DataFrame, rule: dict, file_schema: dict) -> pd.DataFrame:
    kpi_column = file_schema.get("kpi_column")
    if kpi_column and kpi_column in selected.columns:
        include = join_patterns(rule.get("kpi_include"))
        if include:
            selected = selected[match_any(selected, [kpi_column], include)]
        exclude = join_patterns(rule.get("kpi_exclude"))
        if exclude and not selected.empty:
            selected = selected[~match_any(selected, [kpi_column], exclude)]

    message_columns = file_schema.get("message_columns") or []
    if message_columns and not selected.empty:
        include = join_patterns(rule.get("message_include"))
        if include:
            selected = selected[match_any(selected, message_columns, include)]
        exclude = join_patterns(rule.get("message_exclude"))
        if exclude and not selected.empty:
            selected = selected[~match_any(selected, message_columns, exclude)]

    for column, patterns in (rule.get("column_include") or {}).items():
        pattern = join_patterns(patterns)
        if pattern and column in selected.columns and not selected.empty:
            selected = selected[match_any(selected, [column], pattern)]
    return selected


def anomaly_scores(frame: pd.DataFrame, file_schema: dict) -> list[float]:
    duration_column = file_schema.get("duration_column")
    if duration_column and duration_column in frame.columns:
        durations = pd.to_numeric(frame[duration_column], errors="coerce").fillna(0.0)
    else:
        durations = pd.Series(0.0, index=frame.index)

    status_column = file_schema.get("status_column")
    if status_column and status_column in frame.columns:
        ok_values = {str(value).lower() for value in file_schema.get("status_ok_values", [])}
        errors = ~frame[status_column].astype(str).str.strip().str.lower().isin(ok_values)
    else:
        errors = pd.Series(False, index=frame.index)

    return (errors.astype(float) * ERROR_WEIGHT + durations).tolist()


def store_rows(bucket: dict, fname: str, selected: pd.DataFrame, rule: dict, file_schema: dict,
               max_rows: int) -> None:
    strategy = rule.get("strategy") or ("anomaly" if file_schema.get("duration_column") else "head")
    limit = rule.get("max_rows", max_rows)
    bucket["schemas"][fname] = ",".join(selected.columns)
    bucket["counts"][fname] = bucket["counts"].get(fname, 0) + len(selected)
    texts = selected.astype(str).agg(",".join, axis=1)

    if strategy == "anomaly":
        heap = bucket["ranked"].setdefault(fname, [])
        for score, text in zip(anomaly_scores(selected, file_schema), texts):
            if len(heap) < limit:
                heapq.heappush(heap, (score, next(row_counter), text))
                continue
            bucket["truncated"].add(fname)
            if heap and score > heap[0][0]:
                heapq.heapreplace(heap, (score, next(row_counter), text))
        return

    stored = bucket["rows"].setdefault(fname, [])
    room = limit - len(stored)
    if len(texts) > room:
        bucket["truncated"].add(fname)
    if room > 0:
        stored.extend(texts.head(room).tolist())


def finalize(bucket: dict) -> None:
    for fname, heap in bucket["ranked"].items():
        bucket["rows"][fname] = [text for _, _, text in sorted(heap, key=lambda item: (-item[0], item[1]))]


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


def scan_file(path: str, windows: list[tuple[int, int, int]], args, results: dict, fname: str,
              data_type: str, spec: FilterSpec | None, meta: dict, topology: Topology | None) -> None:
    """Stream one telemetry file and dispatch matching rows to every window it covers."""
    earliest = min(start for _, start, _ in windows)
    latest = max(end for _, _, end in windows)
    file_schema = spec.schema.get(fname, {}) if spec else {}

    for chunk in pd.read_csv(path, chunksize=args.chunk_size, dtype=str, low_memory=False):
        time_col = find_time_column(chunk.columns)
        if time_col is None:
            logger.warning(f"no timestamp column in {path}, skipping")
            return

        stamps = normalize_timestamps(chunk[time_col])
        chunk = chunk[stamps.between(earliest, latest)]
        if chunk.empty:
            continue
        stamps = stamps.loc[chunk.index]
        if topology is not None:
            topology.update(chunk, fname)

        for idx, start, end in windows:
            bucket = results[idx]
            if spec is None:
                rule = {}
                if len(bucket["rows"].get(fname, [])) >= args.max_rows:
                    continue
            else:
                rule = spec.file_rule(meta[idx]["reason"], data_type, fname)
                if rule is None:
                    continue

            selected = chunk[stamps.between(start, end)]
            if selected.empty:
                continue
            selected = select_component(selected, spec, meta[idx], fname, file_schema, topology,
                                        args.component_only)
            if selected.empty:
                continue
            selected = apply_rule(selected, rule, file_schema)
            if selected.empty:
                continue

            store_rows(bucket, fname, selected, rule, file_schema, args.max_rows)


def process_dataset(dataset: str, args) -> None:
    record_path = f"dataset/{dataset}/record.csv"
    if not os.path.exists(record_path):
        logger.error(f"{record_path} not found, skipping {dataset}")
        return

    records = pd.read_csv(record_path)
    records["timestamp"] = records["timestamp"].astype(float).astype(int)
    logger.info(f"[{dataset}] {len(records)} failure records")

    spec = load_filter(args.filter, dataset) if args.filter else None
    topology = Topology(spec.topology_config) if spec and spec.topology_config else None
    meta = {
        idx: {
            "reason": str(records.at[idx, "reason"]),
            "component": str(records.at[idx, "component"]),
            "level": str(records.at[idx, "level"]) if "level" in records.columns else "default",
        }
        for idx in records.index
    }

    day_to_records = defaultdict(list)
    for idx, row in records.iterrows():
        for day in record_days(row["datetime"], args.before, args.after):
            day_to_records[day].append(idx)

    results = {
        idx: {
            data_type: {"rows": {}, "ranked": {}, "schemas": {}, "counts": {}, "truncated": set()}
            for data_type in DATA_TYPES
        }
        for idx in records.index
    }

    telemetry_root = f"dataset/{dataset}/telemetry"
    for day in sorted(day_to_records):
        day_path = f"{telemetry_root}/{day}"
        if not os.path.isdir(day_path):
            continue

        windows = [
            (idx, records.at[idx, "timestamp"] - args.before, records.at[idx, "timestamp"] + args.after)
            for idx in day_to_records[day]
        ]

        for data_type in SCAN_ORDER:
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
                    args=args,
                    results={idx: results[idx][data_type] for idx, _, _ in windows},
                    fname=fname,
                    data_type=data_type,
                    spec=spec,
                    meta=meta,
                    topology=topology,
                )

    for idx in records.index:
        for data_type in DATA_TYPES:
            finalize(results[idx][data_type])
            if not results[idx][data_type]["rows"]:
                logger.warning(f"[{dataset}] record {idx} ({meta[idx]['reason']} on "
                               f"{meta[idx]['component']}): no {data_type} row matched the filters")

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
                        help="keep only rows whose cmdb_id matches the root cause component "
                             "(ignored when --filter is used, the filter file drives the scoping)")
    parser.add_argument("--filter", type=str, default=None,
                        help="path to a heuristics JSON file, or a directory holding <Dataset>.json")
    parser.add_argument("--output", type=str, default=None,
                        help="output path (only valid with a single --dataset)")
    args = parser.parse_args()

    if args.output and len(args.dataset) > 1:
        parser.error("--output can only be used with a single --dataset")
    if args.filter and not os.path.exists(args.filter):
        parser.error(f"--filter path not found: {args.filter}")

    for dataset in args.dataset:
        process_dataset(dataset, args)
