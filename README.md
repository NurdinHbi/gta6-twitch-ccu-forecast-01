# gta6-twitch-ccu-forecast-01

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/NurdinHbi/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/NurdinHbi/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts GTA VI's launch-day Twitch viewers hour by hour, as five quantiles
(5/25/50/75/95%) for each of hours 2–24 of release day (UTC), from the
first hour's print and the release-day curves of past big game launches.

Method: per forecast hour, a similarity-weighted least-squares line of the
log-ratio to the hour-1 print on the log hour-1 print, fitted over the
comparable launches in the case (hour-1 print ≥ 10,000), with the spread
taken from the regression residuals. The log-ratio is strongly
scale-dependent (r = −0.94 for the evening peak): a small hour-1 print means
the audience sits mostly in regions unlocking later in UTC, so the day ramps
hard into the evening; a huge hour-1 print means the launch is already
global at midnight UTC. Practice (four past launches, scored locally against
SullyGnome averages): mean pinball loss 0.2049 vs the house persistence
baseline's 0.3871.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` case in the input directory and writes one
`<id>.out` forecast per case. Python 3.13, standard library only, no
network, deterministic.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
