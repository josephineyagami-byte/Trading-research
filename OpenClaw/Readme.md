## Pre-work(setup): 
* terminal: sudo curl -fsSL https://openclaw.ai/install.sh | bash
* type in ID password
* I understand this is personal-by-default and shared multi-user use requires lock-down, continue? - Choose "yes".
* Onboarding mode: - Choose "QuickStart"
* Model/Auth Provider: Choose model, register AI model accounts and copy API
* Skip(Skills, hooks, etc.) - can be set later.
* How do you want to hatch your bot? - choose "Hatch in TUI"./"Open the Web UI"

### My Configuration
| Setting | Value |
|---|---|
| Model | `google/gemma-4-31b-it:free` via OpenRouter |
| Fallbacks | `nvidia/nemotron-3-super-120b-a12b:free`, `meta-llama/llama-3.3-70b-instruct:free`, `mistralai/mistral-small-3.1-24b-instruct:free` |
| Channel | WhatsApp |
| Web Search | Tavily |

---
### Known Gotchas

- **OpenRouter `auto` router requires credits** — do not set it as your primary model if you're on the free tier. Use a specific model ID instead.
- **Free tier daily limit** - OpenRouter provides free,, rate-limited access to select AI models, with daily limits based on account credit history—typically 50 requests/day for new users, increasing to 1000/day after purchasing at least $10 in credits. Free models (ID ending in :free) also have a 20 requests-per-minute (RPM) limit and are designed for testing rather than production
- **Deprecated models** — free model availability changes. If you get a 404, check [openrouter.ai/models](https://openrouter.ai/models) for the current model ID.
- **API key not set** — the OpenRouter plugin needs an explicit `apiKey` in `openclaw.json`. The plugin being `enabled: true` alone is not enough.
- Set the key safely using:
```bash
  python3 -c "
  import json
  with open('/Users//.openclaw/openclaw.json', 'r') as f:
      c = json.load(f)
  c['plugins']['entries']['openrouter']['config'] = {'apiKey': 'sk-or-v1-...'}
  with open('/Users//.openclaw/openclaw.json', 'w') as f:
      json.dump(c, f, indent=2)
  print('Done!')
  "
```
- **Never manually edit `openclaw.json` with a rich text editor** — smart quotes will break the JSON5 parser. Use `nano` or the Python snippet above.

Testing records:
<img width="1290" height="2796" alt="IMG_7883" src="https://github.com/user-attachments/assets/6682daff-d98e-4350-9c47-1ea5c9005fc9" />

## Stock Data Server

A local FastAPI server that exposes Yahoo Finance data to OpenClaw via MCP.

### Requirements

```bash
pip3 install yfinance fastapi uvicorn lxml --break-system-packages
```

> Tested with yfinance 1.2.0, Python 3.9.6

### Available endpoints

| Endpoint | Description |
|---|---|
| `GET /price/{ticker}` | Live price, open, high, low, volume, market cap, 52w high/low |
| `GET /history/{ticker}?period=1mo&interval=1d` | OHLCV candles at any timeframe |
| `GET /fundamentals/{ticker}` | P/E, EPS, ROE, debt/equity, margins, analyst target |
| `GET /income/{ticker}` | Full income statement (4 years) |
| `GET /balance/{ticker}` | Full balance sheet (4 years) |
| `GET /cashflow/{ticker}` | Full cash flow statement (4 years) |
| `GET /earnings/{ticker}` | Upcoming earnings date + EPS surprise history |
| `GET /analysts/{ticker}` | Consensus summary + recent upgrades/downgrades |
| `GET /news/{ticker}` | Latest 10 news headlines |
| `GET /options/{ticker}` | Options chain for next expiry + all expiry dates |
| `GET /compare?tickers=AAPL,MSFT,NVDA` | Side-by-side comparison |

### Supported history intervals

| Interval | Max history |
|---|---|
| 1 minute | Last 7 days |
| 2, 5, 15, 30 minutes | Last 60 days |
| 1 hour | Last 730 days |
| 1 day / 1 week / 1 month | 20+ years |

> Note: yfinance data is ~15-20 minutes delayed on the free tier. Cash flow statements are quarterly only — intraday cash flow does not exist as a concept.

### Running manually

```bash
python3 -m uvicorn stock_server:app --app-dir ~/.openclaw --port 8765
```

### Auto-start on login (macOS)

Run the setup script once:

```bash
python3 ~/Downloads/setup_autostart.py
```

This installs a LaunchAgent that starts the stock server automatically on every login.

To stop/unload:
```bash
launchctl unload ~/Library/LaunchAgents/com.openclaw.stockserver.plist
```

### Connecting to OpenClaw via MCP

```bash
openclaw mcp set stock-data '{"type":"http","baseUrl":"http://localhost:8765","description":"Live stock market data including price, history, fundamentals, income, balance sheet, cash flow, earnings, analysts, news, options and comparison"}'
```

Verify:
```bash
openclaw mcp list
openclaw mcp show stock-data
```

---

## Roadmap

### In progress
- [ ] Verify OpenClaw is correctly calling the stock MCP server for live data queries

### Up next
- [ ] **Alpaca Markets integration** — real-time trade tape, bid/ask, volume delta, paper trading API (free account)
- [ ] **Order flow data** — real-time buy/sell pressure, options flow, dark pool prints via Alpaca
- [ ] **TradingView webhook bridge** — receive TV alerts → forward to OpenClaw → WhatsApp notification (requires TradingView Pro)

### Future ideas
- [ ] SEC EDGAR insider trading (Form 4) filings — same-day, free
- [ ] Pine Script assistant — help writing, debugging, and explaining Pine Script via WhatsApp
- [ ] Chart analysis — send TradingView screenshot to WhatsApp for AI analysis
- [ ] Paper trade execution via WhatsApp commands through Alpaca API

---

## Useful commands

```bash
# Kill stock server
lsof -ti:8765 | xargs kill -9

# Check gateway logs
tail -50 ~/.openclaw/logs/gateway.err.log

# Restart gateway
openclaw gateway restart

# Run OpenClaw doctor
openclaw doctor

# List MCP servers
openclaw mcp list
```

Testing: 
Order flow of AAPL:
Reply: "After searching through various financial data sources, I need to inform you that *intraday or 4-hour interval signed cash flow data is not available for Apple (AAPL) or any publicly traded company*.

Here's why:

Cash Flow Data Frequency Limitations:

1. *Cash flow statements are released quarterly* - Companies like Apple only publish formal cash flow statements in their 10-Q (quarterly) and 10-K (annual) SEC filings.

2. *No real-time cash flow tracking* - Unlike stock prices or trading volume, cash flow is an accounting metric calculated over periods (typically quarters), not something that fluctuates minute-by-minute or hour-by-hour.

3. *Available frequencies* - The highest frequency cash flow data you can get is:
   - *Quarterly* (every 3 months) - from 10-Q filings
   - *Annual* (yearly) - from 10-K filings
   - *TTM (Trailing Twelve Months)* - rolling sum of last 4 quarters

What I Can Provide Instead:

For Apple (AAPL), I can get you:
- *Latest quarterly cash flow* (Q1 2026: ~$29B operating cash flow based on recent trends)
- *Annual cash flow* (2024: $108.8B free cash flow)
- *TTM free cash flow* (~$129.2B as of March 2026)
- *Historical quarterly trends* from SEC filings

Alternative Data You Can Get Intraday:

If you're looking for real-time financial metrics, these ARE available intraday:
- Stock price and volume
- Options flow
- Insider trading filings (with delay)
- News sentiment
- Analyst estimates revisions

Would you like me to get you the latest available quarterly cash flow statement for Apple instead, or would you prefer one of the intraday alternatives mentioned above?"
