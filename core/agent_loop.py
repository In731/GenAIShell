import asyncio
from typing import Callable, List, Dict, Any, Optional
import google.generativeai as genai
from google.generativeai.types import content_types
from google.api_core.exceptions import ResourceExhausted
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
    
    # Return formatted result
    output = ""
    if res.stdout:
        output += f"--- STDOUT ---\n{res.stdout.strip()}\n"
    if res.stderr:
        output += f"--- STDERR ---\n{res.stderr.strip()}\n"
    
    if not output:
        output = "Command completed with empty outputs."
        
    return f"Exit Code: {res.exit_code}\n{output}"


class AgentLoop:
    """Orchestrates ReAct agent operations, executing multi-step goals securely with User-in-the-Loop validations."""

    def __init__(
        self,
        session_id: str,
        confirm_callback: Optional[Callable[[str, str], bool]] = None
    ):
        """
        Args:
            session_id: Persistence identifier for SQLite history.
            confirm_callback: Injectable user prompt callback (takes command_string, explanation and returns bool).
        """
        self.session_id = session_id
        self.memory = MemoryManager()
        # Default fallback synchronous terminal confirmation check if no callback injected
        self.confirm_callback = confirm_callback or self._default_confirm

        # Build System Instructions establishing system boundaries
        self.system_instruction = (
            "You are GenAIShell, an expert GenAI terminal shell assistant.\n"
            "Your objective is to translate natural language goals into precise terminal actions, "
            "explain diagnostics, search resources, or modify files.\n\n"
            "OPERATING GUIDELINES:\n"
            "1. You have a set of local system tools at your disposal (like listing processes, file operations, git).\n"
            "2. To run standard terminal shells, invoke the tool `run_system_shell_command` with your command.\n"
            "3. ALWAYS explain your plan to the user in short sentences before running tools.\n"
            "4. If a shell command or tool operation is blocked or fails, analyze the error and try a different safe route.\n"
            "5. Make sure commands are compatible with the user's current shell environment.\n"
            "6. Break complex requests down into sequential tool invocations (multi-step planning)."
        )

        # Configure the Gemini SDK with the API key from .env BEFORE creating the model.
        # Without this call the SDK has no key and raises "No API_KEY or ADC found".
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please add it to your .env file:\n"
                "  GEMINI_API_KEY=your_key_here"
            )
        genai.configure(api_key=settings.gemini_api_key)
        logger.info("Gemini API key configured successfully.")

        # Initialize the Gemini Model with all registered tools
        self.model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            tools=tool_registry.list_tools(),
            system_instruction=self.system_instruction
        )
        self.chat = self.model.start_chat()
        self._load_chat_history()

    def _default_confirm(self, command: str, reason: str) -> bool:
        """Fallback console confirmation prompter."""
        print(f"\n[bold yellow][SECURITY INTERCEPT][/bold yellow]")
        print(f"Action: {command}")
        print(f"Reason: {reason}")
        ans = input("Do you authorize executing this action? (y/N): ").strip().lower()
        return ans in ("y", "yes")

    def _load_chat_history(self) -> None:
        """Syncs the Gemini API chat context memory with SQLite's session database."""
        db_messages = self.memory.get_messages(self.session_id, limit=20)
        if not db_messages:
            return

        # Pre-populate history in the active Gemini conversation channel
        history = []
        for msg in db_messages:
            role = msg["role"]
            content = msg["content"]
            # Convert roles to Gemini spec (Gemini uses 'user' and 'model')
            gemini_role = "user" if role == "user" else "model"
            history.append(
                content_types.Content(
                    role=gemini_role,
                    parts=[content_types.Part.from_text(text=content)]
                )
            )
        self.chat.history = history
        logger.debug(f"Synced {len(history)} messages from persistent storage into active session.")

    async def execute_goal(self, user_prompt: str, streaming_callback: Optional[Callable[[str], None]] = None) -> str:
        """Runs the ReAct execution loop, coordinating multi-step actions to satisfy the high-level user goal.
        
        Args:
            user_prompt: Natural language command typed by user.
            streaming_callback: Optional function to pipe output streams back to the UI.
            
        Returns:
            The final conversational response text.
        """
        # Save user message to persistent DB
        self.memory.add_message(self.session_id, "user", user_prompt)
        
        current_prompt = user_prompt
        max_steps = 6
        step = 0
        
        logger.info(f"Initiating Agent loop for session {self.session_id} - Goal: '{user_prompt}'")

        while step < max_steps:
            step += 1
            logger.debug(f"ReAct Loop Step {step}/{max_steps}")

            # Send prompt and wait for generation response (with rate-limit retry support)
            response = None
            retries = 3
            backoff = 5
            for attempt in range(retries):
                try:
                    response = self.chat.send_message(current_prompt)
                    break
                except ResourceExhausted as e:
                    if attempt == retries - 1:
                        logger.error("Rate limit hit repeatedly. Exceeded max retries.")
                        raise e
                    logger.warning(f"Rate limit hit (429). Retrying in {backoff} seconds... (Attempt {attempt+1}/{retries})")
                    print(f"\n[bold yellow][RATE LIMIT INTERCEPT][/bold yellow] Quota exceeded. Waiting {backoff} seconds to retry...\n")
                    await asyncio.sleep(backoff)
                    backoff *= 2

            # Check if Gemini wants to invoke a tool
            tool_calls = response.candidates[0].content.parts
            function_calls = [part.function_call for part in tool_calls if part.function_call]

            if not function_calls:
                # No function calls means agent finished reasoning!
                final_text = response.text
                self.memory.add_message(self.session_id, "model", final_text)
                
                # Render to CLI stream if callback attached
                if streaming_callback:
                    streaming_callback(final_text)
                return final_text

            # Execute tool calls
            for call in function_calls:
                name = call.name
                args = dict(call.args)
                
                # Check safety boundary (Guardrails validation)
                is_safe = True
                explanation = "Action classified as safe."

                # If the tool is shell command run, we analyze the command string directly
                if name == "run_system_shell_command":
                    command_str = args.get("command", "")
                    sec_level, explanation = CommandGuard.analyze_command(command_str)
                    
                    if sec_level == SecurityLevel.BLOCKED:
                        # Hard block immediate halt
                        tool_result = f"Security Error: Command blocked by system guardrails. Reason: {explanation}"
                        self.memory.log_command(self.session_id, command_str, tool_result, -1, is_blocked=True)
                        is_safe = False
                    elif sec_level == SecurityLevel.RISKY:
                        # Risk confirmation request
                        logger.info(f"Triggering security callback confirmation for command: {command_str}")
                        user_approved = self.confirm_callback(command_str, explanation)
                        if not user_approved:
                            tool_result = "Security Error: Command execution denied by the user."
                            self.memory.log_command(self.session_id, command_str, tool_result, -1, is_blocked=True)
                            is_safe = False
                
                # General non-shell tools can also trigger confirmation checking (e.g. killing ports or removing files)
                elif name in ("kill_process_by_port", "create_file"):
                    explanation = f"Tool '{name}' executes file modification or system process termination actions."
                    if settings.safe_mode_enabled:
                        logger.info(f"Triggering security callback for tool: {name}")
                        user_approved = self.confirm_callback(f"Tool Call: {name}({args})", explanation)
                        if not user_approved:
                            tool_result = "Security Error: Tool execution denied by the user."
                            is_safe = False

                # Trigger execution if passed checks
                if is_safe:
                    if streaming_callback:
                        streaming_callback(f"[dim italic]Executing tool: {name}...[/dim italic]\n")
                    
                    tool_result = tool_registry.execute_tool(name, **args)
                    
                    # Log run command metrics if shell
                    if name == "run_system_shell_command":
                        cmd_str = args.get("command", "")
                        # Try parsing code if present
                        exit_code = 0 if "Exit Code: 0" in tool_result else -1
                        self.memory.log_command(self.session_id, cmd_str, tool_result, exit_code)

                # Feed tool result back to Gemini Chat Session history as a function part
                part = content_types.Part.from_function_response(
                    name=name,
                    response={"result": tool_result}
                )
                
                # Feed back as next message to Gemini
                # We update the current_prompt reference to loop again with the tool output
                current_prompt = part

        # Reach here if loop steps exceeded
        timeout_msg = "Error: Multi-step planning execution limit reached without resolving final state."
        logger.error(timeout_msg)
        self.memory.add_message(self.session_id, "model", timeout_msg)
        return timeout_msg
