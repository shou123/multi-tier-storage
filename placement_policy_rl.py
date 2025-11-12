# placement_policy_rl.py
# Thin wrapper that plugs the C51 agent into your SimPy Trace flow.


from rl_c51_agent import C51Agent, C51Config
from features import make_state, reward_from_latency, ACTION_TO_TIER, TIER_TO_ACTION
import numpy as np


class RLPlacement:
    def __init__(self, ssd_cap, ram_cap, device="cpu"):
        # Use state_dim=7: [is_read, lba_bin, block_bin, service_bin, last_tier_RAM/SSD/HDD]
        cfg = C51Config(state_dim=7, n_actions=3, device=device)
        self.agent = C51Agent(cfg)
        # simple per-file stats
        self.freq = {}
        self.last_tier = {}
        self.ssd_cap = ssd_cap
        self.ram_cap = ram_cap
        self.prev_state = None
        self.prev_action = None


    def _touch(self, fid):
        self.freq[fid] = self.freq.get(fid, 0) + 1


    def select_tier(self, *,
            is_read: bool,
            size_bytes: int,
            is_seq: bool,
            inter_arrival_s: float,
            ssd_used: int, ssd_cap: int,
            ram_used: int, ram_cap: int,
            file_id: str) -> str:
        self._touch(file_id)
        size_kb = size_bytes / 1024.0
        state = make_state(is_read, size_kb, is_seq, inter_arrival_s,
        self.freq[file_id], ssd_used, ssd_cap, ram_used, ram_cap,
        self.last_tier.get(file_id, "HDD"))
        action = self.agent.act(state)
        self.prev_state = state
        self.prev_action = action
        return ACTION_TO_TIER[action]

    def select_tier_from_state(self, *,
            state: np.ndarray,
            ssd_used: int, ssd_cap: int,
            ram_used: int, ram_cap: int,
            file_id: str) -> str:
        """Select tier using pre-computed state vector (7-dim from FeatureExtractor)."""
        self._touch(file_id)
        action = self.agent.act(state)
        self.prev_state = state
        self.prev_action = action
        return ACTION_TO_TIER[action]


    def observe(self, *, latency_s: float, next_is_read: bool,
            next_size_bytes: int, next_is_seq: bool, next_inter_arrival_s: float,
            ssd_used: int, ssd_cap: int, ram_used: int, ram_cap: int,
            file_id: str, done: bool=False):
        # Build next state using *next* request context
        size_kb = next_size_bytes / 1024.0
        next_state = make_state(next_is_read, size_kb, next_is_seq, next_inter_arrival_s,
        self.freq.get(file_id,1), ssd_used, ssd_cap, ram_used, ram_cap,
        self.last_tier.get(file_id, "HDD"))
        r = reward_from_latency(latency_s)
        if self.prev_state is not None:
            self.agent.push(self.prev_state, self.prev_action, r, next_state, done)
            self.agent.learn()


    def set_last_tier(self, file_id: str, tier: str):
        self.last_tier[file_id] = tier