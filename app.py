# app.py — ESB Dash (Policies + Air/Equity + State Distribution + District Distribution + Summary, Scatter, Lorenz/Gini)
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="ESB Dash", layout="wide")
st.title("Electric School Bus — Policies, Air/Equity & Distributions")

# ---------- Default path ----------
DEFAULT_PATH = (Path(__file__).parent / "ESB_adoption_dataset_v9_update_june_2025.xlsx").resolve()

# ---------- Pick source ----------
src = st.sidebar.radio("Data source", ["Upload Excel", "Default Excel"], index=1)
uploaded = st.sidebar.file_uploader("Upload ESB Excel (.xlsx)", type=["xlsx"]) if src == "Upload Excel" else None

@st.cache_data(show_spinner=False)
def list_sheets(path_or_file):
    return pd.ExcelFile(path_or_file).sheet_names

@st.cache_data(show_spinner=False)
def read_sheet(path_or_file, sheet_name):
    return pd.read_excel(pd.ExcelFile(path_or_file), sheet_name)

# Open workbook
if src == "Upload Excel" and uploaded is not None:
    wb = uploaded
elif src == "Default Excel":
    if not DEFAULT_PATH.exists():
        st.error(f"Default file not found:\n{DEFAULT_PATH}")
        st.stop()
    wb = DEFAULT_PATH
else:
    st.info("Upload a file or switch to Default Excel.")
    st.stop()

sheets = list_sheets(wb)

# Prefer a state sheet if present
default_idx = 0
for i, s in enumerate(sheets):
    if "state" in s.lower():
        default_idx = i
        break
sheet = st.sidebar.selectbox("Sheet", sheets, index=default_idx)
df_raw = read_sheet(wb, sheet)
st.caption(f"Loaded: {df_raw.shape[0]:,} rows × {df_raw.shape[1]:,} cols — Sheet: {sheet}")
df = df_raw.copy()

# ---------- helpers ----------
STATE2ABBR = {
 "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO",
 "Connecticut":"CT","Delaware":"DE","District of Columbia":"DC","Florida":"FL","Georgia":"GA","Hawaii":"HI",
 "Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
 "Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS",
 "Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ",
 "New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK",
 "Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD",
 "Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA",
 "West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"
}
FIPS2ABBR = {1:"AL",2:"AK",4:"AZ",5:"AR",6:"CA",8:"CO",9:"CT",10:"DE",11:"DC",12:"FL",13:"GA",15:"HI",
16:"ID",17:"IL",18:"IN",19:"IA",20:"KS",21:"KY",22:"LA",23:"ME",24:"MD",25:"MA",26:"MI",27:"MN",
28:"MS",29:"MO",30:"MT",31:"NE",32:"NV",33:"NH",34:"NJ",35:"NM",36:"NY",37:"NC",38:"ND",39:"OH",
40:"OK",41:"OR",42:"PA",44:"RI",45:"SC",46:"SD",47:"TN",48:"TX",49:"UT",50:"VT",51:"VA",53:"WA",
54:"WV",55:"WI",56:"WY"}

def _norm(s: str) -> str:
    """lower + trim + collapse spaces"""
    return re.sub(r"\s+", " ", str(s).strip().lower())

def find_col(cols, *aliases):
    """
    Robust column finder:
    - case/space insensitive
    - substring allowed
    - 'bag of words' (order-insensitive) matching
    """
    norm_map = {c: _norm(c) for c in cols}
    # 1) exact
    for a in aliases:
        aN = _norm(a)
        for c, cn in norm_map.items():
            if cn == aN:
                return c
    # 2) substring
    for a in aliases:
        aN = _norm(a)
        for c, cn in norm_map.items():
            if aN in cn:
                return c
    # 3) bag-of-words
    for a in aliases:
        words = set(re.findall(r"\w+", _norm(a)))
        if not words:
            continue
        for c, cn in norm_map.items():
            if words.issubset(set(re.findall(r"\w+", cn))):
                return c
    return None

def to_01(series):
    x = pd.to_numeric(series, errors="coerce")
    if pd.notna(x.max()) and x.max() > 1.5:
        x = x / 100.0
    return x

def to_state_code(val):
    """Accept full name, 2-letter code, or numeric FIPS (as int or string)."""
    if pd.isna(val): return None
    s = str(val).strip()
    if len(s) == 2 and s.isalpha():
        return s.upper()
    if s.isdigit():
        try:
            return FIPS2ABBR.get(int(s))
        except Exception:
            pass
    if s in STATE2ABBR: return STATE2ABBR[s]
    t = s.title()
    if t in STATE2ABBR: return STATE2ABBR[t]
    u = s.upper().title()
    if u in STATE2ABBR: return STATE2ABBR[u]
    return None

def first_sheet_with(keyword: str):
    for s in sheets:
        if keyword.lower() in s.lower():
            return s
    return None

# ---------- find columns (state sheet) ----------
col_state   = find_col(df.columns, "1a. state", "state")
if not col_state:
    st.error("Couldn’t detect a State column in this sheet.")
    st.stop()

col_esb_cnt = find_col(df.columns,
    "number of committed esbs", "3a. number of committed esbs",
    "number of esbs committed", "esbs committed",
    "committed esbs", "operating esbs", "esb count"
)
col_commit  = find_col(df.columns, "number of statewide commitments", "statewide commitments", "policy commitments")
col_act     = find_col(df.columns, "act adopted", "advanced clean trucks", "act rule")

col_pm25    = find_col(df.columns, "pm2.5", "pm25", "5f. pm2.5 concentration", "air pollution")
col_low     = find_col(df.columns, "5d. percent low-income", "low income", "poverty")
col_color   = find_col(df.columns, "percent one race non-white", "students of color", "race", "non-white")

# ---------- build standardized table ----------
tmp = df.copy()
tmp["state_code"] = df[col_state].map(to_state_code)

unmatched = tmp["state_code"].isna().sum()
if unmatched > 0:
    st.caption(f"Note: {unmatched} row(s) had an unrecognized state value and were dropped from the maps.")

if col_esb_cnt:
    tmp["esb_committed"] = pd.to_numeric(tmp[col_esb_cnt], errors="coerce").fillna(0).astype(int)
if col_commit:
    tmp["commitments"] = pd.to_numeric(tmp[col_commit], errors="coerce").fillna(0).astype(int)
if col_act:
    a = tmp[col_act]
    if pd.api.types.is_string_dtype(a):
        tmp["act_adopted"] = a.astype(str).str.lower().str.strip().isin(["yes","y","true","1"]).astype(bool)
    else:
        tmp["act_adopted"] = pd.to_numeric(a, errors="coerce").fillna(0).astype(int).astype(bool)
if col_pm25:
    tmp["pm25"] = pd.to_numeric(tmp[col_pm25], errors="coerce")
if col_low:
    tmp["low_income"] = to_01(tmp[col_low])
if col_color:
    tmp["students_color"] = to_01(tmp[col_color])

# ---------- aggregate to state ----------
avg_dict = {"districts": ("state_code", "size")}
if "pm25" in tmp:           avg_dict["pm25"] = ("pm25", "mean")
if "low_income" in tmp:     avg_dict["low_income"] = ("low_income", "mean")
if "students_color" in tmp: avg_dict["students_color"] = ("students_color", "mean")

avg_by_state = (
    tmp.dropna(subset=["state_code"])
       .groupby("state_code")
       .agg(**avg_dict)
       .reset_index()
)

agg_dict = {}
if "commitments" in tmp:  agg_dict["commitments"]  = ("commitments", "max")
if "act_adopted" in tmp:  agg_dict["act_adopted"]  = ("act_adopted", "max")
if "esb_committed" in tmp:
    agg_dict["esb_committed"] = ("esb_committed", "sum")
else:
    agg_dict["esb_committed"] = ("state_code", "size")

state_df = (
    tmp.dropna(subset=["state_code"])
       .groupby("state_code")
       .agg(**agg_dict)
       .reset_index()
       .merge(avg_by_state, on="state_code", how="left")
)

if state_df.empty:
    st.error("No states recognized for this sheet. Preview first 5 distinct state values below.")
    st.write(df[col_state].dropna().astype(str).drop_duplicates().head(10))
    st.stop()

# ---------- optional extra columns (awarded / ordered / delivered) if present ----------
col_awarded  = find_col(df.columns, "awarded esbs", "awarded")
col_ordered  = find_col(df.columns, "ordered esbs", "ordered")
col_delivered= find_col(df.columns, "delivered esbs", "delivered")

extra_agg = {}
if col_awarded:   tmp["awarded"]   = pd.to_numeric(df[col_awarded], errors="coerce")
if col_ordered:   tmp["ordered"]   = pd.to_numeric(df[col_ordered], errors="coerce")
if col_delivered: tmp["delivered"] = pd.to_numeric(df[col_delivered], errors="coerce")
for k in ["awarded","ordered","delivered"]:
    if k in tmp:
        extra_agg[k] = (k, "sum")

if extra_agg:
    extra_state = (
        tmp.dropna(subset=["state_code"])
           .groupby("state_code")
           .agg(**extra_agg)
           .reset_index()
    )
    state_df = state_df.merge(extra_state, on="state_code", how="left")

# ---------- Filters shared by maps ----------
st.sidebar.markdown("### Filters (maps)")
states = ["All"] + sorted(state_df["state_code"].unique().tolist())
sel_state = st.sidebar.selectbox("Filter by state (applies to Map 2 KPIs)", states, index=0)

# ---------- Summary band (new) ----------
st.markdown("---")
colA, colB, colC, colD, colE, colF = st.columns(6)
with colA:
    st.metric("Total committed ESBs", f"{int(state_df['esb_committed'].sum()):,}")
with colB:
    st.metric("States with ≥1 ESB", state_df.loc[state_df["esb_committed"]>0,"state_code"].nunique())
with colC:
    st.metric("Average PM2.5", f"{state_df['pm25'].mean(skipna=True):.2f} μg/m³" if "pm25" in state_df else "—")
with colD:
    st.metric("% low-income (avg)", f"{state_df['low_income'].mean(skipna=True)*100:.1f}%" if "low_income" in state_df else "—")
with colE:
    st.metric("% students of color (avg)", f"{state_df['students_color'].mean(skipna=True)*100:.1f}%" if "students_color" in state_df else "—")
with colF:
    if "delivered" in state_df:
        st.metric("Delivered ESBs", f"{int(state_df['delivered'].sum()):,}")
    elif "awarded" in state_df:
        st.metric("Awarded ESBs", f"{int(state_df['awarded'].sum()):,}")
    else:
        st.metric("Additional status", "—")

st.caption("This summary mirrors the public ESB dashboard style with national-level indicators.")

# ---------- Tabs ----------
tab1, tab2, tab3, tab4 = st.tabs([
    "Policies by State (Map 1)",
    "Air & Equity (Map 2)",
    "Distribution by State",
    "Distribution by District"
])

# ===== Map 1: Policies =====
with tab1:
    st.subheader("Electrification policies by state")

    color_opts = {}
    if "commitments" in state_df:   color_opts["Policy commitments (0/1/2)"] = "commitments"
    if "esb_committed" in state_df: color_opts["Committed ESBs (sum)"]       = "esb_committed"
    if "pm25" in state_df:          color_opts["Average PM2.5 (μg/m³)"]      = "pm25"
    if "low_income" in state_df:    color_opts["Average % low-income"]       = "low_income"
    if "students_color" in state_df:color_opts["Average % students of color"]= "students_color"

    color_label = st.selectbox("Color by", list(color_opts.keys()), index=0)
    color_col = color_opts[color_label]

    if "commitments" in state_df:
        commit_vals = sorted(state_df["commitments"].dropna().unique().tolist())
        commit_sel = st.multiselect("Show commitments (0/1/2…)", commit_vals, default=commit_vals)
    else:
        commit_sel = None
        st.caption("No statewide commitment column detected in this sheet.")

    can_act = "act_adopted" in state_df and state_df["act_adopted"].notna().any()
    act_only = st.checkbox("Show only states that adopted ACT rule", value=False, disabled=not can_act)

    g = state_df.copy()
    if commit_sel is not None:
        g = g[g["commitments"].isin(commit_sel)]
    if act_only and can_act:
        g = g[g["act_adopted"] == True]

    # Small narrative
    st.markdown(
        f"States in view: **{g['state_code'].nunique()}** — Committed ESBs (sum): **{int(g['esb_committed'].sum()):,}**."
    )

    if g.empty:
        st.warning("No states match the filters above.")
    else:
        fig = px.choropleth(
            g, locations="state_code", locationmode="USA-states",
            color=color_col, scope="usa", color_continuous_scale="Viridis",
            hover_data={c:True for c in g.columns if c!="state_code"},
        )
        fig.update_traces(marker_line_width=0.6, marker_line_color="black")
        fig.update_layout(height=520, margin=dict(l=0,r=0,t=10,b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.write("State table (filtered)")
    sort_cols = [c for c in [color_col, "state_code"] if c in g.columns]
    st.dataframe(g.sort_values(sort_cols, ascending=[False, True] if len(sort_cols)>1 else True),
                 use_container_width=True)

# ===== Map 2: Air & Equity =====
with tab2:
    st.subheader("Air & Equity by state")

    g2 = state_df if sel_state == "All" else state_df[state_df["state_code"] == sel_state]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("States in view", g2["state_code"].nunique())
    k2.metric("Committed ESBs (sum)", f"{int(g2['esb_committed'].sum()):,}" if "esb_committed" in g2 else "—")
    k3.metric("Average PM2.5", f"{g2['pm25'].mean(skipna=True):.2f} μg/m³" if "pm25" in g2 else "—")
    k4.metric("Average % low-income", f"{g2['low_income'].mean(skipna=True)*100:.0f}%" if "low_income" in g2 else "—")

    color2_opts = {}
    if "pm25" in state_df:          color2_opts["PM2.5 (μg/m³)"]       = "pm25"
    if "low_income" in state_df:    color2_opts["% low-income"]        = "low_income"
    if "students_color" in state_df:color2_opts["% students of color"] = "students_color"

    if not color2_opts:
        st.warning("No PM2.5 / equity fields were detected in this sheet.")
    else:
        color2_label = st.selectbox("Color by (Map 2)", list(color2_opts.keys()), index=0)
        color2_col = color2_opts[color2_label]

        fig2 = px.choropleth(
            state_df, locations="state_code", locationmode="USA-states",
            color=color2_col, scope="usa", color_continuous_scale="Plasma",
            hover_data={c:True for c in state_df.columns if c!="state_code"},
        )
        fig2.update_traces(marker_line_width=0.6, marker_line_color="black")
        fig2.update_layout(height=520, margin=dict(l=0,r=0,t=10,b=0))
        st.plotly_chart(fig2, use_container_width=True)

    # -------- New: Scatter PM2.5 vs ESBs (per state) --------
    st.markdown("---")
    st.markdown("PM2.5 vs Committed ESBs (per state)")
    if "pm25" in state_df:
        # Choose color factor
        color_field = st.selectbox(
            "Color by",
            [c for c in ["low_income", "students_color"] if c in state_df] or ["pm25"],
            index=0
        )
        size_scale = st.slider("Bubble size scale (ESBs)", 5, 50, 20, 1)
        g_sc = state_df.dropna(subset=["pm25"]).copy()
        if g_sc.empty:
            st.info("No PM2.5 values available to plot the scatter.")
        else:
            fig_sc = px.scatter(
                g_sc, x="pm25", y="esb_committed",
                color=color_field if color_field in g_sc else None,
                size="esb_committed", size_max=size_scale,
                hover_name="state_code",
                labels={"pm25":"PM2.5 (μg/m³)", "esb_committed":"Committed ESBs"}
            )
            fig_sc.update_layout(height=420, margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig_sc, use_container_width=True)
            st.caption("This chart helps assess whether higher-pollution states receive more committed ESBs.")

    st.write("State table (all states)")
    st.dataframe(state_df.sort_values("state_code"), use_container_width=True)

# ===== KPI 3: Distribution by State (vertical bars + heat map + basic histogram) =====
with tab3:
    st.subheader("Distribution of committed ESBs by state")

    if "esb_committed" not in state_df:
        st.info("No 'esb_committed' column was found — cannot compute the distribution by state.")
    else:
        colL, colR = st.columns([2, 2])
        with colL:
            mode = st.radio("Show as", ["Count", "Share (%)"], index=0, horizontal=True, key="dist_mode")
            view = st.radio("View", ["Top-N", "All states"], index=0, horizontal=True, key="dist_view")
            show_cum = st.checkbox("Show cumulative share (Pareto)", value=True)
        with colR:
            all_states = state_df["state_code"].sort_values().unique().tolist()
            pick_states = st.multiselect("Filter states (optional)", all_states, default=all_states)
            top_n = st.slider("Top N", 5, 50, 10, 1, key="dist_topn")

        g3 = state_df.loc[state_df["state_code"].isin(pick_states), ["state_code", "esb_committed"]].dropna().copy()
        g3["esb_committed"] = pd.to_numeric(g3["esb_committed"], errors="coerce").fillna(0)
        g3 = g3.sort_values("esb_committed", ascending=False)
        total = g3["esb_committed"].sum()
        g3["share"] = g3["esb_committed"] / total if total > 0 else 0
        g3["cum_share"] = g3["share"].cumsum()
        gplot = g3.head(top_n).copy() if view == "Top-N" else g3.copy()
        y_col = "esb_committed" if mode == "Count" else "share"

        # --- Bar chart (+ optional Pareto line on secondary Y)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_bar(x=gplot["state_code"], y=gplot[y_col], name=("ESBs" if mode == "Count" else "Share"))
        if show_cum:
            fig.add_scatter(x=gplot["state_code"], y=gplot["cum_share"],
                            mode="lines+markers", name="Cumulative share",
                            hovertemplate="%{y:.1%} cumulative", secondary_y=True)
        if mode == "Share (%)":
            fig.update_yaxes(tickformat=".0%", secondary_y=False)
        fig.update_yaxes(title_text="Cumulative share", tickformat=".0%", range=[0, 1], secondary_y=True)
        fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10), bargap=0.2)
        st.plotly_chart(fig, use_container_width=True)

        # --- Heat-style map (choropleth)
        st.markdown("---")
        st.markdown("Heat map — concentration of ESBs by state")
        colA, colB = st.columns([2, 2])
        with colA:
            map_mode = "esb_committed" if mode == "Count" else "share"
            classing = st.radio("Color scale", ["Continuous", "Binned"], index=0, horizontal=True, key="dist_mapclass")
        with colB:
            scheme = st.selectbox("Binning scheme (if binned)",
                                  ["1–10 / 11–100 / 101–500 / 501+", "Quartiles"],
                                  index=0, disabled=(classing=="Continuous"), key="dist_binscheme")

        map_df = state_df[["state_code", "esb_committed"]].copy()
        tot_all = map_df["esb_committed"].sum()
        map_df["share"] = (map_df["esb_committed"] / tot_all) if tot_all > 0 else 0
        if len(pick_states) != len(state_df):
            mask_keep = map_df["state_code"].isin(pick_states)
            map_df.loc[~mask_keep, ["esb_committed", "share"]] = 0

        if classing == "Binned":
            if map_mode == "esb_committed":
                if scheme.startswith("1–10"):
                    bins = [0, 10, 100, 500, float("inf")]
                    labels = ["1–10", "11–100", "101–500", "501+"]
                    map_df["bin"] = pd.cut(map_df["esb_committed"], bins=bins, labels=labels, right=True)
                else:
                    tmp_vals = map_df.loc[map_df["esb_committed"] > 0, "esb_committed"]
                    if tmp_vals.empty:
                        map_df["bin"] = pd.Categorical(["No ESBs"]*len(map_df))
                    else:
                        qcats = pd.qcut(tmp_vals, 4, labels=["Q1","Q2","Q3","Q4"])
                        map_df["bin"] = pd.Categorical("No ESBs", categories=["No ESBs","Q1","Q2","Q3","Q4"])
                        map_df.loc[tmp_vals.index, "bin"] = qcats
            else:
                tmp_vals = map_df.loc[map_df["share"] > 0, "share"]
                if scheme.startswith("1–10"):
                    bins = [0, 0.01, 0.05, 0.10, 1.0]
                    labels = ["≤1%", "1–5%", "5–10%", ">10%"]
                    map_df["bin"] = pd.cut(map_df["share"], bins=bins, labels=labels, right=True)
                else:
                    if tmp_vals.empty:
                        map_df["bin"] = pd.Categorical(["No share"]*len(map_df))
                    else:
                        qcats = pd.qcut(tmp_vals, 4, labels=["Q1","Q2","Q3","Q4"])
                        map_df["bin"] = pd.Categorical("No share", categories=["No share","Q1","Q2","Q3","Q4"])
                        map_df.loc[tmp_vals.index, "bin"] = qcats

            fig_map = px.choropleth(
                map_df, locations="state_code", locationmode="USA-states",
                color="bin", scope="usa",
                category_orders={"bin": map_df["bin"].cat.categories if hasattr(map_df["bin"], "cat") else None},
                hover_data={"state_code": True, "esb_committed": True, "share": ":.1%"}
            )
        else:
            rng = [0, map_df[map_mode].max()] if map_df[map_mode].notna().any() else [0, 1]
            fig_map = px.choropleth(
                map_df, locations="state_code", locationmode="USA-states",
                color=map_mode, scope="usa", color_continuous_scale="YlOrRd",
                range_color=rng,
                hover_data={"state_code": True, "esb_committed": True, "share": ":.1%"}
            )

        fig_map.update_traces(marker_line_width=0.6, marker_line_color="black")
        fig_map.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_map, use_container_width=True)

        

        if total > 0:
            st.caption(f"Top {min(top_n, len(g3))} states cover {g3.head(top_n)['share'].sum():.1%} of all committed ESBs (after filters).")
        st.markdown("State table (sorted)")
        st.dataframe(g3.reset_index(drop=True), use_container_width=True)

# ===== KPI 4: Distribution by District =====
with tab4:
    st.subheader("Distribution of committed ESBs by district")

    # Detect a district-level sheet
    dist_sheet = first_sheet_with("district")
    if dist_sheet is None:
        st.info("No district-level sheet detected in the workbook.")
    else:
        d_raw = read_sheet(wb, dist_sheet)
        d = d_raw.copy()

        # ---- Detect columns (robust aliases)
        col_state_d   = find_col(d.columns, "1a. State", "1g. State", "state")
        col_district  = find_col(
            d.columns,
            "1b. Local Education Agency (LEA) or entity name",
            "local education agency", "lea", "entity name",
            "district name", "school district", "district", "primary user"
        )
        col_esb_cnt_d = find_col(
            d.columns,
            "3a. Number of ESBs committed",
            "number of esbs committed",
            "committed esbs",
            "number of committed esbs",
            "3a. number of esbs committed",
            "esb count"
        )
        col_lat = find_col(d.columns, "1s. Latitude", "latitude", "lat")
        col_lon = find_col(d.columns, "1t. Longitude", "longitude", "lon", "lng")

        # Optional fuel-type columns (stacked bars if available)
        fuel_cols_map = {
            "Diesel": find_col(d.columns, "diesel buses", "diesel"),
            "Gasoline": find_col(d.columns, "gasoline buses", "gasoline"),
            "Propane": find_col(d.columns, "propane buses", "propane"),
            "Electric": find_col(d.columns, "electric buses", "electric"),
            "Natural gas": find_col(d.columns, "natural gas buses", "natural gas"),
            "Hybrid": find_col(d.columns, "hybrid buses", "hybrid")
        }
        fuel_cols_map = {k:v for k,v in fuel_cols_map.items() if v is not None}

        if col_state_d is None or col_district is None:
            st.warning("District sheet missing one of: state or district name.")
        else:
            d["state_code"] = d[col_state_d].map(to_state_code)
            d["district_name"] = d[col_district].astype(str).str.strip()
            if col_esb_cnt_d:
                d["esb_committed"] = pd.to_numeric(d[col_esb_cnt_d], errors="coerce").fillna(0)
            else:
                d["esb_committed"] = 1.0

            # ---- Filters (state & district search)
            c1, c2, c3 = st.columns([1.4, 1, 1])
            with c1:
                states_d = sorted(d["state_code"].dropna().unique().tolist())
                pick_states_d = st.multiselect("Filter by state", states_d, default=states_d)
            with c2:
                search = st.text_input("Search district (contains)", value="")
            with c3:
                top_n_d = st.slider("Top N districts", 5, 50, 10, 1)

            dd = d[d["state_code"].isin(pick_states_d)].copy()
            if search.strip():
                dd = dd[dd["district_name"].str.contains(search.strip(), case=False, na=False)]

            # ---- Bar chart: top-N districts by committed ESBs
            dd_sorted = dd.sort_values("esb_committed", ascending=False).head(top_n_d)
            if dd_sorted.empty:
                st.info("No districts match current filters.")
            else:
                fig_d = px.bar(dd_sorted, x="district_name", y="esb_committed", color="state_code",
                               labels={"district_name":"District", "esb_committed":"Committed ESBs"},
                               hover_data=["state_code"])
                fig_d.update_layout(height=460, margin=dict(l=10,r=10,t=10,b=120), xaxis_tickangle=-35)
                st.plotly_chart(fig_d, use_container_width=True)

            # ---- Optional: stacked bars by fuel type (if columns exist)
            if fuel_cols_map:
                st.markdown("Fleet mix by fuel type (stacked, top districts)")
                melt_cols = []
                for label, coln in fuel_cols_map.items():
                    dd[label] = pd.to_numeric(dd[coln], errors="coerce").fillna(0)
                    melt_cols.append(label)

                top_for_mix = (dd.assign(total_mix=dd[melt_cols].sum(axis=1))
                                 .sort_values("total_mix", ascending=False)
                                 .head(top_n_d))

                mix_df = top_for_mix.melt(id_vars=["district_name","state_code"],
                                          value_vars=melt_cols,
                                          var_name="Fuel type", value_name="Buses")
                fig_mix = px.bar(mix_df, x="district_name", y="Buses", color="Fuel type",
                                 barmode="stack", hover_data=["state_code"])
                fig_mix.update_layout(height=460, margin=dict(l=10,r=10,t=10,b=120), xaxis_tickangle=-35)
                st.plotly_chart(fig_mix, use_container_width=True)
            else:
                st.caption("No detailed fuel-type columns detected for stacked mix.")

            # ---- Map of districts (if lat/lon present)
            if col_lat and col_lon:
                st.markdown("Districts map (bubble size = committed ESBs)")
                dd_map = dd.dropna(subset=[col_lat, col_lon]).copy()
                dd_map["lat"] = pd.to_numeric(dd_map[col_lat], errors="coerce")
                dd_map["lon"] = pd.to_numeric(dd_map[col_lon], errors="coerce")
                dd_map = dd_map.dropna(subset=["lat","lon"])
                if dd_map.empty:
                    st.caption("No valid coordinates in the filtered districts.")
                else:
                    fig_m = px.scatter_mapbox(
                        dd_map, lat="lat", lon="lon",
                        size="esb_committed", color="state_code",
                        hover_name="district_name",
                        hover_data={"state_code": True, "esb_committed": True, "lat": False, "lon": False},
                        size_max=30, zoom=3, height=520
                    )
                    fig_m.update_layout(mapbox_style="open-street-map", margin=dict(l=0,r=0,t=0,b=0))
                    st.plotly_chart(fig_m, use_container_width=True)
            else:
                st.caption("No latitude/longitude columns detected — skipping the district map.")

            # ---- Table
            st.markdown("District table (filtered)")
            keep_cols = ["district_name","state_code","esb_committed"]
            st.dataframe(dd[keep_cols].sort_values("esb_committed", ascending=False).reset_index(drop=True),
                         use_container_width=True)