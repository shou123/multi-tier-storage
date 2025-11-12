
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
# OLD FORMAT (for ssd_caching, hashed, f4 policies):
# COLUMN_TIMESTAMP = 0
# COLUMN_ID = 1
# COLUMN_SIZE_FILE = 2
# COLUMN_TYPE_REQUEST = 3

# NEW FORMAT (for rl_c51 policy):
# Format: operation, LBA, block_size, inter_arrival_time, service_time, idle_time
COLUMN_OPERATION = 0       # 'read' or 'write'
COLUMN_LBA = 1             # Logical Block Address (file identifier)
COLUMN_BLOCK_SIZE = 2      # Block/request size in bytes
COLUMN_INTER_ARRIVAL = 3   # Time between requests (seconds)
COLUMN_SERVICE_TIME = 4    # Service time (seconds)
COLUMN_IDLE_TIME = 5       # Idle time (seconds)

# Legacy columns (kept for backward compatibility with old policies)
# COLUMN_TIMESTAMP = 0
# COLUMN_ID = 1
# COLUMN_SIZE_FILE = 2
# COLUMN_TYPE_REQUEST = 3

# Configure the timestamp unit second [s], millisecond [ms], microsecond [us] or nanosecond [ns] at Trace's file
TIMESTAMP_UNIT = 'ns'

# Configure the Replacement Policy to be used in the simulation
# REPLACEMENT_POLICY = 'ssd_caching' 
# REPLACEMENT_POLICY = 'Hashed' 
# REPLACEMENT_POLICY = 'f4' 
REPLACEMENT_POLICY = 'rl_c51' # new RL placement policy

# Optional: select device for torch ("cpu" or "cuda")
RL_DEVICE = 'cuda'


# # Size used un replacement policy simulation
# # Maximum number of Entries in Solid State Drive
# SSD_CAPACITY = 1418
# # Maximum number of Entries in Caching Layer
# RAM_CAPACITY = 10

# SSD Capacity: 
SSD_CAPACITY_BYTES = 100  * 1024 * 1024  # 100MB
RAM_CAPACITY_BYTES = 1  * 1024 * 1024   # 1MB

# Eviction Policy when capacity is exceeded
# Options: 'LRU' (Least Recently Used), 'FIFO' (First In First Out), 'LFU' (Least Frequently Used)
EVICTION_POLICY = 'LRU'

# Total of devices used in each layer to perform the simulation
NUMBER_SSD = 4146
NUMBER_HDD = 4146

# Path to the trace file to be loaded
# Set to None to read from stdin, or provide a file path like 'converted_trace.txt'
FILE_PATH = 'wdev_3.revised'

