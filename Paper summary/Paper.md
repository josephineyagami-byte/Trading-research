# Research Paper

**Paper 1:** *Caught on Tape: Institutional Order Flow and Stock Returns*\
**Authors:** Campbell, Ramadorai, Schwartz


## Overview

This paper investigates how to infer institutional trading activity(capital inflows and outflows) using transaction-level market data. Since institutional trades are not directly labeled in most datasets, the authors develop a methodology to estimate them indirectly.

The central question:

> Can we detect and measure institutional trading flows using only observable market data like trade size and volume?


## Methodology

### 1. Trade Classification

* Trades are grouped by size buckets:

  * Large trades → more likely institutional
  * Small trades → more likely retail

### 2. Order Flow Construction

Institutional flow is approximated using:

```
Flow = Buy Volume − Sell Volume
```

* Positive → net inflow (buy pressure)
* Negative → net outflow (sell pressure)

### 3. Data Sources

* TAQ (Trade and Quote data)
* Institutional ownership data (e.g., 13F filings)


## Key Findings:

### 1. Institutional Flow Predicts Returns

* Stocks with positive institutional flow tend to have:

  * Short-term positive returns
* Stocks with negative flow tend to underperform


### 2. Trading is Persistent

* Institutional investors:

  * Execute trades over multiple days
  * Split large orders into smaller transactions


### 3. Markets Do Not Fully Adjust Immediately

* Prices do not instantly reflect institutional activity
* This creates predictable return patterns (alpha opportunities)


## Key Insights

### Insight 1: Institutional Flow is Hidden but Detectable

Even without direct labels, trading behavior leaves patterns that can be reconstructed.


### Insight 2: Flow is More Informative than Price Alone

* Price = outcome
* Flow = cause

Tracking flow provides earlier signals than price movement.


### Insight 3: Large Players Move Markets Gradually

Institutional investors cannot trade instantly without impacting price, so they:

* Split orders
* Trade over time
* Create detectable trends in order flow


### Insight 4: Alpha Comes from Detecting "Smart Money"

Identifying institutional inflow/outflow allows traders to:

* Follow informed capital
* Anticipate price movements


## Practical Applications

### Quantitative Trading

* Build order flow imbalance signals
* Use flow persistence as a predictive feature

### Market Analysis

* Detect accumulation/distribution phases
* Identify institutional participation

### Risk Management

* Monitor large outflows as early warning signals


## Limitations

* Trade size is only a proxy, not a perfect identifier
* Institutional activity is often hidden via order splitting
* Requires high-quality, high-frequency data


## Summary

This paper establishes a foundational framework for:

* Estimating institutional capital flows
* Understanding their impact on prices
* Building predictive trading signals

> Institutional trading flow is one of the most important hidden drivers of financial markets — and it can be measured.


## References

* Campbell, J. Y., Ramadorai, T., & Schwartz, A. (2005)
* NBER Working Paper

---

## Takeaway

If you can track where large institutions are moving capital, you gain insight into the true direction of the market before it is fully reflected in prices.


## Next: 
The paper assumes: Large trades ≈ institutional
But in reality:
HFTs can also trade large
Institutions split orders (so trades look small)
how to measure institutional flow correctly?

Is price moving because:
institutions know something, or they are just pushing price mechanically?

Backtesting: according to this paper, produce indicators: large money inflow -> buy signal. Look for metrics(sharpe ratio, max drawdown,etc).
Test: Does high flow today → higher return tomorrow?
This one is old paper(2005), differences between past and now?




**Paper 2:** *Deep order flow imbalance: Extracting alpha at multiple horizons from the limit order book*\
**Authors:** Petter N. Kolm, Jeremy Turiel, Nicholas Westray**\
**Data: **115 Nasdaq stocks, high-frequency limit order book data**\
---

# 🧠 Part I — Core Concept: Order Flow Imbalance (OFI)

## 🔹 What is OFI?

Order Flow Imbalance (OFI) measures the **imbalance between buying and selling pressure** in the market.

### Intuition

Market = tug of war:

- Buyers push price up  
- Sellers push price down  

> **OFI tells you who is stronger right now**

---
OFI measures the **net imbalance between buying and selling pressure**.

### Basic intuition

Market = continuous auction:

- Buyers consume liquidity (lift offers)
- Sellers consume liquidity (hit bids)

> **OFI captures which side is consuming liquidity faster**

---

## 🔹 3. Mathematical Definition (Simplified)
OFI = Buy Volume − Sell Volume
Normalized:
OFI = (Buy Volume − Sell Volume) / Total Volume
---

## 🔬 4. Microstructure Definition (More Accurate)

In modern research, OFI is constructed from order book events:

- Increase in bid size → buying pressure  
- Decrease in ask size → buying pressure  
- Increase in ask size → selling pressure  
- Decrease in bid size → selling pressure  

Thus:

> OFI = Net change in supply-demand across price levels

---

## 📊 5. Interpretation

### OFI > 0
- Buyers are more aggressive  
- Liquidity on ask side is being consumed  
- Market under upward pressure  

---

### OFI < 0
- Sellers are more aggressive  
- Liquidity on bid side is being consumed  
- Market under downward pressure  

---

### OFI ≈ 0
- Balanced flow  
- No dominant force  

---

## 📈 6. Magnitude Interpretation

OFI measures **intensity of pressure**, not price

- Small OFI → weak imbalance  
- Large OFI → strong directional pressure  

---

## ⚠️ 7. Important Clarifications

### ❗ OFI ≠ Institutional Flow

OFI = Institutional + HFT + Noise

- It is NOT a clean signal  
- It is a **mixture of all participants**

---

### ❗ OFI ≠ Guaranteed Price Movement

- Liquidity may absorb pressure  
- Other participants may counteract  
- Information may already be priced  

---

## 🔑 8. Why OFI Works

Core mechanism:
Flow → Liquidity consumption → Price adjustment
Sequence:

1. Large participant trades  
2. Order flow becomes imbalanced  
3. Market maker adjusts price  
4. Price moves  

---

## 🧩 9. Relation to Institutional Trading

Institutional traders typically:

- Trade large size  
- Split orders over time (meta-orders)  
- Create persistent directional flow  

Thus:

> Persistent OFI may indicate institutional activity  
BUT cannot identify it directly

---

# 📄 Part II — Paper Deep Dive: Deep Order Flow Imbalance

## 🔹 1. Research Question

> Can order flow extracted from limit order books predict short-term price movements?

---

## 🔹 2. Key Idea

Instead of using raw order book data:

> Transform data into **stationary order-flow features**

Reason:
- Raw order book is noisy and non-stationary  
- Machine learning performs better on stable inputs  

---

## 🔹 3. Methodology Breakdown

### Step 1: Data
- High-frequency limit order book data  
- Multiple stocks (cross-sectional)

---

### Step 2: Feature Engineering

Transform:
Raw Order Book → Order Flow Features

Examples:
- Order flow imbalance  
- Changes in depth  
- Flow dynamics  

---
### Step 3: Modeling

- Deep learning models (LSTM, CNN)
- Predict future returns over multiple horizons  

---

### Step 4: Evaluation

- Compare:
  - Raw order book models  
  - Order flow-based models  

---

## 📊 4. Key Results

### ✔️ 1. Order Flow > Raw Order Book
- Transformed features outperform raw inputs  

---

### ✔️ 2. Predictability is Short-Term
- Signal horizon ≈ very short (few price changes)

---

### ✔️ 3. Cross-Sectional Differences
- Some stocks are more predictable  
- Depends on microstructure properties  

---

## 💡 5. Why This Works

### Reason 1: Noise Reduction
Order flow removes irrelevant information  

---

### Reason 2: Stationarity
Flow features are more stable over time  

---

### Reason 3: Direct Link to Price Formation
Flow directly affects liquidity and price  

---

## ⚠️ 6. Limitations (Critical)

### ❗ 1. No Institutional Identification
- Cannot distinguish who is trading  

---

### ❗ 2. Extremely Short Horizon
- Signal decays very fast  

---

### ❗ 3. Not Directly Tradable
- Does not include:
  - transaction costs  
  - execution constraints  

---

### ❗ 4. High Data Requirement
- Requires high-frequency LOB data  

---

## 🔍 7. Open Questions from the Paper

### Q1: Is predictability due to information or mechanical impact?

---

### Q2: Does signal persist after execution ends?

---

### Q3: Can this survive transaction costs?

---

### Q4: How to separate institutional vs noise flow?

---

### Q5: Can better features improve signal?

---

## 🚀 8. Research Implications

This paper shifts the paradigm:

### Old approach:
> Identify institutions

### New approach:
> Model flow dynamics

---

## 🧠 Key Takeaway

> The market does not move because of price.\n\n> It moves because of **order flow interacting with liquidity**.


### 🔹 Direction A: Real-Time Trading AI
- Use microstructure signals (OFI, order book)
- Predict short-term price movement

---

### 🔹 Direction B: Institutional Flow Tracking
- Infer large capital behavior
- Detect hidden meta-orders

### 1️⃣ Ground Truth (Ancerno)

- Real institutional trades  
- Limited access  

---

### 2️⃣ ETF / Fund Flow

- Tracks capital movement  
- Medium-term signal  

---

### 3️⃣ 13F Ownership

- Institutional holdings  
- Long-term  

---

### 4️⃣ Meta-Order Detection
- High-frequency  
- Hidden but critical  

---

## 📊 Relationship

OFI → short-term pressure
Meta-order → execution behavior
ETF → capital allocation
13F → confirmation
---


# Inferring Microscopic Financial Information from the Long Memory in Order Flow

## Authors
- Iacopo Mastromatteo
- Bence Tóth
- Jean-Philippe Bouchaud
- Others

## Published
Physical Review Letters (2023)

---

## Core Idea

This paper studies one of the most important empirical observations in modern market microstructure:

> Order flow is not random.

More specifically, signed order flow exhibits **long memory**, meaning:

- Buy orders tend to be followed by more buy orders
- Sell orders tend to be followed by more sell orders
- Directional flow persists over long horizons

The paper shows that this persistence is strongly connected to:

# Meta-order Splitting

In other words:

> Large institutions split massive parent orders into many smaller child orders executed sequentially over time.

As a result, markets exhibit persistent directional pressure even when individual trades appear small and fragmented.

---

## Key Mathematical Insight

The paper studies the autocorrelation structure of signed order flow:

$$
C(\tau) \propto \tau^{-\gamma}
$$

Where:

- $C(\tau)$ = autocorrelation of signed order flow
- $\tau$ = time lag
- $\gamma$ = decay exponent

The important result is:

> Order flow autocorrelation decays slowly rather than disappearing immediately.

This means markets retain memory of previous directional trading activity.

---

## Why This Matters

This result fundamentally changes how institutional activity should be modeled.

Traditional models assume:

- Trades are IID
- Order flow quickly randomizes
- Market activity is memoryless

This paper argues the opposite:

> Persistent institutional execution creates statistically observable structure in market flow.

Therefore, persistent signed imbalance is not merely "noise" or "momentum", but may instead represent:

- Institutional accumulation
- Institutional distribution
- Ongoing meta-order execution

---

## Key Insight for This Research

This paper provides the theoretical foundation for:

- Signed order flow persistence detection
- Meta-order segmentation
- Institutional activity inference

Our framework directly builds on the idea that:

> Long memory in order flow is a statistical footprint of institutional order splitting.

---

## Practical Implication

If markets repeatedly exhibit:

- Persistent buy imbalance
- Elevated relative volume
- Stable VWAP interaction
- Low impact efficiency

then the probability of latent institutional execution increases significantly.

This is the conceptual basis for detecting:

- Institutional accumulation regimes
- Institutional participation pressure
- Inventory build-up dynamics

---

# Market Impact: Empirical Evidence, Theory and Practice

## Authors
- Jean-Philippe Bouchaud
- J. Bonart
- Jonathan Donier
- Martin Gould

## Published
2022

---

## Core Idea

This paper studies how large trades move markets.

The key conclusion is:

> Market impact is nonlinear.

More specifically:

$$
Impact \propto \sqrt{Q}
$$

Where:

- $Q$ = trade size
- Impact = resulting price movement

This is known as the:

# Square-root Impact Law

---

## Why This Matters

If price impact were linear:

- Institutions could execute instantly.

However, because impact grows nonlinearly:

- Large aggressive orders become extremely expensive.
- Institutions must minimize execution footprint.
- Large trades must be fragmented over time.

This creates the economic incentive for:

# Meta-order Execution

---

## Key Insight

Institutional execution is fundamentally an optimization problem.

Institutions attempt to:

- Minimize market impact
- Avoid revealing information
- Reduce execution cost
- Maintain execution near VWAP benchmarks

As a result, institutional flow often appears as:

- Persistent elevated volume
- Suppressed volatility
- Stable VWAP interaction
- Liquidity absorption
- Controlled price trajectories

rather than explosive directional movement.

---

## Temporary vs Permanent Impact

Another major contribution of this paper is distinguishing:

### Temporary Impact
Short-term liquidity displacement.

### Permanent Impact
Information that remains embedded in price after execution ends.

This distinction is extremely important.

If price rapidly fully reverts after heavy trading:

- The move was likely liquidity-driven.

If price only partially decays:

- The market may interpret the flow as informational.

---

## Key Insight for This Research

This paper provides the theoretical foundation for:

- Impact efficiency estimation
- Liquidity absorption detection
- VWAP execution analysis
- Inventory accumulation inference

Our framework directly builds on the idea that:

> Institutional execution leaves identifiable market impact structures.

---

## Practical Implication

True institutional accumulation often appears as:

- Large persistent volume
- Low impact efficiency
- Stable VWAP anchoring
- Partial post-trade decay
- Sustained directional imbalance

rather than short-term price spikes.

This allows institutional participation to be inferred statistically even without access to proprietary inventory data.

---

# Combined Research Insight

Together, these two papers establish the core logic of the entire framework.

The first paper explains:

> WHY persistent order flow exists.

The second paper explains:

> HOW institutions execute while minimizing market impact.

Combining both ideas leads to the central thesis of this project:

> Large institutional participants cannot execute instantaneously.
> Therefore, they split orders across time.
> This creates persistent directional order flow and identifiable impact structures.
> These structures become statistically observable in public market data.

As a result, although institutional inventory itself is hidden, markets still reveal:

- Participation pressure
- Accumulation behavior
- Distribution regimes
- Meta-order execution dynamics

through observable signatures such as:

- Signed order flow persistence
- VWAP interaction
- Relative volume expansion
- Liquidity absorption
- Impact decay
- Suppressed impact efficiency

The proposed framework therefore treats institutional inventory as a latent state and attempts to infer it probabilistically through persistent market behavior rather than explicit ownership disclosures.

# Generating Realistic Metaorders from Public Data

## Authors
- Louis Béthune
- Iacopo Mastromatteo
- Jean-Philippe Bouchaud
- Others

## Published
2025

---

## Why This Paper Is Extremely Important

This paper is arguably one of the closest modern research works to the core objective of this project.

Most historical market microstructure research relied on:

- Proprietary institutional datasets
- Broker execution records
- Hidden inventory data

However, such datasets are inaccessible to most researchers.

This paper attempts to solve a much harder and more practical problem:

> Can realistic institutional meta-orders be reconstructed using only public market data?

This directly aligns with the central objective of our framework.

---

# Core Idea

The paper argues that although institutional parent orders are hidden, they still leave behind:

- Persistent directional order flow
- Observable impact structures
- Volume participation patterns
- Execution trajectory signatures

Therefore, even without direct institutional inventory data, it may still be possible to reconstruct statistically realistic meta-order behavior.

This is extremely important because it reframes the entire problem:

Instead of asking:

> "Can we observe institutions directly?"

the paper asks:

> "Can we infer the latent execution process from market behavior?"

---

# What Is a Meta-order?

A meta-order is not a single trade.

Instead, it is:

> A large institutional parent order fragmented into many smaller child orders executed sequentially over time.

For example:

A fund attempting to buy 10 million shares will typically split the order into:

- Thousands of smaller executions
- Spread across hours or days
- Dynamically adjusted based on liquidity conditions

As a result:

Markets do not observe:

- One massive trade

but instead observe:

- Persistent directional pressure
- Stable participation
- VWAP interaction
- Controlled market impact

---

# Key Insight

The paper demonstrates that realistic meta-orders generate highly structured market behavior.

These behaviors include:

- Long-memory in signed order flow
- Persistent participation rate
- Concave execution trajectories
- Partial impact decay
- Stable execution near liquidity centers

This means institutional execution is not random.

Instead, it creates identifiable statistical structure.

---

# Why This Matters for This Research

This paper provides one of the strongest modern justifications for treating:

- Institutional participation
- Institutional inventory
- Meta-order execution

as:

# Latent Variables

rather than directly observable quantities.

The paper strongly supports the idea that:

> Institutional behavior can be statistically inferred even when direct ownership data is unavailable.

This becomes the conceptual foundation for:

- Inventory range estimation
- Participation rate inference
- Latent institutional flow detection

---

# Public Data Reconstruction

One of the most important contributions of this paper is the idea that:

> Public market activity contains enough structural information to reconstruct realistic execution dynamics.

This directly supports our framework's methodology of using:

- Signed order flow persistence
- VWAP interaction
- Relative volume expansion
- Liquidity absorption
- Impact suppression
- Impact decay

to infer hidden institutional activity.

---

# Connection to Inventory Estimation

The paper is particularly relevant to the inventory estimation component of this project.

Our framework assumes that institutional inventory is hidden:

$$
I_t = I_{t-1} + F_t - D_t
$$

Where:

- $I_t$ = latent institutional inventory
- $F_t$ = estimated institutional net flow
- $D_t$ = unwind / decay component

The paper supports the idea that although inventory itself is unobservable, persistent execution behavior creates sufficient statistical structure to estimate:

- Directional accumulation pressure
- Meta-order duration
- Participation intensity
- Inventory build-up ranges

through public flow observations.

---

# Most Important Conceptual Contribution

The most important contribution of this paper is the shift from:

## Traditional Thinking

> Institutions are invisible because inventory is hidden.

to:

## Modern Microstructure Thinking

> Institutions are statistically inferable because execution leaves persistent structural footprints in public markets.

This idea is central to the entire philosophy of this project.

---

# Key Practical Insight

The paper implies that institutional accumulation does not necessarily appear as:

- Explosive directional price movement
- Large visible block trades

Instead, it more commonly appears as:

- Persistent elevated volume
- Stable directional imbalance
- Controlled market impact
- VWAP-constrained execution
- Repeated liquidity absorption
- Gradual inventory accumulation

This distinction is critical.

Retail traders often look for:

- Sudden price spikes
- Breakouts
- Momentum explosions

However, real institutional execution frequently attempts to avoid exactly those outcomes.

---

# Connection to the Proposed Framework

This paper directly supports the central methodology of the project:

1. Detect persistent directional order flow
2. Identify candidate meta-order execution regimes
3. Estimate participation rate probabilistically
4. Infer latent inventory accumulation ranges
5. Model institutional positioning as a hidden state

In this framework:

- Market activity is observable
- Institutional inventory is hidden
- Meta-order execution acts as the latent process connecting both

---

# Combined Insight with Other Papers

Together with:

- *Inferring Microscopic Financial Information from the Long Memory in Order Flow*
- *Market Impact: Empirical Evidence, Theory and Practice*

this paper completes the conceptual foundation of the framework.

The three papers together explain:

1. Why order flow persistence exists
2. Why institutions must split execution
3. Why market impact creates structured execution behavior
4. Why latent institutional flow can be inferred statistically
5. Why inventory estimation must be probabilistic rather than deterministic
