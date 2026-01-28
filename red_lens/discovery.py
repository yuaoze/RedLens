# -*- coding: utf-8 -*-
"""
Discovery module for RedLens
Search for photographers and extract blogger information
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add parent directory to path to import MediaCrawler modules
MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.db import BloggerDB, init_db


def parse_count_str(count_str: str) -> int:
    """
    Convert Chinese count format to integer
    Examples: "10万+" -> 100000, "2.1万" -> 21000, "4834" -> 4834

    Args:
        count_str: Count string in Chinese format

    Returns:
        Integer value
    """
    if not count_str:
        return 0

    count_str = str(count_str).strip()

    # Remove trailing "+"
    if count_str.endswith("+"):
        count_str = count_str[:-1]

    # Handle "万" (ten thousand)
    if "万" in count_str:
        count_str = count_str.replace("万", "")
        try:
            return int(float(count_str) * 10000)
        except ValueError:
            return 0

    # Handle "千" (thousand)
    if "千" in count_str:
        count_str = count_str.replace("千", "")
        try:
            return int(float(count_str) * 1000)
        except ValueError:
            return 0

    # Handle plain numbers
    try:
        return int(count_str)
    except ValueError:
        return 0


def extract_bloggers_from_json(json_file: Path, min_likes: int = 200) -> List[Dict[str, Any]]:
    """
    Extract blogger information from MediaCrawler JSON output

    Args:
        json_file: Path to JSON file containing search results
        min_likes: Minimum likes threshold to filter out non-influential users

    Returns:
        List of blogger dictionaries with deduplicated user_id
    """
    bloggers_dict = {}  # Use dict to deduplicate by user_id

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            notes = json.load(f)

        for note in notes:
            # Parse likes count
            likes_str = note.get("liked_count", "0")
            likes = parse_count_str(likes_str)

            # Filter by likes threshold
            if likes < min_likes:
                continue

            # Extract blogger info
            user_id = note.get("user_id")
            if not user_id:
                continue

            # If we already have this blogger, skip (deduplicate)
            if user_id in bloggers_dict:
                continue

            nickname = note.get("nickname", "Unknown")
            avatar_url = note.get("avatar", "")
            source_keyword = note.get("source_keyword", "")

            bloggers_dict[user_id] = {
                "user_id": user_id,
                "nickname": nickname,
                "avatar_url": avatar_url,
                "source_keyword": source_keyword,
                "sample_likes": likes  # Sample likes from one of their notes
            }

        return list(bloggers_dict.values())

    except FileNotFoundError:
        print(f"✗ JSON file not found: {json_file}")
        return []
    except json.JSONDecodeError as e:
        print(f"✗ Error parsing JSON: {e}")
        return []


def run_mediacrawler_sync(keywords: List[str], max_notes: int = 100) -> bool:
    """
    Run MediaCrawler in search mode to discover bloggers (synchronous version)

    Args:
        keywords: List of keywords to search (e.g., ["富士扫街", "人像摄影"])
        max_notes: Maximum number of notes to crawl per keyword

    Returns:
        True if successful, False otherwise
    """
    print(f"\n🔍 Starting MediaCrawler search for keywords: {keywords}")

    # Prepare MediaCrawler config by modifying config/base_config.py
    config_file = MEDIA_CRAWLER_ROOT / "config" / "base_config.py"

    # Read current config
    with open(config_file, 'r', encoding='utf-8') as f:
        config_content = f.read()

    # Backup original config
    backup_file = config_file.parent / "base_config.py.redlens_backup"
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(config_content)

    try:
        # Modify config for our search
        import re

        # Update KEYWORDS
        keywords_str = ",".join(keywords)
        config_content = re.sub(
            r'KEYWORDS = ".*?"',
            f'KEYWORDS = "{keywords_str}"',
            config_content
        )

        # Set CRAWLER_TYPE to search
        config_content = re.sub(
            r'CRAWLER_TYPE = ".*?"',
            'CRAWLER_TYPE = "search"',
            config_content
        )

        # Set CRAWLER_MAX_NOTES_COUNT
        config_content = re.sub(
            r'CRAWLER_MAX_NOTES_COUNT = \d+',
            f'CRAWLER_MAX_NOTES_COUNT = {max_notes}',
            config_content
        )

        # Disable comment crawling for faster blogger discovery
        config_content = re.sub(
            r'ENABLE_GET_COMMENTS = (True|False)',
            'ENABLE_GET_COMMENTS = False',
            config_content
        )

        # Save modified config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)

        print(f"✓ MediaCrawler config updated:")
        print(f"  • keywords={keywords_str}")
        print(f"  • max_notes={max_notes}")
        print(f"  • comments=disabled (faster discovery)")

        # Run MediaCrawler using uv (since this project uses uv for dependency management)
        print("🚀 Launching MediaCrawler with uv run (this may take a while)...")

        # Try to use uv run first, fall back to direct python if uv is not available
        try:
            # Check if uv is available
            uv_check = subprocess.run(["uv", "--version"], capture_output=True)
            use_uv = (uv_check.returncode == 0)
        except FileNotFoundError:
            use_uv = False

        if use_uv:
            print("  • Using uv run for better dependency isolation")
            cmd = ["uv", "run", "main.py", "--platform", "xhs", "--lt", "qrcode", "--type", "search"]
        else:
            print("  • Using direct python execution (uv not found)")
            cmd = [sys.executable, "main.py"]

        result = subprocess.run(
            cmd,
            cwd=MEDIA_CRAWLER_ROOT,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout
        )

        if result.returncode == 0:
            print("✓ MediaCrawler completed successfully")
            return True
        else:
            print(f"✗ MediaCrawler failed with return code {result.returncode}")
            print(f"Error output: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("✗ MediaCrawler timeout after 10 minutes")
        return False
    except Exception as e:
        print(f"✗ Error running MediaCrawler: {e}")
        return False
    finally:
        # Restore original config
        with open(backup_file, 'r', encoding='utf-8') as f:
            original_config = f.read()
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(original_config)
        backup_file.unlink()  # Delete backup
        print("✓ MediaCrawler config restored")


def search_and_extract_users(
    keywords: List[str],
    min_likes: int = 200,
    max_notes: int = 100,
    run_crawler: bool = True,
    use_existing: bool = False
) -> int:
    """
    Main function: Search for bloggers and save to database

    Args:
        keywords: List of search keywords
        min_likes: Minimum likes threshold for filtering
        max_notes: Maximum notes to crawl per keyword
        run_crawler: Whether to run MediaCrawler to fetch new data (default: True)
        use_existing: If True, use existing JSON files without running crawler (default: False)

    Returns:
        Number of new bloggers discovered and saved
    """
    # Initialize database
    init_db()

    print(f"\n{'='*60}")
    print(f"RedLens Blogger Discovery")
    print(f"{'='*60}")
    print(f"Keywords: {', '.join(keywords)}")
    print(f"Min likes threshold: {min_likes}")
    print(f"Max notes per keyword: {max_notes}")
    print(f"Mode: {'Using existing data' if use_existing else 'Running MediaCrawler'}")
    print(f"{'='*60}\n")

    json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"
    today = datetime.now().strftime("%Y-%m-%d")
    json_file = json_dir / f"search_contents_{today}.json"

    # Run MediaCrawler if requested
    if run_crawler and not use_existing:
        print("🚀 Running MediaCrawler to fetch new data...")
        print("⚠ Note: This requires browser interaction (login, verification, etc.)")
        print("   You may need to manually complete login steps in the browser window.\n")

        # Run MediaCrawler using subprocess
        success = run_mediacrawler_sync(keywords, max_notes)

        if not success:
            print("\n⚠ MediaCrawler execution failed or was interrupted.")
            print("   Falling back to existing data if available...\n")
            use_existing = True
        else:
            print("\n✓ MediaCrawler completed. Proceeding to extract bloggers...\n")

    # Find JSON file (either newly generated or existing)
    if use_existing or not json_file.exists():
        # Try to find the most recent search_contents file
        json_files = list(json_dir.glob("search_contents_*.json"))
        if json_files:
            json_file = max(json_files, key=lambda p: p.stat().st_mtime)
            print(f"ℹ Using existing JSON file: {json_file.name}\n")
        else:
            print(f"✗ No search results found.")
            print(f"  Please ensure MediaCrawler has run successfully.")
            print(f"  Expected directory: {json_dir}")
            return 0

    # Extract bloggers from JSON
    print(f"📊 Parsing search results from: {json_file.name}")
    bloggers = extract_bloggers_from_json(json_file, min_likes=min_likes)

    if not bloggers:
        print("✗ No bloggers found matching the criteria")
        return 0

    print(f"✓ Found {len(bloggers)} unique bloggers with likes > {min_likes}")

    # Save to database
    new_count = 0
    for blogger in bloggers:
        success = BloggerDB.insert_blogger(
            user_id=blogger["user_id"],
            nickname=blogger["nickname"],
            avatar_url=blogger["avatar_url"],
            initial_fans=0,  # We'll get actual fan count in scraping phase
            source_keyword=blogger["source_keyword"]
        )
        if success:
            new_count += 1
            print(f"  ✓ Added: {blogger['nickname']} (ID: {blogger['user_id'][:8]}..., "
                  f"Sample likes: {blogger['sample_likes']})")

    print(f"\n{'='*60}")
    print(f"✓ Discovery completed!")
    print(f"  Total bloggers found: {len(bloggers)}")
    print(f"  New bloggers saved: {new_count}")
    print(f"  Already existing: {len(bloggers) - new_count}")
    print(f"{'='*60}\n")

    return new_count


def main():
    """Test the discovery module"""
    # Test with example keywords
    keywords = ["富士扫街", "人像摄影", "胶片色调"]

    # Run discovery with existing data (for testing)
    print("=" * 60)
    print("TEST MODE: Using existing data")
    print("=" * 60)
    new_bloggers = search_and_extract_users(
        keywords=keywords,
        min_likes=200,
        max_notes=100,
        use_existing=True  # Use existing data for testing
    )

    # Show statistics
    print("\n📈 Database Statistics:")
    print(f"  Pending bloggers: {BloggerDB.count_by_status('pending')}")
    print(f"  Scraped bloggers: {BloggerDB.count_by_status('scraped')}")
    print(f"  Error bloggers: {BloggerDB.count_by_status('error')}")


if __name__ == "__main__":
    main()
