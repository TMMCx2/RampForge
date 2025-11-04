"""DCDock TUI Application."""
import argparse
from typing import Any, Dict, Optional

from textual.app import App

from app.screens import DockDashboardScreen, LoginScreen
from app.services import APIClient, WebSocketClient


class DCDockApp(App):
    """DCDock Terminal User Interface Application."""

    CSS = """
    Screen {
        background: $surface;
    }
    """

    def __init__(self, api_url: str, ws_url: str) -> None:
        """Initialize DCDock app."""
        super().__init__()
        self.api_client = APIClient(api_url)
        self.ws_client = WebSocketClient(ws_url)
        self.user_data: Optional[Dict[str, Any]] = None

    async def on_mount(self) -> None:
        """Show login screen on startup."""
        await self.push_screen(LoginScreen(self.api_client), callback=self.on_login_success)

    def on_login_success(self, user_data: Optional[Dict[str, Any]]) -> None:
        """Handle successful login."""
        if user_data and self.api_client.token:
            self.ws_client.set_token(self.api_client.token)
            self.push_screen(
                DockDashboardScreen(self.api_client, self.ws_client, user_data)
            )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="DCDock Terminal User Interface")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API server URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--ws-url",
        default="ws://localhost:8000",
        help="WebSocket server URL (default: ws://localhost:8000)",
    )

    args = parser.parse_args()

    app = DCDockApp(args.api_url, args.ws_url)
    app.run()


if __name__ == "__main__":
    main()
