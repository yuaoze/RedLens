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


def generate_ai_report(user_id: str, use_mock: bool = True) -> str:
    """
    Generate AI insights report for a blogger

    Args:
        user_id: User ID
        use_mock: If True, return mock report. If False, call actual Claude API

    Returns:
        AI-generated report text
    """
    print(f"\n{'='*60}")
    print(f"RedLens AI Insights")
    print(f"{'='*60}\n")

    analysis = analyze_blogger(user_id)

    if "error" in analysis:
        return f"Error: {analysis['error']}"

    blogger = analysis["blogger"]
    print(f"🤖 Generating AI insights for: {blogger['nickname']}")

    if use_mock:
        # Mock AI report for testing
        print("  [Using mock AI report]")

        report = f"""
# AI 洞察报告：{blogger['nickname']}

## 📊 数据概览

- **总笔记数**: {analysis['total_notes']}
- **平均点赞**: {analysis['avg_likes']:.0f}
- **总互动量**: {analysis['total_engagement']:,} (点赞+收藏+评论)
- **爆款率**: {analysis['outlier_rate']:.1%} ({analysis['outlier_count']}/{analysis['total_notes']})
- **内容类型**: 图文 {analysis['image_count']} 篇 | 视频 {analysis['video_count']} 篇

## 🔥 爆款分析

该博主共产出 **{analysis['outlier_count']} 篇爆款内容**，爆款率达 {analysis['outlier_rate']:.1%}。

"""

        if analysis['outliers']:
            report += "### Top 爆款笔记\n\n"
            for i, note in enumerate(sorted(analysis['outliers'], key=lambda x: x['likes'], reverse=True)[:3], 1):
                report += f"{i}. **{note['title'][:40]}...**\n"
                report += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,} | 评论: {note['comments']:,}\n"
                report += f"   - 类型: {note['type']}\n\n"

        report += """
## 💡 AI 建议

1. **内容策略**: 基于爆款数据，该博主在[主题]方面表现突出，建议继续深耕该领域。

2. **发布节奏**: 平均互动量较高，说明粉丝粘性良好，建议保持稳定的更新频率。

3. **内容形式**: 图文/视频内容各有优势，建议根据主题特点选择合适的呈现方式。

---
🤖 Generated by Claude AI | RedLens v0.1.0
"""

        return report

    else:
        # TODO: Implement actual Claude API call
        print("  [Calling Claude API...]")

        # Placeholder for API implementation
        try:
            import anthropic

            # You would implement the actual API call here:
            # client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            # message = client.messages.create(...)

            return "Real Claude API integration - Coming soon!"

        except ImportError:
            return "Error: anthropic package not installed. Run: pip install anthropic"


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
