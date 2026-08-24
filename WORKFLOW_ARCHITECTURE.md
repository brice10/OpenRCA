# Adaptation Scenarios Workflow: Technical Architecture & Implementation

This document provides a comprehensive technical breakdown of the 4-step pipeline for generating adaptation scenarios, including heuristic filtering logic, agent integration patterns, and data flow specifications.

---

## Pipeline Overview

```
OpenRCA Failure Records (record.csv)
           ↓
┌──────────────────────────────────────────────────────┐
│ STEP 1: Contextual Extraction                        │
│ Script: main/extract_record_details.py               │
│ Input: record.csv + Telemetry files (logs/metrics)   │
│ Heuristics: Failure reason → filtering patterns      │
│ Output: record_detailed.csv (enriched with context)  │
└──────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────┐
│ STEP 2: Task Specification Design                    │
│ File: main/task_specification.json                   │
│ Defines: Agent instructions, action taxonomy,        │
│          scoring rubric, domain constraints          │
│ Output: Agent-ready specification document           │
└──────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────┐
│ STEP 3: Prompt Generation                            │
│ Script: main/generate.py                             │
│ Input: record_detailed.csv + task_specification.json │
│ Process: For each record, build LLM prompt           │
│ Output: Prompt files or prompt batch                 │
└──────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────┐
│ STEP 4: Agent Execution & Dataset Completion         │
│ Script: main/run_agent_standard.py                   │
│ Input: Generated prompts                             │
│ Process: Agent generates adaptation actions per      │
│          failure record; rank by priority            │
│ Output: adaptation_data.csv or enhanced records      │
└──────────────────────────────────────────────────────┘
```

---

## STEP 1: Contextual Extraction — Heuristic Filtering & Data Sampling

### Purpose
Extract only the most relevant log, metric, and trace data surrounding each failure. This reduces noise and focuses analysis on actionable signals.

### Key Concept: Heuristic Filtering

A **heuristic** is a rule-based pattern that maps failure characteristics to relevant telemetry data.

**Example Heuristic Mapping**:

```python
HEURISTIC_RULES = {
    # If failure is about CPU, extract CPU-related metrics
    "high_cpu": {
        "metric_patterns": [
            "cpu_utilization", "cpu_user_time", "cpu_system_time", 
            "context_switches", "load_average"
        ],
        "log_patterns": [
            "CPU", "cpu", "process throttle", "overload"
        ],
        "trace_keywords": ["slow", "long_duration", "timeout"]
    },
    
    # If failure is about memory, extract memory metrics
    "high_memory": {
        "metric_patterns": [
            "memory_usage", "memory_percent", "heap_size", "rss_memory",
            "page_faults", "swap_usage", "gc_pause_time"
        ],
        "log_patterns": [
            "OutOfMemory", "memory pressure", "OOM", "gc", "garbage collection"
        ],
        "trace_keywords": ["allocation", "memory", "gc"]
    },
    
    # If failure is about disk, extract I/O and disk metrics
    "high_disk_io": {
        "metric_patterns": [
            "io_latency", "io_throughput", "queue_depth", "reads_per_sec",
            "writes_per_sec", "disk_util_percent"
        ],
        "log_patterns": [
            "I/O", "disk", "write", "read", "latency"
        ],
        "trace_keywords": ["I/O", "filesystem", "storage"]
    },
    
    # If failure is about network, extract network metrics
    "network_latency": {
        "metric_patterns": [
            "latency_ms", "packet_loss", "jitter", "bandwidth",
            "connection_attempts", "connection_failures"
        ],
        "log_patterns": [
            "timeout", "connection refused", "network error", "latency"
        ],
        "trace_keywords": ["network", "rpc", "timeout", "unreachable"]
    },
    
    # If failure is about database, extract database-specific data
    "database_performance": {
        "metric_patterns": [
            "query_latency", "connection_pool_usage", "transaction_time",
            "lock_wait_time", "replication_lag"
        ],
        "log_patterns": [
            "query", "transaction", "connection", "lock", "deadlock", "replication"
        ],
        "trace_keywords": ["sql", "query", "transaction"]
    }
}
```

### Implementation: `extract_record_details.py`

**Algorithm**:

1. **Load OpenRCA failure records** (`record.csv`):
   - Each row contains: failure_id, timestamp, datetime, component, failure_reason, etc.

2. **For each failure record**:
   - Determine failure_reason (e.g., "high_memory_usage")
   - Look up heuristic rules for this failure type
   - Calculate time window: `[timestamp - before_seconds, timestamp + after_seconds]`
   - Identify which days this window spans (may cross midnight)

3. **For each relevant day's telemetry**:
   - Iterate through log files, metric files, trace files
   - Stream each file in chunks (default: 500k rows per chunk) to manage memory

4. **For each telemetry file**:
   - Parse timestamp column (normalize from milliseconds to seconds if needed)
   - Filter rows within the time window
   - **Apply heuristic filtering**: Keep only rows matching patterns for this failure type
   - **Apply component filtering** (optional): Keep only rows for the root cause component
   - Cap results at max_rows (default: 50 per file per record) to manage data volume
   - Collect row count, schema, and sample rows

5. **Render output**:
   - Format extracted data as markdown blocks with file names and schemas
   - Mark truncated files with "... [truncated]"
   - Store rendered markdown in new columns: `log`, `metric`, `trace`
   - Add count columns: `log_count`, `metric_count`, `trace_count`

### Configuration Parameters

```bash
python main/extract_record_details.py \
    --dataset Bank Telecom Market/cloudbed-1 \
    --before 300 \                    # seconds before failure
    --after 300 \                     # seconds after failure
    --max-rows 50 \                   # cap per telemetry file
    --chunk-size 500000 \             # rows per read_csv chunk
    --component-only                  # only extract rows matching root cause component
```

### Example Output: `record_detailed.csv`

Original columns from `record.csv` + enriched columns:

```csv
failure_id,timestamp,datetime,component,failure_reason,log,metric,trace,log_count,metric_count,trace_count,window_start,window_end
...
failure_bank_001,1614816000,2021-03-04 10:00:00,database_primary_01,high_memory_usage,"#### db_error.log Schema: timestamp,level,message
2021-03-04 10:02:15 ERROR Connection timeout
2021-03-04 10:02:16 ERROR Pool exhaustion
... [truncated]","#### cpu_metrics.csv Schema: timestamp,host,cpu_percent
2021-03-04 10:00:05 database_primary_01 92.3
2021-03-04 10:00:10 database_primary_01 94.1
... [truncated]","#### trace.json Schema: timestamp,span,duration_ms
2021-03-04 10:00:08 query_execute 2400
2021-03-04 10:00:09 query_execute 2350
...",127,45,89,1614815700,1614816300
```

### Data Structures in Code

**Results Dictionary** (intermediate storage during scanning):
```python
results = {
    record_idx: {
        data_type: {  # "log", "metric", "trace"
            "rows": {},           # {filename: [row1, row2, ...]}
            "schemas": {},        # {filename: "col1,col2,col3"}
            "counts": {},         # {filename: row_count}
            "truncated": set()    # {filenames that exceeded max_rows}
        }
    }
}
```

### Performance Considerations

| Factor | Impact | Optimization |
|--------|--------|---|
| Large telemetry files | High memory usage | Stream with chunking (500k rows/chunk) |
| Many records × many days | Long runtime | Parallelize by dataset |
| Wide time windows | More rows to scan | Use reasonable defaults (±300 sec) |
| No heuristic filtering | Lots of noise data | Implement filtering per failure type |

---

## STEP 2: Task Specification Design — Agent Instructions

### Purpose
Define the adaptation problem in structured form so the agent understands:
- What adaptation actions are expected
- How to score and prioritize actions
- Constraints and domain knowledge
- Output format requirements

### Structure: `task_specification.json`

```json
{
  "task_name": "Adaptation Action Generation for System Failures",
  "task_description": "Given a failure scenario with observation, cause, and context, identify prioritized mitigation actions.",
  
  "failure_categories": {
    "infrastructure": {
      "description": "Hardware or OS-level failures (CPU, memory, disk, I/O)",
      "examples": ["high_cpu", "high_memory", "disk_saturation", "io_latency"],
      "typical_actions": [
        "scale_horizontally",
        "scale_vertically",
        "kill_runaway_process",
        "restart_service",
        "emergency_cleanup"
      ]
    },
    "network": {
      "description": "Network-layer failures (latency, packet loss, connectivity)",
      "examples": ["high_latency", "packet_loss", "connection_timeouts"],
      "typical_actions": [
        "increase_timeout",
        "add_retry_logic",
        "implement_circuit_breaker",
        "route_to_backup_link",
        "increase_bandwidth"
      ]
    },
    "application": {
      "description": "Application logic or service failures",
      "examples": ["memory_leak", "connection_pool_exhaustion", "cache_invalidation"],
      "typical_actions": [
        "kill_leaking_process",
        "deploy_hotfix",
        "increase_pool_size",
        "implement_rate_limiting",
        "fix_config"
      ]
    }
  },

  "action_schema": {
    "action_id": "string (unique identifier, e.g., 'scale_db_01')",
    "action_name": "string (human-readable name)",
    "target_component": "string (component to be modified)",
    "action_type": "enum [curative, preventive] (immediate vs. future-focused)",
    "description": "string (what should be done, include specific parameters if applicable)",
    "priority": "enum [P0, P1, P2, P3] (urgency level)",
    "priority_score": "integer 0-100 (numerical ranking)",
    "estimated_time_to_resolve": "string (e.g., '5 minutes', '2 hours')",
    "estimated_impact": "string (e.g., 'reduce query latency by 95%')",
    "risk_level": "enum [low, medium, high] (implementation risk)",
    "rationale": "string (why this action is recommended, linking to observation/cause)"
  },

  "priority_scoring_rubric": {
    "P0_critical": {
      "description": "Active threat to availability or data integrity",
      "urgency_weight": 0.95,
      "examples": [
        "Connection pool exhausted → Kill batch job immediately",
        "Memory saturation in <5 minutes → Restart service immediately",
        "Disk at 99% → Emergency cleanup immediately"
      ]
    },
    "P1_high": {
      "description": "Service degraded but functional; resolve within hours",
      "urgency_weight": 0.80,
      "examples": [
        "Query latency degraded 60% due to missing index → Recreate index (30 min)",
        "Cache hit rate dropped 80% → Deploy cache fix (1-2 hours)"
      ]
    },
    "P2_medium": {
      "description": "System working; efficiency or resilience improvement; resolve within days",
      "urgency_weight": 0.65,
      "examples": [
        "Batch job takes 2x longer → Implement rate limiting (4 hours)",
        "Log aggregation missing 30% → Fix logging pipeline (4-8 hours)"
      ]
    },
    "P3_low": {
      "description": "Minor improvements; nice-to-have; resolve at convenience",
      "urgency_weight": 0.40,
      "examples": [
        "Query timeout too aggressive → Increase timeout + add backoff (2 hours)"
      ]
    }
  },

  "domain_constraints": {
    "scaling_rules": [
      "Horizontal scaling can increase infrastructure cost; prioritize if cost-justified",
      "Vertical scaling may require downtime; schedule during maintenance windows",
      "Cloud instances can scale in <5 minutes; on-premise servers may need days"
    ],
    "deployment_windows": [
      "Production deployments preferred during low-traffic windows (02:00-06:00 UTC)",
      "Hot-fixes can deploy immediately in emergency (P0)",
      "Regular updates should go through full testing (P1/P2)"
    ],
    "component_specific": {
      "database": "Config changes generally low-risk; schema changes require backup",
      "cache": "Invalidation/config changes can be tested in-place with monitoring",
      "api_gateway": "Rate limiting changes need load testing first",
      "application_service": "Restart causes brief downtime; must be graceful"
    }
  },

  "output_format": {
    "type": "JSON array of action objects",
    "ordering": "Sorted by priority_score descending (highest priority first)",
    "validation_rules": [
      "Each action must have all required fields",
      "priority_score must match priority level",
      "rationale must reference observation or cause",
      "estimated_time_to_resolve must be realistic",
      "For P0: must include immediate action; curative actions preferred"
    ]
  }
}
```

### Key Design Decisions

1. **Action Type Classification** (Curative vs. Preventive):
   - **Curative**: Kill processes, restart services, emergency cleanup (minutes)
   - **Preventive**: Deploy code fixes, config changes, infrastructure upgrades (hours/days)

2. **Priority Framework**:
   - **P0**: Active threat requiring immediate intervention (minutes)
   - **P1**: Significant degradation requiring urgent attention (hours)
   - **P2**: Efficiency improvement or preventive measure (days)
   - **P3**: Optional optimization (as time permits)

3. **Scoring Formula**:
   ```
   priority_score = (urgency_weight × 40) + (impact_score × 35) + (risk_score × 25)
   
   Where:
   - urgency_weight ∈ [0.4, 0.8, 0.95, 1.0] based on priority level
   - impact_score ∈ [0, 100]: How much this action reduces degradation
   - risk_score ∈ [0, 100]: 100 = low risk (easily reversible), 0 = high risk
   ```

### Integration with Prompt Generation

The task specification is passed to the agent at prompt time:

```python
# In generate.py
prompt = f"""
TASK SPECIFICATION:
{task_specification}

FAILURE RECORD:
- observation: {record['observation']}
- cause: {record['cause']}
- context: {record['extracted_context']}

INSTRUCTIONS:
Based on the observation and cause, identify and rank adaptation actions.
Each action must follow the schema defined in TASK SPECIFICATION.
Output as JSON array sorted by priority_score descending.
"""
```

---

## STEP 3: Prompt Generation — Building LLM Input

### Purpose
Transform structured failure data into natural-language prompts that guide the adaptation agent toward generating quality mitigation strategies.

### Implementation: `main/generate.py`

**Algorithm**:

```python
def generate_prompts_for_dataset(dataset_name, task_specification):
    # 1. Load enriched failure records
    record_detailed = pd.read_csv(f"dataset/{dataset_name}/record_detailed.csv")
    
    # 2. For each failure record
    for idx, record in record_detailed.iterrows():
        # 3. Build structured input components
        observation = record['observation']
        cause = record['cause']
        extracted_context = record['extracted_context']  # Markdown formatted
        
        # 4. Construct prompt with templates
        prompt = build_prompt(
            observation=observation,
            cause=cause,
            context=extracted_context,
            task_spec=task_specification,
            record_metadata=record
        )
        
        # 5. Save prompt to file
        output_path = f"prompts/{dataset_name}_failure_{idx}.txt"
        save_prompt(prompt, output_path)
```

### Prompt Template Structure

**Typical prompt structure**:

```
=== ADAPTATION ACTION IDENTIFICATION TASK ===

OBJECTIVE:
Identify and rank specific adaptation actions to mitigate the described failure.

FAILURE OBSERVATION (TECHNICAL):
{observation_from_record}

ROOT CAUSE (BUSINESS CONTEXT):
{cause_from_record}

EXTRACTED CONTEXT (TELEMETRY):
{extracted_context_rendered_as_markdown}

AVAILABLE CONTEXT METADATA:
- Dataset: {dataset}
- Component: {component}
- Timestamp: {datetime}
- Failure Nature: {failure_nature}
- Available Logs: {log_count} rows
- Available Metrics: {metric_count} rows
- Available Traces: {trace_count} rows

TASK SPECIFICATION:
{full_task_specification_json}

ADAPTATION ACTION REQUIREMENTS:
1. Identify 3-5 concrete adaptation actions
2. Classify each as CURATIVE (immediate) or PREVENTIVE (future-focused)
3. Assign priority level (P0, P1, P2, P3) with scoring (0-100)
4. Provide specific rationale linking each action to the observation/cause
5. Estimate time-to-resolve and expected impact

OUTPUT FORMAT:
Return a JSON array of action objects matching the schema in TASK SPECIFICATION.
Sort by priority_score descending (highest priority first).
Validate that each action has all required fields.

=== END PROMPT ===
```

### Configuration & Execution

```bash
python main/generate.py \
    --dataset Bank \                  # Target dataset
    --task-spec main/task_specification.json \  # Task definition
    --output prompts/ \               # Output directory
    --template main/prompt_template.txt \  # Custom prompt template
    --batch-size 10                   # Prompts per batch file
```

### Output Format

**Option 1: Individual prompt files**:
```
prompts/
  ├── Bank_failure_0.txt
  ├── Bank_failure_1.txt
  ├── Bank_failure_2.txt
  └── ...
```

**Option 2: Batch file** (for API efficiency):
```json
{
  "batch": [
    {
      "record_id": "failure_bank_001",
      "prompt": "=== ADAPTATION ACTION IDENTIFICATION TASK ===\n..."
    },
    {
      "record_id": "failure_bank_002",
      "prompt": "=== ADAPTATION ACTION IDENTIFICATION TASK ===\n..."
    }
  ]
}
```

### Template Customization

Users can provide custom templates for domain-specific variations:

```jinja2
{# prompt_template.txt #}
=== {{ failure_nature | upper }} FAILURE MITIGATION ===

FAILURE TIMELINE:
- Detected at: {{ datetime }}
- Component: {{ component }}
- Dataset: {{ dataset }}

TECHNICAL SYMPTOM:
{{ observation }}

BUSINESS CONTEXT:
{{ cause }}

TELEMETRY EVIDENCE:
{{ extracted_context }}

Using the task specification provided below, generate prioritized adaptation actions:
{{ task_specification }}

Output as JSON array. Format: action objects with fields defined in task_specification.
```

---

## STEP 4: Agent Execution & Dataset Completion

### Purpose
Execute the adaptation agent on generated prompts to produce mitigation strategies for each failure record.

### Implementation: `main/run_agent_standard.py`

**Algorithm**:

```python
def execute_agent_on_prompts(dataset_name, prompts_dir, task_spec):
    # 1. Load prompts
    prompts = load_prompts_from_directory(prompts_dir)
    
    # 2. Initialize adaptation agent
    agent = AdaptationAgent(task_specification=task_spec)
    
    # 3. For each prompt
    results = []
    for prompt_id, prompt_text in prompts:
        # 4. Call agent (LLM)
        response = agent.generate_actions(prompt_text)
        
        # 5. Parse and validate response
        actions = parse_json_response(response)
        validate_actions(actions, task_spec)
        
        # 6. Enrich with metadata
        result = {
            "record_id": prompt_id,
            "adaptation_actions": actions,
            "priority_score": max(a["priority_score"] for a in actions),
            "agent_reasoning": extract_reasoning(response),
            "generated_at": datetime.now().isoformat()
        }
        results.append(result)
    
    # 7. Merge results with original records
    output = merge_with_original_records(
        record_detailed.csv,
        results
    )
    
    # 8. Save final dataset
    output.to_csv(f"dataset/{dataset_name}/adaptation_data.csv")
    return output
```

### Agent Interface

**Input to Agent**:
- Prompt containing: observation, cause, context, task specification

**Output from Agent**:
- JSON array of adaptation action objects
- Each with: action_id, action_name, description, priority, priority_score, rationale, etc.

**Example Agent Response**:

```json
[
  {
    "action_id": "kill_batch_job_immediate",
    "action_name": "Terminate runaway batch reconciliation job",
    "target_component": "batch_scheduler",
    "action_type": "curative",
    "description": "Stop the month-end reconciliation batch job that is generating 50,000 queries/sec. Kill all processes: `pkill -f month_end_reconciliation`. Reschedule batch for 02:00 UTC tomorrow when traffic is minimal.",
    "priority": "P0",
    "priority_score": 95,
    "estimated_time_to_resolve": "2 minutes",
    "estimated_impact": "Immediately free the 450 exhausted database connections and restore query response times from 2400ms to baseline 120ms",
    "risk_level": "low",
    "rationale": "Observation shows connection pool at 450/500 (exhausted), causing 20x query latency increase. Cause analysis reveals uncontrolled batch queries as the culprit. Killing the batch is the fastest way to restore service (P0 critical: active unavailability)."
  },
  {
    "action_id": "recreate_index_transaction_date",
    "action_name": "Recreate missing database index on transaction_date",
    "target_component": "database_primary_01",
    "action_type": "preventive",
    "description": "The index idx_transaction_date was removed during schema migration on 2021-03-02. Recreate with: `CREATE INDEX idx_transaction_date ON transactions(transaction_date);`. This should reduce query execution time by 60-75%.",
    "priority": "P1",
    "priority_score": 85,
    "estimated_time_to_resolve": "30 minutes",
    "estimated_impact": "Reduce batch query execution time by 60-75%; prevent future batch-induced connection pool exhaustion",
    "risk_level": "low",
    "rationale": "Preventive measure addressing root cause of query slowness. Missing index is why batch queries take 10x longer than normal, exhausting the connection pool. Index recreation is standard DBA maintenance with minimal risk."
  },
  {
    "action_id": "implement_batch_rate_limiting",
    "action_name": "Implement query rate limiting on batch reconciliation job",
    "target_component": "batch_scheduler",
    "action_type": "preventive",
    "description": "Modify batch job configuration to enforce: max 5,000 queries/sec (10% of database capacity). This ensures batch and concurrent user traffic can coexist. Update configuration file: batch_config.yaml: max_queries_per_sec: 5000",
    "priority": "P2",
    "priority_score": 72,
    "estimated_time_to_resolve": "4 hours (including testing in staging)",
    "estimated_impact": "Eliminate future batch-induced service degradation; allow batch and production traffic to coexist",
    "risk_level": "medium",
    "rationale": "Prevents recurrence by enforcing safe execution parameters. Requires testing in staging to ensure batch still completes within SLA."
  }
]
```

### Execution Configuration

```bash
python main/run_agent_standard.py \
    --dataset Bank \                          # Target dataset
    --prompts prompts/ \                      # Prompt directory
    --task-spec main/task_specification.json \
    --model gpt-4 \                           # LLM model
    --max-tokens 2048 \                       # Response token limit
    --temperature 0.7 \                       # Creativity (lower = more consistent)
    --output dataset/Bank/adaptation_data.csv \
    --batch-size 10 \                         # Prompts to process in parallel
    --parallel-workers 3
```

### Agent Variations

**Standard Agent** (`run_agent_standard.py`):
- Sequential processing, standard LLM calls
- Use for single-run generation, smaller datasets

**Balanced Sampling Agent** (`run_sampling_balanced.py`):
- Stratified sampling of failure records by type
- Use for efficiency when all failure types are represented

**Oracle Agent** (`run_sampling_oracle.py`):
- Uses known oracle actions as examples
- Use for quality improvement or evaluation

### Output: `adaptation_data.csv`

Enriches `record_detailed.csv` with:

| Column | Format | Example |
|--------|--------|---------|
| adaptation_actions | JSON | `[{action_id: "...", priority: "P0", ...}, ...]` |
| priority_score | Integer | `95` |
| top_action_id | String | `"kill_batch_job_immediate"` |
| agent_reasoning | Text | `"Observed connection pool exhaustion (450/500)..."` |
| generated_at | ISO timestamp | `"2024-08-24T14:30:00Z"` |

### Validation & Quality Assurance

**Post-generation validation checks**:

```python
def validate_generated_actions(actions, task_spec):
    errors = []
    
    for i, action in enumerate(actions):
        # Check required fields
        required = ["action_id", "action_name", "target_component", "action_type",
                   "description", "priority", "priority_score", "rationale"]
        for field in required:
            if field not in action:
                errors.append(f"Action {i}: missing field '{field}'")
        
        # Check field types and values
        if action.get("priority") not in ["P0", "P1", "P2", "P3"]:
            errors.append(f"Action {i}: invalid priority '{action.get('priority')}'")
        
        if not isinstance(action.get("priority_score"), int) or not 0 <= action.get("priority_score") <= 100:
            errors.append(f"Action {i}: invalid priority_score {action.get('priority_score')}")
        
        if action.get("action_type") not in ["curative", "preventive"]:
            errors.append(f"Action {i}: invalid action_type '{action.get('action_type')}'")
        
        # Check rationale references observation/cause
        if not action.get("rationale"):
            errors.append(f"Action {i}: missing rationale")
        
    return errors
```

### Error Handling & Retry Logic

```python
def generate_with_retry(prompt, agent, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = agent.generate_actions(prompt)
            actions = parse_json_response(response)
            errors = validate_generated_actions(actions, task_spec)
            
            if not errors:
                return actions
            else:
                logger.warning(f"Validation errors (attempt {attempt+1}): {errors}")
        except Exception as e:
            logger.error(f"Generation failed (attempt {attempt+1}): {e}")
    
    # Fallback: return empty actions with error indicator
    return [
        {
            "action_id": "error_no_actions_generated",
            "error": f"Failed after {max_retries} attempts",
            "priority": "P0",
            "priority_score": 0
        }
    ]
```

---

## Data Flow & Integration

### Cross-Step Data Dependencies

```
Step 1 Output: record_detailed.csv
  ├── Columns: (original from record.csv) + extracted_context fields
  ├── New columns: log, metric, trace, log_count, metric_count, trace_count
  └── Purpose: Provides rich context for agent

Step 2 Output: task_specification.json
  └── Purpose: Defines what agent should do (loaded during Step 3 & 4)

Step 3 Output: prompts/ directory
  ├── Files: prompt_<record_id>.txt or batch_prompts.json
  └── Purpose: LLM input (loaded during Step 4)

Step 4 Output: adaptation_data.csv
  ├── Rows: 1 row per failure (same as record_detailed.csv)
  ├── New columns: adaptation_actions (JSON), priority_score, etc.
  └── Purpose: Final dataset with adaptation actions
```

### Schema Evolution

```
record.csv (OpenRCA)
    │
    ├─→ + Step 1 extracts context
    │
record_detailed.csv
    │
    ├─→ + Step 2 defines spec
    ├─→ + Step 3 generates prompts
    │
    ├─→ + Step 4 generates actions
    │
adaptation_data.csv (FINAL)
```

### Integration Points with OpenRCA

| OpenRCA Component | Usage |
|---|---|
| `record.csv` | Source: failure records with timestamps, components, failure reasons |
| `generate.py` pattern | Adapted for adaptation action generation (prompts instead of diagnoses) |
| Agent framework | Can reuse OpenRCA agent execution patterns |
| Evaluation scripts | Can adapt evaluation metrics (correctness, coverage of action types) |

---

## Performance & Scalability

### Computational Requirements

| Step | Input Size | Typical Runtime | Bottleneck |
|------|---|---|---|
| Step 1 (Extraction) | 50 failures × 10 GB telemetry | 2-5 hours | File I/O + heuristic matching |
| Step 2 (Spec) | Task spec definition | <1 minute | Manual work (one-time) |
| Step 3 (Generation) | 50 failures | 5-10 minutes | Prompt construction |
| Step 4 (Agent) | 50 prompts | 10-30 minutes | LLM API latency (depends on model) |

### Optimization Strategies

**Step 1 Optimization**:
- Stream processing (don't load entire files into memory)
- Chunk-based reading (default: 500k rows/chunk)
- Parallel processing by dataset (4 datasets can be processed in parallel)

**Step 4 Optimization**:
- Batch API calls (OpenAI Batch API, etc.)
- Parallel worker threads (default: 3 workers)
- Caching of identical prompts

### Monitoring & Logging

```python
# In extract_record_details.py
logger.info(f"[{dataset}] {len(records)} failure records")
logger.info(f"[{dataset}] scanning {day}/{data_type}/{fname}")
logger.info(f"[{dataset}] saved {output_path}")

# In run_agent_standard.py
logger.info(f"Processing failure {i}/{total}: {record_id}")
logger.info(f"Generated {len(actions)} adaptation actions")
logger.error(f"Failed to generate actions: {error}")
```

---

## Extensibility & Customization

### Adding Custom Heuristics (Step 1)

Users can extend heuristic rules for domain-specific telemetry:

```python
# custom_heuristics.py
CUSTOM_RULES = {
    "cache_performance": {
        "metric_patterns": [
            "cache_hit_ratio", "cache_eviction_rate", "cache_ttl_violations"
        ],
        "log_patterns": ["cache", "eviction", "miss"],
        "trace_keywords": ["cache"]
    }
}

# Merge with standard rules
HEURISTIC_RULES.update(CUSTOM_RULES)
```

### Custom Prompt Templates (Step 3)

```jinja2
{# specialized_template_for_network_failures.txt #}
=== NETWORK FAILURE DIAGNOSIS ===

NETWORK METRICS:
{{ extracted_context }}

Special considerations for network failures:
- Consider cascade effects on dependent services
- Evaluate failover vs. scaling strategies
- Account for ISP/carrier constraints

Generate adaptation actions...
```

### Domain-Specific Task Specifications (Step 2)

```json
{
  "domain": "telecom_networks",
  "failure_categories": {
    "network_latency": {
      "typical_actions": [
        "increase_peering_bandwidth",
        "implement_traffic_engineering",
        "fail_over_to_backup_route"
      ]
    }
  }
}
```

---

## Troubleshooting & Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| Low context quality | Few log/metric/trace rows extracted | Increase `--before` / `--after` window; review heuristic filters |
| Agent timeouts | LLM calls hanging | Reduce token limits; split large prompts into smaller ones |
| Inconsistent priorities | Actions have same content but different scores | Review scoring rubric in task_specification.json |
| Missing adaptation actions | Agent returns empty or error responses | Check prompt format; retry with different model or temperature |
| High latency | Step 4 takes hours for small datasets | Use batch API; increase `--parallel-workers` |

---

## Example: End-to-End Workflow

```bash
# 1. Extract contextual data
python main/extract_record_details.py \
    --dataset Bank \
    --before 300 \
    --after 300 \
    --component-only

# Check output
ls -lh dataset/Bank/record_detailed.csv
wc -l dataset/Bank/record_detailed.csv

# 2. Review task specification (already in repo)
cat main/task_specification.json | jq '.failure_categories'

# 3. Generate prompts
python main/generate.py \
    --dataset Bank \
    --output prompts/

# Check output
ls prompts/ | wc -l

# 4. Execute agent
python main/run_agent_standard.py \
    --dataset Bank \
    --model gpt-4 \
    --output dataset/Bank/adaptation_data.csv \
    --batch-size 5

# Verify results
head -20 dataset/Bank/adaptation_data.csv | cut -d',' -f1-5
python -c "import pandas as pd; df = pd.read_csv('dataset/Bank/adaptation_data.csv'); print(f'Generated actions for {len(df)} failures')"
```

---

**Last Updated**: 2026-08-24  
**Version**: 1.0 - Technical Architecture
