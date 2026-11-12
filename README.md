# qnxdoctor

Host-side doctor for [QNX SDP 8.0](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.prog/topic/devel_OS_version.html) Makefile projects. Point it at a tree and it reports whether this shell can build for Neutrino, and whether the project is using the SDP 8.0 toolchain (`qcc` / `q++`) and the recursive mk system (`qconfig.mk`, `qtargets.mk`, `recurse.mk`) the way the Programmer's Guide describes.

It is a command-line tool for the QNX Global Hackathon 2026, Developer Tooling & Host Tools. It does not flash a board, boot a guest, or run `make` recipes. QEMU is a fine place to run a Neutrino image once you have the SDP; qnxdoctor only needs a checkout of this repository and Python 3.9 or newer. CI does not install SDP 8.0, does not run a real `qcc`, and does not boot QEMU. A judge who has the SDK can follow [Testing on SDP 8.0 and QEMU](#testing-on-sdp-80-and-qemu).

When `QNX_HOST`, `QNX_TARGET`, and `qcc` are missing, qnxdoctor keeps going in **degraded mode**. Project-file checks still run, so CI and a reviewer without a QNX install can use it. Pass `--require-sdp` when a missing toolchain should fail the run. If the report has errors, they are repeated in an **Errors** section just above the summary, after the passed checks, so the failures stay on screen.

## Quick start

From a clone. Nothing to install, and QNX SDP is not required:

```sh
python3 -m qnxdoctor examples/hello-sdp8
python3 -m qnxdoctor examples/plain-aarch64
python3 -m qnxdoctor examples/broken-port   # exits 1
python3 -m qnxdoctor demo --quiet
python3 demo/run_demo.py --check            # scripted session, no sleeps
python3 demo/run_demo.py --play             # same session, about 2.5 minutes
```

`examples/hello-sdp8` is a recursive mk project for `nto-aarch64-o-le` and `nto-x86_64-o`. `examples/plain-aarch64` is a one-file `qcc -Vgcc_ntoaarch64le` Makefile. `examples/broken-port` is a port that still targets SDP 7 and ARMv7.

On an x86_64 Linux machine with GNU make and no SDP activated, the one-line form of the clean project is:

```sh
python3 -m qnxdoctor --quiet examples/hello-sdp8
```

```text
qnxdoctor 0.1.0  examples/hello-sdp8  qnx-mk  degraded  pass  0 errors, 7 warnings, 1 note, 10 passed
```

Optional install, still with no third-party dependencies:

```sh
python3 -m pip install -e .
qnxdoctor examples/hello-sdp8
```

Exit status is `0` when nothing is an error, `1` when any check is an error, and `2` for usage problems. Warnings do not fail the run. A clean project on a machine without the SDP is exit `0` in degraded mode.

## What it checks

| Area | A pass | If it fails |
| --- | --- | --- |
| `QNX_HOST` | Host tree with `usr/bin/qcc` (`host/linux/x86_64` on Linux), not the SDP root and not an SDP 7 tree | Unset is a warning. Missing, pointed at the SDP root, or a Windows tree on Linux is an error |
| `QNX_TARGET` | Neutrino sysroot (`target/qnx` or `target/qnx8`) whose `usr/include` exists | Unset is a warning. Missing, or pointed at the SDP root, is an error |
| `qcc` and `q++` | Both resolve inside that host tree | Missing is a warning. A different `qcc` earlier on `PATH` is an error |
| `MAKEFLAGS` | Includes `-I$QNX_TARGET/usr/include`, which is how `include $(QCONFIG)` is found | Missing. This is an error once `QNX_TARGET` is a real tree, because setting the variable alone is not enough |
| mk includes | `qconfig.mk`, `qtargets.mk`, and `recurse.mk` under the sysroot | Missing is an error. Unchecked because `QNX_TARGET` is unset is a warning |
| Header leak | `CPATH` and `LIBRARY_PATH` do not inject `/usr/include` or `/usr/lib` | Error |
| GNU make | `make --version` reports GNU Make. SDP 8.0 has no `mk` compiler | Missing is a warning. A non-GNU `make` is an error |
| Host OS | x86_64 Linux or 64-bit Windows | macOS, an ARM host, or another OS is a warning, and the shell stays degraded |
| Discovery | Looks at `~/qnx800`, `/opt/qnx800`, `/sdp/800`, and the SDP 7 prefixes | Installed but not sourced, only SDP 7, or nothing found: warning. `--no-discover` skips the scan. `--sdp-root` checks one directory |
| `qcc -V` | Names `gcc_ntoaarch64le` and `gcc_ntox86_64` | Incomplete or unrecognized is a warning. `gcc_ntoarmv7le` is called out. `gcc_ntox86` is not the 64-bit spec |
| Recursive mk | `common.mk` includes `qconfig.mk` and `qtargets.mk`, the root Makefile includes `recurse.mk`, and `LIST=OS CPU VARIANT` | A missing include is an error. A short `LIST` is a warning |
| Variants | `nto-aarch64-o-le`, `nto-x86_64-o` | ARMv7, 32-bit x86, big-endian, and other non-SDP-8 CPUs are errors |
| Compiler | An mk project leaves `CC` unset so `qconfig.mk` supplies `qcc`. A plain Makefile sets `CC=qcc` and passes `-Vgcc_ntoaarch64le` or `-Vgcc_ntox86_64` | `CC=gcc`, an empty `CC`, or `qcc` with no SDP 8.0 spec is an error |
| Flags and old paths | No `-march=native`, `-I/usr/include`, `-L/usr/lib`, `qnx710`, or `target/qnx7` | Error |
| Recipes | Recipe lines start with a tab | Leading spaces are an error. The recipe is not executed |
| Sockets | Calls such as `socket()` are paired with `LIBS+=socket` or `-lsocket` | Warning |
| libc | The link line does not list `pthread`, `dl`, or `rt`. On QNX those come from libc | Warning |
| Headers | No `linux/*`, glibc `bits/*`, or `windows.h` | Those are errors. `sys/epoll.h`, `sys/inotify.h`, and `sys/eventfd.h` are warnings |
| Scripts | Root `*.sh`, `*/*.sh`, and `.github/workflows/*.{yml,yaml}` source `qnxsdp-env.sh` or set `QNX_HOST` before `make` or `qcc` | Warning |
| CMake | `CMakeLists.txt` is noticed when it is present | Detailed checks are for Makefiles. A CMake file that never mentions QNX is a warning beside a Makefile, and an error when it is the only build file |

Make conditionals are not fully evaluated. An assignment inside `ifeq` is still visible. A program named `mk` on `PATH` is a note: SDP 8.0 does not use it as the compiler. The source walk reads C and C++ files a few directories down. It does not preprocess them.

## Requirements

- Python 3.9 or newer. The standard library is enough. There is nothing to compile.
- GNU make, only so the doctor can record `make --version`. The file checks do not need it.
- QNX SDP 8.0 is optional.

## Flags

JSON is the same report for scripts:

```sh
python3 -m qnxdoctor --format json examples/hello-sdp8
```

`python3 -m qnxdoctor self-test` runs the unit tests from a git clone. `python3 -m qnxdoctor demo` prints all three bundled examples and exits 0 even when `broken-port` fails. It is a gallery. Diagnosing `examples/broken-port` directly exits 1.

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

With the SDP env script sourced, qnxdoctor reports mode `ready` when the host tree, sysroot, `qcc`, and mk includes all resolve. The tests cover that shape with a fake tree. A real install is in [Testing on SDP 8.0 and QEMU](#testing-on-sdp-80-and-qemu).

```sh
source ~/qnx800/qnxsdp-env.sh
python3 -m qnxdoctor examples/hello-sdp8
```

## Demo

`demo/run_demo.py` is the faceless session. `--check` runs every command and returns 0 only when the transcript matches. `--play` is the same session on a clock, about two and a half minutes. `demo/narration.md` is the voiceover. Start reading when the banner appears.

```sh
python3 demo/run_demo.py --check
python3 demo/run_demo.py --play
```

The degraded half scrubs `QNX_*`, `MAKEFLAGS`, and host include leaks, and it passes `--no-discover`, so an SDP install on the machine does not change that half. The ready half sources `demo/mock-env.sh`, which builds `demo/.mock-sdp` (gitignored). The `qcc` there answers `qcc -V` with `gcc_ntoaarch64le` and `gcc_ntox86_64` and exits 1 for anything else. It is not a compiler.

`demo/qnxdoctor.tape` is a [VHS](https://github.com/charmbracelet/vhs) tape that types the `--play` command. VHS is optional. CI does not install it. The gif it would write is gitignored. The narrated recording checked in for the submission is [demo/qnxdoctor-demo.mp4](demo/qnxdoctor-demo.mp4), with subtitles in [demo/qnxdoctor-demo.srt](demo/qnxdoctor-demo.srt).

### Regenerating the demo video

From the repository root:

```sh
bash demo/render_video.sh
```

The script records `demo/qnxdoctor.tape` at 1280×720 and mixes a [Piper](https://github.com/rhasspy/piper) voiceover of `demo/narration.md`. The voice is the offline Lessac high model (`en_US-lessac-high`). There is no microphone and no camera. It needs `ffmpeg` and Google Chrome or Chromium, because VHS draws the terminal in a headless browser. On Linux x86_64 it downloads VHS, ttyd, Piper, and the voice into `demo/.render/` when they are not already on `PATH`. `VHS`, `TTYD`, `PIPER`, and `PIPER_MODEL` override those paths. `demo/.render/` is gitignored.

The voice starts when the `qnxdoctor faceless demo` banner appears, on the cue times in `demo/narration.md`. A few tokens are respelled only so the synthesizer says them as initials (`QEMU`, the variant directory names, the `qcc -V` spec names). The subtitles keep the original sentences. The picture is the mock toolchain from `demo/mock-env.sh`. It is not a recording of SDP 8.0, a real `qcc`, or QEMU.

`--check` is pinned to x86_64 Linux with GNU make, which is the SDP 8.0 host GitHub Actions provides. On any other host the script exits 2 instead of pretending the transcript still matches.

## Tests

```sh
python3 -m unittest discover -s tests -v
python3 demo/run_demo.py --check
```

The tests build temporary SDP trees and Makefiles. They do not call a real `qcc`. GitHub Actions runs both commands on Ubuntu.

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

Summary: pass, mode degraded, 0 errors, 7 warnings, 1 note, 10 passed
```

`examples/plain-aarch64` is the same shape for a non-recursive Makefile: degraded mode, no project findings, and passed checks `plain.layout`, `plain.target-spec`, and `project.compiler`. Exit status is 0.

## Example: broken port

`python3 -m qnxdoctor examples/broken-port` exits 1. The environment block matches the clean run above when the SDP is not installed. Passed checks are left out of this excerpt. After them, the report repeats each error without the help text. The project findings are:

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

Errors
  ERROR  mk.qtargets-missing  common.mk
       The mk project never includes qtargets.mk.
  ERROR  project.legacy-sdp-path  common.mk:7
       This makefile references an SDP 7 (or older) install path.
  ERROR  project.host-compiler  common.mk:8
       CC is set to the host compiler (gcc).
  ERROR  project.march-native  common.mk:9
       The makefile passes -march=native or -mtune=native.
  ERROR  source.linux-header  net.c:4
       Includes linux/if.h.
  ERROR  variant.big-endian  nto-aarch64-o-be
       nto-aarch64-o-be requests big-endian output.
  ERROR  variant.cpu-unsupported  nto-armv7-o-le
       nto-armv7-o-le is not an SDP 8.0 Neutrino CPU.

Summary: fail, mode degraded, 7 errors, 13 warnings, 1 note, 4 passed
```

## Testing on SDP 8.0 and QEMU

This repository has not been run against a real SDP 8.0 install, a real `qcc`, or QEMU. The steps below are what a judge with the SDK would do. They are not part of CI.

Host tools for SDP 8.0 are x86_64 Linux or 64-bit Windows. [`mkqnximage`](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.utilities/topic/m/mkqnximage.html) documents QEMU guests on Ubuntu, for x86_64 and AArch64. macOS is not a supported host.

Doctor, after the env script (the directory is `~/qnx800` for a QNX Software Center install):

```sh
source ~/qnx800/qnxsdp-env.sh
python3 -m qnxdoctor --require-sdp examples/hello-sdp8
python3 -m qnxdoctor --require-sdp examples/broken-port
```

Expect mode `ready` and exit 0 on `hello-sdp8`. Expect exit 1 on `broken-port`. `--require-sdp` turns a missing toolchain into an error, so a clean tree on a machine that forgot to source the env script fails instead of passing in degraded mode.

Build, which qnxdoctor does not do itself:

```sh
make -C examples/hello-sdp8
```

That invokes the real `qcc` through the recursive mk files. A failure there is outside what the unit tests cover.

QEMU is separate from the doctor. From a sourced shell, in an empty directory:

```sh
mkdir -p "$HOME/qnx-qemu" && cd "$HOME/qnx-qemu"
mkqnximage --type=qemu --arch=x86_64 --run
```

The official page says QEMU images have no graphics. The terminal that started the image is the serial console. From another shell in that same directory, `mkqnximage --stop` stops it. In the console, Ctrl-A then x quits QEMU. `qemu-system-x86_64` has to be on the host; package names depend on the distro.

QNX Everywhere also ships a quickstart image (`com.qnx.qnx800.quickstart.qemu`). After unpacking it, the same `mkqnximage --run` from that image directory is the documented launch. See the [QEMU quickstart](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti_qemu/getting_started.html). An AArch64 guest needs the QEMU virt startup files, which are not in the stock x86 quickstart image. This project has not booted either image, and it does not copy the example binaries into a guest.

## Layout

```text
qnxdoctor/     CLI, environment checks, Makefile checks, text and JSON reports
examples/      one clean mk project, one clean plain Makefile, one broken port
demo/          scripted session, mock SDP stub, narration, VHS tape, video
tests/         unit tests, including the demo transcript
```

## License

MIT. See [LICENSE](LICENSE).
