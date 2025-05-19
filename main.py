import discord
from discord import app_commands
from discord.ext import commands
import time
import aiohttp
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



MEMORY_FILE = "memory.json"
translator = Translator()

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f)

async def smart_search(query):
    url = f"https://api.duckduckgo.com/?q={query}&format=json&no_redirect=1&no_html=1"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                answer = data.get("AbstractText")
                if answer:
                    return answer
    return None

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync()

@tree.command(name="teach", description="Teach Koe how to respond to a question")
@app_commands.describe(question="What someone might ask", answer="What Koe should say")
async def teach(interaction: discord.Interaction, question: str, answer: str):
    memory = load_memory()
    memory.append({"q": question.lower(), "a": answer})
    save_memory(memory)
    await interaction.response.send_message("Got it! I've learned something new 🧠", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()

    # Translate non-English messages
    try:
        detected = translator.detect(content)
        if detected.lang != 'en':
            translated = translator.translate(content, dest='en')
            await message.reply(f"🌍 Translated from {detected.lang}: {translated.text}", mention_author=True)
            return
    except:
        pass  # Ignore translation errors

    # Respond to replies directed at Koe
    if message.reference:
        ref = await message.channel.fetch_message(message.reference.message_id)
        if ref.author.id == bot.user.id:
            response = await smart_search(message.content)
            if response:
                await message.reply(response, mention_author=True)
                return
            else:
                memory = load_memory()
                for pair in memory:
                    if pair["q"] in content:
                        await message.reply(pair["a"], mention_author=True)
                        return
                await message.reply("Hmm... I'm still learning that. Try teaching me with `/teach`!", mention_author=True)
                return

    # Respond if "koe" is mentioned anywhere in message
    if "koe" in content:
        parts = content.split("koe", 1)
        prompt = parts[1].strip(" ,?!") if len(parts) > 1 else ""

        response = await smart_search(prompt)
        if response:
            await message.reply(response, mention_author=True)
            return
        else:
            memory = load_memory()
            for pair in memory:
                if pair["q"] in prompt:
                    await message.reply(pair["a"], mention_author=True)
                    return
            await message.reply("Hmm... I'm still learning that. Try teaching me with `/teach`!", mention_author=True)
            return

    await bot.process_commands(message)







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



