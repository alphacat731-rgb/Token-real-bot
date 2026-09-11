"""Clyde entry point.

The full Discord helper implementation lives in clyde.py.
This wrapper keeps the normal `python3 bot.py` launch command.
"""

from clyde import DISCORD_TOKEN, bot


if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")


bot.run(DISCORD_TOKEN)
