from pydantic import BaseModel, Extra


class Config(BaseModel, extra=Extra.ignore):
    DbPath: str = "mcs.db"
    QueryInterval: int = 10
    

    class format:
        server_title = (
            "=== {server_name} ==="
        )
        server_java_msg = (
            "服务器ip: {server_host}:{server_port}\n"
            "服务器版本: {server_version}\n"
            "在线人数: {server_players_online}/{server_players_max}\n"
            "ping: {server_latency}ms\n"
            "图标: {server_favicon}"
        )
        server_bedrock_msg = (
            "服务器ip: {server_host}:{server_port}\n"
            "服务器版本: {server_version} \n"
            "在线人数: {server_players_online}/{server_players_max}\n"
            "ping: {server_latency}ms\n"
        )
        server_offline = (
            "服务器ip: {server_host}:{server_port}\n"
            "服务器离线"
        )

        server_state_change_online = (
            "服务器: {server_name}({server_host}:{server_port} {server_type}) 状态改变 离线=>在线"
        )

        server_state_change_offline = (
            "服务器: {server_name}({server_host}:{server_port} {server_type}) 状态改变 在线=>离线"
        )
