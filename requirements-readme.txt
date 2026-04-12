Jarviscore Requirements Readme
==============================

This file explains what the repository requires beyond normal source code.

1) Python
---------
- CI target: Python 3.10
- Local dev can use newer Python versions, but some voice-package installs may be less reliable.

2) Python requirements files
----------------------------
- requirements.txt
  Core runtime file.
  The core runtime itself has no mandatory pip package beyond Python.

- requirements-dev.txt
  Development + test environment:
  * pytest
  * pytest-cov
  * mypy
  * ruff

- requirements-voice.txt
  Optional package-mode voice dependencies:
  * faster-whisper
  * kokoro
  * sounddevice
  * numpy

  Important note:
  * On newer Python versions, `faster-whisper` may install cleanly while the
    optional `kokoro` package path may still be less reliable.
  * The repo-supported local TTS path remains the bundled Kokoro pack.

- requirements-all.txt
  Installs both dev and package-mode voice requirements.

3) Recommended voice modes
--------------------------
- Pack mode (recommended in this repo)
  Uses the bundled Kokoro ONNX voice pack already stored in:
  jarvis/voice/kokoro_pack/

  Minimal pip packages typically needed:
  * numpy
  * soundfile
  * kokoro_onnx
  * sounddevice

- Package mode
  Uses requirements-voice.txt and the Python `kokoro` package path.

- STT mode
  Live speech-to-text requires:
  * faster-whisper
  * sounddevice
  * a working input device

  Software-ready is not the same as hardware-validated.
  Final mic validation still requires a real spoken utterance on the target machine.

4) OCR / vision notes
---------------------
- Windows OCR is supported through the built-in `Windows.Media.Ocr` path.
- Sidecar OCR files such as `<image>.ocr.txt` remain supported as overrides.
- Optional Tesseract CLI can also be used if installed separately.

5) Ollama runtime requirement
-----------------------------
Jarvis specialist/model execution requires a host Ollama install.

Required models:
- llama3.2:1b
- llama3.2:3b
- qwen2.5vl:3b
- qwen3-vl:8b
- deepcoder:14b
- nomic-embed-text-v2-moe

Embedding intent matching is enabled by default.
Disable it with:
  setx JARVIS_ENABLE_EMBEDDING_MATCH false

Semantic memory retrieval is also enabled by default.
Disable it with:
  setx JARVIS_ENABLE_SEMANTIC_MEMORY_RETRIEVAL false

6) Repo-local installation pack
-------------------------------
See:
- install-pack/README.md
- install-pack/bootstrap_host.ps1
- install-pack/bootstrap_host_advanced.bat

Typical bootstrap:

  powershell -NoProfile -ExecutionPolicy Bypass -File .\install-pack\bootstrap_host.ps1

Advanced Windows bootstrap with microphone validation on by default:

  .\install-pack\bootstrap_host_advanced.bat

Combined full auto install:

  .\install-pack\full_auto_install.bat

Model-pull only helper after Ollama is installed:

  .\install-pack\install_models_now.bat

7) Verification
---------------
Readiness:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\model_readiness.ps1 -OutputFormat json

Compile:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\compile_v1.ps1

Target acceptance:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\accept_target_stack.ps1 -SkipVoiceMic

Full mic-inclusive acceptance:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\accept_target_stack.ps1 -SkipVoiceMic:$false -MicDurationSeconds 3

8) Important limitation
-----------------------
The repository can contain install scripts, config, and the bundled Kokoro pack,
but it does not physically contain a real Ollama runtime installation or the
downloaded Ollama model store. Those are host-installed assets.

Some desktop/web helper tools are intentionally truthful about being unavailable;
they are not all production implementations yet.
