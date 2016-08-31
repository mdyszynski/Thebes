import sys
import asyncio
import asyncio.streams
import argparse
import os
import re
import telnetlib
import codecs
import pickle
import json
import base64
import msgpack
import requests
import math
from Crypto.Util import number

from SphinxParams import SphinxParams

class MyServer:
    def __init__(self):
        self.server = None
        self.clients = {}
        output_queue = []
        global output_queue

    def _accept_client(self, client_reader, client_writer):
        task = asyncio.Task(self._handle_client(client_reader, client_writer))
        self.clients[task] = (client_reader, client_writer)

        def client_done(task):
            print("client task done:", task, file=sys.stderr)
            del self.clients[task]

        task.add_done_callback(client_done)



    @asyncio.coroutine
    def _handle_client(self, client_reader, client_writer):
        def find_between(s, start, end):
            return (s.split(start))[1].split(end)[0]
        #Pull node information from public directory server
        @asyncio.coroutine
        def pull_from_directory():
            reader, writer = yield from asyncio.streams.open_connection(
                'ec2-52-209-252-28.eu-west-1.compute.amazonaws.com', 12347, loop=loop)

            def send(msg):
                writer.write((msg).encode("ISO-8859-1"))

            def recv():
                msgback = (yield from reader.readline())
                return msgback

            send("TYPE")
            send("CLIENT")
            send("NAME")
            send("FINISHED")

            data = yield from recv()
            writer.close()
            return data

        data = (yield from client_reader.readuntil(b'FINISHED'))
        alpha = find_between(data, b"alpha", b"beta")
        beta = find_between(data, b"beta", b"gamma")
        gamma = find_between(data, b"gamma", b"delta")
        delta = find_between(data, b"delta", b"FINISHED")

        loop = asyncio.get_event_loop()
        directory = yield from pull_from_directory()
        global n
        next_hop = n.process((int(alpha),beta,gamma),delta,directory)

        while True:
            try:
                global output_queue
                output_queue.append(next_hop)
            except:
                continue
            else:
                yield from client_writer.drain()
                break


    def start(self, loop, port):
        print("Listening on port ", port)
        self.server = loop.run_until_complete(
            asyncio.streams.start_server(self._accept_client,
                                         None, port,
                                         loop=loop))

    def stop(self, loop):
        if self.server is not None:
            self.server.close()
            loop.run_until_complete(self.server.wait_closed())
            self.server = None


def main(name, y, port, id):
    loop = asyncio.get_event_loop()
    @asyncio.coroutine
    def send_messages():
        @asyncio.coroutine
        def client(header, delta, port):
            reader, writer = yield from asyncio.streams.open_connection(port, 12347, loop=loop)

            def send(msg):
                writer.write((msg).encode("ISO-8859-1"))

            def recv():
                msgback = (yield from reader.readline()).decode("utf-8").rstrip()
                print("< " + msgback)
                return msgback

            alpha, beta, gamma = header

            send("alpha" + str(alpha))
            send("beta" + str(beta,'ISO-8859-1'))
            send("gamma" + str(gamma,'ISO-8859-1'))
            send("delta" + str(delta,'ISO-8859-1'))
            send("FINISHED")

            writer.close()
            yield from asyncio.sleep(0.5)

        @asyncio.coroutine
        def client_final(message, port):
            reader, writer = yield from asyncio.streams.open_connection(port, 12347, loop=loop)

            def send(msg):
                writer.write((msg).encode("ISO-8859-1"))

            def recv():
                msgback = (yield from reader.readline()).decode("utf-8").rstrip()
                print("< " + msgback)
                return msgback

            send(message)

            writer.close()
            yield from asyncio.sleep(0.5)

        while True:
            interval = 10
            yield from asyncio.sleep(interval)
            pool_length = len(output_queue)
            minimum_pool = 11
            minimum_send = 1

            if pool_length > minimum_pool:
                send_rate = 0.7
                number_to_send = pool_length * send_rate

                if number_to_send > minimum_send:
                    number_to_send = math.floor(number_to_send)
                    s = set()
                    while len(s) < number_to_send:
                        s.add(number.bytes_to_long(os.urandom(256)) % pool_length)
                    s = list(s)
                    for i in range(0,len(s)):
                        _header, _delta, _port = output_queue[s[i]]
                        if(_delta != None):
                            yield from client(_header,_delta,_port)
                        else:
                            _, message, port = _header
                            try:
                                yield from client_final(message,port)
                            except:
                                pass

                    s = sorted(s, reverse=True)
                    for i in range(0,len(s)):
                        del output_queue[s[i]]

    @asyncio.coroutine
    def directory_submit():
        reader, writer = yield from asyncio.streams.open_connection(
            'ec2-52-209-252-28.eu-west-1.compute.amazonaws.com', 12347, loop=loop)

        def send(msg):
            writer.write((msg).encode("ISO-8859-1"))

        def recv():
            msgback = (yield from reader.readline()).decode("utf-8").rstrip()
            print("< " + msgback)
            return msgback

        r = requests.get('https://api.ipify.org?format=json')

        send("TYPE")
        send("NODE")
        send("NAME" + str(name,'ISO-8859-1'))
        send("THEY" + str(y))
        send("PORT" + str(r.json()['ip']))
        send("IDNO" + str(id,'ISO-8859-1'))
        send("FINISHED")

        writer.close()
        yield from asyncio.sleep(0.5)

    server = MyServer()
    server.start(loop,port)
    loop.run_until_complete(directory_submit())
    asyncio.ensure_future(send_messages())
    loop.run_forever()

def pad_body(msgtotalsize, body):
    body = body + "\x7f"
    body = body + ("\xff" * (msgtotalsize - len(body)))
    return body

def unpad_body(body):
    body = str(body, 'ISO-8859-1')
    return re.compile("\x7f\xff*$").sub('',body)

# The special destination
Dspec = "\x00"

# Any other destination.  Must be between 1 and 127 bytes in length
def Denc(dest):
    assert len(dest) >= 1 and len(dest) <= 127
    return chr(len(dest)) + dest

# Sphinx nodes
class SphinxNode:
    def __Nenc(self, idnum):
        id = b"\xff" + idnum + (b"\x00" * (self.p.k - len(idnum) - 1))
        assert len(id) == self.p.k
        return id

    # Decode the prefix-free encoding.  Return the type, value, and the
    # remainder of the input string
    def __PFdecode(self, s):
        if s == "": return None, None, None
        if s[:1] == b'\x00': return 'Dspec', None, s[1:]
        if s[:1] == b'\xff': return 'node', s[:self.p.k], s[self.p.k:]

        l = ord(s[:1])

        if l < 128: return 'dest', s[1:l+1], s[l+1:]
        return None, None, None

    def __init__(self, params):
        self.p = params
        group = self.p.group
        self.__x = group.gensecret()
        self.y = group.expon(group.g, self.__x)
        idnum = os.urandom(4)
        self.id = self.__Nenc(idnum)
        self.name = b"Node " + codecs.encode(idnum, 'hex')
        self.seen = {}
        params.pki[self.id] = self

    def process(self, header, delta, directory):
        p = self.p
        pki = p.pki
        group = p.group
        alpha, beta, gamma = header

        # Check that alpha is in the group
        if not group.in_group(alpha):
            return

        # Compute the shared secret
        s = group.expon(alpha, self.__x)

        # Have we seen it already?
        tag = p.htau(s)
        if tag in self.seen:
            return
        #Checks message integrity
        if gamma != p.mu(p.hmu(s), beta):
            print("MAC mismatch!")
            print("alpha =", group.printable(alpha))
            print("s =", group.printable(s))
            print("beta =", beta)
            print("gamma =", gamma)
            return

        #Add tag to list (replay prevention, resets when public key is changed)
        self.seen[tag] = 1
        B = p.xor(beta + (b"\x00" * (2 * p.k)), p.rho(p.hrho(s)))

        #Message decoded
        _type, val, rest = self.__PFdecode(B)
        if _type == "node":
            b = p.hb(alpha, s)
            #Alpha beta gamma and delta recalculated and prepared to be sent to next mix node
            alpha = group.expon(alpha, b)
            gamma = B[p.k:p.k*2]
            beta = B[p.k*2:]
            delta = p.pii(p.hpi(s), delta)

            dataz = directory
            data = msgpack.unpackb(dataz)
            result = [item for item in data if base64.b64decode(item[3]) == val]
            aa,aaa,port,aaaa = result[0]

            return ((alpha, beta, gamma), delta, port)
        #If type == dspec message is ready to be sent to final destination
        if _type == "Dspec":
            delta = p.pii(p.hpi(s), delta)
            if delta[:p.k] == (bytes("\x00" * p.k,'ISO-8859-1')):
                _type, val, rest = self.__PFdecode(delta[p.k:])
            if _type == "dest":
                body = unpad_body(rest)
                return ((None,body,val),None,None)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--listento", help="Listen to port")
    args = parser.parse_args()
    r = 5
    from SphinxParams import SphinxParams

    p = SphinxParams(r)
    n = SphinxNode(p)
    main(n.name, n.y, args.listento, n.id)
