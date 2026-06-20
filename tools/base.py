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

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """Converts registered tools into OpenAI/Groq compatible JSON schemas."""
        schemas = []
        for name, func in self._tools.items():
            sig = inspect.signature(func)
            doc = inspect.getdoc(func) or f"Tool {name}"
            
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                param_type = "string"
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation is int: param_type = "integer"
                    elif param.annotation is bool: param_type = "boolean"
                    elif param.annotation is float: param_type = "number"
                
                properties[param_name] = {"type": param_type}
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                    
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": doc.split('\\n')[0][:1024],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })
        return schemas

    def list_tools(self) -> List[Callable[..., Any]]:
        """Lists all registered tool callables."""
        return list(self._tools.values())

    async def execute_tool(self, name: str, **kwargs) -> str:
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
            
            if inspect.iscoroutinefunction(tool_func):
                result = await tool_func(**kwargs)
            else:
                result = tool_func(**kwargs)

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
