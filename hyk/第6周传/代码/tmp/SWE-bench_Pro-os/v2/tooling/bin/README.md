# tooling/bin

`locked_codex.py` installs a pinned Codex CLI inside the sandbox during the setup phase by fetching the official
release tarball (rust-v0.155.1, `codex-package-x86_64-unknown-linux-musl.tar.gz`, sha256
`a65b895c6ac1a73629bbe4b864640c86133e94a43b4d67b3103044e1a306d5a2`) and verifying its checksum. If the sandbox
cannot download it, the agent falls back to uploading `codex-slim-0.155.1.tar.gz` from this directory. The slim
tarball is not committed (130 MB); build it once:

```bash
curl -fsSL -o pkg.tar.gz https://github.com/openai/codex/releases/download/rust-v0.155.1/codex-package-x86_64-unknown-linux-musl.tar.gz
echo "a65b895c6ac1a73629bbe4b864640c86133e94a43b4d67b3103044e1a306d5a2  pkg.tar.gz" | sha256sum -c -
mkdir pkg && tar xzf pkg.tar.gz -C pkg bin/codex bin/codex-code-mode-host codex-path/rg
(cd pkg && tar czf ../codex-slim-0.155.1.tar.gz bin/codex bin/codex-code-mode-host codex-path/rg)
sha256sum codex-slim-0.155.1.tar.gz   # ec82d845f8f6ee267b4e4cda75e4580d765305305ce93802b68286be4708e5ad
```

Note: the standalone `codex` binary alone fails closed (Code Mode needs `codex-code-mode-host`); keep all three files.
