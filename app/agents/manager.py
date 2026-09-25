import logging
from typing import Dict, Any, List
import json

from app.config import get_settings
from app.tools import registry
from app.agents.state import state_manager, SessionStatus
from app.agents.router import router, Intent
from app.llm.gateway import gateway
from app.llm.models import ChatMessage, ToolCall, LLMUnavailableError, LLMTimeoutError, LLMError

logger = logging.getLogger(__name__)

class ManagerAgent:
    def __init__(self):
        settings = get_settings()
        self._chats: Dict[str, List[ChatMessage]] = {}
        
        self.system_instruction = (
            "You are Jagan AI, a helpful and expert AI Engineer Assistant. "
            "You have access to tools. Use them when necessary to fulfill the user's request. "
            "Always explain what you are doing before or after using a tool."
        )

    def _get_chat(self, session_id: str) -> List[ChatMessage]:
        if session_id not in self._chats:
            self._chats[session_id] = [
                ChatMessage(role="system", content=self.system_instruction)
            ]
        return self._chats[session_id]

    def _execute_tool(self, name: str, args: Dict[str, Any], session_id: str = "default") -> str:
        """Executes a tool from the registry and returns the result."""
        tool_func = registry.get_tool(name)
        if not tool_func:
            return f'{{"status": "error", "error": "Tool {name} not found"}}'
        
        import inspect
        sig = inspect.signature(tool_func)
        if "session_id" in sig.parameters:
            args["session_id"] = session_id
        result = tool_func(**args)
            
        return result

    def process_message(self, message: str, session_id: str = "default") -> str:
        """
        Processes a user message through the TaskRouter, StateManager, and LLM Gateway.
        Handles multi-step tool execution and confirmation intercepts.
        """
        chat_history = self._get_chat(session_id)
        session = state_manager.get_session(session_id)
        
        try:
            # 1. Handle Confirmations / Resumes
            if session.status == SessionStatus.WAITING_FOR_CONFIRMATION:
                msg_lower = message.strip().lower()
                
                # Check if this confirmation belongs to an active orchestration plan
                from app.agents.orchestration import orchestrator, TaskState
                plan = orchestrator.get_plan(session_id)
                is_orchestrating = plan and plan.status == TaskState.WAITING_FOR_CONFIRMATION
                
                # Check for pending email action
                if session.pending_email_action or (session.pending_gateway_action and session.pending_gateway_action.get("request").integration == "gmail"):
                    from app.agents.confirmation import confirmation_manager
                    
                    if msg_lower in ['yes', 'y', 'confirm', 'send it', 'send', 'approve', 'proceed', 'go ahead', 'ஆமாம்', 'சரி', 'அனுப்பு', 'aama', 'seri', 'anuppu']:
                        logger.info("User confirmed email sending.")
                        
                        if is_orchestrating:
                            result = confirmation_manager.confirm_email(session_id)
                            orchestrator.resume_after_confirmation(session_id, approved=True, native_result=result)
                            
                            from app.agents.orchestration_response import OrchestrationResponseMapper
                            orch_result = orchestrator.run_orchestration(session_id)
                            if orch_result.terminal:
                                state_manager.update_status(session_id, SessionStatus.IDLE)
                            return OrchestrationResponseMapper.map_to_natural_response(orch_result)
                                
                        else:
                            result = confirmation_manager.confirm_email(session_id)
                            chat_history.append(ChatMessage(
                                role="tool",
                                tool_call_id=session.pending_tool_call.get('id', 'call_0') if session.pending_tool_call else 'call_0',
                                name="send_email",
                                content=json.dumps({"result": result})
                            ))
                            response = gateway.chat(chat_history, tools=registry.get_all_tools())
                    
                    elif msg_lower in ['no', 'n', 'reject', 'cancel', "don't send", 'stop', 'வேண்டாம்', 'நிறுத்து', 'vendam']:
                        logger.info("User rejected email sending.")
                        
                        if is_orchestrating:
                            orchestrator.resume_after_confirmation(session_id, approved=False)
                            from app.agents.orchestration_response import OrchestrationResponseMapper
                            orch_result = orchestrator.run_orchestration(session_id)
                            state_manager.update_status(session_id, SessionStatus.IDLE)
                            return OrchestrationResponseMapper.map_to_natural_response(orch_result)
                        else:
                            result = confirmation_manager.reject_email(session_id)
                            chat_history.append(ChatMessage(
                                role="tool",
                                tool_call_id=session.pending_tool_call.get('id', 'call_0') if session.pending_tool_call else 'call_0',
                                name="send_email",
                                content=json.dumps({"result": result})
                            ))
                            response = gateway.chat(chat_history, tools=registry.get_all_tools())
                        
                    else:
                        return "Please clearly reply 'yes' to send the email or 'no' to cancel."

                # Check for pending consolidation action
                elif session.pending_consolidation_action:
                    from app.agents.confirmation import confirmation_manager
                    
                    if msg_lower in ['yes', 'y', 'confirm', 'approve', 'proceed', 'go ahead', 'do it']:
                        logger.info("User confirmed memory consolidation.")
                        result = confirmation_manager.confirm_consolidation(session_id)
                        
                        if is_orchestrating:
                            orchestrator.resume_after_confirmation(session_id, approved=True, native_result=result)
                            from app.agents.orchestration_response import OrchestrationResponseMapper
                            orch_result = orchestrator.run_orchestration(session_id)
                            if orch_result.terminal:
                                state_manager.update_status(session_id, SessionStatus.IDLE)
                            return OrchestrationResponseMapper.map_to_natural_response(orch_result)
                        else:
                            chat_history.append(ChatMessage(
                                role="tool",
                                tool_call_id=session.pending_tool_call.get('id', 'call_0'),
                                name="consolidate_memories",
                                content=json.dumps({"result": result})
                            ))
                            response = gateway.chat(chat_history, tools=registry.get_all_tools())
                            
                    elif msg_lower in ['no', 'n', 'reject', 'cancel', 'stop']:
                        logger.info("User rejected memory consolidation.")
                        result = confirmation_manager.reject_consolidation(session_id)
                        
                        if is_orchestrating:
                            orchestrator.resume_after_confirmation(session_id, approved=False)
                            from app.agents.orchestration_response import OrchestrationResponseMapper
                            orch_result = orchestrator.run_orchestration(session_id)
                            state_manager.update_status(session_id, SessionStatus.IDLE)
                            return OrchestrationResponseMapper.map_to_natural_response(orch_result)
                        else:
                            chat_history.append(ChatMessage(
                                role="tool",
                                tool_call_id=session.pending_tool_call.get('id', 'call_0'),
                                name="consolidate_memories",
                                content=json.dumps({"result": result})
                            ))
                            response = gateway.chat(chat_history, tools=registry.get_all_tools())
                            
                    else:
                        return "Please clearly reply 'yes' to apply the memory consolidation or 'no' to cancel."

                # Check for standard pending tool call
                elif session.pending_tool_call:
                    if msg_lower in ['yes', 'y', 'confirm', 'approve', 'proceed', 'go ahead', 'ஆமாம்', 'சரி', 'அனுப்பு', 'aama', 'seri', 'anuppu']:
                        tool_name = session.pending_tool_call['name']
                        tool_args = session.pending_tool_call['args']
                        tool_id = session.pending_tool_call.get('id', 'call_0')
                        
                        logger.info(f"User confirmed execution of {tool_name}")
                        
                        if is_orchestrating:
                            orchestrator.resume_after_confirmation(session_id, approved=True)
                            
                            from app.agents.orchestration_response import OrchestrationResponseMapper
                            orch_result = orchestrator.run_orchestration(session_id)
                            if orch_result.terminal:
                                state_manager.update_status(session_id, SessionStatus.IDLE)
                            return OrchestrationResponseMapper.map_to_natural_response(orch_result)
                                
                        else:
                            result = self._execute_tool(tool_name, tool_args, session_id)
                            state_manager.clear_pending_tool(session_id)
                            
                            chat_history.append(ChatMessage(
                                role="tool",
                                tool_call_id=tool_id,
                                name=tool_name,
                                content=json.dumps({"result": result})
                            ))
                            response = gateway.chat(chat_history, tools=registry.get_all_tools())
                    
                    elif msg_lower in ['no', 'n', 'reject', 'cancel', 'stop', 'வேண்டாம்', 'நிறுத்து', 'vendam']:
                        if is_orchestrating:
                            orchestrator.resume_after_confirmation(session_id, approved=False)
                            from app.agents.orchestration_response import OrchestrationResponseMapper
                            orch_result = orchestrator.run_orchestration(session_id)
                            state_manager.update_status(session_id, SessionStatus.IDLE)
                            return OrchestrationResponseMapper.map_to_natural_response(orch_result)
                        else:
                            state_manager.clear_pending_tool(session_id)
                            return "Action cancelled."
                    else:
                        return "Please clearly reply 'yes' to approve or 'no' to cancel the pending action."
                else:
                    # Should not reach here if WAITING_FOR_CONFIRMATION is set correctly
                    state_manager.update_status(session_id, SessionStatus.IDLE)
                    chat_history.append(ChatMessage(role="user", content=message))
                    response = gateway.chat(chat_history, tools=registry.get_all_tools())
            else:
                # 2. Normal Flow
                state_manager.update_status(session_id, SessionStatus.PROCESSING)
                
                # --- MEMORY RETRIEVAL ---
                memory_context = ""
                try:
                    from app.memory.retrieval import build_memory_context
                    memory_context = build_memory_context(session_id, message)
                except Exception as e:
                    logger.error(f"Memory retrieval failed: {e}")
                    
                augmented_message = message + memory_context if memory_context else message
                # ------------------------
                
                # --- MEMORY EXTRACTION ---
                try:
                    from app.memory.extractor import memory_extractor
                    from app.memory.service import memory_service
                    extraction_result = memory_extractor.extract(message)
                    if extraction_result.has_memory:
                        for candidate in extraction_result.candidates:
                            memory_service.remember(
                                session_id=session_id,
                                content=candidate.content,
                                memory_type=candidate.memory_type,
                                source=candidate.source,
                                confidence=candidate.confidence
                            )
                except Exception as e:
                    logger.error(f"Memory extraction failed: {e}")
                # -------------------------
                
                # Route the intent
                route_result = router.route(augmented_message)
                logger.info(f"Detected intent: {route_result.intent}")
                
                if route_result.intent == Intent.ORCHESTRATION:
                    from app.agents.planner import planner
                    from app.agents.orchestration import orchestrator, TaskState
                    
                    plan = planner.create_plan_for_goal(session_id, augmented_message)
                    
                    if plan.steps[0].tool_name == "unknown_tool":
                        state_manager.update_status(session_id, SessionStatus.IDLE)
                        return "I am unable to orchestrate this goal because some required capabilities are not supported."
                    else:
                        from app.agents.orchestration_response import OrchestrationResponseMapper
                        orch_result = orchestrator.run_orchestration(session_id)
                        if orch_result.terminal:
                            state_manager.update_status(session_id, SessionStatus.IDLE)
                        return OrchestrationResponseMapper.map_to_natural_response(orch_result)
                
                else:
                    chat_history.append(ChatMessage(role="user", content=augmented_message))
                    response = gateway.chat(chat_history, tools=registry.get_all_tools())

            # 3. Process Function Calls (Manual Loop)
            # This loop handles tools both for the Normal Flow and Confirmation resumes
            while True:
                # Add assistant message to history before processing it
                if response.tool_calls:
                    chat_history.append(ChatMessage(
                        role="assistant",
                        content=response.text,
                        tool_calls=response.tool_calls
                    ))
                else:
                    if response.text:
                        chat_history.append(ChatMessage(
                            role="assistant",
                            content=response.text
                        ))
                    if session.status != SessionStatus.WAITING_FOR_CONFIRMATION:
                        state_manager.update_status(session_id, SessionStatus.IDLE)
                    return response.text or "Success"
                
                # For simplicity, handle the first function call in this turn
                call = response.tool_calls[0]
                tool_name = call.name
                tool_args = call.arguments
                tool_id = call.id
                
                if registry.requires_confirmation(tool_name):
                    # Intercept!
                    state_manager.set_pending_tool(session_id, tool_name, tool_args)
                    # We must store id to respond properly after confirmation
                    session = state_manager.get_session(session_id)
                    if session.pending_tool_call:
                        session.pending_tool_call['id'] = tool_id
                    return f"The agent wants to execute '{tool_name}' with arguments {tool_args}. Shall I proceed? (Yes/No)"
                else:
                    # Execute normally and loop
                    logger.info(f"Executing tool {tool_name} automatically...")
                    result = self._execute_tool(tool_name, tool_args, session_id)
                    chat_history.append(ChatMessage(
                        role="tool",
                        tool_call_id=tool_id,
                        name=tool_name,
                        content=json.dumps({"result": result})
                    ))
                    response = gateway.chat(chat_history, tools=registry.get_all_tools())
                    
        except Exception as e:
            state_manager.update_status(session_id, SessionStatus.ERROR)
            logger.error(f"Error processing message: {e}")
            if isinstance(e, LLMUnavailableError):
                return "The AI model is temporarily unavailable. Please try again later."
            if isinstance(e, LLMTimeoutError) or "deadline" in str(e).lower() or "timeout" in str(e).lower():
                return "The AI model is temporarily unavailable. Please try again later."
            return f"Error: Failed to process message. Details: {str(e)}"
