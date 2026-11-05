import os
import subprocess
import sys
from pathlib import Path

# Add core and root directories to path
CORE_DIR = Path(__file__).resolve().parent.parent / "core"
ROOT_DIR = Path(__file__).resolve().parent.parent

if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(1, str(ROOT_DIR))

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.queries import (
    get_all_movies_table,
    get_category_stats_df,
    get_collections_df,
    get_imdb_differences_df,
    get_kpis,
    get_rating_distribution_df,
    get_release_year_df,
    get_top_people_df,
)

# Page configuration
st.set_page_config(
    page_title="Letterboxd Data Analyzer",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling (Letterboxd inspired colors: #14181c, #00d75a, #40bcf4, #ff8000)
st.markdown("""
<style>
    .metric-card {
        background-color: #1a2228;
        border-radius: 8px;
        padding: 16px;
        border-left: 4px solid #00d75a;
        margin-bottom: 12px;
    }
    .metric-title {
        color: #9ab;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .metric-value {
        color: #fff;
        font-size: 1.8rem;
        font-weight: 700;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 18px;
        border-radius: 4px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# --- SIDEBAR ---
with st.sidebar:
    st.image("https://a.ltrbxd.com/logos/letterboxd-logo-v-neg-rgb-1000px.png", width=180)
    st.title("Letterboxd Analyzer")
    st.caption("Interactive Movie Statistics Dashboard")

    st.markdown("---")

    # Fetch KPIs to show DB status
    try:
        kpis = get_kpis()
        st.success(f"Connected: **{kpis['total_movies']}** active movies in database")
        st.write(f"📅 **Last Import:** `{kpis['last_import']}`")
        st.write(f"⭐ **IMDb Dataset:** `{kpis['last_imdb']}`")
    except Exception as e:
        st.error(f"Database error: {e}")
        kpis = {
            "total_movies": 0, "avg_rating": 0, "total_runtime_hours": 0,
            "total_runtime_days": 0, "unique_directors": 0, "unique_actors": 0,
            "total_collections": 0
        }

    st.markdown("---")
    st.subheader("Data Management")

    if st.button("🔄 Run Data Import (main.py)", use_container_width=True, help="Run main.py pipeline to import/update exports"):
        with st.spinner("Launching main.py data ingestion pipeline..."):
            try:
                python_exe = sys.executable
                main_script = ROOT_DIR / "main.py"
                cmd = [python_exe, str(main_script), "--latest"]
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=120)
                if proc.returncode == 0:
                    st.success("Data ingestion completed successfully!")
                    st.rerun()
                else:
                    st.error(f"Ingestion failed:\n{proc.stderr}")
            except Exception as ex:
                st.error(f"Error running pipeline: {ex}")

    st.info("💡 You can run `main.py` directly from your terminal or click the button above to refresh.")


# --- MAIN HEADER ---
st.title("🎬 Letterboxd Personal Film Statistics")
st.write("Visualizations generated from your Letterboxd exports, TMDb metadata, and official IMDb datasets.")

# --- METRIC CARDS ROW ---
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: #00d75a;">
        <div class="metric-title">Total Movies</div>
        <div class="metric-value">{kpis['total_movies']}</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: #40bcf4;">
        <div class="metric-title">Average Rating</div>
        <div class="metric-value">{kpis['avg_rating']} <span style="font-size: 1rem; color: #ff8000;">★</span></div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: #ff8000;">
        <div class="metric-title">Time Watched</div>
        <div class="metric-value">{kpis['total_runtime_hours']:,} <span style="font-size: 1rem; color: #9ab;">hrs</span></div>
    </div>
    """, unsafe_allow_html=True)
with col4:
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: #a768ff;">
        <div class="metric-title">Unique Directors</div>
        <div class="metric-value">{kpis['unique_directors']}</div>
    </div>
    """, unsafe_allow_html=True)
with col5:
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: #00c030;">
        <div class="metric-title">Collections</div>
        <div class="metric-value">{kpis['total_collections']}</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# --- TABS FOR DETAILED SECTIONS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Ratings & Release Years",
    "🏷️ Genres, Countries & Languages",
    "👥 Cast & Directors",
    "⚖️ IMDb Differences",
    "📦 Film Collections",
    "🔍 Movie Explorer",
])

# ==========================================
# TAB 1: RATINGS & RELEASE YEARS
# ==========================================
with tab1:
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("⭐ Rating Distribution")
        st.caption("Vertical bar graph of total movies per rating (scale 1 to 10)")
        df_ratings = get_rating_distribution_df()

        fig_rating = px.bar(
            df_ratings,
            x="rating_scale_10",
            y="movie_count",
            text="movie_count",
            hover_data={"letterboxd_stars": True, "movie_count": True, "rating_scale_10": True},
            color="movie_count",
            color_continuous_scale="Greens",
            labels={"rating_scale_10": "Rating (1 to 10)", "movie_count": "Total Movies"}
        )
        fig_rating.update_layout(
            xaxis=dict(tickmode="linear", tick0=1, dtick=1),
            coloraxis_showscale=False,
            margin=dict(l=10, r=10, t=20, b=30),
            height=380,
        )
        st.plotly_chart(fig_rating, use_container_width=True)

    with col_right:
        st.subheader("📅 Release Year Distribution")
        group_mode = st.radio("Group By:", ["Year", "Decade"], horizontal=True, key="year_toggle")
        st.caption(f"Distribution of films by released {group_mode.lower()}")

        df_years = get_release_year_df(group_by=group_mode.lower())
        if not df_years.empty:
            fig_year = px.bar(
                df_years,
                x="period",
                y="movie_count",
                text="movie_count",
                color="movie_count",
                color_continuous_scale="Blues",
                labels={"period": group_mode, "movie_count": "Total Movies"}
            )
            fig_year.update_layout(
                coloraxis_showscale=False,
                margin=dict(l=10, r=10, t=20, b=30),
                height=380,
            )
            st.plotly_chart(fig_year, use_container_width=True)
        else:
            st.info("No movie release year data available.")


# ==========================================
# TAB 2: GENRES, COUNTRIES & LANGUAGES
# ==========================================
with tab2:
    st.subheader("Top Categories")

    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        cat_choice = st.selectbox(
            "Select Dimension:",
            ["genres", "countries", "languages", "years"],
            format_func=lambda x: {
                "genres": "🎬 Film Genres",
                "countries": "🌍 Origin Countries (pycountry)",
                "languages": "🗣️ Languages (pycountry)",
                "years": "📅 Release Years",
            }[x]
        )
    with c2:
        mode_choice = st.radio(
            "Sorting Metric:",
            ["most_watched", "highest_average"],
            format_func=lambda x: "Most Watched (Count)" if x == "most_watched" else "Highest Average Rating",
            horizontal=True
        )

    st.caption("Note: 'Highest Average' includes categories with at least min(10, 5% of total movies).")

    df_cat = get_category_stats_df(category=cat_choice, mode=mode_choice, limit=15)

    if not df_cat.empty:
        metric_col = "movie_count" if mode_choice == "most_watched" else "avg_rating"
        color_seq = "Viridis" if mode_choice == "most_watched" else "Inferno"

        fig_cat = px.bar(
            df_cat.sort_values(by=metric_col, ascending=True),
            x=metric_col,
            y="item_name",
            orientation="h",
            text=metric_col,
            color=metric_col,
            color_continuous_scale=color_seq,
            labels={
                "item_name": cat_choice.capitalize(),
                "movie_count": "Films Watched",
                "avg_rating": "Avg Rating (/10)"
            }
        )
        fig_cat.update_layout(
            margin=dict(l=10, r=10, t=20, b=30),
            height=460,
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig_cat, use_container_width=True)
    else:
        st.info("No items qualify under the current filter.")


# ==========================================
# TAB 3: CAST & DIRECTORS
# ==========================================
with tab3:
    st.subheader("Top Cast & Crew")

    person_role = st.radio(
        "Choose Role:",
        ["directors", "actors"],
        format_func=lambda x: "🎬 Directors" if x == "directors" else "🎭 Actors (Top 25 billed)",
        horizontal=True
    )

    df_people = get_top_people_df(role=person_role, limit=15)

    if not df_people.empty:
        fig_people = px.bar(
            df_people.sort_values(by="movie_count", ascending=True),
            x="movie_count",
            y="person_name",
            orientation="h",
            text="movie_count",
            hover_data={"avg_rating": True},
            color="avg_rating",
            color_continuous_scale="Purples",
            labels={
                "person_name": "Person",
                "movie_count": "Movies Watched",
                "avg_rating": "Avg Rating (/10)"
            }
        )
        fig_people.update_layout(
            margin=dict(l=10, r=10, t=20, b=30),
            height=460,
            coloraxis_colorbar=dict(title="Avg Rating (/10)"),
        )
        st.plotly_chart(fig_people, use_container_width=True)
    else:
        st.info("No crew/cast data available.")


# ==========================================
# TAB 4: IMDB DIFFERENCES
# ==========================================
with tab4:
    st.subheader("⚖️ Largest Rating Divergence vs. IMDb")
    st.caption("Compares your rating (scaled to 10) with the IMDb average for films with ≥ 1,000 votes.")

    df_pos, df_neg = get_imdb_differences_df(limit=10)

    col_pos, col_neg = st.columns(2)

    with col_pos:
        st.markdown("#### 🟢 Rated Much Higher than IMDb")
        st.caption("You loved these much more than the global IMDb audience:")
        if not df_pos.empty:
            for _, r in df_pos.iterrows():
                diff_str = f"+{r['difference']:.1f}"
                st.markdown(f"""
                <div style="background-color: #1a2228; padding: 10px 14px; border-radius: 6px; margin-bottom: 8px; border-left: 4px solid #00d75a;">
                    <div style="font-weight: 600; font-size: 1rem; color: #fff;">{r['title']} <span style="color: #9ab; font-size: 0.85rem;">({r['year']})</span></div>
                    <div style="font-size: 0.9rem; color: #ccc; margin-top: 3px;">
                        You: <b style="color: #00d75a;">{r['your_rating']}/10</b> &nbsp;|&nbsp;
                        IMDb: <b style="color: #40bcf4;">{r['imdb_rating']}/10</b> &nbsp;|&nbsp;
                        Diff: <span style="background-color: #0d381e; color: #00d75a; padding: 2px 6px; border-radius: 4px; font-weight: bold;">{diff_str}</span>
                        <span style="color: #667; font-size: 0.8rem; float: right;">{int(r['imdb_votes']):,} votes</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No qualifying positive difference records.")

    with col_neg:
        st.markdown("#### 🔴 Rated Much Lower than IMDb")
        st.caption("You rated these significantly lower than the global IMDb consensus:")
        if not df_neg.empty:
            for _, r in df_neg.iterrows():
                diff_str = f"{r['difference']:.1f}"
                st.markdown(f"""
                <div style="background-color: #1a2228; padding: 10px 14px; border-radius: 6px; margin-bottom: 8px; border-left: 4px solid #ff4444;">
                    <div style="font-weight: 600; font-size: 1rem; color: #fff;">{r['title']} <span style="color: #9ab; font-size: 0.85rem;">({r['year']})</span></div>
                    <div style="font-size: 0.9rem; color: #ccc; margin-top: 3px;">
                        You: <b style="color: #ff4444;">{r['your_rating']}/10</b> &nbsp;|&nbsp;
                        IMDb: <b style="color: #40bcf4;">{r['imdb_rating']}/10</b> &nbsp;|&nbsp;
                        Diff: <span style="background-color: #3d1414; color: #ff5555; padding: 2px 6px; border-radius: 4px; font-weight: bold;">{diff_str}</span>
                        <span style="color: #667; font-size: 0.8rem; float: right;">{int(r['imdb_votes']):,} votes</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No qualifying negative difference records.")


# ==========================================
# TAB 5: COLLECTIONS
# ==========================================
with tab5:
    st.subheader("📦 Franchise & Collection Completion")
    st.caption("Tracks how many released films you have watched in each movie franchise.")

    df_colls = get_collections_df()

    if not df_colls.empty:
        col_grid1, col_grid2 = st.columns(2)
        for idx, row in df_colls.iterrows():
            target_col = col_grid1 if idx % 2 == 0 else col_grid2
            with target_col:
                pct = min(100.0, float(row["percent_completed"]))
                color = "#00d75a" if pct == 100.0 else "#40bcf4"

                st.markdown(f"""
                <div style="background-color: #1a2228; padding: 14px; border-radius: 8px; margin-bottom: 12px; border: 1px solid #2a343d;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 700; font-size: 1.05rem; color: #fff;">{row['collection_name']}</span>
                        <span style="color: {color}; font-weight: bold;">{int(row['watched_count'])} / {int(row['total_movies'])} ({pct:.0f}%)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                st.progress(pct / 100.0)
    else:
        st.info("No collections data available.")


# ==========================================
# TAB 6: MOVIE EXPLORER
# ==========================================
with tab6:
    st.subheader("🔍 Movie Explorer")
    st.caption("Browse and search all active movies in your database")

    df_all = get_all_movies_table()

    if not df_all.empty:
        f1, f2 = st.columns([3, 1])
        with f1:
            search_query = st.text_input("Search Title or Collection:", placeholder="e.g. John Wick, Avengers, Nolan...")
        with f2:
            min_stars = st.slider("Minimum Rating (★):", 0.0, 5.0, 0.0, step=0.5)

        filtered_df = df_all.copy()

        if search_query:
            q = search_query.strip().lower()
            filtered_df = filtered_df[
                filtered_df["Title"].str.lower().str.contains(q, na=False) |
                filtered_df["Collection"].str.lower().str.contains(q, na=False)
            ]

        if min_stars > 0:
            filtered_df = filtered_df[filtered_df["Rating"] >= min_stars]

        st.dataframe(
            filtered_df[[
                "Title", "Year", "Rating", "Watched On",
                "IMDb Rating", "IMDb Votes", "Runtime (min)", "Lang", "Collection"
            ]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rating": st.column_config.NumberColumn(format="%.1f ★"),
                "IMDb Rating": st.column_config.NumberColumn(format="%.1f / 10"),
                "IMDb Votes": st.column_config.NumberColumn(format="%d"),
            }
        )
        st.caption(f"Showing {len(filtered_df)} of {len(df_all)} movies.")
    else:
        st.info("No movies found in the database. Run data import first.")
