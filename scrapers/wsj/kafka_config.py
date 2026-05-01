#!/usr/bin/env python3
"""
Kafka Configuration Loader
Loads and parses Kafka configuration from YAML file
"""

import os
from typing import Dict, Optional, Any
from pathlib import Path


class KafkaConfig:
    """Kafka configuration loader and manager"""

    def __init__(self, config_file: str = "kafka_config.properties"):
        """
        Load Kafka configuration from properties file

        Args:
            config_file: Path to Kafka configuration file
        """
        self.config_file = Path(config_file)
        self._config = {}

        if self.config_file.exists():
            self._load_config()
        else:
            print(f"⚠️  Kafka config file not found: {config_file}")
            print(f"   Using default configuration")
            self._set_defaults()

    def _load_config(self):
        """Load configuration from YAML file"""
        try:
            config = {}
            with open(self.config_file) as fh:
                for line in fh:
                    line = line.strip()
                    if len(line) != 0 and line[0] != "#":
                        parameter, value = line.strip().split('=', 1)
                        config[parameter] = value.strip()
            print(f"✅ Loaded Kafka config from {self.config_file}")
            self._config = config
        except Exception as e:
            print(f"⚠️  Failed to load Kafka config: {e}")
            print(f"   Using default configuration")
            self._set_defaults()

    def _set_defaults(self):
        """Set default configuration"""
        self._config = {
            'bootstrap.servers': f'{self.bootstrap_servers}'
        }

    @property
    def bootstrap_servers(self) -> str:
        """Get bootstrap servers"""
        # Environment variable overrides config file
        return self._config.get('bootstrap.servers', os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'))

    def get_kafka_config(self) -> Dict[str, Any]:
        return self._config


def load_kafka_config(config_file: Optional[str] = None) -> KafkaConfig:
    """
    Load Kafka configuration from file

    Args:
        config_file: Path to config file (default: kafka_config.properties)

    Returns:
        KafkaConfig instance
    """
    if config_file is None:
        # Look for config file in current directory or script directory
        script_dir = Path(__file__).parent

        # Try current directory first
        if (Path.cwd() / 'kafka_config.properties').exists():
            config_file = 'kafka_config.properties'
        # Then try script directory
        elif (script_dir / 'kafka_config.properties').exists():
            config_file = str(script_dir / 'kafka_config.properties')
        else:
            config_file = 'kafka_config.properties'  # Use default (will trigger warning)

    return KafkaConfig(config_file)
