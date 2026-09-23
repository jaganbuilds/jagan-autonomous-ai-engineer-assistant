import pytest
import os
from unittest.mock import MagicMock, patch
from google.genai import types

from app.agents.manager import ManagerAgent
from app.agents.state import state_manager, SessionStatus
from app.tools.registry import registry

@pytest.fixture
def manager():
    # Ensure api key is set for testing or mock it
    with patch("app.agents.manager.get_settings") as mock_settings:
        mock_settings.return_value.gemini_api_key = "test_key"
        with patch("app.llm_client.get_llm_client") as mock_llm_client:
            mock_llm_client.return_value = MagicMock()
            mgr = ManagerAgent()
            
            # Mock the SDK client's chat mechanism
            mock_chat = MagicMock()
            mgr._get_chat = MagicMock(return_value=mock_chat)
            return mgr

def test_manager_normal_flow(manager):
    session_id = "test_normal"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    # Mock LLM returning plain text, no tools
    mock_response = MagicMock()
    mock_response.function_calls = []
    mock_response.text = "Hello there!"
    mock_chat.send_message.return_value = mock_response
    
    reply = manager.process_message("Hi", session_id)
    
    assert reply == "Hello there!"
    assert state_manager.get_session(session_id).status == SessionStatus.IDLE

def test_manager_auto_tool_flow(manager):
    session_id = "test_auto_tool"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    # Mock LLM returning a tool call
    tool_call = MagicMock()
    tool_call.name = "calculate"
    tool_call.args = {"expression": "2+2"}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "The answer is 4."
    
    # send_message should return the tool call first, then the final text
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    reply = manager.process_message("What is 2+2?", session_id)
    
    assert reply == "The answer is 4."
    assert state_manager.get_session(session_id).status == SessionStatus.IDLE
    assert mock_chat.send_message.call_count == 2

def test_manager_confirmation_flow(manager):
    session_id = "test_confirm"
    state_manager.clear_session(session_id)
    
    # Register a mock sensitive tool
    @registry.register(name="sensitive_tool", requires_confirmation=True)
    def mock_sensitive_tool():
        return "Done"
        
    mock_chat = manager._get_chat(session_id)
    
    # Mock LLM returning the sensitive tool call
    tool_call = MagicMock()
    tool_call.name = "sensitive_tool"
    tool_call.args = {}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    mock_chat.send_message.return_value = call_response
    
    # Step 1: User asks for sensitive action
    reply = manager.process_message("Do sensitive thing", session_id)
    
    # Manager should pause and return confirmation text
    assert "Shall I proceed?" in reply
    assert "sensitive_tool" in reply
    assert state_manager.get_session(session_id).status == SessionStatus.WAITING_FOR_CONFIRMATION
    
    # Step 2: User approves
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "Sensitive action completed."
    mock_chat.send_message.side_effect = [final_response] # The resume step
    
    reply2 = manager.process_message("yes", session_id)
    
    assert reply2 == "Sensitive action completed."
    assert state_manager.get_session(session_id).status == SessionStatus.IDLE

def test_manager_confirmation_rejection(manager):
    session_id = "test_reject"
    state_manager.clear_session(session_id)
    
    # Manually set the state to waiting for confirmation
    state_manager.set_pending_tool(session_id, "sensitive_tool", {})
    
    # User rejects
    reply = manager.process_message("no", session_id)
    
    assert state_manager.get_session(session_id).status == SessionStatus.IDLE

def test_manager_job_search_flow(manager):
    session_id = "test_job_search"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    # Mock LLM returning a tool call
    tool_call = MagicMock()
    tool_call.name = "search_jobs"
    tool_call.args = {"role": "Developer", "location": "Remote"}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    # Mock final text response
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "I found a Python Backend Developer job at WebSolutions."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    original_mock = os.environ.get("USE_MOCK_JOBS", "False")
    os.environ["USE_MOCK_JOBS"] = "True"
    
    try:
        reply = manager.process_message("Locate Developer positions Remote", session_id)
        
        assert reply == "I found a Python Backend Developer job at WebSolutions."
        assert state_manager.get_session(session_id).status == SessionStatus.IDLE
        assert mock_chat.send_message.call_count == 2
        
        # Verify the actual tool executed by checking the arguments passed in the second send_message call
        func_response_part = mock_chat.send_message.call_args_list[1][0][0]
        # Verify that the tool response contained the mock data
        assert "WebSolutions" in str(func_response_part)
    finally:
        os.environ["USE_MOCK_JOBS"] = original_mock

def test_manager_job_match_flow_success(manager):
    session_id = "test_match_flow_success"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "match_job_to_candidate"
    tool_call.args = {
        "title": "Python API Developer",
        "company": "TechCorp",
        "description": "Need Python, FastAPI, and Agile.",
        "location": "Remote",
        "experience": "Mid-Level"
    }
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "You match Python and FastAPI!"
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    reply = manager.process_message("Analyze this Python API Developer job for my profile.", session_id)
    
    assert reply == "You match Python and FastAPI!"
    assert state_manager.get_session(session_id).status == SessionStatus.IDLE
    assert mock_chat.send_message.call_count == 2
    
    func_response_part = mock_chat.send_message.call_args_list[1][0][0]
    assert "python" in str(func_response_part).lower()

def test_manager_job_match_missing_skills(manager):
    session_id = "test_match_flow_missing"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "match_job_to_candidate"
    tool_call.args = {
        "title": "Backend Dev",
        "company": "Tech",
        "description": "Requires Python, FastAPI, Docker, and Kubernetes.",
        "location": "Remote",
        "experience": "Senior"
    }
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "You match Python and FastAPI, but missing Docker and Kubernetes."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    reply = manager.process_message("Analyze this job requiring Docker.", session_id)
    
    func_response_part = str(mock_chat.send_message.call_args_list[1][0][0])
    # The tool returns JSON containing missing skills
    assert "docker" in func_response_part
    assert "kubernetes" in func_response_part
    assert "missing_skills" in func_response_part

def test_manager_job_match_no_match(manager):
    session_id = "test_match_flow_no_match"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "match_job_to_candidate"
    tool_call.args = {
        "title": "Java Dev",
        "company": "Tech",
        "description": "Need Java and Kubernetes.",
        "location": "Mars",
        "experience": "Junior"
    }
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "This job is not a match."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    reply = manager.process_message("Analyze Java Dev role.", session_id)
    
    func_response_part = str(mock_chat.send_message.call_args_list[1][0][0])
    assert "java" in func_response_part
    assert "Not Matched" in func_response_part

def test_manager_job_match_tool_safety(manager):
    # Verify the tool itself is flagged as NOT requiring confirmation
    from app.tools.registry import registry
    assert registry.requires_confirmation("match_job_to_candidate") is False
    
    session_id = "test_match_flow_safety"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "match_job_to_candidate"
    tool_call.args = {"title": "Safe Job", "company": "Co", "description": "Desc"}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "Done."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    manager.process_message("Analyze Safe Job.", session_id)
    

def test_manager_search_and_match_workflow_flow(manager):
    session_id = "test_search_and_match_flow"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "search_and_match_jobs"
    tool_call.args = {
        "role": "Python",
        "location": "Berlin"
    }
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "I found 3 Python jobs in Berlin. The best matches Python and FastAPI."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    original_mock = os.environ.get("USE_MOCK_JOBS", "False")
    os.environ["USE_MOCK_JOBS"] = "True"
    
    # Setup profile for the test session
    from app.profile.manager import profile_manager
    from app.profile.models import CandidateProfile
    test_profile = CandidateProfile(
        name="Test", experience_level="Mid", education="BS", skills=["Python", "FastAPI"]
    )
    profile_manager.save_profile(session_id, test_profile)
    
    try:
        reply = manager.process_message("Locate Python positions in Berlin and match them to my profile.", session_id)
        
        assert reply == "I found 3 Python jobs in Berlin. The best matches Python and FastAPI."
        assert state_manager.get_session(session_id).status == SessionStatus.IDLE
        assert mock_chat.send_message.call_count == 2
        
        # Verify the tool executed was search_and_match_jobs
        func_response_part = mock_chat.send_message.call_args_list[1][0][0]
        func_response_str = str(func_response_part).lower()
        
        # The mock database has no jobs precisely for Python+Berlin
        # But wait, we just verify the tool returned a result dict correctly
        assert "jobs_found" in func_response_str
    finally:
        os.environ["USE_MOCK_JOBS"] = original_mock

def test_manager_resume_extraction_flow(manager):
    session_id = "test_resume_extraction_flow"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "extract_and_save_profile"
    tool_call.args = {
        "file_path": "my_resume.pdf"
    }
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "I've successfully parsed your resume."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    from app.profile.manager import profile_manager
    from app.profile.models import CandidateProfile
    test_profile = CandidateProfile(
        name="John Resume", experience_level="Mid", education="BS", skills=["Python"]
    )
    
    # Mock the tool dependencies globally just for this execution
    with patch("app.tools.resume_profile_tool._parser.extract_text") as mock_extract_text:
        with patch("app.tools.resume_profile_tool._extractor.extract_profile") as mock_extract_profile:
            mock_extract_text.return_value = "Mocked Resume Text"
            mock_extract_profile.return_value = test_profile
            
            reply = manager.process_message("Please analyze my resume at my_resume.pdf", session_id)
            
            assert reply == "I've successfully parsed your resume."
            assert state_manager.get_session(session_id).status == SessionStatus.IDLE
            assert mock_chat.send_message.call_count == 2
            
            # Verify the tool executed and returned the success JSON
            func_response_part = mock_chat.send_message.call_args_list[1][0][0]
            func_response_str = str(func_response_part)
            
            assert "success" in func_response_str
            assert "John Resume" in func_response_str
            
            # Verify ProfileManager intercepted it
            assert profile_manager.has_profile(session_id)
            assert profile_manager.get_profile(session_id).name == "John Resume"

def test_manager_job_retrieval_flow(manager):
    session_id = "test_job_retrieval_flow"
    state_manager.clear_session(session_id)
    
    # 1. Search and store jobs
    from app.workflows.models import JobMatchPair
    from app.job_sources.base import Job
    from app.matching.models import MatchResult
    
    job = Job(title="E2E Dev", company="E2E Inc", description="D", location="L", experience="E", url="")
    match_result = MatchResult(
        matched_skills=["Python"], missing_skills=[], location_match="Matched", 
        experience_match="Matched", education_match="Unknown", explanation="E2E matched"
    )
    pair = JobMatchPair(job=job, match_result=match_result)
    state_manager.store_job_results(session_id, [pair])
    
    # 2. Simulate User asking for "job 1"
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "get_job_details"
    tool_call.args = {"job_reference": "job 1"}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "Here is the analysis for Job 1: E2E Dev at E2E Inc."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    reply = manager.process_message("Analyze job 1", session_id)
    
    assert reply == "Here is the analysis for Job 1: E2E Dev at E2E Inc."
    assert mock_chat.send_message.call_count == 2
    
    # Verify the tool result contained the correct job
    func_response_part = mock_chat.send_message.call_args_list[1][0][0]
    func_response_str = str(func_response_part)
    
    assert "success" in func_response_str
    assert "E2E Dev" in func_response_str

def test_manager_email_draft_flow(manager):
    session_id = "test_email_draft_flow"
    state_manager.clear_session(session_id)
    
    # 1. Store profile and job
    from app.profile.manager import profile_manager
    from app.profile.models import CandidateProfile
    from app.workflows.models import JobMatchPair
    from app.job_sources.base import Job
    from app.matching.models import MatchResult
    
    profile = CandidateProfile(name="Email Test", experience_level="Mid", education="BS", skills=[])
    profile_manager.save_profile(session_id, profile)
    
    job = Job(title="Email Dev", company="Email Inc", description="D", location="L", experience="E", url="")
    match_result = MatchResult(
        matched_skills=[], missing_skills=[], location_match="Unknown", 
        experience_match="Unknown", education_match="Unknown", explanation=""
    )
    pair = JobMatchPair(job=job, match_result=match_result)
    state_manager.store_job_results(session_id, [pair])
    
    # 2. Simulate User asking to draft email
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "draft_hr_email"
    tool_call.args = {"job_reference": "job 1"}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "I have drafted the email for you."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    with patch("app.llm_client.get_llm_client_or_raise") as mock_client:
        mock_response = MagicMock()
        mock_response.text = '{"subject": "Application", "body": "My draft", "recipient": null, "job_id": "job_1"}'
        mock_client.return_value.models.generate_content.return_value = mock_response
        
        reply = manager.process_message("Draft an email for job 1", session_id)
        
        assert reply == "I have drafted the email for you."
        assert mock_chat.send_message.call_count == 2
        
        func_response_part = mock_chat.send_message.call_args_list[1][0][0]
        func_response_str = str(func_response_part)
        
        assert "success" in func_response_str
        assert "My draft" in func_response_str

def test_manager_email_confirmation_flow(manager):
    session_id = "test_email_confirm_flow"
    from app.agents.state import state_manager, SessionStatus
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    # 1. Trigger the send_email tool
    from unittest.mock import MagicMock
    tool_call = MagicMock()
    tool_call.name = "send_email"
    tool_call.args = {"job_id": "job_1", "subject": "S", "body": "B", "recipient": "test@example.com"}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "Do you want to send this email?"
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    reply = manager.process_message("Send the email", session_id)
    assert reply == "Do you want to send this email?"
    
    # Verify session is waiting for confirmation
    session = state_manager.get_session(session_id)
    assert session.status == SessionStatus.WAITING_FOR_CONFIRMATION
    assert getattr(session, "pending_gateway_action", None) is not None
    
    # 2. Ambiguous reply
    reply2 = manager.process_message("I don't know", session_id)
    assert "Please clearly reply 'yes'" in reply2
    assert session.status == SessionStatus.WAITING_FOR_CONFIRMATION
    
    # 3. Explicit reject
    mock_chat.send_message.side_effect = [final_response] # Mock Gemini's response to the cancellation
    final_response.text = "Okay, I won't send it."
    reply3 = manager.process_message("No", session_id)
    
    assert reply3 == "Okay, I won't send it."
    assert session.status == SessionStatus.IDLE
    assert getattr(session, "pending_gateway_action", None) is None

@patch("app.email.gmail_client.GmailClient.send_email")
def test_manager_email_confirmation_confirm_flow(mock_send, manager):
    from app.email.gmail_client import GmailSendResult
    mock_send.return_value = GmailSendResult(success=True, message_id="123")

    session_id = "test_email_confirm_yes_flow"
    state_manager.clear_session(session_id)
    
    # 1. Create pending email
    from app.agents.confirmation import confirmation_manager
    confirmation_manager.create_pending_email(session_id, "job_1", "S", "B", "test@test.com")
    
    mock_chat = manager._get_chat(session_id)
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "Okay, it has been confirmed!"
    mock_chat.send_message.side_effect = [final_response]
    
    reply = manager.process_message("yes", session_id)
    
    assert reply == "Okay, it has been confirmed!"
    session = state_manager.get_session(session_id)
    assert session.status == SessionStatus.IDLE
    assert session.pending_email_action is None
    
    # Verify the confirmation JSON was sent to Gemini
    func_response_part = mock_chat.send_message.call_args[0][0]
    func_response_str = str(func_response_part)
    assert "Email sent successfully." in func_response_str

@patch("app.email.gmail_client.GmailClient.send_email")
def test_manager_email_confirmation_fail_flow(mock_send, manager):
    from app.email.gmail_client import GmailSendResult
    mock_send.return_value = GmailSendResult(success=False, error_code="500", error_message="Gmail down")
    
    session_id = "test_email_confirm_fail_flow"
    state_manager.clear_session(session_id)
    
    from app.agents.confirmation import confirmation_manager
    confirmation_manager.create_pending_email(session_id, "job_1", "S", "B", "recip")
    
    mock_chat = manager._get_chat(session_id)
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "Failed to send."
    mock_chat.send_message.side_effect = [final_response]
    
    reply = manager.process_message("yes", session_id)
    
    assert reply == "Failed to send."
    
    session = state_manager.get_session(session_id)
    assert getattr(session, "pending_gateway_action", None) is None

def test_manager_discovery_flow(manager):
    session_id = "test_discovery_flow"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "discover_new_jobs"
    tool_call.args = {"role": "Python"}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "I found 5 new jobs."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    # We don't care about hitting the real internet for the E2E manager test,
    # we just want to ensure it routes the tool call correctly and injects session.
    import os
    original_mock = os.environ.get("USE_MOCK_JOBS", "False")
    os.environ["USE_MOCK_JOBS"] = "True"
    
    try:
        reply = manager.process_message("Discover new jobs", session_id)
        
        # Verify tool response
        func_response_part = mock_chat.send_message.call_args[0][0]
        assert "profile_not_available" in str(func_response_part) or "completed" in str(func_response_part)
        assert reply == "I found 5 new jobs."
    finally:
        os.environ["USE_MOCK_JOBS"] = original_mock

def test_manager_digest_flow(manager):
    session_id = "test_digest_flow"
    state_manager.clear_session(session_id)
    
    mock_chat = manager._get_chat(session_id)
    
    tool_call = MagicMock()
    tool_call.name = "get_new_job_digest"
    tool_call.args = {"discovery_run_id": 12}
    
    call_response = MagicMock()
    call_response.function_calls = [tool_call]
    
    final_response = MagicMock()
    final_response.function_calls = []
    final_response.text = "Here is the digest for run 12."
    
    mock_chat.send_message.side_effect = [call_response, final_response]
    
    reply = manager.process_message("Show me jobs from run 12", session_id)
    
    func_response_part = mock_chat.send_message.call_args[0][0]
    assert "discovery_run_not_found" in str(func_response_part) or "success" in str(func_response_part)
    assert reply == "Here is the digest for run 12."
