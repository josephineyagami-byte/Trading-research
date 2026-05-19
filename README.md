# Quant Trading Research - Latent Institutional Flow & Inventory Dynamics Research

## Overview

This research does not aim to perform traditional short-term price prediction, nor does it attempt to forecast next-second price movements using limit order book dynamics. Instead, the objective is to address a more fundamental problem in modern market microstructure research:

> Can we infer the existence of persistent institutional execution behavior solely from public market data, and further estimate institutional positioning dynamics over time?

The theoretical foundation of this work is based on recent research in:

- Market Impact Theory
- Meta-order Dynamics
- Long Memory in Order Flow
- Institutional Execution
- Latent State Inference

Modern financial markets are primarily driven by large institutional participants whose capital size prevents them from executing trades instantaneously. Large trades create significant market impact and reveal trading intentions to the market. As a result, institutions typically rely on **order splitting**, where a large parent order is decomposed into thousands of smaller child orders and executed gradually over extended periods of time using algorithmic execution strategies such as:

- VWAP Execution
- TWAP Execution
- POV (Percent-of-Volume) Execution

Recent market impact literature suggests that price impact is not linear with respect to trade size, but instead approximately follows the square-root impact law:

$$
Impact \propto \sqrt{Q}
$$

This implies that as trade size increases, market impact grows substantially, forcing institutions to minimize execution footprint through persistent, low-impact trading behavior.

---

# Core Hypothesis

The central hypothesis of this research is:

> Institutional order splitting creates observable persistence in directional order flow.

In other words, if large institutions continuously execute fragmented orders over time, then market order flow should exhibit:

- Long memory
- Persistent signed imbalance
- Stable execution behavior around VWAP
- Suppressed market impact
- Liquidity absorption

Rather than viewing order flow as an IID random process, modern market microstructure research suggests that signed order flow exhibits significant autocorrelation over long horizons due to persistent institutional execution.

---

# Research Objective

The objective is therefore not to identify specific institutions, but rather to infer:

- Whether persistent institutional activity exists
- Whether institutions are accumulating or distributing inventory
- Whether institutional positioning is increasing or decreasing
- The estimated inventory accumulation range during a meta-order execution regime

This transforms the problem from:

> "Who owns the stock?"

into:

> "Is the market currently being persistently re-priced by large institutional flow?"

---

# Methodology

## 1. Trade Classification

Raw market data only contains:

- Price
- Volume
- Timestamp

It does not directly reveal whether a trade was initiated by a buyer or seller.

Therefore, the first step is to perform **trade classification** using methods such as:

- Lee-Ready Algorithm
- Bulk Volume Classification (BVC)

This allows us to construct:

- Signed Order Flow
- Buy-initiated Volume
- Sell-initiated Volume

Signed order flow is the foundation for detecting directional persistence.

---

## 2. Volume Bucket Methodology

Instead of analyzing markets using fixed clock time intervals, the market is segmented using **volume buckets**.

For example:

- Every 1 million shares traded forms a new analytical bucket.

This is because institutional execution is fundamentally a:

> Volume-driven process rather than a purely time-driven process.

Within each volume bucket, the following variables are computed:

- Signed Volume
- Order Imbalance
- VWAP
- Impact Efficiency
- Relative Volume (RVOL)
- Close Location Value
- Intraday Participation Profile

---

## 3. VWAP as an Institutional Execution Anchor

VWAP (Volume Weighted Average Price) plays a critical role in institutional execution.

Institutions generally do not attempt to buy at absolute lows or sell at absolute highs. Instead, their primary objective is to avoid significantly underperforming VWAP benchmarks.

As a result, institutional execution algorithms tend to:

- Participate around VWAP
- Mean-revert toward VWAP
- Suppress excessive deviation from VWAP

This creates identifiable VWAP interaction patterns.

Persistent institutional participation often manifests as:

- Price holding above VWAP
- Stable VWAP interaction
- Elevated volume with suppressed volatility
- Repeated liquidity absorption near VWAP

---

## 4. Participation Rate Estimation

Institutional execution is often governed by POV (Percent-of-Volume) algorithms.

Instead of executing fixed trade sizes, institutions dynamically participate as a fraction of market volume.

For example:

- Market Volume = 1,000,000 shares
- Institutional Participation Rate = 15%
- Institution executes approximately 150,000 shares

However, institutional participation rate is not directly observable.

Therefore, participation rate must be inferred statistically using observable market behavior such as:

- Persistent order imbalance
- VWAP interaction
- Relative volume expansion
- Suppressed impact efficiency
- Liquidity absorption

The objective is not to estimate an exact percentage, but rather to infer:

> Whether institutional participation is persistently elevated.

---

## 5. Liquidity Absorption

One of the strongest institutional signatures is liquidity absorption.

For example:

- Large sell pressure appears
- Price fails to decline significantly
- VWAP remains supported
- Impact efficiency remains low

This suggests the presence of a large passive liquidity provider continuously absorbing supply.

Institutional accumulation frequently appears as:

- High volume
- Low directional volatility
- Persistent VWAP support
- Stable signed imbalance

rather than explosive directional price movement.

---

## 6. Impact Efficiency & Impact Decay

Another key distinction between retail-driven speculation and institutional execution lies in market impact structure.

Retail-driven flows typically exhibit:

- Small volume
- Large price movement
- Rapid directional expansion

Institutional execution, on the other hand, often exhibits:

- Persistent large volume
- Suppressed price impact
- Controlled execution trajectory

Impact efficiency is defined as:

$$
IE = \frac{|\Delta P|}{Volume}
$$

Low impact efficiency during elevated volume often indicates institutional execution.

Additionally, true institutional flow tends to leave behind partial permanent impact, meaning price does not fully revert after execution ends.

Rapid full reversions are more indicative of temporary liquidity shocks rather than persistent institutional positioning.

---

# Meta-order Segmentation

Institutional execution does not occur instantaneously.

Instead, it unfolds over persistent execution regimes.

To identify candidate institutional execution periods, we apply:

- Hidden Markov Models (HMM)
- Bayesian Changepoint Detection
- Hawkes Process-based Clustering

These methods allow the segmentation of persistent directional flow regimes consistent with meta-order execution.

---

# Institutional Inventory Estimation

The ultimate objective is not merely detecting institutional activity, but estimating institutional positioning dynamics.

However, institutional inventory is not directly observable.

Markets only expose:

- Trades
- Volume
- Price
- Order Flow

while actual institutional inventory remains hidden.

Therefore, institutional inventory is modeled as a latent state:

$$
I_t = I_{t-1} + F_t - D_t
$$

Where:

- $I_t$ = Estimated Institutional Inventory
- $F_t$ = Estimated Institutional Net Flow
- $D_t$ = Inventory Decay / Unwind

We further estimate inventory change using:

$$
\Delta I_t \approx G_t \cdot p_t \cdot M_t
$$

Where:

- $G_t$ = Direction of Flow
- $p_t$ = Estimated Participation Rate
- $M_t$ = Market Volume

This means institutional inventory accumulation is modeled as:

> Directional institutional participation multiplied by market volume.

---

# Latent State Inference

Since participation rate and inventory are not directly observable, the framework becomes a latent-state inference problem.

Observable variables include:

- Signed Order Flow
- VWAP Interaction
- Relative Volume
- Impact Efficiency
- Liquidity Absorption
- Impact Decay

Hidden variables include:

- Institutional Participation Rate
- Institutional Inventory
- Institutional Positioning Pressure

To estimate posterior distributions over these hidden states, the framework utilizes:

- Bayesian State-space Models
- Kalman Filtering
- Particle Filtering
- Hidden Markov Models

The result is not deterministic reconstruction, but probabilistic inference.

---

# Final Output

The model ultimately outputs:

- Accumulation Probability
- Distribution Probability
- Institutional Participation Estimate
- Institutional Positioning Pressure
- Estimated Inventory Accumulation Range
- Meta-order Confidence Score

Importantly, the objective is not to answer:

> "Exactly how much stock does an institution own?"

but rather:

> "Is the market currently undergoing persistent institutional re-pricing, and is institutional positioning systematically increasing or decreasing?"

This research therefore sits at the intersection of:

- Institutional Market Microstructure
- Market Impact Theory
- Meta-order Inference
- Latent State Estimation

with the primary objective of identifying the underlying institutional execution processes that drive medium- and long-term market structure changes.
