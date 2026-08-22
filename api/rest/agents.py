"""Agent roster API — dashboard'un Agents (eski Strategies) sayfası için.

AgentRegistry.create_default()'ın GERÇEKTEN register ettiği domain'leri
okur — statik/uydurma bir liste değil, kod değişse bu da otomatik değişir."""
from fastapi import APIRouter, Depends

from agents.registry import AgentRegistry
from contracts.agent import AgentDomain
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])

_DESCRIPTIONS: dict[AgentDomain, str] = {
    AgentDomain.TECHNICAL: "Trend, momentum, market structure, RSI/EMA — klasik teknik analiz.",
    AgentDomain.MACRO: "Enflasyon, likidite, merkez bankası duruşu.",
    AgentDomain.ONCHAIN: "Exchange akışı, whale hareketleri, MVRV Z-Score.",
    AgentDomain.PATTERN: "Wyckoff fazları, break of structure, fair value gap, likidite süpürme.",
    AgentDomain.QUANT: "Z-score, Hurst exponent, otokorelasyon — rejime göre mean-reversion/momentum.",
    AgentDomain.ORDER_FLOW: "Gerçek order book: bid/ask dengesizliği, spread, agresif alış/satış oranı.",
    AgentDomain.TIME: "Funding saati, hafta sonu, seans — yön tahmini yapmaz, sadece risk işaretler.",
    AgentDomain.EPISTEMOLOGY: "Veri tamlığı/tazeliği — council'in genel güvenini dengeler.",
    AgentDomain.RELATIVE_STRENGTH: "Bu sembolün getirisi, watchlist'teki diğer sembollerin ortalamasına göre daha mı güçlü/zayıf.",
    AgentDomain.CREDIT: "Tahvil piyasası kredi koşulları — getiri eğrisi (10Y-2Y) tersine dönmesi ve kredi spread'i genişlemesi, risk varlıklarından ÖNCE gelen resesyon/stres uyarısı.",
    AgentDomain.VOLATILITY: "Deribit DVOL (kriptonun VIX'i) — ani implied volatilite sıçraması, yön bağımsız genel piyasa-stresi göstergesi.",
}

_ROLE: dict[AgentDomain, str] = {d: "vote" for d in _DESCRIPTIONS}


@router.get("/")
def list_agents(user: AuthContext = Depends(get_current_user)):
    registry = AgentRegistry.create_default()
    domains = registry.list_domains()
    return {
        "agents": [
            {
                "domain": d.value,
                "role": _ROLE.get(d, "vote"),
                "description": _DESCRIPTIONS.get(d, ""),
            }
            for d in domains
        ],
        "critics": [
            {"domain": "risk", "role": "critic", "description": "Aşırı güven + yüksek volatilite, yön kalabalığı, düşük veri kalitesini eleştirir."},
            {"domain": "alter_ego", "role": "critic", "description": "Ajanların %75+'i aynı yönde oy verirken, ortalama güven yüksek ama kanıt zayıfken, ya da oybirliğine rağmen tartışmada hiç itiraz çıkmamışken council'i uyarır — pozisyon küçültmeyi ya da karşıt kanıt aramayı önerir."},
            {"domain": "source_reliability", "role": "annotator", "description": "Her ajanın gerçek geçmiş performansına göre güvenilirlik puanı verir."},
        ],
    }
