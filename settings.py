
# Set the Delimeter character for separating fields in the workload file
DELIMITER = ','

# Set the data transfer rate in Hard Disk Drive, unit must be in MB/s
READ_DATA_TRANSFER_RATE_HDD = 156
WRITE_DATA_TRANSFER_RATE_HDD = 156

# Set the data transfer rate in Solid State Drive, unit must be in MB/s, read is fast. 
READ_DATA_TRANSFER_RATE_SSD = 550
WRITE_DATA_TRANSFER_RATE_SSD = 530

# Set the default size files used in the simulation, it must be in MB
DEFAULT_SIZE_FILE = 128

# Set the size file unit abbreviation, the unit can be B (Byte), KB(Kilobyte), MB(MegaByte), GB(GigaByte)
# If there is no file size set the value to '-'.
SIZE_FILE_UNIT = 'KB'

# Set the Data Transfer Rate Unit abbreviation  HAY Q VER Q TAN CONFIGURABLE ES ESTO
TRANSFER_RATE_UNIT = 'MB/s'

# ***** The columns fields positions are considered Starting in 0 (zero) *****
# OLD FORMAT (for ssd_caching, hashed, f4, all_ram, all_ssd, all_hdd policies):
COLUMN_TIMESTAMP = 0       # Column 0: timestamp
COLUMN_ID = 1              # Column 1: file_id (or LBA)
COLUMN_SIZE_FILE = 2       # Column 2: file_size (or block_size)
COLUMN_TYPE_REQUEST = 3    # Column 3: operation type (read/write)

# NEW FORMAT (for rl_c51 policy):
# Format: timestamp, operation, LBA, block_size, seq/rand, inter_arrival, service_time, idle_time
# Only used: operation, LBA, block_size, service_time
# Note: inter_arrival and idle_time are read but not used in RL reward calculation
COLUMN_OPERATION = 1       # Column 1: operation (WS=write, RS=read)
COLUMN_LBA = 2             # Column 2: Logical Block Address (file identifier)
COLUMN_BLOCK_SIZE = 3      # Column 3: Block/request size in bytes
COLUMN_SERVICE_TIME = 6    # Column 6: Service time (seconds) - only used for RL reward

# Configure the timestamp unit second [s], millisecond [ms], microsecond [us] or nanosecond [ns] at Trace's file
TIMESTAMP_UNIT = 'ns'

# Configure the Replacement Policy to be used in the simulation
# Available policies:
# REPLACEMENT_POLICY = 'ssd_caching'   # SSD caching strategy
# REPLACEMENT_POLICY = 'hashed'        # Hashed placement
# REPLACEMENT_POLICY = 'f4'            # F4 strategy
REPLACEMENT_POLICY = 'rl_c51'        # RL-based placement
# REPLACEMENT_POLICY = 'all_ram'       # All data to RAM
# REPLACEMENT_POLICY = 'all_ssd'       # All data to SSD
# REPLACEMENT_POLICY = 'all_hdd'       # All data to HDD

# Optional: select device for torch ("cpu" or "cuda")
RL_DEVICE = 'cuda'


# # Size used un replacement policy simulation
# # Maximum number of Entries in Solid State Drive
# SSD_CAPACITY = 1418
# # Maximum number of Entries in Caching Layer
# RAM_CAPACITY = 10

# SSD Capacity: 
SSD_CAPACITY_BYTES = 100 * 1024 * 1024 * 1024  # 100GB
RAM_CAPACITY_BYTES = 10 * 1024 * 1024 * 1024   # 10GB

# Eviction Policy when capacity is exceeded
# Options: 'LRU' (Least Recently Used), 'FIFO' (First In First Out), 'LFU' (Least Frequently Used)
EVICTION_POLICY = 'LRU'

# Total of devices used in each layer to perform the simulation
NUMBER_SSD = 4146
NUMBER_HDD = 4146

# Path to the trace file to be loaded
# Set to None to read from stdin, or provide a file path like 'converted_trace.txt'
# FILE_PATH = 'data_trace/MSRC/src2_1.revised'
FILE_PATH = 'data_trace/MSRC/wdev_3.revised'
# FILE_PATH = 'data_trace/MSRC/src1_1.revised'


