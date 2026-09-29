class TinderException(Exception):
    pass


class Unauthorized(TinderException):
    pass


class LoginException(Unauthorized):
    def __init__(self):
        super().__init__("The provided token is invalid!")


class Forbidden(TinderException):
    pass


class NotFound(TinderException):
    pass


class RequestFailed(TinderException):
    pass
