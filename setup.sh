#!/bin/bash

if [ "$EUID" -ne 0 ]
  then echo "Please run as root (with sudo)"
  exit 1
fi

helpFunction()
{
   echo ""
   echo "Usage: $0 --laptop-ip ip --raspberry-ip ip --mac-adr MAC --channel channel --bandwidth bandwidth"
   echo -e "\t --laptop-ip \t ip of the laptop to forward packets to it (place None for no forwarding)"
   echo -e "\t --raspberry-ip  ip of the raspberry pi itself to forward packets (place None for no forwarding)"
   echo -e "\t --mac-adr  MAC addrress of the transmitter device"
   echo -e "\t --channel \t channel"
   echo -e "\t --bandwidth \t bandwidth"
   echo -e "\t --core \t core"
   echo -e "\t --spatial-stream \t spatial stream"
   exit 1 # Exit script after printing help
}

while [ $# -gt 0 ] ; do
  case $1 in
    --laptop-ip) LAPTOPIP="$2" ;;
    --raspberry-ip) RASPBERRYIP="$2" ;;
    --mac-adr) MACADR="$2" ;;
    --channel) CHANNEL="$2" ;;
    --bandwidth) BANDWIDTH="$2" ;;
    --core) CORE="$2" ;;
    --spatial-stream) SPATIALSTREAM="$2" ;;
  esac
  shift
done

# Print helpFunction in case parameters are empty
if [ -z "$LAPTOPIP" ] || [ -z "$RASPBERRYIP" ] || [ -z "$MACADR" ] || [ -z "$CHANNEL" ] || [ -z "$BANDWIDTH" ] || [ -z "$CORE" ] || [ -z "$SPATIALSTREAM" ]
then
   echo "Some or all of the required parameters are empty - see help:";
   helpFunction
fi

# echo $LAPTOPIP $RASPBERRYIP $MACADR, $CHANNEL $BANDWIDTH

MCPOUT=$(mcp -C $CORE -N $SPATIALSTREAM -c $CHANNEL/$BANDWIDTH -m $MACADR)
STATUS=$?
if [ $STATUS -eq 0 ]; then
    echo "mcp command -> Finished Successfully"
else
    echo "mcp command -> Error"
    exit 1
fi

ifconfig wlan0 up
STATUS=$?
if [ $STATUS -eq 0 ]; then
    echo "ifconfig command -> Finished Successfully"
else
    echo "ifconfig command -> Error"
    exit 1
fi

nexutil -Iwlan0 -s500 -b -l34 -v$MCPOUT
STATUS=$?
if [ $STATUS -eq 0 ]; then
    echo "nexutil command -> Finished Successfully"
else
    echo "nexutil command -> Error"
    exit 1
fi

iw dev wlan0 interface add mon0 type monitor
STATUS=$?
if [ $STATUS -eq 0 ]; then
    echo "iw command -> Finished Successfully"
elif [ $STATUS -eq 161 ]; then
    echo "iw command -> Finished Successfully (Already up)"
else
    echo "iw command -> Error"
    exit 1
fi

ip link set mon0 up
STATUS=$?
if [ $STATUS -eq 0 ]; then
    echo "ip command -> Finished Successfully"
else
    echo "ip command -> Error"
    exit 1
fi

if [[ "$LAPTOPIP" == "None" ]] || [[ "$RASPBERRYIP" == "None" ]]
then
   echo "Raspberry pi is sucessfully setuped you can test with 'sudo tcpdump -i wlan0 dst port 5500' to see if you can receive the packets on raspberri pi"
   exit 0
fi

echo "Forwarding packets on from $RASPBERRYIP (raspberry) to $LAPTOPIP (laptop)"

if [[ $(sudo nft list tables) == *"nexmon"* ]]
then
    sudo nft delete table nexmon
fi
nft add table ip nexmon
nft 'add chain ip nexmon input  { type filter hook input  priority -150; policy accept; }'
nft 'add chain ip nexmon output { type filter hook output priority  150; policy accept; }'
nft add rule ip nexmon input  iifname "wlan0" ip protocol udp ip saddr 10.10.10.10 ip daddr 255.255.255.255 udp sport 5500 udp dport 5500 counter mark set 1 dup to $LAPTOPIP device "eth0"
nft add rule ip nexmon output oifname "eth0"  meta mark 1 counter ip saddr set $RASPBERRYIP ip daddr set $LAPTOPIP
