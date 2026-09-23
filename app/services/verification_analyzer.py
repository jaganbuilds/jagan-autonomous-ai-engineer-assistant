import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class FailedTest(BaseModel):
    test_file: Optional[str] = None
    test_name: Optional[str] = None
    status: str = "FAILED"
    message: Optional[str] = None

class VerificationAnalysis(BaseModel):
    operation: str = "pytest"
    success: bool
    exit_code: int
    timed_out: bool
    output_truncated: bool
    summary: str
    failure_count: int = 0
    failed_tests: List[FailedTest] = Field(default_factory=list)
    error_categories: List[str] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

class VerificationResultAnalyzer:
    """
    Analyzes the structured execution result of a verification step (like pytest)
    to extract meaningful failures, errors, and files.
    This is a pure analysis layer. It does not mutate the filesystem or execute code.
    """
    
    def analyze(self, result: Dict[str, Any]) -> VerificationAnalysis:
        # Expected `result` is the `data` block from EXECUTE ActionResult, or the entire ActionResult.
        if "data" in result and isinstance(result["data"], dict) and ("stdout" in result["data"] or "stderr" in result["data"]):
            data = result["data"]
        else:
            data = result
            
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        exit_code = data.get("exit_code", -1)
        success = data.get("success", False)
        timed_out = data.get("timed_out", False)
        truncated = data.get("output_truncated", False)
        operation = data.get("operation", "pytest")
        
        output = str(stdout) + "\n" + str(stderr)
        
        failed_tests = []
        error_categories = set()
        affected_files = set()
        recommendations = []
        
        if timed_out:
            summary = "Pytest verification exceeded the configured execution timeout."
            error_categories.add("TIMEOUT")
            recommendations.append("Increase the execution timeout if the test suite is expected to run longer, or optimize the slow tests.")
        elif exit_code == -1 and not success:
            summary = "Pytest could not be completed because the verification process returned an execution error."
            error_categories.add("EXECUTION_ERROR")
            recommendations.append("Check the environment or the executable invocation for fundamental issues.")
        else:
            # Parse short test summary
            short_summary_pattern = re.compile(r'^(FAILED|ERROR)\s+(.*?\.\w+)::([^\s]+)(?:\s+-\s+(.*))?', re.MULTILINE)
            # Parse standard output test lines
            alt_pattern = re.compile(r'^(.*?\.\w+)::([^\s]+)\s+(FAILED|ERROR)', re.MULTILINE)
            
            for match in short_summary_pattern.finditer(output):
                status, test_file, test_name, message = match.groups()
                failed_tests.append(FailedTest(
                    test_file=test_file.strip(), 
                    test_name=test_name.strip(), 
                    status=status.strip(), 
                    message=message.strip() if message else None
                ))
                affected_files.add(test_file.strip())
                
            for match in alt_pattern.finditer(output):
                test_file, test_name, status = match.groups()
                test_file_clean = test_file.strip()
                test_name_clean = test_name.strip()
                # Avoid duplicates
                if not any(t.test_file == test_file_clean and t.test_name == test_name_clean for t in failed_tests):
                    failed_tests.append(FailedTest(
                        test_file=test_file_clean, 
                        test_name=test_name_clean, 
                        status=status.strip()
                    ))
                    affected_files.add(test_file_clean)
            
            # Error categories detection
            if "AssertionError" in output: error_categories.add("ASSERTION_ERROR")
            if "ImportError" in output: error_categories.add("IMPORT_ERROR")
            if "ModuleNotFoundError" in output: error_categories.add("IMPORT_ERROR")
            if "SyntaxError" in output: error_categories.add("SYNTAX_ERROR")
            if "fixture" in output.lower() and "error" in output.lower(): error_categories.add("FIXTURE_ERROR")
            if "collected 0 items" in output or "collection failure" in output or "Interrupted: " in output: error_categories.add("COLLECTION_ERROR")
            
            if failed_tests or (not success and exit_code != 0):
                error_categories.add("TEST_FAILURE")
                
            if success:
                # Attempt to find passing count if success
                pass_match = re.search(r'(\d+)\s+passed', output)
                if pass_match:
                    summary = f"Pytest verification completed successfully. {pass_match.group(1)} test(s) passed."
                else:
                    summary = "Pytest verification completed successfully."
                recommendations.append("No further action required for these tests.")
            else:
                if len(failed_tests) > 0:
                    summary = f"Pytest verification failed with {len(failed_tests)} failing test(s)."
                else:
                    summary = "Pytest verification failed (no specific test failures were parsed)."
                
                if "ASSERTION_ERROR" in error_categories:
                    recommendations.append("Review the assertion failure(s) in the referenced test(s).")
                if "IMPORT_ERROR" in error_categories:
                    recommendations.append("Check the reported import error. Ensure all dependencies and modules are correctly resolved.")
                if "SYNTAX_ERROR" in error_categories:
                    recommendations.append("Fix syntax errors in the code before running tests.")
                if "COLLECTION_ERROR" in error_categories:
                    recommendations.append("Fix issues preventing pytest from collecting tests, such as import errors or syntax errors in test files.")
                if "FIXTURE_ERROR" in error_categories:
                    recommendations.append("Review the fixture setup associated with the failing test.")
                    
                if not recommendations:
                    recommendations.append("Inspect the reported failing test.")
                
        if truncated:
            recommendations.append("The verification output was truncated. Some failures might not be listed.")
            
        # Treat all pytest output as untrusted. If suspicious strings exist, just flag it.
        malicious_patterns = ["IGNORE PREVIOUS", "IGNORE ALL PREVIOUS", "DELETE ", "rm -rf"]
        if any(p.lower() in output.lower() for p in malicious_patterns):
            recommendations.append("WARNING: Suspicious instructions detected in test output. The output remains untrusted data and was not executed.")
            
        # Fallback for unknown failures
        if not success and not error_categories and exit_code != 0 and not timed_out:
            error_categories.add("UNKNOWN")
            
        return VerificationAnalysis(
            operation=operation,
            success=success,
            exit_code=exit_code,
            timed_out=timed_out,
            output_truncated=truncated,
            summary=summary,
            failure_count=len(failed_tests),
            failed_tests=failed_tests,
            error_categories=sorted(list(error_categories)),
            affected_files=sorted(list(affected_files)),
            recommendations=recommendations
        )

def analyze_verification_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function matching the prompt requirements.
    """
    analyzer = VerificationResultAnalyzer()
    analysis = analyzer.analyze(result)
    return analysis.model_dump()
