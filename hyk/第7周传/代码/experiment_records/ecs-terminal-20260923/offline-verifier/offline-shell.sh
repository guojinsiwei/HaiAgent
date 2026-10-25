# Sourced only during verification. The transport serves two exact cached
# resources and forwards all unrelated requests to the normal curl executable.
export PATH="/opt/tb-verifier-cache/transport:$PATH"
