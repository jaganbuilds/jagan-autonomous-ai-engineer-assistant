import pytest
from app.database.connection import init_db
from app.database.repository import JobRepository, set_job_repository_for_testing
from app.memory.repository import MemoryRepository, set_memory_repository_for_testing

@pytest.fixture(autouse=True)
def mock_db_repository():
    """
    Globally configures the application to use an in-memory SQLite database
    for all tests, ensuring the real data/jagan_ai.db is never touched.
    """
    db_path = "file:memdb_global?mode=memory&cache=shared"
    init_db(db_path)
    
    from app.database.connection import get_db_connection
    with get_db_connection(db_path) as conn:
        conn.cursor().execute("DELETE FROM jobs")
        conn.cursor().execute("DELETE FROM memories")
        conn.cursor().execute("DELETE FROM actions")
        conn.commit()
        
    repo = JobRepository(db_path)
    set_job_repository_for_testing(repo)
    
    mem_repo = MemoryRepository(db_path)
    set_memory_repository_for_testing(mem_repo)
    
    from app.database.action_repository import action_repository
    action_repository.db_path = db_path
    
    yield repo
    
    # Reset it after tests (optional, but good practice)
    set_job_repository_for_testing(None)
    set_memory_repository_for_testing(None)
    action_repository.db_path = None

@pytest.fixture(autouse=True)
def mock_preflight_for_execution_tests(request, monkeypatch):
    """
    Globally mocks validate_preflight inside ActionGateway so that tests written
    before Phase 10 Step 9 do not fail due to missing credentials/network timeouts
    during preflight capability checks.
    """
    if "test_preflight.py" in str(request.node.fspath) or "test_capabilities.py" in str(request.node.fspath):
        return
        
    from app.integrations.capabilities import IntegrationCapability, ActionCapability
    from app.integrations.models import get_action_risk_level, ActionType
    from app.integrations.gateway import action_gateway
    
    def dummy_get_capabilities(self, integration_name):
        integration = action_gateway._integrations.get(integration_name)
        if not integration:
            return None
            
        actions = []
        for a in integration.supported_actions:
            risk = get_action_risk_level(a)
            actions.append(ActionCapability(
                action_type=a,
                risk_level=risk.value,
                requires_confirmation=(risk.value == "HIGH")
            ))
            
        return IntegrationCapability(
            integration_name=integration_name,
            display_name=integration_name,
            available=True,
            authenticated=True,
            healthy=True,
            supported_actions=actions,
            health_message="Test override"
        )
        
    monkeypatch.setattr("app.integrations.capability_service.CapabilityService.get_integration_capabilities", dummy_get_capabilities)
