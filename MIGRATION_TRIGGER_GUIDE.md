# Data Migration Trigger Guide

## Overview

When you run `python multi-tier-simulator.py`, **both data placement AND data migration policies are active**.

---

## Timeline: How Data Placement and Migration Work Together

```
┌─────────────────────────────────────────────────────────────────┐
│ SIMULATION START                                                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: INITIALIZATION                                         │
├─────────────────────────────────────────────────────────────────┤
│ File: Trace.py - __init__() method                             │
│                                                                 │
│ ✓ Create RL placement agent (RLPlacement)                      │
│ ✓ Create migration agent (UnifiedAgentSystem)                  │
│ ✓ Initialize tracking structures                               │
│                                                                 │
│ Result: Both agents ready for simulation                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: MAIN SIMULATION LOOP                                  │
├─────────────────────────────────────────────────────────────────┤
│ File: Trace.py - source_trace_rl() method                      │
│ Called for: Each I/O request in the trace file                 │
│                                                                 │
│ REQUEST 1-49: (DATA PLACEMENT ONLY)                            │
│  ┌──────────────────────────────────────────────────┐          │
│  │ For each request:                                │          │
│  │                                                  │          │
│  │ 1. agent_system.track_io_request()              │          │
│  │    └─ Track which tier request went to          │          │
│  │                                                  │          │
│  │ 2. self.agent_check_counter += 1                │          │
│  │    └─ Increment request counter                 │          │
│  │                                                  │          │
│  │ 3. agent_system.periodic_update()               │          │
│  │    └─ NOT CALLED YET (counter < 50)             │          │
│  └──────────────────────────────────────────────────┘          │
│                                                                 │
│ REQUEST 50: (MIGRATION TRIGGERED!)                             │
│  ┌──────────────────────────────────────────────────┐          │
│  │ 1. agent_system.track_io_request()              │          │
│  │    └─ Track this request                        │          │
│  │                                                  │          │
│  │ 2. self.agent_check_counter = 50                │          │
│  │                                                  │          │
│  │ 3. if (50 % 50 == 0): ✓ YES!                    │          │
│  │    ↓                                             │          │
│  │    agent_system.periodic_update(                │          │
│  │        ssd_usage,                               │          │
│  │        ram_usage                                │          │
│  │    )                                             │          │
│  │                                                  │          │
│  │    ╔═══ MIGRATION PHASE STARTS ═══╗             │          │
│  │    ║ 1. Identify hot LBAs (>= 5 accesses) ║     │          │
│  │    ║ 2. Identify cold LBAs (<= 1 access)  ║     │          │
│  │    ║ 3. Enqueue migration candidates (max 10)║   │          │
│  │    ║ 4. Background executor processes queue ║    │          │
│  │    ║ 5. Calculate reward = migrations / latency ║│          │
│  │    ╚══════════════════════════════════════╝     │          │
│  └──────────────────────────────────────────────────┘          │
│                                                                 │
│ REQUEST 51-99: (Resume normal placement)                       │
│  └─ Same as requests 1-49                                      │
│                                                                 │
│ REQUEST 100: (MIGRATION TRIGGERED AGAIN!)                      │
│  └─ Same as request 50                                         │
│                                                                 │
│ REQUEST 150, 200, 250, ... (MIGRATION TRIGGERED)               │
│  └─ Every 50 requests, migration check happens                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: SHUTDOWN                                               │
├─────────────────────────────────────────────────────────────────┤
│ File: multi-tier-simulator.py                                  │
│                                                                 │
│ ✓ Stop migration executor (background thread)                  │
│ ✓ Collect final statistics                                     │
│ ✓ Write summary to summary_migration_info.txt                  │
│                                                                 │
│ Result: simulation_summary with both placement & migration stats│
└─────────────────────────────────────────────────────────────────┘
```

---

## Code Location: Where Migration Trigger Lives

### File: `Trace.py`

**Method: `transfer_with_rl_state()`** (Lines ~621-630)

```python
def transfer_with_rl_state(self, file_id, size_file, is_read, state_vec, service_time_s):
    
    # ... I/O execution code ...
    
    # Track placement decision
    self.agent_system.track_io_request(
        file_id=int(file_id),
        tier=locationSelected,
        latency_ns=served_time_ns,
        size_bytes=size_file,
        is_read=is_read
    )
    
    # MIGRATION TRIGGER POINT
    self.agent_check_counter += 1
    if self.agent_check_counter % 50 == 0:  # ← Every 50 requests
        self.agent_system.periodic_update(
            ssd_usage=self.ssd_used_bytes,
            ram_usage=self.ram_used_bytes
        )
```

### File: `migration_agent_system.py`

**Method: `periodic_update()`** (Lines ~405-425)

```python
def periodic_update(self, ssd_usage: int, ram_usage: int) -> None:
    """Called every 50 requests to trigger migration checks"""
    
    with self.lock:
        # Step 1: Identify migration candidates
        candidates = self._identify_migration_candidates(ssd_usage, ram_usage)
        
        # Step 2: Enqueue migrations
        if candidates:
            enqueued = self._enqueue_migrations(candidates)
            print(f"Enqueued {enqueued} migrations")
            
        # Step 3: Calculate delayed reward
        reward, stats = self._calculate_delayed_reward()
        print(f"Migration reward: {reward:.2f}")
```

---

## Migration Statistics Output

After simulation completes, check `summary_migration_info.txt`:

```
# Data Migration Statistics (LBA-based)
Total LBAs Tracked:                 117      ← Unique data blocks monitored
Hot LBAs (access >= 5):             7        ← Need faster tier
Cold LBAs (access <= 1):            108      ← Correctly in slow tier
Total LBA Operations:               680      ← Total I/O count
LBAs Migrated:                      0        ← LBAs that actually moved
Total Migrations Across LBAs:       0        ← Total migration events
Migrations Enqueued:                11       ← Candidates identified
Migrations Completed:               1        ← Actually executed
Total I/O Requests:                 680      ← Total requests
Avg Reward:                         18207682 ← migrations_completed / avg_latency
Migration Queue Size:               10       ← Pending migrations
Queue Full:                         True     ← Queue at capacity
```

---

## How to Verify Migration is Triggering

### 1. Console Output (During Simulation)

Look for migration-related messages:
```
[50.00s] Enqueued 5 migrations
[50.00s] Migration reward: 125000.0
[100.00s] Enqueued 3 migrations
[100.00s] Migration reward: 85000.0
```

### 2. Summary File After Simulation

Check `summary_migration_info.txt`:
- `Migrations Enqueued > 0` ✓
- `Migrations Completed > 0` ✓
- `Avg Reward > 0` ✓

### 3. Run a Longer Trace

Short traces may complete before many migrations execute. Run with a larger trace file to see:
- More migrations enqueued
- More migrations completed
- Higher rewards

---

## Key Parameters

| Parameter | Value | Location | Meaning |
|-----------|-------|----------|---------|
| Migration Check Interval | 50 | `migration_agent_system.py:316` | Trigger every 50 requests |
| Hot Threshold | 5 | `LBAHotnessTracker:THRESHOLD` | LBA with ≥5 accesses is hot |
| Cold Threshold | 1 | `LBAHotnessTracker:THRESHOLD` | LBA with ≤1 access is cold |
| Queue Capacity | 10 | `MigrationQueue:MAX_SIZE` | Max pending migrations |
| Reward Formula | `n/lat` | `_calculate_delayed_reward()` | migrations / avg_latency |

---

## Customizing Migration Trigger Frequency

To change migration check interval from **every 50 requests** to **every N requests**:

### Option 1: Edit Trace.py (Recommended)

Find lines ~624-625:
```python
if self.agent_check_counter % 50 == 0:  # ← Change 50 to your value
```

Change to:
```python
if self.agent_check_counter % 100 == 0:  # Every 100 requests
```

### Option 2: Edit migration_agent_system.py

Line ~316:
```python
MIGRATION_CHECK_INTERVAL = 50  # ← Change this constant
```

---

## Summary

| Phase | When | What | Result |
|-------|------|------|--------|
| **Placement** | Every request | RL agent decides tier | I/O at chosen tier |
| **Tracking** | Every request | Record placement decision | Hot/cold data identified |
| **Migration** | Every 50 requests | Identify & enqueue migrations | Up to 10 migrations queued |
| **Execution** | Background | Background thread executes | LBAs move between tiers |
| **Reward** | Every 50 requests | Calculate reward | System learns from migrations |

When you run `python multi-tier-simulator.py`, you get **both** placement and migration working together automatically!
