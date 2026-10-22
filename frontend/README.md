# TurboTranscribe frontend

React 19 + Vite 8 + Tailwind CSS 4. See the [project README](../README.md), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#frontend-frontendsrc) and the design system in [docs/DESIGN.md](../docs/DESIGN.md).

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to http://127.0.0.1:8000 (or BACKEND_URL)
npm run lint       # oxlint
npm test           # Vitest unit tests (src/**/*.test.js)
npm run e2e        # browser end-to-end test against a running app (see e2e/app.e2e.mjs)
npm run build      # production build in dist/ (served by the backend at /)
```

| Variable | Where | Purpose |
| --- | --- | --- |
| `BACKEND_URL` | shell, for `npm run dev` | Dev-proxy target if the backend isn't on port 8000 (`start_app.bat` sets it) |
| `VITE_API_URL` | `.env.local` | Call a backend on another origin directly (also add the origin to the backend's `CORS_ORIGINS`) |
| `BASE_URL`, `BROWSER_CHANNEL`, `E2E_LLM`, `E2E_LIVE`, `SCREENSHOTS`, `HEADED` | shell, for `npm run e2e` | See the header of `e2e/app.e2e.mjs` |

The end-to-end test drives your installed Microsoft Edge (or Chrome with `BROWSER_CHANNEL=chrome`) through `playwright-core`, so no browser download is needed. It uses `e2e/fixtures/standup.mp4`, a 37-second, two-voice, three-slide meeting made with Windows text-to-speech (see `e2e/fixtures/README.md`).

The OpenRouter API key must **never** be placed in frontend code. It belongs in `backend/.env`.
