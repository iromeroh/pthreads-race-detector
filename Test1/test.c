#include<stdio.h>
#include<string.h>
#include<pthread.h>
#include<stdlib.h>
#include<unistd.h>

pthread_t tid[2];
int counter;
int shared=0;
pthread_mutex_t lock;

char * buf;
int * abuf;
float * tbuf;

void* doSomeThing(void *arg)
{

    unsigned long i = 0;
    counter += 1;
    printf("\n Job %d started\n", counter);

    for(i=0; i<(0xff);i++)
    {
      pthread_mutex_lock(&lock);
      shared ++;
      pthread_mutex_unlock(&lock);
    }

    printf("\n Job %d finished\n", counter);

    return NULL;
}

int main(void)
{
    int i = 0;
    int err;
    shared = 3;
 
    if (pthread_mutex_init(&lock, NULL) != 0)
    {
        printf("\n mutex init failed\n");
        return 1;
    }
 
    buf = malloc (5000);
    abuf = malloc (1000);
    
    
    buf[0]= 'a';
    buf[1]=0x00;

    while(i < 2)
    {
        err = pthread_create(&(tid[i]), NULL, &doSomeThing, NULL);
        if (err != 0)
            printf("\ncan't create thread :[%s]", strerror(err));
        i++;
    }

    tbuf = malloc (600);
    pthread_join(tid[0], NULL);
    pthread_join(tid[1], NULL);
    pthread_mutex_destroy(&lock);

    free(abuf);

    free(buf);

    return 0;
}
