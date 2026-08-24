# `extract_record_details` — Failure-centric telemetry extraction

Builds a `record_detailed.csv` for each OpenRCA dataset: every ground-truth failure
from `record.csv`, enriched with the log / metric / trace rows observed in a custom
time window around the failure timestamp.

Script: `main/extract_record_details.py`

---

## 1. Purpose

`record.csv` only states *what* failed, *why*, and *when*. It does not contain the
telemetry evidence of the failure. This script joins the two:

```
record.csv (labels)  +  telemetry/{DATE}/{log,metric,trace}/*.csv  ->  record_detailed.csv
```

The result is a single, self-contained table where each row is one incident together
with the raw observability signals surrounding it. Typical uses:

- inspecting what a failure actually looks like in the data,
- building supervised datasets (features around a labelled fault),
- sanity-checking that a fault is observable in a given window,
- producing compact evidence bundles for prompting.

---

## 2. Usage

```bash
python -m main.extract_record_details [options]
```

Run from the repository root (the script resolves `dataset/...` relative to the
working directory).

### Examples

```bash
# All four datasets, default +/- 5 minutes
python -m main.extract_record_details

# Single dataset, asymmetric window: 10 min before, 2 min after
python -m main.extract_record_details --dataset Bank --before 600 --after 120

# Both Market cloudbeds, keep only rows of the root cause component
python -m main.extract_record_details \
    --dataset Market/cloudbed-1 Market/cloudbed-2 --component-only

# Narrow window, more rows per file, custom destination
python -m main.extract_record_details \
    --dataset Telecom --before 60 --after 60 --max-rows 200 \
    --output test/telecom_detailed.csv
```

### Options

| Option | Default | Description |
|---|---|---|
| `--dataset` | all four | One or more of `Telecom`, `Bank`, `Market/cloudbed-1`, `Market/cloudbed-2` |
| `--before` | `300` | Seconds kept **before** the failure timestamp |
| `--after` | `300` | Seconds kept **after** the failure timestamp |
| `--max-rows` | `50` | Max rows rendered per telemetry file per record |
| `--chunk-size` | `500000` | Rows per `read_csv` chunk (memory/speed trade-off) |
| `--component-only` | off | Keep only rows whose `cmdb_id` matches the root cause component |
| `--output` | `dataset/{DATASET}/record_detailed.csv` | Output path; only allowed with a single `--dataset` |

`--before` and `--after` are independent, so the window can be asymmetric — useful
because the causal signal usually precedes the recorded failure time.

---

## 3. Output schema

All original `record.csv` columns are preserved (`level`, `reason`, `component`,
`timestamp`, `datetime`), plus:

| Column | Type | Description |
|---|---|---|
| `log` | text | Log rows in the window, grouped per source file |
| `log_count` | int | Total matching log rows found (before the `--max-rows` cap) |
| `metric` | text | Metric rows in the window, grouped per source file |
| `metric_count` | int | Total matching metric rows found |
| `trace` | text | Trace spans in the window, grouped per source file |
| `trace_count` | int | Total matching spans found |
| `window_start` | int | Epoch seconds, `timestamp - before` |
| `window_end` | int | Epoch seconds, `timestamp + after` |

The `*_count` columns report what was actually found, while the text columns are
capped by `--max-rows` — so a count much larger than the rendered rows is normal.

### Cell format

Each telemetry cell groups rows by their source file:

```
#### metric_app.csv Schema: serviceName,startTime,avg_time,num,succee_num,succee_rate
osb_001,1586534580000,0.5231,359,359,1.0
osb_001,1586534640000,0.5268,385,385,1.0
... [truncated]

#### metric_container.csv Schema: itemid,name,bomc_id,timestamp,value,cmdb_id
999999996381347,container_session_used,ZJ-004-058,1586534689000,0.000000,docker_001
```

- one `#### <file> Schema: <columns>` header per source file,
- rows are the raw CSV values, comma-joined, in file order,
- `... [truncated]` marks that `--max-rows` was reached for that file.

Empty cells mean no telemetry matched (for example Telecom has no `log` directory,
so `log` is always empty there).

---

## 4. How it works

1. **Load labels** — reads `dataset/{DATASET}/record.csv` and casts `timestamp` to int.
2. **Map records to days** — each record's window is converted to the day folders it
   can touch. A window crossing midnight also pulls the adjacent day, so no data is
   lost at day boundaries.
3. **Stream telemetry** — for every `telemetry/{DAY}/{TYPE}/*.csv`, the file is read
   once with `pandas.read_csv(chunksize=...)`. Streaming is required: the datasets are
   12–25 GB each and cannot be loaded into memory.
4. **Dispatch to windows** — each chunk is first coarsely filtered to the union of all
   windows of that day, then each record's own window selects its rows. A file is read
   once regardless of how many records fall on that day.
5. **Optional component filter** — with `--component-only`, rows are additionally
   filtered on `cmdb_id` containing the record's root cause component.
6. **Render and save** — rows are grouped per file, capped, and written to
   `record_detailed.csv`.

### Timestamp handling

Telemetry uses two different time columns and two different units:

- the time column is `timestamp` or `startTime`, detected per file,
- values above `1e11` are treated as milliseconds and divided by 1000.

This mirrors the normalisation already used in `rca/run_sampling_balanced.py`.

### Timezone

Faults are recorded in **UTC+8**. The day folder is derived from the record's
`datetime` string, which is already expressed in that timezone, so no conversion is
applied. Comparisons themselves are done on epoch values and are timezone-independent.

---

## 5. Practical notes

- **Runtime is dominated by traces.** `trace_span.csv` is by far the largest file of
  each day; a full run over all datasets scans roughly 66 GB.
- **Restrict the scope** with `--dataset` when iterating.
- **A sparse window is expected.** Telemetry has a fixed sampling frequency, so a very
  small window (a few seconds) may legitimately return nothing for some files.
- **`--component-only` only filters files that have a `cmdb_id` column.** Application
  level files such as Bank's `metric_app.csv` have none and are therefore returned
  unfiltered.
- **Cell size** grows quickly with `--max-rows`; keep it low if the CSV is meant to be
  opened in a spreadsheet.

---

## 6. Requirements

Uses `pandas` and `loguru` from `requirements.txt`.

Note the pinned `pandas==1.5.3` is not ABI-compatible with NumPy 2.x. If you hit:

```
ValueError: numpy.dtype size changed, may indicate binary incompatibility.
```

install a compatible NumPy:

```bash
pip install "numpy<2"
```
