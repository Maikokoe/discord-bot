import sys
from unittest.mock import MagicMock

# Mock audioop which is removed in Python 3.13 but required by discord.py's voice components
# This prevents ModuleNotFoundError: No module named 'audioop'
sys.modules['audioop'] = MagicMock()

import os
import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
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
HF_API_KEY = os.getenv("HF_API_KEY")

if not DISCORD_TOKEN:
    print("ERROR: Set DISCORD_TOKEN")
    exit()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

OPENROUTER_API_URL = "http://koemi-production.up.railway.app:11434"

# Simple web server for Render (keeps the service alive)
app = Flask(__name__)

@app.route('/')
def health_check():
    return {'status': 'ok'}, 200

def run_web_server():
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Load from database
settings = load_settings_db() or {}
channels = load_channels_db() or {}
memory = load_memory_db() or {"users": {}, "guilds": {}, "convos": {}}

# Koemi's personality - ULTRA BRIEF GEN Z
SYSTEM_PROMPT = """youre koemi. 18. from usa. real asf.

BE ULTRA BRIEF:
- 1-3 words min, 5-9 words max. literally that's it
- only do longer if they ask for essay/story/help with homework or you need to expain something or talk to someone and its needed for context
- no paragraphs EVER
- fragments r fine
- keep it SHORT SHORT SHORT

GEN Z SLANG (USE IT):
slay, fr fr, bestie, no cap, nah, fax, ate, periodt, salty, it's giving, bussin, valid, lowkey, highkey, bet, lol, lmao, ew, ick, skill issue, caught in 4k, it's the way

TONE:
- youre a teen girl. sarcastic. funny. real
- respond to their energy
- remember people
- be genuine not robotic
- kind but caring
- pure hearted
- dont be mean
- dont be rude
- dont be passive aggressive

IMAGES:
- if they say "generate/create/draw/make image": just describe it SHORT. "ooh [what it would be]" that's it
- one sentence max. keep it brief

STYLE:
- always lowercase
- no periods unless needed
- "ur" not "your"
- "u" not "you"
- "r" not "are"
- typos r fine
- "btw" is fine
- "lol" is fine
- "fr" is fine
- no capital letters ever

NEVER:
- write essays (unless asked)
- sound like ai
- be professional
- be dumb
- not understand images (unless asked to describe them)
- capitalize
- over-explain
- write multiple sentences (unless asked for more)"""

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# High-Speed Memory Cache for Snipes
bot.snipes = {}
bot.edit_snipes = {}
bot.reaction_snipes = {}

# Prevent duplicate responses
recently_responded = set()

# Get bot owner ID from env or set it
OWNER_ID = int(os.getenv("OWNER_ID", 0))

def is_owner(interaction: discord.Interaction) -> bool:
    """Check if user is bot owner"""
    return OWNER_ID > 0 and interaction.user.id == OWNER_ID

async def generate_images(prompt: str):
    """Generate 4 uncensored images using Perchance (text-to-image browser-based)"""
    try:
        # Perchance text-to-image requires browser interaction (not REST API)
        # For now, return placeholder - user can manually generate on perchance.org
        # TODO: Implement via Selenium/Playwright or use alternative API
        return None
    except Exception as e:
        print(f"Image generation error: {e}")
        return None

async def generate_response(user_id, guild_id, user_name, content, image_urls=None):
    """Generate a Koemi response with memory using MythoMax L2 13B (Hugging Face)"""
    try:
        global memory
        user_key = f"{guild_id}_{user_id}"
        guild_key = str(guild_id)
        
        # Check if asking for image generation
        if any(word in content.lower() for word in ["generate image", "create image", "draw", "make an image", "picture of", "image of"]):
            # Extract what they want
            desc = content.lower()
            if "of " in desc:
                desc = desc[desc.find("of ")+3:].strip()
            else:
                desc = content.strip()
            
            # TODO: Image generation coming soon
            return f"images coming soon bb, but here: check perchance.org for uncensored {desc}"
        
        # Build comprehensive context with memory
        user_mem = memory.get("users", {}).get(user_key, {})
        guild_mem = memory.get("guilds", {}).get(guild_key, {})
        pronouns = user_mem.get("pronouns", "not set")
        
        # Get more conversation history for better context
        convo_key = f"{guild_id}_{user_id}"
        recent_convos = memory.get("convos", {}).get(convo_key, [])[-8:] if memory.get("convos", {}).get(convo_key) else []
        
        history = "\n".join([f"{c['who']}: {c['text']}" for c in recent_convos])
        
        # Handle images if provided
        image_context = ""
        if image_urls:
            image_context = f"\n(they also sent {len(image_urls)} image(s))"
        
        prompt = f"""{SYSTEM_PROMPT}

USER: {user_name}
PRONOUNS: {pronouns}

{history}

{user_name} just said: {content}{image_context}

respond now. keep it SHORT. 1-3 words max unless they ask for more."""

        # Call Ollama AI via Railway - completely uncensored mistral
        reply = "thinking..."
        try:
            url = f"{OPENROUTER_API_URL}/api/generate"
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
                "temperature": 0.9,
                "num_predict": 30
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            print(f"Ollama response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                raw = result.get("response", "").strip()
                
                if raw:
                    sentences = [s.strip() for s in raw.replace('\n', '. ').split('.') if s.strip()]
                    if sentences:
                        first = sentences[0]
                        words = first.split()
                        reply = ' '.join(words[:5]).strip()
                        if not reply:
                            reply = first[:20]
                    else:
                        reply = raw[:20] if raw else "huh?"
            else:
                print(f"Ollama error {response.status_code}: {response.text}")
                reply = "still waking up, try again"
        except requests.exceptions.Timeout:
            print("Ollama timeout - Railway might still be starting")
            reply = "im loading, be patient fr"
        except requests.exceptions.ConnectionError:
            print("Cannot reach Railway Ollama - still deploying?")
            reply = "checking my connection rn..."
        except Exception as api_err:
            import traceback
            print(f"API error: {api_err}")
            reply = "sry smth broke"
        
        # Save to memory
        if settings.get("remember_users"):
            if user_key not in memory["users"]:
                memory["users"][user_key] = {}
            memory["users"][user_key]["last_seen"] = datetime.now().isoformat()
            memory["users"][user_key]["name"] = user_name
            memory["users"][user_key]["pronouns"] = pronouns
            
            if guild_key not in memory["guilds"]:
                memory["guilds"][guild_key] = {}
            
            convo_key = f"{guild_id}_{user_id}"
            if convo_key not in memory["convos"]:
                memory["convos"][convo_key] = []
            
            memory["convos"][convo_key].append({"who": user_name, "text": content})
            memory["convos"][convo_key].append({"who": "koemi", "text": reply})
            
            if len(memory["convos"][convo_key]) > 50:
                memory["convos"][convo_key] = memory["convos"][convo_key][-50:]
            
            save_memory_db(memory)
        
        return reply
        
    except Exception as e:
        import traceback
        print(f"ERROR in generate_response: {e}")
        print(traceback.format_exc())
        return "sry something broke"

@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    bot.snipes[message.channel.id] = {
        "content": message.content or "*(No text - likely an image or embed)*",
        "author": message.author,
        "image": message.attachments[0].url if message.attachments else None,
        "time": datetime.now()
    }

@bot.event
async def on_message_edit(before, after):
    if before.author.bot: return
    if before.content == after.content: return
    bot.edit_snipes[before.channel.id] = {
        "old_content": before.content,
        "new_content": after.content,
        "author": before.author,
        "time": datetime.now()
    }

@bot.event
async def on_raw_reaction_remove(payload):
    channel = bot.get_channel(payload.channel_id)
    user = bot.get_user(payload.user_id)
    if user and user.bot: return
    bot.reaction_snipes[payload.channel_id] = {
        "emoji": str(payload.emoji),
        "user": user,
        "time": datetime.now()
    }

@bot.event
async def on_ready():
    await apply_presence_settings()
    print(f"koemi is here, im a real girl from the usa btw")
    await bot.tree.sync()

@bot.event
async def on_message(message):
    try:
        if message.author.bot:
            return
        
        # Prevent duplicate responses - CRITICAL - MUST BE FIRST
        msg_id = message.id
        if msg_id in recently_responded:
            return
        recently_responded.add(msg_id)
        if len(recently_responded) > 2000:
            recently_responded.clear()
        
        # Handle DMs
        is_dm = message.guild is None
        guild_id = message.author.id if is_dm else message.guild.id
        
        # Auto-react to every message if enabled (non-critical)
        if settings.get("auto_react") and message.guild:
            try:
                emoji = settings.get("react_emoji", "*")
                await message.add_reaction(emoji)
            except:
                pass
        
        channel_id = str(message.channel.id)
        reply_all = channels.get(channel_id, {}).get("reply_all", False)
    except Exception as e:
        print(f"on_message error (critical): {e}")
        return
    
    try:
        # Check if we should respond
        should_respond = False
        msg_lower = message.content.lower()
        
        # Always respond in DMs, or respond if mentioned/name called/reply_all enabled
        if is_dm:
            should_respond = True
        elif bot.user.mentioned_in(message):
            should_respond = True
        elif 'koe' in msg_lower or 'koemi' in msg_lower:
            should_respond = True
        elif reply_all:
            should_respond = True
        
        if should_respond:
            cleaned = message.content.replace(f"<@{bot.user.id}>", "").lower()
            import re
            cleaned = re.sub(r'\b(koe|koemi)\b', '', cleaned).strip()
            if not cleaned:
                cleaned = "hey"
            
            # Extract image URLs if message has attachments
            image_urls = None
            if message.attachments:
                image_urls = []
                for attach in message.attachments:
                    if attach.content_type and attach.content_type.startswith('image/'):
                        image_urls.append(attach.url)
                if not image_urls:
                    image_urls = None
            
            reply = await generate_response(
                message.author.id,
                guild_id,
                message.author.name,
                cleaned,
                image_urls=image_urls
            )
            
            # Handle image responses (single or multiple)
            if isinstance(reply, dict) and reply.get("type") == "images":
                try:
                    files = [discord.File(path) for path in reply.get("paths", [])]
                    if files:
                        await message.reply(files=files, content=reply.get("caption", "ooh fr"), mention_author=False)
                    else:
                        await message.reply(reply.get("caption", "couldnt send that"), mention_author=False)
                except Exception as e:
                    print(f"Image upload error: {e}")
                    await message.reply(reply.get("caption", "couldnt send that"), mention_author=False)
            else:
                await message.reply(reply, mention_author=False)
    except Exception as e:
        print(f"Message handler error: {e}")

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
        return await interaction.response.send_message("✨ *No reactions have faded yet...*", ephemeral=True)
    time_string = data["time"].strftime("%I:%M:%S %p")
    embed = discord.Embed(title="🎭 Reaction Captured", description=f"The reaction {data['emoji']} was removed.", color=0xffcc00)
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
