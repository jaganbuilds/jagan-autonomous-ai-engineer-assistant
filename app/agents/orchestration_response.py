from app.agents.orchestration_result import OrchestrationResult

class OrchestrationResponseMapper:
    @staticmethod
    def map_to_natural_response(result: OrchestrationResult) -> str:
        """Converts an OrchestrationResult into a concise, natural language response for the user."""
        if result.success:
            return "Orchestration completed successfully."
            
        if result.waiting_for_confirmation:
            return f"Orchestration paused. Waiting for confirmation on step {result.current_step + 1}."
            
        if result.status == "cancelled":
            return f"Orchestration cancelled. Step {result.current_step + 1} rejected."
            
        if result.status == "failed":
            if result.error and "Action rejected by human" in result.error:
                return f"Orchestration cancelled. Step {result.current_step + 1} rejected."
            return f"Orchestration failed at step {result.current_step + 1}. Error: {result.error}"
            
        return f"Orchestration stopped with status: {result.status}"
