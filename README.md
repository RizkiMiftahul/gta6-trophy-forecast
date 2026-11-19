# gta6-trophy-forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/RizkiMiftahul/gta6-trophy-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/RizkiMiftahul/gta6-trophy-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Forecasts the earn rate of every GTA VI PlayStation 5 trophy on Exophase at a future target time, as five quantiles per trophy. The model compresses unchanged reads into refresh states, then forecasts tracked players and trophy earners separately using recency-weighted fits pooled by trophy tier. A stale single-state snapshot receives a refresh-dilution adjustment, and quantile spread reflects earner-fit residuals and the forecast horizon.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---
<sub>Entered on [make.fun](https://make.fun) in the "Forecast how many GTA VI players earn each trophy in week one" bounty.</sub>
