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
# demo/render_video.sh records this same tape to an MP4 and mixes the
# narration. The session uses examples/ and demo/mock-env.sh.
# No QNX SDP is required.

Output demo/qnxdoctor-demo.gif

Set Shell "bash"
Set FontFamily "JetBrains Mono"
Set FontSize 18
Set LineHeight 1.15
Set Width 1280
Set Height 720
Set Padding 12
Set TypingSpeed 2ms
Set Framerate 8
Set PlaybackSpeed 1.0
Set Theme "Catppuccin Mocha"

# A short prompt, and a clear scrollback, before the recording starts.
# The play command below is the only thing the recording types.
Hide
Type "export PS1='$ '"
Enter
Type "clear"
Enter
Show

Type "python3 demo/run_demo.py --play"
Enter
Sleep 155s
