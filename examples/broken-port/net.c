#include <stdio.h>
#include <sys/socket.h>
#include <sys/epoll.h>
#include <linux/if.h>

int main(void) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    return fd < 0;
}
