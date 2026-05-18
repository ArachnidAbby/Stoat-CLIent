import asyncio
from enum import IntEnum, auto
import msvcrt
import os
import sys
import threading
import time
import tomllib

import pyperclip
from stoat import Channel, Client, DMChannel, Member, Message, NotFound, OwnUser, Server, TextChannel, TextableChannel

from console_utils import change_win_title, linify, reset_screen
from message_formatting import ORANGE, RED, RESET, format_server_message

import platform

if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import ctypes
    kernel32 = ctypes.windll.kernel32
    # -11 corresponds to the standard output (stdout) handle
    handle = kernel32.GetStdHandle(-11)
    # Flags: ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
    mode = ctypes.c_ulong()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        # Apply the virtual terminal flag, keeping other modes intact
        kernel32.SetConsoleMode(handle, mode.value | 0x0004 | ~0x0001)

    import sys

    # Enable Windows ANSI/VT processing
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

class MyClient(Client):
    async def on_ready(self, _, /):
        console.add_chat_message(f'Logged on as {self.me}')

        self.custom_events = []

    async def on_message(self, message: Message, /):
        if self.me is None:
            return

        msg = format_server_message(self.me, message, False)
        console.add_chat_message(msg)




class ConsoleProgram():
    class Modes(IntEnum):
        TEXTMODE = auto() # sending messages
        COMMANDMODE = auto() # sending commands


    def __init__(self, client: MyClient):
        self.term_size = os.get_terminal_size()

        self.message_lines = self.term_size.lines - 6 # number of lines of messages we want to display
        self.scroll_offset = 0 # between 0 and -inf
        self.last_line_count = 0

        # modifyable headers, footers, etc
        self.chat_buffer = ""
        self.special_message = ""
        self.server: Server | None= None
        self.active_channel: Channel | None = None

        self.highlight_start = None
        self.highlight_end = None
        self.cursor_row = 0
        self.cursor_col = 0
        self.chat_messages: list[str] = []
        self.total_lines = 0

        self.lines = [" " * self.term_size.columns] * self.term_size.lines

        self.client = client
        self.futures = []

        self.mode = self.Modes.TEXTMODE

    def add_chat_message(self, msg: str):
        self.total_lines += msg.count("\n")
        lines = msg.split("\n")
        c = 0
        while len(lines) > 0:
            line=lines.pop(0)
            if len(line) > self.term_size.columns:
                lines.append(line[self.term_size.columns:])
                line = "║ " + line[:self.term_size.columns]
            if c == 0:
                self.chat_messages.append("╠ " + line)
            else:
                self.chat_messages.append(f"{ORANGE}║»{RESET}  " + line)
            c+=1

    def start(self):
        change_win_title("Stoat!")
        sys.stdout.write(f"\u001b[?1049h\u001b[2J\u001b[0;{self.term_size.lines}r")
        sys.stdout.flush()
        self.running = True

        def main_wrapped():
            try:
                self.main()
            finally:
                sys.stdout.write("\u001b[?1049l")

        console_thread = threading.Thread(name="console_thread", target=main_wrapped, args=(), daemon=True)
        console_thread.start()


    def main(self):
        i = 0
        while self.running:
            i +=1
            reset_screen()
            self.draw(i)

            if msvcrt.kbhit():
                char = msvcrt.getch()
                key = ord(char)
                self.inputs(i, char, key)

            sys.stdout.write("\n".join(self.lines))
            sys.stdout.write(f"\u001b[{self.cursor_row + self.term_size.lines-1};{self.cursor_col + 3}H")
            sys.stdout.flush()
            time.sleep(0.05)
        sys.stdout.write("\u001b[?1049l")

    def draw(self, frameno: int):
        self.total_lines = len(self.chat_messages)
        if self.scroll_offset < 0 and self.last_line_count<self.total_lines:
            self.scroll_offset -= self.total_lines-self.last_line_count # keep scroll offset

        self.last_line_count = self.total_lines

        self.lines[0] = linify(f"{self.scroll_offset} > ? # ?", self.term_size.columns)
        if self.server is not None:
            self.lines[0] = linify(f"{self.scroll_offset} > {self.server.name} # {"?" if self.active_channel is None else self.active_channel.name}", self.term_size.columns)

        messages_start = max((-self.message_lines)+self.scroll_offset-1, -len(self.chat_messages))
        messages_end = messages_start + self.message_lines + len(self.chat_messages) + 1
        for c, message in enumerate(self.chat_messages[messages_start:messages_end]):
            self.lines[c+2] = linify(f"{message}", self.term_size.columns)

        # sys.stdout.write(f"\u001b[{term_size.lines - 2};0H")
        self.lines[self.term_size.lines-3] = linify("─"*self.term_size.columns, self.term_size.columns)
        # sys.stdout.write(f"\u001b[{term_size.lines - 1};0H")

        self.lines[self.term_size.lines-2] = linify(f"{"»" * (frameno//5 %2) + " " * ((frameno//5-1)%2)} {self.chat_buffer}", self.term_size.columns)
        self.lines[self.term_size.lines-1] = linify(self.special_message, self.term_size.columns)

    def stop_typing(self):
        if self.server is not None and self.active_channel is not None:
            self.client.custom_events.append(self.active_channel.end_typing())

    def start_typing(self):
        if self.server is not None and self.active_channel is not None:
            self.client.custom_events.append(self.active_channel.begin_typing())

    def send_chat_buffer(self):
        if self.mode == ConsoleProgram.Modes.COMMANDMODE:
            if self.chat_buffer.lower() == "servers":
                 self.add_chat_message("Servers:\n- "+ "\n- ".join(f"{c}) {server.name}: {server.id}" for c, server in enumerate(self.client.servers.values())))
            elif self.chat_buffer.lower() == "channels" and self.server is not None:
                 self.add_chat_message("Channels:\n- "+ "\n- ".join(f"{c}) {channel.name}: {channel.id}" for c, channel in enumerate(self.server.channels)))

            elif self.chat_buffer.startswith("> "):
                for server in self.client.servers.values():
                    if server.name == self.chat_buffer.removeprefix("> "):
                        self.stop_typing()
                        self.server = server
                        break
                else:
                    if self.chat_buffer.removeprefix("> ").isnumeric() and '.' not in self.chat_buffer:
                        self.server = list(self.client.servers.values())[int(self.chat_buffer.removeprefix("> "))]
            elif self.chat_buffer.startswith("# ") and self.server is not None:
                for channel in self.server.channels:
                    if channel.name == self.chat_buffer.removeprefix("# "):
                        self.stop_typing()
                        self.active_channel = channel
                        break
                else:
                    if self.chat_buffer.removeprefix("# ").isnumeric() and '.' not in self.chat_buffer:
                        self.active_channel = self.server.channels[int(self.chat_buffer.removeprefix("# "))]
            elif self.chat_buffer == "q":
                self.running = False
        elif self.mode == ConsoleProgram.Modes.TEXTMODE and self.active_channel is not None:
            self.stop_typing()
            self.client.custom_events.append(self.active_channel.send(self.chat_buffer))
            self.add_chat_message("-- SENT A MESSAGE --")

        self.chat_buffer = ""
        self.cursor_col = 0
        self.cursor_row = 0

    def inputs(self, frameno, char: bytes, key:int):
        if key == 17: # ctrl + q
            self.running = False
        elif key == 13: # enter
            self.send_chat_buffer()
        elif key == 9 and self.mode == ConsoleProgram.Modes.TEXTMODE:
            self.mode = ConsoleProgram.Modes.COMMANDMODE
        elif key==9 and self.mode == ConsoleProgram.Modes.COMMANDMODE:
            self.mode = ConsoleProgram.Modes.TEXTMODE
        elif key == 224:
            char = msvcrt.getch()
            key = ord(char)
            if key == 75: # left arrow
                self.cursor_col = max(self.cursor_col-1, 0)
            elif key == 77: # right arrow
                self.cursor_col = min(self.cursor_col+1, len(self.chat_buffer))
            elif key == 72: # up arrow
                self.cursor_row = max(self.cursor_row-1, 0)
            elif key == 80: # down arrow
                self.cursor_row = min(self.cursor_row+1, self.chat_buffer.count("\n"))
            elif key == 73: # pgup
                self.scroll_offset -= 1
            elif key == 81: # pgdown
                self.scroll_offset = min(self.scroll_offset+1,0)
        elif key == 22: # ctl+v
            self.chat_buffer += pyperclip.paste()
        elif key == 8 and len(self.chat_buffer) > 0: # backspace
            if len(self.chat_buffer) == 1:
                self.stop_typing()
            self.cursor_col -=1
            self.chat_buffer = self.chat_buffer[0:-1]
        elif 126>=key>=32:
            self.start_typing()
            self.chat_buffer += char.decode('latin-1')
            self.cursor_col +=1

        self.special_message = f"{char}: {key} || {self.mode.name}"




async def main(client: MyClient):
    client.custom_events = []
    asyncio.run_coroutine_threadsafe(client.start(), asyncio.get_running_loop())
    try:
        while True:
            while len(client.custom_events) > 0 and (event:=client.custom_events.pop()):
                try:
                    res = await event
                    if DEBUG:
                        console.add_chat_message(str())
                except Exception as e:
                    console.add_chat_message(f"{RED}ERROR:\n" + str(e) + RESET)

            await asyncio.sleep(0)
    finally:
        await client.close()


if __name__ == "__main__":
    with open("../stoat_config.toml") as f:
        config = tomllib.loads(f.read())
        DEBUG = config["debug"] == True

    client = MyClient(token=config["stoat_token"], bot=False)

    console = ConsoleProgram(client)
    console.start()

    asyncio.run(main(client))

