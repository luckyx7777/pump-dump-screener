# Pump & Dump Early Detection Screener

Профессиональная система раннего обнаружения пампов и дампов на Binance и Bybit.

**v0.4** — полная реализация методологии из твоего документа + дополнительные производственные улучшения.

## Что реализовано

- WebSocket Collectors (Binance + Bybit) с правильной реконструкцией стакана
- Feature Engine: WOBI, улучшенный MLOFI, CVD, Leverage Velocity, Iceberg Estimator, Spoofing Detector, Cross-Exchange Basis
- HMM Regime Detection для динамических весов
- Dynamic Scorer с гейтами
- PostgreSQL сохранение сигналов
- Telegram Bot с реальными алертами (c метриками и объяснениями)
- Docker + Railway-ready

## Быстрый старт

```bash
git clone https://github.com/luckyx7777/pump-dump-screener.git
cd pump-dump-screener
cp .env.example .env
# заполни .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker-compose up -d
python -m app.main
```