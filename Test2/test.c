#include<stdio.h>
#include<string.h>
#include<pthread.h>
#include<stdlib.h>
#include<unistd.h>

pthread_t tid[3];
int counter;
pthread_mutex_t lock;

int foo=0;

void* doSomeThing(void *arg)
{
    unsigned long i = 0;
    pthread_mutex_lock(&lock);
    counter = counter + 1;
    pthread_mutex_unlock(&lock);

    printf("\n Job %d started\n", counter);

    for(i=0; i<(1000);i++){
	pthread_mutex_lock(&lock);
        foo = foo +1;
	pthread_mutex_unlock(&lock);
    }

    printf("\n Job %d finished\n", counter);

    

    return NULL;
}

int main(void)
{
    int i = 0;
    int err;

    if (pthread_mutex_init(&lock, NULL) != 0)
    {
        printf("\n mutex init failed\n");
        return 1;
    }

    while(i < 3)
    {
        err = pthread_create(&(tid[i]), NULL, &doSomeThing, NULL);
        if (err != 0)
            printf("\ncan't create thread :[%s]", strerror(err));
        i++;
    }

    pthread_join(tid[0], NULL);
    pthread_join(tid[1], NULL);
    pthread_join(tid[2], NULL);
    pthread_mutex_destroy(&lock);

    return 0;
}





