"""
Migration Agent System - Optimizes tier placement over time

SCOPE: Migration Agent ONLY
Placement policy is handled by Trace.py (RL C51 agent)

This Migration Agent:
1. Tracks I/O requests and placement decisions from Trace.py
2. Identifies hot LBAs (access >= 5) and cold LBAs (access <= 1)
3. Enqueues migration candidates for tier optimization
4. Executes migrations in background thread
5. Calculates delayed rewards: migrations_completed / avg_latency

Integration with Trace.py:
    # At Trace.__init__()
    self.agent_system = MigrationAgentSystem(
        ssd_capacity_bytes=settings.SSD_CAPACITY_BYTES,
        ram_capacity_bytes=settings.RAM_CAPACITY_BYTES,
        env=self.env
    )
    
    # In transfer_with_rl_state() after I/O
    self.agent_system.track_io_request(
        file_id=file_id,
        tier=locationSelected,
        latency_ns=served_time_ns,
        size_bytes=size_file,
        is_read=is_read
    )
    
    # Every 50 requests in transfer_with_rl_state()
    if self.agent_check_counter % 50 == 0:
        self.agent_system.periodic_update(
            ssd_usage=self.ssd_used_bytes,
            ram_usage=self.ram_used_bytes
        )
    
    # At end of simulation in multi-tier-simulator.py
    trace.agent_system.shutdown()
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class MigrationCandidate:
    """Represents an LBA for potential migration"""
    file_id: int
    current_tier: str
    target_tier: str
    hotness_score: float
    identified_at: float


class LBAHotnessTracker:
    """
    Tracks hotness of LBAs (Logical Block Addresses) for migration decisions.
    LBA-level granularity instead of page-level.
    Hotness = access frequency
    """
    
    HOTNESS_THRESHOLD_HOT = 5      # Classify as hot (access >= 5)
    HOTNESS_THRESHOLD_COLD = 1     # Classify as cold (access <= 1)
    
    def __init__(self):
        self.lbas: Dict[int, Dict] = {}  # LBA -> access info
        self.lba_migrations: Dict[int, int] = {}  # LBA -> migration count
        self.lock = threading.Lock()
    
    def track_access(self, lba: int, current_time: float, 
                    tier: str, latency_ns: float, size_bytes: int) -> None:
        """Track LBA access for hotness calculation"""
        with self.lock:
            if lba not in self.lbas:
                self.lbas[lba] = {
                    'tier': tier,
                    'access_count': 0,
                    'total_latency': 0,
                    'first_access': current_time,
                    'last_access': current_time,
                    'size_bytes': size_bytes,
                    'access_times': deque(maxlen=100)
                }
                self.lba_migrations[lba] = 0
            
            lba_info = self.lbas[lba]
            lba_info['tier'] = tier
            lba_info['access_count'] += 1
            lba_info['total_latency'] += latency_ns
            lba_info['last_access'] = current_time
            lba_info['access_times'].append(current_time)
    
    def get_hotness_score(self, lba: int, current_time: float) -> float:
        """
        Calculate hotness score for an LBA based on access frequency.
        Score = access_count (simpler for LBA-level tracking)
        """
        with self.lock:
            if lba not in self.lbas:
                return 0.0
            
            lba_info = self.lbas[lba]
            # Simple hotness = access frequency
            recency_bonus = 1.0
            hotness = lba_info['access_count'] * recency_bonus
            
            return hotness
    
    def classify_lba(self, lba: int, current_time: float) -> str:
        """Classify LBA as hot, warm, or cold"""
        hotness = self.get_hotness_score(lba, current_time)
        
        if hotness >= self.HOTNESS_THRESHOLD_HOT:
            return 'hot'
        elif hotness >= self.HOTNESS_THRESHOLD_COLD:
            return 'warm'
        else:
            return 'cold'
    
    def get_lba_info(self, lba: int) -> Optional[Dict]:
        """Get detailed LBA information"""
        with self.lock:
            if lba in self.lbas:
                lba_info = self.lbas[lba].copy()
                # Convert deque to list for serialization
                lba_info['access_times'] = list(lba_info['access_times'])
                lba_info['migration_count'] = self.lba_migrations.get(lba, 0)
                return lba_info
        return None
    
    def get_all_lbas(self) -> Dict:
        """Get all tracked LBAs"""
        with self.lock:
            return {
                lba: {
                    **info, 
                    'access_times': list(info['access_times']),
                    'migration_count': self.lba_migrations.get(lba, 0)
                }
                for lba, info in self.lbas.items()
            }
    
    def record_migration(self, lba: int) -> None:
        """Record that an LBA was migrated"""
        with self.lock:
            if lba not in self.lba_migrations:
                self.lba_migrations[lba] = 0
            self.lba_migrations[lba] += 1



class MigrationQueue:
    """Thread-safe migration queue (max 10 candidates)"""
    MAX_SIZE = 10
    
    def __init__(self):
        self.queue = deque(maxlen=self.MAX_SIZE)
        self.lock = threading.Lock()
    
    def enqueue(self, candidate: MigrationCandidate) -> bool:
        with self.lock:
            if len(self.queue) < self.MAX_SIZE:
                self.queue.append(candidate)
                return True
            return False
    
    def dequeue(self) -> Optional[MigrationCandidate]:
        with self.lock:
            if self.queue:
                return self.queue.popleft()
            return None
    
    def get_all(self) -> List[MigrationCandidate]:
        with self.lock:
            return list(self.queue)
    
    def size(self) -> int:
        with self.lock:
            return len(self.queue)
    
    def is_full(self) -> bool:
        with self.lock:
            return len(self.queue) >= self.MAX_SIZE


class MigrationExecutor:
    """Background thread that executes migrations"""
    
    def __init__(self, migration_queue: MigrationQueue, hotness_tracker):
        self.queue = migration_queue
        self.tracker = hotness_tracker  # Now LBAHotnessTracker instead of PageHotnessTracker
        self.is_running = False
        self.thread = None
        self.migrations_completed = 0
        self.lock = threading.Lock()
    
    def start(self) -> None:
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._migration_loop, daemon=True)
            self.thread.start()
    
    def stop(self) -> None:
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def _migration_loop(self) -> None:
        """Continuously execute migrations from queue"""
        while self.is_running:
            candidate = self.queue.dequeue()
            
            if candidate:
                # Execute migration (simulated)
                with self.lock:
                    self.migrations_completed += 1
                
                # Update LBA tier in tracker
                lba_info = self.tracker.get_lba_info(candidate.file_id)
                if lba_info:
                    self.tracker.track_access(
                        candidate.file_id,
                        time.time(),
                        candidate.target_tier,
                        0,
                        lba_info['size_bytes']
                    )
                    # Record the migration
                    self.tracker.record_migration(candidate.file_id)
            
            time.sleep(0.01)  # Small sleep to avoid busy waiting
    
    def get_completed_count(self) -> int:
        with self.lock:
            return self.migrations_completed


class MigrationAgentSystem:
    """
    Migration Agent System - optimizes tier placement over time.
    
    Works automatically:
    1. Placement agent decides tier for each I/O
    2. System tracks all accesses for hotness analysis
    3. Migration agent identifies optimization opportunities
    4. Background executor performs migrations
    5. System learns and adapts over time
    """
    
    # Configuration parameters
    MIGRATION_CHECK_INTERVAL = 50      # Check every N I/O requests
    REWARD_WINDOW_SIZE = 50            # Use N requests for reward calculation
    
    def __init__(self, ssd_capacity_bytes: int, ram_capacity_bytes: int,
                 env=None, placement_agent=None):
        """
        Initialize the unified agent system.
        
        Args:
            ssd_capacity_bytes: SSD capacity
            ram_capacity_bytes: RAM capacity
            env: SimPy environment (for timing)
            placement_agent: Existing RL placement agent (optional)
        """
        self.ssd_capacity = ssd_capacity_bytes
        self.ram_capacity = ram_capacity_bytes
        self.env = env
        
        # Initialize components (placement_agent not used - Trace.py handles placement)
        self.hotness_tracker = LBAHotnessTracker()  # Tracks individual LBA access patterns
        self.migration_queue = MigrationQueue()
        self.migration_executor = MigrationExecutor(self.migration_queue, self.hotness_tracker)
        
        # Statistics tracking
        self.placement_decisions = deque(maxlen=1000)
        self.latency_window = deque(maxlen=self.REWARD_WINDOW_SIZE)
        self.request_count = 0
        self.migrations_enqueued = 0
        self.total_rewards = []
        self.lba_migration_map = {}  # Track LBA -> tier transitions
        
        # Threading
        self.lock = threading.Lock()
        
        # Start migration executor
        self.migration_executor.start()
    
    def track_io_request(self, file_id: int, tier: str, latency_ns: float, 
                        size_bytes: int, is_read: bool) -> None:
        """
        Track an I/O request for analysis by both agents.
        
        Args:
            file_id: File/page identifier
            tier: Target tier ('RAM', 'SSD', 'HDD')
            latency_ns: Request latency in nanoseconds
            size_bytes: Data size in bytes
            is_read: Whether this is a read operation
        """
        current_time = time.time()
        
        with self.lock:
            # Track for hotness analysis
            self.hotness_tracker.track_access(file_id, current_time, tier, latency_ns, size_bytes)
            
            # Record placement decision
            decision = {
                'file_id': file_id,
                'tier': tier,
                'latency_ns': latency_ns,
                'size_bytes': size_bytes,
                'is_read': is_read,
                'time': current_time
            }
            self.placement_decisions.append(decision)
            
            # Track latency for reward calculation
            self.latency_window.append(latency_ns)
            self.request_count += 1
    
    def periodic_update(self, ssd_usage: int, ram_usage: int) -> None:
        """
        Call periodically (every ~50 requests) to trigger migration decisions.
        
        Args:
            ssd_usage: Current SSD usage in bytes
            ram_usage: Current RAM usage in bytes
        """
        with self.lock:
            # Step 1: Identify migration candidates
            candidates = self._identify_migration_candidates(ssd_usage, ram_usage)
            
            # Step 2: Enqueue migrations
            if candidates:
                enqueued = self._enqueue_migrations(candidates)
                if enqueued > 0:
                    print(f"[{self.env.now if self.env else time.time():.2f}s] "
                          f"Enqueued {enqueued} migrations")
                    for c in candidates[:3]:
                        print(f"  Page {c.file_id}: {c.current_tier} → "
                              f"{c.target_tier} (score: {c.hotness_score:.2f})")
            
            # Step 3: Calculate delayed reward
            reward, stats = self._calculate_delayed_reward()
            if stats and 'avg_latency' in stats:
                print(f"[{self.env.now if self.env else time.time():.2f}s] "
                      f"Migration reward: {reward:.2f}, "
                      f"Avg latency: {stats['avg_latency']:.0f}ns")
    
    def _identify_migration_candidates(self, ssd_usage: int, ram_usage: int) -> List[MigrationCandidate]:
        """Identify LBAs that should be migrated based on access frequency"""
        candidates = []
        current_time = time.time()
        all_lbas = self.hotness_tracker.get_all_lbas()
        
        for lba, lba_info in all_lbas.items():
            current_tier = lba_info['tier']
            hotness = self.hotness_tracker.get_hotness_score(lba, current_time)
            classification = self.hotness_tracker.classify_lba(lba, current_time)
            access_count = lba_info['access_count']
            
            target_tier = self._select_target_tier(
                current_tier, classification, hotness, ssd_usage, ram_usage
            )
            
            # Only suggest migration if target differs from current and LBA is hot
            if target_tier != current_tier and access_count >= 5:
                candidate = MigrationCandidate(
                    file_id=lba,  # Use LBA as file_id
                    current_tier=current_tier,
                    target_tier=target_tier,
                    hotness_score=hotness,
                    identified_at=current_time
                )
                candidates.append(candidate)
        
        # Sort by hotness score (access frequency) and return top candidates
        candidates.sort(key=lambda c: c.hotness_score, reverse=True)
        return candidates[:10]  # Max 10 candidates
    
    def _select_target_tier(self, current_tier: str, classification: str, 
                           hotness: float, ssd_usage: int, ram_usage: int) -> str:
        """Select target tier for an LBA based on hotness and capacity"""
        device_hierarchy = ['RAM', 'SSD', 'HDD']
        current_idx = device_hierarchy.index(current_tier) if current_tier in device_hierarchy else 1
        
        if classification == 'hot':
            # Move hot data to faster tier
            for i in range(current_idx - 1, -1, -1):
                tier = device_hierarchy[i]
                if tier == 'RAM' and ram_usage < self.ram_capacity * 0.9:
                    return 'RAM'
                elif tier == 'SSD' and ssd_usage < self.ssd_capacity * 0.9:
                    return 'SSD'
        
        elif classification == 'cold':
            # Move cold data to slower tier
            for i in range(current_idx + 1, len(device_hierarchy)):
                return device_hierarchy[i]
        
        return current_tier
    
    def _enqueue_migrations(self, candidates: List[MigrationCandidate]) -> int:
        """Enqueue migration candidates"""
        enqueued = 0
        for candidate in candidates:
            if self.migration_queue.enqueue(candidate):
                self.migrations_enqueued += 1
                enqueued += 1
            else:
                break  # Queue full
        
        return enqueued
    
    def _calculate_delayed_reward(self) -> Tuple[float, Optional[Dict]]:
        """Calculate delayed reward based on migrations completed and latency.
        
        Reward = migrations_completed / avg_latency
        Higher reward when more migrations are completed with lower latency.
        """
        if len(self.latency_window) < self.REWARD_WINDOW_SIZE:
            return 0.0, None
        
        migrations_completed = self.migration_executor.get_completed_count()
        if migrations_completed == 0:
            return 0.0, None
        
        # Calculate average latency
        avg_latency = np.mean(list(self.latency_window))
        total_latency = np.sum(list(self.latency_window))
        
        # Reward: migrations_completed / avg_latency
        # Avoid division by zero - if latency is very small, cap it at 1e-9
        if avg_latency < 1e-9:
            avg_latency = 1e-9
        
        reward = migrations_completed / (avg_latency / 1e9)  # avg_latency in seconds
        
        stats = {
            'avg_latency': avg_latency,
            'total_latency': total_latency,
            'num_requests': len(self.latency_window),
            'migrations_completed': migrations_completed,
            'reward_calculation': f"{migrations_completed} / {avg_latency / 1e9:.6f}s"
        }
        
        self.total_rewards.append(reward)
        return reward, stats
    
    def get_statistics(self) -> Dict:
        """Get system statistics based on LBA-level tracking"""
        with self.lock:
            all_lbas = self.hotness_tracker.get_all_lbas()
            hot_lbas = sum(1 for lba in all_lbas.values() if lba['access_count'] >= 5)
            cold_lbas = sum(1 for lba in all_lbas.values() if lba['access_count'] <= 1)
            
            # Calculate total LBA operations (sum of all accesses)
            total_lba_operations = sum(lba['access_count'] for lba in all_lbas.values())
            
            # Count LBAs that have been migrated
            migrated_lbas = sum(1 for lba in all_lbas.values() if lba.get('migration_count', 0) > 0)
            
            # Calculate total migrations across all LBAs
            total_migrations_across_lbas = sum(lba.get('migration_count', 0) for lba in all_lbas.values())
            
            return {
                'total_lbas_tracked': len(all_lbas),
                'hot_lbas': hot_lbas,
                'cold_lbas': cold_lbas,
                'total_lba_operations': total_lba_operations,
                'total_requests': self.request_count,
                'migrations_enqueued': self.migrations_enqueued,
                'migrations_completed': self.migration_executor.get_completed_count(),
                'lbas_migrated': migrated_lbas,
                'total_migrations_across_lbas': total_migrations_across_lbas,
                'queue_size': self.migration_queue.size(),
                'queue_full': self.migration_queue.is_full(),
                'avg_reward': np.mean(self.total_rewards) if self.total_rewards else 0.0
            }
    
    def shutdown(self) -> None:
        """Gracefully shutdown the agent system"""
        print("\n[SHUTDOWN] Unified Agent System stopping...")
        self.migration_executor.stop()
        
        stats = self.get_statistics()
        print("Final Statistics (LBA-level):")
        print(f"  Total LBAs tracked: {stats['total_lbas_tracked']}")
        print(f"  Hot LBAs (access >= 5): {stats['hot_lbas']}")
        print(f"  Cold LBAs (access <= 1): {stats['cold_lbas']}")
        print(f"  Total LBA operations: {stats['total_lba_operations']}")
        print(f"  Total I/O requests: {stats['total_requests']}")
        print(f"  LBAs migrated: {stats['lbas_migrated']}")
        print(f"  Total migrations across LBAs: {stats['total_migrations_across_lbas']}")
        print(f"  Migrations enqueued: {stats['migrations_enqueued']}")
        print(f"  Migrations completed: {stats['migrations_completed']}")
        print(f"  Avg reward: {stats['avg_reward']:.2f}")


# ==============================================================================
# INTEGRATION WITH EXISTING TRACE.PY
# ==============================================================================

def integrate_migration_agent_system(trace_instance):
    """
    Integrate the migration agent system into an existing Trace instance.
    
    Call this immediately after Trace.__init__():
        from migration_agent_system import integrate_migration_agent_system
        trace = Trace(env, resource_hdd, resource_ssd)
        integrate_migration_agent_system(trace)
    """
    import settings
    
    # Create migration agent system
    placement_agent = getattr(trace_instance, 'rl', None)
    
    trace_instance.agent_system = MigrationAgentSystem(
        ssd_capacity_bytes=settings.SSD_CAPACITY_BYTES,
        ram_capacity_bytes=settings.RAM_CAPACITY_BYTES,
        env=trace_instance.env,
        placement_agent=placement_agent
    )
    
    trace_instance.agent_check_counter = 0
    
    print("[INIT] Migration Agent System initialized")
    print(f"  SSD capacity: {settings.SSD_CAPACITY_BYTES / 1e9:.1f}GB")
    print(f"  RAM capacity: {settings.RAM_CAPACITY_BYTES / 1e9:.1f}GB")
    print(f"  Migration check interval: {MigrationAgentSystem.MIGRATION_CHECK_INTERVAL} requests")
    print(f"  Reward window: {MigrationAgentSystem.REWARD_WINDOW_SIZE} requests")

