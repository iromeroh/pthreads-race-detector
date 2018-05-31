#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>

int c = 0;
void *fnC()
{
    int i;
    for(i=0;i<1000;i++)
    {   
        c++;
        printf(" %d", c); 
    }   
}


int main()
{
    int rt1, rt2;
    pthread_t t1, t2; 
    /* Create two threads */
    if( (rt1=pthread_create( &t1, NULL, &fnC, NULL)) )
        printf("Thread creation failed: %d\n", rt1);
    if( (rt2=pthread_create( &t2, NULL, &fnC, NULL)) )
        printf("Thread creation failed: %d\n", rt2);
    /* Wait for both threads to finish */
    pthread_join( t1, NULL);
    pthread_join( t2, NULL);
    printf ("\n");
    return 0;

}
