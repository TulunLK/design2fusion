"""Cliente MCP mínimo por stdio para FigCraft (JSON-RPC por líneas).

FigCraft expone un servidor MCP (``figcraft-cli mcp``) que habla JSON-RPC 2.0
sobre stdin/stdout. Este módulo solo implementa lo necesario: handshake,
``tools/call`` y el comando ``run_command``.
"""
import json
import os
import shutil
import subprocess

FALLBACK_CLI = os.path.expanduser(
    "~/Descargas/figcraft/repo/figcraft/target/release/figcraft-cli")


def find_cli():
    """Ruta a figcraft-cli: $FIGCRAFT_CLI, PATH, o el build local."""
    cli = os.environ.get("FIGCRAFT_CLI") or shutil.which("figcraft-cli")
    if not cli and os.path.exists(FALLBACK_CLI):
        cli = FALLBACK_CLI
    if not cli:
        raise RuntimeError(
            "No encuentro figcraft-cli. Instalá FigCraft "
            "(https://github.com/storytold/figcraft) o definí FIGCRAFT_CLI.")
    return cli


class MCP:
    def __init__(self, args=None, client_name="design2fusion"):
        cmd = [find_cli(), "mcp"] + (args or [])
        self.p = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        self.id = 0
        self.client_name = client_name
        self._init()

    def _send(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self.id += 1
            msg["id"] = self.id
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        if notify:
            return None
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError(
                    "El server MCP cerró la conexión. stderr: "
                    + self.p.stderr.read()[:2000])
            r = json.loads(line)
            if r.get("id") == self.id:
                if "error" in r:
                    raise RuntimeError("error MCP: %s" % r["error"])
                return r

    def _init(self):
        self._send("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": self.client_name, "version": "0.1"},
        })
        self._send("notifications/initialized", notify=True)

    def call(self, tool, **args):
        r = self._send("tools/call", {"name": tool, "arguments": args})
        out = []
        for c in r["result"].get("content", []):
            if c.get("type") == "text":
                try:
                    out.append(json.loads(c["text"]))
                except ValueError:
                    out.append(c["text"])
            else:
                out.append({k: c[k] for k in c if k != "data"})
        return out[0] if len(out) == 1 else out

    def run(self, command, **params):
        return self.call("run_command", command=command, params=params)

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
