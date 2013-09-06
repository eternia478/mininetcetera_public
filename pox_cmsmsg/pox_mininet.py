"""
This file could connect to mininet_service.py, it is just a small test of the JSON and messenger
"""

import uuid
import json
import sys
import socket
import argparse
## Attention: the parser is usesable when we test this file, but when we add this component into the system, we could delete the part
parser = argparse.ArgumentParser(description='Connect to the Mininet service')
parser.add_argument('--address', dest='address', default='127.0.0.1',
                    help="Messenger service address")
parser.add_argument('--port', dest='port', default='7790', type=int,
                    help="Messenger service port")
args = parser.parse_args()
host = args.address
port = args.port

while True:
  try:
    sock = socket.socket()
    sock.connect((host,port))
    print >>sys.stderr, "== Connected =="
    msg = {
        'CHANNEL' : '',
        'cmd' : 'join_channel',
        'channel' : 'CMS',
        'json' : True,
    }
    sock.send(json.dumps(msg))
    msg = {
        'CHANNEL' : 'CMS',
        'host' : 'node1',
    }
    sock.send(json.dumps(msg))

    try:
      while True:
        d = sock.recv(1024)
        print "socket receiving: ", d
        #print "len:d --", len(d)
        if len(d) == 0: raise RuntimeError()
    except KeyboardInterrupt:
      pass
    except RuntimeError as e:
      print >>sys.stderr, "== Disconnected =="
      try:
        sock.close()
      except:
        pass
  except KeyboardInterrupt:
    break
  except:
    pass
