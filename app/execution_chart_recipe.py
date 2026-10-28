"""Reusable Python analysis recipe executed by OpenAI Code Interpreter.

Demo code that illustrates where customer-owned analytics can plug into an agent.
Input: scoped case_activity.json. Outputs: analysis.json and execution_pattern.png.
The application independently validates the numerical results before using them.
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from matplotlib.ticker import FuncFormatter


def main():
    """Load case data, run the supplied analytics, and return artifacts to the agent."""
    output_directory = Path("/mnt/data")

    # 1. Read the case data supplied by the application's analysis tool.
    input_path = next(output_directory.glob("*case_activity.json"))
    case_data = json.loads(input_path.read_text())

    # 2. Execute the reusable Python calculations (potentially customer-owned).
    metrics = calculate_metrics(case_data)

    # 3. Save structured results and a chart for the agent to consume.
    (output_directory / "analysis.json").write_text(json.dumps(metrics, indent=2))
    render_chart(case_data, metrics, output_directory / "execution_pattern.png")


def calculate_metrics(data):
    """Calculate volume, closing-window concentration, and cancellation metrics.

    Uses every supplied execution. The server checks these results independently
    against the same scoped source records before admitting them as evidence.
    """
    # Group executions into one-minute buy/sell buckets.
    trades = pd.DataFrame(data["fills"])
    trades["ts"] = pd.to_datetime(trades["executed_at"], utc=True)
    trades["minute_et"] = (
        trades["ts"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d %H:%M")
    )
    trades["session_day"] = (
        trades["ts"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    )
    close_map = {row["session_date"]: row["close_at"] for row in data["sessions"]}
    closes = pd.to_datetime(trades["session_day"].map(close_map), utc=True)
    if closes.isna().any():
        raise ValueError("Execution date has no exchange session")
    in_closing_window = (trades["ts"] >= closes - pd.Timedelta(minutes=5)) & (
        trades["ts"] <= closes
    )
    trades["buy_shares"] = trades["quantity"].where(trades["side"] == "buy", 0)
    trades["sell_shares"] = trades["quantity"].where(trades["side"] == "sell", 0)
    buckets = (
        trades.groupby("minute_et", sort=True)
        .agg(
            buy_shares=("buy_shares", "sum"),
            sell_shares=("sell_shares", "sum"),
            fill_count=("fill_id", "size"),
        )
        .reset_index()
    )
    total_shares = int(trades["quantity"].sum())
    closing_shares = int(trades.loc[in_closing_window, "quantity"].sum())
    venue_order_count = len(data["venue_orders"])
    cancelled_order_count = sum(
        row["cancelled_at"] is not None for row in data["venue_orders"]
    )
    return {
        "case_id": data["case_id"],
        "fill_count": len(trades),
        "total_shares": total_shares,
        "buy_shares": int(trades["buy_shares"].sum()),
        "sell_shares": int(trades["sell_shares"].sum()),
        "notional_cents": int((trades["quantity"] * trades["price_cents"]).sum()),
        "last_five_minutes_shares": closing_shares,
        "last_five_minutes_pct": 100 * closing_shares / total_shares,
        "venue_order_count": venue_order_count,
        "cancelled_venue_order_count": cancelled_order_count,
        "venue_cancellation_pct": (
            100 * cancelled_order_count / venue_order_count
            if venue_order_count
            else None
        ),
        "minute_buckets": buckets.to_dict(orient="records"),
    }


def render_chart(data, metrics, output_path):
    """Plot calculated volume and order activity with recorded event timestamps."""
    tz = ZoneInfo("America/New_York")

    def parse(timestamp):
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(tz)

    fills = sorted(data["fills"], key=lambda r: r["executed_at"])
    minutes = [
        datetime.strptime(r["minute_et"], "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        for r in metrics["minute_buckets"]
    ]
    events = sorted(data["events"], key=lambda r: r["at"])[:3]
    times = (
        minutes
        + [parse(r["executed_at"]) for r in fills]
        + [parse(r["at"]) for r in events]
    )
    times += [parse(r["submitted_at"]) for r in data["venue_orders"]]
    times += [
        parse(r["cancelled_at"]) for r in data["venue_orders"] if r["cancelled_at"]
    ]
    start = min(times) - timedelta(minutes=1)
    end = max(times) + timedelta(minutes=1)
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "legend.fontsize": 10,
        }
    )
    fig, (upper, lower) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [1.2, 1]}
    )
    fig.subplots_adjust(left=0.12, right=0.97, top=0.87, bottom=0.17, hspace=0.28)
    x = mdates.date2num(minutes)
    buy = [r["buy_shares"] for r in metrics["minute_buckets"]]
    sell = [r["sell_shares"] for r in metrics["minute_buckets"]]
    # Matplotlib datetime bar widths are DAYS, not minutes.
    minute_days = 1 / (24 * 60)
    upper.bar(
        x, buy, width=0.72 * minute_days, color="#16766e", label="Buy shares", zorder=3
    )
    upper.bar(
        x,
        sell,
        bottom=buy,
        width=0.72 * minute_days,
        color="#c99634",
        label="Sell shares",
        zorder=3,
    )
    upper.set_title("Executed shares by minute", loc="left", pad=10)
    upper.set_ylabel("Executed shares")
    upper.set_ylim(bottom=0)
    upper.legend(loc="upper right", framealpha=0.95)
    for i, event in enumerate(events):
        at = mdates.date2num(parse(event["at"]))
        upper.axvline(at, color="#6a7f86", linestyle="--", linewidth=1.2, zorder=2)
        label = (
            ("Recorded call" if "Recorded call" in event["label"] else event["label"])
            + " · "
            + parse(event["at"]).strftime("%H:%M")
        )
        near_right = at > mdates.date2num(start) + 0.65 * (
            mdates.date2num(end) - mdates.date2num(start)
        )
        upper.text(
            at + (-0.15 if near_right else 0.15) * minute_days,
            (0.78 if near_right else 0.94) - i * 0.12,
            label,
            transform=upper.get_xaxis_transform(),
            fontsize=9,
            va="top",
            ha="right" if near_right else "left",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 2},
        )
    if data["venue_orders"]:
        submissions = defaultdict(int)
        cancels = defaultdict(int)
        for row in data["venue_orders"]:
            submissions[
                parse(row["submitted_at"]).replace(second=0, microsecond=0)
            ] += 1
            if row["cancelled_at"]:
                cancels[
                    parse(row["cancelled_at"]).replace(second=0, microsecond=0)
                ] += 1
        keys = sorted(set(submissions) | set(cancels))
        xv = mdates.date2num(keys)
        lower.bar(
            xv - 0.18 * minute_days,
            [submissions[k] for k in keys],
            width=0.32 * minute_days,
            color="#16766e",
            label="Submitted",
        )
        lower.bar(
            xv + 0.18 * minute_days,
            [cancels[k] for k in keys],
            width=0.32 * minute_days,
            color="#c99634",
            label="Cancelled",
        )
        lower.set_title("Supplied venue orders by minute", loc="left", pad=10)
        lower.set_ylabel("Venue order count")
        lower.legend(loc="upper right")
        lower.set_ylim(bottom=0)
    else:
        cumulative = [0]
        points = [start]
        for row in fills:
            cumulative.append(cumulative[-1] + row["quantity"])
            points.append(parse(row["executed_at"]))
        points.append(end)
        cumulative.append(cumulative[-1])
        lower.step(points, cumulative, where="post", color="#16766e", linewidth=2)
        lower.set_title("Cumulative executed shares", loc="left", pad=10)
        lower.set_ylabel("Executed shares")
        lower.set_ylim(bottom=0)
    for axis in (upper, lower):
        axis.set_xlim(start, end)
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
        axis.grid(axis="y", color="#e2e8e8", linewidth=0.7, zorder=0)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
    lower.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    lower.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M", tz=tz))
    lower.set_xlabel("Eastern time", labelpad=8)
    symbols = ", ".join(sorted({r["security_id"] for r in data["fills"]}))
    fig.suptitle(
        f"{data['case_id']} · {symbols}\nCase execution pattern", fontsize=15, y=0.97
    )
    fig.text(
        0.5,
        0.035,
        "Linked case activity; timing does not establish intent",
        ha="center",
        fontsize=9,
        color="#64787d",
    )
    fig.savefig(output_path, dpi=140, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
