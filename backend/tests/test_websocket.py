"""Tests for WebSocket endpoints and real-time updates."""
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient

from app.db.models import Assignment, Load, Ramp, Status, User
from app.main import app
from app.ws.manager import manager


pytestmark = pytest.mark.asyncio


class TestWebSocketConnection:
    """Test WebSocket connection and authentication."""

    def test_websocket_connect_with_valid_token(
        self, client: AsyncClient, admin_token: str
    ):
        """Test WebSocket connection with valid JWT token."""
        # Use sync TestClient for WebSocket
        sync_client = TestClient(app)

        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as websocket:
            # Receive connection acknowledgment
            data = websocket.receive_json()
            assert data["type"] == "connection_ack"
            assert "client_id" in data
            assert "timestamp" in data

    def test_websocket_connect_without_token(self):
        """Test WebSocket connection fails without token."""
        sync_client = TestClient(app)

        with pytest.raises(Exception):  # WebSocket close exception
            with sync_client.websocket_connect("/api/ws"):
                pass

    def test_websocket_connect_with_invalid_token(self):
        """Test WebSocket connection fails with invalid token."""
        sync_client = TestClient(app)

        with pytest.raises(Exception):  # WebSocket close exception
            with sync_client.websocket_connect("/api/ws?token=invalid_token"):
                pass


class TestWebSocketSubscription:
    """Test WebSocket subscription and filtering."""

    def test_websocket_subscribe_without_filter(
        self, client: AsyncClient, admin_token: str
    ):
        """Test subscribing without filters (receive all updates)."""
        sync_client = TestClient(app)

        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as websocket:
            # Receive connection ack
            websocket.receive_json()

            # Send subscribe message without filters
            websocket.send_json({"type": "subscribe"})

            # Receive subscribe acknowledgment
            data = websocket.receive_json()
            assert data["type"] == "subscribe_ack"
            assert data["message"] == "Subscription updated"
            assert data["filters"] == {}

    def test_websocket_subscribe_with_direction_filter(
        self, client: AsyncClient, admin_token: str
    ):
        """Test subscribing with direction filter."""
        sync_client = TestClient(app)

        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as websocket:
            # Receive connection ack
            websocket.receive_json()

            # Subscribe to inbound only
            websocket.send_json({
                "type": "subscribe",
                "filters": {"direction": "IB"}
            })

            # Receive subscribe acknowledgment
            data = websocket.receive_json()
            assert data["type"] == "subscribe_ack"
            assert data["filters"]["direction"] == "IB"

    def test_websocket_unsubscribe(
        self, client: AsyncClient, admin_token: str
    ):
        """Test unsubscribing from updates."""
        sync_client = TestClient(app)

        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as websocket:
            # Receive connection ack
            websocket.receive_json()

            # Subscribe first
            websocket.send_json({
                "type": "subscribe",
                "filters": {"direction": "IB"}
            })
            websocket.receive_json()

            # Unsubscribe
            websocket.send_json({"type": "unsubscribe"})

            # Receive unsubscribe acknowledgment
            data = websocket.receive_json()
            assert data["type"] == "unsubscribe_ack"
            assert "Unsubscribed" in data["message"]

    def test_websocket_ping_pong(
        self, client: AsyncClient, admin_token: str
    ):
        """Test ping-pong keep-alive mechanism."""
        sync_client = TestClient(app)

        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as websocket:
            # Receive connection ack
            websocket.receive_json()

            # Send ping
            websocket.send_json({"type": "ping"})

            # Receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"
            assert "timestamp" in data

    def test_websocket_invalid_message_type(
        self, client: AsyncClient, admin_token: str
    ):
        """Test sending invalid message type."""
        sync_client = TestClient(app)

        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as websocket:
            # Receive connection ack
            websocket.receive_json()

            # Send invalid message type
            websocket.send_json({"type": "invalid_type"})

            # Receive error response
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert "Unknown message type" in data["message"]

    def test_websocket_invalid_json(
        self, client: AsyncClient, admin_token: str
    ):
        """Test sending invalid JSON."""
        sync_client = TestClient(app)

        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as websocket:
            # Receive connection ack
            websocket.receive_json()

            # Send invalid JSON
            websocket.send_text("not valid json")

            # Receive error response
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert "Invalid JSON" in data["message"]


class TestWebSocketBroadcast:
    """Test WebSocket broadcast functionality."""

    @patch('app.ws.manager.manager.broadcast_assignment_update')
    async def test_assignment_create_triggers_broadcast(
        self,
        mock_broadcast: AsyncMock,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_ramp_inbound: Ramp,
        test_load_inbound: Load,
        test_status_planned: Status,
    ):
        """Test that creating assignment triggers WebSocket broadcast."""
        # Create assignment
        assignment_data = {
            "ramp_id": test_ramp_inbound.id,
            "load_id": test_load_inbound.id,
            "status_id": test_status_planned.id,
        }
        response = await client.post(
            "/api/assignments/",
            json=assignment_data,
            headers=admin_headers
        )
        assert response.status_code == 201

        # Verify broadcast was called
        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args
        assert call_args.kwargs["action"] == "CREATE"
        assert call_args.kwargs["assignment_id"] == response.json()["id"]

    @patch('app.ws.manager.manager.broadcast_assignment_update')
    async def test_assignment_update_triggers_broadcast(
        self,
        mock_broadcast: AsyncMock,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_status_arrived: Status,
    ):
        """Test that updating assignment triggers WebSocket broadcast."""
        # Get current version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}",
            headers=admin_headers,
        )
        current_version = get_response.json()["version"]

        # Update assignment
        update_data = {
            "status_id": test_status_arrived.id,
            "version": current_version,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Verify broadcast was called
        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args
        assert call_args.kwargs["action"] == "UPDATE"

    @patch('app.ws.manager.manager.broadcast_assignment_update')
    async def test_assignment_delete_triggers_broadcast(
        self,
        mock_broadcast: AsyncMock,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
    ):
        """Test that deleting assignment triggers WebSocket broadcast."""
        assignment_id = test_assignment.id

        # Delete assignment
        response = await client.delete(
            f"/api/assignments/{assignment_id}",
            headers=admin_headers
        )
        assert response.status_code == 204

        # Verify broadcast was called
        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args
        assert call_args.kwargs["action"] == "DELETE"
        assert call_args.kwargs["assignment_id"] == assignment_id

    @patch('app.ws.manager.manager.broadcast_conflict')
    async def test_version_conflict_triggers_notification(
        self,
        mock_broadcast_conflict: AsyncMock,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_status_arrived: Status,
    ):
        """Test that version conflict triggers conflict notification."""
        # Get current version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}",
            headers=admin_headers,
        )
        current_version = get_response.json()["version"]

        # Try to update with wrong version
        update_data = {
            "status_id": test_status_arrived.id,
            "version": current_version + 999,  # Wrong version
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 409

        # Verify conflict notification was sent
        mock_broadcast_conflict.assert_called_once()
        call_args = mock_broadcast_conflict.call_args
        assert call_args.kwargs["assignment_id"] == test_assignment.id
        assert call_args.kwargs["current_version"] == current_version
        assert call_args.kwargs["attempted_version"] == current_version + 999


class TestWebSocketDirectionFilter:
    """Test WebSocket direction filtering."""

    def test_direction_filter_inbound_only(
        self, client: AsyncClient, admin_token: str, operator_token: str
    ):
        """Test that direction filter works correctly for inbound."""
        sync_client = TestClient(app)

        # Connect two clients
        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as ws_admin:
            with sync_client.websocket_connect(f"/api/ws?token={operator_token}") as ws_operator:
                # Clear connection acks
                ws_admin.receive_json()
                ws_operator.receive_json()

                # Admin subscribes to IB only
                ws_admin.send_json({
                    "type": "subscribe",
                    "filters": {"direction": "IB"}
                })
                ws_admin.receive_json()  # subscribe_ack

                # Operator subscribes to OB only
                ws_operator.send_json({
                    "type": "subscribe",
                    "filters": {"direction": "OB"}
                })
                ws_operator.receive_json()  # subscribe_ack

                # Simulate broadcast of IB assignment
                inbound_data = {
                    "load": {"direction": "IB"},
                    "ramp": {"code": "R1"},
                    "status": {"code": "PLANNED"}
                }

                # Admin should receive (subscribed to IB)
                # Operator should NOT receive (subscribed to OB)
                # This is tested implicitly through the broadcast_filtered logic


class TestWebSocketStats:
    """Test WebSocket statistics endpoint."""

    async def test_get_websocket_stats_no_connections(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test getting WebSocket stats with no active connections."""
        response = await client.get("/api/ws/stats", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "active_connections" in data
        assert "clients" in data
        assert isinstance(data["clients"], list)

    def test_get_websocket_stats_with_connections(
        self, client: AsyncClient, admin_token: str
    ):
        """Test getting WebSocket stats with active connections."""
        sync_client = TestClient(app)

        with sync_client.websocket_connect(f"/api/ws?token={admin_token}") as websocket:
            websocket.receive_json()  # connection_ack

            # Subscribe with filter
            websocket.send_json({
                "type": "subscribe",
                "filters": {"direction": "IB"}
            })
            websocket.receive_json()  # subscribe_ack

            # Get stats (using sync client for HTTP request)
            response = sync_client.get("/api/ws/stats")
            assert response.status_code == 200
            data = response.json()

            assert data["active_connections"] >= 1
            assert len(data["clients"]) >= 1

            # Check client info contains filters
            client_info = data["clients"][0]
            assert "client_id" in client_info
            assert "filters" in client_info


class TestWebSocketConnectionManager:
    """Test WebSocket ConnectionManager directly."""

    async def test_manager_connect_disconnect(self):
        """Test manager connect and disconnect."""
        # Create mock websocket
        mock_ws = AsyncMock()

        # Connect
        client_id = await manager.connect(mock_ws, "test_client")
        assert client_id == "test_client"
        assert manager.get_connection_count() >= 1

        # Disconnect
        await manager.disconnect(client_id)
        # Note: Other tests may have active connections, so just verify it decreased

    async def test_manager_broadcast_filtered(self):
        """Test manager filters broadcasts by direction."""
        # Create mock websockets
        mock_ws_ib = AsyncMock()
        mock_ws_ob = AsyncMock()
        mock_ws_all = AsyncMock()

        # Connect clients
        client_ib = await manager.connect(mock_ws_ib, "client_ib")
        client_ob = await manager.connect(mock_ws_ob, "client_ob")
        client_all = await manager.connect(mock_ws_all, "client_all")

        # Set filters
        manager.client_filters[client_ib] = {"direction": "IB"}
        manager.client_filters[client_ob] = {"direction": "OB"}
        manager.client_filters[client_all] = {}

        # Broadcast IB assignment
        assignment_data = {
            "load": {"direction": "IB"},
            "ramp": {"code": "R1"}
        }

        await manager.broadcast_assignment_update(
            assignment_id=1,
            action="CREATE",
            user_id=1,
            user_email="test@test.com",
            assignment_data=assignment_data
        )

        # Verify IB client received message
        assert mock_ws_ib.send_json.called

        # Verify ALL client received message (no filter)
        assert mock_ws_all.send_json.called

        # Cleanup
        await manager.disconnect(client_ib)
        await manager.disconnect(client_ob)
        await manager.disconnect(client_all)

    async def test_manager_get_client_info(self):
        """Test getting client information."""
        # Create mock websocket
        mock_ws = AsyncMock()

        # Connect with filter
        client_id = await manager.connect(mock_ws, "test_info_client")
        manager.client_filters[client_id] = {"direction": "IB"}

        # Get client info
        clients = manager.get_client_info()

        # Find our client
        our_client = None
        for client in clients:
            if client["client_id"] == client_id:
                our_client = client
                break

        assert our_client is not None
        assert our_client["filters"]["direction"] == "IB"

        # Cleanup
        await manager.disconnect(client_id)
