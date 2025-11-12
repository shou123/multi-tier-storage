#!/usr/bin/env python
"""Quick test to verify trace parsing works."""

from features import create_feature_extractor

print("Testing FeatureExtractor...")
fe = create_feature_extractor()
print(f"Feature stats: max_lba={fe.stats.max_lba}, max_block={fe.stats.max_block}, max_service={fe.stats.max_service}")

count = 0
for state_vec, raw in fe.iter_states():
    count += 1
    print(f"Row {count}: file_id={raw['file_id']}, is_read={raw['is_read']}, lba={raw['lba']}, block={raw['block_size']}, service={raw['service']}")
    if count >= 5:
        break

print(f"\nTotal rows processed: {count}")
