"""
13F Institutional Holdings Validator v3
支持任意 ticker，自动查询 CUSIP。

用法:
  python validate_13f.py --signal-file output/AAPL_1d_xxx_signals.csv --quarters 8
  python validate_13f.py --signal-file output/TSLA_1d_xxx_signals.csv --quarters 8
"""

import argparse
import re
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy import stats

EDGAR_HEADERS = {
    "User-Agent": "Research research@example.com",
    "Accept":     "text/html,application/json",
}
TIMEOUT = 20

# 常用 CUSIP 缓存
CUSIP_CACHE = {
    "AAPL":  "037833100",
    "TSLA":  "88160R101",
    "NVDA":  "67066G104",
    "MSFT":  "594918104",
    "GOOGL": "02079K107",
    "META":  "30303M102",
    "AMZN":  "023135106",
}

# 用于查询未知 ticker 的 Vanguard 13F
VANGUARD_XML_URL = "https://www.sec.gov/Archives/edgar/data/102909/000010290926000031/13F_0000102909_20251231.xml"
_vanguard_xml_cache = None

MAJOR_INSTITUTIONS = {
    "Vanguard":    "0000102909",
    "StateStreet": "0000093751",
    "Fidelity":    "0000315066",
}

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# ── CUSIP 查询
def get_cusip(ticker):
    ticker = ticker.upper()
    if ticker in CUSIP_CACHE:
        return CUSIP_CACHE[ticker]

    global _vanguard_xml_cache
    print("  [INFO] " + ticker + " not in cache, searching Vanguard 13F...")
    if _vanguard_xml_cache is None:
        try:
            r = requests.get(VANGUARD_XML_URL, headers=EDGAR_HEADERS, timeout=30)
            _vanguard_xml_cache = r.text
        except Exception as e:
            print("  [WARN] Cannot fetch Vanguard 13F: " + str(e))
            return None

    entries = re.findall(r"<infoTable>(.*?)</infoTable>",
                         _vanguard_xml_cache, re.DOTALL | re.IGNORECASE)
    for entry in entries:
        name_m  = re.search(r"<nameOfIssuer>(.*?)</nameOfIssuer>", entry, re.IGNORECASE)
        cusip_m = re.search(r"<cusip>([A-Z0-9]{9})</cusip>", entry, re.IGNORECASE)
        if name_m and cusip_m and ticker in name_m.group(1).upper():
            cusip = cusip_m.group(1)
            CUSIP_CACHE[ticker] = cusip
            print("  [INFO] Found " + ticker + " CUSIP: " + cusip)
            return cusip

    print("  [WARN] CUSIP not found for " + ticker)
    return None


# ── 1. 拉取申报列表
def get_filings(cik, name, n):
    url = ("https://data.sec.gov/submissions/CIK" + cik + ".json")
    try:
        r = requests.get(url, headers=EDGAR_HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("  [WARN] " + name + ": " + str(e))
        return []

    recent  = data.get("filings", {}).get("recent", {})
    forms   = recent.get("form", [])
    accs    = recent.get("accessionNumber", [])
    periods = recent.get("reportDate", [])

    results = []
    for form, acc, period in zip(forms, accs, periods):
        if form == "13F-HR":
            results.append({
                "institution": name,
                "cik_num":     cik.lstrip("0"),
                "accession":   acc,
                "period":      period,
            })
            if len(results) >= n:
                break

    print("  " + name + ": found " + str(len(results)) + " 13F filings")
    time.sleep(0.15)
    return results


# ── 2. 从申报中提取目标股票持仓
def get_shares_from_filing(cik_num, accession, cusip):
    acc_clean = accession.replace("-", "")
    idx_url   = ("https://www.sec.gov/Archives/edgar/data/"
                 + cik_num + "/" + acc_clean + "/"
                 + accession + "-index.htm")
    try:
        r = requests.get(idx_url, headers=EDGAR_HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        html = r.text
    except Exception:
        return None

    xml_files = re.findall(r'href="([^"]*\.xml)"', html)
    info_url  = None
    for xf in xml_files:
        if "primary_doc" not in xf.lower() and "xslForm13F" not in xf:
            info_url = "https://www.sec.gov" + xf
            break
    if not info_url:
        return None

    try:
        r = requests.get(info_url, headers=EDGAR_HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        xml = r.text
    except Exception:
        return None

    time.sleep(0.15)

    # 解析：找目标 CUSIP 对应最大的 sshPrnamt
    best    = None
    entries = re.findall(r"<infoTable[^>]*>(.*?)</infoTable>",
                         xml, re.DOTALL | re.IGNORECASE)
    if entries:
        for entry in entries:
            if cusip in entry:
                m = re.search(r"<sshPrnamt>(\d+)</sshPrnamt>",
                              entry, re.IGNORECASE)
                if m:
                    val = float(m.group(1))
                    if best is None or val > best:
                        best = val
    else:
        pos = xml.find(cusip)
        while pos != -1:
            m = re.search(r"<sshPrnamt>(\d+)</sshPrnamt>",
                          xml[pos: pos + 400], re.IGNORECASE)
            if m:
                val = float(m.group(1))
                if best is None or val > best:
                    best = val
            pos = xml.find(cusip, pos + 1)
    return best


# ── 3. 构建季度持仓时间序列
def build_quarterly_holdings(n_quarters, ticker, cusip):
    print("\n[EDGAR] Fetching " + str(n_quarters) +
          " 13F quarters for " + ticker + " (CUSIP: " + cusip + ")...")
    records = []

    for name, cik in MAJOR_INSTITUTIONS.items():
        filings = get_filings(cik, name, n_quarters)
        for f in filings:
            print("    " + name + " " + f["period"] +
                  " -> fetching...", end=" ", flush=True)
            shares = get_shares_from_filing(f["cik_num"], f["accession"], cusip)
            if shares:
                print(str(round(shares / 1e6, 1)) + "M shares")
                records.append({
                    "institution": name,
                    "period":      f["period"],
                    "shares":      shares,
                })
            else:
                print("not found")

    if not records:
        print("[WARN] No 13F data retrieved for " + ticker)
        return pd.DataFrame()

    df  = pd.DataFrame(records)
    df["period"] = pd.to_datetime(df["period"])

    # 只保留所有机构都有数据的季度
    n_inst = df["institution"].nunique()
    period_counts = df.groupby("period")["institution"].nunique()
    valid = period_counts[period_counts == n_inst].index
    if len(valid) == 0:
        valid = period_counts[period_counts >= 2].index
        print("[INFO] Using quarters with >=2 institutions")
    df = df[df["period"].isin(valid)]

    agg = (df.groupby("period")["shares"].sum()
             .reset_index()
             .rename(columns={"shares": "total_shares"})
             .sort_values("period")
             .reset_index(drop=True))
    agg["prev_shares"]    = agg["total_shares"].shift(1)
    agg["net_change"]     = agg["total_shares"] - agg["prev_shares"]
    agg["inst_direction"] = agg["net_change"].apply(
        lambda x: ("accumulation" if pd.notna(x) and x > 0
                   else ("distribution" if pd.notna(x) and x < 0
                         else None)))
    agg["change_pct"] = (
        agg["net_change"] / agg["prev_shares"] * 100).round(3)

    print("\n[OK] Quarterly holdings (" + str(len(agg)) + " periods):")
    print(agg[["period", "total_shares", "net_change",
               "inst_direction", "change_pct"]].to_string(index=False))
    return agg


# ── 4. 信号季度聚合
def aggregate_signals(signal_file):
    df = pd.read_csv(signal_file, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df["quarter"] = (df["datetime"].dt.to_period("Q")
                     .dt.end_time.dt.normalize())

    def summarize(g):
        total = len(g)
        if total == 0:
            return pd.Series()
        acc  = g["signal"].isin(
            ["accumulation", "strong_accumulation"]).sum()
        dist = g["signal"].isin(
            ["distribution", "strong_distribution"]).sum()
        direction = ("accumulation" if acc > dist
                     else ("distribution" if dist > acc else "neutral"))
        return pd.Series({
            "total_bars":      total,
            "acc_pct":         round(acc / total * 100, 1),
            "dist_pct":        round(dist / total * 100, 1),
            "avg_score":       round(g["final_score"].mean(), 4),
            "net_bias":        round((acc - dist) / total, 4),
            "model_direction": direction,
        })

    qdf = df.groupby("quarter", group_keys=False).apply(
        lambda g: summarize(g)).reset_index()
    qdf["quarter"] = pd.to_datetime(qdf["quarter"])
    print("\n[OK] Signal quarterly aggregation ("
          + str(len(qdf)) + " quarters):")
    print(qdf[["quarter", "acc_pct", "dist_pct",
               "avg_score", "model_direction"]].to_string(index=False))
    return qdf


# ── 5. 对比验证
def compare(holdings, signals, ticker):
    merged = pd.merge_asof(
        signals.sort_values("quarter"),
        (holdings.sort_values("period")
                 .rename(columns={"period": "quarter"})),
        on="quarter",
        direction="nearest",
        tolerance=pd.Timedelta("50 days"),
    )
    merged = merged.dropna(subset=["inst_direction", "model_direction"])

    if len(merged) < 2:
        print("[WARN] Less than 2 comparable quarters.")
        return {}, merged

    print("\n" + "-" * 68)
    print("  Quarter       Model Direction      13F Direction        Match")
    print("-" * 68)
    matches = []
    for _, row in merged.iterrows():
        match = row["model_direction"] == row["inst_direction"]
        matches.append(match)
        mark = "YES" if match else "NO "
        print("  " + str(row["quarter"].date()) + "    "
              + str(row["model_direction"]).ljust(20) + "   "
              + str(row["inst_direction"]).ljust(20) + "   " + mark)
    print("-" * 68)

    n          = len(matches)
    match_rate = sum(matches) / n
    binom_p    = stats.binomtest(
        sum(matches), n, p=0.5, alternative="greater").pvalue

    ic_data = merged.dropna(subset=["net_bias", "change_pct"])
    if len(ic_data) >= 4:
        ic, ic_p = stats.spearmanr(
            ic_data["net_bias"], ic_data["change_pct"])
    else:
        ic, ic_p = float("nan"), float("nan")

    result = {
        "Ticker":               ticker,
        "Comparable quarters":  n,
        "Direction matches":    sum(matches),
        "Match rate":           str(round(match_rate * 100, 1)) + "%",
        "Binomial p-value":     round(binom_p, 4),
        "Significant (p<0.05)": ("YES" if binom_p < 0.05
                                  else ("MARGINAL" if binom_p < 0.10
                                        else "NO")),
        "IC (strength corr)":   (round(ic, 4)
                                  if not np.isnan(ic) else "N/A"),
        "IC p-value":           (round(ic_p, 4)
                                  if not np.isnan(ic_p) else "N/A"),
    }
    return result, merged


# ── 6. 主程序
def main():
    parser = argparse.ArgumentParser(
        description="13F Institutional Holdings Validator")
    parser.add_argument("--signal-file", required=True)
    parser.add_argument("--quarters", default=8, type=int)
    parser.add_argument("--ticker", default=None,
                        help="Override ticker (auto-detected from filename)")
    args = parser.parse_args()

    # 自动识别 ticker
    fname = Path(args.signal_file).name
    if args.ticker:
        ticker = args.ticker.upper()
    else:
        m = re.match(r"([A-Z]+)_", fname)
        ticker = m.group(1) if m else "AAPL"

    cusip = get_cusip(ticker)
    if not cusip:
        print("[FATAL] Cannot find CUSIP for " + ticker)
        return

    print("=" * 60)
    print("  13F Methodology Validation")
    print("  Ticker:      " + ticker + " (CUSIP: " + cusip + ")")
    print("  Signal file: " + fname)
    print("  Quarters:    " + str(args.quarters))
    print("=" * 60)

    holdings = build_quarterly_holdings(args.quarters, ticker, cusip)
    if holdings.empty:
        print("[FATAL] Could not retrieve any 13F data")
        return

    holdings.to_csv(
        os.path.join(OUTPUT_DIR, ticker + "_13F_quarterly.csv"), index=False)

    signals  = aggregate_signals(args.signal_file)
    result, merged = compare(holdings, signals, ticker)

    if not result:
        return

    print("\n" + "=" * 60)
    print("  VALIDATION RESULTS")
    print("=" * 60)
    for k, v in result.items():
        print("  " + str(k).ljust(25) + ": " + str(v))

    rate = float(str(result["Match rate"]).replace("%", "")) / 100
    sig  = result["Significant (p<0.05)"]
    print("\n  CONCLUSION:")
    if rate >= 0.75 and sig == "YES":
        print("  PASS  - Method credible at quarterly level.")
    elif rate >= 0.60:
        print("  PARTIAL - Promising, need more quarters.")
    else:
        print("  FAIL  - Low match rate, revisit model.")
    print("\n  NOTE: 13F proves quarterly-level credibility only.")

    report_path = os.path.join(
        REPORT_DIR, Path(args.signal_file).stem + "_13F_validation.txt")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("13F VALIDATION REPORT\n")
        fh.write("Ticker:      " + ticker + "\n")
        fh.write("Signal file: " + fname + "\n")
        fh.write("Generated:   "
                 + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
        for k, v in result.items():
            fh.write(str(k).ljust(25) + ": " + str(v) + "\n")
        if not merged.empty:
            fh.write("\nQuarterly Detail:\n")
            fh.write(merged[["quarter", "model_direction",
                              "inst_direction", "net_bias",
                              "change_pct"]].to_string(index=False))
    print("\n[SAVED] " + report_path)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
