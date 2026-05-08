import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { createInterface } from 'node:readline'

const root = resolve(process.cwd())
const isWindows = process.platform === 'win32'
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
  backend.kill(signal)
  waitForBackend.kill(signal)
  if (frontend.child) {
    frontend.child.kill(signal)
  }
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    shutdown(signal)
    process.exit(0)
  })
}