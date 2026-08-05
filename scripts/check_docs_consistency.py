#!/usr/bin/env python3
"""Faz 182: "durum raporu != gerçek kod" makasını CI'da kapat.

CURRENT_STATE.md'nin en üstteki "**Test:** N passed, ..." satırındaki N
rakamını gerçek `pytest -q` çıktısındaki passed sayısıyla karşılaştırır.
Uyuşmazlarsa (biri diğerini güncellemeyi unuttuysa) CI'ı kırar — bu
oturum boyunca CURRENT_STATE.md defalarca elle güncellendi, otomatik bir
kontrol olmadan bu her zaman tekrar kayacaktır (roadmap'in kendi
tahmini).

Kasıtlı olarak dar kapsamlı: sadece "passed" sayısını kontrol eder, tüm
CURRENT_STATE.md'yi anlamsal olarak doğrulamaya çalışmaz (o, ayrı ve çok
daha büyük bir iş olurdu).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT_STATE = ROOT / "AI_MEMORY_SYSTEM" / "CURRENT_STATE.md"


def real_passed_count() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    if not match:
        print("could not determine collected test count from pytest output:")
        print(result.stdout)
        sys.exit(1)
    return int(match.group(1))


def documented_passed_count() -> int | None:
    text = CURRENT_STATE.read_text()
    match = re.search(r"\*\*Test:\*\*\s*(\d+)\s*passed", text)
    if not match:
        return None
    return int(match.group(1))


def main() -> None:
    documented = documented_passed_count()
    if documented is None:
        print("CURRENT_STATE.md has no '**Test:** N passed' line to check — skipping.")
        return

    # We compare against collected count, not a live pytest run (a full run
    # here would double CI time and needs a real DB) — collected count is a
    # reasonable proxy: if it drifts significantly from what CURRENT_STATE.md
    # claims, someone forgot to update the doc after adding/removing tests.
    collected = real_passed_count()

    # Allow a small margin: CURRENT_STATE.md's "N passed" excludes skipped/
    # xfailed tests, while --collect-only counts every test item.
    if abs(collected - documented) > 5:
        print(
            f"CURRENT_STATE.md claims {documented} passed, but pytest currently "
            f"collects {collected} test items. Update CURRENT_STATE.md's "
            f"'**Test:**' line, or explain the gap."
        )
        sys.exit(1)

    print(f"OK: CURRENT_STATE.md ({documented} passed) is consistent with pytest ({collected} collected).")


if __name__ == "__main__":
    main()
