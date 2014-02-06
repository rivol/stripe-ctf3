import hashlib
import logging
import multiprocessing
import socket
import threading
from time import time, sleep

from dulwich.objects import Commit, parse_timezone

import hasher


FORMAT = '%(asctime)s %(levelname)5s: %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)

TCP_HOST = '54.201.103.17'
TCP_PORT = 34567

git_parent_id = None
git_tree_id = None
difficulty = None


class SolveThread(threading.Thread):
    def __init__(self, socket, client_id, attempt, git_parent_id, git_tree_id, difficulty, *args, **kwargs):
        super(SolveThread, self).__init__(*args, **kwargs)

        self.socket = socket
        self.client_id = client_id
        self.attempt = attempt
        self.git_parent_id = git_parent_id
        self.git_tree_id = git_tree_id
        self.difficulty = difficulty
        self.should_stop = False

        self.daemon = True


    def run(self):
        _time_start = time()
        logging.debug("solve(): %04d-%06d: solving for %s,  current parent is %s",
                      self.client_id, self.attempt, self.difficulty[:10], self.git_parent_id)

        commit = Commit()
        commit.tree = self.git_tree_id
        commit.parents = [self.git_parent_id]
        author = "Rivo Laks <rivolaks@gmail.com>"
        commit.author = commit.committer = author
        commit.commit_time = commit.author_time = int(time())
        tz = parse_timezone('+0200')[0]
        commit.commit_timezone = commit.author_timezone = tz
        commit_message_template = "       Give me a Gitcoin %04d-%06d-%09x"
        commit.message = commit_message_template % (self.client_id, self.attempt, 1)

        hash_src = commit._header()
        for chunk in commit.as_raw_chunks():
            hash_src += chunk
        # Cut out the iteration number at the end which is 9 bytes
        hash_src = hash_src[:-9]
        assert len(hash_src) == 256

        _time_loop = time()
        i = 0
        block_size = 120000
        while not self.should_stop:
            sleep(0.001)
            # hasher.solve() returns either None, or the iteration number, if that iteration seems to match.
            result = hasher.solve(bytearray(hash_src), i, i+block_size, self.difficulty)
            if result is not None:
                logging.info("Hasher found something: %s", result)
                i = result
            else:
                i += block_size
                continue

            commit_tail = "%09x" % i
            commit_id = hashlib.sha1(hash_src + commit_tail).hexdigest()

            if commit_id < self.difficulty:
                logging.info('#' * 120)
                logging.info('   S U C C E S S  ! ! !')
                logging.info('solve(): %04d-%06d-%09x: SUCCESS: found %s / %s',
                             self.client_id, self.attempt, i, commit_id, self.difficulty[:10])
                logging.info('#' * 120)

                commit.message = commit_message_template % (self.client_id, self.attempt, i)
                assert commit.id == commit_id
                commit_body = ''.join(commit._serialize())
                # print commit.id, commit_id
                # print "'%s'" % commit_body
                # print "'%s'" % ''.join(hash_src + commit_tail)

                logging.debug("Commit body is: '%s'", commit_body)
                #subprocess.Popen('git hash-object -t commit --stdin -w'.split(), stdin=subprocess.PIPE,
                #                 stdout=subprocess.PIPE).communicate(commit_body)

                #subprocess.check_output(('git reset --hard %s' % commit.id).split())

                self.socket.sendall("C %40s %40s %5d\n" % (self.git_parent_id, commit_id, len(commit_body)))
                self.socket.sendall(commit_body + '\n')

                return True
            else:
                print "!" * 120
                print "ERROR!!!"
                print "hashes don't match, mine is", commit_tail, commit_id

        _time_end = time()
        speed_mh_s = i / 1000000.0 / (_time_end - _time_loop) if i > 0 else 0
        logging.debug("solve(): %04d-%06d: stopped with %d iterations, speed was %.3f MH/s + %.3f ms startup",
                      self.client_id, self.attempt, i, speed_mh_s, (_time_loop - _time_start) * 1000)
        return False


def create_connection():
    logging.info("Connecting to %s:%d", TCP_HOST, TCP_PORT)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # TODO: wait and retry if connect() fails
    s.connect((TCP_HOST, TCP_PORT))

    s.sendall('HELLO\n')
    data = s.recv(8)
    assert data == 'WELCOME '
    data = s.recv(5)

    client_id = int(data)
    return s, client_id


def read_command(s):
    global git_parent_id, git_tree_id, difficulty

    # TODO: handle case where the server has disappeared
    command = s.recv(1)
    assert s.recv(1) == ' '
    if command == 'P':
        git_parent_id = s.recv(40)
    elif command == 'T':
        git_tree_id = s.recv(40)
    elif command == 'D':
        difficulty = s.recv(40)
    elif command == 'R':
        # Reset
        pass

    assert s.recv(1) == '\n'
    return command


def multiprocess_client_with_thread():
    global git_parent_id, git_tree_id, difficulty

    # while True:
    s, client_id = create_connection()
    logging.info("Connection established, my client_id is %d", client_id)
    solve_thread = None

    attempt = 0
    while True:
        try:
            cmd = read_command(s)
        except KeyboardInterrupt:
            return

        if cmd == 'R' and git_parent_id and git_tree_id and difficulty:
            if solve_thread:
                solve_thread.should_stop = True
                solve_thread.join()

            attempt += 1
            logging.debug("Client %d: Starting solve thread, attempt %d", client_id, attempt)
            solve_thread = SolveThread(s, client_id, attempt, git_parent_id, git_tree_id, difficulty)
            solve_thread.start()


# Start processes
logging.info("Creating process pool...")
pool = multiprocessing.Pool()
for i in range(pool._processes):
    p = multiprocessing.Process(target=multiprocess_client_with_thread)
    p.daemon = True
    p.start()

logging.info("Started %d processes", pool._processes)

while True:
    sleep(100)
