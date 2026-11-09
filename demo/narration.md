# Narration

Spoken voiceover for the faceless demo. Play it against:

```sh
python3 demo/run_demo.py --play
```

Or against a VHS recording of `demo/qnxdoctor.tape`. Start reading when the banner `qnxdoctor faceless demo` appears. Timestamps match that session. Read the paragraphs, not the headings, at about 140 words a minute. The whole read finishes in under two and a half minutes.

The toolchain in the second half is a stub created by `demo/mock-env.sh`. It is not QNX SDP, not `qcc`, and not QEMU. Nothing in this recording was run on a Neutrino target.

## 0:00

qnxdoctor checks a QNX SDP 8.0 Makefile from the host. This demo uses the bundled examples and a fake toolchain. No board, no QEMU, and no SDP.

## 0:14

Version prints 0.1.0, the same string as the report header.

## 0:22

The demo command runs all three examples. hello-sdp8 and plain-aarch64 pass in degraded mode: the files are fine, and a missing qcc is only a warning. broken-port is the expected failure. The demo command still exits 0. It is a gallery, not a gate.

## 0:46

Diagnosing broken-port directly exits 1. The recap at the bottom is the part to read. common.mk forces gcc, passes march native, and still points at qnx710. qtargets.mk is missing. nto-armv7-o-le is not an SDP 8.0 CPU, and nto-aarch64-o-be asks for big-endian. net.c includes a Linux header and epoll, and it calls socket without libsocket. The shell script and the workflow never source qnxsdp-env.sh.

## 1:18

Sourcing demo/mock-env.sh builds a fake SDP tree: qcc and q++ stubs, plus qconfig.mk, qtargets.mk, and recurse.mk. The stub is not a compiler.

## 1:30

The same hello project is now mode ready. QNX_HOST and QNX_TARGET resolve, PATH finds the stub qcc, and qcc -V reports gcc_ntoaarch64le and gcc_ntox86_64. The project checks are unchanged, so the run still passes. This is not a Neutrino boot.

## 1:50

With --require-sdp, those missing-toolchain warnings become errors. hello-sdp8 now fails, even though the Makefiles are clean. Use that flag on a build job that must have the SDK.

## 2:04

JSON is the same report: status, mode, findings, and passed checks. Scripts can read it without scraping the text.

## 2:16

Warnings do not fail the process. Errors do. qnxdoctor reads files and does not run recipes. It has not been tested on real SDP hardware or QEMU.
