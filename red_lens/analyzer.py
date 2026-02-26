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

from red_lens.db import BloggerDB, NoteDB, AIReportDB, init_db


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
        Absolute local file path if successful, None otherwise
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
        # Return absolute path
        return str(local_path.resolve())

    try:
        # Download image
        response = requests.get(cover_url, timeout=30)
        response.raise_for_status()

        # Save to file
        with open(local_path, 'wb') as f:
            f.write(response.content)

        print(f"  ✓ Downloaded cover: {local_path.name}")
        # Return absolute path
        return str(local_path.resolve())

    except Exception as e:
        print(f"  ✗ Failed to download cover for {note_id}: {e}")
        return None


def download_outlier_covers(user_id: Optional[str] = None, overwrite: bool = False, refresh_url: bool = True) -> int:
    """
    Download cover images for all outlier notes

    Args:
        user_id: Optional user ID to filter (if None, download for all users)
        overwrite: Whether to overwrite existing files
        refresh_url: Whether to refresh cover URLs if download fails (default: True)

    Returns:
        Number of covers successfully downloaded
    """
    print(f"\n{'='*60}")
    print(f"RedLens Cover Downloader")
    print(f"{'='*60}")
    print(f"Target: {'All users' if not user_id else f'User {user_id}'}")
    print(f"Save directory: {COVER_DIR}")
    print(f"Refresh URL on failure: {'Yes' if refresh_url else 'No'}")
    print(f"{'='*60}\n")

    outlier_notes = NoteDB.get_outlier_notes(user_id=user_id)

    if not outlier_notes:
        print("✗ No outlier notes found")
        return 0

    print(f"📥 Found {len(outlier_notes)} outlier note(s) to download")

    downloaded = 0
    failed_notes = []

    for note in outlier_notes:
        note_id = note["note_id"]
        cover_url = note["cover_url"]

        print(f"\n📷 {note['title'][:30]}... (Likes: {note['likes']:,})")

        # Try to download with current URL
        local_path = download_cover_image(note_id, cover_url, overwrite=overwrite)

        if local_path:
            # Update database with local path
            NoteDB.update_local_cover_path(note_id, local_path)
            downloaded += 1
        else:
            # Download failed, record for potential URL refresh
            failed_notes.append(note)

    # If refresh_url is enabled and there are failed downloads, try to refresh URLs
    if refresh_url and failed_notes:
        print(f"\n{'='*60}")
        print(f"⚠️  {len(failed_notes)} downloads failed, attempting to refresh cover URLs...")
        print(f"{'='*60}\n")

        # Import refresh function (avoid circular import by importing here)
        try:
            from red_lens.pipeline import refresh_note_cover_urls

            failed_note_ids = [n["note_id"] for n in failed_notes]
            refresh_result = refresh_note_cover_urls(failed_note_ids)

            if refresh_result.get("success") and refresh_result.get("updated", 0) > 0:
                print(f"\n✓ Refreshed {refresh_result['updated']} cover URLs, retrying downloads...")

                # Retry downloads for refreshed notes
                for note_id in failed_note_ids:
                    # Get updated note from database
                    updated_note = NoteDB.get_note(note_id)
                    if updated_note and updated_note.get("cover_url"):
                        print(f"\n📷 Retry: {updated_note['title'][:30]}...")
                        local_path = download_cover_image(
                            note_id,
                            updated_note["cover_url"],
                            overwrite=overwrite
                        )
                        if local_path:
                            NoteDB.update_local_cover_path(note_id, local_path)
                            downloaded += 1
                            print(f"  ✓ Download succeeded after URL refresh")
            else:
                print(f"⚠️  URL refresh failed or no URLs were updated")

        except Exception as e:
            print(f"⚠️  Failed to refresh URLs: {e}")

    print(f"\n{'='*60}")
    print(f"✓ Download completed!")
    print(f"  Total outliers: {len(outlier_notes)}")
    print(f"  Successfully downloaded: {downloaded}")
    print(f"  Failed: {len(outlier_notes) - downloaded}")
    print(f"{'='*60}\n")

    return downloaded


def get_report_file_path(user_id: str, report_mode: str = "traffic", provider: str = None, model: str = None) -> Path:
    """
    Get the file path for a user's AI report

    Args:
        user_id: User ID
        report_mode: Report mode - "traffic" or "personal"
        provider: AI provider name (e.g., "deepseek", "kimi")
        model: Model name (for distinguishing different model reports)

    Returns:
        Path object for the report file
    """
    if provider and model:
        # New format: user_id_reportmode_provider_modelshort.md
        model_short = model.split('-')[-1]  # e.g., "vision" from "kimi-k2.5"
        return REPORTS_DIR / f"{user_id}_{report_mode}_{provider}_{model_short}.md"
    else:
        # Legacy format for backward compatibility
        return REPORTS_DIR / f"{user_id}_{report_mode}_report.md"


def save_report_to_file(user_id: str, report: str, report_mode: str = "traffic", provider: str = None, model: str = None) -> Optional[str]:
    """
    Save AI report to file

    Args:
        user_id: User ID
        report: Report content
        report_mode: Report mode - "traffic" or "personal"
        provider: AI provider name
        model: Model name

    Returns:
        File path string if successful, None otherwise
    """
    try:
        report_file = get_report_file_path(user_id, report_mode, provider, model)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"  ✓ Report saved to: {report_file.name}")
        return str(report_file)
    except Exception as e:
        print(f"  ✗ Failed to save report: {e}")
        return None


def load_report_from_file(user_id: str, report_mode: str = "traffic", provider: str = None, model: str = None) -> Optional[str]:
    """
    Load AI report from file

    Args:
        user_id: User ID
        report_mode: Report mode - "traffic" or "personal"
        provider: AI provider name
        model: Model name

    Returns:
        Report content if exists, None otherwise
    """
    try:
        report_file = get_report_file_path(user_id, report_mode, provider, model)
        if report_file.exists():
            with open(report_file, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    except Exception as e:
        print(f"  ✗ Failed to load report: {e}")
        return None


def report_exists(user_id: str, report_mode: str = "traffic", provider: str = None, model: str = None) -> bool:
    """
    Check if AI report exists for a user

    Args:
        user_id: User ID
        report_mode: Report mode - "traffic" or "personal"
        provider: AI provider name
        model: Model name

    Returns:
        True if report exists, False otherwise
    """
    return get_report_file_path(user_id, report_mode, provider, model).exists()


def delete_report_file(user_id: str, report_mode: str = "traffic", provider: str = None, model: str = None) -> bool:
    """
    Delete AI report file for a user

    Args:
        user_id: User ID
        report_mode: Report mode - "traffic" or "personal"
        provider: AI provider name
        model: Model name

    Returns:
        True if deleted, False otherwise
    """
    try:
        report_file = get_report_file_path(user_id, report_mode, provider, model)
        if report_file.exists():
            report_file.unlink()
            print(f"  ✓ Report deleted: {report_file.name}")
            return True
        return False
    except Exception as e:
        print(f"  ✗ Failed to delete report: {e}")
        return False


def _clean_markdown_code_blocks(content: str) -> str:
    """
    Clean markdown code blocks from AI response

    Some AI models (like KIMI) wrap their response in ```markdown``` code blocks,
    which should be removed for proper rendering.

    Args:
        content: Raw AI response content

    Returns:
        Cleaned content without code block markers
    """
    import re

    content = content.strip()

    # Pattern 1: Remove ```markdown at the beginning
    if content.startswith('```markdown'):
        content = content[len('```markdown'):].lstrip('\n')

    # Pattern 2: Remove ``` at the beginning (if not followed by a language identifier)
    elif content.startswith('```\n'):
        content = content[4:]

    # Pattern 3: Remove trailing ```
    if content.endswith('```'):
        content = content[:-3].rstrip('\n')

    return content.strip()


def download_note_covers(note_ids: List[str], force_redownload: bool = False) -> Dict[str, int]:
    """
    Download covers for specified notes

    Args:
        note_ids: List of note IDs to download covers for
        force_redownload: If True, redownload even if files exist

    Returns:
        Dict with download statistics: {'downloaded': count, 'skipped': count, 'failed': count}
    """
    from pathlib import Path
    import requests
    from PIL import Image
    from io import BytesIO

    # Create unified covers directory
    covers_dir = Path(__file__).parent / 'assets' / 'covers'
    covers_dir.mkdir(parents=True, exist_ok=True)

    stats = {'downloaded': 0, 'skipped': 0, 'failed': 0}

    print(f"  • Downloading {len(note_ids)} note covers...")

    for note_id in note_ids:
        # Get note from database
        note = NoteDB.get_note(note_id)
        if not note:
            print(f"    ⚠️ Note {note_id} not found in database")
            stats['failed'] += 1
            continue

        cover_url = note.get('cover_url')
        if not cover_url:
            print(f"    ⚠️ Note {note_id} has no cover_url")
            stats['failed'] += 1
            continue

        filename = f"{note_id}.jpg"
        filepath = covers_dir / filename

        # Skip if exists and not forcing redownload
        if filepath.exists() and not force_redownload:
            stats['skipped'] += 1
            continue

        try:
            response = requests.get(cover_url, timeout=10)
            response.raise_for_status()

            # Save image
            img = Image.open(BytesIO(response.content))
            # Convert to RGB if needed (in case of RGBA)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            img.save(filepath, 'JPEG', quality=85, optimize=True)

            stats['downloaded'] += 1
            print(f"    ✓ Downloaded: {note.get('title', note_id)[:40]}")

        except Exception as e:
            print(f"    ✗ Failed to download {note_id}: {e}")
            stats['failed'] += 1

    total = stats['downloaded'] + stats['skipped']
    print(f"  ✓ Cover download complete: {stats['downloaded']} downloaded + {stats['skipped']} skipped = {total} total")

    if stats['failed'] > 0:
        print(f"  ⚠️ {stats['failed']} downloads failed")

    return stats


def prepare_images_for_ai(notes: List[Dict], max_images: int = None, use_base64: bool = False, user_id: str = None) -> List[Dict]:
    """
    Prepare image data for AI vision models

    Args:
        notes: List of notes to prepare images for
        max_images: Maximum number of images to prepare (None = prepare for all notes)
        use_base64: If True, download images and convert to base64 (required for KIMI)
        user_id: User ID for loading local covers (if provided, will load from red_lens/assets/covers/)

    Returns:
        List of image data dictionaries with format:
        - If use_base64=False: [{"type": "url", "data": "https://...", "note_id": "...", "title": "..."}, ...]
        - If use_base64=True: [{"type": "base64", "data": "base64_string", "mime_type": "image/jpeg", ...}, ...]
    """
    images = []
    target_notes = notes[:max_images] if max_images else notes

    for note in target_notes:
        cover_url = note.get('cover_url')
        if not cover_url:
            continue

        if use_base64:
            # Try to load from local covers first
            img_data = None
            note_id = note.get('note_id', '')

            if user_id:
                from pathlib import Path
                covers_dir = Path(__file__).parent / 'assets' / 'covers'

                # Try to find matching cover file (simple note_id.jpg naming)
                cover_file = covers_dir / f"{note_id}.jpg"

                if cover_file.exists():
                    try:
                        with open(cover_file, 'rb') as f:
                            img_data = f.read()
                        print(f"    ✓ Loaded from local: {cover_file.name}")
                    except Exception as e:
                        print(f"    ⚠️ Failed to load local cover: {e}, falling back to download")

            # If not found locally, download
            if img_data is None:
                try:
                    import requests
                    import base64
                    from io import BytesIO
                    from PIL import Image

                    print(f"  • Downloading image: {note.get('title', '')[:30]}...")
                    response = requests.get(cover_url, timeout=10)
                    response.raise_for_status()
                    img_data = response.content

                    # Save downloaded image to local covers directory (v1.2.11 fix)
                    if user_id and note_id:
                        from pathlib import Path
                        covers_dir = Path(__file__).parent / 'assets' / 'covers'
                        covers_dir.mkdir(parents=True, exist_ok=True)

                        cover_file = covers_dir / f"{note_id}.jpg"
                        try:
                            with open(cover_file, 'wb') as f:
                                f.write(img_data)

                            # Update database with local cover path
                            local_cover_path = str(cover_file.resolve())
                            from red_lens.db import NoteDB
                            NoteDB.update_local_cover_path(note_id, local_cover_path)
                            print(f"    ✓ Saved to local: {cover_file.name}")
                        except Exception as save_error:
                            print(f"    ⚠️ Failed to save locally: {save_error}")

                except Exception as e:
                    print(f"    ✗ Failed to download image: {e}")
                    continue

            # Process image (optimize size)
            try:
                import base64
                from io import BytesIO
                from PIL import Image

                original_size = len(img_data)

                # If image is too large, resize it
                MAX_IMAGE_SIZE = 500 * 1024  # 500KB
                if original_size > MAX_IMAGE_SIZE:
                    print(f"    ⚠️ Image too large ({original_size / 1024:.1f}KB), resizing...")
                    try:
                        img = Image.open(BytesIO(img_data))
                        # Resize to max 1024px on longest side
                        max_dimension = 1024
                        if max(img.size) > max_dimension:
                            ratio = max_dimension / max(img.size)
                            new_size = tuple(int(dim * ratio) for dim in img.size)
                            img = img.resize(new_size, Image.Resampling.LANCZOS)

                        # Save to bytes
                        output = BytesIO()
                        img_format = img.format if img.format else 'JPEG'
                        img.save(output, format=img_format, quality=85, optimize=True)
                        img_data = output.getvalue()
                        print(f"    ✓ Resized to {len(img_data) / 1024:.1f}KB")
                    except Exception as resize_error:
                        print(f"    ⚠️ Resize failed: {resize_error}, using original")

                # Convert to base64
                img_base64 = base64.b64encode(img_data).decode('utf-8')

                # Detect content type
                content_type = 'image/jpeg'  # Default
                try:
                    img_obj = Image.open(BytesIO(img_data))
                    if img_obj.format:
                        content_type = f'image/{img_obj.format.lower()}'
                except:
                    pass

                images.append({
                    "type": "base64",
                    "data": img_base64,
                    "mime_type": content_type,
                    "note_id": note.get('note_id', ''),
                    "title": note.get('title', '')[:50]
                })
                print(f"    ✓ Encoded to base64 ({len(img_base64)} chars)")

            except Exception as e:
                print(f"    ✗ Failed to process image: {e}")
                continue
        else:
            # Use URL directly (for other providers)
            images.append({
                "type": "url",
                "data": cover_url,
                "note_id": note.get('note_id', ''),
                "title": note.get('title', '')[:50]  # Truncate for logging
            })

    return images


def build_notes_info_with_images(notes: List[Dict], has_images: bool = False, image_note_ids: set = None) -> str:
    """
    Build notes information string with optional image annotations

    Args:
        notes: List of notes
        has_images: Whether images are actually being passed to the AI model (legacy, applies to all notes)
        image_note_ids: Set of note_ids that have images prepared. If provided, overrides has_images
                       for per-note granularity.

    Returns:
        Formatted notes information string
    """
    info = ""
    for i, note in enumerate(notes, 1):
        note_id = note.get('note_id', '')
        # Determine if this specific note has an image
        if image_note_ids is not None:
            note_has_image = note_id in image_note_ids
        else:
            note_has_image = has_images

        info += f"\n**笔记 {i}**: {note['title']}\n"
        info += f"  - 数据: 点赞 {note['likes']:,} | 收藏 {note['collects']:,} | 评论 {note.get('comments', 0):,}\n"
        info += f"  - 类型: {note.get('type', 'image')}\n"

        cover_url = note.get('cover_url')
        if note_has_image and cover_url:
            info += f"  - 📷 封面: [图片已附上，请结合视觉分析]\n"
        elif cover_url:
            info += f"  - 📷 封面: 有封面但未传递给模型\n"
        else:
            info += f"  - 📷 封面: 无\n"

        # Add publish time if available
        pub_time = note.get('create_time', '') or note.get('publish_time', '')
        if pub_time:
            info += f"  - 发布时间: {pub_time}\n"

        info += "\n"

    return info


def generate_ai_report(
    user_id: str,
    use_mock: bool = True,
    force_regenerate: bool = False,
    report_mode: str = "traffic",
    provider: str = None,
    model: str = None
) -> str:
    """
    Generate AI insights report for a blogger with multi-provider support

    Args:
        user_id: User ID
        use_mock: If True, return mock report. If False, call real AI API
        force_regenerate: If True, regenerate report even if file exists
        report_mode: Report mode - "traffic" for traffic analysis, "personal" for personal review
        provider: AI provider name ("deepseek" | "kimi" | None for default)
        model: Model name (None for provider's default model)

    Returns:
        AI-generated report text
    """
    # Import config here to avoid circular import
    import config

    # Determine provider and model
    if not provider:
        provider = config.DEFAULT_AI_PROVIDER
    if not model:
        provider_config = config.AI_PROVIDERS[provider]
        model = provider_config["default_model"]

    print(f"\n{'='*60}")
    print(f"RedLens AI Insights")
    print(f"Mode: {report_mode.upper()}")
    print(f"Provider: {provider} | Model: {model}")
    print(f"{'='*60}\n")

    # Check if report exists (unless force regenerate or mock mode)
    if not force_regenerate and not use_mock:
        existing_report = load_report_from_file(user_id, report_mode, provider, model)
        if existing_report:
            print("  ✓ Using existing report from file")
            return existing_report

    analysis = analyze_blogger(user_id)

    if "error" in analysis:
        return f"Error: {analysis['error']}"

    blogger = analysis["blogger"]
    print(f"🤖 Generating AI insights for: {blogger['nickname']}")

    if use_mock:
        # Mock AI report for testing (legacy logic preserved)
        print("  [Using mock AI report]")

        # Get fans count
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
*   **互动质量**：收藏数超过点赞意味着内容被视为"可复用的资产"（工具属性强）；反之则偏向"一次性消费"（情绪/审美体验）。

### 2. 🎬 流量对比复盘

通过对比 Top 10 和 Bottom 5，可以明显看到：

*   **高赞共性**：（由于这是Mock数据，建议使用真实AI调用后查看）
*   **低赞共性**：封面混乱、标题没有明确价值点、或者与粉丝期望的内容类型不符。

### 3. 📝 下一篇爆文建议

**选题方向**：根据你的高赞笔记，建议下一篇笔记选择类似的风格或选题，并在标题中直接传递价值预期。

**封面建议**：分析高赞笔记的封面风格，保持视觉一致性。

**标题方案 (示例)**：
1. *痛点型*："还在纠结XX？这篇告诉你答案"
2. *反差型*："我用了3年才明白，XX其实不是这样的"
3. *场景型*："那个XX的下午，我拍到了最满意的照片"

---
🤖 Generated by Mock AI | RedLens v1.2.4
"""

            # Save report
            saved_path = save_report_to_file(user_id, report, report_mode, provider, model)
            if saved_path:
                AIReportDB.save_report(user_id, saved_path, report_mode, provider, model)
            return report

        else:  # traffic mode
            # Traffic analysis mode mock
            top_outliers = sorted(analysis['outliers'], key=lambda x: x['likes'], reverse=True)[:5]

            report = f"""
# AI 流量拆解报告：{blogger['nickname']}

## 📊 基础数据

- **粉丝数**: {fans_count:,}
- **笔记数**: {analysis['total_notes']}
- **平均互动**: 赞 {analysis['avg_likes']:.0f}
- **爆款率**: {analysis['outlier_rate']:.1%}

## 🔥 爆款笔记 (Top 5)
"""
            for i, note in enumerate(top_outliers, 1):
                report += f"\n{i}. **{note['title']}**\n"
                report += f"   - 点赞: {note['likes']:,} | 收藏: {note['collects']:,}\n"

            report += """

## 🧬 流量密码分析

### 1. 成长路径诊断
*   （Mock数据模式，使用真实AI后将提供详细分析）

### 2. 流量机制推演
*   **搜索流 vs 推荐流**：根据标题关键词分析，该账号主要依靠推荐流量。

### 3. 优化建议
*   保持高赞笔记的风格和选题
*   标题可以更加突出价值点

---
🤖 Generated by Mock AI | RedLens v1.2.11
"""

            # Collect note cover information for Mock mode (v1.2.11)
            import json
            note_covers_data = {
                "report_mode": report_mode,
                "covers": []
            }

            if report_mode == "traffic":
                # 流量拆解模式：收集Top 5爆款封面
                top_outliers = sorted(analysis['outliers'], key=lambda x: x['likes'], reverse=True)[:5]
                for note in top_outliers:
                    note_id = note.get('note_id', '')
                    local_cover = note.get('local_cover_path', '')
                    if local_cover:
                        note_covers_data["covers"].append({
                            "note_id": note_id,
                            "title": note.get('title', '')[:50],
                            "local_cover_path": local_cover,
                            "likes": note.get('likes', 0),
                            "category": "top5"
                        })
            else:  # personal mode
                # 个人复盘模式：收集Top 10和Bottom 5封面
                for note in top_10_notes:
                    note_id = note.get('note_id', '')
                    local_cover = note.get('local_cover_path', '')
                    if local_cover:
                        note_covers_data["covers"].append({
                            "note_id": note_id,
                            "title": note.get('title', '')[:50],
                            "local_cover_path": local_cover,
                            "likes": note.get('likes', 0),
                            "category": "top10"
                        })

                for note in bottom_5_notes:
                    note_id = note.get('note_id', '')
                    local_cover = note.get('local_cover_path', '')
                    if local_cover:
                        note_covers_data["covers"].append({
                            "note_id": note_id,
                            "title": note.get('title', '')[:50],
                            "local_cover_path": local_cover,
                            "likes": note.get('likes', 0),
                            "category": "bottom5"
                        })

            note_covers_json = json.dumps(note_covers_data, ensure_ascii=False)

            saved_path = save_report_to_file(user_id, report, report_mode, provider, model)
            if saved_path:
                AIReportDB.save_report(user_id, saved_path, report_mode, provider, model, note_covers_json)
            return report

    else:
        # Real AI API call with multi-provider support
        print("  [Calling AI API...]")

        try:
            from red_lens.ai_providers import get_ai_provider

            # Get AI provider instance
            ai_provider = get_ai_provider(provider, model)

            # Check if provider supports vision
            supports_vision = ai_provider.supports_vision()
            print(f"  • Vision support: {'✓' if supports_vision else '✗'}")

            # Get blogger data
            fans_count = blogger.get('current_fans', blogger.get('initial_fans', 0))
            notes = NoteDB.get_notes_by_user(user_id)

            # ===== Determine which notes need covers based on report mode =====
            all_notes_sorted = sorted(notes, key=lambda x: x['likes'], reverse=True)

            if report_mode == "personal":
                # Personal mode: top 10 + bottom 5
                top_10_notes = all_notes_sorted[:10]
                notes_likes_20plus = [note for note in notes if note['likes'] >= 20]
                notes_likes_20plus_sorted = sorted(notes_likes_20plus, key=lambda x: x['likes'])
                bottom_5_notes = notes_likes_20plus_sorted[:5]
                # Combine: all notes that need covers (dedup by note_id)
                seen_ids = set()
                notes_needing_covers = []
                for note in top_10_notes + bottom_5_notes:
                    if note['note_id'] not in seen_ids:
                        seen_ids.add(note['note_id'])
                        notes_needing_covers.append(note)
            else:
                # Traffic mode: top 5 outliers
                top_outliers = sorted(analysis['outliers'], key=lambda x: x['likes'], reverse=True)[:5]
                notes_needing_covers = top_outliers

            # ===== Auto-download covers if vision is supported =====
            if supports_vision and notes_needing_covers:
                print(f"  • Checking cover availability for {len(notes_needing_covers)} notes...")
                from pathlib import Path

                covers_dir = Path(__file__).parent / 'assets' / 'covers'

                # Check which covers are missing
                missing_covers = []
                for note in notes_needing_covers:
                    note_id = note['note_id']
                    cover_file = covers_dir / f"{note_id}.jpg"
                    if not cover_file.exists():
                        missing_covers.append(note_id)

                # If any covers are missing, auto-download
                if missing_covers:
                    print(f"  ⚠️ Missing {len(missing_covers)} covers, auto-downloading...")

                    try:
                        from red_lens.pipeline import refresh_note_cover_urls

                        note_ids_to_download = [note['note_id'] for note in notes_needing_covers]

                        # Step 1: Refresh cover URLs
                        print(f"    • Step 1/2: Refreshing cover URLs...")
                        refresh_result = refresh_note_cover_urls(note_ids_to_download)

                        if refresh_result.get('success'):
                            print(f"    ✓ Refreshed {refresh_result.get('updated', 0)} note URLs")
                        else:
                            print(f"    ⚠️ URL refresh had issues, attempting download anyway...")

                        # Step 2: Download covers
                        print(f"    • Step 2/2: Downloading covers...")
                        download_stats = download_note_covers(note_ids_to_download, force_redownload=False)
                        print(f"    ✓ Downloaded: {download_stats['downloaded']}, Skipped: {download_stats['skipped']}, Failed: {download_stats['failed']}")

                        # Reload notes to get updated cover_url after refresh
                        notes = NoteDB.get_notes_by_user(user_id)
                        all_notes_sorted = sorted(notes, key=lambda x: x['likes'], reverse=True)
                        if report_mode == "personal":
                            top_10_notes = all_notes_sorted[:10]
                            notes_likes_20plus = [note for note in notes if note['likes'] >= 20]
                            notes_likes_20plus_sorted = sorted(notes_likes_20plus, key=lambda x: x['likes'])
                            bottom_5_notes = notes_likes_20plus_sorted[:5]
                            seen_ids = set()
                            notes_needing_covers = []
                            for note in top_10_notes + bottom_5_notes:
                                if note['note_id'] not in seen_ids:
                                    seen_ids.add(note['note_id'])
                                    notes_needing_covers.append(note)
                        else:
                            top_outliers = sorted(analysis['outliers'], key=lambda x: x['likes'], reverse=True)[:5]
                            notes_needing_covers = top_outliers

                    except Exception as e:
                        print(f"    ✗ Auto-download failed: {e}")
                        print(f"    • Continuing with available data...")
                else:
                    print(f"  ✓ All required covers exist")

            # ===== Prepare images if vision is supported =====
            images = []
            image_note_ids = set()  # Track which note_ids have images prepared
            if supports_vision:
                use_base64 = (provider == "kimi")
                # Prepare images for all notes that need covers
                images = prepare_images_for_ai(notes_needing_covers, use_base64=use_base64, user_id=user_id)

                if images:
                    image_note_ids = {img['note_id'] for img in images}
                    img_format = "base64" if use_base64 else "URL"
                    print(f"  • Prepared {len(images)} cover images ({img_format} format)")

            # Select prompts based on mode and vision support
            if report_mode == "personal":
                if supports_vision:
                    system_prompt = config.AI_SYSTEM_PROMPT_PERSONAL_VISION
                    user_prompt_template = config.AI_USER_PROMPT_TEMPLATE_PERSONAL_VISION
                else:
                    system_prompt = config.AI_SYSTEM_PROMPT_PERSONAL
                    user_prompt_template = config.AI_USER_PROMPT_TEMPLATE_PERSONAL

                # Build notes info with per-note image tracking
                top_notes_info = build_notes_info_with_images(top_10_notes, image_note_ids=image_note_ids if images else None)
                bottom_notes_info = build_notes_info_with_images(bottom_5_notes, image_note_ids=image_note_ids if images else None)

                # Calculate metrics
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

            else:  # traffic mode
                if supports_vision:
                    system_prompt = config.AI_SYSTEM_PROMPT_TRAFFIC_VISION
                    user_prompt_template = config.AI_USER_PROMPT_TEMPLATE_TRAFFIC_VISION
                else:
                    system_prompt = config.AI_SYSTEM_PROMPT_TRAFFIC
                    user_prompt_template = config.AI_USER_PROMPT_TEMPLATE_TRAFFIC

                # top_outliers already prepared above during cover selection

                # Build notes info with per-note image tracking
                top_notes_info = build_notes_info_with_images(top_outliers, image_note_ids=image_note_ids if images else None, has_images=bool(images))

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

                # Calculate interaction rate
                total_interactions = analysis['avg_likes'] + (analysis['total_collects'] / analysis['total_notes'] if analysis['total_notes'] > 0 else 0) + (analysis['total_comments'] / analysis['total_notes'] if analysis['total_notes'] > 0 else 0)
                interaction_rate = (total_interactions / fans_count) if fans_count > 0 else 0

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
                    top_notes_info_with_images=top_notes_info,  # Alias for compatibility
                    time_distribution=time_distribution
                )

            # Build messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Select timeout based on provider (KIMI needs more time for images)
            timeout = config.AI_REQUEST_TIMEOUT_KIMI if provider == "kimi" else config.AI_REQUEST_TIMEOUT
            print(f"  • Request timeout: {timeout}s")

            # Call AI provider
            print("  • Sending request to AI...")
            report_content = ai_provider.generate_report(
                messages=messages,
                images=images if supports_vision else None,
                max_tokens=config.AI_MAX_TOKENS,
                temperature=config.AI_TEMPERATURE,
                timeout=timeout
            )

            # Clean markdown code blocks (KIMI sometimes wraps response in ```markdown```)
            report_content = _clean_markdown_code_blocks(report_content)

            # Build full report with header
            report_header = f"# 📊 {blogger['nickname']} - {'流量拆解' if report_mode == 'traffic' else '个人复盘'}报告\n\n"
            report_header += f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            report_header += f"**AI模型**: {ai_provider.get_provider_name()} ({model})\n"
            if supports_vision and images:
                report_header += f"**视觉分析**: 已分析 {len(images)} 张封面图片\n"
            report_header += "\n---\n\n"

            full_report = report_header + report_content

            # Add footer
            full_report += f"\n\n---\n🤖 Generated by {ai_provider.get_provider_name()} ({model}) | RedLens v1.2.11"

            # Collect note cover information (v1.2.11)
            import json
            note_covers_data = {
                "report_mode": report_mode,
                "covers": []
            }

            if report_mode == "traffic":
                # 流量拆解模式：收集Top 5爆款封面
                for note in notes_needing_covers[:5]:
                    note_id = note.get('note_id', '')
                    local_cover = note.get('local_cover_path', '')
                    if local_cover:
                        note_covers_data["covers"].append({
                            "note_id": note_id,
                            "title": note.get('title', '')[:50],
                            "local_cover_path": local_cover,
                            "likes": note.get('likes', 0),
                            "category": "top5"
                        })
            else:  # personal mode
                # 个人复盘模式：收集Top 10和Bottom 5封面
                for note in top_10_notes:
                    note_id = note.get('note_id', '')
                    local_cover = note.get('local_cover_path', '')
                    if local_cover:
                        note_covers_data["covers"].append({
                            "note_id": note_id,
                            "title": note.get('title', '')[:50],
                            "local_cover_path": local_cover,
                            "likes": note.get('likes', 0),
                            "category": "top10"
                        })

                for note in bottom_5_notes:
                    note_id = note.get('note_id', '')
                    local_cover = note.get('local_cover_path', '')
                    if local_cover:
                        note_covers_data["covers"].append({
                            "note_id": note_id,
                            "title": note.get('title', '')[:50],
                            "local_cover_path": local_cover,
                            "likes": note.get('likes', 0),
                            "category": "bottom5"
                        })

            note_covers_json = json.dumps(note_covers_data, ensure_ascii=False)

            # Save report
            saved_path = save_report_to_file(user_id, full_report, report_mode, provider, model)
            if saved_path:
                AIReportDB.save_report(user_id, saved_path, report_mode, provider, model, note_covers_json)

            print("  ✓ AI report generated successfully")
            return full_report

        except ValueError as e:
            # Configuration errors (API key missing, unknown provider, etc.)
            error_msg = f"配置错误: {str(e)}"
            print(f"  ✗ {error_msg}")
            return f"# 报告生成失败\n\n{error_msg}"

        except ImportError as e:
            error_msg = f"依赖缺失: openai 包未安装。请运行: pip install openai\n详情: {str(e)}"
            print(f"  ✗ {error_msg}")
            return f"# 报告生成失败\n\n{error_msg}"

        except Exception as e:
            error_msg = f"生成报告时出错: {str(e)}"
            print(f"  ✗ {error_msg}")
            return f"# 报告生成失败\n\n{error_msg}"


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
