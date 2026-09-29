from collections import deque
from typing import Tuple, Union

from tinder.entities.entity import Entity
from tinder.entities.message import Message
from tinder.entities.photo import MatchPhoto
from tinder.entities.socials import FacebookInfo
from tinder.entities.user import MatchedUser
from tinder.http import Http


class Match(Entity):
    """
    Represents a Tinder match.
    """

    __slots__ = [
        "_client",
        "closed",
        "facebook",
        "created_date",
        "dead",
        "last_activity_date",
        "message_history",
        "pending",
        "is_super_like",
        "is_boost_match",
        "is_super_boost_match",
        "is_experiences_match",
        "is_fast_match",
        "is_opener",
        "following",
        "following_moments",
        "matched_user",
        "liked_content",
        "seen",
        "last_seen_message_id",
    ]

    def __init__(self, match: dict, http: Http, client):
        """
        Creates a new match object

        :param match: the dictionary to construct the match from
        """

        super().__init__(match, http)
        self._client = client
        self.closed: bool = match["closed"]
        self.facebook: FacebookInfo = FacebookInfo(match)
        self.created_date: str = match["created_date"]
        self.dead: bool = match["dead"]
        self.last_activity_date: str = match["last_activity_date"]
        self.message_history: MessageHistory = MessageHistory(http, self.id)
        self.pending: bool = match["pending"]
        self.is_super_like: bool = match["is_super_like"]
        self.is_boost_match: bool = match["is_boost_match"]
        self.is_super_boost_match: bool = match["is_super_boost_match"]
        self.is_experiences_match: bool = match["is_experiences_match"]
        self.is_fast_match: bool = match["is_fast_match"]
        self.is_opener: bool = match["is_opener"]
        """`true` if the self user liked first"""
        self.following: bool = match["following"]
        self.following_moments: bool = match["following_moments"]
        self.matched_user: MatchedUser = MatchedUser(match["person"], http)
        if "liked_content" in match:
            liked_content = match["liked_content"]
            # if is_opener is true the self user liked first. Thus, the other user "closed" aka
            # completed the match. If is_opener is false the other use was the match "opener"
            if self.is_opener:
                self.liked_content: MatchPhoto = liked_content["by_closer"]["photo"]
            else:
                self.liked_content: MatchPhoto = liked_content["by_opener"]["photo"]
        self.seen: bool = False
        self.last_seen_message_id: str = ""
        if "seen" in match:
            self.seen: bool = match["seen"]["match_seen"]
            if "last_seen_message_id" in match["seen"]:
                self.last_seen_message_id: str = match["seen"]["last_seen_message_id"]

    def send_message(self, message: Union[str, Message]) -> Message:
        """
        Sends a message to the match.

        :param message: the message to send
        :return: the sent message
        """

        if type(message) is str:
            content = message
        else:
            content = message.content
        response = self.http.make_request(
            method="POST", route=f"/user/matches/{self.id}", body={"message": content}
        ).json()
        message = Message(response, self.http)
        self.message_history.add_message(message)
        return message

    def delete_match(self):
        """
        Deletes the match.
        <b>WARNING: This cannot be undone<b>
        """

        self.http.make_request(method="DELETE", route=f"match/{self.id}")
        self._client.invalidate_match(self)

    def __str__(self):
        return f"Match({self.id}:{self.matched_user})"


class MessageHistory:
    """
    Access point to the message history of a Match.

    By default, this class will cache the first 60 messages. `load_all_messages` to request
    all messages sent from the Tinder API.

    Message order is always in recent to past order.
    For example, a message at index 0 is more recent than a message at index 1.
    """

    def __init__(self, http: Http, match_id: str):
        self._messages: deque = deque()
        self.http: Http = http
        self._match_id = match_id

    def _fetch_initial_messages(self):
        route = f"/v2/matches/{self._match_id}/messages?count=60"
        data = self.http.make_request(method="GET", route=route).json()["data"]
        if "next_page_token" in data:
            self._page_token = data["next_page_token"]
        else:
            self._page_token = None

        self._messages.extendleft(Message(m, self.http) for m in data["messages"])

    def get_message_by_id(self, message_id: str) -> Message:
        """
        Gets a message by its id. Will request the message from the API if the message is not
        present in the cache.

        :return: a message by its id
        """

        filtered: list = list(filter(lambda message: message.id == message_id, self._messages))
        if len(filtered) == 0:

            return Message(
                self.http.make_request(method="GET", route=f"/message/{message_id}").json(),
                self.http,
            )
        else:
            return filtered[0]

    def get_messages(self) -> Tuple[Message]:
        """
        Gets all messages inside the cache.

        :return: all messages inside the cache
        """

        self._fetch_initial_messages()
        return tuple(self._messages)

    def load_all_messages(self) -> Tuple[Message]:
        """
        Requests all messages from the Tinder API.

        :return: all messages of a match
        """

        self._fetch_initial_messages()

        if self._page_token is None:
            return tuple(self._messages)

        self._messages.extendleft(self._load_messages(self._page_token))

        return tuple(self._messages)

    def _load_messages(self, page_token: str = None) -> Tuple[Message]:
        route = f"/v2/matches/{self._match_id}/messages?count=60"
        if page_token:
            route = f"{route}&page_token={page_token}"

        data = self.http.make_request(method="GET", route=route).json()["data"]
        messages: list = list(Message(m, self.http) for m in data["messages"])
        if "next_page_token" in data:
            messages.extend(self._load_messages(data["next_page_token"]))

        return tuple(messages)

    def size(self):
        """
        Gets the size of the cache.

        :return: the size of the cache
        """

        return len(self._messages)

    def add_message(self, message: Message):
        """
        Appends a message to the cache.

        :param message: the message to append
        """

        self._messages.append(message)
