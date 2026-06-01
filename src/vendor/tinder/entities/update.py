from typing import List


class NewMessage:
    """
    Container for a new message holding the message and match id.
    """

    __slots__ = ["message_id", "match_id"]

    def __init__(self, message_id: str, match_id: str):
        self.message_id: str = message_id
        self.match_id: str = match_id


class Update:
    """
    Describes an update sent by Tinder containing information about new matches and messages.
    """

    __slots__ = ["new_matches", "new_messages", "update"]

    def __init__(self, update: dict):
        self.new_matches: List[str] = []
        """A list of all new matches"""
        self.new_messages: List[NewMessage] = []
        """A list of all new messages"""
        for match in update["matches"]:
            seen = True
            if "seen" in match:
                seen = match["seen"]["match_seen"]
            if seen:
                for message in match["messages"]:
                    self.new_messages.append(NewMessage(message["_id"], message["match_id"]))
            else:
                self.new_matches.append(match["_id"])
        self.update: dict = update
        """The raw update event response"""
