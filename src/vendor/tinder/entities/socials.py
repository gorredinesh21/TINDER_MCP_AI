from typing import Tuple

from tinder.entities.photo import SizedImage


class InstagramInfo:
    """
    Class containing Instagram photos if the Tinder profile is connected with Instagram.
    """

    __slots__ = ["last_fetch_time", "completed_initial_fetch", "media_count", "photos"]

    def __init__(self, instagram: dict):
        self.last_fetch_time: str = instagram["last_fetch_time"]
        self.completed_initial_fetch: bool = instagram["completed_initial_fetch"]
        self.media_count: int = instagram["media_count"]
        self.photos: Tuple[InstagramPhoto] = tuple(InstagramPhoto(p) for p in instagram["photos"])


class InstagramPhoto:
    """
    A photo from Instagram, used inside InstagramInfo.
    """

    __slots__ = ["image", "thumbnail", "ts"]

    def __init__(self, photo: dict):
        self.image: str = photo["image"]
        self.thumbnail: str = photo["thumbnail"]
        self.ts: str = photo["ts"]


class FacebookInfo:
    """
    Information about the same Facebook interests.
    """

    __slots__ = [
        "common_connections",
        "connection_count",
        "common_interests",
        "common_likes",
        "common_like_count",
        "common_friends",
        "common_friend_count",
    ]

    def __init__(self, facebook: dict):
        if "common_connections" in facebook:
            self.common_connections = facebook["common_connections"]
        if "connection_count" in facebook:
            self.connection_count = facebook["connection_count"]
        if "common_interests" in facebook:
            self.common_interests = facebook["common_interests"]
        if "common_likes" in facebook:
            self.common_likes = facebook["common_likes"]
        if "common_like_count" in facebook:
            self.common_like_count = facebook["common_like_count"]
        if "common_friends" in facebook:
            self.common_friends = facebook["common_friends"]
        if "common_friend_count" in facebook:
            self.common_friend_count = facebook["common_friend_count"]


class SpotifyEntity:
    """
    Generic Spotify entity.
    """

    __slots__ = ["id", "name"]

    def __init__(self, entity: dict):
        self.id = entity["id"]
        self.name: str = entity["name"]

    def __str__(self):
        return f"SpotifyEntity({self.id}:{self.name})"


class SpotifyAlbum(SpotifyEntity):
    """
    An album on Spotify.
    """

    __slots__ = ["images"]

    def __init__(self, album: dict):
        super().__init__(album)
        self.images: Tuple[SizedImage] = tuple(SizedImage(i) for i in album["images"])


class GenericSpotifyTrack(SpotifyEntity):
    """
    ABC for Spotify tracks.
    """

    __slots__ = ["album", "artists"]

    def __init__(self, track: dict):
        super().__init__(track)
        self.album: SpotifyAlbum = SpotifyAlbum(track["album"])
        self.artists: Tuple[SpotifyEntity] = tuple(SpotifyEntity(a) for a in track["artists"])


class SpotifyTrack(GenericSpotifyTrack):
    """
    A Spotify track used inside favourite track.
    """

    __slots__ = ["url", "uri"]

    def __init__(self, track: dict):
        super().__init__(track)
        self.url: str = track["preview_url"]
        self.url: str = track["uri"]


class SpotifySongAttachment(GenericSpotifyTrack):
    """
    A song attached to a message.
    """

    __slots__ = ["url"]

    def __init__(self, track: dict):
        super().__init__(track)
        self.url: str = track["url"]


class SpotifyTopArtist(SpotifyEntity):
    """
    A Spotify artist used inside Spotify top artists.
    """

    def __init__(self, artist: dict):
        super().__init__(artist)
        self.selected: bool = artist["selected"]
        self.top_track: SpotifyTrack = SpotifyTrack(artist["top_track"])
