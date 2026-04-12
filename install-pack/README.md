# Jarviscore Installation Pack

This folder packages the host/bootstrap steps that cannot live inside normal Python `requirements*.txt` files.

It does **not** embed Ollama or the model blobs into the repository.  
Instead, it gives you a repeatable repo-local pack that installs:

- Python environment + repo dependencies
- optional voice dependencies
- Ollama runtime on Windows
- the Jarvis model set
- readiness verification

The default Jarvis model set includes:
- `llama3.2:1b`
- `llama3.2:3b`
- `qwen2.5vl:3b`
- `qwen3-vl:8b`
- `deepcoder:14b`
- `nomic-embed-text-v2-moe`

## Files

- `bootstrap_host.ps1` - one-command bootstrap wrapper
- `bootstrap_host_advanced.bat` - resilient Windows bootstrap with Ollama fallbacks and microphone acceptance on by default
- `full_auto_install.bat` - combined full auto installer that runs advanced bootstrap, direct model install, and acceptance
- `install_python_env.ps1` - create/update `.venv` and install repo deps
- `install_ollama_runtime.ps1` - install Ollama on Windows via `winget` if missing
- `pull_jarvis_models.ps1` - pull the Jarvis model set through the existing repo script
- `install_models_now.bat` - force/run the model-pull step directly after Ollama is installed
- `verify_stack.ps1` - run readiness/compile verification
- `..\requirements-readme.txt` - dependency and model reference

## Recommended order

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-pack\bootstrap_host.ps1
```

Advanced Windows bootstrap with microphone acceptance enabled by default:

```bat
install-pack\bootstrap_host_advanced.bat
```

Combined full auto install:

```bat
install-pack\full_auto_install.bat
```

If Ollama is already installed and you only want to force the model pull step:

```bat
install-pack\install_models_now.bat
```

## Notes

- The bootstrap assumes **Windows PowerShell / PowerShell 7**.
- CI is pinned to **Python 3.10**. Local development can use newer versions, but some voice-package installs may be less reliable there.
- The default voice bootstrap mode is **Kokoro pack mode**, which installs the lighter runtime deps needed by the bundled Kokoro ONNX pack.
- The advanced `.bat` wrapper prefers `pwsh` when available, falls back to Windows PowerShell, retries Ollama readiness, retries model pulls once, and runs `scripts\accept_target_stack.ps1` with microphone validation enabled by default.
- If you want package-mode voice dependencies instead, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-pack\install_python_env.ps1 -VoiceMode Package
```
