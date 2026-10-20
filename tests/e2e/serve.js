// Static server for the browser tests. Mirrors GitHub Pages: a directory URL without the
// trailing slash redirects to it, a directory serves its index.html, anything else that is
// missing gets 404.html with status 404.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', '..', 'site');
const PORT = Number(process.env.PORT || 4173);
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.ics': 'text/calendar; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
};

/* The file's bytes, or null for a directory: one open, then fstat and read on that descriptor, so nothing
   can swap the file between the check and the read. */
function readFile(file) {
  const fd = fs.openSync(file, 'r');
  try {
    return fs.fstatSync(fd).isDirectory() ? null : fs.readFileSync(fd);
  } finally {
    fs.closeSync(fd);
  }
}

http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  let file = path.join(ROOT, rel);
  if (file !== ROOT && !file.startsWith(ROOT + path.sep)) {
    res.writeHead(400).end();
    return;
  }
  try {
    let body = readFile(file);
    if (body === null) {
      if (!rel.endsWith('/')) {
        res.writeHead(301, { Location: rel + '/' }).end();
        return;
      }
      file = path.join(file, 'index.html');
      body = readFile(file);
      if (body === null) throw new Error('not a file');
    }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' }).end(body);
  } catch {
    res.writeHead(404, { 'Content-Type': TYPES['.html'] }).end(fs.readFileSync(path.join(ROOT, '404.html')));
  }
}).listen(PORT, '127.0.0.1', () => console.log(`serving ${ROOT} on http://127.0.0.1:${PORT}`));
