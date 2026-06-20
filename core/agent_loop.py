import json
import asyncio
from typing import Callable, List, Dict, Any, Optional
from groq import Groq
from config.settings import settings
from utils.logging import logger
from storage.memory import MemoryManager
from security.guardrails import CommandGuard, SecurityLevel
from core.executor import CommandExecutor
from tools.base import tool_registry, tool

# Register shell execution directly as a first-class system tool
@tool
async def run_system_shell_command(command: str) -> str:
    """Executes a native command inside the host operating system's terminal shell.
    
    Args:
        command: The shell command string to execute (e.g. 'mkdir projects' or 'dir').
        
    Returns:
        The text outputs of stdout/stderr from the executed shell process.
    """
    executor = CommandExecutor()
    res = await executor.execute(command)
    
    output = ""
    if res.stdout:
        output += f"--- STDOUT ---\n{res.stdout.strip()}\n"
    if res.stderr:
        output += f"--- STDERR ---\n{res.stderr.strip()}\n"
    
    if not output:
        output = "Command completed with empty outputs."
        
    return f"Exit Code: {res.exit_code}\n{output}"

class AgentLoop:
    """Orchestrates ReAct agent operations securely with Groq SDK."""

    def __init__(
        self,
        session_id: str,
        confirm_callback: Optional[Callable[[str, str], bool]] = None
    ):
        self.session_id = session_id
        self.memory = MemoryManager()
        self.confirm_callback = confirm_callback or self._default_confirm

        self.system_instruction = (
            "You are GenAIShell, an expert terminal shell assistant.\n"
            "Your objective is to translate natural language goals into precise terminal actions, "
            "explain diagnostics, search resources, or modify files.\n\n"
            "OPERATING GUIDELINES:\n"
            "1. You have a set of local system tools at your disposal (like listing processes, file operations, git).\n"
            "2. To run standard terminal shells, invoke the tool `run_system_shell_command` with your command.\n"
            "3. CONVERSATIONAL PERMISSION: Before running ANY shell commands or file modifications, you MUST first explain exactly what commands you plan to run and explicitly ask the user for permission in your chat response. DO NOT invoke the tool until the user replies with 'yes' or 'go ahead'.\n"
            "4. IMPORTANT EXECUTIONS: When the user grants permission (e.g. says 'yes'), you MUST immediately use the provided tool-calling API to execute the command. Do NOT just say 'Okay, I will do it' and stop. You MUST trigger the function natively!\n"
            "5. If a shell command or tool operation is blocked or fails, analyze the error and try a different safe route.\n"
            "6. Make sure commands are compatible with the user's current shell environment.\n"
            "7. Break complex requests down into sequential tool invocations."
        )

        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Please add it to your .env file:\n"
                "  GROQ_API_KEY=your_key_here"
            )
        self.client = Groq(api_key=settings.groq_api_key)
        self.model_name = settings.groq_model
        logger.info("Groq API client configured successfully.")
        
        self.history = []
        self._load_chat_history()

    def _default_confirm(self, command: str, reason: str) -> bool:
        print(f"\n[bold yellow][SECURITY INTERCEPT][/bold yellow]")
        print(f"Action: {command}")
        print(f"Reason: {reason}")
        ans = input("Do you authorize executing this action? (y/N): ").strip().lower()
        return ans in ("y", "yes")

    def _load_chat_history(self) -> None:
        self.history = [{"role": "system", "content": self.system_instruction}]
        db_messages = self.memory.get_messages(self.session_id, limit=20)
        if not db_messages:
            return

        for msg in db_messages:
            role = "user" if msg["role"] == "user" else "assistant"
            self.history.append({"role": role, "content": msg["content"]})
        logger.debug(f"Synced {len(db_messages)} messages from storage.")

    async def execute_goal(self, user_prompt: str, streaming_callback: Optional[Callable[[str], None]] = None) -> str:
        self.memory.add_message(self.session_id, "user", user_prompt)
        self.history.append({"role": "user", "content": user_prompt})
        
        max_steps = 6
        step = 0
        logger.info(f"Initiating Agent loop for session {self.session_id} - Goal: '{user_prompt}'")

        while step < max_steps:
            step += 1
            logger.debug(f"ReAct Loop Step {step}/{max_steps}")

            retries = 3
            backoff = 5
            response = None
            for attempt in range(retries):
                try:
                    # Execute Groq API Call
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=self.history,
                        tools=tool_registry.get_openai_schemas(),
                        tool_choice="auto"
                    )
                    break
                except Exception as e:
                    if attempt == retries - 1:
                        logger.error("API error hit repeatedly. Exceeded max retries.")
                        raise e
                    logger.warning(f"API Error. Retrying in {backoff} seconds... (Attempt {attempt+1}/{retries})")
                    await asyncio.sleep(backoff)
                    backoff *= 2

            message = response.choices[0].message

            # If no tool calls, generation is complete
            if not message.tool_calls:
                final_text = message.content or ""
                
                # Intercept Llama 3 tool hallucinations
                if "<function" in final_text or "{\"command\":" in final_text:
                    logger.warning("Intercepted Llama 3 tool hallucination tag. Forcing retry.")
                    self.history.append({"role": "assistant", "content": final_text})
                    self.history.append({
                        "role": "user", 
                        "content": "You wrote the function call as raw text instead of using the native tool API. You MUST trigger the function natively using the API now!"
                    })
                    continue
                
                self.memory.add_message(self.session_id, "model", final_text)
                if streaming_callback:
                    streaming_callback(final_text)
                return final_text

            # Add the model's tool calls to the history
            self.history.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [t.model_dump() for t in message.tool_calls]
            })

            # Execute tools
            for tool_call in message.tool_calls:
                name = tool_call.function.name
                args = {}
                if tool_call.function.arguments:
                    args = json.loads(tool_call.function.arguments)
                
                is_safe = True
                explanation = "Action classified as safe."

                if name == "run_system_shell_command":
                    command_str = args.get("command", "")
                    sec_level, explanation = CommandGuard.analyze_command(command_str)
                    
                    if sec_level == SecurityLevel.BLOCKED:
                        tool_result = f"Security Error: Command blocked by system guardrails. Reason: {explanation}"
                        self.memory.log_command(self.session_id, command_str, tool_result, -1, is_blocked=True)
                        is_safe = False
                    elif sec_level == SecurityLevel.RISKY:
                        logger.info(f"Triggering security callback confirmation for command: {command_str}")
                        user_approved = self.confirm_callback(command_str, explanation)
                        if not user_approved:
                            tool_result = "Security Error: Command execution denied by the user."
                            self.memory.log_command(self.session_id, command_str, tool_result, -1, is_blocked=True)
                            is_safe = False
                
                elif name in ("kill_process_by_port", "create_file"):
                    explanation = f"Tool '{name}' executes file modification or system process termination actions."
                    if settings.safe_mode_enabled:
                        logger.info(f"Triggering security callback for tool: {name}")
                        user_approved = self.confirm_callback(f"Tool Call: {name}({args})", explanation)
                        if not user_approved:
                            tool_result = "Security Error: Tool execution denied by the user."
                            is_safe = False

                if is_safe:
                    if streaming_callback:
                        streaming_callback(f"[dim italic]Executing tool: {name}...[/dim italic]\n")
                    
                    tool_result = await tool_registry.execute_tool(name, **args)
                    
                    if name == "run_system_shell_command":
                        cmd_str = args.get("command", "")
                        exit_code = 0 if "Exit Code: 0" in tool_result else -1
                        self.memory.log_command(self.session_id, cmd_str, tool_result, exit_code)

                # Append tool result to history
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": name,
                    "content": tool_result
                })

        timeout_msg = "Error: Multi-step planning execution limit reached without resolving final state."
        logger.error(timeout_msg)
        self.memory.add_message(self.session_id, "model", timeout_msg)
        return timeout_msg
