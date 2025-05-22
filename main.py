import discord
from discord.ext import commands
from datetime import datetime, timedelta

bot = commands.Bot(intents=discord.Intents.all())

@bot.slash_command(name="purge", description="Delete messages with advanced filters")
@discord.option("amount", int, description="Number of messages to check (max 100)")
@discord.option("user", discord.User, required=False, description="Only messages from this user")
@discord.option("keyword", str, required=False, description="Messages containing this word")
@discord.option("bots_only", bool, required=False, description="Only delete bot messages")
@discord.option("max_age_minutes", int, required=False, description="Only messages within the last X minutes")
async def purge(
    ctx: discord.ApplicationContext,
    amount: int,
    user: discord.User = None,
    keyword: str = None,
    bots_only: bool = False,
    max_age_minutes: int = None,
):
    if amount > 100:
        await ctx.respond("Limit is 100 messages.", ephemeral=True)
        return

    await ctx.defer(ephemeral=True)

    def check(msg):
        if user and msg.author.id != user.id:
            return False
        if keyword and keyword.lower() not in msg.content.lower():
            return False
        if bots_only and not msg.author.bot:
            return False
        if max_age_minutes:
            age_limit = datetime.utcnow() - timedelta(minutes=max_age_minutes)
            if msg.created_at < age_limit:
                return False
        return True

    messages = [msg async for msg in ctx.channel.history(limit=amount) if check(msg)]
    if not messages:
        return await ctx.respond("No matching messages found.", ephemeral=True)

    embed = discord.Embed(
        title="Confirm Purge",
        description=f"Found **{len(messages)}** message(s) matching your criteria.\nDo you want to delete them?",
        color=discord.Color.red()
    )
    if user:
        embed.add_field(name="User", value=user.mention, inline=True)
    if keyword:
        embed.add_field(name="Keyword", value=keyword, inline=True)
    if bots_only:
        embed.add_field(name="Bots Only", value="True", inline=True)
    if max_age_minutes:
        embed.add_field(name="Max Age", value=f"{max_age_minutes} min", inline=True)

    view = discord.ui.View(timeout=20)

    @view.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_callback(interaction: discord.Interaction, button: discord.ui.Button):
        await ctx.channel.delete_messages(messages)
        await interaction.response.edit_message(content=f"✅ Deleted {len(messages)} message(s).", embed=None, view=None)

    @view.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_callback(interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Purge cancelled.", embed=None, view=None)

    await ctx.respond(embed=embed, view=view, ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))
