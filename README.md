# Adaptation Scenarios Dataset: Extending OpenRCA for System Mitigation

## Overview

This project extends the foundational OpenRCA benchmark to create a comprehensive **Adaptation Scenarios Dataset**. While OpenRCA provides the mechanism to identify root causes of failures in complex systems, this adaptation project takes the analysis one step further: it identifies and prioritizes the concrete actions needed to mitigate or prevent those failures.

### Objective

Transform failure analysis data into actionable mitigation strategies by creating a dataset that captures:
- **What failed** (Observation): Technical descriptors of system behavior anomalies
- **Why it failed** (Cause): Business logic and contextual reasons
- **How to fix it** (Adaptation Actions): Prioritized, actionable mitigation strategies

## The Adaptation Scenario Data Model

An **Adaptation Scenario** is a structured representation of a failure and its resolution pathway. It consists of three interdependent components:

### 1. The Observation
**Definition**: The implementable description of a dynamic behavior on a metric or set of metrics that causes (or is likely to cause) a system failure.

**Characteristics**:
- Technical and metric-focused
- Automatically detectable or measurable
- Observable from logs, metrics, and traces
- Examples:
  - CPU utilization exceeds 95% for 5+ consecutive minutes
  - Disk I/O latency increases from <5ms to >50ms
  - Network packet loss rate jumps from 0% to 15%
  - Memory heap usage grows linearly, reaching saturation in <2 hours

### 2. The Cause
**Definition**: A human-understandable description of the business logic or operational event that triggered the observation.

**Characteristics**:
- Context-rich and business-aware
- Provides the "why" behind the technical observation
- Derived from logs, metrics, traces, and domain knowledge
- Examples:
  - Website promotion campaign launched, causing 10x traffic surge
  - Scheduled batch job concurrency set to 500, overwhelming database connection pool
  - Disk cleanup job failed silently for 7 days, leading to gradual capacity exhaustion
  - Third-party API latency increased from 100ms to 2s, cascading to application layer

**Key Distinction from Observation**:
- Observation describes *what* happened (metric behavior)
- Cause explains *why* it happened (operational/business context)

### 3. Adaptation Actions
**Definition**: The specific actions required to mitigate the failure, categorized by urgency and approach.

**Characteristics**:
- Actionable and component-specific
- Prioritized by criticality
- Classified as **curative** or **preventive**

**Curative Actions**: Address the immediate failure state
- Example: Immediately kill runaway database processes consuming 85% of CPU
- Urgency: Address within minutes
- Priority scoring: Higher (active system threat)

**Preventive Actions**: Stop future occurrences by addressing root patterns
- Example: Implement gradual disk space monitoring and alert when >85% full
- Urgency: Address within hours/days
- Priority scoring: Medium-to-High (prevents repeated incidents)

**Priority Scoring Framework**:
- **Critical (P0)**: Must be fixed immediately; system is actively degraded
  - Example: Memory leak causing 30% memory increase/hour → allocate resources to identify leak
- **High (P1)**: Should be fixed within hours; significant resource waste or degradation risk
  - Example: Poor cache hit ratio (20% vs expected 80%) → optimize cache strategy
- **Medium (P2)**: Should be fixed within days; improves efficiency or prevents future incidents
  - Example: Log aggregation missing 40% of entries → improve log configuration
- **Low (P3)**: Nice to have; minor improvements to resilience or efficiency
  - Example: Startup time is 5% slower than baseline → profile startup sequence

### Additional Dataset Columns

| Column | Description |
|--------|-------------|
| **failure_nature** | Category of failure: `Network`, `Infrastructure`, or `Application` |
| **extracted_context** | Relevant excerpts from logs, metrics, and traces that justify and support the observation |
| **complete_description** | Narrative summary of the entire adaptation scenario from failure detection to resolution |
| **component** | System component affected (e.g., database, cache, API gateway) |
| **observation** | Technical metric-based description of the failure symptom |
| **cause** | Business/operational explanation of why the failure occurred |
| **adaptation_actions** | JSON or structured list of mitigation actions with priorities |
| **priority_score** | Weighted priority (0-100) considering criticality and complexity |

## Technical Architecture: 4-Step Implementation Workflow

The adaptation scenario dataset is built through a systematic pipeline:

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Contextual Extraction                                   │
│ Extract relevant log/metric/trace data around each failure       │
│ Output: record_detailed.csv per dataset                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Adaptation Agent Task Specification                      │
│ Define agent instructions and task specifications                │
│ Output: task_specification.json                                  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Generation Script Execution                              │
│ Generate prompts for adaptation action identification            │
│ Output: prompt files for agent consumption                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Completion & Output                                      │
│ Execute adaptation agent and generate final adaptation_data.csv │
│ Output: Complete adaptation scenarios dataset                    │
└─────────────────────────────────────────────────────────────────┘
```

### Step 1: Contextual Extraction Script
**Purpose**: Extract the most precise and concise telemetry context surrounding each failure.

**Mechanism**:
- Uses heuristic rules mapping failure types to data filtering patterns
- Example: If `failure_reason = "high_memory_usage"`, extract only memory-related metrics
- Scans log files, metric snapshots, and distributed traces within configurable time windows (default: ±5 minutes)
- Samples up to 50 rows per telemetry file per failure record to manage data volume
- Optionally filters to only the component(s) listed as root causes

**Input**:
- `record.csv` (OpenRCA failure records with timestamps and components)
- Telemetry files organized by date under `dataset/{Dataset}/telemetry/{YYYY_MM_DD}/{log|metric|trace}/`

```
.
├── {SYSTEM}
│   ├── query.csv
│   ├── record.csv
|   ├── record_detailed.csv
│   └── telemetry
│       ├── {DATE}
│       │   ├── log
│       │   ├── metric
│       │   └── trace
│       └── ... 
└── ...
```

**Output**:
- `record_detailed.csv`: Original failure records enriched with extracted telemetry excerpts and summary counts

**Key Script**: `main/extract_record_details.py`

### Step 2: Adaptation Agent Task Specification
**Purpose**: Define the adaptation problem in structured form for the agent to understand and solve.

**Components**:
- **Task Definition**: Clear statement of what actions are needed to resolve each failure type
- **Context Templates**: Structured format for presenting observations, causes, and current state
- **Action Schema**: Defined format for adaptation actions (ID, target component, description)
- **Scoring Rubric**: Guidelines for prioritizing actions

**Format**: JSON configuration with sections for:
- Failure categories (Network, Infrastructure, Application)
- Mapping from observations to typical adaptation action families
- Constraints and domain knowledge (e.g., "scaling decisions require approval", "config changes are low-risk")

**Input**: `record_detailed.csv` from Step 1

**Output**: `task_specification.json` guiding the agent's reasoning

**Key Script**: `main/prompt.py` and `main/task_specification.json`

### Step 3: Generation Script
**Purpose**: Create LLM prompts that guide the adaptation agent toward identifying appropriate mitigation actions.

**Mechanism**:
- Loads `record_detailed.csv` and `task_specification.json`
- For each failure record, constructs a detailed prompt containing:
  - The observation (metric behavior)
  - The cause (business context)
  - Extracted telemetry data (logs, metrics, traces)
  - Task instructions (what adaptation actions are expected)
  - Scoring guidelines
- Applies prompt templates for consistency across all records
- Outputs individual prompt files or batch files for agent execution

**Input**:
- `record_detailed.csv`: Enriched failure records
- `task_specification.json`: Agent task definitions
- Telemetry files (accessed as needed)

**Output**: Prompt files ready for agent consumption

**Key Script**: `main/generate.py` (adapted from OpenRCA's original)

### Step 4: Completion & Agent Execution
**Purpose**: Execute the adaptation agent to generate mitigation strategies and compile the final dataset.

**Mechanism**:
- Agent processes each prompt generated in Step 3
- For each failure, the agent identifies and ranks adaptation actions
- Agent provides:
  - List of specific, actionable adaptation actions
  - Priority/criticality scores
  - Rationale linking actions to observations and causes
  - Target component and expected impact
- Results are aggregated into the final adaptation scenarios dataset

**Output**:
- `adaptation_data.csv` or enhanced `record_detailed.csv` with:
  - `adaptation_actions` column: JSON or structured list of actions
  - `priority_scores` column: Prioritized recommendations
  - `reasoning` column: Agent's explanation for action selection

**Integration**: Leverages OpenRCA's agent framework or a specialized adaptation agent built on similar principles

## Datasets

The project includes three comprehensive datasets representing distinct failure domains:

### Bank
- **Domain**: Financial transaction processing system
- **Scale**: 10 failure records with 10 days of telemetry
- **Metrics**: Database query latency, transaction processing time, memory usage
- **Typical Failures**: Query performance degradation, database connection exhaustion

### Telecom
- **Domain**: Telecommunications infrastructure and service delivery
- **Scale**: ~20+ failure records with historical traces from April-May 2020
- **Metrics**: Network latency, packet loss, service availability
- **Typical Failures**: Network degradation, cascading service failures

### Market (cloudbed-1 & cloudbed-2)
- **Domain**: Cloud marketplace and e-commerce platform
- **Scale**: Multiple failure records per cloudbed instance
- **Metrics**: API response times, resource utilization, cache performance
- **Typical Failures**: API gateway overload, cache invalidation issues, resource contention

## Installation & Setup

### Prerequisites
- Python 3.9+
- pandas, numpy
- loguru
- OpenRCA components (for agent integration)

### Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Extract detailed failure context (Step 1)
python main/extract_record_details.py --dataset Bank Telecom "Market/cloudbed-1" "Market/cloudbed-2"

# 3. Review and customize task specification (Step 2)
# Edit main/task_specification.json to match your domain knowledge

# 4. Generate adaptation prompts (Step 3)
python main/generate.py --dataset Bank

# 5. Execute adaptation agent (Step 4)
python main/run_agent_standard.py --dataset Bank --output results/adaptation_data.csv
```

### Configuration

Key command-line parameters:

**extract_record_details.py**:
- `--before`: Seconds of telemetry to capture before failure (default: 300)
- `--after`: Seconds of telemetry to capture after failure (default: 300)
- `--max-rows`: Maximum rows per telemetry file per record (default: 50)
- `--component-only`: Filter telemetry to only the root cause component

**generate.py**:
- `--dataset`: Target dataset (Bank, Telecom, Market/cloudbed-1, Market/cloudbed-2)
- `--prompt-template`: Custom prompt template file
- `--output`: Output directory for generated prompts

**run_agent_standard.py**:
- `--dataset`: Target dataset
- `--model`: LLM model to use (e.g., gpt-4, claude-3)
- `--batch-size`: Number of failures to process in parallel

## Project Roadmap

| Phase | Timeline | Deliverables | Status |
|-------|----------|--------------|--------|
| **Phase 1: Infrastructure** | Weeks 1-2 | Step 1 extraction, data enrichment, schema validation | 🔵 In Progress |
| **Phase 2: Agent Design** | Weeks 2-3 | Task specification, action taxonomy, scoring rubric | 🔵 In Progress |
| **Phase 3: Generation** | Weeks 3-4 | Prompt generation, template development | ⚪ Planned |
| **Phase 4: Agent Execution** | Weeks 4-5 | Adaptation action generation, quality assurance | ⚪ Planned |
| **Phase 5: Analysis & Iteration** | Weeks 5-6 | Dataset analysis, refinement, documentation | ⚪ Planned |

## Directory Structure

```
OpenRCA/
├── dataset/                          # Source datasets
│   ├── Bank/
│   │   ├── record.csv               # OpenRCA failure records
│   │   ├── record_detailed.csv      # Enriched with telemetry (Step 1 output)
│   │   └── telemetry/               # Logs, metrics, traces by date
│   ├── Telecom/
│   └── Market/
├── main/
│   ├── extract_record_details.py    # Step 1: Context extraction
│   ├── prompt.py                    # Prompt construction utilities
│   ├── generate.py                  # Step 3: Prompt generation
│   ├── task_specification.json      # Step 2: Agent task spec
│   ├── run_agent_standard.py        # Step 4: Agent execution
│   └── evaluate.py                  # Results evaluation
├── docs/                            # Project documentation
└── requirements.txt                 # Python dependencies
```

## Key Concepts & Terminology

| Term | Definition |
|------|-----------|
| **Observation** | Technical metric-based description of system behavior anomaly |
| **Cause** | Business/operational context explaining why the failure occurred |
| **Adaptation Action** | Specific, actionable step to mitigate or prevent a failure |
| **Curative Action** | Immediate response to an active failure condition |
| **Preventive Action** | Proactive measure to stop future occurrences |
| **Priority Score** | Numerical rank (0-100) reflecting action urgency and importance |
| **Telemetry Window** | Time window (default ±5 minutes) around failure timestamp for context extraction |
| **Heuristic Filtering** | Rule-based pattern matching to extract only relevant telemetry data |

## Contributing & Support

For questions about the adaptation dataset methodology, refer to the project source and issue tracker. For root cause analysis background, see the [Original OpenRCA Project](https://github.com/IntelLabs/OpenRCA).

## License

This project extends OpenRCA and maintains compatibility with its licensing. See [LICENSE](LICENSE) and [SECURITY.md](SECURITY.md) for details.

---

**Last Updated**: 2026-08-24
**Version**: 1.0 - Foundation Release
