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


def refresh_note_cover_urls(note_ids: List[str]) -> Dict[str, Any]:
    """
    刷新指定笔记的封面URL

    专门用于更新封面URL（临时链接会失效），使用XHS_SPECIFIED_NOTE_URL_LIST精准爬取
    不会触发智能过滤，因为目的是更新而非采集新笔记

    Args:
        note_ids: 笔记ID列表

    Returns:
        统计信息: {"success": bool, "updated": int, "failed": int}
    """
    init_db()

    print(f"\n{'='*60}")
    print(f"刷新笔记封面URL (精准爬取模式)")
    print(f"{'='*60}")

    # 1. 从数据库获取指定笔记
    target_notes = []
    not_found_ids = []

    for note_id in note_ids:
        note = NoteDB.get_note(note_id)
        if note:
            target_notes.append(note)
        else:
            not_found_ids.append(note_id)
            print(f"  ⚠️ 笔记 {note_id} 未在数据库中找到")

    if not target_notes:
        print(f"✗ 未找到任何有效笔记")
        return {"success": False, "updated": 0, "failed": len(note_ids)}

    print(f"📋 需要刷新 {len(target_notes)} 条笔记的封面URL")
    if not_found_ids:
        print(f"  ⚠️ 跳过 {len(not_found_ids)} 条未找到的笔记")

    # 2. 构建笔记URL列表（使用数据库中的note_url字段）
    note_urls = []
    for note in target_notes:
        # 优先使用数据库中的note_url
        if note.get('note_url'):
            note_urls.append(note['note_url'])
        else:
            # 如果没有note_url，则构建URL（向后兼容）
            note_id = note['note_id']
            note_urls.append(f"https://www.xiaohongshu.com/explore/{note_id}")
            print(f"  ⚠️ 笔记 {note_id} 缺少note_url，使用默认格式")

    print(f"📝 已收集 {len(note_urls)} 个笔记URL")

    # 3. 使用MediaCrawler的detail模式爬取指定笔记
    print(f"\n🚀 启动MediaCrawler (detail模式，精准爬取 {len(note_urls)} 条笔记)...")

    success = _run_mediacrawler_for_specified_notes(note_urls)

    if not success:
        print(f"✗ MediaCrawler爬取失败")
        return {"success": False, "updated": 0, "failed": len(note_ids)}

    # 4. 加载爬取结果并更新数据库
    print(f"\n💾 更新数据库中的封面URL...")

    json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"

    # 查找最新的detail文件（detail模式的输出文件）
    detail_files = list(json_dir.glob("detail_contents_*.json"))
    if not detail_files:
        print(f"✗ 未找到爬取结果文件")
        print(f"  提示: 查找路径 {json_dir}")
        print(f"  期望文件: detail_contents_YYYY-MM-DD.json")
        return {"success": False, "updated": 0, "failed": len(note_ids)}

    latest_file = max(detail_files, key=lambda p: p.stat().st_mtime)
    print(f"📂 加载: {latest_file.name}")

    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            notes_data = json.load(f)
    except Exception as e:
        print(f"✗ 读取文件失败: {e}")
        return {"success": False, "updated": 0, "failed": 0}

    # 5. 更新数据库中的cover_url
    # 建立目标笔记ID集合，用于快速查找
    target_note_ids = {note['note_id'] for note in target_notes}

    updated_count = 0
    failed_count = 0

    for note_data in notes_data:
        note_id = note_data.get('note_id')
        if not note_id or note_id not in target_note_ids:
            continue

        # 获取新的封面URL
        image_list = note_data.get('image_list', '')
        new_cover_url = image_list.split(',')[0] if image_list else ''

        if not new_cover_url:
            print(f"  ⚠ {note_id}: 未找到封面URL")
            failed_count += 1
            continue

        # 更新数据库
        try:
            NoteDB.update_cover_url(note_id, new_cover_url)
            print(f"  ✓ {note_id}: 封面URL已更新")
            updated_count += 1
        except Exception as e:
            print(f"  ✗ {note_id}: 更新失败 - {e}")
            failed_count += 1

    print(f"\n{'='*60}")
    print(f"刷新完成")
    print(f"{'='*60}")
    print(f"✓ 成功更新: {updated_count} 条")
    if failed_count > 0:
        print(f"✗ 失败: {failed_count} 条")
    print(f"{'='*60}\n")

    return {
        "success": updated_count > 0,
        "updated": updated_count,
        "failed": failed_count
    }


def _run_mediacrawler_for_specified_notes(note_urls: List[str]) -> bool:
    """
    运行MediaCrawler爬取指定的笔记列表（使用detail模式 + XHS_SPECIFIED_NOTE_URL_LIST）

    Args:
        note_urls: 笔记URL列表

    Returns:
        True if successful, False otherwise
    """
    print(f"\n🔍 配置MediaCrawler爬取 {len(note_urls)} 条指定笔记")

    # 准备配置文件
    base_config_file = MEDIA_CRAWLER_ROOT / "config" / "base_config.py"
    xhs_config_file = MEDIA_CRAWLER_ROOT / "config" / "xhs_config.py"

    # 读取配置
    with open(base_config_file, 'r', encoding='utf-8') as f:
        base_config_content = f.read()
    with open(xhs_config_file, 'r', encoding='utf-8') as f:
        xhs_config_content = f.read()

    # 备份配置
    base_backup = base_config_file.parent / "base_config.py.refresh_backup"
    xhs_backup = xhs_config_file.parent / "xhs_config.py.refresh_backup"

    with open(base_backup, 'w', encoding='utf-8') as f:
        f.write(base_config_content)
    with open(xhs_backup, 'w', encoding='utf-8') as f:
        f.write(xhs_config_content)

    try:
        import subprocess

        # 修改base_config: 设置为detail模式
        base_config_content = re.sub(
            r'CRAWLER_TYPE\s*=\s*\(.*?\n\)',
            'CRAWLER_TYPE = "detail"',
            base_config_content,
            flags=re.DOTALL
        )
        base_config_content = re.sub(
            r'CRAWLER_TYPE\s*=\s*"[^"]*"',
            'CRAWLER_TYPE = "detail"',
            base_config_content
        )

        # 禁用评论爬取
        base_config_content = re.sub(
            r'ENABLE_GET_COMMENTS\s*=\s*(True|False)',
            'ENABLE_GET_COMMENTS = False',
            base_config_content
        )

        # 保存修改后的base_config
        with open(base_config_file, 'w', encoding='utf-8') as f:
            f.write(base_config_content)

        # 修改xhs_config: 设置XHS_SPECIFIED_NOTE_URL_LIST
        url_list_str = ", ".join([f'"{url}"' for url in note_urls])

        xhs_config_content = re.sub(
            r'XHS_SPECIFIED_NOTE_URL_LIST\s*=\s*\[.*?\]',
            f'XHS_SPECIFIED_NOTE_URL_LIST = [{url_list_str}]',
            xhs_config_content,
            flags=re.DOTALL
        )

        # 保存修改后的xhs_config
        with open(xhs_config_file, 'w', encoding='utf-8') as f:
            f.write(xhs_config_content)

        print(f"  ✓ 配置已更新:")
        print(f"    • note模式")
        print(f"    • {len(note_urls)} 条指定笔记")
        print(f"    • 评论=禁用")

        # 运行MediaCrawler
        print(f"\n  🚀 启动MediaCrawler...")

        # 计算超时时间（每条笔记约4秒 + 60秒启动时间）
        timeout_seconds = len(note_urls) * 4 + 60
        timeout_seconds = max(120, min(timeout_seconds, 600))  # 最少2分钟，最多10分钟

        print(f"  ⏱️  预计时间: {len(note_urls) * 4}s, 超时: {timeout_seconds}s")

        # 检查uv
        try:
            uv_check = subprocess.run(["uv", "--version"], capture_output=True)
            use_uv = (uv_check.returncode == 0)
        except FileNotFoundError:
            use_uv = False

        if use_uv:
            cmd = ["uv", "run", "main.py", "--platform", "xhs", "--lt", "qrcode", "--type", "detail"]
        else:
            cmd = [sys.executable, "main.py"]

        print(f"\n{'='*60}")
        print(f"MediaCrawler Output:")
        print(f"{'='*60}\n")

        # 运行
        process = subprocess.Popen(
            cmd,
            cwd=MEDIA_CRAWLER_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        output_lines = []
        try:
            for line in process.stdout:
                print(line, end='')
                output_lines.append(line)

            return_code = process.wait(timeout=timeout_seconds)

        except subprocess.TimeoutExpired:
            print(f"\n⚠️  超时 ({timeout_seconds}s)")
            process.kill()
            return_code = -1
        except Exception as e:
            print(f"\n✗ 执行错误: {e}")
            process.kill()
            return_code = -1

        print(f"\n{'='*60}")
        print(f"MediaCrawler 完成")
        print(f"{'='*60}\n")

        if return_code == 0:
            print(f"  ✓ 爬取成功")
            return True
        else:
            print(f"  ✗ 爬取失败 (返回码: {return_code})")
            if output_lines:
                print(f"\n  ❌ 最后20行输出:")
                for line in output_lines[-20:]:
                    print(f"    {line}", end='')
            return False

    except Exception as e:
        print(f"  ✗ 运行MediaCrawler失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # 恢复配置
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

        print(f"  ✓ 配置已恢复")


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

        # Read fans from the generated creator JSON files
        # Note: MediaCrawler generates new files on each run, and we need to search all files
        # because the target user_ids might be in different files from different batches
        json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"
        creator_files = list(json_dir.glob("creator_creators_*.json"))

        if not creator_files:
            print(f"    ✗ No creator JSON file found")
            return {uid: 0 for uid in user_ids}

        # Search all recent creator files for the requested user_ids
        # Sort by modification time (most recent first)
        creator_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        found_count = 0
        remaining_ids = set(user_ids)

        for json_file in creator_files:
            if not remaining_ids:
                break  # All users found

            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    creators = json.load(f)

                # Build dictionary of user_id -> fans from this file
                for creator in creators:
                    user_id = creator.get("user_id")
                    if user_id in remaining_ids:
                        fans_raw = creator.get("fans", 0)
                        fans = int(fans_raw) if fans_raw else 0
                        result[user_id] = fans
                        remaining_ids.remove(user_id)
                        found_count += 1
                        print(f"      ✓ {creator.get('nickname', 'Unknown')}: {fans:,} fans (from {json_file.name})")

            except Exception as e:
                print(f"      ⚠ Warning: Failed to read {json_file.name}: {e}")
                continue

        # Fallback: Try to search in creator_contents files for missing users
        if remaining_ids:
            print(f"      ℹ️  Some user_ids not found in creator_creators files, checking creator_contents...")
            content_files = list(json_dir.glob("creator_contents_*.json"))
            content_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Create a mapping from content files (content files don't have fans count)
            # We'll just record that the user exists but fans=0 (cannot get fans from content files)
            for json_file in content_files:
                if not remaining_ids:
                    break

                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        contents = json.load(f)

                    for content in contents:
                        user_id = content.get("user_id")
                        if user_id in remaining_ids:
                            result[user_id] = 0  # Can't get fans from content file
                            remaining_ids.remove(user_id)
                            print(f"      ⚠ {content.get('nickname', 'Unknown')}: found in content file but fans count not available (from {json_file.name})")
                except Exception as e:
                    continue

        # Final check: If MediaCrawler just ran but creator_creators file is empty/invalid, this indicates
        # a problem with MediaCrawler's get_creator_info function (HTML parsing failure)
        if remaining_ids and len(creator_files) > 0:
            # Check if the most recent creator_creators file is very recent (last 5 minutes)
            latest_creator_file = creator_files[0]
            file_age_seconds = (datetime.now().timestamp() - latest_creator_file.stat().st_mtime)
            if file_age_seconds < 60:
                print(f"      ⚠️  Warning: Latest creator_creators file exists but doesn't contain requested user_ids.")
                print(f"      ⚠️  This typically means MediaCrawler's get_creator_info() failed to parse HTML.")
                print(f"      ⚠️  The bloggers exist but their fans count cannot be retrieved without a working creator info fetch.")

        # Fill in missing users with 0
        for uid in user_ids:
            if uid not in result:
                result[uid] = 0
                print(f"      ✗ User {uid[:12]}... not found in any JSON file")

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
    batch_size: int = 5,
    source_keyword: Optional[str] = None
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
        source_keyword: Source keyword filter - only scrape bloggers matching this keyword (default: None = all keywords)

    Returns:
        Dictionary with statistics (scraped, failed, notes_added, skipped_low_fans, resumed)
    """
    init_db()

    print(f"\n{'='*60}")
    print(f"RedLens Deep Scraping Pipeline v1.2.0")
    print(f"{'='*60}")
    print(f"Mode: {'Using existing data' if use_existing_data else 'Running MediaCrawler'}")
    print(f"Max bloggers to scrape: {limit}")
    if source_keyword:
        print(f"Source keyword filter: {source_keyword}")
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

    # Filter by source_keyword if specified
    if source_keyword:
        print(f"\n{'='*60}")
        print(f"Filtering by source keyword: {source_keyword}")
        print(f"{'='*60}\n")

        # Get all pending bloggers by keyword (with higher limit to ensure we find enough)
        all_pending_by_keyword = BloggerDB.get_pending_bloggers_by_keyword(source_keyword, limit=1000)

        # Get resumable bloggers by keyword
        all_resumable_by_keyword = []
        if resume_partial and resumable_count > 0:
            all_resumable = BloggerDB.get_resumable_bloggers(limit=1000)
            all_resumable_by_keyword = [
                b for b in all_resumable
                if b.get('source_keyword', '').find(source_keyword) != -1
            ]

        # Mix resumable and pending bloggers that match the keyword
        keyword_matched = all_pending_by_keyword + all_resumable_by_keyword

        # Remove duplicates by user_id
        seen_ids = set()
        keyword_matchers = []
        for b in keyword_matched:
            if b['user_id'] not in seen_ids:
                seen_ids.add(b['user_id'])
                keyword_matchers.append(b)

        # Limit to requested number
        target_bloggers = keyword_matchers[:limit]

        print(f"  Found {len(keyword_matchers)} blogger(s) matching keyword '{source_keyword}'")
        print(f"  Limited to {len(target_bloggers)} blogger(s) for scraping")

        if not target_bloggers:
            print("✓ No bloggers match the specified keyword")
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
            # As long as MediaCrawler succeeded, mark as completed
            BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'completed')
            BloggerDB.update_status(user_id, "scraped")
            print(f"  ✓ Status: completed (collected {total_collected} notes)")
            stats["scraped"] += 1

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
                    scrape_status='failed',
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
            # As long as MediaCrawler succeeded, mark as completed
            BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'completed')
            BloggerDB.update_status(user_id, "scraped")
            print(f"  ✓ Status: completed (collected {total_collected} notes)")
            stats["scraped"] += 1

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

    # Auto-download covers for successfully scraped bloggers
    if stats['scraped'] > 0:
        print(f"\n{'='*60}")
        print("📥 Auto-downloading note covers")
        print(f"{'='*60}\n")

        from red_lens.analyzer import download_note_covers

        covers_stats = {
            'success': 0,
            'failed': 0,
            'total_top': 0,
            'total_bottom': 0
        }

        for blogger in qualified_bloggers:
            user_id = blogger['user_id']
            nickname = blogger['nickname']

            # Only download for successfully scraped bloggers
            progress = BloggerDB.get_scrape_progress(user_id)
            if progress['scrape_status'] != 'completed':
                continue

            try:
                print(f"📥 Downloading covers for: {nickname}")

                # Get top 10 + bottom 5 note IDs for this blogger
                notes = NoteDB.get_notes_by_user(user_id)
                if not notes:
                    print(f"  ⚠ No notes found for {nickname}")
                    continue

                sorted_notes = sorted(notes, key=lambda x: x['likes'], reverse=True)
                top_10 = sorted_notes[:10]
                bottom_5 = sorted_notes[-5:] if len(sorted_notes) > 5 else []
                note_ids_to_download = [n['note_id'] for n in top_10 + bottom_5]

                result = download_note_covers(note_ids_to_download, force_redownload=False)
                print(f"  ✓ Downloaded: {result['downloaded']}, Skipped: {result['skipped']}, Failed: {result['failed']}")

                covers_stats['success'] += 1
                covers_stats['total_top'] += result['downloaded']
                covers_stats['total_bottom'] += result['skipped']

                if result['failed'] > 0:
                    print(f"  ⚠ Failed: {result['failed']} covers")

            except Exception as e:
                print(f"  ✗ Failed to download covers: {e}")
                covers_stats['failed'] += 1

        print(f"\n{'='*60}")
        print("Cover Download Summary")
        print(f"{'='*60}")
        print(f"✓ Bloggers processed: {covers_stats['success']}")
        print(f"✓ Total Top covers: {covers_stats['total_top']}")
        print(f"✓ Total Bottom covers: {covers_stats['total_bottom']}")
        if covers_stats['failed'] > 0:
            print(f"✗ Failed: {covers_stats['failed']}")
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
    batch_size: int = 5,
    auto_download_covers: bool = True
) -> Dict[str, int]:
    """
    为指定的博主列表采集笔记（带智能过滤，排除已采集笔记）

    专门用于恢复采集模式，只采集缺失的笔记，避免重复采集

    Args:
        user_ids: 要采集的博主 ID 列表
        max_notes: 每个博主的目标笔记数量（默认: 100）
        batch_size: 批处理大小（默认: 5）
        auto_download_covers: 是否自动下载封面（默认: True）

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
        # Mark all as failed
        for blogger in target_bloggers:
            progress = BloggerDB.get_scrape_progress(blogger['user_id'])
            BloggerDB.update_scrape_progress(
                user_id=blogger["user_id"],
                notes_collected=progress['notes_collected'],
                notes_target=max_notes,
                scrape_status='failed',
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
        # As long as MediaCrawler succeeded, mark as completed
        BloggerDB.update_scrape_progress(user_id, total_collected, max_notes, 'completed')
        BloggerDB.update_status(user_id, "scraped")
        print(f"  ✓ Status: completed (collected {total_collected} notes)")
        stats["scraped"] += 1

        stats["notes_added"] += notes_added

    print(f"\n{'='*60}")
    print(f"✓ Scraping completed!")
    print(f"  Bloggers processed: {len(target_bloggers)}")
    print(f"  Successfully completed: {stats['scraped']}")
    print(f"  Failed/Partial: {stats['failed']}")
    print(f"  Total new notes added: {stats['notes_added']}")
    print(f"{'='*60}\n")

    # Auto-download covers for successfully scraped bloggers
    if auto_download_covers and stats['scraped'] > 0:
        print(f"\n{'='*60}")
        print("📥 Auto-downloading note covers")
        print(f"{'='*60}\n")

        from red_lens.analyzer import download_note_covers

        covers_stats = {
            'success': 0,
            'failed': 0,
            'total_top': 0,
            'total_bottom': 0
        }

        for blogger in target_bloggers:
            user_id = blogger['user_id']
            nickname = blogger['nickname']

            # Only download for successfully scraped bloggers
            progress = BloggerDB.get_scrape_progress(user_id)
            if progress['scrape_status'] != 'completed':
                continue

            try:
                print(f"📥 Downloading covers for: {nickname}")

                # Get top 10 + bottom 5 note IDs for this blogger
                notes = NoteDB.get_notes_by_user(user_id)
                if not notes:
                    print(f"  ⚠ No notes found for {nickname}")
                    continue

                sorted_notes = sorted(notes, key=lambda x: x['likes'], reverse=True)
                top_10 = sorted_notes[:10]
                bottom_5 = sorted_notes[-5:] if len(sorted_notes) > 5 else []
                note_ids_to_download = [n['note_id'] for n in top_10 + bottom_5]

                result = download_note_covers(note_ids_to_download, force_redownload=False)
                print(f"  ✓ Downloaded: {result['downloaded']}, Skipped: {result['skipped']}, Failed: {result['failed']}")

                covers_stats['success'] += 1
                covers_stats['total_top'] += result['downloaded']
                covers_stats['total_bottom'] += result['skipped']

                if result['failed'] > 0:
                    print(f"  ⚠ Failed: {result['failed']} covers")

            except Exception as e:
                print(f"  ✗ Failed to download covers: {e}")
                covers_stats['failed'] += 1

        print(f"\n{'='*60}")
        print("Cover Download Summary")
        print(f"{'='*60}")
        print(f"✓ Bloggers processed: {covers_stats['success']}")
        print(f"✓ Total Top covers: {covers_stats['total_top']}")
        print(f"✓ Total Bottom covers: {covers_stats['total_bottom']}")
        if covers_stats['failed'] > 0:
            print(f"✗ Failed: {covers_stats['failed']}")
        print(f"{'='*60}\n")

    return stats


def collect_blogger_by_manual_id(
    user_id: str,
    max_notes: int = 100,
    add_to_db: bool = True,
    nickname: str = None
) -> Dict[str, any]:
    """
    手动采集指定博主ID的笔记

    Args:
        user_id: 小红书博主ID
        max_notes: 最多采集笔记数量
        add_to_db: 是否添加博主到数据库
        nickname: 博主昵称（可选，实际使用会从MediaCrawler数据获取）

    Returns:
        Dict with collection stats:
        {
            "success": bool,
            "user_id": str,
            "notes_count": int,
            "error": str (if failed)
        }
    """
    print(f"\n{'='*60}")
    print(f"📝 Manual Collection for Blogger ID: {user_id}")
    print(f"{'='*60}\n")

    try:
        # Step 1: Run MediaCrawler FIRST to get blogger info and notes
        print(f"🚀 Starting MediaCrawler to fetch blogger data...")
        print(f"   Collection mode: creator")
        print(f"   Max notes: {max_notes}")

        success = run_mediacrawler_for_creator(user_id, max_notes)

        if not success:
            error_msg = "MediaCrawler execution failed"
            print(f"   ❌ {error_msg}")
            return {
                "success": False,
                "user_id": user_id,
                "notes_count": 0,
                "error": error_msg
            }

        print(f"   ✓ MediaCrawler completed successfully")

        # Step 2: Load blogger info from creator_creators.json
        print(f"📚 Loading blogger info from MediaCrawler output...")
        json_dir = MEDIA_CRAWLER_ROOT / "data" / "xhs" / "json"

        # Find the latest creator_creators file
        creator_files = list(json_dir.glob("creator_creators_*.json"))
        if not creator_files:
            error_msg = "No creator_creators_*.json file found"
            print(f"   ❌ {error_msg}")
            return {
                "success": False,
                "user_id": user_id,
                "notes_count": 0,
                "error": error_msg
            }

        latest_creator_file = max(creator_files, key=lambda p: p.stat().st_mtime)
        print(f"   📂 Loading from: {latest_creator_file.name}")

        # Load and parse creator data
        try:
            with open(latest_creator_file, 'r', encoding='utf-8') as f:
                creators = json.load(f)
        except Exception as e:
            error_msg = f"Failed to read creator_creators.json: {str(e)}"
            print(f"   ❌ {error_msg}")
            return {
                "success": False,
                "user_id": user_id,
                "notes_count": 0,
                "error": error_msg
            }

        # Find our blogger in the creators list
        creator_info = None
        for creator in creators:
            if creator.get("user_id") == user_id:
                creator_info = creator
                break

        if not creator_info:
            error_msg = f"Blogger {user_id} not found in creator_creators.json"
            print(f"   ❌ {error_msg}")
            return {
                "success": False,
                "user_id": user_id,
                "notes_count": 0,
                "error": error_msg
            }

        # Extract blogger info with fallbacks
        extracted_nickname = creator_info.get("nickname", "").strip() or nickname or f"user_{user_id[:8]}"
        extracted_avatar = creator_info.get("avatar", "").strip()
        extracted_fans = int(creator_info.get("fans", 0) or 0)
        extracted_desc = creator_info.get("desc", "").strip()
        extracted_gender = creator_info.get("gender", "")
        extracted_location = creator_info.get("ip_location", "")
        follows = int(creator_info.get("follows", 0) or 0)
        interaction = int(creator_info.get("interaction", 0) or 0)

        print(f"   ✓ Blogger info loaded:")
        print(f"      - Nickname: {extracted_nickname}")
        print(f"      - Fans: {extracted_fans:,}")
        print(f"      - Avatar: {'Yes' if extracted_avatar else 'No'}")
        print(f"      - Location: {extracted_location or 'N/A'}")

        # Step 3: Insert or update blogger in database
        if add_to_db:
            existing_blogger = BloggerDB.get_blogger(user_id)

            if existing_blogger:
                print(f"\nℹ️  Blogger already exists in database")
                print(f"   Current nickname: {existing_blogger.get('nickname')}")
                print(f"   Current fans: {existing_blogger.get('current_fans', 0):,}")
                print(f"   Updating with fresh data...")

                # Update blogger info with latest data
                BloggerDB.update_blogger_info(
                    user_id=user_id,
                    nickname=extracted_nickname,
                    avatar_url=extracted_avatar if extracted_avatar else None,
                    current_fans=extracted_fans
                )
                print(f"   ✓ Blogger updated")

                # Get existing notes count
                existing_notes_count = NoteDB.count_notes_by_user(user_id)
                print(f"   Existing notes: {existing_notes_count}")

                if existing_notes_count >= max_notes:
                    print(f"   ⚠️  Already has {existing_notes_count} notes (target: {max_notes})")
                    print(f"   Skipping data import.")
                    BloggerDB.update_scrape_progress(
                        user_id=user_id,
                        notes_collected=existing_notes_count,
                        notes_target=max_notes,
                        scrape_status='completed'
                    )
                    BloggerDB.update_status(user_id, "scraped")

                    return {
                        "success": True,
                        "user_id": user_id,
                        "notes_count": existing_notes_count,
                        "message": "Already collected enough notes"
                    }

                # Update progress for additional collection
                BloggerDB.update_scrape_progress(
                    user_id=user_id,
                    notes_collected=existing_notes_count,
                    notes_target=max_notes,
                    scrape_status='in_progress'
                )
            else:
                # Insert new blogger with full info (no placeholder needed!)
                print(f"\n➕ Inserting new blogger into database...")
                BloggerDB.insert_blogger(
                    user_id=user_id,
                    nickname=extracted_nickname,
                    avatar_url=extracted_avatar if extracted_avatar else None,
                    initial_fans=extracted_fans,
                    source_keyword="manual_input"
                )

                # Initialize progress
                BloggerDB.update_scrape_progress(
                    user_id=user_id,
                    notes_collected=0,
                    notes_target=max_notes,
                    scrape_status='in_progress'
                )

                print(f"   ✓ Blogger added with complete info:")
                print(f"      - Nickname: {extracted_nickname}")
                print(f"      - Initial fans: {extracted_fans:,}")

        # Step 4: Load notes from creator_contents.json
        print(f"\n📚 Loading notes from MediaCrawler output...")

        # Find the latest creator_content file
        content_files = list(json_dir.glob("creator_contents_*.json"))
        if not content_files:
            error_msg = "No creator_contents_*.json file found"
            print(f"   ❌ {error_msg}")

            if add_to_db:
                print(f"   🗑️  Auto-deleting blogger (no notes found)...")
                NoteDB.delete_notes_by_user(user_id)
                BloggerDB.delete_blogger(user_id)

            return {
                "success": False,
                "user_id": user_id,
                "notes_count": 0,
                "error": error_msg
            }

        latest_content_file = max(content_files, key=lambda p: p.stat().st_mtime)
        print(f"   📂 Loading from: {latest_content_file.name}")

        all_notes = load_notes_from_json(latest_content_file)

        # Filter notes for this specific user_id
        notes = [note for note in all_notes if note["user_id"] == user_id]
        print(f"   ✓ Found {len(notes)} note(s) for user {user_id}")

        if not notes and add_to_db:
            # blogger exists but no notes - this is acceptable (blogger might have no public notes)
            print(f"   ℹ️  No notes found for this blogger (may have private or deleted content)")
            total_in_db = NoteDB.count_notes_by_user(user_id)

            BloggerDB.update_scrape_progress(
                user_id=user_id,
                notes_collected=total_in_db,
                notes_target=max_notes,
                scrape_status='completed'
            )
            BloggerDB.update_status(user_id, "scraped")

            return {
                "success": True,
                "user_id": user_id,
                "notes_count": 0,
                "message": "No notes available for this blogger"
            }

        # Step 5: Save notes to database
        print(f"\n💾 Saving notes to database...")
        notes_added = 0

        for note in notes:
            try:
                note_success = NoteDB.insert_note(
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
                if note_success:
                    notes_added += 1
            except Exception as e:
                print(f"   ⚠️  Failed to save note {note['note_id']}: {e}")

        # Get total count in database
        total_notes = NoteDB.count_notes_by_user(user_id)
        print(f"   ✓ Saved {notes_added} new notes (Total: {total_notes})")

        # Step 6: Update progress and status
        if add_to_db:
            BloggerDB.update_scrape_progress(
                user_id=user_id,
                notes_collected=total_notes,
                notes_target=max_notes,
                scrape_status='completed'
            )
            BloggerDB.update_status(user_id, "scraped")
            print(f"   ✓ Collection completed!")

        # Step 7: Auto-download covers
        print(f"\n📥 Auto-downloading note covers...")
        try:
            from red_lens.analyzer import download_note_covers

            # Get top 10 + bottom 5 note IDs for this blogger
            notes = NoteDB.get_notes_by_user(user_id)
            if notes:
                sorted_notes = sorted(notes, key=lambda x: x['likes'], reverse=True)
                top_10 = sorted_notes[:10]
                bottom_5 = sorted_notes[-5:] if len(sorted_notes) > 5 else []
                note_ids_to_download = [n['note_id'] for n in top_10 + bottom_5]

                cover_result = download_note_covers(note_ids_to_download, force_redownload=False)
                print(f"   ✓ Downloaded: {cover_result['downloaded']}, Skipped: {cover_result['skipped']}, Failed: {cover_result['failed']}")
            else:
                print(f"   ⚠ No notes found to download covers")
        except Exception as e:
            print(f"   ⚠️  Cover download failed: {e}")

        print(f"\n{'='*60}")
        print(f"✅ Manual collection completed!")
        print(f"   User ID: {user_id}")
        print(f"   Nickname: {extracted_nickname}")
        print(f"   Fans: {extracted_fans:,}")
        print(f"   Notes added: {notes_added}")
        print(f"   Total notes: {total_notes}")
        print(f"{'='*60}\n")

        return {
            "success": True,
            "user_id": user_id,
            "notes_count": total_notes,
            "notes_added": notes_added,
            "nickname": extracted_nickname,
            "fans": extracted_fans
        }

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"\n❌ {error_msg}")

        if add_to_db:
            try:
                print(f"🗑️  Auto-deleting blogger due to error...")
                notes_deleted = NoteDB.delete_notes_by_user(user_id)
                blogger_deleted = BloggerDB.delete_blogger(user_id)
                print(f"✓ Deleted {notes_deleted} notes and blogger record")
            except Exception as delete_error:
                print(f"⚠️  Failed to auto-delete: {delete_error}")

        return {
            "success": False,
            "user_id": user_id,
            "notes_count": 0,
            "error": error_msg
        }


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
