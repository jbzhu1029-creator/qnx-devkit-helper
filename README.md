# qnxdoctor

Host-side doctor for [QNX SDP 8.0](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.prog/topic/devel_OS_version.html) Makefile projects. Point it at a tree and it reports whether this shell can build for Neutrino, and whether the project is using the SDP 8.0 toolchain (`qcc` / `q++`) and the recursive mk system (`qconfig.mk`, `qtargets.mk`, `recurse.mk`) the way the Programmer's Guide describes.

It is a command-line tool for the QNX Global Hackathon 2026, Developer Tooling & Host Tools. It does not flash a board and it does not boot a guest. QEMU is a fine place to run a Neutrino image once you have the SDP; qnxdoctor only needs a checkout of this repository and Python 3.9 or newer.

When `QNX_HOST`, `QNX_TARGET`, and `qcc` are missing, qnxdoctor keeps going in **degraded mode**. Project-file checks still run, so CI and a reviewer without a QNX install can use it. Pass `--require-sdp` when a missing toolchain should fail the run.

## What it checks

Environment, after `source ~/qnx800/qnxsdp-env.sh`:

- `QNX_HOST` is the host tree (`host/linux/x86_64` on Linux), not the SDP root and not an SDP 7 install.
- `QNX_TARGET` is the Neutrino sysroot (`target/qnx` or `target/qnx8`) and contains `qconfig.mk`, `qtargets.mk`, and `recurse.mk`.
- `PATH` finds `qcc` and `q++` from that host tree.
- `MAKEFLAGS` includes `-I$QNX_TARGET/usr/include`, which is how `include $(QCONFIG)` is resolved.
- `CPATH` / `LIBRARY_PATH` are not injecting host `/usr/include` or `/usr/lib`.
- GNU make is on `PATH`. SDP 8.0 has no `mk` compiler. The mk build is GNU make plus those three include files.
- The host OS is one SDP 8.0 supports (x86_64 Linux or 64-bit Windows, not macOS and not an ARM host).

Project files (no compiler required):

- Recursive mk layout: `common.mk` includes `qconfig.mk` and `qtargets.mk`, the root Makefile includes `recurse.mk`, and `LIST=OS CPU VARIANT` matches flat variant directories.
- Variant directories such as `nto-aarch64-o-le` and `nto-x86_64-o`. SDP 8.0 Neutrino targets are AArch64 little-endian and x86_64. ARMv7, 32-bit x86, and big-endian variants are reported as errors.
- `CC=gcc` (or an unset `CC` in a plain Makefile), `-march=native`, `-I/usr/include`, and leftover `qnx710` / `target/qnx7` paths.
- Plain Makefiles pass `-Vgcc_ntoaarch64le` or `-Vgcc_ntox86_64`. `gcc_ntox86` is not treated as the 64-bit spec.
- Recipes indented with spaces. GNU make requires a tab.
- Socket calls without `LIBS+=socket` / `-lsocket`. On QNX, `pthread`, `dl`, and `rt` come from libc.
- Linux-only headers (`linux/*`, `sys/epoll.h`, glibc `bits/*`).
- Shell scripts and GitHub Actions workflows that run `make` or `qcc` without sourcing `qnxsdp-env.sh`.

Make conditionals are not fully evaluated, and recipes are never executed. An assignment inside `ifeq` is still visible. CMake is reported when `CMakeLists.txt` is present; the detailed checks are for Makefiles.

## Requirements

- Python 3.9 or newer. The standard library is enough. There is nothing to compile.
- GNU make, only so the doctor can record `make --version`. The file checks do not need it.
- QNX SDP 8.0 is optional.

## Run it

From a clone of this repository:

```sh
python3 -m qnxdoctor examples/hello-sdp8
python3 -m qnxdoctor examples/plain-aarch64
python3 -m qnxdoctor examples/broken-port
python3 -m qnxdoctor demo
python3 -m qnxdoctor self-test
```

`examples/hello-sdp8` is a recursive mk project for `nto-aarch64-o-le` and `nto-x86_64-o`. `examples/plain-aarch64` is a one-file `qcc -Vgcc_ntoaarch64le` Makefile. `examples/broken-port` is a port that still targets SDP 7 and ARMv7; qnxdoctor exits 1 on it.

JSON is the same report for scripts:

```sh
python3 -m qnxdoctor --format json examples/hello-sdp8
```

Optional install, still with no third-party dependencies:

```sh
python3 -m pip install -e .
qnxdoctor examples/hello-sdp8
```

Useful flags:

| Flag | Effect |
| --- | --- |
| `--require-sdp` | Missing or inactive SDP 8.0 becomes an error. |
| `--sdp-root PATH` | Look at a specific SDP root (the directory that contains `qnxsdp-env.sh`) even when this shell has not sourced it. |
| `--no-discover` | Do not scan `~/qnx800`, `/opt/qnx800`, `/sdp/800`, and the SDP 7 prefixes. |
| `--format text\|json` | Human report or JSON. |
| `--color auto\|always\|never` | Color when stdout is a terminal. `NO_COLOR` disables it. |
| `--quiet` | One summary line (text format). |

Exit status is `0` when nothing is an error, `1` when any check is an error, and `2` for usage problems. Warnings do not fail the run. A clean project on a machine without the SDP is exit `0` in degraded mode.

With the SDP installed, build from a sourced shell. qnxdoctor then reports `mode: ready` when the host tree, sysroot, `qcc`, and mk includes all resolve:

```sh
source ~/qnx800/qnxsdp-env.sh
python3 -m qnxdoctor examples/hello-sdp8
```

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The tests build temporary SDP trees and Makefiles. They do not call a real `qcc`. GitHub Actions runs the same command on Ubuntu.

## Example: clean project, SDP not installed

`python3 -m qnxdoctor examples/hello-sdp8` on a machine without the SDP (the `env.make` line follows whatever GNU make is on `PATH`):

```text
qnxdoctor 0.1.0 | QNX SDP 8.0 host doctor
project : examples/hello-sdp8
style   : qnx-mk
mode    : degraded
status  : pass

Environment
  WARN  env.qnx-host-unset
       QNX_HOST is not set.
       Source the SDP 8.0 environment in every shell you build from:
         source ~/qnx800/qnxsdp-env.sh
       The script sets QNX_HOST, QNX_TARGET, PATH ($QNX_HOST/usr/bin), and
       MAKEFLAGS (-I$QNX_TARGET/usr/include) so qcc and qconfig.mk resolve.
       Project file checks still run when the SDP is not installed.
  WARN  env.qnx-target-unset
       QNX_TARGET is not set.
       qnxsdp-env.sh sets this to the Neutrino sysroot, either target/qnx or
       target/qnx8 under the SDP root. qcc and qconfig.mk both use it.
  WARN  env.qcc-missing
       qcc is not on PATH.
       qcc is the QNX C and C++ driver. Sourcing qnxsdp-env.sh puts it on
       PATH. File checks do not need it.
  WARN  env.qxx-missing
       q++ is not on PATH.
       q++ is the C++ driver and lives next to qcc after qnxsdp-env.sh is
       sourced.
  WARN  env.makeflags-missing
       MAKEFLAGS cannot point at the SDP include directory until QNX_TARGET is
       set.
       The recursive mk system finds qconfig.mk because MAKEFLAGS contains
       -I$QNX_TARGET/usr/include. qnxsdp-env.sh sets both.
  WARN  env.mk-includes-unverified
       qconfig.mk, qtargets.mk, and recurse.mk were not verified because
       QNX_TARGET is unset or has no usr/include.
       Those files live under $QNX_TARGET/usr/include and
       $QNX_TARGET/usr/include/mk. They are the 'mk' in a QNX build. There is
       no separate mk compiler in SDP 8.0.
  WARN  env.sdp-not-found
       No QNX SDP directory was found in the usual install locations.
       Looked at ~/qnx800, ~/qnx/qnx800, /opt/qnx800, /opt/qnx/qnx800,
       /sdp/800, ~/qnx710. Install SDP 8.0 (QNX Everywhere or a licensed SDP)
       and source ~/qnx800/qnxsdp-env.sh. Judges and CI can still run the
       project checks without it.
  INFO  env.mk-not-required
       No mk executable is on PATH. That is expected for SDP 8.0.
       There is no mk compiler. The mk build system is GNU make plus
       qconfig.mk, qtargets.mk, and recurse.mk under $QNX_TARGET/usr/include.

Project
  (no problems)

Passed
  OK  env.make
       GNU Make 4.3 at /usr/bin/make. The QNX mk system uses GNU make.
  OK  mk.compiler-unpinned
       CC is not overridden. qconfig.mk will supply qcc.
  OK  mk.layout
       Recursive QNX mk layout detected (common.mk, recurse.mk, or variant
       directories).
  OK  mk.list
       LIST includes OS, CPU, and VARIANT.
  OK  mk.preset-order
       Preset macros are not assigned after qtargets.mk.
  OK  mk.qconfig-included
       The project includes qconfig.mk.
  OK  mk.qtargets-included
       The project includes qtargets.mk.
  OK  mk.recurse-included
       The root Makefile includes recurse.mk, so variant directories are
       visited.
  OK  variant.makefiles
       Each variant Makefile includes common.mk.
  OK  variant.targets
       Neutrino variant directories: nto-aarch64-o-le, nto-x86_64-o.

Summary: 0 errors, 7 warnings, 1 note, 10 passed
```

`examples/plain-aarch64` is the same shape for a non-recursive Makefile: degraded mode, no project findings, and passed checks `plain.layout`, `plain.target-spec`, and `project.compiler`. Exit status is 0.

## Example: broken port

`python3 -m qnxdoctor examples/broken-port` exits 1. The environment block matches the clean run above when the SDP is not installed. The project findings are:

```text
Project
  ERROR  mk.qtargets-missing  common.mk
       The mk project never includes qtargets.mk.
       Add `include $(MKFILES_ROOT)/qtargets.mk` after NAME, SRCS, and LIBS.
       That file supplies the all, clean, and install rules. Without it, make
       in a variant directory has nothing to build.
  ERROR  project.legacy-sdp-path  common.mk:7
       This makefile references an SDP 7 (or older) install path.
       SDP 8.0 lives under ~/qnx800. The target tree is target/qnx or
       target/qnx8. qnx710 and target/qnx7 are the previous release.
  ERROR  project.host-compiler  common.mk:8
       CC is set to the host compiler (gcc).
       Delete the CC assignment. qconfig.mk sets the driver to qcc, and the
       variant directory selects the CPU. Host gcc emits a Linux binary, not a
       Neutrino binary.
  ERROR  project.march-native  common.mk:9
       The makefile passes -march=native or -mtune=native.
       Those flags target the build machine. A QNX cross compile has to use
       the qcc spec (-Vgcc_ntoaarch64le or -Vgcc_ntox86_64) instead.
  ERROR  source.linux-header  net.c:4
       Includes linux/if.h.
       This is a Linux kernel header and is not in the QNX sysroot. Use
       Neutrino headers from $QNX_TARGET/usr/include.
  ERROR  variant.big-endian  nto-aarch64-o-be
       nto-aarch64-o-be requests big-endian output.
       SDP 8.0 aarch64 and x86_64 targets are little-endian. Use
       nto-aarch64-o-le or nto-x86_64-o.
  ERROR  variant.cpu-unsupported  nto-armv7-o-le
       nto-armv7-o-le is not an SDP 8.0 Neutrino CPU.
       32-bit ARMv7 was removed in SDP 8.0. Use aarch64. Supported CPUs are
       aarch64 (little-endian) and x86_64.
  WARN  script.sdk-env-not-sourced  .github/workflows/build.yml
       .github/workflows/build.yml runs a QNX build tool without sourcing
       qnxsdp-env.sh or setting QNX_HOST.
       Source ~/qnx800/qnxsdp-env.sh in the same shell before make or qcc. A
       fresh CI job does not inherit the variables from your laptop.
  WARN  mk.list-incomplete  Makefile:2
       LIST is `CPU` and is missing OS and VARIANT.
       For directories named OS-CPU-VARIANT the root Makefile needs `LIST=OS
       CPU VARIANT`.
  WARN  script.sdk-env-not-sourced  build.sh
       build.sh runs a QNX build tool without sourcing qnxsdp-env.sh or
       setting QNX_HOST.
       Source ~/qnx800/qnxsdp-env.sh in the same shell before make or qcc. A
       fresh CI job does not inherit the variables from your laptop.
  WARN  link.libc-builtins  common.mk:14
       The link line pulls in pthread, which libc already provides on QNX.
       Drop -lpthread, -ldl, and -lrt (and the mk tokens pthread, dl, and rt).
       Those libraries are not separate on SDP 8.0, and the link fails when
       they are missing from the sysroot.
  WARN  source.epoll  net.c:3
       Includes sys/epoll.h.
       QNX has no epoll. SDP 8.0 networking is the io-sock stack; use poll,
       select, or kqueue/kevent.
  WARN  link.socket-missing  net.c:7
       Socket APIs are used but the link line does not include libsocket.
       QNX does not pull socket calls in from libc. For a mk project add
       `LIBS+=socket`. For a plain Makefile add `-lsocket` to LDLIBS.

Summary: 7 errors, 13 warnings, 1 note, 4 passed
```

## Layout

```text
qnxdoctor/     CLI, environment checks, and Makefile checks
examples/      one clean mk project, one clean plain Makefile, one broken port
tests/         unit tests for the file and environment logic
```

## License

MIT. See [LICENSE](LICENSE).
