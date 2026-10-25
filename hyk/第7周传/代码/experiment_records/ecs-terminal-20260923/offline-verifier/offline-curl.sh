#!/bin/sh
if [ "$#" -eq 2 ] && [ "$1" = "-LsSf" ] && [ "$2" = "https://astral.sh/uv/0.9.5/install.sh" ]; then
    exec cat /opt/tb-verifier-cache/assets/uv-install.sh
fi
if [ "$#" -eq 4 ] && [ "$1" = "-sSfL" ] && [ "$2" = "file:///opt/tb-verifier-cache/assets/uv-x86_64-unknown-linux-gnu.tar.gz" ] && [ "$3" = "-o" ]; then
    exec cp /opt/tb-verifier-cache/assets/uv-x86_64-unknown-linux-gnu.tar.gz "$4"
fi
for real_curl in /usr/local/bin/curl /usr/bin/curl /bin/curl; do
    if [ -x "$real_curl" ]; then
        exec "$real_curl" "$@"
    fi
done
echo 'curl is unavailable for this uncached request' >&2
exit 127
