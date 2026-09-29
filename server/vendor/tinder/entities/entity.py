from tinder.http import Http


class Entity:
    """
    ABC for all Tinder entities.
    """

    __slots__ = ["http", "id"]

    def __init__(self, entity: dict, http: Http):
        self.http = http
        if "_id" in entity:
            self.id: str = entity["_id"]
        elif "id" in entity:
            self.id: str = entity["id"]
        else:
            raise TypeError("Not an entity!")

    def __str__(self):
        return f"Tinder Entity({self.id})"
