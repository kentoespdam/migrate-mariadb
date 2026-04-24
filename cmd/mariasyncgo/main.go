package main

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"time"

	"mariasyncgo/internal/config"
	"mariasyncgo/internal/discovery"
	"mariasyncgo/internal/mapping"

	_ "github.com/go-sql-driver/mysql"
	"golang.org/x/sync/errgroup"
)

func main() {
	// 1. Load configuration
	cfg, err := config.Load("config.yaml")
	if err != nil {
		fmt.Printf("Gagal memuat konfigurasi: %v\n", err)
		os.Exit(1)
	}

	// 2. Open connections
	dbA, err := sql.Open("mysql", cfg.Source.DSN())
	if err != nil {
		fmt.Printf("Gagal membuka koneksi ke Host Sumber: %v\n", err)
		os.Exit(1)
	}
	defer dbA.Close()
	configurePool(dbA, cfg.Migration)

	dbB, err := sql.Open("mysql", cfg.Target.DSN())
	if err != nil {
		fmt.Printf("Gagal membuka koneksi ke Host Target: %v\n", err)
		os.Exit(1)
	}
	defer dbB.Close()
	configurePool(dbB, cfg.Migration)

	// 3. Discovery Phase
	fmt.Println("🔎 Menjelajahi metadata database...")
	g, gctx := errgroup.WithContext(context.Background())

	var snapA, snapB *discovery.SchemaSnapshot
	g.Go(func() error {
		var err error
		snapA, err = discovery.Discover(gctx, dbA, cfg.Source.Database)
		return err
	})
	g.Go(func() error {
		var err error
		snapB, err = discovery.Discover(gctx, dbB, cfg.Target.Database)
		return err
	})

	if err := g.Wait(); err != nil {
		fmt.Printf("Gagal discovery metadata: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("✅ Sumber: %d tabel ditemukan.\n", len(snapA.Tables))
	fmt.Printf("✅ Target: %d tabel ditemukan.\n", len(snapB.Tables))

	// 4. Mapping Phase (Preview)
	fmt.Println("\n📊 Preview Auto-Mapping:")
	for name, srcTbl := range snapA.Tables {
		if tgtTbl, exists := snapB.Tables[name]; exists {
			plan := mapping.BuildAutoPlan(srcTbl, tgtTbl)
			fmt.Printf(" - [%s] -> [%s]: %d kolom kolom terpetakan", srcTbl.Name, tgtTbl.Name, len(plan.Columns))
			if len(plan.Warnings) > 0 {
				fmt.Printf(" (%d peringatan)", len(plan.Warnings))
			}
			fmt.Println()
		}
	}

	fmt.Println("\n🚀 Siap memulai migrasi (TUI implementation coming soon...)")
}

func configurePool(db *sql.DB, cfg config.MigrationConfig) {
	db.SetMaxOpenConns(cfg.WorkerCount + 2)
	db.SetMaxIdleConns(cfg.WorkerCount)
	db.SetConnMaxLifetime(30 * time.Minute)
}
