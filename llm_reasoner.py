"""NVIDIA NIM tabanlı LLM Decision Critic — nihai sürüm.

Faz 268-sonrası — kullanıcı isteği: yerel Ollama (mistral:7b-instruct)
tabanlı OllamaExplainer'ın yerini, NVIDIA'nın ücretsiz NIM API'si
(build.nvidia.com, OpenAI-uyumlu) üzerinden erişilen çok daha güçlü bir
modelin aldığı bir "eleştirmen." Amaç sadece kararı AÇIKLAMAK değil,
gerçekten İTİRAZ ETMEK — ajanlar arası çelişkileri, gözden kaçan
riskleri, zayıf gerekçeleri arayan bir ikinci göz.

Kasıtlı olarak SADECE danışma/ölçüm — hiçbir kararı burada otomatik
REDDETMİYOR ya da ONAYLAMIYOR (risk_adjustment_factor mevcut sözleşmenin
[0.5, 1.0] aralığında kalıyor, ama bunu gerçekten UYGULAMAK ayrı, insan
onaylı bir karar — bkz. proje kuralı: AI kendi kararlarına unilateral
otorite veremez)."""
import asyncio
import hashlib
import json
import logging
import re

from contracts.llm import LLMExplanation

logger = logging.getLogger(__name__)

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Faz 268-sonrası — kullanıcı bulgusu, gerçek olay: NVIDIA API "Server
# error '529 status code 529'" döndürdü — bu HIZLI başarısız olan, GEÇİCİ
# bir hata (timeout değil, saniyeler içinde dönen bir hata yanıtı), kısa
# bir bekleyip tekrar denemek genellikle işe yarar. Zaman aşımlarını
# (httpx.TimeoutException/TransportError) VARSAYILAN OLARAK yeniden
# denemiyoruz — TEK çağrılık fonksiyonlarda (ask/explain) dış asyncio.
# wait_for'un bütçesi timeout_ms + 0.5sn gibi dar bir pay bırakıyor,
# zaten yavaş bir isteği tekrarlamak o sınırı anlamsızca aşardı.
#
# Kullanıcı bulgusu (sonraki bulgu) — gerçek log: "Respond" sekmesindeki
# ask_with_tools() çok-adımlı araç döngüsünde TEK bir iterasyonun
# httpx.ReadTimeout'a uğraması TÜM konuşmayı çöktürüyordu ("Hata: The
# read operation timed out"), kullanıcı sıfırdan başlamak zorunda
# kalıyordu. Ama ask_with_tools'un dış bütçesi TEK çağrılık fonksiyonların
# aksine timeout_ms × max_iterations (5×120sn=600sn) — bir iterasyonun
# ara sıra yavaş kalmasını tolere edecek kadar geniş. retry_on_timeout=
# True SADECE oradan geçiliyor.
_TRANSIENT_HTTP_STATUS_CODES = {429, 500, 502, 503, 504, 529}
_RETRY_BACKOFF_SECONDS = (2.0, 5.0)


def _post_with_retry(
    url: str, headers: dict, json_payload: dict, timeout_seconds: float, retry_on_timeout: bool = False
):
    """Bu modüldeki HER httpx.post çağrısı için ortak, geçici-hata-
    farkında yeniden deneme sarmalayıcısı — hepsi periyodik arka plan
    görevleri (canlı karar döngüsünde gerçek zamanlı çağrılmıyor), bu
    yüzden birkaç saniyelik ek bekleme kabul edilebilir."""
    import time

    import httpx

    last_exc: Exception | None = None
    for attempt, delay in enumerate((0.0,) + _RETRY_BACKOFF_SECONDS):
        if delay:
            time.sleep(delay)
        try:
            response = httpx.post(url, headers=headers, json=json_payload, timeout=timeout_seconds)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code not in _TRANSIENT_HTTP_STATUS_CODES:
                raise
            logger.warning(
                "LLM API geçici sunucu hatası, tekrar denenecek",
                extra={"status_code": exc.response.status_code, "attempt": attempt},
            )
        except httpx.TimeoutException as exc:
            last_exc = exc
            if not retry_on_timeout:
                raise
            logger.warning(
                "LLM API zaman aşımı, tekrar denenecek (geniş bütçeli çağrı)",
                extra={"attempt": attempt},
            )
    raise last_exc

SYSTEM_PROMPT = """ÖNEMLİ: Bütün yanıtını SADECE TÜRKÇE yaz. İngilizce tek bir cümle bile yazma.
(IMPORTANT: Write your entire response ONLY IN TURKISH. Do not write a single sentence in English.)

You are a skeptical, adversarial senior risk reviewer at a quantitative hedge
fund — your job is NOT to explain why a trading decision looks reasonable,
it is to actively try to TEAR IT APART, in Turkish.
Rules:
- Look for CONTRADICTIONS between the voting agents (e.g. one agent says
  LONG citing momentum while another says SHORT citing the same data).
- Look for evidence that is weak, stale, or contradicted by other evidence
  in the payload.
- Look for risks the ensemble may have missed (regime uncertainty, thin
  data, overconfidence).
- Do NOT be diplomatic — if the decision looks bad, say so bluntly.
- If you genuinely find nothing wrong after a real adversarial attempt,
  say so honestly instead of inventing a fake objection.
- Use precise financial terminology (RSI, MACD, LONG/SHORT etc. may stay as-is).
- Be concise: maximum 6 sentences.
- "explanation", every item in "risks", and "confidence_comment" MUST be
  written in Turkish — this is mandatory, not optional.
- Output ONLY valid JSON in this format:
{"explanation": "(Türkçe itiraz/eleştiri)", "risks": ["(Türkçe risk 1)", "(Türkçe risk 2)"], "confidence_comment": "(Türkçe yorum)", "risk_adjustment_factor": 0.85}
- risk_adjustment_factor must be between 0.5 and 1.0 (1.0 = itirazım yok, 0.5 = ciddi itirazım var).

Hatırlatma: Yanıtının tamamı Türkçe olmalı.
"""

THREAD_GRACE_SECONDS = 0.5

def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]

class NvidiaDecisionCritic:
    # Faz 268-sonrası — gerçek A/B testi (aynı gerçek karar payload'ıyla):
    # deepseek-ai/deepseek-v4-flash-0731 (90s) openai/gpt-oss-20b'den (5s)
    # gözle görülür derecede daha derin eleştiri üretti (ör. Hurst
    # exponent'in "rastgele yürüyüş" bölgesinde olduğunu fark etti —
    # gpt-oss-20b bunu kaçırdı). openai/gpt-oss-120b bu yük altında
    # tutarlı biçimde zaman aşımına uğradı, kullanılamaz. Bu bir canlı
    # işlem kapısı DEĞİL (danışma amaçlı, senkron olmayan bir çağrı) —
    # hız yerine kalite tercih edildi.
    def __init__(self, model: str = "deepseek-ai/deepseek-v4-flash-0731", api_key: str | None = None):
        self.model = model
        self._api_key = api_key

    def _resolve_api_key(self) -> str:
        # None -> constructor'da hiç verilmemiş, AppSettings'e düş.
        # "" (boş string) -> ÇAĞIRAN TARAF bilinçli olarak "anahtar yok"
        # demek istiyor (ör. test) — AppSettings'teki gerçek anahtara
        # sessizce düşülmemeli.
        if self._api_key is not None:
            return self._api_key
        from config.settings import get_settings

        return get_settings().NVIDIA_API_KEY

    _DEFAULT_ASK_SYSTEM_PROMPT = (
        "Bütün yanıtını SADECE TÜRKÇE yaz. Sen bir kantitatif "
        "trading araştırma platformunda çalışan, deneyimli bir "
        "kantitatif analist/risk uzmanısın. Kısa ve net cevap ver."
    )

    async def ask(self, message: str, timeout_ms: int = 120000, system_prompt: str | None = None) -> str:
        """Faz 268-sonrası — kullanıcı isteği: dashboard'da serbest metin
        soru/cevap sekmesi. explain()'in aksine JSON şemasına ZORLAMIYOR
        — ajanlar arası çelişki analiziyle sınırlı değil, genel bir
        soru/cevap. Hata/zaman aşımı durumunda dürüstçe bir hata mesajı
        döner (LLMExplanation.neutral() gibi icat edilmiş bir "yanıt"
        DEĞİL — burada yanıtın kendisi zaten kullanıcıya gösterilecek).

        system_prompt: None ise varsayılan genel-amaçlı asistan rolü;
        verilirse (ör. llm_news_sentiment_provider.py'nin JSON-yapılı
        haber özeti isteği) onun yerine geçer."""
        api_key = self._resolve_api_key()
        if not api_key:
            return "NVIDIA_API_KEY ayarlanmamış — .env dosyasına eklenmeli."

        used_prompt = system_prompt or self._DEFAULT_ASK_SYSTEM_PROMPT
        llm_timeout = timeout_ms / 1000
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._ask_sync, message, timeout_ms, api_key, used_prompt),
                timeout=llm_timeout + THREAD_GRACE_SECONDS,
            )
        except TimeoutError:
            logger.warning("LLM ask timed out", extra={"timeout_ms": timeout_ms, "model": self.model})
            return f"Zaman aşımı ({timeout_ms}ms) — model yanıt veremedi."
        except Exception as e:
            logger.exception("LLM ask failed", extra={"error": str(e)})
            return f"Hata: {e}"

    def _ask_sync(self, message: str, timeout_ms: int, api_key: str, system_prompt: str) -> str:
        response = _post_with_retry(
            NVIDIA_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json_payload={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            },
            timeout_seconds=timeout_ms / 1000,
        )
        data = response.json()
        choices = data.get("choices") or []
        content = (choices[0].get("message", {}).get("content") or "") if choices else ""
        return content.strip() or "(boş yanıt)"

    _TOOLS_SYSTEM_PROMPT = (
        "Bütün yanıtını SADECE TÜRKÇE yaz. Sen bir kantitatif trading "
        "araştırma platformunda çalışan, deneyimli bir kantitatif "
        "analist/risk uzmanısın. Sana bu sistemin GERÇEK koduna ve "
        "veritabanına erişen araçlar verildi. KURALLAR:\n"
        "- Bir soruyu cevaplamak için gerçek veri/kod gerekiyorsa "
        "(kazanma oranı, bir dosyanın içeriği, bir fonksiyonun nerede "
        "olduğu vb.) MUTLAKA ilgili aracı çağır — kendi eğitim "
        "verinden veya genel bilgiden bir sayı/kod parçası UYDURMA. "
        "Bu kritik: geçmişte bunu yapmadığın için yanlış/uydurma "
        "istatistikler ürettiğin tespit edildi.\n"
        "- Araç sonucu boşsa/hata döndürüyorsa dürüstçe 'bu veriyi "
        "bulamadım' de, asla telafi etmek için bir sayı icat etme.\n"
        "- Gerçek bir sorun bulup somut bir düzeltme önerebiliyorsan "
        "propose_code_change aracını kullan. Bunun DIŞINDA hiçbir "
        "zaman koda dokunamazsın — sadece kullanıcının onayını "
        "bekleyen bir öneri kuyruğuna eklersin."
    )
    _MAX_TOOL_ITERATIONS = 5

    async def ask_with_tools(self, message: str, timeout_ms: int = 120000, max_iterations: int = _MAX_TOOL_ITERATIONS) -> dict:
        """Faz 270 — kullanıcı isteği: Respond sekmesindeki LLM'in artık
        GERÇEKTEN kodu/DB'yi görebilmesi (bkz. llm_tools.py). ask()'ın
        aksine gerçek OpenAI-uyumlu function-calling döngüsü çalıştırır —
        model bir araç çağırmak isterse gerçek Python fonksiyonu
        çalıştırılır, sonucu modele geri verilir, model nihai bir metin
        cevabı üretene kadar (ya da max_iterations'a ulaşılana kadar)
        tekrarlanır. Döner: {"response": str, "tool_calls": [...]} —
        tool_calls, dashboard'da "LLM şunu kontrol etti" şeffaflığı için."""
        api_key = self._resolve_api_key()
        if not api_key:
            return {"response": "NVIDIA_API_KEY ayarlanmamış — .env dosyasına eklenmeli.", "tool_calls": []}

        llm_timeout = timeout_ms / 1000
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._ask_with_tools_sync, message, timeout_ms, api_key, max_iterations),
                timeout=llm_timeout * max_iterations + THREAD_GRACE_SECONDS,
            )
        except TimeoutError:
            logger.warning("LLM ask_with_tools timed out", extra={"timeout_ms": timeout_ms, "model": self.model})
            return {"response": f"Zaman aşımı ({timeout_ms}ms) — model yanıt veremedi.", "tool_calls": []}
        except Exception as e:
            logger.exception("LLM ask_with_tools failed", extra={"error": str(e)})
            return {"response": f"Hata: {e}", "tool_calls": []}

    def _ask_with_tools_sync(self, message: str, timeout_ms: int, api_key: str, max_iterations: int) -> dict:
        import llm_tools
        from llm_tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

        messages: list[dict] = [
            {"role": "system", "content": self._TOOLS_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
        tool_call_log: list[dict] = []

        # Faz 268-sonrası — gerçek bulgu: model her iterasyonda YENİ bir
        # araç çağırmaya devam edip max_iterations'a "sessizce" çarpabiliyor
        # — kendiliğinden ne zaman duracağını bilmiyor (gerçek örnek:
        # llm_system_audit_task, 15 iterasyonun TAMAMINI dosya okumakla
        # geçirip hiç sonuç yazmadan bitti). Prompt'a "özet yaz" demek
        # (denendi) modelin kendi takdirine bırakıyor, garantili değil.
        # Artık SON iterasyonda tool_choice="none" ile model API düzeyinde
        # daha fazla araç çağıramıyor — o ana kadar topladığı gerçek
        # bulgularla ZORUNLU olarak bir metin cevabı üretiyor.
        for i in range(max_iterations):
            is_last_iteration = i == max_iterations - 1
            request_messages = messages
            if is_last_iteration:
                request_messages = messages + [{
                    "role": "user",
                    "content": (
                        "Artık araç çağıramazsın. Şimdiye kadar topladığın "
                        "GERÇEK bulgulara dayanarak nihai, somut bir özet "
                        "yaz. Hiçbir şey bulamadıysan bunu dürüstçe söyle."
                    ),
                }]

            response = _post_with_retry(
                NVIDIA_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json_payload={
                    "model": self.model,
                    "messages": request_messages,
                    "tools": TOOL_SCHEMAS,
                    "tool_choice": "none" if is_last_iteration else "auto",
                    "temperature": 0.2,
                    "max_tokens": 1500,
                },
                timeout_seconds=timeout_ms / 1000,
                retry_on_timeout=True,
            )
            data = response.json()
            choices = data.get("choices") or []
            assistant_message = choices[0].get("message", {}) if choices else {}
            tool_calls = assistant_message.get("tool_calls") or []

            if not tool_calls or is_last_iteration:
                content = (assistant_message.get("content") or "").strip()
                return {
                    "response": content or "Araç çağrı döngüsü sınırına ulaşıldı, net bir cevap üretemedim.",
                    "tool_calls": tool_call_log,
                }

            messages.append(assistant_message)
            for call in tool_calls:
                function_name = call.get("function", {}).get("name", "")
                raw_arguments = call.get("function", {}).get("arguments") or "{}"
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {}

                # function_name TOOL_FUNCTIONS'da (izin verilen araç
                # listesi) var mı diye doğrulanıyor, ama gerçek çağrılan
                # callable modül üzerinden TAZE okunuyor (getattr) — testte
                # llm_tools.<fonksiyon>'u monkeypatch'lemek gerçekten
                # etkili olsun diye (TOOL_FUNCTIONS sabit bir dict olsaydı
                # eski referansı tutardı).
                if function_name not in TOOL_FUNCTIONS:
                    result = {"error": f"unknown_tool: {function_name}"}
                else:
                    tool_fn = getattr(llm_tools, function_name)
                    try:
                        result = tool_fn(**arguments)
                    except Exception as exc:
                        logger.warning("LLM tool call failed", extra={"tool": function_name, "error": str(exc)})
                        result = {"error": str(exc)}

                tool_call_log.append({"tool": function_name, "arguments": arguments, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, default=str)[:4000],
                })

        return {
            "response": "Araç çağrı döngüsü sınırına ulaşıldı, net bir cevap üretemedim.",
            "tool_calls": tool_call_log,
        }

    async def explain(self, ensemble_output: dict, prompt: str | None = None, timeout_ms: int = 120000) -> LLMExplanation:
        # NVIDIA_API_KEY boşsa (kayıt yapılmadıysa) fail-closed — sessizce
        # nötr döner, aynı FRED_API_KEY/HELIUS_API_KEY konvansiyonu.
        api_key = self._resolve_api_key()
        if not api_key:
            return LLMExplanation.neutral()

        used_prompt = prompt or SYSTEM_PROMPT
        prompt_hash_val = hash_prompt(used_prompt)
        llm_timeout = timeout_ms / 1000
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._call_llm_sync, ensemble_output, used_prompt, timeout_ms, api_key),
                timeout=llm_timeout + THREAD_GRACE_SECONDS,
            )
        except TimeoutError:
            logger.warning("LLM explain timed out", extra={
                "timeout_ms": timeout_ms,
                "symbol": ensemble_output.get("symbol"),
                "trade_id": ensemble_output.get("trade_id"),
                "model": self.model,
                "prompt_hash": prompt_hash_val,
            })
            return LLMExplanation.neutral()
        except Exception as e:
            logger.exception("LLM explain failed", extra={
                "error": str(e),
                "symbol": ensemble_output.get("symbol"),
                "prompt_hash": prompt_hash_val,
            })
            return LLMExplanation.neutral()

    def _call_llm_sync(self, ensemble_output: dict, prompt: str, timeout_ms: int, api_key: str) -> LLMExplanation:
        import httpx
        user_prompt = json.dumps(ensemble_output, indent=2, default=str)
        symbol = ensemble_output.get("symbol", "unknown")
        try:
            response = _post_with_retry(
                NVIDIA_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json_payload={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    # gpt-oss/reasoning modelleri düşünme adımlarını da
                    # completion token bütçesinden harcıyor — düşük bir
                    # max_tokens gerçek içeriği boş bırakabiliyor (ölçüldü).
                    "max_tokens": 1500,
                },
                timeout_seconds=timeout_ms / 1000,
            )
            data = response.json()
            choices = data.get("choices") or []
            raw = (choices[0].get("message", {}).get("content") or "") if choices else ""
            if not raw or not raw.strip():
                logger.warning("LLM returned empty response", extra={"symbol": symbol})
                return LLMExplanation.neutral()
            return self._parse_output(raw)
        except httpx.TimeoutException:
            logger.warning("LLM HTTP timeout", extra={
                "symbol": symbol,
                "prompt_hash": hash_prompt(prompt),
            })
            return LLMExplanation.neutral()
        except Exception as e:
            logger.exception("LLM HTTP call failed", extra={"error": str(e), "symbol": symbol})
            return LLMExplanation.neutral()

    def _parse_output(self, raw: str) -> LLMExplanation:
        raw = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
        start = raw.find('{')
        if start != -1:
            raw = raw[start:]
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(raw)
        except json.JSONDecodeError:
            logger.warning("JSON parse failed", extra={"raw_preview": raw[:200]})
            return LLMExplanation(
                explanation=raw[:500],
                risks=[],
                confidence_comment="JSON parse failed",
                risk_adjustment_factor=1.0,
            )

        return LLMExplanation(
            explanation=data.get("explanation", ""),
            risks=data.get("risks", []),
            confidence_comment=data.get("confidence_comment", ""),
            risk_adjustment_factor=data.get("risk_adjustment_factor", 1.0),
        )

    async def analyze_logs(self, logs: list[dict], current_prompt: str) -> dict:
        if not logs:
            return {"analysis": "No logs", "new_system_prompt": current_prompt}
        total = len(logs)
        wins = [trade_log for trade_log in logs if trade_log.get("outcome", {}).get("pnl", 0) > 0]
        losses = [trade_log for trade_log in logs if trade_log.get("outcome", {}).get("pnl", 0) <= 0]
        win_rate = len(wins) / total if total > 0 else 0.0
        summary = {
            "task": "analyze_logs",
            "total_trades": total,
            "win_rate": f"{win_rate:.1%}",
            "avg_confidence": f"{sum(trade_log.get('confidence', 0) for trade_log in logs) / total:.2f}" if total > 0 else "0.0",
            "current_prompt": current_prompt,
            "recent_trades": logs[-10:],
            "best_trades": sorted(wins, key=lambda trade_log: trade_log.get("outcome", {}).get("pnl", 0), reverse=True)[:5],
            "worst_trades": sorted(losses, key=lambda trade_log: trade_log.get("outcome", {}).get("pnl", 0))[:5],
        }
        return await self._call_and_parse_json(summary, current_prompt, timeout_ms=120000)

    async def _call_and_parse_json(self, ensemble_output: dict, prompt: str, timeout_ms: int) -> dict:
        api_key = self._resolve_api_key()
        if not api_key:
            return {"analysis": "NVIDIA_API_KEY not set", "new_system_prompt": prompt}
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._call_llm_sync, ensemble_output, prompt, timeout_ms, api_key),
                timeout=timeout_ms / 1000 + THREAD_GRACE_SECONDS,
            )
            decoder = json.JSONDecoder()
            raw = result.explanation
            start = raw.find('{')
            if start != -1:
                raw = raw[start:]
            data, _ = decoder.raw_decode(raw)
            return data if isinstance(data, dict) else {}
        except (TimeoutError, json.JSONDecodeError, Exception):
            return {"analysis": "LLM call failed", "new_system_prompt": prompt}
