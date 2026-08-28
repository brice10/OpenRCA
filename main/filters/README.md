# Telemetry filters

Heuristics used by [`main/extract_record_details.py`](../extract_record_details.py) to keep only the
telemetry that can justify a failure, instead of every row inside the time window.

Without `--filter`, the script keeps the first `--max-rows` rows of every telemetry file in the window
(very noisy). With `--filter`, each record's `reason` selects the files, KPIs, log messages and trace
strategy that are relevant to that specific failure type.

## Usage

```bash
# directory: <Dataset>.json is resolved from the dataset name
python main/extract_record_details.py --dataset Market/cloudbed-1 --filter main/filters

# explicit file
python main/extract_record_details.py --dataset Bank --filter main/filters/Bank.json
```

`Market/cloudbed-1` and `Market/cloudbed-2` both resolve to `Market.json` (only the part before `/`
is used). `--component-only` is ignored when `--filter` is given: component scoping then comes from
the `component_scope` section.

## Available files

| File | Reasons | Notes |
| --- | --- | --- |
| `Market.json` | 15 | node / pod / service levels, node↔pod topology, `log_service` + `log_proxy` |
| `Bank.json` | 8 | single scope level, JVM/GC oriented rules, traces not component-scoped |
| `Telecom.json` | 5 | no log files, KPI column is `name`, trace ids matched on `cmdb_id`/`dsName`/`serviceName` |

## File structure

```jsonc
{
  "dataset": "Market",
  "schema": { "<file.csv>": { /* column aliases */ } },
  "topology": { /* optional, builds the node <-> pod index */ },
  "component_scope": { "<level>": { "<file.csv>": "<regex template>" } },
  "reasons": { "<reason>": { "<data type>": { "<file.csv>": { /* row filters */ } } } },
  "default_reason": { /* used when a reason is missing from `reasons` */ }
}
```

### `schema`

Describes the columns of each telemetry file, because they differ between datasets.

| Key | Meaning |
| --- | --- |
| `id_column` | column holding the component id (`cmdb_id`, `service`, ...) |
| `id_columns` | list of id columns; a row matches if **any** of them matches |
| `kpi_column` | column holding the KPI name (`kpi_name`, `name`) |
| `message_columns` | columns searched by `message_include` / `message_exclude` |
| `duration_column` | numeric column used for anomaly ranking (`duration`, `elapsedTime`) |
| `status_column` | column telling whether the call succeeded (`status_code`, `success`) |
| `status_ok_values` | values of `status_column` that mean "no error" |

A file listed in `reasons` must exist in `schema`. Timestamps do not need to be declared: the script
detects `timestamp` / `startTime` and converts milliseconds to seconds automatically.

### `topology` (optional)

Learns the node ↔ pod placement while scanning, so a node-level failure can be traced down to the pods
hosted on that node. Metrics are always scanned before logs and traces so the index is ready in time.

```json
"topology": {
  "file": "metric_container.csv",
  "id_column": "cmdb_id",
  "pattern": "^(?P<node>[^.]+)\\.(?P<pod>.+)$"
}
```

The regex must define the named groups `node` and `pod`.

### `component_scope`

Maps the record's `component` onto the id column of each file. Keys are the values of the `level`
column of `record.csv` (`node`, `pod`, `service`); `default` is used when the level is missing or has
no entry. Inside a level, `default` applies to files that are not listed explicitly.

Values are regex templates with these placeholders:

| Placeholder | Replaced by |
| --- | --- |
| `{component}` | the record component, regex-escaped (`shippingservice2-0`) |
| `{service}` | the service it belongs to (`shippingservice2-0` → `shippingservice`) |
| `{node}` | the node hosting the component, from the topology index |
| `{pods}` | alternation of the pods hosted on the component, from the topology index |

A `null` value means "no component filtering for this file" (e.g. service-level metrics during a node
failure). If `{node}` or `{pods}` cannot be resolved, the file yields no row for that record.

Examples from `Market.json`:

```jsonc
"pod":  { "metric_container.csv": "\\.{component}$",        // node-3.shippingservice2-0
          "metric_node.csv":      "^{node}$" },             // the node hosting the pod
"node": { "metric_container.csv": "^{component}\\.",        // all containers of the node
          "trace_span.csv":       "^{pods}$" },             // spans of the pods on the node
"service": { "trace_span.csv":    "^{service}\\d*-\\d+$" }  // all pods of the service
```

### `reasons`

One entry per value of the `reason` column of `record.csv`, then one block per data type
(`metric`, `log`, `trace`), then one entry per file. **A file that is not listed is not read for that
reason** — this is how noise is removed. Omitting a whole data type (e.g. no `trace` block for
`node disk space consumption`) means that column stays empty for those records.

Row filter keys (all patterns are case-insensitive regexes, a list is OR-ed):

| Key | Applies to | Meaning |
| --- | --- | --- |
| `kpi_include` | `kpi_column` | keep only these KPIs |
| `kpi_exclude` | `kpi_column` | drop these KPIs |
| `message_include` | `message_columns` | keep rows whose message matches |
| `message_exclude` | `message_columns` | drop rows whose message matches |
| `column_include` | `{ "<column>": [patterns] }` | keep rows matching in that column (AND across columns) |
| `strategy` | — | `head` (first rows) or `anomaly` (ranked), defaults to `anomaly` when the schema declares a `duration_column`, otherwise `head` |
| `max_rows` | — | per-file row cap, defaults to `--max-rows` |

An empty object `{}` means "keep every row of this file that passes the component scope" — used for
service-level KPI files that only contain rr/sr/mrt/count.

```jsonc
"container CPU load": {
  "metric": {
    "metric_container.csv": { "kpi_include": ["cpu", "thread", "process"] },
    "metric_node.csv":      { "kpi_include": ["cpu", "load"] },
    "metric_service.csv":   {}
  },
  "log":   { "log_service.csv": { "message_include": ["error", "timeout", "deadline", "slow"] } },
  "trace": { "trace_span.csv": {} }
}
```

### `default_reason`

Same shape as a reason block. Used, with a warning, when a record's reason is absent from `reasons`
(e.g. a new failure type). Keep it permissive.

## Trace ranking

Traces use the `anomaly` strategy: a bounded heap keeps the best `max_rows` spans, scored as

```
score = (status_column not in status_ok_values) * 1e12 + duration
```

so failed spans come first, then the slowest ones. Rows are written in decreasing score order, and
`... [truncated]` is appended when more rows matched than the cap. `head` keeps the chronologically
first rows instead.

## Behaviour when nothing matches

If the filters return no row for a record and a data type, the cell is left empty and a warning is
logged:

```
[Market/cloudbed-1] record 12 (node CPU spike on node-4): no log row matched the filters
```

There is no fallback to unfiltered sampling — an empty cell is a signal that the heuristics need to be
adjusted for that reason.

## Adding or tuning a reason

1. Check the reason and component vocabulary in `rca/baseline/rca_agent/prompt/basic_prompt_<Dataset>.py`.
2. Add the reason key, list only the files that carry evidence for it, and keep KPI patterns short and
   token-based (`cpu`, `mem`, `fs_read`, `retrans`) so they survive the naming differences between
   datasets (`container_cpu_used`, `system.cpu.iowait`, `OSLinux-CPU_CPU_CPUCpuUtil`).
3. Re-run the extraction and check `metric_count`, `log_count` and `trace_count` in the generated
   `record_detailed.csv`: counts are computed before truncation, so they show how selective a rule is.
