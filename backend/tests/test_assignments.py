"""Tests for assignment management endpoints with optimistic locking."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Assignment, AuditLog, Load, Ramp, Status


pytestmark = pytest.mark.asyncio


class TestListAssignments:
    """Test GET /api/assignments/ endpoint."""

    async def test_list_assignments_as_admin(
        self, client: AsyncClient, admin_headers: dict[str, str], test_assignment: Assignment
    ):
        """Test listing assignments as admin."""
        response = await client.get("/api/assignments/", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Verify full details are included
        assignment = data[0]
        assert "id" in assignment
        assert "ramp" in assignment
        assert "load" in assignment
        assert "status" in assignment
        assert "creator" in assignment
        assert "updater" in assignment

    async def test_list_assignments_as_operator(
        self, client: AsyncClient, operator_headers: dict[str, str], test_assignment: Assignment
    ):
        """Test listing assignments as operator."""
        response = await client.get("/api/assignments/", headers=operator_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_assignments_filter_by_direction(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_load_inbound: Load,
        test_load_outbound: Load,
        test_ramp_inbound: Ramp,
        test_status_planned: Status,
        test_admin_user,
        test_db: AsyncSession
    ):
        """Test filtering assignments by load direction."""
        # Create inbound assignment
        inbound_assignment = Assignment(
            ramp_id=test_ramp_inbound.id,
            load_id=test_load_inbound.id,
            status_id=test_status_planned.id,
            created_by=test_admin_user.id,
            updated_by=test_admin_user.id,
        )
        test_db.add(inbound_assignment)

        # Create outbound assignment
        outbound_assignment = Assignment(
            ramp_id=test_ramp_inbound.id,
            load_id=test_load_outbound.id,
            status_id=test_status_planned.id,
            created_by=test_admin_user.id,
            updated_by=test_admin_user.id,
        )
        test_db.add(outbound_assignment)
        await test_db.commit()

        # Filter by inbound
        response = await client.get(
            "/api/assignments/?direction=IB",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert all(a["load"]["direction"] == "IB" for a in data)

        # Filter by outbound
        response = await client.get(
            "/api/assignments/?direction=OB",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert all(a["load"]["direction"] == "OB" for a in data)

    async def test_list_assignments_pagination(
        self, client: AsyncClient, admin_headers: dict[str, str], test_assignment: Assignment
    ):
        """Test pagination on assignment list."""
        response = await client.get(
            "/api/assignments/?skip=0&limit=1",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1

    async def test_list_assignments_without_auth(self, client: AsyncClient):
        """Test listing assignments without authentication."""
        response = await client.get("/api/assignments/")
        assert response.status_code == 403


class TestCreateAssignment:
    """Test POST /api/assignments/ endpoint."""

    async def test_create_assignment_as_admin(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_ramp_inbound: Ramp,
        test_load_inbound: Load,
        test_status_planned: Status,
        test_db: AsyncSession
    ):
        """Test creating a new assignment as admin."""
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
        data = response.json()
        assert data["ramp"]["id"] == test_ramp_inbound.id
        assert data["load"]["id"] == test_load_inbound.id
        assert data["status"]["id"] == test_status_planned.id
        assert data["version"] == 1
        assert "creator" in data
        assert "updater" in data

        # Verify assignment was created in database
        result = await test_db.execute(
            select(Assignment).where(Assignment.id == data["id"])
        )
        assignment = result.scalar_one_or_none()
        assert assignment is not None

        # Verify audit log was created
        result = await test_db.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "assignment",
                AuditLog.entity_id == assignment.id,
                AuditLog.action == "CREATE"
            )
        )
        audit = result.scalar_one_or_none()
        assert audit is not None

    async def test_create_assignment_as_operator(
        self,
        client: AsyncClient,
        operator_headers: dict[str, str],
        test_ramp_inbound: Ramp,
        test_load_inbound: Load,
        test_status_planned: Status,
    ):
        """Test creating assignment as operator (should be allowed)."""
        assignment_data = {
            "ramp_id": test_ramp_inbound.id,
            "load_id": test_load_inbound.id,
            "status_id": test_status_planned.id,
        }
        response = await client.post(
            "/api/assignments/",
            json=assignment_data,
            headers=operator_headers
        )
        assert response.status_code == 201

    async def test_create_assignment_invalid_ramp(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_load_inbound: Load,
        test_status_planned: Status,
    ):
        """Test creating assignment with non-existent ramp."""
        assignment_data = {
            "ramp_id": 99999,  # Non-existent
            "load_id": test_load_inbound.id,
            "status_id": test_status_planned.id,
        }
        response = await client.post(
            "/api/assignments/",
            json=assignment_data,
            headers=admin_headers
        )
        assert response.status_code == 404
        assert "ramp not found" in response.json()["detail"].lower()

    async def test_create_assignment_invalid_load(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_ramp_inbound: Ramp,
        test_status_planned: Status,
    ):
        """Test creating assignment with non-existent load."""
        assignment_data = {
            "ramp_id": test_ramp_inbound.id,
            "load_id": 99999,  # Non-existent
            "status_id": test_status_planned.id,
        }
        response = await client.post(
            "/api/assignments/",
            json=assignment_data,
            headers=admin_headers
        )
        assert response.status_code == 404
        assert "load not found" in response.json()["detail"].lower()

    async def test_create_assignment_invalid_status(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_ramp_inbound: Ramp,
        test_load_inbound: Load,
    ):
        """Test creating assignment with non-existent status."""
        assignment_data = {
            "ramp_id": test_ramp_inbound.id,
            "load_id": test_load_inbound.id,
            "status_id": 99999,  # Non-existent
        }
        response = await client.post(
            "/api/assignments/",
            json=assignment_data,
            headers=admin_headers
        )
        assert response.status_code == 404
        assert "status not found" in response.json()["detail"].lower()

    async def test_create_assignment_missing_fields(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test creating assignment with missing required fields."""
        assignment_data = {
            "ramp_id": 1,
            # Missing load_id and status_id
        }
        response = await client.post(
            "/api/assignments/",
            json=assignment_data,
            headers=admin_headers
        )
        assert response.status_code == 422  # Validation error


class TestGetAssignment:
    """Test GET /api/assignments/{assignment_id} endpoint."""

    async def test_get_assignment_by_id(
        self, client: AsyncClient, admin_headers: dict[str, str], test_assignment: Assignment
    ):
        """Test getting assignment by ID."""
        response = await client.get(
            f"/api/assignments/{test_assignment.id}",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_assignment.id
        assert "ramp" in data
        assert "load" in data
        assert "status" in data
        assert "creator" in data
        assert "updater" in data

    async def test_get_assignment_not_found(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test getting non-existent assignment."""
        response = await client.get("/api/assignments/99999", headers=admin_headers)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_assignment_invalid_id(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test getting assignment with invalid ID format."""
        response = await client.get("/api/assignments/invalid", headers=admin_headers)
        assert response.status_code == 422  # Validation error


class TestUpdateAssignment:
    """Test PATCH /api/assignments/{assignment_id} endpoint with optimistic locking."""

    async def test_update_assignment_success(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_status_arrived: Status,
        test_db: AsyncSession,
    ):
        """Test successful assignment update."""
        # Get current version first
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}",
            headers=admin_headers,
        )
        current_version = get_response.json()["version"]

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
        data = response.json()
        # Verify update succeeded - version incremented
        assert data["version"] == current_version + 1
        # Verify status was included in response
        assert "status" in data
        assert "code" in data["status"]

        # Verify audit log
        result = await test_db.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "assignment",
                AuditLog.entity_id == test_assignment.id,
                AuditLog.action == "UPDATE"
            )
        )
        audit = result.scalar_one_or_none()
        assert audit is not None

    async def test_update_assignment_optimistic_locking_conflict(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_status_arrived: Status,
    ):
        """Test optimistic locking prevents concurrent update conflicts."""
        # Get current version first
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}",
            headers=admin_headers,
        )
        current_version = get_response.json()["version"]

        # Try to update with wrong version
        wrong_version = current_version + 999
        update_data = {
            "status_id": test_status_arrived.id,
            "version": wrong_version,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 409  # Conflict
        data = response.json()
        assert "detail" in data
        conflict = data["detail"]
        assert "current_version" in conflict
        assert "provided_version" in conflict
        assert "current_data" in conflict
        assert conflict["current_version"] == current_version
        assert conflict["provided_version"] == wrong_version

    async def test_update_assignment_change_ramp(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_ramp_outbound: Ramp,
    ):
        """Test updating assignment ramp."""
        # Get current version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}", headers=admin_headers
        )
        current_version = get_response.json()["version"]

        update_data = {
            "ramp_id": test_ramp_outbound.id,
            "version": current_version,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Verify update succeeded - version incremented
        assert data["version"] == current_version + 1
        assert "ramp" in data

    async def test_update_assignment_change_load(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_load_outbound: Load,
    ):
        """Test updating assignment load."""
        # Get current version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}", headers=admin_headers
        )
        current_version = get_response.json()["version"]

        update_data = {
            "load_id": test_load_outbound.id,
            "version": current_version,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Verify update succeeded - version incremented
        assert data["version"] == current_version + 1
        assert "load" in data

    async def test_update_assignment_invalid_ramp(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
    ):
        """Test updating assignment with non-existent ramp."""
        # Get current version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}", headers=admin_headers
        )
        current_version = get_response.json()["version"]

        update_data = {
            "ramp_id": 99999,
            "version": current_version,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 404
        assert "ramp not found" in response.json()["detail"].lower()

    async def test_update_assignment_invalid_load(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
    ):
        """Test updating assignment with non-existent load."""
        # Get current version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}", headers=admin_headers
        )
        current_version = get_response.json()["version"]

        update_data = {
            "load_id": 99999,
            "version": current_version,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 404
        assert "load not found" in response.json()["detail"].lower()

    async def test_update_assignment_invalid_status(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
    ):
        """Test updating assignment with non-existent status."""
        # Get current version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}", headers=admin_headers
        )
        current_version = get_response.json()["version"]

        update_data = {
            "status_id": 99999,
            "version": current_version,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 404
        assert "status not found" in response.json()["detail"].lower()

    async def test_update_assignment_not_found(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test updating non-existent assignment."""
        update_data = {
            "status_id": 1,
            "version": 1,
        }
        response = await client.patch(
            "/api/assignments/99999",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 404

    async def test_update_assignment_missing_version(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_status_arrived: Status,
    ):
        """Test that version is required for updates."""
        update_data = {
            "status_id": test_status_arrived.id,
            # Missing version
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 422  # Validation error

    async def test_update_assignment_version_increments(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_status_arrived: Status,
    ):
        """Test that version increments correctly on each update."""
        # Get initial version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}", headers=admin_headers
        )
        initial_version = get_response.json()["version"]

        # First update
        update_data = {
            "status_id": test_status_arrived.id,
            "version": initial_version,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["version"] == initial_version + 1

        # Second update
        update_data = {
            "status_id": test_status_arrived.id,
            "version": initial_version + 1,
        }
        response = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data,
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["version"] == initial_version + 2


class TestDeleteAssignment:
    """Test DELETE /api/assignments/{assignment_id} endpoint."""

    async def test_delete_assignment(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        test_assignment: Assignment,
        test_db: AsyncSession,
    ):
        """Test deleting assignment."""
        assignment_id = test_assignment.id
        response = await client.delete(
            f"/api/assignments/{assignment_id}",
            headers=admin_headers
        )
        assert response.status_code == 204

        # Verify assignment was deleted
        result = await test_db.execute(
            select(Assignment).where(Assignment.id == assignment_id)
        )
        assignment = result.scalar_one_or_none()
        assert assignment is None

        # Verify audit log was created
        result = await test_db.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "assignment",
                AuditLog.entity_id == assignment_id,
                AuditLog.action == "DELETE"
            )
        )
        audit = result.scalar_one_or_none()
        assert audit is not None

    async def test_delete_assignment_as_operator(
        self,
        client: AsyncClient,
        operator_headers: dict[str, str],
        test_assignment: Assignment,
    ):
        """Test deleting assignment as operator (should be allowed)."""
        response = await client.delete(
            f"/api/assignments/{test_assignment.id}",
            headers=operator_headers
        )
        assert response.status_code == 204

    async def test_delete_assignment_not_found(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test deleting non-existent assignment."""
        response = await client.delete("/api/assignments/99999", headers=admin_headers)
        assert response.status_code == 404


class TestAssignmentPermissions:
    """Test assignment permission scenarios."""

    async def test_all_authenticated_users_can_manage_assignments(
        self,
        client: AsyncClient,
        operator_headers: dict[str, str],
        test_ramp_inbound: Ramp,
        test_load_inbound: Load,
        test_status_planned: Status,
    ):
        """Test that both admin and operator can manage assignments."""
        # Operator can create
        assignment_data = {
            "ramp_id": test_ramp_inbound.id,
            "load_id": test_load_inbound.id,
            "status_id": test_status_planned.id,
        }
        response = await client.post(
            "/api/assignments/",
            json=assignment_data,
            headers=operator_headers
        )
        assert response.status_code == 201
        assignment_id = response.json()["id"]
        version = response.json()["version"]

        # Operator can update
        update_data = {"status_id": test_status_planned.id, "version": version}
        response = await client.patch(
            f"/api/assignments/{assignment_id}",
            json=update_data,
            headers=operator_headers,
        )
        assert response.status_code == 200

        # Operator can delete
        response = await client.delete(
            f"/api/assignments/{assignment_id}",
            headers=operator_headers
        )
        assert response.status_code == 204


class TestOptimisticLockingScenarios:
    """Test complex optimistic locking scenarios."""

    async def test_concurrent_update_conflict(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        operator_headers: dict[str, str],
        test_assignment: Assignment,
        test_status_arrived: Status,
        test_status_planned: Status,
    ):
        """Simulate concurrent updates from two users."""
        # Get initial version
        get_response = await client.get(
            f"/api/assignments/{test_assignment.id}", headers=admin_headers
        )
        initial_version = get_response.json()["version"]

        # User 1 (admin) successfully updates
        update_data_1 = {
            "status_id": test_status_arrived.id,
            "version": initial_version,
        }
        response_1 = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data_1,
            headers=admin_headers,
        )
        assert response_1.status_code == 200
        assert response_1.json()["version"] == initial_version + 1

        # User 2 (operator) tries to update with stale version
        update_data_2 = {
            "status_id": test_status_planned.id,
            "version": initial_version,  # Stale version
        }
        response_2 = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data_2,
            headers=operator_headers,
        )
        assert response_2.status_code == 409  # Conflict
        conflict = response_2.json()["detail"]
        assert conflict["current_version"] == initial_version + 1
        assert conflict["provided_version"] == initial_version

        # User 2 can retry with correct version
        update_data_3 = {
            "status_id": test_status_planned.id,
            "version": initial_version + 1,  # Correct version
        }
        response_3 = await client.patch(
            f"/api/assignments/{test_assignment.id}",
            json=update_data_3,
            headers=operator_headers,
        )
        assert response_3.status_code == 200
        assert response_3.json()["version"] == initial_version + 2
