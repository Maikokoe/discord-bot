import discord
from discord import app_commands
from discord.ext import commands
import time
import aiohttp
import json
import io
import re
import os
import ascyncio


intents = discord.Intents.default()
intents = discord.Intents.all()  # ✅ Enables ALL intents

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

os.getenv("DISCORD_TOKEN")


@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")












TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("ALLOWED_SERVER_ID", 0))  # Optional

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 👾 Robot Walking Animation
robot_walk = [
    r"""
      [◉_◉] 
     /|_||\
     /   \
    """,
    r"""
      [◉_◉]
     /||_||
     / \ 
    """,
    r"""
      [◉_◉] 
     ||_||\
     /   \
    """,
    r"""
      [◉_◉]
     /|_||\
     /   \
    """,
    r"""
      [◉_◉]
     /||_||
     /   \
    """,
    r"""
      [◉_◉]
     /|_||\
     / \ 
    """
]

# 🧏 Anime Head Nod Animation
anime_nod = [
    r"""
    (≧◡≦)
     /|\
     / \
    """,
    r"""
    (・ω・)
     /|\
     / \
    """,
    r"""
    (≧◡≦)
     /|\
     / \
    """,
    r"""
    (・ω・)
     /|\
     / \
    """
]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if GUILD_ID and message.guild and message.guild.id != GUILD_ID:
        return

    if random.randint(1, 40) == 1:
        animation_type = random.choice(["robot", "anime"])
        frames = robot_walk if animation_type == "robot" else anime_nod

        animated_msg = await message.channel.send("```\nBooting animation...\n```")
        await asyncio.sleep(0.8)

        for frame in frames:
            await animated_msg.edit(content=f"```\n{frame}\n```")
            await asyncio.sleep(0.5)

        await asyncio.sleep(2)
        await animated_msg.delete()

    await bot.process_commands(message)
















bot.run(os.getenv("DISCORD_TOKEN"))



