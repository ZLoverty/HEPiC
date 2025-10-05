"""
receive_ip.py
=============

Receive string from a specified IP and port.

"""
import socket

# Configure server
HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 12345      # Port to listen on (non-privileged ports are > 1023)

# 1. Create a UDP socket
#    socket.SOCK_DGRAM is the key part for specifying UDP
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    
    # 2. Bind the socket to the address and port
    s.bind((HOST, PORT))
    print(f"UDP server listening on {HOST}:{PORT}...")
    
    # 3. Wait to receive data
    #    recvfrom() blocks until a packet is received.
    #    It returns the data (bytes) and the address of the sender.
    while True:
        data_bytes, address = s.recvfrom(1024) # Buffer size is 1024 bytes
        
        # 4. Decode the bytes into a string
        received_string = data_bytes.decode('utf-8')
        
        print(f"Received string: '{received_string}' from {address}")
        
        # 5. (Optional) Send a reply back to the client's address
        # reply_message = "Message received!".encode('utf-8')
        # s.sendto(reply_message, address)