from __future__ import annotations

import random
from typing import Any

from app.services.config_service import ConfigService


class NoisePoolService:
    def __init__(self, config_service: ConfigService):
        self.config_service = config_service
        self.noise_pool: list[str] = []
        self.reload()

    @staticmethod
    def normalize_text(value: Any) -> str:
        if isinstance(value, dict):
            text = str(value.get("text") or "")
        else:
            text = str(value or "")

        return text.strip()

    @classmethod
    def normalize_pool(cls, values: Any) -> list[str]:
        if values is None:
            return []

        if isinstance(values, str):
            raw_items = [values]
        elif isinstance(values, (list, tuple)):
            raw_items = list(values)
        else:
            return []

        result: list[str] = []

        for item in raw_items:
            if isinstance(item, dict) and item.get("enabled") is False:
                continue

            text = cls.normalize_text(item)

            if text:
                result.append(text)

        return result

    def reload(self) -> list[str]:
        self.noise_pool = self.normalize_pool(self.config_service.load_noise_pool())
        return self.get_all()

    def save(self) -> None:
        self.noise_pool = self.normalize_pool(self.noise_pool)
        self.config_service.save_noise_pool(self.noise_pool)

    def replace_all(self, values: Any, save: bool = True) -> list[str]:
        self.noise_pool = self.normalize_pool(values)

        if save:
            self.save()

        return self.get_all()

    def get_all(self) -> list[str]:
        return list(self.noise_pool)

    def count(self) -> int:
        return len(self.noise_pool)

    def has_items(self) -> bool:
        return bool(self.noise_pool)

    def add_text(self, text: str, save: bool = True) -> list[str]:
        normalized_text = self.normalize_text(text)

        if not normalized_text:
            return self.get_all()

        self.noise_pool.append(normalized_text)

        if save:
            self.save()

        return self.get_all()

    def update_text(self, index: int, text: str, save: bool = True) -> list[str]:
        self._validate_index(index)
        normalized_text = self.normalize_text(text)

        if not normalized_text:
            raise ValueError("噪音内容不能为空")

        self.noise_pool[index] = normalized_text

        if save:
            self.save()

        return self.get_all()

    def remove_at(self, index: int, save: bool = True) -> list[str]:
        self._validate_index(index)
        self.noise_pool.pop(index)

        if save:
            self.save()

        return self.get_all()

    def move_up(self, index: int, save: bool = True) -> int:
        self._validate_index(index)

        if index <= 0:
            return index

        self.noise_pool[index - 1], self.noise_pool[index] = (
            self.noise_pool[index],
            self.noise_pool[index - 1],
        )
        new_index = index - 1

        if save:
            self.save()

        return new_index

    def move_down(self, index: int, save: bool = True) -> int:
        self._validate_index(index)

        if index >= len(self.noise_pool) - 1:
            return index

        self.noise_pool[index + 1], self.noise_pool[index] = (
            self.noise_pool[index],
            self.noise_pool[index + 1],
        )
        new_index = index + 1

        if save:
            self.save()

        return new_index

    def clear(self, save: bool = True) -> None:
        self.noise_pool = []

        if save:
            self.save()

    def choose_random(self, rng: random.Random | None = None) -> str | None:
        if not self.noise_pool:
            return None

        random_source = rng if rng is not None else random
        return random_source.choice(self.noise_pool)

    def _validate_index(self, index: int) -> None:
        if index < 0 or index >= len(self.noise_pool):
            raise IndexError("噪音内容索引超出范围")