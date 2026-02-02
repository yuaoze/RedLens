#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test timeout calculation and batch processing
验证超时时间计算和批量处理逻辑
"""

def calculate_timeout(num_creators: int, max_notes: int) -> int:
    """计算动态超时时间"""
    estimated_time_per_creator = max_notes * 4 + 60
    total_estimated_time = num_creators * estimated_time_per_creator
    timeout_seconds = int(total_estimated_time * 1.5)
    timeout_seconds = max(300, min(timeout_seconds, 7200))
    return timeout_seconds


def simulate_batch_processing(total_creators: int, batch_size: int, max_notes: int):
    """模拟批量处理"""
    num_batches = (total_creators + batch_size - 1) // batch_size

    print(f"\n{'='*70}")
    print(f"📦 批量处理模拟")
    print(f"{'='*70}")
    print(f"总博主数: {total_creators}")
    print(f"批量大小: {batch_size}")
    print(f"每博主笔记数: {max_notes}")
    print(f"批次数: {num_batches}")
    print()

    total_time = 0
    for i in range(0, total_creators, batch_size):
        batch = min(batch_size, total_creators - i)
        batch_num = i // batch_size + 1

        timeout = calculate_timeout(batch, max_notes)
        estimated = (batch * max_notes * 4 + batch * 60) // 60

        print(f"Batch {batch_num}/{num_batches}:")
        print(f"  博主数: {batch}")
        print(f"  预计时间: {estimated} 分钟")
        print(f"  超时设置: {timeout // 60} 分钟")
        print(f"  状态: {'✓ 安全' if timeout > estimated * 60 * 1.5 else '⚠️ 可能超时'}")
        print()

        total_time += estimated

    print(f"总预计时间: {total_time} 分钟 ({total_time / 60:.1f} 小时)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    print("\n🧪 超时计算测试")
    print("="*70)

    test_cases = [
        (2, 100, "2个博主，100条笔记/人"),
        (5, 100, "5个博主，100条笔记/人"),
        (10, 100, "10个博主，100条笔记/人"),
        (20, 100, "20个博主，100条笔记/人"),
    ]

    for num_creators, max_notes, desc in test_cases:
        timeout = calculate_timeout(num_creators, max_notes)
        estimated = num_creators * max_notes * 4 + num_creators * 60

        print(f"\n{desc}:")
        print(f"  预计时间: {estimated // 60} 分钟")
        print(f"  超时设置: {timeout // 60} 分钟")
        print(f"  安全余量: {(timeout / estimated - 1) * 100:.0f}%")

        if timeout >= 7200:
            print(f"  ⚠️ 达到最大超时限制（2小时）")
        elif estimated > timeout:
            print(f"  ❌ 预计时间超过超时设置")
        else:
            print(f"  ✓ 超时设置合理")

    print("\n" + "="*70)

    # 测试批量处理
    print("\n🧪 批量处理测试\n")

    simulate_batch_processing(total_creators=2, batch_size=5, max_notes=100)
    simulate_batch_processing(total_creators=5, batch_size=5, max_notes=100)
    simulate_batch_processing(total_creators=10, batch_size=5, max_notes=100)
    simulate_batch_processing(total_creators=20, batch_size=5, max_notes=100)

    # 不同批量大小对比
    print("\n🧪 批量大小对比（10个博主）\n")

    for batch_size in [3, 5, 10]:
        simulate_batch_processing(total_creators=10, batch_size=batch_size, max_notes=100)
