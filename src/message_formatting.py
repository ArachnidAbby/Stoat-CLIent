from dataclasses import dataclass
import math
import re
from typing import NamedTuple

from stoat import DMChannel, Member, Message, OwnUser, TextChannel


RED = u"\u001b[31m"
RESET = u"\u001b[0m"
BOLD = u'\u001b[1m'
BLACK_BG = u'\u001b[40m'
ORANGE = u"\u001b[38;5;208m" # used for mentions


MAGIC = 240 ** (1/3) # represents a third of the color cube for ANSI 256 color


class Color(NamedTuple):
    r: int
    g: int
    b: int

    def __hash__(self):
        # only works if r,g,b values are within their correct range 0 - 255
        return hash(self.r<<16 + self.g<<8 + self.b)

@dataclass
class TermMessageSection:
    text: str
    foreground: Color
    background: Color = Color(0, 0, 0)
    bold: bool = False
    italic: bool = False
    underline: bool = False

@dataclass
class TermMessage():
    sections: list[TermMessageSection]


def convert_to_ansi(r, g, b):
    r_percent = r/256
    g_percent = g/256
    b_percent = b/256

    cube_width = MAGIC

    ansi_r = r_percent * cube_width # goes 0 - cube_width
    ansi_g = max(g_percent * cube_width - 1, 0)
    ansi_b = b_percent * cube_width

    final_code = min(16 + math.ceil(ansi_g + (ansi_b * cube_width) + (ansi_r * cube_width**2)), 256)

    return f"\u001b[38;5;{final_code}m"

def convert_role_color_to_ansi(color: str):
    if not color.startswith("#") or not len(color) == 7:
        return RESET
    r, g, b = (int("0x" + str(color[i*2 + 1: i*2+3]), base=0) for i in range(3))
    return convert_to_ansi(r, g, b)


def replace_mentions(message: Message, me: OwnUser) -> str:
    if message.server is None:
        return message.content
    output = message.content

    # user mentions
    while match:=re.search(r"\<@(.{26})\>", output):
        id = match.group()[2: -1]

        user = None
        for mention in message.mentions_as_members:
            if mention.id == id:
                user = mention

        if user is not None:
            output = output.replace(match.group(), f"{ORANGE}@{user.display_name or user.name}{RESET}")
            continue

        output = output.replace(match.group(), f"<{ORANGE}@{id}{RESET}>")

    # Role mentions
    while match:=re.search(r"\<%(.{26})\>", output):
        id = match.group()[2: -1]

        role = None
        for mention in message.role_mentions:
            if mention.id == id:
                role = mention

        if role is not None:
            output = output.replace(match.group(), f"{convert_role_color_to_ansi(role.color or "#FFFFFF")}@{role.name}{RESET}")
            continue

        output = output.replace(match.group(), f"<{ORANGE}%{id}{RESET}>")

    # Channel mentions
    while match:=re.search(r"\<#(.{26})\>", output):
        id = match.group()[2: -1]

        channel = None
        for server_channel in message.server.channels:
            if server_channel.id == id:
                channel = server_channel

        if channel is not None:
            output = output.replace(match.group(), f"{BOLD}#{channel.name}{RESET}")
            continue

        output = output.replace(match.group(), f"<{BOLD}#{id}{RESET}>")

    return output

def format_server_message(me: OwnUser, message: Message, compact_mode=True) -> str:
    if not isinstance(message.author, Member):
        return ""

    if message.server is None:
        return ""

    top_role = message.author.top_role

    if top_role is None or top_role.color is None:
        user_role_color = RESET
    else:
        user_role_color = convert_role_color_to_ansi(top_role.color)

    if message.channel is None or not isinstance(message.channel, TextChannel):
        channel_prefix = ""
        if isinstance(message.channel, DMChannel):
            channel_prefix = f"@{message.channel.recipient.display_name} "
    else:
        channel_prefix = f"#{message.server.name}.{message.channel.name} "

    mentioned = any(mention.id == me.id for mention in message.mentions)

    return f"{ORANGE if mentioned else RESET}{channel_prefix}[{message.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")}][{user_role_color}{message.author.display_name or message.author.name}{ORANGE if mentioned else RESET}]:{" " if compact_mode else "\n"}{replace_mentions(message, me)} "


