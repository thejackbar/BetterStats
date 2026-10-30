import sys, time, json, torch, soundfile as sf
sys.path.insert(0, '/home/user/debpalash/voicestudio')
from omnivoice.models.omnivoice import OmniVoice
lines = json.load(open(sys.argv[1])); out = sys.argv[2]
instruct = "female, young adult, moderate pitch, australian accent"
torch.set_num_threads(4)
m = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cpu", dtype=torch.float32)
keys = list(lines)
t = time.time()
a = m.generate(text=lines[keys[0]], instruct=instruct)[0].detach().cpu().float().numpy().squeeze()
sf.write(f"{out}/{keys[0]}.wav", a, m.sampling_rate)
print(keys[0], round(len(a) / m.sampling_rate, 2), 's in', round(time.time() - t, 1), flush=True)
prompt = m.create_voice_clone_prompt(ref_audio=f"{out}/{keys[0]}.wav", ref_text=lines[keys[0]])
for key in keys[1:]:
    t = time.time()
    a = m.generate(text=lines[key], voice_clone_prompt=prompt)[0].detach().cpu().float().numpy().squeeze()
    sf.write(f"{out}/{key}.wav", a, m.sampling_rate)
    print(key, round(len(a) / m.sampling_rate, 2), 's in', round(time.time() - t, 1), flush=True)
print('ALL DONE', flush=True)
