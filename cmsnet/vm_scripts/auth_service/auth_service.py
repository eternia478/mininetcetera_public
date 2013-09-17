#!/usr/bin/env python2.7
# Copyright 20xx Regents of the University of California
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import sys
import hashlib
import redis
from traceback import format_exc
import json
redis_host = None
redis_port = 0
""" Authentication service.
  Usage:
    auth_service.py [address_to_bind_to] [port_to_bind_to] [redis_host] [redis_port]
  All arguments are optional
  At this point a password is valid if it is the reverse of the username. Goes with auth_client.py
"""
class AuthHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    """List authenticated users."""
    global redis_host
    global redis_port
    keys = []
    try:
      r = redis.StrictRedis(host=redis_host, port=redis_port, db=0)
      keys = r.keys("auth:*")
    except Exception as ex:
      print >>sys.stderr, "Failed to connect to redis: %s" % ex
      format_exc(ex)
      self.send_response(500)
      self.end_headers()
      self.wfile.write("Redis error: %s" % ex)
      self.wfile.write("\n")
      return

    self.send_response(200)
    self.end_headers()
    self.wfile.write("Authenticated users\n")
    for key in keys:
      self.wfile.write("%s\n" % (r.get(key)))
    self.wfile.write("\n")

  def do_POST (self):
    global redis_host
    global redis_port
    clkey = filter(lambda x: x.lower() == 'content-length', self.headers.keys())[0]
    read = self.rfile.read(int(self.headers[clkey]))
    jobj = json.loads(read)
    h = hashlib.new('md5')
    h.update(jobj['login'][::-1])
    authed = False
    failed = False
    if h.hexdigest() == jobj['password']:
      try:
        r = redis.StrictRedis(host=redis_host, port=redis_port, db=0)
        r.set('auth:%s'%(jobj['mac']), jobj['login'])
        authed = True
      except Exception as e:
        failed = True
        print >>sys.stderr, "Failed to connect to redis %s"%(e)
        format_exc(e)
    if authed:
      self.send_response(200)
      self.end_headers()
      self.wfile.write("Authenticated\n")
    else:
      self.send_response(401)
      self.end_headers()
      if not failed:
        self.wfile.write('Denied\n')
      else:
        self.wfile.write("Binding agent is down")


def main(addr, port):
  httpd = HTTPServer((addr, port), AuthHandler)
  httpd.serve_forever()


if __name__ == "__main__":
  addr = '0.0.0.0' if len(sys.argv) < 2 else sys.argv[1]
  port = 8080 if len(sys.argv) < 3 else int(sys.argv[2])
  redis_host = '127.0.0.1' if len(sys.argv) < 4 else sys.argv[3]
  redis_port = 6379 if len(sys.argv) < 5 else int(sys.argv[4])
  main(addr, port)
