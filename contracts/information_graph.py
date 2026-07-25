"""Information Graph V2 — FROZEN. Cycle-safe root traversal, sorted evidence paths."""
import math
from enum import StrEnum
from pydantic import BaseModel, Field

class SourceType(StrEnum):
    RAW_PRICE = "raw_price"
    DERIVED_INDICATOR = "derived_indicator"
    NEWS_WIRE = "news_wire"
    SOCIAL_MEDIA = "social_media"
    ONCHAIN = "onchain"
    MACRO_DATA = "macro_data"
    SENTIMENT = "sentiment"
    EXPERT_OPINION = "expert_opinion"

class NodeType(StrEnum):
    SOURCE = "source"
    TRANSFORMATION = "transformation"
    AGENT = "agent"

class GraphNode(BaseModel):
    id: str
    source_type: SourceType
    node_type: NodeType = NodeType.TRANSFORMATION
    description: str = ""
    children: list[str] = Field(default_factory=list)
    parents: list[str] = Field(default_factory=list)

class InformationGraph:
    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self._init_default_graph()

    def _init_default_graph(self):
        self.add_node("raw_price", SourceType.RAW_PRICE, NodeType.SOURCE, "OHLCV data")
        self.add_node("news_wire", SourceType.NEWS_WIRE, NodeType.SOURCE, "News feeds")
        self.add_node("social_media", SourceType.SOCIAL_MEDIA, NodeType.SOURCE, "Social media")
        self.add_node("onchain_data", SourceType.ONCHAIN, NodeType.SOURCE, "Blockchain data")
        self.add_node("macro_data", SourceType.MACRO_DATA, NodeType.SOURCE, "Economic indicators")
        self.add_node("orderbook", SourceType.RAW_PRICE, NodeType.SOURCE, "Level2 order book")

        self.add_node("ema", SourceType.DERIVED_INDICATOR, NodeType.TRANSFORMATION, "EMA", parents=["raw_price"])
        self.add_node("rsi", SourceType.DERIVED_INDICATOR, NodeType.TRANSFORMATION, "RSI", parents=["raw_price"])
        self.add_node("vwap", SourceType.DERIVED_INDICATOR, NodeType.TRANSFORMATION, "VWAP", parents=["raw_price"])
        self.add_node("volume_delta", SourceType.DERIVED_INDICATOR, NodeType.TRANSFORMATION, "Bid-ask delta", parents=["orderbook"])
        self.add_node("footprint", SourceType.DERIVED_INDICATOR, NodeType.TRANSFORMATION, "Footprint", parents=["volume_delta"])

        self.add_node("technical_agent", SourceType.EXPERT_OPINION, NodeType.AGENT, "Technical", parents=["ema", "rsi"])
        self.add_node("quant_agent", SourceType.EXPERT_OPINION, NodeType.AGENT, "Quant", parents=["rsi", "vwap"])
        self.add_node("orderflow_agent", SourceType.EXPERT_OPINION, NodeType.AGENT, "Order Flow", parents=["footprint", "vwap"])
        self.add_node("news_agent", SourceType.EXPERT_OPINION, NodeType.AGENT, "News Intelligence", parents=["news_wire"])
        self.add_node("macro_agent", SourceType.EXPERT_OPINION, NodeType.AGENT, "Macro Economics", parents=["macro_data"])
        self.add_node("onchain_agent", SourceType.EXPERT_OPINION, NodeType.AGENT, "On-chain", parents=["onchain_data"])
        self.add_node("sentiment_agent", SourceType.EXPERT_OPINION, NodeType.AGENT, "Sentiment", parents=["social_media"])

    def add_node(self, id: str, source_type: SourceType, node_type: NodeType = NodeType.TRANSFORMATION, description: str = "", parents: list[str] = None):
        self.nodes[id] = GraphNode(
            id=id, source_type=source_type, node_type=node_type, description=description, parents=parents or [],
        )
        for parent in (parents or []):
            if parent in self.nodes:
                self.nodes[parent].children.append(id)

    def get_root_sources(self, node_id: str, visited: set[str] | None = None) -> set[str]:
        """Cycle-safe root traversal."""
        if visited is None:
            visited = set()
        if node_id in visited:
            return set()
        visited.add(node_id)
        if node_id not in self.nodes:
            return {node_id}
        node = self.nodes[node_id]
        if not node.parents:
            return {node_id}
        roots = set()
        for parent in node.parents:
            roots.update(self.get_root_sources(parent, visited.copy()))
        return roots

    def compute_source_diversity(self, agent_ids: list[str]) -> float:
        if not agent_ids:
            return 1.0
        clusters = [frozenset(self.get_root_sources(a)) for a in agent_ids]
        unique = set(clusters)
        return len(unique) / len(clusters)

    def compute_diversity(self, agent_ids: list[str]) -> float:
        return self.compute_source_diversity(agent_ids)

    def compute_cluster_balance(self, agent_ids: list[str]) -> float:
        """Shannon entropy tabanlı cluster dengesi."""
        if not agent_ids:
            return 1.0
        clusters = [frozenset(self.get_root_sources(a)) for a in agent_ids]
        counts: dict[frozenset, int] = {}
        for c in clusters:
            counts[c] = counts.get(c, 0) + 1
        total = len(agent_ids)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            entropy -= p * math.log2(p)
        max_entropy = math.log2(len(counts)) if counts else 1.0
        if max_entropy == 0:
            return 1.0
            return 0.0
        return round(entropy / max_entropy, 3)

    def compute_independence(self, agent_ids: list[str]) -> float:
        return self.compute_source_diversity(agent_ids)

    def get_paths_to_root(self, node_id: str, visited: set[str] | None = None) -> list[str]:
        """Cycle-safe rekürsif yol bulma."""
        if visited is None:
            visited = set()
        if node_id in visited:
            return []
        visited.add(node_id)
        if node_id not in self.nodes:
            return [node_id]
        node = self.nodes[node_id]
        if not node.parents:
            return [node_id]
        paths = []
        for parent in node.parents:
            for parent_path in self.get_paths_to_root(parent, visited.copy()):
                paths.append(f"{node_id} -> {parent_path}")
        return paths

    def get_common_ancestor_depth(self, agent_id1: str, agent_id2: str) -> int:
        roots1 = self.get_root_sources(agent_id1)
        roots2 = self.get_root_sources(agent_id2)
        if roots1 & roots2:
            return 1
        return 3
