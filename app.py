import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime
import anthropic
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UK Restaurant Pricing Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "pricing.db")
MONTH_ORDER = {
    "01. January": 1, "02. February": 2, "03. March": 3, "04. April": 4,
    "05. May": 5, "06. June": 6, "07. July": 7, "08. August": 8,
    "09. September": 9, "10. October": 10, "11. November": 11, "12. December": 12,
}
MONTH_NAMES = {v: k.split(". ")[1] for k, v in MONTH_ORDER.items()}

CLASSIFICATION_RULES = """
CLASSIFICATION RULES (apply in order):
- Restructuring: cuts >= 50% of total changes
- Broad/light:    breadth >40% AND median abs move <= £0.30
- Broad/moderate: breadth >40% AND median abs move <= £1.00
- Broad/heavy:    breadth >40% AND median abs move >  £1.00
- Selective/light:    breadth <=40% AND median abs move <= £0.50
- Selective/moderate: breadth <=40% AND median abs move <= £1.50
- Selective/heavy:    breadth <=40% AND median abs move >  £1.50
- Nominal: 1-2 items changed only
Add "+ churn" modifier if cuts > 30% of total changes (but not Restructuring)
"""


# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            brand       TEXT,
            item_name   TEXT,
            month       TEXT,
            month_num   INTEGER,
            year        INTEGER,
            price       REAL,
            course      TEXT,
            upload_date TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT,
            upload_date TEXT,
            rows_added  INTEGER,
            brands      INTEGER,
            year_range  TEXT
        )
    """)
    conn.commit()
    return conn


def get_uploads():
    conn = get_db()
    df = pd.read_sql("SELECT * FROM uploads ORDER BY upload_date DESC", conn)
    conn.close()
    return df


# ── Pipeline ──────────────────────────────────────────────────────────────────
def process_upload(file) -> dict:
    """Clean, deduplicate and store a new pricing file. Returns a summary dict."""

    # 1. Read
    raw = pd.read_excel(file, sheet_name="Raw Data", header=1)
    raw = raw[["Month", "Year", "Brand", "Item Name", "Item Size", "Price", "Course"]].copy()
    raw = raw.dropna(subset=["Brand", "Price", "Item Name"])
    raw["Year"] = pd.to_numeric(raw["Year"], errors="coerce").dropna().astype(int)
    raw["Price"] = pd.to_numeric(raw["Price"], errors="coerce")
    raw = raw.dropna(subset=["Price", "Year"])
    raw = raw[raw["Price"] > 0]

    # 2. Collapse sizes → median per brand/item/month/year
    df = raw.groupby(["Brand", "Item Name", "Month", "Year"], as_index=False).agg(
        Price=("Price", "median"),
        Course=("Course", "first"),
    )
    df["month_num"] = df["Month"].map(MONTH_ORDER)
    df = df.dropna(subset=["month_num"])
    df["month_num"] = df["month_num"].astype(int)

    # 3. Remove rows already in DB (exact brand/item/month/year match)
    conn = get_db()
    existing = pd.read_sql(
        "SELECT brand, item_name, month, year FROM prices", conn
    )
    if len(existing) > 0:
        existing.columns = ["Brand", "Item Name", "Month", "Year"]
        existing["Year"] = existing["Year"].astype(int)
        merged = df.merge(existing, on=["Brand", "Item Name", "Month", "Year"],
                          how="left", indicator=True)
        df = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])

    if len(df) == 0:
        conn.close()
        return {"rows_added": 0, "brands": 0, "year_range": "already exists",
                "message": "All rows already in database — nothing new to add."}

    # 4. Store
    upload_date = datetime.now().isoformat()
    rows_to_insert = [
        (row["Brand"], row["Item Name"], row["Month"], int(row["month_num"]),
         int(row["Year"]), float(row["Price"]), row.get("Course", ""),
         upload_date)
        for _, row in df.iterrows()
    ]
    conn.executemany(
        "INSERT INTO prices (brand,item_name,month,month_num,year,price,course,upload_date) VALUES (?,?,?,?,?,?,?,?)",
        rows_to_insert,
    )
    year_range = f"{int(df['Year'].min())}–{int(df['Year'].max())}"
    brands_count = df["Brand"].nunique()
    conn.execute(
        "INSERT INTO uploads (filename,upload_date,rows_added,brands,year_range) VALUES (?,?,?,?,?)",
        (getattr(file, "name", "file"), upload_date, len(df), brands_count, year_range),
    )
    conn.commit()
    conn.close()

    return {
        "rows_added": len(df),
        "brands": brands_count,
        "year_range": year_range,
        "message": f"Successfully added {len(df):,} records across {brands_count} brands ({year_range}).",
    }


# ── Analysis helpers ──────────────────────────────────────────────────────────
def load_data(year_filter=None, brand_filter=None) -> pd.DataFrame:
    conn = get_db()
    query = "SELECT * FROM prices WHERE 1=1"
    params = []
    if year_filter:
        query += f" AND year IN ({','.join(['?']*len(year_filter))})"
        params.extend(year_filter)
    if brand_filter:
        query += f" AND brand IN ({','.join(['?']*len(brand_filter))})"
        params.extend(brand_filter)
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


def compute_changes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values(["brand", "item_name", "year", "month_num"])
    df["prev_price"] = df.groupby(["brand", "item_name"])["price"].shift(1)
    df["prev_year"] = df.groupby(["brand", "item_name"])["year"].shift(1)
    df = df[df["prev_price"].notna()]
    df["is_change"] = df["price"] != df["prev_price"]
    df["price_delta"] = df["price"] - df["prev_price"]
    df["pct_change"] = df["price_delta"] / df["prev_price"] * 100
    return df[df["is_change"]].copy()


def classify_brand(items_up, items_down, breadth_pct, med_abs):
    total = items_up + items_down
    if total == 0:
        return "No changes"
    if items_up <= 2:
        return "Nominal"
    churn = items_down / total if total > 0 else 0
    restructuring = churn >= 0.50
    churn_flag = churn > 0.30 and not restructuring

    if restructuring:
        label = "Restructuring"
    elif breadth_pct > 40:
        if med_abs <= 0.30:
            label = "Broad / light"
        elif med_abs <= 1.00:
            label = "Broad / moderate"
        else:
            label = "Broad / heavy"
    else:
        if med_abs <= 0.50:
            label = "Selective / light"
        elif med_abs <= 1.50:
            label = "Selective / moderate"
        else:
            label = "Selective / heavy"

    if churn_flag:
        label += " + churn"
    return label


def brand_summary(changes: pd.DataFrame, menu_sizes: dict) -> pd.DataFrame:
    rows = []
    for brand in sorted(changes["brand"].unique()):
        bc = changes[changes["brand"] == brand]
        inc = bc[bc["price_delta"] > 0]
        dec = bc[bc["price_delta"] < 0]
        menu_n = menu_sizes.get(brand, 1)
        items_up = inc["item_name"].nunique()
        items_down = dec["item_name"].nunique()
        breadth = round(items_up / menu_n * 100, 1) if menu_n > 0 else 0
        med_abs = round(inc["price_delta"].median(), 2) if len(inc) > 0 else None
        med_pct = round(inc["pct_change"].median(), 1) if len(inc) > 0 else None
        primary = (
            MONTH_NAMES.get(int(bc["month_num"].value_counts().index[0]), "")
            if len(bc) > 0 else ""
        )
        classification = classify_brand(items_up, items_down, breadth,
                                         med_abs if med_abs else 0)
        rows.append({
            "Brand": brand,
            "2026 Menu Items": menu_n,
            "Items Raised": items_up,
            "Breadth %": breadth,
            "Items Cut": items_down,
            "Median Abs Move": f"£+{med_abs:.2f}" if med_abs else "—",
            "Median % Move*": f"{med_pct:.1f}%" if med_pct else "—",
            "Primary Month": primary,
            "Classification": classification,
        })
    return pd.DataFrame(rows).sort_values("Breadth %", ascending=False)


# ── Claude interrogation ──────────────────────────────────────────────────────
def ask_claude(question: str, context_df: pd.DataFrame, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)

    # Summarise the data context concisely so we don't blow the context window
    summary = context_df.to_string(index=False) if len(context_df) <= 60 else \
        context_df.head(60).to_string(index=False) + f"\n... ({len(context_df)} rows total)"

    system = f"""You are a pricing intelligence analyst for the UK restaurant sector. 
You have access to menu pricing data for {context_df['brand'].nunique() if 'brand' in context_df.columns else 'multiple'} brands.

METHODOLOGY (always apply):
- Unit: item name (sizes collapsed to median)
- Breadth: % of current year's menu repriced
- Measures: absolute £ move and direction preferred over unweighted % averages
- No volume data available — effective bill impact cannot be stated with certainty
- Median % changes are directional indicators only

{CLASSIFICATION_RULES}

Be direct, specific and commercially useful. Flag where conclusions are limited by the absence of volume data."""

    user = f"""Here is the current pricing data summary:

{summary}

Question: {question}"""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": user}],
        system=system,
    )
    return message.content[0].text


# ── Classification colour map ─────────────────────────────────────────────────
CLASS_COLOURS = {
    "Broad / light": "background-color: #EAF3DE; color: #27500A",
    "Broad / moderate": "background-color: #FFF3CD; color: #7B5800",
    "Broad / heavy": "background-color: #FFE0CC; color: #7A3010",
    "Selective / light": "background-color: #E6F1FB; color: #0C447C",
    "Selective / moderate": "background-color: #D5E8FB; color: #0C447C",
    "Selective / heavy": "background-color: #B5D4F4; color: #042C53",
    "Restructuring": "background-color: #FFCDD2; color: #7F1F1F",
    "Nominal": "background-color: #F0F0F0; color: #555",
    "No changes": "background-color: #F5F5F5; color: #999",
}


def colour_class(val):
    for key, style in CLASS_COLOURS.items():
        if val.startswith(key.split(" +")[0]):
            return style
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Pricing Intelligence")
    st.markdown("---")

    # API key — loaded from .env file, never shown on screen
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        st.success("✓ API key loaded", icon="🔑")
    else:
        st.warning(
            "No API key found. Add it to your .env file to enable "
            "the Ask a Question feature. See the setup guide for instructions.",
            icon="⚠️",
        )

    st.markdown("---")

    # Upload
    st.subheader("Upload new data")
    uploaded = st.file_uploader(
        "Drop a pricing Excel file here",
        type=["xlsx"],
        help="Must have a 'Raw Data' sheet in the same format as the original file",
    )
    if uploaded:
        with st.spinner("Processing..."):
            result = process_upload(uploaded)
        if result["rows_added"] > 0:
            st.success(result["message"])
        else:
            st.info(result["message"])

    st.markdown("---")

    # Upload history
    uploads = get_uploads()
    if len(uploads) > 0:
        st.subheader("Upload history")
        for _, row in uploads.iterrows():
            st.caption(
                f"📁 {row['filename']}\n{row['rows_added']:,} rows · {row['brands']} brands · {row['year_range']}"
            )

    st.markdown("---")
    st.caption("All data stored locally on your machine.")


# ── Load data ─────────────────────────────────────────────────────────────────
conn = get_db()
all_brands = pd.read_sql("SELECT DISTINCT brand FROM prices ORDER BY brand", conn)[
    "brand"
].tolist()
all_years = pd.read_sql("SELECT DISTINCT year FROM prices ORDER BY year DESC", conn)[
    "year"
].tolist()
conn.close()

if not all_years:
    st.title("UK Restaurant Pricing Intelligence")
    st.info(
        "No data loaded yet. Upload a pricing Excel file using the sidebar on the left to get started."
    )
    st.stop()


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["📈 Market Overview", "🏷️ Brand Detail", "📋 Full Table", "💬 Ask a Question"]
)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MARKET OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Market Overview")

    col_yr, col_blank = st.columns([2, 5])
    with col_yr:
        selected_years = st.multiselect(
            "Years to analyse",
            options=all_years,
            default=[all_years[0]] if all_years else [],
        )

    if not selected_years:
        st.info("Select at least one year above.")
        st.stop()

    df_raw = load_data(year_filter=selected_years)

    # Menu sizes for selected years
    menu_sizes = (
        df_raw.groupby("brand")["item_name"].nunique().to_dict()
    )

    # Changes
    df_all = load_data()
    changes = compute_changes(df_all)
    changes_sel = changes[changes["year"].isin(selected_years)]

    if len(changes_sel) == 0:
        st.warning("No price changes found for the selected period. If this is the first year of data, there are no prior periods to compare against.")
        st.stop()

    inc = changes_sel[changes_sel["price_delta"] > 0]
    dec = changes_sel[changes_sel["price_delta"] < 0]
    brands_with_changes = changes_sel["brand"].nunique()
    brands_total = df_raw["brand"].nunique()

    # ── KPI strip ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Brands active", f"{brands_with_changes} / {brands_total}")
    k2.metric(
        "Market median abs move",
        f"£+{inc['price_delta'].median():.2f}" if len(inc) > 0 else "—",
        help="Median absolute £ increase on items that were raised. Unweighted.",
    )
    k3.metric(
        "Market median % move",
        f"{inc['pct_change'].median():.1f}%" if len(inc) > 0 else "—",
        help="Directional signal only — no volume weighting.",
    )
    k4.metric(
        "Brands yet to price",
        str(brands_total - brands_with_changes),
    )

    st.caption(
        "⚠️ Median % move is unweighted across items — a £1 sauce counts equally to a £14 main. "
        "Use the absolute £ move as the primary measure. Effective customer bill impact cannot be "
        "calculated without volume data."
    )

    st.markdown("---")

    # ── Classification breakdown ───────────────────────────────────────────────
    st.subheader("How brands are pricing")
    summary_df = brand_summary(changes_sel, menu_sizes)

    class_counts = summary_df["Classification"].value_counts()
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Classification breakdown**")
        for cls, count in class_counts.items():
            st.markdown(f"- **{cls}**: {count} brand{'s' if count > 1 else ''}")

    with col_b:
        st.markdown("**Clean upward movers** (zero offsetting cuts)")
        clean = summary_df[summary_df["Items Cut"] == 0][
            summary_df["Items Raised"] > 2
        ][["Brand", "Breadth %", "Median Abs Move", "Classification"]]
        if len(clean) > 0:
            st.dataframe(clean, hide_index=True, use_container_width=True)
        else:
            st.caption("None in selected period.")

    st.markdown("---")

    # ── Monthly activity ───────────────────────────────────────────────────────
    st.subheader("When are brands pricing?")
    monthly = (
        changes_sel[changes_sel["price_delta"] > 0]
        .groupby("month_num")
        .size()
        .reset_index(name="count")
    )
    monthly["month"] = monthly["month_num"].map(MONTH_NAMES)
    monthly = monthly.sort_values("month_num")
    if len(monthly) > 0:
        st.bar_chart(monthly.set_index("month")["count"])
        st.caption("Number of individual item price increases by month.")

    # ── Brands not yet priced ──────────────────────────────────────────────────
    brands_changed = set(changes_sel["brand"].unique())
    brands_all_set = set(df_raw["brand"].unique())
    not_priced = sorted(brands_all_set - brands_changed)
    if not_priced:
        st.markdown("---")
        st.subheader(f"Brands yet to price ({len(not_priced)})")
        st.write(", ".join(not_priced))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — BRAND DETAIL
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Brand Detail")

    selected_brand = st.selectbox("Select a brand", options=all_brands)
    compare_year_a, compare_year_b = st.columns(2)
    with compare_year_a:
        year_from = st.selectbox("From year", options=sorted(all_years), index=len(all_years) - 1)
    with compare_year_b:
        year_to = st.selectbox("To year", options=sorted(all_years), index=0)

    if year_from and year_to and selected_brand:
        df_brand = load_data(brand_filter=[selected_brand])
        changes_brand = compute_changes(df_brand)

        # Price history for key items
        st.subheader(f"{selected_brand} — item price history")
        pivot = (
            df_brand.groupby(["item_name", "year"])["price"]
            .median()
            .unstack()
            .dropna(thresh=2)
        )
        if year_from in pivot.columns and year_to in pivot.columns:
            pivot["change"] = pivot[year_to] - pivot[year_from]
            pivot["change_pct"] = (
                (pivot[year_to] - pivot[year_from]) / pivot[year_from] * 100
            ).round(1)
            pivot = pivot.sort_values("change_pct", ascending=False)
            st.dataframe(
                pivot[[year_from, year_to, "change", "change_pct"]].rename(
                    columns={
                        year_from: f"£ {year_from}",
                        year_to: f"£ {year_to}",
                        "change": "£ change",
                        "change_pct": "% change",
                    }
                ).style.format({
                    f"£ {year_from}": "£{:.2f}",
                    f"£ {year_to}": "£{:.2f}",
                    "£ change": "£{:+.2f}",
                    "% change": "{:+.1f}%",
                }),
                use_container_width=True,
                height=400,
            )
            st.caption(
                "⚠️ % change is shown for reference. Without volume data it should not be "
                "read as the effective price increase experienced by customers."
            )
        else:
            st.info(f"Insufficient data to compare {year_from} vs {year_to} for this brand.")

        # 2026-period changes detail
        if changes_brand is not None and len(changes_brand) > 0:
            latest_year = int(changes_brand["year"].max())
            recent = changes_brand[changes_brand["year"] == latest_year]
            st.subheader(f"{selected_brand} — {latest_year} price changes")
            inc_b = recent[recent["price_delta"] > 0]
            dec_b = recent[recent["price_delta"] < 0]

            m1, m2, m3 = st.columns(3)
            m1.metric("Items raised", len(inc_b))
            m2.metric("Items cut", len(dec_b))
            m3.metric(
                "Median abs move",
                f"£+{inc_b['price_delta'].median():.2f}" if len(inc_b) > 0 else "—",
            )

            menu_n = df_brand[df_brand["year"] == latest_year]["item_name"].nunique()
            breadth = round(inc_b["item_name"].nunique() / menu_n * 100, 1) if menu_n > 0 else 0
            med_abs = inc_b["price_delta"].median() if len(inc_b) > 0 else 0
            cls = classify_brand(
                inc_b["item_name"].nunique(),
                dec_b["item_name"].nunique(),
                breadth, med_abs
            )
            st.markdown(f"**Classification:** {cls} &nbsp;|&nbsp; **Breadth:** {breadth}% of {latest_year} menu")

            if len(inc_b) > 0:
                st.markdown("**Items raised (sorted by largest absolute move):**")
                show = inc_b[["item_name", "prev_price", "price", "price_delta", "pct_change", "month_num"]].copy()
                show["month"] = show["month_num"].map(MONTH_NAMES)
                show = show.drop(columns=["month_num"]).sort_values("price_delta", ascending=False)
                show.columns = ["Item", "Previous £", "New £", "£ change", "% change", "Month"]
                st.dataframe(
                    show.style.format({
                        "Previous £": "£{:.2f}",
                        "New £": "£{:.2f}",
                        "£ change": "£{:+.2f}",
                        "% change": "{:+.1f}%",
                    }),
                    hide_index=True,
                    use_container_width=True,
                    height=300,
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FULL TABLE
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Full Brand Comparison Table")

    t3_years = st.multiselect(
        "Years",
        options=all_years,
        default=[all_years[0]] if all_years else [],
        key="t3_years",
    )

    if t3_years:
        df_t3 = load_data(year_filter=t3_years)
        menu_sizes_t3 = df_t3.groupby("brand")["item_name"].nunique().to_dict()
        df_all_t3 = load_data()
        changes_t3 = compute_changes(df_all_t3)
        changes_t3_sel = changes_t3[changes_t3["year"].isin(t3_years)]

        table = brand_summary(changes_t3_sel, menu_sizes_t3)

        # Also show brands with no changes
        brands_no_change = [
            b for b in df_t3["brand"].unique() if b not in changes_t3_sel["brand"].unique()
        ]
        if brands_no_change:
            no_change_rows = pd.DataFrame([{
                "Brand": b,
                "2026 Menu Items": menu_sizes_t3.get(b, 0),
                "Items Raised": 0,
                "Breadth %": 0,
                "Items Cut": 0,
                "Median Abs Move": "—",
                "Median % Move*": "—",
                "Primary Month": "—",
                "Classification": "No changes",
            } for b in sorted(brands_no_change)])
            table = pd.concat([table, no_change_rows], ignore_index=True)

        st.dataframe(
            table.style.map(colour_class, subset=["Classification"]),
            hide_index=True,
            use_container_width=True,
            height=600,
        )

        st.caption(
            "* Median % move is unweighted across items that changed. Directional indicator only. "
            "Breadth uses items present in the selected year as denominator."
        )

        # Download
        csv = table.to_csv(index=False)
        st.download_button(
            "Download as CSV",
            data=csv,
            file_name=f"pricing_comparison_{'_'.join(str(y) for y in t3_years)}.csv",
            mime="text/csv",
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ASK A QUESTION
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Ask a Question")
    st.markdown(
        "Type any question about the pricing data. The answer will draw on the actual "
        "numbers in the database and apply the same methodology used throughout this tool."
    )

    if not api_key:
        st.warning("No API key found. Add your Claude API key to the .env file to use this feature — see the setup guide.")
    else:
        q_years = st.multiselect(
            "Data scope (years)",
            options=all_years,
            default=[all_years[0]] if all_years else [],
            key="q_years",
        )
        q_brands = st.multiselect(
            "Limit to specific brands (optional — leave blank for all)",
            options=all_brands,
            default=[],
            key="q_brands",
        )

        question = st.text_area(
            "Your question",
            placeholder="e.g. Which brands have repriced their mains by more than £1 this year?\n"
                        "e.g. How does Nando's compare to KFC in terms of pricing behaviour?\n"
                        "e.g. Which brands are showing menu restructuring signs?",
            height=100,
        )

        if st.button("Get answer", type="primary"):
            if not question.strip():
                st.warning("Please type a question first.")
            else:
                with st.spinner("Analysing..."):
                    context = load_data(
                        year_filter=q_years if q_years else None,
                        brand_filter=q_brands if q_brands else None,
                    )
                    df_ctx = load_data()
                    changes_ctx = compute_changes(df_ctx)
                    if q_years:
                        changes_ctx = changes_ctx[changes_ctx["year"].isin(q_years)]
                    if q_brands:
                        changes_ctx = changes_ctx[changes_ctx["brand"].isin(q_brands)]

                    menu_ctx = context.groupby("brand")["item_name"].nunique().to_dict()
                    summary_ctx = brand_summary(changes_ctx, menu_ctx)

                    try:
                        answer = ask_claude(question, summary_ctx, api_key)
                        st.markdown("### Answer")
                        st.markdown(answer)
                        st.caption(
                            "This answer is generated by Claude using the pricing data in your "
                            "database. All methodology caveats apply — see the Market Overview tab."
                        )
                    except Exception as e:
                        st.error(f"Error calling Claude API: {e}")

