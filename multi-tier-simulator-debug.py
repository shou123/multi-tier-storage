import simpy
import Trace
import settings
import threading
import time
import signal
import sys

def timeout_handler(signum, frame):
    print("Simulation timeout - likely stuck waiting for input!")
    print("The program is waiting for input from stdin.")
    print("Try running with: python multi-tier-simulator.py < your_trace_file.txt")
    sys.exit(1)

def progress_monitor():
    """Monitor simulation progress"""
    start_time = time.time()
    print("Simulation started... Monitoring progress every 3 seconds")
    while True:
        time.sleep(3)
        elapsed = time.time() - start_time
        print(f"Still running... Elapsed time: {elapsed:.1f}s")
        if elapsed > 15:  # If running more than 15 seconds, likely stuck
            print("WARNING: Simulation taking longer than expected!")
            print("This might indicate it's waiting for stdin input.")

def start_environment():
    # Set up timeout handler
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(10)  # 10 second timeout
    
    print("Creating SimPy environment...")
    env = simpy.Environment()
    print(f"Creating HDD resources (capacity: {settings.NUMBER_HDD})...")
    concurrent_access_hdd = simpy.Resource(env, capacity=settings.NUMBER_HDD)
    print(f"Creating SSD resources (capacity: {settings.NUMBER_SSD})...")
    concurrent_access_ssd = simpy.Resource(env, capacity=settings.NUMBER_SSD)
    print("Creating Trace object...")
    trace = Trace.Trace(env, concurrent_access_hdd, concurrent_access_ssd)
    
    print("Starting trace source process...")
    env.process(trace.source_trace(settings.DELIMITER, settings.COLUMN_ID, settings.COLUMN_TIMESTAMP, settings.COLUMN_SIZE_FILE,
                                   settings.COLUMN_TYPE_REQUEST))
    
    # Start progress monitor in background
    monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
    monitor_thread.start()
    
    print("About to call env.run() - this will block if waiting for stdin...")
    print("If stuck here, the simulation is waiting for input data from stdin")
    
    try:
        env.run()
        signal.alarm(0)  # Cancel timeout
        print("Simulation completed successfully!")
    except Exception as e:
        print(f"Simulation failed with error: {e}")
        return
    
    # Calculate and display results
    avg_served_time_HDD = 0
    avg_served_time_SSD = 0
    nanosecond_to_milisecond = 1 / float(1000 * 1000)
    if Trace.READS_HDD > 0:
        avg_served_time_HDD = Trace.HDD_SERVED_TIME / float(Trace.READS_HDD + Trace.WRITES_HDD)
        avg_served_time_HDD = round(avg_served_time_HDD, 5)
    if Trace.READS_SSD > 0:
        avg_served_time_SSD = Trace.SSD_SERVED_TIME / float(Trace.READS_SSD + Trace.WRITES_HDD)
        avg_served_time_SSD = round(avg_served_time_SSD, 5)
    
    total_served_time_HDD = Trace.HDD_SERVED_TIME
    total_served_time_SSD = Trace.SSD_SERVED_TIME
    total_operations = Trace.READS_RAM + Trace.READS_HDD + Trace.READS_SSD + Trace.WRITES_HDD + Trace.WRITES_SSD
    
    summary = "Total of operations at file's traces:  " + str(total_operations) + '\n'
    summary = summary + 'Total of devices in HDD tier:       ' + str(settings.NUMBER_HDD) + '\n'
    summary = summary + 'Total of devices in SSD tier:       ' + str(settings.NUMBER_SSD) + '\n'
    summary = summary + 'Numbers of Reads in RAM:            ' + str(Trace.READS_RAM) + '\n' + 'Numbers of Reads in HDDs tier:      ' + str(Trace.READS_HDD) + '\n'
    summary = summary + 'Numbers of Reads in SSDs tier:      ' + str(Trace.READS_SSD) + '\n' + 'Number of Writes in HDDs tier:      ' + str(Trace.WRITES_HDD) + '\n'
    summary = summary + 'Numbers of Writes in SSDs tier:     ' + str(Trace.WRITES_SSD) + '\n' + 'Total Served Time in HDDs tier:     ' + str(total_served_time_HDD) + ' [ms]' + '\n'
    summary = summary + 'Total Served Time in SSDs tier:     ' + str(total_served_time_SSD) + ' [ms]' + '\n'
    summary = summary + 'Average Served Time in HDDs tier:   ' + str(avg_served_time_HDD) + ' [ms]' + '\n'
    summary = summary + 'Average Served Time in SSDs tier:   ' + str(avg_served_time_SSD) + ' [ms]'
    
    with open('summary.txt', 'w') as f:
        f.write(summary)
    
    print("Results saved to summary.txt")

if __name__ == "__main__":
    print("Multi-tier Storage Systems Simulator")
    print("=====================================")
    print("NOTE: This program reads trace data from stdin")
    print("Usage: python multi-tier-simulator-debug.py < trace_file.txt")
    print()
    
    start_environment()