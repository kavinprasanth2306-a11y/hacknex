from gemma import gm

# 1. Initialize the model architecture (e.g. lightweight 270M or 1B model)
model = gm.nn.Gemma3_270M()

# 2. Load the instruction-tuned weights (automatically downloaded from Kaggle/GCS)
params = gm.ckpts.load_params(gm.ckpts.CheckpointPath.GEMMA3_270M_IT)

# 3. Create a chat sampler
sampler = gm.text.ChatSampler(
    model=model,
    params=params,
    multi_turn=True,
)

# 4. Generate response
prompt = "Write a haiku about artificial intelligence."
response = sampler.chat(prompt)
print("Response:\n", response)

# Follow-up turn
reply = sampler.chat("Explain the meaning behind it.")
print("\nFollow-up:\n", reply)
