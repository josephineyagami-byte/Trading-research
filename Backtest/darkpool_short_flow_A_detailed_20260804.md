# Darkpool + Short Volume + Flow Insights

- Universe: `24` A-prefix tickers with prior successful trades/signals
- API: `http://74.208.124.247:8000`
- Price window: `2026-01-01` to `2026-08-04`
- Flow window: `2026-07-01` to `2026-08-04`
- Short-volume window: `2026-06-01` to `2026-08-04`
- Darkpool lookback: `365` days; darkpool is delayed, so it is used as context, not as a same-day timing signal.

## Takeaways

- Long candidates: `3`; short candidates: `2`; watch/neutral: `19`.
- `short_volume` is missing for `24` / `24` tickers in this A-prefix run, so current insights rely mostly on flow + price + delayed darkpool.
- Treat this as an insight-layer smoke test. It is not a production trading recommendation.

## Long Candidates

| Ticker | Stance | Score | Conf | 5D Ret | 5D Flow/ADV | Dark 4W Ratio | V4 Signal | Reason | Risk/Data Gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ABG | Long candidate | 2.40 | 71.90 | 0.59% | 7.68% | 1.36 | strong_accumulation | 原 v4 信号为 strong_accumulation; 近 5 日大单净流入为正; 5D/20D 价格动量同向向上; 近 5 日成交量高于 20 日均量 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ABNB | Long candidate | 2.40 | 72.00 | 2.57% | 3.45% | 0.79 | strong_accumulation | 原 v4 信号为 strong_accumulation; 近 5 日大单净流入为正; 5D/20D 价格动量同向向上 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ACCO | Long candidate | 2.40 | 70.40 | 4.60% | 4.34% | 1.08 | strong_accumulation | 原 v4 信号为 strong_accumulation; 近 5 日大单净流入为正; 5D/20D 价格动量同向向上 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |

## Short Candidates

| Ticker | Stance | Score | Conf | 5D Ret | 5D Flow/ADV | Dark 4W Ratio | V4 Signal | Reason | Risk/Data Gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACGL | Short candidate | -3.20 | 72.00 | -2.66% | -10.72% | 0.73 | strong_distribution | 原 v4 信号为 strong_distribution; 近 5 日大单净流出; 5D/20D 价格动量同向向下 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ABAT | Short candidate | -2.40 | 70.10 | -5.73% | -1.98% | 0.36 | strong_distribution | 原 v4 信号为 strong_distribution; 近 5 日大单净流出; 5D/20D 价格动量同向向下; 历史 signal-driven backtest 为正 | 缺少 short_volume，暂不能判断 short pressure/squeeze |

## Watch / Neutral

| Ticker | Stance | Score | Conf | 5D Ret | 5D Flow/ADV | Dark 4W Ratio | V4 Signal | Reason | Risk/Data Gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ABBV | Watch / neutral | -1.90 | 63.80 | -4.60% | -10.14% | 1.02 | distribution | 原 v4 信号为 distribution; 近 5 日大单净流出; 5D/20D 价格动量同向向下; 历史 signal-driven backtest 为正 | 缺少 short_volume，暂不能判断 short pressure/squeeze |
| ACH | Watch / neutral | 1.80 | 64.00 | 5.90% | 4.44% | 0.60 | strong_accumulation | 原 v4 信号为 strong_accumulation; 近 5 日大单净流入为正; 短期反弹但中期趋势仍弱 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ACEL | Watch / neutral | -1.80 | 71.70 | -2.91% | 7.39% | 1.50 | strong_distribution | 原 v4 信号为 strong_distribution; 近 5 日大单净流入为正; 5D/20D 价格动量同向向下; 暗池成交较近 4 周均值放大，配合空头信号 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ABM | Watch / neutral | 1.60 | 55.30 | 0.58% | 2.12% | 1.28 | neutral | 近 5 日大单净流入为正; 5D/20D 价格动量同向向上 | 缺少 short_volume，暂不能判断 short pressure/squeeze |
| ABT | Watch / neutral | -1.50 | 57.20 | 2.52% | -17.81% | 0.98 | distribution | 原 v4 信号为 distribution; 近 5 日大单净流出; 5D/20D 价格动量同向向上 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ABSI | Watch / neutral | -1.40 | 63.00 | 4.89% | -0.26% | 3.46 | strong_distribution | 原 v4 信号为 strong_distribution; 短期反弹但中期趋势仍弱; 暗池成交较近 4 周均值放大，配合空头信号; 历史 signal-driven backtest 为正 | 缺少 short_volume，暂不能判断 short pressure/squeeze |
| A | Watch / neutral | 1.20 | 50.90 | 1.39% | 7.20% | 0.96 | neutral | 近 5 日大单净流入为正; 5D/20D 价格动量同向向上 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ACFN | Watch / neutral | -1.10 | 52.30 | -7.61% | 0.00% | 1.12 | distribution | 原 v4 信号为 distribution; 短期回撤但中期趋势仍强 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| AAP | Watch / neutral | 0.70 | 48.90 | -3.55% | 3.26% | 1.03 | accumulation | 原 v4 信号为 accumulation; 近 5 日大单净流入为正; 5D/20D 价格动量同向向下 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| AAOI | Watch / neutral | -0.70 | 48.10 | 12.67% | -5.59% | 0.63 | accumulation | 原 v4 信号为 accumulation; 近 5 日大单净流出; 短期反弹但中期趋势仍弱 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ACHC | Watch / neutral | 0.60 | 43.40 | -5.88% | 10.26% | 2.67 | neutral | 近 5 日大单净流入为正; 5D/20D 价格动量同向向下; 暗池成交较近 4 周均值放大，配合多头信号 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ACDC | Watch / neutral | -0.60 | 54.30 | 2.49% | 6.49% | 1.08 | strong_distribution | 原 v4 信号为 strong_distribution; 近 5 日大单净流入为正; 短期反弹但中期趋势仍弱 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |

## Backtest Validation

Validation horizon: `5 bar`. IC / event study use this horizon; signal-driven and walk-forward are pulled from each ticker's saved backtest report.

| Ticker | Validation | IC | IC p | Event Long | Event Short | SDB Cum | SDB Sharpe | WF Cum | WF Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACGL | inconclusive historical validation | 0.0817 | 0.3388 | 1.390% | -0.466% | -9.16% | -14.12 | 3.02% | 1.62 |
| ABG | inconclusive historical validation | -0.0576 | 0.5003 | 0.629% | -1.941% | -14.41% | -9.91 | 2.75% | 1.31 |
| ABNB | negative historical validation | -0.0567 | 0.5076 | 0.120% | -1.666% | -9.95% | -10.74 | -14.00% | -8.39 |
| ACCO | inconclusive historical validation | -0.0903 | 0.2903 | 2.281% | -1.861% | -27.38% | -13.10 | 19.96% | 3.64 |
| ABAT | supportive historical validation | 0.0621 | 0.4679 | 0.812% | 2.175% | 59.19% | 7.63 | 22.59% | 3.75 |
| ABBV | supportive historical validation | 0.0113 | 0.8949 | 1.524% | -1.184% | 5.35% | 4.40 | 8.90% | 3.05 |
| ACH | inconclusive historical validation | -0.1075 | 0.2079 | -3.047% | -2.746% | -17.04% | -7.84 | 4.71% | 1.46 |
| ACEL | negative historical validation | -0.0859 | 0.3147 | -0.562% | -1.409% | -10.21% | -8.05 | -9.74% | -3.08 |
| ABM | inconclusive historical validation | -0.1458 | 0.0868 | 0.209% | -1.525% | -0.72% | 0.12 | 2.55% | 1.09 |
| ABT | mixed but positive historical validation | 0.2159 | 0.0107 | 1.096% | 0.590% | -2.95% | -0.50 | 14.94% | 4.15 |
| ABSI | supportive historical validation | 0.1575 | 0.0640 | 8.119% | -1.180% | 23.11% | 5.11 | 26.27% | 4.09 |
| A | negative historical validation | -0.1833 | 0.0307 | -0.407% | -1.673% | -8.28% | -8.99 | -18.28% | -5.57 |
| ACFN | inconclusive historical validation | 0.0192 | 0.8225 | -0.213% | -0.292% | -11.72% | -2.87 | 5.95% | 1.70 |
| AAP | negative historical validation | -0.1511 | 0.0757 | -1.601% | -1.941% | -14.16% | -7.57 | -9.18% | -1.68 |
| AAOI | inconclusive historical validation | -0.0043 | 0.9602 | -6.336% | -1.282% | -46.41% | -7.31 | 38.53% | 5.14 |
| ACHC | mixed but weak historical validation | -0.1480 | 0.0820 | -0.053% | -5.302% | -23.69% | -11.44 | 16.69% | 3.47 |
| ACDC | negative historical validation | 0.1105 | 0.1955 | 0.825% | 2.966% | -22.83% | -8.17 | -29.39% | -3.24 |
| ACA | negative historical validation | -0.1173 | 0.1689 | 1.336% | -3.215% | -11.87% | -9.18 | -16.07% | -4.08 |
| AAON | inconclusive historical validation | 0.0479 | 0.5756 | -0.959% | 0.070% | 14.18% | 4.37 | -11.47% | -1.57 |
| AAL | negative historical validation | 0.0502 | 0.5577 | 2.836% | -1.820% | -19.92% | -30.75 | -23.69% | -8.60 |
| ACCS | inconclusive historical validation | 0.0761 | 0.3730 | 0.070% | 1.664% | -5.86% | -0.74 | 12.87% | 5.24 |
| ACHR | negative historical validation | -0.1415 | 0.0966 | -3.440% | -0.860% | -40.25% | -13.84 | -18.80% | -2.82 |
| AA | supportive historical validation | 0.2148 | 0.0111 | -1.263% | 4.690% | 18.35% | 5.27 | 79.14% | 13.22 |
| AAPL | supportive historical validation | 0.1834 | 0.0307 | 1.990% | -1.077% | 13.37% | 9.39 | 9.79% | 3.03 |

## Detailed Mode

This section is the PM-facing explanation layer. It separates current timing evidence (price/main-flow/short volume) from delayed institutional context (darkpool).

| Ticker | Price | Flow | Short Volume | Darkpool | Combined Regime |
| --- | --- | --- | --- | --- | --- |
| ACGL | bearish price confirmation | strong institutional net selling | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ABG | bullish price confirmation, volume expansion | strong institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ABNB | bullish price confirmation | institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ACCO | bullish price confirmation | strong institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ABAT | bearish price confirmation | strong institutional net selling | short_volume missing | below-normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ABBV | bearish price confirmation | strong institutional net selling | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ACH | short-term rebound inside weak 20D trend | strong institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ACEL | bearish price confirmation | strong institutional net buying | short_volume missing | elevated delayed darkpool activity | conflicted absorption watch: delayed darkpool elevated, current flow buying into weak price |
| ABM | bullish price confirmation | institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ABT | bullish price confirmation | strong institutional net selling | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ABSI | short-term rebound inside weak 20D trend, volume contraction | balanced institutional flow | short_volume missing | very elevated delayed darkpool activity | delayed darkpool activity elevated, but short_volume is unavailable for pressure/squeeze read |
| A | bullish price confirmation | strong institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ACFN | short-term pullback inside strong 20D trend | balanced institutional flow | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| AAP | bearish price confirmation, volume contraction | strong institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| AAOI | short-term rebound inside weak 20D trend | strong institutional net selling | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ACHC | bearish price confirmation | strong institutional net buying | short_volume missing | very elevated delayed darkpool activity | conflicted absorption watch: delayed darkpool elevated, current flow buying into weak price |
| ACDC | short-term rebound inside weak 20D trend | strong institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ACA | short-term rebound inside weak 20D trend | institutional net buying | short_volume missing | very elevated delayed darkpool activity | delayed darkpool activity elevated, but short_volume is unavailable for pressure/squeeze read |
| AAON | bearish price confirmation | strong institutional net buying | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| AAL | short-term rebound inside weak 20D trend, volume contraction | balanced institutional flow | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ACCS | bearish price confirmation | balanced institutional flow | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| ACHR | bearish price confirmation | balanced institutional flow | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| AA | short-term rebound inside weak 20D trend | strong institutional net selling | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |
| AAPL | bearish price confirmation, volume expansion | institutional net selling | short_volume missing | normal delayed darkpool activity | short_volume unavailable; use darkpool only as delayed context |

### ACGL - Short candidate

ACGL 目前偏空，核心是当前大单流和价格行为同向走弱。 价格: bearish price confirmation，5D=-2.66%，20D=-0.68%。 Flow: strong institutional net selling，5D Flow/ADV=-10.72%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.73；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=0.0817 (p=0.3388); Event long=1.390% / 68.0% (17/25), short=-0.466% / 30.6% (11/36); Signal-driven cum=-9.16%, Sharpe=-14.12; Walk-forward cum=3.02%, Sharpe=1.62; inconclusive historical validation.

Next check: 下一步看 flow 是否继续净流出、价格是否跌破/维持弱趋势；若 short_volume 后续补齐且 short pressure 上升，可升级为空头压力确认。

### ABG - Long candidate

ABG 目前偏多，核心是当前大单流和价格行为同向确认。 价格: bullish price confirmation, volume expansion，5D=0.59%，20D=9.62%。 Flow: strong institutional net buying，5D Flow/ADV=7.68%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.36；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=-0.0576 (p=0.5003); Event long=0.629% / 54.5% (18/33), short=-1.941% / 32.0% (8/25); Signal-driven cum=-14.41%, Sharpe=-9.91; Walk-forward cum=2.75%, Sharpe=1.31; inconclusive historical validation.

Next check: 下一步看 flow 是否继续为正、价格是否守住短期趋势；若 short_volume 后续补齐且 short pressure 高但价格不跌，可升级为 squeeze/absorption insight。

### ABNB - Long candidate

ABNB 目前偏多，核心是当前大单流和价格行为同向确认。 价格: bullish price confirmation，5D=2.57%，20D=2.03%。 Flow: institutional net buying，5D Flow/ADV=3.45%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.79；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: negative historical validation。

Backtest validation: 5 bar IC=-0.0567 (p=0.5076); Event long=0.120% / 45.8% (11/24), short=-1.666% / 48.1% (13/27); Signal-driven cum=-9.95%, Sharpe=-10.74; Walk-forward cum=-14.00%, Sharpe=-8.39; negative historical validation.

Next check: 下一步看 flow 是否继续为正、价格是否守住短期趋势；若 short_volume 后续补齐且 short pressure 高但价格不跌，可升级为 squeeze/absorption insight。

### ACCO - Long candidate

ACCO 目前偏多，核心是当前大单流和价格行为同向确认。 价格: bullish price confirmation，5D=4.60%，20D=5.37%。 Flow: strong institutional net buying，5D Flow/ADV=4.34%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.08；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=-0.0903 (p=0.2903); Event long=2.281% / 50.0% (15/30), short=-1.861% / 37.5% (18/48); Signal-driven cum=-27.38%, Sharpe=-13.10; Walk-forward cum=19.96%, Sharpe=3.64; inconclusive historical validation.

Next check: 下一步看 flow 是否继续为正、价格是否守住短期趋势；若 short_volume 后续补齐且 short pressure 高但价格不跌，可升级为 squeeze/absorption insight。

### ABAT - Short candidate

ABAT 目前偏空，核心是当前大单流和价格行为同向走弱。 价格: bearish price confirmation，5D=-5.73%，20D=-25.44%。 Flow: strong institutional net selling，5D Flow/ADV=-1.98%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: below-normal delayed darkpool activity，Dark 4W Ratio=0.36；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: supportive historical validation。

Backtest validation: 5 bar IC=0.0621 (p=0.4679); Event long=0.812% / 45.5% (10/22), short=2.175% / 60.0% (48/80); Signal-driven cum=59.19%, Sharpe=7.63; Walk-forward cum=22.59%, Sharpe=3.75; supportive historical validation.

Next check: 下一步看 flow 是否继续净流出、价格是否跌破/维持弱趋势；若 short_volume 后续补齐且 short pressure 上升，可升级为空头压力确认。

### ABBV - Watch / neutral

ABBV 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-4.60%，20D=-3.79%。 Flow: strong institutional net selling，5D Flow/ADV=-10.14%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.02；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: supportive historical validation。

Backtest validation: 5 bar IC=0.0113 (p=0.8949); Event long=1.524% / 68.6% (24/35), short=-1.184% / 28.0% (7/25); Signal-driven cum=5.35%, Sharpe=4.40; Walk-forward cum=8.90%, Sharpe=3.05; supportive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACH - Watch / neutral

ACH 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=5.90%，20D=-6.32%。 Flow: strong institutional net buying，5D Flow/ADV=4.44%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.60；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=-0.1075 (p=0.2079); Event long=-3.047% / 34.8% (8/23), short=-2.746% / 36.7% (11/30); Signal-driven cum=-17.04%, Sharpe=-7.84; Walk-forward cum=4.71%, Sharpe=1.46; inconclusive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACEL - Watch / neutral

ACEL 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-2.91%，20D=-2.83%。 Flow: strong institutional net buying，5D Flow/ADV=7.39%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: elevated delayed darkpool activity，Dark 4W Ratio=1.50；该数据有发布延迟，只作为机构背景。 联合判断: conflicted absorption watch: delayed darkpool elevated, current flow buying into weak price。 Backtest validation: negative historical validation。

Backtest validation: 5 bar IC=-0.0859 (p=0.3147); Event long=-0.562% / 50.0% (14/28), short=-1.409% / 37.9% (11/29); Signal-driven cum=-10.21%, Sharpe=-8.05; Walk-forward cum=-9.74%, Sharpe=-3.08; negative historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ABM - Watch / neutral

ABM 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bullish price confirmation，5D=0.58%，20D=9.77%。 Flow: institutional net buying，5D Flow/ADV=2.12%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.28；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=-0.1458 (p=0.0868); Event long=0.209% / 49.2% (29/59), short=-1.525% / 17.9% (5/28); Signal-driven cum=-0.72%, Sharpe=0.12; Walk-forward cum=2.55%, Sharpe=1.09; inconclusive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ABT - Watch / neutral

ABT 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bullish price confirmation，5D=2.52%，20D=12.02%。 Flow: strong institutional net selling，5D Flow/ADV=-17.81%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.98；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: mixed but positive historical validation。

Backtest validation: 5 bar IC=0.2159 (p=0.0107); Event long=1.096% / 63.6% (21/33), short=0.590% / 69.4% (25/36); Signal-driven cum=-2.95%, Sharpe=-0.50; Walk-forward cum=14.94%, Sharpe=4.15; mixed but positive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ABSI - Watch / neutral

ABSI 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend, volume contraction，5D=4.89%，20D=-31.28%。 Flow: balanced institutional flow，5D Flow/ADV=-0.26%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: very elevated delayed darkpool activity，Dark 4W Ratio=3.46；该数据有发布延迟，只作为机构背景。 联合判断: delayed darkpool activity elevated, but short_volume is unavailable for pressure/squeeze read。 Backtest validation: supportive historical validation。

Backtest validation: 5 bar IC=0.1575 (p=0.0640); Event long=8.119% / 64.9% (24/37), short=-1.180% / 61.9% (13/21); Signal-driven cum=23.11%, Sharpe=5.11; Walk-forward cum=26.27%, Sharpe=4.09; supportive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### A - Watch / neutral

A 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bullish price confirmation，5D=1.39%，20D=7.04%。 Flow: strong institutional net buying，5D Flow/ADV=7.20%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.96；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: negative historical validation。

Backtest validation: 5 bar IC=-0.1833 (p=0.0307); Event long=-0.407% / 40.7% (11/27), short=-1.673% / 43.8% (14/32); Signal-driven cum=-8.28%, Sharpe=-8.99; Walk-forward cum=-18.28%, Sharpe=-5.57; negative historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACFN - Watch / neutral

ACFN 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term pullback inside strong 20D trend，5D=-7.61%，20D=10.10%。 Flow: balanced institutional flow，5D Flow/ADV=0.00%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.12；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=0.0192 (p=0.8225); Event long=-0.213% / 45.0% (18/40), short=-0.292% / 57.9% (11/19); Signal-driven cum=-11.72%, Sharpe=-2.87; Walk-forward cum=5.95%, Sharpe=1.70; inconclusive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAP - Watch / neutral

AAP 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation, volume contraction，5D=-3.55%，20D=-1.15%。 Flow: strong institutional net buying，5D Flow/ADV=3.26%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.03；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: negative historical validation。

Backtest validation: 5 bar IC=-0.1511 (p=0.0757); Event long=-1.601% / 50.0% (16/32), short=-1.941% / 41.4% (12/29); Signal-driven cum=-14.16%, Sharpe=-7.57; Walk-forward cum=-9.18%, Sharpe=-1.68; negative historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAOI - Watch / neutral

AAOI 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=12.67%，20D=-10.66%。 Flow: strong institutional net selling，5D Flow/ADV=-5.59%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.63；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=-0.0043 (p=0.9602); Event long=-6.336% / 33.3% (5/15), short=-1.282% / 48.6% (18/37); Signal-driven cum=-46.41%, Sharpe=-7.31; Walk-forward cum=38.53%, Sharpe=5.14; inconclusive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACHC - Watch / neutral

ACHC 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-5.88%，20D=-1.61%。 Flow: strong institutional net buying，5D Flow/ADV=10.26%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: very elevated delayed darkpool activity，Dark 4W Ratio=2.67；该数据有发布延迟，只作为机构背景。 联合判断: conflicted absorption watch: delayed darkpool elevated, current flow buying into weak price。 Backtest validation: mixed but weak historical validation。

Backtest validation: 5 bar IC=-0.1480 (p=0.0820); Event long=-0.053% / 47.1% (16/34), short=-5.302% / 29.2% (14/48); Signal-driven cum=-23.69%, Sharpe=-11.44; Walk-forward cum=16.69%, Sharpe=3.47; mixed but weak historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACDC - Watch / neutral

ACDC 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=2.49%，20D=-12.37%。 Flow: strong institutional net buying，5D Flow/ADV=6.49%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.08；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: negative historical validation。

Backtest validation: 5 bar IC=0.1105 (p=0.1955); Event long=0.825% / 55.1% (26/49), short=2.966% / 70.8% (17/24); Signal-driven cum=-22.83%, Sharpe=-8.17; Walk-forward cum=-29.39%, Sharpe=-3.24; negative historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACA - Watch / neutral

ACA 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=0.01%，20D=-0.04%。 Flow: institutional net buying，5D Flow/ADV=0.95%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: very elevated delayed darkpool activity，Dark 4W Ratio=14.48；该数据有发布延迟，只作为机构背景。 联合判断: delayed darkpool activity elevated, but short_volume is unavailable for pressure/squeeze read。 Backtest validation: negative historical validation。

Backtest validation: 5 bar IC=-0.1173 (p=0.1689); Event long=1.336% / 45.5% (15/33), short=-3.215% / 24.0% (6/25); Signal-driven cum=-11.87%, Sharpe=-9.18; Walk-forward cum=-16.07%, Sharpe=-4.08; negative historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAON - Watch / neutral

AAON 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-8.37%，20D=-15.35%。 Flow: strong institutional net buying，5D Flow/ADV=12.30%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.10；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=0.0479 (p=0.5756); Event long=-0.959% / 44.8% (13/29), short=0.070% / 54.5% (18/33); Signal-driven cum=14.18%, Sharpe=4.37; Walk-forward cum=-11.47%, Sharpe=-1.57; inconclusive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAL - Watch / neutral

AAL 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend, volume contraction，5D=7.29%，20D=-9.63%。 Flow: balanced institutional flow，5D Flow/ADV=-0.35%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.95；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: negative historical validation。

Backtest validation: 5 bar IC=0.0502 (p=0.5577); Event long=2.836% / 58.1% (18/31), short=-1.820% / 53.8% (14/26); Signal-driven cum=-19.92%, Sharpe=-30.75; Walk-forward cum=-23.69%, Sharpe=-8.60; negative historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACCS - Watch / neutral

ACCS 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-3.35%，20D=-5.55%。 Flow: balanced institutional flow，5D Flow/ADV=0.00%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.06；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: inconclusive historical validation。

Backtest validation: 5 bar IC=0.0761 (p=0.3730); Event long=0.070% / 45.8% (11/24), short=1.664% / 57.7% (14/26); Signal-driven cum=-5.86%, Sharpe=-0.74; Walk-forward cum=12.87%, Sharpe=5.24; inconclusive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACHR - Watch / neutral

ACHR 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-2.22%，20D=-9.87%。 Flow: balanced institutional flow，5D Flow/ADV=-0.42%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.76；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: negative historical validation。

Backtest validation: 5 bar IC=-0.1415 (p=0.0966); Event long=-3.440% / 36.7% (11/30), short=-0.860% / 51.7% (15/29); Signal-driven cum=-40.25%, Sharpe=-13.84; Walk-forward cum=-18.80%, Sharpe=-2.82; negative historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AA - Watch / neutral

AA 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=1.72%，20D=-10.09%。 Flow: strong institutional net selling，5D Flow/ADV=-4.91%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.09；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: supportive historical validation。

Backtest validation: 5 bar IC=0.2148 (p=0.0111); Event long=-1.263% / 33.3% (6/18), short=4.690% / 66.7% (26/39); Signal-driven cum=18.35%, Sharpe=5.27; Walk-forward cum=79.14%, Sharpe=13.22; supportive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAPL - Watch / neutral

AAPL 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation, volume expansion，5D=-9.94%，20D=-2.96%。 Flow: institutional net selling，5D Flow/ADV=-4.17%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.68；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。 Backtest validation: supportive historical validation。

Backtest validation: 5 bar IC=0.1834 (p=0.0307); Event long=1.990% / 75.6% (31/41), short=-1.077% / 45.8% (11/24); Signal-driven cum=13.37%, Sharpe=9.39; Walk-forward cum=9.79%, Sharpe=3.03; supportive historical validation.

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

## Data Gaps

- A-prefix short volume currently has no rows through the public API for this run. We should not claim squeeze/short-pressure insights on these names yet.
- Darkpool coverage is available for the A-prefix sample, but latest weeks are delayed by FINRA publication lag.
- This report uses existing v4 signal/backtest summary as a validation input, not as a retrained model.
