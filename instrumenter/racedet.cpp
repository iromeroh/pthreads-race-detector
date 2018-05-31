#include <stdio.h>
#include <string.h>
#include <map>
#include <algorithm>
#include "comm_graph.h"
#include "lock_functions.h"
#include "fnv.h"

#include "pin.H"

#define HASH_MASK 0xffffff
#define HASH_SIZE 0x1000000

/*#define READ 1
  #define WRITE 2*/

#define FREE "free"
#define MALLOC "malloc"

#define REQUEST 1
#define NONE 0


#define START_MALLOCS_ADDR 0x7ffff7df0d30

#define DELETED 0
#define ALLOCATED 1
#define GLOBAL 2

extern char lock_func_sets[SETS][MAX_FUNC_NAME_SIZE];
extern char lock_functions[SETS][TYPES][MAX_FUNC_NAME_SIZE];

extern char lock_functions_get[SETS][TYPES][MAX_FUNC_NAME_SIZE];

typedef struct {
  unsigned long thid;
  unsigned long id;
  void * ipc;
  void * addr;
  unsigned char type;
  unsigned long timestamp;
} mem_access_entry;

mem_access_entry table[HASH_SIZE];

typedef std::pair <mem_access_entry, mem_access_entry> idiom;

std::vector<idiom> interleavings;

typedef std::map<unsigned long, unsigned long> Mem_Req_State;

Mem_Req_State memory_req_state;

typedef std::map<unsigned long, unsigned int> Mem_Asked;

Mem_Asked mem_asked;

typedef std::map <unsigned long, unsigned int> Memory_Map;

typedef std::map <unsigned long, unsigned int> Memory_Map_State;

typedef std::map <unsigned long, string> Memory_Map_Descr;

Memory_Map memory_map;
Memory_Map_State memory_map_state;
Memory_Map_Descr memory_map_descr;

std::map <unsigned long, unsigned long> lock_refs;
std::map <unsigned long, unsigned long> pthreads_lock_refs;

unsigned long hash_val;

class CompareAddr {
public:
  bool operator () (const unsigned long addr, std::pair <const unsigned long, unsigned int> & page) { return addr < page.first; }
  bool operator () (std::pair <const unsigned long, unsigned int> & page, const unsigned long addr) { return page.first + page.second < addr; }
};


KNOB<BOOL> KnobAllMemAccesses (KNOB_MODE_WRITEONCE, "pintool",
			       "am", "0" , "gather all memory accesses or just globals and heap");

KNOB<BOOL> KnobGenerateGraph (KNOB_MODE_WRITEONCE, "pintool",
			      "g", "0" , "generate program execution graph as graphviz .dot files");

KNOB<string> KnobOutputFile(KNOB_MODE_WRITEONCE, "pintool",
			    "o", "racedet.trace", "specify output file name");

KNOB<string> KnobMmapFile(KNOB_MODE_WRITEONCE, "pintool",
			  "m", "racedet.mem", "specify output memory map file name");

KNOB<string> KnobSrcMapFile(KNOB_MODE_WRITEONCE, "pintool",
			    "c", "racedet.src", "specify output source file map");

KNOB<string> KnobIdiomFile(KNOB_MODE_WRITEONCE, "pintool",
			   "i", "racedet.id", "specify output interleavings list");


unsigned long timestamp=0;
//Fnv64_t hash_val;
FILE * out;
PIN_LOCK lock;

unsigned int gather_all=0;

unsigned int generate_graph=0;

#ifdef PTHREAD_MT_GRAPH

FILE * graph_file;

map <unsigned long, graph> thread_graphs;
map <unsigned long, unsigned long> thread_state;

void save_idioms (FILE*file);

unsigned long
shash(unsigned char *str)
{
  unsigned long hash = 5381;
  int c;

  while ( (c = *str++) )
    hash = ((hash << 5) + hash) + c; /* hash * 33 + c */

  return hash;
}

map <std::string, unsigned int> files;
unsigned int counter=1;

unsigned int file_hash (std::string &str){
  map<std::string, unsigned int>::iterator itr=files.begin();
  if (str.empty())
    return 0;
  itr=files.find(str);
  if(itr==files.end()){
    files[str] = counter;
    counter ++;
  }
  return files[str];
}

/* Retrieves the last executed state of thread id, return 0 if none */
unsigned long graph_last_state(unsigned long thd)
{
  map<unsigned long, unsigned long>::iterator itr=thread_state.begin();
  itr=thread_state.find(thd);
  if(itr==thread_state.end())
    return 0;
  return thread_state[thd];	
}

/* Sets the last executed state of thread id*/
void graph_set_last_state(unsigned long thd, unsigned long state)
{
  thread_state[thd] = state;
}


/* Figures out if the graph for thread thd has been created or not */ 
bool graph_exists(unsigned long thd){
  map<unsigned long, graph>::iterator itr=thread_graphs.begin();
  itr=thread_graphs.find(thd);
  if(itr==thread_graphs.end())
    return false;
  return true;		
}

/* Creates a new graph for thread thd and sets the initial state */

bool graph_create(unsigned long thd, unsigned long state, unsigned long addr, unsigned long type, unsigned long ts, unsigned long th,
                  unsigned int l, unsigned int c, std::string &f)
{
  if (! graph_exists(thd))
    {
      graph gr;
      gr.tid = th;
      thread_graphs[thd] = gr;
      thread_graphs[thd].add_node (state, addr,  type, ts, th, l ,c, f);
      thread_state[thd] = state; 
      return true;
    }
  return false;
}


#ifdef LOCK_PROF
typedef std:: pair <node *, node*> interleaving;

vector <interleaving> idioms;

int find_idiom (unsigned long from_th, unsigned long from_id, unsigned long to_th, unsigned long to_id )
{
  int i = 0;
  node * f = NULL, * t = NULL;
  if (!graph_exists(from_th) || !graph_exists(to_th))
    return -4;   // missing graph, don't do anything
  if (thread_graphs[from_th].has_node(from_id))
    {
      f = thread_graphs[from_th].nodes[from_id];
    }else{
    return -3; // missing 'from' node, don't do anything
  }

  if (thread_graphs[to_th].has_node(to_id))
    {
      t = thread_graphs[to_th].nodes[to_id];
    }else{
    return -2; // missing 'to' node, don't do anything
  }
	
  for ( std::vector < interleaving>:: iterator itr = idioms.begin(); itr != idioms.end(); ++itr)
    {
      if (f == (*itr).first && t == (*itr).second)
	return i;
      i++;
    }
  return -1;  // nodes exist, but no idiom registered. It's OK to add this new one.
}

int add_idiom (unsigned long from_th, unsigned long from_id, unsigned long to_th, unsigned long to_id )
{
  node * f = NULL, * t = NULL;
  if (!graph_exists(from_th) || !graph_exists(to_th))
    return -4;   // missing graph, didn't do anything
  if (thread_graphs[from_th].has_node(from_id))
    {
      f = thread_graphs[from_th].nodes[from_id];
    }else{
    return -3; // missing 'from' node, didn't do anything
  }

  if (thread_graphs[to_th].has_node(to_id))
    {
      t = thread_graphs[to_th].nodes[to_id];
    }else{
    return -2; // missing 'to' node, didn't do anything
  }
  interleaving idiom = make_pair (f, t) ;
	
  idioms.push_back (idiom);
	
  //fprintf(stderr, "Runtime: ****************** Added idiom ***********************\n");
  return 1;
	
}

#endif


#endif


// Note that opening a file in a callback is only supported on Linux systems.
// See buffer-win.cpp for how to work around this issue on Windows.
//
// This routine is executed every time a thread is created.
VOID ThreadStart(THREADID threadid, CONTEXT *ctxt, INT32 flags, VOID *v)
{
  std::string empty;
  unsigned char label[1024];
  PIN_THREAD_UID uid;
  uid = PIN_ThreadUid();
  PIN_GetLock(&lock, threadid+1);
  timestamp++;

  //fprintf(out,"timestamp , thread , operation , addr , line , column , file\n"); 
  sprintf((char *)label,"0x%lx , 0x%lx , THREADSTART , 0x%lx , 0 , 0 , 0", (unsigned long)v, (unsigned long)uid, (unsigned long)v);

  if (generate_graph){
    hash_val = shash(label);
    graph_create(uid, hash_val, (unsigned long) v, THREAD_START, timestamp, uid,0,0,empty);
  }
  fprintf(out, "%ld , %s\n",timestamp, label);
  fflush(out);
  PIN_ReleaseLock(&lock);
}

// This routine is executed every time a thread is destroyed.
VOID ThreadFini(THREADID threadid, const CONTEXT *ctxt, INT32 code, VOID *v)
{
  std::string empty;
  unsigned char label[1024];
  PIN_THREAD_UID uid;
  uid = PIN_ThreadUid();
  char graph_file_name[256];
      
  sprintf (graph_file_name, "%s_%lx.dot", "racedet", (unsigned long)uid);
  FILE * graph;

  PIN_GetLock(&lock, threadid+1);

  hash_val = shash(label);
  timestamp ++;

  //fprintf(out,"timestamp , ipc, thread , operation , addr , line , column , file\n"); 
  sprintf((char *)label,"%ld , 0x%lx , 0x%lx , THREADEND , 0x%lx , 0 , 0 , 0", timestamp, (unsigned long) v, (unsigned long)uid, (unsigned long)v);

  if (generate_graph){
    pair<long, node*> * edge=NULL;
    unsigned long last_item_executed = graph_last_state(uid);
    if (!thread_graphs[uid].has_node(hash_val)){  // does this line id exist in the graph?
      thread_graphs[uid].add_node (hash_val, (unsigned long) v, THREAD_END, timestamp, uid, 0,0,empty);  // no, we have to create it.
    }
    edge = thread_graphs[uid].find_edge(last_item_executed, hash_val);
    if (! edge)  // does the edge between last item execited and id exist?
      { 
	// no, we have to create it
	thread_graphs[uid].add_edge(last_item_executed, hash_val, 1);
      }else{
      edge->first++;
    }
    graph_set_last_state(uid, hash_val);
  }
  fprintf(out, "%s\n",label);
  PIN_ReleaseLock(&lock);
  if (generate_graph){

    graph = fopen (graph_file_name, "w");
    if (graph != NULL)
      {
	fprintf(stderr, "Racedet: Saving graph for thread 0x%lx in file %s\n", (unsigned long)uid, graph_file_name);
	if (graph_exists (uid) )
	  {
	    thread_graphs[uid].save_to_dot(graph);
	    //thread_graphs[selfThd].save_to_dot(stderr);
	  } else{
	  fprintf (stderr, "Racedet error: Graph for thread 0x%lx doesn't exist!\n", (unsigned long)uid);
	}
	fclose(graph);
      }else{
      fprintf (stderr, "Runtime error: could not write graph for thread 0x%lx into file %s!\n", (unsigned long)uid, graph_file_name);
    }
  }
    
}

IMG mainExe;

// Print a memory read record
VOID RecordMemRead(VOID * ip, VOID * addr, THREADID threadid)
{
  INT32 line=0;
  INT32 column=0;
  string filename="";
  unsigned char label[1024];
  bool found;

  PIN_THREAD_UID uid;
  if (!gather_all){
    found = binary_search(memory_map.begin(),memory_map.end(), (unsigned long) addr, CompareAddr());
    if (!found){
      return;
    }
  }

  PIN_LockClient();
  IMG img = IMG_FindByAddress	((ADDRINT)ip);
  if (img != mainExe){
    PIN_UnlockClient();
    return;
  }
  PIN_GetSourceLocation((ADDRINT) ip,&column, &line, &filename);
  PIN_UnlockClient();
	
  uid = PIN_ThreadUid();
	
  unsigned long index = (unsigned long)addr & HASH_MASK;
  mem_access_entry * ref = & table[index];
  PIN_GetLock(&lock, threadid+1);
  timestamp++;
  //fprintf(out,"timestamp , thread , operation , addr , line , column , file\n"); 
  sprintf((char *)label,"0x%lx , 0x%lx , READ , 0x%lx , %d , %d , %d", (unsigned long)ip, (unsigned long)uid, (unsigned long)addr, line, column, file_hash(filename) );

  //	hash_val = fnv_64_str(label, hash_val);
  if (generate_graph){
    hash_val = shash(label);

    if (graph_exists(uid)){
      pair<long, node*> * edge=NULL;
      unsigned long last_item_executed = graph_last_state(uid);
      if (!thread_graphs[uid].has_node(hash_val)){  // does this line id exist in the graph?
	thread_graphs[uid].add_node (hash_val, (unsigned long) addr, MEM_READ, timestamp, uid, line, column, filename);  // no, we have to create it.
      }
      edge = thread_graphs[uid].find_edge(last_item_executed, hash_val);
      if (! edge)  // does the edge between last item execited and id exist?
	{ 
	  // no, we have to create it
	  thread_graphs[uid].add_edge(last_item_executed, hash_val, 1);
	}else{
	edge->first++;
      }
      graph_set_last_state(uid, hash_val);
    }else{
      //fprintf(stderr, "Creating graph for thread x%x\n", selfThd);
      graph_create(uid, hash_val, (unsigned long) addr, MEM_READ, timestamp, uid, line, column, filename);
    }
  }

  fprintf (out, "%ld , %s\n", timestamp, label);

  if (generate_graph){
    if ((ref->thid != uid) && (ref->type !=MEM_READ)){

      int result = find_idiom(ref->thid, ref->id, uid,hash_val);
      
      //fprintf (stderr, "Runtime: find_idiom() result was %d\n", result);
      
      if (result == -1)  // the nodes exist but there is no interleaving idiom between them... add it
	{
	  mem_access_entry old = *ref;
	  mem_access_entry new_a;
	  new_a.addr = addr;
	  new_a.ipc = ip;
	  new_a.thid = uid;
	  new_a.type = MEM_READ;
	  new_a.id = hash_val;
	  new_a.timestamp = timestamp;

	  idiom i = make_pair(old, new_a);
	  interleavings.push_back(i);

	  add_idiom(ref->thid, ref->id, uid, hash_val);
	}

      ref->addr = addr;
      ref->ipc = ip;
      ref->thid = uid;
      ref->type = MEM_READ;
      ref->id = hash_val;
      ref->timestamp = timestamp;

    }
  }
  PIN_ReleaseLock(&lock);
}

// Print a memory write record
VOID RecordMemWrite(VOID * ip, VOID * addr, THREADID threadid)
{
  INT32 line=0;
  INT32 column=0;
  string filename="";
  unsigned char label[1024];
  PIN_THREAD_UID uid;
  bool found;
  if (!gather_all){
    found = binary_search(memory_map.begin(),memory_map.end(), (unsigned long) addr, CompareAddr());
    if (!found)
      {
	return;
      }
  }
  PIN_LockClient();
  IMG img = IMG_FindByAddress	((ADDRINT)ip);
  if (img != mainExe){
    PIN_UnlockClient();
    return;
  }
  PIN_GetSourceLocation((ADDRINT) ip,&column, &line, &filename);
  PIN_UnlockClient();
  uid = PIN_ThreadUid();

  unsigned long index = (unsigned long)addr & HASH_MASK;
  mem_access_entry * ref = & table[index];
  PIN_GetLock(&lock, threadid+1);

  timestamp++;
  //fprintf(out,"timestamp , thread , operation , addr , line , column , file\n"); 
  sprintf((char *)label,"0x%lx , 0x%lx , WRITE , 0x%lx , %d , %d , %d", (unsigned long)ip, (unsigned long)uid, (unsigned long)addr, line, column, file_hash(filename) );

  if (generate_graph){
    //hash_val = fnv_64_str(label, hash_val);
    hash_val = shash(label);

    if (graph_exists(uid)){
      pair<long, node*> * edge=NULL;
      unsigned long last_item_executed = graph_last_state(uid);
      if (!thread_graphs[uid].has_node(hash_val)){  // does this line id exist in the graph?
	thread_graphs[uid].add_node (hash_val, (unsigned long) addr, MEM_WRITE, timestamp, uid, line, column, filename);  // no, we have to create it.
      }
      edge = thread_graphs[uid].find_edge(last_item_executed, hash_val);
      if (! edge)  // does the edge between last item execited and id exist?
	{ 
	  // no, we have to create it
	  thread_graphs[uid].add_edge(last_item_executed, hash_val, 1);
	}else{
	edge->first++;
      }
      graph_set_last_state(uid, hash_val);
    }else{
      //fprintf(stderr, "Creating graph for thread x%x\n", selfThd);
      graph_create(uid, hash_val, (unsigned long) addr, MEM_WRITE, timestamp, uid, line, column, filename);
    }
  }
  fprintf (out, "%ld , %s\n", timestamp , label);
  if (generate_graph){
    if (ref->addr == NULL)
      {
	ref->addr = addr;
	ref->ipc = ip;
	ref->thid = uid;
	ref->type = MEM_WRITE;
	ref->id = hash_val;
	ref->timestamp = timestamp;
	//fprintf(out,"THREAD %d : %p: W %p\n", threadid, ip, addr);
      }

    if ((ref->thid != uid)){

      int result = find_idiom(ref->thid, ref->id, uid,hash_val);
      
      //fprintf (stderr, "Runtime: find_idiom() result was %d\n", result);
      
      if (result == -1)  // the nodes exist but there is no interleaving idiom between them... add it
	{
	  mem_access_entry old = *ref;
	  mem_access_entry new_a;
	  new_a.addr = addr;
	  new_a.ipc = ip;
	  new_a.thid = uid;
	  new_a.type = MEM_WRITE;
	  new_a.id = hash_val;
	  new_a.timestamp = timestamp;

	  idiom i = make_pair(old, new_a);
	  interleavings.push_back(i);

	  add_idiom(ref->thid, ref->id, uid, hash_val);
	}

      ref->addr = addr;
      ref->ipc = ip;
      ref->thid = uid;
      ref->type = MEM_WRITE;
      ref->id = hash_val;
      ref->timestamp = timestamp;

    }    
  }

  PIN_ReleaseLock(&lock);
}

// Is called for every instruction and instruments reads and writes
VOID Instruction(INS ins, VOID *v)
{
  // Instruments memory accesses using a predicated call, i.e.
  // the instrumentation is called iff the instruction will actually be executed.
  //
  // On the IA-32 and Intel(R) 64 architectures conditional moves and REP 
  // prefixed instructions appear as predicated instructions in Pin.
  UINT32 memOperands = INS_MemoryOperandCount(ins);

  // Iterate over each memory operand of the instruction.
  for (UINT32 memOp = 0; memOp < memOperands; memOp++)
    {
      if (INS_MemoryOperandIsRead(ins, memOp))
        {
	  INS_InsertPredicatedCall(
				   ins, IPOINT_BEFORE, (AFUNPTR)RecordMemRead,
				   IARG_INST_PTR,
				   IARG_MEMORYOP_EA, memOp,
				   IARG_THREAD_ID,
				   IARG_END);
        }
      // Note that in some architectures a single memory operand can be 
      // both read and written (for instance incl (%eax) on IA-32)
      // In that case we instrument it once for read and once for write.
      if (INS_MemoryOperandIsWritten(ins, memOp))
        {
	  INS_InsertPredicatedCall(
				   ins, IPOINT_BEFORE, (AFUNPTR)RecordMemWrite,
				   IARG_INST_PTR,
				   IARG_MEMORYOP_EA, memOp,
				   IARG_THREAD_ID,
				   IARG_END);
        }
    }
}

extern char lock_functions[SETS][TYPES][MAX_FUNC_NAME_SIZE];


/* ===================================================================== */
/* Analysis routines                                                     */
/* ===================================================================== */
 
VOID LockBefore(ADDRINT addr, THREADID thid, VOID *ipc, UINT32 set, UINT32 sem)
{
  INT32 line=0;
  INT32 column=0;
  string filename="";
  unsigned char label[1024];
  PIN_THREAD_UID uid;
  uid = PIN_ThreadUid();
	

  PIN_LockClient();
  PIN_GetSourceLocation((ADDRINT) ipc,&column, &line, &filename);
  PIN_UnlockClient();

  PIN_GetLock(&lock, thid+1);

  switch (set){
   case PTHREADS_SEM:
     pthreads_lock_refs[uid] = (unsigned long)addr;
     break;
  }

  timestamp ++;

  //fprintf(out,"timestamp , thread , operation , addr , line , column , file\n"); 

  //fprintf (stdout, "BEF: Thread 0x%lx, op %s lock addr is : 0x%lx\n", (unsigned long) uid, lock_functions[set][sem], lock_refs[uid]);
  sprintf((char *)label,"0x%lx , 0x%lx , %s , 0x%lx , %d , %d , %d", (unsigned long)ipc, (unsigned long)uid, lock_functions[set][sem] ,  (unsigned long)addr, line, column, file_hash(filename) );
  if(generate_graph){
  hash_val = shash(label);

  if (graph_exists(uid)){
    pair<long, node*> * edge=NULL;
    unsigned long last_item_executed = graph_last_state(uid);
    if (!thread_graphs[uid].has_node(hash_val)){  // does this line id exist in the graph?
      thread_graphs[uid].add_node (hash_val, (unsigned long) addr, LOCK_REQ, timestamp, uid,
				   line, column, filename);  // no, we have to create it.
    }
    edge = thread_graphs[uid].find_edge(last_item_executed, hash_val);		
    if (!edge)  // does the edge between last item execited and id exist?
      { 
	// no we have to create it
	thread_graphs[uid].add_edge(last_item_executed, hash_val, 1);
      }else{
      edge->first++;
    }
    graph_set_last_state(uid, hash_val);
  }else{
    //fprintf(stderr, "Creating graph for thread x%x\n", selfThd);
    graph_create(uid, hash_val, (unsigned long) addr, LOCK_REQ, timestamp, uid, line, column, filename);
  }
  }
  fprintf (out, "%ld , %s\n", timestamp , label);

  /*fprintf(out,  "THREAD: 0x%lx,  IPC: 0x%lx,  %s: ( 0x%lx  ), line: %d, filename: %s\n", (unsigned long)uid  , (unsigned long)ipc,
    lock_functions[set][sem], ((unsigned long)size), line, filename.c_str() );*/
  PIN_ReleaseLock(&lock);
}

VOID LockAfter(THREADID thid, VOID * ipc, ADDRINT ret , UINT32 set, UINT32 sem)
{
  INT32 line=0;
  INT32 column=0;
  string filename="";
  unsigned char label[1024];
  PIN_THREAD_UID uid;
  uid = PIN_ThreadUid();

  unsigned long addr=0;

  PIN_LockClient();
  PIN_GetSourceLocation((ADDRINT) ipc,&column, &line, &filename);
  PIN_UnlockClient();

  PIN_GetLock(&lock, thid+1);

  //	sprintf((char *)label,"THREAD-0x%lx-IPC-%lx-LOCK_GET-0x%lx", (unsigned long)uid, (unsigned long)ipc, (unsigned long) lock_refs[uid]);
  //hash_val = fnv_64_str(label, hash_val);

  timestamp ++;

  //fprintf (stdout, "AFT: Thread 0x%lx, op %s lock addr is : 0x%lx\n", (unsigned long) uid, lock_functions_get[set][sem], lock_refs[uid]);

  //fprintf(out,"timestamp , thread , operation , addr , line , column , file\n"); 
  switch (set) {
    case PTHREADS_SEM:
      addr = pthreads_lock_refs[uid];
      break;
    default:
      addr = (unsigned long) ret;
  }
  sprintf((char *)label,"0x%lx , 0x%lx , %s , 0x%lx , %d , %d , %d", (unsigned long) ipc, (unsigned long)uid, lock_functions_get[set][sem] ,  addr, line, column, file_hash(filename) );
  if (generate_graph){
    hash_val = shash(label);

    if (graph_exists(uid)){
      pair<long, node*> * edge=NULL;
      unsigned long last_item_executed = graph_last_state(uid);
      if (!thread_graphs[uid].has_node(hash_val)){  // does this line id exist in the graph?
	thread_graphs[uid].add_node (hash_val, (unsigned long) lock_refs[uid], LOCK_GET, timestamp, uid,
				     line, column, filename);  // no, we have to create it.
      }
      edge = thread_graphs[uid].find_edge(last_item_executed, hash_val);		
      if (!edge)  // does the edge between last item execited and id exist?
	{ 
	  // no we have to create it
	  thread_graphs[uid].add_edge(last_item_executed, hash_val, 1);
	}else{
	edge->first++;
      }
      graph_set_last_state(uid, hash_val);
    }else{
      //fprintf(stderr, "Creating graph for thread x%x\n", selfThd);
      graph_create(uid, hash_val, lock_refs[uid], LOCK_GET, timestamp, uid, line, column, filename);
    }
  }
  fprintf (out, "%ld , %s\n", timestamp , label);
  //lock_refs[uid] = 0;
  PIN_ReleaseLock(&lock);
}

VOID UnlockBefore(ADDRINT size, THREADID thid, VOID *ipc , UINT32 set, UINT32 sem)
{
  INT32 line=0;
  INT32 column=0;
  string filename="";
  unsigned char label[1024];
  PIN_THREAD_UID uid;
  uid = PIN_ThreadUid();

  PIN_LockClient();
  PIN_GetSourceLocation((ADDRINT) ipc,&column, &line, &filename);
  PIN_UnlockClient();

  PIN_GetLock(&lock, thid+1);


  //	sprintf((char *)label,"THREAD-0x%lx-IPC-%p-UNLOCK_REQ-0x%lx", (unsigned long)uid, ipc,(unsigned long)size);


  timestamp ++;

  sprintf((char *)label,"0x%lx , 0x%lx , %s , 0x%lx , %d , %d , %d", (unsigned long)ipc, (unsigned long)uid, lock_functions[set][sem] ,  (unsigned long)size, line, column, file_hash(filename) );

  if (generate_graph){
    hash_val = shash(label);

    if (graph_exists(uid)){
      pair<long, node*> * edge=NULL;
      unsigned long last_item_executed = graph_last_state(uid);
      if (!thread_graphs[uid].has_node(hash_val)){  // does this line id exist in the graph?
	thread_graphs[uid].add_node (hash_val, (unsigned long) size, LOCK_REL, timestamp, uid,
				     line, column, filename);  // no, we have to create it.
      }
      edge = thread_graphs[uid].find_edge(last_item_executed, hash_val);		
      if (!edge)  // does the edge between last item execited and id exist?
	{ 
	  // no we have to create it
	  thread_graphs[uid].add_edge(last_item_executed, hash_val, 1);
	}else{
	edge->first++;
      }
      graph_set_last_state(uid, hash_val);
    }else{
      //fprintf(stderr, "Creating graph for thread x%x\n", selfThd);
      graph_create(uid, hash_val, (unsigned long) size, LOCK_REL, timestamp, uid, line, column, filename);
    }
  }
  fprintf (out, "%ld , %s\n", timestamp , label);

  /*	fprintf(out,  "THREAD: 0x%lx,  IPC: 0x%lx, %s : ( 0x%lx  ) , line: %d, filename: %s\n", (unsigned long) uid  , (unsigned long)ipc,
    lock_functions[set][sem], ((unsigned long)size), line, filename.c_str());*/
  PIN_ReleaseLock(&lock);
}

VOID UnlockAfter(THREADID thid, VOID * ipc , UINT32 set, UINT32 sem)
{
  /*  INT32 line=0;
      string filename="";
      PIN_THREAD_UID uid;
      uid = PIN_ThreadUid();

      PIN_LockClient();
      PIN_GetSourceLocation((ADDRINT) ipc,NULL, &line, &filename);
      PIN_UnlockClient();

      PIN_GetLock(&lock, thid+1);
      fprintf(out, "THREAD: 0x%lx, IPC: 0x%lx, %s called , line: %d, filename: %s\n", (unsigned long)uid, (unsigned long) ipc,
      lock_functions[set][sem], line, filename.c_str());
      PIN_ReleaseLock(&lock);*/
}

VOID FreeBefore(THREADID thid, VOID * ip, ADDRINT param)
{
  INT32 line=0;
  INT32 column=0;
  string filename="";
  unsigned char label[1024];

  int n = memory_map.count(param);
  PIN_THREAD_UID uid;

  uid = PIN_ThreadUid();

  PIN_LockClient();
  PIN_GetSourceLocation((ADDRINT) ip,&column, &line, &filename);
  PIN_UnlockClient();


  PIN_GetLock(&lock, thid+1);
  //fprintf(stdout, "malloc_mt: Trying to erase 0x%lx\n", param );

  timestamp ++;

  //fprintf(out,"timestamp , thread , operation , addr , line , column , file\n"); 
  sprintf((char *)label,"%ld , 0x%lx , 0x%lx , free , 0x%lx , %d , %d , %d", timestamp, (unsigned long)ip, (unsigned long)uid,   (unsigned long)param, line, column, file_hash(filename) );


  if (n != 0){
    
    memory_map_state[param] = DELETED;
    fprintf(out, "%s\n", label);
  }else{
    fprintf(stderr, "Racedet error: tried to erase an unknown region! IPC: 0x%lx\n", (unsigned long)ip);
  }
  PIN_ReleaseLock(&lock);
}



VOID MallocBefore(THREADID thid,VOID * ip, ADDRINT size)
{
  PIN_THREAD_UID uid;
  uid = PIN_ThreadUid();

  //TraceFile << name << "(" << size << ")" << endl;
  if( (unsigned long) ip == START_MALLOCS_ADDR){
    //fprintf(out, "THREAD: %d, IPC: 0x%lx, OS: %ld\n", thid, (unsigned long)ip, size);
  }
  else
    {
      PIN_GetLock(&lock, thid+1);
      memory_req_state[uid] = REQUEST;
      mem_asked[uid] = size;
      //fprintf(out, "THREAD: %d, IPC: 0x%lx, malloc(): %ld\n", thid, (unsigned long)ip, size);
      PIN_ReleaseLock(&lock);
    }
  
}

VOID MallocAfter(THREADID thid,VOID * ip, ADDRINT ret)
{
	
  INT32 line=0;
  INT32 column=0;
  string filename="";
  char label[1024];
  PIN_THREAD_UID uid;
  uid = PIN_ThreadUid();

   
        
  PIN_LockClient();
  PIN_GetSourceLocation((ADDRINT) ip,&column, &line, &filename);
  PIN_UnlockClient();

  if(memory_req_state[uid] == REQUEST)
    {
      if (ret == 0){  // malloc failed
	mem_asked[uid] = 0;
	return;
      }

      PIN_GetLock(&lock, thid+1);
      //TraceFile << "  returns " << ret << endl;
      memory_map[ret] = mem_asked[uid];
      memory_map_state[ret] = ALLOCATED;
      memory_req_state[uid] = NONE;

      timestamp ++;

      //fprintf(out,"timestamp , thread , operation , addr , line , column , file\n"); 
      sprintf((char *)label,"%ld , 0x%lx , 0x%lx , malloc , 0x%lx , %d , %d , %d", timestamp, (unsigned long)ip, (unsigned long)uid,   (unsigned long)ret, mem_asked[uid], line, file_hash(filename) );

      memory_map_descr[ret] = std::string(label) ;
      mem_asked[uid] = 0;
      fprintf(out, "%s\n", label);
      PIN_ReleaseLock(&lock);
    }else{
    fprintf(stderr, "Racedet : malloc()return without 1st call! IPC: 0x%lx\n" , (unsigned long)ip);
  }
}

//====================================================================
// Instrumentation Routines
//====================================================================

// This routine is executed for each image.
VOID ImageLoad(IMG img, VOID *)
{
  // Instrument the malloc() and free() functions.  Print the input argument
  // of each malloc() or free(), and the return value of malloc().
  //
  //  Find the malloc() function.
    
  if (IMG_IsMainExecutable (img)){
    mainExe = img;
  }
 
  RTN mallocRtn = RTN_FindByName(img, MALLOC);
  if (RTN_Valid(mallocRtn))
    {
      RTN_Open(mallocRtn);

      // Instrument malloc() to print the input argument value and the return value.
      RTN_InsertCall(mallocRtn, IPOINT_BEFORE, (AFUNPTR)MallocBefore,
		     IARG_THREAD_ID,
		     IARG_INST_PTR,
		     IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
		     IARG_END);

      RTN_InsertCall(mallocRtn, IPOINT_AFTER, (AFUNPTR)MallocAfter,
		     IARG_THREAD_ID,
		     IARG_INST_PTR,
		     IARG_FUNCRET_EXITPOINT_VALUE, IARG_END);
      RTN_Close(mallocRtn);
    }

  // Find the free() function.
  RTN freeRtn = RTN_FindByName(img, FREE);
  if (RTN_Valid(freeRtn))
    {
      RTN_Open(freeRtn);
      // Instrument free() to print the input argument value.
      RTN_InsertCall(freeRtn, IPOINT_BEFORE, (AFUNPTR)FreeBefore,
		     IARG_THREAD_ID,
		     IARG_INST_PTR,
		     IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
		     IARG_END);
      RTN_Close(freeRtn);
    }


  RTN pthreads_lockRtn = RTN_FindByName(img, "pthread_mutex_lock");
  if (RTN_Valid(pthreads_lockRtn))
    {
      RTN_Open(pthreads_lockRtn);

      // Instrument pthread_mutex_lock() to print the input argument value and the return value.
      RTN_InsertCall(pthreads_lockRtn, IPOINT_BEFORE, AFUNPTR(LockBefore),
		     IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
		     IARG_THREAD_ID, IARG_INST_PTR, 
		     IARG_UINT32, PTHREADS_SEM,
		     IARG_UINT32, REQ_LOCK,
		     IARG_END);
                       
      RTN_InsertCall(pthreads_lockRtn, IPOINT_AFTER, (AFUNPTR)LockAfter,
		     IARG_THREAD_ID,
		     IARG_INST_PTR,
		     IARG_FUNCRET_EXITPOINT_VALUE,
		     IARG_UINT32, PTHREADS_SEM,
		     IARG_UINT32, GOT_LOCK,
		     IARG_END);

      RTN_Close(pthreads_lockRtn);
    }
        
  RTN pthreads_unlockRtn = RTN_FindByName(img, "pthread_mutex_unlock");
  if (RTN_Valid(pthreads_unlockRtn))
    {
      RTN_Open(pthreads_unlockRtn);

      // Instrument pthread_mutex_lock() to print the input argument value and the return value.
      RTN_InsertCall(pthreads_unlockRtn, IPOINT_BEFORE, AFUNPTR(UnlockBefore),
		     IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
		     IARG_THREAD_ID, IARG_INST_PTR, 
		     IARG_UINT32, PTHREADS_SEM,
		     IARG_UINT32, RELEASE_LOCK,

		     IARG_END);
                       
      /*        RTN_InsertCall(unlockRtn, IPOINT_AFTER, (AFUNPTR)UnlockAfter,
		IARG_THREAD_ID,
		IARG_INST_PTR,
		IARG_FUNCRET_EXITPOINT_VALUE, IARG_END);*/
      RTN_InsertCall(pthreads_unlockRtn, IPOINT_AFTER, (AFUNPTR)UnlockAfter,
		     IARG_THREAD_ID,
		     IARG_INST_PTR,
		     IARG_UINT32, PTHREADS_SEM,
		     IARG_UINT32, RELEASE_LOCK,
		     IARG_END);

      RTN_Close(pthreads_unlockRtn);
    }

    
    
}

// This routine is executed once at the end.
VOID Fini(INT32 code, VOID *v)
{
  Memory_Map::const_iterator itr;
  map<std::string, unsigned int>::const_iterator fmap_itr;
  char from_type_str[20];
  char to_type_str[20];

  vector<idiom>::const_iterator i_itr;

  fclose(out);

  out = fopen (KnobMmapFile.Value().c_str(), "w");  

  if (out != NULL){
    std::string str;
    fprintf(out, "Address , Size , Freed? , Description\n");
  
    for (itr = memory_map.begin(); itr != memory_map.end(); ++itr)
      {
	str = memory_map_descr[(*itr).first];
	str.erase (std::remove (str.begin(), str.end(), ' '), str.end()); 
	std::replace(str.begin(), str.end(), ',' , ':');
	fprintf(out, "0x%lx , %d , %s , %s\n", (*itr).first, (*itr).second, memory_map_state[(*itr).first]? ( memory_map_state[(*itr).first]==1? "NO": "GLOBAL" ):"YES", str.c_str());
      }
    fclose(out);
  }else{
    PIN_ERROR("Unable to create memory map " + KnobMmapFile.Value() +"\n");
  }

  out = fopen (KnobSrcMapFile.Value().c_str(), "w");  

  if (out != NULL){
  
    fprintf(out, "id , Filename\n");

    for(fmap_itr = files.begin(); fmap_itr != files.end(); ++fmap_itr)
      {
	fprintf(out, " %d , %s\n",  (unsigned int)((*fmap_itr).second), ((*fmap_itr).first).c_str());
      }
    fclose(out);
  }else{
    PIN_ERROR("Unable to create source file map " + KnobSrcMapFile.Value() +"\n");
  }

  // KnobIdiomFile
  /*typedef struct {
    unsigned long thid;
    unsigned long id;
    void * ipc;
    void * addr;
    unsigned char type;
    unsigned long timestamp;
    } mem_access_entry;*/

  if (generate_graph){
  out = fopen (KnobIdiomFile.Value().c_str(), "w");  

  if (out != NULL){
    mem_access_entry from, to;

    fprintf(out, "from_timestamp , to_timestamp , from_thread, to_thread , from_op , to_op , addr\n");
    for (i_itr = interleavings.begin(); i_itr != interleavings.end(); ++i_itr){
      from = (*i_itr).first;
      to = (*i_itr).second;
      fill_type_str(from_type_str, from.type);
      fill_type_str(to_type_str, to.type);
      fprintf(out, "%ld , %ld , 0x%lx , 0x%lx , %s , %s , 0x%lx\n", from.timestamp , to.timestamp , from.thid , to.thid , from_type_str, to_type_str, (unsigned long) to.addr);
    }

    fclose(out);

  }else{
    PIN_ERROR("Unable to create idiom list file " + KnobIdiomFile.Value() +"\n");
  }
  }

  if (generate_graph){
  char graph_file_name[256] = "racedet_overall.dot";

  FILE * gr = fopen (graph_file_name, "w");
  int i =0;
  if (gr != NULL)
    {
      fprintf (gr, "digraph {\n");
      fprintf (gr, "     compound=true;\n");
	
      for (map<unsigned long, graph>::iterator itr=thread_graphs.begin(); itr != thread_graphs.end(); ++itr)
	{
	  (*itr).second.save_to_subgraph(gr, i);
	  i++;
	}
      save_idioms (gr);
      fprintf (gr, "}\n");
    }

  fclose(gr);
  }

}

KNOB<string> KnobSymbolFile(KNOB_MODE_WRITEONCE,
                            "pintool", "s", "default.lst", "specify list of symbols file name");

char tool_name[] = "thread scheduler 1.0";

bool read_symbol_list()
{
  FILE * in;
  unsigned long addr;
  unsigned int size;
  char name[1024];
  int ret=0;
  in = fopen(KnobSymbolFile.Value().c_str(), "r");
  if (in==NULL){
    PIN_ERROR("Unable to open symbol list " + KnobSymbolFile.Value() +"\n");
    return false;
  }
  
  while (ret != EOF){
    ret = fscanf (in, "%lx %d %s", &addr, &size, name);
    
    if (ret == 3)
      {
	if (size > 0)
	  {
	    memory_map[addr] = size;
	    memory_map_state[addr] = GLOBAL;
	    memory_map_descr[addr] = name;
	    //fprintf(stdout, "ADDR: 0x%lx SIZE: %d NAME: %s\n", addr, size, name);
	  }
      }
  }
  
  fclose(in);
  return true;
}

/* ===================================================================== */
/* Print Help Message                                                    */
/* ===================================================================== */

INT32 Usage()
{
  PIN_ERROR("This Pintool prints a trace of malloc calls in the guest application\n"
	    + KNOB_BASE::StringKnobSummary() + "\n");
  return -1;
}

/* ===================================================================== */
/* Main                                                                  */
/* ===================================================================== */

int main(INT32 argc, CHAR **argv)
{
  // Initialize the pin lock
  PIN_InitLock(&lock);
	
  // Initialize pin
  if (PIN_Init(argc, argv)) return Usage();
  PIN_InitSymbols();
	
  out = fopen(KnobOutputFile.Value().c_str(), "w");
  fprintf(out,"timestamp , ipc , thread , operation , addr , line , column , file\n"); 

  if (KnobAllMemAccesses){
    gather_all = 1;
    fprintf(stderr, "Racedet: gathering all memory accesses\n");
  }
  else{
    gather_all = 0;
    fprintf(stderr, "Racedet: NOT gathering all memory accesses\n"); 
  }

  if (KnobGenerateGraph){
    generate_graph = 1;
    fprintf(stderr, "Racedet: generating graphs\n");
  }
  else{
    generate_graph = 0;
    fprintf(stderr, "Racedet: NOT generating graphs\n");
  }
	
  //gather_all = 0;

  memset(&table[0], 0, HASH_SIZE * sizeof(mem_access_entry));
	
  read_symbol_list();
	
  // Register ImageLoad to be called when each image is loaded.
  IMG_AddInstrumentFunction(ImageLoad, 0);
	
  // Register Instruction to be called when every instruction runs
  INS_AddInstrumentFunction(Instruction, 0);
	
  // Register Analysis routines to be called when a thread begins/ends
  PIN_AddThreadStartFunction(ThreadStart, 0);
  PIN_AddThreadFiniFunction(ThreadFini, 0);
	
  // Register Fini to be called when the application exits
  PIN_AddFiniFunction(Fini, 0);
	
  // Never returns
  PIN_StartProgram();
	
  return 0;
}
