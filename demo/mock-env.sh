# Source from bash. Exports the variables qnxsdp-env.sh would set, pointed
# at demo/.mock-sdp. The qcc in that tree is a stub: `qcc -V` lists the
# SDP 8.0 specs, and any other invocation fails. It will not compile.
#
#   source demo/mock-env.sh
#
# Run this from a bash shell whose working directory does not matter.
# Executing the file (instead of sourcing it) cannot export into your shell.

if [ -n "${BASH_SOURCE[0]-}" ] && [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "Source this file: source demo/mock-env.sh" >&2
  exit 2
fi

_qnxdoctor_demo_dir=$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd) || return 1
_qnxdoctor_python=$(command -v python3) || {
  echo "python3 is required to build the mock SDP tree" >&2
  return 1
}
_qnxdoctor_exports=$("$_qnxdoctor_python" "$_qnxdoctor_demo_dir/mock_env.py" --export "$_qnxdoctor_demo_dir/.mock-sdp") || return 1
eval "$_qnxdoctor_exports"
unset _qnxdoctor_demo_dir _qnxdoctor_python _qnxdoctor_exports
