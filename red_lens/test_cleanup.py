#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for cleanup features (功能2)
"""

import sys
from pathlib import Path

MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.db import init_db, BloggerDB, NoteDB


def test_reset_blogger_status():
    """Test resetting a blogger's status and deleting their notes"""
    print("\n" + "=" * 70)
    print("  Test: Reset Blogger Status")
    print("=" * 70)

    init_db()

    # Get a scraped blogger
    scraped_bloggers = BloggerDB.get_bloggers_by_status("scraped")

    if not scraped_bloggers:
        print("⚠️  No scraped bloggers found. Cannot test reset functionality.")
        return False

    test_blogger = scraped_bloggers[0]
    user_id = test_blogger["user_id"]
    nickname = test_blogger["nickname"]

    print(f"\n📋 Testing with blogger: {nickname}")
    print(f"   User ID: {user_id}")
    print(f"   Current status: {test_blogger['status']}")

    # Count notes before reset
    notes_before = NoteDB.count_notes_by_user(user_id)
    print(f"   Notes before reset: {notes_before}")

    # Reset blogger status
    print(f"\n🔄 Resetting blogger status...")
    success = BloggerDB.reset_blogger_status(user_id)

    if not success:
        print("❌ TEST FAILED: reset_blogger_status returned False")
        return False

    # Verify blogger status changed to pending
    updated_blogger = BloggerDB.get_blogger(user_id)
    if updated_blogger["status"] != "pending":
        print(f"❌ TEST FAILED: Status is {updated_blogger['status']}, expected 'pending'")
        return False

    print(f"✅ Blogger status changed to: {updated_blogger['status']}")

    # Verify notes were deleted
    notes_after = NoteDB.count_notes_by_user(user_id)
    if notes_after != 0:
        print(f"❌ TEST FAILED: {notes_after} notes still exist, expected 0")
        return False

    print(f"✅ All notes deleted (was {notes_before}, now {notes_after})")

    print(f"\n✅ TEST PASSED: reset_blogger_status works correctly")
    return True


def test_delete_blogger():
    """Test deleting a blogger and all their notes"""
    print("\n" + "=" * 70)
    print("  Test: Delete Blogger")
    print("=" * 70)

    init_db()

    # Create a test blogger
    test_user_id = "test_delete_blogger_456"
    test_nickname = "测试删除博主"

    print(f"\n📋 Creating test blogger: {test_nickname}")
    BloggerDB.insert_blogger(
        user_id=test_user_id,
        nickname=test_nickname,
        initial_fans=100,
        source_keyword="测试"
    )

    # Add some test notes
    print(f"📝 Adding test notes...")
    for i in range(3):
        NoteDB.insert_note(
            note_id=f"test_note_{i}",
            user_id=test_user_id,
            title=f"测试笔记 {i}",
            likes=100 * i,
            note_url=f"https://www.xiaohongshu.com/explore/test_note_{i}"
        )

    notes_count = NoteDB.count_notes_by_user(test_user_id)
    print(f"✅ Created {notes_count} test notes")

    # Delete blogger
    print(f"\n🗑️  Deleting blogger...")
    success = BloggerDB.delete_blogger(test_user_id)

    if not success:
        print("❌ TEST FAILED: delete_blogger returned False")
        return False

    # Verify blogger is deleted
    deleted_blogger = BloggerDB.get_blogger(test_user_id)
    if deleted_blogger is not None:
        print("❌ TEST FAILED: Blogger still exists in database")
        return False

    print(f"✅ Blogger deleted from database")

    # Verify notes are deleted
    notes_after = NoteDB.count_notes_by_user(test_user_id)
    if notes_after != 0:
        print(f"❌ TEST FAILED: {notes_after} notes still exist, expected 0")
        return False

    print(f"✅ All notes deleted")

    print(f"\n✅ TEST PASSED: delete_blogger works correctly")
    return True


def test_get_bloggers_by_keyword():
    """Test filtering bloggers by keyword"""
    print("\n" + "=" * 70)
    print("  Test: Get Bloggers by Keyword")
    print("=" * 70)

    init_db()

    # Get all bloggers to find a keyword
    all_bloggers = BloggerDB.get_all_bloggers()

    if not all_bloggers:
        print("⚠️  No bloggers found. Cannot test keyword filtering.")
        return False

    # Find a blogger with a keyword
    test_keyword = None
    for blogger in all_bloggers:
        if blogger.get("source_keyword"):
            test_keyword = blogger["source_keyword"]
            break

    if not test_keyword:
        print("⚠️  No bloggers with keywords found.")
        return False

    print(f"\n📋 Testing with keyword: {test_keyword}")

    # Get bloggers by keyword
    filtered_bloggers = BloggerDB.get_bloggers_by_keyword(test_keyword)

    print(f"✅ Found {len(filtered_bloggers)} bloggers with keyword '{test_keyword}'")

    # Verify all results contain the keyword
    for blogger in filtered_bloggers:
        if test_keyword not in (blogger.get("source_keyword") or ""):
            print(f"❌ TEST FAILED: Blogger {blogger['nickname']} doesn't have keyword '{test_keyword}'")
            return False

    print(f"✅ All filtered bloggers contain the keyword")

    print(f"\n✅ TEST PASSED: get_bloggers_by_keyword works correctly")
    return True


def test_get_bloggers_by_status():
    """Test filtering bloggers by status"""
    print("\n" + "=" * 70)
    print("  Test: Get Bloggers by Status")
    print("=" * 70)

    init_db()

    # Test with "scraped" status
    test_status = "scraped"
    print(f"\n📋 Testing with status: {test_status}")

    filtered_bloggers = BloggerDB.get_bloggers_by_status(test_status)

    print(f"✅ Found {len(filtered_bloggers)} bloggers with status '{test_status}'")

    # Verify all results have the correct status
    for blogger in filtered_bloggers:
        if blogger["status"] != test_status:
            print(f"❌ TEST FAILED: Blogger {blogger['nickname']} has status '{blogger['status']}', expected '{test_status}'")
            return False

    print(f"✅ All filtered bloggers have status '{test_status}'")

    print(f"\n✅ TEST PASSED: get_bloggers_by_status works correctly")
    return True


def test_delete_notes_by_user():
    """Test deleting all notes for a user"""
    print("\n" + "=" * 70)
    print("  Test: Delete Notes by User")
    print("=" * 70)

    init_db()

    # Create a test blogger
    test_user_id = "test_delete_notes_789"
    test_nickname = "测试删除笔记"

    print(f"\n📋 Creating test blogger: {test_nickname}")
    BloggerDB.insert_blogger(
        user_id=test_user_id,
        nickname=test_nickname,
        initial_fans=100,
        source_keyword="测试"
    )

    # Add some test notes
    print(f"📝 Adding test notes...")
    for i in range(5):
        NoteDB.insert_note(
            note_id=f"test_note_del_{i}",
            user_id=test_user_id,
            title=f"测试笔记 {i}",
            likes=100 * i,
            note_url=f"https://www.xiaohongshu.com/explore/test_note_del_{i}"
        )

    notes_before = NoteDB.count_notes_by_user(test_user_id)
    print(f"✅ Created {notes_before} test notes")

    # Delete all notes
    print(f"\n🗑️  Deleting all notes...")
    deleted_count = NoteDB.delete_notes_by_user(test_user_id)

    print(f"✅ Deleted {deleted_count} notes")

    # Verify notes are deleted
    notes_after = NoteDB.count_notes_by_user(test_user_id)
    if notes_after != 0:
        print(f"❌ TEST FAILED: {notes_after} notes still exist, expected 0")
        # Cleanup
        BloggerDB.delete_blogger(test_user_id)
        return False

    if deleted_count != notes_before:
        print(f"❌ TEST FAILED: Deleted {deleted_count} notes, expected {notes_before}")
        # Cleanup
        BloggerDB.delete_blogger(test_user_id)
        return False

    print(f"✅ All notes deleted correctly")

    # Cleanup
    BloggerDB.delete_blogger(test_user_id)

    print(f"\n✅ TEST PASSED: delete_notes_by_user works correctly")
    return True


def main():
    print("\n" + "=" * 70)
    print("  RedLens Cleanup Features Test Suite (功能2)")
    print("=" * 70)

    results = []

    # Test 1: Reset blogger status
    results.append(("Reset Blogger Status", test_reset_blogger_status()))

    # Test 2: Delete blogger
    results.append(("Delete Blogger", test_delete_blogger()))

    # Test 3: Get bloggers by keyword
    results.append(("Get Bloggers by Keyword", test_get_bloggers_by_keyword()))

    # Test 4: Get bloggers by status
    results.append(("Get Bloggers by Status", test_get_bloggers_by_status()))

    # Test 5: Delete notes by user
    results.append(("Delete Notes by User", test_delete_notes_by_user()))

    # Summary
    print("\n" + "=" * 70)
    print("  TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {status}: {test_name}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\n✅ 功能2验证完成：")
        print("  • 单个博主数据清空功能正常")
        print("  • 博主删除功能正常")
        print("  • 关键词筛选功能正常")
        print("  • 状态筛选功能正常")
        print("  • 笔记批量删除功能正常")
        print("\n📝 前端验证（手动测试）：")
        print("  1. 运行 streamlit run red_lens/app.py")
        print("  2. 进入「详细分析」tab，测试单个博主清空数据按钮")
        print("  3. 进入「博主管理」tab，测试筛选和批量删除功能")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
