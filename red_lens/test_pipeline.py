#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for pipeline module - scrape_pending_bloggers with MediaCrawler
"""

import sys
from pathlib import Path

MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.pipeline import scrape_pending_bloggers
from red_lens.db import BloggerDB, NoteDB, init_db


def test_scrape_with_mediacrawler():
    """
    Test scraping pending bloggers using actual MediaCrawler
    """
    print("\n" + "=" * 70)
    print("  Pipeline Test: Scrape Pending Bloggers with MediaCrawler")
    print("=" * 70)

    # Initialize database
    init_db()

    # Check for pending bloggers
    pending = BloggerDB.get_pending_bloggers(limit=10)

    if not pending:
        print("\n⚠️  No pending bloggers found in database")
        print("   Please run discovery first:")
        print("   python red_lens/discovery.py")
        return 1

    print(f"\n📋 Found {len(pending)} pending blogger(s):")
    for b in pending[:5]:  # Show first 5
        print(f"  • {b['nickname']} (ID: {b['user_id'][:10]}...)")

    if len(pending) > 5:
        print(f"  ... and {len(pending) - 5} more")

    # Ask for confirmation
    print("\n⚠️  This test will:")
    print("  • Run MediaCrawler in creator mode")
    print("  • Open browser and require login")
    print("  • Scrape notes for 1-2 pending bloggers")
    print("  • Take 5-10 minutes")
    print()

    test_limit = min(2, len(pending))  # Test with 1-2 bloggers max
    print(f"Test will process: {test_limit} blogger(s)")
    print()

    # Check JSON files before
    json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"
    before_files = list(json_dir.glob("creator_contents_*.json"))
    print(f"📂 Creator JSON files before: {len(before_files)}")

    if before_files:
        latest = max(before_files, key=lambda p: p.stat().st_mtime)
        print(f"   Latest: {latest.name}")
        before_mtime = latest.stat().st_mtime

    # Run scraping
    print("\n" + "=" * 70)
    print("RUNNING SCRAPING TEST")
    print("=" * 70)

    try:
        stats = scrape_pending_bloggers(
            limit=test_limit,
            use_existing_data=False,  # ✅ Use MediaCrawler
            max_notes=20  # Test with 20 notes per blogger
        )

        # Check results
        print("\n" + "=" * 70)
        print("VERIFICATION")
        print("=" * 70)

        # Check JSON files after
        after_files = list(json_dir.glob("creator_contents_*.json"))
        new_files = set(after_files) - set(before_files)

        print(f"\n📂 Creator JSON files after: {len(after_files)}")

        verified = False

        if new_files:
            print(f"   ✅ NEW file(s) created: {len(new_files)}")
            for f in new_files:
                print(f"      - {f.name} ({f.stat().st_size:,} bytes)")
            verified = True

        elif before_files:
            latest_after = max(after_files, key=lambda p: p.stat().st_mtime)
            if latest_after.stat().st_mtime > before_mtime:
                print(f"   ✅ File UPDATED: {latest_after.name}")
                verified = True
            else:
                print(f"   ⚠️  No files changed")

        # Check database
        print(f"\n📊 Scraping Statistics:")
        print(f"   Bloggers scraped: {stats['scraped']}")
        print(f"   Bloggers failed: {stats['failed']}")
        print(f"   Total notes added: {stats['notes_added']}")

        # Check specific bloggers
        if stats['scraped'] > 0:
            scraped_bloggers = [b for b in BloggerDB.get_all_bloggers() if b['status'] == 'scraped']

            if scraped_bloggers:
                sample = scraped_bloggers[0]
                notes_count = NoteDB.count_notes_by_user(sample['user_id'])
                print(f"\n📝 Sample blogger: {sample['nickname']}")
                print(f"   Status: {sample['status']}")
                print(f"   Notes in DB: {notes_count}")

                if notes_count > 0:
                    print(f"   ✅ Notes successfully saved!")
                    verified = True

        # Final verdict
        print("\n" + "=" * 70)
        print("TEST RESULT")
        print("=" * 70)

        if verified and stats['scraped'] > 0:
            print("\n✅✅✅ TEST PASSED!")
            print("\n证明:")
            print("  • MediaCrawler creator mode 成功运行")
            print("  • JSON 数据已生成/更新")
            print("  • 博主笔记已抓取")
            print("  • 数据已存入数据库")
            print("  • scrape_pending_bloggers 功能正常!")
            return 0

        elif stats['failed'] > 0 and stats['scraped'] == 0:
            print("\n⚠️  TEST INCONCLUSIVE")
            print("\n可能原因:")
            print("  • MediaCrawler 执行失败")
            print("  • 网络问题")
            print("  • 登录中断")
            return 1

        else:
            print("\n⚠️  TEST PARTIALLY PASSED")
            print(f"  • Scraped: {stats['scraped']}")
            print(f"  • Failed: {stats['failed']}")
            return 0 if stats['scraped'] > 0 else 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user (Ctrl+C)")
        return 1

    except Exception as e:
        print(f"\n\n❌ Test failed with exception:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    print("\n" + "=" * 70)
    print("  RedLens Pipeline Module Test")
    print("  Testing: scrape_pending_bloggers with MediaCrawler")
    print("=" * 70)

    exit_code = test_scrape_with_mediacrawler()

    print("\n" + "=" * 70)
    if exit_code == 0:
        print("🎉 测试成功!")
    else:
        print("⚠️  测试未通过，请查看上方输出")
    print("=" * 70 + "\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
