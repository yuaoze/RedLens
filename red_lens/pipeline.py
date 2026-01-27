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

    cleaned_note = {
        "note_id": raw_note.get("note_id"),
        "user_id": raw_note.get("user_id"),
        "title": raw_note.get("title", ""),
        "desc": raw_note.get("desc", ""),
        "type": note_type,
        "likes": likes,
        "collects": collects,
        "comments": comments,
        "create_time": create_time,
        "cover_url": raw_note.get("image_list", "").split(",")[0] if raw_note.get("image_list") else ""
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


def scrape_pending_bloggers(limit: int = 5, use_existing_data: bool = True) -> Dict[str, int]:
    """
    Scrape notes for pending bloggers

    Args:
        limit: Maximum number of bloggers to scrape
        use_existing_data: If True, use existing JSON data instead of running MediaCrawler

    Returns:
        Dictionary with statistics (scraped, failed, notes_added)
    """
    init_db()

    print(f"\n{'='*60}")
    print(f"RedLens Deep Scraping Pipeline")
    print(f"{'='*60}")
    print(f"Mode: {'Using existing data' if use_existing_data else 'Running MediaCrawler'}")
    print(f"Max bloggers to scrape: {limit}")
    print(f"{'='*60}\n")

    # Get pending bloggers
    pending_bloggers = BloggerDB.get_pending_bloggers(limit=limit)

    if not pending_bloggers:
        print("✓ No pending bloggers to scrape")
        return {"scraped": 0, "failed": 0, "notes_added": 0}

    print(f"📋 Found {len(pending_bloggers)} pending blogger(s):")
    for blogger in pending_bloggers:
        print(f"  • {blogger['nickname']} (ID: {blogger['user_id'][:8]}...)")

    stats = {
        "scraped": 0,
        "failed": 0,
        "notes_added": 0
    }

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

        # Process each pending blogger
        print(f"\n{'='*60}")
        print("Processing bloggers...")
        print(f"{'='*60}\n")

        for blogger in pending_bloggers:
            user_id = blogger["user_id"]
            nickname = blogger["nickname"]

            print(f"🔄 Processing: {nickname}")

            # Check if we have notes for this user
            if user_id not in notes_by_user:
                print(f"  ⚠ No notes found for this user")
                BloggerDB.update_status(user_id, "error")
                stats["failed"] += 1
                continue

            user_notes = notes_by_user[user_id]
            print(f"  ✓ Found {len(user_notes)} note(s)")

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
                        cover_url=note["cover_url"]
                    )
                    if success:
                        notes_added += 1
                except Exception as e:
                    print(f"    ⚠ Failed to save note {note['note_id']}: {e}")

            print(f"  ✓ Saved {notes_added}/{len(user_notes)} notes to database")

            # Update blogger status
            BloggerDB.update_status(user_id, "scraped")
            stats["scraped"] += 1
            stats["notes_added"] += notes_added

            # Simulate delay between bloggers (10-30 seconds)
            if len(pending_bloggers) > 1:
                delay = random.randint(10, 30)
                print(f"  ⏱ Waiting {delay}s before next blogger...")
                time.sleep(delay)

    else:
        # TODO: Implement actual MediaCrawler execution for specific bloggers
        print("✗ Running MediaCrawler for specific bloggers not yet implemented")
        print("  Use use_existing_data=True mode for now")
        return stats

    # Final summary
    print(f"\n{'='*60}")
    print(f"✓ Scraping completed!")
    print(f"  Bloggers scraped: {stats['scraped']}")
    print(f"  Bloggers failed: {stats['failed']}")
    print(f"  Total notes added: {stats['notes_added']}")
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
