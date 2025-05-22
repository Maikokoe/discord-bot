import os
import discord
from discord.ext import commands
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(intents=intents)

class ConfirmPurge(discord.ui.View):
    def __init__(self, ctx, messages):
        super().__init__(timeout=20)
        self.ctx = ctx
        self.messages = messages

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("You can't confirm this purge.", ephemeral=True)
            return
        await self.ctx.channel.delete_messages(self.messages)
        await interaction.response.edit_message(content=f"✅ Deleted {len(self.messages)} message(s).", embed=None, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="❌ Purge cancelled.", embed=None, view=None)
        self.stop()

@bot.slash_command(name="purge", description="Delete messages using advanced filters")
@discord.option("amount", int, description="Messages to check (max 100)")
@discord.option("user", discord.User, required=False, description="Only from this user")
@discord.option("keyword", str, required=False, description="Message contains this word")
@discord.option("botsOnly", bool, required=False, description="Only delete bot messages")
@discord.option("maxAge", int, required=False, description="Only messages newer than X minutes")
async def purge(ctx, amount, user=None, keyword=None, botsOnly=False, maxAge=None):
    if amount > 100:
        return await ctx.respond("Limit is 100 messages.", ephemeral=True)

    await ctx.defer(ephemeral=True)

    def isMatch(msg):
        if user and msg.author.id != user.id:
            return False
        if keyword and keyword.lower() not in msg.content.lower():
            return False
        if botsOnly and not msg.author.bot:
            return False
        if maxAge:
            cutoff = datetime.utcnow() - timedelta(minutes=maxAge)
            if msg.created_at < cutoff:
                return False
        return True

    history = [msg async for msg in ctx.channel.history(limit=amount)]
    targets = [msg for msg in history if isMatch(msg)]

    if not targets:
        return await ctx.respond("No matching messages found.", ephemeral=True)

    embed = discord.Embed(
        title="Confirm Purge",
        description=f"Found **{len(targets)}** message(s). Delete them?",
        color=discord.Color.red()
    )
    if user:
        embed.add_field(name="User", value=user.mention, inline=True)
    if keyword:
        embed.add_field(name="Keyword", value=keyword, inline=True)
    if botsOnly:
        embed.add_field(name="Bots Only", value="True", inline=True)
    if maxAge:
        embed.add_field(name="Max Age", value=f"{maxAge} min", inline=True)

    view = ConfirmPurge(ctx, targets)
    await ctx.respond(embed=embed, view=view, ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))
