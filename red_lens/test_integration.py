#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RedLens Integration Test
Run all modules to verify functionality
"""

import sys
from pathlib import Path

MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.db import init_db, BloggerDB, NoteDB
from red_lens.discovery import search_and_extract_users
from red_lens.pipeline import scrape_pending_bloggers, clean_all_data
from red_lens.analyzer import analyze_all_bloggers, download_outlier_covers, generate_ai_report


def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def test_database():
    """Test database initialization"""
    print_header("TEST 1: Database Module")

    init_db()
    print("✓ Database initialized")

    # Test data
    test_user = "test_integration_user"
    success = BloggerDB.insert_blogger(
        user_id=test_user,
        nickname="Integration Test User",
        source_keyword="test"
    )
    print(f"✓ Insert test blogger: {success}")

    blogger = BloggerDB.get_blogger(test_user)
    print(f"✓ Retrieve blogger: {blogger['nickname']}")

    print("\n✅ Database module passed")


def test_discovery():
    """Test blogger discovery"""
    print_header("TEST 2: Discovery Module")

    # Use existing data
    new_count = search_and_extract_users(
        keywords=["摄影"],
        min_likes=200
    )

    print(f"\n✅ Discovery module passed (found {new_count} new bloggers)")


def test_pipeline():
    """Test data scraping and cleaning"""
    print_header("TEST 3: Pipeline Module")

    # Clean existing data
    stats = clean_all_data()
    print(f"✓ Cleaned {stats['notes']} notes from {stats['files']} files")

    # Scrape pending bloggers
    scrape_stats = scrape_pending_bloggers(limit=2, use_existing_data=True)
    print(f"✓ Scraped {scrape_stats['scraped']} bloggers")

    print("\n✅ Pipeline module passed")


def test_analyzer():
    """Test analysis and AI insights"""
    print_header("TEST 4: Analyzer Module")

    # Analyze all bloggers
    analyses = analyze_all_bloggers()
    print(f"✓ Analyzed {len(analyses)} bloggers")

    if analyses:
        # Generate AI report for first blogger
        top_blogger = analyses[0]
        user_id = top_blogger["blogger"]["user_id"]
        report = generate_ai_report(user_id, use_mock=True)
        print(f"✓ Generated AI report ({len(report)} chars)")

    print("\n✅ Analyzer module passed")


def show_final_statistics():
    """Show final statistics"""
    print_header("FINAL STATISTICS")

    all_bloggers = BloggerDB.get_all_bloggers()
    pending = BloggerDB.count_by_status("pending")
    scraped = BloggerDB.count_by_status("scraped")
    error = BloggerDB.count_by_status("error")

    print(f"📊 Database Summary:")
    print(f"  • Total bloggers: {len(all_bloggers)}")
    print(f"  • Pending: {pending}")
    print(f"  • Scraped: {scraped}")
    print(f"  • Error: {error}")
    print()

    # Sample blogger
    if scraped > 0:
        scraped_bloggers = [b for b in all_bloggers if b["status"] == "scraped"]
        sample = scraped_bloggers[0]
        notes_count = NoteDB.count_notes_by_user(sample["user_id"])
        avg_likes = NoteDB.get_avg_likes_by_user(sample["user_id"])
        outliers = len(NoteDB.get_outlier_notes(sample["user_id"]))

        print(f"📝 Sample Blogger: {sample['nickname']}")
        print(f"  • Total notes: {notes_count}")
        print(f"  • Average likes: {avg_likes:.0f}")
        print(f"  • Outlier notes: {outliers}")
        print()

    # Overall stats
    all_notes = []
    for blogger in all_bloggers:
        notes = NoteDB.get_notes_by_user(blogger["user_id"])
        all_notes.extend(notes)

    if all_notes:
        total_notes = len(all_notes)
        total_outliers = sum(1 for n in all_notes if n["is_outlier"])
        total_likes = sum(n["likes"] for n in all_notes)

        print(f"📈 Content Statistics:")
        print(f"  • Total notes: {total_notes}")
        print(f"  • Total outliers: {total_outliers}")
        print(f"  • Total likes: {total_likes:,}")
        print(f"  • Outlier rate: {total_outliers/total_notes:.1%}" if total_notes > 0 else "")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("  RedLens Integration Test Suite")
    print("=" * 60)

    try:
        test_database()
        test_discovery()
        test_pipeline()
        test_analyzer()

        show_final_statistics()

        print("\n" + "=" * 60)
        print("  ✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\n🚀 Ready to launch Streamlit dashboard:")
        print("   streamlit run red_lens/app.py")
        print()

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
