"""Sembol formatlarını standartlaştırır."""
def normalize_symbol(exchange: str, symbol: str) -> str:
    return symbol.upper().replace("-", "").replace("/", "").replace("_", "")
