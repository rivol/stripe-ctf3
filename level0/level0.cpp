#include <unordered_set>
#include <list>
#include <fstream>
#include <iostream>
#include <string>
#include <cstring>
#include <cctype>
#include <cstdio>

using namespace std;


inline void check(const int last_str_start, const int i, const char* buf, const char* buf_lower, const unordered_set<string>& entries) {
    if (last_str_start < i) {
        string word(buf_lower + last_str_start, i - last_str_start);
        bool in_entries = entries.find(word) != entries.end();
        if (in_entries) {
            fwrite(buf + last_str_start, 1, i - last_str_start, stdout);
        } else {
            fputc('<', stdout);
            fwrite(buf + last_str_start, 1, i - last_str_start, stdout);
            fputc('>', stdout);
        }
    }
}

void process_c(const unordered_set<string>& entries) {
    const int max_len = 100000;
    char buf[max_len];
    char buf_lower[max_len];
    while (fgets(buf, max_len, stdin) != NULL) {
        int line_len = strlen(buf);
        int last_str_start = 0;
        for (int i = 0; i < line_len; i++) {
            buf_lower[i] = tolower(buf[i]);
            if (buf_lower[i] == ' ' || buf_lower[i] == '\n') {
                check(last_str_start, i, buf, buf_lower, entries);
                fputc(buf_lower[i], stdout);
                last_str_start = i+1;
            }
        }
        check(last_str_start, line_len, buf, buf_lower, entries);
    }
}

int main(int argc, char**argv) {
    const char default_dict_filename[] = "/usr/share/dict/words";
    
    const char* dict_filename = (argc > 1) ? argv[1] : default_dict_filename;
    list<string> entries_list;
    std::ifstream dict(dict_filename);
    for (string line; getline(dict, line); ) {
        entries_list.push_back(line);
    }
    unordered_set<string> entries(entries_list.begin(), entries_list.end());

    process_c(entries);

    return 0;
}
