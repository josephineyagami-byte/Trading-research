"""
Backtest Validator
=====================
读取 signal_generator.py 的 output CSV，验证信号的可用性和可信度。

方法：
  1. Event Study     — 信号后 N bar 的平均收益
  2. 统计检验        — t-test / Sharpe / p-value
  3. Walk-Forward    — 滚动窗口模拟真实使用
  4. 信息系数 (IC)   — 信号强度与未来收益的相关性
  5. 最大回撤分析

用法：
  python backtest.py --file output/AAPL_1d_xxx_signals.csv
  python backtest.py --file output/AAPL_1d_xxx_signals.csv --forward 5 --cost 0.001
"""

import argparse
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


# ══════════════════════════════════════════════
# 1. 加载信号数据
# ══════════════════════════════════════════════

def load_signals(fpath: str) -> pd.DataFrame:
    df = pd.read_csv(fpath, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    print(f"[OK] 加载 {len(df)} 条信号记录")
    print(f"     时间范围: {df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}")
    print(f"     信号列: {df['signal'].unique().tolist()}")
    return df


# ══════════════════════════════════════════════
# 2. 计算前向收益
# ══════════════════════════════════════════════

def add_forward_returns(df: pd.DataFrame, horizons: list) -> pd.DataFrame:
    """计算信号触发后 N bar 的收益率"""
    df = df.copy()
    for h in horizons:
        df[f"fwd_ret_{h}"] = df["close"].pct_change(h).shift(-h)
    return df


# ══════════════════════════════════════════════
# 3. Event Study — 核心验证
# ══════════════════════════════════════════════

def event_study(df: pd.DataFrame, horizons: list, cost: float) -> pd.DataFrame:
    """
    对每类信号，统计触发后各 horizon 的平均收益。
    返回汇总表。
    """
    acc_signals  = ["accumulation", "strong_accumulation"]
    dist_signals = ["distribution", "strong_distribution"]

    results = []

    for direction, signal_list, sign in [
        ("多头(积累)", acc_signals,  +1),
        ("空头(派发)", dist_signals, -1),
    ]:
        mask = df["signal"].isin(signal_list)
        subset = df[mask].copy()
        if len(subset) < 5:
            print(f"[WARN] {direction} 信号数量不足 (<5)，跳过")
            continue

        for h in horizons:
            col = f"fwd_ret_{h}"
            rets = subset[col].dropna() * sign  # 方向调整后的收益
            rets_after_cost = rets - cost        # 扣除交易成本

            if len(rets_after_cost) < 5:
                continue

            t_stat, p_val = stats.ttest_1samp(rets_after_cost, 0)
            sharpe = rets_after_cost.mean() / (rets_after_cost.std() + 1e-10) * np.sqrt(252 / h)
            hit_rate = (rets_after_cost > 0).mean()

            results.append({
                "方向":      direction,
                "信号数量":  int(mask.sum()),
                "持有周期":  f"{h} bar",
                "平均收益":  f"{rets_after_cost.mean()*100:.3f}%",
                "胜率":      f"{hit_rate*100:.1f}%",
                "年化Sharpe":f"{sharpe:.2f}",
                "t统计量":   f"{t_stat:.2f}",
                "p值":       f"{p_val:.4f}",
                "显著性":    "✅ 显著" if p_val < 0.05 else ("⚠️ 边缘" if p_val < 0.10 else "❌ 不显著"),
            })

    return pd.DataFrame(results)


# ══════════════════════════════════════════════
# 4. 信息系数 (IC) — 信号强度与收益相关性
# ══════════════════════════════════════════════

def information_coefficient(df: pd.DataFrame, horizons: list) -> pd.DataFrame:
    """
    IC = Spearman rank correlation(final_score, fwd_ret_h)
    IC > 0.05 有参考价值，IC > 0.10 较好
    """
    results = []
    for h in horizons:
        col = f"fwd_ret_{h}"
        sub = df[["final_score", col]].dropna()
        if len(sub) < 10:
            continue
        ic, p = stats.spearmanr(sub["final_score"], sub[col])
        results.append({
            "持有周期": f"{h} bar",
            "IC值":     f"{ic:.4f}",
            "p值":      f"{p:.4f}",
            "评级":     "⭐⭐⭐ 优秀" if abs(ic) > 0.10 else (
                         "⭐⭐ 一般"  if abs(ic) > 0.05 else "⭐ 弱")
        })
    return pd.DataFrame(results)


# ══════════════════════════════════════════════
# 5. Walk-Forward 验证
# ══════════════════════════════════════════════

def walk_forward(df: pd.DataFrame, train_window: int, forward_h: int,
                 cost: float) -> pd.DataFrame:
    """
    滚动窗口验证：每次用过去 train_window bar 的信号特征，
    观察接下来 forward_h bar 的实际收益。
    模拟真实场景下信号的稳定性。
    """
    records = []
    total = len(df)
    step = max(1, forward_h)

    for start in range(train_window, total - forward_h, step):
        window = df.iloc[start - train_window: start]
        future = df.iloc[start: start + forward_h]

        last_signal = window["signal"].iloc[-1]
        last_score  = window["final_score"].iloc[-1]

        if pd.isna(last_signal):
            continue

        is_acc  = last_signal in ["accumulation", "strong_accumulation"]
        is_dist = last_signal in ["distribution", "strong_distribution"]

        if not (is_acc or is_dist):
            continue

        direction = +1 if is_acc else -1
        fwd_ret   = (future["close"].iloc[-1] / future["close"].iloc[0] - 1) * direction
        fwd_ret  -= cost

        records.append({
            "start_time": window["datetime"].iloc[-1],
            "signal":     last_signal,
            "score":      last_score,
            "fwd_ret":    fwd_ret,
            "win":        fwd_ret > 0,
        })

    if not records:
        return pd.DataFrame()

    result = pd.DataFrame(records)
    result["cum_ret"] = (1 + result["fwd_ret"]).cumprod() - 1
    return result


def wf_summary(wf: pd.DataFrame) -> dict:
    if wf.empty:
        return {}
    total_trades = len(wf)
    win_rate     = wf["win"].mean()
    avg_ret      = wf["fwd_ret"].mean()
    sharpe       = avg_ret / (wf["fwd_ret"].std() + 1e-10) * np.sqrt(252)
    final_cum    = wf["cum_ret"].iloc[-1]
    max_dd       = (wf["cum_ret"] - wf["cum_ret"].cummax()).min()

    return {
        "总交易次数": total_trades,
        "胜率":       f"{win_rate*100:.1f}%",
        "平均单次收益": f"{avg_ret*100:.3f}%",
        "累计收益":   f"{final_cum*100:.2f}%",
        "最大回撤":   f"{max_dd*100:.2f}%",
        "年化Sharpe": f"{sharpe:.2f}",
    }


# ══════════════════════════════════════════════
# 6. 信号驱动回测
# ══════════════════════════════════════════════

def signal_driven_backtest(df: pd.DataFrame, cost: float,
                           max_hold: int = 24,
                           min_confirm: int = 1,
                           stop_loss: float = 0.02,
                           long_only: bool = False) -> pd.DataFrame:
    """
    信号驱动持仓：积累入场，反向信号或 neutral 出场，最多持仓 max_hold bar
    min_confirm: 连续 N bar 同向信号才入场（过滤噪音）
    """
    records = []
    i = 0
    n = len(df)

    while i < n:
        row    = df.iloc[i]
        signal = row["signal"]
        is_acc  = signal in ["accumulation", "strong_accumulation"]
        is_dist = signal in ["distribution", "strong_distribution"]

        if not (is_acc or is_dist):
            i += 1
            continue

        # 持续性过滤：检查前 min_confirm-1 根 bar 是否同向
        if min_confirm > 1 and i >= min_confirm - 1:
            direction_check = +1 if is_acc else -1
            confirmed = True
            for k in range(1, min_confirm):
                prev_sig = df.iloc[i-k]["signal"]
                prev_acc = prev_sig in ["accumulation", "strong_accumulation"]
                prev_dist = prev_sig in ["distribution", "strong_distribution"]
                if direction_check == +1 and not prev_acc:
                    confirmed = False
                    break
                if direction_check == -1 and not prev_dist:
                    confirmed = False
                    break
            if not confirmed:
                i += 1
                continue

        direction   = +1 if is_acc else -1
        entry_price = row["close"]
        entry_time  = row["datetime"]

        # 找出场点（信号反转 / 止损 / 时间止损）
        # stop_loss 已通过参数传入
        exit_idx = min(i + max_hold, n - 1)
        for j in range(i + 1, min(i + max_hold + 1, n)):
            sig = df.iloc[j]["signal"]
            price_j = df.iloc[j]["close"]
            pnl = (price_j / entry_price - 1) * direction

            # 止损
            if pnl < -stop_loss:
                exit_idx = j
                break
            # 信号反转出场
            if direction == +1 and sig in ["distribution", "strong_distribution", "neutral"]:
                exit_idx = j
                break
            if direction == -1 and sig in ["accumulation", "strong_accumulation", "neutral"]:
                exit_idx = j
                break

        exit_price = df.iloc[exit_idx]["close"]
        hold_bars  = exit_idx - i
        net_ret    = (exit_price / entry_price - 1) * direction - cost * 2

        records.append({
            "entry_time":  entry_time,
            "signal":      signal,
            "direction":   "long" if direction == 1 else "short",
            "hold_bars":   hold_bars,
            "net_ret":     net_ret,
            "win":         net_ret > 0,
        })
        i = exit_idx + 1

    if not records:
        return pd.DataFrame()
    result = pd.DataFrame(records)
    result["cum_ret"] = (1 + result["net_ret"]).cumprod() - 1
    return result


def sdb_summary(sdb: pd.DataFrame) -> dict:
    if sdb.empty:
        return {}
    total   = len(sdb)
    avg_ret = sdb["net_ret"].mean()
    sharpe  = avg_ret / (sdb["net_ret"].std() + 1e-10) * np.sqrt(252)
    cum     = sdb["cum_ret"].iloc[-1]
    max_dd  = (sdb["cum_ret"] - sdb["cum_ret"].cummax()).min()
    long_   = sdb[sdb["direction"] == "long"]
    short_  = sdb[sdb["direction"] == "short"]
    return {
        "总交易次数":    total,
        "胜率":         f"{sdb['win'].mean()*100:.1f}%",
        "平均持仓(bar)": f"{sdb['hold_bars'].mean():.1f}",
        "平均单次收益":  f"{avg_ret*100:.3f}%",
        "累计收益":      f"{cum*100:.2f}%",
        "最大回撤":      f"{max_dd*100:.2f}%",
        "年化Sharpe":   f"{sharpe:.2f}",
        "多头胜率":      f"{long_['win'].mean()*100:.1f}%" if len(long_) else "N/A",
        "空头胜率":      f"{short_['win'].mean()*100:.1f}%" if len(short_) else "N/A",
    }


# ══════════════════════════════════════════════
# 7. 置信度分层分析
# ══════════════════════════════════════════════

def confidence_analysis(df: pd.DataFrame, forward_h: int) -> pd.DataFrame:
    """
    按信号置信度分组，看高置信度信号是否收益更好。
    如果是 → 模型有区分能力；如果没有 → 置信度分数无效。
    """
    col = f"fwd_ret_{forward_h}"
    sub = df[df["signal"].isin(["accumulation","strong_accumulation",
                                 "distribution","strong_distribution"])].copy()
    sub = sub.dropna(subset=[col, "confidence"])

    direction = sub["signal"].isin(["accumulation","strong_accumulation"]).map({True:1, False:-1})
    sub["adj_ret"] = sub[col] * direction

    sub["conf_tier"] = pd.cut(sub["confidence"],
                               bins=[0, 25, 50, 75, 100],
                               labels=["低(0-25%)", "中(25-50%)", "高(50-75%)", "极高(75%+)"])

    result = sub.groupby("conf_tier", observed=True)["adj_ret"].agg(
        count="count",
        mean_ret=lambda x: f"{x.mean()*100:.3f}%",
        hit_rate=lambda x: f"{(x>0).mean()*100:.1f}%"
    ).reset_index()
    result.columns = ["置信度区间", "信号数", "平均收益", "胜率"]
    return result


# ══════════════════════════════════════════════
# 7. 保存报告
# ══════════════════════════════════════════════

def save_report(sections: dict, input_file: str):
    stem = Path(input_file).stem
    fpath = os.path.join(REPORT_DIR, f"{stem}_backtest_report.txt")

    lines = []
    lines.append("=" * 60)
    lines.append("  INSTITUTIONAL FLOW BACKTEST REPORT")
    lines.append(f"  来源文件: {Path(input_file).name}")
    lines.append("=" * 60)

    for title, content in sections.items():
        lines.append(f"\n{'─'*55}")
        lines.append(f"  {title}")
        lines.append(f"{'─'*55}")
        if isinstance(content, pd.DataFrame):
            lines.append(content.to_string(index=False))
        elif isinstance(content, dict):
            for k, v in content.items():
                lines.append(f"  {k:<20}: {v}")
        else:
            lines.append(str(content))

    report = "\n".join(lines)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(report)
    return fpath


# ══════════════════════════════════════════════
# 8. 主程序
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Backtest Validator")
    parser.add_argument("--file",           required=True,  help="signal_generator 输出的 CSV 路径")
    parser.add_argument("--interval",       default=None,   help="时间框架: 1m/5m/15m/1h/4h/1d (不填则自动检测)")
    parser.add_argument("--forward",        default=None,   type=int, help="主持仓周期 bar 数（不填则按时间框架自动设置）")
    parser.add_argument("--cost",           default=None,   type=float, help="单边交易成本（不填则按时间框架自动设置）")
    parser.add_argument("--train",          default=None,   type=int, help="Walk-Forward 训练窗口（不填则按时间框架自动设置）")
    parser.add_argument("--min-confidence", default=0.0,    type=float, help="最低置信度过滤 0-1（默认不过滤）")
    parser.add_argument("--no-overnight",   action="store_true",        help="过滤跨收盘持仓（小时线/分钟线推荐）")
    parser.add_argument("--min-confirm",    default=2,    type=int,   help="信号持续性过滤：连续N bar同向才入场（默认2）")
    parser.add_argument("--max-hold",       default=None, type=int,   help="信号驱动回测最大持仓bar数（默认forward*4）")
    parser.add_argument("--long-only",      action="store_true",        help="只做多，不做空")
    parser.add_argument("--stop-loss",      default=0.02, type=float,   help="止损比例（默认2%%）")
    args = parser.parse_args()

    # 自动检测时间框架
    fname = Path(args.file).name
    import re as _re
    interval_match = _re.search(r"_(1m|5m|15m|30m|1h|4h|1d|1w)_", fname)
    detected = interval_match.group(1) if interval_match else (args.interval or "1d")
    interval = args.interval or detected

    # 按时间框架自动设置默认参数
    PRESETS = {
        "1m":  {"forward": 30,  "train": 2000, "cost": 0.0005, "horizons": [5, 15, 30, 60, 120]},
        "5m":  {"forward": 12,  "train": 1000, "cost": 0.0005, "horizons": [3, 6, 12, 24, 48]},
        "15m": {"forward": 8,   "train": 500,  "cost": 0.0008, "horizons": [2, 4, 8, 16, 32]},
        "30m": {"forward": 6,   "train": 300,  "cost": 0.0008, "horizons": [2, 4, 6, 12, 24]},
        "1h":  {"forward": 6,   "train": 500,  "cost": 0.001,  "horizons": [1, 3, 6, 12, 24]},
        "4h":  {"forward": 5,   "train": 200,  "cost": 0.001,  "horizons": [1, 2, 5, 10, 20]},
        "1d":  {"forward": 5,   "train": 60,   "cost": 0.001,  "horizons": [1, 3, 5, 10, 20]},
        "1w":  {"forward": 4,   "train": 30,   "cost": 0.002,  "horizons": [1, 2, 4, 8, 12]},
    }
    preset = PRESETS.get(interval, PRESETS["1d"])

    forward  = args.forward  if args.forward  is not None else preset["forward"]
    cost     = args.cost     if args.cost     is not None else preset["cost"]
    train    = args.train    if args.train    is not None else preset["train"]
    horizons = sorted(set(preset["horizons"] + [forward]))
    min_conf = args.min_confidence

    print(f"\n{'='*55}")
    print(f"  回测验证开始")
    print(f"  文件: {Path(args.file).name}")
    print(f"  时间框架: {interval} | 训练窗口: {train} bar")
    print(f"  主持仓周期: {forward} bar | 交易成本: {cost*100:.2f}%")
    if min_conf > 0:
        print(f"  最低置信度: {min_conf*100:.0f}%")
    if args.no_overnight:
        print(f"  隔夜过滤: 开启")
    print(f"{'='*55}\n")

    # 加载
    df = load_signals(args.file)

    # 置信度过滤
    if min_conf > 0:
        before = len(df)
        df = df[df["confidence"].abs() >= min_conf].reset_index(drop=True)
        print(f"[过滤] 置信度 >= {min_conf*100:.0f}%: {len(df)}/{before} bars 保留")

    # 隔夜过滤（小时线/分钟线）
    if args.no_overnight and interval in ("1m","5m","15m","30m","1h"):
        before = len(df)
        df["_et"] = df["datetime"] - pd.Timedelta(hours=4)
        df["_hm"] = df["_et"].dt.hour * 100 + df["_et"].dt.minute
        # 只保留距收盘足够距离的信号（持仓不会跨收盘）
        max_hold_mins = forward * {"1m":1,"5m":5,"15m":15,"30m":30,"1h":60}.get(interval,60)
        close_et = 1600
        cutoff = close_et - max_hold_mins
        df = df[df["_hm"] < cutoff].drop(columns=["_et","_hm"]).reset_index(drop=True)
        print(f"[过滤] 隔夜: {len(df)}/{before} bars 保留")

    df = add_forward_returns(df, horizons)

    sections = {}

    # ── Event Study
    print("[1/4] Event Study...")
    es = event_study(df, horizons, cost)
    if not es.empty:
        print("\n" + es.to_string(index=False))
        sections["Event Study — 信号后各持仓周期收益"] = es

    # ── IC 分析
    print("\n[2/4] 信息系数 (IC)...")
    ic = information_coefficient(df, horizons)
    if not ic.empty:
        print("\n" + ic.to_string(index=False))
        sections["信息系数 IC（信号强度与未来收益相关性）"] = ic

    # ── Signal-Driven Backtest
    print(f"\n[3/4] 信号驱动回测 (最大持仓={forward*4} bar)...")
    sdb = signal_driven_backtest(df, cost, max_hold=args.max_hold or forward*4, min_confirm=args.min_confirm, stop_loss=args.stop_loss, long_only=args.long_only)
    if not sdb.empty:
        summary = sdb_summary(sdb)
        print("\n信号驱动回测汇总:")
        for k, v in summary.items():
            print(f"  {k:<16}: {v}")
        by_sig = sdb.groupby("signal").apply(
            lambda g: pd.Series({
                "次数": len(g),
                "胜率": f"{g['win'].mean()*100:.1f}%",
                "平均收益": f"{g['net_ret'].mean()*100:.3f}%",
                "平均持仓": f"{g['hold_bars'].mean():.1f}bar",
            })
        ).reset_index()
        print("\n按信号类型:")
        print(by_sig.to_string(index=False))
        sections["信号驱动回测"] = summary

    # ── Walk-Forward（保留原有）
    print(f"\n[3b/4] Walk-Forward 验证 (窗口={train}, 持仓={forward})...")
    wf = walk_forward(df, train, forward, cost)
    if not wf.empty:
        summary = wf_summary(wf)
        print("\nWalk-Forward 汇总:")
        for k, v in summary.items():
            print(f"  {k:<20}: {v}")
        sections["Walk-Forward 滚动验证汇总"] = summary

        # 按信号类型拆分
        wf_by_sig = wf.groupby("signal").apply(
            lambda x: pd.Series({
                "次数": len(x),
                "胜率": f"{x['win'].mean()*100:.1f}%",
                "平均收益": f"{x['fwd_ret'].mean()*100:.3f}%",
            })
        ).reset_index()
        print("\nWalk-Forward 按信号类型:")
        print(wf_by_sig.to_string(index=False))
        sections["Walk-Forward 按信号类型分解"] = wf_by_sig

    # ── 置信度分层
    print(f"\n[4/4] 置信度分层分析 (forward={forward})...")
    ca = confidence_analysis(df, forward)
    if not ca.empty:
        print("\n" + ca.to_string(index=False))
        print("\n  解读：若高置信度区间收益/胜率更高，说明置信度分数有效。")
        sections["置信度分层分析"] = ca

    # ── 保存报告
    report_path = save_report(sections, args.file)
    print(f"\n{'='*55}")
    print(f"  [DONE] 报告已保存至: {report_path}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
