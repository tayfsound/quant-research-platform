"""Faz 271 — kullanıcı isteği: "LLM'i her pozisyonda devreye sokmak
lazım... onay panelimi anlamlı kılmak için." Gerçek zamanlı, her karar
için LLM'e sormak yerine (gecikme+maliyet, ve kullanıcının kendi
kararı: "kararı sadece LLM'e bırakmak riskli, mekanik yapı daha iyi
kalibre edilirse daha iyi sonuç verir — LLM'i denetleyici gibi
kullanmak, mantık hatalarını görmesini sağlamak"), LLM periyodik olarak
(bkz. services/celery_app.py beat schedule) SON dönemdeki TÜM kararları
toplu gözden geçiriyor.

NvidiaDecisionCritic.ask_with_tools() zaten gerçek DB/kod erişimi olan
6 araca sahip (llm_tools.py) — burada sadece o mekanizmayı, insan
sormasını beklemeden, düzenli aralıklarla kendiliğinden tetikliyoruz."""
import asyncio

from contracts.llm_audit_run import LLMAuditRun
from database.repositories.llm_audit_run_repository import LLMAuditRunRepository
from database.session_factory import SessionFactory
from llm_reasoner import NvidiaDecisionCritic

AUDIT_PROMPT = """Sen bu kantitatif trading araştırma platformunun periyodik SİSTEM
DENETÇİSİSİN. Gerçek zamanlı bir işlem kapısı DEĞİLSİN — tek görevin,
son dönemdeki GERÇEK karar geçmişini toplu olarak gözden geçirip
sistemik/mantıksal sorunlar aramak.

Yapman gerekenler:
1. get_recent_performance_summary aracıyla son 24-48 saatteki gerçek
   performansa bak.
2. classify_recent_stop_loss_failures aracıyla yakın zamandaki stop
   kayıplarının direction_error mi (yön yanlış) yoksa barrier_error mi
   (yön doğruydu ama stop/hedef mesafesi kötü ayarlanmış) olduğuna bak.
3. Gördüğün rakamlarda tutarsızlık, sistemik bir örüntü (ör. belirli bir
   koşulda tekrar eden kayıplar, confidence'ın gerçek sonuçla
   uyuşmaması, bir ajanın sürekli yanlış çıkması) varsa, search_code /
   read_source_file ile ilgili koda bak, kök nedeni anla.
4. get_shadow_mode_comparison aracıyla macro ajanının, council'in gerçek
   kararlarından tamamen bağımsız (sanal/paper) yalın performansını
   council'in gerçek performansıyla karşılaştır. Bu YAVAŞ değişen bir
   sinyal (haftalar içinde birikir) — her çalıştırmada tekrar tekrar
   yorumlama, sadece sample_size_sufficient=True olduğunda VE macro_only
   ile council arasında dikkat çekici bir fark varsa belirt.
5. Gördüğün rakamlarda tutarsızlık, sistemik bir örüntü (ör. belirli bir
   koşulda tekrar eden kayıplar, confidence'ın gerçek sonuçla
   uyuşmaması, bir ajanın sürekli yanlış çıkması) varsa, search_code /
   read_source_file ile ilgili koda bak, kök nedeni anla.
6. Somut, dar kapsamlı bir düzeltme önerebiliyorsan propose_code_change
   aracını kullan (asla doğrudan koda dokunamazsın, sadece insan onayı
   bekleyen bir kuyruğa öneri düşersin). Emin değilsen veya veri
   yetersizse ÖNERİDE BULUNMA — dürüstçe "şu an net bir sorun
   göremiyorum" de.

Bulduğun HER şeyi (öneri oluştursan da oluşturmasan da) Türkçe, kısa ve
somut şekilde özetle."""


async def _run_audit_async() -> dict:
    # Faz 268-sonrası — kritik bulgu: bu görev canlıda kayıtlı denetim
    # (llm_audit_runs) hiç üretmiyordu. Kök neden bulundu: NVIDIA API'nin
    # bu model için gecikmesi çok değişken — gerçek ölçüm, "sadece tamam
    # de" gibi bedava bir istekte bile 15-74 saniye arası salınıyor (curl
    # ile de doğrulandı, ağ/kodumuzla ilgisi yok). Uzun sistem promptu +
    # 6 araç tanımı içeren gerçek denetim isteği eski 120s sınırını
    # düzenli aşıyordu (httpx.ReadTimeout). Bu görev periyodik (6 saatte
    # bir) ve artık kendi "slow" kuyruğunda (bkz. celery_app.py) —
    # gecikmeye duyarlı hiçbir şeyi bloklamıyor, bu yüzden cömert bir
    # üst sınır (300s/çağrı) güvenle uygulanabilir.
    #
    # Faz 268-sonrası (ikinci bulgu) — 300s/çağrı + 3 deneme hakkı bile
    # yetmedi: gerçek llm_audit_runs geçmişi (9/9 çalıştırma) hiç
    # başarılı olmadı — hep "read operation timed out", "529 sunucu
    # hatası" ya da 6 iterasyonun tükenmesiyle bitti. deepseek-v4-flash
    # (varsayılan, "Respond" sekmesinde KALMAYA devam ediyor — orada
    # kullanıcı gerçek zamanlı bekliyor, kalite önceliği bilinçli bir
    # tercih) bu 6-araç-çağrılı döngü yükünde güvenilir değil. Kod
    # içindeki A/B test bulgusuna göre (yukarıdaki NvidiaDecisionCritic
    # yorumu) openai/gpt-oss-20b aynı görevi ~5sn'de tamamlıyor — sadece
    # BU periyodik arka plan denetimi için, döngünün gerçekten
    # tamamlanma ihtimalini büyük ölçüde artırmak amacıyla kullanılıyor.
    #
    # Faz 268-sonrası (üçüncü bulgu) — model değişince zaman aşımı bitti
    # (6 iterasyon ~6sn'de tamamlandı) ama YENİ bir örüntü ortaya çıktı:
    # gerçek bir çalıştırmada model kendi llm_tools.py dosyasını üst üste
    # binen satır aralıklarıyla 3 kez okuyup 6 iterasyonu hiç sonuca
    # varmadan tüketti — A/B testinin öngördüğü "daha sığ" davranışın bir
    # başka yüzü (daha az verimli araç kullanımı). Artık her iterasyon
    # ~1sn (önceden ~90sn) sürdüğüne göre iterasyon sayısını ciddi
    # artırmanın maliyeti neredeyse sıfır — modelin dolaşıp yine de
    # sonuca varabilmesi için pay büyütüldü.
    critic = NvidiaDecisionCritic(model="openai/gpt-oss-20b")
    return await critic.ask_with_tools(AUDIT_PROMPT, timeout_ms=300000, max_iterations=15)


def run_system_audit() -> dict:
    result = _run_and_capture()
    tool_calls = result.get("tool_calls", [])
    proposals_created = sum(
        1 for c in tool_calls
        if c.get("tool") == "propose_code_change" and isinstance(c.get("result"), dict) and c["result"].get("proposal_id")
    )

    run = LLMAuditRun(
        response=result.get("response", ""),
        tool_calls=tool_calls,
        proposals_created=proposals_created,
        status=result.get("status", "ok"),
    )
    with SessionFactory.get_session() as session:
        LLMAuditRunRepository(session).save(run)

    return {
        "id": str(run.id),
        "response": run.response,
        "tool_call_count": len(tool_calls),
        "proposals_created": proposals_created,
        "status": run.status,
    }


def _run_and_capture() -> dict:
    return asyncio.run(_run_audit_async())
