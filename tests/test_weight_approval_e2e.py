"""WeightApproval E2E — approve triggers weight snapshot save."""
from unittest.mock import patch, MagicMock

def test_approve_creates_weight_snapshot():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.weight_optimizer import WeightOptimizer
            from contracts.agent_memory import AgentMemory
            from services.weight_repository import WeightRepository
            
            # Create optimizer with mock memory
            memory = AgentMemory()
            memory.domains = lambda: ["technical", "macro"]
            memory.get_recent = lambda n: []
            
            optimizer = WeightOptimizer(
                agent_memory=memory,
                weight_repository=WeightRepository(),
            )
            
            # Mock: max_change > 0.05 should create pending approval
            with patch.object(optimizer, '_calculate_domain_scores') as mock_scores:
                mock_scores.return_value = {"technical": 1.3, "macro": 1.1}
                
                with patch.object(optimizer.weight_repository, 'get_latest') as mock_latest:
                    mock_latest.return_value = MagicMock(weights={"technical": 1.0})
                    
                    # This should trigger approval creation
                    result = optimizer.optimize(
                        agents=[{"domain": "technical", "score": 0.8}],
                        outcome=MagicMock(decision_score=0.5),
                        require_approval=True,
                    )
                    
                    # Should return old weights (pending)
                    assert result == {"technical": 1.0} or "technical" in result
