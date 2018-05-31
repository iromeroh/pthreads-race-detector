#ifndef __LOCK_FUNCTIONS_H
#define __LOCK_FUNCTIONS_H

#define CREATE_LOCK 0
#define REQ_LOCK 1
#define GOT_LOCK 2
#define RELEASE_LOCK 3
#define DESTROY_LOCK 4

#define PTHREADS_SEM 0
#define PTHREADS_TRYLOCK_SEM 1

#define INVALID_SEM 1000

#define TYPES 5
#define SETS 2

#define MAX_FUNC_NAME_SIZE 128

unsigned int function_of_interest(const char *str, unsigned int * set, unsigned int * index);

#endif

