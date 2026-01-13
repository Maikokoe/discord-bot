import discord
from discord.ext import commands
from discord import app_commands
from collections import deque
import datetime
import os

# --- ELITE DATA STORAGE ---
# Holds last 10 items per channel for various event types
snipe_cache = {}
edit_cache = {}
reaction_cache = {}
voice_cache = {}

def get_queue(cache, channel_id):
    if channel_id not in cache:
        cache[channel_id] = deque(maxlen=10)
    return cache[channel_id]

# --- BOT INITIALIZATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True # Required for voice sniping
bot = commands.Bot(command_prefix="!", intents=intents)

# --- THE EYES: GHOST LISTENERS ---

@bot.event
async def on_message_delete(msg):
    if msg.author.bot: return
    q = get_queue(snipe_cache, msg.channel.id)
    q.appendleft({
        "content": msg.content,
        "uid": msg.author.id,
        "time": datetime.datetime.now(),
        "file": msg.attachments[0].url if msg.attachments else None
    })

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content: return
    q = get_queue(edit_cache, before.channel.id)
    q.appendleft({
        "old": before.content,
        "new": after.content,
        "uid": before.author.id,
        "time": datetime.datetime.now()
    })

@bot.event
async def on_raw_reaction_remove(payload):
    q = get_queue(reaction_cache, payload.channel_id)
    q.appendleft({
        "emoji": str(payload.emoji),
        "uid": payload.user_id,
        "mid": payload.message_id,
        "time": datetime.datetime.now()
    })

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel == after.channel: return
    channel = before.channel or after.channel
    q = get_queue(voice_cache, channel.id)
    status = "left" if after.channel is None else "joined"
    q.appendleft({
        "uid": member.id,
        "status": status,
        "v_name": channel.name,
        "time": datetime.datetime.now()
    })

# --- THE TECH: ADVANCED SLASH COMMANDS ---

async def create_ghost_embed(itx, data, title, color):
    # ELITE TECH: Always fetch current user data to see current avatar/name
    user = await bot.fetch_user(data["uid"])
    embed = discord.Embed(title=title, color=color, timestamp=data["time"])
    embed.set_author(name=f"{user.name}#{user.discriminator}", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)
    return embed, user

@bot.tree.command(name="snipe", description="view deleted ghost history")
async def snipe(itx: discord.Interaction, index: int = 1):
    q = snipe_cache.get(itx.channel_id)
    if not q or len(q) < index: return await itx.response.send_message("ghost cache empty", ephemeral=True)
    
    data = q[index-1]
    embed, user = await create_ghost_embed(itx, data, "Message Sniped", 0x2b2d31)
    embed.description = data["content"] or "*file only*"
    if data["file"]: embed.set_image(url=data["file"])
    await itx.response.send_message(embed=embed)

@bot.tree.command(name="esnipe", description="view edit history")
async def esnipe(itx: discord.Interaction, index: int = 1):
    q = edit_cache.get(itx.channel_id)
    if not q or len(q) < index: return await itx.response.send_message("no edits logged", ephemeral=True)
    
    data = q[index-1]
    embed, user = await create_ghost_embed(itx, data, "Edit Intercepted", 0x00ffff)
    embed.add_field(name="Old", value=f"```\n{data['old']}\n```", inline=False)
    embed.add_field(name="New", value=f"```\n{data['new']}\n```", inline=False)
    await itx.response.send_message(embed=embed)

@bot.tree.command(name="rsnipe", description="see who removed a reaction")
async def rsnipe(itx: discord.Interaction, index: int = 1):
    q = reaction_cache.get(itx.channel_id)
    if not q or len(q) < index: return await itx.response.send_message("no reactions sniped", ephemeral=True)
    
    data = q[index-1]
    embed, user = await create_ghost_embed(itx, data, "Reaction Ghost", 0xff00ff)
    embed.description = f"Removed {data['emoji']} from message `{data['mid']}`"
    await itx.response.send_message(embed=embed)

# --- STARTUP ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Elite Engine Active: {bot.user}")

bot.run(TOKEN)
