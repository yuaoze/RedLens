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
from red_lens.pipeline import scrape_pending_bloggers, collect_blogger_by_manual_id
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

        # Check for resumable bloggers
        resumable_count = BloggerDB.count_resumable_bloggers()
        pending_count = BloggerDB.count_by_status("pending")

        # Display status
        col_status1, col_status2 = st.columns(2)
        with col_status1:
            st.metric("待采集博主", pending_count)
        with col_status2:
            st.metric("可恢复采集", resumable_count)

        # Mode selection
        collection_mode = st.radio(
            "采集模式",
            options=["正常采集", "恢复采集"],
            help="正常采集：采集新的待处理博主｜恢复采集：继续未完成的采集任务",
            horizontal=True
        )

        st.markdown("---")

        # Mode 1: Normal Collection
        if collection_mode == "正常采集":
            st.subheader("📊 正常采集模式")

            if pending_count == 0:
                st.warning("没有待采集的博主")
            else:
                # Get all pending bloggers to extract unique keywords
                all_pending = BloggerDB.get_pending_bloggers(limit=1000)
                pending_keywords = set()
                for blogger in all_pending:
                    if blogger.get("source_keyword"):
                        pending_keywords.add(blogger["source_keyword"])

                # Keyword filter
                keyword_filter_options = ["全部关键词"] + sorted(list(pending_keywords))
                selected_scrape_keyword = st.selectbox(
                    "筛选待采集博主",
                    options=keyword_filter_options,
                    help="按来源关键词筛选要采集的博主"
                )

                # Count pending bloggers based on filter
                if selected_scrape_keyword == "全部关键词":
                    filtered_pending_count = pending_count
                    filter_keyword = None
                else:
                    filtered_pending_count = BloggerDB.count_pending_by_keyword(selected_scrape_keyword)
                    filter_keyword = selected_scrape_keyword

                st.info(f"符合条件的待采集博主: {filtered_pending_count} 位")

                scrape_limit = st.number_input(
                    "采集博主数量",
                    min_value=1,
                    max_value=20,
                    value=min(5, filtered_pending_count) if filtered_pending_count > 0 else 5,
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

                # Advanced settings
                with st.expander("⚙️ 高级设置", expanded=False):
                    # Fans filter
                    enable_fans_filter = st.checkbox(
                        "启用粉丝数过滤",
                        value=False,
                        help="采集前检查博主粉丝数，跳过粉丝数低于阈值的博主"
                    )

                    min_fans = 0
                    if enable_fans_filter:
                        min_fans = st.number_input(
                            "最低粉丝数阈值",
                            min_value=0,
                            max_value=1000000,
                            value=1000,
                            step=1000,
                            help="粉丝数低于此值的博主将被跳过，不采集其笔记"
                        )

                    st.markdown("---")

                    # Batch size
                    batch_size = st.number_input(
                        "批量大小",
                        min_value=1,
                        max_value=20,
                        value=5,
                        step=1,
                        help="每批处理的博主数量。数量越小越稳定，但总耗时越长。推荐5个。"
                    )
                    st.caption("💡 批量处理说明：")
                    st.caption("- 博主数量 ≤ 批量大小：一次性处理")
                    st.caption("- 博主数量 > 批量大小：自动分批处理")
                    st.caption("- 预计时间 ≈ 批次数 × (批量大小 × 笔记数 × 4秒)")

                if st.button("📊 开始正常采集", type="primary", use_container_width=True):
                    if filtered_pending_count == 0:
                        st.warning("没有符合条件的待采集博主")
                    else:
                        # Normal collection - no resume
                        with st.spinner(f"正在采集数据（每位博主最多{max_notes_per_blogger}条笔记）..."):
                            stats = scrape_pending_bloggers(
                                limit=scrape_limit,
                                use_existing_data=False,
                                max_notes=max_notes_per_blogger,
                                min_fans=min_fans,
                                resume_partial=False,  # Disable resume in normal mode
                                batch_size=batch_size,
                                source_keyword=filter_keyword  # Pass keyword filter
                            )

                            msg = f"✓ 采集完成! 成功: {stats['scraped']}, 失败: {stats['failed']}, 笔记: {stats['notes_added']}"
                            if stats.get('resumed', 0) > 0:
                                msg += f", 恢复: {stats['resumed']}"
                            if stats['skipped_low_fans'] > 0:
                                msg += f", 粉丝数不足跳过: {stats['skipped_low_fans']}"
                            st.success(msg)
                            st.rerun()

        # Mode 2: Resume Collection
        else:
            st.subheader("🔄 恢复采集模式")

            if resumable_count == 0:
                st.warning("没有可恢复的采集任务")
                st.info("💡 提示：在正常采集过程中中断后，博主会进入可恢复状态")
            else:
                # Get resumable bloggers
                resumable_bloggers = BloggerDB.get_resumable_bloggers()

                # Create blogger selection options
                blogger_options = {}
                for blogger in resumable_bloggers:
                    progress = BloggerDB.get_scrape_progress(blogger['user_id'])
                    label = f"{blogger['nickname']} ({progress['notes_collected']}/{progress['notes_target']} 笔记)"
                    blogger_options[label] = blogger['user_id']

                # Multi-select for bloggers to resume
                st.write("选择要恢复采集的博主：")
                selected_bloggers = st.multiselect(
                    "选择博主",
                    options=list(blogger_options.keys()),
                    default=list(blogger_options.keys())[:min(3, len(blogger_options))],  # Default select first 3
                    help="可以选择多个博主同时恢复采集"
                )

                if selected_bloggers:
                    selected_user_ids = [blogger_options[label] for label in selected_bloggers]

                    # Show selected bloggers with progress
                    st.write(f"已选择 {len(selected_user_ids)} 位博主：")
                    for label in selected_bloggers:
                        st.caption(f"  • {label}")

                    max_notes_per_blogger = st.slider(
                        "每个博主笔记目标数量",
                        min_value=10,
                        max_value=200,
                        value=100,
                        step=10,
                        help="每个博主的目标笔记数量（会继续采集到达此数量）"
                    )

                    # Advanced settings for resume mode
                    with st.expander("⚙️ 高级设置", expanded=False):
                        # Batch size
                        batch_size = st.number_input(
                            "批量大小",
                            min_value=1,
                            max_value=20,
                            value=5,
                            step=1,
                            help="每批处理的博主数量"
                        )

                    if st.button("🔄 开始恢复采集", type="primary", use_container_width=True):
                        # Resume collection for selected bloggers using smart filtering
                        with st.spinner(f"正在恢复采集 {len(selected_user_ids)} 位博主的数据..."):
                            # Import the new function for resume mode
                            from red_lens.pipeline import scrape_specific_bloggers

                            # Use the new function with smart filtering (excludes already collected notes)
                            stats = scrape_specific_bloggers(
                                user_ids=selected_user_ids,
                                max_notes=max_notes_per_blogger,
                                batch_size=batch_size
                            )

                            msg = f"✓ 恢复采集完成! 已恢复: {stats['resumed']}, 成功: {stats['scraped']}, 失败: {stats['failed']}, 新增笔记: {stats['notes_added']}"
                            st.success(msg)
                            st.rerun()
                else:
                    st.info("请选择至少一个博主进行恢复采集")

        st.markdown("---")

        # Section 2.5: Manual Collection
        st.subheader("📝 手动采集博主")

        manual_user_id = st.text_input(
            "博主ID",
            placeholder="输入小红书博主ID (例如: 5c3a10f80000000007024ac5)",
            help="输入小红书博主的user_id，可以从博主主页URL中获取"
        )

        manual_nickname = st.text_input(
            "博主昵称（可选）",
            placeholder="例如: 某摄影师",
            help="选填，便于在数据库中识别该博主"
        )

        manual_max_notes = st.slider(
            "采集笔记数量",
            min_value=10,
            max_value=200,
            value=100,
            step=10,
            help="要采集的笔记数量"
        )

        manual_add_to_db = st.checkbox(
            "添加到数据库",
            value=True,
            help="勾选后会将博主信息保存到数据库，可在博主管理中查看和管理"
        )

        if st.button("🚀 开始手动采集", type="primary", use_container_width=True):
            if not manual_user_id or not manual_user_id.strip():
                st.error("请输入博主ID")
            else:
                user_id_clean = manual_user_id.strip()

                with st.spinner(f"正在采集博主 {user_id_clean} 的笔记..."):
                    result = collect_blogger_by_manual_id(
                        user_id=user_id_clean,
                        max_notes=manual_max_notes,
                        add_to_db=manual_add_to_db,
                        nickname=manual_nickname.strip() if manual_nickname else None
                    )

                    if result["success"]:
                        if "message" in result:
                            st.info(result["message"])
                        else:
                            st.success(
                                f"✓ 采集完成! 博主: {user_id_clean}\n"
                                f"总笔记数: {result['notes_count']}"
                            )
                        st.rerun()
                    else:
                        st.error(f"❌ 采集失败: {result.get('error', 'Unknown error')}")

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
    tab1, tab2, tab3, tab4 = st.tabs(["📊 博主排行", "🔥 爆款画廊", "📈 详细分析", "🗂️ 博主管理"])

    with tab1:
        show_blogger_ranking()

    with tab2:
        show_outlier_gallery()

    with tab3:
        show_detailed_analysis()

    with tab4:
        show_blogger_management()


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

    # Create DataFrame with hyperlink
    df_data = []
    for analysis in analyses:
        blogger = analysis["blogger"]
        fans_count = blogger.get("current_fans", 0) or blogger.get("initial_fans", 0)
        url = f"https://www.xiaohongshu.com/user/profile/{blogger['user_id']}"
        df_data.append({
            "博主昵称": blogger["nickname"],
            "主页链接": url,  # Separate column for hyperlink
            "粉丝数": fans_count if fans_count > 0 else 0,
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

    # Get all scraped bloggers with at least 20 notes
    all_bloggers = BloggerDB.get_all_bloggers()
    scraped_bloggers = []
    for b in all_bloggers:
        if b["status"] == "scraped":
            note_count = NoteDB.count_notes_by_user(b["user_id"])
            if note_count >= 20:
                scraped_bloggers.append(b)

    if not scraped_bloggers:
        st.info("暂无可分析的博主数据。（需要至少20篇笔记）")
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
    col1, col2, col3, col4 = st.columns([1, 3, 1.5, 1])
    with col1:
        if blogger["avatar_url"]:
            st.image(blogger["avatar_url"], width=150)
        else:
            st.info("无头像")
    with col2:
        st.subheader(blogger['nickname'])
        # 添加博主主页链接按钮
        url = f"https://www.xiaohongshu.com/user/profile/{blogger['user_id']}"
        st.caption(f"User ID: {blogger['user_id']}")
        st.caption(f"状态: {blogger['status']} | 来源: {blogger['source_keyword']}")
    with col3:
        st.markdown("###  ")  # Spacing
        st.link_button("🔗 访问主页", url, use_container_width=True)
    with col4:
        st.markdown("###  ")  # Spacing
        if st.button("🗑️ 清空数据", key=f"reset_{selected_user_id}", type="secondary", use_container_width=True):
            st.session_state[f"show_confirm_reset_{selected_user_id}"] = True

    # Confirmation dialog for reset
    if st.session_state.get(f"show_confirm_reset_{selected_user_id}", False):
        with st.expander("⚠️ 确认清空数据", expanded=True):
            st.warning(f"确认要清空 **{blogger['nickname']}** 的所有笔记数据吗？")
            st.info("博主状态将重置为 pending，所有笔记将被删除。此操作不可恢复！")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ 确认清空", key=f"confirm_yes_{selected_user_id}", type="primary", use_container_width=True):
                    success = BloggerDB.reset_blogger_status(selected_user_id)
                    if success:
                        st.success(f"✓ 已清空 {blogger['nickname']} 的所有笔记数据")
                        st.session_state[f"show_confirm_reset_{selected_user_id}"] = False
                        st.rerun()
                    else:
                        st.error("清空失败，请检查数据库")
            with col_b:
                if st.button("❌ 取消", key=f"confirm_no_{selected_user_id}", use_container_width=True):
                    st.session_state[f"show_confirm_reset_{selected_user_id}"] = False
                    st.rerun()

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

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        fans_count = blogger.get("current_fans", 0) or blogger.get("initial_fans", 0)
        st.metric("粉丝数", f"{fans_count:,}" if fans_count > 0 else "未采集")
    with col2:
        st.metric("总点赞", f"{analysis['total_likes']:,}")
    with col3:
        st.metric("总收藏", f"{analysis['total_collects']:,}")
    with col4:
        st.metric("总评论", f"{analysis['total_comments']:,}")
    with col5:
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

    # Import report functions
    from red_lens.analyzer import report_exists, load_report_from_file, delete_report_file, generate_ai_report
    import config

    # Create report mode selector - use FIXED global key to ensure consistent state
    report_mode = st.radio(
        "报告模式",
        options=["流量拆解", "个人复盘"],
        horizontal=True,
        help="流量拆解：分析账号成长逻辑和流量分发机制｜个人复盘：为您个人提供深度诊断和具体行动建议",
        key="ai_report_mode_global"
    )

    # Convert to internal mode value
    internal_report_mode = "traffic" if report_mode == "流量拆解" else "personal"

    # Check if report exists for current mode
    has_report = report_exists(selected_user_id, internal_report_mode)

    # Configuration controls
    with st.container():
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            use_real_api = st.checkbox(
                "使用真实 Deepseek API",
                value=config.ENABLE_REAL_AI,
                key=f"use_real_api_{selected_user_id}",
                help="需要配置 DEEPSEEK_API_KEY 环境变量"
            )
        with col2:
            # Show report status
            if has_report:
                st.info("✓ 已有报告")
            else:
                st.caption("无报告")
        with col3:
            if has_report and st.button("🗑️ 删除报告", help="删除当前博主的AI报告", key=f"delete_btn_{selected_user_id}"):
                if delete_report_file(selected_user_id, internal_report_mode):
                    st.success("报告已删除")
                    st.rerun()

    # Display existing report if available
    # Use a container with mode-specific key to ensure proper refresh when mode changes
    if has_report:
        existing_report = load_report_from_file(selected_user_id, internal_report_mode)
        if existing_report:
            st.markdown(existing_report)
            st.markdown("---")

    # Generate/Regenerate button
    # Include mode in the key to avoid stale button states
    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if has_report:
            generate_btn = st.button("🔄 重新生成报告", type="secondary", use_container_width=True,
                                    key=f"generate_btn_{selected_user_id}_{internal_report_mode}")
        else:
            generate_btn = st.button("✨ 生成 AI 报告", type="primary", use_container_width=True,
                                    key=f"generate_btn_{selected_user_id}_{internal_report_mode}")
    with col_btn2:
        if use_real_api:
            st.caption("💡 使用真实 API 生成报告")
        else:
            st.caption("💡 使用 Mock 报告（测试模式）")

    if generate_btn:
        use_mock = not use_real_api
        force_regenerate = has_report  # If report exists, force regenerate
        spinner_text = "AI 正在分析..." if use_real_api else "生成模拟报告..."
        with st.spinner(spinner_text):
            try:
                report = generate_ai_report(
                    selected_user_id,
                    use_mock=use_mock,
                    force_regenerate=force_regenerate,
                    report_mode=internal_report_mode
                )
                if report.startswith("Error:"):
                    st.error(report)
                else:
                    st.success("✓ 报告生成成功！")
                    st.rerun()  # Reload to display the new report
            except Exception as e:
                st.error(f"生成报告失败: {str(e)}")

    # Top notes
    st.markdown("---")
    st.subheader("🔝 热门笔记 Top 10")

    if notes:
        top_notes = sorted(notes, key=lambda x: x["likes"], reverse=True)[:10]

        for idx, note in enumerate(top_notes, 1):
            with st.container():
                # Create a card-like display for each note
                col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])

                with col1:
                    outlier_badge = "🔥 " if note["is_outlier"] else ""
                    st.markdown(f"**{idx}. {outlier_badge}{note['title'][:50]}...**")
                    st.caption(f"📝 {note['type']} | 🕐 {note['create_time']}")

                with col2:
                    st.metric("❤️", f"{note['likes']:,}")

                with col3:
                    st.metric("⭐", f"{note['collects']:,}")

                with col4:
                    st.metric("💬", f"{note['comments']:,}")

                with col5:
                    if note.get("note_url"):
                        st.link_button("查看", note["note_url"], use_container_width=True)
                    else:
                        st.caption("无链接")

                st.markdown("---")


def show_blogger_management():
    """Display blogger management page with filtering and batch operations"""
    st.header("🗂️ 博主管理")

    # Get all bloggers
    all_bloggers = BloggerDB.get_all_bloggers()

    if not all_bloggers:
        st.info("暂无博主数据")
        return

    st.success(f"数据库中共有 {len(all_bloggers)} 位博主")

    # Filters
    st.subheader("🔍 筛选条件")
    col1, col2, col3 = st.columns(3)

    with col1:
        # Status filter
        status_options = ["全部状态", "pending", "scraped", "error"]
        selected_status = st.selectbox("按状态筛选", status_options)

    with col2:
        # Keyword filter
        # Get unique keywords
        keywords = set()
        for blogger in all_bloggers:
            if blogger.get("source_keyword"):
                keywords.add(blogger["source_keyword"])

        keyword_options = ["全部关键词"] + sorted(list(keywords))
        selected_keyword = st.selectbox("按来源关键词筛选", keyword_options)

    with col3:
        # Fans filter
        enable_fans_filter = st.checkbox("启用粉丝数筛选", value=False)
        if enable_fans_filter:
            min_fans_filter = st.number_input(
                "最低粉丝数",
                min_value=0,
                max_value=1000000,
                value=1000,
                step=1000,
                help="只显示粉丝数大于等于此值的博主"
            )
        else:
            min_fans_filter = 0

    # Apply filters
    filtered_bloggers = all_bloggers

    if selected_status != "全部状态":
        filtered_bloggers = [b for b in filtered_bloggers if b["status"] == selected_status]

    if selected_keyword != "全部关键词":
        filtered_bloggers = [b for b in filtered_bloggers if b.get("source_keyword") == selected_keyword]

    if enable_fans_filter and min_fans_filter > 0:
        filtered_bloggers = [
            b for b in filtered_bloggers
            if (b.get("current_fans", 0) or b.get("initial_fans", 0)) >= min_fans_filter
        ]

    st.info(f"筛选后: {len(filtered_bloggers)} 位博主")

    st.markdown("---")

    # Blogger list with checkboxes
    st.subheader("📋 博主列表")

    if not filtered_bloggers:
        st.warning("没有符合条件的博主")
        return

    # Select all checkbox
    select_all = st.checkbox("全选", key="select_all_bloggers")

    # Initialize session state for selections
    if "selected_bloggers" not in st.session_state:
        st.session_state.selected_bloggers = set()

    if select_all:
        st.session_state.selected_bloggers = set(b["user_id"] for b in filtered_bloggers)
    elif not select_all and len(st.session_state.selected_bloggers) == len(filtered_bloggers):
        # If all were selected and user unchecks "select all"
        st.session_state.selected_bloggers = set()

    # Display bloggers in a scrollable container
    st.markdown("**选择要删除的博主：**")

    # Create a table-like display with checkboxes
    for idx, blogger in enumerate(filtered_bloggers):
        col1, col2, col3, col4, col5, col6, col7 = st.columns([0.5, 2, 1.5, 1, 1, 1, 1.2])

        with col1:
            is_selected = blogger["user_id"] in st.session_state.selected_bloggers
            if st.checkbox("选择", value=is_selected, key=f"cb_{blogger['user_id']}_{idx}", label_visibility="hidden"):
                st.session_state.selected_bloggers.add(blogger["user_id"])
            else:
                st.session_state.selected_bloggers.discard(blogger["user_id"])

        with col2:
            # 博主名称作为超链接，点击跳转到小红书主页
            url = f"https://www.xiaohongshu.com/user/profile/{blogger['user_id']}"
            st.markdown(f"[{blogger['nickname']}]({url})")

        with col3:
            st.caption(f"关键词: {blogger.get('source_keyword', 'N/A')}")

        with col4:
            status_emoji = {"pending": "⏳", "scraped": "✅", "error": "❌"}
            st.caption(f"{status_emoji.get(blogger['status'], '❓')} {blogger['status']}")

        with col5:
            fans = blogger.get("current_fans", 0) or blogger.get("initial_fans", 0)
            if fans > 0:
                st.caption(f"👥 {fans:,}")
            else:
                st.caption("👥 未采集")

        with col6:
            # Get note count
            note_count = NoteDB.count_notes_by_user(blogger["user_id"])
            st.caption(f"📝 {note_count} 笔记")

        with col7:
            # Show scrape progress
            progress = BloggerDB.get_scrape_progress(blogger["user_id"])
            if progress['notes_collected'] > 0 or progress['scrape_status'] != 'not_started':
                progress_pct = min(progress['notes_collected'] / max(progress['notes_target'], 1), 1.0)
                st.progress(progress_pct, text=f"{progress['notes_collected']}/{progress['notes_target']}")
            else:
                st.caption("未开始")

    st.markdown("---")

    # Batch operations
    st.subheader("⚙️ 批量操作")

    selected_count = len(st.session_state.selected_bloggers)
    st.info(f"已选择 {selected_count} 位博主")

    if selected_count == 0:
        st.warning("请先选择要操作的博主")
    else:
        col1, col2 = st.columns(2)

        with col1:
            if st.button("🗑️ 批量删除选中博主", type="primary", use_container_width=True):
                st.session_state.show_batch_delete_confirm = True

        with col2:
            if st.button("🔄 批量重置为 pending", use_container_width=True):
                st.session_state.show_batch_reset_confirm = True

    # Batch delete confirmation
    if st.session_state.get("show_batch_delete_confirm", False):
        with st.expander("⚠️ 确认批量删除", expanded=True):
            st.error(f"确认要删除选中的 **{selected_count}** 位博主及其所有笔记吗？")
            st.warning("此操作将永久删除博主信息和所有笔记，不可恢复！")

            # Show list of bloggers to be deleted
            st.markdown("**将要删除的博主：**")
            for user_id in list(st.session_state.selected_bloggers)[:10]:  # Show first 10
                blogger = next((b for b in filtered_bloggers if b["user_id"] == user_id), None)
                if blogger:
                    st.markdown(f"- {blogger['nickname']} ({blogger.get('source_keyword', 'N/A')})")
            if selected_count > 10:
                st.markdown(f"... 以及其他 {selected_count - 10} 位博主")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ 确认删除", key="confirm_batch_delete", type="primary", use_container_width=True):
                    deleted_count = 0
                    total_notes_deleted = 0

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for i, user_id in enumerate(st.session_state.selected_bloggers):
                        status_text.text(f"正在删除... ({i+1}/{selected_count})")
                        progress_bar.progress((i + 1) / selected_count)

                        # Count notes before deletion
                        note_count = NoteDB.count_notes_by_user(user_id)

                        # Delete blogger and notes
                        if BloggerDB.delete_blogger(user_id):
                            deleted_count += 1
                            total_notes_deleted += note_count

                    st.success(f"✓ 已删除 {deleted_count} 位博主和 {total_notes_deleted} 条笔记")
                    st.session_state.selected_bloggers = set()
                    st.session_state.show_batch_delete_confirm = False
                    st.rerun()

            with col_b:
                if st.button("❌ 取消", key="cancel_batch_delete", use_container_width=True):
                    st.session_state.show_batch_delete_confirm = False
                    st.rerun()

    # Batch reset confirmation
    if st.session_state.get("show_batch_reset_confirm", False):
        with st.expander("⚠️ 确认批量重置", expanded=True):
            st.warning(f"确认要将选中的 **{selected_count}** 位博主重置为 pending 状态吗？")
            st.info("此操作将删除这些博主的所有笔记，但保留博主信息。")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ 确认重置", key="confirm_batch_reset", type="primary", use_container_width=True):
                    reset_count = 0
                    total_notes_deleted = 0

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for i, user_id in enumerate(st.session_state.selected_bloggers):
                        status_text.text(f"正在重置... ({i+1}/{selected_count})")
                        progress_bar.progress((i + 1) / selected_count)

                        # Count notes before deletion
                        note_count = NoteDB.count_notes_by_user(user_id)

                        # Reset blogger status
                        if BloggerDB.reset_blogger_status(user_id):
                            reset_count += 1
                            total_notes_deleted += note_count

                    st.success(f"✓ 已重置 {reset_count} 位博主，删除 {total_notes_deleted} 条笔记")
                    st.session_state.selected_bloggers = set()
                    st.session_state.show_batch_reset_confirm = False
                    st.rerun()

            with col_b:
                if st.button("❌ 取消", key="cancel_batch_reset", use_container_width=True):
                    st.session_state.show_batch_reset_confirm = False
                    st.rerun()


if __name__ == "__main__":
    main()
