# Development environment

Recorded 2026-11-12 from the original machine (Windows 11 Pro, PowerShell).
Use this to reproduce the setup on a second machine.

## Setup (Windows, PowerShell)

```powershell
# 1. Python 3.12 and uv
winget install Python.Python.3.12
winget install astral-sh.uv

# 2. Virtual environment in the repo root
uv venv --python 3.12

# 3. Exact package versions
uv pip install -r requirements-lock.txt

# 4. llama-cpp-python from the prebuilt CPU wheel (PyPI would compile from source)
uv pip install llama-cpp-python==0.3.36 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --index-strategy unsafe-best-match
```

**Never run `uv sync`.** It removes packages not in `pyproject.toml`'s
dependencies (llama-cpp-python and pymupdf).

## Rules

- Always use the venv's interpreter: `.venv\Scripts\python.exe -m pytest`,
  `.venv\Scripts\python.exe scripts\...`. Never use the `py` launcher; it picks
  a global Python without the project's packages.
- `UV_HTTP_TIMEOUT`: on a slow connection large wheels (onnxruntime, numpy,
  llama-cpp-python) can time out. Raise it for the session, e.g.
  `$env:UV_HTTP_TIMEOUT = "300"`.
- `UV_LINK_MODE`: if the uv cache and the repo are on different drives
  (e.g. cache on C:, repo on D:), uv warns that hardlinks fail and falls back
  to copying. Set `$env:UV_LINK_MODE = "copy"` to silence it.

## Key package versions

pymupdf 2.0, pymupdf4llm 2.0, pymupdf-layout 2.0, onnxruntime 1.31.0,
numpy 2.5.4, sympy 1.14.0, llama-cpp-python 0.3.36, pytest 9.1.1,
ruff 0.17.1, pyright 1.1.414. Full list: `requirements-lock.txt`.

## Local files (not committed)

| Path | Size (bytes) | SHA-256 |
|---|---|---|
| `data\G9-Mathematics-STB-2023-web.pdf` | 19,070,511 | `31CC17EE29F3A10B4C9A8BCA67D21C9B5446112620C7595F7D6D5C3330CDB139` |
| `models\qwen2.5-1.5b-q4_k_m.gguf` | 986,048,512 | `183715C435899236895DA3869489CC30AC241476B4971A20285B1A462818A5B4` |
| `data\extracted\` (12 files, generated) | 1,534,528 total | n/a (regenerated) |

Check a file with:

```powershell
(Get-FileHash data\G9-Mathematics-STB-2023-web.pdf -Algorithm SHA256).Hash
```

## Expected results

- `pytest`: 394 passed.
- Lesson chunks: 32 total; 6 in section 3.1, 26 in section 3.2.
