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
	with open(filename, 'r') as f:
		content = f.readlines()
		if number >=0 and number < len(content):
			return content[number-1]
	return "No such line: " + str(number)
	
	
def get_file_name (filename):
	items = filename.split('/')
	return items[-1]

def validate_ax_bx (tracefile, memsym, srcf, known_issues):
	global timeout
	global start_timestamp
	global end_timestamp
	from collections import namedtuple
	Interleaving = namedtuple("Interleaving", ["first_op","first_addr","first_thread", "first_ipc","second_op","second_addr","second_thread", "second_ipc"])
	Threadpair = namedtuple("Threadpair",["first","second"])
	
	Knownissue = namedtuple("Knownissue", ["itype" , "ax_ipc" , "bx_ipc", "cx_ipc" , "dx_ipc"] )
	
	lock_funcs = ["pthread_mutex_lock", "mem_lock_acquire", "mem_slab_lock", "page_pool_lock"]
	lock_get_funcs = ["pthread_mutex_lock@get", "mem_lock_acquire@get", "mem_slab_lock@get","page_pool_lock@get"]
	unlock_funcs = ["pthread_mutex_unlock", "mem_lock_release" , "mem_slab_unlock","page_pool_unlock"]
	
	issues = {}
	access = {}
	threadpairs = {}
	
	threads = {}
	
	confirmed_ax_bx_0 = {}
	
	confirmed_ax_bx_1 = {}
	
	confirmed_ax_bx_cx_dx = {}
	
	confirmed_ax_bx_cy_dy = {}
	
	ln = 0
	
	period = timedelta(minutes=1)
	next_time = datetime.now() + period
	minutes = 0
	
	block_count = {}
	
	if known_issues:
	
		for i, ty in enumerate(known_issues["type"]):
			issue = Knownissue ( itype = ty , ax_ipc = known_issues["ax_ipc"][i] , bx_ipc = known_issues["bx_ipc"][i], cx_ipc = known_issues["cy_ipc"][i], dx_ipc = known_issues["dy_ipc"][i])
			
			issues[issue] = 0  # stores a count of how often this issue was hit
	
	with open(tracefile, 'r') as trace:
		for line in trace:
			#print line
			items = line.split(",");
			#print items
			if  ln>0:
				curr_access = {}
				curr_access["timestamp"] = int(items[0], 0)
				curr_access["ipc"] = int(items[1],0)
				curr_access["thread"] = int(items[2],0)
				
				thread = curr_access["thread"]
				curr_access["operation"] = items[3].strip()
				curr_access["addr"] = int(items[4],0)
				curr_access["line"] = int(items[5],0)
				curr_access["column"] = int(items[6],0)
				curr_access["src"] = int(items[7],0)
				if curr_access["src"] != 0:
					curr_access["src_file"] = srcf["Filename"][ srcf["id"].index(curr_access["src"])]
				else:
					curr_access["src_file"] = "no source info"
					
					
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
					
					if curr_access["operation"] not in block_count:
						block_count[ curr_access["operation"] ] = 1
					else:
						block_count[ curr_access["operation"] ] += 1
				
						
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
					
					
				if curr_access["timestamp"] >=  end_timestamp and end_timestamp > 0:
					print "Last timestamp ("+ str(end_timestamp) + ") reached. Exiting"
					break

				if curr_access["timestamp"] >=  start_timestamp:
					
					if len(threads[thread]["lock"]) > 0:
						curr_access["lock"] = threads[thread]["lock"][-1]
						curr_access["lock_addr"] = threads[thread]["lock_addr"][-1]
						curr_access["lockstate"] = threads[thread]["lockstate"][-1]
					else:
						curr_access["lock"] = None
						curr_access["lock_addr"] = None
						curr_access["lockstate"] = None
				
					if curr_access["addr"] not in access:
						access[ curr_access["addr"] ] = curr_access
					else:
						prev_access = access[ curr_access["addr"] ]
						
											
						if (prev_access["addr"] == curr_access["addr"]) and (prev_access["thread"] != curr_access["thread"]) :
							#print prev_access["operation"] + " on addr "+ hex(prev_access["addr"]) +" -> " + curr_access["operation"] + " on addr "+ hex(curr_access["addr"])
					
							if (prev_access["operation"] == "READ" or prev_access["operation"] == "WRITE")  and (curr_access["operation"] == "READ" or curr_access["operation"] == "WRITE") and  prev_access["operation"] != curr_access["operation"]  :
							
								
								threadpair = Threadpair( first = prev_access["thread"], second = curr_access["thread"] )
							
								reverse_threadpair = Threadpair( first = curr_access["thread"], second = prev_access["thread"])
							
								if threadpair not in threadpairs:
									if reverse_threadpair not in threadpairs:
										threadpairs[threadpair] = {}
									else:
										threadpair = reverse_threadpair
								idiom = []
								idiom.append(prev_access)
								idiom.append(curr_access)
							
								#threadpairs[threadpair].append(idiom)
								
								
								print "Found idiom in thread pair "+ str(threadpair) + " :\n" + str( idiom)
							
								#if len(threadpairs[threadpair]) > 1 : #we have more than one access to this address in these same 2 thread pair
								if 0 in threadpairs[threadpair]:
									interleaving = threadpairs[threadpair][0]
									#print last_inter
									#for interleaving in threadpairs[threadpair][:-1]:
									last_inter = idiom
									
									if (interleaving[0]["addr"] == last_inter[1]["addr"]) and (interleaving[1]["thread"] == last_inter[0]["thread"]) and ( interleaving[1]["ipc"] == last_inter[0]["ipc"])and ( interleaving[0]["ipc"] == last_inter[1]["ipc"]):  #we have a reversible access to a memory address
										
										inter = Interleaving(first_op = last_inter[0]["operation"], first_addr=last_inter[0]["addr"], first_thread = last_inter[0]["thread"], first_ipc = last_inter[0]["ipc"],  second_op = last_inter[1]["operation"], second_addr=last_inter[1]["addr"], second_thread = last_inter[1]["thread"], second_ipc = last_inter[1]["ipc"] )
										
										if known_issues:
											issue = Knownissue ( itype = 1 , ax_ipc = last_inter[0]["ipc"] , bx_ipc = last_inter[1]["ipc"], cx_ipc = 0, dx_ipc = 0)
									
											if issue in issues:	# We have a known issue of type 1 between these two IPCs
													continue
										
									
										if  inter not in confirmed_ax_bx_1:
										
											confirmed_ax_bx_1[inter] = {}
											confirmed_ax_bx_1[inter] ["interleaving"] = interleaving
										
											confirmed_ax_bx_1[inter]["count"] = 1
											
											print "\n===========================\n"
										
											xlabel = ''
										
											print "Confirmed reversible Ax -> Bx access."
										
											if last_inter[0]["lock"] is None:
												xlabel = "Ax has no lock. "
										
									
											print xlabel + "Ax is " + interleaving[0]["operation"] + " on addr " + hex(last_inter[0]["addr"]) + " (\'" + addr_to_var( last_inter[0]["addr"] ,memsym)+"\') by thread "+ hex(last_inter[0]["thread"]) +" on IPC " + hex(last_inter[0]["ipc"]) + ":"
											
											print " file: "+ get_file_name(last_inter[0]["src_file"]) +", line "+ str(last_inter[0]["line"]) +" :\n   "+ get_line(last_inter[0]["line"],last_inter[0]["src_file"] )
										
											xlabel = ''
										
											if last_inter[1]["lock"] is None:
												xlabel = "Bx has no lock. "
											
											print xlabel + "Bx is " + last_inter[1]["operation"] + " on addr " + hex(last_inter[1]["addr"])+ "(\'"+ addr_to_var( last_inter[1]["addr"] ,memsym)+  "\') by thread "+ hex(last_inter[1]["thread"]) +" on IPC " + hex(last_inter[1]["ipc"]) + ":"
											print " file: "+ get_file_name(last_inter[1]["src_file"]) +", line "+ str(last_inter[1]["line"]) +" :\n   "+ get_line(last_inter[1]["line"],last_inter[1]["src_file"] )
										
										
										else:
											confirmed_ax_bx_1[inter]["count"] += 1
										
										
									else:	 
										if   (last_inter[0]["lock"] is None or  last_inter[1]["lock"]is None) or ( last_inter[0]["lock_addr"] != last_inter[1]["lock_addr"] ) :  # one of the accesses has no lock or the locks are different
										
											inter = Interleaving(first_op = last_inter[0]["operation"], first_addr=last_inter[0]["addr"], first_thread = last_inter[0]["thread"], first_ipc = last_inter[0]["ipc"],  second_op = last_inter[1]["operation"], second_addr=last_inter[1]["addr"], second_thread = last_inter[1]["thread"], second_ipc = last_inter[1]["ipc"] )
											
											if known_issues:
												issue = Knownissue ( itype = 0 , ax_ipc = last_inter[0]["ipc"] , bx_ipc = last_inter[1]["ipc"], cx_ipc = 0, dx_ipc = 0)
										
												if issue in issues:	# We have a known issue of type 0 between these two IPCs
														continue
											
										
											if  inter not in confirmed_ax_bx_0:
											
												confirmed_ax_bx_0[inter] = {}
												confirmed_ax_bx_0[inter] ["interleaving"] = last_inter
											
												confirmed_ax_bx_0[inter]["count"] = 1
												
												print "\n===========================\n"
											
												xlabel = ''
											
												print "Confirmed Ax -> Bx access with a missing lock."
											
												if last_inter[0]["lock"] is None:
													xlabel = "Ax has no lock. "
											
										
												print xlabel + "Ax is " + interleaving[0]["operation"] + " on addr " + hex(last_inter[0]["addr"]) + " (\'" + addr_to_var( last_inter[0]["addr"] ,memsym)+"\') by thread "+ hex(last_inter[0]["thread"]) +" on IPC " + hex(last_inter[0]["ipc"]) + ":"
												
												print " file: "+ get_file_name(last_inter[0]["src_file"]) +", line "+ str(last_inter[0]["line"]) +" :\n   "+ get_line(last_inter[0]["line"],last_inter[0]["src_file"] )
											
												xlabel = ''
											
												if last_inter[1]["lock"] is None:
													xlabel = "Bx has no lock. "
												
												print xlabel + "Bx is " + last_inter[1]["operation"] + " on addr " + hex(last_inter[1]["addr"])+ "(\'"+ addr_to_var( last_inter[1]["addr"] ,memsym)+  "\') by thread "+ hex(last_inter[1]["thread"]) +" on IPC " + hex(last_inter[1]["ipc"]) + ":"
												print " file: "+ get_file_name(last_inter[1]["src_file"]) +", line "+ str(last_inter[1]["line"]) +" :\n   "+ get_line(last_inter[1]["line"],last_inter[1]["src_file"] )
											
											
											else:
												confirmed_ax_bx_0[inter]["count"] += 1
										
									if (interleaving[0]["addr"] != last_inter[1]["addr"]) and (interleaving[1]["thread"] == last_inter[0]["thread"]) and ( ( interleaving[1]["ipc"] != last_inter[0]["ipc"]) or ( interleaving[0]["ipc"] != last_inter[1]["ipc"]) ) : # we have a confirmed reversible ax->bx cy->dy access
										
										if interleaving[0]["lockstate"] is None or interleaving[1]["lockstate"] is None or  last_inter[0]["lockstate"] is None or last_inter[1]["lockstate"] is None :
											print "Found ax->bx cy->dy with unlocked access"
										else:
											if interleaving[0]["lockstate"]["ipc"] == last_inter[1]["lockstate"]["ipc"] and last_inter[0]["lockstate"]["ipc"] == interleaving[1]["lockstate"]["ipc"]:
												continue

									
										inter = Interleaving(first_op = interleaving[0]["operation"], first_addr=interleaving[0]["addr"], first_thread = interleaving[0]["thread"], first_ipc = interleaving[0]["ipc"],  second_op = interleaving[1]["operation"], second_addr=interleaving[1]["addr"], second_thread = interleaving[1]["thread"], second_ipc = interleaving[1]["ipc"] )
									
										#if (interleaving [0]["ipc"] in known_issues["ax_ipc"]) and (interleaving[1]["ipc"] in known_issues["bx_ipc"]):
										#	if  known_issues["ax_ipc"].index(interleaving[0]["ipc"]) == known_issues["bx_ipc"].index(interleaving[1]["ipc"]):
										#		#print "Known issue, skipping"
										#		continue
										if known_issues:
											issue = Knownissue ( itype = 4 , ax_ipc = interleaving[0]["ipc"] , bx_ipc = interleaving[1]["ipc"], cx_ipc = last_inter[0]["ipc"], dx_ipc = last_inter[1]["ipc"])
									
											if issue in issues:	# We have a known issue of type 2 between these two IPCs
													continue
										
									
										if  inter not in confirmed_ax_bx_cy_dy:
										
											confirmed_ax_bx_cy_dy[inter] = {}
											confirmed_ax_bx_cy_dy[inter] ["interleaving"] = []
											confirmed_ax_bx_cy_dy[inter] ["interleaving"].append( interleaving)
											confirmed_ax_bx_cy_dy[inter] ["interleaving"].append( last_inter)
										
											confirmed_ax_bx_cy_dy[inter]["count"] = 1
											
											print "\n===========================\n"
										
											print "Confirmed Ax -> Bx, Cy -> Dy access."
											
											print "Ax is " + interleaving[0]["operation"] + " on addr " + hex(interleaving[0]["addr"]) + " (\'" + addr_to_var( interleaving[0]["addr"] ,memsym)+"\') by thread "+ hex(interleaving[0]["thread"]) +" on IPC " + hex(interleaving[0]["ipc"]) + ":"
											
											print " file: "+ get_file_name(interleaving[0]["src_file"]) +", line "+ str(interleaving[0]["line"]) +" :\n   "+ get_line(interleaving[0]["line"],interleaving[0]["src_file"] )
										
											print "Bx is " + interleaving[1]["operation"] + " on addr " + hex(interleaving[1]["addr"])+ "(\'"+ addr_to_var( interleaving[1]["addr"] ,memsym)+  "\') by thread "+ hex(interleaving[1]["thread"]) +" on IPC " + hex(interleaving[1]["ipc"]) + ":"
											print " file: "+ get_file_name(interleaving[1]["src_file"]) +", line "+ str(interleaving[1]["line"]) +" :\n   "+ get_line(interleaving[1]["line"],interleaving[1]["src_file"] )
										
											print " Cy is " + last_inter[0]["operation"] + " on addr " + hex(last_inter[0]["addr"]) + " (\'" + addr_to_var( last_inter[0]["addr"] ,memsym)+"\') by thread "+ hex(last_inter[0]["thread"]) +" on IPC " + hex(last_inter[0]["ipc"]) + ":"
											
											print " file: "+ get_file_name(last_inter[0]["src_file"]) +", line "+ str(last_inter[0]["line"]) +" :\n   "+ get_line(last_inter[0]["line"],last_inter[0]["src_file"] )
										
											print "Dy is " + last_inter[1]["operation"] + " on addr " + hex(last_inter[1]["addr"])+ "(\'"+ addr_to_var( last_inter[1]["addr"] ,memsym)+  "\') by thread "+ hex(last_inter[1]["thread"]) +" on IPC " + hex(last_inter[1]["ipc"]) + ":"
											print " file: "+ get_file_name(last_inter[1]["src_file"]) +", line "+ str(last_inter[1]["line"]) +" :\n   "+ get_line(last_inter[1]["line"],last_inter[1]["src_file"] )
										
										else:
											confirmed_ax_bx_cy_dy[inter]["count"] += 1

									if (interleaving[0]["addr"] == last_inter[1]["addr"]) and (interleaving[1]["thread"] == last_inter[0]["thread"]) and ( ( interleaving[1]["ipc"] != last_inter[0]["ipc"]) or ( interleaving[0]["ipc"] != last_inter[1]["ipc"]) ) : # we have a confirmed reversible ax->bx cx->dx access
										
										if interleaving[0]["lockstate"] is None or interleaving[1]["lockstate"] is None or  last_inter[0]["lockstate"] is None or last_inter[1]["lockstate"] is None :
											print "Found ax->bx cx->dx with unlocked access"
										else:
											if interleaving[0]["lockstate"]["ipc"] == last_inter[1]["lockstate"]["ipc"] and last_inter[0]["lockstate"]["ipc"] == interleaving[1]["lockstate"]["ipc"]:
												continue
									
										inter = Interleaving(first_op = interleaving[0]["operation"], first_addr=interleaving[0]["addr"], first_thread = interleaving[0]["thread"], first_ipc = interleaving[0]["ipc"],  second_op = interleaving[1]["operation"], second_addr=interleaving[1]["addr"], second_thread = interleaving[1]["thread"], second_ipc = interleaving[1]["ipc"] )
									
										if known_issues:
											issue = Knownissue ( itype = 2 , ax_ipc = interleaving[0]["ipc"] , bx_ipc = interleaving[1]["ipc"], cx_ipc = last_inter[0]["ipc"], dx_ipc = last_inter[1]["ipc"])
									
											if issue in issues:	# We have a known issue of type 2 between these two IPCs
													continue
										
									
										if  inter not in confirmed_ax_bx_cx_dx:
										
											confirmed_ax_bx_cx_dx[inter] = {}
											confirmed_ax_bx_cx_dx[inter] ["interleaving"] = []
											confirmed_ax_bx_cx_dx[inter] ["interleaving"].append( interleaving)
											confirmed_ax_bx_cx_dx[inter] ["interleaving"].append( last_inter)
										
											confirmed_ax_bx_cx_dx[inter]["count"] = 1
											
											print "\n===========================\n"
										
											print "Confirmed Ax -> Bx, Cx -> Dx access."
											
											print "Ax is " + interleaving[0]["operation"] + " on addr " + hex(interleaving[0]["addr"]) + " (\'" + addr_to_var( interleaving[0]["addr"] ,memsym)+"\') by thread "+ hex(interleaving[0]["thread"]) +" on IPC " + hex(interleaving[0]["ipc"]) + ":"
											
											print " file: "+ get_file_name(interleaving[0]["src_file"]) +", line "+ str(interleaving[0]["line"]) +" :\n   "+ get_line(interleaving[0]["line"],interleaving[0]["src_file"] )
										
											print "Bx is " + interleaving[1]["operation"] + " on addr " + hex(interleaving[1]["addr"])+ "(\'"+ addr_to_var( interleaving[1]["addr"] ,memsym)+  "\') by thread "+ hex(interleaving[1]["thread"]) +" on IPC " + hex(interleaving[1]["ipc"]) + ":"
											print " file: "+ get_file_name(interleaving[1]["src_file"]) +", line "+ str(interleaving[1]["line"]) +" :\n   "+ get_line(interleaving[1]["line"],interleaving[1]["src_file"] )
										
											print " Cx is " + last_inter[0]["operation"] + " on addr " + hex(last_inter[0]["addr"]) + " (\'" + addr_to_var( last_inter[0]["addr"] ,memsym)+"\') by thread "+ hex(last_inter[0]["thread"]) +" on IPC " + hex(last_inter[0]["ipc"]) + ":"
											
											print " file: "+ get_file_name(last_inter[0]["src_file"]) +", line "+ str(last_inter[0]["line"]) +" :\n   "+ get_line(last_inter[0]["line"],last_inter[0]["src_file"] )
										
											print "Dx is " + last_inter[1]["operation"] + " on addr " + hex(last_inter[1]["addr"])+ "(\'"+ addr_to_var( last_inter[1]["addr"] ,memsym)+  "\') by thread "+ hex(last_inter[1]["thread"]) +" on IPC " + hex(last_inter[1]["ipc"]) + ":"
											print " file: "+ get_file_name(last_inter[1]["src_file"]) +", line "+ str(last_inter[1]["line"]) +" :\n   "+ get_line(last_inter[1]["line"],last_inter[1]["src_file"] )
										
										else:
											confirmed_ax_bx_cx_dx[inter]["count"] += 1



								threadpairs[threadpair][0] = idiom			
						access[ curr_access["addr"] ] = curr_access
						
			ln += 1	
			if next_time <= datetime.now():
				minutes +=1
				next_time += period
			if minutes >= timeout:
				print "Timeout of "+str(timeout) +" minutes reached. Exiting";
				
				print "First timestamp:  " + str(start_timestamp) + ", last timestamp : " +str( curr_access["timestamp"])
				break
			
	from operator import itemgetter
	items = sorted(confirmed_ax_bx_0.values(), key=itemgetter("count"), reverse=True)
	
	i = 1
	
	with open('racedet_report.csv', 'w') as csvreport:
		csvreport.write(' id , type , count, ax_timestamp , ax_thread , ax_op, ax_addr, ax_ipc, bx_timestamp, bx_thread, bx_op, bx_addr, bx_ipc, cx_timestamp, cx_thread , cx_op, cx_addr, cx_ipc, dx_timestamp, dx_thread, dx_op, dx_addr, dx_ipc , ax_lock , bx_lock , cx_lock , dx_lock\n')
		
		for item in items:
			interleaving = item["interleaving"]
			count = item["count"]
			
			csvreport.write(str(i)+" ,  0  , "+str(count)+" , " +str(interleaving[0]["timestamp"])+" , "+hex(interleaving[0]["thread"])+ " , "+interleaving[0]["operation"]+" , "+hex(interleaving[0]["addr"])+" , "+hex(interleaving[0]["ipc"])+" , ")
			
			csvreport.write(str(interleaving[1]["timestamp"])+" , "+hex(interleaving[1]["thread"])+ " , "+interleaving[1]["operation"]+" , "+hex(interleaving[1]["addr"])+" , "+hex(interleaving[1]["ipc"]) )
			
			csvreport.write("  ,  0  ,  0  ,  N/A  ,  0  ,  0")
			
			csvreport.write("  ,  0  ,  0  ,  N/A  ,  0  ,  0")
			
			ax = '0'
			bx = '0'
			cx = '0'
			dx = '0'
			
			if not interleaving[0]["lock_addr"] is None:
				ax = hex(interleaving[0]["lock_addr"])
				
			if not interleaving[1]["lock_addr"] is None:
				bx = hex(interleaving[1]["lock_addr"])

			
			csvreport.write(" , " + ax + " , " + bx + " , " + cx + " , "+ dx+ "\n")
			
			i += 1
		items = sorted(confirmed_ax_bx_1.values(), key=itemgetter("count"), reverse=True)	
		for item in items:
			interleaving = item["interleaving"]
			count = item["count"]
			
			csvreport.write(str(i)+" ,  1  , "+str(count)+" , " +str(interleaving[0]["timestamp"])+" , "+hex(interleaving[0]["thread"])+ " , "+interleaving[0]["operation"]+" , "+hex(interleaving[0]["addr"])+" , "+hex(interleaving[0]["ipc"])+" , ")
			
			csvreport.write(str(interleaving[1]["timestamp"])+" , "+hex(interleaving[1]["thread"])+ " , "+interleaving[1]["operation"]+" , "+hex(interleaving[1]["addr"])+" , "+hex(interleaving[1]["ipc"]) )
			
			csvreport.write("  ,  0  ,  0  ,  N/A  ,  0  ,  0")
			
			csvreport.write("  ,  0  ,  0  ,  N/A  ,  0  ,  0")
			
			ax = '0'
			bx = '0'
			cx = '0'
			dx = '0'
			
			if not interleaving[0]["lock_addr"] is None:
				ax = hex(interleaving[0]["lock_addr"])
				
			if not interleaving[1]["lock_addr"] is None:
				bx = hex(interleaving[1]["lock_addr"])

			
			csvreport.write(" , " + ax + " , " + bx + " , " + cx + " , "+ dx+ "\n")
			
			i += 1
			
			
		items = sorted(confirmed_ax_bx_cx_dx.values(), key=itemgetter("count"), reverse=True)
		
		for item in items:
			interleaving = item["interleaving"][0]
			last_inter = item["interleaving"][1]
			
			count = item["count"]
			
			
			
			
			csvreport.write(str(i)+" ,  2  , "+str(count)+" , " +str(interleaving[0]["timestamp"])+" , "+hex(interleaving[0]["thread"])+ " , "+interleaving[0]["operation"]+" , "+hex(interleaving[0]["addr"])+" , "+hex(interleaving[0]["ipc"])+" , ")
			
			csvreport.write(str(interleaving[1]["timestamp"])+" , "+hex(interleaving[1]["thread"])+ " , "+interleaving[1]["operation"]+" , "+hex(interleaving[1]["addr"])+" , "+hex(interleaving[1]["ipc"]) )

			csvreport.write(" , " +str(last_inter[0]["timestamp"])+" , "+hex(last_inter[0]["thread"])+ " , "+last_inter[0]["operation"]+" , "+hex(last_inter[0]["addr"])+" , "+hex(last_inter[0]["ipc"])+" , ")
			
			csvreport.write(str(last_inter[1]["timestamp"])+" , "+hex(last_inter[1]["thread"])+ " , "+last_inter[1]["operation"]+" , "+hex(last_inter[1]["addr"])+" , "+hex(last_inter[1]["ipc"] ) )
			
			ax = '0'
			bx = '0'
			cx = '0'
			dx = '0'
			
			print str (interleaving[0])
			
			if not interleaving[0]["lock_addr"] is None:
				ax = hex(interleaving[0]["lock_addr"])
				
			if not interleaving[1]["lock_addr"] is None:
				bx = hex(interleaving[1]["lock_addr"])

			if not last_inter[0]["lock_addr"] is None:
				cx = hex(last_inter[0]["lock_addr"])
				
			if not last_inter[1]["lock_addr"] is None:
				dx = hex(last_inter[1]["lock_addr"])
			
			csvreport.write(" , " + ax + " , " + bx + " , " + cx + " , "+ dx+ "\n")
			
			
			i += 1
		items = sorted(confirmed_ax_bx_cy_dy.values(), key=itemgetter("count"), reverse=True)
		
		for item in items:
			interleaving = item["interleaving"][0]
			last_inter = item["interleaving"][1]
			
			count = item["count"]
			
			
			
			
			csvreport.write(str(i)+" ,  4  , "+str(count)+" , " +str(interleaving[0]["timestamp"])+" , "+hex(interleaving[0]["thread"])+ " , "+interleaving[0]["operation"]+" , "+hex(interleaving[0]["addr"])+" , "+hex(interleaving[0]["ipc"])+" , ")
			
			csvreport.write(str(interleaving[1]["timestamp"])+" , "+hex(interleaving[1]["thread"])+ " , "+interleaving[1]["operation"]+" , "+hex(interleaving[1]["addr"])+" , "+hex(interleaving[1]["ipc"]) )

			csvreport.write(" , " +str(last_inter[0]["timestamp"])+" , "+hex(last_inter[0]["thread"])+ " , "+last_inter[0]["operation"]+" , "+hex(last_inter[0]["addr"])+" , "+hex(last_inter[0]["ipc"])+" , ")
			
			csvreport.write(str(last_inter[1]["timestamp"])+" , "+hex(last_inter[1]["thread"])+ " , "+last_inter[1]["operation"]+" , "+hex(last_inter[1]["addr"])+" , "+hex(last_inter[1]["ipc"] ) )
			
			ax = '0'
			bx = '0'
			cy = '0'
			dy = '0'
			
			if not interleaving[0]["lock_addr"] is None:
				ax = hex(interleaving[0]["lock_addr"])
				
			if not interleaving[1]["lock_addr"] is None:
				bx = hex(interleaving[1]["lock_addr"])

			if not last_inter[0]["lock_addr"] is None:
				cy = hex(last_inter[0]["lock_addr"])
				
			if not last_inter[1]["lock_addr"] is None:
				dy = hex(last_inter[1]["lock_addr"])
			
			csvreport.write(" , " + ax + " , " + bx + " , " + cy + " , "+ dy+ "\n")
			
			
			i += 1
	
	
	i = 1
	
	items = sorted(confirmed_ax_bx_0.values(), key=itemgetter("count"), reverse=True)

	
	with open('racedet_report.txt', 'w') as report:
		for item in items:
			interleaving = item["interleaving"]
			count = item["count"]
			report.write( "\n#########################################\n")
		
			report.write( "Issue# "+ str(i) +": Ax -> Bx access, happening " + str(count)+ " times.\n" )
			
			xlabel = ''
			
			if interleaving[0]["lock"] is None:
				xlabel = "Ax has no lock. "
			
				
			report.write( xlabel + "Ax is " + interleaving[0]["operation"] + " on addr " + hex(interleaving[0]["addr"]) + " (\'" + addr_to_var( interleaving[0]["addr"] ,memsym)+"\') by thread "+ hex(interleaving[0]["thread"]) +" on IPC " + hex(interleaving[0]["ipc"]) + " , timestamp: " + str(interleaving[0]["timestamp"]) + ":\n")
			
			report.write( " file: "+ get_file_name(interleaving[0]["src_file"]) +", line "+ str(interleaving[0]["line"]) +" :\n   "+ get_line(interleaving[0]["line"],interleaving[0]["src_file"] ) +"\n" )
			
			xlabel = ''
			
			if interleaving[1]["lock"] is None:
				xlabel = "Bx has no lock. "
		
			report.write( xlabel+ "Bx is " + interleaving[1]["operation"] + " on addr " + hex(interleaving[1]["addr"])+ "(\'"+ addr_to_var( interleaving[1]["addr"] ,memsym)+  "\') by thread "+ hex(interleaving[1]["thread"]) +" on IPC " + hex(interleaving[1]["ipc"]) + " , timestamp: " + str(interleaving[1]["timestamp"]) + ":\n")
			report.write( " file: "+ get_file_name(interleaving[1]["src_file"]) +", line "+ str(interleaving[1]["line"]) +" :\n   "+ get_line(interleaving[1]["line"],interleaving[1]["src_file"] )+"\n")
			
			i += 1
		
		
		items = sorted(confirmed_ax_bx_1.values(), key=itemgetter("count"), reverse=True)


		for item in items:
			interleaving = item["interleaving"]
			count = item["count"]
			report.write( "\n===========================\n")
		
			report.write( "Issue# "+ str(i) +": Ax -> Bx access, happening " + str(count)+ " times.\n" )
			
			xlabel = ''
			
			if interleaving[0]["lock"] is None:
				xlabel = "Ax has no lock. "
			
				
			report.write( xlabel + "Ax is " + interleaving[0]["operation"] + " on addr " + hex(interleaving[0]["addr"]) + " (\'" + addr_to_var( interleaving[0]["addr"] ,memsym)+"\') by thread "+ hex(interleaving[0]["thread"]) +" on IPC " + hex(interleaving[0]["ipc"]) + " , timestamp: " + str(interleaving[0]["timestamp"]) + ":\n")
			
			report.write( " file: "+ get_file_name(interleaving[0]["src_file"]) +", line "+ str(interleaving[0]["line"]) +" :\n   "+ get_line(interleaving[0]["line"],interleaving[0]["src_file"] ) +"\n" )
			
			xlabel = ''
			
			if interleaving[1]["lock"] is None:
				xlabel = "Bx has no lock. "
		
			report.write( xlabel+ "Bx is " + interleaving[1]["operation"] + " on addr " + hex(interleaving[1]["addr"])+ "(\'"+ addr_to_var( interleaving[1]["addr"] ,memsym)+  "\') by thread "+ hex(interleaving[1]["thread"]) +" on IPC " + hex(interleaving[1]["ipc"]) + " , timestamp: " + str(interleaving[1]["timestamp"]) + ":\n")
			report.write( " file: "+ get_file_name(interleaving[1]["src_file"]) +", line "+ str(interleaving[1]["line"]) +" :\n   "+ get_line(interleaving[1]["line"],interleaving[1]["src_file"] )+"\n")
			
			i += 1
		
		items = sorted(confirmed_ax_bx_cx_dx.values(), key=itemgetter("count"), reverse=True)
		
		for item in items:
			interleaving = item["interleaving"][0]
			last_inter = item["interleaving"][1]
			
			count = item["count"]
			
			report.write( "\n++++++++++++++++++++++++++++\n")
			
			report.write( "Issue# "+ str(i) +": Ax -> Bx, Cx ->Dx access, happening " + str(count)+ " times.\n" )
			
			report.write( "Ax is " + interleaving[0]["operation"] + " on addr " + hex(interleaving[0]["addr"]) + " (\'" + addr_to_var( interleaving[0]["addr"] ,memsym)+"\') by thread "+ hex(interleaving[0]["thread"]) +" on IPC " + hex(interleaving[0]["ipc"]) + " , timestamp: " +str(interleaving[0]["timestamp"]) + ":")
			
			report.write (  " file: "+ get_file_name(interleaving[0]["src_file"]) +", line "+ str(interleaving[0]["line"]) +" :\n   "+ get_line(interleaving[0]["line"],interleaving[0]["src_file"] ) )
		
			report.write (  "Bx is " + interleaving[1]["operation"] + " on addr " + hex(interleaving[1]["addr"])+ "(\'"+ addr_to_var( interleaving[1]["addr"] ,memsym)+  "\') by thread "+ hex(interleaving[1]["thread"]) +" on IPC " + hex(interleaving[1]["ipc"]) + " , timestamp: " + str(interleaving[1]["timestamp"]) + ":" )
			
			report.write (  " file: "+ get_file_name(interleaving[1]["src_file"]) +", line "+ str(interleaving[1]["line"]) +" :\n   "+ get_line(interleaving[1]["line"],interleaving[1]["src_file"] ) )
		
			report.write (  " Cx is " + last_inter[0]["operation"] + " on addr " + hex(last_inter[0]["addr"]) + " (\'" + addr_to_var( last_inter[0]["addr"] ,memsym)+"\') by thread "+ hex(last_inter[0]["thread"]) +" on IPC " + hex(last_inter[0]["ipc"]) + " , timestamp: " + str(last_inter[0]["timestamp"]) + ":" )
			
			report.write (  " file: "+ get_file_name(last_inter[0]["src_file"]) +", line "+ str(last_inter[0]["line"]) +" :\n   "+ get_line(last_inter[0]["line"],last_inter[0]["src_file"] ) )
		
			report.write (  "Dx is " + last_inter[1]["operation"] + " on addr " + hex(last_inter[1]["addr"])+ "(\'"+ addr_to_var( last_inter[1]["addr"] ,memsym)+  "\') by thread "+ hex(last_inter[1]["thread"]) +" on IPC " + hex(last_inter[1]["ipc"]) + " , timestamp: " + str(last_inter[1]["timestamp"]) + ":" )
			report.write (  " file: "+ get_file_name(last_inter[1]["src_file"]) +", line "+ str(last_inter[1]["line"]) +" :\n   "+ get_line(last_inter[1]["line"],last_inter[1]["src_file"] ) )
			
			i += 1
		items = sorted(confirmed_ax_bx_cy_dy.values(), key=itemgetter("count"), reverse=True)
		
		for item in items:
			interleaving = item["interleaving"][0]
			last_inter = item["interleaving"][1]
			
			count = item["count"]
			
			report.write( "\n*********************************************\n")
			
			report.write( "Issue# "+ str(i) +": Ax -> Bx, Cy ->Dy access, happening " + str(count)+ " times.\n" )
			
			report.write( "Ax is " + interleaving[0]["operation"] + " on addr " + hex(interleaving[0]["addr"]) + " (\'" + addr_to_var( interleaving[0]["addr"] ,memsym)+"\') by thread "+ hex(interleaving[0]["thread"]) +" on IPC " + hex(interleaving[0]["ipc"]) + " , timestamp: " +str(interleaving[0]["timestamp"]) + ":")
			
			report.write (  " file: "+ get_file_name(interleaving[0]["src_file"]) +", line "+ str(interleaving[0]["line"]) +" :\n   "+ get_line(interleaving[0]["line"],interleaving[0]["src_file"] ) )
		
			report.write (  "Bx is " + interleaving[1]["operation"] + " on addr " + hex(interleaving[1]["addr"])+ "(\'"+ addr_to_var( interleaving[1]["addr"] ,memsym)+  "\') by thread "+ hex(interleaving[1]["thread"]) +" on IPC " + hex(interleaving[1]["ipc"]) + " , timestamp: " + str(interleaving[1]["timestamp"]) + ":" )
			
			report.write (  " file: "+ get_file_name(interleaving[1]["src_file"]) +", line "+ str(interleaving[1]["line"]) +" :\n   "+ get_line(interleaving[1]["line"],interleaving[1]["src_file"] ) )
		
			report.write (  " Cy is " + last_inter[0]["operation"] + " on addr " + hex(last_inter[0]["addr"]) + " (\'" + addr_to_var( last_inter[0]["addr"] ,memsym)+"\') by thread "+ hex(last_inter[0]["thread"]) +" on IPC " + hex(last_inter[0]["ipc"]) + " , timestamp: " + str(last_inter[0]["timestamp"]) + ":" )
			
			report.write (  " file: "+ get_file_name(last_inter[0]["src_file"]) +", line "+ str(last_inter[0]["line"]) +" :\n   "+ get_line(last_inter[0]["line"],last_inter[0]["src_file"] ) )
		
			report.write (  "Dy is " + last_inter[1]["operation"] + " on addr " + hex(last_inter[1]["addr"])+ "(\'"+ addr_to_var( last_inter[1]["addr"] ,memsym)+  "\') by thread "+ hex(last_inter[1]["thread"]) +" on IPC " + hex(last_inter[1]["ipc"]) + " , timestamp: " + str(last_inter[1]["timestamp"]) + ":" )
			report.write (  " file: "+ get_file_name(last_inter[1]["src_file"]) +", line "+ str(last_inter[1]["line"]) +" :\n   "+ get_line(last_inter[1]["line"],last_inter[1]["src_file"] ) )
			
			i += 1



def find_unsynch_accesses (tracefile, idioms, memsym, srcf):
	from collections import namedtuple
	Interleaving = namedtuple("Interleaving",["src","to"])
	
	Threadpair = namedtuple("Threadpair", ["first","second"])
	
	lock_funcs = ["pthread_mutex_lock", "mem_lock_acquire", "mem_slab_lock"]
	lock_get_funcs = ["pthread_mutex_lock@get", "mem_lock_acquire@get", "mem_slab_lock@get"]
	unlock_funcs = ["pthread_mutex_unlock", "mem_lock_release" , "mem_slab_unlock"]
	
	last_inters = {}
	
	threadpairs = {}
	
	threads = {}
	ln = 0
	with open(tracefile, 'r') as trace:
		for line in trace:
			#print line
			items = line.split(",");
			#print items
			if  ln>0:
				timestamp = int(items[0], 0)
				ipc = int(items[1],0)
				thread = int(items[2],0)
				operation = items[3].strip()
				addr = int(items[4],0)
				line = int(items[5],0)
				column = int(items[6],0)
				srcfile = int(items[7],0)
				
				if operation == "THREADSTART": #we have a new thread
					threads[thread] = {}
					threads[thread]["state"] = "started"
					threads[thread]["lock"] = []
					threads[thread]["lock_addr"] = []
					print "New thread "+hex(thread)

					
				if operation == "THREADEND": #we have a thread ending
					threads[thread]["state"] = "ended"
					print "Thread " + hex(thread) +" ended"
					
				if operation in lock_funcs: # thread called a lock function
					threads[thread]["lock"].append(operation)
					threads[thread]["lock_addr"].append(addr)
					#print "Thread "+hex(thread) + " requested a lock using " + operation + " using object on address "+ hex(addr)
				
				if operation in lock_get_funcs: # thread obtained a lock
					if lock_get_funcs.index(operation) == lock_funcs.index (threads[thread]["lock"][-1]): #ops are of same type
						if threads[thread]["lock_addr"][-1] == addr:
							threads[thread]["lock"][-1] = operation
							#print "Thread: "+ hex(thread) + " obtained lock with " + operation + " on lock address: " + hex(addr)
						else:
							print "Error on timestamp "+str(timestamp)+": address of lock object for lock request and get don't match"
					else:
						print "Error on timestamp "+ str(timestamp) +": lock and get notifications aren't of same type"
						
				if operation in unlock_funcs: #thread is releasing a lock
					if len(threads[thread]["lock"]) > 0:
						if unlock_funcs.index(operation) == lock_get_funcs.index (threads[thread]["lock"][-1]):
							if threads[thread]["lock_addr"][-1] == addr:
								del threads[thread]["lock"][-1]
								del threads[thread]["lock_addr"][-1]
							else:
								print "Error on timestamp "+str(timestamp)+": unlock and last lock operation aren't over the same lock object"
						else:
							print "Error on timestamp "+str(timestamp)+": unlock and last lock aren't of same API type"
					else:
						print "Error on timestamp "+ str(timestamp)+": tried to unlock without a lock"
							
				if timestamp in idioms["from_timestamp"]:
					#print "Timestamp "+ str(timestamp) + " is involved in an last_inter event (from)"
					
					inter = Interleaving(src=timestamp, to = idioms["to_timestamp"][ idioms["from_timestamp"].index(timestamp) ] )
					
					if inter not in last_inters:
						last_inters[inter] = {}
					if len(threads[thread]["lock"]) > 0:  # there is an active lock
						last_inters[inter]["src_lock"] = threads[thread]["lock"][-1]
						last_inters[inter]["src_lock_addr"] = threads[thread]["lock_addr"][-1]
					
					last_inters[inter]["src_thread"] = thread
					last_inters[inter]["src_ipc"] = ipc
					last_inters[inter]["src_op"] = operation
					last_inters[inter]["src_addr"] = addr
					last_inters[inter]["src_line"] = line
					if srcfile != 0:
						last_inters[inter]["src_file"] = srcf["Filename"][ srcf["id"].index(srcfile)]
					else:
						last_inters[inter]["src_file"] = "no source info"
					
				if timestamp in idioms["to_timestamp"]:

					inter = Interleaving(src= idioms["from_timestamp"][ idioms["to_timestamp"].index(timestamp) ], to = timestamp  )
					#print inter
				
					if inter not in last_inters:
						last_inters[inter] = {}
					
					last_inters[inter]["to_thread"] = thread
					last_inters[inter]["to_ipc"] = ipc
					last_inters[inter]["to_op"] = operation
					last_inters[inter]["to_addr"] = addr
					last_inters[inter]["to_line"] = line
					last_inters[inter]["to_file"] = srcf["Filename"][ srcf["id"].index(srcfile)]
					
					#print threads[thread]["lock"]

					if len(threads[thread]["lock"]) > 0 and "src_lock" in last_inters[inter]:  # there is an active lock
						last_inters[inter]["to_lock"] = threads[thread]["lock"][-1]
						last_inters[inter]["to_lock_addr"] = threads[thread]["lock_addr"][-1]
						
						#print last_inters[inter]
						if "src_lock" in last_inters[inter]:
							if last_inters[inter]["src_lock"] != last_inters[inter]["to_lock"]:
								print "Warning on timestamp "+str(timestamp)+" : locks used for shared memory access to address "+hex(addr)+" (\'"+addr_to_var(addr,memsym)+"\') are of different API. First access at 	line "+ str(last_inters[inter]["src_line"]) + " , file: "+ last_inters[inter]["src_file"] + " , second access at line " + str(line) +", file: "+ srcf["Filename"][ srcf["id"].index(srcfile)]
								
						if "src_lock_addr" in last_inters[inter]:
							if last_inters[inter]["src_lock_addr"] != last_inters[inter]["to_lock_addr"]:
								print "Warning on timestamp "+str(timestamp)+" : different lock objects used for shared memory access to address "+hex(addr)+" (\'"+addr_to_var(addr,memsym)+"\'). First access at line "+ str(last_inters[inter]["src_line"]) + " , file: "+ last_inters[inter]["src_file"] + "  uses lock object "+ hex (last_inters[inter]["src_lock_addr"] ) +", second access at line " + str(line) +", file: "+ srcf["Filename"][ srcf["id"].index(srcfile)] + "uses lock object "+ hex (last_inters[inter]["to_lock_addr"])


					else: # There is a missing lock in some of the accesses
						msg_from = " has a lock"
						msg_to = " has a lock"
						
						if "src_lock" not in last_inters[inter]:
							msg_from = " is missing a lock"
						if "to_lock" not in last_inters[inter]:
							msg_to = " is missing a lock"
							ddr_to_var(addr,memsym)
						print "\n-------\n"
						print "Warning on timestamp "+str(timestamp)+" : shared memory accesses to address "+hex(addr)+" (\'"+addr_to_var(addr,memsym)+"\') are missing locks.\n  First "+last_inters[inter]["src_op"]+" access by thread "+ hex(last_inters[inter]["src_thread"])+" at line "+ str(last_inters[inter]["src_line"]) + " , file: "+ get_file_name(last_inters[inter]["src_file"]) + " :\n   "+ get_line(last_inters[inter]["src_line"],last_inters[inter]["src_file"] )+ msg_from +"\n  Second "+last_inters[inter]["to_op"]+" access by thread" + hex(last_inters[inter]["to_thread"])+" at line " + str(line) +", file: "+ get_file_name(last_inters[inter]["to_file"]) +" :\n   "+ get_line(last_inters[inter]["to_line"],last_inters[inter]["to_file"] ) + msg_to
						
					threadpair = Threadpair( first = last_inters[inter]["src_thread"], second = last_inters[inter]["to_thread"])
					
					reverse_threadpair = Threadpair( first = last_inters[inter]["to_thread"], second = last_inters[inter]["src_thread"])
					
					
					if threadpair not in threadpairs:
						if reverse_threadpair not in threadpairs:
							threadpairs[threadpair] = []
						else:
							threadpair = reverse_threadpair
					
					threadpairs[threadpair].append(last_inters[inter])
					
					if ( len(threadpairs[threadpair]) > 1):    # we have more than one last_inter in this thread pair history
						for index, pair in enumerate(threadpairs[threadpair][:-1]):
							if pair["to_addr"] == threadpairs[threadpair][-1]["to_addr"]: # the last_inters access the same direction
								if pair["src_thread"] == threadpairs[threadpair][-1]["to_thread"]: # we have a case 2 race condition
									current = threadpairs[threadpair][-1]
									print "\n--------------------------"
									print "Type 2 Race condition on timestamp "+str(timestamp)+" : shared memory accesses to address "+hex(addr)+" (\'"+addr_to_var(addr,memsym)+"\') happen in a sequence leading to errors.\n"
									
									#print pair
									
									#print "-------------------------"
									
									print "First "+ pair ["src_op"]+" access by thread "+ hex(pair["src_thread"])+" at line "+ str(pair["src_line"]) + " , file: "+ get_file_name(pair["src_file"]) + " :\n   "+ get_line(pair["src_line"], pair["src_file"])
									 
									print "Second "+ pair["to_op"]+" access by thread " + hex(pair["to_thread"])+" at line " + str(pair["to_line"] ) +", file: "+ get_file_name(pair["to_file"]) +" :\n   "+ get_line(pair["to_line"], pair["to_file"])
									
									print "Third "+ current ["src_op"]+" access by thread "+ hex(current["src_thread"])+" at line "+ str(current["src_line"]) + " , file: "+ get_file_name(current["src_file"]) + " :\n   "+ get_line(current["src_line"], current["src_file"])
									 
									print "Fourth "+ current["to_op"]+" access by thread " + hex(current["to_thread"]) + " at line " + str(current["to_line"]) +", file: "+ get_file_name(current["to_file"]) +" :\n   "+ get_line(current["to_line"], current["src_file"] )
								
							if pair["to_addr"] != threadpairs[threadpair][-1]["to_addr"]: # the last_inters access a different direction
								if pair["src_thread"] == threadpairs[threadpair][-1]["to_thread"]: # we have a case 3 race condition
									current = threadpairs[threadpair][-1]
									print "\n--------------------------"
									print "Type 4 Race condition on timestamp "+str(timestamp)+" : shared memory accesses to addresses "+hex(pair["to_addr"])+" (\'"+addr_to_var(pair["to_addr"],memsym)+"\') and "  +hex(current["to_addr"])+" (\'"+addr_to_var(current["to_addr"],memsym)+"\') happen in a sequence leading to errors.\n"
									
									#print pair
									
									#print "-------------------------"
									
									print "First "+ pair ["src_op"]+" access to addr " + hex(pair["src_addr"]) + " by thread "+ hex(pair["src_thread"])+" at line "+ str(pair["src_line"]) + " , file: "+ get_file_name(pair["src_file"]) + " :\n   "+ get_line(pair["src_line"], pair["src_file"])
									 
									print "Second "+ pair["to_op"]+" access to addr " + hex(pair["to_addr"])+ " by thread " + hex(pair["to_thread"])+" at line " + str(pair["to_line"] ) +", file: "+ get_file_name(pair["to_file"]) +" :\n   "+ get_line(pair["to_line"], pair["to_file"])
									
									print "Third "+ current ["src_op"]+" access to addr" + hex(current ["src_addr"]) +" by thread "+ hex(current["src_thread"])+" at line "+ str(current["src_line"]) + " , file: "+ get_file_name(current["src_file"]) + " :\n   "+ get_line(current["src_line"], current["src_file"])
									 
									print "Fourth "+ current["to_op"]+" access to addr "+hex(current ["to_addr"]) + "by thread " + hex(current["to_thread"]) + " at line " + str(current["to_line"]) +", file: "+ get_file_name(current["to_file"]) +" :\n   "+ get_line(current["to_line"], current["src_file"] )
						
					
			ln += 1

def process_trace(inputdir, tracefile, idiomfile, memfile, srcfile, knownissues):
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
		
 	with open(memfile, 'r') as csvin:
		reader=csv.DictReader(csvin)
		memsym = {k.strip():[fitem(v)] for k,v in reader.next().items()}
		for line in reader:
			for k,v in line.items():
				k=k.strip()
				memsym[k].append(fitem(v))

	print "\nMemory map is:\n"
	print memsym 

 	with open(srcfile, 'r') as csvin:
		reader=csv.DictReader(csvin)
		srcmap = {k.strip():[fitem(v)] for k,v in reader.next().items()}
		for line in reader:
			for k,v in line.items():
				k=k.strip()
				srcmap[k].append(fitem(v))

	print "\nSource map is:\n"
	print srcmap 
	
	known_issues = {}
	
	try:
	
		with open(knownissues, 'r') as csvin:
			reader=csv.DictReader(csvin)
			known_issues = {k.strip():[fitem(v)] for k,v in reader.next().items()}
			for line in reader:
				for k,v in line.items():
					k=k.strip()
					known_issues[k].append(fitem(v))
				
	except:
		print knownissues + " file not found (no known issues defined)"

	print "\nKnown issues are:\n"
	print known_issues 

	
	validate_ax_bx (tracefile, memsym, srcmap, known_issues)
	
	#find_unsynch_accesses(tracefile, idioms, memsym, srcmap)
 
 
def main(argv):
   global start_timestamp
   global end_timestamp
   global timeout
   inputdir = "./"
   tracefile = "racedet.trace"
   idiomfile = "racedet.id"
   memfile = "racedet.mem"
   srcfile = "racedet.src"
   knownissues = "racedet.known"
   
   try:
      opts, args = getopt.getopt(argv,"ht:i:d:f:s:e:k:m:",["timeout=","idfile=", "dir=","file=","start=","end=","mem="])
   except getopt.GetoptError:
      print 'analyzer.py -d <inputdir> -t <timeout> -i <idiomfile>'
      sys.exit(2)
   for opt, arg in opts:
      if opt == '-h':
         print 'analyzer.py -d <inputdir> -t <timeout> -i <idiomfile>'
         sys.exit()
      elif opt in ("-i", "--idfile"):
         idiomfile = arg
      elif opt in ("-f", "--file"):
         tracefile = arg
      elif opt in ("-k", "--known"):
         knownissues = arg
      elif opt in ("-t", "--timeout"):
         timeout = int(arg)
      elif opt in ("-s", "--start"):
         start_timestamp = int(arg)
      elif opt in ("-e", "--end"):
         end_timestamp = int(arg)
      elif opt in ("-m", "--mem"):
         memfile = arg
      elif opt in ("-d", "--dir"):
         inputdir = arg
     
   print 'Input dir is', inputdir
   print 'Trace file is', tracefile
   print 'Idiom file is', idiomfile
   print 'Mem file is' , memfile
   print 'src file is', srcfile
   print 'Know issues file is',knownissues
   print 'Start timestamp is ' + str(start_timestamp)
   print 'End timestamp is ' + str(end_timestamp)
   

   process_trace(inputdir, tracefile, idiomfile, memfile, srcfile, knownissues)

if __name__ == "__main__":
   params = len(sys.argv)
   if params < 2:
      print 'analyzer.py -d <inputdirectory>'
      quit()
   else:
      main(sys.argv[1:])

