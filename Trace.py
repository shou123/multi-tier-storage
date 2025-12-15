import sys
from datetime import datetime
from storageDevice import SolidStateDrive
from storageDevice import Ram
import settings
from placement_policy_rl import RLPlacement
from migration_agent_system import MigrationAgentSystem

READS_SSD = 0
READS_HDD = 0
WRITES_SSD = 0
WRITES_HDD = 0
READS_RAM = 0
WRITES_RAM = 0
HDD_SERVED_TIME = 0
SSD_SERVED_TIME = 0
RAM_SERVED_TIME = 0

class Trace:

    def __init__(self, env, resource_hdd, resource_ssd):
        self.env = env
        self.concurrent_access_hdd = resource_hdd
        self.concurrent_access_ssd = resource_ssd
        self.read_transferRateHDD = settings.READ_DATA_TRANSFER_RATE_HDD
        self.write_transferRateHDD = settings.WRITE_DATA_TRANSFER_RATE_HDD
        self.read_transferRateSSD = settings.READ_DATA_TRANSFER_RATE_SSD
        self.write_transferRateSSD = settings.WRITE_DATA_TRANSFER_RATE_SSD
        self.size_file_default = settings.DEFAULT_SIZE_FILE    # 128 MB size file by default
        self.solidStateDrive = None
        self.ram = None

        # NEW: Storage capacity tracking
        self.ssd_used_bytes = 0
        self.ram_used_bytes = 0
        self.ssd_stored_files = {}  # {file_id: size_bytes}
        self.ram_stored_files = {}  # {file_id: size_bytes}
        self.access_order = []  # Track access order for LRU
        self.eviction_policy = settings.EVICTION_POLICY

        self.timestamp_unit_ns_factor = 1  # Factor for working timestamp in nanosecond unit
        self.size_file_unit_b_factor = 1  # Factor for working in Megabyte file size unit
        self.transfer_rate_unit_mbs_factor = 1  # Factor for working in transfer rate in Megabyte per seconds
        self.transfer_rate_ms_factor = 1000     # Factor for working file transfer rate duration in milliseconds
        self.replacement_policy = settings.REPLACEMENT_POLICY.lower()
        timestamp_unit = settings.TIMESTAMP_UNIT
        size_file_unit = settings.SIZE_FILE_UNIT
        
        ssd_capacity_bytes = settings.SSD_CAPACITY_BYTES
        ram_capacity_bytes = settings.RAM_CAPACITY_BYTES

        self.second_to_nanosecond = 1000 * 1000 * 1000
        self.nanosecond_to_millisecond = 1 / float(1000 * 1000)
        # The Simulation works as the smallest unit of time is Nanosecond; and the smallest file unit is byte
        # Set the factor to convert timestamp unit to timestamp unit in Milliseconds
        if timestamp_unit == 's':
            self.timestamp_unit_ns_factor = 1000 * 1000 * 1000
        elif timestamp_unit == 'ms':
            self.timestamp_unit_ns_factor = 1000 * 1000
        elif timestamp_unit == 'us':
            self.timestamp_unit_ns_factor = 1000
        elif timestamp_unit == 'ns':
            self.timestamp_unit_ns_factor = 1
        # Set the factor for convert size file unit to size file in Bytes
        if size_file_unit == 'GB':
            self.size_file_unit_b_factor = 1024 * 1024 * 1024
        elif size_file_unit == 'MB':
            self.size_file_unit_b_factor = 1024 * 1024
        elif size_file_unit == 'KB':
            self.size_file_unit_b_factor = 1024
        elif size_file_unit == 'B':
            self.size_file_unit_b_factor = 1
        # As transfer rate must be in Megabyte per seconds (MB/s), we need to convert it in Byte per seconds (B/s) for next operations
        mb_to_byte = 1024 * 1024
        self.read_transferRateHDD = self.read_transferRateHDD * mb_to_byte
        self.read_transferRateSSD = self.read_transferRateSSD * mb_to_byte
        self.write_transferRateHDD = self.write_transferRateHDD * mb_to_byte
        self.write_transferRateSSD = self.write_transferRateSSD * mb_to_byte

        if self.replacement_policy == 'ssd_caching':
            self.solidStateDrive = SolidStateDrive(capacity_bytes=ssd_capacity_bytes)
        elif self.replacement_policy == 'f4':
            self.ram = Ram(capacity_bytes=ram_capacity_bytes)
        elif self.replacement_policy == 'rl_c51':
            # RL agent will decide tier per request
            self.solidStateDrive = SolidStateDrive(capacity_bytes=ssd_capacity_bytes)
            self.ram = Ram(capacity_bytes=ram_capacity_bytes)
            self.rl = RLPlacement(ssd_cap=ssd_capacity_bytes, ram_cap=ram_capacity_bytes,
                                  device=getattr(settings, 'RL_DEVICE', 'cpu'))
        
        # NEW: Initialize unified agent system (works with all policies)
        self.agent_system = MigrationAgentSystem(
            ssd_capacity_bytes=ssd_capacity_bytes,
            ram_capacity_bytes=ram_capacity_bytes,
            env=self.env,
            placement_agent=getattr(self, 'rl', None)  # Pass RL agent if it exists
        )
        self.agent_check_counter = 0
        
        print("[INIT] Migration Agent System initialized")
        print(f"  SSD capacity: {ssd_capacity_bytes / 1e9:.1f}GB")
        print(f"  RAM capacity: {ram_capacity_bytes / 1e9:.1f}GB")
        print(f"  Placement policy: {self.replacement_policy}")
        print(f"  Migration enabled: Yes")


    def source_trace(self, delimeter, column_id, column_timestamp, column_size, column_type_operation, file_path=None):
        prevTime = 0
        i = 0
        size_file = 0
        
        # If file_path is provided, read from file; otherwise read from stdin
        if file_path:
            try:
                lines = open(file_path, 'r')
            except FileNotFoundError:
                print(f"Error: File '{file_path}' not found!")
                return
        else:
            lines = sys.stdin
        
        for line in lines:
            line = line.strip()
            if not line:  # Skip empty lines
                continue
            campos = line.split(delimeter)
            if i == 0:
                prevTime = float(campos[column_timestamp])
                # prevTime = prevTime * self.timestamp_unit_ms_factor
                i = 2
            actualTime = float(campos[column_timestamp])
            # actualTime = actualTime * self.timestamp_unit_ms_factor
            # mili_seconds = (actualTime - prevTime) * self.timestamp_unit_ms_factor
            mili_seconds = (actualTime - prevTime) * self.timestamp_unit_ns_factor
            prevTime = actualTime
            if mili_seconds < 0:
                mili_seconds = 0
            yield self.env.timeout(mili_seconds)
            file_id = campos[column_id]
            if column_size == '-':
                size_file = self.size_file_default * self.size_file_unit_b_factor
            else:
                size_file = int(float(campos[column_size])) * self.size_file_unit_b_factor
            if column_type_operation == '-':
                type_operation = 'Read'
            else:
                type_operation = campos[column_type_operation]
            if self.replacement_policy == 'ssd_caching':
                self.env.process(self.transfer_with_ssd_caching(file_id, size_file, type_operation))
            elif self.replacement_policy == 'f4':
                self.env.process(self.transfer_with_f_four(file_id, size_file, type_operation, campos[-1]))
            elif self.replacement_policy == 'hashed':
                self.env.process(self.transfer_with_hashed(file_id, size_file, type_operation))
            elif self.replacement_policy == 'rl_c51':
                # infer seq/rand from column: campos[4]
                is_seq = (campos[4].strip().lower() == 'seq') if len(campos) > 4 else False
                inter_arrival_s = float(campos[5]) if len(campos) > 5 else 0.0
                is_read = (type_operation.lower() == 'read')
                self.env.process(self.transfer_with_rl(file_id, size_file, is_read, is_seq, inter_arrival_s))
            elif self.replacement_policy == 'all_ram':
                is_read = (type_operation.lower() == 'read')
                self.env.process(self.transfer_with_all_ram(file_id, size_file, is_read))
            elif self.replacement_policy == 'all_ssd':
                is_read = (type_operation.lower() == 'read')
                self.env.process(self.transfer_with_all_ssd(file_id, size_file, is_read))
            elif self.replacement_policy == 'all_hdd':
                is_read = (type_operation.lower() == 'read')
                self.env.process(self.transfer_with_all_hdd(file_id, size_file, is_read))
        
        # Close file if it was opened (not stdin)
        if file_path:
            lines.close()

    def source_trace_rl(self, file_path=None):
        """Read trace file in RL format: timestamp, operation, LBA, block_size, seq/rand, inter_arrival, service_time, idle_time
        
        Only used fields: operation, LBA, block_size, service_time
        Latency (RL reward) = service_time only (not inter_arrival or idle_time)
        
        This method is optimized for the RL placement policy which needs direct access to
        all trace fields for feature extraction.
        """
        from features import create_feature_extractor
        
        if file_path is None:
            print("Error: RL policy requires FILE_PATH to be set in settings!")
            return
        
        try:
            fe = create_feature_extractor()
        except Exception as e:
            print(f"Error initializing FeatureExtractor: {e}")
            return
        
        for idx, (state_vec, raw) in enumerate(fe.iter_states()):
            # Calculate inter-arrival time (time to wait before processing this request)
            inter_arrival = raw['inter']
            if idx == 0:
                # Skip inter-arrival delay on first request
                inter_arrival = 0
            
            # Convert to nanoseconds for SimPy
            inter_arrival_ns = inter_arrival * self.second_to_nanosecond
            yield self.env.timeout(inter_arrival_ns)
            
            # Extract fields from raw trace data
            file_id = str(int(raw['file_id']))
            size_file = int(raw['block_size'])
            is_read = bool(raw['is_read'])
            service_time_s = raw['service']  # service_time in seconds (only used for RL reward)
            
            # Process request based on replacement policy
            if self.replacement_policy == 'rl_c51':
                self.env.process(self.transfer_with_rl_state(
                    file_id=file_id,
                    size_file=size_file,
                    is_read=is_read,
                    state_vec=state_vec,
                    service_time_s=service_time_s
                ))
            elif self.replacement_policy == 'all_ram':
                self.env.process(self.transfer_with_all_ram(file_id, size_file, is_read))
            elif self.replacement_policy == 'all_ssd':
                self.env.process(self.transfer_with_all_ssd(file_id, size_file, is_read))
            elif self.replacement_policy == 'all_hdd':
                self.env.process(self.transfer_with_all_hdd(file_id, size_file, is_read))

    def transfer_with_hashed(self, file_id, size_file, type_operation):
        locationSelected = ''
        # print ('Trace %s arriving at %d [ms]' % (file_id, self.env.now))
        capeSelected = self.getCapeSelected(file_id)
        type_operation = type_operation.lower()
        if type_operation == 'read':
            transferRateSSD = self.read_transferRateSSD
            transferRateHDD = self.read_transferRateHDD
            if capeSelected == 1:
                global READS_SSD
                READS_SSD += 1
            else:
                global READS_HDD
                READS_HDD += 1
        else:
            transferRateSSD = self.write_transferRateSSD
            transferRateHDD = self.write_transferRateHDD
            if capeSelected == 1:
                global WRITES_SSD
                WRITES_SSD += 1
            else:
                global WRITES_HDD
                WRITES_HDD += 1

        if capeSelected == 1:
            transferDuration = (size_file / float(transferRateSSD)) * self.second_to_nanosecond
            transferDuration = int(transferDuration)
            locationSelected = 'SSD'
            with self.concurrent_access_ssd.request() as req:
                arrived_time = self.env.now
                yield req
                yield self.env.timeout(transferDuration)
                returned_time = self.env.now
                served_time = returned_time - arrived_time
                global SSD_SERVED_TIME
                SSD_SERVED_TIME = SSD_SERVED_TIME + served_time
                # Save time values in millisecond unit [ms]
                arrived_time = int(arrived_time * self.nanosecond_to_millisecond)
                returned_time = int(returned_time * self.nanosecond_to_millisecond)
                served_time = int(served_time * self.nanosecond_to_millisecond)
                print(str(file_id) + ',' + str(arrived_time) + ',' + str(returned_time) + ',' + str(served_time) + ',' + locationSelected)
        else:
            transferDuration = (size_file / float(transferRateHDD)) * self.second_to_nanosecond
            transferDuration =  int(transferDuration)
            locationSelected = 'HDD'
            with self.concurrent_access_hdd.request() as req:
                arrived_time = self.env.now
                yield req
                yield self.env.timeout(transferDuration)
                returned_time = self.env.now
                served_time = returned_time - arrived_time
                global HDD_SERVED_TIME
                HDD_SERVED_TIME = HDD_SERVED_TIME + served_time
                # Save time values in millisecond unit [ms]
                arrived_time = int(arrived_time * self.nanosecond_to_millisecond)
                returned_time = int(returned_time * self.nanosecond_to_millisecond)
                served_time = int(served_time * self.nanosecond_to_millisecond)
                print(str(file_id) + ',' + str(arrived_time) + ',' + str(returned_time) + ',' + str(served_time) + ',' + locationSelected)
        # print ('Finished moving trace %s in %s at %d [ms]' % (file_id, locationSelected,  self.env.now))

    def getCapeSelected(self, id):
        value = hash(id)
        return value & 1

    def transfer_with_ssd_caching(self, file_id, size_file, type_operation):
        locationSelected = ''
        # print ('Trace %s arriving at %d [ms]' % (file_id, self.env.now))
        value = self.solidStateDrive.get_data(file_id)
        type_operation = type_operation.lower()
        if type_operation == 'read':
            transferRateSSD = self.read_transferRateSSD
            transferRateHDD = self.read_transferRateHDD
            if value == -1:
                global READS_HDD
                READS_HDD += 1
            else:
                global READS_SSD
                READS_SSD += 1
        else:
            transferRateSSD = self.write_transferRateSSD
            transferRateHDD = self.write_transferRateHDD
            if value == -1:
                global WRITES_HDD
                WRITES_HDD += 1
            else:
                global WRITES_SSD
                WRITES_SSD += 1

        if value == -1: # The file_id is not in Solid State Drive
            transferDuration = (size_file / float(transferRateHDD)) * self.second_to_nanosecond
            transferDuration = int(transferDuration)
            locationSelected = 'HDD'
            with self.concurrent_access_hdd.request() as req_hdd:
                arrived_time = self.env.now
                yield req_hdd
                # print ('Trace hdd %s arriving at %d [ms]' % (file_id, arrived_time))
                yield self.env.timeout(transferDuration)
                returned_time = self.env.now
                served_time = returned_time - arrived_time
                global HDD_SERVED_TIME
                HDD_SERVED_TIME = HDD_SERVED_TIME + served_time
                # Save time values in millisecond unit [ms]
                # arrived_time = int(arrived_time * self.nanosecond_to_millisecond)
                # returned_time = int(returned_time * self.nanosecond_to_millisecond)
                # served_time = int(served_time * self.nanosecond_to_millisecond)
                print(str(file_id) + ',' + str(arrived_time) + ',' + str(returned_time) + ',' + str(served_time) + ',' + locationSelected)
                # print ('Finished moving trace %s in %s at %d [ms]' % (file_id, locationSelected,  returned_time))
            self.solidStateDrive.set_data(file_id, 5)
        else: # else we need to move to solid state drive the file id
            transferDuration = (size_file / float(transferRateSSD)) * self.second_to_nanosecond
            transferDuration = int(transferDuration)
            locationSelected = 'SSD'
            with self.concurrent_access_ssd.request() as req_ssd:
                arrived_time = self.env.now
                yield req_ssd
                # print ('Trace ssd %s arriving at %d [ms]' % (file_id, arrived_time))
                yield self.env.timeout(transferDuration)
                returned_time = self.env.now
                served_time = returned_time - arrived_time
                global SSD_SERVED_TIME
                SSD_SERVED_TIME = SSD_SERVED_TIME + served_time
                # Save time values in millisecond unit [ms]
                # arrived_time = int(arrived_time * self.nanosecond_to_millisecond)
                # returned_time = int(returned_time * self.nanosecond_to_millisecond)
                # served_time = int(served_time * self.nanosecond_to_millisecond)
                print(str(file_id) + ',' + str(arrived_time) + ',' + str(returned_time) + ',' + str(served_time) + ',' + locationSelected)
                # print ('Finished moving trace %s in %s at %d [ms]' % (file_id, locationSelected,  returned_time))
        
        # NEW: Check SSD capacity after storing (both HDD and SSD paths)
        self.check_ssd_capacity(file_id, size_file)
        # print ('Finished moving trace %s in %s at %d [ms]' % (file_id, locationSelected,  self.env.now))

    def transfer_with_f_four(self, file_id, size_file, type_operation, zone):
        locationSelected = ''
        # print ('Trace %s arriving at %d [ms]' % (file_id, self.env.now))
        value = self.ram.get_data(file_id)
        if value is not None and value >= 0:  # The file_id is in RAM
            global READS_RAM
            READS_RAM += 1
            transferDuration = 10      # [ns]
            locationSelected = 'RAM'
            yield self.env.timeout(transferDuration)
            # print ('Finished reading trace %s in %s at %d [ms]' % (file_id, locationSelected,  self.env.now))
        else:
            type_operation = type_operation.lower()
            if type_operation == 'read':
                transferRateSSD = self.read_transferRateSSD
                transferRateHDD = self.read_transferRateHDD
                if zone == 'hot':
                    global READS_SSD
                    READS_SSD += 1
                else:
                    global READS_HDD
                    READS_HDD += 1
            else:
                transferRateSSD = self.write_transferRateSSD
                transferRateHDD = self.write_transferRateHDD
                if zone == 'hot':
                    global WRITES_SSD
                    WRITES_SSD += 1
                else:
                    global WRITES_HDD
                    WRITES_HDD += 1

            if zone == 'hot':
                transferDuration = (size_file / float(transferRateSSD)) * self.second_to_nanosecond
                transferDuration = int(transferDuration)
                locationSelected = 'SSD'
                with self.concurrent_access_ssd.request() as req_ssd:
                    arrived_time = self.env.now
                    # print ('Trace Hot %s arriving at %d [ms]' % (file_id, arrived_time))
                    yield req_ssd
                    yield self.env.timeout(transferDuration)
                    returned_time = self.env.now
                    served_time = returned_time - arrived_time
                    global SSD_SERVED_TIME
                    SSD_SERVED_TIME = SSD_SERVED_TIME + served_time
                    # Save time values in millisecond unit [ms]
                    arrived_time = int(arrived_time * self.nanosecond_to_millisecond)
                    returned_time = int(returned_time * self.nanosecond_to_millisecond)
                    served_time = int(served_time * self.nanosecond_to_millisecond)
                    print(str(file_id) + ',' + str(arrived_time) + ',' + str(returned_time) + ',' + str(served_time) + ',' + locationSelected)
                    # print ('Finished moving trace %s in %s at %d [ms]' % (file_id, locationSelected,  returned_time))
            else:
                transferDuration = (size_file / float(transferRateHDD)) * self.second_to_nanosecond
                transferDuration = int(transferDuration)
                locationSelected = 'HDD'
                with self.concurrent_access_hdd.request() as req_hdd:
                    arrived_time = self.env.now
                    # print ('Trace Warm %s arriving at %d [ms]' % (file_id, arrived_time))
                    yield req_hdd
                    yield self.env.timeout(transferDuration)
                    returned_time = self.env.now
                    served_time = returned_time - arrived_time
                    global HDD_SERVED_TIME
                    HDD_SERVED_TIME = HDD_SERVED_TIME + served_time
                    # Save time values in millisecond unit [ms]
                    arrived_time = int(arrived_time * self.nanosecond_to_millisecond)
                    returned_time = int(returned_time * self.nanosecond_to_millisecond)
                    served_time = int(served_time * self.nanosecond_to_millisecond)
                    print(str(file_id) + ',' + str(arrived_time) + ',' + str(returned_time) + ',' + str(served_time) + ',' + locationSelected)
                    # print ('Finished moving trace %s in %s at %d [ms]' % (file_id, locationSelected,  returned_time))
            self.ram.set_data(file_id, 5)
            # NEW: Check RAM capacity after storing
            self.check_ram_capacity(file_id, size_file)
        # print ('Finished moving trace %s in %s at %d [ms]' % (file_id, locationSelected,  self.env.now))

    def transfer_with_rl(self, file_id, size_file, is_read, is_seq, inter_arrival_s):
        # Query agent for tier choice using *current* context
        tier = self.rl.select_tier(
            is_read=is_read,
            size_bytes=size_file,
            is_seq=is_seq,
            inter_arrival_s=inter_arrival_s,
            ssd_used=self.ssd_used_bytes,
            ssd_cap=settings.SSD_CAPACITY_BYTES,
            ram_used=self.ram_used_bytes,
            ram_cap=settings.RAM_CAPACITY_BYTES,
            file_id=str(file_id))

        # Map tier to device + transfer rate
        if is_read:
            trSSD, trHDD = self.read_transferRateSSD, self.read_transferRateHDD
        else:
            trSSD, trHDD = self.write_transferRateSSD, self.write_transferRateHDD
    
        if tier == 'RAM':
            transferDuration = 10 # ns for RAM hit (like your f4 path)
            arrived_time = self.env.now
            yield self.env.timeout(int(transferDuration))
            returned_time = self.env.now
            served_time = returned_time - arrived_time
            global READS_RAM, WRITES_RAM, RAM_SERVED_TIME
            RAM_SERVED_TIME += served_time
            if is_read:
                READS_RAM += 1
            else:
                WRITES_RAM += 1
            # no device resource contention when RAM
            locationSelected = 'RAM'
        elif tier == 'SSD':
            transferDuration = int((size_file / float(trSSD)) * self.second_to_nanosecond)
            locationSelected = 'SSD'
            with self.concurrent_access_ssd.request() as req:
                arrived_time = self.env.now
                yield req
                yield self.env.timeout(transferDuration)
                returned_time = self.env.now
                served_time = returned_time - arrived_time
                global SSD_SERVED_TIME, READS_SSD, WRITES_SSD
                SSD_SERVED_TIME += served_time
                if is_read:
                    READS_SSD += 1
                else:
                    WRITES_SSD += 1
        else:
            transferDuration = int((size_file / float(trHDD)) * self.second_to_nanosecond)
            locationSelected = 'HDD'
            with self.concurrent_access_hdd.request() as req:
                arrived_time = self.env.now
                yield req
                yield self.env.timeout(transferDuration)
                returned_time = self.env.now
                served_time = returned_time - arrived_time
                global HDD_SERVED_TIME, READS_HDD, WRITES_HDD
                HDD_SERVED_TIME += served_time
                if is_read:
                    READS_HDD += 1
                else:
                    WRITES_HDD += 1
    
        # Latency accounting for reward: latency = service time only (I/O time)
        # Removed: inter-arrival time and idle time
        service = transferDuration * self.nanosecond_to_millisecond / 1000.0 # ns->ms->s
        latency_s = service
        
        # Store bookkeeping for capacity (reuse your tracking helpers)
        size_b = int(size_file)
        if tier == 'SSD':
            self.check_ssd_capacity(file_id, size_b)
        elif tier == 'RAM':
            self.check_ram_capacity(file_id, size_b)
    
        # Inform agent about outcome, build next-state from same req as proxy
        self.rl.observe(latency_s=latency_s,
            next_is_read=is_read,
            next_size_bytes=size_file,
            next_is_seq=is_seq,
            next_inter_arrival_s=inter_arrival_s,
            ssd_used=self.ssd_used_bytes,
            ssd_cap=settings.SSD_CAPACITY_BYTES,
            ram_used=self.ram_used_bytes,
            ram_cap=settings.RAM_CAPACITY_BYTES,
            file_id=str(file_id),
            done=False)
    
        self.rl.set_last_tier(str(file_id), locationSelected)
    
        # Emit CSV like other paths (ms units)
        arrived_ms = int(arrived_time * self.nanosecond_to_millisecond)
        returned_ms = int(returned_time * self.nanosecond_to_millisecond)
        served_ms = int((returned_time - arrived_time) * self.nanosecond_to_millisecond)
        print(f"{file_id},{arrived_ms},{returned_ms},{served_ms},{locationSelected}")
    

    def transfer_with_rl_state(self, file_id, size_file, is_read, state_vec, service_time_s):
        """Process request with RL agent using pre-computed state vector.
        
        Args:
            file_id: File identifier from trace
            size_file: Block size in bytes
            is_read: True if read operation, False if write
            state_vec: Pre-computed 7-dim state vector from FeatureExtractor
            service_time_s: Service time in seconds from trace (used for RL reward)
        
        This variant receives the complete 7-dim state from FeatureExtractor,
        avoiding redundant feature computation in the agent.
        
        Latency (RL reward) = service_time only (not inter_arrival or idle_time)
        """
        import numpy as np
        
        # Query agent for tier choice using state vector directly
        tier = self.rl.select_tier_from_state(
            state=state_vec,
            ssd_used=self.ssd_used_bytes,
            ssd_cap=settings.SSD_CAPACITY_BYTES,
            ram_used=self.ram_used_bytes,
            ram_cap=settings.RAM_CAPACITY_BYTES,
            file_id=str(file_id))

        # Map tier to device + transfer rate
        if is_read:
            trSSD, trHDD = self.read_transferRateSSD, self.read_transferRateHDD
        else:
            trSSD, trHDD = self.write_transferRateSSD, self.write_transferRateHDD
    
        if tier == 'RAM':
            transferDuration = 10  # ns for RAM hit
            arrived_time = self.env.now
            yield self.env.timeout(int(transferDuration))
            returned_time = self.env.now
            served_time_ns = returned_time - arrived_time
            global READS_RAM, WRITES_RAM, RAM_SERVED_TIME
            RAM_SERVED_TIME += served_time_ns
            if is_read:
                READS_RAM += 1
            else:
                WRITES_RAM += 1
            locationSelected = 'RAM'
        elif tier == 'SSD':
            transferDuration = int((size_file / float(trSSD)) * self.second_to_nanosecond)
            locationSelected = 'SSD'
            with self.concurrent_access_ssd.request() as req:
                arrived_time = self.env.now
                yield req
                yield self.env.timeout(transferDuration)
                returned_time = self.env.now
                served_time_ns = returned_time - arrived_time
                global SSD_SERVED_TIME, READS_SSD, WRITES_SSD
                SSD_SERVED_TIME += served_time_ns
                if is_read:
                    READS_SSD += 1
                else:
                    WRITES_SSD += 1
        else:
            transferDuration = int((size_file / float(trHDD)) * self.second_to_nanosecond)
            locationSelected = 'HDD'
            with self.concurrent_access_hdd.request() as req:
                arrived_time = self.env.now
                yield req
                yield self.env.timeout(transferDuration)
                returned_time = self.env.now
                served_time_ns = returned_time - arrived_time
                global HDD_SERVED_TIME, READS_HDD, WRITES_HDD
                HDD_SERVED_TIME += served_time_ns
                if is_read:
                    READS_HDD += 1
                else:
                    WRITES_HDD += 1
    
        # Update tier tracking
        size_b = int(size_file)
        if tier == 'SSD':
            self.check_ssd_capacity(file_id, size_b)
        elif tier == 'RAM':
            self.check_ram_capacity(file_id, size_b)
    
        # Update agent with outcome
        self.rl.set_last_tier(str(file_id), locationSelected)
        
        # CRITICAL: Provide RL reward for learning
        # The RL agent will compute reward internally from latency_s
        # (typically R = 1 / latency for inverse relationship)
        # Use service_time_s from trace as the actual latency experienced
        
        # Push experience to RL agent's replay buffer for learning
        self.rl.observe(latency_s=service_time_s,
            next_is_read=is_read,
            next_size_bytes=size_file,
            next_is_seq=False,  # Not available in this path, default to False
            next_inter_arrival_s=0.0,  # Not available in this path
            ssd_used=self.ssd_used_bytes,
            ssd_cap=settings.SSD_CAPACITY_BYTES,
            ram_used=self.ram_used_bytes,
            ram_cap=settings.RAM_CAPACITY_BYTES,
            file_id=str(file_id),
            done=False)
    
        # Emit CSV output (ms units)
        arrived_ms = int(arrived_time * self.nanosecond_to_millisecond)
        returned_ms = int(returned_time * self.nanosecond_to_millisecond)
        served_ms = int(served_time_ns * self.nanosecond_to_millisecond)
        print(f"{file_id},{locationSelected}")
        
        # NEW: Track for migration agent system
        self.agent_system.track_io_request(
            file_id=int(file_id),
            tier=locationSelected,
            latency_ns=served_time_ns,
            size_bytes=size_file,
            is_read=is_read
        )
        
        # NEW: Periodic migration check (every 50 requests)
        self.agent_check_counter += 1
        if self.agent_check_counter % 50 == 0:
            self.agent_system.periodic_update(
                ssd_usage=self.ssd_used_bytes,
                ram_usage=self.ram_used_bytes
            )

    def transfer_with_all_ram(self, file_id, size_file, is_read):
        """All data stored in RAM tier only."""
        transferDuration = 10  # ns for RAM hit
        arrived_time = self.env.now
        yield self.env.timeout(int(transferDuration))
        returned_time = self.env.now
        served_time_ns = returned_time - arrived_time
        
        global READS_RAM, WRITES_RAM, RAM_SERVED_TIME
        RAM_SERVED_TIME += served_time_ns
        if is_read:
            READS_RAM += 1
        else:
            WRITES_RAM += 1
        
        locationSelected = 'RAM'
        
        # Track capacity
        size_b = int(size_file)
        self.check_ram_capacity(file_id, size_b)
        
        # Emit CSV output (ms units)
        arrived_ms = int(arrived_time * self.nanosecond_to_millisecond)
        returned_ms = int(returned_time * self.nanosecond_to_millisecond)
        served_ms = int(served_time_ns * self.nanosecond_to_millisecond)
        print(f"{file_id},{arrived_ms},{returned_ms},{served_ms},{locationSelected}")
        
        # NEW: Track for unified agent system
        self.agent_system.track_io_request(
            file_id=int(file_id),
            tier=locationSelected,
            latency_ns=served_time_ns,
            size_bytes=size_file,
            is_read=is_read
        )
        
        # NEW: Periodic migration check (every 50 requests)
        self.agent_check_counter += 1
        if self.agent_check_counter % 50 == 0:
            self.agent_system.periodic_update(
                ssd_usage=self.ssd_used_bytes,
                ram_usage=self.ram_used_bytes
            )

    def transfer_with_all_ssd(self, file_id, size_file, is_read):
        """All data stored in SSD tier only."""
        if is_read:
            trSSD = self.read_transferRateSSD
        else:
            trSSD = self.write_transferRateSSD
        
        transferDuration = int((size_file / float(trSSD)) * self.second_to_nanosecond)
        locationSelected = 'SSD'
        
        with self.concurrent_access_ssd.request() as req:
            arrived_time = self.env.now
            yield req
            yield self.env.timeout(transferDuration)
            returned_time = self.env.now
            served_time_ns = returned_time - arrived_time
            
            global SSD_SERVED_TIME, READS_SSD, WRITES_SSD
            SSD_SERVED_TIME += served_time_ns
            if is_read:
                READS_SSD += 1
            else:
                WRITES_SSD += 1
        
        # Track capacity
        size_b = int(size_file)
        self.check_ssd_capacity(file_id, size_b)
        
        # Emit CSV output (ms units)
        arrived_ms = int(arrived_time * self.nanosecond_to_millisecond)
        returned_ms = int(returned_time * self.nanosecond_to_millisecond)
        served_ms = int(served_time_ns * self.nanosecond_to_millisecond)
        print(f"{file_id},{arrived_ms},{returned_ms},{served_ms},{locationSelected}")
        
        # NEW: Track for unified agent system
        self.agent_system.track_io_request(
            file_id=int(file_id),
            tier=locationSelected,
            latency_ns=served_time_ns,
            size_bytes=size_file,
            is_read=is_read
        )
        
        # NEW: Periodic migration check (every 50 requests)
        self.agent_check_counter += 1
        if self.agent_check_counter % 50 == 0:
            self.agent_system.periodic_update(
                ssd_usage=self.ssd_used_bytes,
                ram_usage=self.ram_used_bytes
            )

    def transfer_with_all_hdd(self, file_id, size_file, is_read):
        """All data stored in HDD tier only."""
        if is_read:
            trHDD = self.read_transferRateHDD
        else:
            trHDD = self.write_transferRateHDD
        
        transferDuration = int((size_file / float(trHDD)) * self.second_to_nanosecond)
        locationSelected = 'HDD'
        
        with self.concurrent_access_hdd.request() as req:
            arrived_time = self.env.now
            yield req
            yield self.env.timeout(transferDuration)
            returned_time = self.env.now
            served_time_ns = returned_time - arrived_time
            
            global HDD_SERVED_TIME, READS_HDD, WRITES_HDD
            HDD_SERVED_TIME += served_time_ns
            if is_read:
                READS_HDD += 1
            else:
                WRITES_HDD += 1
        
        # Emit CSV output (ms units)
        arrived_ms = int(arrived_time * self.nanosecond_to_millisecond)
        returned_ms = int(returned_time * self.nanosecond_to_millisecond)
        served_ms = int(served_time_ns * self.nanosecond_to_millisecond)
        print(f"{file_id},{arrived_ms},{returned_ms},{served_ms},{locationSelected}")
        
        # NEW: Track for unified agent system
        self.agent_system.track_io_request(
            file_id=int(file_id),
            tier=locationSelected,
            latency_ns=served_time_ns,
            size_bytes=size_file,
            is_read=is_read
        )
        
        # NEW: Periodic migration check (every 50 requests)
        self.agent_check_counter += 1
        if self.agent_check_counter % 50 == 0:
            self.agent_system.periodic_update(
                ssd_usage=self.ssd_used_bytes,
                ram_usage=self.ram_used_bytes
            )

    def timedelta_total_seconds(self, timedelta):
        return (timedelta.microseconds + 0.0 +(timedelta.seconds + timedelta.days * 24 * 3600) * 10 ** 6) / 10 ** 6


    # NEW: Check if file fits in SSD and handle overflow
    def check_ssd_capacity(self, file_id, file_size):
        """Check if file fits in SSD, evict if needed"""
        # Don't re-add file if already tracked
        if file_id in self.ssd_stored_files:
            return
        
        available_space = settings.SSD_CAPACITY_BYTES - self.ssd_used_bytes
        
        if file_size > available_space:
            bytes_needed = file_size - available_space
            self.evict_from_ssd(bytes_needed)
        
        # Add file to SSD tracking
        self.ssd_stored_files[file_id] = file_size
        self.ssd_used_bytes += file_size
        self.access_order.append(file_id)
        
        # Debug output
        ssd_percent = (self.ssd_used_bytes / float(settings.SSD_CAPACITY_BYTES)) * 100
        # print(f"[SSD] File {file_id} stored ({file_size} bytes). Usage: {ssd_percent:.2f}% ({self.ssd_used_bytes}/{settings.SSD_CAPACITY_BYTES} bytes) at time {self.env.now}")
    
    # NEW: Check if file fits in RAM and handle overflow
    def check_ram_capacity(self, file_id, file_size):
        """Check if file fits in RAM, evict if needed"""
        # Don't re-add file if already tracked
        if file_id in self.ram_stored_files:
            return
        
        available_space = settings.RAM_CAPACITY_BYTES - self.ram_used_bytes
        
        if file_size > available_space:
            bytes_needed = file_size - available_space
            self.evict_from_ram(bytes_needed)
        
        # Add file to RAM tracking
        self.ram_stored_files[file_id] = file_size
        self.ram_used_bytes += file_size
        
        # Debug output
        ram_percent = (self.ram_used_bytes / float(settings.RAM_CAPACITY_BYTES)) * 100
        print(f"[RAM] File {file_id} stored ({file_size} bytes). Usage: {ram_percent:.2f}% ({self.ram_used_bytes}/{settings.RAM_CAPACITY_BYTES} bytes) at time {self.env.now}")
    
    # NEW: Evict files from SSD based on policy
    def evict_from_ssd(self, bytes_to_free):
        """Remove files from SSD until enough space is freed"""
        evicted_count = 0
        bytes_freed = 0
        
        while bytes_to_free > 0 and len(self.access_order) > 0:
            # Get oldest file (FIFO)
            oldest_file = self.access_order.pop(0)
            if oldest_file in self.ssd_stored_files:
                file_size = self.ssd_stored_files.pop(oldest_file)
                self.ssd_used_bytes -= file_size
                bytes_to_free -= file_size
                bytes_freed += file_size
                evicted_count += 1
        
        if evicted_count > 0:
            ssd_percent = (self.ssd_used_bytes / float(settings.SSD_CAPACITY_BYTES)) * 100
            print(f"[SSD EVICTION] Evicted {evicted_count} files ({bytes_freed} bytes). New usage: {ssd_percent:.2f}% ({self.ssd_used_bytes}/{settings.SSD_CAPACITY_BYTES} bytes) at time {self.env.now}")
    
    # NEW: Evict files from RAM based on policy
    def evict_from_ram(self, bytes_to_free):
        """Remove files from RAM until enough space is freed"""
        evicted_count = 0
        bytes_freed = 0
        ram_access_order = list(self.ram_stored_files.keys())
        
        while bytes_to_free > 0 and len(ram_access_order) > 0:
            # Get oldest file (FIFO)
            oldest_file = ram_access_order.pop(0)
            if oldest_file in self.ram_stored_files:
                file_size = self.ram_stored_files.pop(oldest_file)
                self.ram_used_bytes -= file_size
                bytes_to_free -= file_size
                bytes_freed += file_size
                evicted_count += 1
        
        if evicted_count > 0:
            ram_percent = (self.ram_used_bytes / float(settings.RAM_CAPACITY_BYTES)) * 100
            print(f"[RAM EVICTION] Evicted {evicted_count} files ({bytes_freed} bytes). New usage: {ram_percent:.2f}% ({self.ram_used_bytes}/{settings.RAM_CAPACITY_BYTES} bytes) at time {self.env.now}")
    
    # NEW: Get storage usage statistics
    def get_storage_stats(self):
        """Return current storage utilization"""
        ssd_percent = (self.ssd_used_bytes / float(settings.SSD_CAPACITY_BYTES)) * 100 if settings.SSD_CAPACITY_BYTES > 0 else 0
        ram_percent = (self.ram_used_bytes / float(settings.RAM_CAPACITY_BYTES)) * 100 if settings.RAM_CAPACITY_BYTES > 0 else 0
        return {
            'ssd_used': self.ssd_used_bytes,
            'ssd_capacity': settings.SSD_CAPACITY_BYTES,
            'ssd_percent': ssd_percent,
            'ssd_files': len(self.ssd_stored_files),
            'ram_used': self.ram_used_bytes,
            'ram_capacity': settings.RAM_CAPACITY_BYTES,
            'ram_percent': ram_percent,
            'ram_files': len(self.ram_stored_files)
        }
    
    # NEW: Print storage status
    def print_storage_status(self):
        """Print current storage utilization"""
        stats = self.get_storage_stats()
        print(f"[Storage Status at {self.env.now}] SSD: {stats['ssd_percent']:.2f}% ({stats['ssd_files']} files) | RAM: {stats['ram_percent']:.2f}% ({stats['ram_files']} files)")
