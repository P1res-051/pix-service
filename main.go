package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"pix-service/pix"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/gofiber/fiber/v2/middleware/requestid"
)

type PixRequest struct {
	Link  string `json:"link"`
	Email string `json:"email"`
}

type PixResponse struct {
	Success       bool   `json:"success"`
	Pix           string `json:"pix,omitempty"`
	Error         string `json:"error,omitempty"`
	RequestID     string `json:"request_id"`
	ExecutionTime string `json:"execution_time"`
}

// Concurrency Semaphore (Buffer size = Max Concurrent Requests)
var semaphore = make(chan struct{}, 5)

func main() {
	// Initialize Global Browser
	if err := pix.InitBrowser(); err != nil {
		log.Fatalf("❌ Failed to initialize browser: %v", err)
	}
	defer pix.ShutdownBrowser()

	// Fiber App
	app := fiber.New(fiber.Config{
		AppName:               "Pix Service Go",
		DisableStartupMessage: true,
	})

	// Middleware
	app.Use(recover.New())
	app.Use(requestid.New())
	app.Use(logger.New(logger.Config{
		Format: "${time} | ${locals:requestid} | ${status} | ${method} ${path} | ${latency}\n",
	}))
	app.Use(cors.New())

	// Routes
	app.Get("/", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"status":  "online",
			"service": "Pix Service Go",
			"workers": fmt.Sprintf("%d/%d used", len(semaphore), cap(semaphore)),
		})
	})

	app.Get("/health", func(c *fiber.Ctx) error {
		// Basic health check
		browser, err := pix.GetBrowser()
		if err != nil || !browser.IsConnected() {
			return c.Status(503).JSON(fiber.Map{"status": "error", "message": "Browser disconnected"})
		}
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/gerar-pix", func(c *fiber.Ctx) error {
		start := time.Now()
		reqID := c.Locals("requestid").(string)

		var req PixRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(400).JSON(PixResponse{
				Success:       false,
				Error:         "Invalid JSON",
				RequestID:     reqID,
				ExecutionTime: time.Since(start).String(),
			})
		}

		if req.Email == "" {
			req.Email = "teste@gmail.com"
		}

		// Try to acquire semaphore
		select {
		case semaphore <- struct{}{}:
			defer func() { <-semaphore }()
		default:
			return c.Status(503).JSON(PixResponse{
				Success:       false,
				Error:         "Server Busy (Max Concurrency Reached)",
				RequestID:     reqID,
				ExecutionTime: time.Since(start).String(),
			})
		}

		log.Printf("[%s] Processing: %s", reqID, req.Link)
		
		code, err := pix.GeneratePix(req.Link, req.Email)
		elapsed := time.Since(start).String()

		if err != nil {
			log.Printf("[%s] Error: %v", reqID, err)
			return c.JSON(PixResponse{
				Success:       false,
				Error:         err.Error(),
				RequestID:     reqID,
				ExecutionTime: elapsed,
			})
		}

		log.Printf("[%s] Success!", reqID)
		return c.JSON(PixResponse{
			Success:       true,
			Pix:           code,
			RequestID:     reqID,
			ExecutionTime: elapsed,
		})
	})

	// Start Server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	// Graceful Shutdown
	go func() {
		if err := app.Listen(":" + port); err != nil {
			log.Panic(err)
		}
	}()

	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, syscall.SIGTERM)
	<-c

	log.Println("🛑 Shutting down server...")
	_ = app.Shutdown()
}
