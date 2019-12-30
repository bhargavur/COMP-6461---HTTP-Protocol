import socket
import sys
from urllib.parse import urlparse


# from urllib.parse import urlencode
class http_old:
    counting = 0

    def __init__(self, url, arq, port=80):
        self.url = urlparse(url)
        self.port = port
        self.arq = arq
        self.host = self.url.netloc
        self.path = self.url.path
        if self.path == "":
            self.path = "/"
        self.verbosity = False
        self.header = {"Host": self.host, "User-Agent": "httpc/1.0"}
        self.data = ""
        self.file = ""
        self.content = ""
        self.state = ""
        self.headMap = {}
        self.body = ""
        self.reply = ""

    def status(self, reply):
        self.reply = reply
        (head, self.body) = reply.split("\r\n\r\n")
        headArray = head.split("\r\n")
        line1 = headArray.pop(0).split()
        # if line1[1] == '200':
        self.state = line1[1]
        print("\n====>Status:" + " ".join(line1[2:]) + "  Code:" + line1[1])
        self.headMap = {}
        for key in headArray:
            keyValue = key.split(":")
            self.headMap[keyValue[0]] = keyValue[1].strip()
        if line1[1] == '302' and self.counting < 6:
            r_url = urlparse(self.headMap["Location"])
            if r_url.netloc:
                self.host = r_url.netloc
                self.header["Host"] = self.host
            self.path = r_url.path
            if r_url.path:
                self.path = r_url.path
            else:
                self.path = "/"
            self.constructContent()
            return self.send()
        return self

    def send(self):
        self.counting = self.counting + 1
        if self.arq:
            import udp_socket as udp_socket
            conn = udp_socket.udp_socket()
        else:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            conn.connect((self.host, self.port))
            #print(self.content)
            conn.sendall(self.content.encode("utf-8"))
            if self.arq:
                response = conn.recvall()
            else:
                response = conn.recv(2048, socket.MSG_WAITALL)
            # print(response)
            status = bytearray()
            fileByte = bytearray()
            if self.arq:
                while True:
                    if response[0] == 13 and response[1] == 10 \
                            and response[2] == 13 and response[3] == 10:
                        fileByte = response[4:]
                        self.body = fileByte
                        break
                    else:
                        a = response.pop(0)
                        status.append(a)
            else:
                reply = response.decode("utf-8")
            if self.arq:
                headArray = status.decode("utf-8").split("\r\n")
                line1 = headArray.pop(0).split()
                # if line1[1] == '200':
                self.state = line1[1]
                print("\nHTTP/1.0 " + line1[1] + " " + " ".join(line1[2:]))
                self.headMap = {}
                for key in headArray:
                    keyValue = key.split(":")
                    self.headMap[keyValue[0]] = keyValue[1].strip()
                return self
            else:
                return self.status(reply)
        except OSError as e:
            print(e)
        finally:
            conn.close()

    def setVerbosity(self, v):
        self.verbosity = v

    def getVerbosity(self):
        return self.verbosity

    def addHeader(self, key, value):
        self.header[key] = value

    def getHeader(self):
        head = "\r\n"
        # print(self.header)
        for k, v in self.header.items():
            head += (k + ": " + v + "\r\n")
        return head

    def setType(self, type):
        self.type = type

    def getType(self):
        return self.type

    def setData(self, data):
        self.data = data

    def setFile(self, file):
        self.file = file

    def constructContent(self):
        if self.url.query != "":
            query = "?" + self.url.query
        else:
            query = ""
        # construct get message
        if self.type == "get":
            self.content = self.type.upper() + " " + self.path + query + " HTTP/1.0" + self.getHeader() + "\r\n"
        # construct post message with data or file
        elif self.type == "post":
            if self.data:
                self.content = self.type.upper() + " " + self.path + " HTTP/1.0" + self.getHeader() + "\r\n" + self.data
            elif self.file:
                self.content = self.type.upper() + " " + self.path + " HTTP/1.0" + self.getHeader() + "\r\n" + self.file
            else:
                self.content = self.type.upper() + " " + self.path + " HTTP/1.0" + self.getHeader() + "\r\n"

