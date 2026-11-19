# gta6-trophy-forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/RizkiMiftahul/gta6-trophy-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/RizkiMiftahul/gta6-trophy-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Forecasts the earn rate of every GTA VI PlayStation 5 trophy on Exophase at a future target time, as five quantiles per trophy. V3 collapses duplicate reads into refresh states and weights each state by player growth, duration, and recency, including in the fits pooled by trophy tier. The player forecast selects the better fit between exponential growth and a power law that slows over time. Trophy forecasts adjust earner growth toward the median of their elasticity tercile to account for player progress. Quantile spread includes observed refresh jumps, fit residuals, and the forecast horizon. The model also adjusts for stale snapshots and guards rates near 100%.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---
<sub>Entered on [make.fun](https://make.fun) in the "Forecast how many GTA VI players earn each trophy in week one" bounty.</sub>
