import socket
import logging
import time
from numpy import uint32
from threading import Timer

import ipaddress
import packet as packet

WINDOW = 8
FRAME_SIZE = 1024
RECV_TIME_OUT = 5
HANDSHAKE_TIME_OUT = 2
SLIDE_TIME = 0.1

log = logging.getLogger('ARQ')
fh = logging.FileHandler('debug.log')
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(levelname)s] >> %(message)s << %(funcName)s() %(asctime)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
log.setLevel(logging.DEBUG)
log.addHandler(fh)
log.addHandler(ch)

class udp_socket():

    def __init__(self, router=('localhost', 3000), sequence = 0):
        self.router = router
        self.sequence = uint32(sequence)
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.remote = None
        self.shakeack = None
        self.data = list()
        self.control = list()
        self.client_list = list()

    def connect(self, address):
        try:
            self.remote = self.handshaking(address, self.sequence)
            self.sequence = packet.grow_sequence(self.sequence, 1)
        except HandShakeException as e:
            log.error(e)
            raise e

    def listen(self, max):
        self.MAX = max

    def handshaking(self, address, sequence):
        peer_ip = ipaddress.ip_address(socket.gethostbyname(address[0]))
        log.debug(peer_ip)
        self.conn.connect(self.router)
        for i in range(0, 20):
            try:
                self.conn.sendall(packet.control_package(packet.SYN, peer_ip, address[1], sequence).to_bytes())
                self.conn.settimeout(HANDSHAKE_TIME_OUT)
                data, route = self.conn.recvfrom(FRAME_SIZE)
                p = packet.Packet.from_bytes(data)
                log.debug("Router:{}".format(route))
                log.debug("Packet:{}".format(p))
                log.debug("Payload:{}".format(p.payload.decode("utf-8")))
                self.shakeack = packet.control_package(packet.SYN_ACK, p.peer_ip_addr, p.peer_port, sequence).to_bytes()
                self.conn.sendall(packet.control_package(packet.SYN_ACK, p.peer_ip_addr, p.peer_port, sequence).to_bytes())
                return p.peer_ip_addr, p.peer_port

            except Exception as e:
                log.error(e)
            time.sleep(1)
        raise HandShakeException("Hand shake timeout")

    def accept(self):
        try:
            data, route = self.conn.recvfrom(1024)  # buffer size is 1024 bytes

            p = packet.Packet.from_bytes(data)
            print("Router: ", route)
            print("Packet: ", p)
            print("Payload: ", p.payload.decode("utf-8"))
            if len(self.client_list) > self.MAX:
                return None, None
            if p.packet_type == packet.SYN:
                return self.accept_client(p)
        except socket.timeout as e:
            log.error(e)
            return None, None

    def accept_client(self, p):
        print("create a new thread")
        sock = udp_socket()
        sock.conn.sendto(packet.control_package(packet.SYN_ACK, p.peer_ip_addr, p.peer_port, p.seq_num).to_bytes(),
                         self.router)
        print("send SYN-ACK")

        recv_list = list()
        if p.packet_type == packet.SYN:
            sock.sequence = packet.grow_sequence(p.seq_num, 1)
            sock.remote = (p.peer_ip_addr, p.peer_port)
            sock.conn.connect(self.router)
            print("receive ACK, sequence #:" + str(p.seq_num))
            # print("Router: ", route)
            print("Packet: ", p)
            print("Payload: ", p.payload.decode("utf-8"))
            return sock, (p.peer_ip_addr, p.peer_port)
        return None, None
    def findIndex(self, window, se):
        for i in range(0, len(window)):
            if window[i] == se or (isinstance(window[i], packet.Packet) and window[i].seq_num == se):
                return i

    def getwindows(self, window):
        windows = [i for i in window]
        for i in range(0, len(windows)):
            if isinstance(windows[i], packet.Packet):
                windows[i] = str(windows[i].seq_num)
        return windows

    def flushwindow(self, window):
        for i in range(0, len(window)):
            if isinstance(window[i], packet.Packet):
                return False
        return True

    def recvall(self):
        start = time.time()
        packages = 0
        cache = bytearray()
        log.debug("Initial received sequence number:{}".format(self.sequence))
        window = [-i for i in range(1, WINDOW + 1)]
        for i in range(0, WINDOW):
            window[i] = int(packet.grow_sequence(self.sequence, i))
        self.conn.settimeout(20*RECV_TIME_OUT)
        while True:
            if isinstance(window[0], packet.Packet):
                peek = window[0]
                if len(peek.payload) == 0:
                    self.conn.settimeout(HANDSHAKE_TIME_OUT)
                    spend = time.time()-start
                    rate = spend/packages
                    log.debug("Re-send {} times for BYE".format(int(rate * HANDSHAKE_TIME_OUT)))
                    for i in range(0, 5+int(rate * HANDSHAKE_TIME_OUT)):

                        self.conn.sendall(
                            packet.control_package(packet.BYE, self.remote[0], self.remote[1], packet.minus_sequence(self.sequence)).to_bytes())
                        try:

                           data = self.conn.recv(FRAME_SIZE)
                        except Exception as e:
                           continue
                        recv_packet = packet.Packet.from_bytes(data)
                        if recv_packet.packet_type == packet.BYE:
                           break

                    return cache
            data = self.conn.recv(FRAME_SIZE)
            recv_packet = packet.Packet.from_bytes(data)
            log.debug("Packet: {}".format(recv_packet))
            if not (recv_packet.peer_ip_addr == self.remote[0] and recv_packet.peer_port == self.remote[1]):
                log.debug("Received corrupt data from source {}:{}".format(recv_packet.peer_ip_addr, recv_packet.peer_port))
                continue
            if not recv_packet.packet_type == packet.DATA:
                log.debug("Received control packet Cache")
                self.recv_control_package(recv_packet)
            else:
                if recv_packet.seq_num in window:
                    window_index = self.findIndex(window, recv_packet.seq_num)
                    window[window_index] = recv_packet
                    log.debug("Slot {} received data sequence number {}".format(window_index, recv_packet.seq_num))
                    packages = packages + 1
                else:
                    log.debug("Received unexpected or duplicate sequence number {}".format(recv_packet.seq_num))
                while (isinstance(window[0], packet.Packet)):
                    peek = window[0]
                    if len(peek.payload) == 0:
                        log.debug("Pop Terminate packet, sequence number {}".format(peek.seq_num))
                        self.sequence = packet.grow_sequence(peek.seq_num, 1)
                        break
                    pop_packet = window.pop(0)
                    self.sequence = packet.grow_sequence(pop_packet.seq_num, 1)
                    log.debug("Pop first element in window, sequence number {}".format(pop_packet.seq_num))
                    last = window[len(window) - 1]
                    if isinstance(last, packet.Packet):
                        window.append(packet.grow_sequence(last.seq_num, 1))
                    else:
                        window.append(packet.grow_sequence(last, 1))
                    cache.extend(pop_packet.payload)
                log.debug("Send ACK#{}".format(recv_packet.seq_num))
                log.debug("New Window:{}".format(self.getwindows(window)))
                self.conn.sendall(packet.control_package(packet.ACK, self.remote[0], self.remote[1], recv_packet.seq_num).to_bytes())

    def sendall(self, data, stop=True):
        start = time.time()
        timer = None
        log.debug("Initial send sequence number:{}".format(self.sequence))
        window = [-i for i in range(1, WINDOW + 1)]
        for i in range(0, WINDOW):
            window[i] = int(packet.grow_sequence(self.sequence, i))
        package, self.sequence = packet.data_package(self.remote[0], self.remote[1], data, stop, self.sequence)
        original = package.copy()
        timeout = [False, False, 0]
        log.debug("Initial widow:{}".format(window))
        while len(package) != 0 or not self.flushwindow(window):
            while not isinstance(window[0], packet.Packet):
                if len(package) > 0:
                    window[0] = package.pop(0)
                    window.append(window.pop(0))
                else:
                    log.debug("All packets sent!!!")
                    break
            for i in range(0, len(window)):
                if isinstance(window[i], packet.Packet):
                    if not window[i].send:
                        log.debug("Send {} slot, package number {}".format(i, window[i].seq_num))
                        self.conn.sendall(window[i].to_bytes())
                        window[i].send = True
                    elif timeout[0]:
                        log.debug("Re-send {} slot, package number {}".format(i, window[i].seq_num))
                        self.conn.sendall(window[i].to_bytes())
                    else:
                        log.debug("Slot {} is waiting for a Timeout".format(i))

            def out(timeout):
                log.debug("Get Time-out")
                timeout[0] = True
                timeout[1] = False

            if not timeout[1]:
                timer = Timer(RECV_TIME_OUT, out, [timeout])
                timer.start()
                timeout[0] = False
                timeout[1] = True
            print("[DEBUG] >> ")
            log.debug("After sending, widow:{}".format(self.getwindows(window)))
            log.debug("Receive from a Remote source")

            while not self.flushwindow(window):
                self.conn.settimeout(SLIDE_TIME)
                try:
                    data, route = self.conn.recvfrom(FRAME_SIZE)  # buffer size 1024 bytes
                    p = packet.Packet.from_bytes(data)
                    log.debug("Receive:{}".format(p))
                    if p.packet_type == packet.BYE and p.seq_num == packet.minus_sequence(self.sequence):
                        timer.cancel()
                        self.conn.settimeout(HANDSHAKE_TIME_OUT)
                        spend = time.time()-start
                        rate = spend/len(original)
                        log.debug("Resent {} times for BYE".format(int(rate * HANDSHAKE_TIME_OUT)))
                        for i in range(0, 5+int(rate * HANDSHAKE_TIME_OUT)):

                            self.conn.sendall(
                                packet.control_package(packet.BYE, self.remote[0], self.remote[1],
                                                       uint32(0)).to_bytes())
                        return
                    elif p.packet_type == packet.DATA:
                        log.debug("Cache data")
                        self.data.append(p)
                    elif p.packet_type == packet.ACK:
                        window_index = self.findIndex(window, p.seq_num)
                        if not window_index == None:
                            log.debug("Received ACK {} for slot {}".format(p.seq_num, window_index))
                            log.debug("Old window:{}".format(self.getwindows(window)))
                            window[window_index] = int(packet.grow_sequence(p.seq_num, WINDOW))
                            log.debug("New window:{}".format(self.getwindows(window)))
                        else:
                            log.debug("Received ACK {} but doesn't belong to any window slot, so being dropped!".format(p.seq_num))
                    elif p.packet_type == packet.NAK:
                        if p.seq_num in window:
                            window_index = self.findIndex(window, p.seq_num)
                            log.debug("Received NAK {} for slot {}".format(p.seq_num, window_index))
                            self.conn.sendall(window[window_index].to_bytes())
                            log.debug("resend {} slot, package #{}".format(window_index, p.seq_num))
                        else:
                            log.debug("Received NAK {} but doesn't belong to any window slot, so being dropped!".format(p.seq_num))
                    else:
                        print("Unknown packet type")
                except socket.timeout:
                    break
            while not isinstance(window[0], packet.Packet):
                if len(package) > 0:
                    log.debug("Slide window")
                    window[0] = package.pop(0)
                    window.append(window.pop(0))
                else:
                    log.debug("Package sent!")
                    break
            log.debug("After window sliding:{}".format(self.getwindows(window)))
            if not timeout[0]:
                continue
            else:
                if len(package) == 0:
                    spend = time.time() - start
                    rate = spend / len(original)
                    packs = len([w for w in window if isinstance(w, packet.Packet)])
                    log.debug("Re-send {} packets packages {} times to flush data".format(packs, int(packs * rate / RECV_TIME_OUT)))
                    timeout[2] = timeout[2] + 1
                    if timeout[2] == 5 + int(2*rate / RECV_TIME_OUT):
                        return

        timer.cancel()

    def recv_data_package(self, packet):
        index = 0
        timer = None

    def recv_control_package(self, packet):
        self.control.append(packet)



    def bind(self, address):
        self.conn.bind(address)

    def close(self):
        self.conn.close()
        for c in self.client_list:
            c.close()

    def settimeout(self, timeout):
        pass


class HandShakeException(Exception):
    pass


class SocketException(Exception):
    pass


class FlushException(Exception):
    pass