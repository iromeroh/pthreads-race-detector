#include <string.h>
#include "lock_functions.h"

char lock_func_sets[SETS][MAX_FUNC_NAME_SIZE]= {
  "Pthreads",
  "Pthreads (trylock)",
};

char lock_functions[SETS][TYPES][MAX_FUNC_NAME_SIZE] = 
{ { "pthread_mutex_init",
    "pthread_mutex_lock",
    "N/A",
    "pthread_mutex_unlock",
    "pthread_mutex_destroy"
  },
  { "N/A",
    "pthread_mutex_trylock",
    "N/A",
    "N/A",
    "N/A"
  }
};


char lock_functions_get[SETS][TYPES][MAX_FUNC_NAME_SIZE] = 
{ { "pthread_mutex_init",
    "pthread_mutex_lock",
    "pthread_mutex_lock@get",
    "pthread_mutex_unlock",
    "pthread_mutex_destroy"
  },
  { "N/A",
    "pthread_mutex_trylock",
    "N/A",
    "N/A",
    "N/A"
  }
};


unsigned int function_of_interest(const char *str, unsigned int * set, unsigned int * index){
  unsigned int i,j;

  if (!set || !index)
     return 0;
  for (i=0;i<SETS;i++)
    for (j=0;j<TYPES;j++){
        if (! strncmp(str, lock_functions[i][j],MAX_FUNC_NAME_SIZE) ){
           *set = i;
           *index = j;
           return 1;
        }
      }
  return 0;
}



