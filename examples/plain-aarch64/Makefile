# Plain qcc Makefile for SDP 8.0, AArch64 little-endian.
CC = qcc
CXX = q++
TARGET_ARCH = -Vgcc_ntoaarch64le
CFLAGS = -Wall -O2

.PHONY: all clean

all: hello

hello: hello.c
	$(CC) $(TARGET_ARCH) $(CFLAGS) $< -o $@

clean:
	rm -f hello
