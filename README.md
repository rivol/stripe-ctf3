Here you can find the code I wrote for [Stripe's 3rd CTF](https://stripe-ctf.com/) (distributed systems).

Code written by me is licenced under the MIT licence. Note though that this repository also contains code from Stripe
and OpenSSL project.

# Level 0

Nothing too complex here. Load words from dictionary, then process text from standard input, highlighting words than
were not in the dictionary.

At first I wrote a straightforward Python solution.

Then, hoping for a speedup, I also created quite simple C++ solution. The speedup that I got was about 2.5x, which was
less than I had hoped for. But I wanted to move on.

# Level 1

Gitcoin mining (creating Git commits with certain hashes). This is where most of my time was spent and where I got my
highest rank - 6th.

My solution is a distributed CPU miner, consisting of coordinator (server) and miners (clients).

## Coordinator

As the name says, the coordinator oversees the mining process. It has three main responsibilities - fetching updates
from Git, notifying the miners when a commit had been made and committing and pushing hashes found by the miners.
The coordinator is written completely in Python.

It has one thread which continually executes `git fetch` and checks if the head's revision changed.
If there have been changes, then we update to latest state (using `git reset --hard origin/master`) and send a reset
message to all clients. The message contains Git's parent and tree ids and current difficulty - everything a miner needs
for mining.

The coordinator also has a simple TCP server that accepts connections from miners. This makes the miners almost
completely independent - they only need the coordinator's IP address. Miners can be added and removed at will. Every
miner gets a unique id to ensure that the hashes it generates are unique.

When a commit is received from a miner, we attempt to commit and push it to server. A lock is used to ensured only a
single Git operation is active at any time.

## Miners

Miners are finding the correct hashes via brute force. Miner is mostly written in Python which the inner loop written
in C, as Python extension.

Miners use Python's multiprocessing module to start up enough processes to keep all threads of the CPU busy. Every
process has two threads - the main one handles networking (listening to coordinator's updates) and the second one
handles mining.

Each mining thread first creates the static part of the commit message and then starts calculating hashes in blocks.
Each block is processed by the C extension and computes 120000 hashes before returning. This gave a reasonably good
balance between pure performance and reaction time - we check for stop condition after processing each block. The stop
condition is a simple variable that's set to true when the networking thread receives a reset message from the server.
This stops the computation thread and starts a new one with the updated state.

When a good hash is found, the commit body sent to the server which tries to commit & push it.

### The C extension

The main loop that calculates hashes is written in C code, as Python extension. It uses a few tricks to speed up its
inner loops and get as many hashes-per-second as possible.

For every iteration, we don't calculate the complete hash. Instead, only the nonce at the very end of the commit body
changes. The static part of the commit body is tuned to be a multiple of 64 (SHA-1 algorithm's block size) in length.
This means that for every iteration, we only need to hash a single block of data. The rest is precomputed and cached.

Nonces are in hex, instead of decimals, to make them faster to calculate (I wanted to avoid binary nonces, although Git
doesn't forbid them). Surprisingly, this alone gave 10% speedup after all the other optimizations.

SHA-1 calculation uses assembly code from OpenSSL project, optimized for 64-bit CPUs and AVX/SSE3 instruction sets. This
is the reason the miners probably won't work on older/different machines. The SHA-1 functions from Git's source code which
I initially used were pretty well optimized already and the switch to assembly didn't give very big boost.

### Compiling the extension

Execute the `hasher/build.sh` script to build the C extension. Note that it is meant to compile & run only on recent
CPUs - it assumes AVX or SSE3 instruction sets are available.

## Competition

In the competition, I used some AWS credits to have 4 c3.2xlarge machines mining (8 cores each), plus my personal
computer (4 cores, but faster than AWS ones). The total hashrate was about 130 MH/s.

In the end, [I ranked 6th](https://stripe-ctf.com/leaderboard/1). Majority of the ones above me used GPU miners and had
hash rates measured in GH/s. A lot of my points came from bonuses (since I mined something in most of rounds), while in
comparison my Elo rank was quite low.

# Level 2

A firewall to filter out evil DDOS requests while letting innocent ones pass as well as the keeping the servers busy
(even with evil requests).

The original code was written in Node.js (well, Javascript actually, I didn't write anything Node-specific myself) and
I modified it a bit to pass the level. This was also the level I spent the least amount of effort on.

My solution blacklists IPs after a certain amount of requests from a single IP or when too many requests are made in a
short period of time. This was made slightly more complex by the requirement to keep the servers busy, even if that
means processing evil requests. So if there have been no requests for some time, I always let the next one pass.
The various variables were hand-tuned to find reasonably good values.

# Level 3

Search server to find files and lines matching a word as quickly as possible. The files can be pre-processed.

The example solution was written in Scala. I hadn't used Scala before and found it quite interesting, but unfortunately
it kept randomly crashing for me. Sometimes during indexing, often during search and occasionally it managed to finish
without problems. I didn't get any backtraces either. I never found out what the problem was.
So I rewrote the solution... in Python (again).

My solution is based on [suffix arrays](https://en.wikipedia.org/wiki/Suffix_array) which allow very fast checking
whether a pre-processed string contains another string. During the pre-processing, I create a suffix array for every
file as well as for every line.
My first attempt was to keep everything in a single node, but it didn't work out due to memory constraints,
even without per-line SAs. To overcome that, I create three search nodes and distribute the files to be searched among
them (just like the example did). The main node sends the search query to each of the client nodes, awaits results and
combines them. The search nodes simply iterate over files/lines and check for substring matches, using the suffix
arrays.

I used [existing Python package](https://pypi.python.org/pypi/suffix_array) for suffix arrays,
[Flask](http://flask.pocoo.org/) for http server in the main node and simple TCP sockets for communication between
search nodes and the main node.

# Level 4

Distributed SQLite cluster.

Unfortunately I ran out of time and didn't manage to try out this one :-(

# Conclusion

Overall it was a lot of fun. [My final rank was 235th](https://stripe-ctf.com/achievements/Rivo) which wasn't too bad,
considering that I didn't participate in the last level.

I learned how to write Python extensions in C, dabbled in Git internals, wrote a pretty nice distributed computing
project and picked up a bit of Scala.
