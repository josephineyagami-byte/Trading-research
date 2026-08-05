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
| ABT | Watch / neutral | -1.50 | 57.20 | 2.52% | -17.82% | 0.98 | distribution | 原 v4 信号为 distribution; 近 5 日大单净流出; 5D/20D 价格动量同向向上 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ABSI | Watch / neutral | -1.40 | 63.00 | 4.89% | -0.26% | 3.46 | strong_distribution | 原 v4 信号为 strong_distribution; 短期反弹但中期趋势仍弱; 暗池成交较近 4 周均值放大，配合空头信号; 历史 signal-driven backtest 为正 | 缺少 short_volume，暂不能判断 short pressure/squeeze |
| A | Watch / neutral | 1.20 | 50.90 | 1.39% | 7.20% | 0.96 | neutral | 近 5 日大单净流入为正; 5D/20D 价格动量同向向上 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ACFN | Watch / neutral | -1.10 | 52.30 | -7.61% | 0.00% | 1.12 | distribution | 原 v4 信号为 distribution; 短期回撤但中期趋势仍强 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| AAP | Watch / neutral | 0.70 | 48.90 | -3.55% | 3.28% | 1.03 | accumulation | 原 v4 信号为 accumulation; 近 5 日大单净流入为正; 5D/20D 价格动量同向向下 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| AAOI | Watch / neutral | -0.70 | 48.10 | 12.67% | -5.58% | 0.63 | accumulation | 原 v4 信号为 accumulation; 近 5 日大单净流出; 短期反弹但中期趋势仍弱 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ACHC | Watch / neutral | 0.60 | 43.40 | -5.88% | 10.26% | 2.67 | neutral | 近 5 日大单净流入为正; 5D/20D 价格动量同向向下; 暗池成交较近 4 周均值放大，配合多头信号 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |
| ACDC | Watch / neutral | -0.60 | 54.30 | 2.49% | 6.49% | 1.08 | strong_distribution | 原 v4 信号为 strong_distribution; 近 5 日大单净流入为正; 短期反弹但中期趋势仍弱 | 缺少 short_volume，暂不能判断 short pressure/squeeze; 历史 signal-driven backtest 为负，降低信号可信度 |

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

ACGL 目前偏空，核心是当前大单流和价格行为同向走弱。 价格: bearish price confirmation，5D=-2.66%，20D=-0.68%。 Flow: strong institutional net selling，5D Flow/ADV=-10.72%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.73；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步看 flow 是否继续净流出、价格是否跌破/维持弱趋势；若 short_volume 后续补齐且 short pressure 上升，可升级为空头压力确认。

### ABG - Long candidate

ABG 目前偏多，核心是当前大单流和价格行为同向确认。 价格: bullish price confirmation, volume expansion，5D=0.59%，20D=9.62%。 Flow: strong institutional net buying，5D Flow/ADV=7.68%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.36；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步看 flow 是否继续为正、价格是否守住短期趋势；若 short_volume 后续补齐且 short pressure 高但价格不跌，可升级为 squeeze/absorption insight。

### ABNB - Long candidate

ABNB 目前偏多，核心是当前大单流和价格行为同向确认。 价格: bullish price confirmation，5D=2.57%，20D=2.03%。 Flow: institutional net buying，5D Flow/ADV=3.45%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.79；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步看 flow 是否继续为正、价格是否守住短期趋势；若 short_volume 后续补齐且 short pressure 高但价格不跌，可升级为 squeeze/absorption insight。

### ACCO - Long candidate

ACCO 目前偏多，核心是当前大单流和价格行为同向确认。 价格: bullish price confirmation，5D=4.60%，20D=5.37%。 Flow: strong institutional net buying，5D Flow/ADV=4.34%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.08；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步看 flow 是否继续为正、价格是否守住短期趋势；若 short_volume 后续补齐且 short pressure 高但价格不跌，可升级为 squeeze/absorption insight。

### ABAT - Short candidate

ABAT 目前偏空，核心是当前大单流和价格行为同向走弱。 价格: bearish price confirmation，5D=-5.73%，20D=-25.44%。 Flow: strong institutional net selling，5D Flow/ADV=-1.98%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: below-normal delayed darkpool activity，Dark 4W Ratio=0.36；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步看 flow 是否继续净流出、价格是否跌破/维持弱趋势；若 short_volume 后续补齐且 short pressure 上升，可升级为空头压力确认。

### ABBV - Watch / neutral

ABBV 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-4.60%，20D=-3.79%。 Flow: strong institutional net selling，5D Flow/ADV=-10.14%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.02；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACH - Watch / neutral

ACH 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=5.90%，20D=-6.32%。 Flow: strong institutional net buying，5D Flow/ADV=4.44%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.60；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACEL - Watch / neutral

ACEL 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-2.91%，20D=-2.83%。 Flow: strong institutional net buying，5D Flow/ADV=7.39%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: elevated delayed darkpool activity，Dark 4W Ratio=1.50；该数据有发布延迟，只作为机构背景。 联合判断: conflicted absorption watch: delayed darkpool elevated, current flow buying into weak price。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ABM - Watch / neutral

ABM 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bullish price confirmation，5D=0.58%，20D=9.77%。 Flow: institutional net buying，5D Flow/ADV=2.12%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.28；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ABT - Watch / neutral

ABT 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bullish price confirmation，5D=2.52%，20D=12.02%。 Flow: strong institutional net selling，5D Flow/ADV=-17.82%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.98；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ABSI - Watch / neutral

ABSI 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend, volume contraction，5D=4.89%，20D=-31.28%。 Flow: balanced institutional flow，5D Flow/ADV=-0.26%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: very elevated delayed darkpool activity，Dark 4W Ratio=3.46；该数据有发布延迟，只作为机构背景。 联合判断: delayed darkpool activity elevated, but short_volume is unavailable for pressure/squeeze read。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### A - Watch / neutral

A 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bullish price confirmation，5D=1.39%，20D=7.04%。 Flow: strong institutional net buying，5D Flow/ADV=7.20%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.96；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACFN - Watch / neutral

ACFN 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term pullback inside strong 20D trend，5D=-7.61%，20D=10.10%。 Flow: balanced institutional flow，5D Flow/ADV=0.00%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.12；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAP - Watch / neutral

AAP 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation, volume contraction，5D=-3.55%，20D=-1.15%。 Flow: strong institutional net buying，5D Flow/ADV=3.28%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.03；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAOI - Watch / neutral

AAOI 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=12.67%，20D=-10.66%。 Flow: strong institutional net selling，5D Flow/ADV=-5.58%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.63；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACHC - Watch / neutral

ACHC 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-5.88%，20D=-1.61%。 Flow: strong institutional net buying，5D Flow/ADV=10.26%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: very elevated delayed darkpool activity，Dark 4W Ratio=2.67；该数据有发布延迟，只作为机构背景。 联合判断: conflicted absorption watch: delayed darkpool elevated, current flow buying into weak price。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACDC - Watch / neutral

ACDC 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=2.49%，20D=-12.37%。 Flow: strong institutional net buying，5D Flow/ADV=6.49%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.08；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACA - Watch / neutral

ACA 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=0.01%，20D=-0.04%。 Flow: institutional net buying，5D Flow/ADV=0.95%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: very elevated delayed darkpool activity，Dark 4W Ratio=14.48；该数据有发布延迟，只作为机构背景。 联合判断: delayed darkpool activity elevated, but short_volume is unavailable for pressure/squeeze read。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAON - Watch / neutral

AAON 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-8.37%，20D=-15.35%。 Flow: strong institutional net buying，5D Flow/ADV=12.30%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.10；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAL - Watch / neutral

AAL 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend, volume contraction，5D=7.29%，20D=-9.63%。 Flow: balanced institutional flow，5D Flow/ADV=-0.34%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.95；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACCS - Watch / neutral

ACCS 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-3.35%，20D=-5.55%。 Flow: balanced institutional flow，5D Flow/ADV=0.00%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.06；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### ACHR - Watch / neutral

ACHR 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation，5D=-2.22%，20D=-9.87%。 Flow: balanced institutional flow，5D Flow/ADV=-0.42%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.76；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AA - Watch / neutral

AA 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: short-term rebound inside weak 20D trend，5D=1.72%，20D=-10.09%。 Flow: strong institutional net selling，5D Flow/ADV=-4.91%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=1.09；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

### AAPL - Watch / neutral

AAPL 目前更适合观察，信号之间还没有形成足够一致的方向。 价格: bearish price confirmation, volume expansion，5D=-9.94%，20D=-2.96%。 Flow: institutional net selling，5D Flow/ADV=-4.17%。 Short volume: short_volume missing，latest=NA，10D change=NA。 Darkpool: normal delayed darkpool activity，Dark 4W Ratio=0.68；该数据有发布延迟，只作为机构背景。 联合判断: short_volume unavailable; use darkpool only as delayed context。

Next check: 下一步等缺失数据或方向确认：如果 flow、价格、short_volume、darkpool 后续同向，再从 watch 升级为 long/short candidate。

## Data Gaps

- A-prefix short volume currently has no rows through the public API for this run. We should not claim squeeze/short-pressure insights on these names yet.
- Darkpool coverage is available for the A-prefix sample, but latest weeks are delayed by FINRA publication lag.
- This report uses existing v4 signal/backtest summary as a validation input, not as a retrained model.
