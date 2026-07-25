"""Autonomous Experiment Runner — düzeltilmiş."""
from contracts.curiosity import ExperimentProposal, ExperimentStatus, ExperimentResult
from contracts.memory import EpisodicMemory, SemanticMemory, Episode
from contracts.context import CognitiveCycleContext
from contracts.execution_mode import ExecutionMode
from engines.sandbox_executor import SandboxExecutor

class ExperimentRunner:
    def __init__(self, episodic: EpisodicMemory, semantic: SemanticMemory):
        self.episodic = episodic
        self.semantic = semantic
        self.sandbox = SandboxExecutor()
        self.queue: list[ExperimentProposal] = []
        self.results: list[ExperimentResult] = []

    def enqueue(self, proposal: ExperimentProposal):
        proposal.status = ExperimentStatus.APPROVED
        self.queue.append(proposal)

    def run_all(self) -> list[Episode]:
        results: list[Episode] = []
        for proposal in self.queue:
            episode = self._run_experiment(proposal)
            if episode:
                results.append(episode)
        self.queue.clear()
        return results

    def _run_experiment(self, proposal: ExperimentProposal) -> Episode | None:
        proposal.status = ExperimentStatus.RUNNING

        # Market data fallback — gerçek sistemde MarketDataProvider'dan gelir
        ctx = CognitiveCycleContext(
            mode=ExecutionMode.EXPERIMENT,
            market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"price": 50000, "RSI": 25}},
            decision={"proposed_direction": "LONG", "proposed_size": 0.5},
        )
        ctx.cognition.relevant_knowledge.append({
            "type": "cognitive_binding",
            "data": {"expression": {"description": proposal.test_expression}}
        })

        ctx = self.sandbox.execute(ctx)

        episode = Episode(
            symbol=ctx.market.symbol,
            binding_expression=proposal.test_expression,
            decision=ctx.decision.final_direction,
            outcome=ctx.outcome,
            lesson=f"Experiment: {proposal.hypothesis}",
        )
        self.episodic.add_episode(episode)

        # ExperimentResult oluştur — SemanticMemory'ye dokunma!
        result = ExperimentResult(
            proposal_id=proposal.id,
            samples=1,
            pnl=ctx.outcome.get("pnl", 0) if ctx.outcome else 0,
            conclusion=f"Experiment completed: {proposal.hypothesis}",
        )
        self.results.append(result)

        proposal.status = ExperimentStatus.COMPLETED
        return episode

    def queue_size(self) -> int:
        return len(self.queue)
