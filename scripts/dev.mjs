import { execSync, spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { createInterface } from 'node:readline'

const root = resolve(process.cwd())
const isWindows = process.platform === 'win32'
const BACKEND_PORT = 7999
const colors = {
  backend: '\u001b[36m',
  frontend: '\u001b[35m',
  reset: '\u001b[0m',
}

function prefix(label, color, text) {
  process.stdout.write(`${color}[${label}]${colors.reset} ${text}\n`)
}

function streamProcess(label, color, command, args, options = {}) {
  const childEnv = { ...process.env, FORCE_COLOR: '1', CLICOLOR: '1' }
  const child = spawn(command, args, {
    cwd: root,
    env: childEnv,
    shell: false,
    ...options,
  })

  const stdout = createInterface({ input: child.stdout })
  const stderr = createInterface({ input: child.stderr })

  stdout.on('line', (line) => prefix(label, color, maybeColorize(line)))
  stderr.on('line', (line) => prefix(label, color, maybeColorize(line)))

  child.on('error', (error) => {
    prefix(label, color, `failed to start: ${error.message}`)
    process.exitCode = 1
  })

  return child
}

function maybeColorize(line) {
  // If line already contains an ANSI escape, assume it's colored and return as-is.
  if (line.includes('\u001b[')) return line

  // Simple regex to find level tokens like "INFO:" or "WARNING:" and color them.
  return line
    .replace(/\bINFO\b:?/, `${colors.reset}\u001b[32mINFO\u001b[0m:`)
    .replace(/\bWARNING\b:?/, `${colors.reset}\u001b[33mWARNING\u001b[0m:`)
    .replace(/\bERROR\b:?/, `${colors.reset}\u001b[31mERROR\u001b[0m:`)
    .replace(/\bCRITICAL\b:?/, `${colors.reset}\u001b[91mCRITICAL\u001b[0m:`)
}

// --- Stale-backend preflight ---------------------------------------------
// A previous `npm run dev` whose terminal/IDE was closed without a clean Ctrl+C
// can leave an orphaned uvicorn `--reload` worker holding BACKEND_PORT. If that
// happens, the backend we spawn below can't bind the port and piles up as a
// duplicate, while `wait-on` greenlights the frontend against the *stale*
// server (old code). Reclaim the port before starting to prevent that.

function sleepSync(ms) {
  // Block the main thread without async — fine for a short preflight.
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
}

function tryExec(command) {
  try {
    return execSync(command, { stdio: ['ignore', 'pipe', 'ignore'] }).toString()
  } catch {
    return ''
  }
}

function runPowerShell(script) {
  // -EncodedCommand (UTF-16LE base64) sidesteps all cmd/PowerShell quoting.
  const encoded = Buffer.from(script, 'utf16le').toString('base64')
  return tryExec(`powershell -NoProfile -NonInteractive -EncodedCommand ${encoded}`)
}

function parsePids(text) {
  return [...new Set(text.split(/\s+/).map((s) => s.trim()).filter((s) => /^\d+$/.test(s)))]
}

function listListenerPids(port) {
  if (isWindows) {
    const out = tryExec('netstat -ano -p tcp')
    const pids = new Set()
    for (const line of out.split(/\r?\n/)) {
      const match = line.match(/^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$/i)
      if (match && Number(match[1]) === port) pids.add(match[2])
    }
    return [...pids]
  }
  return parsePids(tryExec(`lsof -nP -iTCP:${port} -sTCP:LISTEN -t`))
}

function listBackendPids() {
  // Match the uvicorn invocation so we also catch the `--reload` parent, whose
  // child worker is what actually holds the port (tree-kill needs the parent).
  if (isWindows) {
    return parsePids(
      runPowerShell(
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | " +
          "Where-Object { $_.CommandLine -match 'uvicorn app.api.main:app' } | " +
          'ForEach-Object { $_.ProcessId }'
      )
    )
  }
  return parsePids(tryExec('pgrep -f "uvicorn app.api.main:app"'))
}

function killPidTree(pid) {
  if (isWindows) tryExec(`taskkill /F /T /PID ${pid}`)
  else tryExec(`kill -9 ${pid}`)
}

function reclaimBackendPort() {
  const stale = [...new Set([...listBackendPids(), ...listListenerPids(BACKEND_PORT)])]
  if (stale.length === 0) return

  prefix(
    'backend',
    colors.backend,
    `port ${BACKEND_PORT} already in use — stopping stale uvicorn process(es): ${stale.join(', ')}`
  )
  for (const pid of stale) killPidTree(pid)

  // Wait for the socket to release (orphaned workers can linger briefly).
  for (let i = 0; i < 25; i += 1) {
    if (listListenerPids(BACKEND_PORT).length === 0) break
    sleepSync(200)
  }

  if (listListenerPids(BACKEND_PORT).length > 0) {
    prefix(
      'backend',
      colors.backend,
      `WARNING: port ${BACKEND_PORT} is still in use after cleanup — the backend may fail to start. Free it manually and retry.`
    )
  } else {
    prefix('backend', colors.backend, `port ${BACKEND_PORT} reclaimed — starting fresh backend.`)
  }
}

reclaimBackendPort()

const pythonExe = resolve(root, '.venv', 'Scripts', 'python.exe')
const backend = streamProcess(
  'backend',
  colors.backend,
  pythonExe,
  ['-m', 'uvicorn', 'app.api.main:app', '--port', '7999', '--reload', '--log-config', 'app/logging.ini']
)

const waitOnBin = isWindows
  ? resolve(root, 'node_modules', '.bin', 'wait-on.cmd')
  : resolve(root, 'node_modules', '.bin', 'wait-on')

const frontend = { child: null }

const waitForBackend = spawn(waitOnBin, ['tcp:127.0.0.1:7999'], {
  cwd: root,
  env: process.env,
  shell: true,
})

createInterface({ input: waitForBackend.stdout }).on('line', (line) => {
  prefix('frontend', colors.frontend, line)
})

createInterface({ input: waitForBackend.stderr }).on('line', (line) => {
  prefix('frontend', colors.frontend, line)
})

waitForBackend.on('exit', (code) => {
  if (code !== 0) {
    process.exitCode = code ?? 1
    return
  }

  frontend.child = spawn('npm', ['run', 'dev', '--prefix', 'frontend'], {
    cwd: root,
    env: process.env,
    shell: true,
  })

  createInterface({ input: frontend.child.stdout }).on('line', (line) => {
    prefix('frontend', colors.frontend, line)
  })

  createInterface({ input: frontend.child.stderr }).on('line', (line) => {
    prefix('frontend', colors.frontend, line)
  })

  frontend.child.on('exit', (frontendCode) => {
    if (frontendCode && frontendCode !== 0) {
      process.exitCode = frontendCode
    }
  })
})

function shutdown(signal) {
  for (const child of [backend, waitForBackend, frontend.child]) {
    if (!child) continue
    try {
      child.kill(signal)
    } catch {
      // already gone
    }
    // `child.kill` only signals the direct child; uvicorn's `--reload` worker
    // (and vite's child processes) are spawned as a subtree and would otherwise
    // be orphaned — holding BACKEND_PORT until the next run's preflight. Tree-
    // kill on Windows so we don't leak them on exit.
    if (isWindows && child.pid) killPidTree(child.pid)
  }
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    shutdown(signal)
    process.exit(0)
  })
}