import sys
import os
import codecs
from SphinxParams import SphinxParams
from SphinxNode import SphinxNode, Denc, Dspec, pad_body, unpad_body
from SphinxNymserver import Nymserver
from Crypto.Util import number
import json
import asyncio
import asyncio.streams
import argparse
import msgpack
import base64
import time
import cProfile

def main(sendport, header, delta, loop):
    @asyncio.coroutine
    def client():
        reader, writer = yield from asyncio.streams.open_connection(
            sendport, 12347, loop=loop)

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
        print("Message sent")

        writer.close()
        yield from asyncio.sleep(0.5)

    try:
        loop.run_until_complete(client())
    finally:
        pass


def create_header(params, nodelist, dest, id):
    p = params
    pki = p.pki
    nu = len(nodelist)
    assert nu <= p.r
    assert len(id) == p.k
    assert len(dest) <= 2 * (p.r - nu + 1) * p.k
    group = p.group
    x = group.gensecret()
    # Compute the (alpha, s, b) tuples
    blinds = [x]
    asbtuples = []
    for node in nodelist:
        alpha = group.multiexpon(group.g, blinds)
        node_key, node_id = node
        s = group.multiexpon(node_key, blinds)
        b = p.hb(alpha, s)
        blinds.append(b)
        asbtuples.append({'alpha': alpha, 's': s, 'b': b})

    # Compute the filler strings
    phi = b''
    for i in range(1, nu):
        min = (2 * (p.r - i) + 3) * p.k
        phi = p.xor(phi + (b"\x00" * (2 * p.k)), p.rho(p.hrho(asbtuples[i - 1]['s']))[min:])

    # Compute the (beta, gamma) tuples
    beta = bytes(dest, 'ISO-8859-1') + bytes(id, 'ISO-8859-1') + os.urandom(((2 * (p.r - nu) + 2) * p.k - len(dest)))
    beta = p.xor(beta, p.rho(p.hrho(asbtuples[nu - 1]['s']))[:(2 * (p.r - nu) + 3) * p.k]) + phi
    gamma = p.mu(p.hmu(asbtuples[nu - 1]['s']), beta)

    for i in range(nu - 2, -1, -1):
        node_key, id = nodelist[i + 1]
        assert len(id) == p.k
        beta = p.xor(id + gamma + beta[:(2 * p.r - 1) * p.k],
                     p.rho(p.hrho(asbtuples[i]['s']))[:(2 * p.r + 1) * p.k])
        gamma = p.mu(p.hmu(asbtuples[i]['s']), beta)

    return (asbtuples[0]['alpha'], beta, gamma), [x['s'] for x in asbtuples]


def create_forward_message(params, nodelist, dest, msg):
    p = params
    pki = p.pki
    nu = len(nodelist)
    assert len(dest) < 128 and len(dest) > 0
    assert p.k + 1 + len(dest) + len(msg) < p.m

    # Compute the header and the secrets
    header, secrets = create_header(params, nodelist, Dspec, "\x00" * p.k)

    body = pad_body(p.m, ("\x00" * p.k) + Denc(dest) + msg)

    # Compute the delta values
    delta = p.pi(p.hpi(secrets[nu - 1]), body)

    for i in range(nu - 2, -1, -1):
        delta = p.pi(p.hpi(secrets[i]), delta)

    return header, delta

def create_surb(params, nodelist, dest):
    p = params
    pki = p.pki
    nu = len(nodelist)
    id = os.urandom(p.k)

    # Compute the header and the secrets
    header, secrets = create_header(params, nodelist, Denc(dest), id)

    ktilde = os.urandom(p.k)
    keytuple = [ktilde]
    keytuple.extend(list(map(p.hpi, secrets)))
    return id, keytuple, (nodelist[0], header, ktilde)


class SphinxClient:
    def __init__(self, params):
        self.id = b"Client " + codecs.encode(os.urandom(4), 'hex')
        self.params = params
        params.clients[self.id] = self
        self.keytable = {}

if __name__ == '__main__':
    use_ecc = (len(sys.argv) > 1 and sys.argv[1] == "-ecc")
    #Number of intermediate mix nodes used
    r = 5
    params = SphinxParams(r, ecc=use_ecc)
    data = []
    # Create a client object
    client = SphinxClient(params)
    loop = asyncio.get_event_loop()
    #Pull available nodes from public directory
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
        global data
        data = yield from recv()

        writer.close()
        yield from asyncio.sleep(0.5)


    loop.run_until_complete(pull_from_directory())

    data = msgpack.unpackb(data)
    parser = argparse.ArgumentParser()
    parser.add_argument("-to", "--sendport", help="Send to port")
    parser.add_argument("-m", "--message", help="The message")
    args = parser.parse_args()
    use_nodes = []
    first_port = 0
    counter = 0
    nodeno_forprint = []
    s = set()
    while len(s) < r:
        s.add(number.bytes_to_long(os.urandom(256)) % len(data))
    s = list(s)
    for i in range(0, r):
        nodeno_forprint.append(s[i])
        a1 = data[s[i]][0]
        b1 = data[s[i]][1]
        c1 = data[s[i]][2]
        d1 = base64.b64decode(data[s[i]][3])
        if counter == 0:
            first_port = c1
        counter = counter + 1
        use_nodes.append((int(b1),d1))
    print("Nodes used: ", nodeno_forprint)

    header, delta = create_forward_message(params, use_nodes, args.sendport, args.message)
    alpha, beta, gamma = header
    main(first_port, header, delta, loop)
