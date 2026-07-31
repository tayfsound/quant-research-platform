import os

# 1. engines/cognitive_pipeline.py'ye BinderStage ekle
with open('engines/cognitive_pipeline.py', 'r') as f:
    content = f.read()

binder_stage = '''class BinderStage:
    """Knowledge -> CognitiveBinding -> Belief (P0-5 bind)."""
    def __init__(self):
        from services.cognitive_binder import CognitiveBinder
        self.binder = CognitiveBinder()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        for item in ctx.cognition.relevant_knowledge:
            if item.get("type") == "wisdom":
                from contracts.expression import Expression, Constant
                from contracts.cognitive_binding import CognitiveBinding
                expr = Expression(
                    name=item.get("category", "unknown"),
                    description=item.get("principle", ""),
                    root=Constant(value=item.get("confidence", 0.5)),
                )
                binding = CognitiveBinding(
                    source_type="knowledge_base",
                    expression=expr,
                    confidence=item.get("confidence", 0.5),
                    evidence_count=item.get("validation_count", 0),
                )
                belief = self.binder.knowledge_to_belief(binding)
                ctx.cognition.relevant_knowledge.append({
                    "type": "binder_belief",
                    "data": belief.model_dump(),
                })
        return ctx

'''

content = content.replace('class RecordingStage:', binder_stage + 'class RecordingStage:')
with open('engines/cognitive_pipeline.py', 'w') as f:
    f.write(content)
print('✓ engines/cognitive_pipeline.py')

# 2. services/cognitive_engine.py'ye import ve cagri ekle
with open('services/cognitive_engine.py', 'r') as f:
    content = f.read()

content = content.replace(
    'from engines.cognitive_pipeline import (',
    'from engines.cognitive_pipeline import (\n    BinderStage,'
)
content = content.replace(
    'self.knowledge_stage = KnowledgeStage()',
    'self.knowledge_stage = KnowledgeStage()\n        self.binder_stage = BinderStage()'
)
content = content.replace(
    'ctx = self.knowledge_stage.execute(ctx)\n        ctx, belief, opinions = self.council_stage.execute(ctx)',
    'ctx = self.knowledge_stage.execute(ctx)\n        ctx = self.binder_stage.execute(ctx)\n        ctx, belief, opinions = self.council_stage.execute(ctx)'
)

with open('services/cognitive_engine.py', 'w') as f:
    f.write(content)
print('✓ services/cognitive_engine.py')

# 3. Test ekle
with open('tests/test_cognitive_cycle.py', 'r') as f:
    content = f.read()

new_test = '''
def test_binder_stage_produces_belief_from_wisdom():
    """BinderStage wisdom itemlarini belief e cevirir (CognitiveBinder bound)."""
    from engines.cognitive_pipeline import BinderStage, KnowledgeStage
    from contracts.context import CognitiveCycleContext

    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.decision.proposed_direction = "LONG"

    ks = KnowledgeStage()
    ctx = ks.execute(ctx)

    bs = BinderStage()
    ctx = bs.execute(ctx)

    binder_beliefs = [k for k in ctx.cognition.relevant_knowledge if k.get("type") == "binder_belief"]
    assert len(binder_beliefs) > 0
    assert "data" in binder_beliefs[0]
    assert "direction" in binder_beliefs[0]["data"]
'''

content = content.rstrip() + new_test
with open('tests/test_cognitive_cycle.py', 'w') as f:
    f.write(content)
print('✓ tests/test_cognitive_cycle.py')

print('\n=== TEST ===')
import subprocess
r = subprocess.run(['pytest', 'tests/test_cognitive_cycle.py', '-v', '--tb=short'], capture_output=True, text=True)
print(r.stdout[-1000:] if len(r.stdout) > 1000 else r.stdout)
if r.returncode != 0:
    print('ERR:', r.stderr[:400])
