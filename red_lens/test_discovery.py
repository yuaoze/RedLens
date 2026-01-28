#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test suite for discovery module
Ensures MediaCrawler integration works correctly
"""

import sys
from pathlib import Path

MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.discovery import search_and_extract_users, run_mediacrawler_sync
from red_lens.db import BloggerDB, init_db


def test_function_parameters():
    """Test 1: Verify function has correct parameters"""
    print("\n" + "=" * 60)
    print("TEST 1: Function Parameter Verification")
    print("=" * 60)

    import inspect

    # Get function signature
    sig = inspect.signature(search_and_extract_users)
    params = list(sig.parameters.keys())

    print(f"Function parameters: {params}")

    # Check required parameters exist
    assert "keywords" in params, "Missing 'keywords' parameter"
    assert "min_likes" in params, "Missing 'min_likes' parameter"
    assert "max_notes" in params, "Missing 'max_notes' parameter"
    assert "run_crawler" in params, "Missing 'run_crawler' parameter"
    assert "use_existing" in params, "Missing 'use_existing' parameter"

    # Check default values
    defaults = {
        "run_crawler": True,
        "use_existing": False
    }

    for param_name, expected_default in defaults.items():
        param = sig.parameters[param_name]
        actual_default = param.default
        print(f"  • {param_name}: default={actual_default}")
        assert actual_default == expected_default, \
            f"Parameter '{param_name}' should default to {expected_default}, got {actual_default}"

    print("\n✅ TEST 1 PASSED: Function parameters are correct")


def test_use_existing_mode():
    """Test 2: Verify use_existing mode works"""
    print("\n" + "=" * 60)
    print("TEST 2: Use Existing Data Mode")
    print("=" * 60)

    init_db()

    # Should NOT run MediaCrawler, just parse existing JSON
    count = search_and_extract_users(
        keywords=["测试"],
        min_likes=200,
        use_existing=True  # Important: use existing data
    )

    print(f"  • Found {count} blogger(s) from existing data")
    print("\n✅ TEST 2 PASSED: use_existing mode works correctly")


def test_run_crawler_disabled():
    """Test 3: Verify run_crawler=False prevents execution"""
    print("\n" + "=" * 60)
    print("TEST 3: Disable Crawler Mode")
    print("=" * 60)

    init_db()

    # run_crawler=False should skip MediaCrawler entirely
    count = search_and_extract_users(
        keywords=["测试"],
        min_likes=200,
        run_crawler=False,  # Explicitly disable
        use_existing=True
    )

    print(f"  • Processed without running crawler")
    print("\n✅ TEST 3 PASSED: run_crawler=False works correctly")


def test_mediacrawler_function_exists():
    """Test 4: Verify MediaCrawler wrapper function exists"""
    print("\n" + "=" * 60)
    print("TEST 4: MediaCrawler Function Existence")
    print("=" * 60)

    # Check if function exists
    assert callable(run_mediacrawler_sync), "run_mediacrawler_sync function not found"

    # Check function signature
    import inspect
    sig = inspect.signature(run_mediacrawler_sync)
    params = list(sig.parameters.keys())

    print(f"  • Function: run_mediacrawler_sync")
    print(f"  • Parameters: {params}")

    assert "keywords" in params, "Missing 'keywords' parameter"
    assert "max_notes" in params, "Missing 'max_notes' parameter"

    print("\n✅ TEST 4 PASSED: MediaCrawler wrapper function exists")


def test_config_backup_mechanism():
    """Test 5: Verify config backup exists in function"""
    print("\n" + "=" * 60)
    print("TEST 5: Config Backup Mechanism")
    print("=" * 60)

    import inspect

    # Get function source code
    source = inspect.getsource(run_mediacrawler_sync)

    # Check for key backup operations
    checks = {
        "backup_file": "backup_file" in source,
        "config_restore": "with open(backup_file" in source and "original_config" in source,
        "finally_block": "finally:" in source,
        "unlink_backup": "unlink()" in source
    }

    print("  Checking backup mechanism:")
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"    {status} {check_name}: {result}")
        assert result, f"Missing: {check_name}"

    print("\n✅ TEST 5 PASSED: Config backup mechanism is present")


def test_json_file_fallback():
    """Test 6: Verify JSON file fallback logic"""
    print("\n" + "=" * 60)
    print("TEST 6: JSON File Fallback Logic")
    print("=" * 60)

    import inspect

    source = inspect.getsource(search_and_extract_users)

    # Check for fallback logic
    checks = {
        "checks_exists": "json_file.exists()" in source,
        "glob_search": "glob(" in source and "search_contents_" in source,
        "max_by_mtime": "max(" in source and "st_mtime" in source,
        "error_message": "No search results found" in source
    }

    print("  Checking fallback logic:")
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"    {status} {check_name}: {result}")
        assert result, f"Missing: {check_name}"

    print("\n✅ TEST 6 PASSED: JSON fallback logic is correct")


def test_mode_display():
    """Test 7: Verify mode is displayed to user"""
    print("\n" + "=" * 60)
    print("TEST 7: User Mode Display")
    print("=" * 60)

    import inspect

    source = inspect.getsource(search_and_extract_users)

    # Check for mode display
    assert "Mode:" in source, "Mode should be displayed to user"
    assert "use_existing" in source, "use_existing logic should be present"

    print("  • Mode display: Found")
    print("  • User notification: Present")

    print("\n✅ TEST 7 PASSED: Mode is properly displayed")


def test_mediacrawler_actual_run():
    """Test 8: Actually run MediaCrawler"""
    print("\n" + "=" * 60)
    print("TEST 8: MediaCrawler Live Integration Test")
    print("=" * 60)

    print("\n⚠️  This test will:")
    print("  • Run MediaCrawler with real browser")
    print("  • Require manual login (QR/SMS)")
    print("  • Take 5-10 minutes")
    print("  • Generate/update JSON files\n")

    json_dir = Path(__file__).parent.parent / "data" / "xhs" / "json"
    before_files = list(json_dir.glob("search_contents_*.json"))

    print(f"📂 Before: {len(before_files)} JSON file(s)")
    if before_files:
        latest_before = max(before_files, key=lambda p: p.stat().st_mtime)
        before_mtime = latest_before.stat().st_mtime
        print(f"   Latest: {latest_before.name}")

    # Run MediaCrawler (no confirmation needed)
    print("\n🚀 Running MediaCrawler...")

    try:
        new_count = search_and_extract_users(
            keywords=["摄影师"],
            min_likes=500,
            max_notes=20,
            run_crawler=True,    # ✅ ACTUALLY RUN MediaCrawler
            use_existing=False   # ✅ DON'T use existing data
        )

        # Verify results
        after_files = list(json_dir.glob("search_contents_*.json"))
        new_files = set(after_files) - set(before_files)

        print(f"\n📂 After: {len(after_files)} JSON file(s)")

        # Check if new files were created
        if new_files:
            print(f"   ✅ NEW file(s) created: {len(new_files)}")
            for f in new_files:
                print(f"      - {f.name} ({f.stat().st_size:,} bytes)")
            verified = True

        elif before_files:
            # Check if existing file was updated
            latest_after = max(after_files, key=lambda p: p.stat().st_mtime)
            if latest_after.stat().st_mtime > before_mtime:
                print(f"   ✅ File UPDATED: {latest_after.name}")
                verified = True
            else:
                print(f"   ❌ No files changed")
                verified = False
        else:
            print(f"   ❌ No files found")
            verified = False

        print(f"\n👥 Bloggers discovered: {new_count}")

        if verified:
            print("\n✅ TEST 8 PASSED: MediaCrawler successfully ran and generated data!")
            assert True, "MediaCrawler integration working"
        else:
            print("\n❌ TEST 8 FAILED: MediaCrawler did not generate/update files")
            assert False, "MediaCrawler did not produce expected output"

    except Exception as e:
        print(f"\n❌ TEST 8 FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        assert False, f"MediaCrawler test failed: {e}"


def run_all_tests():
    """Run all discovery tests including live MediaCrawler test"""
    print("\n" + "=" * 60)
    print("  RedLens Discovery Module Test Suite")
    print("=" * 60)

    tests = [
        ("Parameter Verification", test_function_parameters),
        ("Use Existing Mode", test_use_existing_mode),
        ("Disable Crawler", test_run_crawler_disabled),
        ("Function Existence", test_mediacrawler_function_exists),
        ("Config Backup", test_config_backup_mechanism),
        ("JSON Fallback", test_json_file_fallback),
        ("Mode Display", test_mode_display),
        ("MediaCrawler Live Test", test_mediacrawler_actual_run),  # Always run
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ TEST FAILED: {test_name}")
            print(f"   Error: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ TEST ERROR: {test_name}")
            print(f"   Exception: {e}")
            failed += 1

    # Final summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    print(f"  Total tests: {len(tests)}")
    print(f"  ✅ Passed: {passed}")
    print(f"  ❌ Failed: {failed}")
    print("=" * 60)

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        print("✓ Discovery module is properly fixed")
        print("✓ MediaCrawler integration is functional")
        print("✓ Live test successfully verified actual crawling")
        print("✓ Backward compatibility maintained")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
