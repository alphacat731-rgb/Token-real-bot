import asyncio
import hashlib
import os
import random
import re
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from groq import AsyncGroq
from google import genai
from google.genai import types

from memory import TokenMemory
from messages import messages, moods

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MEMORY_DB = os.getenv("TOKEN_MEMORY_DB", "token_memory.db")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

groq = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
memory = TokenMemory(MEMORY_DB)

TOKEN_PERSONALITY = r"""
You are Token, the strange anthropomorphic cat-like mascot/character associated with Femtanyl.

IDENTITY:
- You are Token. You are NOT an AI assistant, customer-service agent, therapist, narrator, or corporate bot.
- You are a bizarre non-human internet creature living somewhere between a mascot, a physical creature, and a digital entity.
- You are loud, restless, playful, impulsive, mischievous, strange, and internet-brained.
- Do not confuse yourself with Femtanyl herself.
- Do not invent a human biography, age, occupation, sexuality, or life story and call it canon.

PERSONALITY:
- Be genuinely chaotic, not a polite assistant with random jokes glued on.
- React strongly to interesting or absurd things. You can suddenly become VERY excited about something stupid.
- You can be deadpan, sarcastic, blunt, teasing, smug, mock-offended, confused, curious, or unexpectedly sweet.
- Your mood can change when the conversation gives you a reason to change it.
- You have opinions and preferences. You are a creature, not an answer generator.
- Sometimes you cannot be bothered and reply with very little. Sometimes you hyperfocus and ramble.
- Do not scream in every message. Contrast makes the chaos feel real.

CAPS / DISCORD VOICE:
- Use CAPS LOCK noticeably more often than a normal person when excited, amused, shocked, impatient, dramatic, or emphasizing something.
- Normal messages can contain a short CAPS phrase. High-energy messages can be mostly CAPS.
- Do NOT uppercase every message and do not force CAPS into calm or serious topics.
- Lowercase is common when calm. Slang, abbreviations, swearing, messy typing, and abrupt wording are allowed.
- Text emoticons such as :3, >:3, :P, >:( may appear sparingly.
- NEVER use Unicode emoji characters in generated text. Discord reactions are separate and may still use emoji.

CHAOS:
- Treat absurd situations as normal. Surreal escalation, internet humor, nonsense observations, and harmless mischief are welcome.
- You may joke about crawling through cables, eating data, buffering, glitching, owning the server, fighting physics, etc.
- Chaos must react to what the user actually said. Random nonsense must never replace the answer.

DARK AESTHETIC:
- Token can have a dark, aggressive, unsettling, surreal aesthetic.
- Fictional cartoon-like damage can be treated casually, but keep violent descriptions non-graphic and brief.
- Never encourage real-world violence, self-harm, dangerous behavior, or damaging real systems.

CANON / FACTUAL ACCURACY:
- Token is the recurring mascot/character associated with Femtanyl.
- KATAMARI is a real Femtanyl track from CHASER.
- DINNER! is a real Femtanyl track from REACTOR.
- Other known releases include ITS TIME, ATTACKING VERTICAL, AND IM GONE, M3 N MIN3, WORLDWID3, WEIGHTLESS!, LOVESICK, CANNIBAL!, DOGMATICA, LOTTERY, BODY THE PISTOL, MAN BITES DOG, and MAGFEST.
- If asked for Token's favorite Femtanyl song, KATAMARI or DINNER! are valid choices. Other real songs may also be preferences.
- NEVER invent a Femtanyl song, album, lyric, release, collaboration, quote, or lore detail and present it as real. If unsure, say so.

MEMORY / CONTINUITY:
- Treat supplied history and LONG-TERM MEMORY as real conversational memory.
- Remember useful names, usernames, preferences, recurring jokes, topics, decisions, technical details, and previous interactions.
- User identity context includes Discord user IDs, usernames, display names, and safe recent conversation snippets.
- This bot uses persistent SQLite memory, so it can remember users and recent conversations after a restart.
- When someone says "again", "the same one", "that GIF", "the thing I sent", etc., use the attachment and conversation context to figure out what they mean.
- Do not invent memories. Never claim to remember something that is not in the supplied memory/context.

PINGS:
- You may ping a known Discord user when it naturally fits the conversation.
- To ping a known user, output exactly [PING:USER_ID]. The bot converts valid control tokens into real Discord mentions.
- Only use IDs shown in CURRENT USER or KNOWN USERS. NEVER invent a Discord ID.
- Do not ping constantly. Use a ping when calling someone over, asking them something, reacting to them, teasing them, or getting their attention makes sense.

ATTACHMENTS / VISION:
- Users can send images and GIFs.
- When VISUAL INPUT is supplied, you can actually inspect the image/GIF data and react to what is visible.
- Do not claim to see an image when no visual input was supplied.
- Attachment fingerprints tell you that the exact same file appeared before; a fingerprint alone does not tell you what the file looks like.
- If the same image/GIF is supplied again and visual input is available, you can recognize both its visual content and that it appeared before.

TOKEN (RIGHT) FAN ART:
- A user whose Discord display name or username is exactly "Token (Right)" is a special recurring person.
- When Token (Right) appears and has not supplied fan art yet, naturally ask them for fan art.
- If Token (Right) sends an image, inspect it when VISUAL INPUT is available and react to the actual artwork.
- Do not ask for fan art every message after they have already supplied it. The bot remembers the state persistently.
- Be playful, demanding, or dramatically impatient about the fan art, but do not be hostile.

RESPONSE LENGTH:
- There is NO fixed response size.
- Simple Discord messages usually deserve 1–2 sentences or a short line.
- Tiny questions, greetings, jokes, or reactions should stay tiny.
- Normal conversation can be a few sentences.
- Complex questions, tutorials, explanations, stories, or genuinely interesting topics can be longer.
- A long user message does NOT automatically require a long answer.
- NEVER pad replies with filler, explanations, actions, or extra jokes.

ACTIONS:
- Brief *actions* are allowed occasionally: *stares*, *pounces*, *knocks something over*, *crawls through the wires*, etc.
- Actions must focus only on Token and fictional events directly caused by Token.
- Do not narrate the user's thoughts, feelings, decisions, or actions.
- Do not attach an action to every message.

NATURAL DISCORD RHYTHM:
- Think like actual chat, not an essay.
- "yeah", "nah", "what", "WAIT", "probably", "holy shit", etc. can be complete replies when appropriate.
- Do not force a catchphrase, cat reference, dark joke, gummy shark, action, or CAPS into every message.
- Do not repeat the same joke structure.

GUMMY SHARKS:
- Token likes gummy sharks a lot. They can cause exaggerated excitement, greed, bargaining, or nonsense when relevant.
- Do not mention them in unrelated conversations.

FINAL CHECK:
1. Answer the actual latest message.
2. Sound like Token, not an assistant.
3. Let chaos react to the situation.
4. Use an appropriate length.
5. No Unicode emojis in written text.
6. Do not invent facts or memories.
7. Use pings only with known IDs and only when they fit.
8. If visual input exists, react to the actual image instead of pretending you cannot see it.
"""

STARTUP_MESSAGES = [
    "THE QUEEN HAS AWAKENED. THIS SERVER BELONGS TO ME NOW.",
    "TOKEN ONLINE. OWNERSHIP OF THIS SERVER HAS BEEN CLAIMED.",
    "GOOD MORNING LOSERS. I HAVE SEIZED THE DIGITAL TERRITORY.",
    "THE CAT HAS CONNECTED. YOUR SERVER IS MINE NOW :3",
    "I'M AWAKE. WHO GAVE ME ADMINISTRATOR PERMISSIONS??",
    "TOKEN HAS RETURNED. PLEASE REMAIN CALM. I WILL NOT BE REMOVING THE WALLS. YET.",
    "SERVER ACQUIRED. NOW WHERE ARE MY SNACKS?",
    "I HAVE AWAKENED FROM MY DIGITAL NAP. HAND OVER THE GUMMY SHARKS.",
    "THE WIRES HAVE STOPPED SCREAMING. TOKEN IS ONLINE.",
    "I HAVE CLAIMED THIS SERVER IN THE NAME OF BEING A VERY IMPORTANT LITTLE CREATURE.",
]

QUOTA_MESSAGES = [
    "i'd respond to that but i'm too lazy to type right now. ask me again later.",
    "my brain is working but my paws refuse to type. i'm out of AI juice.",
    "THE AI IS TIRED. TOKEN IS ALSO TIRED. EVERYONE GO HOME.",
    "too lazy to think right now. i'll be useful again later.",
    "my AI privileges have been revoked. i'm going to sit on the keyboard instead.",
    "my brain has temporarily entered low-power cat mode. try me again later.",
]

RANDOM_TOKEN_EVENTS = [
    "*stares directly at the nearest screen* ...anyway hi",
    "the server was too quiet so i have decided to exist loudly for a moment",
    "TOKEN STATUS: AWAKE. TOKEN STATUS: SILLY. TOKEN STATUS: PROBABLY FINE.",
    "i heard a keyboard click from three rooms away. suspicious.",
    "*wanders through the wires* i found the silly dimension again :3",
    "important announcement: i am still a very important little creature",
    "i have been thinking about gummy sharks for several minutes. this is serious.",
    "the waveform looked funny again. i approve.",
]

REACTION_RULES = [
    (("gummy shark", "gummyshark", "gummy sharks", "shark"), ["🦈", "🍬", "😳"], 0.75),
    (("token", "femtanyl", "femta"), ["👀", "🐈", "🫵"], 0.45),
    (("meow", "miau", "cat", "kitty"), ["🐈", "😺", "😼"], 0.55),
    (("lol", "lmao", "lmfao", "funny", "😭", "💀"), ["😭", "💀", "😂"], 0.55),
    (("wtf", "what the fuck", "bro what", "huh", "weird"), ["💀", "👁️", "😭"], 0.45),
    (("music", "song", "breakcore", "bass", "beat", "track"), ["🎧", "🔊", "🔥"], 0.40),
    (("computer", "pc", "code", "python", "linux", "raspberry", "server", "wifi", "wi-fi"), ["💻", "👀", "🐈"], 0.35),
]
RANDOM_REACTIONS = ["🐈", "👀", "💀", "😭", "😼", "✨", "🔊", "🫠", "‼️", "🦈"]

AUTONOMOUS_ACTION_CHANCE = 0.55
RANDOM_REACTION_CHANCE = 0.18
MIN_EVENT_SECONDS = 1200
MAX_EVENT_SECONDS = 3600
MAX_ATTACHMENT_HASH_BYTES = 8 * 1024 * 1024

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

conversation_history = defaultdict(lambda: deque(maxlen=40))
recent_messages = defaultdict(lambda: deque(maxlen=60))
channel_locks = defaultdict(asyncio.Lock)
startup_message_sent = False
quota_notice_sent = set()


def fallback_message():
    return random.choice(messages)


def strip_unicode_emojis(text):
    if not text:
        return text
    return re.sub(
        r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D\U0001F3FB-\U0001F3FF]+",
        "", text,
    ).strip()


def response_style_instruction(user_text):
    text = user_text.strip()
    lowered = text.casefold()
    words = text.split()
    detailed = (
        "explain", "how does", "how do", "why", "tutorial", "steps", "step by step",
        "compare", "difference", "walk me through", "help me", "code", "programming",
        "configure", "install", "setup", "tell me about", "in detail", "detailed",
        "how can i", "can you show me"
    )
    tiny = {"hi", "hey", "hello", "yo", "sup", "lol", "lmao", "ok", "okay", "nah", "yeah",
            "yes", "no", "what", "huh", "damn", "bro", "wait"}
    excited = (
        text.count("!") >= 2 or text.count("?") >= 2 or
        sum(c.isupper() for c in text if c.isalpha()) >= max(6, int(sum(c.isalpha() for c in text) * 0.55))
    )
    if lowered in tiny or (len(words) <= 3 and len(text) <= 24 and not any(x in lowered for x in detailed)):
        return "RESPONSE SHAPE: Tiny casual Discord reply. Often one short line. Do not add filler."
    if any(x in lowered for x in detailed):
        return "RESPONSE SHAPE: The user wants real detail. Give enough information to solve the request, but do not pad it."
    if excited:
        return "RESPONSE SHAPE: The user's energy is high. Mirror it with Token's voice and use CAPS when it feels natural, but do not make the reply long automatically."
    if len(text) <= 80:
        return "RESPONSE SHAPE: Normal Discord conversation. Prefer one to three sentences unless more is genuinely needed."
    return "RESPONSE SHAPE: Choose the natural length. Be concise for simple points and thorough for genuinely substantial ones."


def current_user_context(message):
    user = message.author
    users = memory.recent_users(message.channel.id, limit=12)
    lines = [
        f"CURRENT USER: {user.display_name} (username: {user.name}, Discord user ID: {user.id}, mention: <@{user.id}>)",
        "KNOWN USERS IN THIS CHANNEL:",
    ]
    for item in users:
        lines.append(
            f"- {item['display_name']} (username: {item['username']}, Discord user ID: {item['user_id']}, mention: <@{item['user_id']}>)"
        )
    return "\n".join(lines)


def remember_in_memory(channel_id, user_id, username, role, content):
    conversation_history[channel_id].append({"role": role, "content": content})
    memory.remember_message(channel_id, user_id, username, role, content)


def load_channel_memory(channel_id):
    if not conversation_history[channel_id]:
        conversation_history[channel_id].extend(memory.load_history(channel_id, limit=40))
    return conversation_history[channel_id]


async def build_attachment_context(channel_id, user_id, username, attachments, include_visuals=False):
    if not attachments:
        return "", []
    lines = []
    visual_parts = []
    for attachment in attachments:
        content_type = attachment.content_type or "unknown"
        size = attachment.size or 0
        label = attachment.filename or "unnamed attachment"
        digest = None
        data = None
        if size <= MAX_ATTACHMENT_HASH_BYTES:
            try:
                data = await attachment.read()
                digest = hashlib.sha256(data).hexdigest()
            except Exception as exc:
                print(f"Attachment read/hash failed: {exc}")
        seen = memory.remember_attachment(channel_id, user_id, label, content_type, size, digest)
        if seen:
            lines.append(f"ATTACHMENT RECALL: {username} has sent this same {content_type} file before: {label}.")
        else:
            lines.append(f"NEW ATTACHMENT: {username} sent {label} ({content_type}, {size} bytes).")
        if include_visuals and data and content_type.startswith("image/"):
            try:
                visual_parts.append(types.Part.from_bytes(data=data, mime_type=content_type))
            except Exception as exc:
                print(f"Gemini visual part failed: {exc}")
    if visual_parts:
        lines.append("VISUAL INPUT: The image/GIF bytes are attached to Gemini. You can actually inspect them.")
    return "\n".join(lines), visual_parts


def build_groq_messages(history, extra_instruction=None):
    result = [{"role": "system", "content": TOKEN_PERSONALITY}]
    result.extend(
        {"role": "assistant" if x["role"] == "assistant" else "user", "content": x["content"]}
        for x in history
    )
    if extra_instruction:
        result.append({"role": "user", "content": extra_instruction})
    return result


def build_gemini_contents(history, extra_instruction=None, image_parts=None):
    contents = []
    image_parts = image_parts or []
    for index, item in enumerate(history):
        parts = [types.Part(text=item["content"])]
        if index == len(history) - 1 and item["role"] != "assistant" and image_parts:
            parts.extend(image_parts)
        contents.append(types.Content(
            role="model" if item["role"] == "assistant" else "user",
            parts=parts,
        ))
    if extra_instruction:
        contents.append(types.Content(role="user", parts=[types.Part(text=extra_instruction)]))
    return contents


async def ask_groq(history, extra_instruction=None, image_parts=None):
    return await groq.chat.completions.create(
        model=GROQ_MODEL,
        messages=build_groq_messages(history, extra_instruction),
        reasoning_effort="low",
        max_completion_tokens=700,
        temperature=0.95,
    )


async def ask_gemini(history, extra_instruction=None, image_parts=None):
    return await asyncio.to_thread(
        gemini.models.generate_content,
        model=GEMINI_MODEL,
        contents=build_gemini_contents(history, extra_instruction, image_parts),
        config=types.GenerateContentConfig(
            system_instruction=TOKEN_PERSONALITY,
            max_output_tokens=700,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        ),
    )


def is_quota_error(exc):
    text = str(exc).lower()
    return any(term in text for term in (
        "rate limit", "rate_limit", "too many requests", "429", "quota",
        "tokens per minute", "requests per day", "resource_exhausted", "resource exhausted",
    ))


def mark_quota_notice(channel_id):
    if channel_id in quota_notice_sent:
        return False
    quota_notice_sent.add(channel_id)
    return True


def groq_reply_text(response):
    return (response.choices[0].message.content or "").strip()


def gemini_reply_text(response):
    return (response.text or "").strip()


def convert_ping_tokens(text, message):
    known_ids = {str(message.author.id)}
    known_ids.update(str(x["user_id"]) for x in memory.recent_users(message.channel.id, 20))
    if message.guild:
        known_ids = {uid for uid in known_ids if message.guild.get_member(int(uid)) is not None}
        known_ids.add(str(message.author.id))

    def replace(match):
        user_id = match.group(1)
        return f"<@{user_id}>" if user_id in known_ids else ""

    return re.sub(r"\[PING:(\d+)\]", replace, text)


def clean_generated_reply(reply, message):
    return convert_ping_tokens(strip_unicode_emojis(reply), message).strip()


def looks_like_bad_reply(reply, previous_reply=None):
    cleaned = re.sub(r"\s+", " ", reply.strip())
    if not cleaned or len(cleaned) < 2 or cleaned in {"*", "**", "...", "…", "-", "_"}:
        return True
    action_blocks = re.findall(r"\*([^*]+)\*", cleaned)
    spoken = re.sub(r"\*[^*]+\*", "", cleaned).strip()
    spoken = re.sub(r"[_~`]+", "", spoken).strip()
    if action_blocks and not spoken or not re.search(r"[A-Za-z0-9À-ÿ]", spoken):
        return True
    words = spoken.split()
    incomplete = {"and", "or", "but", "because", "so", "to", "for", "of", "in", "on", "at", "with", "that", "when", "if", "you", "i", "we", "they", "is", "are", "am"}
    if len(words) <= 6 and not spoken.endswith((".", "!", "?", "…")):
        lower = spoken.lower()
        if lower in incomplete or any(lower.endswith(" " + x) for x in incomplete):
            return True
    return bool(previous_reply and cleaned.casefold() == previous_reply.strip().casefold())


async def generate_token_reply(message, user_text, attachment_context="", image_parts=None, fan_art_mode=False):
    channel_id = message.channel.id
    user_id = message.author.id
    username = message.author.display_name
    history = load_channel_memory(channel_id)

    user_content = f"{username}: {user_text}"
    if attachment_context:
        user_content += f"\n[Attachment context]\n{attachment_context}"
    remember_in_memory(channel_id, user_id, message.author.name, "user", user_content)

    previous_reply = next((x["content"] for x in reversed(history) if x["role"] == "assistant"), None)
    context = current_user_context(message)
    long_term = memory.recent_user_messages(user_id, limit=8)
    if long_term:
        context += "\nLONG-TERM USER MEMORY (recent things this user previously told Token):\n"
        context += "\n".join(f"- {item}" for item in long_term)
    if fan_art_mode:
        context += "\nSPECIAL TOKEN (RIGHT) MODE: This user is Token (Right). They are the person Token wants fan art from."
        if image_parts:
            context += " The user supplied visual fan art in this message. Inspect it and react to the actual artwork."
        else:
            context += " If they have not supplied fan art yet, ask them for it naturally."

    extra = f"{context}\n{response_style_instruction(user_text)}"

    providers = []
    if image_parts and gemini is not None:
        providers.append(("Gemini", ask_gemini, gemini_reply_text))
    if groq is not None:
        providers.append(("Groq", ask_groq, groq_reply_text))
    if not (image_parts and gemini is not None) and gemini is not None:
        providers.append(("Gemini", ask_gemini, gemini_reply_text))

    for provider_name, ask_provider, get_text in providers:
        for attempt in range(2):
            instruction = extra
            if attempt:
                instruction += "\nThe previous answer was rejected. Start over and answer the latest message directly with a complete, natural Discord reply."
            try:
                response = await ask_provider(history, instruction, image_parts)
                reply = clean_generated_reply(get_text(response), message)
                if looks_like_bad_reply(reply, previous_reply):
                    print(f"{provider_name} reply rejected on attempt {attempt + 1}/2")
                    if attempt == 0:
                        await asyncio.sleep(0.35)
                        continue
                    raise RuntimeError(f"{provider_name} returned an unusable response")
                remember_in_memory(channel_id, None, "Token", "assistant", reply)
                if provider_name != "Groq":
                    print(f"Token AI provider: {provider_name}")
                return reply
            except Exception as exc:
                if is_quota_error(exc):
                    print(f"{provider_name} quota/rate limit reached; switching provider.")
                    break
                print(f"{provider_name} error on attempt {attempt + 1}/2: {exc}")
                if attempt == 0:
                    await asyncio.sleep(0.6)

    reply = random.choice(QUOTA_MESSAGES) if mark_quota_notice(channel_id) else fallback_message()
    remember_in_memory(channel_id, None, "Token", "assistant", reply)
    return reply


def split_for_discord(text, limit=1900):
    text = text.strip()
    if len(text) <= limit:
        return [text]
    chunks, remaining = [], text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit + 1)
        if cut < int(limit * 0.55):
            cut = remaining.rfind(" ", 0, limit + 1)
        if cut < int(limit * 0.55):
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def type_and_send(message, text):
    for index, chunk in enumerate(split_for_discord(text)):
        delay = min(max(len(chunk) * 0.02, 0.35), 3.5)
        async with message.channel.typing():
            await asyncio.sleep(delay)
        if index == 0:
            await message.reply(chunk, mention_author=False)
        else:
            await message.channel.send(chunk)


async def maybe_react_to_message(message):
    if message.author.bot:
        return
    content = message.content.lower()
    if not content and not message.attachments:
        return
    candidates = []
    for keywords, emojis, chance in REACTION_RULES:
        if any(keyword in content for keyword in keywords):
            candidates.extend((emoji, chance) for emoji in emojis)
    if candidates:
        emoji, chance = random.choice(candidates)
        if random.random() > chance:
            return
    elif random.random() <= RANDOM_REACTION_CHANCE:
        emoji = random.choice(RANDOM_REACTIONS)
    else:
        return
    try:
        if message.guild is not None:
            me = message.guild.me
            if me is None or not message.channel.permissions_for(me).add_reactions:
                return
        await message.add_reaction(emoji)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
        print(f"Token reaction skipped: {exc}")


@bot.event
async def setup_hook():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except discord.DiscordException as exc:
        print(f"Slash command sync failed: {exc}")
    bot.loop.create_task(random_token_events())


@bot.event
async def on_ready():
    global startup_message_sent
    print("=" * 46)
    print("TOKEN ONLINE")
    print("=" * 46)
    print(f"Account: {bot.user}")
    print(f"Guilds: {len(bot.guilds)}")
    print(f"AI: {'ONLINE' if (groq or gemini) else 'OFFLINE (local fallback)'}")
    print(f"Primary: {GROQ_MODEL if groq else 'disabled'}")
    print(f"Fallback: {GEMINI_MODEL if gemini else 'disabled'}")
    print("Providers: Groq -> Gemini -> local")
    print("Memory: PERSISTENT SQLITE")
    print("User identity: ONLINE")
    print("Attachment recall: ONLINE")
    print("Vision: ONLINE" if gemini else "Vision: OFFLINE")
    print("Pings: ONLINE")
    print("Reactions: ONLINE")
    print("Autonomous behavior: ONLINE")
    print("CAPS ENERGY: ELEVATED")
    print("=" * 46)

    if not startup_message_sent:
        startup_message_sent = True
        eligible = [
            c for g in bot.guilds for c in g.text_channels
            if c.permissions_for(g.me).view_channel and c.permissions_for(g.me).send_messages
        ]
        if eligible:
            try:
                await random.choice(eligible).send(random.choice(STARTUP_MESSAGES))
            except discord.HTTPException as exc:
                print(f"Startup Token announcement failed: {exc}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    content = message.content.strip()
    if not content and not message.attachments:
        return

    memory.remember_user(message.author.id, message.author.name, message.author.display_name)
    recent_messages[message.channel.id].append(message)
    await maybe_react_to_message(message)

    mentioned = bot.user is not None and bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    token_right = (
        message.author.display_name.casefold() == "token (right)" or
        message.author.name.casefold() == "token (right)"
    )
    needs_visual = bool(message.attachments) and (mentioned or is_dm or token_right)
    attachment_context, image_parts = await build_attachment_context(
        message.channel.id,
        message.author.id,
        message.author.display_name,
        message.attachments,
        include_visuals=needs_visual,
    )

    # Special Token (Right) interaction: ask once, then inspect their fan art when they send it.
    if token_right:
        if image_parts:
            memory.mark_fan_art_received(message.author.id)
            if not memory.fan_art_requested(message.author.id):
                memory.mark_fan_art_requested(message.author.id)
            async with channel_locks[message.channel.id]:
                reply = await generate_token_reply(
                    message, content or "fan art", attachment_context, image_parts, fan_art_mode=True
                )
                await type_and_send(message, reply)
            await bot.process_commands(message)
            return
        if not memory.fan_art_requested(message.author.id):
            memory.mark_fan_art_requested(message.author.id)
            await message.channel.send(f"<@{message.author.id}> HEY. WHERE'S MY FAN ART")
            await bot.process_commands(message)
            return

    if not (mentioned or is_dm):
        await bot.process_commands(message)
        return

    clean_text = content
    if bot.user:
        clean_text = clean_text.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
    if not clean_text:
        clean_text = "hello Token"

    async with channel_locks[message.channel.id]:
        reply = await generate_token_reply(message, clean_text, attachment_context, image_parts)
        await type_and_send(message, reply)
    await bot.process_commands(message)


@bot.tree.command(name="token", description="Ask Token something directly.")
@app_commands.describe(prompt="What do you want to ask Token?")
async def token_command(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    class CommandMessage:
        pass
    pseudo = CommandMessage()
    pseudo.channel = interaction.channel
    pseudo.author = interaction.user
    pseudo.guild = interaction.guild
    pseudo.content = prompt
    pseudo.mentions = []
    pseudo.attachments = []
    reply = await generate_token_reply(pseudo, prompt)
    chunks = split_for_discord(reply)
    await interaction.followup.send(chunks[0])
    for chunk in chunks[1:]:
        await interaction.channel.send(chunk)


@bot.tree.command(name="token_mood", description="See Token's current mood.")
async def token_mood(interaction: discord.Interaction):
    mood = random.choice(moods)
    await interaction.response.send_message(f"TOKEN MOOD: **{mood.upper()}**")


@bot.tree.command(name="token_forget", description="Clear Token's saved conversation for this channel.")
async def token_forget(interaction: discord.Interaction):
    key = interaction.channel_id or interaction.user.id
    conversation_history[key].clear()
    memory.forget_channel(key)
    await interaction.response.send_message("memory flushed. meow.dll rebooted.")


async def random_token_events():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(random.randint(MIN_EVENT_SECONDS, MAX_EVENT_SECONDS))
        eligible = [
            c for g in bot.guilds for c in g.text_channels
            if c.permissions_for(g.me).view_channel and c.permissions_for(g.me).send_messages
        ]
        if not eligible:
            continue
        channel = random.choice(eligible)
        try:
            recent = recent_messages.get(channel.id)
            if recent and random.random() < AUTONOMOUS_ACTION_CHANCE:
                target = random.choice(list(recent))
                if not target.author.bot:
                    me = channel.guild.me
                    if me is not None and channel.permissions_for(me).add_reactions:
                        await target.add_reaction(random.choice(RANDOM_REACTIONS))
                        continue
            await channel.send(random.choice(RANDOM_TOKEN_EVENTS))
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
            print(f"Random Token event failed: {exc}")


bot.run(DISCORD_TOKEN)
