# -*- coding: utf-8 -*-
"""
Streamlit Dashboard for RedLens
Interactive visualization and control panel
"""

import sys
from pathlib import Path

# Add parent directory to path
MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from red_lens.db import BloggerDB, NoteDB, init_db
from red_lens.discovery import search_and_extract_users
from red_lens.pipeline import scrape_pending_bloggers
from red_lens.analyzer import (
    analyze_blogger,
    analyze_all_bloggers,
    download_outlier_covers,
    generate_ai_report
)


# Page configuration
st.set_page_config(
    page_title="RedLens - 小红书摄影博主分析",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database
init_db()


def main():
    """Main Streamlit app"""

    # Title
    st.title("📸 RedLens - 小红书摄影博主分析工具")
    st.markdown("---")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ 控制面板")

        # Section 1: Discovery
        st.subheader("🔍 博主发现")

        keywords_input = st.text_input(
            "搜索关键词 (逗号分隔)",
            value="富士扫街,人像摄影,胶片色调",
            help="输入关键词，用逗号分隔"
        )

        min_likes = st.slider(
            "最低点赞数过滤",
            min_value=0,
            max_value=1000,
            value=200,
            step=50,
            help="仅保留笔记点赞数超过此值的博主"
        )

        # Add mode selection
        run_mode = st.radio(
            "运行模式",
            options=["使用现有数据", "运行 MediaCrawler 爬取"],
            help="选择是使用已有JSON数据还是运行MediaCrawler获取新数据"
        )

        use_existing = (run_mode == "使用现有数据")

        if st.button("🚀 开始发现博主", type="primary", use_container_width=True):
            keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

            if not use_existing:
                st.warning("⚠️ 即将启动 MediaCrawler，需要浏览器交互（登录、验证等）")
                st.info("请在弹出的浏览器窗口中完成登录步骤")

            with st.spinner("正在搜索博主..." if use_existing else "正在运行 MediaCrawler..."):
                new_count = search_and_extract_users(
                    keywords,
                    min_likes=min_likes,
                    use_existing=use_existing
                )
                st.success(f"✓ 发现 {new_count} 位新博主!")
                st.rerun()

        st.markdown("---")

        # Section 2: Scraping
        st.subheader("📥 数据采集")

        pending_count = BloggerDB.count_by_status("pending")
        st.info(f"待采集博主: {pending_count} 位")

        scrape_limit = st.number_input(
            "采集博主数量",
            min_value=1,
            max_value=20,
            value=5,
            help="每次采集的博主数量"
        )

        max_notes_per_blogger = st.slider(
            "每个博主爬取笔记数量",
            min_value=10,
            max_value=200,
            value=100,
            step=10,
            help="每个博主最多爬取的笔记数量（默认100条）"
        )

        if st.button("📊 开始采集数据", use_container_width=True):
            if pending_count == 0:
                st.warning("没有待采集的博主")
            else:
                with st.spinner(f"正在采集数据（每位博主最多{max_notes_per_blogger}条笔记）..."):
                    stats = scrape_pending_bloggers(
                        limit=scrape_limit,
                        max_notes=max_notes_per_blogger,
                        use_existing_data=False
                    )
                    st.success(f"✓ 采集完成! 成功: {stats['scraped']}, 失败: {stats['failed']}, 笔记: {stats['notes_added']}")
                    st.rerun()

        st.markdown("---")

        # Section 3: Analysis
        st.subheader("🔬 数据分析")

        if st.button("🔥 识别所有爆款", use_container_width=True):
            with st.spinner("正在分析..."):
                analyses = analyze_all_bloggers()
                st.success(f"✓ 分析完成! 共分析 {len(analyses)} 位博主")
                st.rerun()

        if st.button("📥 下载爆款封面", use_container_width=True):
            with st.spinner("正在下载封面图..."):
                count = download_outlier_covers()
                st.success(f"✓ 下载完成! 共下载 {count} 张封面")
                st.rerun()

        st.markdown("---")

        # Database stats
        st.subheader("📈 数据库统计")
        total_bloggers = len(BloggerDB.get_all_bloggers())
        scraped_count = BloggerDB.count_by_status("scraped")
        error_count = BloggerDB.count_by_status("error")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("总博主", total_bloggers)
            st.metric("已采集", scraped_count)
        with col2:
            st.metric("待采集", pending_count)
            st.metric("失败", error_count)

    # Main area
    tab1, tab2, tab3 = st.tabs(["📊 博主排行", "🔥 爆款画廊", "📈 详细分析"])

    with tab1:
        show_blogger_ranking()

    with tab2:
        show_outlier_gallery()

    with tab3:
        show_detailed_analysis()


def show_blogger_ranking():
    """Display blogger ranking"""
    st.header("📊 博主排行榜")

    # Get all scraped bloggers
    scraped_bloggers = [b for b in BloggerDB.get_all_bloggers() if b["status"] == "scraped"]

    if not scraped_bloggers:
        st.info("暂无已采集的博主数据。请先使用侧边栏的「数据采集」功能。")
        return

    # Analyze all bloggers
    analyses = []
    for blogger in scraped_bloggers:
        analysis = analyze_blogger(blogger["user_id"])
        if "error" not in analysis:
            analyses.append(analysis)

    if not analyses:
        st.warning("分析失败，请检查数据")
        return

    # Sort by outlier rate
    analyses.sort(key=lambda x: (x["outlier_rate"], x["avg_likes"]), reverse=True)

    # Create DataFrame
    df_data = []
    for analysis in analyses:
        blogger = analysis["blogger"]
        df_data.append({
            "博主昵称": blogger["nickname"],
            "总笔记数": analysis["total_notes"],
            "平均点赞": int(analysis["avg_likes"]),
            "爆款数量": analysis["outlier_count"],
            "爆款率": f"{analysis['outlier_rate']:.1%}",
            "总互动量": analysis["total_engagement"],
            "来源关键词": blogger["source_keyword"] or "N/A",
            "user_id": blogger["user_id"]  # Hidden column for selection
        })

    df = pd.DataFrame(df_data)

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("博主总数", len(analyses))
    with col2:
        total_notes = sum(a["total_notes"] for a in analyses)
        st.metric("总笔记数", total_notes)
    with col3:
        total_outliers = sum(a["outlier_count"] for a in analyses)
        st.metric("总爆款数", total_outliers)
    with col4:
        avg_outlier_rate = sum(a["outlier_rate"] for a in analyses) / len(analyses)
        st.metric("平均爆款率", f"{avg_outlier_rate:.1%}")

    st.markdown("---")

    # Display table
    st.subheader("博主列表 (按爆款率排序)")

    # Show dataframe without user_id column
    display_df = df.drop(columns=["user_id"])
    st.dataframe(
        display_df,
        use_container_width=True,
        height=400
    )

    # Visualization: Bar chart
    st.markdown("---")
    st.subheader("📊 可视化分析")

    col1, col2 = st.columns(2)

    with col1:
        # Outlier rate chart
        fig1 = px.bar(
            df.head(10),
            x="博主昵称",
            y="爆款率",
            title="Top 10 博主爆款率",
            color="爆款率",
            color_continuous_scale="Reds"
        )
        fig1.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        # Average likes chart
        fig2 = px.bar(
            df.head(10),
            x="博主昵称",
            y="平均点赞",
            title="Top 10 博主平均点赞数",
            color="平均点赞",
            color_continuous_scale="Blues"
        )
        fig2.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig2, use_container_width=True)

    # Scatter plot: Notes vs Outlier Rate
    fig3 = px.scatter(
        df,
        x="总笔记数",
        y="爆款率",
        size="平均点赞",
        color="爆款数量",
        hover_data=["博主昵称"],
        title="笔记数量 vs 爆款率 (气泡大小=平均点赞)",
        color_continuous_scale="Viridis"
    )
    st.plotly_chart(fig3, use_container_width=True)


def show_outlier_gallery():
    """Display outlier notes gallery"""
    st.header("🔥 爆款内容画廊")

    # Get all outlier notes
    outlier_notes = NoteDB.get_outlier_notes()

    if not outlier_notes:
        st.info("暂无爆款内容。请先使用侧边栏的「数据分析」功能识别爆款。")
        return

    # Sort by likes
    outlier_notes.sort(key=lambda x: x["likes"], reverse=True)

    st.success(f"共发现 {len(outlier_notes)} 篇爆款内容")

    # Filter options
    col1, col2 = st.columns([1, 3])
    with col1:
        min_likes_filter = st.number_input("最低点赞数", value=0, step=1000)
    with col2:
        # Get unique users
        users = list(set(note["user_id"] for note in outlier_notes))
        user_names = {}
        for user_id in users:
            blogger = BloggerDB.get_blogger(user_id)
            if blogger:
                user_names[user_id] = blogger["nickname"]

        selected_user = st.selectbox(
            "筛选博主",
            options=["全部"] + list(user_names.values())
        )

    # Apply filters
    filtered_notes = outlier_notes
    if min_likes_filter > 0:
        filtered_notes = [n for n in filtered_notes if n["likes"] >= min_likes_filter]

    if selected_user != "全部":
        selected_user_id = [uid for uid, name in user_names.items() if name == selected_user][0]
        filtered_notes = [n for n in filtered_notes if n["user_id"] == selected_user_id]

    st.markdown(f"**筛选后: {len(filtered_notes)} 篇**")
    st.markdown("---")

    # Display in grid
    cols_per_row = 3
    for i in range(0, len(filtered_notes), cols_per_row):
        cols = st.columns(cols_per_row)

        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(filtered_notes):
                break

            note = filtered_notes[idx]
            blogger = BloggerDB.get_blogger(note["user_id"])
            blogger_name = blogger["nickname"] if blogger else "Unknown"

            with col:
                # Card container
                with st.container():
                    st.markdown(f"### {note['title'][:30]}...")

                    # Display image if available
                    if note["local_cover_path"]:
                        try:
                            st.image(note["local_cover_path"], use_container_width=True)
                        except:
                            st.info("封面图加载失败")
                    elif note["cover_url"]:
                        st.info("封面未下载")
                    else:
                        st.info("无封面图")

                    # Metrics
                    metric_col1, metric_col2, metric_col3 = st.columns(3)
                    with metric_col1:
                        st.metric("❤️ 点赞", f"{note['likes']:,}")
                    with metric_col2:
                        st.metric("⭐ 收藏", f"{note['collects']:,}")
                    with metric_col3:
                        st.metric("💬 评论", f"{note['comments']:,}")

                    # Author and type
                    st.caption(f"👤 {blogger_name}")
                    st.caption(f"📝 {note['type']} | 🕐 {note['create_time']}")

                    # Link
                    if note.get("note_url"):
                        st.link_button("查看原文", note["note_url"], use_container_width=True)

                st.markdown("---")


def show_detailed_analysis():
    """Display detailed analysis for selected blogger"""
    st.header("📈 博主详细分析")

    # Get all scraped bloggers
    scraped_bloggers = [b for b in BloggerDB.get_all_bloggers() if b["status"] == "scraped"]

    if not scraped_bloggers:
        st.info("暂无已采集的博主数据。")
        return

    # Blogger selection
    blogger_names = {b["user_id"]: b["nickname"] for b in scraped_bloggers}
    selected_name = st.selectbox(
        "选择博主",
        options=list(blogger_names.values())
    )

    # Find user_id
    selected_user_id = [uid for uid, name in blogger_names.items() if name == selected_name][0]

    # Analyze
    analysis = analyze_blogger(selected_user_id)

    if "error" in analysis:
        st.error(f"分析失败: {analysis['error']}")
        return

    blogger = analysis["blogger"]

    # Display header
    col1, col2 = st.columns([1, 3])
    with col1:
        if blogger["avatar_url"]:
            st.image(blogger["avatar_url"], width=150)
        else:
            st.info("无头像")
    with col2:
        st.subheader(blogger["nickname"])
        st.caption(f"User ID: {blogger['user_id']}")
        st.caption(f"状态: {blogger['status']} | 来源: {blogger['source_keyword']}")

    st.markdown("---")

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总笔记数", analysis["total_notes"])
    with col2:
        st.metric("平均点赞", f"{analysis['avg_likes']:.0f}")
    with col3:
        st.metric("爆款数量", analysis["outlier_count"])
    with col4:
        st.metric("爆款率", f"{analysis['outlier_rate']:.1%}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总点赞", f"{analysis['total_likes']:,}")
    with col2:
        st.metric("总收藏", f"{analysis['total_collects']:,}")
    with col3:
        st.metric("总评论", f"{analysis['total_comments']:,}")
    with col4:
        st.metric("平均互动", f"{analysis['avg_engagement']:.0f}")

    st.markdown("---")

    # Content distribution
    st.subheader("📊 内容分布")
    col1, col2 = st.columns(2)

    with col1:
        # Pie chart: Content type
        fig_pie = go.Figure(data=[go.Pie(
            labels=["图文", "视频"],
            values=[analysis["image_count"], analysis["video_count"]],
            hole=0.3
        )])
        fig_pie.update_layout(title="内容类型分布")
        st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        # Bar chart: Outlier vs Normal
        fig_bar = go.Figure(data=[go.Bar(
            x=["普通内容", "爆款内容"],
            y=[analysis["total_notes"] - analysis["outlier_count"], analysis["outlier_count"]],
            marker_color=["lightblue", "red"]
        )])
        fig_bar.update_layout(title="内容质量分布", yaxis_title="数量")
        st.plotly_chart(fig_bar, use_container_width=True)

    # Notes timeline
    st.subheader("📈 笔记数据趋势")

    notes = NoteDB.get_notes_by_user(selected_user_id)
    if notes:
        df_notes = pd.DataFrame(notes)

        # Line chart: Likes over time
        fig_line = px.line(
            df_notes,
            x="create_time",
            y="likes",
            title="点赞数时间趋势",
            markers=True
        )
        fig_line.update_traces(line_color="red")
        st.plotly_chart(fig_line, use_container_width=True)

    # AI Report
    st.markdown("---")
    st.subheader("🤖 AI 洞察报告")

    if st.button("生成 AI 报告", type="primary"):
        with st.spinner("AI 正在分析..."):
            report = generate_ai_report(selected_user_id, use_mock=True)
            st.markdown(report)

    # Top notes
    st.markdown("---")
    st.subheader("🔝 热门笔记 Top 10")

    if notes:
        top_notes = sorted(notes, key=lambda x: x["likes"], reverse=True)[:10]

        df_top = pd.DataFrame([{
            "标题": note["title"][:40] + "...",
            "类型": note["type"],
            "点赞": note["likes"],
            "收藏": note["collects"],
            "评论": note["comments"],
            "发布时间": note["create_time"],
            "是否爆款": "🔥" if note["is_outlier"] else ""
        } for note in top_notes])

        st.dataframe(df_top, use_container_width=True, height=400)


if __name__ == "__main__":
    main()
