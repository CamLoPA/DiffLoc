import warnings
warnings.filterwarnings("ignore")
import sys
sys.path.append('/home/pi/PJ0/csitool')
import subprocess
import time
import numpy as np
import csitools
from csitool.passband import lowpass
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from csitool.read_pcap import NEXBeamformReader
from scipy.optimize import fsolve
import RPi.GPIO as GPIO
import time
import subprocess

# setting GPIO

def run_command(command):
    print(f"Running command: {' '.join(command)}")
    subprocess.run(command)

def start_tcpdump():
    tcpdump_process = subprocess.Popen(['sudo', 'timeout', '7', 'tcpdump', '-i', 'wlan0', 'dst', 'port', '5500', '-w', 'capture.pcap'])
    return tcpdump_process

def run_motor_and_record_steps(revolutions, filename):
    GPIO.setmode(GPIO.BCM)
    control_pins = [6, 13, 19, 26]  
    for pin in control_pins:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, 0)

    halfstep_seq = [
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [0, 1, 0, 0],
        [0, 1, 1, 0],
        [0, 0, 1, 0],
        [0, 0, 1, 1],
        [0, 0, 0, 1],
        [1, 0, 0, 1]
    ]

    steps_per_revolution = 256
    steps = steps_per_revolution * revolutions
    timestamps = []

    with open(filename, 'w') as file:
        for step in range(steps):
            timestamp = time.time()
            timestamps.append(timestamp)

            file.write(f"{timestamp}\n")

            for halfstep in range(8):
                for pin in range(4):
                    GPIO.output(control_pins[pin], halfstep_seq[halfstep][pin])
                time.sleep(0.0015)

    return timestamps

def remove_data_with_high_variance(data):
    data = np.array(data)
    
    for i in range(len(data) - 2, -1, -1):
        variance = np.var(data[i:])
        
        if variance > 2:
            return data[0:i]
            break

def find_closest_timestamp(target, timestamps):

    return np.argmin(np.abs(np.array(timestamps) - target))

def find_troughs(csi_data, timestamp, time_window=0.5):

    troughs = []
    n = len(csi_data)

    cpar = 0.2*(np.min(csi_data))
    
    for i in range(n):
        start_idx = find_closest_timestamp(timestamp[i] - time_window,timestamp)
        end_idx = find_closest_timestamp(timestamp[i] + time_window,timestamp)

        if csi_data[i] <= np.min(csi_data[start_idx:end_idx]) and csi_data[i] <= cpar:
            troughs.append(i)
                
    return np.array(troughs)

def process_csi_data(csi_data, csi_timestamps, timestamp_file):
    with open(timestamp_file, 'r') as f:
        file_timestamps = np.array([float(line.strip()) for line in f])

    ts_512 = file_timestamps[255]
    closest_idx = find_closest_timestamp(ts_512, csi_timestamps)
    ts_1 = file_timestamps[0] 
    start_idx = find_closest_timestamp(ts_1, csi_timestamps)

    csi_part1 = csi_data[start_idx+1:closest_idx+1]
    print(start_idx)

    ts_part1 = csi_timestamps[start_idx+1:closest_idx+1]

    troughs1 = find_troughs(csi_part1,csi_timestamps)

    if len(troughs1) == 0:
        raise ValueError("No trough")

    idxtrough1 = np.argmin(csi_part1[troughs1])
    trough1 = troughs1[idxtrough1]

    ts_trough1 = ts_part1[trough1]

    idx_trough1_in_B = find_closest_timestamp(ts_trough1, file_timestamps)
    C_time = ts_trough1
    print(C_time)

    if len(troughs1) > 1:
        if trough1==min(troughs1):
            ts_ca = ts_part1[troughs1[idxtrough1+1]]
            csi_nex=csi_part1[troughs1[idxtrough1+1]]
            peak1 = np.max(csi_part1[trough1:troughs1[idxtrough1+1]])
        elif trough1 < max(troughs1) and abs(ts_part1[trough1]-ts_part1[troughs1[idxtrough1+1]]) < abs(ts_part1[trough1]-ts_part1[troughs1[idxtrough1-1]]):
            ts_ca = ts_part1[troughs1[idxtrough1+1]]
            csi_nex=csi_part1[troughs1[idxtrough1+1]]
            peak1 = np.max(csi_part1[trough1:troughs1[idxtrough1+1]])
        else:
            ts_ca = ts_part1[troughs1[idxtrough1-1]]
            csi_nex=csi_part1[troughs1[idxtrough1-1]]
            peak1 = np.max(csi_part1[troughs1[idxtrough1-1]:trough1])
        max_csi = np.max(csi_part1)
        min_csi = np.min(csi_part1)
        if (abs(csi_part1[trough1]-csi_nex) < 0.4 * (max_csi-min_csi)) and (np.abs(ts_trough1 - ts_ca) < 1.5):
            C_time = (ts_trough1 + ts_ca) / 2
        else:
            C_time = ts_trough1
    print(C_time)

    angtimestamp = find_closest_timestamp(C_time, file_timestamps)
    ang = (angtimestamp/512- int(angtimestamp/512))*360
    
    return ang

def main():
    '''if len(sys.argv) != 3:
        print(f"Usage: python3 location.py <mac> <channel>")
        sys.exit(1)'''

    mac = '78:8B:2A:52:3A:6A'
    channel = '6'

    # Run setup command
    setup_command = [
        'sudo', 'bash', 'setup.sh', '--laptop-ip', 'None', '--raspberry-ip', 'None',
        '--mac-adr', mac, '--channel', channel, '--bandwidth', '20', '--core', '1', '--spatial-stream', '1'
    ]
    run_command(setup_command)
    
    tcpdump_process = start_tcpdump()
    time.sleep(2)
    timestamp_filename = 'timestamps.txt'
    timestamp_filename1 = 'timestamps1.txt'
    timestamps = run_motor_and_record_steps(1, timestamp_filename)
    time.sleep(2)
    print("Time stamps saved to {timestamp_filename}")
    tcpdump_process.terminate()
    GPIO.cleanup()
    datapath = r'capture.pcap'
    my_reader = NEXBeamformReader()
    csi_data = my_reader.read_file(datapath,scaled=True)
    csi_matrix, no_frames, no_subcarriers = csitools.get_CSI(csi_data)
    csi_matrix_first = csi_matrix[:, :, 0, 0]
    csi_matrix_first[csi_matrix_first == -np.inf] = np.nan
    imp_mean = SimpleImputer(missing_values=np.nan, strategy='mean')
    csi_matrix_first = imp_mean.fit_transform(csi_matrix_first)
    # Then we'll squeeze it to remove the singleton dimensions.
    csi_matrix_squeeze = np.squeeze(csi_matrix_first)
    csi_matrix_squeezed = np.transpose(csi_matrix_squeeze)
    for x in range(no_subcarriers-1):
        csi_matrix_squeezed[x] = lowpass(csi_matrix_squeezed[x], 3, 50, 5)

    x = csi_data.timestamps
    row_means = np.min(csi_matrix_squeezed, axis=1)
    top_5_indices = np.argsort(row_means)[:5]
    top_5_rows = csi_matrix_squeezed[top_5_indices]
    sum_top_5_rows = np.sum(top_5_rows, axis=0)
    csi_mean = sum_top_5_rows - np.mean(sum_top_5_rows)
    csi_mean = remove_data_with_high_variance(csi_mean)

    result_timestamp = process_csi_data(csi_mean, x, r'timestamps.txt')
    print("Azimuth:", result_timestamp)
    timestamps = run_motor_and_record_steps(1, timestamp_filename1)

if __name__ == "__main__":
    main()
