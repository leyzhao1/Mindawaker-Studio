#!/usr/bin/env python3
"""
检查深度图文件差异
"""
import hashlib
from pathlib import Path

print("Checking depth files in data/test_outputs/")
depth_dir = Path("./data/test_outputs")

depth_files = list(depth_dir.glob("*_depth.png"))
print(f"Found {len(depth_files)} depth files")

for file in depth_files:
    with open(file, 'rb') as f:
        data = f.read()
        md5 = hashlib.md5(data).hexdigest()
        print(f"{file.name}: {len(data)} bytes, MD5: {md5[:8]}")

# 比较前两个文件
if len(depth_files) >= 2:
    print("\nComparing first two files:")
    with open(depth_files[0], 'rb') as f1, open(depth_files[1], 'rb') as f2:
        data1 = f1.read()
        data2 = f2.read()
        if data1 == data2:
            print("  Files are IDENTICAL")
        else:
            print("  Files are DIFFERENT")
            # 找出第一个不同的字节位置
            for i, (b1, b2) in enumerate(zip(data1, data2)):
                if b1 != b2:
                    print(f"  First difference at byte {i}: {b1} vs {b2}")
                    break