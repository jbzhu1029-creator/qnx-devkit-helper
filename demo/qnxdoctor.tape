# Faceless recording of the qnxdoctor demo.
#
# From the repository root, with VHS installed (https://github.com/charmbracelet/vhs):
#
#   vhs demo/qnxdoctor.tape
#
# The tape types one command. That command is the scripted session in
# demo/run_demo.py, and demo/narration.md is timed to it. Start the
# voiceover when the "qnxdoctor faceless demo" banner appears.
# VHS writes demo/qnxdoctor-demo.gif, which is gitignored.
#
# No QNX SDP is required. The session uses examples/ and demo/mock-env.sh.

Output demo/qnxdoctor-demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 740
Set Padding 16
Set TypingSpeed 2ms

Type "python3 demo/run_demo.py --play"
Enter
Sleep 155s
