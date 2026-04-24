package main

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"time"

	"mariasyncgo/internal/config"

	_ "github.com/go-sql-driver/mysql"
)

func main() {
	// 1. Load configuration
	cfg, err := config.Load("config.yaml")
	if err != nil {
		fmt.Printf("Gagal memuat konfigurasi: %v\n", err)
		os.Exit(1)
	}

	// 2. Open Source DB
	dbA, err := sql.Open("mysql", cfg.Source.DSN())
	if err != nil {
		fmt.Printf("Gagal membuka koneksi ke Host Sumber: %v\n", err)
		os.Exit(1)
	}
	defer dbA.Close()
	configurePool(dbA, cfg.Migration)

	// 3. Open Target DB
	dbB, err := sql.Open("mysql", cfg.Target.DSN())
	if err != nil {
		fmt.Printf("Gagal membuka koneksi ke Host Target: %v\n", err)
		os.Exit(1)
	}
	defer dbB.Close()
	configurePool(dbB, cfg.Migration)

	// 4. Ping health checks
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := dbA.PingContext(ctx); err != nil {
		fmt.Printf("Gagal terhubung ke Host Sumber (%s:%d): %v\n", cfg.Source.Host, cfg.Source.Port, err)
		os.Exit(1)
	}

	if err := dbB.PingContext(ctx); err != nil {
		fmt.Printf("Gagal terhubung ke Host Target (%s:%d): %v\n", cfg.Target.Host, cfg.Target.Port, err)
		os.Exit(1)
	}

	fmt.Println("Berhasil terhubung ke Host Sumber dan Host Target!")
	fmt.Println("Memulai fase TUI...")
	// TUI phase will be implemented in later steps
}

func configurePool(db *sql.DB, cfg config.MigrationConfig) {
	db.SetMaxOpenConns(cfg.WorkerCount + 2)
	db.SetMaxIdleConns(cfg.WorkerCount)
	db.SetConnMaxLifetime(30 * time.Minute)
}
