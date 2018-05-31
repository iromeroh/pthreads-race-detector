#! /usr/bin/env python

import glob
import os
import shutil
import csv

import sys, getopt
import operator

from datetime import datetime, timedelta


timeout = 5 # default maximum execution time in minutes

start_timestamp = 0 # we start from the beginning
end_timestamp = 0 # we end and the last line


pre_recording_ts = 10

post_recording_ts = 10


def fitem(item):
	item=item.strip()
	try:
		item=int(item,0)
	except ValueError:
		pass
	return item

def addr_to_var (addr, memsym):
	if addr in memsym["Address"]:
		return memsym["Description"][memsym["Address"].index(addr)]
	else:
		for idx, m_addr in enumerate(memsym["Address"]):
			if addr >= m_addr and addr< m_addr + memsym["Size"][ idx ]:
				if memsym["Freed?"][idx] == "GLOBAL":
					return memsym["Description"][idx]
				else:
					return "heap memory index: "+ hex(idx)
		return 'other memory'

def get_line( number, filename):
	try:
		with open(filename, 'r') as f:
			content = f.readlines()
			if number >0 and number <= len(content):
				return content[number-1]
	except:
				return ""
	
	
def get_file_name (filename):
	items = filename.split('/')
	return items[-1]

def grapher (tracefile, graphfile, memsym, srcf):
	global timeout
	global start_timestamp
	global end_timestamp
	from collections import namedtuple
	Interleaving = namedtuple("Interleaving", ["first_op","first_addr","first_thread", "first_ipc","second_op","second_addr","second_thread", "second_ipc"])
	Threadpair = namedtuple("Threadpair",["first","second"])
	
	Knownissue = namedtuple("Knownissue", ["itype" , "ax_ipc" , "bx_ipc", "cx_ipc" , "dx_ipc"] )
	
	State = namedtuple("State", ["operation","thread", "addr", "ipc","line","srcfile"])
	
	Transition = namedtuple("Transition" , ["src" , "tgt"])
	

	
	graph = {}
	
	graph_last_state = {}

	transitions = {}
	
	interleavings = {}
	
	access = {}
	threadpairs = {}
	

	ln = 0
	
	period = timedelta(minutes=1)
	next_time = datetime.now() + period
	minutes = 0
	
	
	with open(tracefile, 'r') as trace:
		for line in trace:
			#print line
			items = line.split(",");
			#print items
			if  ln>0:
			
				curr_thread = int(items[2],0)
				
				curr_access  = {}
				curr_access ["timestamp"] = int(items[0], 0)
				curr_access ["ipc"] = int(items[1],0)
				curr_access ["thread"] = int(items[2],0)
				curr_access ["operation"] = items[3].strip()
				curr_access ["addr"] = int(items[4],0)
				curr_access ["line"] = int(items[5],0)
				curr_access ["column"] = int(items[6],0)
				curr_access["src"] = int(items[7],0)
				
				if curr_access["src"] != 0:
					curr_access["src_file"] = srcf["Filename"][ srcf["id"].index(curr_access["src"])]
				else:
					curr_access["src_file"] = "no source info"
					
				if curr_access["timestamp"] >=  end_timestamp and end_timestamp > 0:
					print "Last timestamp ("+ str(end_timestamp) + ") reached. Exiting"
					break

				if curr_access["timestamp"] >=  start_timestamp:
					
					
					new_state = State( operation = curr_access["operation"] , thread = curr_access["thread"], addr= curr_access["addr"], ipc= curr_access["ipc"],line = curr_access["line"],srcfile = curr_access["src_file"])
					
					if curr_thread not in graph:
						graph[ curr_thread ] = {}
						
					
					if new_state not in graph[ curr_thread ]:
						graph[ curr_thread ][new_state] =  curr_access
					
					if curr_thread not in graph_last_state:
						graph_last_state [curr_thread] = curr_access
						continue
						 
					
					prev_access = graph_last_state[curr_thread]
					
					
					old_state = State( operation = prev_access["operation"] , thread = prev_access["thread"] ,addr= prev_access["addr"], ipc= prev_access["ipc"],line = prev_access["line"],srcfile = prev_access["src_file"])
					
					transition = Transition ( src=old_state, tgt = new_state)
					
					if curr_access["thread"] not in transitions:
						transitions[ curr_access["thread"] ] = {}
					
					if transition not in transitions[ curr_access["thread"] ]:
						transitions[ curr_access["thread"] ] [transition] = 1 # we store in the dict the number of times this transition is taken
						
						#print "New transition: " + str(transition)
					else:
						transitions[ curr_access["thread"] ] [transition] += 1
						
					# This code handles interleavings
					
					if curr_access["addr"] not in access:
						access[ curr_access["addr"] ] = curr_access
					else:
						prev_i_access = access[ curr_access["addr"] ]
						
											
						if (prev_i_access["addr"] == curr_access["addr"]) and (prev_i_access["thread"] != curr_access["thread"]) :
					
							if (prev_i_access["operation"] == "READ" or prev_i_access["operation"] == "WRITE")  and (curr_access["operation"] == "READ" or curr_access["operation"] == "WRITE") and  prev_i_access["operation"] != curr_access["operation"]  :
							
								print prev_i_access["operation"] + " on addr "+ hex(prev_i_access["addr"]) +" -> " + curr_access["operation"] + " on addr "+ hex(curr_access["addr"])
								
								state1 = State( operation = prev_i_access["operation"] , thread = prev_i_access["thread"] ,addr= prev_i_access["addr"], ipc= prev_i_access["ipc"],line = prev_i_access["line"],srcfile = prev_i_access["src_file"])
								
								state2 = new_state
								
								state1_found = False
								state2_found = False
								
								#print "\ngraph keys are: " + str(graph.keys())
								
								#print "\n graph is: " + str(graph)
								
								for i, th in enumerate ( graph.keys() ) :
									
									#print str(th)
									
									if th in graph:
										
										#print "graph "+hex(th) + " in graph : " +  str(graph[th])

										if state1 in graph[th]:
											#print "state1 found " + str(state1)
											state1_found = True
										
										if state2 in graph[th]:
											#print "state2 found " + str(state2)
											state2_found = True
								if state1_found and state2_found:
									print "Adding new interleaving transition"
									i_transition = Transition ( src=state1, tgt = state2)
									
									if i_transition not in interleavings:
										interleavings[i_transition] = 1
									else:
										interleavings[i_transition] += 1
								else:
									print "Transition states not found"
									#print "\nState1 is " + str(state1)
									#print "\nState2 is " + str(state2)
						access[ curr_access["addr"] ] = curr_access		
					
					graph_last_state [curr_thread] = curr_access
						
			ln += 1	
			if next_time <= datetime.now():
				minutes +=1
				next_time += period
			if minutes >= timeout:
				print "Timeout of "+str(timeout) +" minutes reached. Exiting";
				
				print "First timestamp:  " + str(start_timestamp) + ", last timestamp : " +str( curr_access["timestamp"])
				break
			
	from operator import itemgetter
	
	threads = graph.keys()
	
	with open(graphfile, 'w') as gr:
				
		gr.write("digraph {\n")
		gr.write("    compound=true;\n")
		
		for n, thread in enumerate(threads):
			items = sorted(graph[thread].values(), key=itemgetter("timestamp"), reverse=False)
			
			gr.write("    subgraph cluster_"+str(n)+"{\n")
			
			gr.write("        label = \"Thread " + hex(thread)+ "\";\n")

			
			for n, item in enumerate(items):
				
				code_line = get_line(item["line"], item["src_file"]).replace('\"','\\\"')
				
				code_line = code_line.replace('\n',' ')
				
				code_line = code_line.replace('\\n', '<nl>')
				
				gr.write("        "+item["operation"].replace('@','_') +"_"+hex(item["addr"])+"_"+hex(item["ipc"])+"_"+hex(item["thread"])+"_"+str(item["timestamp"])+" [label=\""+item["operation"].replace('@','_') +","+ hex(item["addr"]) +"\\nline "+ str(item["line"]) +", "+ get_file_name(item["src_file"])+"\\n"+ code_line + "\" shape=box")
				 
				if n == 0:
					gr.write(" color=blue ")
				 
				gr.write ("];\n")
					
			items = transitions[thread].keys()
			
			for item in items:
				#print "Transition src is " + str(item.src)
				#print "Transition tgt is " + str(item.tgt)
				gr.write ("        "+ item.src.operation.replace('@','_')+"_"+hex(item.src.addr)+"_"+hex(item.src.ipc)+"_"+hex(item.src.thread)+"_"+ str(graph[thread][item.src]["timestamp"]) +" -> ")
				gr.write ( item.tgt.operation.replace('@','_')+"_"+hex(item.tgt.addr)+"_"+hex(item.tgt.ipc)+"_"+hex(item.tgt.thread)+"_"+ str(graph[thread][item.tgt]["timestamp"]) + "[label=\""+ str(transitions[thread][item]) +"\" , fontcolor=blue ];\n")
				
			
			gr.write("   }\n")

		items = interleavings.keys()
		
		#print "interleaving items are: "+ str(items)
		
		for item in items:
			#print "\nTransition src is " + str(item.src)
			#print "Transition tgt is " + str(item.tgt)
			
			#print "\ngraph [item.src.thread][item.src] = " + str(graph[item.src.thread][item.src])
			
			gr.write ("        "+ item.src.operation.replace('@','_')+"_"+hex(item.src.addr)+"_"+hex(item.src.ipc)+"_"+hex(item.src.thread)+"_"+ str( graph[item.src.thread][item.src]["timestamp"])  +" -> ")
			
			gr.write ( item.tgt.operation.replace('@','_')+"_"+hex(item.tgt.addr)+"_"+hex(item.tgt.ipc)+"_"+hex(item.tgt.thread)+"_"+ str(graph[item.tgt.thread][item.tgt]["timestamp"]) + "[label=\""+ str(interleavings[item]) +"\" , fontcolor=blue color=\"red\" ];\n")

		gr.write("}\n")

# ********************************************************************************************************************************************************************

def explainer (tracefile, graphfile, memsym, srcf, explain, csvreport):
	global timeout
	from collections import namedtuple
	Interleaving = namedtuple("Interleaving", ["first_op","first_addr","first_thread", "first_ipc","second_op","second_addr","second_thread", "second_ipc"])
	Threadpair = namedtuple("Threadpair",["first","second"])
	
	Knownissue = namedtuple("Knownissue", ["itype" , "ax_ipc" , "bx_ipc", "cx_ipc" , "dx_ipc"] )
	
	State = namedtuple("State", ["operation","thread", "addr", "ipc","line","srcfile"])
	
	Transition = namedtuple("Transition" , ["src" , "tgt"])
	
	lock_funcs = ["pthread_mutex_lock", "mem_lock_acquire", "mem_slab_lock", "page_pool_lock"]
	lock_get_funcs = ["pthread_mutex_lock@get", "mem_lock_acquire@get", "mem_slab_lock@get","page_pool_lock@get"]
	unlock_funcs = ["pthread_mutex_unlock", "mem_lock_release" , "mem_slab_unlock","page_pool_unlock"]
	
	print "explain is: " + str(explain)
	
	print "csvreport[id] is: " + str(csvreport["id"])
	
	if explain not in csvreport["id"]:
		print "Error: issue " + str(explain) + " not in CSV report. Exiting"
		exit (4)
	else:
		issue_index = csvreport["id"].index(explain)
		issue_type = csvreport["type"][issue_index]
		
		print "issue_index is " + str(issue_index) + " , issue type is " + str(issue_type) 
		
		target_thread = []
		
		target_thread.append( csvreport["ax_thread"][issue_index] )
		target_thread.append( csvreport["bx_thread"][issue_index] )
		
		starts = []
		
		starts.append( csvreport["ax_timestamp"][issue_index] - pre_recording_ts )
		starts.append( csvreport["bx_timestamp"][issue_index] - pre_recording_ts )
		
		if (issue_type != 1):
			starts.append( csvreport["cx_timestamp"][issue_index] - pre_recording_ts )
			starts.append( csvreport["dx_timestamp"][issue_index] - pre_recording_ts)
			
		
		starts.sort()
		
		ends = []
		
		if issue_type == 1 or issue_type == 0:
			if csvreport["ax_timestamp"][issue_index] + post_recording_ts < starts[1]:
				ends.append( csvreport["ax_timestamp"][issue_index] + post_recording_ts )
			ends.append( csvreport["bx_timestamp"][issue_index] + post_recording_ts)
		
		
		
		if issue_type > 1:
			
			#if csvreport["ax_timestamp"][issue_index] + post_recording_ts < starts[1]:
			if starts[0] + post_recording_ts < starts[1]:
				ends.append( csvreport["ax_timestamp"][issue_index] + post_recording_ts )
			#if csvreport["bx_timestamp"][issue_index] + post_recording_ts < starts[2]:
			if starts[1] + post_recording_ts < starts[2]:
				ends.append( csvreport["bx_timestamp"][issue_index] + post_recording_ts )
			#if csvreport["cx_timestamp"][issue_index] + post_recording_ts < starts[3]:
			if starts[2] + post_recording_ts < starts[3]:
				ends.append( csvreport["cx_timestamp"][issue_index] + post_recording_ts )
			ends.append( csvreport["dx_timestamp"][issue_index] + post_recording_ts)
		

	
	graph = {}
	
	graph_last_state = {}

	transitions = {}
	
	interleavings = {}
	
	access = {}
	threadpairs = {}
	
	threads = {}
	
	ln = 0
	
	period = timedelta(minutes=1)
	next_time = datetime.now() + period
	minutes = 0
	
	recording = False
	
	nolock = {}
	nolock ["timestamp"] = 0
	nolock ["ipc"] = 0
	nolock ["thread"] = 0
	nolock ["operation"] = "no_lock"
	nolock ["addr"] = 0
	
	nolock ["line"] = 0
	nolock ["column"] = 0
	nolock["src"] = 0
	nolock["src_file"] = "no_source"
	
	nolock["block"] = -1
		
	block = 0
	
	with open(tracefile, 'r') as trace:
		for line in trace:
			#print line
			items = line.split(",");
			#print items
			if  ln>0:
			
				curr_thread = int(items[2],0)
				
				curr_access  = {}
				curr_access ["timestamp"] = int(items[0], 0)
				timestamp = curr_access ["timestamp"]
				curr_access ["ipc"] = int(items[1],0)
				curr_access ["thread"] = int(items[2],0)
				thread = curr_access ["thread"]
				curr_access ["operation"] = items[3].strip()
				curr_access ["addr"] = int(items[4],0)
				
				curr_access ["line"] = int(items[5],0)
				curr_access ["column"] = int(items[6],0)
				curr_access["src"] = int(items[7],0)
				
				curr_access["block"] = block
				
				if curr_access["src"] != 0:
					curr_access["src_file"] = srcf["Filename"][ srcf["id"].index(curr_access["src"])]
				else:
					curr_access["src_file"] = "no source info"
					
				if curr_access["timestamp"] >=  end_timestamp and end_timestamp > 0:
					print "Last timestamp ("+ str(end_timestamp) + ") reached. Exiting"
					break
				
				if curr_access["operation"] == "THREADSTART": #we have a new thread
					threads[thread] = {}
					threads[thread]["state"] = "started"
					threads[thread]["lock"] = []
					threads[thread]["lock_addr"] = []
					threads[thread]["lockstate"] = []
					print "New thread "+hex(thread)

					
				if curr_access["operation"] == "THREADEND": #we have a thread ending
					threads[thread]["state"] = "ended"
					print "Thread " + hex(thread) +" ended"
					
				#if curr_access["operation"] in lock_funcs: # thread called a lock function
				#	threads[thread]["lock"].append(curr_access["operation"])
				#	threads[thread]["lock_addr"].append(curr_access["addr"])
				#	threads[thread]["lockstate"].append (curr_access)
				#	print "Thread "+hex(thread) + " requested a lock using " +  curr_access["operation"]+ " using object on address "+ hex( curr_access["addr"])
				
				if curr_access["operation"] in lock_get_funcs: # thread obtained a lock
					
					#print "curr_access[\"operation\"] = " + curr_access["operation"]
					#print "threads[thread][\"lock\"][-1] = " + threads[thread]["lock"][-1]
					
					##f lock_get_funcs.index(curr_access["operation"]) == lock_funcs.index (threads[thread]["lock"][-1]): #ops are of same type
				#	print "threads[thread][\"lock_addr\"][-1] = " + hex(threads[thread]["lock_addr"][-1])
						
				#	if threads[thread]["lock_addr"][-1] == curr_access["addr"]:
					threads[thread]["lock"].append (curr_access["operation"])
					threads[thread]["lockstate"].append ( curr_access)
					threads[thread]["lock_addr"].append(curr_access["addr"])
				
						
				if curr_access["operation"] in unlock_funcs: #thread is releasing a lock
					if len(threads[thread]["lock"]) > 0:
						
						#if unlock_funcs.index(curr_access["operation"]) == lock_get_funcs.index (threads[thread]["lock"][-1]):
						
						op_found = False
						
						paired_op1 = lock_get_funcs[ unlock_funcs.index(curr_access["operation"]) ]
						#paired_op2 = lock_funcs[ unlock_funcs.index(curr_access["operation"]) ]
						
						if paired_op1  in threads[thread]["lock"]: # or paired_op2  in threads[thread]["lock"]:
							
							indices = [i for i, x in enumerate(threads[thread]["lock"]) if x == paired_op1 ] # or x == paired_op2 ]
							
							for i in indices[::-1]:
							
								if threads[thread]["lock_addr"][i] == curr_access["addr"]:
									#print "curr_access[\"operation\"] = "+ curr_access["operation"] + " found in the list at index " + str(i)
									#print "ts: "+ str(timestamp)
									del threads[thread]["lock"][i]
									del threads[thread]["lock_addr"][i]
									del threads[thread]["lockstate"][i]
									op_found = True
									break
								#else:
								#	print "curr_access[\"operation\"] = "+ curr_access["operation"]
								#	print "threads[thread][\"lock\"][i] = " + threads[thread]["lock"][i]

							if not op_found:
								print "Error on timestamp "+str(timestamp)+": unlock over unknown lock object "+hex(curr_access["addr"])
								print curr_access["operation"]
								print threads[thread]["lock"]
								exit (5)
						else:
							print "Error on timestamp "+str(timestamp)+": unlock and last lock aren't of same API type on thread " + hex(thread)
							print "curr_access[\"operation\"] = "+ curr_access["operation"]
							print "paired_op = "+ paired_op
							print "threads[thread][\"lock\"] = " + str(threads[thread]["lock"])
							exit(7)
					else:
						print "Error on timestamp "+ str(timestamp)+": tried to unlock without a lock"
						exit(6)

				if curr_access["timestamp"] in  starts:
					recording = True
					block += 1


					
				if curr_access["timestamp"] in ends:
					recording = False
					
					
				if curr_access["timestamp"] == ends[-1]:  # we are at the last timestamp of interest
					break
					
				if recording and thread in target_thread:
					new_state = State( operation = curr_access["operation"] , thread = curr_access["thread"], addr= curr_access["addr"], ipc= curr_access["ipc"],line = curr_access["line"],srcfile = curr_access["src_file"])
					
					if curr_thread not in graph:
						graph[ curr_thread ] = {}
						
						print "First state for thread "+hex(curr_thread)
						if len(threads[curr_thread]["lockstate"]) > 0:
							print "Thread " + hex(curr_thread) + " has a lock"
							last_lock = threads[curr_thread]["lockstate"][-1]
						else:
							print "Thread " + hex(curr_thread) + " has NO lock"
							last_lock = nolock
							last_lock["thread"] = curr_thread
						
							
						lock_state = State( operation = last_lock["operation"] , thread = last_lock["thread"], addr= last_lock["addr"], ipc= last_lock["ipc"],line = last_lock["line"],srcfile = last_lock["src_file"])
						
						
						if lock_state not in graph[ curr_thread ]:
							graph[ curr_thread ][lock_state] =  last_lock
						
						if curr_thread not in graph_last_state:
							graph_last_state [curr_thread] = last_lock						
						
						
					
					if new_state not in graph[ curr_thread ]:
						graph[ curr_thread ][new_state] =  curr_access
					
					if curr_thread not in graph_last_state:
						graph_last_state [curr_thread] = curr_access
						continue
						 
					
					prev_access = graph_last_state[curr_thread]
					
					
					old_state = State( operation = prev_access["operation"] , thread = prev_access["thread"] ,addr= prev_access["addr"], ipc= prev_access["ipc"],line = prev_access["line"],srcfile = prev_access["src_file"])
					
					transition = Transition ( src=old_state, tgt = new_state)
					
					if curr_access["thread"] not in transitions:
						transitions[ curr_access["thread"] ] = {}
					
					if transition not in transitions[ curr_access["thread"] ]:
						transitions[ curr_access["thread"] ] [transition] = 1 # we store in the dict the number of times this transition is taken
						
						#print "New transition: " + str(transition)
					else:
						transitions[ curr_access["thread"] ] [transition] += 1
						
					# This code handles interleavings
					
					
					if curr_access["addr"] not in access:
						access[ curr_access["addr"] ] = curr_access
					else:
						prev_i_access = access[ curr_access["addr"] ]
						
											
						if (prev_i_access["addr"] == curr_access["addr"]) and (prev_i_access["thread"] != curr_access["thread"]) :
							
					
							if (prev_i_access["operation"] == "READ" or prev_i_access["operation"] == "WRITE")  and (curr_access["operation"] == "READ" or curr_access["operation"] == "WRITE") and  (prev_i_access["operation"] != curr_access["operation"])  :
							
								print prev_i_access["operation"] + " on addr "+ hex(prev_i_access["addr"]) +" -> " + curr_access["operation"] + " on addr "+ hex(curr_access["addr"])
								
								state1 = State( operation = prev_i_access["operation"] , thread = prev_i_access["thread"] ,addr= prev_i_access["addr"], ipc= prev_i_access["ipc"],line = prev_i_access["line"],srcfile = prev_i_access["src_file"])
								
								state2 = new_state
								
								state1_found = False
								state2_found = False
								
								#print "\ngraph keys are: " + str(graph.keys())
								
								#print "\n graph is: " + str(graph)
								
								for i, th in enumerate ( graph.keys() ) :
									
									#print str(th)
									
									if th in graph:
										
										#print "graph "+hex(th) + " in graph : " +  str(graph[th])

										if state1 in graph[th]:
											#print "state1 found " + str(state1)
											state1_found = True
										
										if state2 in graph[th]:
											#print "state2 found " + str(state2)
											state2_found = True
								if state1_found and state2_found:
									print "Adding new interleaving transition"
									i_transition = Transition ( src=state1, tgt = state2)
									
									if i_transition not in interleavings:
										interleavings[i_transition] = 1
									else:
										interleavings[i_transition] += 1
								else:
									print "Transition states not found"
									#print "\nState1 is " + str(state1)
									#print "\nState2 is " + str(state2)
						access[ curr_access["addr"] ] = curr_access		
					
					graph_last_state [curr_thread] = curr_access
						
			ln += 1	
			if next_time <= datetime.now():
				minutes +=1
				next_time += period
			if minutes >= timeout:
				print "Timeout of "+str(timeout) +" minutes reached. Exiting";
				
				print "First timestamp:  " + str(start_timestamp) + ", last timestamp : " +str( curr_access["timestamp"])
				break
			
	from operator import itemgetter
	
	threads = graph.keys()
	
	with open(graphfile, 'w') as gr:
				
		gr.write("digraph {\n")
		gr.write("    compound=true;\n")
		gr.write("    forcelabels=true;\n")
		gr.write("    concentrate=true;\n")
		
		in_cluster = False
		
		for n, thread in enumerate(threads):
			items = sorted(graph[thread].values(), key=itemgetter("timestamp"), reverse=False)
			
			#gr.write("    subgraph cluster_"+str(n)+"{\n")
			
			#gr.write("        label = \"Thread " + hex(thread)+ "\";\n")

			
			
			for n, item in enumerate(items):
				
				code_line = get_line(item["line"], item["src_file"]).replace('\"','\\\"')
				
				code_line = code_line.replace('\n',' ')
				
				code_line = code_line.replace('\\n', '<nl>')
				
				xlabel = ''
				
				if n>0:
					if item["block"] != items[n-1]["block"] :
						if in_cluster:
							gr.write("   }\n")
							in_cluster = False
						
						#if item["block"] <= 4:
						gr.write("    subgraph cluster_thread_"+hex(item["thread"])+"_"+str(item["block"])+"{\n")
						gr.write("        label = \"Thread "+hex(thread) + " Block " + str(item["block"])+ "\";\n")
						in_cluster = True
				
				if item["thread"] == csvreport["ax_thread"][issue_index] and item["ipc"] == csvreport["ax_ipc"][issue_index]:
					xlabel = "Ax: "
				if item["thread"] == csvreport["bx_thread"][issue_index] and item["ipc"] == csvreport["bx_ipc"][issue_index]:
					xlabel = "Bx: "
				if item["thread"] == csvreport["cx_thread"][issue_index] and item["ipc"] == csvreport["cx_ipc"][issue_index]:
					xlabel = "Cx: "
				if item["thread"] == csvreport["dx_thread"][issue_index] and item["ipc"] == csvreport["dx_ipc"][issue_index]:
					xlabel = "Dx: "

				
				gr.write("        "+item["operation"].replace('@','_') +"_"+hex(item["addr"])+"_"+hex(item["ipc"])+"_"+hex(item["thread"])+"_"+str(item["timestamp"])+" [label=\""+xlabel+item["operation"].replace('@','_') +","+ hex(item["addr"]) +"\\nline "+ str(item["line"]) +", "+ get_file_name(item["src_file"])+"\\n"+ code_line + "\" shape=box")
				 
				if n == 0:
					gr.write(" color=blue ")
				if n == len(items)-1 :
					gr.write(" color=green ")

				gr.write ("];\n")
			if in_cluster:
				gr.write("    }\n")
				in_cluster = False
					
			items = transitions[thread].keys()
			
			for item in items:
				gr.write ("        "+ item.src.operation.replace('@','_')+"_"+hex(item.src.addr)+"_"+hex(item.src.ipc)+"_"+hex(item.src.thread)+"_"+ str(graph[thread][item.src]["timestamp"]) +" -> ")
				
				print "graph[thread][item.src][\"block\"] is " + str(graph[thread][item.src]["block"]) + ", graph[thread][item.tgt][\"block\"] is " + str(graph[thread][item.tgt]["block"])
				if graph[thread][item.src]["block"] != graph[thread][item.tgt]["block"]:
					
					xlabel = "style=\"dashed\""
				else:
					xlabel = "style=\"solid\""
			
				gr.write ( item.tgt.operation.replace('@','_')+"_"+hex(item.tgt.addr)+"_"+hex(item.tgt.ipc)+"_"+hex(item.tgt.thread)+"_"+ str(graph[thread][item.tgt]["timestamp"]) + "[label=\"" + str(transitions[thread][item]) +"\" " +xlabel+" , fontcolor=blue ];\n")
				
			
			#gr.write("   }\n")

		items = interleavings.keys()
		
		#print "interleaving items are: "+ str(items)
		
		for item in items:
			#print "\nTransition src is " + str(item.src)
			#print "Transition tgt is " + str(item.tgt)
			
			#print "\ngraph [item.src.thread][item.src] = " + str(graph[item.src.thread][item.src])
			
			gr.write ("        "+ item.src.operation.replace('@','_')+"_"+hex(item.src.addr)+"_"+hex(item.src.ipc)+"_"+hex(item.src.thread)+"_"+ str( graph[item.src.thread][item.src]["timestamp"])  +" -> ")
			
			gr.write ( item.tgt.operation.replace('@','_')+"_"+hex(item.tgt.addr)+"_"+hex(item.tgt.ipc)+"_"+hex(item.tgt.thread)+"_"+ str(graph[item.tgt.thread][item.tgt]["timestamp"]) + "[label=\""+ str(interleavings[item]) +"\" , fontcolor=blue color=\"red\" ];\n")

		gr.write("}\n")

# ****************************************************************************************************************


def process_trace(inputdir, tracefile, idiomfile, memfile, srcfile, graphfile, explain, csvreportfile):
	os.chdir(inputdir)
	try:
		with open(idiomfile, 'r') as csvin:
			reader=csv.DictReader(csvin)
			idioms = {k.strip():[fitem(v)] for k,v in reader.next().items()}
			for line in reader:
				for k,v in line.items():
					k=k.strip()
					idioms[k].append(fitem(v))
		print "\nIdioms are:\n"
		print idioms 
	except:
		print "No idioms file "+idiomfile+" found"
		idioms = {}
	try:
		with open(memfile, 'r') as csvin:
			reader=csv.DictReader(csvin)
			memsym = {k.strip():[fitem(v)] for k,v in reader.next().items()}
			for line in reader:
				for k,v in line.items():
					k=k.strip()
					memsym[k].append(fitem(v))
	except:
		print "No memory map file "+memfile+" found. Exiting"
		exit(1)

#	print "\nMemory map is:\n"
#	print memsym 
	try:
		with open(srcfile, 'r') as csvin:
			reader=csv.DictReader(csvin)
			srcmap = {k.strip():[fitem(v)] for k,v in reader.next().items()}
			for line in reader:
				for k,v in line.items():
					k=k.strip()
					srcmap[k].append(fitem(v))
	except:
		print "No source code map file "+memfile+" found. Exiting"
		exit(2)
				
	#print "\nSource map is:\n"
	#print srcmap 
	
	if (explain > 0):
		
		try:
			with open(csvreportfile, 'r') as csvin:
				reader=csv.DictReader(csvin)
				csvreport = {k.strip():[fitem(v)] for k,v in reader.next().items()}
				for line in reader:
					for k,v in line.items():
						k=k.strip()
						csvreport[k].append(fitem(v))
		except:
			print "No source code map file "+csvreportfile+" found. Exiting"
			exit(3)
		
		explainer (tracefile, graphfile, memsym, srcmap, explain,csvreport)
	else:
		grapher (tracefile, graphfile, memsym, srcmap)
 
 
def main(argv):
   global start_timestamp
   global end_timestamp
   global timeout
   global pre_recording_ts
   global post_recording_ts
   inputdir = "./"
   tracefile = "racedet.trace"
   idiomfile = "racedet.id"
   memfile = "racedet.mem"
   srcfile = "racedet.src"
   graphfile = "racedet.dot"
   
   explain = 0
   
   csvreportfile = "racedet_report.csv"
   
   try:
      opts, args = getopt.getopt(argv,"ht:i:d:f:s:e:g:j:c:b:a:",["timeout=","idfile=", "dir=","file=","start=","end=","graph=","justify=","csvreport=","before=","after="])
   except getopt.GetoptError:
      print 'grapher.py -d <inputdir> -t <timeout>'
      sys.exit(2)
   for opt, arg in opts:
      if opt == '-h':
         print 'grapher.py -d <inputdir> -t <timeout>'
         sys.exit()
      elif opt in ("-i", "--idfile"):
         idiomfile = arg
      elif opt in ("-f", "--file"):
         tracefile = arg
      elif opt in ("-g", "--graph"):
         graphfile = arg
      elif opt in ("-c", "--csvreport"):
         csvreportfile = arg
      elif opt in ("-t", "--timeout"):
         timeout = int(arg)
      elif opt in ("-s", "--start"):
         start_timestamp = int(arg)
      elif opt in ("-e", "--end"):
         end_timestamp = int(arg)
      elif opt in ("-b", "--before"):
         pre_recording_ts = int(arg)
      elif opt in ("-a", "--after"):
         post_recording_ts = int(arg)
      elif opt in ("-j", "--justify"):
         explain = int(arg)
      elif opt in ("-d", "--dir"):
         inputdir = arg
     
   print 'Input dir is', inputdir
   print 'Trace file is', tracefile
   print 'Idiom file is', idiomfile
   print 'Mem file is' , memfile
   print 'src file is', srcfile
   print 'Graph file is', graphfile
   print 'Start timestamp is ' + str(start_timestamp)
   print 'End timestamp is ' + str(end_timestamp)
   
   if explain == 0:
	   print "Not explaining any case"
   else:
	   print "Explaing case "+str(explain)
   

   process_trace(inputdir, tracefile, idiomfile, memfile, srcfile, graphfile, explain, csvreportfile)

if __name__ == "__main__":
   params = len(sys.argv)
   if params < 2:
      print 'grapher.py -d <inputdirectory> -t <timeout>'
      quit()
   else:
      main(sys.argv[1:])

