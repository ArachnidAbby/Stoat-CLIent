import asyncio
from enum import IntEnum, auto
import os
import sys
import threading
import time
import tomllib

from comprehensiveconfig import ConfigSpec, TomlWriter, spec
import pyperclip
from stoat import (
    Channel,
    Client,
    DMChannel,
    Member,
    Message,
    NotFound,
    OwnUser,
    Server,
    TextChannel,
    TextableChannel,
)

from console_utils import (
    BACKSPACE,
    DOWN_ARROW,
    ENTER,
    LEFT_ARROW,
    PG_DOWN,
    PG_UP,
    REVERSE,
    RIGHT_ARROW,
    UP_ARROW,
    arrow_pressed,
    break_and_wrap_text,
    change_win_title,
    enter_alternative_mode,
    enter_standard_mode,
    has_char,
    horiz_line,
    linify,
    next_char,
    reset_screen,
    ORANGE,
    RED,
    RESET,
    setup_terminal,
    visible_len,
)
from message_formatting import format_server_message

import platform

if platform.system() == "Windows":
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
        console.add_chat_message(f"Logged on as {self.me}")

        self.custom_events = []

    async def on_message(self, message: Message, /):
        if self.me is None:
            return

        msg = format_server_message(self.me, message, AppConfig.compact_mode)
        console.add_chat_message(msg)


class ConsoleProgram:
    class Modes(IntEnum):
        TEXTMODE = auto()  # sending messages
        COMMANDMODE = auto()  # sending commands

    def __init__(self, client: MyClient):
        self.resize()
        self.message_lines = (
            self.term_size.lines - 6
        )  # number of lines of messages we want to display
        self.scroll_offset = 0  # between 0 and -inf
        self.last_line_count = 0

        # modifyable headers, footers, etc
        self.chat_buffer = ""
        self.special_message = ""
        self.server: Server | None = None
        self.active_channel: Channel | None = None

        self.highlight_start = None
        self.highlight_end = None
        self.cursor_row = 0
        self.cursor_col = 0
        self.chat_messages: list[str] = []
        self.total_lines = 0

        self.client = client
        self.futures = []
        self.text_buffer_scroll = 0  # starts at beginning of buffer

        self.mode = self.Modes.TEXTMODE

    def add_chat_message(self, msg: str):
        self.total_lines += msg.count("\n")
        lines = msg.split("\n")
        c = 0
        while len(lines) > 0:
            line = lines.pop(0)
            if len(line) > self.term_size.columns - 4:
                lines.append(line[self.term_size.columns :])
                line = line[: self.term_size.columns]
            if c == 0:
                self.chat_messages.append("╠ " + line)
            else:
                self.chat_messages.append(f"{ORANGE}║»{RESET}  " + line)
            c += 1

    def start(self):
        setup_terminal()
        change_win_title("Stoat!")
        enter_alternative_mode(self.term_size)
        self.running = True

        def main_wrapped():
            try:
                self.main()
            finally:
                enter_standard_mode()

        console_thread = threading.Thread(
            name="console_thread", target=main_wrapped, args=(), daemon=True
        )
        console_thread.start()

    def main(self):
        i = 0
        while self.running:
            i += 1
            reset_screen()
            self.draw(i)

            if has_char():
                char = next_char()
                key = ord(char)
                self.inputs(i, char, key)

            sys.stdout.write(
                "\n".join(
                    line[
                        0 : min(
                            self.term_size.columns
                            - 1
                            + (len(line) - visible_len(line)),
                            len(line) - 1,
                        )
                    ]
                    for line in self.lines
                )
            )
            sys.stdout.write(
                f"\u001b[{self.cursor_row + self.term_size.lines-1};{self.cursor_col + 3}H\u001b[?25h"
            )

            time.sleep(0.05)
        enter_standard_mode()

    def draw(self, frameno: int):
        self.total_lines = len(self.chat_messages)
        if self.scroll_offset < 0 and self.last_line_count < self.total_lines:
            self.scroll_offset -= (
                self.total_lines - self.last_line_count
            )  # keep scroll offset

        self.last_line_count = self.total_lines

        self.lines[0] = linify(f"{self.scroll_offset} > ? # ?", self.term_size.columns)
        if self.server is not None:
            self.lines[0] = linify(
                f"{self.scroll_offset} > {self.server.name} # {"?" if self.active_channel is None else self.active_channel.name}",
                self.term_size.columns,
            )

        messages_start = max(
            (-self.message_lines)
            + self.scroll_offset
            - 1
            - len(break_and_wrap_text(self.chat_buffer, self.term_size.columns - 3)),
            -len(self.chat_messages),
        )

        messages_end = max(
            messages_start
            + self.message_lines
            + len(self.chat_messages)
            + 1
            - len(break_and_wrap_text(self.chat_buffer, self.term_size.columns - 3)),
            self.min_chat_lines + messages_start,
        )
        line_count = messages_end - messages_start
        for c in range(0, self.horiz_rule_line - 2):
            self.lines[c + 2] = linify("", self.term_size.columns)

        for c, message in enumerate(self.chat_messages[messages_start:messages_end]):
            self.lines[c + 2] = linify(f"{message}", self.term_size.columns)

        self.lines[
            self.term_size.lines
            - 2
            - min(
                len(break_and_wrap_text(self.chat_buffer, self.term_size.columns - 3)),
                self.min_chat_lines,
            )
        ] = horiz_line(self.term_size.columns)

        # self.lines[self.text_buffer_line] = linify(
        #     f"{"»" * (frameno//5 %2) + " " * ((frameno//5-1)%2)} {self.chat_buffer}",
        #     self.term_size.columns,
        # )
        self.lines[self.special_message_line] = linify(
            self.special_message, self.term_size.columns
        )

        self.draw_text_buffer(line_count, frameno)

    def draw_text_buffer(self, line_count: int, frameno):
        lines = self.chat_buffer.split("\n")
        real_lines = len(break_and_wrap_text(self.chat_buffer, self.wrap_len))
        start = self.text_buffer_scroll
        draw_line = (
            self.term_size.lines - 1 - min(real_lines, self.max_chat_buffer_lines)
        )  # start line- found from the bottom
        total_line_counter = 0
        lines_visited = 0
        for c, line in enumerate(lines):
            line += " "
            for c2, sub_line in enumerate(break_and_wrap_text(line, self.wrap_len)):
                # early return if we have no more lines to draw
                if total_line_counter >= self.max_chat_buffer_lines:
                    return
                # skip drawing this line if we haven't reached our start line yet
                lines_visited += 1
                if lines_visited < start:
                    continue
                # add highlights
                if (
                    c == self.cursor_row
                    and len(sub_line) != 0
                    and self.cursor_col - (c2 * self.wrap_len) < len(sub_line)
                    and self.cursor_col >= c2 * self.wrap_len
                ):
                    cursor_loc = min(
                        self.cursor_col - c2 * self.wrap_len, len(sub_line) - 1
                    )
                    sub_line = (
                        sub_line[:cursor_loc]
                        + REVERSE
                        + sub_line[cursor_loc]
                        + RESET
                        + sub_line[cursor_loc + 1 :]
                    )

                if c == 0 and c2 == 0:
                    sub_line = (
                        f"{"»" * (frameno//5 %2) + " " * ((frameno//5-1)%2)} {sub_line}"
                    )
                else:
                    sub_line = f"  {sub_line}"

                self.lines[draw_line + total_line_counter] = linify(
                    f"{start + total_line_counter}{sub_line}",
                    self.term_size.columns,
                )
                total_line_counter += 1

    def resize(self):
        """Changes the internal state to reflect the new terminal size."""
        self.term_size = os.get_terminal_size()
        # self.wrap_len = self.term_size.columns - 3
        self.wrap_len = 8

        self.lines = [" " * self.term_size.columns] * self.term_size.lines
        # individual elements
        self.text_buffer_line = self.term_size.lines - 2
        self.horiz_rule_line = self.term_size.lines - 3
        self.special_message_line = self.term_size.lines - 1
        self.min_chat_lines = min(5, self.term_size.lines)
        self.max_chat_buffer_lines = max(
            self.term_size.lines - self.min_chat_lines - 6, 1
        )

    def stop_typing(self):
        if self.server is not None and self.active_channel is not None:
            self.client.custom_events.append(self.active_channel.end_typing())

    def start_typing(self):
        if self.server is not None and self.active_channel is not None:
            self.client.custom_events.append(self.active_channel.begin_typing())

    def send_chat_buffer(self):
        if self.mode == ConsoleProgram.Modes.COMMANDMODE:
            if self.chat_buffer.lower() == "resize":
                self.resize()
            elif self.chat_buffer.lower() == "servers":
                self.add_chat_message(
                    "Servers:\n- "
                    + "\n- ".join(
                        f"{c}) {server.name}: {server.id}"
                        for c, server in enumerate(self.client.servers.values())
                    )
                )
            elif self.chat_buffer.lower() == "channels" and self.server is not None:
                self.add_chat_message(
                    "Channels:\n- "
                    + "\n- ".join(
                        f"{c}) {channel.name}: {channel.id}"
                        for c, channel in enumerate(self.server.channels)
                    )
                )

            elif self.chat_buffer.startswith("> "):
                for server in self.client.servers.values():
                    if server.name == self.chat_buffer.removeprefix("> "):
                        self.stop_typing()
                        self.server = server
                        break
                else:
                    if (
                        self.chat_buffer.removeprefix("> ").isnumeric()
                        and "." not in self.chat_buffer
                    ):
                        self.server = list(self.client.servers.values())[
                            int(self.chat_buffer.removeprefix("> "))
                        ]
            elif self.chat_buffer.startswith("# ") and self.server is not None:
                for channel in self.server.channels:
                    if channel.name == self.chat_buffer.removeprefix("# "):
                        self.stop_typing()
                        self.active_channel = channel
                        break
                else:
                    if (
                        self.chat_buffer.removeprefix("# ").isnumeric()
                        and "." not in self.chat_buffer
                    ):
                        self.active_channel = self.server.channels[
                            int(self.chat_buffer.removeprefix("# "))
                        ]
            elif self.chat_buffer == "q":
                self.running = False
        elif (
            self.mode == ConsoleProgram.Modes.TEXTMODE
            and self.active_channel is not None
        ):
            self.stop_typing()
            self.client.custom_events.append(self.active_channel.send(self.chat_buffer))
            self.add_chat_message("-- SENT A MESSAGE --")

        self.chat_buffer = ""
        self.cursor_col = 0
        self.cursor_row = 0

    def inputs(self, frameno, char: bytes, key: int):
        if key == 17 or key == 3:  # ctrl + q or ctrl+c
            self.running = False
        elif key == ENTER:  # enter
            self.send_chat_buffer()
        elif key == 9 and self.mode == ConsoleProgram.Modes.TEXTMODE:
            self.mode = ConsoleProgram.Modes.COMMANDMODE
        elif key == 9 and self.mode == ConsoleProgram.Modes.COMMANDMODE:
            self.mode = ConsoleProgram.Modes.TEXTMODE
        elif arrow_pressed(key):
            char = next_char()
            key = ord(char)
            if key == LEFT_ARROW:  # left arrow
                self.cursor_col = max(self.cursor_col - 1, 0)
            elif key == RIGHT_ARROW:  # right arrow
                self.cursor_col = min(self.cursor_col + 1, len(self.chat_buffer))
            elif key == UP_ARROW:  # up arrow
                lines = self.chat_buffer.split("\n")
                for c, line in enumerate(lines):
                    if self.cursor_row == c:
                        sub_lines = break_and_wrap_text(line, self.wrap_len)
                        if len(sub_lines) > 1 and self.cursor_col >= self.wrap_len:
                            self.cursor_col = max(self.cursor_col - self.wrap_len, 0)
                        elif len(sub_lines) > 1 and self.text_buffer_scroll == 0:
                            self.cursor_col = 0
                        else:
                            self.cursor_row = max(self.cursor_row - 1, 0)
                            if self.cursor_row < self.text_buffer_scroll:
                                self.text_buffer_scroll = self.cursor_row
                        if (
                            len(sub_lines) > 1
                            and c + self.cursor_col // self.wrap_len
                            < self.text_buffer_scroll
                        ):
                            self.text_buffer_scroll = (
                                c + self.cursor_col // self.wrap_len
                            )
                        break
            elif key == DOWN_ARROW:  # down arrow
                lines = self.chat_buffer.split("\n")
                for c, line in enumerate(lines):
                    if self.cursor_row == c:
                        sub_lines = break_and_wrap_text(line, self.wrap_len)
                        if (
                            len(sub_lines) > 1
                            and self.cursor_col <= len(line) - self.wrap_len
                        ):
                            self.cursor_col += self.wrap_len
                        elif len(sub_lines) > 1:
                            self.cursor_col = len(line)
                        else:
                            self.cursor_row = min(self.cursor_row + 1, len(lines) - 1)
                            if self.cursor_row > self.text_buffer_scroll:
                                self.text_buffer_scroll = self.cursor_row
                        if (
                            len(sub_lines) > 1
                            and c + self.cursor_col // self.wrap_len
                            >= self.text_buffer_scroll + self.max_chat_buffer_lines - 1
                        ):
                            self.text_buffer_scroll += 1
                        break
            elif key == PG_UP:  # pgup
                self.scroll_offset -= 1
            elif key == PG_DOWN:  # pgdown
                self.scroll_offset = min(self.scroll_offset + 1, 0)
        elif key == 22:  # ctl+v
            self.chat_buffer += pyperclip.paste()
        elif key == BACKSPACE and len(self.chat_buffer) > 0:  # backspace
            if len(self.chat_buffer) == 1:
                self.stop_typing()
            self.cursor_col -= 1
            previous = len(break_and_wrap_text(self.chat_buffer, self.wrap_len))
            self.chat_buffer = self.chat_buffer[0:-1]
            after = len(break_and_wrap_text(self.chat_buffer, self.wrap_len))
            if previous > after and previous >= self.max_chat_buffer_lines - 1:
                self.text_buffer_scroll = max(self.text_buffer_scroll - 1, 0)

        elif 126 >= key >= 32:
            self.start_typing()
            previous = len(break_and_wrap_text(self.chat_buffer, self.wrap_len))
            self.chat_buffer += char.decode("latin-1")
            after = len(break_and_wrap_text(self.chat_buffer, self.wrap_len))
            if (
                after > previous and previous >= self.max_chat_buffer_lines - 1
            ):  # new lines added:
                self.text_buffer_scroll += 1
            self.cursor_col += 1

        self.special_message = f"{char}: {key} || {self.mode.name} {self.cursor_col=} {self.cursor_row=} {self.text_buffer_scroll=}"


async def main(client: MyClient):
    client.custom_events = []
    asyncio.run_coroutine_threadsafe(client.start(), asyncio.get_running_loop())
    try:
        while console.running:
            while len(client.custom_events) > 0 and (
                event := client.custom_events.pop()
            ):
                try:
                    res = await event
                    if AppConfig.debug:
                        console.add_chat_message(str())
                except Exception as e:
                    console.add_chat_message(f"{RED}ERROR:\n" + str(e) + RESET)

            await asyncio.sleep(0)
    finally:
        await client.close()


class AppConfig(
    ConfigSpec, default_file="config.toml", writer=TomlWriter, create_file=True
):
    stoat_token = spec.Text("")
    debug = spec.Boolean(False)
    compact_mode = spec.Boolean(False)


if __name__ == "__main__":
    if AppConfig.stoat_token == "":
        print("Please enter in a stoat token in your config file")
        exit(1)

    client = MyClient(token=AppConfig.stoat_token, bot=False)

    console = ConsoleProgram(client)
    console.start()

    asyncio.run(main(client))
