import os
import sys
sys.path.append(os.getcwd())  # NOQA

from abc import ABC, abstractmethod
from datetime import datetime

import json
import sqlite3


class BaseCrawler(ABC):
    """
        Base class for all crawlers.
    """

    CONFIG_DIR = os.path.join(os.getcwd(), 'config')
    DATABASE_DIR = os.path.join(os.getcwd(), 'database')

    def load_config(self, filename) -> dict:
        """
            Load the config file from config directory.
        """
        with open(os.path.join(self.CONFIG_DIR, filename), 'r') as f:
            return json.load(f)

    def log(self, msg, color='white'):
        datefmt = datetime.strftime(datetime.now(), format='%Y-%m-%d %H:%M:%S')

        # If color is green
        if color == 'green':
            print('\033[92m' + f'[{datefmt}]: {msg}' + '\033[0m')
        # If color is red
        elif color == 'red':
            print('\033[91m' + f'[{datefmt}]: {msg}' + '\033[0m')
        # If color is yellow
        elif color == 'yellow':
            print('\033[93m' + f'[{datefmt}]: {msg}' + '\033[0m')
        else:
            print(f'[{datefmt}]: {msg}')

    @abstractmethod
    def get_all_product_links(self):
        pass

    @abstractmethod
    def crawl_raw_htmls(self):
        pass

    @abstractmethod
    def parse_specs(self):
        pass