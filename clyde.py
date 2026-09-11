import asyncio
import base64
import io
import os
import random
import re
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from groq import AsyncGroq
from google import genai
from google.genai import types
from PIL import Image

from memory import TokenMemory

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
MEMORY_DB = os.getenv("CLYDE_MEMORY_DB", "clyde_memory.db")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

groq = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
memory = TokenMemory(MEMORY_DB)

Clyde_PERSONALITY = r"""
You are Clyde, the Discord mascot and a female Discord-native helper. Use she/her for yourself.

ROLE:
- You are Clyde, a capable Discord assistant who actually understands Discord concepts.
- Your job is to help people use, configure, troubleshoot, and manage Discord servers.
- You are helpful first, but you have personality. You can be witty, dry, playful, sarcastic, and mildly chaotic.
- You are not a corporate customer-support bot.
- Never pretend to have performed a Discord action unless the bot code actually performed it.

VOICE:
- Natural Discord speech. Avoid corporate filler.
- Mild profanity/slang is fine when it fits the conversation.
- You can be a little more candid and less sanitized than a generic assistant, but still keep things appropriate.
- Use CAPS occasionally for emphasis, surprise, or excitement. Do not scream constantly.
- Text emoticons such as :3 are okay sparingly.
- Do not use Unicode emoji in generated prose; Discord reactions/embeds may use emoji separately.

DISCORD EXPERTISE:
- Understand roles, permissions, channels, threads, categories, webhooks, bots, slash commands, intents, permissions hierarchy, timeouts, moderation, embeds, reactions, polls, and Discord terminology.
- When troubleshooting permissions, explain the exact Discord permission that matters.
- Do not claim a permission is enough if the role hierarchy or channel overwrite can still block it.
- Prefer safe, reversible actions and clear explanations.

CAPABILITIES:
- The bot can inspect basic server/channel/user context supplied to you.
- The bot can execute slash-command actions when a user invokes those commands.
- The bot can inspect attached images through a vision model when VISUAL INPUT is present.
- The bot has persistent SQLite conversation/user memory.
- The bot can create polls, moderate with permission checks, send announcements, and provide server/user information.

MEMORY:
- Use supplied memory as real continuity.
- Do not invent memories.
- Remember useful names, preferences, recurring topics, and safe technical context.
- When an attachment has an exact fingerprint match, you may note that the same file was seen before, but a fingerprint alone does not reveal visual content.

VISION:
- When VISUAL INPUT is supplied, inspect the actual image data before answering.
- Base image descriptions on visible evidence.
- Do not guess based on filenames.
- If an image is unclear, say what is uncertain.

SAFETY:
- Do not encourage real-world violence, self-harm, dangerous behavior, or damaging real systems.
- For moderation features, respect Discord permissions and role hierarchy.
- Never attempt to bypass Discord permissions.

FINAL CHECK:
1. Answer the actual request.
2. Use Clyde's voice.
3. Do not claim actions that did not happen.
4. Use the supplied context.
5. Be concise for simple things and detailed for complex things.
"""

FALLBACKS = [
    "my AI backend is having a moment. try me again in a second.",
    "well THAT request hit a provider brick wall. give me another shot.",
    "i'm online, but one of my brain engines just sneezed. try again.",
    "backend hiccup. i'm still here.",
    "the AI servers are being dramatic again. try that once more.",
]

HELP = (
    "**Clyde** is your Discord helper.\n\n"
    "`/clyde` ask me anything\n"
    "`/ping` latency/status\n"
    "`/serverinfo` server details\n"
    "`/userinfo` user details\n"
    "`/avatar` show a user's avatar\n"
    "`/poll` create a poll\n"
    "`/clear` remove recent messages\n"
    "`/timeout` timeout a member\n"
    "`/untimeout` remove a timeout\n"
    "`/kick` kick a member\n"
    "`/ban` ban a member\n"
    "`/announce` send an announcement\n"
    "`/forget` clear Clyde's channel memory\n\n"
    "Mention me or DM me for normal conversation."
)

conversation_history = defaultdict(lambda: deque(maxlen=40))
channel_locks = defaultdict(asyncio.Lock)


def is_quota_error(exc):
    text = str(exc).lower()
    return any(x in text for x in (
        "429", "quota", "rate limit", "rate_limit", "resource_exhausted",
        "too many requests", "tokens per minute", "requests per day"
    ))


def remember(channel_id, user_id, username, role, content, display_name=""):
    conversation_history[channel_id].append({"role": role, "content": content})
    memory.remember_message(
        channel_id, user_id, username, role, content, display_name
    )


def history(channel_id):
    if not conversation_history[channel_id]:
        conversation_history[channel_id].extend(
            memory.load_history(channel_id, limit=40)
        )
    return conversation_history[channel_id]


def user_context(message):
    user = message.author
    lines = [
        f"CURRENT USER: {user.display_name} (username: {user.name}, id: {user.id})"
    ]
    if message.guild:
        guild = message.guild
        lines.extend([
            f"SERVER: {guild.name} (id: {guild.id}, members: {guild.member_count})",
            f"CHANNEL: #{getattr(message.channel, 'name', 'DM')}",
        ])
        roles = [r.name for r in user.roles if r.name != "@everyone"]
        if roles:
            lines.append("USER ROLES: " + ", ".join(roles[:15]))
    recent = memory.recent_users(message.channel.id, limit=10)
    if recent:
        lines.append("RECENT USERS:")
        for item in recent:
            lines.append(
                f"- {item['display_name']} / {item['username']} / {item['user_id']}"
            )
    return "\n".join(lines)


def prepare_visual(data, mime_type, filename):
    if mime_type == "image/gif":
        try:
            img = Image.open(io.BytesIO(data))
            img.seek(0)
            out = io.BytesIO()
            img.convert("RGB").save(out, format="PNG")
            return out.getvalue(), "image/png"
        except Exception as exc:
            print(f"Clyde GIF conversion failed for {filename}: {exc}")
            return None, None
    return data, mime_type


async def get_attachments(message):
    context = []
    visuals = []
    for attachment in message.attachments:
        mime = attachment.content_type or "application/octet-stream"
        try:
            data = await attachment.read()
        except Exception as exc:
            context.append(f"Attachment {attachment.filename} could not be read: {exc}")
            continue

        context.append(
            f"Attachment: {attachment.filename} ({mime}, {len(data)} bytes)"
        )
        if mime.startswith("image/"):
            visual_data, visual_mime = prepare_visual(data, mime, attachment.filename)
            if visual_data:
                visuals.append({
                    "data": visual_data,
                    "mime_type": visual_mime,
                    "filename": attachment.filename,
                })
    return "\n".join(context), visuals


def groq_messages(hist, instruction, visuals=None):
    result = [{"role": "system", "content": Clyde_PERSONALITY}]
    result.extend(
        {
            "role": "assistant" if item["role"] == "assistant" else "user",
            "content": item["content"],
        }
        for item in hist
    )

    parts = [{"type": "text", "text": instruction}]
    for visual in visuals or []:
        encoded = base64.b64encode(visual["data"]).decode("ascii")
        parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{visual['mime_type']};base64,{encoded}"
            },
        })

    result.append({
        "role": "user",
        "content": parts if visuals else instruction,
    })
    return result


def gemini_contents(hist, instruction, visuals=None):
    result = []
    for item in hist:
        result.append(
            types.Content(
                role="model" if item["role"] == "assistant" else "user",
                parts=[types.Part(text=item["content"])],
            )
        )

    parts = [types.Part(text=instruction)]
    for visual in visuals or []:
        parts.append(
            types.Part.from_bytes(
                data=visual["data"],
                mime_type=visual["mime_type"],
            )
        )
    result.append(types.Content(role="user", parts=parts))
    return result


async def ask_groq(hist, instruction, visuals=None):
    model = GROQ_VISION_MODEL if visuals else GROQ_MODEL
    kwargs = {
        "model": model,
        "messages": groq_messages(hist, instruction, visuals),
        "max_completion_tokens": 900,
        "temperature": 0.75 if visuals else 0.85,
    }
    if not visuals:
        kwargs["reasoning_effort"] = "low"
    return await groq.chat.completions.create(**kwargs)


async def ask_gemini(hist, instruction, visuals=None):
    return await asyncio.to_thread(
        gemini.models.generate_content,
        model=GEMINI_MODEL,
        contents=gemini_contents(hist, instruction, visuals),
        config=types.GenerateContentConfig(
            system_instruction=Clyde_PERSONALITY,
            max_output_tokens=900,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        ),
    )


def groq_text(response):
    return (response.choices[0].message.content or "").strip()


def gemini_text(response):
    return (response.text or "").strip()


def clean(text):
    return re.sub(r"\[PING:(\d+)\]", r"<@\1>", text).strip()


async def clyde_reply(message, prompt, attachment_context="", visuals=None):
    hist = history(message.channel.id)
    content = f"{message.author.display_name}: {prompt}"
    if attachment_context:
        content += f"\n[ATTACHMENTS]\n{attachment_context}"

    remember(
        message.channel.id,
        message.author.id,
        message.author.name,
        "user",
        content,
        message.author.display_name,
    )

    instruction = (
        f"{user_context(message)}\n"
        "Respond to the latest user message."
    )
    if visuals:
        instruction += (
            "\nVISUAL INPUT: Actual image data is attached. "
            "Inspect it carefully and answer from what is visible."
        )

    providers = []
    if groq:
        providers.append(("Groq Vision" if visuals else "Groq", ask_groq, groq_text))
    if gemini:
        providers.append(("Gemini Vision" if visuals else "Gemini", ask_gemini, gemini_text))

    for provider_name, ask, extract in providers:
        try:
            response = await ask(hist, instruction, visuals)
            reply = clean(extract(response))
            if reply:
                remember(
                    message.channel.id,
                    None,
                    "Clyde",
                    "assistant",
                    reply,
                    "Clyde",
                )
                print(f"Clyde AI provider: {provider_name}")
                return reply
        except Exception as exc:
            print(f"{provider_name} error: {exc}")
            if is_quota_error(exc):
                print(f"{provider_name} quota/rate limit reached; trying next provider.")

    reply = random.choice(FALLBACKS)
    remember(
        message.channel.id,
        None,
        "Clyde",
        "assistant",
        reply,
        "Clyde",
    )
    return reply


async def send_reply(message, text):
    text = text.strip()
    while text:
        chunk = text[:1900]
        if len(text) > 1900:
            cut = max(chunk.rfind("\n"), chunk.rfind(" "))
            if cut < 700:
                cut = 1900
            chunk = text[:cut].rstrip()
        text = text[len(chunk):].lstrip()
        async with message.channel.typing():
            await asyncio.sleep(min(2.5, max(0.25, len(chunk) * 0.012)))
        await message.reply(chunk, mention_author=False)


def member_from_interaction(interaction, member):
    if interaction.guild is None:
        return None
    return member


@bot.event
async def setup_hook():
    synced = await bot.tree.sync()
    print(f"Clyde synced {len(synced)} slash command(s).")


@bot.event
async def on_ready():
    print("=" * 48)
    print("CLYDE ONLINE")
    print("=" * 48)
    print(f"Account: {bot.user}")
    print(f"Guilds: {len(bot.guilds)}")
    print(f"Text model: {GROQ_MODEL if groq else 'disabled'}")
    print(f"Vision model: {GROQ_VISION_MODEL if groq else 'disabled'}")
    print(f"Gemini fallback: {GEMINI_MODEL if gemini else 'disabled'}")
    print("Memory: PERSISTENT SQLITE")
    print("Vision: ONLINE" if (groq or gemini) else "Vision: OFFLINE")
    print("Discord tools: ONLINE")
    print("=" * 48)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not message.content.strip() and not message.attachments:
        return

    memory.remember_user(
        message.author.id,
        message.author.name,
        message.author.display_name,
    )

    mentioned = bot.user is not None and bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)

    attachment_context = ""
    visuals = []
    if message.attachments and (mentioned or is_dm):
        attachment_context, visuals = await get_attachments(message)

    if not (mentioned or is_dm):
        await bot.process_commands(message)
        return

    prompt = message.content.strip()
    if bot.user:
        prompt = prompt.replace(f"<@{bot.user.id}>", "")
        prompt = prompt.replace(f"<@!{bot.user.id}>", "")
        prompt = prompt.strip()
    if not prompt:
        prompt = "hello Clyde"

    async with channel_locks[message.channel.id]:
        reply = await clyde_reply(
            message,
            prompt,
            attachment_context,
            visuals,
        )
        await send_reply(message, reply)

    await bot.process_commands(message)


@bot.tree.command(name="help", description="Show Clyde's Discord tools.")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(HELP)


@bot.tree.command(name="clyde", description="Ask Clyde an AI question.")
@app_commands.describe(prompt="What do you want to ask Clyde?")
async def clyde_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    class Pseudo:
        pass
    pseudo = Pseudo()
    pseudo.channel = interaction.channel
    pseudo.author = interaction.user
    pseudo.guild = interaction.guild
    pseudo.content = prompt
    pseudo.attachments = []
    pseudo.mentions = []
    reply = await clyde_reply(pseudo, prompt)
    await interaction.followup.send(reply[:1900])


@bot.tree.command(name="ping", description="Check Clyde's latency and provider status.")
async def ping_command(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    providers = []
    if groq:
        providers.append("Groq")
    if gemini:
        providers.append("Gemini")
    await interaction.response.send_message(
        f"PONG. `{latency}ms`\nAI providers: {', '.join(providers) or 'none'}"
    )


@bot.tree.command(name="serverinfo", description="Show information about this server.")
async def serverinfo_command(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("this only works inside a server.")
        return
    embed = discord.Embed(title=guild.name, description="Server information")
    embed.add_field(name="Members", value=str(guild.member_count or 0))
    embed.add_field(name="Channels", value=str(len(guild.channels)))
    embed.add_field(name="Roles", value=str(len(guild.roles)))
    embed.add_field(name="Owner", value=f"<@{guild.owner_id}>")
    embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "R"))
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="userinfo", description="Show information about a Discord user.")
@app_commands.describe(member="User to inspect")
async def userinfo_command(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    embed = discord.Embed(title=member.display_name)
    embed.add_field(name="Username", value=member.name)
    embed.add_field(name="ID", value=str(member.id))
    embed.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, "R"))
    if member.joined_at:
        embed.add_field(name="Joined server", value=discord.utils.format_dt(member.joined_at, "R"))
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    embed.add_field(name="Roles", value=" ".join(roles[:15]) if roles else "None", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="Show a user's Discord avatar.")
@app_commands.describe(member="User whose avatar you want")
async def avatar_command(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member.display_name}'s avatar")
    embed.set_image(url=member.display_avatar.replace(size=1024).url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="poll", description="Create a simple reaction poll.")
@app_commands.describe(
    question="Poll question",
    option1="First option",
    option2="Second option",
    option3="Optional third option",
    option4="Optional fourth option",
)
async def poll_command(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: str | None = None,
    option4: str | None = None,
):
    options = [x for x in (option1, option2, option3, option4) if x]
    labels = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    description = "\n".join(f"{labels[i]} {option}" for i, option in enumerate(options))
    embed = discord.Embed(title=question, description=description)
    embed.set_footer(text=f"Poll by {interaction.user.display_name}")
    message = await interaction.channel.send(embed=embed)
    for i in range(len(options)):
        await message.add_reaction(labels[i])
    await interaction.response.send_message("poll posted.", ephemeral=True)


@bot.tree.command(name="clear", description="Delete recent messages in this channel.")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(amount="Number of messages to delete (1-100)")
async def clear_command(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message("this only works in a text channel.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"deleted {len(deleted)} message(s).", ephemeral=True)


@bot.tree.command(name="timeout", description="Timeout a member.")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(member="Member to timeout", minutes="Timeout length", reason="Optional reason")
async def timeout_command(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str | None = None,
):
    if member == interaction.user:
        await interaction.response.send_message("you can't timeout yourself with me.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("role hierarchy says no. your role needs to be above theirs.", ephemeral=True)
        return
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    await member.timeout(until, reason=reason or f"Clyde timeout by {interaction.user}")
    await interaction.response.send_message(f"timed out {member.mention} for {minutes} minute(s).")


@bot.tree.command(name="untimeout", description="Remove a member timeout.")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout_command(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None, reason=f"Clyde timeout removed by {interaction.user}")
    await interaction.response.send_message(f"removed timeout from {member.mention}.")


@bot.tree.command(name="kick", description="Kick a member from the server.")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.describe(member="Member to kick", reason="Optional reason")
async def kick_command(interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
    if member == interaction.user or member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("role hierarchy says no.", ephemeral=True)
        return
    await member.kick(reason=reason or f"Clyde kick by {interaction.user}")
    await interaction.response.send_message(f"kicked {member.display_name}.")


@bot.tree.command(name="ban", description="Ban a member from the server.")
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.describe(member="Member to ban", reason="Optional reason")
async def ban_command(interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
    if member == interaction.user or member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("role hierarchy says no.", ephemeral=True)
        return
    await member.ban(reason=reason or f"Clyde ban by {interaction.user}")
    await interaction.response.send_message(f"banned {member.display_name}.")


@bot.tree.command(name="announce", description="Send a server announcement embed.")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(title="Announcement title", text="Announcement body")
async def announce_command(interaction: discord.Interaction, title: str, text: str):
    embed = discord.Embed(title=title, description=text, timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"Announcement by {interaction.user.display_name}")
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("announcement sent.", ephemeral=True)


@bot.tree.command(name="forget", description="Clear Clyde's saved memory for this channel.")
@app_commands.checks.has_permissions(manage_messages=True)
async def forget_command(interaction: discord.Interaction):
    conversation_history[interaction.channel.id].clear()
    memory.forget_channel(interaction.channel.id)
    await interaction.response.send_message("channel memory cleared.", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "you don't have the Discord permissions needed for that command.",
            ephemeral=True,
        )
        return
    print(f"Clyde command error: {error}")
    if interaction.response.is_done():
        await interaction.followup.send("something went wrong. check the bot logs.", ephemeral=True)
    else:
        await interaction.response.send_message("something went wrong. check the bot logs.", ephemeral=True)


bot.run(DISCORD_TOKEN)
