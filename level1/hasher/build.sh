#!/bin/sh

mkdir -p build

FLAGS="-pthread -fno-strict-aliasing -DNDEBUG -fwrapv -O3 -Wall -Wstrict-prototypes -fPIC -I/usr/include/python2.7 -ffast-math -march=native -DSHA1_ASM -DOPENSSL_IA32_SSE2 -DL_ENDIAN"

gcc $FLAGS -c -o build/hasher.o hasher.c
gcc $FLAGS -c -o build/sha_dgst.o openssl/sha_dgst.c
gcc $FLAGS -c -o build/sha1-x86_64.o openssl/sha1-x86_64.s
gcc $FLAGS -c -o build/cryptlib.o openssl/cryptlib.c
gcc $FLAGS -c -o build/x86_64cpuid.o openssl/x86_64cpuid.s

gcc -pthread -shared -Wl,-O3 -Wl,-Bsymbolic-functions -Wl,-Bsymbolic-functions -Wl,-z,relro -ffast-math -march=native \
        -o build/hasher.so  build/hasher.o build/cryptlib.o build/sha_dgst.o build/x86_64cpuid.o build/sha1-x86_64.o

ln -fs hasher/build/hasher.so ../hasher.so
