import pytest
from app.profile.models import CandidateProfile
from app.profile.manager import ProfileManager

@pytest.fixture
def manager():
    return ProfileManager()

@pytest.fixture
def dummy_profile():
    return CandidateProfile(
        name="Test User",
        experience_level="Mid",
        education="B.S.",
        skills=["Python", "FastAPI"]
    )

def test_save_and_retrieve(manager, dummy_profile):
    manager.save_profile("sess_1", dummy_profile)
    retrieved = manager.get_profile("sess_1")
    
    assert retrieved is not None
    assert retrieved.name == "Test User"
    assert retrieved.skills == ["Python", "FastAPI"]

def test_session_isolation(manager, dummy_profile):
    profile_a = dummy_profile.model_copy(deep=True)
    profile_a.name = "Alice"
    
    profile_b = dummy_profile.model_copy(deep=True)
    profile_b.name = "Bob"
    
    manager.save_profile("sess_a", profile_a)
    manager.save_profile("sess_b", profile_b)
    
    assert manager.get_profile("sess_a").name == "Alice"
    assert manager.get_profile("sess_b").name == "Bob"

def test_update(manager, dummy_profile):
    manager.save_profile("sess_1", dummy_profile)
    
    updated_profile = dummy_profile.model_copy(deep=True)
    updated_profile.name = "Updated User"
    manager.update_profile("sess_1", updated_profile)
    
    retrieved = manager.get_profile("sess_1")
    assert retrieved.name == "Updated User"

def test_delete(manager, dummy_profile):
    manager.save_profile("sess_1", dummy_profile)
    assert manager.has_profile("sess_1") is True
    
    manager.delete_profile("sess_1")
    assert manager.has_profile("sess_1") is False
    assert manager.get_profile("sess_1") is None
    
    # Deleting an unknown session should not crash
    manager.delete_profile("sess_unknown")

def test_unknown_session(manager):
    assert manager.get_profile("sess_unknown") is None
    assert manager.has_profile("sess_unknown") is False

def test_copy_reference_safety(manager, dummy_profile):
    # 1. Modify local object after save
    manager.save_profile("sess_1", dummy_profile)
    dummy_profile.name = "Mutated Local Name"
    
    retrieved = manager.get_profile("sess_1")
    assert retrieved.name == "Test User" # Internal state was unaffected
    
    # 2. Modify retrieved object
    retrieved.skills.append("Hacked Skill")
    retrieved2 = manager.get_profile("sess_1")
    
    assert "Hacked Skill" not in retrieved2.skills # Internal state was unaffected

def test_type_validation(manager):
    with pytest.raises(TypeError):
        manager.save_profile("sess_1", {"name": "Not a pydantic object"})

def test_multiple_sessions(manager, dummy_profile):
    for i in range(10):
        p = dummy_profile.model_copy(deep=True)
        p.name = f"User {i}"
        manager.save_profile(f"sess_{i}", p)
        
    for i in range(10):
        assert manager.has_profile(f"sess_{i}") is True
        assert manager.get_profile(f"sess_{i}").name == f"User {i}"
