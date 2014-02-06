import logging
import socket
import subprocess
import sys
import threading
import time


TCP_PORT = 34567

current_git_tree_id = ''
current_git_parent_id = ''
current_difficulty = ''
next_client_id = 1
# Maps client ids to socket objects
client_sockets = {}
git_lock = threading.Lock()
pushed_commits_total = 0
pushed_commits_succeeded = 0

FORMAT = '%(asctime)s %(levelname)5s: %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)


def git_fetch():
    """ Fetch updates from Git's origin
    """
    _start = time.time()
    subprocess.call('git fetch'.split())
    logging.debug("Git fetch done in %.3f secs", time.time() - _start)
    return get_parent_id('origin/master')


def get_tree_id():
    return subprocess.check_output('git write-tree'.split()).strip()


def get_parent_id(rev='HEAD'):
    return subprocess.check_output(('git rev-parse ' + rev).split()).strip()


def get_difficulty():
    return open('difficulty.txt', 'r').read().strip()


def prep_ledger(username):
    output = ""
    found = False
    for line in open('LEDGER.txt', 'r'):
        if ':' not in line:
            output += line
            continue

        user, amount = line.rsplit(':', 1)
        if user == username:
            output += "%s: %d\n" % (username, int(amount)+1)
            found = True
        else:
            output += line
    if not found:
        output += "%s: 1\n" % username

    with open('LEDGER.txt', 'w') as f:
        f.write(output)

    subprocess.call('git add LEDGER.txt'.split())


def git_reset(username):
    global current_git_parent_id, current_git_tree_id, current_difficulty

    subprocess.call('git reset --hard origin/master'.split())
    prep_ledger(username)

    current_git_parent_id = get_parent_id()
    current_git_tree_id = get_tree_id()
    current_difficulty = get_difficulty()
    current_difficulty += '0' * (40 - len(current_difficulty))
    assert len(current_difficulty) == 40

    logging.info("git_reset(): difficulty is %s, parent is %s", current_difficulty[:10], current_git_parent_id)


def git_update_loop(username):
    global git_lock, current_git_parent_id
    logging.info('git_update_loop(%s)', username)
    git_rev = current_git_parent_id
    while True:
        with git_lock:
            origin_rev = git_fetch()
            if origin_rev != git_rev:
                logging.info("Updating Git to %s", origin_rev)
                git_reset(username)

        if origin_rev != git_rev:
            reset_clients()
            git_rev = origin_rev

        # This is to give the git_lock a better chance of resolving towards commits
        time.sleep(0.1)


def start_git_update_thread():
    username = sys.argv[1]

    logging.info("Doing initial git fetch...")
    git_fetch()
    git_reset(username)

    logging.info("Starting Git update thread, username is %s", username)
    t = threading.Thread(target=git_update_loop, args=(username,))
    t.daemon = True
    t.start()


def make_git_commit(parent_id, commit_id, commit_body):
    global current_git_parent_id, pushed_commits_total, pushed_commits_succeeded
    if parent_id != current_git_parent_id:
        logging.warning("make_git_commit(): parent %s is already outdated", parent_id)
        return

    logging.info("make_git_commit(): Committing %s to parent %s...", commit_id, parent_id)
    subprocess.Popen('git hash-object -t commit --stdin -w'.split(), stdin=subprocess.PIPE, stdout=subprocess.PIPE).communicate(commit_body)

    logging.info("make_git_commit(): Resetting to new commit %s...", commit_id)
    subprocess.check_output(('git reset --hard %s' % commit_id).split())

    logging.info("make_git_commit(): Pushing...")
    pushed_commits_total += 1
    if subprocess.call('git push origin master'.split()) == 0:
        logging.info('#' * 120)
        logging.info("   COMMIT SUCCESSFULLY SENT   ")
        logging.info('#' * 120)
        pushed_commits_succeeded += 1
    else:
        logging.info("Commit was too late :-(")
        subprocess.call('git reset --hard origin/master'.split())
    logging.info("%d of %d commits have succeeded so far", pushed_commits_succeeded, pushed_commits_total)

    username = sys.argv[1]
    git_reset(username)
    logging.info("make_git_commit(): Reset Git to rev %s...", current_git_parent_id)


def make_commit(parent_id, commit_id, commit_body):
    with git_lock:
        make_git_commit(parent_id, commit_id, commit_body)

    # Send Reset cmd to all clients
    reset_clients()


def reset_clients():
    logging.debug("reset_clients(): %d clients", len(client_sockets))
    for sock in client_sockets.values():
        try:
            sock.sendall('P %s\n' % current_git_parent_id)
            sock.sendall('T %s\n' % current_git_tree_id)
            sock.sendall('D %s\n' % current_difficulty)
            sock.sendall('R \n')
        except:
            # Probably the client has disappeared and we haven't noticed yet.
            pass


def connection_handler(client_id, conn, addr):
    global client_sockets

    data = conn.recv(6)
    if data != 'HELLO\n':
        conn.close()
        return

    conn.sendall("WELCOME %04d\n" % client_id)
    conn.sendall('P %s\n' % current_git_parent_id)
    conn.sendall('T %s\n' % current_git_tree_id)
    conn.sendall('D %s\n' % current_difficulty)
    conn.sendall('R \n')

    client_sockets[client_id] = conn
    logging.info("Client %d: welcoming complete", client_id)

    while True:
        cmd = conn.recv(1)
        if not cmd:
            # Client has left
            break

        if cmd != 'C':
            logging.error("Client %d sent unknown command %s", client_id, cmd)
            # Try to skip garbage
            conn.recv(4096)
            continue

        # Command format is 'C <40-char parent hash> <40-char commit id> <5-digit commit body length>\n<commit body>\n'
        assert conn.recv(1) == ' '
        parent_id = conn.recv(40)
        assert conn.recv(1) == ' '
        commit_id = conn.recv(40)
        assert conn.recv(1) == ' '
        commit_body_len = int(conn.recv(5))
        assert conn.recv(1) == '\n'
        commit_body = conn.recv(commit_body_len)
        assert conn.recv(1) == '\n'

        logging.info("!!!!!!!!!!     Client %d sent commit %s for parent %s     !!!!!!!!!!",
                     client_id, commit_id, parent_id)

        make_commit(parent_id, commit_id, commit_body)

    del client_sockets[client_id]
    logging.info("Client %d left", client_id)


def start_server():
    global next_client_id

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', TCP_PORT))
    s.listen(10)

    logging.info('start_server(): waiting for connection on port %d', TCP_PORT)
    while True:
        try:
            conn, addr = s.accept()
        except BaseException:
            logging.info('Emergency-closing the socket')
            s.shutdown(socket.SHUT_RDWR)
            raise

        client_id = next_client_id
        next_client_id += 1
        logging.info('Client %d: New connection from %s', client_id, addr)
        t = threading.Thread(target=connection_handler, args=(client_id, conn, addr))
        t.daemon = True
        t.start()


assert len(sys.argv) == 2

# Create Git updater thread
start_git_update_thread()
start_server()
