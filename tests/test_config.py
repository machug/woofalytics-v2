"""Tests for configuration system."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
import yaml

from woofalytics.config import (
    AudioConfig,
    DOAConfig,
    EvidenceConfig,
    ModelConfig,
    Settings,
    load_settings,
)


class TestAudioConfig:
    """Tests for AudioConfig model."""

    def test_defaults(self):
        """Test default values."""
        config = AudioConfig()

        assert config.device_name is None
        assert config.sample_rate == 44100
        assert config.channels == 2
        assert config.chunk_size == 441
        assert config.volume_percent == 75

    def test_volume_validation(self):
        """Test volume percent validation."""
        # Valid values
        config = AudioConfig(volume_percent=0)
        assert config.volume_percent == 0

        config = AudioConfig(volume_percent=100)
        assert config.volume_percent == 100

        # Invalid values should raise
        with pytest.raises(ValueError):
            AudioConfig(volume_percent=-1)

        with pytest.raises(ValueError):
            AudioConfig(volume_percent=101)


class TestModelConfig:
    """Tests for ModelConfig model."""

    def test_defaults(self):
        """Test default values."""
        config = ModelConfig()

        assert config.path == Path("./models/traced_model.pt")
        assert config.threshold == 0.88
        assert config.target_sample_rate == 16000

    def test_threshold_validation(self):
        """Test threshold validation."""
        config = ModelConfig(threshold=0.0)
        assert config.threshold == 0.0

        config = ModelConfig(threshold=1.0)
        assert config.threshold == 1.0

        with pytest.raises(ValueError):
            ModelConfig(threshold=-0.1)

        with pytest.raises(ValueError):
            ModelConfig(threshold=1.1)


class TestDOAConfig:
    """Tests for DOAConfig model."""

    def test_defaults(self):
        """Test default values."""
        config = DOAConfig()

        assert config.enabled is True
        assert config.element_spacing == 0.1
        assert config.num_elements == 2
        assert config.angle_min == 0
        assert config.angle_max == 180


class TestSettings:
    """Tests for root Settings class."""

    def test_defaults(self):
        """Test default settings."""
        settings = Settings()

        assert settings.log_level == "INFO"
        assert settings.log_format == "console"
        assert isinstance(settings.audio, AudioConfig)
        assert isinstance(settings.model, ModelConfig)
        assert isinstance(settings.doa, DOAConfig)
        assert isinstance(settings.evidence, EvidenceConfig)

    def test_nested_config(self):
        """Test nested configuration."""
        settings = Settings(
            audio=AudioConfig(sample_rate=48000),
            model=ModelConfig(threshold=0.5),
        )

        assert settings.audio.sample_rate == 48000
        assert settings.model.threshold == 0.5


class TestLoadSettings:
    """Tests for load_settings function."""

    def test_load_defaults(self):
        """Test loading with no config file."""
        settings = load_settings(None)

        assert isinstance(settings, Settings)
        assert settings.log_level == "INFO"

    def test_load_from_yaml(self, tmp_path: Path):
        """Test loading from YAML file."""
        config_data = {
            "audio": {
                "sample_rate": 48000,
                "channels": 4,
            },
            "model": {
                "threshold": 0.75,
            },
            "log_level": "DEBUG",
        }

        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        settings = load_settings(config_file)

        assert settings.audio.sample_rate == 48000
        assert settings.audio.channels == 4
        assert settings.model.threshold == 0.75
        assert settings.log_level == "DEBUG"

    def test_env_override(self, monkeypatch):
        """Test environment variable override."""
        monkeypatch.setenv("WOOFALYTICS__LOG_LEVEL", "WARNING")

        settings = load_settings(None)
        assert settings.log_level == "WARNING"
