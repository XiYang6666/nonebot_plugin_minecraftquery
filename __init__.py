from pathlib import Path
import hashlib
import base64
import os
import asyncio
import time
import typing
import json
import re

import nonebot
from nonebot import get_driver, get_bot, get_bots, require, on_command, on_shell_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot.internal.adapter.bot import Bot
from nonebot.log import logger
from nonebot.params import ShellCommandArgs
from argparse import Namespace
import mcstatus


require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .config import Config
global_config = get_driver().config
plugin_config = Config.parse_obj(global_config)


class Server:
    """
    服务器类
    提供查询服务器状态,判断服务器在线状态是否改变等功能
    """

    def __init__(self, name: str, type: str, host: str, port: int):
        self.name = name
        self.type = type.lower()
        self.host = host
        self.port = port
        assert self.type in ["java", "bedrock"]
        if self.type == "java":
            self.server = mcstatus.JavaServer(self.host, self.port)
        elif self.type == "bedrock":
            self.server = mcstatus.BedrockServer(self.host, self.port)

        self.last_online_status = None

    async def status(self):
        """
        获取服务器状态
        """
        try:
            return await self.server.async_status()
        except:
            return None

    async def get_online_status(self):
        """
        获取在线状态
        """
        if await self.status() is None:
            return "offline"
        else:
            return "online"

    async def is_online_status_changed(self):
        """
        在线状态是否改变
        """
        online_status = await self.get_online_status()
        if online_status != self.last_online_status and not self.last_online_status is None:
            self.last_online_status = online_status
            return online_status
        else:
            self.last_online_status = online_status
            return False

    def get_format_dict(self):
        return {
            "server_name": self.name,
            "server_type": self.type,
            "server_host": self.host,
            "server_port": self.port,
        }

    async def get_status_msg(self):
        """
        获取服务器消息
        """
        format_data = self.get_format_dict()
        server_status = await self.status()
        if not server_status is None:
            """
            所有服务器公有
            """
            format_data["server_latency"] = int(server_status.latency)
        else:
            """
            服务器离线
            """
            return Message.template(
                f"{plugin_config.format.server_title}\n"
                f"{plugin_config.format.server_offline}"
            ).format(**format_data)
        if self.type == "java" and not server_status is None:
            """
            JAVA服务器
            """
            assert isinstance(server_status, mcstatus.pinger.PingResponse)
            # 处理服务器图标
            server_favicon_data = base64.b64decode(server_status.favicon.split(",")[1])  # type: ignore
            server_favicon_filename = hashlib.sha256(server_favicon_data).hexdigest() + ".png"
            with open(f"mcQuery/favicon/{server_favicon_filename}", "wb") as f:
                f.write(server_favicon_data)
            format_data["server_favicon_dataLink"] = server_status.favicon
            format_data["server_favicon_filename"] = server_favicon_filename
            format_data["server_favicon_path"] = f"{os.getcwd()}\\mcQuery\\favicon\\{server_favicon_filename}"
            format_data["server_favicon"] = MessageSegment.image(server_favicon_data)
            # 处理服务器版本
            format_data["server_version"] = server_status.version.name
            format_data["server_version_name"] = server_status.version.name
            format_data["server_version_protocol"] = server_status.version.protocol
            # 处理玩家数量
            format_data["server_players_max"] = server_status.players.max
            format_data["server_players_online"] = server_status.players.online
            return Message.template(
                f"{plugin_config.format.server_title}\n"
                f"{plugin_config.format.server_java_msg}"
            ).format(**format_data)
        elif self.type == "bedrock" and not server_status is None:
            """
            基岩服务器
            """
            assert isinstance(server_status, mcstatus.bedrock_status.BedrockStatusResponse)
            # 处理服务器版本
            format_data["server_version"] = server_status.version.brand + " " + server_status.version.version
            format_data["server_version_brand"] = server_status.version.brand
            format_data["server_version_protocol"] = server_status.version.protocol
            # 处理玩家数量
            format_data["server_players_max"] = server_status.players_max
            format_data["server_players_online"] = server_status.players_online

            return Message.template(
                f"{plugin_config.format.server_title}\n"
                f"{plugin_config.format.server_bedrock_msg}"
            ).format(**format_data)
        else:
            return Message.template(
                f"{plugin_config.format.server_title}\n"
                f"未知错误"
            ).format(**format_data)


class Group:
    """
    群聊类
    包含群聊关注服务器等信息
    """

    def __init__(self, group_id: str | int, enable_query: bool = True, servers: list[Server] = []) -> None:
        self.group_id = int(group_id)
        self.enable_query = enable_query
        self.servers = servers

    def load_config(self, config: dict):
        """
        从字典中加载
        """
        self.enable_query = config["enable_query"]
        self.servers = []
        for server_data in config["servers"]:
            server = Server(
                name=server_data["name"],
                type=server_data["type"],
                host=server_data["host"],
                port=server_data["port"]
            )
            self.servers.append(server)
        return self

    def send_message(self, message: str):
        """
        向群聊发送消息
        """


def init_folder():
    if not os.path.exists("mcQuery"):
        os.mkdir("mcQuery")
    if not os.path.exists("mcQuery\\favicon"):
        os.mkdir("mcQuery\\favicon")
    if not os.path.exists("mcQuery\\group_config.json"):
        with open("mcQuery\\group_config.json", "w", encoding="utf-8") as f:
            f.write("{}")


def read_group_config() -> dict:
    with open("mcQuery\\group_config.json", encoding="utf-8") as f:
        return json.load(f)


def save_group_config(config: dict):
    with open("mcQuery\\group_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, sort_keys=True, indent=4, separators=(',', ': '))


def get_group_dict() -> dict[str, Group]:
    """
    获取群聊列表
    """
    group_dict = {}
    for group_id in group_config:
        group_data: dict = group_config[group_id]
        group = Group(group_id).load_config(group_data)
        group_dict[group_id] = group
    return group_dict


init_folder()
group_config = read_group_config()
group_dict = get_group_dict()


@scheduler.scheduled_job("interval", seconds=plugin_config.QueryInterval)
async def queryServerStatusChanged():
    """
    定时查询服务器状态是否改变
    改变则向群聊发送消息
    """
    try:
        bots = get_bots()
    except:
        return
    # logger.debug(f"开始查询服务器在线状态")
    start_time = time.time()

    async def async_func_query(bot: Bot, group: Group, server: Server,):
        start_query_time = time.time()
        online_status_changed = await server.is_online_status_changed()
        if online_status_changed:
            if online_status_changed == "online":
                status_message = "离线=>在线"
                message = plugin_config.format.server_state_change_online
            else:
                status_message = "在线=>离线"
                message = plugin_config.format.server_state_change_offline
            logger.info(f"监测到服务器: {server.name}({server.host}:{server.port}) 状态改变 {status_message}")
            message = message.format(**server.get_format_dict())
            await bot.call_api("send_group_msg", group_id=group.group_id, message=message)

    tasks = []
    for bot in bots.values():
        for group in group_dict.values():
            for server in group.servers:
                tasks.append(asyncio.create_task(async_func_query(bot, group, server)))
    if tasks:
        await asyncio.wait(tasks)
    # logger.debug(f"查询服务器在线完成,耗时 {((time.time()-start_time)*1000):.0f}s")


query_command = on_shell_command("查询")
# query_command = on_shell_command("查询",parser=querier_parser)


@query_command.handle()
async def queryAllServers(bot: Bot, event: GroupMessageEvent):
    """
    群聊查询服务器状态
    """
    group = group_dict[str(event.group_id)]
    if not group.enable_query:
        # 群聊不允许查询直接提出
        return

    logger.info(f"开始查询服务器状态 群聊：{event.group_id} 查询者: {event.get_user_id()}")
    await bot.send(event, "查询中...")

    start_time = time.time()
    server_message_dict: dict[Server, typing.Any] = {}  # 存储服务器信息

    async def query(server: Server):
        # 查询服务器，将数据存到：server_message_dict
        start_query_time = time.time()
        server_message_dict[server] = await server.get_status_msg()
    tasks = [asyncio.create_task(query(server)) for server in group.servers]
    if tasks:
        await asyncio.wait(tasks)  # 等待所有服务器查询完成
    group_message = Message()  # 要发送的消息
    for server in group.servers:
        # 拼接消息
        group_message += server_message_dict[server]
        group_message += "\n\n"

    logger.info(f"查询所有服务器状态完成 群聊：{event.group_id} 查询者: {event.get_user_id()} 耗时: {(start_time-time.time())*1000:.0f}ms")
    logger.debug(f"查询结果：{server_message_dict}")
    # await bot.call_api("send_group_msg", group_id=group.group_id, message=group_message) # 调用 cqHttp api 发送消息(能解析CQ码)
    await bot.send(event, group_message)


debug_command = on_command("调试", permission=SUPERUSER)


@debug_command.handle()
async def debug(bot: Bot, event: GroupMessageEvent):
    server = Server("debug", "java", "2b2t.xin", 25565)
    result = await server.get_status_msg()
    await bot.send(event, result)  # type: ignore
