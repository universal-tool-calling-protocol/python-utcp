import importlib.metadata

def _load_plugins():
    from utcp.plugins.discovery import register_auth, register_variable_loader, register_tool_repository, register_tool_search_strategy, register_tool_post_processor
    from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepositoryConfigSerializer
    from utcp.interfaces.tool_search_strategy import ToolSearchStrategyConfigSerializer
    from utcp.implementations.in_mem_tool_repository import InMemToolRepositoryConfigSerializer
    from utcp.implementations.tag_search import TagAndDescriptionWordMatchStrategyConfigSerializer
    from utcp.data.auth_implementations import OAuth2AuthSerializer, BasicAuthSerializer, ApiKeyAuthSerializer
    from utcp.data.variable_loader_implementations import DotEnvVariableLoaderSerializer
    from utcp.implementations.post_processors import FilterDictPostProcessorConfigSerializer, LimitStringsPostProcessorConfigSerializer

    register_auth("oauth2", OAuth2AuthSerializer())
    register_auth("basic", BasicAuthSerializer())
    register_auth("api_key", ApiKeyAuthSerializer())

    register_variable_loader("dotenv", DotEnvVariableLoaderSerializer())

    register_tool_repository(ConcurrentToolRepositoryConfigSerializer.default_repository, InMemToolRepositoryConfigSerializer())

    register_tool_search_strategy(ToolSearchStrategyConfigSerializer.default_strategy, TagAndDescriptionWordMatchStrategyConfigSerializer())

    register_tool_post_processor("filter_dict", FilterDictPostProcessorConfigSerializer())
    register_tool_post_processor("limit_strings", LimitStringsPostProcessorConfigSerializer())

    for ep in importlib.metadata.entry_points(group="utcp.plugins"):
        register_func = ep.load()
        register_func()

plugins_initialized = False
loading_plugins = False

def ensure_plugins_initialized():
    global plugins_initialized
    global loading_plugins
    if plugins_initialized:
        return
    if loading_plugins:
        return
    loading_plugins = True
    try:
        _load_plugins()
        plugins_initialized = True
    finally:
        loading_plugins = False
