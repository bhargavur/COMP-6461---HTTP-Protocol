import sys
sys.path.extend(["../"])
sys.path.extend(["."])
from threading import Thread
from http_old import http_old

def get(file, index):
    h = http_old("http://localhost/"+file, 8080)
    h.setType('get')
    h.constructContent()
    reply = h.send()
    print("========="+reply.reply+"========\nThread:"+str(index)+" of GET got this")

def post(file, index):
    body = str(index)
    h = http_old("http://localhost/"+file, 8080)
    h.setType('post')
    h.setData(body)
    h.addHeader("Content-Type", "application/json")
    h.addHeader("Content-Length", str(len(body)))
    h.constructContent()
    reply = h.send()
    print("======="+reply.reply+"=======\nThread:" + str(index) + " of POST is running this")

for i in range(1, 20):
    #Thread(target=post, args=("foo", i)).start()
    Thread(target=get, args=("bar", i)).start()