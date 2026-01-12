package pix

import (
	"errors"
	"fmt"
	"log"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/playwright-community/playwright-go"
)

var (
	pw          *playwright.Playwright
	browser     playwright.Browser
	browserLock sync.Mutex
)

// InitBrowser initializes the global Playwright browser instance
func InitBrowser() error {
	browserLock.Lock()
	defer browserLock.Unlock()

	if browser != nil && browser.IsConnected() {
		return nil
	}

	log.Println("🚀 Initializing Playwright Global Browser...")

	var err error
	pw, err = playwright.Run()
	if err != nil {
		return fmt.Errorf("could not start playwright: %v", err)
	}

	browser, err = pw.Chromium.Launch(playwright.BrowserTypeLaunchOptions{
		Headless: playwright.Bool(true),
		Args: []string{
			"--no-sandbox",
			"--disable-setuid-sandbox",
			"--disable-blink-features=AutomationControlled",
			"--disable-dev-shm-usage",
		},
	})
	if err != nil {
		return fmt.Errorf("could not launch browser: %v", err)
	}

	log.Println("✅ Browser initialized successfully")
	return nil
}

// ShutdownBrowser closes the browser and stops Playwright
func ShutdownBrowser() {
	browserLock.Lock()
	defer browserLock.Unlock()

	if browser != nil {
		browser.Close()
		browser = nil
	}
	if pw != nil {
		pw.Stop()
		pw = nil
	}
	log.Println("🛑 Browser shutdown complete")
}

// GetBrowser returns the global browser instance, re-initializing if needed
func GetBrowser() (playwright.Browser, error) {
	if browser == nil || !browser.IsConnected() {
		if err := InitBrowser(); err != nil {
			return nil, err
		}
	}
	return browser, nil
}

// GeneratePix accesses the URL and attempts to extract the Pix Copy & Paste code
func GeneratePix(link, email string) (string, error) {
	maxRetries := 3
	var lastErr error

	for i := 0; i < maxRetries; i++ {
		log.Printf("--- Attempt %d/%d for %s ---", i+1, maxRetries, link)
		
		code, err := attemptGeneratePix(link, email)
		if err == nil && code != "" {
			return code, nil
		}
		
		lastErr = err
		log.Printf("⚠️ Attempt %d failed: %v", i+1, err)
		time.Sleep(2 * time.Second)
	}

	return "", fmt.Errorf("failed after %d attempts. Last error: %v", maxRetries, lastErr)
}

func attemptGeneratePix(link, email string) (string, error) {
	br, err := GetBrowser()
	if err != nil {
		return "", err
	}

	// Create a new context
	ctx, err := br.NewContext(playwright.BrowserNewContextOptions{
		UserAgent:        playwright.String("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
		Permissions:      []string{"clipboard-read", "clipboard-write"},
		Viewport:         &playwright.Size{Width: 1920, Height: 1080},
		IgnoreHttpsErrors: playwright.Bool(true),
		JavaScriptEnabled: playwright.Bool(true),
		Locale:           playwright.String("pt-BR"),
	})
	if err != nil {
		return "", fmt.Errorf("failed to create context: %v", err)
	}
	defer ctx.Close()

	// Block media to save resources
	ctx.Route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff,woff2}", func(route playwright.Route) {
		route.Abort()
	})

	page, err := ctx.NewPage()
	if err != nil {
		return "", fmt.Errorf("failed to create page: %v", err)
	}
	defer page.Close()

	// Network Interception for Pix Code
	pixCodeChan := make(chan string, 1)
	
	page.On("response", func(response playwright.Response) {
		go func() {
			// Check if it's a JSON response likely to contain Pix
			if response.Request().Method() == "POST" && 
			   (strings.Contains(response.URL(), "000201") || strings.Contains(strings.ToLower(response.Headers()["content-type"]), "json")) {
				
				body, err := response.Body()
				if err == nil {
					bodyStr := string(body)
					if strings.Contains(bodyStr, "000201") {
						if code := extractPix(bodyStr); code != "" {
							select {
							case pixCodeChan <- code:
							default:
							}
						}
					}
				}
			}
		}()
	})

	// Navigate with timeout
	log.Printf("Navigating to %s", link)
	if _, err := page.Goto(link, playwright.PageGotoOptions{
		Timeout: playwright.Float(40000),
		WaitUntil: playwright.WaitUntilStateDomcontentloaded,
	}); err != nil {
		return "", fmt.Errorf("navigation failed: %v", err)
	}

	// Handle Email Input logic if needed (Mercado Pago style)
	// Try to fill email if input exists
	fillEmail(page, email)

	// Wait loop for Pix Code
	timeout := time.After(25 * time.Second)
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case code := <-pixCodeChan:
			log.Println("✅ Pix found via Network Interception!")
			return cleanPix(code), nil
		case <-timeout:
			return "", errors.New("timeout waiting for Pix code")
		case <-ticker.C:
			// 1. Check Inputs/Textareas
			if code := checkInputs(page); code != "" {
				log.Println("✅ Pix found in Input/Textarea")
				return cleanPix(code), nil
			}

			// 2. Try Clipboard (Click Copy Buttons)
			if code := checkClipboard(page); code != "" {
				log.Println("✅ Pix found via Clipboard")
				return cleanPix(code), nil
			}

			// 3. Check Body Text and Iframes
			if code := checkBodyAndFrames(page); code != "" {
				log.Println("✅ Pix found in Body/Iframe Text")
				return cleanPix(code), nil
			}
		}
	}
}

func extractPix(text string) string {
	re := regexp.MustCompile(`(000201[a-zA-Z0-9\s\.\-\*@:]+)`)
	matches := re.FindStringSubmatch(text)
	if len(matches) > 1 {
		candidate := strings.ReplaceAll(matches[1], " ", "")
		candidate = strings.ReplaceAll(candidate, "\n", "")
		if len(candidate) > 50 {
			return candidate
		}
	}
	return ""
}

func cleanPix(code string) string {
	code = strings.TrimSpace(code)
	if idx := strings.Index(code, "<"); idx != -1 {
		code = code[:idx]
	}
	code = strings.ReplaceAll(code, "\"", "")
	code = strings.ReplaceAll(code, "'", "")
	return code
}

func fillEmail(page playwright.Page, email string) {
	// Simple heuristic to find email input
	selectors := []string{
		"input[type='email']", 
		"input[name*='email']", 
		"input[placeholder*='email']", 
		"input[placeholder*='Ex.:']",
		"#user-email-input",
	}

	for _, sel := range selectors {
		if loc := page.Locator(sel).First(); loc != nil {
			if visible, _ := loc.IsVisible(); visible {
				log.Printf("Filling email in %s", sel)
				loc.Click()
				loc.Fill(email)
				loc.Press("Enter")
				// Sometimes needed to trigger validation
				loc.DispatchEvent("change", nil)
				time.Sleep(1 * time.Second)
				return
			}
		}
	}
}

func checkInputs(page playwright.Page) string {
	inputs, err := page.Locator("input, textarea").All()
	if err != nil {
		return ""
	}
	for _, inp := range inputs {
		if vis, _ := inp.IsVisible(); !vis {
			continue
		}
		val, _ := inp.GetAttribute("value")
		if strings.Contains(val, "000201") {
			return extractPix(val)
		}
		txt, _ := inp.InnerText()
		if strings.Contains(txt, "000201") {
			return extractPix(txt)
		}
	}
	return ""
}

func checkClipboard(page playwright.Page) string {
	// Find buttons that might be copy buttons
	btns, err := page.Locator("button, span, div, a").Filter(playwright.LocatorFilterOptions{
		HasText: regexp.MustCompile(`(?i)Copiar|Copy`),
	}).All()
	
	if err != nil {
		return ""
	}

	for _, btn := range btns {
		if vis, _ := btn.IsVisible(); vis {
			btn.Click()
			// Small delay for clipboard write
			time.Sleep(200 * time.Millisecond)
			
			// Read clipboard
			clip, err := page.Evaluate("navigator.clipboard.readText()")
			if err == nil {
				if str, ok := clip.(string); ok && strings.Contains(str, "000201") {
					return extractPix(str)
				}
			}
		}
	}
	return ""
}

func checkBodyAndFrames(page playwright.Page) string {
	// Check main body
	if content, err := page.InnerText("body"); err == nil {
		if strings.Contains(content, "000201") {
			return extractPix(content)
		}
	}

	// Check iframes
	for _, frame := range page.Frames() {
		if content, err := frame.InnerText("body"); err == nil {
			if strings.Contains(content, "000201") {
				return extractPix(content)
			}
		}
	}
	return ""
}
