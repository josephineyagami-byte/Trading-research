# Research

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
