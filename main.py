from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import aiohttp
import json

@register("astrbot_dg_lab_plugin", "Orange9", "郊狼API一键开火插件（离线版）", "0.1")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        game_api_config = config.get("game_api", {})
        self.session = aiohttp.ClientSession(trust_env=True)
        # Game API 配置初始化
        self.base_url = game_api_config.get("base_url", "")
        self.default_client_id = game_api_config.get("default_client_id", "all")
        self.verify_ssl = game_api_config.get("verify_ssl", False)

    async def _send_fire_command(self, strength, time=None, override=None):
        """内部方法：执行一键开火请求，返回结果字符串"""
        target_client_id = self.default_client_id
        if not self.base_url:
            logger.error("API基础URL未配置")
            return "错误：API基础URL未配置。"
        if not target_client_id:
            logger.error("客户端ID未配置")
            return "错误：客户端ID未配置。"

        api_url = f"{self.base_url.rstrip('/')}/api/v2/game/{target_client_id}/action/fire"
        payload = {"strength": strength}
        if time is not None:
            payload["time"] = time
        if override is not None:
            payload["override"] = override

        logger.debug(f"请求URL: {api_url}, Payload: {json.dumps(payload)}")

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        try:
            async with self.session.post(
                api_url,
                json=payload,
                ssl=self.verify_ssl,
                headers=headers
            ) as response:
                logger.debug(f"API响应状态: {response.status}")
                try:
                    resp_json = await response.json()
                    logger.debug(f"API响应JSON: {json.dumps(resp_json)}")
                except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
                    text = await response.text()
                    logger.error(f"JSON解析失败: {e}, 状态: {response.status}, 内容: {text[:200]}")
                    if 200 <= response.status < 300:
                        return f"操作可能已成功（状态码 {response.status}），但响应非标准JSON：{text[:200]}"
                    return f"API请求失败（状态码 {response.status}）：{text[:200]}"

                if 200 <= response.status < 300:
                    msg = resp_json.get("message", "操作成功完成。")
                    if resp_json.get("status") == 1 and resp_json.get("code") == "OK":
                        clients = resp_json.get("successClientIds")
                        if isinstance(clients, list) and clients:
                            msg += f" 成功影响的客户端: {', '.join(map(str, clients))}."
                    return msg
                else:
                    err_msg = resp_json.get("message", f"API返回错误，原始响应: {str(resp_json)[:200]}")
                    return f"API请求失败（状态码 {response.status}）：{err_msg}"
        except aiohttp.ClientConnectorError as e:
            logger.error(f"连接错误: {e}")
            return f"连接到API服务器失败: {e}"
        except Exception as e:
            logger.exception(f"发送开火指令时发生意外错误: {e}")
            return f"执行开火指令时发生意外错误: {str(e)}"

    def _parse_args(self, args_str):
        """
        解析命令参数，返回 (strength, time, override) 元组。
        """
        parts = args_str.split()
        strength = 10
        time = 5000
        override = False
        if '-s' in parts:
            idx = parts.index('-s')
            strength = int(parts[idx + 1])
        if '-t' in parts:
            idx = parts.index('-t')
            time = int(parts[idx + 1])
        if '-o' in parts:
            idx = parts.index('-o')
            val = parts[idx + 1]
            override = val=='True'
        return strength, time, override
    
    @filter.regex(r'shockhelp')
    async def handle_shock_help(self, event: AstrMessageEvent):
        """显示 /shock 命令帮助"""
        help_text = (
            "郊狼电击指令用法：\n"
            "/shock -s <强度> [-t <时间毫秒>] [-o <True|False>]\n"
            "  -s  强度 默认10/区间[1,40]\n"
            "  -t  持续时间（毫秒），可选，默认5000/区间[1,30000]\n"
            "  -o  覆盖模式，可选，True=重置计时，False=叠加，除非是True不然该值视为False\n"
            "示例：/shock -s 30 -t 10 -o False"
        )
        await event.reply(help_text)

    @filter.regex(r'shock(.*)')
    async def handle_shock_command(self, event: AstrMessageEvent, args_str):
        """处理 /shock 命令（带参数）"""
        try:
            strength, time, override = self._parse_args(args_str)
            result = await self._send_fire_command(strength, time, override)
            await event.reply(result)
        except Exception as e:
            logger.exception("处理 /shock 命令时发生未知异常")
            await event.reply(f"处理命令时发生未知错误: {str(e)}")

    async def terminate(self):
        """插件卸载时清理资源"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(f"{self.__class__.__name__}: HTTP session 已关闭。")
