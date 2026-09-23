import pytest
from app.agents.router import TaskRouter, Intent

@pytest.fixture
def router():
    return TaskRouter()

def test_calculate_intent(router):
    assert router.route("What is 452 multiplied by 13?").intent == Intent.CALCULATE
    assert router.route("calculate 5 + 5").intent == Intent.CALCULATE
    assert router.route("10 / 2").intent == Intent.CALCULATE

def test_file_operation_intent(router):
    assert router.route("List the files in the project.").intent == Intent.FILE_OPERATION
    assert router.route("Can you read the file main.py?").intent == Intent.FILE_OPERATION
    assert router.route("delete file test.txt").intent == Intent.FILE_OPERATION

def test_project_information_intent(router):
    assert router.route("Analyze the current project structure.").intent == Intent.PROJECT_INFORMATION
    assert router.route("What is the project info?").intent == Intent.PROJECT_INFORMATION

def test_general_chat_intent(router):
    assert router.route("Hello there!").intent == Intent.GENERAL_CHAT
    assert router.route("Who are you?").intent == Intent.GENERAL_CHAT

def test_unknown_intent(router):
    assert router.route("Do a barrel roll").intent == Intent.UNKNOWN
    assert router.route("Sing me a song").intent == Intent.UNKNOWN
