from replacementPolicy import LRUCache

class Ram:
    def __init__(self, capacity_bytes=1342177280, block_size=4):
        """
        Initialize RAM cache
        :param capacity_bytes: Maximum storage capacity in bytes
        :param block_size: Block size in bytes
        """
        self.capacity_bytes = capacity_bytes
        self.block_size = block_size
        self.used_bytes = 0
        self.data_cache = {}  # Store file_id -> size mapping

    def get_data(self, key):
        return self.data_cache.get(key)

    def set_data(self, key, size_bytes):
        """Store file in RAM if space available"""
        if key not in self.data_cache:
            if self.used_bytes + size_bytes <= self.capacity_bytes:
                self.data_cache[key] = size_bytes
                self.used_bytes += size_bytes
                return True
            else:
                return False  # Not enough space
        return True

    def delete_data(self, data_key):
        if data_key in self.data_cache:
            self.used_bytes -= self.data_cache[data_key]
            del self.data_cache[data_key]

    def get_available_space(self):
        return self.capacity_bytes - self.used_bytes

    def get_usage_percentage(self):
        return (self.used_bytes / self.capacity_bytes) * 100


class HardDiskDrive:

    def __init__(self, capacity_bytes=1000000000000, block_size=128):
        """
        Initialize HDD
        :param capacity_bytes: Maximum storage capacity in bytes
        :param block_size: Block size in bytes
        """
        self.capacity_bytes = capacity_bytes
        self.block_size = block_size
        self.data = {}  # Store file_id -> size mapping
        self.used_bytes = 0

    def add_data(self, new_data, size_bytes):
        """Add data to HDD and return frequency"""
        frequency = 0
        if new_data in self.data:
            frequency = self.data[new_data] + 1
            self.data[new_data] = frequency
        else:
            self.data[new_data] = 1
            self.used_bytes += size_bytes
            frequency = 1

        return frequency

    def delete_data(self, data_key):
        if data_key in self.data:
            self.used_bytes -= self.data.get(data_key, 0)
            del self.data[data_key]

    def get_available_space(self):
        return self.capacity_bytes - self.used_bytes


class SolidStateDrive:

    def __init__(self, capacity_bytes=181555200, block_size=128):
        """
        Initialize SSD cache
        :param capacity_bytes: Maximum storage capacity in bytes
        :param block_size: Block size in bytes
        """
        self.capacity_bytes = capacity_bytes
        self.block_size = block_size
        self.used_bytes = 0
        self.data_cache = {}  # Store file_id -> size mapping

    def get_data(self, key):
        return self.data_cache.get(key)

    def set_data(self, key, size_bytes):
        """Store file in SSD if space available, evict LRU if needed"""
        if key not in self.data_cache:
            if self.used_bytes + size_bytes <= self.capacity_bytes:
                self.data_cache[key] = size_bytes
                self.used_bytes += size_bytes
                return True
            else:
                # Need to evict - remove least recently used
                if self.data_cache:  # If cache not empty
                    lru_key = next(iter(self.data_cache))  # Get first (oldest) key
                    self.used_bytes -= self.data_cache[lru_key]
                    del self.data_cache[lru_key]
                    # Now add the new data
                    self.data_cache[key] = size_bytes
                    self.used_bytes += size_bytes
                    return True
                return False
        return True

    def delete_data(self, data_key):
        if data_key in self.data_cache:
            self.used_bytes -= self.data_cache[data_key]
            del self.data_cache[data_key]

    def get_available_space(self):
        return self.capacity_bytes - self.used_bytes

    def get_usage_percentage(self):
        return (self.used_bytes / self.capacity_bytes) * 100
