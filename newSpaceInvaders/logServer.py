import os
import pickle
import logging
import logging.handlers
import socketserver
import struct
import logging.config
import yaml

from constants import *


class LogUDPHandler(socketserver.DatagramRequestHandler):
    def handle(self):
        try:
            while True:
                datagram = self.request[0].strip()
                chunk = datagram[0:4]
                struct.unpack(">L", chunk)[0]
                chunk = datagram[4:]
                obj = self.unPickle(chunk)
                record = logging.makeLogRecord(obj)
                self.handleLogRecord(record)
                break
        except Exception as ex:
            print("Exception in logger {}".format(ex))

    def unPickle(self, data):
        return pickle.loads(data)

    def handleLogRecord(self, record):
        if self.server.logname is not None:
            name = self.server.logname
        else:
            name = record.name
        logger = logging.getLogger(name)
        rotating = logging.handlers.RotatingFileHandler(filename=LOG_NAME, maxBytes=0)
        rotating.setLevel('DEBUG')
        rotating.setFormatter(
            logging.Formatter(FORMAT))
        log = logging.getLogger(name)
        log.addHandler(rotating)
        log.debug(msg=record.msg)
        logger.handle(record)


class LogSocketListener(socketserver.ThreadingUDPServer):
    allow_reuse_address = True

    def __init__(self, host='localhost',
                 port=logging.handlers.DEFAULT_UDP_LOGGING_PORT,
                 handler=LogUDPHandler):
        socketserver.ThreadingUDPServer.__init__(self, (host, port), handler)
        self.abort = 0
        self.timeout = 1
        self.logname = None

    def serve_until_stopped(self):
        import select
        abort = 0
        while not abort:
            rd, wr, ex = select.select([self.socket.fileno()],
                                       [], [],
                                       self.timeout)
            if rd:
                self.handle_request()
            abort = self.abort


def getPath(path):
    if os.path.exists(path):
        with open(path, READ) as logConfigFile:
            config = yaml.load(logConfigFile.read(), Loader=yaml.FullLoader)
        return config


def main():
    logging.basicConfig(format=FORMAT)
    tcpserver = LogSocketListener()
    print('Log UDP service...')
    tcpserver.serve_until_stopped()


if __name__ == '__main__':
    main()
