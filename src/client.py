"""HTTP API client class matching Table 22 route method naming rules."""

import requests

from src.constants import (
    HTTP_ERROR_THRESHOLD,
    REQUIRED_ACCEPT_HEADER,
    REQUIRED_ACCEPT_LANGUAGE,
    STATUS_ERROR,
)


class HTTPAPIError(RuntimeError):
    """Exception raised when HTTP API returns an error or HTTP >= 400."""

    def __init__(self, status_code, message):
        """Store HTTP status code and error description."""
        super().__init__(message)
        self.status_code = status_code


class HTTPAPIClient:
    """Client to Variant 22 HTTP API with route-derived method names."""

    def __init__(self, base_url):
        """Initialize client session and default required headers."""
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.default_headers = {
            "Accept": REQUIRED_ACCEPT_HEADER,
            "Accept-Language": REQUIRED_ACCEPT_LANGUAGE,
        }

    def close(self):
        """Close underlying HTTP client session."""
        self.session.close()

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager closing HTTP session."""
        self.close()

    def _request(self, method, path, params=None, json_body=None):
        """Send HTTP request with required headers and unwrap JSON result."""
        url = f"{self.base_url}{path}"
        resp = self.session.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=self.default_headers,
        )
        if resp.status_code >= HTTP_ERROR_THRESHOLD:
            raise HTTPAPIError(resp.status_code, resp.text)
        data = resp.json()
        if data.get("status") == STATUS_ERROR:
            raise HTTPAPIError(resp.status_code, data.get("error", "Error"))
        return data.get("result")

    def raw_request(self, method, path, headers=None):
        """Send HTTP request with custom headers for header tests."""
        url = f"{self.base_url}{path}"
        return self.session.request(method, url, headers=headers or {})

    def public_api_create_session(self, uid, timestamp, locale, user_agent):
        """Call POST /public/api/create/session."""
        return self._request(
            "POST",
            "/public/api/create/session",
            params={
                "uid": uid,
                "timestamp": timestamp,
                "locale": locale,
                "user_agent": user_agent,
            },
        )

    def public_api_remove_session(self, uid):
        """Call DELETE /public/api/remove/session/:uid."""
        return self._request("DELETE", f"/public/api/remove/session/{uid}")

    def public_api_query_session(self, **filters):
        """Call GET /public/api/query/session."""
        clean = {k: v for k, v in filters.items() if v is not None}
        return self._request("GET", "/public/api/query/session", params=clean)

    def public_api_correct_session(self, uid, **updates):
        """Call POST /public/api/correct/session."""
        body = {"uid": uid}
        for key, val in updates.items():
            if val is not None:
                body[key] = val
        return self._request(
            "POST", "/public/api/correct/session", json_body=body
        )

    def public_api_create_request(self, uid, timestamp, content,
                                  session, triggered):
        """Call POST /public/api/create/request."""
        return self._request(
            "POST",
            "/public/api/create/request",
            params={
                "uid": uid,
                "timestamp": timestamp,
                "content": content,
                "session": session,
                "triggered": triggered,
            },
        )

    def public_api_remove_request(self, uid):
        """Call DELETE /public/api/remove/request/:uid."""
        return self._request("DELETE", f"/public/api/remove/request/{uid}")

    def public_api_query_request(self, session, **filters):
        """Call GET /public/api/query/request/:session."""
        clean = {k: v for k, v in filters.items() if v is not None}
        return self._request(
            "GET",
            f"/public/api/query/request/{session}",
            params=clean,
        )

    def public_api_correct_request(self, uid, **updates):
        """Call POST /public/api/correct/request."""
        body = {"uid": uid}
        for key, val in updates.items():
            if val is not None:
                body[key] = val
        return self._request(
            "POST", "/public/api/correct/request", json_body=body
        )

    def public_api_query_answer(self, request_uid, **filters):
        """Call GET /public/api/query/answer/:request."""
        clean = {k: v for k, v in filters.items() if v is not None}
        return self._request(
            "GET",
            f"/public/api/query/answer/{request_uid}",
            params=clean,
        )

    def public_api_query_report(self):
        """Call GET /public/api/query/report."""
        return self._request("GET", "/public/api/query/report")

    _public_api_create_session = public_api_create_session
    _public_api_remove_session = public_api_remove_session
    _public_api_query_session = public_api_query_session
    _public_api_correct_session = public_api_correct_session
    _public_api_create_request = public_api_create_request
    _public_api_remove_request = public_api_remove_request
    _public_api_query_request = public_api_query_request
    _public_api_correct_request = public_api_correct_request
    _public_api_query_answer = public_api_query_answer
    _public_api_query_report = public_api_query_report
