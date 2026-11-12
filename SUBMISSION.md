# qnxdoctor

Host-side doctor for QNX SDP 8.0 Makefile projects. Hackathon category: Developer Tooling & Host Tools.

This file is the project write-up. It describes what the code in this repository does today. It does not describe a run on a real QNX board, a real `qcc`, or QEMU. Those have not been executed here. CI is unit tests plus a scripted demo, both without the SDP installed.

## Inspiration

A Neutrino port dies in the same few places before it dies in the code. The shell never sourced `qnxsdp-env.sh`, so `qcc` and `qconfig.mk` are missing. `QNX_HOST` points at the SDP root instead of `host/linux/x86_64`. `MAKEFLAGS` has no `-I$QNX_TARGET/usr/include`, so `include $(QCONFIG)` cannot see the file. A tree left over from SDP 7 still has `qnx710`, `target/qnx7`, `CC=gcc`, `-march=native`, or `nto-armv7-o-le`. Socket calls are not in libc on QNX, and `pthread`, `dl`, and `rt` are.

Those are checklist items. They should fail in CI, including on a runner that does not have a QNX license. qnxdoctor is that checklist.

## What it does

`qnxdoctor` reads the process environment and the project's Makefiles, C and C++ sources, shell scripts, and GitHub Actions workflows. It prints a text report or the same report as JSON. Exit status is 0 when nothing is an error, 1 when any check is an error, and 2 for usage problems. Warnings do not fail the run.

Without the SDP, the shell is **degraded** and the project checks still run. `--require-sdp` promotes the "toolchain is missing" warnings to errors, for a build job that must have the SDK. `--sdp-root` inspects one install tree. `--no-discover` skips the usual prefixes (`~/qnx800`, `/opt/qnx800`, `/sdp/800`, and the SDP 7 paths).

The bundled trees are the demo:

- `examples/hello-sdp8` is a recursive mk project for `nto-aarch64-o-le` and `nto-x86_64-o`. It passes.
- `examples/plain-aarch64` is a one-file Makefile with `CC=qcc` and `-Vgcc_ntoaarch64le`. It passes.
- `examples/broken-port` is an SDP 7 port: host `gcc`, `-march=native`, `qnx710`, no `qtargets.mk`, ARMv7, big-endian, `linux/if.h`, `sys/epoll.h`, `socket()` without `libsocket`, and scripts that never source the env file. It exits 1.

`qnxdoctor demo` prints all three and exits 0. It is a gallery, not a gate.

The tool does not run `make`, does not compile, and does not boot a guest. The only time it executes `qcc` is `qcc -V`, and only when a binary is already on `PATH`. Make conditionals are not fully evaluated. An assignment inside `ifeq` is still visible. CMake is reported; the detailed checks are for Makefiles. Shell scripts are read at the project root and one directory down, plus `.github/workflows`.

## How it was built

Python 3.9 or newer, standard library only. No third-party packages.

The environment checks compare `QNX_HOST`, `QNX_TARGET`, `PATH`, and `MAKEFLAGS` with the layout `qnxsdp-env.sh` publishes, and with the SDP 8.0 facts in the Programmer's Guide: Neutrino CPUs are AArch64 little-endian and x86_64, there is no `mk` compiler, and the recursive build is GNU make plus `qconfig.mk`, `qtargets.mk`, and `recurse.mk`. A small Makefile reader records assignments, includes, and recipe indentation without running GNU make. Findings are notes with a severity. The text renderer and the JSON renderer share that list.

Tests build a fake SDP tree (host `qcc` stub, sysroot include files, a banner that says 8.0) and point the doctor at it. They also parse the three examples. Nothing in CI calls a real compiler.

The faceless demo is `demo/run_demo.py`. `--check` is what CI runs. `--play` is the same commands on a clock of about two and a half minutes. `demo/narration.md` is the voiceover, timestamped to that clock. `demo/qnxdoctor.tape` is an optional VHS tape that types `--play`. The ready half of the session sources `demo/mock-env.sh`, whose `qcc` prints the two SDP 8.0 specs for `-V` and refuses every other invocation.

`demo/qnxdoctor-demo.mp4` is that session already recorded, with a Piper voiceover of the narration and `demo/qnxdoctor-demo.srt` beside it. `bash demo/render_video.sh` regenerates both. The video was not captured on a board, a real `qcc`, or QEMU.

## Challenges

SDP 8.0 reused the name "mk" for the include files, not for a compiler driver. Treating a missing `mk` binary as a failure would be wrong, so the doctor reports it as a note.

`QNX_TARGET` on its own does not make `include $(QCONFIG)` work. `MAKEFLAGS` has to carry `-I$QNX_TARGET/usr/include`. That is an error when the sysroot exists and a warning when it does not.

`gcc_ntox86` is the old 32-bit spec. A substring check would accept it as `gcc_ntox86_64`. The spec parser does not.

A missing SDK has to be a warning, or a judge without QNX Everywhere cannot run the tool. The same warning has to be an error in a build job. `--require-sdp` is that switch, and it does not promote notes.

The long text report scrolled the project errors off the screen, under the environment warnings and above the passed checks. The report now repeats each error, without the help paragraph, directly above the summary line. The summary also repeats the status and the mode.

## Accomplishments

- A doctor that runs in CI with no SDP install, and that can still say `mode: ready` against a fake tree shaped like SDP 8.0.
- Exit codes a workflow can use, plus JSON with the same findings.
- Three examples, including a broken port whose error ids are locked by tests.
- A demo a judge can replay with `python3 demo/run_demo.py --play` and read along from `demo/narration.md`. No camera, no board, no SDK.
- The checks follow the public SDP 8.0 Programmer's Guide and the `mkqnximage` utilities page. Where this repository has not performed a step, the README says so.

## What we learned

Sourcing `qnxsdp-env.sh` is the product. Copying `qcc` onto `PATH` without `QNX_HOST`, `QNX_TARGET`, and `MAKEFLAGS` is not a build environment. The doctor treats that as its own warning.

Variant directory names are the target. `nto-armv7-o-le` and `nto-aarch64-o-be` are not SDP 8.0 Neutrino outputs, even when the rest of the Makefile looks familiar.

On QNX, "link with pthread" and "sockets are in libc" are Linux habits. The broken sample trips both, on purpose.

## What's next

Run `source ~/qnx800/qnxsdp-env.sh`, `qnxdoctor --require-sdp`, and `make -C examples/hello-sdp8` on a real SDP 8.0 host, then boot a guest with `mkqnximage --type=qemu`. None of that has been done in this repository. The README has the commands and the official links.

After that, the gaps that are already visible in the code:

- Make `ifeq` blocks are not evaluated, so a compiler assignment that is actually disabled still counts.
- CMake is only a mention check, not a toolchain-file check.
- The doctor does not apply a patch. It prints the finding and the fix.
- It does not inspect a built Neutrino binary. There is no `readelf` step, because CI never produces one.

## Built with

- Python 3.9+ standard library (no third-party runtime dependencies)
- GNU make, detected when it is on `PATH`. The file checks do not need it
- QNX SDP 8.0 Programmer's Guide and Utilities Reference, as the spec the checks follow. The SDK is not linked, vendored, or required
- GitHub Actions (Ubuntu) for the unit tests and `demo/run_demo.py --check`
- Optional: [VHS](https://github.com/charmbracelet/vhs), ttyd, ffmpeg, and [Piper](https://github.com/rhasspy/piper) (Lessac high) for `demo/qnxdoctor-demo.mp4`. CI does not install or run them

Not used, and not claimed: a QNX license, a real `qcc`, QEMU, or a Neutrino board.
