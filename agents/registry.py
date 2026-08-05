"""Agent Registry — tüm uzman ajanları merkezi olarak yönetir."""
from agents.epistemology_agent import EpistemologyAgent
from agents.macro_agent import MacroAgent
from agents.onchain_agent import OnChainAgent
from agents.order_flow_agent import OrderFlowAgent
from agents.pattern_agent import PatternAgent
from agents.quant_agent import QuantAgent
from agents.sentiment_agent import SentimentAgent
from agents.technical_agent import TechnicalAgent
from agents.time_agent import TimeAgent
from contracts.agent import AgentDomain


class AgentRegistry:
    def __init__(self):
        self._agents: dict[AgentDomain, object] = {}

    def register(self, domain: AgentDomain, agent):
        self._agents[domain] = agent

    def get(self, domain: AgentDomain):
        return self._agents.get(domain)

    def all_agents(self):
        return self._agents.items()

    def list_domains(self) -> list[AgentDomain]:
        return list(self._agents.keys())

    @classmethod
    def create_default(cls) -> "AgentRegistry":
        """Dokuz uzman ajanla (4 orijinal + 5 bu turda eklenen: Pattern,
        Quant, Order Flow, Time, Epistemology) hazır bir registry oluşturur,
        sonra agents/plugins/'daki güvenilir (hash'i TRUSTED_PLUGIN_HASHES'te
        olan) eklentileri keşfeder. TRUSTED_PLUGIN_HASHES varsayılan olarak
        boş — hiçbir plugin, bir insan onun hash'ini gözden geçirip
        eklemeden otomatik yüklenmez (Sprint 17-18)."""
        registry = cls()
        registry.register(AgentDomain.MACRO, MacroAgent())
        registry.register(AgentDomain.SENTIMENT, SentimentAgent())
        registry.register(AgentDomain.ONCHAIN, OnChainAgent())
        registry.register(AgentDomain.TECHNICAL, TechnicalAgent())
        registry.register(AgentDomain.PATTERN, PatternAgent())
        registry.register(AgentDomain.QUANT, QuantAgent())
        registry.register(AgentDomain.ORDER_FLOW, OrderFlowAgent())
        registry.register(AgentDomain.TIME, TimeAgent())
        registry.register(AgentDomain.EPISTEMOLOGY, EpistemologyAgent())

        from agents.plugin_loader import discover_plugins
        discover_plugins(registry)

        return registry
