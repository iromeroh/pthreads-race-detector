# pthreads-race-detector 

Pthread race detector is a pintool that can be used to analyze Pthreads
programs and tests for finding concurrency issues.

## Dependencies

The tool runs on an AMD64 version of Linux and it depends on GNU
 binutils and Intel pin to compile and run. It assumes the pin binary is
 available in the system PATH.

It also requires graphviz tools for getting PostScript execution graphs.

It is strongly suggested to run this tool with Address Space Layout 
Randomization (ASLR) disabled, for getting the same addresses for
global symbols and functions at every execution. Check your Linux manual
about how to disable ASLR.

## Compiling the tool

For compiling the tool, go into the $INSTALL_DIR/instrumenter directory and
check the file makefile and change the variable PIN_ROOT to the path 
where your Pin installation can be found. Then you can do:

   make

This creates the directory $INSTALL_DIR/instrumenter/obj-intel64 and inside
it you can find file racedet.so , which is a pin tool you can use to 
generate a trace of parallel events (memory read/writes and calls to 
malloc/delete and synchronization functions per thread). The tool works
for Pthreads programs.

## Tracing an application

For tracing an application, you can call the pin tool by doing:

   pin -t $INSTALL_DIR/instrumenter/obj-intel64/racedet.so -- $BINARY

From the installation directory (assuming pin is in the $PATH). Where
$INSTALL_DIR is the installation directory of the tool, and $BINARY can
be any AMD64 Linux binary.

The tool supports detecting accesses to global symbols, by feeding it a 
file that can be extracted from Binutil's readelf.

For getting the global symbol list from readelf, you can do:

   readelf -s $BINARY | grep OBJECT | awk '{ print $$2,$$3,$$8 }' > $BINARY.lst

Which produces a file called $BINARY.lst . Then you can do:
   
   pin -t $INSTALL_DIR/instrumenter/obj-intel64/racedet.so -s $BINARY.lst -- $BINARY

And the tool will generate a trace with the accesses to global symbols 
clearly identified.


## Execution of the C tests

Just follow these steps:

1. Assuming you are on the software installation directoy, the first
 step is to go to the $INSTALL_DIR/instrumenter directory and change the
 variable PIN_ROOT to the path  where your Pin installation can be found.
 Compile the pintool doing:
   
   $ make

2. Then you can go to the directory where the tests are located, and run
  the test using make, for example:

   $ cd ..
   $ cd Test1
   $ make graph
   
   This should compile and execute the test, and produce a number of
   files, among them racedet.ps, which shows the execution graph for the
   C program in the current directoy

3. You can edit other variables in the Makefile. This is their meaning:

   BINARY  is the test binary to process with the pintool.

   START_TIMESTAMP is the unique event counter at which the analysis 
   must start. This value is visible in the leftmost column of the trace
   files produced by racedet.so pintool.

   END_TIMESTAMP is the event counter at which the analysis must stop. 

   RUN_TIME is the time in minutes the tool will run. After the time
   runs out, the analysis stops and a list of issues found is reported.

   ISSUE is the id of the issue found by the analyzer you want to have 
   explained by the tool "make explain".

   BEFORE is the number of timestamped events you want to see before any
    access involved in a potential concurrency issue. 
   It helps you see the context of the program execution before a 
   potential issue happens.

   AFTER is the number of timestamped events you want to see after any 
   access involved in a potential concurrency issue. 
   It helps you see the context of the program execution after a 
   potential issue happens.

4. You can run the pintool by doing

     make run

   This generates several files which have names starting in 'racedet'

     racedet.mem   is a memory map of the application. It contains 
     global variables and memory allocated/deallocated with malloc()
     and delete()

     racedet.src   is a table of the source files the pin tool detects 
     as making part of the program execution.

     racedet.trace is a trace of the program execution, describing the
     sequence of memory reads, writes and calls to syncronization
     functions.

5. You can then run the analysis tool with:

    make report

   This runs the analyzer by up to RUN_TIME minutes. A typical analysis 
   for a moderately sized MT program can takes more than 1 hour.
   At the end you get 2 files:


   racedet_report.txt  this is a list of the issues found, including 
   their id and a description with pointers to the source code
   involved.

   racedet_report.csv  this is a CSV describing the same issues, with
   some additional information added.

6. For having a PostScript graph describing the issue, you can do:

   make explain ISSUE=<issue id>

   Where <issue id> is any id of an issue present in racedet_report.txt
   or racedet_report.csv

   After doing this, you should get 2 files:

   issue_<id>.dot
   issue_<id>.ps

