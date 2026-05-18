import re

from stoat import Channel, Message


def get_message_channels(message: Message) -> list[Channel]:
    '''Get all channels mentioned in a message'''
    if message.server is None:
        return []

    output = []

    for  match in re.findall(r"\<#.{26}\>", message.content):
        id = match.group()[2: -1]

        for server_channel in message.server.channels:
            if server_channel.id == id:
                output.append(server_channel)

    return output
