import logging
import os
import socket
import sys
import time

from flask import Flask, request, jsonify
import suffix_array


FORMAT = '%(asctime)s %(levelname)5s: %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)

app = Flask(__name__)

file_datas = []
nodes = []


class FileData(object):
    def __init__(self, filename, file_data):
        super(FileData, self).__init__()

        self.filename = filename

        # Per-file SA
        self.file_sa = suffix_array.SuffixArray(file_data)

        # Per-line SA
        self.line_sa = []
        for i, line in enumerate(file_data.split('\n')):
            self.line_sa.append(suffix_array.SuffixArray(line))

    def contribute(self, results, q):
        if q not in self.file_sa:
            return

        for i, line_sa in enumerate(self.line_sa):
            if q in line_sa:
                results.append('%s:%d' % (self.filename, i+1))


@app.route("/")
def query():
    q = request.args.get('q', '')
    # logging.info("Searching for %s", q)
    _start = time.time()

    for node in nodes:
        node.send('Q\n%s\n' % q)

    results = []
    # logging.info("    aggregating results...")
    for node in nodes:
        count = int(node.read_line())
        for i in range(count):
            results.append(node.read_line())

    _end = time.time()
    resp = jsonify(success=True, results=results)
    _endend = time.time()
    logging.info("  Got %d matches for %s in %.2f + %.2f ms", len(results), q, (_end - _start)*1000, (_endend - _end)*1000)
    return resp


def get_results(q):
    # _start = time.time()
    results = []
    for fd in file_datas:
        fd.contribute(results, q)
    # _end = time.time()
    # logging.info("    Node: got %d matches in %.2f ms", len(results), (_end - _start)*1000)
    return results


@app.route("/index")
def index():
    path = request.args.get('path', None)
    if not path:
        return 'ERROR'
    logging.info("Indexing %s", path)

    filenames = []
    for root, dirs, files in os.walk(path):
        print root
        for name in files:
            filename_full = os.path.join(root, name)
            filenames.append(filename_full)

    logging.debug('  Found %d files', len(filenames))

    # Split filenames
    nodes_len = len(nodes)
    node_files = []
    for i in range(nodes_len):
        node_files.append([])
    for i, filename in enumerate(filenames):
        node_files[i % nodes_len].append(filename)

    for i, node_conn in enumerate(nodes):
        node_conn.send('I\n')
        node_conn.send('%d\n' % len(node_files[i]))
        node_conn.send('%s\n' % path)
        for filename in node_files[i]:
            node_conn.send('%s\n' % filename)

    logging.info("Indexing IN PROGRESS")
    wait_for_indexing_completed()
    time.sleep(2)
    return '{"success": "true"}'


def wait_for_indexing_completed():
    logging.info("Indexing - waiting for nodes")
    for node in nodes:
        line = node.read_line()
        assert line == 'D'

    logging.info("Indexing DONE")


def index_files(root_path, filenames):
    logging.info("index_files(): %s (%d files)", root_path, len(filenames))

    rm_len = len(root_path) + (0 if root_path.endswith('/') else 1)
    for filename_full in filenames:
        filename_rel = filename_full[rm_len:]

        file_data = open(filename_full, 'r').read()

        file_datas.append(FileData(filename_rel, file_data))

    logging.info("index_files(): DONE")


def start_server():
    server_inner()


def server_inner():
    global nodes
    time.sleep(2)

    logging.info("Server: connecting to nodes...")
    for i in range(3):
        logging.info("    node on port %d", 9091+i)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('localhost', 9091 + i))
        s.setblocking(False)

        nodes.append(LineSocket(s))

    logging.info("Server:     all nodes ready")


class LineSocket(object):
    def __init__(self, s):
        super(LineSocket, self).__init__()
        self.conn = s
        self.buf = ''

    def read_line(self):
        nl_pos = -1
        while True:
            nl_pos = self.buf.find('\n')
            if nl_pos != -1:
                break
            try:
                self.buf += self.conn.recv(1024)
            except:
                pass

        line = self.buf[:nl_pos]
        self.buf = self.buf[nl_pos+1:]
        return line

    def send(self, text):
        self.conn.send(text)


def start_node(index):
    logging.info("Node %d: Starting", index)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 9090 + index))
    s.listen(1)

    logging.info("Node %d:     waiting for server", index)
    conn, addr = s.accept()

    s = LineSocket(conn)

    logging.info("Node %d:   connected, awaiting commands", index)
    while True:
        cmd = s.read_line()
        if cmd == 'I':
            logging.info("Node %d: Got Index cmd", index)
            files_count = int(s.read_line())
            root_path = s.read_line()

            logging.info("Node %d:     have %d files to index in %s", index, files_count, root_path)
            filenames = []
            for i in range(files_count):
                filenames.append(s.read_line())

            index_files(root_path, filenames)
            logging.info("Node %d:     indexing complete", index)
            s.send('D\n')

        elif cmd == 'Q':
            # logging.info("Node %d: Got Query cmd", index)
            q = s.read_line()
            # logging.info("Node %d:     q is '%s'", index, q)
            results = get_results(q)
            # logging.info("Node %d:     returning %d results", index, len(results))
            response = '%d\n' % len(results)
            for result in results:
                response += '%s\n' % result
            # logging.info("Node %d:     sending response", index)
            s.send(response)
            # logging.info("Node %d:     response SENT", index)

        else:
            logging.info("Node %d: Got UNKNOWN cmd '%s'", index, cmd)


@app.route("/healthcheck")
def healthcheck():
    return '{"success": "%s"}' % 'true' if len(nodes) == 3 else 'false'


@app.route("/isIndexed")
def isIndexed():
    return '{"success": "true"}'


if __name__ == "__main__":
    if sys.argv[1] == '--master':
        start_server()
        app.run(host='0.0.0.0', port=9090)
    elif sys.argv[1] == '--id':
        start_node(int(sys.argv[2]))
