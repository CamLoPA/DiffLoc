import subprocess
import dpkt
import os
import time
from tqdm import tqdm
import socket
import numpy as np

def scan_wifi():
    print("Scanning for WiFi networks...")
    scan_result = subprocess.run(['sudo', 'iwlist', 'wlan0', 'scan'], capture_output=True, text=True)
    scan_output = scan_result.stdout.splitlines()

    networks = []
    current_network = {}
    for line in scan_output:
        line = line.strip()
        if "Cell" in line:
            if 'BSSID' in current_network and 'ESSID' in current_network and 'Channel' in current_network and 'RSSI' in current_network:
                networks.append(current_network)
            current_network = {}
        if "Address:" in line:
            current_network['BSSID'] = line.split()[-1]
        if "Channel:" in line:
            current_network['Channel'] = line.split(':')[-1].strip('"')
        if "ESSID:" in line:
            current_network['ESSID'] = line.split(':')[1].strip('"')
        if "Quality=" in line:
            rssi = line.split('=')[1].split()[0]
            quality = rssi.split('/')
            rssi_value = int(quality[0]) - int(quality[1])
            current_network['RSSI'] = rssi_value

    if 'BSSID' in current_network and 'ESSID' in current_network and 'Channel' in current_network and 'RSSI' in current_network:
        networks.append(current_network)

    print("\nAvailable Networks (RSSI > -39dBm):")
    for i, network in enumerate(networks):
        if network['RSSI'] > -39:
            print(f"{i}: BSSID: {network['BSSID']}, Channel: {network['Channel']}, RSSI: {network['RSSI']}, ESSID: {network['ESSID']}")

    return [network for network in networks if network['RSSI'] > -39]

def set_channel(channel):
    subprocess.run(['sudo', 'iwconfig', 'wlan2mon', 'channel', channel])
    print(f"Set wlan2mon to channel {channel}")

def start_capture(filename='capture.pcap',duration=None):
    if duration:
        print(f"Starting packet capture for {duration} seconds...")
        tcpdump_process = subprocess.Popen(['sudo', 'timeout', str(duration), 'tcpdump', '-i', 'wlan2mon', '-w', filename])
        time.sleep(duration)
        tcpdump_process.terminate()
        tcpdump_process.wait()
        subprocess.run(['sudo', 'cp', 'capture.pcap', 'captured.pcap'])
        subprocess.run(['sudo', 'rm', 'capture.pcap'])
    else:
        print(f"Starting packet capture for {duration} seconds...")
        '''tcpdump_process = subprocess.Popen(['sudo', 'tcpdump', '-i', 'wlan2mon', '-w', filename])
        return tcpdump_process'''
        tcpdump_process = subprocess.Popen(['sudo', 'timeout', '15', 'tcpdump', '-i', 'wlan2mon', '-w', filename])
        time.sleep(10)
        tcpdump_process.terminate()
        tcpdump_process.wait()
        subprocess.run(['sudo', 'cp', 'capture.pcap', 'deep_captured.pcap'])
        subprocess.run(['sudo', 'rm', 'capture.pcap'])

def stop_capture(proc):
    proc.terminate()
    proc.wait()
    subprocess.run(['sudo', 'cp', 'capture.pcap', 'captured.pcap'])
    subprocess.run(['sudo', 'rm', 'capture.pcap'])
    print("Packet capture stopped.")

def mac_addr_to_str(mac_addr):
    return ':'.join('%02x' % b for b in mac_addr)

def analyze_pcap(filename):
    print("Analyzing pcap file...")
    with open(filename, 'rb') as f:
        pcap = dpkt.pcap.Reader(f)

        packets_by_mac = {}
        total_packets = 0

        for timestamp, buf in tqdm(pcap):
            total_packets += 1
            try:
                radiotap = dpkt.radiotap.Radiotap(buf)
                wlan = radiotap.data
                type_subtype = wlan.type << 2 | wlan.subtype
                src_mac = mac_addr_to_str(wlan.data_frame.src)
                if src_mac not in packets_by_mac:
                    packets_by_mac[src_mac] = []
                if type_subtype == 0x08:
                    packets_by_mac[src_mac].append((timestamp, len(wlan.data)))
            except (dpkt.dpkt.NeedData, dpkt.dpkt.UnpackError, AttributeError):
                continue

    print(f"Total packets captured: {total_packets}")
    return packets_by_mac, total_packets

def detect_suspicious_devices(packets_by_mac, router_mac):
    suspicious_devices = []
    for mac, packets in packets_by_mac.items():
        total_length = sum(length for _, length in packets)
        avg_length = total_length / (len(packets)+1)
        if avg_length > 150 and mac[:-1] != router_mac[:-1] and len(packets)>50:
            suspicious_devices.append((mac, len(packets), avg_length))

    return suspicious_devices

def send_suspicious_devices_to_macos(suspicious_devices):
    macos_ip = "192.168.31.68"  # Replace with macOS IP address
    macos_port = 12345
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((macos_ip, macos_port))
        for device in suspicious_devices:
            data = ','.join(map(str, device))
            s.sendall(data.encode())
            s.sendall(b'\n')

def deep_analysis(file, device_mac):
    print(f"Performing deep analysis on {device_mac}...")
    with open(file, 'rb') as f:
        pcap = dpkt.pcap.Reader(f)

        packet_times = []
        packet_lengths = []

        for timestamp, buf in tqdm(pcap):
            try:
                radiotap = dpkt.radiotap.Radiotap(buf)
                wlan = radiotap.data
                type_subtype = wlan.type << 2 | wlan.subtype
                src_mac = mac_addr_to_str(wlan.data_frame.src)
                if src_mac == device_mac and type_subtype == 0x08:
                    packet_times.append(timestamp)
                    packet_lengths.append(len(wlan.data))
            except (dpkt.dpkt.NeedData, dpkt.dpkt.UnpackError, AttributeError):
                continue

    if not packet_times:
        return False, 0, 0

    packet_times.sort()
    segments = 15
    segment_size = (packet_times[-1] - packet_times[0]) / segments
    throughputs = [0] * segments

    for i in range(len(packet_times)):
        segment_index = int((packet_times[i] - packet_times[0]) / segment_size)
        if segment_index >= segments:
            segment_index = segments - 1
        throughputs[segment_index] += packet_lengths[i]

    avg_throughput = sum(throughputs) / segments
    if 0.25 * (throughputs[1] + throughputs[2] + throughputs[3] + throughputs[4]) >= 1.1 * 0.25 * (throughputs[11] + throughputs[12]+throughputs[13] + throughputs[14]):
        return 0, (throughputs[1] + throughputs[2] + throughputs[3] + throughputs[4]) / ((throughputs[11] + throughputs[12]+throughputs[13] + throughputs[14]))
    elif 0.25 * (throughputs[1] + throughputs[2] + throughputs[3] + throughputs[4]) >= 0.95 * 0.25 * (throughputs[11] + throughputs[12]+throughputs[13] + throughputs[14]):
        return 1, (throughputs[1] + throughputs[2] + throughputs[3] + throughputs[4]) / ((throughputs[11] + throughputs[12]+throughputs[13] + throughputs[14]))

    return 2, (throughputs[1] + throughputs[2] + throughputs[3] + throughputs[4]) / ((throughputs[11] + throughputs[12]+throughputs[13] + throughputs[14]))

def call_location_script(dangerous_devices, channel):
    try:
        subprocess.run(['python', 'locationfu.py', dangerous_devices, str(channel)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to execute location.py for MAC: {dangerous_devices}, Channel: {channel}. Error: {e}")

def main():
    networks = scan_wifi()
    if not networks:
        print("No networks found. Exiting...")
        return

    for network in networks:
        bssid = network['BSSID']
        channel = network['Channel']
        essid = network['ESSID']
        rssi = network['RSSI']

        if rssi > -39:
            print(f"Scanning network: ESSID: {essid}, BSSID: {bssid}, Channel: {channel}, RSSI: {rssi}")
            set_channel(channel)
            time.sleep(1)
            start_capture('capture.pcap',duration=5)

            packets_by_mac, total_packets = analyze_pcap('captured.pcap')

            suspicious_devices = detect_suspicious_devices(packets_by_mac, bssid)

            if suspicious_devices:
                print("\033[31mSuspicious devices found:\033[0m")
                for mac, count, avg_length in suspicious_devices:
                    print(f"\033[31m\033[47m\033[1mMAC: {mac}, Packet Count: {count}, Avg Packet Length: {avg_length}\033[0m")
                    print("Re-capturing packets for suspicious devices...")
                    input("Press Enter to start capturing packets...")
                    tcpdump_proc = start_capture('capture.pcap')
                    #stop_capture('deepcapture.pcap',tcpdump_proc)
                    is_dangerous, throughputs = deep_analysis('deep_captured.pcap', mac)
                    if is_dangerous == 0:
                        print(f"\033[31m\033[47m\033[1mDangerous device detected! MAC: {mac}, Dangerousness: {throughputs}\033[0m")
                        call_location_script(mac, channel)
                    elif is_dangerous == 1:
                        print(f"\033[33m\033[47m\033[1mDangerous device detected! MAC: {mac}, Dangerousness: {throughputs}\033[0m")
                        call_location_script(mac, channel)
                    else:
                        print(f"Device {mac} is not dangerous. Throughputs: {throughputs}")
            else:
                print("No suspicious devices found.")

if __name__ == "__main__":
    main()

