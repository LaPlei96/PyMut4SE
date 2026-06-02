from pymut4se.model.input import ProgramInput
import json
from pathlib import Path
import pickle
import base64
from dataclasses import dataclass
from abc import ABC, abstractmethod


class Inputs(ABC):
    @staticmethod
    @abstractmethod
    def get_inputs() -> list[ProgramInput]:
        pass
    
    @staticmethod
    def to_json(list_of_inputs: list[ProgramInput], file_path:Path) -> None:
        with open(file_path, "w") as f:
            json.dump([input.__dict__ for input in list_of_inputs], f)
