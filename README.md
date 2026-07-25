# AI Quant Research Platform

Kurumsal seviye yapay zekâ kantitatif araştırma işletim sistemi.  
**Sadece kâğıt ticaret!** Canlı emir iletimi yoktur.

## Hızlı Başlangıç

1. Depoyu klonlayın.
2. `docker compose up -d` ile altyapıyı başlatın.
3. Backend: `pip install -e ".[dev]"` ve `uvicorn api.main:app --reload`
4. Dashboard: `cd dashboard && npm install && npm run dev`

## AI Bellek Sistemi

Projenin kurumsal hafızası `AI_MEMORY_SYSTEM/` altındadır.  
Yeni katkıcılar önce `PROJECT_MEMORY.md` ve `CURRENT_STATE.md` dosyalarını okumalıdır.

## Lisans

MIT
