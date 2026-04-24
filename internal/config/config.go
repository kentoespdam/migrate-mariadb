package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// DBConfig holds database connection parameters.
type DBConfig struct {
	Host     string `yaml:"host"`
	Port     int    `yaml:"port"`
	User     string `yaml:"user"`
	Password string `yaml:"password"`
	Database string `yaml:"database"`
	Charset  string `yaml:"charset"`
}

// MigrationConfig holds migration-specific settings.
type MigrationConfig struct {
	BatchSize      int    `yaml:"batch_size"`
	WorkerCount    int    `yaml:"worker_count"`
	CheckpointPath string `yaml:"checkpoint_path"`
	LogPath        string `yaml:"log_path"`
}

// AppConfig is the root configuration object.
type AppConfig struct {
	Source    DBConfig        `yaml:"source"`
	Target    DBConfig        `yaml:"target"`
	Migration MigrationConfig `yaml:"migration"`
}

// DSN generates a Data Source Name for the MySQL driver.
func (c DBConfig) DSN() string {
	// Format: user:password@tcp(host:port)/database?charset=utf8mb4&parseTime=true&multiStatements=false&interpolateParams=false
	return fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?charset=%s&parseTime=true&multiStatements=false&interpolateParams=false",
		c.User, c.Password, c.Host, c.Port, c.Database, c.Charset)
}

// Load reads and parses the YAML configuration file.
func Load(path string) (*AppConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("file konfigurasi tidak ditemukan di `%s`", path)
		}
		return nil, fmt.Errorf("gagal membaca file konfigurasi: %w", err)
	}

	var cfg AppConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("format konfigurasi salah: %w", err)
	}

	// Simple validation
	if err := cfg.Validate(); err != nil {
		return nil, err
	}

	return &cfg, nil
}

// Validate ensures required fields are present.
func (c *AppConfig) Validate() error {
	if c.Source.Host == "" {
		return fmt.Errorf("field wajib `source.host` tidak boleh kosong")
	}
	if c.Source.Database == "" {
		return fmt.Errorf("field wajib `source.database` tidak boleh kosong")
	}
	if c.Target.Host == "" {
		return fmt.Errorf("field wajib `target.host` tidak boleh kosong")
	}
	if c.Target.Database == "" {
		return fmt.Errorf("field wajib `target.database` tidak boleh kosong")
	}
	return nil
}
