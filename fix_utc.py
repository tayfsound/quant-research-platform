import os
import re

files = [
    "market_data/ingestion/mock_adapter.py",
    "market_data/ingestion/ohlcv.py", 
    "backtest/walk_forward.py",
    "tests/replay/test_replay_snapshot.py",
]

for path in files:
    with open(path, 'r') as f:
        content = f.read()
    
    # from datetime import datetime -> from datetime import datetime, timezone
    content = content.replace(
        "from datetime import datetime",
        "from datetime import datetime, timezone"
    )
    
    # datetime.utcnow() -> datetime.now(timezone.utc)
    content = content.replace("datetime.utcnow()", "datetime.now(timezone.utc)")
    
    with open(path, 'w') as f:
        f.write(content)
    print(f"  ✓ {path}")

print("\n=== TEST ===")
import subprocess
r = subprocess.run([
    "pytest", 
    "tests/test_market_data.py", 
    "tests/test_market_data_provider.py", 
    "tests/replay/test_replay_snapshot.py", 
    "tests/test_backtest.py", 
    "-q"
], capture_output=True, text=True)
print(r.stdout[-800:] if len(r.stdout) > 800 else r.stdout)
if r.returncode != 0:
    print("ERR:", r.stderr[:400])
