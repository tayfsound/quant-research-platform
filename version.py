"""Sistem versiyon bilgileri."""
# SYSTEM_VERSION daha önce Faz 44'ten (2026-07) beri hiç bumplenmemiş, ayrı
# bir 0.x semver şemasıydı — AI_MEMORY_SYSTEM/CURRENT_STATE.md'nin kendi
# "v1.x" başlık numarasıyla çelişiyordu (iki farklı versiyon kaynağı). Artık
# CURRENT_STATE.md'nin numarasını takip ediyor — tek gerçek kaynak.
SYSTEM_VERSION = "1.53.0"
PROMPT_VERSION = "155-R3"
# Faz 268w'den beri gerçek LLM Decision Critic modeli bu — eski değer
# (mistral, yerel Ollama) Faz 268w'de NVIDIA NIM'e geçişle birlikte
# güncellenmemiş kalmıştı, sadece metrics.py'nin gözlemlenebilirlik
# etiketi (karar mantığı buna bağlı değil).
MODEL_VERSION = "deepseek-ai/deepseek-v4-flash-0731"
SCHEMA_VERSION = 3
