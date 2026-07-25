# Mimari Özeti

Platform, altıgen (hexagonal) mimari kullanır. Bounded context'ler:
- exchange_gateway, market_data, ml, rl, strategies, simulator, risk, analytics, api, dashboard

Tüm iletişim portlar (Python Protocol) ve asenkron olaylar ile yapılır.  
Risk bağlamı AI/ML'ye bağımlı değildir.  
Veri tabanı: TimescaleDB (zaman serisi), PostgreSQL (ilişkisel), Redis (önbellek), pgvector (vektör bellek).  
Event log (Kafka/Redpanda) sistem sinir sistemi; tüm durum bu log'dan türetilir.
