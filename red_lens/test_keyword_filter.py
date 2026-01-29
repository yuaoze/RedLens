#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for keyword filtering in data collection (功能3)
"""

import sys
from pathlib import Path

MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.db import init_db, BloggerDB


def test_get_pending_bloggers_by_keyword():
    """Test getting pending bloggers filtered by keyword"""
    print("\n" + "=" * 70)
    print("  Test: Get Pending Bloggers by Keyword")
    print("=" * 70)

    init_db()

    # Get all pending bloggers to see available keywords
    all_pending = BloggerDB.get_pending_bloggers(limit=1000)

    if not all_pending:
        print("⚠️  No pending bloggers found. Cannot test keyword filtering.")
        print("   Please add some pending bloggers first using discovery module.")
        return False

    # Extract unique keywords
    keywords = set()
    for blogger in all_pending:
        if blogger.get("source_keyword"):
            keywords.add(blogger["source_keyword"])

    if not keywords:
        print("⚠️  No bloggers with keywords found.")
        return False

    print(f"\n📋 Found {len(all_pending)} pending bloggers")
    print(f"📋 Available keywords: {', '.join(sorted(keywords))}")

    # Test with the first keyword
    test_keyword = sorted(list(keywords))[0]
    print(f"\n🔍 Testing with keyword: {test_keyword}")

    # Get pending bloggers by keyword
    filtered_bloggers = BloggerDB.get_pending_bloggers_by_keyword(
        keyword=test_keyword,
        limit=10
    )

    print(f"✅ Found {len(filtered_bloggers)} pending bloggers with keyword '{test_keyword}'")

    # Verify all results contain the keyword and are pending
    for blogger in filtered_bloggers:
        if blogger["status"] != "pending":
            print(f"❌ TEST FAILED: Blogger {blogger['nickname']} has status '{blogger['status']}', expected 'pending'")
            return False

        if test_keyword not in (blogger.get("source_keyword") or ""):
            print(f"❌ TEST FAILED: Blogger {blogger['nickname']} doesn't have keyword '{test_keyword}'")
            return False

    print(f"✅ All filtered bloggers are pending and contain the keyword")

    # Show sample results
    if filtered_bloggers:
        print(f"\n📝 Sample pending bloggers with keyword '{test_keyword}':")
        for blogger in filtered_bloggers[:5]:
            print(f"  • {blogger['nickname']} ({blogger.get('source_keyword', 'N/A')})")

    print(f"\n✅ TEST PASSED: get_pending_bloggers_by_keyword works correctly")
    return True


def test_count_pending_by_keyword():
    """Test counting pending bloggers filtered by keyword"""
    print("\n" + "=" * 70)
    print("  Test: Count Pending Bloggers by Keyword")
    print("=" * 70)

    init_db()

    # Get all pending bloggers
    all_pending = BloggerDB.get_pending_bloggers(limit=1000)

    if not all_pending:
        print("⚠️  No pending bloggers found.")
        return False

    # Extract unique keywords
    keywords = set()
    for blogger in all_pending:
        if blogger.get("source_keyword"):
            keywords.add(blogger["source_keyword"])

    if not keywords:
        print("⚠️  No bloggers with keywords found.")
        return False

    # Test count for each keyword
    print(f"\n📊 Counting pending bloggers by keyword:")

    total_verified = 0
    for keyword in sorted(keywords):
        # Count using database function
        db_count = BloggerDB.count_pending_by_keyword(keyword)

        # Manually count for verification
        manual_count = sum(
            1 for b in all_pending
            if b["status"] == "pending" and keyword in (b.get("source_keyword") or "")
        )

        print(f"  • {keyword}: {db_count} 位 (manual: {manual_count})")

        if db_count != manual_count:
            print(f"❌ TEST FAILED: Count mismatch for keyword '{keyword}'")
            print(f"   Database count: {db_count}, Manual count: {manual_count}")
            return False

        total_verified += db_count

    print(f"\n✅ All counts verified correctly")
    print(f"✅ Total pending bloggers: {total_verified}")

    # Test count with None (all pending)
    all_count = BloggerDB.count_pending_by_keyword(None)
    total_pending = BloggerDB.count_by_status("pending")

    if all_count != total_pending:
        print(f"❌ TEST FAILED: count_pending_by_keyword(None) returned {all_count}, expected {total_pending}")
        return False

    print(f"✅ count_pending_by_keyword(None) = {all_count} matches total pending")

    print(f"\n✅ TEST PASSED: count_pending_by_keyword works correctly")
    return True


def test_no_results_for_nonexistent_keyword():
    """Test that nonexistent keyword returns empty list"""
    print("\n" + "=" * 70)
    print("  Test: No Results for Nonexistent Keyword")
    print("=" * 70)

    init_db()

    # Use a keyword that definitely doesn't exist
    fake_keyword = "这个关键词绝对不存在_xyz123"

    print(f"\n🔍 Testing with nonexistent keyword: {fake_keyword}")

    # Try to get bloggers with fake keyword
    results = BloggerDB.get_pending_bloggers_by_keyword(
        keyword=fake_keyword,
        limit=10
    )

    if len(results) != 0:
        print(f"❌ TEST FAILED: Expected 0 results, got {len(results)}")
        return False

    print(f"✅ Correctly returned 0 results for nonexistent keyword")

    # Test count
    count = BloggerDB.count_pending_by_keyword(fake_keyword)

    if count != 0:
        print(f"❌ TEST FAILED: Expected count 0, got {count}")
        return False

    print(f"✅ Correctly returned count 0 for nonexistent keyword")

    print(f"\n✅ TEST PASSED: Nonexistent keyword handling works correctly")
    return True


def test_limit_parameter():
    """Test that limit parameter works correctly"""
    print("\n" + "=" * 70)
    print("  Test: Limit Parameter")
    print("=" * 70)

    init_db()

    # Get all pending bloggers
    all_pending = BloggerDB.get_pending_bloggers(limit=1000)

    if len(all_pending) < 5:
        print("⚠️  Not enough pending bloggers to test limit parameter.")
        return False

    # Test different limits
    test_limits = [1, 3, 5, 10]

    print(f"\n📊 Testing limit parameter:")

    for limit in test_limits:
        results = BloggerDB.get_pending_bloggers_by_keyword(
            keyword=None,  # All pending
            limit=limit
        )

        expected_count = min(limit, len(all_pending))
        actual_count = len(results)

        print(f"  • limit={limit}: got {actual_count} results (expected {expected_count})")

        if actual_count != expected_count:
            print(f"❌ TEST FAILED: Limit not working correctly")
            return False

    print(f"\n✅ Limit parameter works correctly")

    print(f"\n✅ TEST PASSED: Limit parameter test passed")
    return True


def main():
    print("\n" + "=" * 70)
    print("  RedLens Keyword Filtering Test Suite (功能3)")
    print("=" * 70)

    results = []

    # Test 1: Get pending bloggers by keyword
    results.append(("Get Pending Bloggers by Keyword", test_get_pending_bloggers_by_keyword()))

    # Test 2: Count pending bloggers by keyword
    results.append(("Count Pending by Keyword", test_count_pending_by_keyword()))

    # Test 3: Nonexistent keyword
    results.append(("Nonexistent Keyword Handling", test_no_results_for_nonexistent_keyword()))

    # Test 4: Limit parameter
    results.append(("Limit Parameter", test_limit_parameter()))

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
        print("\n✅ 功能3验证完成：")
        print("  • 按关键词筛选pending博主功能正常")
        print("  • 按关键词计数功能正常")
        print("  • 不存在的关键词处理正常")
        print("  • Limit参数功能正常")
        print("\n📝 前端验证（手动测试）：")
        print("  1. 运行 streamlit run red_lens/app.py")
        print("  2. 在侧边栏「数据采集」部分查看关键词筛选下拉框")
        print("  3. 选择不同关键词，查看待采集博主数量是否正确变化")
        print("  4. 开始采集，验证是否只采集了选中关键词的博主")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
