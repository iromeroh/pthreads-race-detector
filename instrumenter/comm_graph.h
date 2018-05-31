#ifndef __COMM_GRAPH_H
#define __COMM_GRAPH_H

#include <stdio.h>
#include <iostream>
#include <vector>
#include <map>
#include <string>

#define PTHREAD_MT_GRAPH
#define LOCK_PROF

 #ifdef PTHREAD_MT_GRAPH

#define MEM_READ 1
#define MEM_WRITE 2
#define LOCK_REQ 3
#define LOCK_GET 4
#define LOCK_REL 5
#define THREAD_START 6
#define THREAD_END 7


using namespace std;

std::vector<std::string> &split(const std::string &s, char delim, std::vector<std::string> &elems);

struct node{
    vector< pair< long ,node * > > adj; //cost of edge, destination node
    unsigned long line_id;
    unsigned int line;
    unsigned int column;
    string file;
    unsigned long type;
    unsigned long addr;
    unsigned long timestamp;
    unsigned long thread;
    
    node(unsigned long, unsigned long, unsigned long, unsigned long, unsigned long);

    void set_debug_info(unsigned int, unsigned int, std::string &);
};

    

typedef pair<long,node*> ve;

typedef map<unsigned long, node *> vmap;

class graph
{
   public:
    unsigned long tid;
    vmap nodes;
    bool has_node(unsigned long);
    bool add_node(unsigned long, unsigned long, unsigned long, unsigned long, unsigned long, unsigned int, unsigned int, std::string &);
    pair<long, node*> * find_edge (unsigned long, unsigned long);
    bool add_edge(unsigned long from, unsigned long to, long cost);
    bool save_to_dot(FILE*);
    #ifdef LOCK_PROF
    bool save_to_subgraph(FILE*, unsigned long);
    #endif
};

void fill_type_str(char *type_str, unsigned int type);

#endif

#endif
