"""RL ajan modelleri stub."""
import torch
import torch.nn as nn


class PolicyNetwork(nn.Module):
    def __init__(self, state_dim: int, action_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 128), nn.ReLU(),
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, action_dim),
        )

    def forward(self, x):
        return self.net(x)

class QNetwork(nn.Module):
    def __init__(self, state_dim: int, action_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 128), nn.ReLU(),
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, action_dim),
        )

    def forward(self, x):
        return self.net(x)

class PPOAgent:
    def __init__(self, state_dim, action_dim):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.policy = PolicyNetwork(state_dim, action_dim)

    def select_action(self, state):
        with torch.no_grad():
            logits = self.policy(torch.tensor(state, dtype=torch.float32))
            return torch.argmax(logits).item()

class A2CAgent:
    def __init__(self, state_dim, action_dim):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.policy = PolicyNetwork(state_dim, action_dim)

    def select_action(self, state):
        with torch.no_grad():
            logits = self.policy(torch.tensor(state, dtype=torch.float32))
            return torch.argmax(logits).item()

class DQNAgent:
    def __init__(self, state_dim, action_dim):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.q_net = QNetwork(state_dim, action_dim)

    def select_action(self, state, epsilon=0.1):
        if torch.rand(1).item() < epsilon:
            return torch.randint(0, 3, (1,)).item()
        with torch.no_grad():
            q = self.q_net(torch.tensor(state, dtype=torch.float32))
            return torch.argmax(q).item()

class SACAgent:
    def __init__(self, state_dim, action_dim):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.policy = PolicyNetwork(state_dim, action_dim)

    def select_action(self, state):
        with torch.no_grad():
            logits = self.policy(torch.tensor(state, dtype=torch.float32))
            return torch.argmax(logits).item()

class TD3Agent:
    def __init__(self, state_dim, action_dim):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.policy = PolicyNetwork(state_dim, action_dim)

    def select_action(self, state):
        with torch.no_grad():
            logits = self.policy(torch.tensor(state, dtype=torch.float32))
            return torch.argmax(logits).item()
