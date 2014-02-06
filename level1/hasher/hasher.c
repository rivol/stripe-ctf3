#include <Python.h>
#include <stdio.h>   // debugging

#include "openssl/cryptlib.h"
#include "openssl/sha.h"


int bin_value(char ch)
{
    if('0'<=ch && ch<='9')
    {
        return ch - '0';
    }
    else if('a'<=ch && ch<='z')
    {
        return ch - 'a' + 0x0A;
    }
    else if('A'<=ch && ch<='Z')
    {
        return ch - 'A' + 0x0A;
    }
    else
    {
        return -1;
    }
}


static PyObject* hasher_solve(PyObject *self, PyObject *args)
{
    PyByteArrayObject *source_obj;
    const char *source;
    int source_len;
    const char *difficulty_hex;
    int i_start, i_end, i;
    SHA_CTX template_ctx;

    if (!PyArg_ParseTuple(args, "Oiis", &source_obj, &i_start, &i_end, &difficulty_hex)) {
        return NULL;
    }
    source = PyByteArray_AsString((PyObject*) source_obj);
    source_len = PyByteArray_Size((PyObject*) source_obj);
    if (source_len != 256) {
        return NULL;
    }

    // Convert difficulty from hex to bin
    unsigned char difficulty[20];
    for (i = 0; i < 20; i++) {
        difficulty[i] = bin_value(difficulty_hex[i*2]) << 4 | bin_value(difficulty_hex[i*2 + 1]);
    }

    // Prepare template context
    SHA1_Init(&template_ctx);
    SHA1_Update(&template_ctx, source, source_len);

    static const char idx2hex[] = "0123456789abcdef";
    char i_buf[10] = "000000000";
    for (i = i_start; i < i_end; i++) {
        i_buf[8] = idx2hex[(i & 0x000000f) >> 0];
        i_buf[7] = idx2hex[(i & 0x00000f0) >> 4];
        i_buf[6] = idx2hex[(i & 0x0000f00) >> 8];
        i_buf[5] = idx2hex[(i & 0x000f000) >> 12];
        i_buf[4] = idx2hex[(i & 0x00f0000) >> 16];
        i_buf[3] = idx2hex[(i & 0x0f00000) >> 20];
        i_buf[2] = idx2hex[(i & 0xf000000) >> 24];

        SHA_CTX ctx = template_ctx;
        SHA1_Update(&ctx, i_buf, 9);
        unsigned char hashout[20];
        SHA1_Final(hashout, &ctx);

        if (memcmp(hashout, difficulty, 20) < 0) {
//            fprintf(stderr, "!!! HIT: %s: %02x%02x%02x%02x%02x%02x%02x%02x%02x%02x\n", i_buf, hashout[0], hashout[1], hashout[2], hashout[3], hashout[4], hashout[5], hashout[6], hashout[7], hashout[8], hashout[9]);
            return Py_BuildValue("i", i);
        }
    }

    Py_RETURN_NONE;
}


static PyMethodDef HasherMethods[] = {
    {"solve",  hasher_solve, METH_VARARGS, "Solve stuff."},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

PyMODINIT_FUNC
inithasher(void)
{
    OPENSSL_cpuid_setup();
    (void) Py_InitModule("hasher", HasherMethods);
}
