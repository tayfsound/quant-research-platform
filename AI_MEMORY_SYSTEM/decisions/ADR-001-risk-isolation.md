# ADR-001: Risk Motorunun Tam İzolasyonu

**Durum:** Kabul edildi  
**Tarih:** 2026-07-20  
**Karar:** Risk yönetimi, yapay zekâ modellerinden ve strateji optimizasyonundan tamamen bağımsız bir bounded context olarak tasarlanacaktır.  
**Gerekçe:** AI'nın risk limitlerini değiştirmesi, felaketle sonuçlanabilecek bir güvenlik açığıdır. Risk, imzalı konfigürasyon dosyaları ile çalışmalı ve yalnızca yetkili insan operatörler tarafından güncellenebilmelidir.  
**Alternatifler:** AI'nın risk limitlerini önermesine izin verip manuel onay gerektirmek; ancak bu da kötüye kullanıma açıktır. Tam izolasyon en güvenlisidir.  
**Sonuçlar:** Risk bağlamı hiçbir ML/RL/strateji modülüne bağımlı olmayacak. Simülatör, karar alınmadan önce risk onayını bekleyecek.
