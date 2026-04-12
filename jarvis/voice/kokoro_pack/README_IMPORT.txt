Jarvis Kokoro Voice Pack (2026-03-31)

Includes:
- kokoro/kokoro-v1.0.onnx
- kokoro/voices-v1.0.bin
- kokoro/voices.json
- kokoro/custom_voice_profiles.json
- kokoro/custom_voice_vectors.npz
- jarvis_launcher.py
- pronunciation_overrides.txt
- shortform_expansions.json

Preferred voice profile:
- jarvis_clone_from_piper
- speed: 0.90
- vector_blend: 0.35

How to use in another project:
1) Copy the kokoro folder into your target project.
2) Ensure dependencies include: kokoro_onnx, numpy, soundfile.
3) Load the profile from kokoro/custom_voice_profiles.json and vectors from kokoro/custom_voice_vectors.npz.
4) Set default voice to "jarvis_clone_from_piper", lang "en-gb", speed 0.90.

Notes:
- This pack contains large model files.
- If your other project already has the same kokoro-v1.0.onnx and voices-v1.0.bin, only custom_voice_profiles.json and custom_voice_vectors.npz are strictly needed for the tuned voice.
