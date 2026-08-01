with open('services/replay_engine.py', 'r') as f:
    content = f.read()

# Lazy init: engine ilk kullanımda oluşturulsun
content = content.replace(
    '        self.engine = CognitiveEngine()',
    '        self._engine = None'
)

content = content.replace(
    '            ctx = self.engine.run(ctx, persist=False)',
    '''            if self._engine is None:
n                self._engine = CognitiveEngine()
n            ctx = self._engine.run(ctx, persist=False)'''
)

with open('services/replay_engine.py', 'w') as f:
    f.write(content)
print("✓ Lazy init eklendi")

import subprocess
r = subprocess.run(['pytest', 'tests/test_replay_integration.py', '-q'], capture_output=True, text=True)
print(r.stdout)
if r.returncode != 0:
    print("ERR:", r.stderr[:300])
