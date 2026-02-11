# -*- coding: utf-8 -*-
"""
Analyzer module for RedLens
Identifies viral content (爆款) and provides AI insights
"""

import os
import sys
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add parent directory to path
MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.db import BloggerDB, NoteDB, init_db


# Directory for storing cover images
COVER_DIR = Path(__file__).parent / "assets" / "covers"
COVER_DIR.mkdir(parents=True, exist_ok=True)

# Directory for storing AI reports
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def calculate_outlier_threshold(user_id: str, multiplier: float = 3.0, min_likes: int = 500) -> float:
    """
    Calculate the outlier threshold for a user's notes

    Args:
        user_id: User ID
        multiplier: How many times above average to consider outlier (default: 3x)
        min_likes: Minimum absolute likes to consider outlier (default: 500)

    Returns:
        Outlier threshold value
    """
    avg_likes = NoteDB.get_avg_likes_by_user(user_id)
    threshold = max(avg_likes * multiplier, min_likes)
    return threshold


def identify_outliers(user_id: str, multiplier: float = 3.0, min_likes: int = 500) -> List[Dict[str, Any]]:
    """
    Identify viral notes (爆款) for a specific blogger

    A note is considered an outlier if:
    - likes > avg_likes * multiplier (default: 3x)
    - AND likes > min_likes (default: 500)

    Args:
        user_id: User ID
        multiplier: Outlier multiplier
        min_likes: Minimum absolute likes

    Returns:
        List of outlier notes
    """
    notes = NoteDB.get_notes_by_user(user_id)

    if not notes:
        return []

    threshold = calculate_outlier_threshold(user_id, multiplier, min_likes)
    outliers = []

    for note in notes:
        likes = note["likes"]
        if likes >= threshold:
            outliers.append(note)
            # Mark as outlier in database
            NoteDB.update_outlier_status(note["note_id"], True)

    return outliers


def analyze_blogger(user_id: str) -> Dict[str, Any]:
    """
    Comprehensive analysis of a blogger's content

    Args:
        user_id: User ID

    Returns:
        Analysis results dictionary
    """
    blogger = BloggerDB.get_blogger(user_id)
    if not blogger:
        return {"error": "Blogger not found"}

    notes = NoteDB.get_notes_by_user(user_id)
    if not notes:
        return {
            "error": "No notes found",
            "blogger": blogger
        }

    # Calculate metrics
    total_notes = len(notes)
    avg_likes = NoteDB.get_avg_likes_by_user(user_id)
    total_likes = sum(note["likes"] for note in notes)
    total_collects = sum(note["collects"] for note in notes)
    total_comments = sum(note["comments"] for note in notes)

    # Find outliers
    outliers = identify_outliers(user_id)
    outlier_rate = len(outliers) / total_notes if total_notes > 0 else 0

    # Content type distribution
    video_count = sum(1 for note in notes if note["type"] == "video")
    image_count = sum(1 for note in notes if note["type"] == "image")

    # Engagement rate (likes + collects + comments) / notes
    total_engagement = total_likes + total_collects + total_comments
    avg_engagement = total_engagement / total_notes if total_notes > 0 else 0

    analysis = {
        "blogger": blogger,
        "total_notes": total_notes,
        "avg_likes": avg_likes,
        "total_likes": total_likes,
        "total_collects": total_collects,
        "total_comments": total_comments,
        "total_engagement": total_engagement,
        "avg_engagement": avg_engagement,
        "outlier_count": len(outliers),
        "outlier_rate": outlier_rate,
        "video_count": video_count,
        "image_count": image_count,
        "outliers": outliers
    }

    return analysis


def download_cover_image(note_id: str, cover_url: str, overwrite: bool = False) -> Optional[str]:
    """
    Download cover image for a note

    Args:
        note_id: Note ID
        cover_url: URL of the cover image
        overwrite: Whether to overwrite existing file

    Returns:
        Local file path if successful, None otherwise
    """
    if not cover_url:
        print(f"  ⚠ No cover URL for note {note_id}")
        return None

    # Determine file extension from URL
    ext = ".jpg"  # default
    if ".png" in cover_url.lower():
        ext = ".png"
    elif ".webp" in cover_url.lower():
        ext = ".webp"

    local_path = COVER_DIR / f"{note_id}{ext}"

    # Check if already exists
    if local_path.exists() and not overwrite:
        print(f"  ✓ Cover already exists: {local_path.name}")
        return str(local_path)

    try:
        # Download image
        response = requests.get(cover_url, timeout=30)
        response.raise_for_status()

        # Save to file
        with open(local_path, 'wb') as f:
            f.write(response.content)

        print(f"  ✓ Downloaded cover: {local_path.name}")
        return str(local_path)

    except Exception as e:
        print(f"  ✗ Failed to download cover for {note_id}: {e}")
        return None


def download_outlier_covers(user_id: Optional[str] = None, overwrite: bool = False) -> int:
    """
    Download cover images for all outlier notes

    Args:
        user_id: Optional user ID to filter (if None, download for all users)
        overwrite: Whether to overwrite existing files

    Returns:
        Number of covers successfully downloaded
    """
    print(f"\n{'='*60}")
    print(f"RedLens Cover Downloader")
    print(f"{'='*60}")
    print(f"Target: {'All users' if not user_id else f'User {user_id}'}")
    print(f"Save directory: {COVER_DIR}")
    print(f"{'='*60}\n")

    outlier_notes = NoteDB.get_outlier_notes(user_id=user_id)

    if not outlier_notes:
        print("✗ No outlier notes found")
        return 0

    print(f"📥 Found {len(outlier_notes)} outlier note(s) to download")

    downloaded = 0
    for note in outlier_notes:
        note_id = note["note_id"]
        cover_url = note["cover_url"]

        print(f"\n📷 {note['title'][:30]}... (Likes: {note['likes']:,})")

        local_path = download_cover_image(note_id, cover_url, overwrite=overwrite)

        if local_path:
            # Update database with local path
            NoteDB.update_local_cover_path(note_id, local_path)
            downloaded += 1

    print(f"\n{'='*60}")
    print(f"✓ Download completed!")
    print(f"  Total outliers: {len(outlier_notes)}")
    print(f"  Successfully downloaded: {downloaded}")
    print(f"  Failed: {len(outlier_notes) - downloaded}")
    print(f"{'='*60}\n")

    return downloaded


def get_report_file_path(user_id: str, report_mode: str = "traffic") -> Path:
    """
    Get the file path for a user's AI report

    Args:
        user_id: User ID
        report_mode: Report mode - "traffic" or "personal"

    Returns:
        Path object for the report file
    """
    return REPORTS_DIR / f"{user_id}_{report_mode}_report.md"


def save_report_to_file(user_id: str, report: str, report_mode: str = "traffic") -> bool:
    """
    Save AI report to file

    Args:
        user_id: User ID
        report: Report content
        report_mode: Report mode - "traffic" or "personal"

    Returns:
        True if successful, False otherwise
    """
    try:
        report_file = get_report_file_path(user_id, report_mode)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"  ✓ Report saved to: {report_file.name}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to save report: {e}")
        return False


def load_report_from_file(user_id: str, report_mode: str = "traffic") -> Optional[str]:
    """
    Load AI report from file

    Args:
        user_id: User ID
        report_mode: Report mode - "traffic" or "personal"

    Returns:
        Report content if exists, None otherwise
    """
    try:
        report_file = get_report_file_path(user_id, report_mode)
        if report_file.exists():
            with open(report_file, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    except Exception as e:
        print(f"  ✗ Failed to load report: {e}")
        return None


def report_exists(user_id: str, report_mode: str = "traffic") -> bool:
    """
    Check if AI report exists for a user

    Args:
        user_id: User ID
        report_mode: Report mode - "traffic" or "personal"

    Returns:
        True if report exists, False otherwise
    """
    return get_report_file_path(user_id, report_mode).exists()


def delete_report_file(user_id: str, report_mode: str = "traffic") -> bool:
    """
    Delete AI report file for a user

    Args:
        user_id: User ID
        report_mode: Report mode - "traffic" or "personal"

    Returns:
        True if deleted, False otherwise
    """
    try:
        report_file = get_report_file_path(user_id, report_mode)
        if report_file.exists():
            report_file.unlink()
            print(f"  ✓ Report deleted: {report_file.name}")
            return True
        return False
    except Exception as e:
        print(f"  ✗ Failed to delete report: {e}")
        return False


def generate_ai_report(user_id: str, use_mock: bool = True, force_regenerate: bool = False, report_mode: str = "traffic") -> str:
    """
    Generate AI insights report for a blogger

    Args:
        user_id: User ID
        use_mock: If True, return mock report. If False, call Deepseek API
        force_regenerate: If True, regenerate report even if file exists
        report_mode: Report mode - "traffic" for traffic analysis, "personal" for personal review

    Returns:
        AI-generated report text
    """
    # Import config here to avoid circular import
    import config

    print(f"\n{'='*60}")
    print(f"RedLens AI Insights")
    print(f"Mode: {report_mode.upper()}")
    print(f"{'='*60}\n")

    analysis = analyze_blogger(user_id)

    if "error" in analysis:
        return f"Error: {analysis['error']}"

    blogger = analysis["blogger"]
    print(f"🤖 Generating AI insights for: {blogger['nickname']}")

    # Check if report file exists (unless force regenerate)
    if not force_regenerate:
        existing_report = load_report_from_file(user_id, report_mode)
        if existing_report:
            print("  ✓ Using existing report from file")
            return existing_report

    if use_mock:
        # Mock AI report for testing
        print("  [Using mock AI report]")

        # Get fans count (current_fans or initial_fans)
        fans_count = blogger.get('current_fans', blogger.get('initial_fans', 0))

        if report_mode == "personal":
            # Personal review mode mock
            notes = NoteDB.get_notes_by_user(user_id)
            all_notes_sorted = sorted(notes, key=lambda x: x['likes'], reverse=True)

            top_10_notes = all_notes_sorted[:10]

            # Bottom 5 notes: select the 5 notes with minimum likes among those with >= 20 likes
            notes_likes_20plus = [note for note in notes if note['likes'] >= 20]
            notes_likes_20plus_sorted = sorted(notes_likes_20plus, key=lambda x: x['likes'])  # ascending
            bottom_5_notes = notes_likes_20plus_sorted[:5]  # first 5 = lowest among >= 20

            total_likes = sum(note["likes"] for note in notes)
            total_collects = sum(note["collects"] for note in notes)
            collect_like_ratio = total_collects / total_likes if total_likes > 0 else 0
            avg_collects = total_collects / analysis['total_notes'] if analysis['total_notes'] > 0 else 0

            report = f"""
# AI 个人复盘报告：{blogger['nickname']}

## 📊 账号现状

- **粉丝数**: {fans_count:,}
- **笔记数**: {analysis['total_notes']}
- **平均表现**: 赞 {analysis['avg_likes']:.0f} | 藏 {avg_collects:.0f}
- **核心指标 (藏赞比)**: {collect_like_ratio:.2f}
  *(注：<0.2 为强视觉/情绪向；>0.5 为强干货/工具向)*

## 📝 数据对比：高光 vs 低谷

**🏆 Top 10 高赞笔记**
"""
            for i, note in enumerate(top_10_notes, 1):
                report += f"\n{i}. **{note['title']}**\n"
                report += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,} | 评论: {note['comments']:,}\n"

            if bottom_5_notes:
                report += "\n**🥀 Bottom 5 低赞笔记**\n"
                for i, note in enumerate(bottom_5_notes, 1):
                    report += f"\n{i}. **{note['title']}**\n"
                    report += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,} | 评论: {note['comments']:,}\n"

            report += """

## 🩺 深度诊断与优化建议

### 1. 🎯 账号定位诊断
*   **数据反映的人设**：根据 """
            report += f"`{collect_like_ratio:.2f}` 的藏赞比，你在粉丝眼中是一个 "
            if collect_like_ratio < 0.2:
                report += "**强视觉/情绪向博主**，内容偏重审美和情感共鸣。"
            elif collect_like_ratio > 0.5:
                report += "**干货/工具向博主**，大家把你当作资料库和知识来源。"
            else:
                report += "**平衡型博主**，兼具审美价值和实用价值。"

            report += """
*   **互动质量**："""
            avg_comments = analysis['total_comments'] / analysis['total_notes'] if analysis['total_notes'] > 0 else 0
            if avg_comments < 5:
                report += "评论区活跃度较低，建议增加与粉丝的互动，提升人设魅力。"
            else:
                report += "评论区活跃度良好，粉丝粘性不错。"

            report += """

### 2. ⚖️ 成功与失败的复盘
*   **爆款共性**：Top 10 笔记在标题用词上可能有情绪词、数字、提问等吸引点击的元素，这是你需要坚持的"舒适区"。
*   **避坑指南**：请分析低分笔记，看看是否存在标题晦涩、选题自嗨或偏离账号核心定位的问题。

### 3. 🛠️ 内容优化方向 (Action Plan)
*   **做减法 (Stop Doing)**：请观察低分笔记，找出不要再发的内容类型或标题风格。
*   **做加法 (Start Doing)**：基于高分笔记，考虑将相似选题系列化或翻拍。
*   **标题诊所**：建议从笔记中挑选1个，重写3个更具爆款潜力的标题。

### 4. 🚀 下阶段策略
*   给出一句话建议：基于藏赞比 """
            report += f"`{collect_like_ratio:.2f}`"
            if collect_like_ratio < 0.2:
                report += "，建议继续强化视觉表现，同时适当增加干货内容提升收藏价值。"
            elif collect_like_ratio > 0.5:
                report += "，建议在保持干货质量的同时，提升标题的情绪号召力和视觉吸引力。"
            else:
                report += "，建议找到你的差异化优势，在视觉和实用之间找到平衡点。"

        else:
            # Traffic analysis mode mock (default)
            notes = NoteDB.get_notes_by_user(user_id)

            # Calculate avg collects
            avg_collects = analysis['total_collects'] / analysis['total_notes'] if analysis['total_notes'] > 0 else 0

            # Calculate time distribution
            time_dist = {}
            for note in notes:
                create_time = note.get('create_time', '') or note.get('publish_time', '')
                if create_time:
                    try:
                        hour = int(create_time.split(':')[0]) if ':' in str(create_time) else 0
                        time_dist[hour] = time_dist.get(hour, 0) + 1
                    except:
                        pass

            time_distribution = "发布时间主要集中在: " + ", ".join([f"{h}时({c}篇)" for h, c in sorted(time_dist.items(), key=lambda x: x[1], reverse=True)[:5]])

            # Calculate publish frequency
            if notes:
                last_publish = notes[0].get('create_time', '') or notes[0].get('publish_time', 'N/A')
            else:
                last_publish = "N/A"
            publish_frequency = f"约 {len(notes) / 30:.1f} 篇/月" if len(notes) >= 30 else f"{len(notes)} 篇总计"

            report = f"""
# AI 流量拆解报告：{blogger['nickname']}

## 1. 基础画像
- **昵称**: {blogger['nickname']}
- **ID**: {user_id}
- **当前量级**: 粉丝 {fans_count:,} | 笔记 {analysis['total_notes']} 篇
- **互动大盘**: 平均点赞 {analysis['avg_likes']:.0f} | 平均收藏 {avg_collects:.0f}

## 2. 爆款笔记样本 (Top 5)
"""

            if analysis['outliers']:
                top_5_notes = sorted(analysis['outliers'], key=lambda x: x['likes'], reverse=True)[:5]
                for i, note in enumerate(top_5_notes, 1):
                    report += f"\n{i}. **{note['title']}**\n"
                    report += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,} | 评论: {note['comments']:,}\n"
                    pub_time = note.get('create_time', '') or note.get('publish_time', 'N/A')
                    report += f"   - 发布时间: {pub_time}\n"
            else:
                # If no outliers, use top notes by likes
                all_notes_sorted = sorted(notes, key=lambda x: x['likes'], reverse=True)[:5]
                for i, note in enumerate(all_notes_sorted, 1):
                    report += f"\n{i}. **{note['title']}**\n"
                    report += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,} | 评论: {note['comments']:,}\n"
                    pub_time = note.get('create_time', '') or note.get('publish_time', 'N/A')
                    report += f"   - 发布时间: {pub_time}\n"

            report += f"""

## 3. 时间与频率
- 最近发布: {last_publish}
- 发布频率: {publish_frequency}
- 时间分布: {time_distribution}

---

## 🕵️‍♂️ 深度分析

### 1. 📈 成长路径与人设定位
*   **账号定位判定**：基于数据表现，该博主是**审美/情绪博主**（观赏属性），内容偏重视觉呈现和情绪共鸣。
*   **成长阶段判断**：根据互动数据，该账号处于**稳定增长期**，建议维持内容质量的同时尝试新的内容形式。
*   **人设记忆点**：从爆款标题中可以提取出其最具吸引力的标签是"摄影+场景+情绪"的组合拳。

### 2. 🧬 流量密码拆解
*   **爆文基因**：Top 笔记的共性是靠**特定场景**（如独特时间、地点的氛围感）和**情绪共鸣**，而非纯技术参数。
*   **触达机制推演**：
    *   *搜索侧*：标题中较少包含器材型号等强搜索词，说明流量主要来自推荐流。
    *   *推荐侧*：标题包含情绪词和强烈的视觉描述，容易被推荐算法捕捉。
*   **低粉爆文特征**：存在点赞数远超粉丝数预期的笔记，说明内容击中了算法推荐机制。

### 3. 🎨 摄影垂直风格分析
*   **视觉关键词**：胶片感、街拍、蓝调、氛围感、扫街
*   **选题偏好**：更倾向于街头摄影和情绪化场景

### 4. 🚀 策略复盘与建议
*   **All-in方向**：继续强化"场景+情绪"的内容模式
*   **砍掉内容**：减少纯技术参数分享类内容

### 5. ⚠️ 总结
这个博主能火的核心逻辑：**用有氛围感的场景照片击中用户的情绪共鸣点**

---
🤖 Generated by Mock AI | RedLens v1.2.2
"""

        # Save report to file
        save_report_to_file(user_id, report, report_mode)

        return report

    else:
        # Real Deepseek API call
        print("  [Calling Deepseek API...]")

        try:
            from openai import OpenAI

            # Check API key
            if not config.DEEPSEEK_API_KEY:
                return "Error: DEEPSEEK_API_KEY not configured. Please set the environment variable or configure it in config/ai_config.py"

            # Get fans count
            fans_count = blogger.get('current_fans', blogger.get('initial_fans', 0))

            # Prepare data for prompt
            notes = NoteDB.get_notes_by_user(user_id)

            # Get top outliers for analysis
            top_outliers = sorted(analysis['outliers'], key=lambda x: x['likes'], reverse=True)[:5]

            # Select system and user prompt based on report mode
            if report_mode == "personal":
                system_prompt = config.AI_SYSTEM_PROMPT_PERSONAL
                user_prompt_template = config.AI_USER_PROMPT_TEMPLATE_PERSONAL

                # For personal mode: need Top 10 and Bottom 5 notes
                all_notes_sorted = sorted(notes, key=lambda x: x['likes'], reverse=True)

                # Top 10 notes
                top_10_notes = all_notes_sorted[:10]
                top_notes_info = ""
                for i, note in enumerate(top_10_notes, 1):
                    top_notes_info += f"\n{i}. **{note['title']}**\n"
                    top_notes_info += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,} | 评论: {note['comments']:,}\n"

                # Bottom 5 notes: select the 5 notes with minimum likes among those with >= 20 likes
                notes_likes_20plus = [note for note in notes if note['likes'] >= 20]
                notes_likes_20plus_sorted = sorted(notes_likes_20plus, key=lambda x: x['likes'])  # ascending
                bottom_5_notes = notes_likes_20plus_sorted[:5]  # first 5 = lowest among >= 20
                bottom_notes_info = ""
                for i, note in enumerate(bottom_5_notes, 1):
                    bottom_notes_info += f"\n{i}. **{note['title']}**\n"
                    bottom_notes_info += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,} | 评论: {note['comments']:,}\n"

                # Calculate collect-like ratio
                total_likes = sum(note["likes"] for note in notes)
                total_collects = sum(note["collects"] for note in notes)
                collect_like_ratio = total_collects / total_likes if total_likes > 0 else 0

                user_prompt = user_prompt_template.format(
                    nickname=blogger['nickname'],
                    fans=fans_count,
                    total_notes=analysis['total_notes'],
                    avg_likes=analysis['avg_likes'],
                    avg_collects=total_collects / analysis['total_notes'] if analysis['total_notes'] > 0 else 0,
                    collect_like_ratio=collect_like_ratio,
                    top_notes_info=top_notes_info,
                    bottom_notes_info=bottom_notes_info
                )

            else:  # traffic mode (default)
                system_prompt = config.AI_SYSTEM_PROMPT_TRAFFIC
                user_prompt_template = config.AI_USER_PROMPT_TEMPLATE_TRAFFIC

                # Format top notes info with titles (no cover URLs as Deepseek doesn't support vision)
                top_notes_info = ""
                for i, note in enumerate(top_outliers, 1):
                    top_notes_info += f"\n{i}. **{note['title']}**\n"
                    top_notes_info += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,} | 评论: {note['comments']:,}\n"
                    top_notes_info += f"   - 类型: {note['type']}\n"
                    top_notes_info += f"   - 发布时间: {note.get('create_time', '') or note.get('publish_time', 'N/A')}\n"

                # Calculate time distribution
                time_dist = {}
                for note in notes:
                    pub_time = note.get('create_time', '') or note.get('publish_time', '')
                    if pub_time:
                        try:
                            hour = int(pub_time.split(':')[0]) if ':' in str(pub_time) else 0
                            time_dist[hour] = time_dist.get(hour, 0) + 1
                        except:
                            pass

                time_distribution = "发布时间主要集中在: " + ", ".join([f"{h}时({c}篇)" for h, c in sorted(time_dist.items(), key=lambda x: x[1], reverse=True)[:5]])

                # Calculate publish frequency
                if notes:
                    last_publish = notes[0].get('create_time', '') or notes[0].get('publish_time', 'N/A')
                else:
                    last_publish = "N/A"
                publish_frequency = f"约 {len(notes) / 30:.1f} 篇/月" if len(notes) >= 30 else f"{len(notes)} 篇总计"

                # Calculate interaction rate (avoid division by zero)
                total_interactions = analysis['avg_likes'] + (analysis['total_collects'] / analysis['total_notes'] if analysis['total_notes'] > 0 else 0) + (analysis['total_comments'] / analysis['total_notes'] if analysis['total_notes'] > 0 else 0)
                interaction_rate = (total_interactions / fans_count * 100) if fans_count > 0 else 0

                user_prompt = user_prompt_template.format(
                    nickname=blogger['nickname'],
                    user_id=user_id,
                    fans=fans_count,
                    total_notes=analysis['total_notes'],
                    avg_likes=analysis['avg_likes'],
                    avg_collects=analysis['total_collects'] / analysis['total_notes'] if analysis['total_notes'] > 0 else 0,
                    interaction_rate=interaction_rate,
                    outlier_rate=analysis['outlier_rate'],
                    last_publish_date=last_publish,
                    publish_frequency=publish_frequency,
                    top_n=len(top_outliers),
                    top_notes_info=top_notes_info,
                    time_distribution=time_distribution
                )

            # Call Deepseek API
            client = OpenAI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=config.DEEPSEEK_BASE_URL
            )

            print(f"  • Model: {config.AI_MODEL}")
            print(f"  • Max tokens: {config.AI_MAX_TOKENS}")

            response = client.chat.completions.create(
                model=config.AI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=config.AI_MAX_TOKENS,
                temperature=config.AI_TEMPERATURE,
                timeout=config.AI_REQUEST_TIMEOUT
            )

            report_content = response.choices[0].message.content

            # Add header and footer
            report = f"# AI 洞察报告：{blogger['nickname']}\n\n"
            report += report_content
            report += f"\n\n---\n🤖 Generated by Deepseek AI ({config.AI_MODEL}) | RedLens v1.2.2"

            # Save report to file
            save_report_to_file(user_id, report, report_mode)

            print("  ✓ AI report generated successfully")

            return report

        except ImportError as e:
            return f"Error: openai package not installed. Run: pip install openai\nDetails: {str(e)}"
        except Exception as e:
            error_msg = f"Error generating AI report: {str(e)}"
            print(f"  ✗ {error_msg}")
            return error_msg


def analyze_all_bloggers() -> List[Dict[str, Any]]:
    """
    Analyze all scraped bloggers and rank by viral rate

    Returns:
        List of analysis results sorted by outlier_rate
    """
    print(f"\n{'='*60}")
    print(f"RedLens Batch Analysis")
    print(f"{'='*60}\n")

    scraped_bloggers = [b for b in BloggerDB.get_all_bloggers() if b["status"] == "scraped"]

    if not scraped_bloggers:
        print("✗ No scraped bloggers to analyze")
        return []

    print(f"📊 Analyzing {len(scraped_bloggers)} blogger(s)...\n")

    analyses = []
    for blogger in scraped_bloggers:
        user_id = blogger["user_id"]
        analysis = analyze_blogger(user_id)

        if "error" not in analysis:
            analyses.append(analysis)

            # Print summary
            print(f"✓ {blogger['nickname']}")
            print(f"  • Notes: {analysis['total_notes']}")
            print(f"  • Avg likes: {analysis['avg_likes']:.0f}")
            print(f"  • Outliers: {analysis['outlier_count']} ({analysis['outlier_rate']:.1%})")

    # Sort by outlier rate
    analyses.sort(key=lambda x: x["outlier_rate"], reverse=True)

    print(f"\n{'='*60}")
    print(f"✓ Analysis completed!")
    print(f"{'='*60}\n")

    return analyses


def main():
    """Test the analyzer module"""
    init_db()

    print("=" * 60)
    print("STEP 1: Analyze all bloggers")
    print("=" * 60)

    analyses = analyze_all_bloggers()

    if analyses:
        print("\n" + "=" * 60)
        print("STEP 2: Download outlier covers")
        print("=" * 60)

        download_outlier_covers()

        print("\n" + "=" * 60)
        print("STEP 3: Generate AI report for top blogger")
        print("=" * 60)

        # Generate report for the top blogger
        top_blogger = analyses[0]
        user_id = top_blogger["blogger"]["user_id"]
        report = generate_ai_report(user_id, use_mock=True)

        print("\n" + "=" * 60)
        print("AI REPORT")
        print("=" * 60)
        print(report)


if __name__ == "__main__":
    main()
