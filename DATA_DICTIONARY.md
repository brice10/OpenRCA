# Adaptation Scenarios Dataset: Data Dictionary & Concepts

This document provides comprehensive definitions of all columns in the adaptation scenarios dataset, with concrete examples illustrating key concepts and decision-making frameworks.

## Core Dataset Schema

### 1. Failure Identification Columns

#### `failure_id`
- **Type**: String (UUID or sequential ID)
- **Source**: Inherited from OpenRCA `record.csv`
- **Description**: Unique identifier for the failure event
- **Example**: `"failure_20210304_bank_001"` or UUID

#### `timestamp`
- **Type**: Unix epoch (seconds)
- **Source**: Inherited from OpenRCA `record.csv`
- **Description**: Exact moment of failure detection (usually when anomaly triggers alerting system)
- **Example**: `1614816000` (2021-03-04 10:00:00 UTC)

#### `datetime`
- **Type**: ISO 8601 string
- **Format**: `"YYYY-MM-DD HH:MM:SS"`
- **Description**: Human-readable timestamp for the failure
- **Example**: `"2021-03-04 10:00:00"`

#### `dataset`
- **Type**: Categorical (Bank | Telecom | Market/cloudbed-1 | Market/cloudbed-2)
- **Description**: Which dataset this failure comes from
- **Example**: `"Bank"`, `"Telecom"`

#### `component`
- **Type**: String
- **Source**: Inherited from OpenRCA root cause analysis
- **Description**: System component identified as the root cause
- **Example**: `"database_primary_01"`, `"api_gateway_02"`, `"cache_node_03"`

---

### 2. Failure Characterization Columns

#### `failure_nature`
- **Type**: Categorical
- **Allowed Values**:
  - `Network`: Network-layer failures (latency, packet loss, connectivity)
  - `Infrastructure`: Hardware or OS-level failures (CPU, memory, disk, I/O)
  - `Application`: Application logic or service failures (bugs, resource leaks, deadlocks)
- **Description**: High-level category of the failure type
- **Usage**: Guides which action families are most relevant

**Examples**:
| Failure Nature | Example Scenario |
|---|---|
| Infrastructure | Database node runs out of disk space; CPU usage exceeds capacity |
| Network | API latency increases; packet loss on interconnect |
| Application | Memory leak in worker process; database connection pool exhaustion |

---

### 3. The Observation Column

#### `observation`
- **Type**: Text (medium-length description)
- **Length**: 100-500 characters typical
- **Source**: Manually written based on log/metric/trace analysis
- **Description**: The *technical, implementable* description of the metric behavior that constitutes the failure

**Key Characteristics**:
- ✅ Metric-focused and quantitative
- ✅ Observable and measurable
- ✅ Can be detected by automated systems
- ✅ Specific thresholds and time durations
- ❌ NOT explanatory of *why* the metrics behave this way
- ❌ NOT business-oriented

**Examples**:

| Good Observation | Why | Poor Observation |
|---|---|---|
| `"CPU usage on database_primary_01 jumps from 15% to 92% within 45 seconds and sustains for 8+ minutes"` | Quantified, specific thresholds, time durations | `"High CPU"` |
| `"Network latency to api_gateway_02 increases from 50ms (baseline) to 1200ms; jitter > 500ms; affects 40% of requests"` | Quantified baseline, specific metrics, scope | `"Slow network"` |
| `"Disk I/O latency on /data partition exceeds 100ms for 95% of operations; queue depth reaches 512 (system max)"` | Specific filesystem, metric (I/O latency), and limits | `"Disk issue"` |
| `"Memory heap usage grows linearly at 15MB/min; heap occupancy reaches 94% (near GC ceiling) in 180 seconds"` | Quantified growth rate, threshold, and timeframe | `"Memory problem"` |

**Real Example from Bank Dataset**:
```
Observation: "Database query response time increases from average 120ms to p95=2400ms; 
             connection pool reaches 450/500 max connections; query queue depth > 200"
```

---

### 4. The Cause Column

#### `cause`
- **Type**: Text (medium-to-long description)
- **Length**: 200-800 characters typical
- **Source**: Manually written based on observation + logs + traces + domain knowledge
- **Description**: The *business logic* or *operational context* explaining why the observation occurred

**Key Characteristics**:
- ✅ Provides business/operational reasoning
- ✅ Explains the causal chain: "because → which led to → resulting in"
- ✅ Draws on domain knowledge (application logic, business events, deployment changes)
- ✅ Links observation back to root operational event
- ❌ NOT just restating the observation
- ❌ NOT vague or speculative

**Observation vs. Cause: The Critical Distinction**

| Observation | Cause |
|---|---|
| **Technical facts about behavior** | **Why behavior changed** |
| "CPU usage jumps to 92%" | "Marketing team launched flash sale, traffic increased 8x; promotional code misconfigured looping queries" |
| "Memory grows at 15MB/min" | "Batch job started with incorrect settings: buffer sizes 100x normal; missing memory cleanup between tasks" |
| "Database connections exhaust 450/500" | "Application deployment v2.4 changed pool size from 200 to 500; query time degraded due to index missing after schema migration" |
| "Network latency jumps to 1200ms" | "ISP maintenance on primary link; traffic rerouted to backup link with 60% capacity" |

**Real Examples from Different Datasets**:

**Bank Dataset - Query Overload**:
```
Observation: Database query response time increases from 120ms to 2400ms; 
             connection pool exhaustion at 450/500 max; query queue > 200 pending

Cause: End-of-month batch reconciliation job started at scheduled time (11:59 PM) 
       without rate limiting. Job generates 50k queries/sec against single database instance. 
       Concurrent user traffic remained normal (~5k queries/sec), but batch overwhelmed 
       connection pool. Index on transaction_date missing after schema migration two days prior.
```

**Telecom Dataset - Network Cascade**:
```
Observation: API latency increases from 50ms baseline to avg 800ms, p99 to 3200ms.
             Downstream service response times degrade proportionally.
             Network packet loss detected at 2% on primary ISP link.

Cause: Third-party ISP announced unscheduled maintenance on primary peering link at 
       14:00 UTC. Network traffic automatically rerouted to secondary link with 60% 
       capacity. Backup link already carrying 40% baseline traffic. Total traffic 
       exceeded backup link capacity, causing congestion and packet loss. Application 
       timeout settings (5 second) too aggressive, causing cascade of retry storms.
```

**Market/CloudBed Dataset - Cache Invalidation**:
```
Observation: Cache hit rate drops from 82% (baseline) to 12%; TTL-based evictions 
             and memory pressure evictions spike 15x normal. Database query load 
             increases 10x (from avg 200 q/s to 2000 q/s).

Cause: Deployment of cache code v3.2 introduced bug in invalidation logic. When 
       any product listing updated, entire product category cache key invalidated 
       instead of just affected product. 8% of all products received updates during 
       busy shopping hour (20:00-21:00). Cascade effect: 15 minute window saw 95% 
       of cache invalidated. Old cache logic (v3.1) would have invalidated ~1-2%.
```

---

### 5. Context & Evidence Columns

#### `extracted_context`
- **Type**: Text (long-form, structured)
- **Format**: Markdown with sections for each telemetry type
- **Source**: Generated by Step 1 extraction script from logs, metrics, traces
- **Description**: Relevant excerpts from telemetry data surrounding the failure timestamp

**Structure** (example output from `record_detailed.csv`):
```markdown
#### log_metrics Schema: timestamp,level,message,component
Line 1245: 2021-03-04 10:02:15 ERROR [db_connection] Connection timeout after 30000ms
Line 1246: 2021-03-04 10:02:16 ERROR [db_connection] Exceeded max pool size 500/500
Line 1247: 2021-03-04 10:02:17 WARN [app] Query queue depth exceeds 200

#### metric_cpu Schema: timestamp,host,cpu_util_percent,load_avg
Line 456: 2021-03-04 10:02:10 database_primary_01 92.3 18.7
Line 457: 2021-03-04 10:02:15 database_primary_01 94.1 22.1

#### trace_calls Schema: timestamp,service,span_name,duration_ms,status
Line 789: 2021-03-04 10:02:20 api_service query_database 2400 TIMEOUT
Line 790: 2021-03-04 10:02:21 api_service query_database 2350 TIMEOUT
```

**Characteristics**:
- Extracted within configurable time window (default: ±5 minutes from failure timestamp)
- Limited to 50 rows per telemetry file per record (to manage data volume)
- Optionally filtered to only root cause component (via `--component-only` flag)
- Includes both raw data samples and summary counts

**Columns in extracted_context output**:
- `log_count`, `metric_count`, `trace_count`: Total rows available in telemetry window
- `log`, `metric`, `trace`: Rendered excerpts with headers and truncation indicators

---

### 6. Adaptation Actions Columns

#### `adaptation_actions`
- **Type**: JSON array
- **Format**: Structured action objects
- **Source**: Generated by adaptation agent (Step 4)
- **Description**: List of specific, prioritized mitigation actions

**Schema for each action object**:
```json
{
  "action_id": "string",           // Unique identifier (e.g., "scale_db_01")
  "action_name": "string",         // Human-readable name
  "target_component": "string",    // Component affected
  "action_type": "string",         // curative | preventive
  "description": "string",         // What should be done
  "priority": "P0 | P1 | P2 | P3", // Urgency level
  "priority_score": 0-100,         // Numerical priority (0=lowest, 100=highest)
  "estimated_time_to_resolve": "string", // Time to implement (e.g., "5 minutes", "2 hours")
  "estimated_impact": "string",    // Expected improvement (e.g., "reduce query time 95%")
  "risk_level": "low | medium | high", // Implementation risk
  "rationale": "string"            // Why this action is recommended
}
```

**Example**: Bank Database Overload Scenario
```json
[
  {
    "action_id": "kill_batch_job",
    "action_name": "Terminate runaway batch job",
    "target_component": "batch_scheduler",
    "action_type": "curative",
    "description": "Stop the month-end reconciliation batch job immediately. Reschedule for 02:00 UTC tomorrow when traffic is minimal.",
    "priority": "P0",
    "priority_score": 95,
    "estimated_time_to_resolve": "2 minutes",
    "estimated_impact": "Free 50k queries/sec; reduce queue depth from 200 to ~10; restore response times to 120-150ms",
    "risk_level": "low",
    "rationale": "Active threat causing total connection pool exhaustion. P0: immediate system degradation."
  },
  {
    "action_id": "add_index_transaction_date",
    "action_name": "Recreate missing database index on transaction_date",
    "target_component": "database_primary_01",
    "action_type": "preventive",
    "description": "Add missing index: CREATE INDEX idx_transaction_date ON transactions(transaction_date). Root cause analysis shows this index missing since schema migration on 2021-03-02.",
    "priority": "P1",
    "priority_score": 85,
    "estimated_time_to_resolve": "30 minutes",
    "estimated_impact": "Reduce query execution time 60-75%; prevent future batch job overload",
    "risk_level": "low",
    "rationale": "Prevents recurrence by addressing query performance root cause. Index creation is low-risk maintenance."
  },
  {
    "action_id": "implement_batch_rate_limiting",
    "action_name": "Add query rate limiting to batch reconciliation",
    "target_component": "batch_scheduler",
    "action_type": "preventive",
    "description": "Modify batch job to use query rate limiter: max 5000 queries/sec (10% of database capacity). Increase batch duration from 1hr to 2hrs.",
    "priority": "P2",
    "priority_score": 72,
    "estimated_time_to_resolve": "4 hours",
    "estimated_impact": "Eliminate future batch-induced connection pool exhaustion; allow concurrent user traffic",
    "risk_level": "medium",
    "rationale": "Prevents recurrence by enforcing safe execution parameters. Requires testing in staging environment."
  },
  {
    "action_id": "adjust_retry_strategy",
    "action_name": "Increase application database query timeout from 5s to 15s",
    "target_component": "application_service",
    "action_type": "preventive",
    "description": "Current 5-second timeout insufficient for legitimate batch operations. Increase to 15s but add exponential backoff with max-retries=3 to prevent retry storms.",
    "priority": "P3",
    "priority_score": 45,
    "estimated_time_to_resolve": "2 hours (code change + testing)",
    "estimated_impact": "Reduce false-positive query failures during legitimate load spikes",
    "risk_level": "medium",
    "rationale": "Improves robustness but lower priority since more aggressive actions address root cause."
  }
]
```

#### `priority_score`
- **Type**: Integer (0-100)
- **Calculation**: Weighted combination of:
  - **Urgency** (40%): How quickly the failure needs addressing
    - P0 (Critical): 90-100
    - P1 (High): 75-89
    - P2 (Medium): 50-74
    - P3 (Low): 0-49
  - **Impact** (35%): How much this action reduces failure severity
    - Critical improvement (>80% degradation reduction): 80-100
    - Significant improvement (50-80%): 60-79
    - Moderate improvement (20-50%): 40-59
    - Minor improvement (<20%): 0-39
  - **Implementation Risk** (25%): How risky to implement
    - Low risk (tested, reversible): 80-100
    - Medium risk (requires monitoring): 50-79
    - High risk (potential side effects): 0-49

**Example Scoring**:
- Kill runaway batch: Urgency 95 × 0.4 + Impact 90 × 0.35 + Risk 85 × 0.25 = **89.5 → 95**
- Add database index: Urgency 80 × 0.4 + Impact 85 × 0.35 + Risk 90 × 0.25 = **84.25 → 85**
- Implement rate limiting: Urgency 70 × 0.4 + Impact 75 × 0.35 + Risk 65 × 0.25 = **71 → 72**

---

### 7. Metadata Columns

#### `window_start`, `window_end`
- **Type**: Unix epoch (seconds)
- **Description**: Time window boundaries for extracted telemetry context
- **Calculation**: `window_start = timestamp - before_seconds`, `window_end = timestamp + after_seconds`
- **Default**: ±300 seconds (5 minutes)
- **Example**: If failure at `1614816000`, default window is `[1614815700, 1614816300]`

#### `log_count`, `metric_count`, `trace_count`
- **Type**: Integer
- **Description**: Total number of rows extracted from each telemetry type
- **Usage**: Indicates data completeness and richness for analysis
- **Interpretation**:
  - High counts (>500): Rich telemetry for deep analysis
  - Medium counts (100-500): Adequate context
  - Low counts (<100): Limited evidence; may need wider time window

#### `complete_description`
- **Type**: Text (long-form narrative)
- **Length**: 500-2000 characters typical
- **Source**: Synthesized by analyst combining observation, cause, and adaptation actions
- **Description**: Executive summary of the end-to-end adaptation scenario

**Format** (narrative flow):
1. What failed (observation)
2. Why it failed (cause)
3. What went wrong (business impact)
4. How to fix it immediately (curative actions)
5. How to prevent recurrence (preventive actions)

**Example (Bank):**
```
At 2021-03-04 10:00:00 UTC, the Bank database experienced severe connection pool 
exhaustion, with query response times degrading from 120ms baseline to 2400ms average. 
The root cause was an unscheduled end-of-month reconciliation batch job that generated 
50,000 queries/second against a single database instance, exhausting the 500-connection 
pool. Additionally, a critical index (idx_transaction_date) was missing due to a schema 
migration performed on 2021-03-02, exacerbating query execution time.

IMMEDIATE MITIGATION: Kill the batch job and reschedule for 02:00 UTC when traffic is 
minimal. This will immediately free the connection pool and restore response times.

LONG-TERM RESOLUTION: (1) Recreate the missing database index to prevent future batch 
job performance degradation. (2) Implement query rate limiting in the batch job to 
ensure maximum 5,000 queries/sec. (3) Improve application timeout handling to prevent 
cascading failures during legitimate load spikes.

Estimated time to restore service: 2 minutes (kill job)
Estimated time to full resolution: 4 hours (testing and deployment of all fixes)
```

---

## Key Conceptual Distinctions

### Curative vs. Preventive: Decision Framework

**Curative Actions** address the immediate failure state.

| Scenario | Curative Action | Why Curative |
|----------|---|---|
| CPU stuck at 92%, blocking service | Kill runaway process; restart service | Fixes immediate problem; service recovers within seconds |
| Database pool exhausted (450/500) | Restart database connection pool; kill idle queries | Immediately frees resources and restores connectivity |
| Memory leak (growing at 20MB/min) | Restart memory-leaking service | Immediate memory pressure relief while root cause is fixed |
| Disk at 98% capacity | Emergency cleanup: delete old logs; archive temp files | Prevents imminent disk-full emergency |

**Curative characteristics**:
- ✅ Can be executed immediately (within minutes)
- ✅ Does not require investigation or testing
- ✅ Reverses immediate symptoms
- ✅ Should be P0/P1 priority

**Preventive Actions** stop future occurrences by addressing root patterns.

| Scenario | Preventive Action | Why Preventive |
|----------|---|---|
| CPU spikes from traffic surge | Implement auto-scaling policy; add load balancer | Prevents recurrence by handling future traffic spikes automatically |
| Database pool exhaustion (missing rate limiting) | Implement batch job rate limiting; configure pool based on expected load | Prevents runaway queries by enforcing safe execution |
| Memory leak in service | Debug and patch memory leak source code; implement memory profiling in CI/CD | Prevents leak recurrence in future deployments |
| Disk capacity issues | Implement disk usage monitoring and alerting at 80% threshold; auto-archive old data | Prevents reaching 98% saturation by proactive action |

**Preventive characteristics**:
- ✅ Requires investigation and testing (4 hours to days)
- ✅ Deployed via code changes, config updates, or infrastructure changes
- ✅ Addresses root cause
- ✅ Prevents future incidents of same type
- ✅ Should be P1/P2 priority (implement within hours/days of incident)

### Priority Levels: Practical Examples

#### P0: Critical — System Actively Degraded
**Definition**: Active threat to service availability or data integrity. Immediate intervention needed.

| Example | Action | Time-to-Fix | Why P0 |
|---------|--------|---|---|
| Database connection pool exhausted | Kill batch job | 2 min | Service completely unavailable without action |
| Memory leak growing 50MB/min (reaching saturation in 5 min) | Restart service | 3 min | Imminent cascade failure; every minute counts |
| Disk at 99% (filesystem will become read-only) | Emergency cleanup | 5 min | Data loss or corruption risk; cannot wait |
| Network link carrying critical traffic fails | Failover to backup | 1 min | All traffic rerouted; potential data loss |

#### P1: High — Significant Degradation
**Definition**: Service degraded but functional. Needs resolution within hours.

| Example | Action | Time-to-Fix | Why P1 |
|---------|--------|---|---|
| Query performance degraded 60% due to missing index | Recreate index | 30 min | Service functional but 40% slower; affects users immediately |
| Cache hit ratio dropped 80% (cache invalidation bug) | Deploy hotfix + restart | 1-2 hours | Database receiving 10x normal load; must fix before cascade |
| Third-party API latency increased 5x due to network issue | Increase timeout; add retry logic | 2 hours | Cascading failures in dependent services |
| Memory growth steady but not yet critical (will saturate in 4 hours) | Deploy memory leak fix | 3 hours | Preventive; still plenty of runway but needs urgent attention |

#### P2: Medium — Incremental Improvement
**Definition**: System working, but efficiency or resilience could be improved. Fix within days.

| Example | Action | Time-to-Fix | Why P2 |
|---------|--------|---|---|
| Batch job takes 2x longer than expected (but completes) | Add query rate limiting | 4 hours | Improves efficiency; allows concurrent user traffic |
| Log aggregation missing 30% of entries | Fix logging pipeline | 4-8 hours | Data quality issue; non-urgent but should be fixed |
| Startup time increased 5% (likely due to extra validation) | Profile and optimize | 2-4 hours | User-facing improvement; can wait until next maintenance window |
| Cache miss rate higher than baseline (but acceptable) | Optimize cache parameters | 3-4 hours | Improves efficiency; not urgent |

#### P3: Low — Nice-to-Have Optimization
**Definition**: Minor improvements to robustness or efficiency. Fix at convenience.

| Example | Action | Time-to-Fix | Why P3 |
|---------|--------|---|---|
| Query timeout too aggressive (5s when 15s needed) | Increase timeout + add backoff | 2 hours | Works, but could be more robust |
| Alerts firing with low signal-to-noise ratio | Tune alert thresholds | 1 hour | Operational improvement; not urgent |
| Database query plans suboptimal (but working) | Refactor query; add more indices | 4-6 hours | Performance optimization; not urgent |

---

## Column Definitions Summary Table

| Column | Type | Source | Key Properties |
|--------|------|--------|---|
| failure_id | String | OpenRCA | Unique identifier |
| timestamp | Unix epoch | OpenRCA | Failure detection time |
| datetime | ISO 8601 | OpenRCA | Human-readable timestamp |
| dataset | Categorical | OpenRCA | Bank \| Telecom \| Market/* |
| component | String | OpenRCA | Root cause component |
| failure_nature | Categorical | Manual | Network \| Infrastructure \| Application |
| observation | Text | Manual | Technical metric description |
| cause | Text | Manual | Business/operational context |
| adaptation_actions | JSON array | Agent | Prioritized mitigation steps |
| priority_score | Integer 0-100 | Calculated | Overall urgency/impact score |
| extracted_context | Text | Step 1 | Log/metric/trace excerpts |
| window_start, window_end | Unix epoch | Calculated | Telemetry extraction window |
| log_count, metric_count, trace_count | Integer | Step 1 | Data completeness indicators |
| complete_description | Text | Manual | Executive narrative |

---

## Data Quality Guidelines

### Writing High-Quality Observations
✅ **DO**:
- Include specific metric names and thresholds
- Provide time durations and growth rates
- Quantify baseline vs. degraded values
- Specify affected components or services

❌ **DON'T**:
- Use vague terms like "slow", "high", "problem"
- Omit time context
- Guess at numbers; use actual data
- Mix observation with cause

### Writing High-Quality Causes
✅ **DO**:
- Link to specific operational events (deployments, promotions, etc.)
- Explain the causal chain
- Reference business context
- Draw on logs, traces, and domain knowledge

❌ **DON'T**:
- Repeat the observation verbatim
- Speculate without evidence
- Write without referencing telemetry
- Make it too detailed; stay at executive level

### Generating Quality Adaptation Actions
✅ **DO**:
- Provide specific, actionable instructions
- Include estimated time and impact
- Distinguish curative (immediate) from preventive (future)
- Provide clear rationale linking to observation/cause

❌ **DON'T**:
- Suggest vague improvements ("optimize", "improve")
- Overlook implementation complexity
- Propose actions without clear connection to root cause
- Forget about testing and rollback procedures

---

**Last Updated**: 2026-08-24  
**Version**: 1.0 - Data Schema Definition
