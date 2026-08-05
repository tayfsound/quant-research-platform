# TradingView Webhook Kurulumu (Faz 185)

TradingView, Binance gibi "API key alıp veri çek" modeliyle çalışmıyor —
Pine Script alarmları, tetiklendiğinde bizim belirlediğimiz bir URL'e HTTP
POST gönderiyor. Bu doküman, o alarmı sistemimize bağlamanın adımlarını
anlatıyor.

## 1. Alıcı endpoint

`POST /api/v1/webhooks/tradingview` — kimlik doğrulaması gerektirmiyor
(TradingView'ın bize Authorization header'ı gönderme imkanı yok). Bunun
yerine, isterseniz `.env`'de `TRADINGVIEW_WEBHOOK_SECRET` set edip alert
mesajının JSON gövdesine `"secret"` alanı ekleyerek doğrulama
zorunlu kılabilirsiniz (boşsa doğrulama atlanır — dev modu).

Kayıtlar `external_signals` tablosuna yazılır, `GET
/api/v1/webhooks/tradingview/recent` ile (giriş yapmış kullanıcılar için)
görüntülenebilir.

## 2. Pine Script — örnek alert scripti

TradingView'da bir chart açın → Pine Editor → aşağıdaki scripti yapıştırıp
"Add to Chart" deyin, sonra grafikteki alarm zili ikonuna tıklayıp bu
script'in ürettiği koşulla bir alarm oluşturun:

```pinescript
//@version=5
indicator("Cognitive Core Sinyali", overlay=true)

ema50 = ta.ema(close, 50)
ema200 = ta.ema(close, 200)
rsiValue = ta.rsi(close, 14)
volSpike = volume > ta.sma(volume, 20) * 1.5

bullish = ema50 > ema200 and rsiValue < 30 and volSpike
bearish = ema50 < ema200 and rsiValue > 70 and volSpike

if bullish
    alert('{"symbol":"' + syminfo.ticker + '","signal":"LONG","rsi":' + str.tostring(rsiValue, "#.##") + ',"ema_cross":"bullish","volume_ratio":' + str.tostring(volume / ta.sma(volume, 20), "#.##") + '}', alert.freq_once_per_bar_close)

if bearish
    alert('{"symbol":"' + syminfo.ticker + '","signal":"SHORT","rsi":' + str.tostring(rsiValue, "#.##") + ',"ema_cross":"bearish","volume_ratio":' + str.tostring(volume / ta.sma(volume, 20), "#.##") + '}', alert.freq_once_per_bar_close)
```

Secret kullanacaksanız, JSON'a `"secret":"..."` alanını ekleyin (yukarıdaki
string'in içine, `"symbol"` alanının yanına).

## 3. Alarm ayarları (TradingView arayüzünde)

1. Grafikte sağ tık → "Add Alert" (veya zil ikonu).
2. Condition: yukarıdaki indikatör, "Cognitive Core Sinyali".
3. "Webhook URL" kutusuna: `https://<sizin-erişilebilir-adresiniz>/api/v1/webhooks/tradingview`
   — **local geliştirme ortamında bu `localhost` TradingView'ın sunucularından
   erişilemez.** TradingView'ın sunucuları dışarıdan sizin makinenize POST
   atabilmeli — bunun için ya (a) API'yi gerçek bir domain/IP'ye deploy
   etmeniz (K8s manifestleri zaten hazır), ya da (b) geliştirme sırasında
   `ngrok`/`cloudflared` gibi bir tünel aracıyla local sunucunuzu geçici bir
   public URL'e açmanız gerekiyor.
4. Message kutusuna dokunmayın — Pine Script'teki `alert(...)` çağrısı zaten
   mesajı üretiyor.

## 4. Gerçek doğrulama

`tests/test_tradingview_webhook.py` — gerçek HTTP POST → `external_signals`
tablosuna gerçek satır → gerçek `GET /recent` ile geri okuma; yanlış/doğru
secret senaryoları; `symbol` zorunluluğu; `secret` alanının asla
saklanmadığı/geri döndürülmediği ayrıca kanıtlı.

## Bilinçli olarak yapılmayan (sonraki adım)

Gelen sinyal şu an sadece saklanıyor — `TechnicalAgent`'ın kararına henüz
otomatik olarak "ikinci görüş" olarak karışmıyor. Bu, `ContextAdapter.
to_technical()`'a `external_signals`'tan en son sinyali okuyup ekleyen ayrı,
küçük bir adım — TradingView tarafı gerçek trafikle doğrulandıktan sonra
yapılması daha sağlıklı.
