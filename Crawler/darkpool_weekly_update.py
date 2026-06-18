"""
FINRA Dark Pool Weekly Update Script
=====================================
定时运行，自动拉取最新一周的暗池数据存入 ClickHouse。

部署方式（服务器 crontab）：
  # 每周一 UTC 10:00 运行（FINRA 约每周一发布上上周数据）
  0 10 * * 1 cd /path/to/repo && python3 darkpool_weekly_update.py >> logs/darkpool.log 2>&1

  # 或者每天跑一次，自动跳过已有的周
  0 10 * * * cd /path/to/repo && python3 darkpool_weekly_update.py >> logs/darkpool.log 2>&1

环境变量（在服务器上设置）：
  FINRA_CLIENT_ID      FINRA API Client ID
  FINRA_CLIENT_SECRET  FINRA API Client Secret
  CH_HOST              ClickHouse host
  CH_PORT              ClickHouse port (default: 8123)
  CH_USER              ClickHouse user (default: default)
  CH_PASSWORD          ClickHouse password
  CH_DATABASE          ClickHouse database (default: default)

用法：
  python3 darkpool_weekly_update.py           # 更新所有 tier
  python3 darkpool_weekly_update.py --tier T1 # 只更新 T1
  python3 darkpool_weekly_update.py --dry-run # 只打印要更新的周，不写入
"""

import argparse
import base64
import os
import time
from datetime import datetime, timedelta

import requests

# ── 配置（优先读环境变量，fallback 到默认值）
FINRA_CLIENT_ID     = os.getenv("FINRA_CLIENT_ID",     "3971122ba9964bacb25c")
FINRA_CLIENT_SECRET = os.getenv("FINRA_CLIENT_SECRET", "alskdj789123.")
FINRA_TOKEN_URL     = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token?grant_type=client_credentials"

CH_HOST     = os.getenv("CH_HOST",     "104.192.7.156")
CH_PORT     = int(os.getenv("CH_PORT", "8123"))
CH_USER     = os.getenv("CH_USER",     "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "Admin1234")
CH_DATABASE = os.getenv("CH_DATABASE", "default")

TABLE_NAME  = "darkpool_finra"

# Tier 配置
TIER_CONFIG = {
    "T1": {
        "endpoint_recent":  "weeklySummary",
        "endpoint_historic": "weeklySummaryHistoric",
        "historic_cutoff":   "2025-06-09",  # Historic 最新可用周
        "recent_delay_weeks": 3,             # T1 延迟约 3 周
    },
    "T2": {
        "endpoint_recent":  "weeklySummary",
        "endpoint_historic": "weeklySummaryHistoric",
        "historic_cutoff":   "2025-06-09",
        "recent_delay_weeks": 4,             # T2 延迟约 4 周
    },
    "OTCE": {
        "endpoint_recent":  "weeklySummary",
        "endpoint_historic": "weeklySummaryHistoric",
        "historic_cutoff":   "2025-06-09",
        "recent_delay_weeks": 4,
    },
}


def get_finra_token() -> str:
    creds = base64.b64encode(
        f"{FINRA_CLIENT_ID}:{FINRA_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post(
        FINRA_TOKEN_URL,
        headers={"Authorization": f"Basic {creds}"},
        timeout=30
    )
    token = r.json().get("access_token")
    if not token:
        raise Exception(f"Token failed: {r.text}")
    print(f"[FINRA] Token OK (expires in {int(r.json().get('expires_in',0))//3600}h)")
    return token


def get_ch_client():
    import clickhouse_connect
    client = clickhouse_connect.get_client(
        host=CH_HOST, port=CH_PORT,
        username=CH_USER, password=CH_PASSWORD,
        database=CH_DATABASE, compress=True
    )
    print(f"[CH] Connected to {CH_HOST}:{CH_PORT}/{CH_DATABASE}")
    return client


def get_existing_weeks(ch, tier: str) -> set:
    """获取数据库中该 tier 已有的周"""
    r = ch.query(
        f"SELECT DISTINCT week_start FROM {TABLE_NAME} WHERE tier = '{tier}'"
    )
    return {str(row[0]) for row in r.result_rows}


def get_latest_monday() -> datetime:
    """获取最近的周一"""
    today = datetime.now()
    days_since_monday = today.weekday()
    return today - timedelta(days=days_since_monday)


def get_available_weeks(token: str, tier: str, n_weeks: int = 60) -> list:
    """
    找到该 tier 当前可用的所有周（自动处理延迟）
    返回从新到旧排列的日期列表
    """
    config = TIER_CONFIG[tier]
    delay  = config["recent_delay_weeks"]

    # 最新可用周 = 今天往前推 delay 周的周一
    latest = get_latest_monday() - timedelta(weeks=delay)
    # 向前取整到周一
    latest = latest - timedelta(days=latest.weekday())

    available = []
    d = latest
    cutoff = datetime(2024, 6, 10)  # 我们数据的起始日期

    while d >= cutoff and len(available) < n_weeks:
        date_str = d.strftime("%Y-%m-%d")
        is_historic = date_str <= config["historic_cutoff"]
        endpoint = config["endpoint_historic"] if is_historic else config["endpoint_recent"]

        if is_historic:
            payload = {"limit": 1, "compareFilters": [
                {"fieldName": "weekStartDate", "fieldValue": date_str, "compareType": "EQUAL"},
                {"fieldName": "tierIdentifier", "fieldValue": tier,     "compareType": "EQUAL"}
            ]}
        else:
            payload = {"limit": 1,
                       "dateRangeFilters": [{"fieldName": "weekStartDate", "startDate": date_str, "endDate": date_str}],
                       "compareFilters":   [{"fieldName": "tierIdentifier", "fieldValue": tier, "compareType": "EQUAL"}]}

        resp = requests.post(
            f"https://api.finra.org/data/group/otcMarket/name/{endpoint}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json=payload, timeout=15
        )
        if resp.status_code == 200 and resp.text:
            data = resp.json()
            if isinstance(data, list) and data:
                available.append(date_str)

        d -= timedelta(weeks=1)
        time.sleep(0.2)

    return available


def fetch_week(token: str, week: str, tier: str, config: dict) -> list:
    """拉取某周某 tier 的全量数据"""
    is_historic = week <= config["historic_cutoff"]
    endpoint    = config["endpoint_historic"] if is_historic else config["endpoint_recent"]
    week_date   = datetime.strptime(week, "%Y-%m-%d").date()

    rows   = []
    offset = 0

    while True:
        if is_historic:
            payload = {"limit": 5000, "offset": offset, "compareFilters": [
                {"fieldName": "weekStartDate", "fieldValue": week, "compareType": "EQUAL"},
                {"fieldName": "tierIdentifier", "fieldValue": tier,  "compareType": "EQUAL"}
            ]}
        else:
            payload = {"limit": 5000, "offset": offset,
                       "dateRangeFilters": [{"fieldName": "weekStartDate", "startDate": week, "endDate": week}],
                       "compareFilters":   [{"fieldName": "tierIdentifier", "fieldValue": tier, "compareType": "EQUAL"}]}

        resp = requests.post(
            f"https://api.finra.org/data/group/otcMarket/name/{endpoint}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json=payload, timeout=30
        )
        data = resp.json() if resp.status_code == 200 and isinstance(resp.json(), list) else []
        if not data:
            break

        now = datetime.now()
        for row in data:
            rows.append([
                row.get("issueSymbolIdentifier") or "",
                week_date,
                row.get("MPID") or "",
                row.get("marketParticipantName") or "",
                row.get("tierIdentifier") or tier,
                int(float(row.get("totalWeeklyShareQuantity") or 0)),
                int(row.get("totalWeeklyTradeCount") or 0),
                float(row.get("totalNotionalSum") or 0),
                0, 0.0,
                now,  # created_at
                now,  # updated_at
            ])

        if len(data) < 5000:
            break
        offset += 5000
        time.sleep(0.5)

    return rows


def main():
    parser = argparse.ArgumentParser(description="FINRA Dark Pool Weekly Update")
    parser.add_argument("--tier",    default="all", choices=["T1", "T2", "OTCE", "all"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--weeks",   default=4, type=int, help="检查最近 N 周（默认4周）")
    args = parser.parse_args()

    tiers = ["T1", "T2", "OTCE"] if args.tier == "all" else [args.tier]

    token = get_finra_token()
    token_time = time.time()

    ch = None if args.dry_run else get_ch_client()

    for tier in tiers:
        print(f"\n{'='*50}")
        print(f"[{tier}] Checking for new weeks...")
        config = TIER_CONFIG[tier]

        # 已有的周
        existing = get_existing_weeks(ch, tier) if not args.dry_run else set()

        # 最新可用的周
        available = get_available_weeks(token, tier, n_weeks=args.weeks)
        new_weeks  = [w for w in available if w not in existing]

        print(f"[{tier}] Available: {len(available)} weeks, New: {len(new_weeks)} weeks")

        if not new_weeks:
            print(f"[{tier}] Already up to date ✅")
            continue

        if args.dry_run:
            print(f"[{tier}] Would insert: {new_weeks}")
            continue

        total = 0
        for i, week in enumerate(new_weeks):
            # Token 刷新
            if time.time() - token_time > 36000:
                token = get_finra_token()
                token_time = time.time()

            rows = fetch_week(token, week, tier, config)

            if rows:
                ch.insert(TABLE_NAME, rows,
                    column_names=["ticker", "week_start", "ats_mpid", "ats_name", "tier",
                                  "ats_shares", "ats_trades", "total_notional",
                                  "total_dark_shares", "dark_pool_pct",
                                  "created_at", "updated_at"])
                total += len(rows)

            print(f"  [{i+1}/{len(new_weeks)}] {week}: {len(rows):,} rows (total: {total:,})")
            time.sleep(1)

        print(f"[{tier}] Done: inserted {total:,} rows")

    # 最终统计
    if not args.dry_run:
        r = ch.query(f"SELECT tier, count(), max(week_start) FROM {TABLE_NAME} GROUP BY tier ORDER BY tier")
        print(f"\n{'='*50}")
        print("DB Summary:")
        for row in r.result_rows:
            print(f"  {row[0]}: {row[1]:,} rows, latest={row[2]}")

    print(f"\n[Done] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
