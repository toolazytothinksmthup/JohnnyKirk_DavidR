import io
import json
import math
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ==============================================================================
# CAREER VENTURE LAB - STREAMLIT DASHBOARD (STAGE 1)
# Team ID: JohnnyKirk | Course: AP Calculus | Pathway: AER-3 (Advanced)
# Business: Engineering / Aerospace - Drone Inspection Service
# ==============================================================================

st.set_page_config(
    page_title="Career Venture Lab | Team JohnnyKirk (AER-3)",
    page_icon="🚁",
    layout="wide",
)

TWOPLACES = Decimal("0.01")

EMBEDDED_FIXTURE_CSV = """month,requested,capacity_override,ad_cost
2027-01,50,40,0
2027-02,55,40,100
2027-03,45,30,0
"""


def d_money(val) -> Decimal:
    return Decimal(str(val)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def fmt_usd(val) -> str:
    d = d_money(val)
    if d < 0:
        return f"-${abs(d):,.2f}"
    return f"${d:,.2f}"


def default_state() -> dict:
    return {
        "team_id": "JohnnyKirk",
        "course": "AP Calculus",
        "pathway_id": "AER-3",
        "snapshot_id": "snap_001",
        "state_version": 1,
        "simulation_date": "2027-01-31",
        "base_period": "monthly",
        "working_days": 20,
        "currency": "USD",
        "random_seed": 2027,
        "level_by_skill": {
            "Constrained Optimization & Rate Analysis": "Advanced"
        },
        "assumptions": [
            "All startup and monthly values are fictional teaching defaults from Handbook AER-3.",
            "No backlog by default; unmet monthly inspection requests are lost demand.",
            "Borrowing, interest, refunds, depreciation, and sales tax are disabled at baseline.",
            "Linear demand model q(p) = 100 - (50/35)*p is an illustrative continuous model; actual sales are floored to whole completed inspections.",
        ],
        "sources": [
            "Career Venture Lab Student Handbook (Revised Edition, Nov 2026) - Pathway AER-3 & AP Calculus Adapter"
        ],
        "offerings": [
            {
                "offering_id": "OFF-ROOF-01",
                "name": "Roof inspection (Primary)",
                "unit": "inspection",
                "price": "35.00",
                "demand_rule": "q(p) = max(0, 100 - (50/35)*p)",
                "capacity_rule": "min(floor(staff_hours/hours_per_unit), equipment_slots, floor(battery_minutes_available/flight_minutes_per_job))",
            },
            {
                "offering_id": "OFF-SOLAR-02",
                "name": "Solar-panel inspection (Stage 2+ separate allocation)",
                "unit": "inspection",
                "price": "35.00",
                "demand_rule": "Disabled in Stage 1 acceptance baseline",
                "capacity_rule": "Requires separate capacity allocation",
            },
            {
                "offering_id": "OFF-SITE-03",
                "name": "Site progress survey (Stage 2+ separate allocation)",
                "unit": "survey",
                "price": "35.00",
                "demand_rule": "Disabled in Stage 1 acceptance baseline",
                "capacity_rule": "Requires separate capacity allocation",
            },
        ],
        "funding": {
            "owner_contribution": "8000.00",
            "equipment_assets": "4200.00",
            "pre_opening_expense": "800.00",
            "opening_inventory": "0.00",
            "opening_cash": "3000.00",
            "retained_earnings": "-800.00",
            "loan_principal": "0.00",
            "interest": "0.00",
            "additional_capex": "0.00",
            "refund_amount": "0.00",
        },
        "inputs": {
            "base_price": 35.0,
            "D0": 50,
            "requested_demand": 50,
            "staff_hours": 80.0,
            "hours_per_unit": 2.0,
            "equipment_slots": 40,
            "flight_minutes_per_job": 20.0,
            "battery_minutes_available": 800.0,
            "own_marketing_expense": 0.0,
        },
        "cost_lines": {
            "variable": {
                "field_labor": 4.00,
                "travel": 3.00,
                "maintenance_consumables": 2.00,
                "report_delivery": 1.00,
            },
            "fixed": {
                "insurance_assumption": 150.00,
                "software": 100.00,
                "equipment_maintenance": 100.00,
                "workspace_admin": 150.00,
            },
        },
        "capacity": {},
        "ledger": [],
        "processed_run_ids": [],
        "campaigns": [],
        "decisions": [],
    }


def compute_normal_capacity(inputs: dict) -> dict:
    staff_cap = math.floor(inputs["staff_hours"] / inputs["hours_per_unit"]) if inputs["hours_per_unit"] > 0 else 0
    equip_cap = int(inputs["equipment_slots"])
    battery_cap = (
        math.floor(inputs["battery_minutes_available"] / inputs["flight_minutes_per_job"])
        if inputs["flight_minutes_per_job"] > 0
        else 0
    )
    effective_cap = max(0, min(staff_cap, equip_cap, battery_cap))
    bottlenecks = []
    if staff_cap == effective_cap:
        bottlenecks.append("Staff Hours")
    if equip_cap == effective_cap:
        bottlenecks.append("Equipment Slots")
    if battery_cap == effective_cap:
        bottlenecks.append("Battery Minutes")
    return {
        "staff_cap": staff_cap,
        "equip_cap": equip_cap,
        "battery_cap": battery_cap,
        "effective_capacity": effective_cap,
        "bottleneck": ", ".join(bottlenecks),
    }


def run_monthly_step(
    state: dict,
    run_id: str,
    sim_date: str,
    price: float,
    requested: int,
    ad_cost: float,
    capacity_override: int | None = None,
    capex_outflow: float = 0.0,
    refund_amount: float = 0.0,
    interest_expense: float = 0.0,
    principal_repayment: float = 0.0,
    new_owner_cash: float = 0.0,
    new_loan_cash: float = 0.0,
) -> tuple[bool, str, dict | None]:
    if run_id in state["processed_run_ids"]:
        return False, f"Duplicate run_id '{run_id}' rejected: transaction already recorded.", None

    if price <= 0 or requested < 0 or ad_cost < 0 or capex_outflow < 0:
        return False, "Invalid negative or zero input detected.", None

    if capacity_override is not None:
        capacity = int(capacity_override)
        mode_label = "FIXTURE_OVERRIDE"
    else:
        cap_info = compute_normal_capacity(state["inputs"])
        capacity = cap_info["effective_capacity"]
        mode_label = "NORMAL_DERIVED"

    sold = max(0, min(int(requested), capacity))
    unserved = max(0, int(requested) - sold)

    p_dec = d_money(price)
    var_unit = sum(d_money(v) for v in state["cost_lines"]["variable"].values())
    fixed_total = sum(d_money(v) for v in state["cost_lines"]["fixed"].values())
    ad_dec = d_money(ad_cost)
    capex_dec = d_money(capex_outflow)
    refund_dec = d_money(refund_amount)
    interest_dec = d_money(interest_expense)
    principal_dec = d_money(principal_repayment)
    owner_in_dec = d_money(new_owner_cash)
    loan_in_dec = d_money(new_loan_cash)

    gross_revenue = (p_dec * Decimal(sold)).quantize(TWOPLACES)
    net_revenue = gross_revenue - refund_dec
    var_expense = (var_unit * Decimal(sold)).quantize(TWOPLACES)
    operating_profit = net_revenue - var_expense - fixed_total - ad_dec
    net_profit = operating_profit - interest_dec

    opening_cash = d_money(state["funding"]["opening_cash"])
    closing_cash = (
        opening_cash
        + net_revenue
        - var_expense
        - fixed_total
        - ad_dec
        - interest_dec
        - principal_dec
        - capex_dec
        + owner_in_dec
        + loan_in_dec
    )

    v_num = state["state_version"]

    def add_tx(event_type: str, category: str, amount: Decimal, qty: int = 0, u_price: Decimal = Decimal("0.00"), fin_type: str = "operating"):
        if amount == Decimal("0.00") and event_type != "zero_sales_check":
            return
        state["ledger"].append(
            {
                "transaction_id": f"TX-{run_id}-{len(state['ledger']) + 1:03d}",
                "run_id": run_id,
                "date": sim_date,
                "event_type": event_type,
                "category": category,
                "amount": str(amount),
                "quantity": qty,
                "unit_price": str(u_price),
                "offering_id": "OFF-ROOF-01",
                "campaign_id": f"CAMP-{run_id}" if category == "marketing" else None,
                "financing_type": fin_type,
                "state_version": v_num,
                "mode": mode_label,
            }
        )

    if sold > 0:
        add_tx("revenue", "inspection_sales", gross_revenue, qty=sold, u_price=p_dec)
        add_tx("expense", "variable_inspection_cost", -var_expense, qty=sold, u_price=var_unit)
    else:
        add_tx("zero_sales_check", "no_completed_inspections", Decimal("0.00"), qty=0, u_price=p_dec)

    add_tx("expense", "fixed_monthly_overhead", -fixed_total, qty=1, u_price=fixed_total)
    if ad_dec > 0:
        add_tx("expense", "marketing", -ad_dec, qty=1, u_price=ad_dec)
    if refund_dec > 0:
        add_tx("contra_revenue", "customer_refund", -refund_dec, qty=1, u_price=refund_dec)
    if capex_dec > 0:
        add_tx("capex", "equipment_replacement", -capex_dec, qty=1, u_price=capex_dec, fin_type="investing")
    if interest_dec > 0:
        add_tx("expense", "loan_interest", -interest_dec, qty=1, u_price=interest_dec, fin_type="financing")
    if principal_dec > 0:
        add_tx("financing", "loan_principal_repayment", -principal_dec, qty=1, u_price=principal_dec, fin_type="financing")
    if owner_in_dec > 0:
        add_tx("financing", "owner_contribution", owner_in_dec, qty=1, u_price=owner_in_dec, fin_type="financing")
    if loan_in_dec > 0:
        add_tx("financing", "loan_proceeds", loan_in_dec, qty=1, u_price=loan_in_dec, fin_type="financing")

    state["funding"]["opening_cash"] = str(closing_cash)
    state["funding"]["equipment_assets"] = str(d_money(state["funding"]["equipment_assets"]) + capex_dec)
    state["funding"]["retained_earnings"] = str(d_money(state["funding"]["retained_earnings"]) + net_profit)
    state["simulation_date"] = sim_date
    state["state_version"] = v_num + 1
    state["snapshot_id"] = f"snap_{state['state_version']:03d}"
    state["processed_run_ids"].append(run_id)

    total_expense = var_expense + fixed_total + ad_dec + interest_dec
    summary = {
        "month": sim_date[:7],
        "run_id": run_id,
        "requested": int(requested),
        "capacity": capacity,
        "sold": sold,
        "unserved": unserved,
        "revenue": float(net_revenue),
        "total_expense": float(total_expense),
        "profit": float(net_profit),
        "closing_cash": float(closing_cash),
        "mode": mode_label,
    }
    return True, f"Recorded run '{run_id}' -> Advanced to v{state['state_version']}.", summary


def validate_and_import_snapshot(raw_json: str, expected_team: str = "JohnnyKirk", min_version: int = 1) -> tuple[bool, str, dict | None]:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {e}", None

    required_keys = [
        "team_id",
        "course",
        "pathway_id",
        "snapshot_id",
        "state_version",
        "simulation_date",
        "base_period",
        "working_days",
        "currency",
        "level_by_skill",
        "assumptions",
        "sources",
        "offerings",
        "funding",
        "cost_lines",
        "ledger",
    ]
    missing = [k for k in required_keys if k not in data]
    if missing:
        return False, f"Import rejected: missing required fields {missing}.", None

    if data.get("team_id") != expected_team:
        return False, f"Import rejected: wrong team_id '{data.get('team_id')}' (expected '{expected_team}').", None

    incoming_version = data.get("state_version")
    if not isinstance(incoming_version, int) or incoming_version < min_version:
        return (
            False,
            f"Import rejected: stale state_version v{incoming_version} (current state is v{min_version}).",
            None,
        )

    inputs = data.get("inputs", {})
    if inputs.get("base_price", 1) <= 0 or inputs.get("D0", 0) < 0 or inputs.get("staff_hours", 0) < 0:
        return False, "Import rejected: invalid negative or zero operational inputs.", None

    tx_ids = [tx.get("transaction_id") for tx in data.get("ledger", [])]
    if len(tx_ids) != len(set(tx_ids)):
        return False, "Import rejected: duplicate transaction_id detected in ledger.", None

    return True, f"Snapshot '{data['snapshot_id']}' (v{incoming_version}) validated and loaded.", data


# ------------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# ------------------------------------------------------------------------------
if "biz_state" not in st.session_state:
    st.session_state.biz_state = default_state()
if "fixture_results" not in st.session_state:
    st.session_state.fixture_results = []

state = st.session_state.biz_state

# ------------------------------------------------------------------------------
# SIDEBAR: PERSISTENT SNAPSHOT SAVE / LOAD & STAGE STATUS
# ------------------------------------------------------------------------------
with st.sidebar:
    st.header("🚁 Team JohnnyKirk")
    st.caption("Course: **AP Calculus** | Pathway: **AER-3**")
    st.metric("Current State Version", f"v{state['state_version']}", delta=state["snapshot_id"])
    st.metric("Spendable Cash", fmt_usd(state["funding"]["opening_cash"]))

    st.divider()
    st.subheader("💾 Durable Save / Load JSON")
    st.caption("Browser memory resets on refresh. Export JSON to save progress.")

    snapshot_json_str = json.dumps(state, indent=2)
    st.download_button(
        label="⬇️ Export Snapshot JSON",
        data=snapshot_json_str,
        file_name=f"{state['team_id']}_{state['pathway_id']}_v{state['state_version']}.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded_file = st.file_uploader("⬆️ Import Snapshot JSON", type=["json"])
    if uploaded_file is not None:
        raw_text = uploaded_file.read().decode("utf-8")
        if st.button("Validate & Load Snapshot", use_container_width=True):
            ok, msg, loaded = validate_and_import_snapshot(
                raw_text, expected_team="JohnnyKirk", min_version=state["state_version"]
            )
            if ok and loaded is not None:
                st.session_state.biz_state = loaded
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    if st.button("🔄 Reset to AER-3 Teaching Defaults", use_container_width=True):
        st.session_state.biz_state = default_state()
        st.session_state.fixture_results = []
        st.rerun()

    st.divider()
    st.subheader("📋 Build Roadmap Status")
    st.success("✅ **Stage 1 (Active):** Inputs, AP Calculus Engine, Ledger, Save/Load JSON, Fixture Tests")
    st.info("⏳ **Stage 2 (Placeholder):** Departmental AI Tabs, Full Report Center, Costed Marketing Studio")
    st.info("⏳ **Stage 3 (Placeholder):** Snapshot Practice Assessments, Cross-Course Artifacts")
    st.info("⏳ **Stage 4 (Optional):** Demonstration Storefront")

# ------------------------------------------------------------------------------
# MAIN NAVIGATION TABS
# ------------------------------------------------------------------------------
tabs = st.tabs(
    [
        "1. Overview & Math Panel",
        "2. Inputs & Funding",
        "3. Ledger & Fixture Tests",
        "4. Stage 2–4 Placeholders",
    ]
)

# ==============================================================================
# TAB 1: OVERVIEW & PERSISTENT AP CALCULUS PANEL
# ==============================================================================
with tabs[0]:
    st.title("Career Venture Lab — Drone Inspection Service (AER-3)")
    st.markdown(
        f"**Team:** `{state['team_id']}` | **Course:** `{state['course']}` | "
        f"**Approved Challenge Level:** `{state['level_by_skill']['Constrained Optimization & Rate Analysis']}` | "
        f"**Date:** `{state['simulation_date']}`"
    )

    cap_now = compute_normal_capacity(state["inputs"])
    var_now = sum(state["cost_lines"]["variable"].values())
    fix_now = sum(state["cost_lines"]["fixed"].values())
    sold_now = min(state["inputs"]["requested_demand"], cap_now["effective_capacity"])
    rev_now = state["inputs"]["base_price"] * sold_now
    prof_now = rev_now - (var_now * sold_now) - fix_now - state["inputs"]["own_marketing_expense"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Post-Startup Cash", fmt_usd(state["funding"]["opening_cash"]))
    c2.metric("Normal Capacity", f"{cap_now['effective_capacity']} / mo", help=f"Bottleneck: {cap_now['bottleneck']}")
    c3.metric("Baseline Demand (D0)", f"{state['inputs']['requested_demand']} / mo")
    c4.metric("Projected Monthly Profit", fmt_usd(prof_now))
    c5.metric("Bottleneck Resource", cap_now["bottleneck"])

    st.divider()

    st.subheader("📐 Math Skills & Challenge Level Panel (AP Calculus)")
    level_choice = st.radio(
        "Select Challenge Mode (Teacher-Approved Level: Advanced):",
        ["Foundation", "Applied", "Advanced"],
        index=2,
        horizontal=True,
    )

    p0 = float(state["inputs"]["base_price"])
    D0 = float(state["inputs"]["D0"])
    v_cost = float(var_now)
    F_cost = float(fix_now)
    cap_limit = float(cap_now["effective_capacity"])

    a_coef = 2.0 * D0
    b_coef = D0 / p0 if p0 > 0 else 1.0
    p_max = 2.0 * p0
    p_unconstrained = (a_coef + b_coef * v_cost) / (2.0 * b_coef)
    p_corner = max(0.0, (a_coef - cap_limit) / b_coef)

    if level_choice == "Foundation":
        st.markdown(
            f"""
            **Business Question:** What inspection price $p$ maximizes unconstrained monthly profit before checking drone/staff capacity?  
            **Equations:** Demand $q(p) = {a_coef:.2f} - {b_coef:.4f}p$ on $0 \le p \le {p_max:.2f}$;  
            Unconstrained Profit $P(p) = (p - {v_cost:.2f})({a_coef:.2f} - {b_coef:.4f}p) - {F_cost:.2f}$;  
            Derivative $P'(p) = {a_coef + b_coef*v_cost:.4f} - {2*b_coef:.4f}p$ (units: dollars per dollar of price).  
            **Critical Point:** $P'(p) = 0 \implies p^* = \mathbf{{\${p_unconstrained:.2f}}}$, giving $q({p_unconstrained:.2f}) = {a_coef - b_coef*p_unconstrained:.2f}$ inspections.
            """
        )
    elif level_choice == "Applied":
        st.markdown(
            f"""
            **Business Question:** How does the physical capacity ceiling ($q \le {cap_limit:.0f}$ inspections/month) change the optimal price?  
            **Piecewise Model:** $s(p) = \min({cap_limit:.0f}, \max(0, {a_coef:.2f} - {b_coef:.4f}p))$.  
            - On the capacity-capped branch ($p < \${p_corner:.2f}$): $P(p) = {cap_limit:.0f}(p - {v_cost:.2f}) - {F_cost:.2f}$ and $P'(p) = \mathbf{{{cap_limit:.0f}}}$ $/dollar.  
            - On the demand-limited branch ($p > \${p_corner:.2f}$): $P'(p) = {a_coef + b_coef*v_cost:.4f} - {2*b_coef:.4f}p$.  
            - **Capacity Corner:** $p = \mathbf{{\${p_corner:.2f}}}$ (derivative is **undefined** at this corner because left-hand slope $\neq$ right-hand slope).
            """
        )
    else:
        st.markdown(
            f"""
            **Business Question (Advanced):** How do capacity corners, demand uncertainty ($0.90\times, 1.00\times, 1.10\times$), and time-dependent campaign rates affect profit accumulation?  
            **Model & Assumptions:** Continuous piecewise profit $P(p)$ is plotted alongside $P'(p)$ (without differentiating `floor()`). Scenario multipliers are teaching assumptions, not statistical confidence bounds.  
            **Interpretation Prompt:** *Why is the unconstrained critical point $p = \${p_unconstrained:.2f}$ infeasible when capacity is {cap_limit:.0f} inspections/month, and what happens if demand drops by 10%?*
            """
        )

    test_price = st.slider(
        "Explore Inspection Price p ($ USD) — Continuous Model vs. Whole-Unit Sales:",
        min_value=0.0,
        max_value=float(p_max),
        value=float(p0),
        step=0.5,
    )

    prices = np.linspace(0.0, p_max, 281)
    q_unconstrained = np.maximum(0.0, a_coef - b_coef * prices)
    s_constrained = np.minimum(cap_limit, q_unconstrained)
    profit_unconstrained = (prices - v_cost) * q_unconstrained - F_cost
    profit_constrained = (prices - v_cost) * s_constrained - F_cost

    deriv_vals = np.where(
        prices < p_corner - 1e-6,
        cap_limit,
        np.where(prices > p_corner + 1e-6, a_coef + b_coef * v_cost - 2.0 * b_coef * prices, np.nan),
    )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        subplot_titles=(
            f"Monthly Profit P(p) — Constrained vs. Unconstrained (Continuous Projection, {state['snapshot_id']})",
            "Marginal Rate of Profit P'(p) ($ profit per $1 price change)",
        ),
    )

    fig.add_trace(
        go.Scatter(x=prices, y=profit_constrained, name="Constrained Profit P(p)", line=dict(color="#1f77b4", width=3)),
        row=1,
        col=1,
    )
    if level_choice == "Foundation":
        fig.add_trace(
            go.Scatter(
                x=prices,
                y=profit_unconstrained,
                name="Unconstrained Profit (Ignores Capacity)",
                line=dict(color="#ff7f0e", dash="dash"),
            ),
            row=1,
            col=1,
        )
    if level_choice == "Advanced":
        for mult, label, dash_style in [(1.10, "Upside Demand (1.10x)", "dot"), (0.90, "Downside Demand (0.90x)", "dashdot")]:
            q_scen = np.maximum(0.0, mult * (a_coef - b_coef * prices))
            s_scen = np.minimum(cap_limit, q_scen)
            p_scen = (prices - v_cost) * s_scen - F_cost
            fig.add_trace(
                go.Scatter(x=prices, y=p_scen, name=label, line=dict(dash=dash_style, width=1.8)),
                row=1,
                col=1,
            )

    fig.add_hline(y=0, line_color="black", line_width=1, row=1, col=1)
    fig.add_vline(x=p_corner, line_dash="dash", line_color="#d62728", row=1, col=1)
    fig.add_vline(x=test_price, line_dash="dot", line_color="#2ca02c", row=1, col=1)

    fig.add_trace(
        go.Scatter(x=prices, y=deriv_vals, name="Piecewise Derivative P'(p)", line=dict(color="#9467bd", width=2.5)),
        row=2,
        col=1,
    )
    fig.add_hline(y=0, line_color="black", line_width=1, row=2, col=1)
    fig.add_vline(x=p_corner, line_dash="dash", line_color="#d62728", row=2, col=1)

    fig.update_layout(height=560, hovermode="x unified", legend=dict(orientation="h", y=1.08))
    fig.update_xaxes(title_text="Price per Inspection p ($ USD)", row=2, col=1)
    fig.update_yaxes(title_text="Profit ($ USD)", row=1, col=1)
    fig.update_yaxes(title_text="P'(p) ($ / $)", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    sample_prices = sorted(list({25.0, 35.0, round(p_unconstrained, 2), round(p_corner, 2), 50.0, round(test_price, 2)}))
    rows = []
    for sp in sample_prices:
        q_c = max(0.0, a_coef - b_coef * sp)
        s_c = min(cap_limit, q_c)
        s_int = math.floor(s_c)
        prof_c = (sp - v_cost) * s_c - F_cost
        prof_int = (sp - v_cost) * s_int - F_cost
        rows.append(
            {
                "Price ($)": f"${sp:.2f}",
                "Continuous Demand q(p)": round(q_c, 2),
                "Continuous Sales s(p)": round(s_c, 2),
                "Integer Completed Sales": s_int,
                "Continuous Profit ($)": f"${prof_c:,.2f}",
                "Integer Ledger Profit ($)": f"${prof_int:,.2f}",
                "Binding Constraint": "Capacity Capped" if q_c > cap_limit else "Demand Limited",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if level_choice == "Advanced":
        with st.expander("∫ Advanced Integration Exercise: Time-Dependent Campaign Rates (Handbook Fixture)", expanded=True):
            st.markdown(
                """
                **Isolated Rate Exercise (Does not alter monthly ledger):**  
                Suppose a 10-day promotional sprint ($0 \le t \le 10$ days) generates marginal revenue rate $r(t) = 100 + 20t$ ($/day) and marginal cost rate $c(t) = 60 + 5t$ ($/day).
                """
            )
            t_end = st.slider("Integration Horizon T (days):", min_value=1, max_value=14, value=10)
            acc_rev = 100.0 * t_end + 10.0 * (t_end ** 2)
            acc_cost = 60.0 * t_end + 2.5 * (t_end ** 2)
            acc_prof = acc_rev - acc_cost
            ic1, ic2, ic3 = st.columns(3)
            ic1.metric(f"Accumulated Revenue ∫₀^{t_end} r(t) dt", f"${acc_rev:,.2f}")
            ic2.metric(f"Accumulated Cost ∫₀^{t_end} c(t) dt", f"${acc_cost:,.2f}")
            ic3.metric(f"Net Campaign Accumulation", f"${acc_prof:,.2f}")

# ==============================================================================
# TAB 2: INPUTS, FUNDING & COST LINES (NORMAL MODE)
# ==============================================================================
with tabs[1]:
    st.header("Inputs, Startup Funding & Editable Cost Rows")
    st.info("Changes here update your scenario parameters. Record a monthly step in Tab 3 to write to the official ledger.")

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("🚁 Operational & Demand Parameters (Normal Mode)")
        new_price = st.number_input("Base Price per Inspection ($ USD)", min_value=0.01, value=float(state["inputs"]["base_price"]), step=1.0)
        new_d0 = st.number_input("Baseline Demand D0 (inspections/mo)", min_value=0, value=int(state["inputs"]["D0"]), step=1)
        new_req = st.number_input("Current Month Requested Demand", min_value=0, value=int(state["inputs"]["requested_demand"]), step=1)
        new_staff_hrs = st.number_input("Staff Hours Available / Month", min_value=0.0, value=float(state["inputs"]["staff_hours"]), step=2.0)
        new_hrs_unit = st.number_input("Productive Hours per Inspection", min_value=0.1, value=float(state["inputs"]["hours_per_unit"]), step=0.5)
        new_slots = st.number_input("Equipment Slots / Month", min_value=0, value=int(state["inputs"]["equipment_slots"]), step=1)
        new_flight_min = st.number_input("Flight Minutes per Job", min_value=1.0, value=float(state["inputs"]["flight_minutes_per_job"]), step=1.0)
        new_batt_min = st.number_input("Battery Minutes Available / Month", min_value=0.0, value=float(state["inputs"]["battery_minutes_available"]), step=20.0)

        if st.button("Apply Operational Parameters", type="primary"):
            state["inputs"]["base_price"] = new_price
            state["inputs"]["D0"] = int(new_d0)
            state["inputs"]["requested_demand"] = int(new_req)
            state["inputs"]["staff_hours"] = new_staff_hrs
            state["inputs"]["hours_per_unit"] = new_hrs_unit
            state["inputs"]["equipment_slots"] = int(new_slots)
            state["inputs"]["flight_minutes_per_job"] = new_flight_min
            state["inputs"]["battery_minutes_available"] = new_batt_min
            st.success("Operational parameters updated!")
            st.rerun()

    with col_right:
        st.subheader("🏦 Startup Financing & Opening Balances")
        f_data = state["funding"]
        st.table(
            pd.DataFrame(
                [
                    {"Line Item": "Owner Contribution (Equity)", "Amount": fmt_usd(f_data["owner_contribution"]), "Accounting Treatment": "Equity (Not Sales Revenue)"},
                    {"Line Item": "Equipment Assets (Drone $3,200 + PC $1,000)", "Amount": fmt_usd(f_data["equipment_assets"]), "Accounting Treatment": "Capital Asset (Not Expensed Again)"},
                    {"Line Item": "Pre-Opening Setup / Training", "Amount": fmt_usd(f_data["pre_opening_expense"]), "Accounting Treatment": "Pre-Opening Retained Earnings (-$800)"},
                    {"Line Item": "Post-Startup Spendable Cash", "Amount": fmt_usd(f_data["opening_cash"]), "Accounting Treatment": "Opening Cash Reserve"},
                ]
            )
        )

        st.subheader("🧾 Editable Cost Lines")
        v_col, f_col = st.columns(2)
        with v_col:
            st.markdown("**Variable Cost / Inspection ($10 baseline)**")
            for k, val in state["cost_lines"]["variable"].items():
                state["cost_lines"]["variable"][k] = st.number_input(
                    f"{k} ($/unit)", min_value=0.0, value=float(val), step=0.5, key=f"var_{k}"
                )
            st.caption(f"Total Variable Cost: **${sum(state['cost_lines']['variable'].values()):.2f} / unit**")

        with f_col:
            st.markdown("**Fixed Monthly Overhead ($500 baseline)**")
            for k, val in state["cost_lines"]["fixed"].items():
                state["cost_lines"]["fixed"][k] = st.number_input(
                    f"{k} ($/mo)", min_value=0.0, value=float(val), step=10.0, key=f"fix_{k}"
                )
            st.caption(f"Total Fixed Cost: **${sum(state['cost_lines']['fixed'].values()):.2f} / month**")

# ==============================================================================
# TAB 3: LEDGER & FIXTURE ACCEPTANCE TESTS
# ==============================================================================
with tabs[2]:
    st.header("Dated Event Ledger & AER-3 Acceptance Tests")

    mode_col1, mode_col2 = st.columns(2)

    with mode_col1:
        st.subheader("🟢 Normal Mode: Advance Simulation One Month")
        st.caption("Derives capacity automatically from staff hours, equipment slots, and battery minutes.")
        cap_derived = compute_normal_capacity(state["inputs"])
        st.write(
            f"**Derived Capacity:** `{cap_derived['effective_capacity']}` inspections "
            f"(Staff: {cap_derived['staff_cap']}, Slots: {cap_derived['equip_cap']}, Battery: {cap_derived['battery_cap']})"
        )

        with st.form("normal_step_form"):
            run_id_in = st.text_input("Unique Run ID", value=f"RUN-{state['state_version']:03d}")
            sim_date_in = st.text_input("Simulation Date (YYYY-MM-DD)", value=state["simulation_date"])
            ad_in = st.number_input("Approved Own-Marketing Expense ($)", min_value=0.0, value=0.0, step=25.0)
            capex_in = st.number_input("Additional Equipment Capex ($)", min_value=0.0, value=0.0, step=50.0)
            submitted = st.form_submit_button("Approve & Advance Simulation Once", type="primary")
            if submitted:
                ok, msg, _ = run_monthly_step(
                    state=state,
                    run_id=run_id_in.strip(),
                    sim_date=sim_date_in.strip(),
                    price=state["inputs"]["base_price"],
                    requested=state["inputs"]["requested_demand"],
                    ad_cost=ad_in,
                    capacity_override=None,
                    capex_outflow=capex_in,
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    with mode_col2:
        st.subheader("🧪 Fixture-Test Mode (Handbook `monthly_fixture.csv`)")
        st.warning(
            "⚠️ **Fixture-Test Mode Warning:** Uses explicit `capacity_override` from the handbook fixture "
            "to verify ledger math. Resets state to opening cash ($3,000) before replaying."
        )
        if os.path.exists("sample_data/monthly_fixture.csv"):
            fixture_df = pd.read_csv("sample_data/monthly_fixture.csv")
        else:
            fixture_df = pd.read_csv(io.StringIO(EMBEDDED_FIXTURE_CSV))
        st.dataframe(fixture_df, use_container_width=True, hide_index=True)

        if st.button("▶️ Reset & Replay 3-Month AER Fixture", use_container_width=True):
            st.session_state.biz_state = default_state()
            fresh = st.session_state.biz_state
            results = []
            for _, row in fixture_df.iterrows():
                m_str = str(row["month"])
                last_day = "28" if m_str.endswith("-02") else "31"
                ok, _, summ = run_monthly_step(
                    state=fresh,
                    run_id=f"FIXTURE-{m_str}",
                    sim_date=f"{m_str}-{last_day}",
                    price=35.0,
                    requested=int(row["requested"]),
                    ad_cost=float(row["ad_cost"]),
                    capacity_override=int(row["capacity_override"]),
                )
                if ok and summ:
                    results.append(summ)
            st.session_state.fixture_results = results
            st.rerun()

        if st.session_state.fixture_results:
            st.markdown("**Observed Fixture Replay Results (Compare vs. Handbook Page 75):**")
            res_df = pd.DataFrame(st.session_state.fixture_results)[
                ["month", "sold", "revenue", "total_expense", "profit", "closing_cash"]
            ]
            st.dataframe(res_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📒 Official Dated Event Ledger")
    if state["ledger"]:
        ledger_df = pd.DataFrame(state["ledger"])
        st.dataframe(ledger_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Export Ledger CSV",
            data=ledger_df.to_csv(index=False),
            file_name=f"{state['team_id']}_ledger_v{state['state_version']}.csv",
            mime="text/csv",
        )
    else:
        st.info("No transactions recorded yet. Advance a month or run the AER fixture above.")

# ==============================================================================
# TAB 4: STAGE 2–4 PLACEHOLDERS (HONEST UNIMPLEMENTED STATUS)
# ==============================================================================
with tabs[3]:
    st.header("Stage 2–4 Modules (Not Yet Implemented in Stage 1)")
    st.markdown(
        """
        Per the Career Venture Lab build sequence, **Stage 1** must pass all acceptance checks before adding later stages:
        - **Stage 2 (Pending):** Departmental AI Advisor Tabs (`Finance`, `Operations`, `Market & Marketing`, `Independent Reviewer`), full printable PDF Report Center, and Costed Marketing Studio.
        - **Stage 3 (Pending):** Frozen-snapshot Practice Assessment generator and Cross-Course Connections evidence panel.
        - **Stage 4 (Optional):** Demonstration storefront with fictional test orders.
        """
    )
