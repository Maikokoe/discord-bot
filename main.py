import discord
from discord import app_commands
from discord.ext import commands
import time
import aiohttp
from transformers import GPT2LMHeadModel, GPT2Tokenizer
import torch
import json
import io
import re
import os


intents = discord.Intents.default()
intents = discord.Intents.all()  # ✅ Enables ALL intents

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

os.getenv("DISCORD_TOKEN")


@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")




# Load GPT-2 tokenizer and model
tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
model_path = "./gpt2-trained"
model = GPT2LMHeadModel.from_pretrained(model_path if os.path.exists(model_path) else "gpt2")

# Load memory
if os.path.exists("memory.json"):
    with open("memory.json", "r") as f:
        memory = json.load(f)
else:
    memory = {}

def save_memory():
    with open("memory.json", "w") as f:
        json.dump(memory, f, indent=2)

def generate_response(user_id, new_input):
    if user_id not in memory:
        memory[user_id] = []

    memory[user_id].append(new_input)
    memory[user_id] = memory[user_id][-10:]

    prompt = "\n".join(memory[user_id]) + "\nBot:"
    input_ids = tokenizer.encode(prompt, return_tensors='pt')

    output = model.generate(
        input_ids,
        max_length=150,
        pad_token_id=tokenizer.eos_token_id,
        temperature=0.9,
        top_k=50,
        top_p=0.95,
        do_sample=True,
    )

    response = tokenizer.decode(output[0], skip_special_tokens=True)
    bot_response = response[len(prompt):].strip()
    memory[user_id].append("Bot: " + bot_response)

    # Save to training data
    with open("training_data.txt", "a", encoding="utf-8") as f:
        f.write(f"User: {new_input}\nBot: {bot_response}\n\n")

    save_memory()
    return bot_response

def train_on_logs():
    if not os.path.exists("training_data.txt"):
        return "❌ No training data yet."

    dataset = TextDataset(
        tokenizer=tokenizer,
        file_path="training_data.txt",
        block_size=128,
    )
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    training_args = TrainingArguments(
        output_dir="./gpt2-trained",
        overwrite_output_dir=True,
        num_train_epochs=1,
        per_device_train_batch_size=1,
        save_steps=500,
        save_total_limit=1,
        logging_dir="./logs",
        logging_steps=100,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        data_collator=data_collator,
        train_dataset=dataset,
    )

    trainer.train()
    trainer.save_model("./gpt2-trained")
    return "✅ Training complete. Model updated!"

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"🌐 Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"⚠️ Sync error: {e}")

@tree.command(name="speak", description="Talk to the bot and help it learn.")
async def speak(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    user_id = str(interaction.user.id)
    response = generate_response(user_id, "User: " + message)
    await interaction.followup.send(response or "🤖 Hmm... I didn’t catch that.")

@tree.command(name="train", description="Train the bot on your conversation history.")
async def train(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    msg = train_on_logs()
    await interaction.followup.send(msg)








# /emoji command
@tree.command(name="emoji", description="Get a custom emoji by ID")
async def get_emoji(interaction: discord.Interaction, emoji_id: str):
    try:
        emoji = await bot.fetch_emoji(int(emoji_id))
        await interaction.response.send_message(f"{emoji}")
    except discord.NotFound:
        await interaction.response.send_message("Emoji not found.")
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}")

# /sticker command
@tree.command(name="sticker", description="Get a sticker by ID")
async def get_sticker(interaction: discord.Interaction, sticker_id: str):
    try:
        sticker = await bot.fetch_sticker(int(sticker_id))
        await interaction.response.send_message(sticker.url)
    except discord.NotFound:
        await interaction.response.send_message("Sticker not found.")
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}")







start_time = time.time()

@tree.command(name="uptime", description="Check how long the bot has been running")
async def uptime(interaction: discord.Interaction):
    uptime_seconds = int(time.time() - start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    await interaction.response.send_message(
        f"🟢 Uptime: {hours}h {minutes}m {seconds}s"
    )









@tree.command(name="steale", description="Steal a custom emoji by ID or emoji input and add it to your server")
async def steal_emoji(interaction: discord.Interaction, emoji_input: str, name: str):
    try:
        await interaction.response.defer()  # In case it takes time

        # Extract emoji ID and animated status using regex
        match = re.match(r'<(a?):\w+:(\d+)>', emoji_input)
        if match:
            is_animated = match.group(1) == 'a'
            emoji_id = match.group(2)
        elif emoji_input.isdigit():
            emoji_id = emoji_input
            is_animated = False  # Default to png
        else:
            return await interaction.followup.send("❌ Invalid emoji or ID format.")

        # Build URL based on animation type
        ext = "gif" if is_animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?v=1"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await interaction.followup.send("❌ Failed to download emoji.")
                data = await resp.read()

        # Add the emoji to the server
        new_emoji = await interaction.guild.create_custom_emoji(name=name, image=data)
        await interaction.followup.send(f"✅ Stolen emoji added: <{'a' if is_animated else ''}:{new_emoji.name}:{new_emoji.id}>")

    except discord.Forbidden:
        await interaction.followup.send("❌ I don’t have permission to add emojis.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")



@tree.command(name="steals", description="Steal a sticker by ID and add to your server")
async def steal_sticker(interaction: discord.Interaction, sticker_id: str, name: str):
    try:
        sticker = await bot.fetch_sticker(int(sticker_id))
        url = sticker.url
        format = sticker.format.name.lower()  # png, apng, or lottie

        if format == "lottie":
            return await interaction.response.send_message("❌ Lottie stickers can't be added by bots.")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await interaction.response.send_message("❌ Failed to download sticker.")
                data = await resp.read()

        # Upload to server
        await interaction.guild.create_sticker(
            name=name,
            description="Stolen sticker 😈",
            emoji="🙂",  # required emoji association
            file=discord.File(io.BytesIO(data), filename=f"{name}.{format}")
        )

        await interaction.response.send_message(f"✅ Stolen sticker added: `{name}`")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}")





bot.run(os.getenv("DISCORD_TOKEN"))



