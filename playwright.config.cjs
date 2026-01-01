const baseURL = process.env.BASE_URL || "http://127.0.0.1:5001";
const useWebServer = process.env.PLAYWRIGHT_SKIP_WEBSERVER !== "1";

module.exports = {
  testDir: "tests/ui",
  workers: 1,
  timeout: 60000,
  expect: {
    timeout: 10000
  },
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1280, height: 720 }
  },
  webServer: useWebServer
    ? {
        command: "python main.py",
        url: baseURL,
        reuseExistingServer: true,
        timeout: 120000
      }
    : undefined
};
