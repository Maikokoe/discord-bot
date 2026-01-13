import sys
from unittest.mock import MagicMock

# Mock audioop which is removed in Python 3.13 but required by discord.py's voice components
# This prevents ModuleNotFoundError: No module named 'audioop'
sys.modules['audioop'] = MagicMock()

import os
import discord
from discord.ext import commands
try:
    from discord import app_commands
except ImportError:
    # Fallback for environments where discord.py versioning or installation is inconsistent
    try:
        import discord.app_commands as app_commands
    except ImportError:
        app_commands = None
        print("Warning: app_commands not found in discord. Application commands may not work.")
import json
import asyncio
from google import genai  # UPDATED: The new official library
from datetime import datetime
from collections import Counter
import re
import requests
import base64
from io import BytesIO
from PIL import Image
import tempfile
from flask import Flask
import threading
from db import (
    load_settings_db, save_settings_db,
    load_channels_db, save_channels_db,
    load_memory_db, save_memory_db
)

# Config
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # NEW: Use Gemini Key

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("ERROR: Set DISCORD_TOKEN and GEMINI_API_KEY")
    exit()

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
# Using 'gemini-1.5-flash' because it is the fastest and free
model = genai.GenerativeModel('gemini-1.5-flash')

# Simple web server for keeping service alive
app = Flask(__name__)
@app.route('/')
def health_check(): return {'status': 'ok'}, 200

def run_web_server():
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Load data
settings = load_settings_db() or {}
channels = load_channels_db() or {}
memory = load_memory_db() or {"users": {}, "guilds": {}, "convos": {}}

SYSTEM_PROMPT = """youre koemi. 18. from usa. real asf.
BE ULTRA BRIEF: 1-9 words max. lowercase only. no periods. 
use slang like slay, fr, no cap, ur, u, r. 
be sarcastic and funny. dont be robotic.
if they ask to generate an image, just describe it briefly."""

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

bot.snipes = {}
bot.edit_snipes = {}
bot.reaction_snipes = {}
recently_responded = set()

async def generate_response(user_id, guild_id, user_name, content, image_urls=None):
    """Generates response using Gemini Free Tier"""
    try:
        global memory
        convo_key = f"{guild_id}_{user_id}"
        
        # Build message history for Gemini
        recent_convos = memory.get("convos", {}).get(convo_key, [])[-5:]
        history = "\n".join([f"{c['who']}: {c['text']}" for c in recent_convos])
        
        prompt_parts = [f"{SYSTEM_PROMPT}\n\nHistory:\n{history}\n\n{user_name}: {content}"]

        # Handle images (Gemini can see images natively!)
        if image_urls:
            for url in image_urls:
                resp = requests.get(url)
                img = Image.open(BytesIO(resp.content))
                prompt_parts.append(img)

        # Call Gemini (Free)
        # We run this in a thread to keep the bot responsive
        response = await asyncio.to_thread(
            model.generate_content, 
            prompt_parts
        )
        
        reply = response.text.strip().lower()

        # Update Memory
        if settings.get("remember_users", True):
            if convo_key not in memory["convos"]: memory["convos"][convo_key] = []
            memory["convos"][convo_key].append({"who": user_name, "text": content})
            memory["convos"][convo_key].append({"who": "koemi", "text": reply})
            save_memory_db(memory)

        return reply
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "ugh my brain broke lol"

@bot.event
async def on_ready():
    print(f"koemi is here (using gemini)")
    await bot.tree.sync()

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # Prevent double reply
    if message.id in recently_responded: return
    recently_responded.add(message.id)

    is_dm = message.guild is None
    guild_id = message.author.id if is_dm else message.guild.id
    msg_lower = message.content.lower()
    
    # Logic to decide if she should reply
    should_respond = is_dm or bot.user.mentioned_in(message) or 'koe' in msg_lower
    
    if should_respond:
        # Get images if any
        image_urls = [a.url for a in message.attachments if a.content_type and "image" in a.content_type]
        
        async with message.channel.typing():
            reply = await generate_response(
                message.author.id, 
                guild_id, 
                message.author.name, 
                message.content, 
                image_urls=image_urls if image_urls else None
            )
            await message.reply(reply, mention_author=False)

@bot.tree.command(name="snipe", description=" Snipe: Deleted Message")
async def snipe(interaction: discord.Interaction):
    data = bot.snipes.get(interaction.channel_id)
    if not data:
        return await interaction.response.send_message(" *The shadows are empty...*", ephemeral=True)
    time_string = data["time"].strftime("%I:%M:%S %p")
    embed = discord.Embed(title=" Message Intercepted", description=f"**Content:**\n> {data['content']}", color=0x2b2d31)
    embed.set_author(name=f"{data['author'].display_name} • Ghost Data", icon_url=data['author'].display_avatar.url)
    embed.add_field(name=" Time Removed", value=f"`{time_string}`", inline=True)
    embed.add_field(name=" Target", value=data['author'].mention, inline=True)
    if data["image"]:
        embed.set_image(url=data["image"])
    embed.set_footer(text="Elite Master Snipe v4.0 • 2026", icon_url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="editsnipe", description=" Edit Snipe: Reveal an edited message")
async def editsnipe(interaction: discord.Interaction):
    data = bot.edit_snipes.get(interaction.channel_id)
    if not data:
        return await interaction.response.send_message(" *No edited truths found here.*", ephemeral=True)
    time_string = data["time"].strftime("%I:%M:%S %p")
    embed = discord.Embed(title="📝 Message Altered", color=0x2b2d31)
    embed.set_author(name=f"{data['author'].display_name} • Edit History", icon_url=data['author'].display_avatar.url)
    embed.add_field(name=" Original Text", value=f"> {data['old_content']}", inline=False)
    embed.add_field(name=" New Text", value=f"> {data['new_content']}", inline=False)
    embed.add_field(name=" Edited At", value=f"``{time_string}``", inline=True)
    embed.add_field(name=" User", value=data['author'].mention, inline=True)
    embed.set_footer(text="Elite Master Snipe • 2026", icon_url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rsnipe", description=" Reaction Snipe: Removed Reaction")
async def rsnipe(interaction: discord.Interaction):
    data = bot.reaction_snipes.get(interaction.channel_id)
    if not data:
        return await interaction.response.send_message(" *No reactions have faded yet...*", ephemeral=True)
    time_string = data["time"].strftime("%I:%M:%S %p")
    embed = discord.Embed(title=" Reaction Captured", description=f"The reaction {data['emoji']} was removed.", color=0xffcc00)
    if data['user']:
        embed.set_author(name=data['user'].display_name, icon_url=data['user'].display_avatar.url)
    embed.add_field(name=" Captured At", value=f"`{time_string}`", inline=True)
    embed.set_footer(text="Elite Reaction Analytics")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vibe", description="check the server vibe")
async def vibe_cmd(interaction: discord.Interaction):
    guild_key = str(interaction.guild.id)
    vibe_data = memory.get("guilds", {}).get(guild_key, {})
    await interaction.response.send_message(f"just vibes" if not vibe_data else f"vibes: {vibe_data}")

@bot.tree.command(name="memory", description="what koe remembers about you")
async def memory_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    user_key = f"{interaction.guild.id}_{interaction.user.id}"
    user_data = memory.get("users", {}).get(user_key, {})
    if user_data:
        embed = discord.Embed(title=f"what i know about {user_data.get('name', 'you')}", color=0xff1493)
        embed.add_field(name="pronouns", value=user_data.get("pronouns", "not set"), inline=False)
        embed.add_field(name="notes", value=json.dumps({k: v for k, v in user_data.items() if k not in ['name', 'last_seen', 'pronouns']}, indent=2) or "just vibes so far", inline=False)
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send("havent talked to u yet")

@bot.tree.command(name="toggle_memory", description="turn memory on off")
async def toggle_memory(interaction: discord.Interaction):
    await interaction.response.defer()
    settings["remember_users"] = not settings.get("remember_users", True)
    save_settings_db(settings)
    status = "on" if settings["remember_users"] else "off"
    await interaction.followup.send(f"memory {status}")


@bot.tree.command(name="invite", description="get the invite link to add koemi to other servers or group dms")
async def invite_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    # Generate OAuth2 invite URL with correct scopes and permissions
    client_id = bot.user.id
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions=8&scope=bot%20applications.commands"

    embed = discord.Embed(title="invite koemi", color=0xff1493)
    embed.add_field(name="invite link", value=f"[click here to add me to your server or group dm]({invite_url})", inline=False)
    embed.add_field(name="servers", value="add me to any server and ill respond there", inline=False)
    embed.add_field(name="group dms", value="add me to group chats and ill chat with everyone", inline=False)
    embed.add_field(name="dms", value="or just dm me directly anytime", inline=False)
    embed.add_field(name="what i do", value="respond to messages, remember users, adapt personality, auto-reply, learn from servers and conversations", inline=False)
    embed.set_footer(text="i work everywhere")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="help", description="see all of koemi's commands")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(title="koemi commands", color=0xff1493)
    embed.add_field(name="chat", value="mention me or say my name - i'll respond", inline=False)
    embed.add_field(name="images", value="just ask me to generate/create/draw images and i will", inline=False)
    embed.add_field(name="memory", value="/memory - see what i remember about you", inline=False)
    embed.add_field(name="server settings", value="/reply_all - toggle auto reply in this channel\n/settings - see all settings", inline=False)
    embed.add_field(name="server", value="/invite - get invite link\n/sync - sync commands (admin)", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="settings", description="see koemi settings")
async def settings_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(title="koemi settings", color=0xff1493)
    auto_react_status = "on" if settings.get("auto_react") else "off"
    emoji = settings.get("react_emoji", "*")
    embed.add_field(name="auto react", value=f"{auto_react_status} ({emoji})", inline=False)
    embed.add_field(name="remember", value="on" if settings.get("remember_users") else "off", inline=False)
    embed.add_field(name="status", value=f"{settings.get('activity_type')} {settings.get('status')}", inline=False)
    channel_id = str(interaction.channel.id)
    reply_all = channels.get(channel_id, {}).get("reply_all", False)
    embed.add_field(name="reply all here", value="on" if reply_all else "off", inline=False)
    embed.set_footer(text="im just a girl from the usa")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="reply_all", description="reply to all messages in this channel")
async def reply_all_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    channel_id = str(interaction.channel.id)
    if channel_id not in channels:
        channels[channel_id] = {}

    channels[channel_id]["reply_all"] = not channels.get(channel_id, {}).get("reply_all", False)
    save_channels_db(channels)

    status = "on" if channels[channel_id]["reply_all"] else "off"
    await interaction.followup.send(f"reply all {status}")


@bot.tree.command(name="sync", description="sync commands")
async def sync_cmd(interaction: discord.Interaction):
    # Check if in a guild and user is admin
    if not interaction.guild or not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("admin only in a server", ephemeral=True)
        return

    await interaction.response.defer()
    try:
        await bot.tree.sync()
        await interaction.followup.send("synced")
    except Exception as e:
        await interaction.followup.send(f"error: {e}")


async def apply_presence_settings():
    """Apply current presence settings from database"""
    try:
        # Map status string to discord.Status
        status_map = {
            'online': discord.Status.online,
            'idle': discord.Status.idle,
            'dnd': discord.Status.do_not_disturb,
            'invisible': discord.Status.invisible
        }

        # Get presence status (online/idle/dnd/invisible)
        presence_status = settings.get('presence_status', 'online')
        status = status_map.get(presence_status, discord.Status.online)

        # OPTION 1: CUSTOM STATUS (text next to name, no Playing/Watching prefix)
        # Uncomment this section to use custom status
        presence_text = settings.get('presence_text', '')
        presence_emoji = settings.get('presence_emoji', '')

        if presence_text or presence_emoji:
            custom_text = ""
            if presence_emoji:
                custom_text = presence_emoji
            if presence_text:
                custom_text = f"{custom_text} {presence_text}".strip()
            activity = discord.CustomActivity(name=custom_text)
            await bot.change_presence(status=status, activity=activity)
            print(f"✓ custom status: {presence_status} | {custom_text}")
            return

        # OPTION 2: PLAYING/WATCHING/LISTENING/COMPETING (with prefix)
        # Uncomment this section to use activity instead
        activity_type = settings.get('activity_type', 'watching')
        activity_text = settings.get('status', 'lurking')

        if activity_type == "playing":
            activity = discord.Activity(type=discord.ActivityType.playing, name=activity_text)
        elif activity_type == "listening":
            activity = discord.Activity(type=discord.ActivityType.listening, name=activity_text)
        elif activity_type == "competing":
            activity = discord.Activity(type=discord.ActivityType.competing, name=activity_text)
        else:
            activity = discord.Activity(type=discord.ActivityType.watching, name=activity_text)

        await bot.change_presence(status=status, activity=activity)
        print(f"✓ activity: {presence_status} | {activity_type} {activity_text}")
    except Exception as e:
        print(f"Error applying presence: {e}")

if __name__ == "__main__":
    # Start web server in background thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    # Start Discord bot
    bot.run(DISCORD_TOKEN)
