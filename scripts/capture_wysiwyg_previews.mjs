#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createReadStream, existsSync } from 'node:fs';
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const scriptPath = fileURLToPath(import.meta.url);
const mobileRoot = resolve(scriptPath, '..', '..');
const outputDir = join(mobileRoot, 'build', 'wysiwyg-preview');
const webBuildDir = join(mobileRoot, 'build', 'web');

const flavors = ['coolshow', 'hongguo', 'douyin', 'hippo', 'reelshort'];
const screens = [
  'splash',
  'auth',
  'home',
  'catalog',
  'detail',
  'player',
  'unlock',
  'wallet',
];
const capturePlan = flavors.flatMap((flavor) => (
  screens.map((screen) => ({ flavor, screen, fileName: `${flavor}-${screen}.png` }))
));

function parseArgs(argv) {
  const options = {
    skipBuild: false,
    port: 51236,
    settleMs: 2500,
    minSizeBytes: 20000,
    flavorFilter: new Set(flavors),
    screenFilter: null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else if (arg === '--skip-build') {
      options.skipBuild = true;
    } else if (arg === '--port') {
      options.port = Number(argv[++index]);
    } else if (arg === '--settle-ms') {
      options.settleMs = Number(argv[++index]);
    } else if (arg === '--min-size-bytes') {
      options.minSizeBytes = Number(argv[++index]);
    } else if (arg === '--flavors') {
      options.flavorFilter = new Set(String(argv[++index]).split(',').map((item) => item.trim()).filter(Boolean));
    } else if (arg === '--screens') {
      options.screenFilter = new Set(String(argv[++index]).split(',').map((item) => item.trim()).filter(Boolean));
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return options;
}

function usage() {
  return [
    'Usage: node scripts/capture_wysiwyg_previews.mjs [options]',
    '',
    'Options:',
    '  --skip-build           Capture from the existing build/web output.',
    '  --flavors coolshow,... Restrict flavors. Default: all template flavors.',
    '  --screens home,...     Restrict screens. Default: all eight MVP screens.',
    '  --port 51236           Local static server port.',
    '  --settle-ms 2500       Wait after page load before screenshot.',
    '  --min-size-bytes 20000 Fail captures that are likely blank.',
  ].join('\n');
}

async function resolveFlutterBin() {
  const result = await runCommand('bash', [join(mobileRoot, 'scripts', 'resolve_flutter_bin.sh')], {
    cwd: mobileRoot,
    capture: true,
  });
  return result.stdout.trim();
}

function runCommand(command, args, { cwd = mobileRoot, env = process.env, capture = false } = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd,
      env,
      stdio: capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    });
    let stdout = '';
    let stderr = '';
    if (capture) {
      child.stdout.on('data', (chunk) => {
        stdout += chunk.toString();
      });
      child.stderr.on('data', (chunk) => {
        stderr += chunk.toString();
      });
    }
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) {
        resolvePromise({ stdout, stderr });
      } else {
        const detail = capture ? `\n${stdout}${stderr}` : '';
        reject(new Error(`${command} ${args.join(' ')} exited with ${code}${detail}`));
      }
    });
  });
}

async function buildWeb(flutterBin, flavor) {
  await runCommand(flutterBin, [
    'build',
    'web',
    '-t',
    'lib/preview_main.dart',
    '--dart-define',
    `APP_FLAVOR=${flavor}`,
    '--release',
  ]);
}

function mimeType(path) {
  const ext = extname(path).toLowerCase();
  if (ext === '.html') return 'text/html; charset=utf-8';
  if (ext === '.js') return 'text/javascript; charset=utf-8';
  if (ext === '.json') return 'application/json; charset=utf-8';
  if (ext === '.wasm') return 'application/wasm';
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.svg') return 'image/svg+xml';
  return 'application/octet-stream';
}

function startStaticServer(root, port) {
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url || '/', `http://127.0.0.1:${port}`);
      let path = decodeURIComponent(url.pathname);
      if (path === '/') path = '/index.html';
      const filePath = resolve(root, `.${path}`);
      if (!filePath.startsWith(root)) {
        response.writeHead(403);
        response.end('Forbidden');
        return;
      }
      const fileStat = await stat(filePath);
      if (!fileStat.isFile()) {
        response.writeHead(404);
        response.end('Not found');
        return;
      }
      response.writeHead(200, {
        'Content-Type': mimeType(filePath),
        'Cache-Control': 'no-store',
      });
      createReadStream(filePath).pipe(response);
    } catch {
      response.writeHead(404);
      response.end('Not found');
    }
  });
  return new Promise((resolvePromise, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => {
      server.off('error', reject);
      resolvePromise(server);
    });
  });
}

async function sha256(path) {
  return new Promise((resolvePromise, reject) => {
    const digest = createHash('sha256');
    const stream = createReadStream(path);
    stream.on('data', (chunk) => digest.update(chunk));
    stream.on('error', reject);
    stream.on('end', () => resolvePromise(digest.digest('hex')));
  });
}

async function pngDimensions(path) {
  const file = await readFile(path);
  if (file.length < 24 || file.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') {
    return { width: null, height: null };
  }
  return {
    width: file.readUInt32BE(16),
    height: file.readUInt32BE(20),
  };
}

function systemChromePath() {
  const candidates = [
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ].filter(Boolean);
  return candidates.find((candidate) => existsSync(candidate)) || null;
}

async function launchBrowser() {
  const executablePath = systemChromePath();
  if (executablePath) {
    try {
      return await chromium.launch({ executablePath });
    } catch (error) {
      console.warn(
        `System Chrome failed to launch for WYSIWYG capture; falling back to bundled Chromium: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
  }
  return chromium.launch();
}

async function waitForFlutterView(page, capture) {
  await page.waitForFunction(
    () => {
      const flutterView = document.querySelector('flutter-view');
      if (!flutterView) {
        return false;
      }
      const rect = flutterView.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    },
    null,
    { timeout: 90000 },
  ).catch((error) => {
    throw new Error(
      `Timed out waiting for Flutter view while capturing ${capture.flavor}/${capture.screen}: ${error.message}`,
    );
  });
}

async function captureScreen(browser, port, capture, options) {
  const pageErrors = [];
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });
  page.on('console', (message) => {
    if (message.type() === 'error') {
      pageErrors.push(message.text());
    }
  });
  await page.goto(`http://127.0.0.1:${port}/?screen=${encodeURIComponent(capture.screen)}`, {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await waitForFlutterView(page, capture);
  await page.waitForTimeout(options.settleMs);
  const target = join(outputDir, capture.fileName);
  await page.screenshot({ path: target, fullPage: false });
  await context.close();
  if (pageErrors.length) {
    throw new Error(
      `Browser errors while capturing ${capture.flavor}/${capture.screen}: ${pageErrors.join(' | ')}`,
    );
  }
  const dimensions = await pngDimensions(target);
  const fileStat = await stat(target);
  if (dimensions.width !== 780 || dimensions.height !== 1688) {
    throw new Error(
      `Unexpected screenshot dimensions for ${capture.fileName}: ${dimensions.width}x${dimensions.height}`,
    );
  }
  if (fileStat.size < options.minSizeBytes) {
    throw new Error(
      `Screenshot ${capture.fileName} is only ${fileStat.size} bytes; likely blank or not settled.`,
    );
  }
  return {
    ...capture,
    path: relative(mobileRoot, target),
    width: dimensions.width,
    height: dimensions.height,
    sizeBytes: fileStat.size,
    sha256: await sha256(target),
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }
  if (!Number.isFinite(options.port) || options.port <= 0) {
    throw new Error('Invalid --port value.');
  }
  if (!Number.isFinite(options.settleMs) || options.settleMs < 0) {
    throw new Error('Invalid --settle-ms value.');
  }
  if (!Number.isFinite(options.minSizeBytes) || options.minSizeBytes < 0) {
    throw new Error('Invalid --min-size-bytes value.');
  }
  const selected = capturePlan.filter((capture) => {
    if (!options.flavorFilter.has(capture.flavor)) return false;
    if (options.screenFilter && !options.screenFilter.has(capture.screen)) return false;
    return true;
  });
  if (selected.length === 0) {
    throw new Error('No WYSIWYG captures selected.');
  }
  await mkdir(outputDir, { recursive: true });
  const flutterBin = await resolveFlutterBin();
  const browser = await launchBrowser();
  const captures = [];
  try {
    for (const flavor of flavors.filter((flavor) => selected.some((capture) => capture.flavor === flavor))) {
      if (!options.skipBuild) {
        await buildWeb(flutterBin, flavor);
      }
      const server = await startStaticServer(webBuildDir, options.port);
      try {
        for (const capture of selected.filter((item) => item.flavor === flavor)) {
          console.log(`Capturing ${capture.flavor}/${capture.screen} -> ${capture.fileName}`);
          captures.push(await captureScreen(browser, options.port, capture, options));
        }
      } finally {
        await new Promise((resolveServer) => server.close(resolveServer));
      }
    }
  } finally {
    await browser.close();
  }
  const manifestPath = join(outputDir, 'wysiwyg-preview-manifest.json');
  const manifest = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString().replace(/\.\d{3}Z$/, '+00:00'),
    packageType: 'mobile_wysiwyg_preview_captures',
    source: 'flutter_web_release_runtime_capture',
    flutterBin,
    skipBuild: options.skipBuild,
    viewport: { width: 390, height: 844, deviceScaleFactor: 2 },
    captureCommand: 'node scripts/capture_wysiwyg_previews.mjs',
    minSizeBytes: options.minSizeBytes,
    requiredFlavorCount: flavors.length,
    requiredScreenCount: screens.length,
    captureCount: captures.length,
    captures,
    publicBoundary: 'Release-rendered Flutter Web screenshots only; no signing material, provider credentials, tenant secrets, Cloudflare tokens, or private keys.',
  };
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  console.log(`Wrote ${relative(mobileRoot, manifestPath)} (${captures.length} captures)`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
