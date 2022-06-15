__all__ = ["EksplaNt340"]

import asyncio
from typing import Dict, Any, List
import re
import time

from yaqd_core import IsDaemon, HasPosition, UsesUart, aserial


re_msg = re.compile(r"\[(?P<to>\w+):(?P<info>[\w/.]+)\\(?P<sender>\w+)\]$")
re_info = re.compile(r"(?P<cmd>[A-Z][0-9])/(?P<action>[SAP?]+)(?P<value>[\d.\d]*)")
msg = "[{to}:{info}\\{sender}]\n"


class EksplaNt340(UsesUart, HasPosition, IsDaemon):
    _kind = "ekspla-nt340"

    def __init__(self, name, config, config_filepath):
        super().__init__(name, config, config_filepath)
        self._ser = aserial.ASerial(config["serial_port"], eol=b"]", baudrate=config["baud_rate"])
        self._alias = config["serial_name"]
        self._write("W0/?")
        self._incoming = []
        self._loop.create_task(self._areadlines())

    def _set_position(self, position: float) -> None:
        position = round(position, 1)
        self._state["destination"] = position
        self._write(f"W0/S{position}")
        self._busy = True

    async def update_state(self):
        while True:
            if self._incoming:
                try:
                    received = re_msg.match(self._incoming.pop().decode())
                except Exception as e:
                    self.logger.error(e)
                    await asyncio.sleep(0.1)
                    continue
                if received and received["sender"] == self._alias:
                    info = re_info.match(received["info"])
                    if not info:
                        self.logger.error(f"unparsed info: {received['info']}")
                        await asyncio.sleep(0.1)
                        continue
                    if info["cmd"] == "W0" and info["action"] == "S":
                        self._state["position"] = float(info["value"])
                else:
                    self.logger.error(f"received not parsed: {received}")
                    continue
            if self._busy:
                self._write("W0/?")
            if self._state["destination"] == self._state["position"]:
                self._busy = False
            await asyncio.sleep(0.1)

    def direct_serial_write(self, cmd: bytes) -> str:
        self._ser.write(cmd)
        return self._ser.read_until("]").decode()

    def get_units(self):
        return "nm"

    def close(self):
        self._ser.close()

    def _write(self, info: str):
        message = msg.format(to=self._alias, info=info, sender="PC").encode()
        self.logger.debug(f"writing: {message!r}")
        self._ser.write(message)

    async def _areadlines(self):
        while True:
            async for line in self._ser.areadlines():
                self._incoming.append(line)
