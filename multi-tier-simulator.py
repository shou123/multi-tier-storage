import simpy
import Trace
import settings

def start_environment():
    env = simpy.Environment()
    concurrent_access_hdd = simpy.Resource(env, capacity=settings.NUMBER_HDD)
    concurrent_access_ssd = simpy.Resource(env, capacity=settings.NUMBER_SSD)
    trace = Trace.Trace(env, concurrent_access_hdd, concurrent_access_ssd)
    
    # Choose trace format based on replacement policy
    if settings.REPLACEMENT_POLICY.lower() in ['rl_c51', 'all_ram', 'all_ssd', 'all_hdd']:
        # These policies use the new trace format: timestamp, operation, LBA, block_size, seq/rand, inter_arrival, service_time, idle_time
        env.process(trace.source_trace_rl(file_path=settings.FILE_PATH))
    else:
        # Legacy policies use old format: timestamp, id, size, type
        env.process(trace.source_trace(settings.DELIMITER, settings.COLUMN_ID, settings.COLUMN_TIMESTAMP, settings.COLUMN_SIZE_FILE,
                                       settings.COLUMN_TYPE_REQUEST, file_path=settings.FILE_PATH))
    env.run()
    
    # NEW: Shutdown unified agent system
    trace.agent_system.shutdown()
    
    # Print storage status after simulation completes
    print("\n" + "="*80)
    trace.print_storage_status()
    print("="*80 + "\n")
    
    # Get migration statistics from unified agent system
    migration_stats = trace.agent_system.get_statistics()
    
    avg_served_time_HDD = 0
    avg_served_time_SSD = 0
    avg_served_time_RAM = 0
    nanosecond_to_milisecond = 1 / float(1000 * 1000)
    ms_to_seconds = 1 / float(1000)  # Convert milliseconds to seconds
    if Trace.READS_RAM + Trace.WRITES_RAM > 0:
        avg_served_time_RAM = Trace.RAM_SERVED_TIME / float(Trace.READS_RAM + Trace.WRITES_RAM)
        avg_served_time_RAM = round(avg_served_time_RAM, 5)
    if Trace.READS_HDD > 0:
        avg_served_time_HDD = Trace.HDD_SERVED_TIME / float(Trace.READS_HDD + Trace.WRITES_HDD)
        avg_served_time_HDD = round(avg_served_time_HDD, 5)
    if Trace.READS_SSD > 0:
        avg_served_time_SSD = Trace.SSD_SERVED_TIME / float(Trace.READS_SSD + Trace.WRITES_SSD)
        avg_served_time_SSD = round(avg_served_time_SSD, 5)
    total_served_time_RAM = Trace.RAM_SERVED_TIME
    total_served_time_HDD = Trace.HDD_SERVED_TIME
    total_served_time_SSD = Trace.SSD_SERVED_TIME

    # Convert to seconds and hours
    seconds_to_hours = 1 / float(3600)  # Convert seconds to hours
    total_served_time_RAM_sec = round(total_served_time_RAM * ms_to_seconds, 5)
    total_served_time_HDD_sec = round(total_served_time_HDD * ms_to_seconds, 5)
    total_served_time_SSD_sec = round(total_served_time_SSD * ms_to_seconds, 5)
    avg_served_time_RAM_sec = round(avg_served_time_RAM * ms_to_seconds, 5)
    avg_served_time_HDD_sec = round(avg_served_time_HDD * ms_to_seconds, 5)
    avg_served_time_SSD_sec = round(avg_served_time_SSD * ms_to_seconds, 5)
    
    # Convert to hours
    total_served_time_RAM_hour = round(total_served_time_RAM_sec * seconds_to_hours, 5)
    total_served_time_HDD_hour = round(total_served_time_HDD_sec * seconds_to_hours, 5)
    total_served_time_SSD_hour = round(total_served_time_SSD_sec * seconds_to_hours, 5)
    avg_served_time_RAM_hour = round(avg_served_time_RAM_sec * seconds_to_hours, 5)
    avg_served_time_HDD_hour = round(avg_served_time_HDD_sec * seconds_to_hours, 5)
    avg_served_time_SSD_hour = round(avg_served_time_SSD_sec * seconds_to_hours, 5)

    total_operations = Trace.READS_RAM + Trace.WRITES_RAM + Trace.READS_HDD + Trace.READS_SSD + Trace.WRITES_HDD + Trace.WRITES_SSD
    summary = "Total of operations at file's traces:  " + str(total_operations) + '\n'
    # summary = summary + 'Total of devices in HDD tier:       ' + str(settings.NUMBER_HDD) + '\n'
    # summary = summary + 'Total of devices in SSD tier:       ' + str(settings.NUMBER_SSD) + '\n'

    summary = summary + 'Numbers of Reads in RAM:            ' + str(Trace.READS_RAM) + '\n'
    summary = summary + 'Numbers of Writes in RAM:           ' + str(Trace.WRITES_RAM) + '\n'
    summary = summary + 'Numbers of Reads in SSDs tier:      ' + str(Trace.READS_SSD) + '\n'
    summary = summary + 'Numbers of Writes in SSDs tier:     ' + str(Trace.WRITES_SSD) + '\n'
    summary = summary + 'Numbers of Reads in HDDs tier:      ' + str(Trace.READS_HDD) + '\n'
    summary = summary + 'Numbers of Writes in HDDs tier:     ' + str(Trace.WRITES_HDD) + '\n'

    summary = summary + 'Total Served Time in RAM tier:      ' + str(total_served_time_RAM_hour) + ' [h]' + '\n'
    summary = summary + 'Total Served Time in SSDs tier:     ' + str(total_served_time_SSD_hour) + ' [h]' + '\n'
    summary = summary + 'Total Served Time in HDDs tier:     ' + str(total_served_time_HDD_hour) + ' [h]' + '\n'

    summary = summary + 'Average Served Time in RAM tier:    ' + str(avg_served_time_RAM_hour) + ' [h]' + '\n'
    summary = summary + 'Average Served Time in SSDs tier:   ' + str(avg_served_time_SSD_hour) + ' [h]' + '\n'
    summary = summary + 'Average Served Time in HDDs tier:   ' + str(avg_served_time_HDD_hour) + ' [h]' + '\n'
    
    # NEW: Add Data Migration Statistics (LBA-based)
    summary = summary + '\n# Data Migration Statistics (LBA-based)\n'
    summary = summary + 'Total LBAs Tracked:                 ' + str(migration_stats['total_lbas_tracked']) + '\n'
    summary = summary + 'Hot LBAs (access >= 5):             ' + str(migration_stats['hot_lbas']) + '\n'
    summary = summary + 'Cold LBAs (access <= 1):            ' + str(migration_stats['cold_lbas']) + '\n'
    summary = summary + 'Total LBA Operations:               ' + str(migration_stats['total_lba_operations']) + '\n'
    summary = summary + 'LBAs Migrated:                      ' + str(migration_stats['lbas_migrated']) + '\n'
    summary = summary + 'Total Migrations Across LBAs:       ' + str(migration_stats['total_migrations_across_lbas']) + '\n'
    summary = summary + 'Migrations Enqueued:                ' + str(migration_stats['migrations_enqueued']) + '\n'
    summary = summary + 'Migrations Completed:               ' + str(migration_stats['migrations_completed']) + '\n'
    summary = summary + 'Total I/O Requests:                 ' + str(migration_stats['total_requests']) + '\n'
    summary = summary + 'Avg Reward:                         ' + str(round(migration_stats['avg_reward'], 5)) + '\n'
    summary = summary + 'Migration Queue Size:               ' + str(migration_stats['queue_size']) + '\n'
    summary = summary + 'Queue Full:                         ' + str(migration_stats['queue_full'])

    # print summary
    with open('summary_migration_info.txt', 'w') as f:
        f.write(summary)

start_environment()