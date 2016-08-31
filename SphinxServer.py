import sys
import asyncio
import asyncio.streams
import argparse
import requests
import time
import json

class MyServer:
    def __init__(self):
        self.server = None
        self.clients = {}
        server_json = []
        global server_json
        clients_since = 0
        global clients_since

    def _accept_client(self, client_reader, client_writer):
        global clients_since
        clients_since = clients_since + 1
        task = asyncio.Task(self._handle_client(client_reader, client_writer))
        self.clients[task] = (client_reader, client_writer)

        def client_done(task):
            del self.clients[task]

        task.add_done_callback(client_done)

    @asyncio.coroutine
    def _handle_client(self, client_reader, client_writer):
        details = []
        data = (yield from client_reader.read()).decode("utf-8")

        detail = [data, time.time() * 1000]

        global server_json
        server_json.append(detail)
        global clients_since
        print(clients_since)

        yield from client_writer.drain()

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


def main(args):
    loop = asyncio.get_event_loop()
    server = MyServer()
    server.start(loop,args.listento)
    loop.run_forever()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--listento", help="Listen to port")
    args = parser.parse_args()
    r = requests.get('https://api.ipify.org?format=json')
    print("Receive messages on: ", r.json()['ip'])
    main(args)
