from dataclasses import dataclass


@dataclass
class Response:
    status_code: int
    _body: dict

    def json(self) -> dict:
        return self._body


class ESPClient:
    """Provided interface — do not modify send_batch signature."""

    def send_batch(self, campaign_id: str, recipients: list[dict]) -> Response:
        """Sends a batch of recipients to the ESP.
        Returns a Response with .status_code and .json()"""
        raise NotImplementedError
