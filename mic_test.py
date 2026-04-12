"""Quick mic diagnostic — records 3 seconds and shows amplitude."""
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
DURATION = 3

print(f"Recording {DURATION}s from default mic at {SAMPLE_RATE} Hz...")
print("Speak now!\n")

audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
sd.wait()

pcm = audio.flatten()
peak = int(np.max(np.abs(pcm)))
mean = float(np.abs(pcm.astype("int32")).mean())
nonzero = int(np.count_nonzero(pcm))

print(f"Samples:    {len(pcm)}")
print(f"Non-zero:   {nonzero} / {len(pcm)}")
print(f"Peak amp:   {peak}")
print(f"Mean amp:   {mean:.1f}")
print()

if peak == 0:
    print("PROBLEM: Mic recorded pure silence. Wrong device or muted.")
elif peak < 100:
    print("PROBLEM: Mic signal is extremely quiet. Check input level or device.")
elif mean < 200:
    print("LOW: Mean amplitude is below Jarvis speech threshold (520). You may need to speak louder or move closer.")
else:
    print(f"OK: Signal looks good. Jarvis speech threshold is 520, your mean is {mean:.0f}.")
