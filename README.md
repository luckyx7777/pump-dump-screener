# Pump & Dump Early Detection Screener

Профессиональная система раннего обнаружения пампов и дампов на Binance и Bybit.

Основана на методологии из документа:
«Прогностическое моделирование высокочастотных импульсов ликвидности» (микроструктура L2, WOBI, MLOFI, CVD, Leverage Velocity, Iceberg, Spoofing detection и т.д.).

## Архитектура (оптимизирована под Railway)

- **Collector** — асинхронные WebSocket-подписки на Binance + Bybit (depth@100ms, aggTrade, forceOrder, tickers и т.д.)
- **Feature Engine** — real-time расчёт всех ключевых метрик из документа (Weighted OBI, CVD Taker Aggression, θ_LV, Iceberg Estimator, Spoof detector и др.)
- **Scorer** — динамическая Z-score нормализация + многофакторный скоринг + логические гейты (фильтры ложных срабатываний)
- **Telegram Bot** — алерты + команды /screen, /status, /symbols
- **Storage** — Redis (горячие данные + кэш) + PostgreSQL (история сигналов и фич)

## Почему Python, а не Rust?

Документ предлагает Rust + Tokio для ультра-низкой латентности.  
Для **скринера с алертами** (горизонт 5 сек — 15 мин) Python даёт:
- В 5–10× быстрее разработку и поддержку
- Отличную интеграцию с Telegram (aiogram)
- pandas / polars / numpy для фич
- Простой деплой на Railway

Для настоящего HFT-execution (суб-10мс) — переходи на Rust позже.

## Быстрый старт (локально)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Запусти Redis и Postgres (docker-compose)
docker-compose up -d

# Запусти приложение
python -m app.main
```

## Деплой на Railway (paid)

1. Создай новый проект на Railway
2. Подключи GitHub-репозиторий
3. Добавь сервисы:
   - **PostgreSQL**
   - **Redis**
4. В Variables добавь:
   - `TELEGRAM_BOT_TOKEN=...`
   - `TELEGRAM_ALERT_CHAT_ID=123456789`   ← ID чата/канала для алертов
   - `BINANCE_API_KEY=...` (опционально)
   - `BYBIT_API_KEY=...`
5. Railway автоматически соберёт Docker-образ.
6. Масштабируй CPU/Memory под количество символов (рекомендуется 8 vCPU / 8GB+ для 100+ пар).

## Поддерживаемые метрики (реализованы / в roadmap)

- [x] Weighted Order Book Imbalance (WOBI)
- [x] CVD Taker Aggression
- [ ] Multi-Level Order Flow Imbalance (MLOFI) — частично
- [x] Leverage Velocity (θ_LV)
- [x] Iceberg Volume Estimator (базовый)
- [x] Spoofing Detector (Ψ_spoof)
- [ ] TWAP/VWAP pattern detection via ACF
- [ ] Cross-exchange basis (Binance Spot vs Bybit Perp)
- [ ] Интеграция Glassnode / Coinglass / Santiment (заготовки есть)

## Следующие шаги (что я могу добавить сразу)

- Полная реализация MLOFI + HMM regime detection
- Подключение Coinglass liquidation heatmap
- Сохранение всех фич в TimescaleDB
- Веб-дашборд (FastAPI + HTMX / Streamlit)
- Backtesting engine на исторических данных (Tardis.dev или CSV)

Напиши в чат, какую часть нужно доработать в первую очередь.