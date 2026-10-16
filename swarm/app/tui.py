from __future__ import annotations

import asyncio
import json
import sys
import textwrap
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from rich import box
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from .api import messages_to_agent_input
from .app import chat_completion, load_config, stream_chat_completion
from .attachments import build_user_message, human_size
__version__ = "1.2.0"  
# ----------------------------------------------------------------- aesthetics

THEME = Theme({
    "accent":  "#8ab4f8",
    "accent2": "#c58af9",
    "muted":   "grey62",
    "faint":   "grey39",
    "ok":      "#81c995",
    "warn":    "#fdd663",
    "err":     "#f28b82",
    "reason":  "italic grey62",
})

BANNER = (
    "███╗   ██╗  ██████╗  ███╗   ███╗ ██████╗  ███████╗ ██████╗ ",
    "████╗  ██║ ██╔═══██╗ ████╗ ████║ ██╔══██╗ ██╔════╝ ██╔══██╗",
    "██╔██╗ ██║ ██║   ██║ ██╔████╔██║ ██████╔╝ █████╗   ██████╔╝",
    "██║╚██╗██║ ██║   ██║ ██║╚██╔╝██║ ██╔══██╗ ██╔══╝   ██╔══██╗",
    "██║ ╚████║ ╚██████╔╝ ██║ ╚═╝ ██║ ██████╔╝ ███████╗ ██║  ██║",
    "╚═╝  ╚═══╝  ╚═════╝  ╚═╝     ╚═╝ ╚═════╝  ╚══════╝ ╚═╝  ╚═╝",
)


def gradient_text(text: str, from_=(138, 180, 248), to=(197, 138, 249), row: float = 0.0) -> Text:
    """Blue → purple gradient, horizontally across a line, nudged by row."""
    n = max(len(text) - 1, 1)
    out = Text()
    for x, ch in enumerate(text):
        if ch == " ":
            out.append(" ")
            continue
        f = (x / n) * 0.65 + row * 0.35
        r = int(from_[0] + (to[0] - from_[0]) * f)
        g = int(from_[1] + (to[1] - from_[1]) * f)
        b = int(from_[2] + (to[2] - from_[2]) * f)
        out.append(ch, style=f"#{r:02x}{g:02x}{b:02x}")
    return out


def wrapped_tail(text: str, k: int, width: int):
    """Last k terminal-width lines of text, plus how many lines were cut above."""
    w = max(width - 2, 16)
    lines: list[str] = []
    for raw in text.split("\n"):
        raw = raw.replace("\t", "    ")
        if not raw:
            lines.append("")
            continue
        parts = textwrap.wrap(
            raw, w,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        lines.extend(parts or [""])
    cut = max(len(lines) - k, 0)
    return lines[-k:], cut


# ----------------------------------------------------------------- transport

class ApiError(Exception):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def _error_from_body(status: int, body: str) -> str:
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)
            if err is not None:
                return str(err)
            if data.get("detail"):
                return str(data["detail"])[:300]
    except ValueError:
        pass
    snippet = " ".join(body.split())[:300]
    return f"HTTP {status} — {snippet or 'request failed'}"


class SwarmClient:
    """Remote transport — talks to a running `agent-swarm serve` over HTTP."""

    def __init__(self, base_url: str, api_key: str | None = None):
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(600.0, connect=10.0),
        )

    async def aclose(self):
        await self._http.aclose()

    async def health(self) -> dict:
        r = await self._http.get("/health")
        if r.status_code >= 400:
            raise ApiError(_error_from_body(r.status_code, r.text), status=r.status_code)
        return r.json()

    async def list_models(self) -> list:
        r = await self._http.get("/v1/models")
        if r.status_code >= 400:
            raise ApiError(_error_from_body(r.status_code, r.text), status=r.status_code)
        return r.json().get("data", [])

    async def complete(self, messages: list[dict], model: str) -> str:
        r = await self._http.post(
            "/v1/chat/completions",
            json={"model": model, "messages": messages, "stream": False},
        )
        if r.status_code >= 400:
            raise ApiError(_error_from_body(r.status_code, r.text), status=r.status_code)
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError):
            raise ApiError("malformed response from server")
        return content or ""

    async def stream_chat(self, messages: list[dict], model: str):
        """Yield ("reasoning" | "content", delta_text) tuples parsed from SSE."""
        async with self._http.stream(
            "POST",
            "/v1/chat/completions",
            json={"model": model, "messages": messages, "stream": True},
        ) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise ApiError(_error_from_body(resp.status_code, body), status=resp.status_code)

            async for raw in resp.aiter_lines():
                if not raw or raw.startswith(":"):        # keep-alives / comments
                    continue
                if not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    event = json.loads(data)
                except ValueError:
                    continue

                if isinstance(event, dict) and event.get("error"):
                    info = event["error"]
                    if isinstance(info, dict):
                        code = info.get("code")
                        raise ApiError(
                            str(info.get("message", "agent workflow failed")),
                            code=str(code) if code else None,
                        )
                    raise ApiError(str(info))

                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                rc = delta.get("reasoning_content")
                if rc:
                    yield "reasoning", rc
                c = delta.get("content")
                if c:
                    yield "content", c


# ----------------------------------------------------------------- reasoning drawer

class ReasoningDrawer:
    """Live spinner + tail of the reasoning trace; collapses to a single line."""

    VERBS = ("Thinking", "Reasoning", "Pondering", "Deliberating", "Synthesizing", "Musing")

    def __init__(self, console: Console, spinner: str = "circleHalves", tail_lines: int = 6):
        self.console = console
        self.spinner_name = spinner
        self.tail_lines = tail_lines
        self.active = False
        self.text = ""
        self.elapsed = 0.0
        self._t0 = 0.0
        self._live: Live | None = None

    def open(self):
        if self.active:
            return
        self.active = True
        self.text = ""
        self._t0 = time.perf_counter()
        self._live = Live(self._frame(), console=self.console,
                          refresh_per_second=12, transient=True)
        self._live.start()

    def feed(self, delta: str):
        if not self.active:
            self.open()
        self.text += delta
        if self._live:
            self._live.update(self._frame())

    def close(self):
        if not self.active:
            return
        self.active = False
        self.elapsed = time.perf_counter() - self._t0
        if self._live:
            self._live.stop()
            self._live = None
        if self.text.strip():
            self.console.print(
                f"  ▸ [muted]thought for {self.elapsed:0.1f}s · "
                f"{len(self.text):,} chars[/] [faint]· /reason to expand[/]"
            )

    def _frame(self):
        elapsed = time.perf_counter() - self._t0
        verb = self.VERBS[int(elapsed // 5) % len(self.VERBS)]
        status = Text()
        status.append("✦ ", style="accent2")
        status.append(verb, style="bold")
        status.append(f"  {elapsed:0.1f}s", style="muted")
        if self.text:
            status.append(f"  ·  {len(self.text):,} chars", style="faint")

        grid = Table.grid(padding=(0, 1))
        grid.add_column()
        grid.add_column()
        grid.add_row(Spinner(self.spinner_name, style="accent"), status)

        if self.text.strip():
            visible, cut = wrapped_tail(self.text, self.tail_lines, self.console.width)
            tail = Text()
            if cut:
                tail.append("⋮\n", style="faint")
            for i, ln in enumerate(visible):
                tail.append("│ ", style="faint")
                tail.append(ln or " ", style="reason")
                if i < len(visible) - 1:
                    tail.append("\n")
            grid.add_row("", tail)
        return grid


# ----------------------------------------------------------------- content stream

class ContentStream:
    """Streams the answer into a live markdown block; falls back to a scrolling
    tail viewport once the answer outgrows the terminal."""

    CURSOR = "▌"

    def __init__(self, console: Console):
        self.console = console
        self.text = ""
        self.started = False
        self.printed = False
        self._live: Live | None = None

    def start(self):
        if self.started:
            return
        self.started = True
        self._live = Live(self._frame(), console=self.console,
                          refresh_per_second=12, transient=True)
        self._live.start()

    def feed(self, delta: str):
        if not self.started:
            self.start()
        self.text += delta
        if self._live:
            self._live.update(self._frame())

    def finish(self):
        if self._live:
            self._live.stop()
            self._live = None
        if not self.printed and self.text.strip():
            self.console.print(Markdown(self.text))
            self.printed = True

    def _frame(self, cursor: bool = True):
        h = max(self.console.size.height - 2, 6)

        if not self.text:
            out = Text("…", style="faint")
            if cursor:
                out.append(self.CURSOR, style="accent")
            return out

        md = Markdown(self.text + self.CURSOR) if cursor else Markdown(self.text)
        try:
            n = len(self.console.render_lines(md, self.console.options, pad=False))
        except Exception:
            n = h + 1

        if n <= h:                       # fits on screen — pretty markdown view
            return md

        # outgrew the screen — raw scrolling tail so new output stays visible
        visible, cut = wrapped_tail(self.text, h - 1, self.console.width)
        out = Text()
        if cut:
            out.append("⋮\n", style="faint")
        for i, ln in enumerate(visible):
            out.append(ln or " ")
            if i < len(visible) - 1:
                out.append("\n")
        if cursor:
            out.append(self.CURSOR, style="accent")
        return out


# ----------------------------------------------------------------- session / REPL


def _print_error(console: Console, err: Exception) -> None:
    sub = None
    if isinstance(err, ApiError):
        bits = []
        if err.status:
            bits.append(f"http {err.status}")
        if err.code:
            bits.append(err.code)
        if bits:
            sub = Text(" · ".join(bits), style="faint")

    console.print(Panel(
        Text(str(err), style="red"),
        title=Text(" ✖ error ", style="bold red"),
        title_align="left",
        subtitle=sub,
        subtitle_align="right",
        box=box.ROUNDED,
        border_style="red",
        padding=(0, 1),
    ))



class Session:
    def __init__(self, args: TuiOptions):
        self.args = args
        self.console = Console(theme=THEME)
        self.messages: list[dict] = []
        # In local mode, the YAML config is the source of truth.
        self.model = (
            _configured_model(args.config_path)
            if getattr(args, "config_path", None) is not None
            else args.model
        )
        self.stream = not args.no_stream
        self.system = args.system
        self.last_drawer: ReasoningDrawer | None = None
        self._stoppers: list = []
        self._last_sigint = 0.0

    # -- plumbing -----------------------------------------------------------

    def _is_local(self) -> bool:
        """True when the TUI runs the swarm in-process (run mode)."""
        return getattr(self.args, "config_path", None) is not None

    def _client(self):
        factory = getattr(self.args, "client_factory", None)
        if factory is not None:
            return factory()
        return SwarmClient(self.args.base_url, self.args.api_key)

    def _payload(self) -> list[dict]:
        msgs = []
        if self.system:
            msgs.append({"role": "system", "content": self.system})
        msgs.extend(self.messages)
        return msgs

    def _attach_files(self, line: str) -> str:
        """Parse local image paths out of ``line`` and append the resulting
        multimodal user message to ``self.messages``.

        Returns the original line unchanged — callers don't need to care
        whether attachments were found. Prints a small confirmation per
        attached image so the user knows the file was actually read.
        """
        msg, attached = build_user_message(line)
        self.messages.append(msg)
        for p in attached:
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            self.console.print(
                f"  [ok]✓[/] [muted]attached image[/] "
                f"[accent]{p.name}[/] [faint]({human_size(size)})[/]"
            )
        return line

    def _sync(self, coro_fn):
        """Run a client call in a fresh loop with proper client cleanup."""
        async def go():
            client = self._client()
            try:
                return await coro_fn(client)
            finally:
                await client.aclose()
        return asyncio.run(go())

    # -- one turn ------------------------------------------------------------

    def turn(self) -> str:
        try:
            return asyncio.run(self._turn())
        except KeyboardInterrupt:
            # pre-3.11 fallback: the coroutine never got to clean up
            for fn in list(self._stoppers):
                try:
                    fn()
                except Exception:
                    pass
            self._stoppers.clear()
            self.console.print("  [faint]✶ interrupted[/]")
            return "interrupted"

    async def _turn(self) -> str:
        console = self.console
        t0 = time.perf_counter()
        t_first: float | None = None
        drawer = ReasoningDrawer(console, self.args.spinner)
        streamer = ContentStream(console)
        err: ApiError | None = None
        interrupted = False
        self._stoppers = []

        client = self._client()
        try:
            if self.stream:
                drawer.open()
                self._stoppers = [drawer.close, streamer.finish]
                async for kind, delta in client.stream_chat(self._payload(), self.model):
                    if t_first is None:
                        t_first = time.perf_counter() - t0
                    if kind == "reasoning":
                        if not streamer.started:
                            drawer.feed(delta)
                        # reasoning after content started is ignored
                    else:
                        if drawer.active:
                            drawer.close()          # collapse the drawer
                        streamer.feed(delta)
            else:
                st = console.status(Text("✦ composing…", style="accent2"),
                                    spinner=self.args.spinner, spinner_style="accent")
                self._stoppers = [st.stop, streamer.finish]
                with st:
                    streamer.text = await client.complete(self._payload(), self.model)
        except ApiError as exc:
            err = exc
        except Exception as exc:                     # transport & friends
            err = ApiError(f"{type(exc).__name__}: {exc}")
        except BaseException:                        # ctrl+c / cancellation
            interrupted = True
        finally:
            if drawer.active:
                drawer.close()
            streamer.finish()
            self.last_drawer = drawer
            self._stoppers.clear()
            await client.aclose()

        if interrupted:
            if streamer.text.strip():
                console.print("  [faint]✶ interrupted — partial answer above[/]")
            else:
                console.print("  [faint]✶ interrupted[/]")
            return "interrupted"

        if err is not None:
            _print_error(console, err)
            return "error"

        answer = streamer.text
        if answer.strip():
            dt = time.perf_counter() - t0
            self.messages.append({"role": "assistant", "content": answer})
            stats = f"  [faint]· {dt:0.1f}s"
            if t_first is not None:
                stats += f" · first token {t_first:0.1f}s"
            stats += f" · {len(answer):,} chars · {self.model}[/]"
            console.print(stats)
        else:
            console.print("  [faint]· (empty response)[/]")
        return "ok"

    # -- commands ------------------------------------------------------------

    def _cmd_help(self):
        t = Table.grid(padding=(0, 2))
        t.add_column(style="accent", no_wrap=True)
        t.add_column(style="muted")
        for a, b in [
            ("/help",            "show this help"),
            ("/reason",          "expand the last reasoning drawer"),
            ("/clear",           "reset conversation history"),
            ("/model [name]",    "show or switch model"),
            ("/stream on|off",   "toggle streaming mode"),
            ("/system <text>",   "set system prompt · /system clear to remove"),
            ("/history",         "conversation stats"),
            ("/models",          "list models"),
            ("/health",          "validate config / ping the API"),
            ("/exit",            "quit · Ctrl+C twice also works"),
        ]:
            t.add_row(a, b)
        self.console.print(Panel(
            t,
            title=Text(" ✦ commands ", style="bold #c58af9"),
            title_align="left",
            box=box.ROUNDED,
            border_style="faint",
            padding=(0, 1),
        ))
        
        self.console.print(
            "  [faint]tip · end a line with \\ for a soft wrap · Ctrl+C interrupts a response[/]"
        )
        self.console.print(
            "  [faint]tip · type an image path (.png/.jpg/.gif/.webp/.bmp) in your message "
            "to attach it · quotes allowed for paths with spaces[/]"
        )
    def _cmd_reason(self):
        d = self.last_drawer
        if d and d.text.strip():
            self.console.print(Panel(
                Markdown(d.text),
                title=Text(" ▸ reasoning ", style="bold #c58af9"),
                title_align="left",
                subtitle=Text(f"{d.elapsed:0.1f}s · {len(d.text):,} chars", style="faint"),
                subtitle_align="right",
                box=box.ROUNDED,
                border_style="faint",
                padding=(0, 1),
            ))
        else:
            self.console.print("  [faint]· no reasoning captured in the last turn[/]")

    def _cmd_models(self):
        try:
            if self._is_local():
                data = self._sync(lambda c: c.list_models())
            else:
                with self.console.status(Text("✦ fetching models…", style="accent2"),
                                         spinner=self.args.spinner, spinner_style="accent"):
                    data = self._sync(lambda c: c.list_models())
            for m in data:
                self.console.print(f"  [accent]·[/] {m.get('id', '?')}  "
                                   f"[faint]{m.get('owned_by', '')}[/]")
        except Exception as exc:
            _print_error(self.console, exc if isinstance(exc, ApiError) else ApiError(str(exc)))

    def _cmd_health(self):
        try:
            if self._is_local():
                data = self._sync(lambda c: c.health())
            else:
                with self.console.status(Text("✦ pinging…", style="accent2"),
                                         spinner=self.args.spinner, spinner_style="accent"):
                    data = self._sync(lambda c: c.health())
            n = data.get("agents")
            detail = f" · {n} agent{'s' if n != 1 else ''}" if isinstance(n, int) else ""
            self.console.print(f"  [ok]✓[/] [muted]{data.get('status', 'ok')}{detail}[/]")
        except Exception as exc:
            _print_error(self.console, exc if isinstance(exc, ApiError) else ApiError(str(exc)))

    def _command(self, line: str) -> bool:
        console = self.console
        parts = line[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in {"exit", "quit", "q"}:
            console.print("  [faint]✦ bye[/]")
            return True
        elif cmd == "help":
            self._cmd_help()
        elif cmd == "clear":
            self.messages.clear()
            console.print("  [ok]✓[/] [muted]conversation cleared[/]")
        elif cmd == "reason":
            self._cmd_reason()
        elif cmd == "model":
            if self._is_local():
                # Local execution always uses provider.model from the YAML.
                self.model = _configured_model(self.args.config_path)
                if arg:
                    console.print(
                        "  [warn]Local mode uses the model configured in YAML; "
                        "change provider.model in the config file to switch models.[/]"
                    )
                console.print(f"  [muted]model[/] [accent]{self.model}[/]")
            else:
                if arg:
                    self.model = arg
                console.print(f"  [muted]model[/] [accent]{self.model}[/]")
        elif cmd == "stream":
            if arg == "on":
                self.stream = True
            elif arg == "off":
                self.stream = False
            console.print(f"  [muted]streaming[/] "
                          f"{'[ok]on[/]' if self.stream else '[warn]off[/]'}")
        elif cmd == "system":
            if arg in {"clear", "off"}:
                self.system = None
                console.print("  [ok]✓[/] [muted]system prompt removed[/]")
            elif arg:
                self.system = arg
                console.print(f"  [ok]✓[/] [muted]system prompt set[/] "
                              f"[faint]({len(arg)} chars)[/]")
            else:
                console.print(f"  [muted]system[/] {self.system or '(none)'}")
        elif cmd == "history":
            users = sum(1 for m in self.messages if m["role"] == "user")
            bots = sum(1 for m in self.messages if m["role"] == "assistant")
            chars = sum(len(m["content"]) for m in self.messages)
            console.print(f"  [muted]{users} user · {bots} assistant · "
                          f"~{chars:,} chars in context[/]")
        elif cmd == "models":
            self._cmd_models()
        elif cmd == "health":
            self._cmd_health()
        else:
            console.print(f"  [faint]unknown command: /{cmd} — /help for the list[/]")
        return False

    # -- banner / connect -----------------------------------------------------

    def _banner(self):
        console = self.console
        console.print()
        for y, row in enumerate(BANNER):
            line = Text("  ")
            line.append_text(gradient_text(row, row=y / max(len(BANNER) - 1, 1)))
            console.print(line)

        console.print()
        console.print(f"  [muted]NOMBER[/] [faint]v{__version__}[/]")

        if self._is_local():
            # Refresh from config so the banner cannot show a stale CLI default.
            self.model = _configured_model(self.args.config_path)
            console.print(
                f"  [muted]config[/]    [accent]{self.args.config_path}[/]"
            )
        else:
            console.print(
                f"  [muted]endpoint[/]  [accent]{self.args.base_url}[/]"
            )

        console.print(f"  [muted]model[/]     [accent]{self.model}[/]")
        stream_status = "[ok]on[/]" if self.stream else "[warn]off[/]"
        console.print(f"  [muted]stream[/]    {stream_status}")
        console.print("  [faint]/help for commands · /exit to quit[/]")
        console.print()

    def _connect(self):
        console = self.console
        if self._is_local():
            # Nothing to dial — the only real check is: does the config load?
            try:
                data = self._sync(lambda c: c.health())
            except Exception as exc:
                _print_error(console, exc if isinstance(exc, ApiError) else ApiError(str(exc)))
                return
            n = data.get("agents")
            detail = f" · {n} agent{'s' if n != 1 else ''}" if isinstance(n, int) else ""
            console.print(f"  [ok]✓[/] [muted]config validated · in-process{detail}[/]")
            return

        with console.status(Text("✦ connecting…", style="accent2"),
                            spinner=self.args.spinner, spinner_style="accent"):
            try:
                self._sync(lambda c: c.health())
                ok = True
            except Exception:
                ok = False
        if ok:
            console.print(f"  [ok]✓[/] [muted]connected to[/] [accent]{self.args.base_url}[/]")
        else:
            console.print(f"  [err]✗[/] [muted]can't reach[/] [accent]{self.args.base_url}[/] "
                          f"[faint]— /health to retry[/]")

    # -- REPL -------------------------------------------------------------------

    def repl(self):
        _setup_readline()
        self._banner()
        self._connect()
        console = self.console
        while True:
            console.print()
            try:
                console.print("  [ok]❯[/] ", end="")
                line = input()
                while line.endswith("\\"):
                    line = line[:-1].rstrip() + " "
                    console.print("  [faint]…[/] ", end="")
                    line += input()
            except EOFError:
                console.print("\n  [faint]✦ bye[/]")
                return
            except KeyboardInterrupt:
                now = time.time()
                if now - self._last_sigint < 2.0:
                    console.print("\n  [faint]✦ bye[/]")
                    return
                self._last_sigint = now
                console.print("  [faint]press Ctrl+C again to exit[/]")
                continue

            line = line.strip()
            if not line:
                continue
            if line.startswith("/"):
                if self._command(line):
                    return
                continue

            self._attach_files(line)
            self.turn()


# ----------------------------------------------------------------- misc

def _setup_readline():
    if sys.platform == "win32":
        return
    try:
        import readline  # noqa: F401 — arrow keys / history
    except ImportError:
        return
    hist = Path.home() / ".swarm_history"
    try:
        readline.read_history_file(str(hist))
    except OSError:
        pass
    readline.set_history_length(1000)

    import atexit

    def _save():
        try:
            readline.write_history_file(str(hist))
        except OSError:
            pass

    atexit.register(_save)


def _valid_spinner(name: str) -> str:
    try:
        Spinner(name)
        return name
    except Exception:
        return "circleHalves"


# ----------------------------------------------------------------- local transport

def _count_agents(cfg: Any) -> int | None:
    """Best-effort: how many agents does this config define?"""
    def probe(get):
        for key in ("agents", "agent_configs", "workers"):
            v = get(key)
            if isinstance(v, (list, tuple, dict)):
                return len(v)
        return None
    if isinstance(cfg, dict):
        return probe(cfg.get)
    return probe(lambda k: getattr(cfg, k, None))


def _configured_model(config_path: str) -> str:
    """Read provider.model directly from the YAML used by local execution.

    Reading the raw YAML avoids assumptions about the internal object returned
    by load_config (which may normalize or omit the nested provider mapping).
    """
    try:
        import yaml

        with Path(config_path).expanduser().open("r", encoding="utf-8") as stream:
            raw_cfg = yaml.safe_load(stream) or {}
        if isinstance(raw_cfg, dict):
            provider = raw_cfg.get("provider")
            if isinstance(provider, dict):
                model = provider.get("model")
                if model is not None and str(model).strip():
                    return str(model).strip()

            # Backward compatibility for configs using a top-level model.
            model = raw_cfg.get("model")
            if model is not None and str(model).strip():
                return str(model).strip()
    except Exception:
        # Fall back to the app's parsed config if direct YAML reading fails.
        pass

    try:
        cfg = load_config(Path(config_path))
        provider = cfg.get("provider") if isinstance(cfg, dict) else getattr(cfg, "provider", None)
        if isinstance(provider, dict):
            model = provider.get("model")
        else:
            model = getattr(provider, "model", None)
        if model is not None and str(model).strip():
            return str(model).strip()

        model = cfg.get("model") if isinstance(cfg, dict) else getattr(cfg, "model", None)
        if model is not None and str(model).strip():
            return str(model).strip()
    except Exception:
        # _cmd_health() will show the real config error if the config is invalid.
        pass

    return "unknown (check provider.model)"


class LocalSwarm:
    """In-process transport — calls the swarm directly, no HTTP hop.

    Mirrors SwarmClient's interface (stream_chat / complete / list_models /
    health / aclose) so Session can't tell the difference.
    """

    def __init__(self, config_path: str, model: str | None = None):
        self.config_path = config_path
        # The YAML provider.model is authoritative for local execution.
        self.model = _configured_model(config_path)

    def _prompt(self, messages: list[dict]) -> list[dict]:
        try:
            return messages_to_agent_input(messages)
        except ValueError as exc:
            raise ApiError(str(exc), status=400) from exc

    async def complete(self, messages: list[dict], model: str) -> str:
        answer = await chat_completion(self._prompt(messages), self.config_path)
        return answer if isinstance(answer, str) else str(answer)

    async def stream_chat(self, messages: list[dict], model: str):
        prompt = self._prompt(messages)
        async for event in stream_chat_completion(prompt, self.config_path):
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "reasoning":
                yield "reasoning", str(event.get("text", ""))
            elif kind == "content":
                yield "content", str(event.get("text", ""))
            elif kind == "error":
                raise ApiError(
                    str(event.get("message", "Agent workflow failed.")),
                    code="agent_workflow_error",
                )

    async def list_models(self) -> list:
        return [{"id": self.model, "object": "model", "owned_by": "local"}]

    async def health(self) -> dict:
        """Real check in local mode: the config must still load."""
        try:
            cfg = load_config(Path(self.config_path))
        except Exception as exc:
            raise ApiError(f"invalid config: {exc}") from exc
        return {"status": "ok", "agents": _count_agents(cfg)}

    async def aclose(self):
        pass


# ----------------------------------------------------------------- entry points

@dataclass
class TuiOptions:
    """Everything Session needs; constructed by agent_swarm.cli."""

    base_url: str = "http://127.0.0.1:8010"
    api_key: str | None = None
    model: str = "agent-swarm"
    system: str | None = None
    no_stream: bool = False
    spinner: str = "circleHalves"
    prompt: str | None = None
    client_factory: Callable[[], Any] | None = None
    config_path: str | None = None   # set → in-process mode


def run_tui(options: TuiOptions) -> int:
    """Entry point for the package CLI. Returns a process exit code."""
    options.spinner = _valid_spinner(options.spinner)
    session = Session(options)
    if options.prompt:
        session._attach_files(options.prompt)
        return 0 if session.turn() == "ok" else 1
    session.repl()
    return 0