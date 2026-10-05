import json
import os
from pathlib import Path
from urllib import request, error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 3000
API_PATH = "/api/chat"
HEALTH_PATH = "/health"
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ENV_FILE = Path("safarismart_backend.env")


def load_env_file():
    if not ENV_FILE.exists():
        return {}

    values = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


ENV_VALUES = load_env_file()


class ChatHandler(BaseHTTPRequestHandler):
    server_version = "SafariSmartBackend/1.0"

    def log_message(self, format, *args):
        return

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == HEALTH_PATH:
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != API_PATH:
            self._send_json(404, {"error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        text = (payload.get("text") or "").strip()
        lang = (payload.get("lang") or "sw").strip() or "sw"

        if not text:
            self._send_json(400, {"error": "Missing text"})
            return

        api_key = os.getenv("GROQ_API_KEY", ENV_VALUES.get("GROQ_API_KEY", os.getenv("OPENAI_API_KEY", ENV_VALUES.get("OPENAI_API_KEY", "")))).strip()
        if not api_key:
            self._send_json(503, {
                "error": "GROQ_API_KEY is not configured. Add it to safarismart_backend.env or set it in your environment."
            })
            return

        try:
            reply = self._ask_groq(text, lang, api_key)
            self._send_json(200, {"reply": reply})
        except Exception as exc:
            self._send_json(500, {"error": f"AI request failed: {str(exc)}"})

    def _ask_groq(self, text, lang, api_key):
        system_text = (
            "You are SafariBot for SafariSmart TZ. "
            "Answer in Kiswahili if the user language is sw, otherwise in English. "
            "Focus on Tanzania tourism, safari planning, wildlife, beaches, travel, visas, transport, safety, food, culture, and practical trip advice. "
            "Keep answers helpful, concise, and friendly."
        )

        model = os.getenv("GROQ_MODEL", ENV_VALUES.get("GROQ_MODEL", GROQ_MODEL)).strip() or GROQ_MODEL

        data = {
            "model": model,
            "temperature": 0.5,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": text}
            ]
        }

        request_body = json.dumps(data).encode("utf-8")
        req = request.Request(
            GROQ_URL,
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "SafariSmartBackend/1.0"
            },
            method="POST"
        )

        try:
            with request.urlopen(req, timeout=60) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            message = f"Groq API error: {exc.code} {raw}"
            if exc.code == 403 and "1010" in raw:
                message += " The configured GROQ_API_KEY appears to be rejected or expired. Please generate a fresh Groq API key and update safarismart_backend.env."
            raise RuntimeError(message)
        except Exception as exc:
            raise RuntimeError(f"Groq request failed: {str(exc)}")

        if not response_data.get("choices"):
            raise RuntimeError("Groq returned no choices")

        content = response_data["choices"][0]["message"].get("content", "")
        return content.strip() or "I’m sorry, I could not generate a response right now."

    def _send_json(self, status_code, payload):
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


if __name__ == "__main__":
    print(f"Starting SafariSmart backend on http://{HOST}:{PORT}")
    print("Set GROQ_API_KEY in safarismart_backend.env or your terminal before starting the server.")
    server = ThreadingHTTPServer((HOST, PORT), ChatHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SafariSmart backend...")
    finally:
        server.server_close()
