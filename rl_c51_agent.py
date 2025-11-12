# rl_c51_agent.py
# Minimal C51 agent (PyTorch) for 3 actions: RAM / SSD / HDD
# Works online inside SimPy. No external deps beyond torch & numpy.


from dataclasses import dataclass
import random
import math
from typing import Tuple, List
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


# ---------- Hyperparams (tunable) ----------
@dataclass
class C51Config:
    state_dim: int = 7  # 7 features: is_read, lba_bin, block_bin, service_bin, last_tier_RAM/SSD/HDD
    n_actions: int = 3  # RAM, SSD, HDD
    Vmin: float = 0.0  # min return
    Vmax: float = 10.0  # max return
    n_atoms: int = 51
    gamma: float = 0.95
    lr: float = 1e-3
    batch_size: int = 128
    buffer_size: int = 20000
    start_learn_after: int = 1000
    train_freq: int = 1
    target_update_interval: int = 1000
    eps_start: float = 0.10
    eps_end: float = 0.01
    eps_decay_steps: int = 20000
    device: str = "cpu"


class ReplayBuffer:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.data = []
        self.pos = 0

    def push(self, s, a, r, ns, done):
        item = (s.astype(np.float32), a, float(r), ns.astype(np.float32), bool(done))
        if len(self.data) < self.capacity:
            self.data.append(item)
        else:
           self.data[self.pos] = item
        self.pos = (self.pos + 1) % self.capacity

    def sample(self, batch_size: int):
        batch = random.sample(self.data, batch_size)
        s, a, r, ns, d = map(np.array, zip(*batch))
        return s, a, r, ns, d

    def __len__(self):
        return len(self.data)


class Net(nn.Module):
    def __init__(self, state_dim: int, n_actions: int, n_atoms: int):
        super().__init__()
        hidden = 64
        self.net = nn.Sequential(
        nn.Linear(state_dim, hidden),
        nn.SiLU(),
        nn.Linear(hidden, hidden),
        nn.SiLU(),
        nn.Linear(hidden, n_actions * n_atoms),
        )
        self.n_actions = n_actions
        self.n_atoms = n_atoms

    def forward(self, x):
        logits = self.net(x) # [B, n_actions*n_atoms]
        logits = logits.view(-1, self.n_actions, self.n_atoms)
        probs = torch.softmax(logits, dim=-1)
        return probs # categorical distribution per action


class C51Agent:
    def __init__(self, cfg: C51Config):
        self.cfg = cfg
        self.device = torch.device(cfg.device)
        self.support = torch.linspace(cfg.Vmin, cfg.Vmax, cfg.n_atoms, device=self.device)
        self.delta_z = (cfg.Vmax - cfg.Vmin) / (cfg.n_atoms - 1)
        self.online = Net(cfg.state_dim, cfg.n_actions, cfg.n_atoms).to(self.device)
        self.target = Net(cfg.state_dim, cfg.n_actions, cfg.n_atoms).to(self.device)
        self.target.load_state_dict(self.online.state_dict())
        self.optim = optim.Adam(self.online.parameters(), lr=cfg.lr)
        self.buffer = ReplayBuffer(cfg.buffer_size)
        self.steps = 0
        self.eps = cfg.eps_start


    # Epsilon decays linearly
    def _update_eps(self):
        t = min(self.steps, self.cfg.eps_decay_steps)
        self.eps = self.cfg.eps_end + (self.cfg.eps_start - self.cfg.eps_end) * (1 - t / self.cfg.eps_decay_steps)


    @torch.no_grad()
    def act(self, state: np.ndarray) -> int:
        self.steps += 1
        self._update_eps()
        if random.random() < self.eps:
            return random.randrange(self.cfg.n_actions)
        s = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
        probs = self.online(s) # [1, A, Z]
        q = torch.sum(probs * self.support, dim=-1) # [1, A]
        return int(torch.argmax(q, dim=1).item())


    def push(self, s, a, r, ns, done):
        self.buffer.push(s, a, r, ns, done)


    def project(self, next_dist, rewards, dones):
        # Categorical projection (Bellemare et al. 2017)
        cfg = self.cfg
        Tz = rewards.unsqueeze(1) + (1 - dones.unsqueeze(1)) * cfg.gamma * self.support.unsqueeze(0)
        Tz = Tz.clamp(cfg.Vmin, cfg.Vmax)
        b = (Tz - cfg.Vmin) / self.delta_z
        l = b.floor().long()
        u = b.ceil().long()
        B, Z = next_dist.shape
        m = torch.zeros(B, Z, device=self.device)
        for i in range(B):
            m[i].index_add_(0, l[i], next_dist[i] * (u[i].float() - b[i]))
            m[i].index_add_(0, u[i], next_dist[i] * (b[i] - l[i].float()))
        return m


    def learn(self):
        cfg = self.cfg
        if len(self.buffer) < cfg.start_learn_after or len(self.buffer) < cfg.batch_size:
            return 0.0
        if self.steps % cfg.train_freq != 0:
            return 0.0
        s, a, r, ns, d = self.buffer.sample(cfg.batch_size)
        s = torch.tensor(s, device=self.device)
        a = torch.tensor(a, device=self.device, dtype=torch.int64)
        r = torch.tensor(r, device=self.device)
        ns = torch.tensor(ns, device=self.device)
        d = torch.tensor(d, device=self.device, dtype=torch.float32)


        # Next distribution via double-DQN trick: action from online, dist from target
        with torch.no_grad():
            next_probs = self.online(ns) # [B, A, Z]
            next_q = torch.sum(next_probs * self.support, dim=-1) # [B, A]
            next_a = torch.argmax(next_q, dim=1) # [B]
            target_probs = self.target(ns) # [B, A, Z]
            next_dist = target_probs[range(cfg.batch_size), next_a, :] # [B, Z]
            m = self.project(next_dist, r, d) # [B, Z]


        probs = self.online(s)[range(cfg.batch_size), a, :] # [B, Z]
        loss = -torch.sum(m * torch.log(probs + 1e-8), dim=-1).mean()
        self.optim.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.online.parameters(), 5.0)
        self.optim.step()


        if self.steps % cfg.target_update_interval == 0:
            self.target.load_state_dict(self.online.state_dict())
        return float(loss.item())