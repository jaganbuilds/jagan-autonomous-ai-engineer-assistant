from app.tools.registry import registry

# Import all tools to ensure they are registered
import app.tools.file_tool
import app.tools.project_tool
import app.tools.calculator_tool
import app.tools.job_search_tool
import app.tools.job_match_tool
import app.tools.job_matching_workflow_tool
import app.tools.resume_profile_tool
import app.tools.get_job_details_tool
import app.tools.hr_email_tool
import app.tools.send_email_tool
import app.tools.get_job_history_tool
import app.tools.job_discovery_tool
import app.tools.job_digest_tool
import app.tools.application_preparation_tool
import app.tools.application_tracking_tool
import app.tools.orchestration_status_tool
import app.tools.orchestration_control_tool
import app.tools.memory_tools
import app.tools.github_tools
import app.tools.audit_tools
import app.tools.integration_tools
import app.tools.local_coding_tools
import app.tools.local_git_tools

# Expose the registry
__all__ = ['registry']
