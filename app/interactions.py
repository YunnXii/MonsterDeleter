from __future__ import annotations

import random
from abc import ABC, abstractmethod


class InteractionProvider(ABC):
    """Provide one short line when the resident pet is clicked.

    The resident UI deliberately depends on this tiny interface instead of a
    hard-coded random.choice call. A future AI/chat provider can replace the
    local quip provider without changing drag, tray, IPC, or deletion logic.
    """

    @abstractmethod
    def next_message(self, click_streak: int = 1) -> str:
        raise NotImplementedError


class RandomQuipProvider(InteractionProvider):
    NORMAL = (
        "不要动我啦！",
        "有什么倒霉文件要踹？",
        "又怎么了，我刚站稳。",
        "本小姐不是桌面挂件。",
        "你点我干嘛，文件自己会消失吗？",
        "工作时间禁止骚扰执行人员。",
        "有事说事，没事我继续站着了。",
        "今天又是谁惹你了？",
    )

    REPEAT = (
        "你怎么还点？",
        "再点也不会掉金币。",
        "手是不是有自己的想法？",
        "有文件就说，别戳了。",
    )

    VERY_REPEAT = (
        "……你真的很闲。",
        "你再点一下试试？",
        "我开始怀疑你才是要被收拾的那个。",
    )

    def __init__(self, *, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._last: str | None = None

    def next_message(self, click_streak: int = 1) -> str:
        if click_streak >= 5:
            pool = self.VERY_REPEAT
        elif click_streak >= 3:
            pool = self.REPEAT
        else:
            pool = self.NORMAL

        choices = tuple(item for item in pool if item != self._last) or pool
        message = self._rng.choice(choices)
        self._last = message
        return message
