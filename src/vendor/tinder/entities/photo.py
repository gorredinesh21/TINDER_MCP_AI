from typing import Tuple

from tinder.entities.entity import Entity
from tinder.http import Http


class FacialScope:
    """
    Facial Scope contains coordinates to locate faces inside a photo.
    """

    __slots__ = ["width_pct", "x_offset_pct", "height_pct", "y_offset_pct"]

    def __init__(self, scope: dict):
        self.width_pct: float = scope["width_pct"]
        self.x_offset_pct: float = scope["width_pct"]
        self.height_pct: float = scope["height_pct"]
        self.y_offset_pct: float = scope["y_offset_pct"]


class Face:
    """
    A face inside a photo.
    """

    __slots__ = ["algo", "bounding_box_percentage"]

    def __init__(self, face: dict):
        self.algo: FacialScope = FacialScope(face["algo"])
        self.bounding_box_percentage: float = face["bounding_box_percentage"]


class CropInfo:
    """
    Photo processing metadata.
    """

    __slots__ = ["processed_by_bullseye", "user_customized", "user", "algo", "faces"]

    def __init__(self, crop_info: dict):
        self.processed_by_bullseye: bool = crop_info["processed_by_bullseye"]
        self.user_customized: bool = crop_info["user_customized"]

        self.user = None
        if "user" in crop_info:
            self.user: FacialScope = FacialScope(crop_info["user"])

        self.algo = None
        if "algo" in crop_info:
            self.algo: FacialScope = FacialScope(crop_info["algo"])

        if "faces" in crop_info:
            self.faces: Tuple[Face] = tuple(Face(algo) for algo in crop_info["faces"])

    def has_faces(self) -> bool:
        return len(self.faces) > 0


class SizedImage:
    """
    An image with a fixed size. Used in various places inside the API.
    """

    __slots__ = ["height", "width", "url", "quality"]

    def __init__(self, sized_image: dict):
        self.height: int = sized_image["height"]
        self.width: int = sized_image["width"]
        self.url: str = sized_image["url"]

        self.quality = None
        if "quality" in sized_image:
            self.quality: str = sized_image["quality"]

    def is_descriptor_image(self) -> bool:
        return self.quality is not None


class Hash:
    """
    A photo hash.
    """

    __slots__ = ["version", "value"]

    def __init__(self, hash_algo: dict):
        self.version: str = hash_algo["version"]
        self.value: str = hash_algo["value"]


class GenericPhoto(Entity):
    """
    ABC for photos.
    """

    __slots__ = [
        "crop_info",
        "url",
        "processed_files",
        "processed_videos",
        "file_name",
        "extension",
        "type",
    ]

    def __init__(self, photo: dict, http: Http):
        super().__init__(photo, http)
        self.crop_info: CropInfo = CropInfo(photo["crop_info"])
        self.url: str = photo["url"]
        if "type" in photo:
            self.type: str = photo["type"]
        else:
            self.type: str = photo["media_type"]
        self.processed_files: Tuple[SizedImage] = tuple(
            SizedImage(i) for i in photo["processedFiles"]
        )
        if self.type == "video":
            self.processed_videos: Tuple[SizedImage] = tuple(
                SizedImage(i) for i in photo["processedFiles"]
            )
        self.file_name: str = photo["fileName"]
        self.extension: str = photo["extension"]

    def __str__(self):
        return f"Photo({self.id})"


class ProfilePhoto(GenericPhoto):
    """
    Photos inside a profile object.
    """

    __slots__ = [
        "assets",
        "created_at",
        "updated_at",
        "fb_id",
        "webp_qf",
        "rank",
        "score",
        "win_count",
        "phash",
        "dhash",
    ]

    def __init__(self, photo: dict, http: Http):
        super().__init__(photo, http)
        self.assets: Tuple[SizedImage] = tuple(SizedImage(i) for i in photo["assets"])
        self.created_at: str = photo["created_at"]
        self.updated_at: str = photo["updated_at"]
        self.fb_id: str = photo["fbId"]
        self.webp_qf: int = photo["webp_qf"][0]
        self.rank: int = photo["rank"]
        self.score: float = photo["score"]
        self.win_count: int = photo["win_count"]
        self.phash: Hash = Hash(photo["phash"])
        self.dhash: Hash = Hash(photo["dhash"])


class MatchPhoto(GenericPhoto):
    """
    Photos inside a matched user object.
    """

    __slots__ = ["assets", "webp_qf", "rank", "score", "win_count"]

    def __init__(self, photo: dict, http: Http):
        super().__init__(photo, http)
        self.assets: Tuple[SizedImage] = tuple(SizedImage(i) for i in photo["assets"])
        if type == "image":
            self.webp_qf: int = photo["webp_qf"][0]
            self.rank: int = photo["rank"]
            self.score: float = photo["score"]
            self.win_count: int = photo["win_count"]
