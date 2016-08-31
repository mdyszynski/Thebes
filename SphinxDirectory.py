import sys
import asyncio
import asyncio.streams
import json
import os
import msgpack
import base64

class MyServer:
    def __init__(self):
        self.server = None
        self.clients = {}

    def _accept_client(self, client_reader, client_writer):
        task = asyncio.Task(self._handle_client(client_reader, client_writer))
        self.clients[task] = (client_reader, client_writer)

        def client_done(task):
            del self.clients[task]

        task.add_done_callback(client_done)

    @asyncio.coroutine
    def _handle_client(self, client_reader, client_writer):
        def append_record(record):
            with open('data.json', 'a') as f:
                json.dump(record, f)
                f.write(os.linesep)

        def find_between(s, start, end):
            return (s.split(start))[1].split(end)[0]

        data = (yield from client_reader.readuntil(b'FINISHED'))

        _type = find_between(data, b"TYPE", b"NAME")

        if _type == b'NODE':
            name = find_between(data, b"NAME", b"THEY")
            they = find_between(data, b"THEY", b"PORT")
            port = find_between(data, b"PORT", b"IDNO")
            idno = find_between(data, b"IDNO", b"FINISHED")

            data = []

            idno = base64.b64encode(idno)

            details = [str(name,'ISO-8859-1'), str(they,'ISO-8859-1'),str(port,'ISO-8859-1'),str(idno,'ISO-8859-1')]

            with open ('data.json', mode="r+") as file:
                try:
                    file.seek(os.stat('data.json').st_size -1)
                    file.write( ",{}]".format(json.dumps(details)) )
                except:
                    file.write('[')
                    file.write(json.dumps(details))
                    file.write(']')


        elif _type == b'CLIENT':
            with open('data.json', 'r') as fp:
                data = json.load(fp)

            to_send = msgpack.packb(data)

            client_writer.write(to_send)
            client_writer.write_eof()

        else:
            print("Bad command {!r}".format(data), file=sys.stderr)

        yield from client_writer.drain()

    def start(self, loop):
        self.server = loop.run_until_complete(
            asyncio.streams.start_server(self._accept_client,
                                         None, 12347,
                                         loop=loop))
        print("LISTENING ON PORT 12347")

    def stop(self, loop):
        if self.server is not None:
            self.server.close()
            loop.run_until_complete(self.server.wait_closed())
            self.server = None

def deleteContent(fName):
    with open(fName, "w"):
        pass

def main():
    loop = asyncio.get_event_loop()
    deleteContent('data.json')
    server = MyServer()
    server.start(loop)
    loop.run_forever()

if __name__ == '__main__':
    main()
