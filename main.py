from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import aiohttp
import json

@register("astrbot_dg_lab_plugin", "RC-CHN", "郊狼API一键开火插件（离线精简版）", "0.3")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        game_api_config = config.get("game_api", {})
        self.session = aiohttp.ClientSession(trust_env=True)
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
        使用简单的 split() 按空格分割，然后遍历选项。
        """
        parts = args_str.split()  # 不引入 shlex，简单按空白分割
        strength = None
        time = None
        override = None
        i = 0
        while i < len(parts):
            opt = parts[i]
            if opt == "-s":
                if i + 1 < len(parts):
                    try:
                        strength = int(parts[i+1])
                    except ValueError:
                        raise ValueError(f"强度参数 -s 必须为整数，收到: {parts[i+1]}")
                    i += 2
                else:
                    raise ValueError("强度参数 -s 缺少数值")
            elif opt == "-t":
                if i + 1 < len(parts):
                    try:
                        time = int(parts[i+1])
                        if time < 0:
                            raise ValueError("时间必须为非负数")
                    except ValueError:
                        raise ValueError(f"时间参数 -t 必须为整数，收到: {parts[i+1]}")
                    i += 2
                else:
                    raise ValueError("时间参数 -t 缺少数值")
            elif opt == "-o":
                if i + 1 < len(parts):
                    val = parts[i+1].lower()
                    if val in ("true", "1"):
                        override = True
                    elif val in ("false", "0"):
                        override = False
                    else:
                        raise ValueError(f"覆盖参数 -o 必须为 true/false，收到: {parts[i+1]}")
                    i += 2
                else:
                    raise ValueError("覆盖参数 -o 缺少数值")
            else:
                raise ValueError(f"未知选项: {opt}")
        if strength is None:
            raise ValueError("缺少必填参数 -s（强度）")
        if strength < 1 or strength > 40:
            raise ValueError("强度参数必须在 1~40 之间")
        if time is not None and time > 30000:
            raise ValueError("时间参数不能超过 30000 毫秒")
        return strength, time, override

    @filter.regex(r'^/shock\s+(.*)')
    async def handle_shock_command(self, event: AstrMessageEvent, args_str):
        """处理 /shock 命令（带参数）"""
        try:
            strength, time, override = self._parse_args(args_str)
            result = await self._send_fire_command(strength, time, override)
            await event.reply(result)
        except ValueError as e:
            await event.reply(f"参数错误: {str(e)}\n用法示例：/shock -s 30 -t 10 -o false")
        except Exception as e:
            logger.exception("处理 /shock 命令时发生未知异常")
            await event.reply(f"处理命令时发生未知错误: {str(e)}")

    @filter.regex(r'^/shock\s*$')
    async def handle_shock_help(self, event: AstrMessageEvent):
        """显示 /shock 命令帮助"""
        help_text = (
            "郊狼电击指令用法：\n"
            "/shock -s <强度> [-t <时间毫秒>] [-o <true|false>]\n"
            "  -s  强度，必填，整数 1~40\n"
            "  -t  持续时间（毫秒），可选，默认 5000，最大 30000\n"
            "  -o  覆盖模式，可选，true=重置计时，false=叠加，默认 false\n"
            "示例：/shock -s 30 -t 10 -o false"
        )
        await event.reply(help_text)

    async def terminate(self):
        """插件卸载时清理资源"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(f"{self.__class__.__name__}: HTTP session 已关闭。")
