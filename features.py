"""features.py

RL state vector extraction for multi-tier storage placement decisions.

State Vector (7 dimensions):
  0  is_read           1 if read, 0 if write
  1  lba_bin           Normalized LBA (captures locality)
  2  block_bin         Normalized block size
  3  service_bin       Log-scaled + normalized service time (only time feature)
  4  last_tier_RAM     1 if last access was served from RAM
  5  last_tier_SSD     1 if last access was served from SSD
  6  last_tier_HDD     1 if last access was served from HDD

Trace format (from FILE_PATH):
  Space-separated: timestamp, operation(WS/RS), LBA, block_size, seq/rand, inter_arrival, service_time, idle_time
  Only used: operation, LBA, block_size, service_time
  
  Latency (RL reward) = service_time only (not inter_arrival or idle_time)

Example:
  0.000003537 WS 1540175 8 seq 1.2074e-05 0.000048534 0
  0.000064145 WS 1540167 8 rand 5.002759086 0.000071110 5.0025943
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

try:
    from settings import FILE_PATH
except ImportError:
    FILE_PATH = 'converted_trace.txt'


@dataclass
class FeatureStats:
    """Statistics for normalization of features."""
    max_lba: float = 0.0
    max_block: float = 0.0
    max_service: float = 0.0

    def update(self, lba: float, block: float, service: float) -> None:
        if lba > self.max_lba:
            self.max_lba = lba
        if block > self.max_block:
            self.max_block = block
        if service > self.max_service:
            self.max_service = service


class FeatureExtractor:
    """Extracts 7-dim RL state vectors from trace file.
    
    Usage:
        fe = FeatureExtractor(FILE_PATH)
        for state, raw in fe.iter_states():
            # state: np.ndarray shape (7,) dtype float32
            # raw: dict with original trace values
            action = agent.act(state)
            fe.set_last_tier(raw['file_id'], tier_name)
    """

    def __init__(self, file_path: str, pre_scan: bool = True) -> None:
        self.file_path = file_path
        self.stats = FeatureStats()
        self.last_tier: Dict[int, str] = {}
        if pre_scan:
            self._scan_file()

    def iter_states(self) -> Iterator[Tuple[np.ndarray, Dict]]:
        """Stream (state_vector, raw_dict) pairs from trace file.
        
        Reads space-separated raw trace format:
        timestamp, operation(WS/RS), LBA, block_size, seq/rand, inter_arrival, service_time, idle_time
        """
        with open(self.file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Parse space-separated format (raw trace data)
                parts = line.split()
                if len(parts) < 8:
                    continue
                
                try:
                    timestamp = float(parts[0])
                    op_raw = parts[1].lower()      # WS or RS
                    lba = float(parts[2])
                    block_size = float(parts[3])
                    seq_rand = parts[4].lower()    # 'seq' or 'rand', not used
                    inter = float(parts[5])         # inter_arrival not used for reward
                    service = float(parts[6])       # service_time only used for reward
                    idle = float(parts[7])          # idle_time not used
                except (ValueError, IndexError):
                    continue
                
                # Map operation codes: WS/write=write, RS/read=read
                is_read = 1.0 if op_raw in ('read', 'r', 'rs', 'rr') else 0.0
                file_id = int(lba)
                
                state_vec = self._build_state(is_read, lba, block_size, service, file_id)
                raw = {
                    'is_read': is_read,
                    'lba': lba,
                    'block_size': block_size,
                    'inter': inter,
                    'service': service,
                    'idle': idle,
                    'file_id': file_id,
                }
                yield state_vec, raw

    def build_state_matrix(self) -> np.ndarray:
        """Materialize all states into (N, 7) array."""
        states = []
        for s, _ in self.iter_states():
            states.append(s)
        if states:
            return np.vstack(states)
        return np.empty((0, 7), dtype=np.float32)

    def set_last_tier(self, file_id: int, tier: str) -> None:
        """Update last tier for a file (call after placement decision)."""
        if tier in {'RAM', 'SSD', 'HDD'}:
            self.last_tier[file_id] = tier

    def _scan_file(self) -> None:
        """Two-pass: collect max values for normalization from space-separated trace format."""
        if not os.path.exists(self.file_path):
            return
        
        with open(self.file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split()
                if len(parts) < 8:
                    continue
                
                try:
                    # Space-separated format:
                    # timestamp(0), op(1), lba(2), block_size(3), seq/rand(4), inter(5), service(6), idle(7)
                    lba = float(parts[2])
                    block_size = float(parts[3])
                    service = float(parts[6])
                except (ValueError, IndexError):
                    continue
                
                self.stats.update(lba, block_size, service)
        
        # Ensure no division by zero
        if self.stats.max_lba <= 0:
            self.stats.max_lba = 1.0
        if self.stats.max_block <= 0:
            self.stats.max_block = 1.0
        if self.stats.max_service <= 0:
            self.stats.max_service = 1.0

    def _norm_linear(self, value: float, max_v: float) -> float:
        """Linear normalization to [0, 1]."""
        return min(max(value / max_v, 0.0), 1.0)

    def _norm_log(self, value: float, max_v: float) -> float:
        """Log normalization for time values."""
        if value <= 0:
            return 0.0
        return math.log1p(value) / math.log1p(max_v)

    def _build_state(self, is_read: float, lba: float, block_size: float,
                     service: float, file_id: int) -> np.ndarray:
        """Build 7-dim state vector."""
        lba_bin = self._norm_linear(lba, self.stats.max_lba)
        block_bin = self._norm_linear(block_size, self.stats.max_block)
        service_bin = self._norm_log(service, self.stats.max_service)
        
        last = self.last_tier.get(file_id)
        last_ram = 1.0 if last == 'RAM' else 0.0
        last_ssd = 1.0 if last == 'SSD' else 0.0
        last_hdd = 1.0 if last == 'HDD' else 0.0
        
        state = np.array([
            is_read,
            lba_bin,
            block_bin,
            service_bin,
            last_ram,
            last_ssd,
            last_hdd
        ], dtype=np.float32)
        return state


def reward_from_latency(latency_s: float) -> float:
    """Inverse-latency reward, clamped into [0, 10]."""
    r = 1.0 / max(latency_s, 1e-9)
    return min(max(r, 0.0), 10.0)


def create_feature_extractor() -> FeatureExtractor:
    """Factory to create extractor from settings.FILE_PATH."""
    return FeatureExtractor(FILE_PATH)


# ============================================================================
# Backward Compatibility Exports
# ============================================================================

ACTION_TO_TIER = {0: "RAM", 1: "SSD", 2: "HDD"}
TIER_TO_ACTION = {v: k for k, v in ACTION_TO_TIER.items()}

_global_extractor: Optional[FeatureExtractor] = None

def _get_global_extractor() -> FeatureExtractor:
    """Lazy-load global extractor."""
    global _global_extractor
    if _global_extractor is None:
        _global_extractor = create_feature_extractor()
    return _global_extractor


def make_state(is_read: bool, size_kb: float, is_seq: bool, inter_arrival_s: float,
               access_freq: int, ssd_used: int, ssd_cap: int, ram_used: int,
               ram_cap: int, last_tier: str) -> np.ndarray:
    """Backward-compat wrapper: old signature -> new 7-dim state.
    
    Returns state with indices:
      [is_read, lba_bin, block_bin, service_bin, last_tier_RAM, last_tier_SSD, last_tier_HDD]
    """
    fe = _get_global_extractor()
    
    last_ram = 1.0 if last_tier == 'RAM' else 0.0
    last_ssd = 1.0 if last_tier == 'SSD' else 0.0
    last_hdd = 1.0 if last_tier == 'HDD' else 0.0
    
    size_bin = fe._norm_linear(size_kb, fe.stats.max_block) if fe.stats.max_block > 0 else 0.0
    lba_bin = fe._norm_linear(float(ssd_used), fe.stats.max_lba) if fe.stats.max_lba > 0 else 0.0
    service_bin = 0.0  # not available in old signature
    
    state = np.array([
        1.0 if is_read else 0.0,
        lba_bin,
        size_bin,
        service_bin,
        last_ram,
        last_ssd,
        last_hdd
    ], dtype=np.float32)
    return state


if __name__ == "__main__":
    # Quick test
    fe = create_feature_extractor()
    for i, (s, raw) in enumerate(fe.iter_states()):
        print(f"Row {i} state={s}")
        if i >= 4:
            break