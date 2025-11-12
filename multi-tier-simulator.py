import simpy
import Trace
import settings

def start_environment():
    env = simpy.Environment()
    concurrent_access_hdd = simpy.Resource(env, capacity=settings.NUMBER_HDD)
    concurrent_access_ssd = simpy.Resource(env, capacity=settings.NUMBER_SSD)
    trace = Trace.Trace(env, concurrent_access_hdd, concurrent_access_ssd)
    
    # Choose trace format based on replacement policy
    if settings.REPLACEMENT_POLICY.lower() == 'rl_c51':
        # RL policy uses new trace format: operation, LBA, block_size, inter_arrival, service_time, idle_time
        env.process(trace.source_trace_rl(file_path=settings.FILE_PATH))
    else:
        # Legacy policies use old format: timestamp, id, size, type
        env.process(trace.source_trace(settings.DELIMITER, settings.COLUMN_ID, settings.COLUMN_TIMESTAMP, settings.COLUMN_SIZE_FILE,
                                       settings.COLUMN_TYPE_REQUEST, file_path=settings.FILE_PATH))
    env.run()
    
    # Print storage status after simulation completes
    print("\n" + "="*80)
    trace.print_storage_status()
    print("="*80 + "\n")
    
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
    summary = summary + 'Average Served Time in HDDs tier:   ' + str(avg_served_time_HDD_hour) + ' [h]'

    # print summary
    with open('summary.txt', 'w') as f:
        f.write(summary)

start_environment()