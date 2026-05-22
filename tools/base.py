import inspect
from typing import Callable, Dict, Any, List, Optional
from utils.logging import logger

class ToolRegistry:
    """Central registry and dispatch controller for Agent plugins/tools."""
    
    def __init__(self):
        self._tools: Dict[str, Callable[..., Any]] = {}

    def register(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator to register a python function as a system tool."""
        name = func.__name__
        if name in self._tools:
            logger.warning(f"Overwriting already registered tool: {name}")
        self._tools[name] = func
        logger.debug(f"Registered tool plugin: '{name}'")
        return func

    def get_tool(self, name: str) -> Optional[Callable[..., Any]]:
        """Retrieves registered tool callable reference by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Callable[..., Any]]:
        """Lists all registered tool callables."""
        return list(self._tools.values())

    def execute_tool(self, name: str, **kwargs) -> str:
        """Invokes a registered tool dynamically with arguments and captures output as string.
        
        Args:
            name: Name of the registered tool function.
            kwargs: Parameters matching the function signature.
            
        Returns:
            String output of the tool execution (or error message if failed).
        """
        tool_func = self.get_tool(name)
        if not tool_func:
            return f"Error: Tool '{name}' is not registered."

        try:
            logger.info(f"Invoking Tool: '{name}' with args: {kwargs}")
            
            # If function is async, we run it in a separate event loop or run it synchronously
            # In our case, tools will be standard synchronous functions or we check if coroutine
            if inspect.iscoroutinefunction(tool_func):
                # Standard trick to run async in sync: run it in executor or run_until_complete
                # Since we run inside async orchestrator, let's keep all tools sync or let executor run them
                # For high reliability, let's write tools as sync, or support both gracefully
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    # If we have an active loop, we schedule it as task
                    future = asyncio.run_coroutine_threadsafe(tool_func(**kwargs), loop)
                    result = future.result()
                except RuntimeError:
                    # No active loop, use run
                    result = asyncio.run(tool_func(**kwargs))
            else:
                result = tool_func(**kwargs)

            # Cast results to string representation
            if result is None:
                return "Operation completed successfully with no return value."
            return str(result)

        except Exception as e:
            err_msg = f"Error executing tool '{name}': {e}"
            logger.error(err_msg, exc_info=True)
            return err_msg

# Instantiate registry globally
tool_registry = ToolRegistry()

def tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorates and registers helper functions as system plugins."""
    return tool_registry.register(func)
