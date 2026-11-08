ifndef QCONFIG
QCONFIG=qconfig.mk
endif
include $(QCONFIG)

NAME=hello

define PINFO
PINFO DESCRIPTION=Hello from the qnxdoctor SDP 8.0 sample
endef

SRCS+=hello.c
EXTRA_SRCVPATH+=$(PROJECT_ROOT)

include $(MKFILES_ROOT)/qtargets.mk
