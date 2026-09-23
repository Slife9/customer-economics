"""Reusable Plotly chart builders. One consistent, brand-neutral palette."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

COLORS = {
    "revenue": "#2563eb", "cost": "#ef4444", "net_pos": "#16a34a",
    "net_neg": "#dc2626", "neutral": "#64748b", "amber": "#d97706",
}
LEVER_COLORS = {
    "L1": "#2563eb", "L2": "#7c3aed", "L3": "#0891b2", "L4": "#16a34a",
    "L5": "#d97706", "L6": "#db2777", "STRUCTURAL": "#64748b",
}


def revenue_cost_waterfall(ledger_card: pd.DataFrame, trailing_months: int = 12) -> go.Figure:
    """Trailing N months only, matching the customer view's own window - the
    executive KPI (trailing-12mo NEP) and this chart must reconcile to the
    same number, or the two halves of one page silently disagree."""
    window = sorted(ledger_card["Cycle Month"].unique())[-trailing_months:]
    led = ledger_card[ledger_card["Cycle Month"].isin(window)]
    interest = led["interest_revenue"].sum()
    interchange = led["interchange_revenue"].sum()
    fees = led["fee_revenue"].sum()
    rewards = -led["reward_expense"].sum()
    funding = -led["funding_cost"].sum()
    credit = -led["credit_cost"].sum()
    cts = -led["cost_to_serve"].sum()
    capital = -led["capital_cost"].sum()
    net = interest + interchange + fees + rewards + funding + credit + cts + capital

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative"] * 8 + ["total"],
        x=["Interest", "Interchange", "Fees", "Rewards", "Funding", "Credit Loss",
          "Cost to Serve", "Capital", "Net Economic Profit"],
        y=[interest, interchange, fees, rewards, funding, credit, cts, capital, net],
        decreasing={"marker": {"color": COLORS["cost"]}},
        increasing={"marker": {"color": COLORS["revenue"]}},
        totals={"marker": {"color": COLORS["net_pos"] if net >= 0 else COLORS["net_neg"]}},
        connector={"line": {"color": "#cbd5e1"}},
        text=[f"${v:,.0f}" for v in [interest, interchange, fees, rewards, funding,
                                     credit, cts, capital, net]],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"Card Economics — Trailing {trailing_months} Months (matches the headline NEP)",
        showlegend=False, height=460,
        yaxis_title=f"USD / trailing {trailing_months}mo", margin=dict(t=60, b=20))
    return fig


def routing_bar(routing_summary: pd.DataFrame) -> go.Figure:
    df = routing_summary.reset_index()
    colors = [LEVER_COLORS.get(r, COLORS["neutral"]) for r in df["routed_lever"]]
    fig = go.Figure(go.Bar(
        x=df["routed_lever"], y=df["total_loss"], marker_color=colors,
        text=[f"${v:,.0f}<br>{n} customers" for v, n in zip(df["total_loss"], df["customers"])],
        textposition="outside"))
    fig.update_layout(title="Below-Cost Loss, Routed by Dominant Cause",
                      xaxis_title="Routed to", yaxis_title="Annualized loss (USD)",
                      height=420, margin=dict(t=60, b=20))
    return fig


def cev_band_distribution(customer_view: pd.DataFrame) -> go.Figure:
    order = ["Detractor", "Underperforming", "Core", "Valued", "Premier"]
    counts = customer_view["cev_band"].value_counts().reindex(order).fillna(0)
    colors = ["#dc2626", "#f59e0b", "#64748b", "#2563eb", "#16a34a"]
    fig = go.Figure(go.Bar(x=order, y=counts.to_numpy(), marker_color=colors,
                          text=counts.to_numpy().astype(int), textposition="outside"))
    fig.update_layout(title="Customers by CEV Band", xaxis_title="Band",
                      yaxis_title="Customers", height=380, margin=dict(t=60, b=20))
    return fig


def relationship_view_chart(customer_view: pd.DataFrame) -> go.Figure:
    cv = customer_view
    covers = int(cv["relationship_covers_card_loss"].sum())
    card_loss_total = int((cv["card_only_net_economic_profit"] < 0).sum())
    still_loss = card_loss_total - covers
    fig = go.Figure(go.Bar(
        y=["Card-only view", "Full relationship view"],
        x=[card_loss_total, still_loss],
        orientation="h", marker_color=COLORS["net_neg"],
        text=[card_loss_total, still_loss], textposition="outside", name="Still below cost"))
    fig.add_trace(go.Bar(
        y=["Full relationship view"], x=[covers], orientation="h",
        marker_color=COLORS["net_pos"], text=[covers], textposition="outside",
        name="Covered by deposits/loans"))
    fig.update_layout(barmode="stack", title="Card-Only Loss vs. Full Relationship View",
                      xaxis_title="Customers", height=280, margin=dict(t=60, b=20),
                      legend=dict(orientation="h", y=-0.25))
    return fig


def gate_chart(gate_report: pd.DataFrame) -> go.Figure:
    df = gate_report[gate_report["lever"] != "DEFECTS"].copy()
    status_color = {"PASS": "#16a34a", "FAIL": "#dc2626", "INCONCLUSIVE": "#94a3b8"}
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Driver ratio (control/demo)", x=df["lever"],
                         y=df["driver_ratio"], marker_color="#94a3b8"))
    fig.add_trace(go.Bar(name="Value ratio (control/demo)", x=df["lever"],
                         y=df["value_ratio"],
                         marker_color=[status_color.get(s, "#94a3b8") for s in df["status"]]))
    fig.add_hline(y=1.0, line_dash="dot", line_color="#334155")
    fig.update_layout(barmode="group", title="Negative Control Gate — Value Must Fall At Least as Fast as Its Driver",
                      yaxis_title="Ratio to demo book (lower = more suppressed in the control)",
                      height=420, margin=dict(t=60, b=20))
    return fig


def fairness_chart(fairness_df: pd.DataFrame, title: str) -> go.Figure:
    if not len(fairness_df):
        return go.Figure()
    df = fairness_df.sort_values("ratio_to_population")
    colors = ["#dc2626" if not p else "#16a34a" for p in df["passes"]]
    fig = go.Figure(go.Bar(x=df["group"], y=df["ratio_to_population"], marker_color=colors,
                          text=df["n"], textposition="outside"))
    fig.add_hline(y=0.80, line_dash="dash", line_color="#334155",
                 annotation_text="four-fifths threshold")
    fig.update_layout(title=title, yaxis_title="Selection rate ÷ population rate",
                      height=440, margin=dict(t=60, b=120))
    fig.update_xaxes(tickangle=-60)
    return fig


def leakage_bar(leakage_df: pd.DataFrame) -> go.Figure:
    df = leakage_df.copy()
    df["value"] = df["priced_value_usd"].fillna(0.0)
    df["kind"] = df["priced_value_usd"].apply(lambda v: "Priced" if pd.notna(v) else "Unpriced context")
    df.loc[df["kind"] == "Unpriced context", "value"] = df["unpriced_context_usd"].fillna(0.0)
    colors = [LEVER_COLORS.get(l, COLORS["neutral"]) for l in df["lever"]]
    patterns = ["" if k == "Priced" else "/" for k in df["kind"]]
    fig = go.Figure(go.Bar(x=df["lever"], y=df["value"], marker_color=colors,
                          marker_pattern_shape=patterns,
                          text=[f"${v:,.0f}<br>{k}" for v, k in zip(df["value"], df["kind"])],
                          textposition="outside"))
    fig.update_layout(title="Value by Lever (solid = priced, hatched = unpriced context only)",
                      yaxis_title="USD / year", height=420, margin=dict(t=60, b=20))
    return fig
