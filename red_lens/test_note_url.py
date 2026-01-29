#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for note_url feature
"""

import sys
from pathlib import Path

MEDIA_CRAWLER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MEDIA_CRAWLER_ROOT))

from red_lens.db import init_db, NoteDB
from red_lens.pipeline import clean_note_data


def test_note_url_construction():
    """Test that note_url is correctly constructed from note_id"""
    print("\n" + "=" * 70)
    print("  Test: note_url Construction")
    print("=" * 70)

    # Test data (simulating MediaCrawler JSON output)
    raw_note = {
        "note_id": "675003000000000002018d8d",
        "user_id": "test_user_123",
        "title": "测试笔记标题",
        "desc": "测试描述",
        "type": "normal",
        "liked_count": "1000",
        "collected_count": "200",
        "comment_count": "50",
        "time": 1640000000000,
        "image_list": "http://example.com/image.jpg"
    }

    print(f"\n📋 Raw note data:")
    print(f"  note_id: {raw_note['note_id']}")
    print(f"  title: {raw_note['title']}")

    # Clean note data
    cleaned_note = clean_note_data(raw_note)

    print(f"\n✅ Cleaned note data:")
    print(f"  note_id: {cleaned_note['note_id']}")
    print(f"  title: {cleaned_note['title']}")
    print(f"  note_url: {cleaned_note.get('note_url', 'MISSING!')}")

    # Verify note_url is constructed correctly
    expected_url = f"https://www.xiaohongshu.com/explore/{raw_note['note_id']}"
    actual_url = cleaned_note.get('note_url', '')

    if actual_url == expected_url:
        print(f"\n✅ TEST PASSED: note_url correctly constructed")
        print(f"  Expected: {expected_url}")
        print(f"  Actual: {actual_url}")
        return True
    else:
        print(f"\n❌ TEST FAILED: note_url mismatch")
        print(f"  Expected: {expected_url}")
        print(f"  Actual: {actual_url}")
        return False


def test_database_note_url():
    """Test that note_url is saved to database"""
    print("\n" + "=" * 70)
    print("  Test: note_url Database Storage")
    print("=" * 70)

    init_db()

    # Insert a test note with note_url
    test_note_id = "test_note_url_feature"
    test_user_id = "test_user_123"
    test_url = "https://www.xiaohongshu.com/explore/test_note_url_feature"

    success = NoteDB.insert_note(
        note_id=test_note_id,
        user_id=test_user_id,
        title="测试笔记URL功能",
        desc="这是一个测试",
        note_type="image",
        likes=100,
        collects=20,
        comments=5,
        note_url=test_url
    )

    if not success:
        print("❌ Failed to insert note")
        return False

    print(f"✅ Inserted test note with ID: {test_note_id}")

    # Retrieve the note and check note_url
    retrieved_note = NoteDB.get_note(test_note_id)

    if not retrieved_note:
        print("❌ Failed to retrieve note")
        return False

    print(f"\n📄 Retrieved note:")
    print(f"  note_id: {retrieved_note['note_id']}")
    print(f"  title: {retrieved_note['title']}")
    print(f"  note_url: {retrieved_note.get('note_url', 'MISSING!')}")

    if retrieved_note.get('note_url') == test_url:
        print(f"\n✅ TEST PASSED: note_url correctly saved to database")
        return True
    else:
        print(f"\n❌ TEST FAILED: note_url not saved correctly")
        print(f"  Expected: {test_url}")
        print(f"  Actual: {retrieved_note.get('note_url', 'NULL')}")
        return False


def test_existing_notes_update():
    """Test updating existing notes to add note_url"""
    print("\n" + "=" * 70)
    print("  Test: Updating Existing Notes with note_url")
    print("=" * 70)

    # Get a few existing notes without note_url
    import sqlite3
    from red_lens.db import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT note_id, title, note_url FROM notes WHERE note_url IS NULL OR note_url = '' LIMIT 3")
    notes = [dict(row) for row in cursor.fetchall()]

    if not notes:
        print("ℹ️  No notes without note_url found (all notes already have URLs)")
        conn.close()
        return True

    print(f"\n📋 Found {len(notes)} notes without note_url:")
    for note in notes:
        print(f"  • {note['note_id'][:16]}... - {note['title'][:40]}...")

    # Update these notes to add note_url
    updated_count = 0
    for note in notes:
        note_id = note['note_id']
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"

        cursor.execute("UPDATE notes SET note_url = ? WHERE note_id = ?", (note_url, note_id))
        updated_count += 1

    conn.commit()
    conn.close()

    print(f"\n✅ Updated {updated_count} notes with note_url")

    # Verify update
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT note_id, note_url FROM notes WHERE note_id = ?", (notes[0]['note_id'],))
    updated_note = dict(cursor.fetchone())
    conn.close()

    expected_url = f"https://www.xiaohongshu.com/explore/{notes[0]['note_id']}"
    if updated_note['note_url'] == expected_url:
        print(f"✅ TEST PASSED: Existing notes updated correctly")
        print(f"  Sample URL: {updated_note['note_url']}")
        return True
    else:
        print(f"❌ TEST FAILED: Update verification failed")
        return False


def main():
    print("\n" + "=" * 70)
    print("  RedLens Note URL Feature Test Suite")
    print("=" * 70)

    results = []

    # Test 1: note_url construction
    results.append(("note_url Construction", test_note_url_construction()))

    # Test 2: Database storage
    results.append(("Database Storage", test_database_note_url()))

    # Test 3: Update existing notes
    results.append(("Update Existing Notes", test_existing_notes_update()))

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
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
