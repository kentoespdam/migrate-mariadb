package config

import (
	"os"
	"testing"
)

func TestDSN(t *testing.T) {
	cfg := DBConfig{
		Host:     "127.0.0.1",
		Port:     3306,
		User:     "user",
		Password: "password",
		Database: "testdb",
		Charset:  "utf8mb4",
	}
	expected := "user:password@tcp(127.0.0.1:3306)/testdb?charset=utf8mb4&parseTime=true&multiStatements=false&interpolateParams=false"
	if cfg.DSN() != expected {
		t.Errorf("expected %s, got %s", expected, cfg.DSN())
	}
}

func TestLoad(t *testing.T) {
	yamlContent := `
source:
  host: "src-host"
  database: "src-db"
target:
  host: "tgt-host"
  database: "tgt-db"
`
	tmpfile, err := os.CreateTemp("", "config*.yaml")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(tmpfile.Name())

	if _, err := tmpfile.Write([]byte(yamlContent)); err != nil {
		t.Fatal(err)
	}
	if err := tmpfile.Close(); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(tmpfile.Name())
	if err != nil {
		t.Fatalf("failed to load config: %v", err)
	}

	if cfg.Source.Host != "src-host" {
		t.Errorf("expected source.host src-host, got %s", cfg.Source.Host)
	}
}

func TestLoad_Invalid(t *testing.T) {
	// Missing source.host
	yamlContent := `
source:
  database: "src-db"
target:
  host: "tgt-host"
  database: "tgt-db"
`
	tmpfile, err := os.CreateTemp("", "config_invalid*.yaml")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(tmpfile.Name())

	if _, err := tmpfile.Write([]byte(yamlContent)); err != nil {
		t.Fatal(err)
	}
	tmpfile.Close()

	_, err = Load(tmpfile.Name())
	if err == nil {
		t.Error("expected error for invalid config, got nil")
	}
}
