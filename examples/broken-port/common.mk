ifndef QCONFIG
QCONFIG=qconfig.mk
endif
include $(QCONFIG)

# Intentional SDP 8.0 mistakes for `qnxdoctor examples/broken-port`.
QNX_TARGET ?= $(HOME)/qnx710/target/qnx7
CC = gcc
CFLAGS += -march=native

NAME = ported
SRCS += net.c
EXTRA_SRCVPATH += $(PROJECT_ROOT)
LIBS += pthread
