# -*- coding: utf-8 -*-
"""
Pipeline module for RedLens
Handles deep scraping and data cleaning
"""

import os
import sys
import json
import time
import random
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add parent directory to path
MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.db import BloggerDB, NoteDB, init_db
from red_lens.discovery import parse_count_str


def fetch_creators_fans_batch(user_ids: List[str]) -> Dict[str, int]:
    """
    Fetch fans count for multiple creators by running MediaCrawler once

    Args:
        user_ids: List of Xiaohongshu user IDs

    Returns:
        Dictionary mapping user_id to fans count
    """
    result = {}

    if not user_ids:
        return result

    try:
        # Run MediaCrawler to fetch all creators info (with minimal notes)
        print(f"    🚀 Running MediaCrawler to fetch {len(user_ids)} creator(s) info...")
        success = run_mediacrawler_for_creators_batch(user_ids, max_notes=1)

        if not success:
            print(f"    ✗ MediaCrawler failed")
            return {uid: 0 for uid in user_ids}

        # Read fans from the generated creator JSON file
        json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"
        creator_files = list(json_dir.glob("creator_creators_*.json"))

        if not creator_files:
            print(f"    ✗ No creator JSON file found")
            return {uid: 0 for uid in user_ids}

        latest_file = max(creator_files, key=lambda p: p.stat().st_mtime)

        with open(latest_file, 'r', encoding='utf-8') as f:
            creators = json.load(f)

        # Build dictionary of user_id -> fans
        for creator in creators:
            user_id = creator.get("user_id")
            if user_id in user_ids:
                fans_raw = creator.get("fans", 0)
                fans = int(fans_raw) if fans_raw else 0
                result[user_id] = fans

        # Fill in missing users with 0
        for uid in user_ids:
            if uid not in result:
                result[uid] = 0

        print(f"    ✓ Successfully fetched fans for {len([f for f in result.values() if f > 0])}/{len(user_ids)} creator(s)")
        return result

    except Exception as e:
        print(f"    ✗ Error fetching fans: {e}")
        return {uid: 0 for uid in user_ids}


def fetch_creator_fans_via_mediacrawler(user_id: str) -> int:
    """
    Fetch creator fans count by running MediaCrawler in creator mode
    This is a wrapper around fetch_creators_fans_batch for single user

    Args:
        user_id: Xiaohongshu user ID

    Returns:
        Fans count (integer), 0 if failed
    """
    result = fetch_creators_fans_batch([user_id])
    return result.get(user_id, 0)


def _run_mediacrawler_with_exclude_filter(user_ids: List[str], max_notes: int, exclude_note_ids_map: Dict[str, List[str]], batch_size: int = 5) -> bool:
    """
    Run MediaCrawler with smart note filtering (excludes already collected notes at source)

    Args:
        user_ids: List of user IDs to crawl
        max_notes: Maximum notes to collect per user
        exclude_note_ids_map: Map of user_id -> list of note_ids to exclude
        batch_size: Number of bloggers to process in each batch (default: 5)

    Returns:
        True if successful, False otherwise
    """
    # Temporarily modify xhs_config to add exclude_note_ids_map
    xhs_config_file = MEDIA_CRAWLER_ROOT / "config" / "xhs_config.py"

    with open(xhs_config_file, 'r', encoding='utf-8') as f:
        xhs_config_content = f.read()

    # Backup original config
    xhs_backup = xhs_config_file.parent / "xhs_config.py.pipeline_backup"
    with open(xhs_backup, 'w', encoding='utf-8') as f:
        f.write(xhs_config_content)

    try:
        import re

        # Update XHS_EXCLUDE_NOTE_IDS_MAP
        # Convert exclude_note_ids_map to Python code string
        map_str = "{\n"
        for user_id, note_ids in exclude_note_ids_map.items():
            # Only include first 1000 IDs to avoid config file being too large
            note_ids_subset = note_ids[:1000] if len(note_ids) > 1000 else note_ids
            map_str += f'    "{user_id}": {note_ids_subset},\n'
        map_str += "}"

        # Replace XHS_EXCLUDE_NOTE_IDS_MAP value
        xhs_config_content = re.sub(
            r'XHS_EXCLUDE_NOTE_IDS_MAP\s*=\s*\{[^}]*\}',
            f'XHS_EXCLUDE_NOTE_IDS_MAP = {map_str}',
            xhs_config_content,
            flags=re.DOTALL
        )

        # Write updated config
        with open(xhs_config_file, 'w', encoding='utf-8') as f:
            f.write(xhs_config_content)

        # Run MediaCrawler with updated config
        success = run_mediacrawler_for_creators_batch(user_ids, max_notes=max_notes, batch_size=batch_size)

        return success

    finally:
        # Restore original config
        if xhs_backup.exists():
            with open(xhs_backup, 'r', encoding='utf-8') as f:
                original_content = f.read()
            with open(xhs_config_file, 'w', encoding='utf-8') as f:
                f.write(original_content)
            xhs_backup.unlink()  # Delete backup


def run_mediacrawler_for_creators_batch(user_ids: List[str], max_notes: int = 100, batch_size: int = 5) -> bool:
    """
    Run MediaCrawler in creator mode to scrape multiple bloggers at once
    Automatically splits into batches if the number of creators is large

    Args:
        user_ids: List of Xiaohongshu user IDs
        max_notes: Maximum number of notes to crawl per creator (default: 100)
        batch_size: Maximum number of creators to process in one batch (default: 5)

    Returns:
        True if successful, False otherwise
    """
    if not user_ids:
        print("⚠️  No user IDs provided")
        return False

    # Auto-batching: Split into smaller batches if too many creators
    if len(user_ids) > batch_size:
        print(f"\n📦 Auto-batching: {len(user_ids)} creators → {(len(user_ids) + batch_size - 1) // batch_size} batches of {batch_size}")

        all_success = True
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(user_ids) + batch_size - 1) // batch_size

            print(f"\n{'='*60}")
            print(f"📦 Batch {batch_num}/{total_batches}: Processing {len(batch)} creators")
            print(f"{'='*60}")

            success = _run_mediacrawler_for_creators_single_batch(batch, max_notes)
            if not success:
                print(f"⚠️  Batch {batch_num} failed, continuing with next batch...")
                all_success = False
            else:
                print(f"✓ Batch {batch_num} completed successfully")

        return all_success
    else:
        # Process all at once if within batch size
        return _run_mediacrawler_for_creators_single_batch(user_ids, max_notes)


def _run_mediacrawler_for_creators_single_batch(user_ids: List[str], max_notes: int = 100) -> bool:
    """
    Internal function: Run MediaCrawler for a single batch of creators

    Args:
        user_ids: List of Xiaohongshu user IDs (should be <= batch_size)
        max_notes: Maximum number of notes to crawl per creator

    Returns:
        True if successful, False otherwise
    """
    print(f"\n🔍 Starting MediaCrawler for {len(user_ids)} creator(s)")

    # Prepare MediaCrawler config files
    base_config_file = MEDIA_CRAWLER_ROOT / "config" / "base_config.py"
    xhs_config_file = MEDIA_CRAWLER_ROOT / "config" / "xhs_config.py"

    # Read both configs
    with open(base_config_file, 'r', encoding='utf-8') as f:
        base_config_content = f.read()
    with open(xhs_config_file, 'r', encoding='utf-8') as f:
        xhs_config_content = f.read()

    # Backup both configs
    base_backup = base_config_file.parent / "base_config.py.pipeline_backup"
    xhs_backup = xhs_config_file.parent / "xhs_config.py.pipeline_backup"

    with open(base_backup, 'w', encoding='utf-8') as f:
        f.write(base_config_content)
    with open(xhs_backup, 'w', encoding='utf-8') as f:
        f.write(xhs_config_content)

    try:
        import re
        import subprocess

        # Modify base_config: Set CRAWLER_TYPE to creator
        # Handle the multi-line format with parentheses: CRAWLER_TYPE = (\n    "value"\n)
        base_config_content = re.sub(
            r'CRAWLER_TYPE\s*=\s*\(.*?\n\)',
            'CRAWLER_TYPE = "creator"',
            base_config_content,
            flags=re.DOTALL
        )
        # Also handle simple single-line format: CRAWLER_TYPE = "value"
        base_config_content = re.sub(
            r'CRAWLER_TYPE\s*=\s*"[^"]*"',
            'CRAWLER_TYPE = "creator"',
            base_config_content
        )

        # Set maximum notes count
        base_config_content = re.sub(
            r'CRAWLER_MAX_NOTES_COUNT = \d+',
            f'CRAWLER_MAX_NOTES_COUNT = {max_notes}',
            base_config_content
        )

        # Disable comment crawling for faster scraping
        base_config_content = re.sub(
            r'ENABLE_GET_COMMENTS\s*=\s*(True|False)',
            'ENABLE_GET_COMMENTS = False',
            base_config_content
        )

        # Save modified base_config
        with open(base_config_file, 'w', encoding='utf-8') as f:
            f.write(base_config_content)

        # Modify xhs_config: Set creator URL/ID list
        # Convert user_ids to full URLs (MediaCrawler expects URLs, not plain IDs)
        creator_urls = [f"https://www.xiaohongshu.com/user/profile/{uid}" for uid in user_ids]
        url_list_str = ", ".join([f'"{url}"' for url in creator_urls])

        # Update XHS_CREATOR_ID_LIST in xhs_config with all creator URLs
        xhs_config_content = re.sub(
            r'XHS_CREATOR_ID_LIST\s*=\s*\[.*?\]',
            f'XHS_CREATOR_ID_LIST = [{url_list_str}]',
            xhs_config_content,
            flags=re.DOTALL
        )

        # Save modified xhs_config
        with open(xhs_config_file, 'w', encoding='utf-8') as f:
            f.write(xhs_config_content)

        print(f"  ✓ Config updated:")
        print(f"    • creator mode")
        print(f"    • {len(user_ids)} creator(s) to process")
        print(f"    • max_notes={max_notes} per creator")
        print(f"    • comments=disabled")

        # Run MediaCrawler using uv
        print(f"  🚀 Launching MediaCrawler...")

        # Calculate dynamic timeout based on number of creators and notes
        # Estimated time: ~4 seconds per note + overhead
        estimated_time_per_creator = max_notes * 4 + 60  # 60s overhead per creator
        total_estimated_time = len(user_ids) * estimated_time_per_creator
        # Add 50% buffer for network delays and anti-crawling
        timeout_seconds = int(total_estimated_time * 1.5)
        # Minimum 5 minutes, maximum 2 hours
        timeout_seconds = max(300, min(timeout_seconds, 7200))

        print(f"  ⏱️  Estimated time: {total_estimated_time//60}min, Timeout: {timeout_seconds//60}min")

        # Check if uv is available
        try:
            uv_check = subprocess.run(["uv", "--version"], capture_output=True)
            use_uv = (uv_check.returncode == 0)
        except FileNotFoundError:
            use_uv = False

        if use_uv:
            cmd = ["uv", "run", "main.py", "--platform", "xhs", "--lt", "qrcode", "--type", "creator"]
        else:
            cmd = [sys.executable, "main.py"]

        print(f"\n{'='*60}")
        print(f"MediaCrawler Output (Real-time):")
        print(f"{'='*60}\n")

        # Run with real-time output streaming
        process = subprocess.Popen(
            cmd,
            cwd=MEDIA_CRAWLER_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True
        )

        # Stream output in real-time
        output_lines = []
        try:
            for line in process.stdout:
                # Print to console in real-time
                print(line, end='')
                # Also collect for later analysis
                output_lines.append(line)

            # Wait for process to complete with timeout
            return_code = process.wait(timeout=timeout_seconds)

        except subprocess.TimeoutExpired:
            print(f"\n⚠️  MediaCrawler timeout after {timeout_seconds}s")
            process.kill()
            return_code = -1
        except Exception as e:
            print(f"\n✗ Error during MediaCrawler execution: {e}")
            process.kill()
            return_code = -1

        print(f"\n{'='*60}")
        print(f"MediaCrawler Finished")
        print(f"{'='*60}\n")

        if return_code == 0:
            print(f"  ✓ MediaCrawler completed successfully")
            return True
        else:
            print(f"  ✗ MediaCrawler failed with return code {return_code}")
            # Show last 20 lines of output for debugging
            if output_lines:
                print(f"\n  ❌ Last 20 lines of output:")
                for line in output_lines[-20:]:
                    print(f"    {line}", end='')
            return False

    except Exception as e:
        print(f"  ✗ Error running MediaCrawler: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Restore both configs
        with open(base_backup, 'r', encoding='utf-8') as f:
            original_base = f.read()
        with open(base_config_file, 'w', encoding='utf-8') as f:
            f.write(original_base)
        base_backup.unlink()

        with open(xhs_backup, 'r', encoding='utf-8') as f:
            original_xhs = f.read()
        with open(xhs_config_file, 'w', encoding='utf-8') as f:
            f.write(original_xhs)
        xhs_backup.unlink()

        print(f"  ✓ Config restored")


def run_mediacrawler_for_creator(user_id: str, max_notes: int = 100) -> bool:
    """
    Run MediaCrawler in creator mode to scrape a single blogger
    This is a wrapper around run_mediacrawler_for_creators_batch for single user

    Args:
        user_id: Xiaohongshu user ID
        max_notes: Maximum number of notes to crawl (default: 100)

    Returns:
        True if successful, False otherwise
    """
    return run_mediacrawler_for_creators_batch([user_id], max_notes)


def clean_note_data(raw_note: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean and normalize note data from MediaCrawler output

    Args:
        raw_note: Raw note data from JSON

    Returns:
        Cleaned note dictionary
    """
    # Parse engagement metrics
    likes = parse_count_str(raw_note.get("liked_count", "0"))
    collects = parse_count_str(raw_note.get("collected_count", "0"))
    comments = parse_count_str(raw_note.get("comment_count", "0"))

    # Determine note type
    note_type = raw_note.get("type", "normal")
    if note_type == "normal":
        note_type = "image"
    elif note_type == "video":
        note_type = "video"
    else:
        note_type = "image"  # default

    # Parse timestamps
    create_time = raw_note.get("time")
    if create_time:
        # Convert milliseconds to datetime string
        create_time = datetime.fromtimestamp(create_time / 1000).strftime("%Y-%m-%d %H:%M:%S")

    # Get note_id and construct note_url
    note_id = raw_note.get("note_id")
    note_url = raw_note.get("note_url", "")

    # If note_url is not in JSON, construct it from note_id
    if not note_url and note_id:
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"

    cleaned_note = {
        "note_id": note_id,
        "user_id": raw_note.get("user_id"),
        "title": raw_note.get("title", ""),
        "desc": raw_note.get("desc", ""),
        "type": note_type,
        "likes": likes,
        "collects": collects,
        "comments": comments,
        "create_time": create_time,
        "cover_url": raw_note.get("image_list", "").split(",")[0] if raw_note.get("image_list") else "",
        "note_url": note_url
    }

    return cleaned_note


def load_notes_from_json(json_file: Path) -> List[Dict[str, Any]]:
    """
    Load and clean all notes from a JSON file

    Args:
        json_file: Path to JSON file

    Returns:
        List of cleaned note dictionaries
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            raw_notes = json.load(f)

        cleaned_notes = []
        for raw_note in raw_notes:
            try:
                cleaned = clean_note_data(raw_note)
                cleaned_notes.append(cleaned)
            except Exception as e:
                print(f"  ⚠ Warning: Failed to clean note {raw_note.get('note_id')}: {e}")
                continue

        return cleaned_notes

    except FileNotFoundError:
        print(f"✗ JSON file not found: {json_file}")
        return []
    except json.JSONDecodeError as e:
        print(f"✗ Error parsing JSON: {e}")
        return []


def scrape_pending_bloggers(
    limit: int = 5,
    use_existing_data: bool = True,
    max_notes: int = 100,
    min_fans: int = 0,
    resume_partial: bool = True,
    batch_size: int = 5
) -> Dict[str, int]:
    """
    Scrape notes for pending bloggers with resume capability

    Args:
        limit: Maximum number of bloggers to scrape
        use_existing_data: If True, use existing JSON data instead of running MediaCrawler
        max_notes: Maximum number of notes to crawl per blogger (default: 100)
        min_fans: Minimum fans threshold - skip bloggers with fewer fans (default: 0 = no filtering)
        resume_partial: If True, resume incomplete scraping for partial status bloggers
        batch_size: Number of bloggers to process in each batch when running MediaCrawler (default: 5)

    Returns:
        Dictionary with statistics (scraped, failed, notes_added, skipped_low_fans, resumed)
    """
    init_db()

    print(f"\n{'='*60}")
    print(f"RedLens Deep Scraping Pipeline v1.2.0")
    print(f"{'='*60}")
    print(f"Mode: {'Using existing data' if use_existing_data else 'Running MediaCrawler'}")
    print(f"Max bloggers to scrape: {limit}")
    if not use_existing_data:
        print(f"Max notes per blogger: {max_notes}")
    if min_fans > 0:
        print(f"Min fans threshold: {min_fans:,}")
    print(f"Resume partial scraping: {'Enabled' if resume_partial else 'Disabled'}")
    print(f"{'='*60}\n")

    # Get pending and resumable bloggers
    pending_bloggers = BloggerDB.get_pending_bloggers(limit=limit)
    resumable_count = BloggerDB.count_resumable_bloggers()

    target_bloggers = []

    if resume_partial and resumable_count > 0:
        resumable_bloggers = BloggerDB.get_resumable_bloggers(limit=limit)
        print(f"📦 Found {resumable_count} blogger(s) with partial scraping to resume")
        target_bloggers.extend(resumable_bloggers)

    target_bloggers.extend(pending_bloggers[:max(0, limit - len(target_bloggers))])

    if not target_bloggers:
        print("✓ No bloggers to scrape")
        return {"scraped": 0, "failed": 0, "notes_added": 0, "skipped_low_fans": 0, "resumed": 0}

    print(f"📋 Found {len(target_bloggers)} blogger(s) to process:")
    for blogger in target_bloggers:
        progress = BloggerDB.get_scrape_progress(blogger['user_id'])
        status_label = progress['scrape_status']
        if progress['notes_collected'] > 0:
            status_label += f" ({progress['notes_collected']}/{progress['notes_target']} notes)"
        print(f"  • {blogger['nickname']} (ID: {blogger['user_id'][:8]}...) [{status_label}]")

    stats = {
        "scraped": 0,
        "failed": 0,
        "notes_added": 0,
        "skipped_low_fans": 0,
        "resumed": 0
    }

    # Phase 1: Filter bloggers by fans count (if enabled)
    qualified_bloggers = []

    if min_fans > 0:
        print(f"\n{'='*60}")
        print(f"Phase 1: Filtering bloggers by fans count (batch mode)")
        print(f"{'='*60}\n")

        # Collect all user IDs
        user_ids = [b["user_id"] for b in target_bloggers]

        # Batch fetch fans for all bloggers
        print(f"Fetching fans count for {len(user_ids)} blogger(s) in batch...")
        fans_dict = fetch_creators_fans_batch(user_ids)

        # Filter based on threshold
        for blogger in target_bloggers:
            user_id = blogger["user_id"]
            nickname = blogger["nickname"]
            fans_count = fans_dict.get(user_id, 0)

            # Update fans in database
            BloggerDB.update_fans(user_id, current_fans=fans_count)

            if fans_count < min_fans:
                print(f"  ⚠ Skipped: {nickname} - Fans ({fans_count:,}) < threshold ({min_fans:,})")
                BloggerDB.update_status(user_id, "error")
                stats["skipped_low_fans"] += 1
            else:
                print(f"  ✓ Qualified: {nickname} - Fans ({fans_count:,}) >= threshold ({min_fans:,})")
                qualified_bloggers.append(blogger)

        print(f"\n{'='*60}")
        print(f"Filtering complete:")
        print(f"  • Total bloggers: {len(target_bloggers)}")
        print(f"  • Qualified: {len(qualified_bloggers)}")
        print(f"  • Skipped (low fans): {stats['skipped_low_fans']}")
        print(f"{'='*60}\n")
    else:
        # No filtering, all bloggers are qualified
        qualified_bloggers = target_bloggers
        print(f"\n✓ Fans filtering disabled, proceeding with all {len(qualified_bloggers)} bloggers\n")

    # If no qualified bloggers, return early
    if not qualified_bloggers:
        print("✓ No qualified bloggers to scrape")
        return stats

    # Phase 2: Scrape notes for qualified bloggers
    print(f"\n{'='*60}")
    print(f"Phase 2: Scraping notes for qualified bloggers")
    print(f"{'='*60}\n")

    if use_existing_data:
        # Load notes from existing JSON files
        json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"
        json_files = list(json_dir.glob("search_contents_*.json"))

        if not json_files:
            print("✗ No JSON files found in data/xhs/json/")
            return stats

        # Use the most recent JSON file
        json_file = max(json_files, key=lambda p: p.stat().st_mtime)
        print(f"\n📂 Loading data from: {json_file.name}")

        all_notes = load_notes_from_json(json_file)
        print(f"✓ Loaded {len(all_notes)} total notes from JSON")

        # Group notes by user_id
        notes_by_user = {}
        for note in all_notes:
            user_id = note["user_id"]
            if user_id not in notes_by_user:
                notes_by_user[user_id] = []
            notes_by_user[user_id].append(note)

        # Process each qualified blogger
        for idx, blogger in enumerate(qualified_bloggers, 1):
            user_id = blogger["user_id"]
            nickname = blogger["nickname"]

            # Check progress
            progress = BloggerDB.get_scrape_progress(user_id)
            notes_collected = progress['notes_collected']
            is_resuming = progress['scrape_status'] == 'partial'

            if notes_collected >= max_notes:
                print(f"✓ [{idx}/{len(qualified_bloggers)}] Skipped: {nickname} - Already completed ({notes_collected}/{max_notes} notes)")
                BloggerDB.update_scrape_progress(user_id, notes_collected, max_notes, 'completed')
                continue

            if is_resuming:
                print(f"🔄 [{idx}/{len(qualified_bloggers)}] Resuming: {nickname} ({notes_collected}/{max_notes} notes)")
                stats["resumed"] += 1
            else:
                print(f"🔄 [{idx}/{len(qualified_bloggers)}] Processing: {nickname}")

            # Mark as in progress
            BloggerDB.update_scrape_progress(user_id, notes_collected, max_notes, 'in_progress')

            # Check if we have notes for this user
            if user_id not in notes_by_user:
                print(f"  ⚠ No notes found for this user")
                BloggerDB.update_scrape_progress(user_id, notes_collected, max_notes, 'partial', 'No notes in JSON')
                stats["failed"] += 1
                continue

            user_notes = notes_by_user[user_id]
            print(f"  ✓ Found {len(user_notes)} note(s) in JSON")

            # Save notes to database
            notes_added = 0
            for note in user_notes:
                try:
                    success = NoteDB.insert_note(
                        note_id=note["note_id"],
                        user_id=note["user_id"],
                        title=note["title"],
                        desc=note["desc"],
                        note_type=note["type"],
                        likes=note["likes"],
                        collects=note["collects"],
                        comments=note["comments"],
                        create_time=note["create_time"],
                        cover_url=note["cover_url"],
                        note_url=note.get("note_url", "")
                    )
                    if success:
                        notes_added += 1
                except Exception as e:
                    print(f"    ⚠ Failed to save note {note['note_id']}: {e}")

            # Count actual notes in database
            total_collected = NoteDB.count_notes_by_user(user_id)
            print(f"  ✓ Saved {notes_added}/{len(user_notes)} notes (Total in DB: {total_collected})")

            # Update progress and status
            # Important: If we got fewer notes than requested, it means the blogger has no more notes
            remaining_needed = max_notes - notes_collected
            if total_collected >= max_notes:
                # Reached or exceeded target
                BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'completed')
                BloggerDB.update_status(user_id, "scraped")
                print(f"  ✓ Status: completed")
                stats["scraped"] += 1
            elif len(user_notes) < remaining_needed:
                # Got fewer notes than expected, meaning blogger has no more notes
                # Adjust target to actual collected amount and mark as completed
                BloggerDB.update_scrape_progress(user_id, total_collected, total_collected, 'completed')
                BloggerDB.update_status(user_id, "scraped")
                print(f"  ✓ Status: completed (blogger has only {total_collected} notes total, adjusted target)")
                stats["scraped"] += 1
            else:
                # Still have more notes to collect
                BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'partial')
                print(f"  ⚠ Status: partial ({total_collected}/{max_notes} notes)")

            stats["notes_added"] += notes_added

            # Simulate delay between bloggers (10-30 seconds)
            if idx < len(qualified_bloggers):
                delay = random.randint(10, 30)
                print(f"  ⏱ Waiting {delay}s before next blogger...")
                time.sleep(delay)

    else:
        # Run MediaCrawler for all qualified bloggers in batch
        qualified_user_ids = [b["user_id"] for b in qualified_bloggers]

        # Mark all bloggers as in_progress BEFORE starting MediaCrawler
        print(f"\n📝 Marking {len(qualified_user_ids)} blogger(s) as in_progress...")

        # Build exclude note IDs map for smart filtering
        exclude_note_ids_map = {}
        for blogger in qualified_bloggers:
            user_id = blogger["user_id"]
            progress = BloggerDB.get_scrape_progress(user_id)

            # Get existing note IDs for this user
            existing_note_ids = NoteDB.get_note_ids_by_user(user_id)

            if existing_note_ids:
                exclude_note_ids_map[user_id] = existing_note_ids
                print(f"  • {blogger['nickname']}: {len(existing_note_ids)} existing notes to exclude")

            BloggerDB.update_scrape_progress(
                user_id=user_id,
                notes_collected=progress['notes_collected'],
                notes_target=max_notes,
                scrape_status='in_progress'
            )
        print(f"✓ All bloggers marked as in_progress\n")

        # Configure MediaCrawler to exclude already collected notes
        if exclude_note_ids_map:
            print(f"📋 Smart filtering enabled: excluding {sum(len(ids) for ids in exclude_note_ids_map.values())} existing notes across {len(exclude_note_ids_map)} blogger(s)\n")

        print(f"🔍 Running MediaCrawler for {len(qualified_user_ids)} blogger(s) in batch...")
        print(f"  Strategy: Fetch latest notes, MediaCrawler will skip already collected notes at source")
        print(f"  Batch size: {batch_size} blogger(s) per batch")
        success = _run_mediacrawler_with_exclude_filter(qualified_user_ids, max_notes, exclude_note_ids_map, batch_size)

        if not success:
            print(f"✗ MediaCrawler batch run failed")
            # Mark all as partial (not failed, so they can be resumed)
            for blogger in qualified_bloggers:
                progress = BloggerDB.get_scrape_progress(blogger['user_id'])
                BloggerDB.update_scrape_progress(
                    user_id=blogger["user_id"],
                    notes_collected=progress['notes_collected'],
                    notes_target=max_notes,
                    scrape_status='partial',
                    failure_reason='MediaCrawler batch failed'
                )
                stats["failed"] += 1
            return stats

        # Load the newly generated data
        json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"

        # Look for creator content files (MediaCrawler saves creator posts separately)
        creator_files = list(json_dir.glob("creator_contents_*.json"))
        if creator_files:
            latest_file = max(creator_files, key=lambda p: p.stat().st_mtime)
        else:
            # Fallback to search contents
            search_files = list(json_dir.glob("search_contents_*.json"))
            if search_files:
                latest_file = max(search_files, key=lambda p: p.stat().st_mtime)
            else:
                print(f"✗ No data files found after scraping")
                # Mark all as failed
                for blogger in qualified_bloggers:
                    BloggerDB.update_status(blogger["user_id"], "error")
                    stats["failed"] += 1
                return stats

        # Load all notes
        print(f"📂 Loading from: {latest_file.name}")
        all_notes = load_notes_from_json(latest_file)

        # Group notes by user_id
        notes_by_user = {}
        for note in all_notes:
            user_id = note["user_id"]
            if user_id not in notes_by_user:
                notes_by_user[user_id] = []
            notes_by_user[user_id].append(note)

        # Process each qualified blogger
        for idx, blogger in enumerate(qualified_bloggers, 1):
            user_id = blogger["user_id"]
            nickname = blogger["nickname"]

            # Check progress
            progress = BloggerDB.get_scrape_progress(user_id)
            notes_collected = progress['notes_collected']
            is_resuming = progress['scrape_status'] == 'partial'

            if notes_collected >= max_notes:
                print(f"\n✓ [{idx}/{len(qualified_bloggers)}] Skipped: {nickname} - Already completed ({notes_collected}/{max_notes} notes)")
                BloggerDB.update_scrape_progress(user_id, notes_collected, max_notes, 'completed')
                continue

            if is_resuming:
                print(f"\n🔄 [{idx}/{len(qualified_bloggers)}] Resuming: {nickname} ({notes_collected}/{max_notes} notes)")
                stats["resumed"] += 1
            else:
                print(f"\n🔄 [{idx}/{len(qualified_bloggers)}] Processing: {nickname}")

            # Mark as in progress
            BloggerDB.update_scrape_progress(user_id, notes_collected, max_notes, 'in_progress')

            # Check if we have notes for this user in JSON
            if user_id not in notes_by_user:
                print(f"  ⚠ No notes found for this user in JSON")
                BloggerDB.update_scrape_progress(user_id, notes_collected, max_notes, 'partial', 'No notes in JSON')
                stats["failed"] += 1
                continue

            user_notes = notes_by_user[user_id]
            print(f"  ✓ Found {len(user_notes)} new note(s) from MediaCrawler (duplicates already filtered at source)")

            # Save notes to database
            notes_added = 0
            for note in user_notes:
                try:
                    success = NoteDB.insert_note(
                        note_id=note["note_id"],
                        user_id=note["user_id"],
                        title=note["title"],
                        desc=note["desc"],
                        note_type=note["type"],
                        likes=note["likes"],
                        collects=note["collects"],
                        comments=note["comments"],
                        create_time=note["create_time"],
                        cover_url=note["cover_url"],
                        note_url=note.get("note_url", "")
                    )
                    if success:
                        notes_added += 1
                except Exception as e:
                    print(f"    ⚠ Failed to save note {note['note_id']}: {e}")

            # Count actual notes in database
            total_collected = NoteDB.count_notes_by_user(user_id)
            print(f"  ✓ Saved {notes_added}/{len(user_notes)} notes (Total in DB: {total_collected})")

            # Update progress and status
            # Important: If we got fewer notes than requested, it means the blogger has no more notes
            remaining_needed = max_notes - notes_collected
            if total_collected >= max_notes:
                # Reached or exceeded target
                BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'completed')
                BloggerDB.update_status(user_id, "scraped")
                print(f"  ✓ Status: completed")
                stats["scraped"] += 1
            elif len(user_notes) < remaining_needed:
                # Got fewer notes than expected, meaning blogger has no more notes
                # Adjust target to actual collected amount and mark as completed
                BloggerDB.update_scrape_progress(user_id, total_collected, total_collected, 'completed')
                BloggerDB.update_status(user_id, "scraped")
                print(f"  ✓ Status: completed (blogger has only {total_collected} notes total, adjusted target)")
                stats["scraped"] += 1
            else:
                # Still have more notes to collect
                BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'partial')
                print(f"  ⚠ Status: partial ({total_collected}/{max_notes} notes)")

            stats["notes_added"] += notes_added

            # Delay between bloggers
            if idx < len(qualified_bloggers):
                delay = random.randint(10, 30)
                print(f"  ⏱ Waiting {delay}s before next blogger...")
                time.sleep(delay)

    # Final summary
    print(f"\n{'='*60}")
    print("Scraping Complete")
    print(f"{'='*60}")
    print(f"✓ Successfully scraped: {stats['scraped']}")
    print(f"✓ Total notes added: {stats['notes_added']}")
    if stats['skipped_low_fans'] > 0:
        print(f"⚠ Skipped (low fans): {stats['skipped_low_fans']}")
    if stats['failed'] > 0:
        print(f"✗ Failed: {stats['failed']}")
    print(f"{'='*60}\n")

    return stats


def clean_all_data(json_dir: Optional[Path] = None) -> Dict[str, int]:
    """
    Batch process all JSON files and clean data

    Args:
        json_dir: Directory containing JSON files (default: data/xhs/json/)

    Returns:
        Statistics dictionary
    """
    if json_dir is None:
        json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"

    init_db()

    print(f"\n{'='*60}")
    print(f"RedLens Data Cleaning Pipeline")
    print(f"{'='*60}")
    print(f"Source directory: {json_dir}")
    print(f"{'='*60}\n")

    # Find all JSON files
    json_files = list(json_dir.glob("search_contents_*.json"))

    if not json_files:
        print("✗ No JSON files found")
        return {"files": 0, "notes": 0, "bloggers": 0}

    print(f"📂 Found {len(json_files)} JSON file(s)")

    all_notes = []
    all_bloggers = {}  # Deduplicate by user_id

    for json_file in json_files:
        print(f"\n📄 Processing: {json_file.name}")

        with open(json_file, 'r', encoding='utf-8') as f:
            raw_notes = json.load(f)

        print(f"  • Loaded {len(raw_notes)} notes")

        for raw_note in raw_notes:
            try:
                # Clean note
                cleaned_note = clean_note_data(raw_note)
                all_notes.append(cleaned_note)

                # Extract blogger info
                user_id = raw_note.get("user_id")
                if user_id and user_id not in all_bloggers:
                    all_bloggers[user_id] = {
                        "user_id": user_id,
                        "nickname": raw_note.get("nickname", "Unknown"),
                        "avatar_url": raw_note.get("avatar", ""),
                        "source_keyword": raw_note.get("source_keyword", "")
                    }

            except Exception as e:
                print(f"    ⚠ Warning: Failed to process note: {e}")
                continue

    # Save to database
    print(f"\n💾 Saving to database...")

    # Save bloggers
    bloggers_added = 0
    for blogger in all_bloggers.values():
        success = BloggerDB.insert_blogger(
            user_id=blogger["user_id"],
            nickname=blogger["nickname"],
            avatar_url=blogger["avatar_url"],
            source_keyword=blogger["source_keyword"]
        )
        if success:
            bloggers_added += 1

    # Save notes
    notes_added = 0
    for note in all_notes:
        success = NoteDB.insert_note(
            note_id=note["note_id"],
            user_id=note["user_id"],
            title=note["title"],
            desc=note["desc"],
            note_type=note["type"],
            likes=note["likes"],
            collects=note["collects"],
            comments=note["comments"],
            create_time=note["create_time"],
            cover_url=note["cover_url"]
        )
        if success:
            notes_added += 1

    stats = {
        "files": len(json_files),
        "notes": notes_added,
        "bloggers": bloggers_added
    }

    print(f"\n{'='*60}")
    print(f"✓ Cleaning completed!")
    print(f"  Files processed: {stats['files']}")
    print(f"  Bloggers saved: {stats['bloggers']}")
    print(f"  Notes saved: {stats['notes']}")
    print(f"{'='*60}\n")

    return stats


def scrape_specific_bloggers(
    user_ids: List[str],
    max_notes: int = 100,
    batch_size: int = 5
) -> Dict[str, int]:
    """
    为指定的博主列表采集笔记（带智能过滤，排除已采集笔记）

    专门用于恢复采集模式，只采集缺失的笔记，避免重复采集

    Args:
        user_ids: 要采集的博主 ID 列表
        max_notes: 每个博主的目标笔记数量（默认: 100）
        batch_size: 批处理大小（默认: 5）

    Returns:
        统计信息字典: {"scraped": int, "failed": int, "notes_added": int, "resumed": int}
    """
    init_db()

    print(f"\n{'='*60}")
    print(f"RedLens Specific Bloggers Scraping (Resume Mode)")
    print(f"{'='*60}")
    print(f"Target bloggers: {len(user_ids)}")
    print(f"Max notes per blogger: {max_notes}")
    print(f"Batch size: {batch_size}")
    print(f"{'='*60}\n")

    stats = {
        "scraped": 0,
        "failed": 0,
        "notes_added": 0,
        "resumed": len(user_ids)
    }

    # Get blogger information
    target_bloggers = []
    for user_id in user_ids:
        blogger = BloggerDB.get_blogger(user_id)
        if blogger:
            target_bloggers.append(blogger)
        else:
            print(f"⚠ Warning: Blogger {user_id} not found in database")
            stats["failed"] += 1

    if not target_bloggers:
        print("✗ No valid bloggers to process")
        return stats

    print(f"📋 Processing {len(target_bloggers)} blogger(s):")
    for blogger in target_bloggers:
        progress = BloggerDB.get_scrape_progress(blogger['user_id'])
        print(f"  • {blogger['nickname']} ({progress['notes_collected']}/{max_notes} notes)")

    # Mark all bloggers as in_progress BEFORE starting MediaCrawler
    # print(f"\n📝 Marking {len(target_bloggers)} blogger(s) as in_progress...")

    # Build exclude note IDs map for smart filtering
    # Calculate the maximum remaining notes needed
    max_remaining_notes = 0
    exclude_note_ids_map = {}

    for blogger in target_bloggers:
        user_id = blogger["user_id"]
        progress = BloggerDB.get_scrape_progress(user_id)
        notes_collected = progress['notes_collected']

        # Calculate remaining notes needed for this blogger
        remaining_notes = max(0, max_notes - notes_collected)
        max_remaining_notes = max(max_remaining_notes, remaining_notes)

        # Get existing note IDs for this user
        existing_note_ids = NoteDB.get_note_ids_by_user(user_id)

        if existing_note_ids:
            exclude_note_ids_map[user_id] = existing_note_ids
            print(f"  • {blogger['nickname']}: {len(existing_note_ids)} existing notes to exclude, needs {remaining_notes} more")
        else:
            print(f"  • {blogger['nickname']}: needs {remaining_notes} notes")

        BloggerDB.update_scrape_progress(
            user_id=user_id,
            notes_collected=progress['notes_collected'],
            notes_target=max_notes,
            scrape_status='in_progress'
        )

    # Use the maximum remaining notes for MediaCrawler
    # This ensures we fetch enough for the blogger who needs the most
    if max_remaining_notes == 0:
        print(f"\n✓ All bloggers have reached their target, no need to crawl")
        return stats

    print(f"\n💡 Will fetch up to {max_remaining_notes} new notes per blogger")
    # print(f"✓ All bloggers marked as in_progress\n")

    # Configure MediaCrawler to exclude already collected notes
    if exclude_note_ids_map:
        print(f"📋 Smart filtering enabled: excluding {sum(len(ids) for ids in exclude_note_ids_map.values())} existing notes across {len(exclude_note_ids_map)} blogger(s)\n")

    print(f"🔍 Running MediaCrawler for {len(target_bloggers)} blogger(s) in batch...")
    print(f"  Strategy: Fetch latest notes, MediaCrawler will skip already collected notes at source")
    print(f"  Batch size: {batch_size} blogger(s) per batch")

    # Use max_remaining_notes instead of max_notes to avoid over-fetching
    success = _run_mediacrawler_with_exclude_filter(user_ids, max_remaining_notes, exclude_note_ids_map, batch_size)

    if not success:
        print(f"✗ MediaCrawler batch run failed")
        # Mark all as partial (not failed, so they can be resumed)
        for blogger in target_bloggers:
            progress = BloggerDB.get_scrape_progress(blogger['user_id'])
            BloggerDB.update_scrape_progress(
                user_id=blogger["user_id"],
                notes_collected=progress['notes_collected'],
                notes_target=max_notes,
                scrape_status='partial',
                failure_reason='MediaCrawler batch failed'
            )
            stats["failed"] += 1
        return stats

    # Load the newly generated data
    json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"

    # Look for creator content files (MediaCrawler saves creator posts separately)
    creator_files = list(json_dir.glob("creator_contents_*.json"))
    if creator_files:
        latest_file = max(creator_files, key=lambda p: p.stat().st_mtime)
    else:
        # Fallback to search contents
        search_files = list(json_dir.glob("search_contents_*.json"))
        if search_files:
            latest_file = max(search_files, key=lambda p: p.stat().st_mtime)
        else:
            print(f"✗ No data files found after scraping")
            for blogger in target_bloggers:
                progress = BloggerDB.get_scrape_progress(blogger['user_id'])
                BloggerDB.update_scrape_progress(
                    blogger["user_id"],
                    progress['notes_collected'],
                    max_notes,
                    'partial',
                    'No result file'
                )
                stats["failed"] += 1
            return stats

    print(f"\n📂 Loading data from: {latest_file.name}")
    all_notes = load_notes_from_json(latest_file)
    print(f"✓ Loaded {len(all_notes)} total notes from JSON")

    # Group notes by user_id
    notes_by_user = {}
    for note in all_notes:
        note_user_id = note["user_id"]
        if note_user_id in user_ids:
            if note_user_id not in notes_by_user:
                notes_by_user[note_user_id] = []
            notes_by_user[note_user_id].append(note)

    print(f"\n{'='*60}")
    print(f"Processing notes for each blogger")
    print(f"{'='*60}\n")

    # Process each blogger
    for idx, blogger in enumerate(target_bloggers, 1):
        user_id = blogger["user_id"]
        nickname = blogger["nickname"]

        # Check progress
        progress = BloggerDB.get_scrape_progress(user_id)
        notes_collected = progress['notes_collected']

        print(f"🔄 [{idx}/{len(target_bloggers)}] {nickname} (Previously: {notes_collected} notes)")

        # Check if we have notes for this user in JSON
        if user_id not in notes_by_user:
            print(f"  ⚠ No new notes found in JSON")
            BloggerDB.update_scrape_progress(user_id, notes_collected, max_notes, 'partial', 'No notes in JSON')
            stats["failed"] += 1
            continue

        user_notes = notes_by_user[user_id]
        print(f"  ✓ Found {len(user_notes)} new note(s) from MediaCrawler")

        # Save notes to database
        notes_added = 0
        for note in user_notes:
            try:
                success = NoteDB.insert_note(
                    note_id=note["note_id"],
                    user_id=note["user_id"],
                    title=note["title"],
                    desc=note["desc"],
                    note_type=note["type"],
                    likes=note["likes"],
                    collects=note["collects"],
                    comments=note["comments"],
                    create_time=note["create_time"],
                    cover_url=note["cover_url"],
                    note_url=note.get("note_url", "")
                )
                if success:
                    notes_added += 1
            except Exception as e:
                print(f"    ⚠ Failed to save note {note['note_id']}: {e}")

        # Count actual notes in database
        total_collected = NoteDB.count_notes_by_user(user_id)
        print(f"  ✓ Saved {notes_added} new notes (Total in DB: {total_collected})")

        # Update progress and status
        if total_collected >= max_notes:
            # Reached or exceeded target
            BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'completed')
            BloggerDB.update_status(user_id, "scraped")
            print(f"  ✓ Status: completed (reached target)")
            stats["scraped"] += 1
        else:
            # Still need more notes OR no more notes available from blogger
            if len(user_notes) == 0:
                # No new notes means blogger has no more notes to offer
                BloggerDB.update_scrape_progress(user_id, total_collected, total_collected, 'completed')
                BloggerDB.update_status(user_id, "scraped")
                print(f"  ✓ Status: completed (blogger has only {total_collected} notes total)")
                stats["scraped"] += 1
            else:
                # Got some notes but not enough
                BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'partial')
                print(f"  ⚠ Status: partial ({total_collected}/{max_notes} notes)")

        stats["notes_added"] += notes_added

    print(f"\n{'='*60}")
    print(f"✓ Scraping completed!")
    print(f"  Bloggers processed: {len(target_bloggers)}")
    print(f"  Successfully completed: {stats['scraped']}")
    print(f"  Failed/Partial: {stats['failed']}")
    print(f"  Total new notes added: {stats['notes_added']}")
    print(f"{'='*60}\n")

    return stats


def main():
    """Test the pipeline module"""

    # First, clean all existing data
    print("=" * 60)
    print("STEP 1: Batch clean all JSON data")
    print("=" * 60)
    clean_stats = clean_all_data()

    # Then, scrape pending bloggers
    print("\n" + "=" * 60)
    print("STEP 2: Scrape pending bloggers")
    print("=" * 60)
    scrape_stats = scrape_pending_bloggers(limit=5, use_existing_data=True)

    # Show final statistics
    print("\n" + "=" * 60)
    print("📊 Final Statistics")
    print("=" * 60)
    print(f"Total bloggers in DB: {len(BloggerDB.get_all_bloggers())}")
    print(f"  • Pending: {BloggerDB.count_by_status('pending')}")
    print(f"  • Scraped: {BloggerDB.count_by_status('scraped')}")
    print(f"  • Error: {BloggerDB.count_by_status('error')}")
    print()

    # Sample blogger stats
    all_bloggers = BloggerDB.get_all_bloggers()
    if all_bloggers:
        sample_blogger = all_bloggers[0]
        notes_count = NoteDB.count_notes_by_user(sample_blogger["user_id"])
        avg_likes = NoteDB.get_avg_likes_by_user(sample_blogger["user_id"])
        print(f"Sample blogger: {sample_blogger['nickname']}")
        print(f"  • Notes: {notes_count}")
        print(f"  • Avg likes: {avg_likes:.0f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
