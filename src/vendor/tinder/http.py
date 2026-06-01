import logging
import time
from math import floor
from random import random

import requests

from tinder.exceptions import Unauthorized, Forbidden, NotFound, RequestFailed


class Http:
    _base_url = "https://api.gotinder.com"
    _headers = {
        "User-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36",
        "Content-Type": "application/json",
        "X-Auth-Token": "",
    }
    _reattempt_count = {}
    _request_count = 0
    _logger = logging.getLogger("tinder-py")

    def __init__(self, token: str, log_level: int, timeout_factor: int = 10):
        self._headers["X-Auth-Token"] = token
        self._max_reattempts = 3
        self._timeout = timeout_factor
        logging.basicConfig(level=log_level)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        if timeout_factor < 1:
            self._logger.warning(
                f"The ratelimit multiplicator is set to {timeout_factor}."
                "This might result in API spam and banned accounts!"
            )

    def make_request(self, **kwargs) -> requests.Response:
        route = kwargs.get("route")
        method = kwargs.get("method")
        body = kwargs.get("body")

        self._request_count += 1

        if self._request_count > 2:
            timeout = floor(self._timeout * random())
            self._logger.debug(f"Too many requests. Waiting for {timeout} secs")
            time.sleep(timeout)
            self._request_count = 0
            self._logger.debug("Continuing...")

        url = self._base_url + route
        self._logger.debug(f"Sending {method} request to {url}")
        if method == "GET":
            response = requests.get(url, headers=self._headers)
        elif method == "POST":
            response = requests.post(url, headers=self._headers, json=body)
        elif method == "PUT":
            response = requests.put(url, headers=self._headers, json=body)
        elif method == "DELETE":
            response = requests.delete(url, headers=self._headers)
        else:
            raise ValueError("Invalid request method!")
        status = response.status_code
        self._logger.debug(f"Got response: {status}")

        if 200 <= status < 300:
            return response

        elif 400 <= status < 500:
            if status == 401:
                raise Unauthorized(response)
            elif status == 403:
                raise Forbidden(response)
            elif status == 404:
                raise NotFound(response)
            elif status == 429:
                timeout = floor(self._timeout * random())
                self._logger.debug(f"Too many requests. Waiting for {timeout} secs")
                time.sleep(timeout)
                self._logger.debug("Reattempting...")
                self.make_request(route=route, method=method, body=body)
            else:
                raise RequestFailed(response)

        else:
            if url.__hash__() in self._reattempt_count:
                self._reattempt_count[url.__hash__()] += 1
            else:
                self._reattempt_count[url.__hash__()] = 1

            if self._reattempt_count[url.__hash__()] < self._max_reattempts:
                self._logger.warning(
                    f"Something went wrong. Status Code {status}. "
                    f"Reattempting Request "
                    f"{self._reattempt_count[url.__hash__()]}..."
                )
                self.make_request(route=route, method=method, body=body)
            else:
                self._logger.error(
                    f"Something went wrong. Status Code {status}. Exceeded max retries."
                )
                raise RequestFailed(response)

        self._request_count = 0
