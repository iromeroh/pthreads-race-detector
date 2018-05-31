#include <iostream>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include "comm_graph.h"

using namespace std;


#ifdef PTHREAD_MT_GRAPH

std::vector<std::string> &split(const std::string &s, char delim, std::vector<std::string> &elems)
{
  std::stringstream sstr(s);
  std::string item;
  while (std::getline(sstr, item, delim)) {
    elems.push_back(item);
  }
  return elems;
}

string get_file_only(string &s)
{
  std::vector<string> sv;
  split(s,'/',sv);
  if (sv.size() > 0)
    return sv.back();
  return string("");
}


node::node (unsigned long id, unsigned long address, unsigned long tp, unsigned long ts, unsigned long th)
{
  line_id = id;
  type = tp;
  addr = address;
  timestamp = ts;
  thread = th;

  line = 0;
  column = 0;
}

void node::set_debug_info(unsigned int l, unsigned int c, std::string &f){
  line = l;
  column = c;
  file = f;
}

bool graph::add_node(unsigned long id, unsigned long addr, unsigned long tp, unsigned long ts, unsigned long th, unsigned int l,
                     unsigned int c, std::string & f)
{
  vmap::iterator itr=nodes.begin();
  itr=nodes.find(id);
  if(itr==nodes.end())
    {
      node *v;
      v= new node(id, addr, tp, ts, th);
      v->set_debug_info(l,c,f);
      nodes[id]=v;
      return true;
    }
  return false;
}

bool graph::has_node (unsigned long id)
{
  vmap::iterator itr=nodes.begin();
  itr=nodes.find(id);
  if(itr==nodes.end())
    return false;
  return true;
}

pair<long, node*> * graph::find_edge (unsigned long from, unsigned long to)
{
  if (has_node(from) && has_node(to)){
    node *f=(nodes.find(from)->second);
    node *t=(nodes.find(to)->second);
    for(std::vector<ve>::iterator it = f->adj.begin(); it != f->adj.end(); ++it)
      {
	if ((*it).second == t)  // is the second element equals to 'to'?
	  {
	    return & (*it);
	  }
      }
    return NULL; // we don't have the edge, but the nodes exist
  }
  return NULL; // one or both nodes are missing, so no, we don't have the edge
}

bool graph::add_edge(unsigned long from, unsigned long to, long cost)
{
  if (has_node(from) && has_node(to))
    {
      node *f=(nodes.find(from)->second);
      node *t=(nodes.find(to)->second);
      pair<long,node *> edge = make_pair(cost,t);
      f->adj.push_back(edge);
      return 1;
    }
  return 0;
}

bool sort_nodes (node* first, node *second)
{
  return first->timestamp < second->timestamp;
}

void fill_type_str(char *type_str, unsigned int type)
{
  if ( type == MEM_READ )
    strcpy (type_str, "READ");
  else if ( type == MEM_WRITE )
    strcpy (type_str, "WRITE");
  else if ( type == LOCK_GET )
    strcpy (type_str, "LOCKGET");
  else if ( type == LOCK_REL )
    strcpy (type_str, "LOCKREL");
  else if ( type == LOCK_REQ )
    strcpy (type_str, "LOCKREQ");
  else if ( type == THREAD_START )
    strcpy (type_str, "THREADSTART");
  else if ( type == THREAD_END )
    strcpy (type_str, "THREADEND");
  else
    strcpy (type_str, "UNKNOWN");
}

#ifdef PTHREAD_MT_GRAPH
#ifdef LOCK_PROF

typedef std:: pair <node *, node*> interleaving;

extern vector <interleaving> idioms;

#endif

#endif



bool graph::save_to_dot(FILE* file)
{
  std::vector< node* > vec;
  char from_type_str[30];
  char to_type_str[30];
  unsigned long from_addr;
  unsigned long to_addr;
  unsigned int line;
  string filename;
	
  unsigned long from_id;
  unsigned long to_id;
  fprintf(file, "digraph {\n");
  fprintf(file, "     label = \"Thread %lx\";\n" , tid);
  for(vmap::iterator itr=nodes.begin(); itr != nodes.end(); ++itr)
    {
      vec.push_back ( itr->second);
    }
	
  std::sort (vec.begin(), vec.end(), sort_nodes);
	
  for (vector < node* >::iterator iter=vec.begin(); iter != vec.end(); ++iter)
    {
      fill_type_str(from_type_str, (*iter)->type); 
      from_addr = (*iter)->addr;
      from_id = (*iter)->line_id;
      line = (*iter)-> line;
      filename = (*iter)->file;
      fprintf(file, "     %s_%lx_%lx [label=\"%s_%lx_%d_%s\"];\n", from_type_str , from_addr , from_id ,  from_type_str , from_addr, line, (const char *)(get_file_only(filename)).c_str() );
    }

  for (vector < node* >::iterator nodes_itr=vec.begin(); nodes_itr != vec.end(); ++nodes_itr)
    {
      fill_type_str(from_type_str, (*nodes_itr)->type); 
      from_addr = (*nodes_itr)->addr;
      from_id = (*nodes_itr)->line_id;
      for(std::vector<ve>::iterator it = (*nodes_itr)->adj.begin(); it != (*nodes_itr)->adj.end(); ++it)
	{
	  fill_type_str(to_type_str, (*it).second->type); 
	  to_addr = (*it).second->addr;
	  to_id = (*it).second->line_id;
	  fprintf(file, "     %s_%lx_%lx -> %s_%lx_%lx [label=\"%ld\" , fontcolor=blue ];\n",from_type_str, from_addr, from_id, to_type_str, to_addr, to_id, (*it).first);
	}
    }
  fprintf(file, "}\n");
  return true;
}

bool graph::save_to_subgraph(FILE* file, unsigned long index)
{
  std::vector< node* > vec;
  char from_type_str[30];
  char to_type_str[30];
  unsigned long from_addr;
  unsigned long to_addr;
  unsigned int line;
  string filename;
	
  unsigned long from_id;
  unsigned long to_id;
	
  unsigned long thread1, thread2;
  fprintf(file, "     subgraph cluster_%ld{\n", index);
  fprintf(file, "          label = \"Thread %lx\";\n" , tid);
  for(vmap::iterator itr=nodes.begin(); itr != nodes.end(); ++itr)
    {
      vec.push_back ( itr->second);
    }
	
  std::sort (vec.begin(), vec.end(), sort_nodes);
	
  for (vector < node* >::iterator iter=vec.begin(); iter != vec.end(); ++iter)
    {
      fill_type_str(from_type_str, (*iter)->type); 
      from_addr = (*iter)->addr;
      from_id = (*iter)->line_id;
      from_id = (*iter)->line_id;
      line = (*iter)-> line;
      filename = (*iter)->file;
      thread1 = (*iter)->thread;
      fprintf(file, "          %s_%lx_%lx_%lx [label=\"%s_%lx_%d_%s\"];\n", from_type_str , from_addr , from_id , thread1, from_type_str , from_addr, line, (const char *)(get_file_only(filename)).c_str() );
    }

  for (vector < node* >::iterator nodes_itr=vec.begin(); nodes_itr != vec.end(); ++nodes_itr)
    {
      fill_type_str(from_type_str, (*nodes_itr)->type); 
      from_addr = (*nodes_itr)->addr;
      from_id = (*nodes_itr)->line_id;
      thread1 = (*nodes_itr)->thread;
      for(std::vector<ve>::iterator it = (*nodes_itr)->adj.begin(); it != (*nodes_itr)->adj.end(); ++it)
	{
	  fill_type_str(to_type_str, (*it).second->type); 
	  to_addr = (*it).second->addr;
	  to_id = (*it).second->line_id;
	  thread2 = (*it).second->thread;
	  fprintf(file, "          %s_%lx_%lx_%lx -> %s_%lx_%lx_%lx [label=\"%ld\" , fontcolor=blue ];\n",from_type_str, from_addr, from_id, thread1, to_type_str, to_addr, to_id, thread2, (*it).first);
	}
    }
    
  fprintf(file, "     }\n");
  return true;
}


void save_idioms (FILE*file)
{
  char from_type_str[30];
  char to_type_str[30];
  unsigned long from_addr;
  unsigned long to_addr;
	
  unsigned long from_id;
  unsigned long to_id;
  unsigned long thread1, thread2;

  for ( vector<interleaving>::iterator iit = idioms.begin(); iit != idioms.end(); ++iit)
    {
      //fprintf (stderr,"Found idiom starting on this node\n");
      fill_type_str(from_type_str, (*iit).first->type);
      from_addr = (*iit).first->addr;
      from_id = (*iit).first->line_id;
			
      thread1 = (*iit).first->thread;

      fill_type_str(to_type_str, (*iit).second->type);
      to_addr = (*iit).second->addr;
      to_id = (*iit).second->line_id;
      thread2 = (*iit).second->thread;

      fprintf(file, "     %s_%lx_%lx_%lx -> %s_%lx_%lx_%lx [color=red];\n",from_type_str, from_addr, from_id, thread1, to_type_str, to_addr, to_id, thread2);
    }
}


#endif
